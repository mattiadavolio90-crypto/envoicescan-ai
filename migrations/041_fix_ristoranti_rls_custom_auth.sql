-- ============================================================
-- MIGRATION 041: Fix RLS Policy tabella ristoranti per Custom Auth
-- ============================================================
-- Problema: Migration 016 ha creato policies che usano auth.uid(),
-- ma l'app usa autenticazione custom (tabella users), NON Supabase Auth.
-- Quindi auth.uid() è SEMPRE NULL → INSERT/SELECT su ristoranti fallisce
-- silenziosamente → ristorante_id rimane NULL → errore missing_ristorante_id
-- al salvataggio fatture.
--
-- Fix: Sostituire policies con versioni permissive (sicurezza a livello app).
-- Pattern identico a migration 024 per le altre tabelle.
-- Data: 2026-03-10
-- ============================================================

BEGIN;

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. Rimuovi TUTTE le vecchie policies sulla tabella ristoranti
-- ────────────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "User owns restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Users can select own restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Users can insert own restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Users can update own restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Users can delete own restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Admin sees all restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Admin full access restaurants" ON ristoranti;

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. Crea nuove policies permissive (sicurezza gestita dall'app Streamlit)
-- ────────────────────────────────────────────────────────────────────────────────
CREATE POLICY "ristoranti_select_policy" ON ristoranti
    FOR SELECT USING (true);

CREATE POLICY "ristoranti_insert_policy" ON ristoranti
    FOR INSERT WITH CHECK (true);

CREATE POLICY "ristoranti_update_policy" ON ristoranti
    FOR UPDATE USING (true);

CREATE POLICY "ristoranti_delete_policy" ON ristoranti
    FOR DELETE USING (true);

-- Grant espliciti per evitare problemi di permessi
GRANT ALL ON ristoranti TO anon;
GRANT ALL ON ristoranti TO authenticated;
GRANT ALL ON ristoranti TO service_role;

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. Assicurati che RLS sia abilitata (deve essere ON per le policies)
-- ────────────────────────────────────────────────────────────────────────────────
ALTER TABLE ristoranti ENABLE ROW LEVEL SECURITY;

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. Crea ristorante mancante per utenti con partita_iva ma senza record
--    (ripete migration 015 in modo idempotente)
-- ────────────────────────────────────────────────────────────────────────────────
INSERT INTO ristoranti (user_id, nome_ristorante, partita_iva, ragione_sociale, attivo)
SELECT
    u.id,
    COALESCE(NULLIF(u.nome_ristorante, ''), 'Ristorante ' || u.partita_iva),
    u.partita_iva,
    COALESCE(u.ragione_sociale, u.nome_ristorante, ''),
    true
FROM users u
WHERE u.partita_iva IS NOT NULL
  AND u.partita_iva != ''
  AND NOT EXISTS (
      SELECT 1
      FROM ristoranti r
      WHERE r.user_id = u.id
  );

COMMIT;

-- ============================================================
-- VERIFICA POST-MIGRAZIONE
-- ============================================================
-- Esegui per verificare:
-- SELECT tablename, policyname, cmd, qual, with_check
-- FROM pg_policies
-- WHERE tablename = 'ristoranti';
--
-- SELECT u.email, u.partita_iva, r.id as ristorante_id, r.nome_ristorante
-- FROM users u
-- LEFT JOIN ristoranti r ON r.user_id = u.id
-- WHERE u.partita_iva IS NOT NULL
-- ORDER BY u.email;
