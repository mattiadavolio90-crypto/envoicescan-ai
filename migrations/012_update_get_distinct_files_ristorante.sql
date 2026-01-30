-- ============================================================
-- MIGRAZIONE 012: Aggiorna funzione RPC get_distinct_files
-- ============================================================
-- Aggiunge supporto per filtro ristorante_id alla funzione
-- che restituisce la lista dei file distinti
--
-- IMPORTANTE: Eseguire in Supabase SQL Editor
-- ============================================================

-- Drop vecchia funzione
DROP FUNCTION IF EXISTS get_distinct_files(UUID);

-- Ricrea funzione con parametro ristorante_id opzionale
CREATE OR REPLACE FUNCTION get_distinct_files(p_user_id UUID, p_ristorante_id UUID DEFAULT NULL)
RETURNS TABLE (file_origine TEXT) 
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Se ristorante_id è specificato, filtra per ristorante
    IF p_ristorante_id IS NOT NULL THEN
        RETURN QUERY
        SELECT DISTINCT f.file_origine
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = p_ristorante_id
          AND f.file_origine IS NOT NULL
          AND f.file_origine != ''
        ORDER BY f.file_origine;
    ELSE
        -- Altrimenti restituisci tutti i file dell'utente
        RETURN QUERY
        SELECT DISTINCT f.file_origine
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.file_origine IS NOT NULL
          AND f.file_origine != ''
        ORDER BY f.file_origine;
    END IF;
END;
$$;

-- Grant permessi per utenti autenticati
GRANT EXECUTE ON FUNCTION get_distinct_files(UUID, UUID) TO authenticated;

-- Commento funzione
COMMENT ON FUNCTION get_distinct_files(UUID, UUID) IS 
'Restituisce lista file_origine distinti per un user_id e opzionalmente ristorante_id. Ottimizzata per deduplicazione upload.';
