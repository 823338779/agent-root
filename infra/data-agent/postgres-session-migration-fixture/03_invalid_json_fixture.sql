\set ON_ERROR_STOP on
CREATE TABLE agent_sessions (
  id varchar(80) PRIMARY KEY, title varchar(240) NOT NULL, tag varchar(80) NOT NULL,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, payload_json text NOT NULL
);
CREATE TABLE agent_audit_records (
  id varchar(80) PRIMARY KEY, session_id varchar(80) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  action varchar(120) NOT NULL, occurred_at timestamptz NOT NULL, detail_json text NOT NULL
);
INSERT INTO agent_sessions VALUES ('invalid','invalid','test',now(),now(),'{not-json');
