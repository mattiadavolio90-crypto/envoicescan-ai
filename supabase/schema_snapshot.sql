-- Snapshot dello schema `public` del DB live, generato da
-- scripts/genera_schema_snapshot.py. NON modificare a mano: rigenerare.
-- Serve a montare il Postgres dei test (le migration del repo non
-- ricostruiscono il database: vedi il docstring dello script).
-- Rigenerato il 2026-09-08.

-- Ambiente Supabase ricreato per il DB di test: ruoli, schema auth, GUC.
-- NON fa parte dello schema dell'applicazione — vedi scripts/genera_schema_snapshot.py.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS extensions;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END
$$;

-- Il Postgres embedded dei test non ha uuid-ossp (il live si). Invece di
-- riscrivere i DEFAULT delle tabelle, si fornisce la funzione con lo stesso
-- nome: dalla 13 gen_random_uuid() e' nel core e basta a se stessa.
--
-- La sostitutiva va in `extensions`, NON in `public`: nel live uuid_generate_v4
-- appartiene all'estensione e non compare fra le funzioni di public. Metterla
-- li' falserebbe ogni conteggio sulle funzioni del progetto e la farebbe
-- risultare "eseguibile da anon" in un test sui permessi. `extensions` e' nel
-- search_path di default di Supabase, quindi i DEFAULT la trovano comunque.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        BEGIN
            CREATE EXTENSION "uuid-ossp";
        EXCEPTION WHEN OTHERS THEN
            CREATE OR REPLACE FUNCTION extensions.uuid_generate_v4() RETURNS uuid
                LANGUAGE sql VOLATILE AS $f$ SELECT gen_random_uuid() $f$;
        END;
    END IF;
END
$$;
-- Sul live il search_path di default include `extensions`; qui lo si imposta
-- per la sessione che carica lo snapshot, cosi' i DEFAULT delle tabelle
-- risolvono uuid_generate_v4() sia in CREATE TABLE sia negli INSERT dei test.
SET search_path TO public, extensions;

-- auth.uid() e' sempre NULL in produzione (auth custom, non Supabase Auth):
-- qui legge la stessa claim, cosi' un test puo' simulare entrambi i casi.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION auth.role() RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('request.jwt.claim.role', true), '') $$;

CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb
    LANGUAGE sql STABLE
    AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;

CREATE TABLE IF NOT EXISTS auth.users (
    id uuid PRIMARY KEY,
    email text
);

-- ── Sequenze, tabelle, sequenze possedute ───────────────────────
CREATE SEQUENCE IF NOT EXISTS public.ai_review_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.ai_usage_events_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.brand_ambigui_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.categorie_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.category_change_log_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.classificazioni_manuali_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.custom_tag_prodotti_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.custom_tag_suggestion_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.custom_tag_suggestions_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.custom_tags_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.fatture_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.fatture_queue_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.gruppo_tag_prodotti_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.gruppo_tags_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.login_attempts_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.prezzi_preferiti_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.prodotti_master_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.review_confirmed_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.review_ignored_id_seq;
CREATE TABLE IF NOT EXISTS public.ai_review_log (
    id bigint DEFAULT nextval('ai_review_log_id_seq'::regclass) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    attore text NOT NULL,
    azione text NOT NULL,
    descrizione text,
    categoria_da text,
    categoria_a text NOT NULL,
    ids_fatture bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    righe_count integer DEFAULT 0 NOT NULL,
    nota text,
    annullato_at timestamp with time zone,
    annullato_da text
);
CREATE TABLE IF NOT EXISTS public.ai_usage_events (
    id bigint DEFAULT nextval('ai_usage_events_id_seq'::regclass) NOT NULL,
    ristorante_id uuid NOT NULL,
    user_id uuid,
    operation_type text NOT NULL,
    model text DEFAULT 'gpt-4o-mini'::text NOT NULL,
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    input_cost numeric(12,6) DEFAULT 0 NOT NULL,
    output_cost numeric(12,6) DEFAULT 0 NOT NULL,
    total_cost numeric(12,6) DEFAULT 0 NOT NULL,
    item_count integer DEFAULT 1 NOT NULL,
    source_file text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.app_settings (
    key text NOT NULL,
    value jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by text
);
CREATE TABLE IF NOT EXISTS public.assistant_preferences (
    ristorante_id uuid NOT NULL,
    nome_referente text,
    topics_disabled jsonb DEFAULT '[]'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    chat_ai_enabled boolean DEFAULT true NOT NULL,
    alert_prezzi_solo_preferiti boolean DEFAULT false NOT NULL,
    giorni_chiusura_settimanali smallint DEFAULT 0 NOT NULL
);
CREATE TABLE IF NOT EXISTS public.brand_ambigui (
    id bigint DEFAULT nextval('brand_ambigui_id_seq'::regclass) NOT NULL,
    brand text NOT NULL,
    num_correzioni integer DEFAULT 0 NOT NULL,
    categorie_viste text[] DEFAULT '{}'::text[] NOT NULL,
    tasso_correzione numeric(6,4) DEFAULT 0 NOT NULL,
    aggiunto_automaticamente boolean DEFAULT false NOT NULL,
    prima_vista timestamp with time zone DEFAULT now() NOT NULL,
    ultima_modifica timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.cache_version (
    key text NOT NULL,
    version bigint DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.categorie (
    id bigint DEFAULT nextval('categorie_id_seq'::regclass) NOT NULL,
    nome text NOT NULL,
    icona text DEFAULT '📦'::text NOT NULL,
    ordinamento integer DEFAULT 999 NOT NULL,
    attiva boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.category_change_log (
    id bigint DEFAULT nextval('category_change_log_id_seq'::regclass) NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    table_name text NOT NULL,
    target_id text,
    user_id uuid,
    ristorante_id uuid,
    descrizione text,
    file_origine text,
    numero_riga integer,
    old_categoria text,
    new_categoria text,
    actor_user_id uuid,
    actor_email text,
    source text DEFAULT 'db_trigger'::text NOT NULL,
    batch_id uuid,
    details jsonb DEFAULT '{}'::jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS public.chat_usage_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    ristorante_id uuid,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.classificazioni_manuali (
    id integer DEFAULT nextval('classificazioni_manuali_id_seq'::regclass) NOT NULL,
    descrizione text NOT NULL,
    categoria_corretta text NOT NULL,
    is_dicitura boolean DEFAULT false,
    validato_da text NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    user_id uuid
);
CREATE TABLE IF NOT EXISTS public.custom_tag_prodotti (
    id bigint DEFAULT nextval('custom_tag_prodotti_id_seq'::regclass) NOT NULL,
    tag_id bigint NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    descrizione text NOT NULL,
    descrizione_key text NOT NULL,
    fattore_kg numeric(12,6),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.custom_tag_suggestion_items (
    id bigint DEFAULT nextval('custom_tag_suggestion_items_id_seq'::regclass) NOT NULL,
    suggestion_id bigint NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    descrizione text NOT NULL,
    descrizione_key text NOT NULL,
    occorrenze integer DEFAULT 1 NOT NULL,
    fornitori_count integer DEFAULT 0 NOT NULL,
    last_seen_date date,
    selected_by_default boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.custom_tag_suggestions (
    id bigint DEFAULT nextval('custom_tag_suggestions_id_seq'::regclass) NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    suggestion_type text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    suggested_tag_name text,
    target_tag_id bigint,
    cluster_key text NOT NULL,
    confidence_score numeric(5,2),
    detection_window_days integer DEFAULT 30 NOT NULL,
    matched_products_count integer DEFAULT 0 NOT NULL,
    matched_rows_count integer DEFAULT 0 NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    snooze_until timestamp with time zone,
    feedback_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.custom_tags (
    id bigint DEFAULT nextval('custom_tags_id_seq'::regclass) NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    nome text NOT NULL,
    emoji text,
    colore text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.daily_briefing_state (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    generated_for_date date NOT NULL,
    snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.diario_eventi (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ristorante_id uuid NOT NULL,
    user_id uuid NOT NULL,
    data_evento date NOT NULL,
    ora_inizio time without time zone,
    ora_fine time without time zone,
    titolo text NOT NULL,
    descrizione text,
    colore text DEFAULT 'sky'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.dipendenti (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ristorante_id uuid NOT NULL,
    nome text NOT NULL,
    costo_orario_default numeric(6,2),
    attivo boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.email_rate_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    destinatario text NOT NULL,
    oggetto_hash text,
    ristorante_id uuid,
    user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.fatture (
    id bigint DEFAULT nextval('fatture_id_seq'::regclass) NOT NULL,
    user_id uuid NOT NULL,
    file_origine text NOT NULL,
    numero_riga integer NOT NULL,
    data_documento date,
    fornitore text NOT NULL,
    descrizione text NOT NULL,
    quantita numeric(10,2) DEFAULT 1,
    unita_misura text,
    prezzo_unitario numeric(10,2) DEFAULT 0,
    iva_percentuale numeric(5,2) DEFAULT 0,
    totale_riga numeric(10,2) DEFAULT 0,
    categoria text DEFAULT 'Da Classificare'::text,
    codice_articolo text,
    data_elaborazione timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    prezzo_standard numeric(10,4) DEFAULT NULL::numeric,
    sconto_percentuale numeric(6,2) DEFAULT 0,
    needs_review boolean DEFAULT false,
    reviewed_at timestamp without time zone,
    reviewed_by text,
    stato text DEFAULT ''::text,
    ristorante_id uuid NOT NULL,
    tipo_documento character varying(4) DEFAULT 'TD01'::character varying,
    data_consegna date,
    deleted_at timestamp with time zone,
    totale_documento numeric,
    totale_imponibile numeric,
    totale_iva numeric,
    data_competenza date,
    piva_cedente text,
    ripartita_su_gruppo boolean DEFAULT false NOT NULL,
    categoria_fonte text,
    categoria_fiducia text
);
CREATE TABLE IF NOT EXISTS public.fatture_documenti (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    file_origine text NOT NULL,
    fornitore text,
    piva_fornitore text,
    numero_documento text,
    data_documento date,
    data_competenza date,
    tipo_documento character varying(4) DEFAULT 'TD01'::character varying NOT NULL,
    totale_documento numeric(12,2),
    totale_imponibile numeric(12,2),
    totale_iva numeric(12,2),
    segno_compensazione smallint DEFAULT 1 NOT NULL,
    scadenza_xml date,
    giorni_termini_xml integer,
    scadenza_override date,
    scadenza_effettiva date,
    scadenza_source text DEFAULT 'none'::text NOT NULL,
    pagata boolean DEFAULT false NOT NULL,
    pagata_at timestamp with time zone,
    note_pagamento text,
    source_origin text DEFAULT 'manual'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    pagata_manuale_at timestamp with time zone
);
CREATE TABLE IF NOT EXISTS public.fatture_queue (
    id bigint NOT NULL,
    event_id text NOT NULL,
    user_id uuid,
    ristorante_id uuid,
    piva_raw text NOT NULL,
    xml_content text,
    xml_url text,
    xml_hash text,
    payload_meta jsonb,
    source text DEFAULT 'invoicetronic'::text NOT NULL,
    correlation_id text,
    status text DEFAULT 'pending'::text NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 8 NOT NULL,
    next_retry_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_at timestamp with time zone,
    locked_by text,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone,
    xml_purged_at timestamp with time zone,
    indirizzo_raw text,
    anteprima_righe jsonb,
    anteprima_at timestamp with time zone
);
CREATE TABLE IF NOT EXISTS public.fornitori_pagamenti_config (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    piva_fornitore text,
    fornitore_norm text,
    giorni_pagamento integer NOT NULL,
    data_riferimento text DEFAULT 'data_documento'::text NOT NULL,
    attiva boolean DEFAULT true NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    modalita text
);
CREATE TABLE IF NOT EXISTS public.gruppo_assistant_config (
    user_id uuid NOT NULL,
    segnali_disattivati text[] DEFAULT '{}'::text[] NOT NULL,
    pv_esclusi uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    chat_disabilitata boolean DEFAULT false NOT NULL
);
CREATE TABLE IF NOT EXISTS public.gruppo_segnali_state (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    generated_for_date date NOT NULL,
    snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.gruppo_tag_prodotti (
    id bigint NOT NULL,
    tag_id bigint NOT NULL,
    user_id uuid NOT NULL,
    descrizione text NOT NULL,
    descrizione_key text NOT NULL,
    fattore_kg numeric,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.gruppo_tags (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    nome text NOT NULL,
    emoji text,
    colore text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ingredienti_utente (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid,
    nome character varying(255) NOT NULL,
    um character varying(20) DEFAULT 'KG'::character varying NOT NULL,
    prezzo_per_um numeric(10,4) NOT NULL,
    categoria character varying(100),
    fornitore character varying(255),
    note text,
    attivo boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.ingredienti_workspace (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid,
    nome character varying(255) NOT NULL,
    prezzo_per_um numeric(10,4) NOT NULL,
    um character varying(20) DEFAULT 'KG'::character varying NOT NULL,
    categoria character varying(100),
    note text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.inventario_voci (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    ristorante_id uuid,
    data_inventario date NOT NULL,
    nome text NOT NULL,
    categoria text DEFAULT ''::text NOT NULL,
    quantita numeric(10,3) DEFAULT 0 NOT NULL,
    um text DEFAULT 'KG'::text NOT NULL,
    prezzo_unitario numeric(10,4) DEFAULT 0 NOT NULL,
    valore_totale numeric(10,2) GENERATED ALWAYS AS (round((quantita * prezzo_unitario), 2)) STORED,
    note text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.login_attempts (
    id bigint NOT NULL,
    email text NOT NULL,
    attempted_at timestamp with time zone DEFAULT now(),
    success boolean DEFAULT false
);
CREATE TABLE IF NOT EXISTS public.margini_mensili (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    anno integer NOT NULL,
    mese integer NOT NULL,
    fatturato_iva10 numeric(10,2) DEFAULT 0,
    fatturato_iva22 numeric(10,2) DEFAULT 0,
    altri_costi_fb numeric(10,2) DEFAULT 0,
    altri_costi_spese numeric(10,2) DEFAULT 0,
    costo_dipendenti numeric(10,2) DEFAULT 0,
    costi_fb_auto numeric(10,2) DEFAULT 0,
    costi_spese_auto numeric(10,2) DEFAULT 0,
    fatturato_netto numeric(10,2) DEFAULT 0,
    costi_fb_totali numeric(10,2) DEFAULT 0,
    primo_margine numeric(10,2) DEFAULT 0,
    mol numeric(10,2) DEFAULT 0,
    food_cost_perc numeric(5,2) DEFAULT 0,
    spese_perc numeric(5,2) DEFAULT 0,
    personale_perc numeric(5,2) DEFAULT 0,
    mol_perc numeric(5,2) DEFAULT 0,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    altri_ricavi_noiva numeric(10,2) DEFAULT 0,
    fatturato_food numeric(12,2) DEFAULT 0,
    fatturato_beverage numeric(12,2) DEFAULT 0,
    fatturato_alcolici numeric(12,2) DEFAULT 0,
    fatturato_dolci numeric(12,2) DEFAULT 0,
    costo_personale_extra numeric DEFAULT 0,
    coperti integer,
    quote_riparto_fb numeric(12,2) DEFAULT 0 NOT NULL,
    quote_riparto_spese numeric(12,2) DEFAULT 0 NOT NULL
);
CREATE TABLE IF NOT EXISTS public.marketplace_leads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    ristorante_id uuid,
    servizio_key text NOT NULL,
    servizio_label text NOT NULL,
    messaggio text DEFAULT ''::text NOT NULL,
    contatto_email text,
    contatto_nome text,
    stato text DEFAULT 'nuovo'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.memoria_ai_categorie (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    descrizione_normalizzata character varying(255) NOT NULL,
    categoria character varying(100) NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.note_diario (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid,
    testo text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.notification_inbox (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    topic_key text NOT NULL,
    source_type text NOT NULL,
    severity text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    action_page text,
    dedupe_key text NOT NULL,
    source_event_at timestamp with time zone DEFAULT now() NOT NULL,
    dismissed_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.piva_ristoranti (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    piva character varying(11) NOT NULL,
    nome_ristorante text NOT NULL
);
CREATE TABLE IF NOT EXISTS public.prezzi_preferiti (
    id bigint DEFAULT nextval('prezzi_preferiti_id_seq'::regclass) NOT NULL,
    ristorante_id uuid NOT NULL,
    user_id uuid NOT NULL,
    descrizione_key text NOT NULL,
    fornitore_key text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.prodotti_master (
    id integer DEFAULT nextval('prodotti_master_id_seq'::regclass) NOT NULL,
    descrizione text NOT NULL,
    categoria text NOT NULL,
    confidence text DEFAULT 'alta'::text,
    volte_visto integer DEFAULT 1,
    ultima_modifica timestamp without time zone DEFAULT now(),
    classificato_da text DEFAULT 'AI'::text,
    created_at timestamp without time zone DEFAULT now(),
    descrizione_originale text,
    correzioni_count integer DEFAULT 0,
    ultimo_correttore text,
    verified boolean DEFAULT false,
    consecutive_correct_classifications integer DEFAULT 0 NOT NULL,
    categoria_suggerita text,
    suggerimento_fonte text,
    suggerito_at timestamp without time zone
);
CREATE TABLE IF NOT EXISTS public.prodotti_utente (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    descrizione text NOT NULL,
    categoria text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    volte_visto integer DEFAULT 1,
    classificato_da text
);
CREATE TABLE IF NOT EXISTS public.regole_turni_ricorrenti (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ristorante_id uuid NOT NULL,
    dipendente_id uuid NOT NULL,
    giorno_settimana smallint NOT NULL,
    tipo_giorno text NOT NULL,
    ora_inizio text,
    ora_fine text,
    ora_inizio2 text,
    ora_fine2 text,
    costo_orario numeric(6,2),
    attiva boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.review_confirmed (
    id bigint DEFAULT nextval('review_confirmed_id_seq'::regclass) NOT NULL,
    descrizione text NOT NULL,
    categoria_finale text NOT NULL,
    is_correct boolean DEFAULT true,
    confirmed_by text NOT NULL,
    confirmed_at timestamp with time zone DEFAULT now(),
    note text
);
CREATE TABLE IF NOT EXISTS public.review_ignored (
    id bigint DEFAULT nextval('review_ignored_id_seq'::regclass) NOT NULL,
    row_id text NOT NULL,
    descrizione text NOT NULL,
    ignored_by text NOT NULL,
    ignored_at timestamp with time zone DEFAULT now(),
    ignored_until timestamp with time zone NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ricavi_email_queue (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    idempotency_key text NOT NULL,
    email_sender text NOT NULL,
    email_subject text,
    attachment_name text,
    storage_path text,
    ristorante_id uuid,
    user_id uuid,
    status text DEFAULT 'pending'::text NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 5 NOT NULL,
    next_retry_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_at timestamp with time zone,
    locked_by text,
    last_error text,
    imported_rows integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone
);
CREATE TABLE IF NOT EXISTS public.ricavi_email_sender_map (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email_sender text NOT NULL,
    ristorante_id uuid NOT NULL,
    gestionale text DEFAULT 'passbi_v1'::text NOT NULL,
    attivo boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ricavi_giornalieri (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    data date NOT NULL,
    fatturato_iva10 numeric(12,2) DEFAULT 0 NOT NULL,
    fatturato_iva22 numeric(12,2) DEFAULT 0 NOT NULL,
    altri_ricavi_noiva numeric(12,2) DEFAULT 0 NOT NULL,
    source text DEFAULT 'manuale'::text NOT NULL,
    source_meta jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    coperti integer
);
CREATE TABLE IF NOT EXISTS public.ricavi_modalita_mensile (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ristorante_id uuid NOT NULL,
    anno integer NOT NULL,
    mese integer NOT NULL,
    modalita text DEFAULT 'giornaliero'::text NOT NULL,
    fatturato_iva10 numeric(12,4) DEFAULT 0 NOT NULL,
    fatturato_iva22 numeric(12,4) DEFAULT 0 NOT NULL,
    altri_ricavi_noiva numeric(12,4) DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    coperti integer
);
CREATE TABLE IF NOT EXISTS public.ricavi_ragione_sociale_map (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ragione_sociale_norm text NOT NULL,
    ristorante_id uuid NOT NULL,
    gestionale text DEFAULT 'passbi_v1'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ricette (
    id uuid DEFAULT uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    ristorante_id uuid,
    nome text NOT NULL,
    categoria text NOT NULL,
    ingredienti jsonb DEFAULT '[]'::jsonb NOT NULL,
    foodcost_totale numeric(10,2) DEFAULT 0 NOT NULL,
    ordine_visualizzazione integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    note text,
    prezzo_vendita_ivainc numeric(10,2) DEFAULT NULL::numeric
);
CREATE TABLE IF NOT EXISTS public.riparto_costi_catena (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    origine text DEFAULT 'fattura'::text NOT NULL,
    file_origine text,
    fornitore text,
    descrizione text NOT NULL,
    importo_totale numeric(12,2) NOT NULL,
    tipo text DEFAULT 'generale'::text NOT NULL,
    anno integer NOT NULL,
    mese integer NOT NULL,
    regola text DEFAULT 'equa'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.riparto_costi_catena_quote (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    riparto_id uuid NOT NULL,
    ristorante_id uuid NOT NULL,
    quota_perc numeric(6,3) NOT NULL,
    quota_importo numeric(12,2) NOT NULL,
    categoria text
);
CREATE TABLE IF NOT EXISTS public.riparto_regole_fornitore (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    fornitore text NOT NULL,
    regola text DEFAULT 'equa'::text NOT NULL,
    tipo text DEFAULT 'generale'::text NOT NULL,
    percentuali jsonb,
    attiva boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.ristoranti (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    nome_ristorante text NOT NULL,
    partita_iva character varying(11) NOT NULL,
    ragione_sociale text,
    attivo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    ai_cost_total numeric(10,4) DEFAULT 0,
    ai_pdf_count integer DEFAULT 0,
    ai_last_usage timestamp without time zone,
    ai_categorization_count integer DEFAULT 0,
    nuovi_da timestamp with time zone,
    indirizzo text,
    cap text,
    comune text,
    indirizzo_match text,
    piano text,
    piano_inizio_at timestamp with time zone,
    sdi_attivo boolean DEFAULT false NOT NULL,
    sdi_attivo_dal date,
    bypass_guardia_piva boolean DEFAULT false NOT NULL,
    sede_tecnica boolean DEFAULT false NOT NULL
);
CREATE TABLE IF NOT EXISTS public.sessioni (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    user_agent text,
    ip text,
    source text DEFAULT 'login'::text NOT NULL,
    revoked_at timestamp with time zone
);
CREATE TABLE IF NOT EXISTS public.spese_extra (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ristorante_id uuid NOT NULL,
    user_id uuid NOT NULL,
    data_spesa date NOT NULL,
    tipo text NOT NULL,
    importo numeric(10,2) NOT NULL,
    descrizione text NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now(),
    categoria text
);
CREATE TABLE IF NOT EXISTS public.system_maintenance_status (
    job_name text NOT NULL,
    last_run_at timestamp with time zone,
    rows_deleted integer DEFAULT 0 NOT NULL,
    rows_from_trash integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'ok'::text NOT NULL,
    error_message text,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);
CREATE TABLE IF NOT EXISTS public.turni_personale (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ristorante_id uuid NOT NULL,
    user_id uuid NOT NULL,
    data_turno date NOT NULL,
    ora_inizio time without time zone NOT NULL,
    ora_fine time without time zone NOT NULL,
    ora_inizio2 time without time zone,
    ora_fine2 time without time zone,
    note text,
    created_at timestamp with time zone DEFAULT now(),
    costo_orario numeric(6,2),
    ore_extra numeric(5,2) DEFAULT 0,
    costo_orario_extra numeric(10,2),
    mensile boolean DEFAULT false NOT NULL,
    ore_dichiarate numeric(7,2),
    lordo_mensile numeric(10,2),
    importo_extra numeric(10,2),
    dipendente_id uuid NOT NULL,
    tipo_giorno text DEFAULT 'turno'::text NOT NULL,
    importo_a_carico numeric(10,2)
);
CREATE TABLE IF NOT EXISTS public.upload_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    user_id uuid NOT NULL,
    user_email text NOT NULL,
    file_name text NOT NULL,
    file_type text,
    status text NOT NULL,
    rows_parsed integer DEFAULT 0,
    rows_saved integer DEFAULT 0,
    rows_excluded integer DEFAULT 0,
    error_stage text,
    error_message text,
    details jsonb,
    ack boolean DEFAULT false,
    ack_at timestamp with time zone,
    ack_by text,
    needs_ack boolean DEFAULT false NOT NULL,
    alert_data_consegna text,
    ristorante_id uuid
);
CREATE TABLE IF NOT EXISTS public.upload_locks (
    ristorante_id uuid NOT NULL,
    user_id uuid NOT NULL,
    locked_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    nome_ristorante character varying(255) NOT NULL,
    piano character varying(50) DEFAULT 'free'::character varying,
    ruolo character varying(50) DEFAULT 'cliente'::character varying,
    attivo boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    last_login timestamp with time zone,
    note_admin text,
    reset_code text,
    reset_expires timestamp with time zone,
    last_logout timestamp with time zone,
    partita_iva character varying(11),
    ragione_sociale text,
    password_changed_at timestamp with time zone DEFAULT now(),
    login_attempts integer DEFAULT 0,
    ultimo_ristorante_id uuid,
    session_token text,
    pagine_abilitate jsonb,
    session_token_created_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    last_reset_requested_at timestamp with time zone,
    trial_activated_at timestamp with time zone,
    trial_active boolean DEFAULT false NOT NULL,
    dismissed_notification_ids jsonb DEFAULT '{}'::jsonb NOT NULL,
    price_alert_threshold numeric(5,2) DEFAULT 5.0,
    auth_uid uuid,
    privacy_accepted_at timestamp with time zone,
    piano_inizio_at timestamp with time zone,
    nome_referente text,
    tema text DEFAULT 'dark'::text NOT NULL,
    last_briefing_seen timestamp with time zone,
    nome_gruppo text
);
ALTER SEQUENCE public.ai_review_log_id_seq OWNED BY public.ai_review_log.id;
ALTER SEQUENCE public.ai_usage_events_id_seq OWNED BY public.ai_usage_events.id;
ALTER SEQUENCE public.brand_ambigui_id_seq OWNED BY public.brand_ambigui.id;
ALTER SEQUENCE public.categorie_id_seq OWNED BY public.categorie.id;
ALTER SEQUENCE public.category_change_log_id_seq OWNED BY public.category_change_log.id;
ALTER SEQUENCE public.classificazioni_manuali_id_seq OWNED BY public.classificazioni_manuali.id;
ALTER SEQUENCE public.custom_tag_prodotti_id_seq OWNED BY public.custom_tag_prodotti.id;
ALTER SEQUENCE public.custom_tag_suggestion_items_id_seq OWNED BY public.custom_tag_suggestion_items.id;
ALTER SEQUENCE public.custom_tag_suggestions_id_seq OWNED BY public.custom_tag_suggestions.id;
ALTER SEQUENCE public.custom_tags_id_seq OWNED BY public.custom_tags.id;
ALTER SEQUENCE public.fatture_id_seq OWNED BY public.fatture.id;
ALTER SEQUENCE public.prezzi_preferiti_id_seq OWNED BY public.prezzi_preferiti.id;
ALTER SEQUENCE public.prodotti_master_id_seq OWNED BY public.prodotti_master.id;
ALTER SEQUENCE public.review_confirmed_id_seq OWNED BY public.review_confirmed.id;
ALTER SEQUENCE public.review_ignored_id_seq OWNED BY public.review_ignored.id;

-- ── Vincoli (PK, UNIQUE, CHECK, FK) e indici ────────────────────
ALTER TABLE public.ai_review_log ADD CONSTRAINT ai_review_log_pkey PRIMARY KEY (id);
ALTER TABLE public.ai_usage_events ADD CONSTRAINT ai_usage_events_pkey PRIMARY KEY (id);
ALTER TABLE public.app_settings ADD CONSTRAINT app_settings_pkey PRIMARY KEY (key);
ALTER TABLE public.assistant_preferences ADD CONSTRAINT assistant_preferences_pkey PRIMARY KEY (ristorante_id);
ALTER TABLE public.brand_ambigui ADD CONSTRAINT brand_ambigui_pkey PRIMARY KEY (id);
ALTER TABLE public.cache_version ADD CONSTRAINT cache_version_pkey PRIMARY KEY (key);
ALTER TABLE public.categorie ADD CONSTRAINT categorie_pkey PRIMARY KEY (id);
ALTER TABLE public.category_change_log ADD CONSTRAINT category_change_log_pkey PRIMARY KEY (id);
ALTER TABLE public.chat_usage_log ADD CONSTRAINT chat_usage_log_pkey PRIMARY KEY (id);
ALTER TABLE public.classificazioni_manuali ADD CONSTRAINT classificazioni_manuali_pkey PRIMARY KEY (id);
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_pkey PRIMARY KEY (id);
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_pkey PRIMARY KEY (id);
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_pkey PRIMARY KEY (id);
ALTER TABLE public.custom_tags ADD CONSTRAINT custom_tags_pkey PRIMARY KEY (id);
ALTER TABLE public.daily_briefing_state ADD CONSTRAINT daily_briefing_state_pkey PRIMARY KEY (id);
ALTER TABLE public.diario_eventi ADD CONSTRAINT diario_eventi_pkey PRIMARY KEY (id);
ALTER TABLE public.dipendenti ADD CONSTRAINT dipendenti_pkey PRIMARY KEY (id);
ALTER TABLE public.email_rate_log ADD CONSTRAINT email_rate_log_pkey PRIMARY KEY (id);
ALTER TABLE public.fatture ADD CONSTRAINT fatture_pkey PRIMARY KEY (id);
ALTER TABLE public.fatture_documenti ADD CONSTRAINT fatture_documenti_pkey PRIMARY KEY (id);
ALTER TABLE public.fatture_queue ADD CONSTRAINT fatture_queue_pkey PRIMARY KEY (id);
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fornitori_pagamenti_config_pkey PRIMARY KEY (id);
ALTER TABLE public.gruppo_assistant_config ADD CONSTRAINT gruppo_assistant_config_pkey PRIMARY KEY (user_id);
ALTER TABLE public.gruppo_segnali_state ADD CONSTRAINT gruppo_segnali_state_pkey PRIMARY KEY (id);
ALTER TABLE public.gruppo_tag_prodotti ADD CONSTRAINT gruppo_tag_prodotti_pkey PRIMARY KEY (id);
ALTER TABLE public.gruppo_tags ADD CONSTRAINT gruppo_tags_pkey PRIMARY KEY (id);
ALTER TABLE public.ingredienti_utente ADD CONSTRAINT ingredienti_utente_pkey PRIMARY KEY (id);
ALTER TABLE public.ingredienti_workspace ADD CONSTRAINT ingredienti_workspace_pkey PRIMARY KEY (id);
ALTER TABLE public.inventario_voci ADD CONSTRAINT inventario_voci_pkey PRIMARY KEY (id);
ALTER TABLE public.login_attempts ADD CONSTRAINT login_attempts_pkey PRIMARY KEY (id);
ALTER TABLE public.margini_mensili ADD CONSTRAINT margini_mensili_pkey PRIMARY KEY (id);
ALTER TABLE public.marketplace_leads ADD CONSTRAINT marketplace_leads_pkey PRIMARY KEY (id);
ALTER TABLE public.memoria_ai_categorie ADD CONSTRAINT memoria_ai_categorie_pkey PRIMARY KEY (id);
ALTER TABLE public.note_diario ADD CONSTRAINT note_diario_pkey PRIMARY KEY (id);
ALTER TABLE public.notification_inbox ADD CONSTRAINT notification_inbox_pkey PRIMARY KEY (id);
ALTER TABLE public.piva_ristoranti ADD CONSTRAINT piva_ristoranti_pkey PRIMARY KEY (id);
ALTER TABLE public.prezzi_preferiti ADD CONSTRAINT prezzi_preferiti_pkey PRIMARY KEY (id);
ALTER TABLE public.prodotti_master ADD CONSTRAINT prodotti_master_pkey PRIMARY KEY (id);
ALTER TABLE public.prodotti_utente ADD CONSTRAINT prodotti_utente_pkey PRIMARY KEY (id);
ALTER TABLE public.regole_turni_ricorrenti ADD CONSTRAINT regole_turni_ricorrenti_pkey PRIMARY KEY (id);
ALTER TABLE public.review_confirmed ADD CONSTRAINT review_confirmed_pkey PRIMARY KEY (id);
ALTER TABLE public.review_ignored ADD CONSTRAINT review_ignored_pkey PRIMARY KEY (id);
ALTER TABLE public.ricavi_email_queue ADD CONSTRAINT ricavi_email_queue_pkey PRIMARY KEY (id);
ALTER TABLE public.ricavi_email_sender_map ADD CONSTRAINT ricavi_email_sender_map_pkey PRIMARY KEY (id);
ALTER TABLE public.ricavi_giornalieri ADD CONSTRAINT ricavi_giornalieri_pkey PRIMARY KEY (id);
ALTER TABLE public.ricavi_modalita_mensile ADD CONSTRAINT ricavi_modalita_mensile_pkey PRIMARY KEY (id);
ALTER TABLE public.ricavi_ragione_sociale_map ADD CONSTRAINT ricavi_ragione_sociale_map_pkey PRIMARY KEY (id);
ALTER TABLE public.ricette ADD CONSTRAINT ricette_pkey PRIMARY KEY (id);
ALTER TABLE public.riparto_costi_catena ADD CONSTRAINT riparto_costi_catena_pkey PRIMARY KEY (id);
ALTER TABLE public.riparto_costi_catena_quote ADD CONSTRAINT riparto_costi_catena_quote_pkey PRIMARY KEY (id);
ALTER TABLE public.riparto_regole_fornitore ADD CONSTRAINT riparto_regole_fornitore_pkey PRIMARY KEY (id);
ALTER TABLE public.ristoranti ADD CONSTRAINT ristoranti_pkey PRIMARY KEY (id);
ALTER TABLE public.sessioni ADD CONSTRAINT sessioni_pkey PRIMARY KEY (id);
ALTER TABLE public.spese_extra ADD CONSTRAINT spese_extra_pkey PRIMARY KEY (id);
ALTER TABLE public.system_maintenance_status ADD CONSTRAINT system_maintenance_status_pkey PRIMARY KEY (job_name);
ALTER TABLE public.turni_personale ADD CONSTRAINT turni_personale_pkey PRIMARY KEY (id);
ALTER TABLE public.upload_events ADD CONSTRAINT upload_events_pkey PRIMARY KEY (id);
ALTER TABLE public.upload_locks ADD CONSTRAINT upload_locks_pkey PRIMARY KEY (ristorante_id);
ALTER TABLE public.users ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE public.brand_ambigui ADD CONSTRAINT brand_ambigui_brand_unique UNIQUE (brand);
ALTER TABLE public.categorie ADD CONSTRAINT categorie_nome_key UNIQUE (nome);
ALTER TABLE public.classificazioni_manuali ADD CONSTRAINT classificazioni_manuali_descrizione_key UNIQUE (descrizione);
ALTER TABLE public.fatture_documenti ADD CONSTRAINT fatture_documenti_user_id_ristorante_id_file_origine_key UNIQUE (user_id, ristorante_id, file_origine);
ALTER TABLE public.fatture_queue ADD CONSTRAINT uq_fatture_queue_event_id UNIQUE (event_id);
ALTER TABLE public.margini_mensili ADD CONSTRAINT margini_mensili_ristorante_id_anno_mese_key UNIQUE (ristorante_id, anno, mese);
ALTER TABLE public.memoria_ai_categorie ADD CONSTRAINT memoria_ai_categorie_user_id_descrizione_normalizzata_key UNIQUE (user_id, descrizione_normalizzata);
ALTER TABLE public.piva_ristoranti ADD CONSTRAINT piva_ristoranti_user_id_ristorante_id_key UNIQUE (user_id, ristorante_id);
ALTER TABLE public.prezzi_preferiti ADD CONSTRAINT prezzi_preferiti_ristorante_id_descrizione_key_fornitore_ke_key UNIQUE (ristorante_id, descrizione_key, fornitore_key);
ALTER TABLE public.prodotti_master ADD CONSTRAINT prodotti_master_descrizione_key UNIQUE (descrizione);
ALTER TABLE public.prodotti_utente ADD CONSTRAINT uq_user_descrizione UNIQUE (user_id, descrizione);
ALTER TABLE public.review_confirmed ADD CONSTRAINT review_confirmed_descrizione_key UNIQUE (descrizione);
ALTER TABLE public.ricavi_email_queue ADD CONSTRAINT ricavi_email_queue_idempotency_key_key UNIQUE (idempotency_key);
ALTER TABLE public.ricavi_email_sender_map ADD CONSTRAINT ricavi_email_sender_map_email_sender_key UNIQUE (email_sender);
ALTER TABLE public.ricavi_giornalieri ADD CONSTRAINT ricavi_giornalieri_unique UNIQUE (ristorante_id, data);
ALTER TABLE public.ricavi_modalita_mensile ADD CONSTRAINT ricavi_modalita_mensile_ristorante_id_anno_mese_key UNIQUE (ristorante_id, anno, mese);
ALTER TABLE public.ricavi_ragione_sociale_map ADD CONSTRAINT ricavi_ragione_sociale_map_ragione_sociale_norm_gestionale_key UNIQUE (ragione_sociale_norm, gestionale);
ALTER TABLE public.riparto_costi_catena ADD CONSTRAINT uq_riparto_file_origine UNIQUE (user_id, file_origine);
ALTER TABLE public.riparto_costi_catena_quote ADD CONSTRAINT uq_riparto_quota_sede_categoria UNIQUE (riparto_id, ristorante_id, categoria);
ALTER TABLE public.riparto_regole_fornitore ADD CONSTRAINT uq_riparto_regola_fornitore UNIQUE (user_id, fornitore);
ALTER TABLE public.users ADD CONSTRAINT users_email_key UNIQUE (email);
ALTER TABLE public.ai_usage_events ADD CONSTRAINT ai_usage_events_operation_type_check CHECK ((operation_type = ANY (ARRAY['pdf'::text, 'categorization'::text, 'chat'::text, 'other'::text])));
ALTER TABLE public.assistant_preferences ADD CONSTRAINT assistant_giorni_chiusura_range_chk CHECK (((giorni_chiusura_settimanali >= 0) AND (giorni_chiusura_settimanali <= 6)));
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_descrizione_key_non_vuota CHECK ((btrim(descrizione_key) <> ''::text));
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_descrizione_non_vuota CHECK ((btrim(descrizione) <> ''::text));
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_fattore_kg_positivo CHECK (((fattore_kg IS NULL) OR (fattore_kg > (0)::numeric)));
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_descrizione_key_nonempty_chk CHECK ((btrim(descrizione_key) <> ''::text));
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_descrizione_nonempty_chk CHECK ((btrim(descrizione) <> ''::text));
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_fornitori_nonnegative_chk CHECK ((fornitori_count >= 0));
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_occorrenze_positive_chk CHECK ((occorrenze >= 1));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_cluster_key_nonempty_chk CHECK ((btrim(cluster_key) <> ''::text));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_confidence_range_chk CHECK (((confidence_score IS NULL) OR ((confidence_score >= (0)::numeric) AND (confidence_score <= (100)::numeric))));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_products_nonnegative_chk CHECK ((matched_products_count >= 0));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_rows_nonnegative_chk CHECK ((matched_rows_count >= 0));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_status_chk CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'dismissed'::text, 'snoozed'::text])));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_type_chk CHECK ((suggestion_type = ANY (ARRAY['new_tag'::text, 'extend_tag'::text])));
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_window_positive_chk CHECK ((detection_window_days > 0));
ALTER TABLE public.custom_tags ADD CONSTRAINT custom_tags_colore_hex_valido CHECK (((colore IS NULL) OR (colore ~* '^#[0-9A-F]{6}$'::text)));
ALTER TABLE public.custom_tags ADD CONSTRAINT custom_tags_nome_non_vuoto CHECK ((btrim(nome) <> ''::text));
ALTER TABLE public.fatture ADD CONSTRAINT fatture_categoria_fiducia_chk CHECK (((categoria_fiducia IS NULL) OR (categoria_fiducia = ANY (ARRAY['certa'::text, 'probabile'::text, 'da_verificare'::text]))));
ALTER TABLE public.fatture ADD CONSTRAINT fatture_categoria_not_empty_chk CHECK (((categoria IS NOT NULL) AND (btrim(categoria) <> ''::text)));
ALTER TABLE public.fatture ADD CONSTRAINT fatture_note_diciture_solo_importo_zero_chk CHECK (((categoria <> '📝 NOTE E DICITURE'::text) OR (COALESCE(totale_riga, (0)::numeric) = (0)::numeric)));
ALTER TABLE public.fatture_documenti ADD CONSTRAINT fatture_documenti_scadenza_source_check CHECK ((scadenza_source = ANY (ARRAY['override'::text, 'fornitore'::text, 'xml'::text, 'none'::text])));
ALTER TABLE public.fatture_documenti ADD CONSTRAINT fatture_documenti_source_origin_check CHECK ((source_origin = ANY (ARRAY['manual'::text, 'invoicetronic'::text])));
ALTER TABLE public.fatture_queue ADD CONSTRAINT chk_fatture_queue_attempt_count CHECK ((attempt_count >= 0));
ALTER TABLE public.fatture_queue ADD CONSTRAINT chk_fatture_queue_max_attempts CHECK (((max_attempts > 0) AND (max_attempts <= 20)));
ALTER TABLE public.fatture_queue ADD CONSTRAINT chk_fatture_queue_piva_raw CHECK ((length(TRIM(BOTH FROM piva_raw)) > 0));
ALTER TABLE public.fatture_queue ADD CONSTRAINT chk_fatture_queue_status CHECK ((status = ANY (ARRAY['pending'::text, 'processing'::text, 'done'::text, 'failed'::text, 'dead'::text, 'unknown_tenant'::text, 'da_assegnare'::text, 'scartata'::text])));
ALTER TABLE public.fatture_queue ADD CONSTRAINT chk_fatture_queue_tenant_consistency CHECK ((((user_id IS NULL) AND (ristorante_id IS NULL)) OR ((user_id IS NOT NULL) AND (ristorante_id IS NOT NULL)) OR ((status = ANY (ARRAY['da_assegnare'::text, 'scartata'::text])) AND (user_id IS NOT NULL) AND (ristorante_id IS NULL))));
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fornitori_pagamenti_config_check CHECK (((piva_fornitore IS NOT NULL) OR (fornitore_norm IS NOT NULL)));
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fornitori_pagamenti_config_data_riferimento_check CHECK ((data_riferimento = ANY (ARRAY['data_documento'::text, 'fine_mese'::text, 'fine_mese_successivo'::text])));
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fornitori_pagamenti_config_giorni_pagamento_check CHECK (((giorni_pagamento >= 0) AND (giorni_pagamento <= 365)));
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fpc_modalita_check CHECK (((modalita IS NULL) OR (modalita = ANY (ARRAY['rid'::text, '30gg'::text, '60gg'::text, '90gg'::text, '30gg_fm'::text, '60gg_fm'::text, '90gg_fm'::text]))));
ALTER TABLE public.margini_mensili ADD CONSTRAINT margini_mensili_mese_check CHECK (((mese >= 1) AND (mese <= 12)));
ALTER TABLE public.marketplace_leads ADD CONSTRAINT marketplace_leads_stato_check CHECK ((stato = ANY (ARRAY['nuovo'::text, 'gestito'::text, 'archiviato'::text])));
ALTER TABLE public.notification_inbox ADD CONSTRAINT notification_inbox_severity_check CHECK ((severity = ANY (ARRAY['error'::text, 'warning'::text, 'info'::text])));
ALTER TABLE public.notification_inbox ADD CONSTRAINT notification_inbox_source_type_check CHECK ((source_type = ANY (ARRAY['operativa'::text, 'upload'::text, 'invoicetronic'::text])));
ALTER TABLE public.regole_turni_ricorrenti ADD CONSTRAINT regole_turni_ricorrenti_giorno_settimana_check CHECK (((giorno_settimana >= 0) AND (giorno_settimana <= 6)));
ALTER TABLE public.regole_turni_ricorrenti ADD CONSTRAINT regole_turni_ricorrenti_orari_solo_turno_chk CHECK ((((tipo_giorno = 'turno'::text) AND (ora_inizio IS NOT NULL) AND (ora_fine IS NOT NULL)) OR ((tipo_giorno = 'riposo'::text) AND (ora_inizio IS NULL) AND (ora_fine IS NULL) AND (ora_inizio2 IS NULL) AND (ora_fine2 IS NULL))));
ALTER TABLE public.regole_turni_ricorrenti ADD CONSTRAINT regole_turni_ricorrenti_tipo_giorno_check CHECK ((tipo_giorno = ANY (ARRAY['turno'::text, 'riposo'::text])));
ALTER TABLE public.ricavi_email_queue ADD CONSTRAINT ricavi_email_queue_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'processing'::text, 'done'::text, 'failed'::text, 'dead'::text, 'unknown_sender'::text])));
ALTER TABLE public.ricavi_giornalieri ADD CONSTRAINT ricavi_giornalieri_amounts_nonneg CHECK (((fatturato_iva10 >= (0)::numeric) AND (fatturato_iva22 >= (0)::numeric) AND (altri_ricavi_noiva >= (0)::numeric)));
ALTER TABLE public.ricavi_giornalieri ADD CONSTRAINT ricavi_giornalieri_source_check CHECK ((source = ANY (ARRAY['manuale'::text, 'xls'::text, 'email'::text])));
ALTER TABLE public.ricavi_modalita_mensile ADD CONSTRAINT ricavi_modalita_mensile_anno_check CHECK (((anno >= 2020) AND (anno <= 2100)));
ALTER TABLE public.ricavi_modalita_mensile ADD CONSTRAINT ricavi_modalita_mensile_mese_check CHECK (((mese >= 1) AND (mese <= 12)));
ALTER TABLE public.ricavi_modalita_mensile ADD CONSTRAINT ricavi_modalita_mensile_modalita_check CHECK ((modalita = ANY (ARRAY['giornaliero'::text, 'mensile'::text])));
ALTER TABLE public.ricette ADD CONSTRAINT ricette_categoria_check CHECK ((categoria = ANY (ARRAY['BRACE'::text, 'CARNE'::text, 'CONTORNI'::text, 'CRUDI'::text, 'DOLCI'::text, 'FOCACCE'::text, 'FRITTI'::text, 'GRIGLIA'::text, 'INSALATE'::text, 'PANINI'::text, 'PESCE'::text, 'PIADINE'::text, 'PINZE'::text, 'PIZZE'::text, 'POKE'::text, 'RISOTTI'::text, 'SALTATI'::text, 'SEMILAVORATI'::text, 'SUSHI'::text, 'TEMPURA'::text, 'VAPORE'::text, 'VERDURE'::text, 'ANTIPASTI'::text, 'PRIMI'::text, 'SECONDI'::text])));
ALTER TABLE public.riparto_costi_catena ADD CONSTRAINT riparto_costi_catena_mese_check CHECK (((mese >= 1) AND (mese <= 12)));
ALTER TABLE public.riparto_costi_catena ADD CONSTRAINT riparto_costi_catena_origine_check CHECK ((origine = ANY (ARRAY['fattura'::text, 'manuale'::text])));
ALTER TABLE public.riparto_costi_catena ADD CONSTRAINT riparto_costi_catena_regola_check CHECK ((regola = ANY (ARRAY['equa'::text, 'percentuali'::text])));
ALTER TABLE public.riparto_costi_catena ADD CONSTRAINT riparto_costi_catena_tipo_check CHECK ((tipo = ANY (ARRAY['generale'::text, 'fb'::text])));
ALTER TABLE public.riparto_costi_catena_quote ADD CONSTRAINT riparto_costi_catena_quote_quota_perc_check CHECK (((quota_perc >= (0)::numeric) AND (quota_perc <= (100)::numeric)));
ALTER TABLE public.riparto_regole_fornitore ADD CONSTRAINT riparto_regole_fornitore_regola_check CHECK ((regola = ANY (ARRAY['equa'::text, 'percentuali'::text])));
ALTER TABLE public.riparto_regole_fornitore ADD CONSTRAINT riparto_regole_fornitore_tipo_check CHECK ((tipo = ANY (ARRAY['generale'::text, 'fb'::text])));
ALTER TABLE public.spese_extra ADD CONSTRAINT spese_extra_importo_check CHECK ((importo >= (0)::numeric));
ALTER TABLE public.spese_extra ADD CONSTRAINT spese_extra_tipo_check CHECK ((tipo = ANY (ARRAY['fb'::text, 'generale'::text])));
ALTER TABLE public.system_maintenance_status ADD CONSTRAINT system_maintenance_status_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'error'::text])));
ALTER TABLE public.turni_personale ADD CONSTRAINT turni_personale_importo_a_carico_solo_assenze_chk CHECK (((importo_a_carico IS NULL) OR (tipo_giorno = ANY (ARRAY['ferie'::text, 'malattia'::text]))));
ALTER TABLE public.turni_personale ADD CONSTRAINT turni_personale_tipo_giorno_check CHECK ((tipo_giorno = ANY (ARRAY['turno'::text, 'riposo'::text, 'ferie'::text, 'malattia'::text])));
ALTER TABLE public.upload_events ADD CONSTRAINT upload_events_status_check CHECK ((status = ANY (ARRAY['SAVED_OK'::text, 'SAVED_PARTIAL'::text, 'FAILED'::text])));
ALTER TABLE public.users ADD CONSTRAINT users_price_alert_threshold_range CHECK (((price_alert_threshold >= (0)::numeric) AND (price_alert_threshold <= (100)::numeric)));
ALTER TABLE public.users ADD CONSTRAINT users_ruolo_check CHECK (((ruolo)::text = ANY ((ARRAY['admin'::character varying, 'cliente'::character varying])::text[])));
ALTER TABLE public.users ADD CONSTRAINT users_tema_chk CHECK ((tema = ANY (ARRAY['dark'::text, 'light'::text])));
ALTER TABLE public.ai_usage_events ADD CONSTRAINT ai_usage_events_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ai_usage_events ADD CONSTRAINT ai_usage_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE public.assistant_preferences ADD CONSTRAINT assistant_preferences_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.category_change_log ADD CONSTRAINT fk_category_change_log_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.category_change_log ADD CONSTRAINT fk_category_change_log_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.chat_usage_log ADD CONSTRAINT fk_chat_usage_log_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.chat_usage_log ADD CONSTRAINT fk_chat_usage_log_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES custom_tags(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_prodotti ADD CONSTRAINT custom_tag_prodotti_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_suggestion_id_fkey FOREIGN KEY (suggestion_id) REFERENCES custom_tag_suggestions(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_suggestion_items ADD CONSTRAINT custom_tag_suggestion_items_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_target_tag_id_fkey FOREIGN KEY (target_tag_id) REFERENCES custom_tags(id) ON DELETE SET NULL;
ALTER TABLE public.custom_tag_suggestions ADD CONSTRAINT custom_tag_suggestions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tags ADD CONSTRAINT custom_tags_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.custom_tags ADD CONSTRAINT custom_tags_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.daily_briefing_state ADD CONSTRAINT fk_daily_briefing_state_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.daily_briefing_state ADD CONSTRAINT fk_daily_briefing_state_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.diario_eventi ADD CONSTRAINT diario_eventi_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.diario_eventi ADD CONSTRAINT diario_eventi_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.dipendenti ADD CONSTRAINT dipendenti_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.email_rate_log ADD CONSTRAINT fk_email_rate_log_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.email_rate_log ADD CONSTRAINT fk_email_rate_log_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.fatture ADD CONSTRAINT fatture_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.fatture ADD CONSTRAINT fatture_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.fatture_queue ADD CONSTRAINT fatture_queue_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.fatture_queue ADD CONSTRAINT fatture_queue_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fk_fornitori_pagamenti_config_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.fornitori_pagamenti_config ADD CONSTRAINT fk_fornitori_pagamenti_config_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.gruppo_assistant_config ADD CONSTRAINT gruppo_assistant_config_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.gruppo_tag_prodotti ADD CONSTRAINT gruppo_tag_prodotti_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES gruppo_tags(id) ON DELETE CASCADE;
ALTER TABLE public.ingredienti_utente ADD CONSTRAINT ingredienti_utente_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ingredienti_utente ADD CONSTRAINT ingredienti_utente_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.ingredienti_workspace ADD CONSTRAINT ingredienti_workspace_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ingredienti_workspace ADD CONSTRAINT ingredienti_workspace_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.inventario_voci ADD CONSTRAINT inventario_voci_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.inventario_voci ADD CONSTRAINT inventario_voci_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.margini_mensili ADD CONSTRAINT fk_margini_mensili_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.margini_mensili ADD CONSTRAINT fk_margini_mensili_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.marketplace_leads ADD CONSTRAINT marketplace_leads_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE SET NULL;
ALTER TABLE public.marketplace_leads ADD CONSTRAINT marketplace_leads_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE public.memoria_ai_categorie ADD CONSTRAINT memoria_ai_categorie_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.note_diario ADD CONSTRAINT note_diario_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.note_diario ADD CONSTRAINT note_diario_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.notification_inbox ADD CONSTRAINT fk_notification_inbox_rist FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.notification_inbox ADD CONSTRAINT fk_notification_inbox_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.piva_ristoranti ADD CONSTRAINT piva_ristoranti_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.piva_ristoranti ADD CONSTRAINT piva_ristoranti_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.prezzi_preferiti ADD CONSTRAINT prezzi_preferiti_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.prodotti_utente ADD CONSTRAINT prodotti_utente_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.regole_turni_ricorrenti ADD CONSTRAINT regole_turni_ricorrenti_dipendente_id_fkey FOREIGN KEY (dipendente_id) REFERENCES dipendenti(id) ON DELETE CASCADE;
ALTER TABLE public.regole_turni_ricorrenti ADD CONSTRAINT regole_turni_ricorrenti_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_email_queue ADD CONSTRAINT ricavi_email_queue_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_email_queue ADD CONSTRAINT ricavi_email_queue_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_email_sender_map ADD CONSTRAINT ricavi_email_sender_map_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_giornalieri ADD CONSTRAINT ricavi_giornalieri_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_giornalieri ADD CONSTRAINT ricavi_giornalieri_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_modalita_mensile ADD CONSTRAINT ricavi_modalita_mensile_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricavi_ragione_sociale_map ADD CONSTRAINT ricavi_ragione_sociale_map_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricette ADD CONSTRAINT ricette_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.ricette ADD CONSTRAINT ricette_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.riparto_costi_catena_quote ADD CONSTRAINT riparto_costi_catena_quote_riparto_id_fkey FOREIGN KEY (riparto_id) REFERENCES riparto_costi_catena(id) ON DELETE CASCADE;
ALTER TABLE public.riparto_costi_catena_quote ADD CONSTRAINT riparto_costi_catena_quote_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id);
ALTER TABLE public.ristoranti ADD CONSTRAINT ristoranti_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.sessioni ADD CONSTRAINT sessioni_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.spese_extra ADD CONSTRAINT spese_extra_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.spese_extra ADD CONSTRAINT spese_extra_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.turni_personale ADD CONSTRAINT turni_personale_dipendente_id_fkey FOREIGN KEY (dipendente_id) REFERENCES dipendenti(id) ON DELETE RESTRICT;
ALTER TABLE public.turni_personale ADD CONSTRAINT turni_personale_ristorante_id_fkey FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE;
ALTER TABLE public.turni_personale ADD CONSTRAINT turni_personale_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE public.users ADD CONSTRAINT users_auth_uid_fkey FOREIGN KEY (auth_uid) REFERENCES auth.users(id) ON DELETE SET NULL;
ALTER TABLE public.users ADD CONSTRAINT users_ultimo_ristorante_id_fkey FOREIGN KEY (ultimo_ristorante_id) REFERENCES ristoranti(id) ON DELETE SET NULL;
CREATE INDEX ai_review_log_annullato_idx ON public.ai_review_log USING btree (annullato_at) WHERE (annullato_at IS NULL);
CREATE INDEX ai_review_log_attore_idx ON public.ai_review_log USING btree (attore);
CREATE INDEX ai_review_log_created_at_idx ON public.ai_review_log USING btree (created_at DESC);
CREATE INDEX idx_ai_usage_events_created_at ON public.ai_usage_events USING btree (created_at DESC);
CREATE INDEX idx_ai_usage_events_operation_type ON public.ai_usage_events USING btree (operation_type);
CREATE INDEX idx_ai_usage_events_rist_type_created ON public.ai_usage_events USING btree (ristorante_id, operation_type, created_at DESC);
CREATE INDEX idx_ai_usage_events_ristorante_created_at ON public.ai_usage_events USING btree (ristorante_id, created_at DESC);
CREATE INDEX idx_ai_usage_events_user_id ON public.ai_usage_events USING btree (user_id);
CREATE INDEX idx_brand_ambigui_aggiunto ON public.brand_ambigui USING btree (aggiunto_automaticamente) WHERE (aggiunto_automaticamente = true);
CREATE INDEX idx_categorie_attiva ON public.categorie USING btree (attiva);
CREATE INDEX idx_categorie_ordinamento ON public.categorie USING btree (ordinamento);
CREATE INDEX idx_category_change_log_batch_id ON public.category_change_log USING btree (batch_id);
CREATE INDEX idx_category_change_log_changed_at ON public.category_change_log USING btree (changed_at DESC);
CREATE INDEX idx_category_change_log_ristorante_id ON public.category_change_log USING btree (ristorante_id);
CREATE INDEX idx_category_change_log_table_target ON public.category_change_log USING btree (table_name, target_id);
CREATE INDEX idx_category_change_log_user_changed_at ON public.category_change_log USING btree (user_id, changed_at DESC);
CREATE INDEX idx_chat_usage_ristorante_giorno ON public.chat_usage_log USING btree (ristorante_id, created_at DESC);
CREATE INDEX idx_chat_usage_user_giorno ON public.chat_usage_log USING btree (user_id, created_at DESC);
CREATE INDEX idx_classificazioni_manuali_descrizione ON public.classificazioni_manuali USING btree (descrizione);
CREATE INDEX idx_classificazioni_manuali_user_id ON public.classificazioni_manuali USING btree (user_id);
CREATE INDEX idx_custom_tag_prodotti_rist_desc_key ON public.custom_tag_prodotti USING btree (ristorante_id, descrizione_key);
CREATE INDEX idx_custom_tag_prodotti_tag_id ON public.custom_tag_prodotti USING btree (tag_id);
CREATE UNIQUE INDEX idx_custom_tag_prodotti_unique_tag_desc_key ON public.custom_tag_prodotti USING btree (tag_id, descrizione_key);
CREATE INDEX idx_custom_tag_prodotti_user_rist_created ON public.custom_tag_prodotti USING btree (user_id, ristorante_id, created_at DESC);
CREATE INDEX idx_custom_tag_prodotti_user_rist_desc_key ON public.custom_tag_prodotti USING btree (user_id, ristorante_id, descrizione_key);
CREATE INDEX idx_ctsi_rist_desc_key ON public.custom_tag_suggestion_items USING btree (ristorante_id, descrizione_key);
CREATE INDEX idx_ctsi_suggestion_id ON public.custom_tag_suggestion_items USING btree (suggestion_id);
CREATE UNIQUE INDEX idx_ctsi_unique_suggestion_desc_key ON public.custom_tag_suggestion_items USING btree (suggestion_id, descrizione_key);
CREATE INDEX idx_ctsi_user_rist_desc_key ON public.custom_tag_suggestion_items USING btree (user_id, ristorante_id, descrizione_key);
CREATE INDEX idx_cts_rist_status_updated ON public.custom_tag_suggestions USING btree (ristorante_id, status, updated_at DESC);
CREATE INDEX idx_cts_snooze_until ON public.custom_tag_suggestions USING btree (user_id, ristorante_id, snooze_until) WHERE (status = 'snoozed'::text);
CREATE UNIQUE INDEX idx_cts_unique_pending_cluster ON public.custom_tag_suggestions USING btree (user_id, ristorante_id, suggestion_type, cluster_key) WHERE (status = 'pending'::text);
CREATE INDEX idx_cts_user_rist_last_seen ON public.custom_tag_suggestions USING btree (user_id, ristorante_id, last_seen_at DESC);
CREATE INDEX idx_cts_user_rist_status_updated ON public.custom_tag_suggestions USING btree (user_id, ristorante_id, status, updated_at DESC);
CREATE INDEX idx_cts_user_rist_type_status ON public.custom_tag_suggestions USING btree (user_id, ristorante_id, suggestion_type, status);
CREATE INDEX idx_custom_tag_suggestions_target_tag_id ON public.custom_tag_suggestions USING btree (target_tag_id);
CREATE INDEX idx_custom_tags_ristorante_created ON public.custom_tags USING btree (ristorante_id, created_at DESC);
CREATE UNIQUE INDEX idx_custom_tags_unique_nome_ci ON public.custom_tags USING btree (user_id, ristorante_id, lower(btrim(nome)));
CREATE INDEX idx_custom_tags_user_ristorante_created ON public.custom_tags USING btree (user_id, ristorante_id, created_at DESC);
CREATE INDEX idx_daily_briefing_state_generated_for_date ON public.daily_briefing_state USING btree (generated_for_date DESC);
CREATE INDEX idx_daily_briefing_state_ristorante_id ON public.daily_briefing_state USING btree (ristorante_id);
CREATE UNIQUE INDEX idx_daily_briefing_state_unique ON public.daily_briefing_state USING btree (user_id, ristorante_id, generated_for_date);
CREATE INDEX idx_daily_briefing_state_user_ristorante ON public.daily_briefing_state USING btree (user_id, ristorante_id);
CREATE INDEX idx_diario_eventi_data ON public.diario_eventi USING btree (ristorante_id, data_evento);
CREATE INDEX idx_diario_eventi_ristorante ON public.diario_eventi USING btree (ristorante_id);
CREATE INDEX idx_diario_eventi_user_id ON public.diario_eventi USING btree (user_id);
CREATE UNIQUE INDEX dipendenti_nome_norm_unico ON public.dipendenti USING btree (ristorante_id, lower(TRIM(BOTH FROM nome))) WHERE (attivo = true);
CREATE INDEX idx_dipendenti_attivo ON public.dipendenti USING btree (ristorante_id, attivo);
CREATE INDEX idx_dipendenti_ristorante ON public.dipendenti USING btree (ristorante_id);
CREATE INDEX idx_email_rate_log_created_at ON public.email_rate_log USING btree (created_at DESC);
CREATE INDEX idx_email_rate_log_dest_time ON public.email_rate_log USING btree (destinatario, created_at DESC);
CREATE INDEX idx_email_rate_log_ristorante_id ON public.email_rate_log USING btree (ristorante_id);
CREATE INDEX idx_email_rate_log_user_id ON public.email_rate_log USING btree (user_id);
CREATE INDEX idx_fatture_active ON public.fatture USING btree (user_id, ristorante_id) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_categoria ON public.fatture USING btree (categoria);
CREATE INDEX idx_fatture_categoria_piva ON public.fatture USING btree (user_id, ristorante_id, categoria, piva_cedente, data_documento) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_created_at ON public.fatture USING btree (created_at);
CREATE INDEX idx_fatture_da_verificare ON public.fatture USING btree (ristorante_id, data_documento) WHERE ((categoria_fiducia = 'da_verificare'::text) AND (deleted_at IS NULL));
CREATE INDEX idx_fatture_data_documento ON public.fatture USING btree (data_documento);
CREATE INDEX idx_fatture_deleted_at ON public.fatture USING btree (deleted_at) WHERE (deleted_at IS NOT NULL);
CREATE INDEX idx_fatture_descrizione ON public.fatture USING btree (descrizione);
CREATE INDEX idx_fatture_file_origine ON public.fatture USING btree (file_origine);
CREATE INDEX idx_fatture_filtro_rapido ON public.fatture USING btree (user_id, ristorante_id, data_documento DESC);
CREATE INDEX idx_fatture_fornitore ON public.fatture USING btree (fornitore);
CREATE INDEX idx_fatture_needs_review ON public.fatture USING btree (needs_review) WHERE (needs_review = true);
CREATE INDEX idx_fatture_prezzo_zero ON public.fatture USING btree (prezzo_unitario) WHERE (prezzo_unitario = (0)::numeric);
CREATE INDEX idx_fatture_review_prezzo ON public.fatture USING btree (needs_review, prezzo_unitario);
CREATE INDEX idx_fatture_reviewed_at ON public.fatture USING btree (reviewed_at) WHERE (reviewed_at IS NOT NULL);
CREATE INDEX idx_fatture_ripartita_su_gruppo ON public.fatture USING btree (ristorante_id) WHERE (ripartita_su_gruppo = true);
CREATE INDEX idx_fatture_ristorante_id ON public.fatture USING btree (ristorante_id);
CREATE INDEX idx_fatture_stato ON public.fatture USING btree (stato);
CREATE INDEX idx_fatture_td24_data_consegna ON public.fatture USING btree (user_id, tipo_documento, data_consegna) WHERE ((tipo_documento)::text = 'TD24'::text);
CREATE INDEX idx_fatture_tipo_documento ON public.fatture USING btree (tipo_documento);
CREATE INDEX idx_fatture_tipo_piva_data ON public.fatture USING btree (user_id, ristorante_id, tipo_documento, piva_cedente, data_documento) WHERE ((deleted_at IS NULL) AND (piva_cedente IS NOT NULL));
CREATE INDEX idx_fatture_upload_dedup_active ON public.fatture USING btree (user_id, ristorante_id, file_origine) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_upload_dedup_active_lower ON public.fatture USING btree (user_id, ristorante_id, lower(file_origine)) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_upload_replace_lookup ON public.fatture USING btree (user_id, ristorante_id, file_origine);
CREATE INDEX idx_fatture_user_categoria ON public.fatture USING btree (user_id, categoria);
CREATE INDEX idx_fatture_user_data ON public.fatture USING btree (user_id, data_documento);
CREATE INDEX idx_fatture_user_fornitore ON public.fatture USING btree (user_id, fornitore);
CREATE INDEX idx_fatture_user_id ON public.fatture USING btree (user_id);
CREATE INDEX idx_fatture_user_ristorante ON public.fatture USING btree (user_id, ristorante_id);
CREATE UNIQUE INDEX uq_fatture_dedup ON public.fatture USING btree (user_id, ristorante_id, file_origine, numero_riga);
CREATE INDEX idx_fat_doc_scadenza_source ON public.fatture_documenti USING btree (user_id, ristorante_id, scadenza_source) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fat_doc_user_rist_deleted_scadenza ON public.fatture_documenti USING btree (user_id, ristorante_id, deleted_at, scadenza_effettiva) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fat_doc_user_rist_fornitore ON public.fatture_documenti USING btree (user_id, ristorante_id, fornitore) WHERE (fornitore IS NOT NULL);
CREATE INDEX idx_fat_doc_user_rist_pagata_scadenza ON public.fatture_documenti USING btree (user_id, ristorante_id, pagata, scadenza_effettiva) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fat_doc_user_rist_piva ON public.fatture_documenti USING btree (user_id, ristorante_id, piva_fornitore) WHERE (piva_fornitore IS NOT NULL);
CREATE INDEX idx_fatture_documenti_identita_naturale ON public.fatture_documenti USING btree (user_id, ristorante_id, piva_fornitore, numero_documento, data_documento, tipo_documento) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_documenti_piva_data ON public.fatture_documenti USING btree (user_id, ristorante_id, piva_fornitore, data_documento DESC) WHERE ((deleted_at IS NULL) AND (piva_fornitore IS NOT NULL));
CREATE INDEX idx_fatture_documenti_radar ON public.fatture_documenti USING btree (user_id, ristorante_id, piva_fornitore, data_documento, totale_documento) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_documenti_rist_created ON public.fatture_documenti USING btree (ristorante_id, created_at) WHERE (deleted_at IS NULL);
CREATE INDEX idx_fatture_queue_correlation_id ON public.fatture_queue USING btree (correlation_id) WHERE (correlation_id IS NOT NULL);
CREATE INDEX idx_fatture_queue_da_assegnare ON public.fatture_queue USING btree (user_id, created_at) WHERE (status = 'da_assegnare'::text);
CREATE INDEX idx_fatture_queue_gdpr_purge ON public.fatture_queue USING btree (processed_at) WHERE ((status = 'done'::text) AND (xml_content IS NOT NULL));
CREATE INDEX idx_fatture_queue_polling ON public.fatture_queue USING btree (next_retry_at) WHERE (status = ANY (ARRAY['pending'::text, 'failed'::text]));
CREATE INDEX idx_fatture_queue_stale_locks ON public.fatture_queue USING btree (locked_at) WHERE ((status = 'processing'::text) AND (locked_at IS NOT NULL));
CREATE INDEX idx_fatture_queue_tenant ON public.fatture_queue USING btree (user_id, ristorante_id, status) WHERE (user_id IS NOT NULL);
CREATE INDEX idx_fatture_queue_unknown_tenant ON public.fatture_queue USING btree (piva_raw) WHERE (status = 'unknown_tenant'::text);
CREATE INDEX idx_fornitori_pagamenti_config_ristorante_id ON public.fornitori_pagamenti_config USING btree (ristorante_id);
CREATE UNIQUE INDEX idx_frn_pag_cfg_norm_unique ON public.fornitori_pagamenti_config USING btree (user_id, ristorante_id, fornitore_norm) WHERE ((piva_fornitore IS NULL) AND (fornitore_norm IS NOT NULL));
CREATE UNIQUE INDEX idx_frn_pag_cfg_piva_unique ON public.fornitori_pagamenti_config USING btree (user_id, ristorante_id, piva_fornitore) WHERE (piva_fornitore IS NOT NULL);
CREATE INDEX idx_frn_pag_cfg_user_rist_attiva ON public.fornitori_pagamenti_config USING btree (user_id, ristorante_id, attiva);
CREATE UNIQUE INDEX idx_gruppo_segnali_state_unique ON public.gruppo_segnali_state USING btree (user_id, generated_for_date);
CREATE INDEX idx_gruppo_tag_prodotti_tag ON public.gruppo_tag_prodotti USING btree (tag_id);
CREATE UNIQUE INDEX idx_gruppo_tag_prodotti_unique ON public.gruppo_tag_prodotti USING btree (tag_id, descrizione_key);
CREATE INDEX idx_gruppo_tags_user ON public.gruppo_tags USING btree (user_id);
CREATE INDEX idx_ingredienti_utente_categoria ON public.ingredienti_utente USING btree (categoria);
CREATE INDEX idx_ingredienti_utente_nome ON public.ingredienti_utente USING btree (nome);
CREATE INDEX idx_ingredienti_utente_ristorante ON public.ingredienti_utente USING btree (ristorante_id);
CREATE UNIQUE INDEX idx_ingredienti_utente_unique_nome_rist_v2 ON public.ingredienti_utente USING btree (user_id, ristorante_id, lower((nome)::text)) WHERE (ristorante_id IS NOT NULL);
CREATE UNIQUE INDEX idx_ingredienti_utente_unique_nome_v2 ON public.ingredienti_utente USING btree (user_id, lower((nome)::text)) WHERE (ristorante_id IS NULL);
CREATE INDEX idx_ingredienti_utente_user_id ON public.ingredienti_utente USING btree (user_id);
CREATE INDEX idx_ingredienti_workspace_nome ON public.ingredienti_workspace USING btree (nome);
CREATE INDEX idx_ingredienti_workspace_ristorante ON public.ingredienti_workspace USING btree (ristorante_id);
CREATE UNIQUE INDEX idx_ingredienti_workspace_unique_nome_rist_v2 ON public.ingredienti_workspace USING btree (user_id, ristorante_id, lower((nome)::text)) WHERE (ristorante_id IS NOT NULL);
CREATE UNIQUE INDEX idx_ingredienti_workspace_unique_nome_v2 ON public.ingredienti_workspace USING btree (user_id, lower((nome)::text)) WHERE (ristorante_id IS NULL);
CREATE INDEX idx_ingredienti_workspace_user_id ON public.ingredienti_workspace USING btree (user_id);
CREATE INDEX idx_inventario_voci_ristorante_data ON public.inventario_voci USING btree (ristorante_id, data_inventario DESC);
CREATE INDEX idx_inventario_voci_user_id ON public.inventario_voci USING btree (user_id);
CREATE INDEX idx_login_attempts_email_time ON public.login_attempts USING btree (email, attempted_at DESC);
CREATE INDEX idx_margini_anno_mese ON public.margini_mensili USING btree (anno, mese);
CREATE INDEX idx_margini_ristorante_anno ON public.margini_mensili USING btree (ristorante_id, anno);
CREATE INDEX idx_margini_user ON public.margini_mensili USING btree (user_id);
CREATE INDEX idx_marketplace_leads_ristorante_id ON public.marketplace_leads USING btree (ristorante_id);
CREATE INDEX idx_marketplace_leads_stato_created ON public.marketplace_leads USING btree (stato, created_at DESC);
CREATE INDEX idx_marketplace_leads_user_id ON public.marketplace_leads USING btree (user_id);
CREATE INDEX idx_memoria_ai_user ON public.memoria_ai_categorie USING btree (user_id);
CREATE INDEX idx_note_diario_created_at ON public.note_diario USING btree (created_at DESC);
CREATE INDEX idx_note_diario_ristorante ON public.note_diario USING btree (ristorante_id);
CREATE INDEX idx_note_diario_user_id ON public.note_diario USING btree (user_id);
CREATE INDEX idx_notification_inbox_active ON public.notification_inbox USING btree (user_id, ristorante_id, dismissed_at, expires_at) WHERE (dismissed_at IS NULL);
CREATE UNIQUE INDEX idx_notification_inbox_dedupe_active ON public.notification_inbox USING btree (user_id, ristorante_id, dedupe_key) WHERE (dismissed_at IS NULL);
CREATE INDEX idx_notification_inbox_recency ON public.notification_inbox USING btree (user_id, ristorante_id, source_event_at DESC) WHERE (dismissed_at IS NULL);
CREATE INDEX idx_notification_inbox_ristorante_id ON public.notification_inbox USING btree (ristorante_id);
CREATE INDEX idx_notification_inbox_source_type ON public.notification_inbox USING btree (user_id, ristorante_id, source_type, dismissed_at);
CREATE INDEX idx_piva_ristoranti_piva ON public.piva_ristoranti USING btree (piva);
CREATE INDEX idx_piva_ristoranti_ristorante_id ON public.piva_ristoranti USING btree (ristorante_id);
CREATE INDEX idx_piva_ristoranti_user_id ON public.piva_ristoranti USING btree (user_id);
CREATE INDEX idx_prezzi_preferiti_rist ON public.prezzi_preferiti USING btree (ristorante_id);
CREATE INDEX idx_pm_streak_promo ON public.prodotti_master USING btree (consecutive_correct_classifications) WHERE (consecutive_correct_classifications >= 3);
CREATE INDEX idx_prodotti_categoria ON public.prodotti_master USING btree (categoria);
CREATE INDEX idx_prodotti_master_descrizione ON public.prodotti_master USING btree (descrizione);
CREATE INDEX idx_prodotti_master_verified ON public.prodotti_master USING btree (verified);
CREATE INDEX idx_prodotti_original ON public.prodotti_master USING btree (descrizione_originale);
CREATE INDEX prodotti_master_suggerimento_idx ON public.prodotti_master USING btree (suggerito_at) WHERE (categoria_suggerita IS NOT NULL);
CREATE INDEX idx_prodotti_utente_categoria ON public.prodotti_utente USING btree (categoria);
CREATE INDEX idx_prodotti_utente_user_desc ON public.prodotti_utente USING btree (user_id, descrizione);
CREATE INDEX idx_regole_turni_ricorrenti_dipendente ON public.regole_turni_ricorrenti USING btree (ristorante_id, dipendente_id);
CREATE INDEX idx_regole_turni_ricorrenti_ristorante ON public.regole_turni_ricorrenti USING btree (ristorante_id);
CREATE INDEX idx_review_ignored_row_id ON public.review_ignored USING btree (row_id);
CREATE INDEX idx_review_ignored_until ON public.review_ignored USING btree (ignored_until);
CREATE INDEX idx_ricavi_email_queue_ristorante_id ON public.ricavi_email_queue USING btree (ristorante_id);
CREATE INDEX idx_ricavi_email_queue_status_retry ON public.ricavi_email_queue USING btree (status, next_retry_at) WHERE (status = ANY (ARRAY['pending'::text, 'failed'::text]));
CREATE INDEX idx_ricavi_email_queue_user_id ON public.ricavi_email_queue USING btree (user_id);
CREATE INDEX idx_ricavi_email_sender_map_ristorante_id ON public.ricavi_email_sender_map USING btree (ristorante_id);
CREATE INDEX idx_ricavi_email_sender_map_sender ON public.ricavi_email_sender_map USING btree (email_sender);
CREATE INDEX idx_ricavi_giornalieri_ristorante_data ON public.ricavi_giornalieri USING btree (ristorante_id, data DESC);
CREATE INDEX idx_ricavi_giornalieri_user ON public.ricavi_giornalieri USING btree (user_id);
CREATE INDEX idx_ricavi_modalita_mensile_ristorante_anno_mese ON public.ricavi_modalita_mensile USING btree (ristorante_id, anno, mese);
CREATE INDEX idx_ricavi_ragione_sociale_map_norm ON public.ricavi_ragione_sociale_map USING btree (ragione_sociale_norm, gestionale);
CREATE INDEX idx_ricavi_ragione_sociale_map_ristorante_id ON public.ricavi_ragione_sociale_map USING btree (ristorante_id);
CREATE INDEX idx_ricette_ingredienti_gin ON public.ricette USING gin (ingredienti);
CREATE INDEX idx_ricette_ristorante_id ON public.ricette USING btree (ristorante_id);
CREATE INDEX idx_ricette_user_id_categoria ON public.ricette USING btree (user_id, categoria);
CREATE INDEX idx_ricette_user_id_order ON public.ricette USING btree (user_id, ordine_visualizzazione);
CREATE INDEX idx_ricette_user_id_ristorante ON public.ricette USING btree (user_id, ristorante_id);
CREATE INDEX idx_riparto_file_origine ON public.riparto_costi_catena USING btree (user_id, file_origine) WHERE (file_origine IS NOT NULL);
CREATE INDEX idx_riparto_user_periodo ON public.riparto_costi_catena USING btree (user_id, anno, mese);
CREATE INDEX idx_riparto_quote_riparto ON public.riparto_costi_catena_quote USING btree (riparto_id);
CREATE INDEX idx_riparto_quote_sede ON public.riparto_costi_catena_quote USING btree (ristorante_id);
CREATE INDEX idx_riparto_regole_user ON public.riparto_regole_fornitore USING btree (user_id) WHERE (attiva = true);
CREATE INDEX idx_ristoranti_piva ON public.ristoranti USING btree (partita_iva);
CREATE INDEX idx_ristoranti_user_id ON public.ristoranti USING btree (user_id);
CREATE UNIQUE INDEX uq_ristoranti_sede_tecnica_per_account ON public.ristoranti USING btree (user_id) WHERE (sede_tecnica = true);
CREATE UNIQUE INDEX idx_sessioni_token_active ON public.sessioni USING btree (token) WHERE (revoked_at IS NULL);
CREATE INDEX idx_sessioni_user_active ON public.sessioni USING btree (user_id, last_seen_at DESC) WHERE (revoked_at IS NULL);
CREATE INDEX idx_spese_extra_categoria ON public.spese_extra USING btree (ristorante_id, categoria) WHERE (categoria IS NOT NULL);
CREATE INDEX idx_spese_extra_data ON public.spese_extra USING btree (ristorante_id, data_spesa);
CREATE INDEX idx_spese_extra_ristorante ON public.spese_extra USING btree (ristorante_id);
CREATE INDEX idx_spese_extra_tipo ON public.spese_extra USING btree (ristorante_id, tipo);
CREATE INDEX idx_spese_extra_user_id ON public.spese_extra USING btree (user_id);
CREATE INDEX idx_turni_personale_data ON public.turni_personale USING btree (ristorante_id, data_turno);
CREATE INDEX idx_turni_personale_dipendente ON public.turni_personale USING btree (ristorante_id, dipendente_id);
CREATE INDEX idx_turni_personale_ristorante ON public.turni_personale USING btree (ristorante_id);
CREATE INDEX idx_turni_personale_tipo_giorno ON public.turni_personale USING btree (ristorante_id, dipendente_id, tipo_giorno) WHERE (tipo_giorno <> 'turno'::text);
CREATE INDEX idx_turni_personale_user_id ON public.turni_personale USING btree (user_id);
CREATE UNIQUE INDEX turni_personale_mensile_unico ON public.turni_personale USING btree (ristorante_id, dipendente_id, data_turno) WHERE (mensile = true);
CREATE INDEX idx_upload_events_created_at ON public.upload_events USING btree (created_at);
CREATE INDEX idx_upload_events_file_name ON public.upload_events USING btree (file_name);
CREATE INDEX idx_upload_events_needs_ack ON public.upload_events USING btree (user_id, needs_ack) WHERE (needs_ack = true);
CREATE INDEX idx_upload_events_ristorante_needs_ack ON public.upload_events USING btree (ristorante_id, needs_ack) WHERE (needs_ack = true);
CREATE INDEX idx_upload_events_ristorante_status ON public.upload_events USING btree (ristorante_id, status, created_at DESC) WHERE (ristorante_id IS NOT NULL);
CREATE INDEX idx_upload_events_saved_ok_lookup ON public.upload_events USING btree (user_id, status, file_name) WHERE (status = 'SAVED_OK'::text);
CREATE INDEX idx_upload_events_status ON public.upload_events USING btree (status);
CREATE INDEX idx_upload_events_status_ack ON public.upload_events USING btree (ack, status, created_at DESC);
CREATE INDEX idx_upload_events_user_email ON public.upload_events USING btree (user_email);
CREATE INDEX idx_upload_events_user_id ON public.upload_events USING btree (user_id);
CREATE INDEX idx_upload_locks_locked_at ON public.upload_locks USING btree (locked_at DESC);
CREATE INDEX idx_users_auth_uid ON public.users USING btree (auth_uid);
CREATE INDEX idx_users_email ON public.users USING btree (email);
CREATE INDEX idx_users_last_logout ON public.users USING btree (last_logout);
CREATE INDEX idx_users_partita_iva ON public.users USING btree (partita_iva) WHERE (partita_iva IS NOT NULL);
CREATE INDEX idx_users_session_token ON public.users USING btree (session_token);
CREATE INDEX idx_users_trial_active ON public.users USING btree (trial_active) WHERE (trial_active = true);
CREATE INDEX idx_users_ultimo_ristorante_id ON public.users USING btree (ultimo_ristorante_id);
CREATE INDEX users_reset_code_idx ON public.users USING btree (reset_code);

-- ── Funzioni, trigger, permessi EXECUTE, RLS ───────────────────
-- I permessi sono la fotografia di quelli VERI, difetti compresi: e' cosi'
-- che un test puo' vedere una funzione SECURITY DEFINER aperta ad anon.
-- Le REVOKE da PUBLIC vengono prima: Postgres concede EXECUTE a PUBLIC a
-- ogni funzione creata, e senza riprodurre le revoche del live il DB di
-- test mostrerebbe 57 funzioni aperte ad anon invece di 6.
-- Delle 96 policy RLS si riporta solo l'abilitazione: ogni client dell'app
-- usa service_role (BYPASSRLS), quindi le policy non filtrano nulla e
-- ricopiarle darebbe ai test una protezione solo apparente.
CREATE OR REPLACE FUNCTION public._azzera_attribuzione_categoria()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
    PERFORM set_config('app.category_change_source', '', true);
    PERFORM set_config('app.category_change_batch_id', '', true);
    PERFORM set_config('app.category_change_actor_email', '', true);
    PERFORM set_config('app.category_change_actor_user_id', '', true);
END;
$function$;
CREATE OR REPLACE FUNCTION public._riparto_categoria_is_fb(p_categoria text)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT upper(btrim(coalesce(p_categoria, ''))) IN (
        'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
        'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA','SALSE E CREME',
        'ACQUA','BEVANDE','CAFFE E THE','BIRRE','VINI',
        'VARIE BAR','DISTILLATI','AMARI/LIQUORI','PASTICCERIA',
        'PRODOTTI DA FORNO','SPEZIE E AROMI','GELATI E DESSERT','SHOP','SUSHI VARIE'
    );
$function$;
CREATE OR REPLACE FUNCTION public.normalize_custom_tag_key(input_text text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'public'
AS $function$
    SELECT NULLIF(
        regexp_replace(
            upper(btrim(COALESCE(input_text, ''))),
            '\s+',
            ' ',
            'g'
        ),
        ''
    )
$function$;
CREATE OR REPLACE FUNCTION public.normalizza_indirizzo_match(p_raw text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'public'
AS $function$
    SELECT NULLIF(
        trim(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        lower(coalesce(p_raw, '')),
                                        '\m(v\.?le)\M', 'viale', 'g'),
                                    '\m(c\.?so)\M', 'corso', 'g'),
                                '\m(p\.?zza|p\.?za)\M', 'piazza', 'g'),
                            '\m(v\.?)\M', 'via', 'g'),
                        '\m(str\.?)\M', 'strada', 'g'),
                    '[^a-z0-9 ]', ' ', 'g'),
                '\s+', ' ', 'g')
        ),
        ''
    );
$function$;
CREATE OR REPLACE FUNCTION public.aggiorna_categoria_fatture_attribuita(p_ids bigint[], p_categoria text, p_source text, p_extra jsonb DEFAULT '{}'::jsonb, p_actor_email text DEFAULT NULL::text, p_actor_user_id uuid DEFAULT NULL::uuid, p_batch_id uuid DEFAULT NULL::uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_count integer;
BEGIN
    IF p_ids IS NULL OR array_length(p_ids, 1) IS NULL THEN
        RETURN 0;
    END IF;

    PERFORM set_config('app.category_change_source', COALESCE(p_source, ''), true);
    PERFORM set_config('app.category_change_batch_id', COALESCE(p_batch_id::text, ''), true);
    PERFORM set_config('app.category_change_actor_email', COALESCE(p_actor_email, ''), true);
    PERFORM set_config('app.category_change_actor_user_id', COALESCE(p_actor_user_id::text, ''), true);

    UPDATE public.fatture SET
        categoria = p_categoria,
        needs_review = COALESCE((p_extra->>'needs_review')::boolean, needs_review),
        categoria_fonte = COALESCE(p_extra->>'categoria_fonte', categoria_fonte),
        categoria_fiducia = COALESCE(p_extra->>'categoria_fiducia', categoria_fiducia),
        reviewed_at = COALESCE((p_extra->>'reviewed_at')::timestamp, reviewed_at),
        reviewed_by = COALESCE(p_extra->>'reviewed_by', reviewed_by)
    WHERE id = ANY(p_ids)
      AND deleted_at IS NULL;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    PERFORM public._azzera_attribuzione_categoria();

    RETURN v_count;
END;
$function$;
CREATE OR REPLACE FUNCTION public.aggiorna_categoria_prodotto_attribuita(p_user_id uuid, p_descrizione text, p_categoria text, p_source text, p_actor_email text DEFAULT NULL::text, p_actor_user_id uuid DEFAULT NULL::uuid, p_batch_id uuid DEFAULT NULL::uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_count integer;
BEGIN
    PERFORM set_config('app.category_change_source', COALESCE(p_source, ''), true);
    PERFORM set_config('app.category_change_batch_id', COALESCE(p_batch_id::text, ''), true);
    PERFORM set_config('app.category_change_actor_email', COALESCE(p_actor_email, ''), true);
    PERFORM set_config('app.category_change_actor_user_id', COALESCE(p_actor_user_id::text, ''), true);

    UPDATE public.prodotti_utente
       SET categoria = p_categoria
     WHERE user_id = p_user_id
       AND descrizione = p_descrizione;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    PERFORM public._azzera_attribuzione_categoria();
    RETURN v_count;
END;
$function$;
CREATE OR REPLACE FUNCTION public.accoda_upload_ambiguo(p_user_id uuid, p_piva_raw text, p_xml_content text, p_nome_file text, p_indirizzo_raw text, p_xml_hash text, p_payload_meta jsonb DEFAULT '{}'::jsonb, p_anteprima_righe jsonb DEFAULT NULL::jsonb)
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
        RAISE EXCEPTION 'p_user_id non puo essere NULL';
    END IF;
    IF p_piva_raw IS NULL OR length(trim(p_piva_raw)) = 0 THEN
        RAISE EXCEPTION 'p_piva_raw non puo essere vuota';
    END IF;
    IF p_xml_hash IS NULL OR length(trim(p_xml_hash)) = 0 THEN
        RAISE EXCEPTION 'p_xml_hash non puo essere vuoto (serve per idempotenza)';
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
CREATE OR REPLACE FUNCTION public.assegna_fattura_a_sede(p_queue_id bigint, p_ristorante_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_queue_user_id UUID;
    v_queue_status  TEXT;
    v_rist_user_id  UUID;
    v_rist_attivo   BOOLEAN;
BEGIN
    SELECT user_id, status
    INTO   v_queue_user_id, v_queue_status
    FROM   public.fatture_queue
    WHERE  id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record coda % inesistente', p_queue_id;
    END IF;

    IF v_queue_status <> 'da_assegnare' THEN
        RETURN FALSE;
    END IF;

    SELECT user_id, attivo
    INTO   v_rist_user_id, v_rist_attivo
    FROM   public.ristoranti
    WHERE  id = p_ristorante_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ristorante % inesistente', p_ristorante_id;
    END IF;

    IF v_rist_user_id IS DISTINCT FROM v_queue_user_id THEN
        RAISE EXCEPTION 'Ristorante % non appartiene al cliente della fattura', p_ristorante_id;
    END IF;

    IF v_rist_attivo IS NOT TRUE THEN
        RAISE EXCEPTION 'Ristorante % non attivo', p_ristorante_id;
    END IF;

    UPDATE public.fatture_queue
    SET
        ristorante_id = p_ristorante_id,
        status        = 'pending',
        next_retry_at = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        last_error    = NULL
    WHERE id = p_queue_id;

    RETURN TRUE;
END;
$function$;
CREATE OR REPLACE FUNCTION public.assegna_fattura_a_sede_tecnica(p_queue_id bigint)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_queue_user_id UUID;
    v_queue_status  TEXT;
    v_tecnica_id    UUID;
    v_piva          TEXT;
BEGIN
    SELECT user_id, status
    INTO   v_queue_user_id, v_queue_status
    FROM   public.fatture_queue
    WHERE  id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record coda % inesistente', p_queue_id;
    END IF;

    IF v_queue_status <> 'da_assegnare' THEN
        RETURN NULL;
    END IF;

    SELECT id INTO v_tecnica_id
    FROM   public.ristoranti
    WHERE  user_id = v_queue_user_id AND sede_tecnica = TRUE
    LIMIT  1;

    IF v_tecnica_id IS NULL THEN
        SELECT partita_iva INTO v_piva
        FROM   public.ristoranti
        WHERE  user_id = v_queue_user_id AND COALESCE(sede_tecnica, FALSE) = FALSE
        ORDER  BY created_at
        LIMIT  1;

        IF v_piva IS NULL THEN
            RAISE EXCEPTION 'Nessuna sede reale per l''account %: impossibile creare la sede tecnica', v_queue_user_id;
        END IF;

        INSERT INTO public.ristoranti (
            user_id, nome_ristorante, partita_iva, attivo, sede_tecnica, sdi_attivo
        )
        VALUES (
            v_queue_user_id, 'Costi comuni di gruppo', v_piva, TRUE, TRUE, FALSE
        )
        RETURNING id INTO v_tecnica_id;
    END IF;

    UPDATE public.fatture_queue
    SET
        ristorante_id = v_tecnica_id,
        status        = 'pending',
        next_retry_at = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        last_error    = NULL
    WHERE id = p_queue_id;

    RETURN v_tecnica_id;
END;
$function$;
CREATE OR REPLACE FUNCTION public.chat_usage_check_and_log(p_user_id uuid, p_ristorante_id uuid, p_limite integer, p_pool boolean DEFAULT false)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_inizio  TIMESTAMPTZ := date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
    v_count   INTEGER;
BEGIN
    IF p_limite IS NULL OR p_limite <= 0 THEN
        RETURN -1;
    END IF;

    SELECT count(*)::int INTO v_count
    FROM public.chat_usage_log
    WHERE created_at >= v_inizio
      AND (
        (p_pool AND user_id = p_user_id)
        OR (NOT p_pool AND p_ristorante_id IS NOT NULL AND ristorante_id = p_ristorante_id)
        OR (NOT p_pool AND p_ristorante_id IS NULL AND user_id = p_user_id)
      );

    IF v_count >= p_limite THEN
        RETURN -1;
    END IF;

    INSERT INTO public.chat_usage_log (user_id, ristorante_id)
    VALUES (p_user_id, p_ristorante_id);

    RETURN v_count + 1;
END;
$function$;
CREATE OR REPLACE FUNCTION public.claim_batch_for_processing(p_worker_id text, p_batch_size integer DEFAULT 10)
 RETURNS SETOF fatture_queue
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
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
          AND  attempt_count < max_attempts
          AND  next_retry_at <= now()
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING fq.*;
END;
$function$;
CREATE OR REPLACE FUNCTION public.claim_ricavi_email_batch(p_worker_id text, p_batch_size integer DEFAULT 5)
 RETURNS SETOF ricavi_email_queue
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
    IF p_worker_id IS NULL OR trim(p_worker_id) = '' THEN
        RAISE EXCEPTION 'p_worker_id non può essere NULL o vuoto';
    END IF;
    IF p_batch_size < 1 OR p_batch_size > 100 THEN
        RAISE EXCEPTION 'p_batch_size deve essere tra 1 e 100, ricevuto: %', p_batch_size;
    END IF;

    RETURN QUERY
    UPDATE public.ricavi_email_queue q
    SET
        status        = 'processing',
        locked_at     = now(),
        locked_by     = p_worker_id,
        attempt_count = q.attempt_count + 1
    WHERE q.id IN (
        SELECT id
        FROM   public.ricavi_email_queue
        WHERE  status IN ('pending', 'failed')
          AND  next_retry_at <= now()
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC, created_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING q.*;
END;
$function$;
CREATE OR REPLACE FUNCTION public.crea_riparto_con_quote(p_user_id uuid, p_origine text, p_file_origine text, p_fornitore text, p_descrizione text, p_importo_totale numeric, p_tipo text, p_anno integer, p_mese integer, p_regola text, p_quote jsonb)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_riparto_id UUID;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;
    IF p_quote IS NULL OR jsonb_array_length(p_quote) = 0 THEN
        RAISE EXCEPTION 'p_quote non può essere vuoto';
    END IF;

    INSERT INTO public.riparto_costi_catena (
        user_id, origine, file_origine, fornitore, descrizione,
        importo_totale, tipo, anno, mese, regola
    )
    VALUES (
        p_user_id, p_origine, p_file_origine, p_fornitore, p_descrizione,
        p_importo_totale, p_tipo, p_anno, p_mese, p_regola
    )
    RETURNING id INTO v_riparto_id;

    INSERT INTO public.riparto_costi_catena_quote (
        riparto_id, ristorante_id, quota_perc, quota_importo, categoria
    )
    SELECT
        v_riparto_id,
        (q->>'ristorante_id')::UUID,
        (q->>'quota_perc')::NUMERIC,
        (q->>'quota_importo')::NUMERIC,
        NULLIF(q->>'categoria', '')
    FROM jsonb_array_elements(p_quote) AS q;

    RETURN v_riparto_id;
END;
$function$;
CREATE OR REPLACE FUNCTION public.dashboard_stats_aggregata(p_user_id uuid, p_ristorante_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    v_oggi          date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_mese_corr     text := to_char(v_oggi, 'YYYY-MM');
    v_mese_prec     text := to_char((date_trunc('month', v_oggi) - interval '1 day')::date, 'YYYY-MM');
    v_result        jsonb;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    WITH base AS (
        SELECT
            COALESCE(f.totale_riga, 0)                         AS totale,
            f.data_documento,
            to_char(f.data_documento, 'YYYY-MM')               AS mese_key,
            NULLIF(btrim(COALESCE(f.fornitore, '')), '')       AS fornitore,
            NULLIF(btrim(COALESCE(f.categoria, '')), '')       AS categoria,
            f.file_origine
        FROM public.fatture f
        WHERE f.user_id = p_user_id
          AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
          AND f.deleted_at IS NULL
    ),
    kpi AS (
        SELECT
            COUNT(DISTINCT file_origine)                                          AS fatture_uniche,
            COUNT(*)                                                              AS righe_totali,
            COALESCE(SUM(totale), 0)                                              AS spesa_totale,
            COALESCE(SUM(totale) FILTER (WHERE mese_key = v_mese_corr), 0)        AS spesa_mese_corrente,
            COALESCE(SUM(totale) FILTER (WHERE mese_key = v_mese_prec), 0)        AS spesa_mese_precedente,
            MIN(data_documento)                                                   AS prima_fattura,
            MAX(data_documento)                                                   AS ultima_fattura
        FROM base
    ),
    per_mese AS (
        SELECT mese_key, ROUND(SUM(totale), 2) AS spesa
        FROM base
        WHERE mese_key IS NOT NULL
        GROUP BY mese_key
        ORDER BY mese_key DESC
        LIMIT 12
    ),
    per_mese_asc AS (
        SELECT mese_key, spesa FROM per_mese ORDER BY mese_key ASC
    ),
    per_fornitore AS (
        SELECT COALESCE(fornitore, '—') AS nome, ROUND(SUM(totale), 2) AS spesa, COUNT(*) AS righe
        FROM base
        GROUP BY COALESCE(fornitore, '—')
        ORDER BY SUM(totale) DESC
        LIMIT 5
    ),
    per_categoria AS (
        SELECT COALESCE(categoria, '—') AS nome, ROUND(SUM(totale), 2) AS spesa, COUNT(*) AS righe
        FROM base
        GROUP BY COALESCE(categoria, '—')
        ORDER BY SUM(totale) DESC
        LIMIT 5
    )
    SELECT jsonb_build_object(
        'kpi', jsonb_build_object(
            'fatture_uniche',       (SELECT fatture_uniche FROM kpi),
            'righe_totali',         (SELECT righe_totali FROM kpi),
            'spesa_totale',         ROUND((SELECT spesa_totale FROM kpi), 2),
            'spesa_mese_corrente',  ROUND((SELECT spesa_mese_corrente FROM kpi), 2),
            'spesa_mese_precedente',ROUND((SELECT spesa_mese_precedente FROM kpi), 2),
            'prima_fattura',        (SELECT prima_fattura FROM kpi),
            'ultima_fattura',       (SELECT ultima_fattura FROM kpi)
        ),
        'spesa_mensile', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('mese', mese_key, 'spesa', spesa))
            FROM per_mese_asc
        ), '[]'::jsonb),
        'top_fornitori', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('nome', nome, 'spesa', spesa, 'righe', righe))
            FROM per_fornitore
        ), '[]'::jsonb),
        'top_categorie', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('nome', nome, 'spesa', spesa, 'righe', righe))
            FROM per_categoria
        ), '[]'::jsonb)
    )
    INTO v_result;

    RETURN v_result;
END;
$function$;
CREATE OR REPLACE FUNCTION public.get_ai_costs_summary(p_days integer DEFAULT NULL::integer)
 RETURNS TABLE(ristorante_id uuid, nome_ristorante text, ragione_sociale text, ai_cost_total numeric, ai_pdf_count integer, ai_categorization_count integer, ai_last_usage timestamp with time zone, ai_avg_cost_per_operation numeric, pdf_cost_total numeric, categorization_cost_total numeric, avg_cost_per_pdf numeric, avg_cost_per_categorization numeric, total_tokens bigint, prompt_tokens bigint, completion_tokens bigint)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
    RETURN QUERY
    WITH scoped_ristoranti AS (
        SELECT r.*
        FROM public.ristoranti AS r
        WHERE r.attivo = true
          AND (
              COALESCE(auth.role(), '') = 'service_role'
              OR r.user_id = auth.uid()
          )
    ),
    filtered_events AS (
        SELECT e.*
        FROM public.ai_usage_events AS e
        JOIN scoped_ristoranti AS sr
          ON sr.id = e.ristorante_id
        WHERE p_days IS NULL
           OR e.created_at >= NOW() - make_interval(days => p_days)
    ),
    agg AS (
        SELECT
            e.ristorante_id,
            SUM(e.total_cost)::DECIMAL(12,6) AS total_cost,
            COUNT(*) FILTER (WHERE e.operation_type = 'pdf')::INT AS pdf_count,
            COUNT(*) FILTER (WHERE e.operation_type = 'categorization')::INT AS categorization_count,
            MAX(e.created_at) AS last_usage,
            SUM(e.total_cost) FILTER (WHERE e.operation_type = 'pdf')::DECIMAL(12,6) AS pdf_cost_total,
            SUM(e.total_cost) FILTER (WHERE e.operation_type = 'categorization')::DECIMAL(12,6) AS categorization_cost_total,
            SUM(e.total_tokens)::BIGINT AS total_tokens,
            SUM(e.prompt_tokens)::BIGINT AS prompt_tokens,
            SUM(e.completion_tokens)::BIGINT AS completion_tokens
        FROM filtered_events AS e
        GROUP BY e.ristorante_id
    )
    SELECT
        sr.id,
        sr.nome_ristorante,
        sr.ragione_sociale,
        COALESCE(a.total_cost, 0)::DECIMAL(12,6) AS ai_cost_total,
        COALESCE(a.pdf_count, 0)::INT AS ai_pdf_count,
        COALESCE(a.categorization_count, 0)::INT AS ai_categorization_count,
        a.last_usage,
        CASE
            WHEN (COALESCE(a.pdf_count, 0) + COALESCE(a.categorization_count, 0)) > 0
            THEN ROUND(COALESCE(a.total_cost, 0) / (COALESCE(a.pdf_count, 0) + COALESCE(a.categorization_count, 0)), 6)
            ELSE 0
        END::DECIMAL(12,6) AS ai_avg_cost_per_operation,
        COALESCE(a.pdf_cost_total, 0)::DECIMAL(12,6) AS pdf_cost_total,
        COALESCE(a.categorization_cost_total, 0)::DECIMAL(12,6) AS categorization_cost_total,
        CASE
            WHEN COALESCE(a.pdf_count, 0) > 0 THEN ROUND(COALESCE(a.pdf_cost_total, 0) / a.pdf_count, 6)
            ELSE 0
        END::DECIMAL(12,6) AS avg_cost_per_pdf,
        CASE
            WHEN COALESCE(a.categorization_count, 0) > 0 THEN ROUND(COALESCE(a.categorization_cost_total, 0) / a.categorization_count, 6)
            ELSE 0
        END::DECIMAL(12,6) AS avg_cost_per_categorization,
        COALESCE(a.total_tokens, 0)::BIGINT,
        COALESCE(a.prompt_tokens, 0)::BIGINT,
        COALESCE(a.completion_tokens, 0)::BIGINT
    FROM scoped_ristoranti AS sr
    LEFT JOIN agg AS a
      ON a.ristorante_id = sr.id
    WHERE COALESCE(a.total_cost, 0) > 0
    ORDER BY COALESCE(a.total_cost, 0) DESC, sr.nome_ristorante;
END;
$function$;
CREATE OR REPLACE FUNCTION public.get_ai_costs_timeseries(p_days integer DEFAULT 30)
 RETURNS TABLE(usage_date date, total_cost numeric, pdf_cost numeric, categorization_cost numeric, operations_count integer)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        e.created_at::DATE AS usage_date,
        SUM(e.total_cost)::DECIMAL(12,6) AS total_cost,
        SUM(e.total_cost) FILTER (WHERE e.operation_type = 'pdf')::DECIMAL(12,6) AS pdf_cost,
        SUM(e.total_cost) FILTER (WHERE e.operation_type = 'categorization')::DECIMAL(12,6) AS categorization_cost,
        COUNT(*)::INT AS operations_count
    FROM public.ai_usage_events AS e
    JOIN public.ristoranti AS r
      ON r.id = e.ristorante_id
    WHERE e.created_at >= NOW() - make_interval(days => COALESCE(p_days, 30))
      AND (
          COALESCE(auth.role(), '') = 'service_role'
          OR r.user_id = auth.uid()
      )
    GROUP BY e.created_at::DATE
    ORDER BY usage_date;
END;
$function$;
CREATE OR REPLACE FUNCTION public.get_ai_recent_operations(p_days integer DEFAULT 30, p_limit integer DEFAULT 100)
 RETURNS TABLE(created_at timestamp with time zone, nome_ristorante text, ragione_sociale text, operation_type text, model text, source_file text, item_count integer, prompt_tokens integer, completion_tokens integer, total_tokens integer, total_cost numeric)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        e.created_at,
        r.nome_ristorante,
        r.ragione_sociale,
        e.operation_type,
        e.model,
        e.source_file,
        e.item_count,
        e.prompt_tokens,
        e.completion_tokens,
        e.total_tokens,
        e.total_cost
    FROM public.ai_usage_events AS e
    JOIN public.ristoranti AS r
      ON r.id = e.ristorante_id
    WHERE e.created_at >= NOW() - make_interval(days => COALESCE(p_days, 30))
      AND (
          COALESCE(auth.role(), '') = 'service_role'
          OR r.user_id = auth.uid()
      )
    ORDER BY e.created_at DESC
    LIMIT COALESCE(p_limit, 100);
END;
$function$;
CREATE OR REPLACE FUNCTION public.get_distinct_files(p_user_id uuid, p_ristorante_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(file_origine text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF p_ristorante_id IS NOT NULL
       AND COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = p_user_id
       ) THEN
        RAISE EXCEPTION 'Ristorante non autorizzato';
    END IF;

    RETURN QUERY
    SELECT DISTINCT f.file_origine
    FROM public.fatture AS f
    WHERE f.user_id = p_user_id
      AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
      AND f.file_origine IS NOT NULL
      AND f.file_origine <> ''
      AND f.deleted_at IS NULL          -- escludi cestino
    ORDER BY f.file_origine;
END;
$function$;
CREATE OR REPLACE FUNCTION public.get_next_ordine_ricetta(p_user_id uuid, p_ristorante_id uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    v_max_ordine INTEGER;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF p_ristorante_id IS NOT NULL
       AND COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = p_user_id
       ) THEN
        RAISE EXCEPTION 'Ristorante non autorizzato';
    END IF;

    SELECT COALESCE(MAX(r.ordine_visualizzazione), 0)
    INTO v_max_ordine
    FROM public.ricette AS r
    WHERE r.user_id = p_user_id
      AND (
          r.ristorante_id = p_ristorante_id
          OR (r.ristorante_id IS NULL AND p_ristorante_id IS NULL)
      );

    RETURN v_max_ordine + 1;
END;
$function$;
CREATE OR REPLACE FUNCTION public.increment_ai_cost(p_ristorante_id uuid, p_cost numeric, p_tokens integer DEFAULT 0, p_operation_type text DEFAULT 'pdf'::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
    PERFORM public.track_ai_usage_event(
        p_ristorante_id := p_ristorante_id,
        p_operation_type := p_operation_type,
        p_model := 'gpt-4o-mini',
        p_prompt_tokens := 0,
        p_completion_tokens := 0,
        p_input_cost := 0,
        p_output_cost := 0,
        p_total_cost := COALESCE(p_cost, 0),
        p_user_id := auth.uid(),
        p_source_file := NULL,
        p_item_count := 1,
        p_metadata := jsonb_build_object(
            'legacy_tokens', COALESCE(p_tokens, 0),
            'tracking_mode', 'legacy_increment'
        )
    );
END;
$function$;
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
CREATE OR REPLACE FUNCTION public.purge_processed_xml_content(p_retention_hours integer DEFAULT 24)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$;
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

    UPDATE public.fatture_queue
    SET payload_meta = payload_meta - 'raw_body_sample'
    WHERE payload_meta ? 'raw_body_sample'
      AND created_at < now() - make_interval(days => p_retention_days);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$function$;
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
CREATE OR REPLACE FUNCTION public.release_stale_locks(p_timeout_minutes integer DEFAULT 10)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE public.fatture_queue
    SET
        status     = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END,
        last_error = format(
            'Lock stale rilasciato: worker %s bloccato da %s minuti (timeout: %s min)',
            locked_by,
            EXTRACT(EPOCH FROM (now() - locked_at)) / 60,
            p_timeout_minutes
        ),
        locked_at = NULL,
        locked_by = NULL,
        next_retry_at = CASE
            WHEN attempt_count >= max_attempts THEN next_retry_at
            ELSE now() + INTERVAL '1 minute'
        END
    WHERE status    = 'processing'
      AND locked_at < now() - make_interval(mins => p_timeout_minutes);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$function$;
CREATE OR REPLACE FUNCTION public.resolve_unknown_tenant(p_piva text)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$;
CREATE OR REPLACE FUNCTION public.riparto_quote_mensili(p_user_id uuid, p_anno integer, p_mese integer)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_touched INTEGER := 0;
    r RECORD;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non puo'' essere NULL';
    END IF;

    FOR r IN
        WITH quote_agg AS (
            SELECT
                q.ristorante_id,
                COALESCE(SUM(q.quota_importo) FILTER (
                    WHERE (q.categoria IS NOT NULL AND public._riparto_categoria_is_fb(q.categoria))
                       OR (q.categoria IS NULL AND rc.tipo = 'fb')
                ), 0) AS q_fb,
                COALESCE(SUM(q.quota_importo) FILTER (
                    WHERE (q.categoria IS NOT NULL AND NOT public._riparto_categoria_is_fb(q.categoria))
                       OR (q.categoria IS NULL AND rc.tipo = 'generale')
                ), 0) AS q_spese
            FROM public.riparto_costi_catena rc
            JOIN public.riparto_costi_catena_quote q ON q.riparto_id = rc.id
            WHERE rc.user_id = p_user_id
              AND rc.anno = p_anno
              AND rc.mese = p_mese
            GROUP BY q.ristorante_id
        ),
        sedi_da_azzerare AS (
            SELECT mm.ristorante_id, 0::numeric AS q_fb, 0::numeric AS q_spese
            FROM public.margini_mensili mm
            WHERE mm.user_id = p_user_id
              AND mm.anno = p_anno
              AND mm.mese = p_mese
              AND (COALESCE(mm.quote_riparto_fb, 0) <> 0 OR COALESCE(mm.quote_riparto_spese, 0) <> 0)
              AND mm.ristorante_id NOT IN (SELECT ristorante_id FROM quote_agg)
        )
        SELECT ristorante_id, q_fb, q_spese FROM quote_agg
        UNION ALL
        SELECT ristorante_id, q_fb, q_spese FROM sedi_da_azzerare
    LOOP
        INSERT INTO public.margini_mensili AS mm (
            user_id, ristorante_id, anno, mese,
            quote_riparto_fb, quote_riparto_spese, updated_at
        )
        VALUES (
            p_user_id, r.ristorante_id, p_anno, p_mese,
            r.q_fb, r.q_spese, now()
        )
        ON CONFLICT (ristorante_id, anno, mese) DO UPDATE
        SET quote_riparto_fb    = EXCLUDED.quote_riparto_fb,
            quote_riparto_spese = EXCLUDED.quote_riparto_spese,
            updated_at          = now();

        UPDATE public.margini_mensili mm
        SET
            costi_fb_totali = round(
                COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0), 2),
            fatturato_netto = round(
                COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22 + COALESCE(mm.altri_ricavi_noiva,0), 2),
            primo_margine = round(
                (COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22 + COALESCE(mm.altri_ricavi_noiva,0))
                - (COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0)), 2),
            mol = round(
                (COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22 + COALESCE(mm.altri_ricavi_noiva,0))
                - (COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0))
                - (COALESCE(mm.costi_spese_auto,0) + COALESCE(mm.altri_costi_spese,0) + COALESCE(mm.quote_riparto_spese,0))
                - (COALESCE(mm.costo_dipendenti,0) + COALESCE(mm.costo_personale_extra,0)), 2),
            updated_at = now()
        WHERE mm.user_id = p_user_id
          AND mm.ristorante_id = r.ristorante_id
          AND mm.anno = p_anno
          AND mm.mese = p_mese;

        v_touched := v_touched + 1;
    END LOOP;

    RETURN v_touched;
END;
$function$;
CREATE OR REPLACE FUNCTION public.scadenziario_fatture_aggregate(p_user_id uuid, p_ristorante_ids uuid[])
 RETURNS TABLE(file_origine text, ristorante_id uuid, fornitore text, tipo_documento text, totale_documento numeric, data_documento date, created_at timestamp with time zone)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    RETURN QUERY
    WITH base AS (
        SELECT
            btrim(f.file_origine)                       AS file_origine,
            f.ristorante_id,
            COALESCE(f.fornitore, 'Sconosciuto')::text  AS fornitore,
            COALESCE(f.tipo_documento, 'TD01')::text    AS tipo_documento,
            COALESCE(f.totale_riga, 0)                  AS totale_riga,
            f.data_documento,
            f.created_at
        FROM public.fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.file_origine IS NOT NULL
          AND btrim(f.file_origine) <> ''
    ),
    prima_riga AS (
        SELECT DISTINCT ON (b.file_origine, b.ristorante_id)
            b.file_origine,
            b.ristorante_id,
            b.fornitore,
            b.tipo_documento,
            b.data_documento,
            b.created_at
        FROM base b
        ORDER BY b.file_origine, b.ristorante_id, b.created_at ASC NULLS LAST
    )
    SELECT
        p.file_origine,
        p.ristorante_id,
        p.fornitore,
        p.tipo_documento,
        ROUND(SUM(b.totale_riga), 2) AS totale_documento,
        p.data_documento,
        p.created_at
    FROM base b
    JOIN prima_riga p
      ON p.file_origine = b.file_origine AND p.ristorante_id = b.ristorante_id
    GROUP BY p.file_origine, p.ristorante_id, p.fornitore, p.tipo_documento, p.data_documento, p.created_at
    ORDER BY p.file_origine, p.ristorante_id;
END;
$function$;
CREATE OR REPLACE FUNCTION public.scarta_fattura_da_coda(p_queue_id bigint, p_user_id uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_updated INTEGER := 0;
BEGIN
    IF p_queue_id IS NULL OR p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_queue_id e p_user_id sono obbligatori';
    END IF;

    UPDATE public.fatture_queue
    SET status        = 'scartata',
        xml_content   = NULL,
        xml_purged_at = now(),
        processed_at  = now(),
        locked_at     = NULL,
        locked_by     = NULL
    WHERE id = p_queue_id
      AND user_id = p_user_id
      AND status = 'da_assegnare';

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated > 0;
END;
$function$;
CREATE OR REPLACE FUNCTION public.schedule_retry(p_queue_id bigint, p_error_msg text)
 RETURNS fatture_queue
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$;
CREATE OR REPLACE FUNCTION public.soft_delete_fatture_massivo(p_user_id uuid, p_ristorante_id uuid DEFAULT NULL::uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_count integer;
BEGIN
  UPDATE public.fatture
  SET deleted_at = now()
  WHERE user_id = p_user_id
    AND deleted_at IS NULL
    AND (p_ristorante_id IS NULL OR ristorante_id = p_ristorante_id);
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$function$;
CREATE OR REPLACE FUNCTION public.sostituisci_quote_riparto(p_riparto_id uuid, p_user_id uuid, p_tipo text, p_regola text, p_importo_totale numeric, p_quote jsonb)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_updated_id UUID;
BEGIN
    IF p_riparto_id IS NULL OR p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_riparto_id e p_user_id non possono essere NULL';
    END IF;
    IF p_quote IS NULL OR jsonb_array_length(p_quote) = 0 THEN
        RAISE EXCEPTION 'p_quote non può essere vuoto';
    END IF;

    UPDATE public.riparto_costi_catena
    SET tipo = p_tipo, regola = p_regola, importo_totale = p_importo_totale
    WHERE id = p_riparto_id AND user_id = p_user_id
    RETURNING id INTO v_updated_id;

    IF v_updated_id IS NULL THEN
        RAISE EXCEPTION 'Riparto % non trovato per user %', p_riparto_id, p_user_id;
    END IF;

    DELETE FROM public.riparto_costi_catena_quote WHERE riparto_id = v_updated_id;

    INSERT INTO public.riparto_costi_catena_quote (
        riparto_id, ristorante_id, quota_perc, quota_importo, categoria
    )
    SELECT
        v_updated_id,
        (q->>'ristorante_id')::UUID,
        (q->>'quota_perc')::NUMERIC,
        (q->>'quota_importo')::NUMERIC,
        NULLIF(q->>'categoria', '')
    FROM jsonb_array_elements(p_quote) AS q;

    RETURN v_updated_id;
END;
$function$;
CREATE OR REPLACE FUNCTION public.sposta_fattura_a_sede(p_user_id uuid, p_file_origine text, p_ristorante_id uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_rist_user_id UUID;
    v_rist_attivo  BOOLEAN;
    v_updated      INTEGER;
    v_collisioni   INTEGER;
BEGIN
    IF p_user_id IS NULL OR p_file_origine IS NULL OR p_ristorante_id IS NULL THEN
        RAISE EXCEPTION 'Parametri mancanti per sposta_fattura_a_sede';
    END IF;

    SELECT user_id, attivo
    INTO   v_rist_user_id, v_rist_attivo
    FROM   public.ristoranti
    WHERE  id = p_ristorante_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ristorante % inesistente', p_ristorante_id;
    END IF;

    IF v_rist_user_id IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'Ristorante % non appartiene all''utente', p_ristorante_id;
    END IF;

    IF v_rist_attivo IS NOT TRUE THEN
        RAISE EXCEPTION 'Ristorante % non attivo', p_ristorante_id;
    END IF;

    SELECT count(*)
    INTO   v_collisioni
    FROM   public.fatture
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  ristorante_id = p_ristorante_id
      AND  deleted_at IS NULL;

    IF v_collisioni > 0 THEN
        PERFORM 1
        FROM   public.fatture
        WHERE  user_id       = p_user_id
          AND  file_origine  = p_file_origine
          AND  ristorante_id IS DISTINCT FROM p_ristorante_id
          AND  deleted_at IS NULL
        LIMIT 1;

        IF FOUND THEN
            RAISE EXCEPTION 'collisione_file_in_sede_destinazione'
                USING DETAIL = format(
                    'Il file %s esiste già nella sede destinazione %s: '
                    'spostamento bloccato per evitare duplicati.',
                    p_file_origine, p_ristorante_id
                );
        END IF;
    END IF;

    UPDATE public.fatture
    SET    ristorante_id = p_ristorante_id
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  ristorante_id IS DISTINCT FROM p_ristorante_id
      AND  deleted_at IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    UPDATE public.fatture_documenti
    SET    ristorante_id = p_ristorante_id
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  ristorante_id IS DISTINCT FROM p_ristorante_id
      AND  deleted_at IS NULL;

    RETURN v_updated;
END;
$function$;
CREATE OR REPLACE FUNCTION public.track_ai_usage_event(p_ristorante_id uuid, p_operation_type text DEFAULT 'pdf'::text, p_model text DEFAULT 'gpt-4o-mini'::text, p_prompt_tokens integer DEFAULT 0, p_completion_tokens integer DEFAULT 0, p_input_cost numeric DEFAULT 0, p_output_cost numeric DEFAULT 0, p_total_cost numeric DEFAULT 0, p_user_id uuid DEFAULT NULL::uuid, p_source_file text DEFAULT NULL::text, p_item_count integer DEFAULT 1, p_metadata jsonb DEFAULT '{}'::jsonb)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    v_event_id BIGINT;
    v_total_tokens INT;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = auth.uid()
       ) THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF COALESCE(auth.role(), '') <> 'service_role'
       AND p_user_id IS NOT NULL
       AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'user_id non autorizzato';
    END IF;

    v_total_tokens := COALESCE(p_prompt_tokens, 0) + COALESCE(p_completion_tokens, 0);

    INSERT INTO public.ai_usage_events (
        ristorante_id,
        user_id,
        operation_type,
        model,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        input_cost,
        output_cost,
        total_cost,
        item_count,
        source_file,
        metadata
    )
    VALUES (
        p_ristorante_id,
        COALESCE(p_user_id, auth.uid()),
        COALESCE(NULLIF(p_operation_type, ''), 'other'),
        COALESCE(NULLIF(p_model, ''), 'gpt-4o-mini'),
        COALESCE(p_prompt_tokens, 0),
        COALESCE(p_completion_tokens, 0),
        v_total_tokens,
        COALESCE(p_input_cost, 0),
        COALESCE(p_output_cost, 0),
        COALESCE(p_total_cost, 0),
        GREATEST(COALESCE(p_item_count, 1), 1),
        NULLIF(p_source_file, ''),
        COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_event_id;

    UPDATE public.ristoranti
    SET ai_cost_total = COALESCE(ai_cost_total, 0) + COALESCE(p_total_cost, 0),
        ai_pdf_count = CASE
            WHEN p_operation_type = 'pdf' THEN COALESCE(ai_pdf_count, 0) + 1
            ELSE COALESCE(ai_pdf_count, 0)
        END,
        ai_categorization_count = CASE
            WHEN p_operation_type = 'categorization' THEN COALESCE(ai_categorization_count, 0) + 1
            ELSE COALESCE(ai_categorization_count, 0)
        END,
        ai_last_usage = NOW()
    WHERE id = p_ristorante_id;

    RETURN v_event_id;
END;
$function$;
CREATE OR REPLACE FUNCTION public.upsert_notification_inbox(p_notifications jsonb)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$;
CREATE OR REPLACE FUNCTION public.admin_ai_mensile(p_dal date)
 RETURNS TABLE(ristorante_id uuid, mese text, categorization bigint, chat bigint, richieste bigint, token bigint, costo numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select e.ristorante_id,
         to_char(date_trunc('month', e.created_at), 'YYYY-MM') as mese,
         count(*) filter (where e.operation_type = 'categorization')::bigint as categorization,
         count(*) filter (where e.operation_type = 'chat')::bigint           as chat,
         count(*)::bigint                                                    as richieste,
         coalesce(sum(e.total_tokens), 0)::bigint                            as token,
         coalesce(sum(e.total_cost), 0)::numeric                             as costo
  from ai_usage_events e
  where e.created_at >= p_dal
  group by e.ristorante_id, date_trunc('month', e.created_at)
  order by mese desc;
$function$;
CREATE OR REPLACE FUNCTION public.admin_consumi_mensili(p_dal date)
 RETURNS TABLE(ristorante_id uuid, mese text, manuali bigint, sdi bigint, tot bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  with doc as (
    select distinct
           fd.ristorante_id,
           fd.file_origine,
           date_trunc('month', fd.created_at)::date as mese,
           fd.source_origin
    from fatture_documenti fd
    where fd.deleted_at is null
      and fd.created_at >= p_dal
  )
  select d.ristorante_id,
         to_char(d.mese, 'YYYY-MM') as mese,
         count(*) filter (where d.source_origin = 'manual')::bigint        as manuali,
         count(*) filter (where d.source_origin = 'invoicetronic')::bigint as sdi,
         count(*)::bigint                                                  as tot
  from doc d
  group by d.ristorante_id, d.mese
  order by d.mese desc;
$function$;
CREATE OR REPLACE FUNCTION public.admin_conteggio_fatture(p_user_ids uuid[])
 RETURNS TABLE(user_id uuid, n bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select fd.user_id, count(*)::bigint as n
  from fatture_documenti fd
  where fd.user_id = any(p_user_ids)
    and fd.deleted_at is null
  group by fd.user_id;
$function$;
CREATE OR REPLACE FUNCTION public.admin_fatture_per_mese(p_dal date)
 RETURNS TABLE(mese text, n bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select to_char(fd.data_documento, 'YYYY-MM') as mese, count(*)::bigint as n
  from fatture_documenti fd
  where fd.data_documento >= p_dal
    and fd.deleted_at is null
  group by to_char(fd.data_documento, 'YYYY-MM')
  order by mese;
$function$;
CREATE OR REPLACE FUNCTION public.articoli_da_fatture(p_user_id uuid, p_ristorante_id uuid, p_categorie_escluse text[])
 RETURNS TABLE(descrizione text, prezzo_unitario numeric, unita_misura text, data_documento date)
 LANGUAGE sql
 STABLE
AS $function$
    select distinct on (f.descrizione)
        f.descrizione,
        f.prezzo_unitario,
        f.unita_misura,
        f.data_documento
    from public.fatture f
    where f.user_id = p_user_id
      and f.ristorante_id = p_ristorante_id
      and f.deleted_at is null
      and f.descrizione is not null
      and btrim(f.descrizione) <> ''
      and not (f.categoria = any (p_categorie_escluse))
    order by f.descrizione, f.data_documento desc nulls last;
$function$;
CREATE OR REPLACE FUNCTION public.chat_top_categoria_fornitore(p_user_id uuid, p_ristorante_id uuid, p_giorni integer DEFAULT 90, p_top integer DEFAULT 5)
 RETURNS TABLE(tipo text, voce text, spesa numeric)
 LANGUAGE sql
 STABLE
 SET search_path TO 'public'
AS $function$
    WITH base AS (
        SELECT
            COALESCE(NULLIF(TRIM(f.categoria), ''), 'Altro') AS categoria,
            COALESCE(NULLIF(TRIM(f.fornitore), ''), 'Sconosciuto') AS fornitore,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.deleted_at IS NULL
          AND f.data_documento >= (CURRENT_DATE - p_giorni)
          AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
    ),
    top_cat AS (
        SELECT 'categoria'::text AS tipo, categoria AS voce, SUM(totale_riga) AS spesa
        FROM base GROUP BY categoria ORDER BY SUM(totale_riga) DESC LIMIT p_top
    ),
    top_forn AS (
        SELECT 'fornitore'::text AS tipo, fornitore AS voce, SUM(totale_riga) AS spesa
        FROM base GROUP BY fornitore ORDER BY SUM(totale_riga) DESC LIMIT p_top
    )
    SELECT tipo, voce, ROUND(spesa, 2) AS spesa FROM top_cat
    UNION ALL
    SELECT tipo, voce, ROUND(spesa, 2) AS spesa FROM top_forn;
$function$;
CREATE OR REPLACE FUNCTION public.costi_automatici_mensili(p_user_id uuid, p_ristorante_id uuid, p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(mese integer, food numeric, spese numeric)
 LANGUAGE sql
 STABLE
AS $function$
    WITH base AS (
        SELECT
            EXTRACT(MONTH FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
            f.categoria,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = p_ristorante_id
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)   -- anti-doppio-conteggio (MOL)
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(f.data_competenza, f.data_documento)) = p_anno
    )
    SELECT
        base.mese,
        COALESCE(SUM(base.totale_riga) FILTER (
            WHERE base.categoria <> ALL(p_cat_spese) AND base.categoria <> '📝 NOTE E DICITURE'
        ), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.mese
    ORDER BY base.mese;
$function$;
CREATE OR REPLACE FUNCTION public.costi_automatici_mensili_gruppo(p_user_id uuid, p_ristorante_ids uuid[], p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(ristorante_id uuid, mese integer, food numeric, spese numeric)
 LANGUAGE sql
 STABLE
AS $function$
    WITH base AS (
        SELECT
            f.ristorante_id,
            EXTRACT(MONTH FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
            f.categoria,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)   -- anti-doppio-conteggio (MOL)
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(f.data_competenza, f.data_documento)) = p_anno
    )
    SELECT
        base.ristorante_id,
        base.mese,
        COALESCE(SUM(base.totale_riga) FILTER (
            WHERE base.categoria <> ALL(p_cat_spese) AND base.categoria <> '📝 NOTE E DICITURE'
        ), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.ristorante_id, base.mese
    ORDER BY base.ristorante_id, base.mese;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_peso_categoria(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(ristorante_id uuid, categoria text, spesa numeric, peso_perc numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH righe AS (
        SELECT
            f.ristorante_id AS rid,
            f.categoria AS cat,
            SUM(f.totale_riga) AS tot
        FROM fatture f
        WHERE f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND f.totale_riga > 0
          AND UPPER(f.categoria) NOT IN (
                'SERVIZI E CONSULENZE',
                'UTENZE E LOCALI',
                'MANUTENZIONE E ATTREZZATURE',
                'MATERIALE DI CONSUMO'
          )
          AND f.categoria NOT LIKE '%NOTE E DICITURE%'
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
          AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
        GROUP BY 1, 2
    ),
    tot_pv AS (
        SELECT rid, SUM(tot) AS tot_fb FROM righe GROUP BY 1
    )
    SELECT
        r.rid AS ristorante_id,
        r.cat AS categoria,
        r.tot AS spesa,
        (100.0 * r.tot / t.tot_fb)::numeric AS peso_perc
    FROM righe r
    JOIN tot_pv t ON t.rid = r.rid
    WHERE t.tot_fb > 0;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_salute_componenti(p_ristorante_ids uuid[], p_inizio timestamp with time zone, p_anno integer, p_mese integer)
 RETURNS TABLE(ristorante_id uuid, n_fatture bigint, n_needs_review bigint, netto numeric, personale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH f AS (
        SELECT fa.ristorante_id AS rid,
               count(*) AS n_fatture,
               count(*) FILTER (WHERE fa.needs_review) AS n_needs_review
        FROM fatture fa
        WHERE fa.ristorante_id = ANY(p_ristorante_ids)
          AND fa.deleted_at IS NULL
          AND fa.created_at >= p_inizio
        GROUP BY fa.ristorante_id
    ),
    m AS (
        SELECT mm.ristorante_id AS rid,
               sum(coalesce(mm.fatturato_iva10, 0) + coalesce(mm.fatturato_iva22, 0)
                   + coalesce(mm.altri_ricavi_noiva, 0)) AS netto,
               sum(coalesce(mm.costo_dipendenti, 0) + coalesce(mm.costo_personale_extra, 0)) AS personale
        FROM margini_mensili mm
        WHERE mm.ristorante_id = ANY(p_ristorante_ids)
          AND mm.anno = p_anno AND mm.mese = p_mese
        GROUP BY mm.ristorante_id
    )
    SELECT r AS ristorante_id,
           coalesce(f.n_fatture, 0)::bigint AS n_fatture,
           coalesce(f.n_needs_review, 0)::bigint AS n_needs_review,
           coalesce(m.netto, 0)::numeric AS netto,
           coalesce(m.personale, 0)::numeric AS personale
    FROM unnest(p_ristorante_ids) AS r
    LEFT JOIN f ON f.rid = r
    LEFT JOIN m ON m.rid = r;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_spesa_pivot(p_ristorante_ids uuid[], p_dimensione text, p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(ristorante_id uuid, dim_val text, totale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        COALESCE(
            NULLIF(CASE WHEN p_dimensione = 'fornitore' THEN f.fornitore ELSE f.categoria END, ''),
            'N/D'
        ) AS dim_val,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.totale_riga > 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, dim_val;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_spreco_fb_categorie(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(ristorante_id uuid, anno integer, mese integer, categoria text, totale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        EXTRACT(YEAR FROM f.data_documento)::int AS anno,
        EXTRACT(MONTH FROM f.data_documento)::int AS mese,
        f.categoria,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.ripartita_su_gruppo IS DISTINCT FROM true
      AND f.totale_riga > 0
      AND f.data_documento IS NOT NULL
      AND f.data_documento >= p_data_da
      AND f.data_documento <= p_data_a
      AND f.categoria IN (
          'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
          'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA',
          'SALSE E CREME','PRODOTTI DA FORNO','SPEZIE E AROMI','SUSHI VARIE',
          'ACQUA','BEVANDE','CAFFE E THE','VARIE BAR',
          'BIRRE','VINI','DISTILLATI','AMARI/LIQUORI',
          'PASTICCERIA','GELATI E DESSERT',
          'SHOP'
      )
    GROUP BY f.ristorante_id, anno, mese, f.categoria;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_tag_analisi(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
 RETURNS TABLE(ristorante_id uuid, spesa numeric, spesa_prezzo_valido numeric, quantita numeric, n_righe bigint, n_fornitori bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        sum(f.totale_riga) AS spesa,
        sum(f.totale_riga) FILTER (WHERE f.prezzo_unitario > 0) AS spesa_prezzo_valido,
        sum(CASE WHEN f.quantita > 0 THEN f.quantita ELSE 0 END) AS quantita,
        count(*)::bigint AS n_righe,
        count(DISTINCT f.fornitore)::bigint AS n_fornitori
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_tag_descrizioni(p_ristorante_ids uuid[], p_q text DEFAULT NULL::text, p_limit integer DEFAULT 500, p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(descrizione text, descrizione_key text, n bigint, spesa numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        (array_agg(f.descrizione ORDER BY f.data_documento DESC))[1] AS descrizione,
        upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) AS descrizione_key,
        count(*)::bigint AS n,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.descrizione IS NOT NULL
      AND btrim(f.descrizione) <> ''
      AND (p_q IS NULL OR btrim(p_q) = '' OR f.descrizione ILIKE '%' || btrim(p_q) || '%')
    GROUP BY descrizione_key
    ORDER BY spesa DESC NULLS LAST
    LIMIT p_limit;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_tag_fornitori(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
 RETURNS TABLE(fornitore text, spesa numeric, n_righe bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        COALESCE(NULLIF(btrim(f.fornitore), ''), '—') AS fornitore,
        sum(f.totale_riga) AS spesa,
        count(*)::bigint AS n_righe
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1
    ORDER BY spesa DESC NULLS LAST
    LIMIT 20;
$function$;
CREATE OR REPLACE FUNCTION public.gruppo_tag_trend(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
 RETURNS TABLE(anno integer, mese integer, spesa numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        extract(year  FROM COALESCE(f.data_competenza, f.data_documento))::int AS anno,
        extract(month FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1, 2
    ORDER BY 1, 2;
$function$;
CREATE OR REPLACE FUNCTION public.custom_tag_prodotti_prepare_row()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE
    v_user_id UUID;
    v_ristorante_id UUID;
BEGIN
    NEW.descrizione := btrim(NEW.descrizione);
    NEW.descrizione_key := public.normalize_custom_tag_key(NEW.descrizione);

    IF NEW.descrizione_key IS NULL THEN
        RAISE EXCEPTION 'descrizione_key vuota non consentita';
    END IF;

    SELECT ct.user_id, ct.ristorante_id
      INTO v_user_id, v_ristorante_id
      FROM public.custom_tags AS ct
     WHERE ct.id = NEW.tag_id;

    IF v_user_id IS NULL OR v_ristorante_id IS NULL THEN
        RAISE EXCEPTION 'tag_id % non valido o ownership non trovata', NEW.tag_id;
    END IF;

    NEW.user_id := v_user_id;
    NEW.ristorante_id := v_ristorante_id;

    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.custom_tag_suggestion_items_prepare_row()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE
    v_user_id UUID;
    v_ristorante_id UUID;
BEGIN
    NEW.descrizione := btrim(COALESCE(NEW.descrizione, ''));
    NEW.descrizione_key := public.normalize_custom_tag_key(NEW.descrizione);

    IF NEW.descrizione_key IS NULL THEN
        RAISE EXCEPTION 'descrizione_key vuota non consentita';
    END IF;

    SELECT s.user_id, s.ristorante_id
      INTO v_user_id, v_ristorante_id
      FROM public.custom_tag_suggestions AS s
     WHERE s.id = NEW.suggestion_id;

    IF v_user_id IS NULL OR v_ristorante_id IS NULL THEN
        RAISE EXCEPTION 'suggestion_id % non valido o ownership non trovata', NEW.suggestion_id;
    END IF;

    NEW.user_id := v_user_id;
    NEW.ristorante_id := v_ristorante_id;

    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.custom_tag_suggestions_set_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.fn_bump_cache_version()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
    update public.cache_version
        set version = version + 1,
            updated_at = now()
    where key = 'memoria_classificazione';
    return null;
end;
$function$;
CREATE OR REPLACE FUNCTION public.fn_bump_cache_version_fatture_documenti()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
    UPDATE public.cache_version
        SET version = version + 1,
            updated_at = now()
    WHERE key = 'fatture_documenti';
    RETURN NULL;
END;
$function$;
CREATE OR REPLACE FUNCTION public.fn_bump_cache_version_fornitori_config()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
    UPDATE public.cache_version
        SET version = version + 1,
            updated_at = now()
    WHERE key = 'fornitori_pagamenti_config';
    RETURN NULL;
END;
$function$;
CREATE OR REPLACE FUNCTION public.fn_log_category_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_actor_sub_text TEXT;
    v_actor_email TEXT;
    v_source TEXT;
    v_batch_text TEXT;
    v_batch_id UUID;
    v_ristorante_id UUID;
    v_file_origine TEXT;
    v_numero_riga INTEGER;
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RETURN NEW;
    END IF;

    IF NEW.categoria IS NOT DISTINCT FROM OLD.categoria THEN
        RETURN NEW;
    END IF;

    v_actor_sub_text := COALESCE(
        NULLIF(current_setting('app.category_change_actor_user_id', true), ''),
        NULLIF(current_setting('request.jwt.claim.sub', true), '')
    );
    v_actor_email := COALESCE(
        NULLIF(current_setting('app.category_change_actor_email', true), ''),
        NULLIF(current_setting('request.jwt.claim.email', true), '')
    );
    v_source := COALESCE(NULLIF(current_setting('app.category_change_source', true), ''), 'db_trigger');
    v_batch_text := NULLIF(current_setting('app.category_change_batch_id', true), '');

    IF v_batch_text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
        v_batch_id := v_batch_text::UUID;
    ELSE
        v_batch_id := NULL;
    END IF;

    -- Accesso SICURO ai campi che esistono solo su alcune tabelle (es. fatture ha
    -- ristorante_id/file_origine/numero_riga, prodotti_utente no). to_jsonb(...)->>'campo'
    -- ritorna NULL se il campo non esiste, evitando l'errore "record new has no field"
    -- che PL/pgSQL solleverebbe risolvendo NEW.<campo> a compile-time anche dentro un CASE.
    v_ristorante_id := NULLIF(COALESCE(to_jsonb(NEW)->>'ristorante_id', to_jsonb(OLD)->>'ristorante_id'), '')::UUID;

    IF TG_TABLE_NAME = 'fatture' THEN
        v_file_origine := COALESCE(to_jsonb(NEW)->>'file_origine', to_jsonb(OLD)->>'file_origine');
        v_numero_riga  := NULLIF(COALESCE(to_jsonb(NEW)->>'numero_riga', to_jsonb(OLD)->>'numero_riga'), '')::INTEGER;
    ELSE
        v_file_origine := NULL;
        v_numero_riga := NULL;
    END IF;

    INSERT INTO public.category_change_log (
        table_name, target_id, user_id, ristorante_id, descrizione,
        file_origine, numero_riga, old_categoria, new_categoria,
        actor_user_id, actor_email, source, batch_id, details
    )
    VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id::TEXT, OLD.id::TEXT),
        COALESCE(NEW.user_id, OLD.user_id),
        v_ristorante_id,
        COALESCE(NEW.descrizione, OLD.descrizione),
        v_file_origine,
        v_numero_riga,
        OLD.categoria,
        NEW.categoria,
        CASE WHEN v_actor_sub_text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN v_actor_sub_text::UUID ELSE NULL END,
        v_actor_email,
        v_source,
        v_batch_id,
        jsonb_build_object('trigger', TG_NAME)
    );

    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.fn_propagate_deleted_at_fatture()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
    -- Se deleted_at e' cambiato su fatture, aggiornare fatture_documenti
    IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
        UPDATE public.fatture_documenti
            SET deleted_at = NEW.deleted_at,
                updated_at = now()
        WHERE user_id = NEW.user_id
          AND ristorante_id = NEW.ristorante_id
          AND file_origine = NEW.file_origine;
    END IF;
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.set_inventario_voci_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.set_marketplace_leads_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.set_ricavi_giornalieri_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.sync_margini_mensili_from_ricavi()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE
  v_user_id UUID;
  v_ristorante_id UUID;
  v_anno INT;
  v_mese INT;
  v_iva10 NUMERIC(12,2);
  v_iva22 NUMERIC(12,2);
  v_altri NUMERIC(12,2);
  v_coperti INT;
BEGIN
  IF TG_OP = 'DELETE' THEN
    v_user_id := OLD.user_id;
    v_ristorante_id := OLD.ristorante_id;
    v_anno := EXTRACT(YEAR FROM OLD.data);
    v_mese := EXTRACT(MONTH FROM OLD.data);
  ELSE
    v_user_id := NEW.user_id;
    v_ristorante_id := NEW.ristorante_id;
    v_anno := EXTRACT(YEAR FROM NEW.data);
    v_mese := EXTRACT(MONTH FROM NEW.data);
  END IF;

  SELECT
    COALESCE(SUM(fatturato_iva10), 0),
    COALESCE(SUM(fatturato_iva22), 0),
    COALESCE(SUM(altri_ricavi_noiva), 0),
    SUM(coperti)
  INTO v_iva10, v_iva22, v_altri, v_coperti
  FROM public.ricavi_giornalieri
  WHERE ristorante_id = v_ristorante_id
    AND EXTRACT(YEAR FROM data) = v_anno
    AND EXTRACT(MONTH FROM data) = v_mese;

  INSERT INTO public.margini_mensili (
    user_id, ristorante_id, anno, mese,
    fatturato_iva10, fatturato_iva22, altri_ricavi_noiva,
    fatturato_netto, coperti, updated_at
  )
  VALUES (
    v_user_id, v_ristorante_id, v_anno, v_mese,
    v_iva10, v_iva22, v_altri,
    (v_iva10 / 1.10) + (v_iva22 / 1.22) + v_altri,
    v_coperti, now()
  )
  ON CONFLICT (ristorante_id, anno, mese)
  DO UPDATE SET
    fatturato_iva10 = EXCLUDED.fatturato_iva10,
    fatturato_iva22 = EXCLUDED.fatturato_iva22,
    altri_ricavi_noiva = EXCLUDED.altri_ricavi_noiva,
    fatturato_netto = EXCLUDED.fatturato_netto,
    coperti = EXCLUDED.coperti,
    updated_at = now();

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.sync_piva_ristoranti()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.piva_ristoranti (
            user_id,
            ristorante_id,
            piva,
            nome_ristorante
        )
        VALUES (
            NEW.user_id,
            NEW.id,
            NEW.partita_iva,
            NEW.nome_ristorante
        );

        IF NEW.partita_iva IS NOT NULL AND trim(NEW.partita_iva) <> '' THEN
            PERFORM public.resolve_unknown_tenant(trim(NEW.partita_iva));
        END IF;

        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE public.piva_ristoranti
        SET piva = NEW.partita_iva,
            nome_ristorante = NEW.nome_ristorante
        WHERE ristorante_id = NEW.id;

        IF NEW.partita_iva IS DISTINCT FROM OLD.partita_iva
           AND NEW.partita_iva IS NOT NULL
           AND trim(NEW.partita_iva) <> '' THEN
            PERFORM public.resolve_unknown_tenant(trim(NEW.partita_iva));
        END IF;

        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM public.piva_ristoranti
        WHERE ristorante_id = OLD.id;

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$function$;
CREATE OR REPLACE FUNCTION public.trg_riparto_touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.trg_ristoranti_indirizzo_match()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
    NEW.indirizzo_match := public.normalizza_indirizzo_match(
        concat_ws(' ', NEW.indirizzo, NEW.cap, NEW.comune)
    );
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.update_diario_eventi_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$function$;
CREATE OR REPLACE FUNCTION public.update_dipendenti_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$function$;
CREATE OR REPLACE FUNCTION public.update_ingredienti_utente_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.update_ingredienti_workspace_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.update_note_diario_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$;
CREATE OR REPLACE FUNCTION public.update_regole_turni_ricorrenti_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$function$;
CREATE OR REPLACE FUNCTION public.update_ricette_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$;
CREATE TRIGGER trg_bump_cache_cm AFTER INSERT OR DELETE OR UPDATE ON public.classificazioni_manuali FOR EACH STATEMENT EXECUTE FUNCTION fn_bump_cache_version();
CREATE TRIGGER trg_custom_tag_prodotti_prepare_row BEFORE INSERT OR UPDATE ON public.custom_tag_prodotti FOR EACH ROW EXECUTE FUNCTION custom_tag_prodotti_prepare_row();
CREATE TRIGGER trg_custom_tag_suggestion_items_prepare_row BEFORE INSERT OR UPDATE ON public.custom_tag_suggestion_items FOR EACH ROW EXECUTE FUNCTION custom_tag_suggestion_items_prepare_row();
CREATE TRIGGER trg_custom_tag_suggestions_set_updated_at BEFORE UPDATE ON public.custom_tag_suggestions FOR EACH ROW EXECUTE FUNCTION custom_tag_suggestions_set_updated_at();
CREATE TRIGGER trg_diario_eventi_updated_at BEFORE UPDATE ON public.diario_eventi FOR EACH ROW EXECUTE FUNCTION update_diario_eventi_timestamp();
CREATE TRIGGER trg_dipendenti_updated_at BEFORE UPDATE ON public.dipendenti FOR EACH ROW EXECUTE FUNCTION update_dipendenti_timestamp();
CREATE TRIGGER trg_log_category_change_fatture AFTER UPDATE OF categoria ON public.fatture FOR EACH ROW EXECUTE FUNCTION fn_log_category_change();
CREATE TRIGGER trg_propagate_deleted_at_fatture AFTER UPDATE OF deleted_at ON public.fatture FOR EACH ROW EXECUTE FUNCTION fn_propagate_deleted_at_fatture();
CREATE TRIGGER trg_bump_cache_fat_doc AFTER INSERT OR DELETE OR UPDATE ON public.fatture_documenti FOR EACH STATEMENT EXECUTE FUNCTION fn_bump_cache_version_fatture_documenti();
CREATE TRIGGER trg_bump_cache_frn_cfg AFTER INSERT OR DELETE OR UPDATE ON public.fornitori_pagamenti_config FOR EACH STATEMENT EXECUTE FUNCTION fn_bump_cache_version_fornitori_config();
CREATE TRIGGER trigger_update_ingredienti_utente_timestamp BEFORE UPDATE ON public.ingredienti_utente FOR EACH ROW EXECUTE FUNCTION update_ingredienti_utente_timestamp();
CREATE TRIGGER trigger_update_ingredienti_workspace_timestamp BEFORE UPDATE ON public.ingredienti_workspace FOR EACH ROW EXECUTE FUNCTION update_ingredienti_workspace_timestamp();
CREATE TRIGGER trg_inventario_voci_updated_at BEFORE UPDATE ON public.inventario_voci FOR EACH ROW EXECUTE FUNCTION set_inventario_voci_updated_at();
CREATE TRIGGER trg_marketplace_leads_updated_at BEFORE UPDATE ON public.marketplace_leads FOR EACH ROW EXECUTE FUNCTION set_marketplace_leads_updated_at();
CREATE TRIGGER trigger_update_note_diario_timestamp BEFORE UPDATE ON public.note_diario FOR EACH ROW EXECUTE FUNCTION update_note_diario_timestamp();
CREATE TRIGGER trg_bump_cache_pm AFTER INSERT OR DELETE OR UPDATE ON public.prodotti_master FOR EACH STATEMENT EXECUTE FUNCTION fn_bump_cache_version();
CREATE TRIGGER trg_bump_cache_pu AFTER INSERT OR DELETE OR UPDATE ON public.prodotti_utente FOR EACH STATEMENT EXECUTE FUNCTION fn_bump_cache_version();
CREATE TRIGGER trg_log_category_change_prodotti_utente AFTER UPDATE OF categoria ON public.prodotti_utente FOR EACH ROW EXECUTE FUNCTION fn_log_category_change();
CREATE TRIGGER trg_regole_turni_ricorrenti_updated_at BEFORE UPDATE ON public.regole_turni_ricorrenti FOR EACH ROW EXECUTE FUNCTION update_regole_turni_ricorrenti_timestamp();
CREATE TRIGGER trg_ricavi_giornalieri_sync_margini AFTER INSERT OR DELETE OR UPDATE ON public.ricavi_giornalieri FOR EACH ROW EXECUTE FUNCTION sync_margini_mensili_from_ricavi();
CREATE TRIGGER trg_ricavi_giornalieri_updated_at BEFORE UPDATE ON public.ricavi_giornalieri FOR EACH ROW EXECUTE FUNCTION set_ricavi_giornalieri_updated_at();
CREATE TRIGGER trigger_update_ricette_timestamp BEFORE UPDATE ON public.ricette FOR EACH ROW EXECUTE FUNCTION update_ricette_timestamp();
CREATE TRIGGER riparto_costi_catena_touch BEFORE UPDATE ON public.riparto_costi_catena FOR EACH ROW EXECUTE FUNCTION trg_riparto_touch_updated_at();
CREATE TRIGGER riparto_regole_fornitore_touch BEFORE UPDATE ON public.riparto_regole_fornitore FOR EACH ROW EXECUTE FUNCTION trg_riparto_touch_updated_at();
CREATE TRIGGER ristoranti_indirizzo_match_biu BEFORE INSERT OR UPDATE OF indirizzo, cap, comune ON public.ristoranti FOR EACH ROW EXECUTE FUNCTION trg_ristoranti_indirizzo_match();
CREATE TRIGGER trigger_sync_piva_ristoranti AFTER INSERT OR DELETE OR UPDATE ON public.ristoranti FOR EACH ROW EXECUTE FUNCTION sync_piva_ristoranti();
REVOKE ALL ON FUNCTION public.accoda_upload_ambiguo(p_user_id uuid, p_piva_raw text, p_xml_content text, p_nome_file text, p_indirizzo_raw text, p_xml_hash text, p_payload_meta jsonb, p_anteprima_righe jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_ai_mensile(p_dal date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_consumi_mensili(p_dal date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_conteggio_fatture(p_user_ids uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_fatture_per_mese(p_dal date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.assegna_fattura_a_sede(p_queue_id bigint, p_ristorante_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.assegna_fattura_a_sede_tecnica(p_queue_id bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.chat_top_categoria_fornitore(p_user_id uuid, p_ristorante_id uuid, p_giorni integer, p_top integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.chat_usage_check_and_log(p_user_id uuid, p_ristorante_id uuid, p_limite integer, p_pool boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_batch_for_processing(p_worker_id text, p_batch_size integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_ricavi_email_batch(p_worker_id text, p_batch_size integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.costi_automatici_mensili(p_user_id uuid, p_ristorante_id uuid, p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.costi_automatici_mensili_gruppo(p_user_id uuid, p_ristorante_ids uuid[], p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.crea_riparto_con_quote(p_user_id uuid, p_origine text, p_file_origine text, p_fornitore text, p_descrizione text, p_importo_totale numeric, p_tipo text, p_anno integer, p_mese integer, p_regola text, p_quote jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.dashboard_stats_aggregata(p_user_id uuid, p_ristorante_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_ai_costs_summary(p_days integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_ai_costs_timeseries(p_days integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_ai_recent_operations(p_days integer, p_limit integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_distinct_files(p_user_id uuid, p_ristorante_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_peso_categoria(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_salute_componenti(p_ristorante_ids uuid[], p_inizio timestamp with time zone, p_anno integer, p_mese integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_spesa_pivot(p_ristorante_ids uuid[], p_dimensione text, p_data_da date, p_data_a date, p_escludi_da_verificare boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_spreco_fb_categorie(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_tag_descrizioni(p_ristorante_ids uuid[], p_q text, p_limit integer, p_escludi_da_verificare boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_tag_fornitori(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_tag_trend(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.increment_ai_cost(p_ristorante_id uuid, p_cost numeric, p_tokens integer, p_operation_type text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.mark_queue_item_done(p_queue_id bigint, p_purge_xml boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_fatture_queue_last_error(p_retention_days integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_processed_xml_content(p_retention_hours integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_raw_body_sample(p_retention_days integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_ricavi_email_queue(p_retention_days integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.purge_upload_events_retention(p_retention_days integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.release_stale_locks(p_timeout_minutes integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.resolve_unknown_tenant(p_piva text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.riparto_quote_mensili(p_user_id uuid, p_anno integer, p_mese integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.scadenziario_fatture_aggregate(p_user_id uuid, p_ristorante_ids uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.scarta_fattura_da_coda(p_queue_id bigint, p_user_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.schedule_retry(p_queue_id bigint, p_error_msg text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public._azzera_attribuzione_categoria() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.aggiorna_categoria_fatture_attribuita(p_ids bigint[], p_categoria text, p_source text, p_extra jsonb, p_actor_email text, p_actor_user_id uuid, p_batch_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.aggiorna_categoria_prodotto_attribuita(p_user_id uuid, p_descrizione text, p_categoria text, p_source text, p_actor_email text, p_actor_user_id uuid, p_batch_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.soft_delete_fatture_massivo(p_user_id uuid, p_ristorante_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sostituisci_quote_riparto(p_riparto_id uuid, p_user_id uuid, p_tipo text, p_regola text, p_importo_totale numeric, p_quote jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sposta_fattura_a_sede(p_user_id uuid, p_file_origine text, p_ristorante_id uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.track_ai_usage_event(p_ristorante_id uuid, p_operation_type text, p_model text, p_prompt_tokens integer, p_completion_tokens integer, p_input_cost numeric, p_output_cost numeric, p_total_cost numeric, p_user_id uuid, p_source_file text, p_item_count integer, p_metadata jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.upsert_notification_inbox(p_notifications jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.gruppo_tag_analisi(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_next_ordine_ricetta(p_user_id uuid, p_ristorante_id uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.articoli_da_fatture(p_user_id uuid, p_ristorante_id uuid, p_categorie_escluse text[]) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._riparto_categoria_is_fb(p_categoria text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.normalize_custom_tag_key(input_text text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.normalizza_indirizzo_match(p_raw text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public._riparto_categoria_is_fb(p_categoria text) TO service_role;
GRANT EXECUTE ON FUNCTION public.accoda_upload_ambiguo(p_user_id uuid, p_piva_raw text, p_xml_content text, p_nome_file text, p_indirizzo_raw text, p_xml_hash text, p_payload_meta jsonb, p_anteprima_righe jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_ai_mensile(p_dal date) TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_consumi_mensili(p_dal date) TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_conteggio_fatture(p_user_ids uuid[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_fatture_per_mese(p_dal date) TO service_role;
GRANT EXECUTE ON FUNCTION public.articoli_da_fatture(p_user_id uuid, p_ristorante_id uuid, p_categorie_escluse text[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.assegna_fattura_a_sede(p_queue_id bigint, p_ristorante_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.assegna_fattura_a_sede_tecnica(p_queue_id bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.chat_top_categoria_fornitore(p_user_id uuid, p_ristorante_id uuid, p_giorni integer, p_top integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.chat_usage_check_and_log(p_user_id uuid, p_ristorante_id uuid, p_limite integer, p_pool boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_batch_for_processing(p_worker_id text, p_batch_size integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_ricavi_email_batch(p_worker_id text, p_batch_size integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.costi_automatici_mensili(p_user_id uuid, p_ristorante_id uuid, p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.costi_automatici_mensili_gruppo(p_user_id uuid, p_ristorante_ids uuid[], p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.crea_riparto_con_quote(p_user_id uuid, p_origine text, p_file_origine text, p_fornitore text, p_descrizione text, p_importo_totale numeric, p_tipo text, p_anno integer, p_mese integer, p_regola text, p_quote jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.dashboard_stats_aggregata(p_user_id uuid, p_ristorante_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_summary(p_days integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_timeseries(p_days integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_ai_recent_operations(p_days integer, p_limit integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_distinct_files(p_user_id uuid, p_ristorante_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_next_ordine_ricetta(p_user_id uuid, p_ristorante_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_peso_categoria(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_salute_componenti(p_ristorante_ids uuid[], p_inizio timestamp with time zone, p_anno integer, p_mese integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_spesa_pivot(p_ristorante_ids uuid[], p_dimensione text, p_data_da date, p_data_a date, p_escludi_da_verificare boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_spreco_fb_categorie(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_analisi(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_descrizioni(p_ristorante_ids uuid[], p_q text, p_limit integer, p_escludi_da_verificare boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_fornitori(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_trend(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date) TO service_role;
GRANT EXECUTE ON FUNCTION public.increment_ai_cost(p_ristorante_id uuid, p_cost numeric, p_tokens integer, p_operation_type text) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_queue_item_done(p_queue_id bigint, p_purge_xml boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.normalize_custom_tag_key(input_text text) TO service_role;
GRANT EXECUTE ON FUNCTION public.normalizza_indirizzo_match(p_raw text) TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_fatture_queue_last_error(p_retention_days integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_processed_xml_content(p_retention_hours integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_raw_body_sample(p_retention_days integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_ricavi_email_queue(p_retention_days integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_upload_events_retention(p_retention_days integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.release_stale_locks(p_timeout_minutes integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.resolve_unknown_tenant(p_piva text) TO service_role;
GRANT EXECUTE ON FUNCTION public.riparto_quote_mensili(p_user_id uuid, p_anno integer, p_mese integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.scadenziario_fatture_aggregate(p_user_id uuid, p_ristorante_ids uuid[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.scarta_fattura_da_coda(p_queue_id bigint, p_user_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.schedule_retry(p_queue_id bigint, p_error_msg text) TO service_role;
GRANT EXECUTE ON FUNCTION public._azzera_attribuzione_categoria() TO service_role;
GRANT EXECUTE ON FUNCTION public.aggiorna_categoria_fatture_attribuita(p_ids bigint[], p_categoria text, p_source text, p_extra jsonb, p_actor_email text, p_actor_user_id uuid, p_batch_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.aggiorna_categoria_prodotto_attribuita(p_user_id uuid, p_descrizione text, p_categoria text, p_source text, p_actor_email text, p_actor_user_id uuid, p_batch_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.soft_delete_fatture_massivo(p_user_id uuid, p_ristorante_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.sostituisci_quote_riparto(p_riparto_id uuid, p_user_id uuid, p_tipo text, p_regola text, p_importo_totale numeric, p_quote jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.sposta_fattura_a_sede(p_user_id uuid, p_file_origine text, p_ristorante_id uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.track_ai_usage_event(p_ristorante_id uuid, p_operation_type text, p_model text, p_prompt_tokens integer, p_completion_tokens integer, p_input_cost numeric, p_output_cost numeric, p_total_cost numeric, p_user_id uuid, p_source_file text, p_item_count integer, p_metadata jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.upsert_notification_inbox(p_notifications jsonb) TO service_role;
ALTER TABLE public.ai_review_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assistant_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_ambigui ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cache_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categorie ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.category_change_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_usage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.classificazioni_manuali ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tag_prodotti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tag_suggestion_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tag_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_briefing_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.diario_eventi ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dipendenti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_rate_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fatture ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fatture_documenti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fatture_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fornitori_pagamenti_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gruppo_assistant_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gruppo_segnali_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gruppo_tag_prodotti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gruppo_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingredienti_utente ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingredienti_workspace ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventario_voci ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.margini_mensili ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.marketplace_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memoria_ai_categorie ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.note_diario ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.piva_ristoranti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prezzi_preferiti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prodotti_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prodotti_utente ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.regole_turni_ricorrenti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_confirmed ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_ignored ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ricavi_email_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ricavi_email_sender_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ricavi_giornalieri ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ricavi_modalita_mensile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ricavi_ragione_sociale_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ricette ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.riparto_costi_catena ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.riparto_costi_catena_quote ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.riparto_regole_fornitore ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ristoranti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessioni ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spese_extra ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_maintenance_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.turni_personale ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.upload_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.upload_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
