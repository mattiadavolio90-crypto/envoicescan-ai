-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRAZIONE 017: RPC Function per creare ristoranti (bypass RLS)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Problema: RLS impedisce insert da client app
-- Soluzione: Funzione RPC con SECURITY DEFINER che bypassa RLS
-- Data: 2026-02-02
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- Funzione per creare ristorante per un utente (bypass RLS)
CREATE OR REPLACE FUNCTION create_ristorante_for_user(
    p_user_id UUID,
    p_nome TEXT,
    p_piva VARCHAR(11),
    p_ragione_sociale TEXT DEFAULT NULL
)
RETURNS TABLE(id UUID, nome_ristorante TEXT, partita_iva VARCHAR(11)) 
SECURITY DEFINER -- Esegue come proprietario funzione, bypassa RLS
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO ristoranti (user_id, nome_ristorante, partita_iva, ragione_sociale, attivo)
    VALUES (p_user_id, p_nome, p_piva, p_ragione_sociale, true)
    RETURNING ristoranti.id, ristoranti.nome_ristorante, ristoranti.partita_iva;
END;
$$ LANGUAGE plpgsql;

-- Grant execute a tutti gli utenti autenticati
GRANT EXECUTE ON FUNCTION create_ristorante_for_user(UUID, TEXT, VARCHAR(11), TEXT) TO authenticated;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- TEST
-- ═══════════════════════════════════════════════════════════════════════════════
-- SELECT * FROM create_ristorante_for_user(
--     'user-id-qui'::UUID,
--     'Test Ristorante',
--     '12345678901',
--     'Test SRL'
-- );
