-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: purge di payload_meta.raw_body_sample (retention GDPR)
-- ═══════════════════════════════════════════════════════════════════════════════
-- CONTESTO
--   La rete di sicurezza del webhook Invoicetronic salva in
--   fatture_queue.payload_meta.raw_body_sample i primi 2KB del body grezzo, per
--   diagnosticare la forma reale di un payload non riconosciuto (bug 22/7/2026).
--   È diagnostica preziosa nell'immediato, ma non ha motivo di restare per sempre.
--
-- IL GAP (audit Edge Functions, 30/7/2026)
--   purge_processed_xml_content azzera xml_content solo su status='done'. Le righe
--   che portano raw_body_sample sono per costruzione 'failed' o 'da_assegnare'
--   (l'evento non era processabile), quindi NON venivano mai toccate da alcun
--   purge: il campo restava a tempo indeterminato.
--
--   L'oggetto Event di Invoicetronic è composto da id numerici, endpoint e
--   timestamp — non PII. Ma raw_body_sample è il body GREZZO: se una forma di
--   payload imprevista includesse dati del cedente/cessionario, finirebbero lì
--   senza scadenza. Applichiamo la minimizzazione (GDPR art. 5.1.c/e) senza
--   perdere la finestra diagnostica.
--
-- SCELTA
--   Retention default 90 giorni: ampia per qualsiasi indagine su un evento
--   anomalo (i casi reali si chiudono in ore), abbastanza corta da non conservare
--   indefinitamente. Rimuove SOLO la chiave raw_body_sample; tutto il resto di
--   payload_meta (resource_id, motivo, endpoint) resta — è quello che serve per
--   capire cosa è successo, e non è PII.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.purge_raw_body_sample(p_retention_days integer DEFAULT 90)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_updated INTEGER;
BEGIN
    IF p_retention_days < 0 THEN
        RAISE EXCEPTION 'p_retention_days deve essere >= 0';
    END IF;

    -- Rimuove la sola chiave diagnostica, preservando il resto di payload_meta.
    UPDATE public.fatture_queue
    SET payload_meta = payload_meta - 'raw_body_sample'
    WHERE payload_meta ? 'raw_body_sample'
      AND created_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$function$;

COMMENT ON FUNCTION public.purge_raw_body_sample(integer) IS
    'Rimuove payload_meta.raw_body_sample dalle righe fatture_queue piu vecchie di '
    'p_retention_days (default 90), preservando il resto di payload_meta. '
    'Minimizzazione GDPR: il campo e diagnostica del body grezzo, non serve a tempo '
    'indeterminato. purge_processed_xml_content non copre queste righe perche filtra '
    'status=done, mentre raw_body_sample sta su righe failed/da_assegnare.';

-- GRANT coerenti col pattern di purge_processed_xml_content: solo service_role
-- (il worker/cron la invoca), mai anon/authenticated.
REVOKE ALL ON FUNCTION public.purge_raw_body_sample(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_raw_body_sample(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_raw_body_sample(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_raw_body_sample(integer) TO service_role;
