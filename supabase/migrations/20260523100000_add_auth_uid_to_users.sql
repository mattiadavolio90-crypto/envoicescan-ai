-- MIGRATION 078: Aggiunge colonna auth_uid a public.users
-- Traccia il legame tra public.users e auth.users (UUID identici dopo backfill FASE 1).
--
-- NOTA: Colonna nullable — non blocca nessun insert esistente.
-- Dopo esecuzione script migrate_users_to_supabase_auth.py, tutti gli utenti
-- avranno auth_uid = id (stessa value, UUID preservato).

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS auth_uid UUID REFERENCES auth.users(id) ON DELETE SET NULL;

-- Dopo il backfill, gli UUID sono identici: popola auth_uid = id per tutti
-- gli utenti che hanno già un corrispondente in auth.users
UPDATE public.users u
SET auth_uid = u.id
WHERE u.auth_uid IS NULL
  AND EXISTS (
    SELECT 1 FROM auth.users a WHERE a.id = u.id
  );

-- Indice per lookup rapido
CREATE INDEX IF NOT EXISTS idx_users_auth_uid ON public.users(auth_uid);

COMMENT ON COLUMN public.users.auth_uid IS
  'FK a auth.users.id. Popolata da migrate_users_to_supabase_auth.py (FASE 1). '
  'Identica a id dopo la migrazione con UUID preservati.';
