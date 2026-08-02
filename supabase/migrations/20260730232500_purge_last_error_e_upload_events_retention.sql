-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: purge last_error terminale + retention upload_events (GDPR)
-- ═══════════════════════════════════════════════════════════════════════════════
-- CONTESTO (audit Database, 30/7/2026 — remediation MEDIUM)
--   Due campi diagnostici testuali senza retention, popolati a ogni errore:
--
--   1. fatture_queue.last_error: sovrascritto a ogni tentativo fallito, include
--      frammenti delle eccezioni di salva_fattura_processata (potenzialmente
--      dati della fattura). Sopravvive indefinitamente su righe dead/scartata,
--      che purge_processed_xml_content (filtra status=done) e
--      purge_raw_body_sample (filtra presenza chiave JSONB) non toccano.
--      L'errore serve nell'immediato per capire perché un item è morto, non a
--      distanza di mesi: stesso ragionamento già applicato a raw_body_sample.
--
--   2. upload_events: logga OGNI upload di OGNI cliente con user_email in
--      chiaro + un JSONB libero "details". Cresce con l'uso normale, non solo
--      con gli errori. Nessuna purge esisteva in tutto il repo.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.purge_fatture_queue_last_error(p_retention_days integer DEFAULT 90)
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

    UPDATE public.fatture_queue
    SET last_error = NULL
    WHERE status IN ('dead', 'scartata')
      AND last_error IS NOT NULL
      AND created_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$function$;

COMMENT ON FUNCTION public.purge_fatture_queue_last_error(integer) IS
    'Azzera last_error sulle righe fatture_queue in stato terminale (dead/scartata) '
    'piu vecchie di p_retention_days (default 90). Puo contenere frammenti di dati '
    'fattura nel messaggio di eccezione; le altre purge non coprono questo campo '
    '(filtrano su status=done o su presenza di raw_body_sample).';

REVOKE ALL ON FUNCTION public.purge_fatture_queue_last_error(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_fatture_queue_last_error(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_fatture_queue_last_error(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_fatture_queue_last_error(integer) TO service_role;


CREATE OR REPLACE FUNCTION public.purge_upload_events_retention(p_retention_days integer DEFAULT 365)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_deleted INTEGER;
BEGIN
    IF p_retention_days < 0 THEN
        RAISE EXCEPTION 'p_retention_days deve essere >= 0';
    END IF;

    DELETE FROM public.upload_events
    WHERE created_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;

COMMENT ON FUNCTION public.purge_upload_events_retention(integer) IS
    'Elimina definitivamente le righe upload_events piu vecchie di p_retention_days '
    '(default 365gg = 12 mesi). Log di upload con user_email in chiaro e JSONB '
    'details libero: nessuna purge esisteva prima del 30/7/2026 (audit Database).';

REVOKE ALL ON FUNCTION public.purge_upload_events_retention(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_upload_events_retention(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_upload_events_retention(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_upload_events_retention(integer) TO service_role;
