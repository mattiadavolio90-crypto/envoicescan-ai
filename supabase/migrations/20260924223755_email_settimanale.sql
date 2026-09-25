-- Email settimanale dell'assistente (fase 7 del piano consulente): preferenza
-- del cliente e registro degli invii.
--
-- PREFERENZA. `users.email_settimanale`, default TRUE: decisione di Mattia
-- (24/09/2026) — parte a tutti i clienti attivi, con la disiscrizione in ogni
-- email e l'interruttore nelle Impostazioni. Stessa forma di `users.tema`: la
-- preferenza segue l'account, non il browser.
--
-- REGISTRO. Una riga per (utente, settimana), UNIQUE: e' la garanzia che nessuno
-- riceva due email nella stessa settimana, anche se il cron riparte, gira due
-- volte (lo fa di proposito: 05:30 e 06:30 UTC, per il cambio d'ora) o un
-- operatore lo lancia a mano. Chi invia prima INSERISCE la riga e solo se
-- l'insert riesce spedisce: il vincolo decide, non un controllo in Python fra
-- una lettura e una scrittura.
--   stato: 'in_corso' (riga presa, invio non ancora concluso), 'inviata',
--          'saltata' (niente da dire, invio spento, prova), 'errore'.
--   settimana: il LUNEDI' della settimana dell'invio (data di Roma).
--
-- Idempotente. service_role only: anon/authenticated nominati nella REVOKE,
-- perche' su Supabase hanno grant propri dalle default privileges.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS email_settimanale boolean NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS public.email_settimanale_invii (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    settimana   date        NOT NULL,
    stato       text        NOT NULL,
    motivo      text,
    creata_at   timestamptz NOT NULL DEFAULT now(),
    aggiornata_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT email_settimanale_invii_stato_chk
        CHECK (stato = ANY (ARRAY['in_corso'::text, 'inviata'::text, 'saltata'::text, 'errore'::text])),
    CONSTRAINT email_settimanale_invii_lunedi_chk
        CHECK (EXTRACT(ISODOW FROM settimana) = 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_settimanale_invii_unico
    ON public.email_settimanale_invii (user_id, settimana);

ALTER TABLE public.email_settimanale_invii ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.email_settimanale_invii TO service_role;
REVOKE ALL ON public.email_settimanale_invii FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.email_settimanale_invii IS
    'Una riga per (utente, lunedi''): chi la inserisce spedisce. UNIQUE = mai due '
    'email nella stessa settimana. service_role only.';
COMMENT ON COLUMN public.users.email_settimanale IS
    'Il cliente riceve l''email settimanale dell''assistente. Default true (decisione '
    'del 24/09/2026), si spegne dal link nell''email o dalle Impostazioni.';
