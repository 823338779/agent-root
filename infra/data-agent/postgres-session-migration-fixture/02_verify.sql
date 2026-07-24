\set ON_ERROR_STOP on
DO $$ BEGIN
  IF (SELECT count(*) FROM agent_sessions) <> 3 THEN RAISE EXCEPTION 'session count mismatch'; END IF;
  IF (SELECT count(*) FROM agent_messages) <> 1 THEN RAISE EXCEPTION 'message count mismatch'; END IF;
  IF (SELECT count(*) FROM agent_runs) <> 2 THEN RAISE EXCEPTION 'run count mismatch'; END IF;
  IF (SELECT count(*) FROM agent_run_events) <> 1 THEN RAISE EXCEPTION 'event count mismatch'; END IF;
  IF (SELECT count(*) FROM agent_confirmations) <> 1 THEN RAISE EXCEPTION 'confirmation count mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM agent_sessions WHERE id='s_null' AND legacy_payload_json::jsonb->'run' = 'null'::jsonb)
    THEN RAISE EXCEPTION 'JSON null legacy session missing'; END IF;
  IF NOT EXISTS (SELECT 1 FROM agent_sessions WHERE id='s_confirmation' AND created_at='2026-07-01T11:59:59Z'::timestamptz)
    THEN RAISE EXCEPTION 'timezone normalization mismatch'; END IF;
END $$;
SELECT 'PASS' AS result, (SELECT count(*) FROM agent_sessions) sessions,
       (SELECT count(*) FROM agent_messages) messages, (SELECT count(*) FROM agent_runs) runs,
       (SELECT count(*) FROM agent_run_events) events, (SELECT count(*) FROM agent_confirmations) confirmations;
