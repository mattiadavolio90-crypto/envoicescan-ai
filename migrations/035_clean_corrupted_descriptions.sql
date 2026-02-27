-- ============================================================
-- Migration 035: Pulizia descrizioni corrotte (encoding errato)
-- ============================================================
-- PROBLEMA:
--   Fatture XML da fornitori cinesi codificate in GB2312/GBK
--   venivano decodificate come Latin-1, producendo caratteri
--   come Ü Õ Ä ½ Ç Ã È Ì nei campi descrizione.
--
-- SOLUZIONE:
--   Rimuove tutti i caratteri non-ASCII (range 0x80–0xFF)
--   da fatture.descrizione, prodotti_master.nome/descrizione.
--   Le descrizioni fatture elettroniche italiane sono sempre
--   in ASCII puro (maiuscole, numeri, punteggiatura base).
--
-- SICUREZZA:
--   - WHERE filtra solo le righe che CONTENGONO caratteri estesi
--   - Sostituisce sequenze con un singolo spazio
--   - Fa trim finale per rimuovere spazi iniziali/finali
--   - Non tocca righe già pulite
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. PULISCI fatture.descrizione
-- ────────────────────────────────────────────────────────────
UPDATE fatture
SET descrizione = trim(
    regexp_replace(
        regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'), -- rimuovi non-ASCII
        '\s{2,}', ' ', 'g'                                       -- comprimi spazi multipli
    )
)
WHERE descrizione ~ '[^\x00-\x7F]';   -- solo righe con caratteri corrotti

-- ────────────────────────────────────────────────────────────
-- 2. PULISCI prodotti_master.descrizione
--    Strategia in 3 passi per gestire duplicati post-pulizia:
--    a) Calcola la descrizione pulita per ogni riga corrotta
--    b) Trova le righe che si "scontrano" con righe già pulite
--       o con altre righe corrotte che collassano sullo stesso valore
--    c) Accumula volte_visto sulla riga "vincitrice" ed elimina le altre
-- ────────────────────────────────────────────────────────────
DO $$
DECLARE
    _clean_desc TEXT;
    _winner_id  INT;
    _loser_ids  INT[];
    _total_vv   INT;
BEGIN
    -- Itera sui valori puliti di TUTTE le righe corrotte.
    -- La collision check guarda TUTTE le righe (corrotte + già pulite)
    -- per intercettare anche il caso "riga già pulita con lo stesso valore".
    FOR _clean_desc IN
        SELECT DISTINCT
            trim(regexp_replace(regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'), '\s{2,}', ' ', 'g'))
        FROM prodotti_master
        WHERE descrizione ~ '[^\x00-\x7F]'   -- parte solo da righe corrotte
        ORDER BY 1
    LOOP
        -- Controlla se esiste qualsiasi collisione (riga pulita O altra riga corrotta)
        IF (
            SELECT COUNT(*)
            FROM prodotti_master
            WHERE trim(regexp_replace(regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'), '\s{2,}', ' ', 'g')) = _clean_desc
        ) > 1 THEN

            -- Vincitore: priorità 1) riga già pulita, 2) volte_visto alto, 3) id minore
            SELECT id INTO _winner_id
            FROM prodotti_master
            WHERE trim(regexp_replace(regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'), '\s{2,}', ' ', 'g')) = _clean_desc
            ORDER BY
                CASE WHEN descrizione !~ '[^\x00-\x7F]' THEN 0 ELSE 1 END ASC,
                volte_visto DESC,
                id ASC
            LIMIT 1;

            -- Somma volte_visto di tutti i "perdenti"
            SELECT COALESCE(SUM(volte_visto), 0), array_agg(id)
            INTO _total_vv, _loser_ids
            FROM prodotti_master
            WHERE trim(regexp_replace(regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'), '\s{2,}', ' ', 'g')) = _clean_desc
              AND id <> _winner_id;

            -- Aggiorna vincitore: descrizione pulita + volte_visto cumulati
            UPDATE prodotti_master
            SET descrizione = _clean_desc,
                volte_visto = COALESCE(volte_visto, 0) + _total_vv
            WHERE id = _winner_id;

            -- Elimina i duplicati
            DELETE FROM prodotti_master WHERE id = ANY(_loser_ids);

            RAISE NOTICE 'Merged % row(s) into id=% → "%"', array_length(_loser_ids,1), _winner_id, _clean_desc;
        END IF;
    END LOOP;
END
$$;

-- Aggiorna le righe corrotte rimaste (senza collisioni)
UPDATE prodotti_master
SET descrizione = trim(
    regexp_replace(
        regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'),
        '\s{2,}', ' ', 'g'
    )
)
WHERE descrizione ~ '[^\x00-\x7F]';

-- ────────────────────────────────────────────────────────────
-- 3. PULISCI prodotti_utente.descrizione (se esiste)
-- ────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'prodotti_utente'
          AND column_name = 'descrizione'
    ) THEN
        UPDATE prodotti_utente
        SET descrizione = trim(
            regexp_replace(
                regexp_replace(descrizione, '[^\x00-\x7F]+', ' ', 'g'),
                '\s{2,}', ' ', 'g'
            )
        )
        WHERE descrizione ~ '[^\x00-\x7F]';
    END IF;
END
$$;

-- ────────────────────────────────────────────────────────────
-- 4. Verifica (opzionale – esegui per controllare i risultati)
-- ────────────────────────────────────────────────────────────
-- SELECT COUNT(*) AS ancora_corrotti FROM fatture          WHERE descrizione ~ '[^\x00-\x7F]';
-- SELECT COUNT(*) AS ancora_corrotti FROM prodotti_master  WHERE descrizione ~ '[^\x00-\x7F]';
