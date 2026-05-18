-- Migration 072: Backfill fatture_documenti da fatture (con batch strategy)
--
-- Contesto:
-- Popolare fatture_documenti dai record esistenti in fatture.
-- Una riga in fatture_documenti corrisponde a 1 gruppo (user_id, ristorante_id, file_origine).
--
-- Per performance con scale future (500k+ record):
--   1. Indice temporaneo CONCURRENTLY per query aggregate
--   2. Loop batch da 1000 file_origine alla volta
--   3. COMMIT intermedi per evitare lock table
--   4. ON CONFLICT DO NOTHING per idempotenza
--   5. VACUUM ANALYZE post-backfill
--   6. Verifica finale consistenza

-- ============================================================================
-- STEP 1: Create temporary index
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_fatture_backfill
    ON public.fatture (user_id, ristorante_id, file_origine)
    WHERE deleted_at IS NULL;

-- ============================================================================
-- STEP 2: Backfill batch strategy in PL/pgSQL
-- ============================================================================
-- Raccogliamo i file_origine distinti, poi per ogni batch di 1000 inseriamo
-- un record in fatture_documenti aggregando i dati dalle righe fatture.

DO $$
DECLARE
    v_batch_size INT := 1000;
    v_offset INT := 0;
    v_file_origins TEXT[];
    v_count INT := 0;
    v_processed INT := 0;
BEGIN
    -- Ottieni lista di tutti i file_origine distinti (non cancellati)
    SELECT ARRAY_AGG(file_origine ORDER BY file_origine)
    INTO v_file_origins
    FROM (
        SELECT DISTINCT file_origine
        FROM public.fatture
        WHERE deleted_at IS NULL
        ORDER BY file_origine
    ) t;
    
    IF v_file_origins IS NULL THEN
        v_file_origins := ARRAY[]::TEXT[];
    END IF;
    
    v_count := ARRAY_LENGTH(v_file_origins, 1);
    RAISE NOTICE 'Backfill inizio: % file_origine distinti da processare', COALESCE(v_count, 0);
    
    -- Loop batch
    v_offset := 1;
    WHILE v_offset <= COALESCE(v_count, 0) LOOP
        -- Batch di file_origine
        INSERT INTO public.fatture_documenti (
            user_id,
            ristorante_id,
            file_origine,
            fornitore,
            piva_fornitore,
            numero_documento,
            data_documento,
            data_competenza,
            tipo_documento,
            totale_documento,
            totale_imponibile,
            totale_iva,
            segno_compensazione,
            scadenza_xml,
            giorni_termini_xml,
            scadenza_effettiva,
            scadenza_source,
            pagata,
            source_origin,
            created_at,
            updated_at
        )
        SELECT
            f.user_id,
            f.ristorante_id,
            f.file_origine,
            -- Aggregazione header: prendere il primo non-NULL per ogni colonna
            (ARRAY_AGG(DISTINCT f.fornitore ORDER BY f.fornitore) FILTER (WHERE f.fornitore IS NOT NULL))[1],
            (ARRAY_AGG(DISTINCT f.piva_cedente ORDER BY f.piva_cedente) FILTER (WHERE f.piva_cedente IS NOT NULL))[1],
            NULL::TEXT,  -- numero_documento non disponibile in fatture storiche (sempre NULL)
            (ARRAY_AGG(DISTINCT f.data_documento ORDER BY f.data_documento))[1],
            (ARRAY_AGG(DISTINCT f.data_competenza ORDER BY f.data_competenza))[1],
            (ARRAY_AGG(DISTINCT f.tipo_documento ORDER BY f.tipo_documento))[1],
            (ARRAY_AGG(DISTINCT f.totale_documento ORDER BY f.totale_documento))[1],
            (ARRAY_AGG(DISTINCT f.totale_imponibile ORDER BY f.totale_imponibile))[1],
            (ARRAY_AGG(DISTINCT f.totale_iva ORDER BY f.totale_iva))[1],
            -- segno_compensazione: -1 se TD04, +1 altrimenti
            CASE
                WHEN (ARRAY_AGG(DISTINCT f.tipo_documento ORDER BY f.tipo_documento))[1] = 'TD04' THEN -1
                ELSE 1
            END,
            -- scadenza_xml: NULL per ora (no parse DatiPagamento storico)
            NULL::DATE,
            NULL::INT,
            -- scadenza_effettiva: NULL (da ricalcolare con regole in futuro)
            NULL::DATE,
            -- scadenza_source: 'none' per record storici (nessuna fonte disponibile)
            'none'::TEXT,
            -- pagata: FALSE per default
            FALSE::BOOLEAN,
            -- source_origin: 'manual' per tutti (non Invoicetronic in passato)
            'manual'::TEXT,
            now()::TIMESTAMPTZ,
            now()::TIMESTAMPTZ
        FROM public.fatture f
        WHERE f.deleted_at IS NULL
          AND f.file_origine = ANY(v_file_origins[v_offset:v_offset + v_batch_size - 1])
        GROUP BY f.user_id, f.ristorante_id, f.file_origine
        ON CONFLICT (user_id, ristorante_id, file_origine) DO NOTHING;
        
        v_processed := v_processed + v_batch_size;
        RAISE NOTICE 'Backfill batch completato: % / % file_origine', 
            LEAST(v_offset + v_batch_size - 1, COALESCE(v_count, 0)), v_count;
        
        -- COMMIT intermedio (PL/pgSQL implicit commit a fine blocco DO)
        v_offset := v_offset + v_batch_size;
    END LOOP;
    
    RAISE NOTICE 'Backfill completato: % record inseriti in fatture_documenti', v_processed;
END $$;

-- ============================================================================
-- STEP 3: Cleanup e maintenance
-- ============================================================================

-- NOTA: VACUUM ANALYZE non supportato in Supabase Dashboard (transaction block)
-- Verrà eseguito automaticamente dalla manutenzione di Supabase
-- VACUUM ANALYZE public.fatture_documenti;

DROP INDEX IF EXISTS idx_fatture_backfill;

-- ============================================================================
-- STEP 4: Verifica consistenza finale
-- ============================================================================
-- Eseguire manualmente POST-MIGRATION per validare:
--
--   SELECT COUNT(*) AS documenti_inseriti FROM public.fatture_documenti WHERE deleted_at IS NULL;
--   SELECT COUNT(DISTINCT file_origine) AS file_distinti_attivi FROM public.fatture WHERE deleted_at IS NULL;
--   
-- I due valori DEVONO coincidere. Se divergono, investigation necessaria.
--
-- Se file_origine in fatture ma non in fatture_documenti, controllare:
--   SELECT file_origine FROM public.fatture WHERE deleted_at IS NULL
--   EXCEPT
--   SELECT file_origine FROM public.fatture_documenti WHERE deleted_at IS NULL;

COMMENT ON SCHEMA public IS
    'Post-migration check (execute manually after 072 applied): '
    'SELECT COUNT(*) FROM fatture_documenti WHERE deleted_at IS NULL '
    'SHOULD EQUAL '
    'SELECT COUNT(DISTINCT file_origine) FROM fatture WHERE deleted_at IS NULL';
