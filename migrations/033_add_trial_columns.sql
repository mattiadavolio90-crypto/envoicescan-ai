-- ============================================================
-- Migrazione 033: Aggiunge colonne trial 7 giorni gratuiti
-- Applicare via Supabase SQL Editor
-- 
-- Utenti esistenti: trial_active = FALSE (default) → nessun impatto
-- Admin: non coinvolti (nessuna logica trial applicata a ADMIN_EMAILS)
-- ============================================================

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS trial_activated_at TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS trial_active        BOOLEAN    NOT NULL DEFAULT FALSE;

-- Indice parziale per monitoraggio trial attive (query veloci su sottoinsieme piccolo)
CREATE INDEX IF NOT EXISTS idx_users_trial_active
  ON users(trial_active)
  WHERE trial_active = TRUE;

-- Documentazione colonne
COMMENT ON COLUMN users.trial_activated_at IS
  'Timestamp UTC di attivazione trial 7 giorni. NULL = trial mai attivata.';
COMMENT ON COLUMN users.trial_active IS
  'TRUE se trial attiva (non ancora scaduta). Impostato a FALSE da app al page-load se scaduta.';
