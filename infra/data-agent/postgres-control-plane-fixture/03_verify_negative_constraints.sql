\set ON_ERROR_STOP on
BEGIN;

-- All attempted rows are rolled back. Each block must receive a PostgreSQL FK violation.
DO $$
BEGIN
  BEGIN
    INSERT INTO data_source_revision (id, tenant_id, data_source_id, revision_number, lifecycle_state, jdbc_url, username)
    VALUES ('71000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000002', 99, 'DRAFT', 'jdbc:postgresql://invalid.local:5432/db', 'fixture_reader');
    RAISE EXCEPTION 'cross-tenant data_source_revision was accepted';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;

  BEGIN
    INSERT INTO data_source_revision (id, tenant_id, data_source_id, revision_number, lifecycle_state, jdbc_url, username, secret_reference_id)
    VALUES ('71000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 100, 'DRAFT', 'jdbc:postgresql://invalid.local:5432/db', 'fixture_reader', '50000000-0000-0000-0000-000000000002');
    RAISE EXCEPTION 'cross-tenant secret_reference was accepted';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;

  BEGIN
    INSERT INTO data_source_policy (id, tenant_id, data_source_id, policy_code, policy_value)
    VALUES ('81000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000002', 'INVALID_CROSS_TENANT', '{}'::jsonb);
    RAISE EXCEPTION 'cross-tenant data_source_policy was accepted';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;

  BEGIN
    INSERT INTO tenant_role_binding (id, tenant_id, membership_id, role_code)
    VALUES ('41000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000003', 'INVALID_CROSS_TENANT');
    RAISE EXCEPTION 'cross-tenant tenant_role_binding was accepted; require a composite (membership_id, tenant_id) foreign key to tenant_membership';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;

  BEGIN
    UPDATE audit_event SET event_type = 'TAMPERED'
    WHERE id = '90000000-0000-0000-0000-000000000001';
    RAISE EXCEPTION 'audit_event UPDATE was accepted';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'audit_event is append-only' THEN RAISE; END IF;
  END;

  BEGIN
    DELETE FROM audit_event
    WHERE id = '90000000-0000-0000-0000-000000000001';
    RAISE EXCEPTION 'audit_event DELETE was accepted';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'audit_event is append-only' THEN RAISE; END IF;
  END;

  BEGIN
    TRUNCATE TABLE audit_event;
    RAISE EXCEPTION 'audit_event TRUNCATE was accepted';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'audit_event is append-only' THEN RAISE; END IF;
  END;
END $$;

-- Exercise the same atomic state transition used by revoke and prove list-visible state cannot remain ACTIVE.
UPDATE data_source_revision
SET lifecycle_state = 'REVOKED', revoked_at = current_timestamp
WHERE id = '70000000-0000-0000-0000-000000000002'
  AND tenant_id = '10000000-0000-0000-0000-000000000001';
UPDATE data_source
SET status = CASE WHEN EXISTS (
  SELECT 1 FROM data_source_revision
  WHERE tenant_id = '10000000-0000-0000-0000-000000000001'
    AND data_source_id = '60000000-0000-0000-0000-000000000001'
    AND lifecycle_state = 'ACTIVE'
) THEN 'ACTIVE' ELSE 'INACTIVE' END
WHERE id = '60000000-0000-0000-0000-000000000001'
  AND tenant_id = '10000000-0000-0000-0000-000000000001';
DO $$
BEGIN
  IF (SELECT status FROM data_source WHERE id = '60000000-0000-0000-0000-000000000001') <> 'INACTIVE' THEN
    RAISE EXCEPTION 'revoking the only active revision left the data source ACTIVE';
  END IF;
  IF EXISTS (SELECT 1 FROM data_source_revision WHERE data_source_id = '60000000-0000-0000-0000-000000000001' AND lifecycle_state = 'ACTIVE') THEN
    RAISE EXCEPTION 'active revision remained after revoke regression';
  END IF;
END $$;

ROLLBACK;
