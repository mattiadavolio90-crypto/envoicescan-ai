-- ============================================================
-- MIGRATION 029: Aggiungi last_login e last_logout a users
-- ============================================================
-- Colonne usate da auth_service.py per:
-- - last_login: aggiornato con datetime.now(timezone.utc).isoformat()
--   su login riuscito (riga ~477), filtrato con .eq('id', user['id'])
-- - last_logout: aggiornato con datetime.now(timezone.utc).isoformat()
--   su logout (riga ~625), filtrato con .eq('email', email)
--   Letto con .select('last_logout').eq('email', email) per
--   validare sessioni (riga ~648)
-- ============================================================

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_logout TIMESTAMPTZ;

COMMENT ON COLUMN public.users.last_login IS 'Timestamp ultimo login riuscito (UTC)';
COMMENT ON COLUMN public.users.last_logout IS 'Timestamp ultimo logout (UTC) - usato per invalidare sessioni';

-- Indice su email per la query verifica_sessione_valida()
-- che fa .select('last_logout').eq('email', email)
-- (email dovrebbe già avere un indice/unique, ma aggiungiamo per sicurezza)
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users (email);
