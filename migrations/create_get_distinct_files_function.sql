-- ============================================================
-- FUNZIONE RPC: Ottieni lista file distinti per user_id
-- ============================================================
-- Questa funzione restituisce solo i nomi file UNICI (DISTINCT)
-- per un determinato user_id, evitando di caricare 6000+ righe
--
-- USO: SELECT * FROM get_distinct_files('user-id-qui')
-- ============================================================

CREATE OR REPLACE FUNCTION get_distinct_files(p_user_id UUID)
RETURNS TABLE (file_origine TEXT) 
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT f.file_origine
    FROM fatture f
    WHERE f.user_id = p_user_id
      AND f.file_origine IS NOT NULL
      AND f.file_origine != ''
    ORDER BY f.file_origine;
END;
$$;

-- Grant permessi per utenti autenticati
GRANT EXECUTE ON FUNCTION get_distinct_files(UUID) TO authenticated;

-- Commento funzione
COMMENT ON FUNCTION get_distinct_files(UUID) IS 
'Restituisce lista file_origine distinti per un user_id. Ottimizzata per deduplicazione upload.';
