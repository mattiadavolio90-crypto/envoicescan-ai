-- Migration 074: lock per evitare upload concorrenti sullo stesso ristorante
-- Strategia: row-lock idempotente con cleanup di lock "vecchi" (>10 min).
-- L'app usa service_role_key (bypassa RLS) — no policy granulari necessarie.

CREATE TABLE IF NOT EXISTS upload_locks (
    ristorante_id uuid        PRIMARY KEY,
    user_id       uuid        NOT NULL,
    locked_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_upload_locks_locked_at
    ON upload_locks (locked_at DESC);

ALTER TABLE upload_locks ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON upload_locks TO service_role;
REVOKE ALL ON upload_locks FROM anon;
REVOKE ALL ON upload_locks FROM authenticated;

COMMENT ON TABLE upload_locks IS
    'Lock di concorrenza per upload fatture. PK su ristorante_id. Cleanup app-managed (>10 min).';
