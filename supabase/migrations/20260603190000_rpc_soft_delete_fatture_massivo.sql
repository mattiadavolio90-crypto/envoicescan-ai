-- RPC atomica per il soft-delete massivo delle fatture di un tenant.
-- Prima il codice faceva count->update->verify in chiamate HTTP separate (non
-- transazionale). Questa RPC esegue l'UPDATE in un solo statement atomico e
-- ritorna il numero di righe spostate nel cestino. Il codice Python la usa con
-- fallback alla logica esistente se la RPC non e' disponibile.
CREATE OR REPLACE FUNCTION public.soft_delete_fatture_massivo(
  p_user_id uuid,
  p_ristorante_id uuid DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_count integer;
BEGIN
  UPDATE public.fatture
  SET deleted_at = now()
  WHERE user_id = p_user_id
    AND deleted_at IS NULL
    AND (p_ristorante_id IS NULL OR ristorante_id = p_ristorante_id);
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

-- SECURITY DEFINER bypassa RLS: eseguibile solo da service_role (unico ruolo usato
-- da ONEFLUX, server-side). Revoca da public/anon/authenticated.
REVOKE EXECUTE ON FUNCTION public.soft_delete_fatture_massivo(uuid, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.soft_delete_fatture_massivo(uuid, uuid) FROM anon;
REVOKE EXECUTE ON FUNCTION public.soft_delete_fatture_massivo(uuid, uuid) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.soft_delete_fatture_massivo(uuid, uuid) TO service_role;
