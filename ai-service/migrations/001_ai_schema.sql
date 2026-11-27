-- QĐ-HARNESS-017 / INV-HARNESS-04. Run as the database migration administrator.
BEGIN;

DO $migration$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_service') THEN
        CREATE ROLE ai_service LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;

    IF EXISTS (
        SELECT FROM pg_roles
        WHERE rolname = 'ai_service'
          AND (rolsuper OR rolinherit OR rolcreatedb OR rolcreaterole
               OR rolreplication OR rolbypassrls OR NOT rolcanlogin)
    ) OR EXISTS (
        SELECT FROM pg_auth_members
        WHERE member = 'ai_service'::regrole
    ) THEN
        RAISE EXCEPTION 'ai_service must be a restricted login without role memberships';
    END IF;

    -- Check effective ACLs, including grants to PUBLIC. The BE owns these ACLs.
    IF has_schema_privilege('ai_service', 'public', 'CREATE') OR EXISTS (
        SELECT FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND CASE
              WHEN c.relkind = 'S' THEN
                  has_sequence_privilege('ai_service', c.oid, 'USAGE, SELECT, UPDATE')
              WHEN c.relkind IN ('r', 'p', 'v', 'm', 'f') THEN
                  has_table_privilege(
                      'ai_service', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
                  ) OR has_any_column_privilege(
                      'ai_service', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'
                  )
              ELSE false
          END
    ) OR EXISTS (
        SELECT FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prosecdef
          AND has_function_privilege('ai_service', p.oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ai_service has effective access in public; have the BE owner review its ACLs';
    END IF;
END;
$migration$;

CREATE SCHEMA IF NOT EXISTS ai AUTHORIZATION ai_service;
ALTER SCHEMA ai OWNER TO ai_service;
REVOKE ALL ON SCHEMA ai FROM PUBLIC;
ALTER ROLE ai_service SET search_path = pg_catalog, ai;

SET LOCAL ROLE ai_service;

CREATE TABLE IF NOT EXISTS ai.pending_action (
    id          text PRIMARY KEY,
    user_id     text NOT NULL,
    turn_id     text NOT NULL,
    tool        text NOT NULL,
    args        jsonb NOT NULL,
    risk        text NOT NULL CHECK (risk IN ('read', 'low', 'medium', 'high')),
    source      text NOT NULL CHECK (source IN ('chat', 'proactive', 'document')),
    preview     jsonb NOT NULL,
    status      text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai.messages (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          text NOT NULL,
    conversation_id  text NOT NULL,
    turn_id          text NOT NULL,
    role             text NOT NULL,
    content          jsonb NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_context_idx
    ON ai.messages (user_id, conversation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai.conversation_summary (
    conversation_id  text NOT NULL,
    user_id          text NOT NULL,
    summary          text NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, conversation_id)
);

CREATE TABLE IF NOT EXISTS ai.usage_daily (
    user_id        text NOT NULL,
    date           date NOT NULL,
    messages       integer NOT NULL DEFAULT 0 CHECK (messages >= 0),
    input_tokens   bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens  bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    model          text,
    PRIMARY KEY (user_id, date)
);

REVOKE ALL ON ALL TABLES IN SCHEMA ai FROM PUBLIC;
COMMIT;
