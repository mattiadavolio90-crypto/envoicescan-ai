-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: nome_gruppo su users (etichetta catena per clienti multi-sede)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Obiettivo:
--   Un cliente con più sedi (es. SUSHILAND, 4 PV) non ha un nome di "gruppo": la
--   UI mostra il nome della PRIMA sede. `nome_gruppo` dà un'etichetta opzionale a
--   livello account, usata da lista clienti e titolo anagrafica admin quando il
--   cliente ha più sedi. NON sostituisce nome_ristorante (= nome account/1ª sede)
--   né il nome della sede attiva mostrato in testata.
--
-- Idempotente: ri-eseguibile senza errori.
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS nome_gruppo TEXT;

COMMENT ON COLUMN public.users.nome_gruppo IS
    'Etichetta opzionale del gruppo/catena per clienti multi-sede (es. "SUSHILAND"). '
    'Usata da lista clienti e anagrafica admin al posto del nome della prima sede '
    'quando valorizzata. NULL per i clienti mono-sede.';
