[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ManagerAdvertiseAddress
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $PSScriptRoot

if ((docker info --format '{{.Swarm.LocalNodeState}}') -ne 'active') {
    docker swarm init --advertise-addr $ManagerAdvertiseAddress
    if ($LASTEXITCODE -ne 0) { throw 'Docker Swarm initialization failed.' }
}

# Stateful services use this explicit label so an application replica is never accidentally pinned.
$nodeName = docker info --format '{{.Name}}'
$nodeId = docker node ls --filter "name=$nodeName" --quiet
if (-not $nodeId) { throw "Unable to resolve the local Swarm node '$nodeName'." }
docker node update --label-add data-agent.stateful=true $nodeId
if ($LASTEXITCODE -ne 0) { throw 'Unable to label the stateful Swarm node.' }

docker stack deploy --compose-file (Join-Path $scriptRoot 'registry-stack.yml') local-registry
if ($LASTEXITCODE -ne 0) { throw 'Local registry deployment failed.' }

Write-Host 'Swarm and local registry are ready. Configure every node to trust the manager LAN address as an insecure registry before pushing application images.'
