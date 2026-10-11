param([string] $ConfigPath, [switch] $SelfTest, [switch] $Preflight)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'MetricsBranchConfig.ps1')
if (!$SelfTest) {
    if (!$ConfigPath) { throw '必须提供 ConfigPath，或使用 SelfTest 运行隔离配置测试' }
    $configuration = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json -AsHashtable
    Assert-MetricsBranchConfig $configuration
    if ($Preflight) {
        $result = Test-MetricsContractPreflight $configuration
        if (!$result.Valid) { throw ('协议预检失败：' + ($result.Errors -join '；')) }
    }
    Write-Output 'PASS：新构建协议配置有效。'
    exit 0
}
# fixture 仅存在内存；禁止把令牌写到文件、URL 或失败诊断。
$secret = [Guid]::NewGuid().ToString('N')
$env:METRICS_CONTRACT_TEST_TOKEN = $secret
try {
    $good = @{
        agentBaseUrl='http://127.0.0.1:8080'; metricPlatformBaseUrl='http://127.0.0.1:8090'; dbtServiceBaseUrl='http://127.0.0.1:8000'
        agentProjectId='project-1'; repository='ssh://git@agent-metrics-git/agent-admin/metrics.git'; branchName='feature/revenue'
        previewBinding='preview'; previewConfigVersion='1'; previewSchemaName='analytics_preview'; productionBinding='production'; productionConfigVersion='1'; productionSchemaName='analytics_production'
        dbtServiceTokenEnvironment='METRICS_CONTRACT_TEST_TOKEN'; platformTokenEnvironment='METRICS_CONTRACT_TEST_TOKEN'
    }
    Assert-MetricsBranchConfig $good
    $cases = @(
        @{ name='旧项目子目录'; mutate={param($c) $c.projectSubdir='.'}; error='projectSubdir' },
        @{ name='旧服务分支身份'; mutate={param($c) $c.branchId='opaque-old'}; error='branchId' },
        @{ name='旧代理模式'; mutate={param($c) $c.mode='service-proxy'}; error='mode' },
        @{ name='缺少preview版本'; mutate={param($c) $c.Remove('previewConfigVersion')}; error='previewConfigVersion' },
        @{ name='缺少正式版本'; mutate={param($c) $c.Remove('productionConfigVersion')}; error='productionConfigVersion' },
        @{ name='缺少预览schema'; mutate={param($c) $c.Remove('previewSchemaName')}; error='previewSchemaName' },
        @{ name='非法正式schema'; mutate={param($c) $c.productionSchemaName='invalid-schema'}; error='productionSchemaName' },
        @{ name='缺少仓库不兜底'; mutate={param($c) $c.Remove('repository')}; error='repository' },
        @{ name='凭据嵌入URL'; mutate={param($c) $c.agentBaseUrl='http://user:password@example.test'}; error='agentBaseUrl' },
        @{ name='预览禁止main'; mutate={param($c) $c.branchName='main'}; error='branchName' },
        @{ name='自动发布hook'; mutate={param($c) $c.hooks=@(@{active=$true})}; error='hooks' },
        @{ name='令牌环境缺失'; mutate={param($c) $c.dbtServiceTokenEnvironment='METRICS_CONTRACT_MISSING_TOKEN'}; error='dbtServiceTokenEnvironment' }
    )
    foreach ($case in $cases) {
        $copy = $good | ConvertTo-Json -Depth 8 | ConvertFrom-Json -AsHashtable
        & $case.mutate $copy | Out-Null
        $caught=$false
        try { Assert-MetricsBranchConfig $copy } catch {
            $caught=$true
            if ($_.Exception.Message -notmatch $case.error -or $_.Exception.Message.Contains($secret)) {
                throw "错误诊断不符合约束：$($case.name)"
            }
        }
        if (!$caught) { throw "预期配置被拒绝：$($case.name)" }
    }
    # 缺少实际schema时必须无效，不允许以健康检查200代替协议检查。
    $calls=[Collections.Generic.List[string]]::new()
    $reader={ param($url,$headers) $calls.Add($url); return @{status='UP'} }.GetNewClosure()
    $observed=Test-MetricsContractPreflight $good $reader
    if ($observed.Valid -or @($calls | Where-Object {$_ -match '/v[12]/projects|/publication'}).Count) {
        throw '旧/未知schema不能通过预检或回退旧路由'
    }
    # 与三端公开路径匹配的schema才通过；只模拟预检读取，不替代真实闭环。
    $validReader={param($url,$headers)
        if($url.EndsWith('/development-config')){return $good}
        if($url -match '/health(?:/ready)?$'){return @{status='UP'}}
        $paths=@{}
        foreach($path in @('/v3/builds','/v3/deployments/current','/v3/query','/v3/query/available-dimensions',
            '/api/v1/agent-sessions/{sessionId}/development/save','/api/v1/agent-sessions/{sessionId}/development/preview',
            '/api/v1/agent-sessions/{sessionId}/development/deliver','/api/v3/dbt/builds/{buildId}/catalog','/api/v3/dbt/builds/{buildId}/queries')){$paths[$path]=@{}}
        return @{protocolVersion='build-deployment-v3';paths=$paths}
    }.GetNewClosure()
    if(!(Test-MetricsContractPreflight $good $validReader).Valid){throw '匹配三端schema的配置必须通过预检'}
    $httpShapeReader={param($url,$headers) (&$validReader $url $headers)|ConvertTo-Json -Depth 12|ConvertFrom-Json}.GetNewClosure()
    if(!(Test-MetricsContractPreflight $good $httpShapeReader).Valid){throw '真实HTTP形态的PSCustomObject schema必须通过预检'}
    # 即使绑定版本相同，schema 不一致也可能写入错误的数据环境，必须拦截。
    $mismatchedSchemaReader={param($url,$headers)
        if($url.EndsWith('/development-config')){
            $config=$good.Clone();$config.previewSchemaName='another_preview';return $config
        }
        return &$validReader $url $headers
    }.GetNewClosure()
    if((Test-MetricsContractPreflight $good $mismatchedSchemaReader).Valid){throw '环境schema不一致必须拒绝预检'}
    Write-Output "PASS：有效配置、$($cases.Count) 个无效配置以及协议不匹配拒绝，无凭据输出。"
} finally { Remove-Item Env:METRICS_CONTRACT_TEST_TOKEN }
