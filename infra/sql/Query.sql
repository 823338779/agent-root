ALTER TABLE public.agent_sessions OWNER TO data_agent;

SELECT tablename, tableowner
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename = 'agent_sessions';
