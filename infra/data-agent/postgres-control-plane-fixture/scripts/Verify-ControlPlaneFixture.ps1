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
Invoke-ControlPlaneSql -SqlPath (Join-Path $fixtureRoot '02_verify_fixture.sql') -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
Invoke-ControlPlaneSql -SqlPath (Join-Path $fixtureRoot '03_verify_negative_constraints.sql') -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
$verifySql = [System.IO.File]::ReadAllText((Join-Path $fixtureRoot '02_verify_fixture.sql'))
$mismatchSql = "BEGIN; DELETE FROM data_source_policy WHERE id = '80000000-0000-0000-0000-000000000001';`n$verifySql`nROLLBACK;"
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $mismatchOutput = $mismatchSql | docker exec -i $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d $DatabaseName 2>&1
    $mismatchExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
if ($mismatchExitCode -eq 0) {
    throw 'Fail-closed regression failed: an intentional fixture row-count mismatch was not rejected.'
}
if (($mismatchOutput | Out-String) -notmatch 'fixture row count mismatch') {
    throw 'Fail-closed regression failed for an unexpected reason; expected fixture row count mismatch.'
}

$policyCount = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM data_source_policy WHERE id BETWEEN '80000000-0000-0000-0000-000000000001' AND '80000000-0000-0000-0000-000000000002'" 2>$null
if ($LASTEXITCODE -ne 0 -or ($policyCount | Out-String).Trim() -ne '2') {
    throw 'Intentional row-count drift test left fixture data modified.'
}

Write-Host 'Intentional fixture row-count drift produced the expected fixture row count mismatch, exited nonzero, and rolled back.'
Write-Host 'Control-plane fixture and all negative constraint checks passed.'
