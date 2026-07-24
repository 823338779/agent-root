[CmdletBinding()]
param([ValidateSet('LOCAL')][string]$Environment='LOCAL',[string]$ContainerName='data-agent-postgres',[string]$DatabaseName='data_agent',[string]$DatabaseUser='data_agent',[switch]$ConfirmReconciliationTest)
$ErrorActionPreference='Stop'
if (-not $ConfirmReconciliationTest) { throw 'Refusing reconciliation regression. Re-run with -ConfirmReconciliationTest.' }
if ($ContainerName -ne 'data-agent-postgres' -or $DatabaseName -ne 'data_agent' -or $DatabaseUser -ne 'data_agent') { throw 'Safety guard: fixed local Docker data_agent target only.' }
. (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
Assert-LocalControlPlaneTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser
$repair=Join-Path $PSScriptRoot 'Repair-ControlPlaneLocalV3.ps1'; $migrate=Join-Path $PSScriptRoot 'Migrate-ControlPlaneLocalDatabase.ps1'

function Invoke-Sql([string]$Sql) { docker exec $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d $DatabaseName -c $Sql; if ($LASTEXITCODE -ne 0) { throw 'Regression fixture SQL failed.' } }
function Get-V3 { (docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT checksum FROM flyway_schema_history WHERE version='3'").Trim() }
function Get-RoleCount { (docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM pg_roles WHERE rolname='data_agent_app'").Trim() }
function Invoke-ExpectedFailure([string[]]$Arguments,[string]$Pattern) {
    $old=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $output=powershell -NoProfile -ExecutionPolicy Bypass -File $repair @Arguments 2>&1; $code=$LASTEXITCODE } finally { $ErrorActionPreference=$old }
    if ($code -eq 0 -or ($output|Out-String) -notmatch $Pattern) { throw "Expected failure '$Pattern' was not observed. exit=$code output=$output" }
}
function New-ExactLegacyState {
    if ((Get-RoleCount) -ne '0') { throw 'Legacy role must be absent before constructing a fixture.' }
    Invoke-Sql "UPDATE flyway_schema_history SET checksum=1550874236 WHERE version='3'; CREATE ROLE data_agent_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; GRANT data_agent_app TO data_agent; GRANT SELECT,INSERT ON audit_event TO data_agent_app; GRANT SELECT,INSERT,UPDATE,DELETE ON tenant,user_account,tenant_membership,tenant_role_binding,data_source,data_source_revision,data_source_connection_test,secret_reference,data_source_policy TO data_agent_app;"
}
function Restore-CanonicalState {
    $exists=Get-RoleCount
    if ($exists -eq '1') {
        Invoke-Sql "COMMENT ON ROLE data_agent_app IS NULL; DROP SCHEMA IF EXISTS data_agent_app_owned CASCADE; DROP SEQUENCE IF EXISTS data_agent_app_extra_sequence; REVOKE CONNECT ON DATABASE data_agent FROM data_agent_app; ALTER DEFAULT PRIVILEGES REVOKE SELECT ON TABLES FROM data_agent_app; ALTER ROLE data_agent_app RESET ALL; REVOKE REFERENCES(id) ON tenant FROM data_agent_app; REVOKE SELECT,INSERT ON audit_event FROM data_agent_app; REVOKE SELECT,INSERT,UPDATE,DELETE ON tenant,user_account,tenant_membership,tenant_role_binding,data_source,data_source_revision,data_source_connection_test,secret_reference,data_source_policy FROM data_agent_app; REVOKE data_agent_app FROM data_agent; DROP ROLE data_agent_app;"
    }
    Invoke-Sql "DELETE FROM flyway_schema_history WHERE version='99'; UPDATE flyway_schema_history SET checksum=-1821703590 WHERE version='3';"
}

$env:DATA_AGENT_RECONCILIATION_FAULT_INJECTION='true'
try {
    Restore-CanonicalState

    Invoke-Sql "INSERT INTO flyway_schema_history(installed_rank,version,description,type,script,checksum,installed_by,execution_time,success) VALUES (99,'99','unknown failed','SQL','V99__unknown.sql',99,current_user,0,false)"
    Invoke-ExpectedFailure @('-Environment','LOCAL','-ConfirmLegacyV3Repair') 'complete Flyway history is not an approved'
    if ((docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM flyway_schema_history WHERE version='99'").Trim() -ne '1') { throw 'Unknown history was modified.' }
    Invoke-Sql "DELETE FROM flyway_schema_history WHERE version='99'"

    New-ExactLegacyState
    Invoke-ExpectedFailure @('-Environment','LOCAL','-ConfirmLegacyV3Repair','-TestFault','REPAIR') 'Injected Flyway repair failure'
    if ((Get-V3) -ne '1550874236' -or (Get-RoleCount) -ne '1') { throw 'Repair failure changed persistent state.' }
    & $repair -Environment LOCAL -ConfirmLegacyV3Repair
    if ((Get-V3) -ne '-1821703590' -or (Get-RoleCount) -ne '0') { throw 'Retry after repair fault did not reach canonical.' }

    New-ExactLegacyState
    Invoke-ExpectedFailure @('-Environment','LOCAL','-ConfirmLegacyV3Repair','-TestFault','CLEANUP') 'Injected cleanup failure'
    if ((Get-V3) -ne '-1821703590' -or (Get-RoleCount) -ne '1') { throw 'Cleanup failure did not preserve the retryable pending state.' }
    & $repair -Environment LOCAL -ConfirmLegacyV3Repair
    if ((Get-RoleCount) -ne '0') { throw 'Retry from cleanup-pending did not remove the role.' }

    foreach ($case in @('CONNECT','COLUMN','SETTING','OWNERSHIP','COMMENT','ADMIN','GRANT_OPTION','SEQUENCE','DEFAULT_ACL')) {
        New-ExactLegacyState
        switch ($case) {
            'CONNECT' { Invoke-Sql 'GRANT CONNECT ON DATABASE data_agent TO data_agent_app' }
            'COLUMN' { Invoke-Sql 'GRANT REFERENCES(id) ON tenant TO data_agent_app' }
            'SETTING' { Invoke-Sql "ALTER ROLE data_agent_app SET statement_timeout='1s'" }
            'OWNERSHIP' { Invoke-Sql 'CREATE SCHEMA data_agent_app_owned AUTHORIZATION data_agent_app' }
            'COMMENT' { Invoke-Sql "COMMENT ON ROLE data_agent_app IS 'unexpected'" }
            'ADMIN' { Invoke-Sql 'GRANT data_agent_app TO data_agent WITH ADMIN OPTION' }
            'GRANT_OPTION' { Invoke-Sql 'GRANT SELECT ON tenant TO data_agent_app WITH GRANT OPTION' }
            'SEQUENCE' { Invoke-Sql 'CREATE SEQUENCE data_agent_app_extra_sequence; GRANT USAGE ON SEQUENCE data_agent_app_extra_sequence TO data_agent_app' }
            'DEFAULT_ACL' { Invoke-Sql 'ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO data_agent_app' }
        }
        Invoke-ExpectedFailure @('-Environment','LOCAL','-ConfirmLegacyV3Repair') 'Fail-closed:'
        if ((Get-V3) -ne '1550874236' -or (Get-RoleCount) -ne '1') { throw "$case dependency rejection partially changed state." }
        Restore-CanonicalState
    }

    New-ExactLegacyState
    $old=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $noConfirm=powershell -NoProfile -ExecutionPolicy Bypass -File $migrate -Environment LOCAL 2>&1; $noConfirmCode=$LASTEXITCODE } finally { $ErrorActionPreference=$old }
    if ($noConfirmCode -eq 0 -or ($noConfirm|Out-String) -notmatch 'ConfirmLegacyV3Repair') { throw 'Approved legacy state did not require explicit confirmation.' }
    & $migrate -Environment LOCAL -ConfirmLegacyV3Repair
    & $migrate -Environment LOCAL

    $listener=[System.Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,18082); $listener.Start()
    try {
        $old=$ErrorActionPreference; $ErrorActionPreference='Continue'
        try { $portOutput=powershell -NoProfile -ExecutionPolicy Bypass -File $migrate -Environment LOCAL 2>&1; $portCode=$LASTEXITCODE } finally { $ErrorActionPreference=$old }
        if ($portCode -eq 0 -or ($portOutput|Out-String) -notmatch 'port 18082 is already in use') { throw 'Occupied readiness port was not rejected.' }
    } finally { $listener.Stop() }
    Write-Host 'Complete history, repair/cleanup fault retry, dependency, confirmation, idempotency, readiness, and occupied-port regressions passed.'
} finally {
    Restore-CanonicalState
    Remove-Item Env:DATA_AGENT_RECONCILIATION_FAULT_INJECTION -ErrorAction SilentlyContinue
}
