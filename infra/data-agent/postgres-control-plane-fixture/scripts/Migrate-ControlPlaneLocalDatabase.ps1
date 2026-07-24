[CmdletBinding()]
param(
    [ValidateSet('LOCAL')][string]$Environment = 'LOCAL',
    [string]$ContainerName = 'data-agent-postgres',
    [string]$DatabaseName = 'data_agent',
    [string]$DatabaseUser = 'data_agent',
    [switch]$ConfirmLegacyV3Repair
)

$ErrorActionPreference = 'Stop'
if ($ContainerName -ne 'data-agent-postgres' -or $DatabaseName -ne 'data_agent') {
    throw 'Safety guard: controlled baseline is restricted to the local Docker data_agent database.'
}
. (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
Assert-LocalControlPlaneTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser

$history = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT to_regclass('public.flyway_schema_history')"
if (($history | Out-String).Trim() -ne 'flyway_schema_history') {
    $unexpectedTables = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('agent_sessions','agent_audit_records','agent_accounts') ORDER BY tablename"
    if (($unexpectedTables | Out-String).Trim()) {
        throw "Refusing controlled baseline: unexpected pre-Flyway tables exist: $unexpectedTables"
    }
}
else {
    $v3Checksum = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT checksum FROM flyway_schema_history WHERE version='3' AND description='lock down audit event' AND success=true" 2>$null
    $legacyRoleCount = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM pg_roles WHERE rolname='data_agent_app'" 2>$null
    if ($ConfirmLegacyV3Repair) {
        & (Join-Path $PSScriptRoot 'Repair-ControlPlaneLocalV3.ps1') -Environment LOCAL -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser -ConfirmLegacyV3Repair
    } elseif (($v3Checksum | Out-String).Trim() -eq '1550874236' -or ($legacyRoleCount | Out-String).Trim() -eq '1') {
        throw 'Legacy V3 or cleanup-pending state detected. Re-run with -ConfirmLegacyV3Repair for guarded reconciliation.'
    } elseif (($v3Checksum | Out-String).Trim() -ne '-1821703590' -or ($legacyRoleCount | Out-String).Trim() -ne '0') {
        throw 'Unknown V3 checksum detected; refusing automatic migration or repair.'
    }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$javaHome = Join-Path $projectRoot '.tools\jdk-21'
$java = Join-Path $javaHome 'bin\java.exe'
$env:JAVA_HOME = $javaHome
$env:Path = "$javaHome\bin;$env:Path"
Push-Location $projectRoot
try {
    .\backend\mvnw.cmd -f .\backend\pom.xml -pl agent-api -am package -DskipTests
    if ($LASTEXITCODE -ne 0) { throw 'Backend package build failed.' }
    $previousUrl = $env:DATA_AGENT_DB_URL
    $previousProfiles = $env:SPRING_PROFILES_ACTIVE
    $env:DATA_AGENT_DB_URL = 'jdbc:postgresql://localhost:5432/data_agent'
    $env:SPRING_PROFILES_ACTIVE = 'local'
    if (Get-NetTCPConnection -LocalPort 18082 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Validation port 18082 is already in use; refusing readiness verification against an unrelated process.'
    }
    $process = Start-Process -FilePath $java -ArgumentList @('-jar', (Join-Path $projectRoot 'backend\agent-api\target\agent-api-0.1.0-SNAPSHOT-exec.jar'), '--server.port=18082') -PassThru -WindowStyle Hidden
    try {
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 1
            if ($process.HasExited) { throw 'Backend exited before controlled local Flyway migration completed.' }
            try {
                $health = Invoke-RestMethod -Uri 'http://127.0.0.1:18082/actuator/health/readiness' -TimeoutSec 2
                if ($health.status -eq 'UP') { break }
            } catch { }
            if ($attempt -eq 59) { throw 'Timed out waiting for controlled local Flyway migration.' }
        }
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
        $env:DATA_AGENT_DB_URL = $previousUrl
        $env:SPRING_PROFILES_ACTIVE = $previousProfiles
    }
} finally {
    Pop-Location
}

Assert-ControlPlaneSchema -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
$canonicalHistory = docker exec $ContainerName psql -X -At -F '|' -U $DatabaseUser -d $DatabaseName -c "SELECT version || '|' || description || '|' || coalesce(checksum::text,'') || '|' || success FROM flyway_schema_history WHERE version IN ('1','2','3') ORDER BY version" 2>$null
$expectedCanonicalHistory = @('1|create tenant control plane|-1758498178|true','2|harden tenant control plane|2133965838|true','3|lock down audit event|-1821703590|true')
if ($LASTEXITCODE -ne 0 -or (Compare-Object $expectedCanonicalHistory @($canonicalHistory))) { throw 'Local Flyway history does not match the canonical V1-V3 history.' }
$deprecatedRoleCount = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM pg_roles WHERE rolname='data_agent_app'" 2>$null
if (($deprecatedRoleCount | Out-String).Trim() -ne '0') { throw 'Deprecated data_agent_app role remains after local migration.' }
$legacyCount = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename IN ('agent_sessions','agent_audit_records','agent_accounts')"
if (($legacyCount | Out-String).Trim() -ne '3') { throw 'Controlled baseline caused legacy schema drift.' }
Write-Host 'Controlled local baseline/migration passed Flyway validation, application readiness, canonical history, role cleanup, and legacy-table preservation.'
