-- Vista preferita di Gestione Fatture, per utente.
--
-- La pagina ha due viste storiche ("agenda" = Lista per fascia di scadenza,
-- "calendario") e ne aggiunge una terza, "lista_mensile": elenco cronologico per
-- mese della data fattura, senza scadenze. Chi non gestisce i pagamenti da qui la
-- vuole come default e non la vuole ri-scegliere a ogni accesso.
--
-- Stessa forma di `users.tema` (text NOT NULL DEFAULT + CHECK, non un enum): la
-- preferenza segue l'account, viaggia nel payload di sessione e non in
-- localStorage, che e' per-browser e si perde.
--
-- Il default 'agenda' e non 'lista_mensile': chi non sceglie niente deve trovare
-- la pagina esattamente com'era prima.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS vista_fatture text NOT NULL DEFAULT 'agenda';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_vista_fatture_chk'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_vista_fatture_chk
            CHECK (vista_fatture = ANY (ARRAY['agenda'::text, 'calendario'::text, 'lista_mensile'::text]));
    END IF;
END $$;
