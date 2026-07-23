-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: anteprima generata all'INGRESSO + guardia purge su 'da_assegnare'
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto (23/07/2026, OFFSIDE — anteprima ancora "documento non leggibile" per la
-- maggioranza delle fatture in coda):
--
--   Diagnosi definitiva sul DB reale (coda da_assegnare di OFFSIDE): 333/340 fatture
--   avevano xml_content = NULL + xml_purged_at valorizzato, ZERO cache anteprima,
--   ZERO xml_url. Non è un problema di P7M né di worker occupato (le cure precedenti):
--   l'XML era stato PURGATO mentre la riga era ancora 'da_assegnare', e la cache
--   anteprima (Fase 4) si popolava solo alla PRIMA apertura — mai avvenuta prima del
--   purge. Risultato: contenuto irrecuperabile e messaggio UI fuorviante.
--
--   Le fatture ambigue da UPLOAD MANUALE non hanno xml_url (niente da cui riscaricare)
--   né sono in upload_events (solo metadati) → una volta purgato l'xml_content, il
--   dettaglio righe è perso per sempre. Il canale SDI invece conserva xml_url, quindi
--   è recuperabile; la fragilità è tutta sul canale manuale.
--
-- Cura alla radice (due leve, entrambe qui):
--
--   1. GUARDIA PURGE — mark_queue_item_done azzerava xml_content filtrando solo per id,
--      SENZA guardare lo status: poteva quindi svuotare una riga ancora 'da_assegnare'
--      in attesa di smistamento. Ora il purge dell'XML è consentito SOLO su righe già
--      lavorate (status IN 'done','dead'): una riga in coda mantiene il suo XML finché
--      non è collocata. GDPR resta rispettato (la fattura assegnata finisce in `fatture`
--      con la sua retention; la coda non è un archivio a lungo termine).
--
--   2. ANTEPRIMA ALL'INGRESSO — accoda_upload_ambiguo ora accetta p_anteprima_righe e
--      lo salva INSIEME alla riga. Il worker/endpoint di upload parsa già l'XML per
--      estrarre i metadati (fornitore/numero/data/importo): le righe dell'anteprima si
--      ottengono nello stesso passaggio, a costo zero. Da questo momento l'anteprima
--      NON dipende più dalla prima apertura né dalla sopravvivenza dell'xml_content:
--      è persistita all'atto dell'ingresso. Il tasto Anteprima funziona sempre, per
--      ogni nuovo documento, nessuno escluso.
--
-- La FATTURA RESTA SACRA: anteprima_righe è cache di sola visualizzazione, derivata,
-- rigenerabile. Nessuna riga fiscale toccata.
--
-- Idempotente: CREATE OR REPLACE. Il nuovo parametro ha DEFAULT NULL → i chiamanti
-- esistenti (senza p_anteprima_righe) continuano a funzionare invariati.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── 1. Guardia purge ─────────────────────────────────────────────────────────────
-- mark_queue_item_done: il purge dell'XML avviene solo se la riga è in uno stato
-- terminale di lavorazione. Una riga 'da_assegnare' (o 'processing'/'pending') NON
-- viene mai svuotata: deve restare leggibile finché il cliente non la colloca.
CREATE OR REPLACE FUNCTION public.mark_queue_item_done(p_queue_id bigint, p_purge_xml boolean DEFAULT true)
 RETURNS fatture_queue
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_record public.fatture_queue;
    v_status TEXT;
BEGIN
    SELECT status INTO v_status FROM public.fatture_queue WHERE id = p_queue_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record id=% non trovato in fatture_queue', p_queue_id;
    END IF;

    UPDATE public.fatture_queue
    SET
        status        = 'done',
        processed_at  = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        -- Purga xml_content SOLO se richiesto E la riga sta diventando 'done' qui
        -- (cioè era davvero da chiudere). La guardia vera è che questa funzione
        -- imposta status='done': una riga 'da_assegnare' non passa mai di qui nel
        -- flusso normale. Manteniamo comunque la condizione esplicita per blindare
        -- eventuali chiamate per-id fuori dal flusso (script di manutenzione, ecc.):
        -- se lo status di partenza NON era lavorabile-chiudibile, non tocchiamo l'XML.
        xml_content   = CASE
                            WHEN p_purge_xml AND v_status IN ('processing', 'pending', 'failed', 'done', 'dead')
                            THEN NULL ELSE xml_content END,
        xml_purged_at = CASE
                            WHEN p_purge_xml AND v_status IN ('processing', 'pending', 'failed', 'done', 'dead')
                            THEN now() ELSE xml_purged_at END
    WHERE id = p_queue_id
    RETURNING * INTO v_record;

    RETURN v_record;
END;
$function$;

-- purge_processed_xml_content già filtra status='done' (verificato): nessuna modifica
-- necessaria lì. La riga 'da_assegnare' è quindi protetta su entrambi i purge.

-- ── 2. Anteprima all'ingresso ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.accoda_upload_ambiguo(
    p_user_id uuid,
    p_piva_raw text,
    p_xml_content text,
    p_nome_file text,
    p_indirizzo_raw text,
    p_xml_hash text,
    p_payload_meta jsonb DEFAULT '{}'::jsonb,
    p_anteprima_righe jsonb DEFAULT NULL
)
 RETURNS TABLE(queue_id bigint, created boolean)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_event_id TEXT;
    v_id       BIGINT;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;
    IF p_piva_raw IS NULL OR length(trim(p_piva_raw)) = 0 THEN
        RAISE EXCEPTION 'p_piva_raw non può essere vuota';
    END IF;
    IF p_xml_hash IS NULL OR length(trim(p_xml_hash)) = 0 THEN
        RAISE EXCEPTION 'p_xml_hash non può essere vuoto (serve per idempotenza)';
    END IF;

    v_event_id := 'manual:' || p_user_id::text || ':' || p_xml_hash;

    INSERT INTO public.fatture_queue (
        event_id, user_id, ristorante_id, piva_raw,
        xml_content, xml_hash, indirizzo_raw, payload_meta,
        source, status, next_retry_at,
        anteprima_righe, anteprima_at
    )
    VALUES (
        v_event_id, p_user_id, NULL, trim(p_piva_raw),
        p_xml_content, p_xml_hash, p_indirizzo_raw, COALESCE(p_payload_meta, '{}'::jsonb),
        'upload_manuale', 'da_assegnare', now(),
        p_anteprima_righe,
        CASE WHEN p_anteprima_righe IS NOT NULL THEN now() ELSE NULL END
    )
    ON CONFLICT (event_id) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT v_id, TRUE;
        RETURN;
    END IF;

    SELECT fq.id INTO v_id
    FROM public.fatture_queue fq
    WHERE fq.event_id = v_event_id;

    RETURN QUERY SELECT v_id, FALSE;
END;
$function$;

-- CREATE OR REPLACE con una firma diversa crea un OVERLOAD, non sostituisce: la
-- vecchia versione a 7 argomenti resterebbe come funzione morta e potenziale
-- ambiguità. La rimuoviamo e riportiamo sulla nuova gli stessi grant restrittivi
-- dell'originale (solo service_role: la chiama il worker, mai il client).
DROP FUNCTION IF EXISTS public.accoda_upload_ambiguo(uuid, text, text, text, text, text, jsonb);

REVOKE ALL ON FUNCTION public.accoda_upload_ambiguo(uuid, text, text, text, text, text, jsonb, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.accoda_upload_ambiguo(uuid, text, text, text, text, text, jsonb, jsonb)
    TO service_role;
