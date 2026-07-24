[CmdletBinding()]
param(
    [ValidateSet('TEST')][string]$Environment = 'TEST',
    [string]$ContainerName = 'data-agent-postgres',
    [string]$DatabaseName = 'data_agent_test',
    [string]$DatabaseUser = 'data_agent'
)

$ErrorActionPreference = 'Stop'
if ($ContainerName -ne 'data-agent-postgres' -or $DatabaseName -ne 'data_agent_test') {
    throw 'Safety guard: migration verification creates or uses only data_agent_test in the local data-agent-postgres container.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }
$state = docker inspect --format '{{.State.Running}}|{{.Config.Image}}' $ContainerName 2>$null
$labels = docker inspect --format '{{json .Config.Labels}}' $ContainerName 2>$null
if ($LASTEXITCODE -ne 0 -or $state -notmatch '^true\|postgres:.*$' -or $labels -notmatch '"com\.docker\.compose\.project":"data-agent"') {
    throw 'Safety guard: data-agent-postgres must be the running local PostgreSQL Compose container.'
}

$databaseExists = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$DatabaseName'" 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect local PostgreSQL databases.' }
if (($databaseExists | Out-String).Trim() -ne '1') {
    docker exec $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d postgres -c "CREATE DATABASE $DatabaseName"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the isolated local test database.' }
}

. (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
Assert-LocalControlPlaneTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
$history = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT to_regclass('public.flyway_schema_history')" 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Flyway history in the isolated local test database.' }
if (($history | Out-String).Trim() -ne 'flyway_schema_history') {
    $userTables = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'" 2>$null
    if (($userTables | Out-String).Trim() -ne '0') { throw 'Refusing to baseline or migrate a non-empty test database without Flyway history.' }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$javaHome = Join-Path $projectRoot '.tools\jdk-21'
$java = Join-Path $javaHome 'bin\java.exe'
if (-not (Test-Path -LiteralPath $java)) { throw 'Java 21 runtime was not found at .tools\\jdk-21.' }
Push-Location $projectRoot
try {
    $env:JAVA_HOME = $javaHome
    $env:Path = "$javaHome\bin;$env:Path"
    .\backend\mvnw.cmd -f .\backend\pom.xml -pl agent-api -am package -DskipTests
    if ($LASTEXITCODE -ne 0) { throw 'Backend package build failed.' }

    $previousUrl = $env:DATA_AGENT_DB_URL
    $previousProfiles = $env:SPRING_PROFILES_ACTIVE
    $env:DATA_AGENT_DB_URL = "jdbc:postgresql://localhost:5432/$DatabaseName"
    $env:SPRING_PROFILES_ACTIVE = 'test'
    $process = Start-Process -FilePath $java -ArgumentList @('-jar', (Join-Path $projectRoot 'backend\agent-api\target\agent-api-0.1.0-SNAPSHOT-exec.jar'), '--server.port=18081') -PassThru -WindowStyle Hidden
    try {
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 1
            $historyReady = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT to_regclass('public.flyway_schema_history')" 2>$null
            if ($LASTEXITCODE -eq 0 -and ($historyReady | Out-String).Trim() -eq 'flyway_schema_history') {
                $version = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT version FROM flyway_schema_history WHERE success = true ORDER BY installed_rank DESC LIMIT 1" 2>$null
                if ($LASTEXITCODE -eq 0 -and ($version | Out-String).Trim() -eq '3') { break }
            }
            if ($process.HasExited) { throw 'Backend exited before Flyway created the tenant table.' }
            if ($attempt -eq 59) { throw 'Timed out waiting for Flyway to create the tenant table.' }
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
Write-Host 'Flyway migration verified in isolated data_agent_test.'
