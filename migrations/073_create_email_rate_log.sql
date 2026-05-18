-- Migration 073: tabella rate-limit invio email (anti-spam/loop)
-- Tracciamento invii email per destinatario + finestra temporale.
-- L'app usa service_role_key (bypassa RLS) — non servono policy granulari.

CREATE TABLE IF NOT EXISTS email_rate_log (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    destinatario text       NOT NULL,
    oggetto_hash text        NULL,
    ristorante_id uuid       NULL,
    user_id     uuid         NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Indice principale: lookup per destinatario nelle ultime N minuti/ore
CREATE INDEX IF NOT EXISTS idx_email_rate_log_dest_time
    ON email_rate_log (destinatario, created_at DESC);

-- Indice per cleanup periodico righe vecchie
CREATE INDEX IF NOT EXISTS idx_email_rate_log_created_at
    ON email_rate_log (created_at DESC);

-- RLS: abilitata; service_role bypassa; nessun client deve scrivere
ALTER TABLE email_rate_log ENABLE ROW LEVEL SECURITY;

-- Permessi minimi
GRANT SELECT, INSERT, DELETE ON email_rate_log TO service_role;
REVOKE ALL ON email_rate_log FROM anon;
REVOKE ALL ON email_rate_log FROM authenticated;

COMMENT ON TABLE email_rate_log IS
    'Rate-limit log invii email. Mantenere finestra ~24h, cleanup gestito da app.';
