[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$DatabasePassword,
    [Parameter(Mandatory)]
    [string]$RedisPassword,
    [Parameter(Mandatory)]
    [string]$OllamaBaseUrl,
    [Parameter(Mandatory)]
    [uri]$DbtServiceBaseUrl,
    [Parameter(Mandatory)]
    [string]$DbtServiceToken,
    [Parameter(Mandatory)]
    [string]$MetricPlatformAdminPassword,
    [switch]$ReuseInfrastructureSecrets
)

$ErrorActionPreference = 'Stop'

function Add-Secret([string]$Name, [string]$Value) {
    docker secret inspect $Name *> $null
    if ($LASTEXITCODE -eq 0) { throw "Swarm secret '$Name' already exists. Do not overwrite a deployed secret; create a versioned name and update the stack deliberately." }
    $Value | docker secret create $Name -
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Swarm secret '$Name'." }
}

# JSON 标量同样是合法 YAML 标量，避免密码中的冒号、引号或换行破坏秘密配置。
if (!$DbtServiceBaseUrl.IsAbsoluteUri -or $DbtServiceBaseUrl.Scheme -notin @('http', 'https')) {
    throw 'dbt-service 地址必须为可从 Swarm 服务访问的绝对 HTTP(S) URL。'
}
$databaseValue = ConvertTo-Json -InputObject $DatabasePassword -Compress
$redisValue = ConvertTo-Json -InputObject $RedisPassword -Compress
$ollamaValue = ConvertTo-Json -InputObject $OllamaBaseUrl -Compress
$dbtUrlValue = ConvertTo-Json -InputObject $DbtServiceBaseUrl.AbsoluteUri.TrimEnd('/') -Compress
$dbtTokenValue = ConvertTo-Json -InputObject $DbtServiceToken -Compress
$adminValue = ConvertTo-Json -InputObject $MetricPlatformAdminPassword -Compress

$dataAgentConfig = @"
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/data_agent_v2
    username: data_agent
    password: $databaseValue
  ai:
    ollama:
      base-url: $ollamaValue
data-agent:
  dbt:
    base-url: $dbtUrlValue
    service-token: $dbtTokenValue
"@

$metricPlatformConfig = @"
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/metric_platform
    username: data_agent
    password: $databaseValue
  data:
    redis:
      host: redis
      port: 6379
      username: default
      password: $redisValue
metric-platform:
  dbt-runtime:
    base-uri: $dbtUrlValue
    service-token: $dbtTokenValue
  identity-auth:
    bootstrap:
      password: $adminValue
"@

# 升级已有栈时显式复用基础设施 secret；数据库与 Redis 密码参数须与原 secret 匹配。
if ($ReuseInfrastructureSecrets) {
    foreach ($name in @('postgres-password', 'redis-password')) {
        docker secret inspect $name *> $null
        if ($LASTEXITCODE -ne 0) { throw "缺少待复用的基础设施 secret：$name" }
    }
} else {
    Add-Secret 'postgres-password' $DatabasePassword
    Add-Secret 'redis-password' $RedisPassword
}
# 新版应用使用独立 secret 名称，旧部署的 secret 不会被原地替换或复用。
Add-Secret 'data-agent-v2-application' $dataAgentConfig
Add-Secret 'metric-platform-v3-application' $metricPlatformConfig
Write-Host 'Created Swarm secrets. The values are stored only in Docker Swarm and are not written to the repository.'
