-- Trigger "rientro assenza": serve sapere da quanti giorni un utente non vedeva
-- un briefing, per aprire con un bentornato (e, se l'app e' incompleta, offrire
-- soft l'Assistenza Continuativa).
--
-- Perche' una colonna nuova e non last_seen_at / last_login: quelli vengono
-- aggiornati ad "adesso" gia' al login, PRIMA che il briefing giri, quindi al
-- momento del calcolo l'assenza risulterebbe sempre 0. last_briefing_seen e'
-- letto e poi aggiornato dal briefing stesso: "ultima volta che ho mostrato un
-- briefing a questo utente". Deterministico e indipendente dai timestamp di auth.
--
-- NULL = nessun briefing mai mostrato (utente nuovo o pre-feature): trattato
-- come "non in rientro" dal codice, cosi' la feature non sbotta al primo deploy.

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS last_briefing_seen timestamptz;

COMMENT ON COLUMN public.users.last_briefing_seen IS
  'Ultima volta che il briefing Home e'' stato mostrato a questo utente. Usato dal trigger rientro_assenza per calcolare i giorni di assenza in modo indipendente da last_seen_at/last_login (gia'' aggiornati al login).';
