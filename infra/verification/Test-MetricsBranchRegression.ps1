param(
    [ValidateSet('SelfTest', 'Webhook', 'MainAsA', 'MainAsB')][string] $Mode = 'SelfTest',
    [string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'

# 子进程隔离脚本的 exit 行为；fixture 无网络请求，不接触实际仓库或凭据。
if ($Mode -eq 'SelfTest') {
    $root = Join-Path $PSScriptRoot '../../tmp'
    $directory = Join-Path $root ('branch-regression-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $failures = @()
    foreach ($case in @('Webhook', 'MainAsA', 'MainAsB')) {
        $output = Join-Path $directory $case
        & pwsh -NoProfile -File $PSCommandPath -Mode $case -OutputDirectory $output *> (Join-Path $directory "$case.log")
        $code = $LASTEXITCODE
        if ($case -eq 'Webhook') {
            if ($code -ne 0) { $failures += $case }
        } else {
            $report = Get-Content (Join-Path $output 'branch-flow.json') -Raw | ConvertFrom-Json
            $rejected = @($report.checks | Where-Object { $_.name -eq 'three_distinct_branch_ids' -and $_.status -eq 'FAIL' })
            if ($code -eq 0 -or $report.passed -or $rejected.Count -ne 1) { $failures += $case }
        }
    }
    if ($failures.Count) { throw "回归未通过：$($failures -join ', ')" }
    Write-Output 'PASS：实际旧 Webhook 停用、无关通知保留、main 不能冒充 A/B。'
    exit 0
}

if ($Mode -eq 'Webhook') {
    . (Join-Path $PSScriptRoot '../git/Forgejo-Service.ps1')
    $global:MetricsBranchFixtureHooks = @(
        @{ id = 1; active = $true; config = @{ url = 'http://platform/internal/git-sync/events' } },
        @{ id = 2; active = $true; config = @{ url = 'http://platform/api/dbt/webhooks/forgejo' } },
        @{ id = 3; active = $true; config = @{ url = 'http://notify/events' } }
    )
    # API fixture 执行真实 helper 的 GET/PATCH/POST 序列，不模拟 helper 的判断。
    function Invoke-ForgejoApi($Method, $BaseUri, $Path, $Token, $Body) {
        if ($Method -eq 'GET') { return @{ StatusCode = 200; Data = $global:MetricsBranchFixtureHooks } }
        if ($Method -eq 'PATCH') {
            $id = [int]($Path.Split('/')[-1])
            $hook = $global:MetricsBranchFixtureHooks | Where-Object id -eq $id
            foreach ($key in $Body.Keys) { $hook[$key] = $Body[$key] }
            return @{ StatusCode = 200; Data = $hook }
        }
        if ($Method -eq 'POST') {
            $hook = $Body.Clone(); $hook.id = 4
            $global:MetricsBranchFixtureHooks += $hook
            return @{ StatusCode = 201; Data = $hook }
        }
        throw '未预期的 fixture API 调用'
    }
    $target = 'http://service/internal/git-branch-events'
    Ensure-MetricsBranchWebhook 'http://forgejo' 'fixture-token' $target 'fixture-secret'
    Ensure-MetricsBranchWebhook 'http://forgejo' 'fixture-token' $target 'fixture-secret'
    if ($global:MetricsBranchFixtureHooks[0].active -or $global:MetricsBranchFixtureHooks[1].active) { throw '旧发布通知未停用' }
    if (!$global:MetricsBranchFixtureHooks[2].active) { throw '无关通知被错误停用' }
    $publishers = @($global:MetricsBranchFixtureHooks | Where-Object { $_.active -and $_.config.url -eq $target })
    if ($publishers.Count -ne 1 -or $global:MetricsBranchFixtureHooks.Count -ne 4) { throw '重复接线产生额外通知' }
    exit 0
}

# 其余接口均提供可成功验证的完整响应，旧脚本会把 main 重复验证并误报 PASS。
$global:MetricsBranchFixtureProduction = '10000000-0000-0000-0000-000000000001'
$global:MetricsBranchFixturePreview = '10000000-0000-0000-0000-000000000002'
$global:MetricsBranchFixtureSha = 'a' * 40
function Invoke-WebRequest([uri] $Uri, $Method, $Headers, $TimeoutSec, $MaximumRedirection,
    $SkipHttpErrorCheck, $ContentType, $Body) {
    $path = $Uri.AbsolutePath
    $branch = if ($path.Contains($global:MetricsBranchFixturePreview)) { $global:MetricsBranchFixturePreview } else { $global:MetricsBranchFixtureProduction }
    $release = 'release-' + $branch
    if ($path.EndsWith('/branches') -or $path.EndsWith('/metric-branches')) {
        $data = @(
            @{ projectId = 'metrics'; branchId = $global:MetricsBranchFixtureProduction; mode = 'PRODUCTION'; status = 'ACTIVE'; gitRef = 'refs/heads/main' },
            @{ projectId = 'metrics'; branchId = $global:MetricsBranchFixturePreview; mode = 'PREVIEW'; status = 'ACTIVE'; gitRef = 'refs/heads/dev' }
        )
    } elseif ($path.EndsWith('/publication')) {
        $data = @{ capabilities = @('branch-development-v1'); activePublication = @{ branchId = $branch; releaseId = $release; state = 'PUBLISHED'; sourceSha = $global:MetricsBranchFixtureSha } }
    } elseif ($path.EndsWith('/catalog')) {
        $data = @{ releaseId = $release; total = 1; resources = @(@{ resourceId = 'metric'; capabilities = @('QUERY') }) }
    } elseif ($path.EndsWith('/queries')) {
        $data = @{ queryId = 'query'; releaseId = $release }
    } elseif ($path.EndsWith('/queries/query')) {
        $data = @{ branchId = $branch; releaseId = $release; state = 'READY'; rows = @(@(1)) }
    } else { throw '未预期的 fixture API 路径' }
    $content = ConvertTo-Json -InputObject $data -Depth 10 -Compress
    return @{ StatusCode = 200; RawContentLength = $content.Length; Content = $content }
}
$env:METRIC_PLATFORM_ACCESS_TOKEN = 'fixture-token'
$first = if ($Mode -eq 'MainAsA') { $global:MetricsBranchFixtureProduction } else { $global:MetricsBranchFixturePreview }
$second = if ($Mode -eq 'MainAsB') { $global:MetricsBranchFixtureProduction } else { $global:MetricsBranchFixturePreview }
& (Join-Path $PSScriptRoot 'Test-MetricsBranchFlow.ps1') -ServiceBaseUri http://service `
    -PlatformBaseUri http://platform -AgentBaseUri http://agent -ProjectId metrics `
    -BranchAId $first -BranchBId $second -ExpectedProductionSha $global:MetricsBranchFixtureSha -OutputDirectory $OutputDirectory
exit $LASTEXITCODE
