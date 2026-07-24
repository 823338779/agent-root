# PostgreSQL tenant control-plane fixture

This fixture injects deterministic, non-sensitive local data into the Flyway-managed control-plane schema. It owns only UUIDs in the `10000000` through `90000000` fixture ranges and never stores a real connection string, password, token, or enterprise data.

## Preconditions

Run all commands from `E:\IdeaProjects\data-agent`. Docker Desktop must be running and the `data-agent-postgres` Compose service must be healthy. Initialize an isolated database and apply the backend Flyway migration; this never baselines or changes the existing `data_agent` developer database:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\data-agent\postgres-control-plane-fixture\scripts\Initialize-ControlPlaneTestDatabase.ps1 -Environment TEST
```

The initializer builds the API, starts it only until Flyway creates the schema, then stops it synchronously. Load and validate the fixture:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\data-agent\postgres-control-plane-fixture\scripts\Setup-ControlPlaneFixture.ps1 -Environment TEST -DatabaseName data_agent_test
powershell -ExecutionPolicy Bypass -File .\infra\data-agent\postgres-control-plane-fixture\scripts\Verify-ControlPlaneFixture.ps1 -Environment TEST -DatabaseName data_agent_test
```

The scripts operate only through the `data-agent-postgres` Docker container. They reject non-`LOCAL`/`TEST` environment values, non-local/test database names, non-Compose PostgreSQL containers, and databases that do not contain `flyway_schema_history` plus every control-plane table. Reset is explicit, takes a machine-wide cross-session mutex, verifies the fixed Compose container and maintenance database first, and can bootstrap when `data_agent_test` does not yet exist:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\data-agent\postgres-control-plane-fixture\scripts\Reset-ControlPlaneFixture.ps1 -Environment TEST -DatabaseName data_agent_test -ConfirmLocalReset
```

Reset destroys and recreates only the isolated `data_agent_test` database. Its previous rows, including audit rows, are discarded with that database; migrations and deterministic seeds then create a fresh baseline. It never bypasses the append-only triggers in an existing database. A `Global\DataAgentControlPlaneFixtureReset` mutex refuses concurrent resets across Windows sessions that run under the same trusted security principal; the script does not claim cross-identity ACL coordination.

If an older local `data_agent` previously applied the superseded role/grant-bearing V3, migration fails closed until an operator explicitly runs `Migrate-ControlPlaneLocalDatabase.ps1 -Environment LOCAL -ConfirmLegacyV3Repair`. Reconciliation validates every V0-V3 history row and the exact legacy role attributes, settings, membership, table grants, ownership, cross-database ACL, explicit column/database/schema/routine/type ACL, and policy dependencies. It is a repair-first retryable state machine: exact legacy history/role runs Flyway `repair`; canonical history with the exact legacy role is the cleanup-pending state; cleanup explicitly revokes only the approved grants/membership and drops the role in one transaction; canonical history with no role is idempotent success. It never uses `DROP OWNED`. Unknown or mixed states stop without mutation. Migration then requires an unused validation port, real application readiness, canonical checksums, absence of the role, and all three legacy tables.

The destructive local-only regression `Verify-ControlPlaneLocalReconciliation.ps1 -Environment LOCAL -ConfirmReconciliationTest` operates only on the fixed Docker `data_agent` database. It covers extra failed history, repair and cleanup fault injection/retry, explicit column/database ACL, role setting, schema ownership, confirmation, approved legacy success, two-run idempotency, occupied readiness port, and real local-profile readiness. It restores canonical history/role state in `finally`; the `TEST` environment label is rejected so this command cannot be confused with the isolated `data_agent_test` reset flow.

V3 is intentionally limited to the statement-level trigger. It contains no cluster-level `CREATE ROLE`, role membership, `GRANT`, or `REVOKE`; migration/runtime account separation requires a separate approved ADR. To prove the migration itself does not require superuser or `CREATEROLE`, run the destructive fixed-target TEST check:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\data-agent\postgres-control-plane-fixture\scripts\Verify-LeastPrivilegeFlyway.ps1 -Environment TEST -ConfirmLeastPrivilegeTest
```

The script creates only `data_agent_migration_test` and `data_agent_migrator_test`, verifies the role is `LOGIN`, `NOSUPERUSER`, `NOCREATEROLE`, and `NOCREATEDB`, applies V1/V2/V3 through Spring Boot/Flyway, checks `installed_by` plus the real trigger catalog, then drops the test database and role in `finally`. Its random password remains process-local and is never printed or stored.

## Fixture contract

| Table | Expected fixture rows |
| --- | ---: |
| `tenant` | 2 |
| `user_account` | 4 |
| `tenant_membership` | 4 |
| `tenant_role_binding` | 4 |
| `secret_reference` | 2 |
| `data_source` | 2 |
| `data_source_revision` | 6 (2 each of `DRAFT`, `ACTIVE`, `REVOKED`) |
| `data_source_policy` | 2 |
| `audit_event` | 4 |

`02_verify_fixture.sql` fails with a nonzero exit when any row count differs, and also checks lifecycle coverage plus cross-tenant role, revision, and secret relationships. The verification wrapper deliberately creates a transactional row-count mismatch, requires that check to fail, and confirms rollback left no dirty data. `03_verify_negative_constraints.sql` performs transactional negative operations and expects PostgreSQL to reject cross-tenant revision, secret, policy, and role-binding attempts plus audit `UPDATE`, `DELETE`, and `TRUNCATE`.

## Tenant-isolation migration

V1 already rejects cross-tenant `data_source_revision`, `secret_reference`, and `data_source_policy` relations through composite foreign keys. Flyway V2 closes the original P0 gap in `tenant_role_binding` by adding `UNIQUE (id, tenant_id)` to `tenant_membership` and replacing the single-column membership reference with `FOREIGN KEY (membership_id, tenant_id) REFERENCES tenant_membership(id, tenant_id)`. This follows PostgreSQL's documented composite foreign-key model: https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK.
