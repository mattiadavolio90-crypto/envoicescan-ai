-- ============================================================
-- MIGRATION: notification_inbox
-- Data: 2026-05-13
-- Scopo: inbox persistente per notifiche operative, post-upload
--        e Invoicetronic, con supporto dismiss, dedupe e scadenza.
--
-- RETENTION POLICY (documentata esplicitamente):
--   - Soft-delete: dismissed_at per operazioni utente (dismiss, visibilità)
--     → NON viene mai fatto DELETE per ragioni di business
--   - Hard DELETE tecnico (cron/Edge Function):
--       DELETE WHERE dismissed_at IS NOT NULL
--         AND dismissed_at < now() - interval '30 days'
--     → Eccezione infrastrutturale, non operazione di business
--   - Notifiche scadute (expires_at < now()) ma non dismissate:
--       restano in DB, invisibili alla UI
--       cleanup separato opzionale a 90 giorni
-- ============================================================

-- ============================================================
-- 1. TABELLA
-- ============================================================
CREATE TABLE IF NOT EXISTS public.notification_inbox (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL,
    ristorante_id   uuid        NOT NULL,
    -- Tipologia semantica della notifica (es. "scadenza_superata", "price_alert")
    topic_key       text        NOT NULL,
    -- Categoria di provenienza: "operativa" | "upload" | "invoicetronic"
    source_type     text        NOT NULL CHECK (source_type IN ('operativa', 'upload', 'invoicetronic')),
    -- Livello: "error" | "warning" | "info"
    severity        text        NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    title           text        NOT NULL,
    body            text        NOT NULL,
    -- Dati aggiuntivi (link action, conteggi, file names, ecc.)
    payload         jsonb       NOT NULL DEFAULT '{}',
    -- Etichetta human-readable della pagina destinazione (es. "Scadenziario", "Analisi Fatture AI")
    action_page     text        NULL,
    -- Chiave di deduplicazione con bucket temporale: "{ristorante_id}::{topic_key}::{bucket}"
    -- Bucket: settimana ISO per ricorrenti, hash file_ids per upload one-shot
    -- L'indice univoco parziale su questa chiave garantisce una sola notifica attiva
    -- per combinazione (user, ristorante, dedupe_key) finché non viene dismissata.
    -- Dopo il dismiss, la stessa dedupe_key può riapparire nella sessione successiva.
    dedupe_key      text        NOT NULL,
    -- Data evento sorgente (mostrata nella card UI, non altered dall'upsert DO NOTHING)
    source_event_at timestamptz NOT NULL DEFAULT now(),
    -- NULL = notifica attiva | NOT NULL = dismissata manualmente dall'utente
    dismissed_at    timestamptz NULL,
    -- Scadenza automatica per tipologia:
    --   operativa     → created_at + 7 giorni
    --   upload        → created_at + 14 giorni
    --   invoicetronic → created_at + 3 giorni
    -- Notifiche con expires_at < now() escluse dal badge e dalla lista UI
    expires_at      timestamptz NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.notification_inbox IS
    'Inbox notifiche persistente per utente+ristorante. '
    'Dismiss = soft-delete via dismissed_at. '
    'Hard DELETE solo via cron su dismissed_at > 30 giorni (eccezione infrastrutturale).';

COMMENT ON COLUMN public.notification_inbox.dedupe_key IS
    'Chiave univoca con occurrence bucket: {ristorante_id}::{topic_key}::{bucket}. '
    'Indice parziale su dismissed_at IS NULL: stessa notifica può riapparire dopo dismiss.';
COMMENT ON COLUMN public.notification_inbox.dismissed_at IS
    'NULL = notifica attiva. NOT NULL = dismissata dall''utente (soft-delete).';
COMMENT ON COLUMN public.notification_inbox.expires_at IS
    'Scadenza automatica per tipologia. Esclusa dalla UI se expires_at < now().';

-- ============================================================
-- 2. INDICI
-- ============================================================

-- Indice principale per query lista notifiche attive (badge + tab UI)
CREATE INDEX IF NOT EXISTS idx_notification_inbox_active
    ON public.notification_inbox (user_id, ristorante_id, dismissed_at, expires_at)
    WHERE dismissed_at IS NULL;

-- Indice per query ordinate per recency (used nel tab UI)
CREATE INDEX IF NOT EXISTS idx_notification_inbox_recency
    ON public.notification_inbox (user_id, ristorante_id, source_event_at DESC)
    WHERE dismissed_at IS NULL;

-- Indice per filtro source_type nel tab (dropdown Tutte/Operative/Upload/Invoicetronic)
CREATE INDEX IF NOT EXISTS idx_notification_inbox_source_type
    ON public.notification_inbox (user_id, ristorante_id, source_type, dismissed_at);

-- Indice unico parziale per deduplicazione:
-- Una sola notifica attiva per (user, ristorante, dedupe_key).
-- Dopo il dismiss (dismissed_at NOT NULL), il vincolo si rilascia → stessa key può ricomparire.
CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_inbox_dedupe_active
    ON public.notification_inbox (user_id, ristorante_id, dedupe_key)
    WHERE dismissed_at IS NULL;

-- ============================================================
-- 3. RLS
-- ============================================================
ALTER TABLE public.notification_inbox ENABLE ROW LEVEL SECURITY;

-- Utente autenticato: accede solo alle proprie notifiche (auth.uid() = user_id)
CREATE POLICY notification_inbox_select_own ON public.notification_inbox
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY notification_inbox_insert_own ON public.notification_inbox
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY notification_inbox_update_own ON public.notification_inbox
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY notification_inbox_delete_own ON public.notification_inbox
    FOR DELETE TO authenticated
    USING (user_id = auth.uid());

-- service_role: accesso completo (usato dall'app Streamlit con service_role key)
CREATE POLICY notification_inbox_service_all ON public.notification_inbox
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================
-- 4. GRANTS
-- ============================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notification_inbox TO authenticated;
GRANT ALL ON public.notification_inbox TO service_role;

-- ============================================================
-- 5. FUNZIONE RPC: upsert_notification_inbox
--
-- Gestisce upsert condizionale per l'inbox notifiche.
-- Chiamata via: supabase.rpc("upsert_notification_inbox", {"p_notifications": [...]})
--
-- Ogni elemento di p_notifications è un oggetto JSON con i campi della tabella +
-- "refresh_on_conflict" (bool):
--   - true  → notifica RICORRENTE: DO UPDATE rinnova source_event_at, expires_at, body, title
--             (usato per: fatturato_mancante, costo_personale_mancante, scadenze)
--   - false → notifica ONE-SHOT: DO NOTHING
--             (usato per: upload-specific, credit_note, td24, invoicetronic_auto)
--
-- Restituisce il numero di righe inserite (NOTHING = 0 righe per quel record).
-- ============================================================
CREATE OR REPLACE FUNCTION public.upsert_notification_inbox(
    p_notifications jsonb
)
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    rec              jsonb;
    inserted_count   int := 0;
    rows_affected    int;
    refresh_flag     boolean;
    v_user_id        uuid;
    v_ristorante_id  uuid;
    v_topic_key      text;
    v_source_type    text;
    v_severity       text;
    v_title          text;
    v_body           text;
    v_payload        jsonb;
    v_action_page    text;
    v_dedupe_key     text;
    v_source_event_at timestamptz;
    v_expires_at     timestamptz;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(p_notifications)
    LOOP
        -- Estrai e valida campi obbligatori
        v_user_id         := (rec->>'user_id')::uuid;
        v_ristorante_id   := (rec->>'ristorante_id')::uuid;
        v_topic_key       := rec->>'topic_key';
        v_source_type     := rec->>'source_type';
        v_severity        := rec->>'severity';
        v_title           := rec->>'title';
        v_body            := rec->>'body';
        v_payload         := COALESCE((rec->'payload'), '{}'::jsonb);
        v_action_page     := rec->>'action_page';
        v_dedupe_key      := rec->>'dedupe_key';
        v_source_event_at := COALESCE((rec->>'source_event_at')::timestamptz, now());
        v_expires_at      := (rec->>'expires_at')::timestamptz;
        refresh_flag      := COALESCE((rec->>'refresh_on_conflict')::boolean, false);

        -- Salta record malformati (campi obbligatori mancanti)
        IF v_user_id IS NULL OR v_ristorante_id IS NULL OR v_dedupe_key IS NULL
            OR v_topic_key IS NULL OR v_source_type IS NULL OR v_severity IS NULL
            OR v_title IS NULL OR v_body IS NULL
        THEN
            CONTINUE;
        END IF;

        IF refresh_flag THEN
            -- RICORRENTE: rinnova la notifica se la condizione è ancora vera
            INSERT INTO public.notification_inbox (
                user_id, ristorante_id, topic_key, source_type, severity,
                title, body, payload, action_page, dedupe_key,
                source_event_at, expires_at
            )
            VALUES (
                v_user_id, v_ristorante_id, v_topic_key, v_source_type, v_severity,
                v_title, v_body, v_payload, v_action_page, v_dedupe_key,
                v_source_event_at, v_expires_at
            )
            ON CONFLICT (user_id, ristorante_id, dedupe_key) WHERE dismissed_at IS NULL
            DO UPDATE SET
                source_event_at = EXCLUDED.source_event_at,
                expires_at      = EXCLUDED.expires_at,
                body            = EXCLUDED.body,
                title           = EXCLUDED.title;

            GET DIAGNOSTICS rows_affected = ROW_COUNT;
            inserted_count := inserted_count + rows_affected;
        ELSE
            -- ONE-SHOT: inserisce solo se non esiste già una notifica attiva con questa dedupe_key
            INSERT INTO public.notification_inbox (
                user_id, ristorante_id, topic_key, source_type, severity,
                title, body, payload, action_page, dedupe_key,
                source_event_at, expires_at
            )
            VALUES (
                v_user_id, v_ristorante_id, v_topic_key, v_source_type, v_severity,
                v_title, v_body, v_payload, v_action_page, v_dedupe_key,
                v_source_event_at, v_expires_at
            )
            ON CONFLICT (user_id, ristorante_id, dedupe_key) WHERE dismissed_at IS NULL
            DO NOTHING;

            GET DIAGNOSTICS rows_affected = ROW_COUNT;
            inserted_count := inserted_count + rows_affected;
        END IF;
    END LOOP;

    RETURN inserted_count;
END;
$$;

-- Solo service_role può chiamare la funzione (l'app usa service_role key)
REVOKE ALL ON FUNCTION public.upsert_notification_inbox(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.upsert_notification_inbox(jsonb) TO service_role;

COMMENT ON FUNCTION public.upsert_notification_inbox(jsonb) IS
    'Upsert batch notifiche inbox. '
    'refresh_on_conflict=true → DO UPDATE (ricorrenti: fatturato, scadenze). '
    'refresh_on_conflict=false → DO NOTHING (one-shot: upload, TD24, Invoicetronic). '
    'Restituisce numero righe inserite.';
