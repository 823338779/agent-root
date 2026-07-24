[CmdletBinding()]
param(
    [ValidateSet('LOCAL')][string]$Environment = 'LOCAL',
    [string]$ContainerName = 'data-agent-postgres',
    [string]$DatabaseName = 'data_agent',
    [string]$DatabaseUser = 'data_agent',
    [switch]$ConfirmLegacyV3Repair,
    [ValidateSet('NONE', 'REPAIR', 'CLEANUP')][string]$TestFault = 'NONE'
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmLegacyV3Repair) { throw 'Refusing legacy V3 reconciliation. Re-run with -ConfirmLegacyV3Repair after reviewing the state evidence.' }
if ($ContainerName -ne 'data-agent-postgres' -or $DatabaseName -ne 'data_agent' -or $DatabaseUser -ne 'data_agent') {
    throw 'Safety guard: reconciliation is restricted to the fixed local Docker data_agent database and user.'
}
if ($TestFault -ne 'NONE' -and $env:DATA_AGENT_RECONCILIATION_FAULT_INJECTION -ne 'true') {
    throw 'Fault injection is restricted to the guarded reconciliation regression.'
}
. (Join-Path $PSScriptRoot 'Fixture-Common.ps1')
Assert-LocalControlPlaneTarget -Environment $Environment -ContainerName $ContainerName -DatabaseName $DatabaseName -DatabaseUser $DatabaseUser

$legacyHistory = @(
    '1|0|controlled local baseline for pre-Flyway legacy tables|BASELINE|controlled local baseline for pre-Flyway legacy tables||t',
    '2|1|create tenant control plane|SQL|V1__create_tenant_control_plane.sql|-1758498178|t',
    '3|2|harden tenant control plane|SQL|V2__harden_tenant_control_plane.sql|2133965838|t',
    '4|3|lock down audit event|SQL|V3__lock_down_audit_event.sql|1550874236|t'
)
$canonicalHistory = @(
    $legacyHistory[0], $legacyHistory[1], $legacyHistory[2],
    '4|3|lock down audit event|SQL|V3__lock_down_audit_event.sql|-1821703590|t'
)
$expectedGrants = @(
    'audit_event|INSERT,SELECT',
    'data_source|DELETE,INSERT,SELECT,UPDATE',
    'data_source_connection_test|DELETE,INSERT,SELECT,UPDATE',
    'data_source_policy|DELETE,INSERT,SELECT,UPDATE',
    'data_source_revision|DELETE,INSERT,SELECT,UPDATE',
    'secret_reference|DELETE,INSERT,SELECT,UPDATE',
    'tenant|DELETE,INSERT,SELECT,UPDATE',
    'tenant_membership|DELETE,INSERT,SELECT,UPDATE',
    'tenant_role_binding|DELETE,INSERT,SELECT,UPDATE',
    'user_account|DELETE,INSERT,SELECT,UPDATE'
)

function Get-HistoryState {
    $rows = docker exec $ContainerName psql -X -At -F '|' -U $DatabaseUser -d $DatabaseName -c "SELECT installed_rank,coalesce(version,''),description,type,script,coalesce(checksum::text,''),success FROM flyway_schema_history ORDER BY installed_rank" 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect complete Flyway history.' }
    if (-not (Compare-Object $legacyHistory @($rows))) { return 'LEGACY' }
    if (-not (Compare-Object $canonicalHistory @($rows))) { return 'CANONICAL' }
    throw 'Fail-closed: complete Flyway history is not an approved V0-V3 state.'
}

function Get-RoleState {
    $roleCount = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT count(*) FROM pg_roles WHERE rolname='data_agent_app'" 2>$null
    if (($roleCount | Out-String).Trim() -eq '0') { return 'ABSENT' }
    if (($roleCount | Out-String).Trim() -ne '1') { throw 'Fail-closed: deprecated role lookup is ambiguous.' }

    $role = docker exec $ContainerName psql -X -At -F '|' -U $DatabaseUser -d $DatabaseName -c "SELECT r.rolname,r.rolinherit,r.rolcanlogin,r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls,r.rolconnlimit,r.rolvaliduntil IS NULL,a.rolpassword IS NULL,r.rolconfig IS NULL,shobj_description(r.oid,'pg_authid') IS NULL,(SELECT count(*) FROM pg_db_role_setting s WHERE s.setrole=r.oid),(SELECT count(*) FROM pg_shseclabel l WHERE l.classoid='pg_authid'::regclass AND l.objoid=r.oid) FROM pg_roles r JOIN pg_authid a ON a.oid=r.oid WHERE r.rolname='data_agent_app'" 2>$null
    $expectedRole = 'data_agent_app|t|f|f|f|f|f|f|-1|t|t|t|t|0|0'
    if ($LASTEXITCODE -ne 0 -or ($role | Out-String).Trim() -ne $expectedRole) { throw 'Fail-closed: data_agent_app has unknown attributes, settings, comment, password, or security labels.' }

    $memberships = docker exec $ContainerName psql -X -At -F '|' -U $DatabaseUser -d $DatabaseName -c "SELECT granted.rolname,member.rolname,grantor.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m JOIN pg_roles granted ON granted.oid=m.roleid JOIN pg_roles member ON member.oid=m.member JOIN pg_roles grantor ON grantor.oid=m.grantor WHERE granted.rolname='data_agent_app' OR member.rolname='data_agent_app' ORDER BY 1" 2>$null
    if (@($memberships).Count -ne 1 -or ($memberships | Out-String).Trim() -ne 'data_agent_app|data_agent|data_agent|f|t|t') { throw 'Fail-closed: data_agent_app has unknown membership grantor or options.' }

    $grants = docker exec $ContainerName psql -X -At -F '|' -U $DatabaseUser -d $DatabaseName -c "SELECT table_name || '|' || string_agg(privilege_type,',' ORDER BY privilege_type) || '|' || string_agg(DISTINCT grantor,'') || '|' || string_agg(DISTINCT is_grantable,'') FROM information_schema.role_table_grants WHERE grantee='data_agent_app' GROUP BY table_name ORDER BY table_name" 2>$null
    $expectedGrantDetails=$expectedGrants | ForEach-Object { "$_|data_agent|NO" }
    if (Compare-Object $expectedGrantDetails @($grants)) { throw 'Fail-closed: data_agent_app table grants differ in privilege, grantor, or grantability.' }

    $dependencies = docker exec $ContainerName psql -X -At -F '|' -U $DatabaseUser -d $DatabaseName -c "WITH target AS (SELECT oid FROM pg_roles WHERE rolname='data_agent_app'), current_db AS (SELECT oid FROM pg_database WHERE datname=current_database()) SELECT coalesce(c.relname,'?'),d.classid::regclass,d.objsubid,d.deptype FROM pg_shdepend d CROSS JOIN target CROSS JOIN current_db LEFT JOIN pg_class c ON d.dbid=current_db.oid AND d.classid='pg_class'::regclass AND d.objid=c.oid WHERE d.refclassid='pg_authid'::regclass AND d.refobjid=target.oid ORDER BY 1,2::text,3,4" 2>$null
    $expectedDependencies=@('audit_event|pg_class|0|a','data_source|pg_class|0|a','data_source_connection_test|pg_class|0|a','data_source_policy|pg_class|0|a','data_source_revision|pg_class|0|a','secret_reference|pg_class|0|a','tenant|pg_class|0|a','tenant_membership|pg_class|0|a','tenant_role_binding|pg_class|0|a','user_account|pg_class|0|a')
    if (Compare-Object $expectedDependencies @($dependencies)) { throw 'Fail-closed: cluster-wide pg_shdepend differs from the exact approved table ACL whitelist.' }
    return 'EXACT_LEGACY'
}

function Invoke-FlywayRepair {
    if ($TestFault -eq 'REPAIR') { throw 'Injected Flyway repair failure before any destructive cleanup.' }
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
    $javaHome = Join-Path $projectRoot '.tools\jdk-21'
    $saved = @($env:JAVA_HOME,$env:DATA_AGENT_DB_URL,$env:DATA_AGENT_DB_USERNAME,$env:DATA_AGENT_DB_PASSWORD)
    try {
        $env:JAVA_HOME=$javaHome; $env:DATA_AGENT_DB_URL="jdbc:postgresql://localhost:5432/$DatabaseName"; $env:DATA_AGENT_DB_USERNAME=$DatabaseUser
        if (-not $env:DATA_AGENT_DB_PASSWORD) { $env:DATA_AGENT_DB_PASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { 'data_agent_local_dev' } }
        Push-Location $projectRoot
        try { .\backend\mvnw.cmd -f .\backend\pom.xml -pl agent-api -am flyway:repair; if ($LASTEXITCODE -ne 0) { throw 'Flyway repair failed; legacy role was not cleaned.' } } finally { Pop-Location }
    } finally {
        $env:JAVA_HOME=$saved[0]; $env:DATA_AGENT_DB_URL=$saved[1]; $env:DATA_AGENT_DB_USERNAME=$saved[2]; $env:DATA_AGENT_DB_PASSWORD=$saved[3]
    }
    if ((Get-HistoryState) -ne 'CANONICAL') { throw 'Flyway repair did not reach canonical history; legacy role was not cleaned.' }
}

function Remove-ExactLegacyRole {
    if ($TestFault -eq 'CLEANUP') { throw 'Injected cleanup failure; canonical checksum with exact legacy role remains retryable.' }
    $sql = @'
BEGIN;
REVOKE SELECT, INSERT ON audit_event FROM data_agent_app;
REVOKE SELECT, INSERT, UPDATE, DELETE ON tenant, user_account, tenant_membership, tenant_role_binding, data_source, data_source_revision, data_source_connection_test, secret_reference, data_source_policy FROM data_agent_app;
REVOKE data_agent_app FROM data_agent;
DROP ROLE data_agent_app;
COMMIT;
'@
    $sql | docker exec -i $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d $DatabaseName
    if ($LASTEXITCODE -ne 0) { throw 'Explicit legacy role cleanup failed and was rolled back.' }
}

$mutex=[System.Threading.Mutex]::new($false,'Global\DataAgentControlPlaneMigrationRepair'); $locked=$false
try {
    $locked=$mutex.WaitOne(0); if (-not $locked) { throw 'Another control-plane migration repair is already running on this machine.' }
    $historyState=Get-HistoryState; $roleState=Get-RoleState
    if ($historyState -eq 'CANONICAL' -and $roleState -eq 'ABSENT') { Write-Host 'Control-plane local migration state is already canonical.'; return }
    if ($historyState -eq 'LEGACY' -and $roleState -eq 'EXACT_LEGACY') { Invoke-FlywayRepair; $historyState='CANONICAL'; $roleState=Get-RoleState }
    elseif ($historyState -ne 'CANONICAL' -or $roleState -ne 'EXACT_LEGACY') { throw "Fail-closed: unsupported reconciliation state $historyState/$roleState." }
    Remove-ExactLegacyRole
    if ((Get-HistoryState) -ne 'CANONICAL' -or (Get-RoleState) -ne 'ABSENT') { throw 'Post-reconciliation state is not canonical.' }
    Write-Host 'Approved legacy V3 state reached canonical history and explicit role cleanup.'
} finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
