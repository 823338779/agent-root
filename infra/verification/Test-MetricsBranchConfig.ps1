param([string] $ConfigPath, [switch] $SelfTest)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'MetricsBranchConfig.ps1')

if (!$SelfTest) {
    if (!$ConfigPath) { throw '必须提供 ConfigPath，或使用 SelfTest 运行隔离配置测试' }
    $configuration = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json -AsHashtable
    Assert-MetricsBranchConfig $configuration
    Write-Output 'PASS：项目、仓库、目录、事件和发布者配置一致。'
    exit 0
}

# fixture 仅存在内存；实际凭据不写入配置文件，也不输出到测试日志。
$fixtureSecret = [Guid]::NewGuid().ToString('N')
$env:METRICS_BRANCH_TEST_SECRET = $fixtureSecret
try {
    $good = @{
        agent = @{ projectId = 'metrics'; repositoryId = 'agent-admin/metrics'; subdir = '.'; tokenEnvironment = 'METRICS_BRANCH_TEST_SECRET' }
        service = @{ projectId = 'metrics'; repositoryId = 'agent-admin/metrics'; subdir = '.'; eventsEnabled = $true; secretEnvironment = 'METRICS_BRANCH_TEST_SECRET'; tokenEnvironment = 'METRICS_BRANCH_TEST_SECRET'; capabilities = @('branch-development-v1', 'draft-validation-v2') }
        platform = @{ mode = 'service-proxy'; legacyPublisherEnabled = $false }
        hooks = @(@{ active = $true; url = 'http://host.docker.internal:8081/internal/git-branch-events'; events = @('push', 'delete'); secretEnvironment = 'METRICS_BRANCH_TEST_SECRET' })
    }
    Assert-MetricsBranchConfig $good
    $cases = @(
        @{ name = '旧平台 Webhook'; mutate = { param($c) $c.hooks[0].url = 'http://host.docker.internal:8090/api/git/webhook' }; error = 'hooks' },
        @{ name = '两个发布者'; mutate = { param($c) $c.platform.legacyPublisherEnabled = $true }; error = 'legacyPublisherEnabled' },
        @{ name = '错误项目'; mutate = { param($c) $c.agent.projectId = 'other' }; error = 'projectId' },
        @{ name = '一致但错误的业务仓库'; mutate = { param($c) $c.agent.repositoryId = 'test/metrics'; $c.service.repositoryId = 'test/metrics' }; error = 'repositoryId' },
        @{ name = '错误目录'; mutate = { param($c) $c.agent.subdir = 'other' }; error = 'subdir' },
        @{ name = '缺少 Secret'; mutate = { param($c) $c.service.secretEnvironment = 'METRICS_BRANCH_MISSING_SECRET' }; error = 'secretEnvironment' },
        @{ name = '重复事件目标'; mutate = { param($c) $c.hooks += $c.hooks[0] }; error = 'hooks' }
    )
    foreach ($case in $cases) {
        $copy = $good | ConvertTo-Json -Depth 8 | ConvertFrom-Json -AsHashtable
        & $case.mutate $copy
        $caught = $false
        try { Assert-MetricsBranchConfig $copy } catch {
            $caught = $true
            if ($_.Exception.Message -notmatch $case.error -or $_.Exception.Message.Contains($fixtureSecret)) {
                throw "错误诊断不符合约束：$($case.name)"
            }
        }
        if (!$caught) { throw "预期配置被拒绝：$($case.name)" }
    }
    Write-Output 'PASS：有效配置及 7 个错误配置 fixture，无凭据输出。'
} finally {
    Remove-Item Env:METRICS_BRANCH_TEST_SECRET
}
