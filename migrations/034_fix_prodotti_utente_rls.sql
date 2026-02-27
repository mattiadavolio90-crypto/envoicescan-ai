-- ============================================================
-- MIGRATION 034: Fix RLS prodotti_utente per Custom Auth
-- ============================================================
-- La tabella prodotti_utente ha RLS con auth.uid() che è sempre NULL
-- perché l'app usa autenticazione custom (tabella users).
-- Questo causa che la query restituisce SEMPRE 0 righe.
--
-- FIX: Sostituire con policies permissive (sicurezza gestita dall'app).
-- Stessa logica applicata in migration 024 per le altre tabelle.
-- ============================================================

-- Drop vecchia policy restrittiva
DROP POLICY IF EXISTS "Users see own products" ON prodotti_utente;

-- Nuove policies permissive (sicurezza gestita a livello applicativo)
CREATE POLICY "prodotti_utente_select_policy" ON prodotti_utente
    FOR SELECT USING (true);

CREATE POLICY "prodotti_utente_insert_policy" ON prodotti_utente
    FOR INSERT WITH CHECK (true);

CREATE POLICY "prodotti_utente_update_policy" ON prodotti_utente
    FOR UPDATE USING (true);

CREATE POLICY "prodotti_utente_delete_policy" ON prodotti_utente
    FOR DELETE USING (true);

-- Grant accesso a tutti i ruoli Supabase
GRANT ALL ON prodotti_utente TO anon;
GRANT ALL ON prodotti_utente TO authenticated;
GRANT ALL ON prodotti_utente TO service_role;

-- Verifica
-- SELECT count(*) FROM prodotti_utente;
