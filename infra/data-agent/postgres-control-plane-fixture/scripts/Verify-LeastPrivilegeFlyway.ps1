[CmdletBinding()]
param(
    [switch]$ConfirmLeastPrivilegeTest,
    [ValidateSet('TEST')][string]$Environment = 'TEST',
    [string]$ContainerName = 'data-agent-postgres',
    [string]$DatabaseName = 'data_agent_migration_test',
    [string]$MigrationRole = 'data_agent_migrator_test',
    [string]$AdminUser = 'data_agent'
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmLeastPrivilegeTest) {
    throw 'Refusing destructive least-privilege migration test. Re-run with -ConfirmLeastPrivilegeTest.'
}
if ($Environment -ne 'TEST' -or $ContainerName -ne 'data-agent-postgres' -or
    $DatabaseName -ne 'data_agent_migration_test' -or $MigrationRole -ne 'data_agent_migrator_test') {
    throw 'Safety guard: this test is restricted to the fixed local Docker TEST database and role.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }

$state = docker inspect --format '{{.State.Running}}|{{.Config.Image}}' $ContainerName 2>$null
$labels = docker inspect --format '{{json .Config.Labels}}' $ContainerName 2>$null
if ($LASTEXITCODE -ne 0 -or $state -notmatch '^true\|postgres:.*$' -or $labels -notmatch '"com\.docker\.compose\.project":"data-agent"') {
    throw 'Safety guard: data-agent-postgres must be the running local PostgreSQL Compose container.'
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$migrationRoot = Join-Path $projectRoot 'backend\agent-api\src\main\resources\db\migration'
$v3Files = @(Get-ChildItem -LiteralPath $migrationRoot -Filter 'V3__*.sql')
if ($v3Files.Count -ne 1 -or $v3Files[0].Name -ne 'V3__lock_down_audit_event.sql') {
    throw 'Expected exactly one V3 migration named V3__lock_down_audit_event.sql.'
}
$v3Sql = [System.IO.File]::ReadAllText($v3Files[0].FullName)
if ($v3Sql -match '(?im)\b(CREATE|ALTER|DROP)\s+ROLE\b|\b(GRANT|REVOKE)\b|data_agent_app') {
    throw 'V3 must not create cluster roles, role memberships, or grants/revokes.'
}

$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $passwordBytes = New-Object byte[] 32
    $random.GetBytes($passwordBytes)
    $migrationPassword = [Convert]::ToBase64String($passwordBytes)
} finally {
    $random.Dispose()
}

$process = $null
$databaseProvisioned = $false
try {
    $provisionSql = @"
DROP DATABASE IF EXISTS $DatabaseName WITH (FORCE);
DROP ROLE IF EXISTS $MigrationRole;
    CREATE ROLE $MigrationRole LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '$migrationPassword';
CREATE DATABASE $DatabaseName OWNER $MigrationRole;
"@
    $databaseProvisioned = $true
    $provisionSql | docker exec -i $ContainerName psql -X -v ON_ERROR_STOP=1 -U $AdminUser -d postgres
    if ($LASTEXITCODE -ne 0) { throw 'Unable to provision the fixed least-privilege migration test target.' }

    $roleAttributes = docker exec $ContainerName psql -X -Atq -U $AdminUser -d postgres -c "SELECT rolsuper::int || '|' || rolcreaterole::int || '|' || rolcreatedb::int || '|' || rolcanlogin::int FROM pg_roles WHERE rolname = '$MigrationRole'"
    if ($LASTEXITCODE -ne 0 -or ($roleAttributes | Out-String).Trim() -ne '0|0|0|1') {
        throw 'Migration test role is not LOGIN + NOSUPERUSER + NOCREATEROLE + NOCREATEDB.'
    }

    $javaHome = Join-Path $projectRoot '.tools\jdk-21'
    $java = Join-Path $javaHome 'bin\java.exe'
    if (-not (Test-Path -LiteralPath $java)) { throw 'Java 21 runtime was not found at .tools\jdk-21.' }

    Push-Location $projectRoot
    try {
        $env:JAVA_HOME = $javaHome
        $env:Path = "$javaHome\bin;$env:Path"
        .\backend\mvnw.cmd -f .\backend\pom.xml -pl agent-api -am package -DskipTests
        if ($LASTEXITCODE -ne 0) { throw 'Backend package build failed.' }

        $previousUrl = $env:DATA_AGENT_DB_URL
        $previousUsername = $env:DATA_AGENT_DB_USERNAME
        $previousPassword = $env:DATA_AGENT_DB_PASSWORD
        $previousProfiles = $env:SPRING_PROFILES_ACTIVE
        try {
            $env:DATA_AGENT_DB_URL = "jdbc:postgresql://localhost:5432/$DatabaseName"
            $env:DATA_AGENT_DB_USERNAME = $MigrationRole
            $env:DATA_AGENT_DB_PASSWORD = $migrationPassword
            $env:SPRING_PROFILES_ACTIVE = 'test'
            $process = Start-Process -FilePath $java -ArgumentList @('-jar', (Join-Path $projectRoot 'backend\agent-api\target\agent-api-0.1.0-SNAPSHOT-exec.jar'), '--server.port=18083') -PassThru -WindowStyle Hidden
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                Start-Sleep -Seconds 1
                $historyReady = docker exec $ContainerName psql -X -Atq -U $AdminUser -d $DatabaseName -c "SELECT to_regclass('public.flyway_schema_history')" 2>$null
                if ($LASTEXITCODE -eq 0 -and ($historyReady | Out-String).Trim() -eq 'flyway_schema_history') {
                    $version = docker exec $ContainerName psql -X -Atq -U $AdminUser -d $DatabaseName -c "SELECT version FROM flyway_schema_history WHERE success = true ORDER BY installed_rank DESC LIMIT 1" 2>$null
                    if ($LASTEXITCODE -eq 0 -and ($version | Out-String).Trim() -eq '3') { break }
                }
                if ($process.HasExited) { throw 'Backend exited before the least-privilege Flyway migration completed.' }
                if ($attempt -eq 59) { throw 'Timed out waiting for the least-privilege Flyway migration.' }
            }
        } finally {
            if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
            $env:DATA_AGENT_DB_URL = $previousUrl
            $env:DATA_AGENT_DB_USERNAME = $previousUsername
            $env:DATA_AGENT_DB_PASSWORD = $previousPassword
            $env:SPRING_PROFILES_ACTIVE = $previousProfiles
        }
    } finally {
        Pop-Location
    }

    . (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
    Assert-ControlPlaneSchema -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $AdminUser
    $installedBy = docker exec $ContainerName psql -X -Atq -U $AdminUser -d $DatabaseName -c "SELECT string_agg(version || ':' || installed_by, ',' ORDER BY installed_rank) FROM flyway_schema_history WHERE success"
    if ($LASTEXITCODE -ne 0 -or ($installedBy | Out-String).Trim() -ne "1:$MigrationRole,2:$MigrationRole,3:$MigrationRole") {
        throw 'Flyway history does not prove that the least-privilege role applied V1/V2/V3.'
    }

    Write-Host 'Least-privilege role attributes verified: NOSUPERUSER, NOCREATEROLE, NOCREATEDB, LOGIN.'
    Write-Host "Flyway history verified: 1:$MigrationRole,2:$MigrationRole,3:$MigrationRole."
    Write-Host 'Unique trigger-only V3 applied successfully without cluster-role or grant/revoke SQL.'
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
    if ($databaseProvisioned) {
        $cleanupSql = @"
DROP DATABASE IF EXISTS $DatabaseName WITH (FORCE);
DROP ROLE IF EXISTS $MigrationRole;
"@
        $cleanupSql | docker exec -i $ContainerName psql -X -v ON_ERROR_STOP=1 -U $AdminUser -d postgres
        if ($LASTEXITCODE -ne 0) { throw 'Least-privilege migration test passed but cleanup failed.' }
    }
    $migrationPassword = $null
}
