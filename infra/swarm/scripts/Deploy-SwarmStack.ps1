[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$LocalRegistry,
    [string]$ImageTag = 'dev',
    [switch]$RequireMultipleNodes
)

$ErrorActionPreference = 'Stop'
$stackRoot = Split-Path -Parent $PSScriptRoot
if ((docker info --format '{{.Swarm.LocalNodeState}}') -ne 'active') { throw 'Docker Swarm is not active. Run Initialize-LocalSwarm.ps1 first.' }

$readyNodes = @(docker node ls --format '{{.Status}}' | Where-Object { $_ -eq 'Ready' }).Count
if ($RequireMultipleNodes -and $readyNodes -lt 2) { throw 'At least two Ready Swarm nodes are required by -RequireMultipleNodes.' }
if ($readyNodes -lt 2) { Write-Warning 'Deploying to one Swarm node: application replicas run, but this is not host-failure tolerant.' }

$env:LOCAL_REGISTRY = $LocalRegistry
$env:IMAGE_TAG = $ImageTag
docker stack deploy --with-registry-auth --compose-file (Join-Path $stackRoot 'stack.yml') data-agent
if ($LASTEXITCODE -ne 0) { throw 'Swarm stack deployment failed.' }
docker stack services data-agent
