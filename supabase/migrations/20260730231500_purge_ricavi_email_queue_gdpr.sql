-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: retention GDPR per ricavi_email_queue (dati testuali)
-- ═══════════════════════════════════════════════════════════════════════════════
-- CONTESTO (audit Database, 30/7/2026 — remediation MEDIUM)
--   ricavi_email_queue non aveva alcuna retention, a differenza della gemella
--   fatture_queue (purge_processed_xml_content + purge_raw_body_sample). Le
--   righe accumulano email_sender/email_subject/attachment_name/last_error a
--   tempo indeterminato — dati personali/aziendali del cliente (mittente e
--   oggetto email), non solo metadati tecnici.
--
--   Questa funzione copre la parte testuale in tabella. La rimozione del file
--   XLS dal bucket Storage "ricavi-xls" (il dato più sensibile: fatturato
--   giornaliero completo) è gestita separatamente dal worker Python
--   (worker/email_queue_processor.py, vedi _purge_ricavi_xls_storage) perché
--   Storage non è raggiungibile da una funzione SQL.
--
--   Retention 90gg, stessa scelta già fatta per raw_body_sample
--   (20260730210000): ampia per qualsiasi indagine su un import anomalo,
--   corta abbastanza da non conservare indefinitamente. idempotency_key NON
--   viene mai toccata — è ciò che rende idempotenti le riconsegne dell'Edge
--   Function, deve sopravvivere quanto la riga stessa.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.purge_ricavi_email_queue(p_retention_days integer DEFAULT 90)
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

    UPDATE public.ricavi_email_queue
    SET email_subject   = NULL,
        attachment_name = NULL,
        last_error      = NULL
    WHERE status IN ('done', 'dead')
      AND created_at < now() - make_interval(days => p_retention_days)
      AND (email_subject IS NOT NULL OR attachment_name IS NOT NULL OR last_error IS NOT NULL);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$function$;

COMMENT ON FUNCTION public.purge_ricavi_email_queue(integer) IS
    'Azzera email_subject/attachment_name/last_error sulle righe ricavi_email_queue '
    'in stato terminale (done/dead) piu vecchie di p_retention_days (default 90). '
    'Minimizzazione GDPR: coerente con purge_raw_body_sample su fatture_queue. '
    'idempotency_key/email_sender/storage_path NON toccati: servono a diagnosticare '
    'duplicati e restano finche la riga esiste.';

REVOKE ALL ON FUNCTION public.purge_ricavi_email_queue(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_ricavi_email_queue(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_ricavi_email_queue(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_ricavi_email_queue(integer) TO service_role;
