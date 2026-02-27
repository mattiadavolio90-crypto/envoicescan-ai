-- ============================================================
-- MIGRATION 037: Aggiungi session_token a users
-- ============================================================
-- Colonna usata per sessioni persistenti cookie-based.
-- 
-- Flusso:
--   Login  → genera UUID, salva in DB + cookie
--   Restore→ legge UUID da cookie, valida contro DB
--   Logout → SET session_token = NULL → cookie diventa invalido
-- ============================================================

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS session_token TEXT;

COMMENT ON COLUMN public.users.session_token IS 'Token sessione attiva - NULL = nessuna sessione valida';

CREATE INDEX IF NOT EXISTS idx_users_session_token ON public.users (session_token);
