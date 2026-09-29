-- Sotto-utenti: piu' credenziali di accesso sopra lo STESSO account.
--
-- Il tenant non cambia. I dati restano del titolare (users.id); un sotto-utente
-- e' solo uno strato di autenticazione e di restrizione (pagine, sedi) sopra di
-- lui, e non diventa mai proprietario di dati. Per questo sta in una tabella
-- propria e NON in `users`: job, email e liste admin leggono `users` e non lo
-- vedono per costruzione.
--
-- Le sessioni restano intestate al titolare (sessioni.user_id): tutti i filtri
-- multi-tenant esistenti continuano a funzionare identici. `sotto_utente_id`
-- dice CHI sta agendo — e' l'aggancio per un futuro audit trail.
--
-- Additiva: nessuna colonna esistente cambia significato. Senza righe in
-- sotto_utenti il comportamento dell'app e' quello di prima.

CREATE TABLE IF NOT EXISTS public.sotto_utenti (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    titolare_id           uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    email                 text        NOT NULL,
    password_hash         text        NOT NULL,
    nome                  text,
    attivo                boolean     NOT NULL DEFAULT true,
    -- Chiavi esplicite, assente = spenta: il default e' il privilegio minimo.
    pagine                jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ultimo_ristorante_id  uuid        REFERENCES public.ristoranti(id) ON DELETE SET NULL,
    -- Preferenze personali: sulla riga del titolare due persone si
    -- sovrascriverebbero a vicenda.
    tema                  text        NOT NULL DEFAULT 'dark',
    vista_fatture         text        NOT NULL DEFAULT 'agenda',
    last_briefing_seen    timestamptz,
    privacy_accepted_at   timestamptz,
    -- Attivazione via email (stessa meccanica di users.reset_code).
    reset_code            text,
    reset_expires         timestamptz,
    password_changed_at   timestamptz,
    last_login            timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sotto_utenti_email_normalizzata_chk
        CHECK (email = lower(btrim(email)) AND email <> ''),
    CONSTRAINT sotto_utenti_pagine_oggetto_chk
        CHECK (jsonb_typeof(pagine) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS sotto_utenti_email_key
    ON public.sotto_utenti (lower(email));
CREATE INDEX IF NOT EXISTS idx_sotto_utenti_titolare
    ON public.sotto_utenti (titolare_id);

CREATE TABLE IF NOT EXISTS public.sotto_utenti_sedi (
    sotto_utente_id  uuid NOT NULL REFERENCES public.sotto_utenti(id) ON DELETE CASCADE,
    ristorante_id    uuid NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    PRIMARY KEY (sotto_utente_id, ristorante_id)
);
CREATE INDEX IF NOT EXISTS idx_sotto_utenti_sedi_ristorante
    ON public.sotto_utenti_sedi (ristorante_id);

-- Una sede si assegna solo se e' dell'account del titolare. Il codice lo
-- ricontrolla a ogni richiesta (una sede puo' cambiare account dopo), questo e'
-- il freno all'ingresso.
CREATE OR REPLACE FUNCTION public.sotto_utenti_sedi_guardia()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.sotto_utenti s
          JOIN public.ristoranti r ON r.user_id = s.titolare_id
         WHERE s.id = NEW.sotto_utente_id
           AND r.id = NEW.ristorante_id
    ) THEN
        RAISE EXCEPTION 'sede % non appartiene al titolare del sotto-utente %',
            NEW.ristorante_id, NEW.sotto_utente_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS sotto_utenti_sedi_guardia ON public.sotto_utenti_sedi;
CREATE TRIGGER sotto_utenti_sedi_guardia
    BEFORE INSERT OR UPDATE ON public.sotto_utenti_sedi
    FOR EACH ROW EXECUTE FUNCTION public.sotto_utenti_sedi_guardia();

-- Il titolare di un sotto-utente non cambia: spostarlo porterebbe con se' le
-- sedi assegnate di un altro account.
CREATE OR REPLACE FUNCTION public.sotto_utenti_titolare_immutabile()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
BEGIN
    IF NEW.titolare_id IS DISTINCT FROM OLD.titolare_id THEN
        RAISE EXCEPTION 'il titolare di un sotto-utente non si cambia'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS sotto_utenti_titolare_immutabile ON public.sotto_utenti;
CREATE TRIGGER sotto_utenti_titolare_immutabile
    BEFORE UPDATE OF titolare_id ON public.sotto_utenti
    FOR EACH ROW EXECUTE FUNCTION public.sotto_utenti_titolare_immutabile();

-- Email unica fra titolari E sotto-utenti: il login cerca in entrambe le
-- tabelle, e due righe con la stessa email renderebbero ambiguo chi entra.
-- users.email ha gia' il suo UNIQUE; qui si chiude l'incrocio, nei due versi.
CREATE OR REPLACE FUNCTION public.sotto_utenti_email_non_di_un_titolare()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
BEGIN
    IF EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(NEW.email)) THEN
        RAISE EXCEPTION 'email % gia'' usata da un account', NEW.email
            USING ERRCODE = 'unique_violation';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS sotto_utenti_email_unica ON public.sotto_utenti;
CREATE TRIGGER sotto_utenti_email_unica
    BEFORE INSERT OR UPDATE OF email ON public.sotto_utenti
    FOR EACH ROW EXECUTE FUNCTION public.sotto_utenti_email_non_di_un_titolare();

CREATE OR REPLACE FUNCTION public.users_email_non_di_un_sotto_utente()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
BEGIN
    IF EXISTS (SELECT 1 FROM public.sotto_utenti s WHERE lower(s.email) = lower(NEW.email)) THEN
        RAISE EXCEPTION 'email % gia'' usata da un sotto-utente', NEW.email
            USING ERRCODE = 'unique_violation';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS users_email_non_di_un_sotto_utente ON public.users;
CREATE TRIGGER users_email_non_di_un_sotto_utente
    BEFORE INSERT OR UPDATE OF email ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.users_email_non_di_un_sotto_utente();

-- Chi sta agendo in una sessione. NULL = il titolare (tutte le sessioni di oggi).
ALTER TABLE public.sessioni
    ADD COLUMN IF NOT EXISTS sotto_utente_id uuid
    REFERENCES public.sotto_utenti(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_sessioni_sotto_utente_active
    ON public.sessioni (sotto_utente_id) WHERE revoked_at IS NULL AND sotto_utente_id IS NOT NULL;

-- La sessione di un sotto-utente e' intestata al SUO titolare, mai a un altro.
CREATE OR REPLACE FUNCTION public.sessioni_sotto_utente_del_titolare()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
BEGIN
    IF NEW.sotto_utente_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.sotto_utenti s
         WHERE s.id = NEW.sotto_utente_id AND s.titolare_id = NEW.user_id
    ) THEN
        RAISE EXCEPTION 'sessione di un sotto-utente intestata a un account non suo'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS sessioni_sotto_utente_del_titolare ON public.sessioni;
CREATE TRIGGER sessioni_sotto_utente_del_titolare
    BEFORE INSERT OR UPDATE OF user_id, sotto_utente_id ON public.sessioni
    FOR EACH ROW EXECUTE FUNCTION public.sessioni_sotto_utente_del_titolare();

-- Solo il worker (service_role). anon/authenticated vanno nominati: su Supabase
-- hanno grant propri dalle default privileges, REVOKE FROM PUBLIC non basta.
ALTER TABLE public.sotto_utenti ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sotto_utenti_sedi ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sotto_utenti FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.sotto_utenti_sedi FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sotto_utenti TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sotto_utenti_sedi TO service_role;
REVOKE ALL ON FUNCTION public.sotto_utenti_sedi_guardia() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.sotto_utenti_titolare_immutabile() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.sotto_utenti_email_non_di_un_titolare() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.users_email_non_di_un_sotto_utente() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.sessioni_sotto_utente_del_titolare() FROM PUBLIC, anon, authenticated;
