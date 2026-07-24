[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$DatabasePassword,
    [Parameter(Mandatory)]
    [string]$RedisPassword,
    [Parameter(Mandatory)]
    [string]$OllamaBaseUrl,
    [Parameter(Mandatory)]
    [string]$DataAgentAdminPassword,
    [Parameter(Mandatory)]
    [string]$MetricPlatformAdminPassword
)

$ErrorActionPreference = 'Stop'

function New-Base64Key {
    $bytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToBase64String($bytes)
}

function Add-Secret([string]$Name, [string]$Value) {
    docker secret inspect $Name *> $null
    if ($LASTEXITCODE -eq 0) { throw "Swarm secret '$Name' already exists. Do not overwrite a deployed secret; create a versioned name and update the stack deliberately." }
    $Value | docker secret create $Name -
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Swarm secret '$Name'." }
}

$artifactKey = New-Base64Key
$artifactSigningKey = New-Base64Key
$sourceSecretKey = New-Base64Key

$dataAgentConfig = @"
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/data_agent
    username: data_agent
    password: $DatabasePassword
  data:
    redis:
      host: redis
      port: 6379
      username: default
      password: $RedisPassword
  ai:
    ollama:
      base-url: $OllamaBaseUrl
data-agent:
  metric-platform:
    base-url: http://metric-platform-api:8090
    artifact:
      active-key-version: 1
      keys:
        1: $artifactKey
      signing-key: $artifactSigningKey
    secret:
      active-key-version: 1
      keys:
        1: $sourceSecretKey
  single-account:
    password: $DataAgentAdminPassword
  security:
    formal-authentication-configured: true
"@

$metricPlatformConfig = @"
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/metric_platform
    username: data_agent
    password: $DatabasePassword
  data:
    redis:
      host: redis
      port: 6379
      username: default
      password: $RedisPassword
metric-platform:
  identity-auth:
    bootstrap:
      password: $MetricPlatformAdminPassword
"@

Add-Secret 'postgres-password' $DatabasePassword
Add-Secret 'redis-password' $RedisPassword
Add-Secret 'data-agent-application' $dataAgentConfig
Add-Secret 'metric-platform-application' $metricPlatformConfig
Write-Host 'Created Swarm secrets. The values are stored only in Docker Swarm and are not written to the repository.'
