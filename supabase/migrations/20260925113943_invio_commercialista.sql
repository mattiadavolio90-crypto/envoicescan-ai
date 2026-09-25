-- Invio automatico degli XML delle fatture passive al commercialista (fase B del
-- piano, 25/09/2026): la configurazione per P.IVA e il registro degli invii.
-- Nessun codice li usa ancora per spedire: l'esecutore arriva nella fase C.
--
-- CONFIGURAZIONE, una per P.IVA: su Invoicetronic una P.IVA e' di una sola azienda
-- in tutta la piattaforma. Si attiva solo con consenso datato E rilasciato per
-- quell'email, company_id trovato via API, email, data di partenza. Cambiare email
-- azzera consenso e attivazione. Cliente, P.IVA e company_id (una volta scritto)
-- non cambiano: si crea una configurazione nuova. Il DB rifiuta una configurazione
-- la cui P.IVA non e' di una sede del cliente, o e' anche di un altro account.
--
-- REGISTRO. Il DB garantisce cio' che nessun controllo in Python fra una lettura e
-- una scrittura puo' garantire:
--   - si spedisce solo per una configurazione attiva, non sospesa, al destinatario
--     che ha il consenso, con cliente/P.IVA/company_id copiati da lei: alla
--     creazione della riga, quando l'esecutore la prende e quando l'email parte
--     (la configurazione puo' cambiare fra un momento e l'altro);
--   - un solo invio in volo (o dall'esito incerto) per configurazione;
--   - un solo «primo» riuscito o in corso;
--   - periodi di primo/ordinario mai sovrapposti, e l'ordinario che riparte dal
--     giorno dopo l'ultimo inviato (trigger: btree_gist non c'e' nel Postgres dei
--     test, quindi niente EXCLUDE);
--   - un reinvio solo dentro cio' che e' gia' stato inviato (altrimenti il prossimo
--     ordinario rispedirebbe quei giorni);
--   - mai un periodo che arriva a oggi (le fatture di oggi non sono finite) ne' che
--     va oltre i 2 anni che Invoicetronic conserva;
--   - stati solo in avanti. Un invio la cui email e' partita (email_tentata_at,
--     scrivibile una volta sola) non torna mai «non partito»: ne' `bloccato` ne'
--     `errore`, salvo un rifiuto certo di Brevo (4xx) mentre e' in corso, o l'admin
--     che lo dichiara esplicitamente (chiarito_non_partito_at) chiarendo un esito
--     incerto. Un timeout e' `esito_incerto`, perche' rispedire il periodo la notte
--     dopo sarebbe un doppione al commercialista. `inviato` ed `esito_incerto`
--     esistono solo con l'email tentata (e quindi autorizzata);
--   - il registro non dimentica: nessuna riga si cancella (service_role non ha
--     DELETE; la pulizia e' SECURITY DEFINER, le cascate girano come proprietario)
--     e config_id diventa NULL solo quando la configurazione non c'e' piu'.
-- Ogni riga copia cliente, P.IVA, company_id e destinatario: resta la traccia di
-- cosa e' andato a chi anche dopo un cambio di configurazione, e anche dopo la sua
-- cancellazione (config_id diventa NULL, la riga resta fino alla retention). La
-- cancellazione dell'ACCOUNT invece porta via tutto, come promette la privacy.
--
-- Idempotente e rieseguibile per intero. service_role only: anon e authenticated
-- nominati nella REVOKE, perche' su Supabase hanno grant propri dalle default
-- privileges.

CREATE TABLE IF NOT EXISTS public.invio_commercialista_config (
    id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    piva                      text        NOT NULL,
    invoicetronic_company_id  integer,
    invoicetronic_nome        text,
    email_destinatario        text,
    frequenza                 text        NOT NULL DEFAULT 'mensile',
    data_partenza             date,
    attivo                    boolean     NOT NULL DEFAULT false,
    consenso_ricevuto         boolean     NOT NULL DEFAULT false,
    consenso_data             date,
    consenso_email            text,
    sospesa_at                timestamptz,
    sospesa_motivo            text,
    disattivata_at            timestamptz,
    creata_at                 timestamptz NOT NULL DEFAULT now(),
    aggiornata_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT icc_piva_chk CHECK (piva ~ '^[0-9]{11}$'),
    CONSTRAINT icc_frequenza_chk CHECK (frequenza IN ('settimanale', 'quindicinale', 'mensile')),
    CONSTRAINT icc_email_chk CHECK (
        email_destinatario IS NULL
        OR (email_destinatario = lower(btrim(email_destinatario))
            AND email_destinatario ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')
    ),
    CONSTRAINT icc_consenso_chk CHECK (
        NOT consenso_ricevuto OR (consenso_data IS NOT NULL AND consenso_email IS NOT NULL)
    ),
    CONSTRAINT icc_consenso_email_chk CHECK (
        consenso_email IS NULL OR consenso_email = lower(btrim(consenso_email))
    ),
    CONSTRAINT icc_attivabile_chk CHECK (
        NOT attivo OR (
            consenso_ricevuto
            AND consenso_email = email_destinatario
            AND invoicetronic_company_id IS NOT NULL
            AND email_destinatario IS NOT NULL
            AND data_partenza IS NOT NULL
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS icc_piva_unica ON public.invio_commercialista_config (piva);
CREATE UNIQUE INDEX IF NOT EXISTS icc_company_unica
    ON public.invio_commercialista_config (invoicetronic_company_id)
    WHERE invoicetronic_company_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.invio_commercialista_config_guardia()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
DECLARE
    v_account_altrui integer;
    v_sedi_proprie   integer;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.piva IS DISTINCT FROM OLD.piva THEN
            RAISE EXCEPTION 'cliente e P.IVA di una configurazione non cambiano: se ne crea una nuova'
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.invoicetronic_company_id IS NOT NULL
           AND NEW.invoicetronic_company_id IS DISTINCT FROM OLD.invoicetronic_company_id THEN
            RAISE EXCEPTION 'il company_id Invoicetronic, una volta trovato, non cambia'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.email_destinatario IS DISTINCT FROM OLD.email_destinatario THEN
            NEW.consenso_ricevuto := false;
            NEW.consenso_data := NULL;
            NEW.consenso_email := NULL;
            NEW.attivo := false;
        END IF;
        IF OLD.attivo AND NOT NEW.attivo AND NEW.disattivata_at IS NULL THEN
            NEW.disattivata_at := now();
        END IF;
        IF NEW.attivo THEN
            NEW.disattivata_at := NULL;
        END IF;
        NEW.aggiornata_at := now();
    END IF;

    -- La P.IVA deve essere di una sede del cliente e di nessun altro account, su
    -- ristoranti E su piva_ristoranti: il trigger che tiene piva_ristoranti non
    -- segue lo spostamento di una sede fra account. Solo alla creazione e per le
    -- configurazioni attive e non sospese: spegnerne o sospenderne una deve
    -- riuscire sempre, anche e soprattutto quando la P.IVA e' passata a un altro
    -- account (e' la guardia dell'esecutore a sospenderla, proprio per questo).
    -- Togliere la sospensione rifa' il controllo.
    IF TG_OP = 'UPDATE' AND (NOT NEW.attivo OR NEW.sospesa_at IS NOT NULL) THEN
        RETURN NEW;
    END IF;
    SELECT count(*) INTO v_sedi_proprie
    FROM public.ristoranti r
    WHERE r.partita_iva = NEW.piva AND r.user_id = NEW.user_id;
    SELECT count(*) INTO v_account_altrui
    FROM (
        SELECT r.user_id FROM public.ristoranti r WHERE r.partita_iva = NEW.piva
        UNION
        SELECT p.user_id FROM public.piva_ristoranti p WHERE p.piva = NEW.piva
    ) a
    WHERE a.user_id IS DISTINCT FROM NEW.user_id;
    IF v_sedi_proprie = 0 OR v_account_altrui > 0 THEN
        RAISE EXCEPTION 'la P.IVA non e'' di una sede del cliente, o e'' anche di un altro account'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS invio_commercialista_config_guardia ON public.invio_commercialista_config;
CREATE TRIGGER invio_commercialista_config_guardia
    BEFORE INSERT OR UPDATE ON public.invio_commercialista_config
    FOR EACH ROW EXECUTE FUNCTION public.invio_commercialista_config_guardia();

CREATE TABLE IF NOT EXISTS public.invio_commercialista_invii (
    id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id                 uuid        REFERENCES public.invio_commercialista_config(id) ON DELETE SET NULL,
    user_id                   uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    piva                      text        NOT NULL,
    invoicetronic_company_id  integer     NOT NULL,
    destinatario              text,
    tipo                      text        NOT NULL,
    periodo_dal               date        NOT NULL,
    periodo_al                date        NOT NULL,
    stato                     text        NOT NULL DEFAULT 'richiesto',
    richiesto_da              text        NOT NULL,
    n_file                    integer,
    byte_totali               bigint,
    documenti_ids             integer[],
    storage_paths             text[],
    link_scade_il             timestamptz,
    file_rimossi_at           timestamptz,
    email_tentata_at          timestamptz,
    brevo_http_status         integer,
    brevo_message_id          text,
    avviso_inviato_at         timestamptz,
    chiarito_non_partito_at   timestamptz,
    motivo                    text,
    creata_at                 timestamptz NOT NULL DEFAULT now(),
    iniziata_at               timestamptz,
    conclusa_at               timestamptz,
    CONSTRAINT ici_tipo_chk CHECK (tipo IN ('primo', 'ordinario', 'reinvio', 'prova')),
    CONSTRAINT ici_stato_chk CHECK (
        stato IN ('richiesto', 'in_corso', 'inviato', 'errore', 'bloccato', 'prova_ok', 'esito_incerto')
    ),
    CONSTRAINT ici_richiesto_da_chk CHECK (richiesto_da IN ('notturno', 'admin')),
    CONSTRAINT ici_notturno_solo_ordinario_chk CHECK (richiesto_da <> 'notturno' OR tipo = 'ordinario'),
    CONSTRAINT ici_prova_mai_inviata_chk CHECK (tipo <> 'prova' OR stato NOT IN ('inviato', 'esito_incerto')),
    CONSTRAINT ici_prova_ok_solo_prova_chk CHECK (stato <> 'prova_ok' OR tipo = 'prova'),
    CONSTRAINT ici_periodo_chk CHECK (periodo_al >= periodo_dal),
    CONSTRAINT ici_mai_oggi_chk CHECK (periodo_al < timezone('Europe/Rome', creata_at)::date),
    CONSTRAINT ici_due_anni_chk CHECK (
        periodo_dal >= (timezone('Europe/Rome', creata_at)::date - interval '2 years')::date
    ),
    CONSTRAINT ici_email_partita_chk CHECK (
        email_tentata_at IS NULL
        OR stato IN ('in_corso', 'inviato', 'esito_incerto')
        OR (stato = 'errore' AND (coalesce(brevo_http_status BETWEEN 400 AND 499, false)
                                  OR chiarito_non_partito_at IS NOT NULL))
    ),
    CONSTRAINT ici_prova_senza_email_chk CHECK (tipo <> 'prova' OR email_tentata_at IS NULL),
    CONSTRAINT ici_spedito_con_email_chk CHECK (
        tipo = 'prova' OR stato NOT IN ('inviato', 'esito_incerto') OR email_tentata_at IS NOT NULL
    ),
    CONSTRAINT ici_chiarito_chk CHECK (
        chiarito_non_partito_at IS NULL OR (stato = 'errore' AND email_tentata_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ici_uno_in_volo
    ON public.invio_commercialista_invii (config_id)
    WHERE stato IN ('richiesto', 'in_corso', 'esito_incerto');
CREATE UNIQUE INDEX IF NOT EXISTS ici_un_solo_primo
    ON public.invio_commercialista_invii (config_id)
    WHERE tipo = 'primo' AND stato IN ('richiesto', 'in_corso', 'inviato', 'esito_incerto');
CREATE UNIQUE INDEX IF NOT EXISTS ici_inizio_unico
    ON public.invio_commercialista_invii (config_id, periodo_dal)
    WHERE tipo IN ('primo', 'ordinario') AND stato IN ('richiesto', 'in_corso', 'inviato', 'esito_incerto');
CREATE INDEX IF NOT EXISTS ici_per_config ON public.invio_commercialista_invii (config_id, creata_at DESC);
CREATE INDEX IF NOT EXISTS ici_file_da_rimuovere
    ON public.invio_commercialista_invii (link_scade_il)
    WHERE storage_paths IS NOT NULL AND file_rimossi_at IS NULL;

-- L'ultimo giorno gia' consegnato al commercialista: il cursore del pianificatore.
-- Solo primo e ordinario riusciti (o dall'esito incerto, che conta come consegnato
-- finche' non lo si chiarisce): ne' i reinvii ne' le prove lo spostano.
CREATE OR REPLACE FUNCTION public.invio_commercialista_ultimo_giorno(p_config_id uuid)
RETURNS date
LANGUAGE sql
STABLE
SET search_path TO 'public'
AS $function$
    SELECT max(periodo_al)
    FROM public.invio_commercialista_invii
    WHERE config_id = p_config_id
      AND tipo IN ('primo', 'ordinario')
      AND stato IN ('inviato', 'esito_incerto');
$function$;

-- Si puo' spedire a questo destinatario per questa configurazione, adesso?
-- `attivo` porta con se' il consenso rilasciato per quell'email
-- (icc_attivabile_chk): basta che il destinatario sia l'email della configurazione.
CREATE OR REPLACE FUNCTION public.invio_commercialista_autorizzato(p_config_id uuid, p_destinatario text)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO 'public'
AS $function$
    SELECT coalesce((
        SELECT c.attivo AND c.sospesa_at IS NULL AND c.email_destinatario = p_destinatario
        FROM public.invio_commercialista_config c
        WHERE c.id = p_config_id
    ), false);
$function$;

CREATE OR REPLACE FUNCTION public.invio_commercialista_invii_guardia()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
DECLARE
    v_cfg     public.invio_commercialista_config%ROWTYPE;
    v_ultimo  date;
    v_primo   date;
    v_limite  date;
    v_attesa  date;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- config_id puo' solo diventare NULL, e solo quando la configurazione non
        -- c'e' piu' (ON DELETE SET NULL: durante la cascata la riga e' gia'
        -- invisibile). A mano, con la configurazione viva, la riga uscirebbe dal
        -- cursore e il suo periodo si potrebbe rispedire.
        IF (NEW.config_id IS DISTINCT FROM OLD.config_id
            AND (NEW.config_id IS NOT NULL
                 OR EXISTS (SELECT 1 FROM public.invio_commercialista_config c WHERE c.id = OLD.config_id)))
           OR NEW.tipo IS DISTINCT FROM OLD.tipo
           OR NEW.periodo_dal IS DISTINCT FROM OLD.periodo_dal
           OR NEW.periodo_al IS DISTINCT FROM OLD.periodo_al
           OR NEW.user_id IS DISTINCT FROM OLD.user_id
           OR NEW.piva IS DISTINCT FROM OLD.piva
           OR NEW.invoicetronic_company_id IS DISTINCT FROM OLD.invoicetronic_company_id
           OR (NEW.destinatario IS DISTINCT FROM OLD.destinatario AND NEW.destinatario IS NOT NULL)
           OR NEW.richiesto_da IS DISTINCT FROM OLD.richiesto_da
           OR NEW.creata_at IS DISTINCT FROM OLD.creata_at THEN
            RAISE EXCEPTION 'un invio registrato non cambia periodo, tipo ne'' destinatario'
                USING ERRCODE = 'check_violation';
        END IF;
        -- Cio' che dice se e come l'email e' partita si scrive una volta sola.
        IF (OLD.email_tentata_at IS NOT NULL AND NEW.email_tentata_at IS DISTINCT FROM OLD.email_tentata_at)
           OR (OLD.brevo_http_status IS NOT NULL AND NEW.brevo_http_status IS DISTINCT FROM OLD.brevo_http_status)
           OR (OLD.brevo_message_id IS NOT NULL AND NEW.brevo_message_id IS DISTINCT FROM OLD.brevo_message_id)
           OR (OLD.chiarito_non_partito_at IS NOT NULL
               AND NEW.chiarito_non_partito_at IS DISTINCT FROM OLD.chiarito_non_partito_at) THEN
            RAISE EXCEPTION 'l''esito dell''email di un invio si scrive una volta sola'
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.chiarito_non_partito_at IS NULL AND NEW.chiarito_non_partito_at IS NOT NULL
           AND NOT (OLD.stato = 'esito_incerto' AND NEW.stato = 'errore') THEN
            RAISE EXCEPTION 'solo un esito incerto si chiarisce come non partito'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.stato IS DISTINCT FROM OLD.stato AND NOT (
               (OLD.stato = 'richiesto' AND NEW.stato IN ('in_corso', 'errore'))
            OR (OLD.stato = 'in_corso' AND NEW.stato IN ('inviato', 'errore', 'bloccato', 'prova_ok', 'esito_incerto'))
            OR (OLD.stato = 'esito_incerto' AND (NEW.stato = 'inviato'
                OR (NEW.stato = 'errore' AND NEW.chiarito_non_partito_at IS NOT NULL)))
        ) THEN
            RAISE EXCEPTION 'transizione di stato non ammessa: % -> %', OLD.stato, NEW.stato
                USING ERRCODE = 'check_violation';
        END IF;
        -- L'esecutore prende la riga, poi l'email parte: la configurazione puo'
        -- essere stata spenta o cambiata nel frattempo.
        IF NEW.tipo <> 'prova' AND (
               (OLD.stato = 'richiesto' AND NEW.stato = 'in_corso')
            OR (OLD.email_tentata_at IS NULL AND NEW.email_tentata_at IS NOT NULL)
        ) AND NOT public.invio_commercialista_autorizzato(NEW.config_id, NEW.destinatario) THEN
            RAISE EXCEPTION 'configurazione spenta, sospesa o destinatario senza consenso'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    -- INSERT. Il lock sulla configurazione serializza gli inserimenti della stessa
    -- configurazione (per quelli in volo lo fa gia' ici_uno_in_volo).
    IF NEW.creata_at > now() + interval '5 minutes' THEN
        RAISE EXCEPTION 'creata_at nel futuro: i limiti sulle date si calcolano da li'''
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO v_cfg FROM public.invio_commercialista_config WHERE id = NEW.config_id FOR UPDATE;
    IF NOT FOUND
       OR NEW.user_id IS DISTINCT FROM v_cfg.user_id
       OR NEW.piva IS DISTINCT FROM v_cfg.piva
       OR NEW.invoicetronic_company_id IS DISTINCT FROM v_cfg.invoicetronic_company_id THEN
        RAISE EXCEPTION 'l''invio copia cliente, P.IVA e company_id della sua configurazione'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.tipo <> 'prova' AND NOT public.invio_commercialista_autorizzato(NEW.config_id, NEW.destinatario) THEN
        RAISE EXCEPTION 'configurazione spenta, sospesa o destinatario senza consenso'
            USING ERRCODE = 'check_violation';
    END IF;
    v_ultimo := public.invio_commercialista_ultimo_giorno(NEW.config_id);
    v_limite := (timezone('Europe/Rome', NEW.creata_at)::date - interval '2 years')::date;

    IF NEW.tipo IN ('primo', 'ordinario') AND EXISTS (
        SELECT 1 FROM public.invio_commercialista_invii i
        WHERE i.config_id = NEW.config_id
          AND i.tipo IN ('primo', 'ordinario')
          AND i.stato IN ('richiesto', 'in_corso', 'inviato', 'esito_incerto')
          AND daterange(i.periodo_dal, i.periodo_al, '[]') && daterange(NEW.periodo_dal, NEW.periodo_al, '[]')
    ) THEN
        RAISE EXCEPTION 'periodo sovrapposto a un invio gia'' preso'
            USING ERRCODE = 'exclusion_violation';
    END IF;

    IF NEW.tipo = 'ordinario' THEN
        IF v_ultimo IS NULL THEN
            RAISE EXCEPTION 'l''ordinario viene dopo un primo invio riuscito'
                USING ERRCODE = 'check_violation';
        END IF;
        v_attesa := GREATEST(v_ultimo + 1, v_limite);
        IF NEW.periodo_dal <> v_attesa THEN
            RAISE EXCEPTION 'l''ordinario riparte dal giorno dopo l''ultimo inviato (%), non dal %', v_attesa, NEW.periodo_dal
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.tipo = 'reinvio' THEN
        SELECT min(periodo_dal) INTO v_primo
        FROM public.invio_commercialista_invii
        WHERE config_id = NEW.config_id
          AND tipo IN ('primo', 'ordinario')
          AND stato IN ('inviato', 'esito_incerto');
        IF v_ultimo IS NULL OR NEW.periodo_al > v_ultimo OR NEW.periodo_dal < v_primo THEN
            RAISE EXCEPTION 'si reinvia solo cio'' che e'' gia'' stato inviato'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS invio_commercialista_invii_guardia ON public.invio_commercialista_invii;
CREATE TRIGGER invio_commercialista_invii_guardia
    BEFORE INSERT OR UPDATE ON public.invio_commercialista_invii
    FOR EACH ROW EXECUTE FUNCTION public.invio_commercialista_invii_guardia();

-- Retention (GDPR): l'email del destinatario non resta oltre il bisogno.
--   - registro: dopo p_retention_days il destinatario si cancella (resta il resto,
--     che non e' un dato personale), e le righe rimaste senza configurazione
--     (cliente o configurazione cancellati) spariscono del tutto;
--   - configurazione spenta da piu' di p_giorni_config (o mai accesa e ferma da
--     altrettanto): email e consenso via.
CREATE OR REPLACE FUNCTION public.purge_invio_commercialista(
    p_retention_days integer DEFAULT 365,
    p_giorni_config integer DEFAULT 90
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_orfani   integer;
    v_registro integer;
    v_config   integer;
BEGIN
    IF p_retention_days < 30 OR p_giorni_config < 30 THEN
        RAISE EXCEPTION 'p_retention_days e p_giorni_config almeno 30: il link di un invio vale 30 giorni';
    END IF;
    DELETE FROM public.invio_commercialista_invii
    WHERE config_id IS NULL
      AND creata_at < now() - make_interval(days => p_retention_days);
    GET DIAGNOSTICS v_orfani = ROW_COUNT;

    UPDATE public.invio_commercialista_invii
    SET destinatario = NULL
    WHERE destinatario IS NOT NULL
      AND creata_at < now() - make_interval(days => p_retention_days);
    GET DIAGNOSTICS v_registro = ROW_COUNT;

    UPDATE public.invio_commercialista_config
    SET email_destinatario = NULL, consenso_ricevuto = false, consenso_data = NULL, consenso_email = NULL
    WHERE NOT attivo
      AND coalesce(disattivata_at, aggiornata_at) < now() - make_interval(days => p_giorni_config)
      AND (email_destinatario IS NOT NULL OR consenso_email IS NOT NULL);
    GET DIAGNOSTICS v_config = ROW_COUNT;
    RETURN v_orfani + v_registro + v_config;
END;
$function$;

ALTER TABLE public.invio_commercialista_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invio_commercialista_invii ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.invio_commercialista_config FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.invio_commercialista_invii FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.invio_commercialista_config TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.invio_commercialista_invii TO service_role;
-- Esplicita: su Supabase le default privileges danno ALL a service_role.
REVOKE DELETE, TRUNCATE ON public.invio_commercialista_invii FROM service_role;
REVOKE ALL ON FUNCTION public.invio_commercialista_ultimo_giorno(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.invio_commercialista_autorizzato(uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.purge_invio_commercialista(integer, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.invio_commercialista_config_guardia() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.invio_commercialista_invii_guardia() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.invio_commercialista_ultimo_giorno(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.invio_commercialista_autorizzato(uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_invio_commercialista(integer, integer) TO service_role;

-- Bucket privato degli ZIP. Lo schema storage non c'e' nel Postgres dei test: li'
-- il blocco non fa niente, e lo dice. Se il bucket esiste gia' (creato a mano) lo
-- si riporta privato: un bucket pubblico renderebbe inutili i link firmati.
DO $bucket$
BEGIN
    IF to_regclass('storage.buckets') IS NULL THEN
        RAISE NOTICE 'schema storage assente: bucket invii-commercialista non creato';
        RETURN;
    END IF;
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    VALUES ('invii-commercialista', 'invii-commercialista', false, 52428800, ARRAY['application/zip'])
    ON CONFLICT (id) DO UPDATE
        SET public = false,
            file_size_limit = EXCLUDED.file_size_limit,
            allowed_mime_types = EXCLUDED.allowed_mime_types;
END;
$bucket$;

COMMENT ON TABLE public.invio_commercialista_config IS
    'Invio automatico degli XML al commercialista: una configurazione per P.IVA. Si attiva '
    'solo col consenso rilasciato per quell''email. service_role only.';
COMMENT ON TABLE public.invio_commercialista_invii IS
    'Registro degli invii al commercialista. Il DB impedisce doppioni: un invio in volo per '
    'configurazione, periodi mai sovrapposti, stati solo in avanti. service_role only.';
