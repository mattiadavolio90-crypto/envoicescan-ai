-- Migration 079: add privacy_accepted_at to users table
-- GDPR Art. 7(1) — il titolare deve poter dimostrare che l'interessato ha
-- prestato il proprio consenso. Salviamo il timestamp dell'accettazione
-- esplicita della Privacy Policy al momento dell'attivazione account.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS privacy_accepted_at TIMESTAMPTZ;

COMMENT ON COLUMN users.privacy_accepted_at IS
  'Timestamp UTC dell''accettazione esplicita della Privacy Policy (GDPR Art. 7.1). '
  'Valorizzato al primo accesso tramite checkbox nel form di attivazione account. '
  'NULL per utenti creati prima della migration 079 (pre-24-maggio-2026).';
