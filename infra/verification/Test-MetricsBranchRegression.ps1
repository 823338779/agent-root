param([string] $ConfigPath, [switch] $SelfTest)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'MetricsBranchConfig.ps1')
. (Join-Path $PSScriptRoot '../git/Forgejo-Service.ps1')
# 真实helper的请求序列fixture，不访问任何共享Forgejo；旧URL仅用于退出负向测试。
$script:MetricsCutoverHooks=@(
    @{id=1;active=$true;config=@{url='http://platform/internal/git-sync/events'}},
    @{id=2;active=$true;config=@{url='http://platform/api/dbt/webhooks/forgejo'}},
    @{id=3;active=$true;config=@{url='http://notify/events'}},
    @{id=4;active=$true;config=@{url='http://service/internal/git-branch-events'}}
)
function Invoke-ForgejoApi($Method,$BaseUri,$Path,$Token,$Body) {
    if ($Method -eq 'GET') {return @{StatusCode=200;Data=$script:MetricsCutoverHooks}}
    if ($Method -eq 'PATCH') {
        $hook=$script:MetricsCutoverHooks | Where-Object id -eq ([int]$Path.Split('/')[-1])
        $hook.active=$Body.active; return @{StatusCode=200;Data=$hook}
    }
    throw '切换不允许创建新的发布Webhook'
}
Disable-MetricsPublishingWebhooks 'http://fixture' 'fixture'
Disable-MetricsPublishingWebhooks 'http://fixture' 'fixture'
if ($script:MetricsCutoverHooks.Count -ne 4 -or @($script:MetricsCutoverHooks | Where-Object active).Count -ne 1 -or !$script:MetricsCutoverHooks[2].active) {
    throw '旧发布者未全部停用或误动了无关Webhook'
}
& (Join-Path $PSScriptRoot 'Test-MetricsBranchConfig.ps1') -SelfTest
if ($ConfigPath) {
    $configuration=Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json -AsHashtable
    Assert-MetricsBranchConfig $configuration
    $ready=Test-MetricsContractPreflight $configuration
    if (!$ready.Valid) {throw '三端协议预检不通过，未执行后续检查'}
    # 退出检查只读；未知旧字段的构建请求在协议校验阶段422，不得产生构建。
    $checks=@(
        @{component='service';base=$configuration.dbtServiceBaseUrl;path='/v2/projects'},
        @{component='service';base=$configuration.dbtServiceBaseUrl;path='/v2/projects/retired/releases'},
        @{component='service';base=$configuration.dbtServiceBaseUrl;path='/v2/projects/retired/validations'},
        @{component='service';base=$configuration.dbtServiceBaseUrl;path='/v1/project-runs'},
        @{component='service';base=$configuration.dbtServiceBaseUrl;path='/v1/query-jobs'},
        @{component='service';base=$configuration.dbtServiceBaseUrl;path='/internal/git-branch-events'},
        @{component='agent';base=$configuration.agentBaseUrl;path='/api/v1/git-workspaces'},
        @{component='agent';base=$configuration.agentBaseUrl;path='/api/v1/metric-branches'},
        @{component='platform';base=$configuration.metricPlatformBaseUrl;path='/api/v1/semantic-projects'},
        @{component='platform';base=$configuration.metricPlatformBaseUrl;path='/api/v2/semantic-projects'},
        @{component='platform';base=$configuration.metricPlatformBaseUrl;path='/api/v1/semantic-projects/retired/releases'},
        @{component='platform';base=$configuration.metricPlatformBaseUrl;path='/api/v2/semantic-projects/retired/branches'}
    )
    foreach ($check in $checks) {
        $response=Invoke-WebRequest -Uri ($check.base.TrimEnd('/')+$check.path) -Method Get -Headers (Get-MetricsContractHeaders $configuration $check.component) -MaximumRedirection 0 -SkipHttpErrorCheck -TimeoutSec 20
        if ($response.StatusCode -ne 404) {throw ('旧路由未退出：'+$check.component)}
    }
    # 在完整有效的新请求上仅附加旧字段，避免缺少必填字段造成422假阳性。
    $branches=Invoke-MetricsContractRead ($configuration.agentBaseUrl.TrimEnd('/')+'/api/v1/agent-projects/'+[Uri]::EscapeDataString($configuration.agentProjectId)+'/branches') (Get-MetricsContractHeaders $configuration 'agent')
    $branch=@($branches.items | Where-Object branchName -CEQ $configuration.branchName)
    if($branch.Count-ne 1){throw '负向协议测试需要明确存在的隔离测试分支'}
    $invalid=@{repository=$configuration.repository;branchName=$configuration.branchName;commitSha=$branch[0].headSha;environment='PREVIEW';executionBinding=$configuration.previewBinding;configVersion=$configuration.previewConfigVersion;deploymentPolicy='NONE';idempotencyKey=[Guid]::NewGuid().ToString();projectId='retired'} | ConvertTo-Json
    $response=Invoke-WebRequest -Uri ($configuration.dbtServiceBaseUrl.TrimEnd('/')+'/v3/builds') -Method Post -Body $invalid -ContentType 'application/json' -Headers (Get-MetricsContractHeaders $configuration 'service') -MaximumRedirection 0 -SkipHttpErrorCheck -TimeoutSec 20
    if ($response.StatusCode -ne 422) {throw '未知旧字段必须返回422'}
    Write-Output 'PASS：真实三端旧路由404及旧字段422。'
}
Write-Output 'PASS：发布Webhook退出、自检拒绝main冒充预览、无关通知保留；未传ConfigPath时未执行真实HTTP验证。'
