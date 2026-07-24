\set ON_ERROR_STOP on

-- Expected fixture counts; total database rows may be higher in a shared local developer database.
WITH actual AS (
  SELECT 'tenant' AS table_name, 2 AS expected_rows, COUNT(*)::integer AS actual_rows FROM tenant WHERE id BETWEEN '10000000-0000-0000-0000-000000000001' AND '10000000-0000-0000-0000-000000000002'
  UNION ALL SELECT 'user_account', 4, COUNT(*)::integer FROM user_account WHERE id BETWEEN '20000000-0000-0000-0000-000000000001' AND '20000000-0000-0000-0000-000000000004'
  UNION ALL SELECT 'tenant_membership', 4, COUNT(*)::integer FROM tenant_membership WHERE id BETWEEN '30000000-0000-0000-0000-000000000001' AND '30000000-0000-0000-0000-000000000004'
  UNION ALL SELECT 'tenant_role_binding', 4, COUNT(*)::integer FROM tenant_role_binding WHERE id BETWEEN '40000000-0000-0000-0000-000000000001' AND '40000000-0000-0000-0000-000000000004'
  UNION ALL SELECT 'secret_reference', 2, COUNT(*)::integer FROM secret_reference WHERE id BETWEEN '50000000-0000-0000-0000-000000000001' AND '50000000-0000-0000-0000-000000000002'
  UNION ALL SELECT 'data_source', 2, COUNT(*)::integer FROM data_source WHERE id BETWEEN '60000000-0000-0000-0000-000000000001' AND '60000000-0000-0000-0000-000000000002'
  UNION ALL SELECT 'data_source_revision', 6, COUNT(*)::integer FROM data_source_revision WHERE id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006'
  UNION ALL SELECT 'data_source_policy', 2, COUNT(*)::integer FROM data_source_policy WHERE id BETWEEN '80000000-0000-0000-0000-000000000001' AND '80000000-0000-0000-0000-000000000002'
  UNION ALL SELECT 'audit_event', 4, COUNT(*)::integer FROM audit_event WHERE id BETWEEN '90000000-0000-0000-0000-000000000001' AND '90000000-0000-0000-0000-000000000004'
)
SELECT table_name, expected_rows, actual_rows, (expected_rows = actual_rows) AS passed FROM actual ORDER BY table_name;

DO $$
DECLARE
  unexpected_count integer;
BEGIN
  WITH actual (table_name, expected_rows, actual_rows) AS (
    SELECT 'tenant', 2, COUNT(*)::integer FROM tenant WHERE id BETWEEN '10000000-0000-0000-0000-000000000001' AND '10000000-0000-0000-0000-000000000002'
    UNION ALL SELECT 'user_account', 4, COUNT(*)::integer FROM user_account WHERE id BETWEEN '20000000-0000-0000-0000-000000000001' AND '20000000-0000-0000-0000-000000000004'
    UNION ALL SELECT 'tenant_membership', 4, COUNT(*)::integer FROM tenant_membership WHERE id BETWEEN '30000000-0000-0000-0000-000000000001' AND '30000000-0000-0000-0000-000000000004'
    UNION ALL SELECT 'tenant_role_binding', 4, COUNT(*)::integer FROM tenant_role_binding WHERE id BETWEEN '40000000-0000-0000-0000-000000000001' AND '40000000-0000-0000-0000-000000000004'
    UNION ALL SELECT 'secret_reference', 2, COUNT(*)::integer FROM secret_reference WHERE id BETWEEN '50000000-0000-0000-0000-000000000001' AND '50000000-0000-0000-0000-000000000002'
    UNION ALL SELECT 'data_source', 2, COUNT(*)::integer FROM data_source WHERE id BETWEEN '60000000-0000-0000-0000-000000000001' AND '60000000-0000-0000-0000-000000000002'
    UNION ALL SELECT 'data_source_revision', 6, COUNT(*)::integer FROM data_source_revision WHERE id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006'
    UNION ALL SELECT 'data_source_policy', 2, COUNT(*)::integer FROM data_source_policy WHERE id BETWEEN '80000000-0000-0000-0000-000000000001' AND '80000000-0000-0000-0000-000000000002'
    UNION ALL SELECT 'audit_event', 4, COUNT(*)::integer FROM audit_event WHERE id BETWEEN '90000000-0000-0000-0000-000000000001' AND '90000000-0000-0000-0000-000000000004'
  )
  SELECT COUNT(*) INTO unexpected_count FROM actual WHERE actual_rows <> expected_rows;
  IF unexpected_count <> 0 THEN
    RAISE EXCEPTION 'fixture row count mismatch in % table(s)', unexpected_count;
  END IF;

  WITH expected (id, tenant_id, actor_subject, event_type, resource_type, resource_id, detail, occurred_at) AS (
    VALUES
      ('90000000-0000-0000-0000-000000000001'::uuid, '10000000-0000-0000-0000-000000000001'::uuid, 'fixture:tenant_a:admin', 'DATA_SOURCE_CREATED', 'DATA_SOURCE', '60000000-0000-0000-0000-000000000001'::uuid, '{"fixture":true}'::jsonb, '2026-07-11T00:00:00Z'::timestamptz),
      ('90000000-0000-0000-0000-000000000002'::uuid, '10000000-0000-0000-0000-000000000001'::uuid, 'fixture:tenant_a:admin', 'DATA_SOURCE_REVISION_ACTIVATED', 'DATA_SOURCE_REVISION', '70000000-0000-0000-0000-000000000002'::uuid, '{"fixture":true}'::jsonb, '2026-07-11T00:05:00Z'::timestamptz),
      ('90000000-0000-0000-0000-000000000003'::uuid, '10000000-0000-0000-0000-000000000002'::uuid, 'fixture:tenant_b:admin', 'DATA_SOURCE_CREATED', 'DATA_SOURCE', '60000000-0000-0000-0000-000000000002'::uuid, '{"fixture":true}'::jsonb, '2026-07-11T00:00:00Z'::timestamptz),
      ('90000000-0000-0000-0000-000000000004'::uuid, '10000000-0000-0000-0000-000000000002'::uuid, 'fixture:tenant_b:admin', 'DATA_SOURCE_REVISION_ACTIVATED', 'DATA_SOURCE_REVISION', '70000000-0000-0000-0000-000000000005'::uuid, '{"fixture":true}'::jsonb, '2026-07-11T00:05:00Z'::timestamptz)
  )
  SELECT COUNT(*) INTO unexpected_count
  FROM expected e
  FULL JOIN audit_event a USING (id)
  WHERE COALESCE(a.id, e.id) BETWEEN '90000000-0000-0000-0000-000000000001' AND '90000000-0000-0000-0000-000000000004'
    AND (a.tenant_id, a.actor_subject, a.event_type, a.resource_type, a.resource_id, a.detail, a.occurred_at)
        IS DISTINCT FROM
        (e.tenant_id, e.actor_subject, e.event_type, e.resource_type, e.resource_id, e.detail, e.occurred_at);
  IF unexpected_count <> 0 THEN
    RAISE EXCEPTION 'append-only fixture audit history differs from the deterministic baseline; recreate data_agent_test';
  END IF;

  SELECT COUNT(*) INTO unexpected_count
  FROM tenant_role_binding rb
  JOIN tenant_membership m ON m.id = rb.membership_id
  WHERE rb.id BETWEEN '40000000-0000-0000-0000-000000000001' AND '40000000-0000-0000-0000-000000000004'
    AND rb.tenant_id <> m.tenant_id;
  IF unexpected_count <> 0 THEN RAISE EXCEPTION 'fixture contains % cross-tenant role bindings', unexpected_count; END IF;

  SELECT COUNT(*) INTO unexpected_count
  FROM data_source_revision r
  JOIN data_source s ON s.id = r.data_source_id
  LEFT JOIN secret_reference sr ON sr.id = r.secret_reference_id
  WHERE r.id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006'
    AND (r.tenant_id <> s.tenant_id OR (sr.id IS NOT NULL AND r.tenant_id <> sr.tenant_id));
  IF unexpected_count <> 0 THEN RAISE EXCEPTION 'fixture contains % cross-tenant revision links', unexpected_count; END IF;

  SELECT COUNT(*) INTO unexpected_count
  FROM data_source_revision
  WHERE id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006'
    AND lifecycle_state NOT IN ('DRAFT', 'ACTIVE', 'REVOKED');
  IF unexpected_count <> 0 THEN RAISE EXCEPTION 'fixture contains % invalid revision lifecycle values', unexpected_count; END IF;

  IF (SELECT COUNT(*) FROM data_source_revision WHERE id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006' AND lifecycle_state = 'DRAFT') <> 2 THEN RAISE EXCEPTION 'expected exactly 2 DRAFT revisions'; END IF;
  IF (SELECT COUNT(*) FROM data_source_revision WHERE id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006' AND lifecycle_state = 'ACTIVE') <> 2 THEN RAISE EXCEPTION 'expected exactly 2 ACTIVE revisions'; END IF;
  IF (SELECT COUNT(*) FROM data_source_revision WHERE id BETWEEN '70000000-0000-0000-0000-000000000001' AND '70000000-0000-0000-0000-000000000006' AND lifecycle_state = 'REVOKED') <> 2 THEN RAISE EXCEPTION 'expected exactly 2 REVOKED revisions'; END IF;
END $$;
