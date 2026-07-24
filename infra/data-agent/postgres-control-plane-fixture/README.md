# PostgreSQL tenant control-plane fixture

This fixture loads deterministic synthetic data into the Flyway-managed Data Agent control-plane schema. It uses reserved fixture UUID ranges and must never contain real credentials, tokens, connection strings, or enterprise data.

> [!WARNING]
> Reset and regression commands are destructive. They are restricted to named local Docker containers and approved local/test databases, but you must still verify the target before confirming execution.

## Current workspace status

The SQL loaders and database-only setup, verification, and reset wrappers are stored correctly under `agent-root/infra`. The migration-oriented wrappers still derive the Data Agent project root using their former standalone-repository location. In this workspace, do not run the following scripts until that path migration is completed:

- `Initialize-ControlPlaneTestDatabase.ps1`
- `Migrate-ControlPlaneLocalDatabase.ps1`
- `Repair-ControlPlaneLocalV3.ps1`
- `Verify-ControlPlaneLocalReconciliation.ps1`
- `Verify-LeastPrivilegeFlyway.ps1`

This warning prevents the documentation from presenting the old `E:\IdeaProjects\data-agent` layout as a supported workflow.

## Safe database-only workflow

Start the fixed local PostgreSQL container from the workspace root:

```powershell
docker compose -f .\infra\compose\data-agent.yml up -d postgres
```

After Flyway has already created the complete schema in `data_agent_test`, load and verify the fixture:

```powershell
.\infra\data-agent\postgres-control-plane-fixture\scripts\Setup-ControlPlaneFixture.ps1 -Environment TEST -DatabaseName data_agent_test
.\infra\data-agent\postgres-control-plane-fixture\scripts\Verify-ControlPlaneFixture.ps1 -Environment TEST -DatabaseName data_agent_test
```

Recreate only the isolated `data_agent_test` database and reload the fixture:

```powershell
.\infra\data-agent\postgres-control-plane-fixture\scripts\Reset-ControlPlaneFixture.ps1 -Environment TEST -DatabaseName data_agent_test -ConfirmLocalReset
```

The reset discards all rows in `data_agent_test`. It does not target the normal `data_agent` development database.

## Safety contract

The wrappers verify the fixed `data-agent-postgres` Compose container, approved environment and database names, Flyway history, required tables, tenant constraints, and audit append-only triggers. Reset uses a machine-wide mutex to prevent concurrent resets by the same trusted Windows principal.

Verification includes:

- exact fixture row counts and lifecycle coverage;
- cross-tenant relationship constraints;
- rejection of audit `UPDATE`, `DELETE`, and `TRUNCATE`;
- a deliberate transactional mismatch proving failed verification does not leave dirty data.

## Fixture rows

| Table | Expected rows |
| --- | ---: |
| `tenant` | 2 |
| `user_account` | 4 |
| `tenant_membership` | 4 |
| `tenant_role_binding` | 4 |
| `secret_reference` | 2 |
| `data_source` | 2 |
| `data_source_revision` | 6 |
| `data_source_policy` | 2 |
| `audit_event` | 4 |

`data_source_revision` contains two rows each in `DRAFT`, `ACTIVE`, and `REVOKED`.

## Migration invariants

The V2 tenant-isolation migration changes the role-binding relationship to a composite `(membership_id, tenant_id)` foreign key. V3 is limited to audit-event append-only triggers and must not create cluster roles or grants. Migration/runtime account separation requires a separately approved design.

See the [PostgreSQL composite foreign-key documentation](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK) for the constraint model.
