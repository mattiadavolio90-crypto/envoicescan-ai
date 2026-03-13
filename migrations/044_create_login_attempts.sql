-- Migration 044: Tabella login_attempts per rate limiting persistente su DB
-- Sostituisce il rate limiting in-memory che non funziona su Streamlit Cloud

CREATE TABLE IF NOT EXISTS login_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    attempted_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_email_time
    ON login_attempts(email, attempted_at DESC);

-- RLS: solo service role può leggere/scrivere (nessun utente diretto)
ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY;

-- Nessuna policy per authenticated/anon → solo service_role bypassa RLS
