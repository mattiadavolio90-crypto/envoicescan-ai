-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRAZIONE 016: Fix RLS Policy INSERT per tabella ristoranti
-- ═══════════════════════════════════════════════════════════════════════════════
-- Problema: Policy RLS impedisce INSERT da parte dell'utente
-- Soluzione: Aggiungi policy esplicita per INSERT
-- Data: 2026-02-02
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. Rimuovi policy vecchie e ricreale con permessi corretti
-- ────────────────────────────────────────────────────────────────────────────────

-- Policy SELECT: Utente vede solo i propri ristoranti
DROP POLICY IF EXISTS "User owns restaurants" ON ristoranti;
DROP POLICY IF EXISTS "Users can select own restaurants" ON ristoranti;
CREATE POLICY "Users can select own restaurants" ON ristoranti
FOR SELECT
USING (user_id = auth.uid() OR user_id IN (SELECT id FROM users WHERE id = auth.uid()));

-- Policy INSERT: Utente può creare ristoranti per se stesso
DROP POLICY IF EXISTS "Users can insert own restaurants" ON ristoranti;
CREATE POLICY "Users can insert own restaurants" ON ristoranti
FOR INSERT
WITH CHECK (user_id = auth.uid() OR user_id IN (SELECT id FROM users WHERE id = auth.uid()));

-- Policy UPDATE: Utente può modificare solo i propri ristoranti
DROP POLICY IF EXISTS "Users can update own restaurants" ON ristoranti;
CREATE POLICY "Users can update own restaurants" ON ristoranti
FOR UPDATE
USING (user_id = auth.uid() OR user_id IN (SELECT id FROM users WHERE id = auth.uid()))
WITH CHECK (user_id = auth.uid() OR user_id IN (SELECT id FROM users WHERE id = auth.uid()));

-- Policy DELETE: Utente può eliminare solo i propri ristoranti
DROP POLICY IF EXISTS "Users can delete own restaurants" ON ristoranti;
CREATE POLICY "Users can delete own restaurants" ON ristoranti
FOR DELETE
USING (user_id = auth.uid() OR user_id IN (SELECT id FROM users WHERE id = auth.uid()));

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. Policy ADMIN: vede e modifica tutto
-- ────────────────────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "Admin sees all restaurants" ON ristoranti;
CREATE POLICY "Admin full access restaurants" ON ristoranti
FOR ALL TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM users 
        WHERE users.id = auth.uid()
        AND users.email IN ('mattiadavolio90@gmail.com', 'admin@envoicescan-ai.com')
    )
);

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- VERIFICA POST-MIGRAZIONE
-- ═══════════════════════════════════════════════════════════════════════════════
-- Esegui per verificare le policy:
-- SELECT schemaname, tablename, policyname, cmd, qual 
-- FROM pg_policies 
-- WHERE tablename = 'ristoranti'
-- ORDER BY policyname;
