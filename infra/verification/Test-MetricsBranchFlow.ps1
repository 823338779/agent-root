param(
    [Parameter(Mandatory)][uri] $ServiceBaseUri,
    [Parameter(Mandatory)][uri] $PlatformBaseUri,
    [Parameter(Mandatory)][uri] $AgentBaseUri,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]{1,100}$')][string] $ProjectId,
    [Parameter(Mandatory)][guid] $BranchAId,
    [Parameter(Mandatory)][guid] $BranchBId,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string] $ExpectedProductionSha,
    [Parameter(Mandatory)][string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
$checks = [Collections.Generic.List[object]]::new()
$identities = [Collections.Generic.List[object]]::new()
$phase = 'configuration'
$passed = $false

# 不输出服务响应正文、请求凭据或 SQL，只保留断言名称与结果。
function Assert-Flow([bool] $Condition, [string] $Name) {
    $checks.Add(@{ name = $Name; status = $(if ($Condition) { 'PASS' } else { 'FAIL' }) })
    if (!$Condition) { throw 'assertion_failed' }
}

function Read-BranchApi([uri] $Base, [string] $Path, [string] $Method = 'GET', [object] $Body = $null, [switch] $Platform) {
    $headers = @{}
    if ($Platform) { $headers.Authorization = "Bearer $env:METRIC_PLATFORM_ACCESS_TOKEN" }
    $arguments = @{ Uri = $Base.AbsoluteUri.TrimEnd('/') + $Path; Method = $Method; Headers = $headers
        TimeoutSec = 20; MaximumRedirection = 0; SkipHttpErrorCheck = $true }
    if ($null -ne $Body) { $arguments.ContentType = 'application/json'; $arguments.Body = ConvertTo-Json $Body -Depth 8 -Compress }
    try { $response = Invoke-WebRequest @arguments } catch { throw 'api_transport_failed' }
    if ($response.StatusCode -notin @(200, 202)) { throw "api_status_$($response.StatusCode)" }
    if ($response.RawContentLength -gt 2097152) { throw 'api_response_too_large' }
    return $response.Content | ConvertFrom-Json
}

try {
    foreach ($base in @($ServiceBaseUri, $PlatformBaseUri, $AgentBaseUri)) {
        Assert-Flow ($base.Scheme -in @('http', 'https') -and !$base.UserInfo -and !$base.Query) 'base_uri'
    }
    Assert-Flow (![string]::IsNullOrWhiteSpace($env:METRIC_PLATFORM_ACCESS_TOKEN)) 'platform_access_token_present'
    Assert-Flow ($BranchAId -ne $BranchBId) 'distinct_preview_branches'
    $serviceRoot = "/v2/projects/$ProjectId/branches"
    $platformRoot = "/api/v2/semantic-projects/$ProjectId/branches"
    $phase = 'branches'
    $serviceBranches = @(Read-BranchApi $ServiceBaseUri $serviceRoot)
    $platformBranches = @(Read-BranchApi $PlatformBaseUri $platformRoot -Platform)
    $agentBranches = @(Read-BranchApi $AgentBaseUri '/api/v1/metric-branches')
    $production = @($serviceBranches | Where-Object mode -eq 'PRODUCTION')
    Assert-Flow ($production.Count -eq 1) 'one_production_branch'
    $ids = @($production[0].branchId, $BranchAId.ToString(), $BranchBId.ToString())
    # main 不能作为开发分支参数，否则重复检查同一分支会产生三分支通过的假证据。
    Assert-Flow (@($ids | Select-Object -Unique).Count -eq 3) 'three_distinct_branch_ids'
    foreach ($id in $ids) {
        $phase = 'branch_identity'
        $branch = @($serviceBranches | Where-Object branchId -eq $id)
        Assert-Flow ($branch.Count -eq 1 -and $branch[0].projectId -ceq $ProjectId -and $branch[0].status -ceq 'ACTIVE') 'registered_active_branch'
        $expectedMode = if ($id -eq $production[0].branchId) { 'PRODUCTION' } else { 'PREVIEW' }
        Assert-Flow ($branch[0].mode -ceq $expectedMode) 'branch_environment_mode'
        foreach ($listing in @(@{ values = $platformBranches }, @{ values = $agentBranches })) {
            $other = @($listing.values | Where-Object branchId -eq $id)
            Assert-Flow ($other.Count -eq 1 -and $other[0].gitRef -ceq $branch[0].gitRef -and $other[0].projectId -ceq $ProjectId) 'three_service_branch_identity'
        }
        $path = "$serviceRoot/$id"
        $proxy = "$platformRoot/$id"
        $publication = Read-BranchApi $ServiceBaseUri "$path/publication"
        Assert-Flow ($publication.capabilities -contains 'branch-development-v1') 'service_branch_capability'
        $active = $publication.activePublication
        Assert-Flow ($null -ne $active -and $active.state -ceq 'PUBLISHED' -and $active.branchId -ceq $id) 'active_release_identity'
        $release = $active.releaseId
        if ($id -eq $production[0].branchId) { Assert-Flow ($active.sourceSha -ceq $ExpectedProductionSha) 'production_sha_unchanged' }
        $identities.Add(@{ projectId = $ProjectId; branchId = $id; releaseId = $release; sourceSha = $active.sourceSha })
        $phase = 'fixed_catalog'
        $catalog = Read-BranchApi $ServiceBaseUri "$path/releases/$release/catalog?kind=METRIC&size=200"
        $proxyCatalog = Read-BranchApi $PlatformBaseUri "$proxy/releases/$release/catalog?kind=METRIC&size=200" -Platform
        Assert-Flow ($catalog.releaseId -ceq $release -and $proxyCatalog.releaseId -ceq $release) 'fixed_catalog_release'
        Assert-Flow ($catalog.total -eq @($catalog.resources).Count -and $catalog.total -le 200) 'bounded_complete_metric_catalog'
        $resourceIds = @($catalog.resources.resourceId | Sort-Object)
        $proxyIds = @($proxyCatalog.resources.resourceId | Sort-Object)
        Assert-Flow (($resourceIds -join ',') -ceq ($proxyIds -join ',')) 'proxy_catalog_identity'
        $metric = @($catalog.resources | Where-Object { $_.capabilities -contains 'QUERY' }) | Select-Object -First 1
        Assert-Flow ($null -ne $metric) 'queryable_metric_present'
        $phase = 'fixed_query'
        $body = @{ releaseId = $release; idempotencyKey = [Guid]::NewGuid().ToString('N'); mode = 'QUERY'; metricResourceIds = @($metric.resourceId); limit = 10 }
        $receipt = Read-BranchApi $PlatformBaseUri "$proxy/queries" 'POST' $body -Platform
        # 通过同一协议键从服务恢复原任务，证明代理未改写查询身份。
        $replay = Read-BranchApi $ServiceBaseUri "$path/queries" 'POST' $body
        Assert-Flow ($receipt.queryId -ceq $replay.queryId -and $receipt.releaseId -ceq $release) 'same_key_same_query'
        $deadline = [DateTime]::UtcNow.AddSeconds(180)
        do {
            $query = Read-BranchApi $ServiceBaseUri "$path/queries/$($receipt.queryId)"
            if ($query.state -in @('READY', 'FAILED', 'CANCELLED')) { break }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $deadline)
        Assert-Flow ($query.state -ceq 'READY' -and $query.releaseId -ceq $release -and $query.branchId -ceq $id) 'query_completed_in_fixed_context'
        $proxyQuery = Read-BranchApi $PlatformBaseUri "$proxy/queries/$($receipt.queryId)" -Platform
        Assert-Flow ((ConvertTo-Json $query.rows -Depth 8 -Compress) -ceq (ConvertTo-Json $proxyQuery.rows -Depth 8 -Compress)) 'proxy_query_values_equal_service'
        if ($branch[0].latestReleaseId -and $branch[0].latestReleaseId -ne $release) {
            $latest = Read-BranchApi $ServiceBaseUri "$path/releases/$($branch[0].latestReleaseId)"
            Assert-Flow ($latest.state -ne 'PUBLISHED') 'latest_unpublished_keeps_available_release'
        }
    }
    $passed = $true
} catch {
    # 外部异常文本可能包含地址或身份信息，报告只给出固定阶段码。
    $checks.Add(@{ name = $phase; status = 'FAIL'; reason = '请检查该阶段的服务状态与上方断言，响应正文未记录' })
} finally {
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $report = @{ passed = $passed; scope = '已存在的 main/A/B 三服务目录与查询一致性；不代表 A01-A18 全部验收'
        identities = @($identities.ToArray()); checks = @($checks.ToArray()); recordedAt = [DateTime]::UtcNow.ToString('o') }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'branch-flow.json') -Encoding utf8
}
if (!$passed) { Write-Error '分支聚合验收失败或必需输入缺失，详见 branch-flow.json' -ErrorAction Continue; exit 1 }
Write-Output 'PASS：已存在 main/A/B 的三服务目录、固定查询与代理结果一致；完整业务验收仍需 A01-A18 场景证据。'
