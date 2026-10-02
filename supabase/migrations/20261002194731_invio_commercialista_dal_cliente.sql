-- Invio al commercialista: lo attiva il CLIENTE dalle sue Impostazioni (02/10/2026).
--
-- Prima lo configurava l'admin, con un consenso firmato su carta registrato a
-- mano e il primo invio lanciato a mano. Ora l'attivazione del cliente (email,
-- frequenza, casella «Autorizzo») E' il consenso, e il primo invio parte da solo.
--
-- CONFIGURAZIONE. Il consenso porta con se' la prova: quando (consenso_at), chi
-- l'ha dato (consenso_da, l'email dell'account) e il testo esatto autorizzato
-- (consenso_testo). Cambiare email li azzera come gia' azzerava il resto; e
-- cosi' anche la pulizia GDPR (purge_invio_commercialista), che cancella l'email
-- delle configurazioni spente da 90 giorni e fa scattare lo stesso trigger.
--
-- REGISTRO.
--   - il pianificatore notturno crea anche il `primo`;
--   - la data di partenza fa da pavimento per primo E ordinario: il primo parte
--     esattamente da GREATEST(data_partenza, limite 2 anni); l'ordinario da
--     GREATEST(ultimo inviato + 1, limite, data_partenza). Cosi' un cliente che
--     riattiva «solo le fatture nuove» non riceve il buco di quando era spento,
--     e uno che le chiede tutte riparte da dove si era fermato, senza doppioni;
--   - il primo parte dopo l'ultimo giorno gia' spedito da una configurazione
--     cancellata della stessa P.IVA (prima lo controllava solo il router admin).
--
-- Idempotente. Nessuna funzione cambia firma.

ALTER TABLE public.invio_commercialista_config
    ADD COLUMN IF NOT EXISTS consenso_at    timestamptz,
    ADD COLUMN IF NOT EXISTS consenso_da    text,
    ADD COLUMN IF NOT EXISTS consenso_testo text;

ALTER TABLE public.invio_commercialista_config DROP CONSTRAINT IF EXISTS icc_consenso_chk;
ALTER TABLE public.invio_commercialista_config ADD CONSTRAINT icc_consenso_chk CHECK (
    NOT consenso_ricevuto OR (
        consenso_data IS NOT NULL
        AND consenso_email IS NOT NULL
        AND consenso_at IS NOT NULL
        AND nullif(btrim(consenso_da), '') IS NOT NULL
        AND nullif(btrim(consenso_testo), '') IS NOT NULL
    )
);

ALTER TABLE public.invio_commercialista_invii DROP CONSTRAINT IF EXISTS ici_notturno_solo_ordinario_chk;
ALTER TABLE public.invio_commercialista_invii DROP CONSTRAINT IF EXISTS ici_notturno_chk;
ALTER TABLE public.invio_commercialista_invii ADD CONSTRAINT ici_notturno_chk CHECK (
    richiesto_da <> 'notturno' OR tipo IN ('primo', 'ordinario')
);

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
            NEW.consenso_at := NULL;
            NEW.consenso_da := NULL;
            NEW.consenso_testo := NULL;
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
    v_orfano  date;
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
        -- Ultima linea sotto la guardia dell'esecutore (che sospende): quando l'email
        -- parte, la P.IVA e' di una sede del cliente e di nessun altro account.
        IF NEW.tipo <> 'prova' AND OLD.email_tentata_at IS NULL AND NEW.email_tentata_at IS NOT NULL AND (
               NOT EXISTS (SELECT 1 FROM public.ristoranti r
                           WHERE r.partita_iva = NEW.piva AND r.user_id = NEW.user_id)
            OR EXISTS (SELECT 1 FROM public.ristoranti r
                       WHERE r.partita_iva = NEW.piva AND r.user_id IS DISTINCT FROM NEW.user_id)
            OR EXISTS (SELECT 1 FROM public.piva_ristoranti p
                       WHERE p.piva = NEW.piva AND p.user_id IS DISTINCT FROM NEW.user_id)
        ) THEN
            RAISE EXCEPTION 'la P.IVA non e'' piu'' solo del cliente'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    -- INSERT. Il lock sulla configurazione serializza gli inserimenti della stessa
    -- configurazione (per quelli in volo lo fa gia' ici_uno_in_volo). Un invio
    -- nasce richiesto e senza esiti (email_tentata_at la esclude gia'
    -- ici_email_partita_chk su uno stato `richiesto`).
    IF NEW.stato <> 'richiesto'
       OR NEW.iniziata_at IS NOT NULL OR NEW.conclusa_at IS NOT NULL
       OR NEW.brevo_http_status IS NOT NULL
       OR NEW.brevo_message_id IS NOT NULL OR NEW.chiarito_non_partito_at IS NOT NULL
       OR NEW.storage_paths IS NOT NULL OR NEW.file_rimossi_at IS NOT NULL
       OR NEW.documenti_ids IS NOT NULL OR NEW.documenti_visti IS NOT NULL
       OR NEW.avviso_inviato_at IS NOT NULL THEN
        RAISE EXCEPTION 'un invio nasce richiesto e senza esiti: li scrive chi lo esegue'
            USING ERRCODE = 'check_violation';
    END IF;
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

    -- Un secondo primo dopo uno riuscito lo ferma gia' ici_un_solo_primo: finche'
    -- c'e' un ordinario, il primo resta per forza inviato (un esito incerto blocca
    -- ogni altro invio finche' non lo si chiarisce).
    IF NEW.tipo = 'primo' THEN
        IF v_cfg.data_partenza IS NULL THEN
            RAISE EXCEPTION 'il primo invio parte dalla data di partenza, che manca'
                USING ERRCODE = 'check_violation';
        END IF;
        v_attesa := GREATEST(v_cfg.data_partenza, v_limite);
        IF NEW.periodo_dal <> v_attesa THEN
            RAISE EXCEPTION 'il primo invio parte dalla data di partenza (%), non dal %', v_attesa, NEW.periodo_dal
                USING ERRCODE = 'check_violation';
        END IF;
        -- Una configurazione cancellata della stessa P.IVA puo' aver gia' spedito:
        -- la nuova riparte dopo, o il commercialista riceve due volte gli stessi file.
        SELECT max(i.periodo_al) INTO v_orfano
        FROM public.invio_commercialista_invii i
        WHERE i.config_id IS NULL AND i.piva = NEW.piva
          AND i.tipo IN ('primo', 'ordinario')
          AND i.stato IN ('inviato', 'esito_incerto');
        IF v_orfano IS NOT NULL AND NEW.periodo_dal <= v_orfano THEN
            RAISE EXCEPTION 'una configurazione cancellata ha gia'' inviato fino al %: il primo invio parte dopo', v_orfano
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.tipo = 'ordinario' THEN
        IF v_ultimo IS NULL THEN
            RAISE EXCEPTION 'l''ordinario viene dopo un primo invio riuscito'
                USING ERRCODE = 'check_violation';
        END IF;
        v_attesa := GREATEST(v_ultimo + 1, v_limite, v_cfg.data_partenza);
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

-- CREATE OR REPLACE conserva i grant, ma una funzione ricreata da zero (DB dei
-- test, o dopo un DROP) li riprende dalle default privileges: si ridichiarano.
REVOKE ALL ON FUNCTION public.invio_commercialista_config_guardia() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.invio_commercialista_invii_guardia() FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.invio_commercialista_config IS
    'Invio automatico degli XML al commercialista: una configurazione per P.IVA. La attiva il '
    'cliente dalle Impostazioni: l''attivazione e'' il consenso (quando, chi, testo). service_role only.';
