[CmdletBinding()]
param(
    [switch]$ConfirmLocalReset,
    [ValidateSet('TEST')][string]$Environment = 'TEST',
    [string]$ContainerName = 'data-agent-postgres',
    [string]$DatabaseName = 'data_agent_test',
    [string]$DatabaseUser = 'data_agent'
)

if (-not $ConfirmLocalReset) { throw 'Refusing destructive reset. Re-run with -ConfirmLocalReset for the local/test fixture only.' }
if ($DatabaseName -ne 'data_agent_test' -or $ContainerName -ne 'data-agent-postgres') {
    throw 'Safety guard: reset is restricted to the isolated local Docker data_agent_test database.'
}
. (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
$mutex = [System.Threading.Mutex]::new($false, 'Global\DataAgentControlPlaneFixtureReset')
$lockAcquired = $false
try {
    $lockAcquired = $mutex.WaitOne(0)
    if (-not $lockAcquired) { throw 'Another data_agent_test reset is already running; concurrent destructive resets are refused.' }
    Assert-LocalControlPlaneMaintenanceTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
    docker exec $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d postgres -c "DROP DATABASE IF EXISTS $DatabaseName WITH (FORCE)"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to drop the isolated test database.' }
    docker exec $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d postgres -c "CREATE DATABASE $DatabaseName"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the isolated test database.' }
    Assert-LocalControlPlaneTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
    & (Join-Path $PSScriptRoot 'Initialize-ControlPlaneTestDatabase.ps1') -Environment TEST -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
    & (Join-Path $PSScriptRoot 'Setup-ControlPlaneFixture.ps1') -Environment TEST -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
    Write-Host 'Isolated data_agent_test database was destroyed, recreated, migrated, and reseeded; audit rows from the previous database were discarded with that database.'
} finally {
    if ($lockAcquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
