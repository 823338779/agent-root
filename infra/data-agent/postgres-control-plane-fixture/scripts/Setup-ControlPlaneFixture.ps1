[CmdletBinding()]
param(
    [ValidateSet('LOCAL', 'TEST')][string]$Environment = 'LOCAL',
    [string]$ContainerName = 'data-agent-postgres',
    [string]$DatabaseName = 'data_agent',
    [string]$DatabaseUser = 'data_agent'
)

$fixtureRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
Assert-LocalControlPlaneTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
Assert-ControlPlaneSchema -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
Invoke-ControlPlaneSql -SqlPath (Join-Path $fixtureRoot '01_seed.sql') -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
Invoke-ControlPlaneSql -SqlPath (Join-Path $fixtureRoot '02_verify_fixture.sql') -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
Write-Host 'Control-plane fixture is loaded and fixture quality checks passed.'
