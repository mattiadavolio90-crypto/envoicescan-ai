-- Migration: 20260524100000_add_privacy_accepted_at
-- Scopo: GDPR Art. 7(1) — Aggiunge colonna per registrare timestamp
--        dell'accettazione della Privacy Policy da parte dell'utente.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS privacy_accepted_at TIMESTAMPTZ;

COMMENT ON COLUMN users.privacy_accepted_at IS
  'Timestamp UTC accettazione Privacy Policy (GDPR Art. 7.1). '
  'Valorizzato al primo accesso tramite form di attivazione account.';
