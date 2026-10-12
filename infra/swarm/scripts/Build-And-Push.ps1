[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$LocalRegistry,
    [string]$ImageTag = 'dev'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path

function Build-And-Push([string]$Name, [string]$Dockerfile, [string[]]$BuildArguments = @()) {
    $image = "$LocalRegistry/$Name`:$ImageTag"
    docker build --file (Join-Path $repoRoot $Dockerfile) --tag $image @BuildArguments $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Image build failed: $image" }
    docker push $image
    if ($LASTEXITCODE -ne 0) { throw "Image push failed: $image" }
}

Build-And-Push 'data-agent-api' 'infra\docker\data-agent-api.Dockerfile'
Build-And-Push 'metric-platform-api' 'infra\docker\metric-platform-api.Dockerfile'
Build-And-Push 'data-agent-web' 'infra\docker\data-agent-web.Dockerfile'
Build-And-Push 'metric-platform-web' 'infra\docker\metric-platform-web.Dockerfile'
