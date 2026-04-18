-- MIGRAZIONE 057: Soft-delete (cestino) per fatture
-- Aggiunge colonna deleted_at + index parziale + aggiorna RPC get_distinct_files
-- Le fatture con deleted_at IS NOT NULL sono nel cestino.
-- Dopo 30 giorni vengono eliminate definitivamente dal worker.

-- 1. Colonna soft-delete
ALTER TABLE public.fatture
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL;

-- 2. Index parziale: query veloci sul cestino
CREATE INDEX IF NOT EXISTS idx_fatture_deleted_at
  ON public.fatture (deleted_at)
  WHERE deleted_at IS NOT NULL;

-- 3. Index parziale: query normali escludono cestino in modo efficiente
CREATE INDEX IF NOT EXISTS idx_fatture_active
  ON public.fatture (user_id, ristorante_id)
  WHERE deleted_at IS NULL;

-- 4. Aggiorna RPC get_distinct_files per escludere fatture nel cestino
DROP FUNCTION IF EXISTS public.get_distinct_files(UUID);
DROP FUNCTION IF EXISTS public.get_distinct_files(UUID, UUID);

CREATE OR REPLACE FUNCTION public.get_distinct_files(
    p_user_id UUID,
    p_ristorante_id UUID DEFAULT NULL
)
RETURNS TABLE(file_origine TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF p_ristorante_id IS NOT NULL
       AND COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = p_user_id
       ) THEN
        RAISE EXCEPTION 'Ristorante non autorizzato';
    END IF;

    RETURN QUERY
    SELECT DISTINCT f.file_origine
    FROM public.fatture AS f
    WHERE f.user_id = p_user_id
      AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
      AND f.file_origine IS NOT NULL
      AND f.file_origine <> ''
      AND f.deleted_at IS NULL          -- escludi cestino
    ORDER BY f.file_origine;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_distinct_files(
    p_user_id UUID
)
RETURNS TABLE(file_origine TEXT)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT f.file_origine
    FROM public.get_distinct_files(p_user_id, NULL::uuid) AS f;
$$;

GRANT EXECUTE ON FUNCTION public.get_distinct_files(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_distinct_files(UUID, UUID) TO authenticated;
