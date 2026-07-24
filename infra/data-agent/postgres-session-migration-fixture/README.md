# PostgreSQL legacy-session migration fixture

This deterministic synthetic fixture verifies migration of legacy agent-session JSON into normalized session, message, run, event, confirmation, and audit records.

> [!WARNING]
> Use only a disposable local database whose name ends in `_test`. Drop it after verification.

## Files

| File | Purpose |
| --- | --- |
| `01_legacy_fixture.sql` | Loads valid legacy session shapes after Flyway V1-V3. |
| `02_verify.sql` | Verifies normalized rows after V4. |
| `03_invalid_json_fixture.sql` | Supplies invalid JSON for rollback verification. |

## Positive workflow

1. Create a disposable `_test` database.
2. Apply Flyway V1-V3.
3. Run `01_legacy_fixture.sql`.
4. Apply Flyway V4.
5. Run `02_verify.sql`.
6. Drop the disposable database.

The fixture covers JSON `null`, empty arrays, a valid run, null and valid confirmations, ordered child records, and a timezone boundary.

## Negative workflow

In a separate disposable database, apply V1-V3 and then `03_invalid_json_fixture.sql`. V4 must fail and roll back, Flyway must remain at V3, and no normalized child table may exist.

V4 intentionally rejects invalid JSON, duplicate identifiers or sequences, missing required fields, and count or presence mismatches. It must not silently discard conflicts with `ON CONFLICT DO NOTHING`.
