# PostgreSQL legacy session migration fixture

Use only against a disposable local database whose name ends in `_test`. Apply Flyway V1-V3, run `01_legacy_fixture.sql`, apply V4, then run `02_verify.sql`. The fixture is deterministic and synthetic; it covers JSON `null`, empty arrays, a valid run, null/valid confirmation, ordered children and a timezone boundary. Drop the disposable database after verification.

V4 intentionally fails and rolls back on invalid JSON, duplicate identifiers/sequences, missing required fields, or any count/presence mismatch. It never uses `ON CONFLICT DO NOTHING`.

`03_invalid_json_fixture.sql` is the negative fixture: apply it after V1-V3 in a separate disposable database, assert V4 fails, then assert Flyway remains at V3 and no normalized child table exists.
