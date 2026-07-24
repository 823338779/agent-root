$ErrorActionPreference = 'Stop'

function Assert-LocalControlPlaneTarget {
    param(
        [ValidateSet('LOCAL', 'TEST')][string]$Environment,
        [string]$ContainerName,
        [string]$DatabaseName,
        [string]$DatabaseUser
    )

    if ($Environment -notin @('LOCAL', 'TEST')) { throw 'Safety guard: Environment must be LOCAL or TEST.' }
    if ($ContainerName -ne 'data-agent-postgres') { throw 'Safety guard: only the local data-agent-postgres Docker container is allowed.' }
    if ($DatabaseName -notin @('data_agent', 'data_agent_test', 'data_agent_local')) { throw 'Safety guard: database name is not an approved local/test target.' }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }

    $state = docker inspect --format '{{.State.Running}}|{{.Config.Image}}' $ContainerName 2>$null
    $labels = docker inspect --format '{{json .Config.Labels}}' $ContainerName 2>$null
    if ($LASTEXITCODE -ne 0 -or $state -notmatch '^true\|postgres:.*$' -or $labels -notmatch '"com\.docker\.compose\.project":"data-agent"') {
        throw "Safety guard: '$ContainerName' must be the running local data-agent PostgreSQL Compose container."
    }

    $actualDatabase = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c 'SELECT current_database()' 2>$null
    if ($LASTEXITCODE -ne 0 -or $actualDatabase.Trim() -ne $DatabaseName) {
        throw 'Safety guard: unable to verify the requested local/test database from inside the Docker PostgreSQL container.'
    }
}

function Assert-LocalControlPlaneMaintenanceTarget {
    param(
        [ValidateSet('TEST')][string]$Environment,
        [string]$ContainerName,
        [string]$DatabaseName,
        [string]$DatabaseUser
    )

    if ($Environment -ne 'TEST' -or $ContainerName -ne 'data-agent-postgres' -or $DatabaseName -ne 'data_agent_test') {
        throw 'Safety guard: database recreation is restricted to the fixed local Docker data_agent_test target.'
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }
    $state = docker inspect --format '{{.State.Running}}|{{.Config.Image}}' $ContainerName 2>$null
    $labels = docker inspect --format '{{json .Config.Labels}}' $ContainerName 2>$null
    if ($LASTEXITCODE -ne 0 -or $state -notmatch '^true\|postgres:.*$' -or $labels -notmatch '"com\.docker\.compose\.project":"data-agent"') {
        throw "Safety guard: '$ContainerName' must be the running local data-agent PostgreSQL Compose container."
    }
    $identity = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d postgres -c "SELECT current_database() || '|' || current_user" 2>$null
    if ($LASTEXITCODE -ne 0 -or ($identity | Out-String).Trim() -ne "postgres|$DatabaseUser") {
        throw 'Safety guard: unable to verify the maintenance database and expected local application user.'
    }
}

function Assert-ControlPlaneSchema {
    param(
        [string]$ContainerName,
        [string]$DatabaseName,
        [string]$DatabaseUser
    )

    $requiredTables = @('flyway_schema_history', 'tenant', 'user_account', 'tenant_membership', 'tenant_role_binding', 'data_source', 'data_source_revision', 'data_source_connection_test', 'secret_reference', 'data_source_policy', 'audit_event')
    $actualTables = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename" 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the PostgreSQL schema.' }
    foreach ($table in $requiredTables) {
        if ($actualTables -notcontains $table) { throw "Control-plane migration is missing table '$table'. Apply Flyway before loading the fixture." }
    }
    $constraints = docker exec $ContainerName psql -X -Atq -U $DatabaseUser -d $DatabaseName -c "SELECT conname FROM pg_constraint WHERE conname IN ('uq_tenant_membership_id_tenant', 'fk_role_binding_membership_tenant') ORDER BY conname" 2>$null
    if ($LASTEXITCODE -ne 0 -or $constraints -notcontains 'uq_tenant_membership_id_tenant' -or $constraints -notcontains 'fk_role_binding_membership_tenant') {
        throw 'Control-plane migration is missing tenant_role_binding composite tenant constraints.'
    }
    $triggers = docker exec $ContainerName psql -X -Atq -F '|' -U $DatabaseUser -d $DatabaseName -c "SELECT t.tgname, t.tgenabled, t.tgtype, p.proname, pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid WHERE t.tgrelid = 'audit_event'::regclass AND NOT t.tgisinternal ORDER BY t.tgname" 2>$null
    $rowTrigger = $triggers | Where-Object { $_ -match '^audit_event_append_only\|O\|27\|reject_audit_event_mutation\|CREATE TRIGGER .* BEFORE (UPDATE OR DELETE|DELETE OR UPDATE) ON .*audit_event FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation\(\)$' }
    $truncateTrigger = $triggers | Where-Object { $_ -match '^audit_event_reject_truncate\|O\|34\|reject_audit_event_mutation\|CREATE TRIGGER .* BEFORE TRUNCATE ON .*audit_event FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_event_mutation\(\)$' }
    if ($LASTEXITCODE -ne 0 -or -not $rowTrigger -or -not $truncateTrigger) {
        throw 'Control-plane migration is missing enabled audit UPDATE/DELETE/TRUNCATE append-only trigger definitions.'
    }
}

function Invoke-ControlPlaneSql {
    param(
        [string]$SqlPath,
        [string]$ContainerName,
        [string]$DatabaseName,
        [string]$DatabaseUser
    )

    if (-not (Test-Path -LiteralPath $SqlPath)) { throw "SQL file not found: $SqlPath" }
    [System.IO.File]::ReadAllText($SqlPath) | docker exec -i $ContainerName psql -X -v ON_ERROR_STOP=1 -U $DatabaseUser -d $DatabaseName
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL command failed: $([System.IO.Path]::GetFileName($SqlPath))" }
}
