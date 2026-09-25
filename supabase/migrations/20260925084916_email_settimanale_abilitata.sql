-- Email settimanale: la abilita l'admin, cliente per cliente (Mattia, 25/09/2026).
--
-- La 7a l'aveva pensata per tutti i clienti attivi (preferenza default accesa).
-- Mattia, alla 7c: «non e' per tutti, e probabilmente per nessuno degli attuali
-- clienti» — la accende lui dal pannello admin per i clienti a cui ha senso.
--
-- DUE INTERRUTTORI, NON UNO. `email_settimanale` resta la scelta del CLIENTE
-- (default accesa: «la voglio»), `email_settimanale_abilitata` e' quella
-- dell'ADMIN (default SPENTA: «questo cliente puo' riceverla»). L'email parte
-- solo se entrambi sono accesi. Con una colonna sola, un admin che abilita un
-- cliente disiscritto annullerebbe la sua disiscrizione: la scelta del cliente
-- non deve poter essere sovrascritta da nessuno.
--
-- Nessun UPDATE: il DEFAULT false vale anche per le righe esistenti, quindi oggi
-- nessuno la riceve. Idempotente.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS email_settimanale_abilitata boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.users.email_settimanale_abilitata IS
    'L''admin ha abilitato l''email settimanale per questo cliente (default false). '
    'Parte solo se anche email_settimanale (la scelta del cliente) e'' vera.';
