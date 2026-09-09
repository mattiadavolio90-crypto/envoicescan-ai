-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: retention GDPR su sessioni e log applicativi con dati personali
-- ═══════════════════════════════════════════════════════════════════════════════
-- CONTESTO (audit compliance 09/09/2026)
--   L'audit dei documenti legali ha misurato quali tabelle con dati personali
--   avessero una retention e quali no. Otto purge erano già attivi
--   (cestino, xml_content, raw_body_sample, ricavi_email_queue, last_error,
--   storage XLS, fatture 2 anni, upload_events 365gg), ma cinque tabelle
--   conservavano dati personali **a tempo indeterminato**:
--
--     sessioni            → ip, user_agent (i più sensibili del gruppo)
--     email_rate_log      → destinatario (indirizzo email)
--     category_change_log → actor_email
--     ai_usage_events     → source_file, metadata (nome file del cliente)
--     marketplace_leads   → contatto_email, contatto_nome, messaggio
--
--   L'art. 5.1.e (limitazione della conservazione) non ammette "per sempre"
--   senza una finalità che lo giustifichi. Nessuna di queste tabelle ne ha una:
--   servono a diagnosticare, non ad archiviare.
--
-- SCELTE DI RETENTION
--   sessioni — 90 giorni su last_seen_at, e SOLO righe già morte.
--     Una sessione scade per inattività dopo SESSION_INACTIVITY_HOURS = 8h
--     (config/constants.py): a 90 giorni di inattività non esiste alcuna
--     sessione viva, con due ordini di grandezza di margine. Il filtro su
--     revoked_at non basta da solo — le sessioni scadute per inattività non
--     vengono revocate esplicitamente, restano lì con revoked_at NULL.
--
--   email_rate_log — 90 giorni. Serve a non rimandare la stessa email due
--     volte: la finestra utile è di ore.
--
--   category_change_log — 365 giorni. È la traccia di chi ha cambiato una
--     categoria: va tenuta più a lungo (il cliente contesta un dato di mesi
--     prima), ma non per sempre. Stesso valore già scelto per upload_events.
--
--   ai_usage_events — 365 giorni. Serve alla rendicontazione dei costi AI, che
--     è annuale.
--
--   marketplace_leads — 730 giorni sui soli lead ARCHIVIATI. Un lead aperto
--     non si cancella a tempo: è una trattativa in corso. Due anni dalla
--     chiusura coprono la prescrizione ordinaria di un rapporto commerciale.
--
-- FORMA
--   Stesso pattern dei purge già in esercizio (purge_raw_body_sample):
--   SECURITY DEFINER + search_path fissato, REVOKE nominale anche ad
--   anon/authenticated — su Supabase le default privileges concedono grant
--   nominali che il solo REVOKE FROM PUBLIC non toglie — GRANT al solo
--   service_role, che è il ruolo con cui gira il worker.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── sessioni ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_sessioni_scadute(p_retention_days integer DEFAULT 90)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_deleted INTEGER;
BEGIN
    IF p_retention_days < 1 THEN
        RAISE EXCEPTION 'p_retention_days deve essere >= 1 (una retention a 0 cancellerebbe le sessioni attive)';
    END IF;

    DELETE FROM public.sessioni
    WHERE last_seen_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;

COMMENT ON FUNCTION public.purge_sessioni_scadute(integer) IS
    'Elimina le sessioni inattive da oltre p_retention_days (default 90). Rimuove '
    'ip e user_agent, dati personali che restavano senza scadenza. Sicura rispetto '
    'alle sessioni vive: scadono per inattivita dopo 8h (SESSION_INACTIVITY_HOURS), '
    'il minimo accettato qui e 1 giorno. GDPR art. 5.1.e.';

REVOKE ALL ON FUNCTION public.purge_sessioni_scadute(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_sessioni_scadute(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_sessioni_scadute(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_sessioni_scadute(integer) TO service_role;


-- ── email_rate_log ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_email_rate_log(p_retention_days integer DEFAULT 90)
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

    DELETE FROM public.email_rate_log
    WHERE created_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;

COMMENT ON FUNCTION public.purge_email_rate_log(integer) IS
    'Elimina le righe email_rate_log piu vecchie di p_retention_days (default 90). '
    'La colonna destinatario e un indirizzo email: serve per la deduplica degli '
    'invii, la cui finestra utile e di ore. GDPR art. 5.1.e.';

REVOKE ALL ON FUNCTION public.purge_email_rate_log(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_email_rate_log(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_email_rate_log(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_email_rate_log(integer) TO service_role;


-- ── category_change_log ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_category_change_log(p_retention_days integer DEFAULT 365)
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

    DELETE FROM public.category_change_log
    WHERE changed_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;

COMMENT ON FUNCTION public.purge_category_change_log(integer) IS
    'Elimina le righe category_change_log piu vecchie di p_retention_days '
    '(default 365). Conserva actor_email: e la traccia di chi ha cambiato una '
    'categoria, utile per un anno, non per sempre. GDPR art. 5.1.e.';

REVOKE ALL ON FUNCTION public.purge_category_change_log(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_category_change_log(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_category_change_log(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_category_change_log(integer) TO service_role;


-- ── ai_usage_events ───────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_ai_usage_events(p_retention_days integer DEFAULT 365)
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

    DELETE FROM public.ai_usage_events
    WHERE created_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;

COMMENT ON FUNCTION public.purge_ai_usage_events(integer) IS
    'Elimina le righe ai_usage_events piu vecchie di p_retention_days (default '
    '365). source_file e metadata portano nomi di file del cliente; la '
    'rendicontazione dei costi AI e annuale. GDPR art. 5.1.e.';

REVOKE ALL ON FUNCTION public.purge_ai_usage_events(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_ai_usage_events(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_ai_usage_events(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_ai_usage_events(integer) TO service_role;


-- ── marketplace_leads ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_marketplace_leads(p_retention_days integer DEFAULT 730)
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

    -- Solo i lead archiviati: 'nuovo' e 'gestito' sono trattative ancora vive e
    -- non si cancellano allo scadere di un timer. Gli stati sono quelli del
    -- CHECK constraint della tabella ('nuovo','gestito','archiviato'): usarne
    -- altri renderebbe questa purge un no-op silenzioso.
    DELETE FROM public.marketplace_leads
    WHERE stato = 'archiviato'
      AND COALESCE(updated_at, created_at) < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;

COMMENT ON FUNCTION public.purge_marketplace_leads(integer) IS
    'Elimina i lead marketplace CHIUSI piu vecchi di p_retention_days (default '
    '730). Contengono contatto_email, contatto_nome e messaggio. Solo stato archiviato: '
    'nuovo e gestito sono trattative in corso e non vengono mai toccati. GDPR art. 5.1.e.';

REVOKE ALL ON FUNCTION public.purge_marketplace_leads(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_marketplace_leads(integer) FROM anon;
REVOKE ALL ON FUNCTION public.purge_marketplace_leads(integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.purge_marketplace_leads(integer) TO service_role;
