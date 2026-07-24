\set ON_ERROR_STOP on
CREATE TABLE agent_sessions (
  id varchar(80) PRIMARY KEY, title varchar(240) NOT NULL, tag varchar(80) NOT NULL,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, payload_json text NOT NULL
);
CREATE TABLE agent_audit_records (
  id varchar(80) PRIMARY KEY, session_id varchar(80) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  action varchar(120) NOT NULL, occurred_at timestamptz NOT NULL, detail_json text NOT NULL
);
INSERT INTO agent_sessions VALUES
('s_null','no run','test','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',
 '{"id":"s_null","title":"no run","tag":"test","createdAt":"2026-01-01T00:00:00Z","updatedAt":"2026-01-01T00:00:00Z","messages":[],"run":null}'),
('s_run','valid run','test','2026-01-01T00:00:00Z','2026-01-01T00:01:00Z',
 '{"id":"s_run","title":"valid run","tag":"test","createdAt":"2026-01-01T00:00:00Z","updatedAt":"2026-01-01T00:01:00Z","messages":[{"id":"m1","role":"USER","author":"user","content":"hello","createdAt":"2026-01-01T00:00:10Z"}],"run":{"id":"r1","status":"COMPLETED","progress":100,"objective":"answer","events":[{"id":"e1","sequence":1,"type":"RUN_STARTED","occurredAt":"2026-01-01T00:00:20Z","runId":"r1","input":{},"output":{},"approved":null}],"pendingConfirmation":null}}'),
('s_confirmation','pending','test','2026-06-30T23:59:59-12:00','2026-07-01T12:00:00+00:00',
 '{"id":"s_confirmation","title":"pending","tag":"test","createdAt":"2026-07-01T11:59:59Z","updatedAt":"2026-07-01T12:00:00Z","messages":[],"run":{"id":"r2","status":"WAITING_CONFIRMATION","progress":50,"objective":"confirm","events":[],"pendingConfirmation":{"id":"c1","title":"Approve","summary":"summary","detail":"detail","requestedAt":"2026-07-01T12:00:00Z"}}}');
INSERT INTO agent_audit_records VALUES ('a1','s_run','SESSION_CREATED','2026-01-01T00:00:00Z','{}');
