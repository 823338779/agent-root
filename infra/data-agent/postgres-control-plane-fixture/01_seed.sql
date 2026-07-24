\set ON_ERROR_STOP on
BEGIN;

-- Fixed, non-sensitive local fixture identifiers. Re-running this file is idempotent.
INSERT INTO tenant (id, slug, display_name) VALUES
  ('10000000-0000-0000-0000-000000000001', 'tenant_a', 'Tenant A (local fixture)'),
  ('10000000-0000-0000-0000-000000000002', 'tenant_b', 'Tenant B (local fixture)')
ON CONFLICT (id) DO UPDATE SET slug = EXCLUDED.slug, display_name = EXCLUDED.display_name, updated_at = CURRENT_TIMESTAMP;

INSERT INTO user_account (id, external_subject, display_name, enabled) VALUES
  ('20000000-0000-0000-0000-000000000001', 'fixture:tenant_a:admin', 'Tenant A Admin', TRUE),
  ('20000000-0000-0000-0000-000000000002', 'fixture:tenant_a:analyst', 'Tenant A Analyst', TRUE),
  ('20000000-0000-0000-0000-000000000003', 'fixture:tenant_b:admin', 'Tenant B Admin', TRUE),
  ('20000000-0000-0000-0000-000000000004', 'fixture:tenant_b:viewer', 'Tenant B Viewer', TRUE)
ON CONFLICT (id) DO UPDATE SET external_subject = EXCLUDED.external_subject, display_name = EXCLUDED.display_name, enabled = EXCLUDED.enabled, updated_at = CURRENT_TIMESTAMP;

INSERT INTO tenant_membership (id, tenant_id, user_id, status) VALUES
  ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'ACTIVE'),
  ('30000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002', 'ACTIVE'),
  ('30000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000003', 'ACTIVE'),
  ('30000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000004', 'SUSPENDED')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, user_id = EXCLUDED.user_id, status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP;

INSERT INTO tenant_role_binding (id, tenant_id, membership_id, role_code) VALUES
  ('40000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'TENANT_ADMIN'),
  ('40000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000002', 'DATA_ANALYST'),
  ('40000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000003', 'TENANT_ADMIN'),
  ('40000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000004', 'DATA_VIEWER')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, membership_id = EXCLUDED.membership_id, role_code = EXCLUDED.role_code;

INSERT INTO secret_reference (id, tenant_id, provider, reference_uri) VALUES
  ('50000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'LOCAL_TEST', 'local://fixture/tenant_a/source_main'),
  ('50000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'LOCAL_TEST', 'local://fixture/tenant_b/source_main')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, provider = EXCLUDED.provider, reference_uri = EXCLUDED.reference_uri, updated_at = CURRENT_TIMESTAMP;

INSERT INTO data_source (id, tenant_id, name, engine, status) VALUES
  ('60000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'tenant-a-postgres', 'POSTGRESQL', 'ACTIVE'),
  ('60000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'tenant-b-postgres', 'POSTGRESQL', 'ACTIVE')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, name = EXCLUDED.name, engine = EXCLUDED.engine, status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP;

INSERT INTO data_source_revision (id, tenant_id, data_source_id, revision_number, lifecycle_state, jdbc_url, username, secret_reference_id, activated_at, revoked_at) VALUES
  ('70000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 1, 'REVOKED', 'jdbc:postgresql://fixture-a.local:5432/analytics', 'fixture_reader', '50000000-0000-0000-0000-000000000001', NULL, '2026-07-11T00:00:00Z'),
  ('70000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 2, 'ACTIVE', 'jdbc:postgresql://fixture-a.local:5432/analytics', 'fixture_reader', '50000000-0000-0000-0000-000000000001', '2026-07-11T00:05:00Z', NULL),
  ('70000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 3, 'DRAFT', 'jdbc:postgresql://fixture-a.local:5432/analytics_next', 'fixture_reader', '50000000-0000-0000-0000-000000000001', NULL, NULL),
  ('70000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000002', 1, 'REVOKED', 'jdbc:postgresql://fixture-b.local:5432/analytics', 'fixture_reader', '50000000-0000-0000-0000-000000000002', NULL, '2026-07-11T00:00:00Z'),
  ('70000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000002', 2, 'ACTIVE', 'jdbc:postgresql://fixture-b.local:5432/analytics', 'fixture_reader', '50000000-0000-0000-0000-000000000002', '2026-07-11T00:05:00Z', NULL),
  ('70000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000002', 3, 'DRAFT', 'jdbc:postgresql://fixture-b.local:5432/analytics_next', 'fixture_reader', '50000000-0000-0000-0000-000000000002', NULL, NULL)
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, data_source_id = EXCLUDED.data_source_id, revision_number = EXCLUDED.revision_number, lifecycle_state = EXCLUDED.lifecycle_state, jdbc_url = EXCLUDED.jdbc_url, username = EXCLUDED.username, secret_reference_id = EXCLUDED.secret_reference_id, activated_at = EXCLUDED.activated_at, revoked_at = EXCLUDED.revoked_at;

INSERT INTO data_source_policy (id, tenant_id, data_source_id, policy_code, policy_value) VALUES
  ('80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 'CONNECTION_LIMITS', '{"max_connections": 4, "query_timeout_ms": 10000}'::jsonb),
  ('80000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000002', 'CONNECTION_LIMITS', '{"max_connections": 4, "query_timeout_ms": 10000}'::jsonb),
  ('80000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 'SQL_OBJECT_ALLOWLIST', '{"catalog":"default_catalog","database":"tenant_a","allowed_objects":["orders","customers"]}'::jsonb),
  ('80000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', 'SQL_EXECUTION_LIMITS', '{"maximum_rows":1000,"query_timeout_ms":10000,"maximum_concurrency":4,"explain_allowed":false}'::jsonb),
  ('80000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000002', 'SQL_OBJECT_ALLOWLIST', '{"catalog":"default_catalog","database":"tenant_b","allowed_objects":["orders","customers"]}'::jsonb),
  ('80000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000002', '60000000-0000-0000-0000-000000000002', 'SQL_EXECUTION_LIMITS', '{"maximum_rows":1000,"query_timeout_ms":10000,"maximum_concurrency":4,"explain_allowed":false}'::jsonb)
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, data_source_id = EXCLUDED.data_source_id, policy_code = EXCLUDED.policy_code, policy_value = EXCLUDED.policy_value, updated_at = CURRENT_TIMESTAMP;

INSERT INTO audit_event (id, tenant_id, actor_subject, event_type, resource_type, resource_id, detail, occurred_at) VALUES
  ('90000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'fixture:tenant_a:admin', 'DATA_SOURCE_CREATED', 'DATA_SOURCE', '60000000-0000-0000-0000-000000000001', '{"fixture":true}'::jsonb, '2026-07-11T00:00:00Z'),
  ('90000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'fixture:tenant_a:admin', 'DATA_SOURCE_REVISION_ACTIVATED', 'DATA_SOURCE_REVISION', '70000000-0000-0000-0000-000000000002', '{"fixture":true}'::jsonb, '2026-07-11T00:05:00Z'),
  ('90000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000002', 'fixture:tenant_b:admin', 'DATA_SOURCE_CREATED', 'DATA_SOURCE', '60000000-0000-0000-0000-000000000002', '{"fixture":true}'::jsonb, '2026-07-11T00:00:00Z'),
  ('90000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', 'fixture:tenant_b:admin', 'DATA_SOURCE_REVISION_ACTIVATED', 'DATA_SOURCE_REVISION', '70000000-0000-0000-0000-000000000005', '{"fixture":true}'::jsonb, '2026-07-11T00:05:00Z')
ON CONFLICT (id) DO NOTHING;

COMMIT;
