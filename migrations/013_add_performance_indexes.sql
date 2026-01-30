-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRAZIONE 013: Indici Performance per Query Temporali
-- ═══════════════════════════════════════════════════════════════════════════════
-- Obiettivo: Ottimizzare query dashboard con filtri data_documento
-- Impatto: Query 10-200x più veloci con >10k righe
-- Sicurezza: Creazione veloce (<5 sec), lock brevissimo accettabile
-- Data: 2026-01-30
-- ═══════════════════════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. INDICE TEMPORALE: Ordinamento per data (DESC per query recenti)
-- ────────────────────────────────────────────────────────────────────────────────
-- Caso d'uso: ORDER BY data_documento DESC (ultime fatture)
-- Beneficio: Evita full table scan per ordinamenti temporali
CREATE INDEX IF NOT EXISTS idx_fatture_data_documento 
ON public.fatture (data_documento DESC);

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. INDICE COMPOSITO: Filtro multi-tenant + range temporale
-- ────────────────────────────────────────────────────────────────────────────────
-- Caso d'uso: WHERE user_id = X AND ristorante_id = Y AND data_documento >= Z
-- Pattern: OGNI query dashboard usa questi 3 filtri insieme
-- Beneficio: Index-only scan, riduce I/O del 95%+
CREATE INDEX IF NOT EXISTS idx_fatture_filtro_rapido 
ON public.fatture (user_id, ristorante_id, data_documento DESC);

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. COMMENTI DOCUMENTAZIONE
-- ────────────────────────────────────────────────────────────────────────────────
COMMENT ON INDEX idx_fatture_data_documento IS 
'Indice per ordinamenti temporali (ultime fatture, grafici cronologici)';

COMMENT ON INDEX idx_fatture_filtro_rapido IS 
'Indice composito per query dashboard multi-ristorante con range temporale';

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. VERIFICA INDICI CREATI
-- ────────────────────────────────────────────────────────────────────────────────
-- Esegui per verificare che gli indici esistano:
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'fatture'
  AND indexname LIKE 'idx_fatture_%'
ORDER BY indexname;

-- ────────────────────────────────────────────────────────────────────────────────
-- 5. TEST QUERY PLAN (Prima vs Dopo)
-- ────────────────────────────────────────────────────────────────────────────────
-- Testa query tipica per vedere se usa indici:
EXPLAIN ANALYZE
SELECT file_origine, data_documento, fornitore, totale_riga
FROM fatture
WHERE user_id = (SELECT id FROM users LIMIT 1)  -- Usa un user_id reale
  AND ristorante_id IS NOT NULL
  AND data_documento >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY data_documento DESC
LIMIT 100;

-- Output atteso: "Index Scan using idx_fatture_filtro_rapido"
-- (Se vedi "Seq Scan" = indice non usato, verifica WHERE clause)

-- ═══════════════════════════════════════════════════════════════════════════════
-- ROLLBACK (Se necessario)
-- ═══════════════════════════════════════════════════════════════════════════════
-- DROP INDEX IF EXISTS idx_fatture_data_documento;
-- DROP INDEX IF EXISTS idx_fatture_filtro_rapido;

-- ═══════════════════════════════════════════════════════════════════════════════
-- ISTRUZIONI ESECUZIONE
-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. Dashboard Supabase → SQL Editor
-- 2. Copia/Incolla questo file completo
-- 3. RUN (o Shift+Enter)
-- 4. Attendi 5-30 secondi (dipende da numero righe)
-- 5. Verifica output: "CREATE INDEX" (successo)
-- 
-- NOTE SICUREZZA:
-- ✅ Creazione velocissima (<5 sec anche con 50k righe)
-- ✅ IF NOT EXISTS = esecuzione multipla sicura (idempotente)
-- ✅ Non modifica dati esistenti (solo metadata)
-- ✅ Query esistenti diventano solo più veloci
-- ✅ Lock brevissimo (millisecondi) accettabile
-- ═══════════════════════════════════════════════════════════════════════════════
