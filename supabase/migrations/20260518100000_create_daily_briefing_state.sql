-- Migration 075: tabella per lo snapshot giornaliero del Daily Briefing
-- Ogni record rappresenta il briefing generato in una data per uno specifico ristorante/utente.
-- Immutabile per data: upsert su (user_id, ristorante_id, generated_for_date).
-- L'app usa service_role_key (bypassa RLS) — no policy granulari necessarie.

CREATE TABLE IF NOT EXISTS daily_briefing_state (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             text        NOT NULL,
    ristorante_id       text        NOT NULL,
    generated_for_date  date        NOT NULL,
    snapshot            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Unicità per (utente, ristorante, data): un solo briefing per giorno
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_briefing_state_unique
    ON daily_briefing_state (user_id, ristorante_id, generated_for_date);

-- Indici di lookup principali
CREATE INDEX IF NOT EXISTS idx_daily_briefing_state_user_ristorante
    ON daily_briefing_state (user_id, ristorante_id);

CREATE INDEX IF NOT EXISTS idx_daily_briefing_state_generated_for_date
    ON daily_briefing_state (generated_for_date DESC);

ALTER TABLE daily_briefing_state ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON daily_briefing_state TO service_role;
REVOKE ALL ON daily_briefing_state FROM anon;
REVOKE ALL ON daily_briefing_state FROM authenticated;

COMMENT ON TABLE daily_briefing_state IS
    'Snapshot giornaliero del Daily Briefing per utente/ristorante. '
    'Immutabile per data — upsert su (user_id, ristorante_id, generated_for_date).';

COMMENT ON COLUMN daily_briefing_state.snapshot IS
    'JSON del briefing: {bullets: [...], generated_at: ISO, notif_count: int, severity_max: str}';
