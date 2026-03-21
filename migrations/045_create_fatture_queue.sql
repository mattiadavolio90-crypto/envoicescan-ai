-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRATION 045: Tabella fatture_queue per ricezione webhook Invoicetronic
-- ═══════════════════════════════════════════════════════════════════════════════
-- Scopo:
--   Riceve le notifiche SDI inoltrate da Invoicetronic (codice dest. 7HD37X0).
--   Funge da buffer persistente prima dell'elaborazione asincrona.
--
-- Flusso:
--   Invoicetronic webhook → INSERT in fatture_queue (status=pending)
--     → Worker (Edge Function, service_role) chiama claim_batch_for_processing()
--       → processa XML, risolve P.IVA → crea record in tabella fatture
--         → mark_queue_item_done()   ← xml_content nullificato auto (GDPR)
--   Se P.IVA sconosciuta → status = unknown_tenant (mai scartato)
--     → quando P.IVA aggiunta al DB → resolve_unknown_tenant(piva) → pending
--
-- Sicurezza:
--   RLS ABILITATA senza policy per anon/authenticated.
--   Solo service_role bypassa RLS (Supabase default behavior).
--   Il frontend Streamlit NON deve mai accedere a questa tabella.
--   Pattern identico a migration 044 (login_attempts).
--
-- Naming:
--   user_id / ristorante_id (con underscore) — consistente con tabelle
--   ristoranti, fatture, prodotti_utente, ecc.
--
-- Compatibilità: PostgreSQL 15, Supabase free tier (no pg_cron)
-- Data: 2026-03-20
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. TIPO ENUM per status (garantisce integrità a livello DB senza lista string)
-- ─────────────────────────────────────────────────────────────────────────────
-- Non usiamo CREATE TYPE ENUM per non complicare ALTER futuri su Supabase.
-- Il CHECK constraint sotto svolge la stessa funzione con più flessibilità.

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. TABELLA PRINCIPALE
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.fatture_queue (

    -- ── Identità evento ────────────────────────────────────────────────────
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id        TEXT        NOT NULL,
        -- ID univoco fornito da Invoicetronic nel webhook.
        -- Garantisce idempotenza: re-invii dello stesso evento non duplicano.
        -- UNIQUE constraint più sotto.

    -- ── Risoluzione tenant ─────────────────────────────────────────────────
    user_id         UUID,
        -- FK logica verso public.users(id). Nullable perché popolato DOPO
        -- il lookup P.IVA; NULL quando tenant non trovato (unknown_tenant).
        -- NON FK reale: evita errori di integrità referenziale quando
        -- il record arriva prima della registrazione del ristorante.
    ristorante_id   UUID,
        -- FK logica verso public.ristoranti(id). Stessa logica di user_id.
    piva_raw        TEXT        NOT NULL,
        -- P.IVA destinatario estratta dall'XML (Cessionario/Committente).
        -- Usata per il lookup su ristoranti.partita_iva.
        -- Conservata anche dopo la risoluzione per audit e re-lookup.

    -- ── Payload XML ────────────────────────────────────────────────────────
    xml_content     TEXT,
        -- Contenuto XML grezzo del file FatturaPA.
        -- Nullificato dopo elaborazione per minimizzazione GDPR.
        -- Se NULL + xml_url non NULL → XML recuperabile da Invoicetronic.
    xml_url         TEXT,
        -- URL di download originale su Invoicetronic.
        -- Conservato per recupero XML dopo purge GDPR.
    xml_hash        TEXT,
        -- SHA-256 (hex) dell'xml_content originale.
        -- Utile per deduplicazione alternativa se event_id non è affidabile,
        -- e per verificare integrità all'atto del recupero da xml_url.
    payload_meta    JSONB,
        -- Metadati estratti dal webhook / XML (senza dati personali):
        -- { "numero_fattura": "123", "data_fattura": "2026-01-15",
        --   "piva_cedente": "01234567890", "importo_totale": 1230.50,
        --   "tipo_documento": "TD01", "nome_file": "IT01234_001.xml" }
        -- Permette query senza ri-parsare l'XML.

    -- ── Sorgente e routing ─────────────────────────────────────────────────
    source          TEXT        NOT NULL DEFAULT 'invoicetronic',
        -- Identificatore del canale di ricezione.
        -- Estendibile in futuro: 'email', 'upload_manuale', ecc.
    correlation_id  TEXT,
        -- ID di correlazione per distributed tracing (es. X-Request-ID
        -- del webhook HTTP). Utile per debug cross-sistema.

    -- ── Gestione stati ─────────────────────────────────────────────────────
    status          TEXT        NOT NULL DEFAULT 'pending',
        -- Macchina a stati:
        --   pending         → in attesa di elaborazione
        --   processing      → claimato da un worker, elaborazione in corso
        --   done            → elaborato con successo (fattura creata)
        --   failed          → errore temporaneo, retry schedulato
        --   dead            → max_attempts raggiunto, nessun retry
        --   unknown_tenant  → P.IVA non trovata in DB, in attesa di risoluzione

    -- ── Retry e backoff ────────────────────────────────────────────────────
    attempt_count   INTEGER     NOT NULL DEFAULT 0,
        -- Numero di tentativi di elaborazione effettuati finora.
    max_attempts    INTEGER     NOT NULL DEFAULT 8,
        -- Tentativi massimi prima di passare a dead.
        -- Default 8 → copertura ~4h con backoff 30s×2^n (cap 1h).
    next_retry_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- Timestamp dal quale il record è disponibile per il polling.
        -- Aggiornato da schedule_retry() con backoff esponenziale + jitter.

    -- ── Lock per concorrenza ───────────────────────────────────────────────
    locked_at       TIMESTAMPTZ,
        -- Timestamp in cui il worker ha acquisito il lock.
        -- Usato per rilevare lock stale (worker crashato).
    locked_by       TEXT,
        -- Identificatore univoco del worker (es. "worker-prod-1", UUID invocazione).
        -- Permette di distinguere lock propri da lock altrui.

    -- ── Diagnostica errori ─────────────────────────────────────────────────
    last_error      TEXT,
        -- Messaggio dell'ultima eccezione/errore catturato.
        -- Sovrascritto ad ogni tentativo fallito.

    -- ── Timestamp ciclo di vita ────────────────────────────────────────────
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,
        -- Popolato da mark_queue_item_done() quando status → done.
    xml_purged_at   TIMESTAMPTZ,
        -- Popolato quando xml_content viene nullificato (GDPR purge).
        -- NULL = xml_content ancora presente (o mai arrivato).

    -- ── CONSTRAINT di integrità ────────────────────────────────────────────
    CONSTRAINT uq_fatture_queue_event_id
        UNIQUE (event_id),

    CONSTRAINT chk_fatture_queue_status
        CHECK (status IN (
            'pending', 'processing', 'done',
            'failed', 'dead', 'unknown_tenant'
        )),

    CONSTRAINT chk_fatture_queue_attempt_count
        CHECK (attempt_count >= 0),

    CONSTRAINT chk_fatture_queue_max_attempts
        CHECK (max_attempts > 0 AND max_attempts <= 20),

    CONSTRAINT chk_fatture_queue_piva_raw
        CHECK (length(trim(piva_raw)) > 0),

    -- Consistenza tenant: se uno è popolato, lo deve essere anche l'altro.
    -- Eccezione: entrambi NULL (unknown_tenant o pre-risoluzione).
    CONSTRAINT chk_fatture_queue_tenant_consistency
        CHECK (
            (user_id IS NULL AND ristorante_id IS NULL)
            OR
            (user_id IS NOT NULL AND ristorante_id IS NOT NULL)
        )
);

COMMENT ON TABLE public.fatture_queue IS
    'Buffer persistente per le notifiche SDI ricevute da Invoicetronic via webhook. '
    'Solo il worker backend (service_role) legge/scrive questa tabella.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. INDICI OTTIMIZZATI
-- ─────────────────────────────────────────────────────────────────────────────

-- Indice primario per il worker polling (status + next_retry_at).
-- Partial index: copre solo i record "attivi", minimizza dimensione indice.
CREATE INDEX IF NOT EXISTS idx_fatture_queue_polling
    ON public.fatture_queue (next_retry_at ASC)
    WHERE status IN ('pending', 'failed');

-- Indice per rilevamento lock stale (worker morto).
CREATE INDEX IF NOT EXISTS idx_fatture_queue_stale_locks
    ON public.fatture_queue (locked_at)
    WHERE status = 'processing' AND locked_at IS NOT NULL;

-- Indice per lookup tenant (visualizzazione per utente, admin).
CREATE INDEX IF NOT EXISTS idx_fatture_queue_tenant
    ON public.fatture_queue (user_id, ristorante_id, status)
    WHERE user_id IS NOT NULL;

-- Indice per risoluzione unknown_tenant (cerca per P.IVA specifica).
CREATE INDEX IF NOT EXISTS idx_fatture_queue_unknown_tenant
    ON public.fatture_queue (piva_raw)
    WHERE status = 'unknown_tenant';

-- Indice per GDPR purge automatica (cerca record da nullificare).
CREATE INDEX IF NOT EXISTS idx_fatture_queue_gdpr_purge
    ON public.fatture_queue (processed_at)
    WHERE status = 'done' AND xml_content IS NOT NULL;

-- Indice per correlation_id (distributed tracing).
CREATE INDEX IF NOT EXISTS idx_fatture_queue_correlation_id
    ON public.fatture_queue (correlation_id)
    WHERE correlation_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────────────────────
-- Strategia: RLS abilitata, ZERO policy per anon/authenticated.
-- Effetto: accesso negato di default per qualunque ruolo non privilegiato.
-- service_role bypassa RLS per definizione in Supabase → worker autorizzato.
-- Frontend Streamlit non deve MAI accedere a questa tabella.
-- Pattern identico a migration 044 (login_attempts).

ALTER TABLE public.fatture_queue ENABLE ROW LEVEL SECURITY;

-- Nessun GRANT a anon/authenticated → accesso negato per tutti i client.
-- Solo service_role (bypass automatico RLS) può operare sulla tabella.
GRANT ALL ON public.fatture_queue TO service_role;

-- sequence per BIGINT GENERATED ALWAYS AS IDENTITY
GRANT USAGE ON SEQUENCE fatture_queue_id_seq TO service_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. FUNZIONE: claim_batch_for_processing()
-- ─────────────────────────────────────────────────────────────────────────────
-- Acquisisce atomicamente un batch di record pronti per l'elaborazione.
-- Usa SELECT ... FOR UPDATE SKIP LOCKED per evitare contese tra worker
-- paralleli senza blocchi espliciti (pattern "optimistic queue").
--
-- Comportamento:
--   - Prende solo record con status IN ('pending','failed')
--   - con next_retry_at <= now()
--   - o con lock stale (locked_at < now() - 10 min, worker presumibilmente morto)
--   - Imposta status='processing', incrementa attempt_count, imposta lock
--   - Restituisce i record claimati (per il worker)
--
-- Uso:
--   SELECT * FROM claim_batch_for_processing('worker-prod-1', 10);

CREATE OR REPLACE FUNCTION public.claim_batch_for_processing(
    p_worker_id  TEXT,
    p_batch_size INTEGER DEFAULT 10
)
RETURNS SETOF public.fatture_queue
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Validazione parametri
    IF p_worker_id IS NULL OR trim(p_worker_id) = '' THEN
        RAISE EXCEPTION 'p_worker_id non può essere NULL o vuoto';
    END IF;
    IF p_batch_size < 1 OR p_batch_size > 100 THEN
        RAISE EXCEPTION 'p_batch_size deve essere tra 1 e 100, ricevuto: %', p_batch_size;
    END IF;

    RETURN QUERY
    UPDATE public.fatture_queue fq
    SET
        status        = 'processing',
        locked_at     = now(),
        locked_by     = p_worker_id,
        attempt_count = fq.attempt_count + 1
    WHERE fq.id IN (
        SELECT id
        FROM   public.fatture_queue
        WHERE  status IN ('pending', 'failed')
          AND  next_retry_at <= now()
          -- Recupera anche record con lock stale (worker crashato > 10 min fa)
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED   -- chiave: nessun blocco tra worker concorrenti
    )
    RETURNING fq.*;
END;
$$;

COMMENT ON FUNCTION public.claim_batch_for_processing(TEXT, INTEGER) IS
    'Acquisisce atomicamente un batch di record pending/failed per il worker. '
    'Usa FOR UPDATE SKIP LOCKED per concorrenza sicura tra più worker paralleli. '
    'Incrementa attempt_count e imposta il lock (locked_at, locked_by).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. FUNZIONE: schedule_retry()
-- ─────────────────────────────────────────────────────────────────────────────
-- Aggiorna un record fallito: calcola il prossimo retry con backoff
-- esponenziale + jitter, oppure passa a 'dead' se max_attempts raggiunto.
--
-- Formula backoff: delay = LEAST(30 × 2^attempt_count, 3600) secondi
-- Jitter: ±25% del delay calcolato (anti-thundering-herd)
-- Delay minimo garantito: 10 secondi
--
-- Tabella backoff di riferimento (senza jitter):
--   attempt 0 →   30s  (primo retry)
--   attempt 1 →   60s
--   attempt 2 →  120s  (2 min)
--   attempt 3 →  240s  (4 min)
--   attempt 4 →  480s  (8 min)
--   attempt 5 →  960s  (~16 min)
--   attempt 6 → 1920s  (~32 min)
--   attempt 7 → 3600s  (1h, cap)
--   attempt 8 → dead   (con max_attempts=8)
--
-- Uso:
--   SELECT * FROM schedule_retry(42, 'Timeout connessione DB');

CREATE OR REPLACE FUNCTION public.schedule_retry(
    p_queue_id  BIGINT,
    p_error_msg TEXT
)
RETURNS public.fatture_queue
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_record      public.fatture_queue;
    v_base_delay  DOUBLE PRECISION;
    v_jitter      DOUBLE PRECISION;
    v_total_delay DOUBLE PRECISION;
BEGIN
    -- Legge e blocca il record (evita race condition su retry concorrente)
    SELECT * INTO v_record
    FROM   public.fatture_queue
    WHERE  id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record id=% non trovato in fatture_queue', p_queue_id;
    END IF;

    IF v_record.attempt_count >= v_record.max_attempts THEN
        -- ── Tutti i tentativi esauriti → dead ─────────────────────────────
        UPDATE public.fatture_queue
        SET
            status    = 'dead',
            last_error = p_error_msg,
            locked_at  = NULL,
            locked_by  = NULL
        WHERE id = p_queue_id
        RETURNING * INTO v_record;

    ELSE
        -- ── Backoff esponenziale con jitter ───────────────────────────────
        -- 30s × 2^attempt_count, cappato a 3600s (1 ora)
        v_base_delay  := LEAST(30.0 * POWER(2.0, v_record.attempt_count::DOUBLE PRECISION), 3600.0);
        -- Jitter uniforme ±25%: (2*random()-1) ∈ [-1, 1)
        v_jitter      := v_base_delay * 0.25 * (2.0 * random() - 1.0);
        -- Delay totale, minimo garantito 10 secondi
        v_total_delay := GREATEST(v_base_delay + v_jitter, 10.0);

        UPDATE public.fatture_queue
        SET
            status        = 'failed',
            last_error    = p_error_msg,
            next_retry_at = now() + make_interval(secs => v_total_delay),
            locked_at     = NULL,
            locked_by     = NULL
        WHERE id = p_queue_id
        RETURNING * INTO v_record;
    END IF;

    RETURN v_record;
END;
$$;

COMMENT ON FUNCTION public.schedule_retry(BIGINT, TEXT) IS
    'Aggiorna un record fallito: calcola next_retry_at con backoff esponenziale '
    '(30s×2^attempt, cap 1h) + jitter ±25%. Passa a ''dead'' se attempt_count '
    '>= max_attempts. Rilascia sempre il lock (locked_at/locked_by → NULL).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. FUNZIONE: mark_queue_item_done()
-- ─────────────────────────────────────────────────────────────────────────────
-- Marca un record come elaborato con successo.
-- Di default nullifica xml_content (GDPR minimizzazione).
-- xml_url rimane per consentire recupero futuro se necessario.
-- xml_hash rimane per audit di integrità.
--
-- Uso:
--   SELECT * FROM mark_queue_item_done(42);           -- purge XML
--   SELECT * FROM mark_queue_item_done(42, false);    -- mantieni XML

CREATE OR REPLACE FUNCTION public.mark_queue_item_done(
    p_queue_id  BIGINT,
    p_purge_xml BOOLEAN DEFAULT true
)
RETURNS public.fatture_queue
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_record public.fatture_queue;
BEGIN
    UPDATE public.fatture_queue
    SET
        status        = 'done',
        processed_at  = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        -- Nullifica xml_content se richiesto (GDPR minimizzazione).
        -- xml_hash e xml_url rimangono per audit/recupero.
        xml_content   = CASE WHEN p_purge_xml THEN NULL ELSE xml_content END,
        xml_purged_at = CASE WHEN p_purge_xml THEN now() ELSE xml_purged_at END
    WHERE id = p_queue_id
    RETURNING * INTO v_record;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record id=% non trovato in fatture_queue', p_queue_id;
    END IF;

    RETURN v_record;
END;
$$;

COMMENT ON FUNCTION public.mark_queue_item_done(BIGINT, BOOLEAN) IS
    'Marca il record come done, rilascia il lock, e (di default) nullifica '
    'xml_content per conformità GDPR. xml_url e xml_hash rimangono per audit.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 8. FUNZIONE: resolve_unknown_tenant()
-- ─────────────────────────────────────────────────────────────────────────────
-- Risolve i record in stato 'unknown_tenant' per una P.IVA data.
-- Chiamata quando:
--   (a) Un nuovo ristorante con quella P.IVA viene registrato nel sistema
--   (b) L'admin corregge manualmente la P.IVA di un ristorante esistente
--
-- Effetto: popola user_id e ristorante_id e rimette i record in 'pending'
-- in modo che il worker li riprenda al prossimo ciclo.
--
-- Uso (da trigger o da chiamata applicativa):
--   SELECT resolve_unknown_tenant('01234567890');
--   -- Restituisce il numero di record rimessi in pending.

CREATE OR REPLACE FUNCTION public.resolve_unknown_tenant(
    p_piva TEXT
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_user_id       UUID;
    v_ristorante_id UUID;
    v_updated       INTEGER;
BEGIN
    IF p_piva IS NULL OR trim(p_piva) = '' THEN
        RAISE EXCEPTION 'p_piva non può essere NULL o vuota';
    END IF;

    -- Cerca il ristorante attivo con questa P.IVA.
    -- Se esistono duplicati (migration 042 lo permette per admin),
    -- prende il più recente creato da un utente non-admin (attivo=true).
    SELECT r.user_id, r.id
    INTO   v_user_id, v_ristorante_id
    FROM   public.ristoranti r
    WHERE  r.partita_iva = trim(p_piva)
      AND  r.attivo      = true
    ORDER BY r.created_at DESC
    LIMIT 1;

    IF v_user_id IS NULL THEN
        -- P.IVA ancora non presente nel DB → niente da fare
        RETURN 0;
    END IF;

    -- Rimette in pending i record unknown_tenant con questa P.IVA
    UPDATE public.fatture_queue
    SET
        user_id       = v_user_id,
        ristorante_id = v_ristorante_id,
        status        = 'pending',
        next_retry_at = now(),
        last_error    = NULL
    WHERE piva_raw = trim(p_piva)
      AND status   = 'unknown_tenant';

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$$;

COMMENT ON FUNCTION public.resolve_unknown_tenant(TEXT) IS
    'Risolve i record unknown_tenant per una P.IVA: cerca il ristorante nel DB, '
    'popola user_id/ristorante_id e rimette i record in pending. '
    'Restituisce il numero di record riattivati. '
    'Chiamare dopo la registrazione di un nuovo ristorante.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 9. FUNZIONE: purge_processed_xml_content()
-- ─────────────────────────────────────────────────────────────────────────────
-- Nullifica xml_content dei record 'done' più vecchi di p_retention_hours.
-- Per conformità GDPR (minimizzazione dei dati personali nell'XML).
--
-- Nota fiscale: L'XML FatturaPA deve essere conservato 10 anni (DPR 633/72).
-- La conservazione avviene tramite xml_url (Invoicetronic) o Supabase Storage.
-- Qui si rimuove solo la COPIA inline nel DB, non l'originale.
--
-- Supabase free tier: niente pg_cron disponibile.
-- Soluzioni:
--   (a) Chiamare questa funzione all'inizio di ogni ciclo del worker  ← CONSIGLIATO
--   (b) Trigger AFTER UPDATE (vedi sotto, commentato)
--   (c) Cron job esterno (GitHub Actions scheduler, ecc.)
--
-- Uso:
--   SELECT purge_processed_xml_content();         -- default: 24h di retention
--   SELECT purge_processed_xml_content(1);        -- rimozione dopo 1h
--   SELECT purge_processed_xml_content(168);      -- rimozione dopo 7 giorni

CREATE OR REPLACE FUNCTION public.purge_processed_xml_content(
    p_retention_hours INTEGER DEFAULT 24
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    IF p_retention_hours < 0 THEN
        RAISE EXCEPTION 'p_retention_hours deve essere >= 0';
    END IF;

    UPDATE public.fatture_queue
    SET
        xml_content   = NULL,
        xml_purged_at = now()
    WHERE status      = 'done'
      AND xml_content IS NOT NULL
      AND processed_at < now() - make_interval(hours => p_retention_hours);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$$;

COMMENT ON FUNCTION public.purge_processed_xml_content(INTEGER) IS
    'Nullifica xml_content dei record done più vecchi di N ore (default 24). '
    'xml_url e xml_hash rimangono per recupero e verifica integrità. '
    'Chiamare all''inizio di ogni ciclo del worker (free tier: niente pg_cron).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 10. TRIGGER OPZIONALE: purge automatica alla transizione → done
-- ─────────────────────────────────────────────────────────────────────────────
-- Se preferisci la purge immediata garantita a livello DB (senza affidarti
-- alla chiamata del worker), abilita questo trigger.
-- ATTENZIONE: aggiunge overhead ad ogni UPDATE sulla tabella.
-- Commentato: attivalo solo se il worker non chiama purge_processed_xml_content().

/*
CREATE OR REPLACE FUNCTION public._auto_purge_xml_on_done()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'done' AND OLD.status != 'done' THEN
        NEW.xml_content   := NULL;
        NEW.xml_purged_at := now();
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_auto_purge_xml_on_done
BEFORE UPDATE ON public.fatture_queue
FOR EACH ROW
WHEN (NEW.status = 'done' AND OLD.status IS DISTINCT FROM 'done')
EXECUTE FUNCTION public._auto_purge_xml_on_done();
*/

-- ─────────────────────────────────────────────────────────────────────────────
-- 11. FUNZIONE: release_stale_locks()
-- ─────────────────────────────────────────────────────────────────────────────
-- Recupera i record bloccati da worker morti (lock stale > p_timeout_minutes).
-- Chiuamre dal worker all'avvio o periodicamente come heartbeat check.
-- Restituisce il numero di lock rilasciati.

CREATE OR REPLACE FUNCTION public.release_stale_locks(
    p_timeout_minutes INTEGER DEFAULT 10
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE public.fatture_queue
    SET
        status    = 'failed',
        last_error = format(
            'Lock stale rilasciato: worker %s bloccato da %s minuti (timeout: %s min)',
            locked_by,
            EXTRACT(EPOCH FROM (now() - locked_at)) / 60,
            p_timeout_minutes
        ),
        locked_at = NULL,
        locked_by = NULL
        -- next_retry_at rimane invariato (ritenta subito se era già passato)
    WHERE status    = 'processing'
      AND locked_at < now() - make_interval(mins => p_timeout_minutes);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$$;

COMMENT ON FUNCTION public.release_stale_locks(INTEGER) IS
    'Rilascia i lock di worker morti (status=processing da più di N min). '
    'Reimposta status=failed per permettere il retry. '
    'Chiamare all''avvio del worker come safety net contro crash.';

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- VERIFICA POST-MIGRAZIONE
-- ═══════════════════════════════════════════════════════════════════════════════

-- 1. Struttura tabella
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_schema = 'public' AND table_name = 'fatture_queue'
-- ORDER BY ordinal_position;

-- 2. Indici creati
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE schemaname = 'public' AND tablename = 'fatture_queue';

-- 3. Policy RLS (deve essere vuota: nessuna policy per anon/authenticated)
-- SELECT policyname, cmd, roles, qual
-- FROM pg_policies
-- WHERE schemaname = 'public' AND tablename = 'fatture_queue';

-- 4. Funzioni disponibili
-- SELECT proname, pronargs
-- FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
-- WHERE n.nspname = 'public'
--   AND proname IN (
--       'claim_batch_for_processing', 'schedule_retry',
--       'mark_queue_item_done', 'resolve_unknown_tenant',
--       'purge_processed_xml_content', 'release_stale_locks'
--   );

-- 5. Test inserimento + claim (da esceguire con service_role)
-- INSERT INTO fatture_queue (event_id, piva_raw, xml_url, source)
-- VALUES ('test-event-001', '01234567890', 'https://invoicetronic.it/xml/001', 'invoicetronic');
-- SELECT * FROM claim_batch_for_processing('test-worker', 1);
-- SELECT * FROM schedule_retry(1, 'Errore test: P.IVA non trovata');
-- SELECT * FROM schedule_retry(1, 'Errore test: secondo tentativo');

-- ═══════════════════════════════════════════════════════════════════════════════
-- NOTE OPERATIVE PER IL WORKER (Edge Function)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Ciclo tipico del worker:
--   1. release_stale_locks()                          -- safety net
--   2. purge_processed_xml_content(24)                -- GDPR cleanup
--   3. batch = claim_batch_for_processing(worker_id)  -- acquisisce lavoro
--   4. Per ogni record nel batch:
--        a. Parsa XML, estrae piva_raw
--        b. Cerca piva in ristoranti → ottieni user_id + ristorante_id
--        c. Se non trovata → UPDATE status='unknown_tenant' (non usare schedule_retry)
--        d. Se trovata → crea record in tabella fatture
--        e. On success → mark_queue_item_done(id)
--        f. On error   → schedule_retry(id, error_message)
--   5. Se nuovo ristorante registrato → resolve_unknown_tenant(piva)
-- ═══════════════════════════════════════════════════════════════════════════════
