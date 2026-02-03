-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRAZIONE 011: Aggiunge ristorante_id a tabella fatture
-- ═══════════════════════════════════════════════════════════════════════════════
-- PROBLEMA: Le fatture sono filtrate solo per user_id, quindi tutti i ristoranti
--           dello stesso utente vedono le stesse fatture
-- SOLUZIONE: Aggiunge ristorante_id + migrazione dati esistenti al primo ristorante
-- Data: 2026-01-30
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. AGGIUNGI colonna ristorante_id a tabella fatture
-- ────────────────────────────────────────────────────────────────────────────────
ALTER TABLE fatture 
ADD COLUMN IF NOT EXISTS ristorante_id UUID REFERENCES ristoranti(id) ON DELETE CASCADE;

-- Index per performance
CREATE INDEX IF NOT EXISTS idx_fatture_ristorante_id ON fatture(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_fatture_user_ristorante ON fatture(user_id, ristorante_id);

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. MIGRAZIONE DATI ESISTENTI
-- ────────────────────────────────────────────────────────────────────────────────
-- Assegna tutte le fatture esistenti al primo ristorante dell'utente
UPDATE fatture f
SET ristorante_id = (
    SELECT r.id
    FROM ristoranti r
    WHERE r.user_id = f.user_id
    ORDER BY r.created_at ASC
    LIMIT 1
)
WHERE ristorante_id IS NULL;

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. RENDI ristorante_id OBBLIGATORIO (dopo migrazione dati)
-- ────────────────────────────────────────────────────────────────────────────────
ALTER TABLE fatture 
ALTER COLUMN ristorante_id SET NOT NULL;

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. AGGIORNA RLS POLICIES
-- ────────────────────────────────────────────────────────────────────────────────
-- Drop TUTTE le policies esistenti (vecchie e nuove)
DROP POLICY IF EXISTS "Users can view own fatture" ON fatture;
DROP POLICY IF EXISTS "Users can insert own fatture" ON fatture;
DROP POLICY IF EXISTS "Users can update own fatture" ON fatture;
DROP POLICY IF EXISTS "Users can delete own fatture" ON fatture;
DROP POLICY IF EXISTS "Users can view own fatture per ristorante" ON fatture;
DROP POLICY IF EXISTS "Users can insert own fatture per ristorante" ON fatture;
DROP POLICY IF EXISTS "Users can update own fatture per ristorante" ON fatture;
DROP POLICY IF EXISTS "Users can delete own fatture per ristorante" ON fatture;

-- Nuove policies che includono ristorante_id
CREATE POLICY "Users can view own fatture per ristorante" ON fatture
    FOR SELECT TO authenticated
    USING (
        user_id = auth.uid() 
        AND ristorante_id IN (
            SELECT id FROM ristoranti WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert own fatture per ristorante" ON fatture
    FOR INSERT TO authenticated
    WITH CHECK (
        user_id = auth.uid()
        AND ristorante_id IN (
            SELECT id FROM ristoranti WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update own fatture per ristorante" ON fatture
    FOR UPDATE TO authenticated
    USING (
        user_id = auth.uid()
        AND ristorante_id IN (
            SELECT id FROM ristoranti WHERE user_id = auth.uid()
        )
    )
    WITH CHECK (
        user_id = auth.uid()
        AND ristorante_id IN (
            SELECT id FROM ristoranti WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete own fatture per ristorante" ON fatture
    FOR DELETE TO authenticated
    USING (
        user_id = auth.uid()
        AND ristorante_id IN (
            SELECT id FROM ristoranti WHERE user_id = auth.uid()
        )
    );

-- ────────────────────────────────────────────────────────────────────────────────
-- 5. VERIFICA
-- ────────────────────────────────────────────────────────────────────────────────
-- Conta fatture per ristorante
SELECT 
    r.nome_ristorante,
    r.partita_iva,
    COUNT(f.id) as num_fatture
FROM ristoranti r
LEFT JOIN fatture f ON f.ristorante_id = r.id
GROUP BY r.id, r.nome_ristorante, r.partita_iva
ORDER BY r.nome_ristorante;

-- Verifica nessuna fattura senza ristorante
SELECT COUNT(*) as fatture_senza_ristorante
FROM fatture
WHERE ristorante_id IS NULL;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- ISTRUZIONI ESECUZIONE:
-- 1. Backup database PRIMA di eseguire
-- 2. Dashboard Supabase → SQL Editor → Copia/Incolla questo file → RUN
-- 3. Verifica output: fatture_senza_ristorante = 0
-- 4. Redeploy app con codice aggiornato
-- ═══════════════════════════════════════════════════════════════════════════════
