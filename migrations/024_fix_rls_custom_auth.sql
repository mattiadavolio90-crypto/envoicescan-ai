-- ============================================================
-- MIGRATION 024: Fix RLS Policies per Custom Auth
-- ============================================================
-- L'app usa autenticazione custom (tabella users), NON Supabase Auth.
-- Quindi auth.uid() è SEMPRE NULL e current_setting('app.current_user_id') 
-- non viene mai impostato.
--
-- FIX: Sostituire le RLS policies con versioni che funzionano senza auth.uid().
-- La sicurezza è gestita a livello applicativo (Streamlit session state).
-- Essendo un'app server-side, la chiave Supabase non è mai esposta al client.
-- ============================================================

-- ============================================================
-- 1. FIX: ingredienti_workspace
-- ============================================================

-- Drop vecchie policies
DROP POLICY IF EXISTS "ingredienti_workspace_select_policy" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_insert_policy" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_update_policy" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_delete_policy" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_anon_select" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_anon_insert" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_anon_update" ON ingredienti_workspace;
DROP POLICY IF EXISTS "ingredienti_workspace_anon_delete" ON ingredienti_workspace;

-- Nuove policies permissive (sicurezza gestita dall'app)
CREATE POLICY "ingredienti_workspace_select_policy" ON ingredienti_workspace
    FOR SELECT USING (true);

CREATE POLICY "ingredienti_workspace_insert_policy" ON ingredienti_workspace
    FOR INSERT WITH CHECK (true);

CREATE POLICY "ingredienti_workspace_update_policy" ON ingredienti_workspace
    FOR UPDATE USING (true);

CREATE POLICY "ingredienti_workspace_delete_policy" ON ingredienti_workspace
    FOR DELETE USING (true);

-- Grant accesso anon (il default di Supabase potrebbe non includerlo)
GRANT ALL ON ingredienti_workspace TO anon;
GRANT ALL ON ingredienti_workspace TO authenticated;
GRANT ALL ON ingredienti_workspace TO service_role;


-- ============================================================
-- 2. FIX: ricette
-- ============================================================

-- Drop vecchie policies
DROP POLICY IF EXISTS "ricette_select_policy" ON ricette;
DROP POLICY IF EXISTS "ricette_insert_policy" ON ricette;
DROP POLICY IF EXISTS "ricette_update_policy" ON ricette;
DROP POLICY IF EXISTS "ricette_delete_policy" ON ricette;

-- Nuove policies permissive
CREATE POLICY "ricette_select_policy" ON ricette
    FOR SELECT USING (true);

CREATE POLICY "ricette_insert_policy" ON ricette
    FOR INSERT WITH CHECK (true);

CREATE POLICY "ricette_update_policy" ON ricette
    FOR UPDATE USING (true);

CREATE POLICY "ricette_delete_policy" ON ricette
    FOR DELETE USING (true);

-- Grant accesso
GRANT ALL ON ricette TO anon;
GRANT ALL ON ricette TO authenticated;
GRANT ALL ON ricette TO service_role;


-- ============================================================
-- 3. FIX: note_diario
-- ============================================================

-- Drop vecchie policies
DROP POLICY IF EXISTS "note_diario_select_policy" ON note_diario;
DROP POLICY IF EXISTS "note_diario_insert_policy" ON note_diario;
DROP POLICY IF EXISTS "note_diario_update_policy" ON note_diario;
DROP POLICY IF EXISTS "note_diario_delete_policy" ON note_diario;

-- Nuove policies permissive
CREATE POLICY "note_diario_select_policy" ON note_diario
    FOR SELECT USING (true);

CREATE POLICY "note_diario_insert_policy" ON note_diario
    FOR INSERT WITH CHECK (true);

CREATE POLICY "note_diario_update_policy" ON note_diario
    FOR UPDATE USING (true);

CREATE POLICY "note_diario_delete_policy" ON note_diario
    FOR DELETE USING (true);

-- Grant accesso
GRANT ALL ON note_diario TO anon;
GRANT ALL ON note_diario TO authenticated;
GRANT ALL ON note_diario TO service_role;


-- ============================================================
-- 4. FIX: ingredienti_utente
-- ============================================================

-- Drop vecchie policies
DROP POLICY IF EXISTS "ingredienti_utente_select_policy" ON ingredienti_utente;
DROP POLICY IF EXISTS "ingredienti_utente_insert_policy" ON ingredienti_utente;
DROP POLICY IF EXISTS "ingredienti_utente_update_policy" ON ingredienti_utente;
DROP POLICY IF EXISTS "ingredienti_utente_delete_policy" ON ingredienti_utente;

-- Nuove policies permissive
CREATE POLICY "ingredienti_utente_select_policy" ON ingredienti_utente
    FOR SELECT USING (true);

CREATE POLICY "ingredienti_utente_insert_policy" ON ingredienti_utente
    FOR INSERT WITH CHECK (true);

CREATE POLICY "ingredienti_utente_update_policy" ON ingredienti_utente
    FOR UPDATE USING (true);

CREATE POLICY "ingredienti_utente_delete_policy" ON ingredienti_utente
    FOR DELETE USING (true);

-- Grant accesso
GRANT ALL ON ingredienti_utente TO anon;
GRANT ALL ON ingredienti_utente TO authenticated;
GRANT ALL ON ingredienti_utente TO service_role;


-- ============================================================
-- 5. FIX: swap_ricette_order (usa auth.uid() che è NULL)
-- ============================================================

CREATE OR REPLACE FUNCTION swap_ricette_order(
    ricetta_id_1 UUID,
    ricetta_id_2 UUID
)
RETURNS BOOLEAN AS $$
DECLARE
    ordine_1 INTEGER;
    ordine_2 INTEGER;
BEGIN
    -- Recupera ordini attuali (senza auth.uid() che è NULL con custom auth)
    SELECT ordine_visualizzazione INTO ordine_1 
    FROM ricette 
    WHERE id = ricetta_id_1;
    
    SELECT ordine_visualizzazione INTO ordine_2 
    FROM ricette 
    WHERE id = ricetta_id_2;
    
    -- Verifica che entrambe le ricette esistano
    IF ordine_1 IS NULL OR ordine_2 IS NULL THEN
        RAISE EXCEPTION 'Ricette non trovate';
    END IF;
    
    -- Swap atomico
    UPDATE ricette SET ordine_visualizzazione = ordine_2 
    WHERE id = ricetta_id_1;
    
    UPDATE ricette SET ordine_visualizzazione = ordine_1 
    WHERE id = ricetta_id_2;
    
    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Errore swap ordine: %', SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ============================================================
-- VERIFICA
-- ============================================================
-- Esegui per verificare le policies dopo la migrazione:
-- SELECT tablename, policyname, cmd, qual, with_check 
-- FROM pg_policies 
-- WHERE tablename IN ('ingredienti_workspace', 'ricette', 'note_diario', 'ingredienti_utente');
