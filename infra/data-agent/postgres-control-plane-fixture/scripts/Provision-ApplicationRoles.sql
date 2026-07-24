-- Run as a PostgreSQL administrator, never as the application account.
-- Role ownership is deliberately outside Flyway because cluster roles are not database-scoped.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='data_agent_owner') THEN
    CREATE ROLE data_agent_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='data_agent_app') THEN
    CREATE ROLE data_agent_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;

GRANT CONNECT ON DATABASE data_agent TO data_agent_app;
GRANT USAGE ON SCHEMA public TO data_agent_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO data_agent_app;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM data_agent_app;
ALTER DEFAULT PRIVILEGES FOR ROLE data_agent_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO data_agent_app;
