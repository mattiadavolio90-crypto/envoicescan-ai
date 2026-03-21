-- ============================================================
-- Migration 046: Rate limiting reset password persistente su DB
-- Aggiunge colonna last_reset_requested_at su tabella users
-- Sostituisce il dizionario in-memory (perso ad ogni restart Streamlit).
-- ============================================================

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS last_reset_requested_at TIMESTAMPTZ;

COMMENT ON COLUMN public.users.last_reset_requested_at IS
    'Timestamp ultima richiesta reset password — usato per rate limiting DB-backed (5 min cooldown)';
