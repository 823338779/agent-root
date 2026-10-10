[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$swarmRoot = Split-Path -Parent $PSScriptRoot
$stack = Get-Content -LiteralPath (Join-Path $swarmRoot 'stack.yml') -Raw

# 配置静态检查先保护数据库边界，避免新镜像继续写入旧版 Agent 库。
if ($stack -notmatch "datname='data_agent_v2'") { throw '缺少 Agent V2 独立数据库初始化。' }
if ($stack -match 'DATA_AGENT_(SCHEDULER|CLUSTER_EVENTS)') { throw '仍包含旧版 Agent 运行配置。' }
if ($stack -match 'failure_action: rollback') { throw '迁移后不允许自动回退旧二进制。' }

# PowerShell 语法检查覆盖部署入口，但不会运行集群变更或创建密钥。
foreach ($path in Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1') {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($path.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count) { throw "PowerShell 语法错误：$($path.Name)" }
}

# 拦截 Docker 变更命令，实际运行模板生成与镜像参数组装；所有输入均为公开测试值。
$dockerExecutable = (Get-Command docker -CommandType Application | Select-Object -First 1).Source
$script:commands = [System.Collections.Generic.List[object]]::new()
function docker {
    $arguments = @($args)
    $body = @($input) -join "`n"
    $commands.Add(@{ arguments = $arguments; body = $body })
    $global:LASTEXITCODE = if ($arguments[0] -eq 'secret' -and $arguments[1] -eq 'inspect') { 1 } else { 0 }
}
try {
    & (Join-Path $PSScriptRoot 'New-SwarmSecrets.ps1') -DatabasePassword 'test: db' -RedisPassword 'test: redis' `
        -OllamaBaseUrl 'http://ollama.example:11434' -DbtServiceBaseUrl 'http://engine.example:8000' `
        -DbtServiceToken 'test: token' -MetricPlatformAdminPassword 'test: admin' 6>$null
    $created = @($script:commands | Where-Object { $_.arguments[0] -eq 'secret' -and $_.arguments[1] -eq 'create' })
    if ($created.Count -ne 4) { throw '应用和基础设施 secret 数量不符合预期。' }
    $agent = ($created | Where-Object { $_.arguments[2] -eq 'data-agent-v2-application' }).body
    $platform = ($created | Where-Object { $_.arguments[2] -eq 'metric-platform-v3-application' }).body
    if ($agent -notmatch 'postgres:5432/data_agent_v2' -or $agent -match 'single-account|formal-authentication|artifact:') { throw 'Agent secret 仍使用旧配置。' }
    foreach ($configuration in @($agent, $platform)) {
        if ($configuration -notmatch 'http://engine.example:8000' -or $configuration -notmatch 'service-token: "test: token"') { throw '缺少显式 dbt 服务地址或凭据。' }
    }
    if ($platform -notmatch 'base-uri: http://data-agent-api:8080') { throw '平台缺少 Agent 服务地址。' }
    & (Join-Path $PSScriptRoot 'Build-And-Push.ps1') -LocalRegistry 'registry.example:5000' -ImageTag test `
        -AgentPublicUrl 'https://agent.example' -MetricPlatformPublicUrl 'https://metrics.example'
    $builds = @($script:commands | Where-Object { $_.arguments[0] -eq 'build' })
    if ($builds.Count -ne 4) { throw '未构建四个应用镜像。' }
    if (@($builds | Where-Object { $_.arguments -contains 'VITE_AGENT_URL=https://agent.example/' }).Count -ne 1 -or
        @($builds | Where-Object { $_.arguments -contains 'VITE_METRIC_PLATFORM_URL=https://metrics.example/' }).Count -ne 1) { throw 'Web 镜像缺少公开地址构建参数。' }
} finally {
    Remove-Item Function:\docker
}

# 仅执行 Docker 本地配置解析，不接触 daemon、Swarm 集群或真实 secrets。
$previousRegistry = $env:LOCAL_REGISTRY
$previousTag = $env:IMAGE_TAG
try {
    $env:LOCAL_REGISTRY = 'registry.example:5000'
    $env:IMAGE_TAG = 'test'
    & $dockerExecutable stack config --compose-file (Join-Path $swarmRoot 'stack.yml') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'docker stack config 校验失败。' }
} finally {
    $env:LOCAL_REGISTRY = $previousRegistry
    $env:IMAGE_TAG = $previousTag
}
Write-Output 'PASS：Swarm 模板、Vite 构建参数和 docker stack config；未部署或创建真实 secrets。'
