[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$LocalRegistry,
    [string]$ImageTag = 'dev',
    [Parameter(Mandatory)]
    [uri]$AgentPublicUrl,
    [Parameter(Mandatory)]
    [uri]$MetricPlatformPublicUrl
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path

# 浏览器地址在 Vite 构建时固化，必须是用户浏览器能够访问的 HTTP(S) 地址。
foreach ($url in @($AgentPublicUrl, $MetricPlatformPublicUrl)) {
    if (!$url.IsAbsoluteUri -or $url.Scheme -notin @('http', 'https')) { throw '公开地址必须为绝对 HTTP(S) URL。' }
}
function Build-And-Push([string]$Name, [string]$Dockerfile, [string[]]$BuildArguments = @()) {
    $image = "$LocalRegistry/$Name`:$ImageTag"
    docker build --file (Join-Path $repoRoot $Dockerfile) --tag $image @BuildArguments $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Image build failed: $image" }
    docker push $image
    if ($LASTEXITCODE -ne 0) { throw "Image push failed: $image" }
}

Build-And-Push 'data-agent-api' 'infra\docker\data-agent-api.Dockerfile'
Build-And-Push 'metric-platform-api' 'infra\docker\metric-platform-api.Dockerfile'
Build-And-Push 'data-agent-web' 'infra\docker\data-agent-web.Dockerfile' @('--build-arg', "VITE_METRIC_PLATFORM_URL=$MetricPlatformPublicUrl")
Build-And-Push 'metric-platform-web' 'infra\docker\metric-platform-web.Dockerfile' @('--build-arg', "VITE_AGENT_URL=$AgentPublicUrl")
