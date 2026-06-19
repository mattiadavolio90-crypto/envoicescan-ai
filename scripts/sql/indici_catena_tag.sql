-- Indici per velocizzare le query dei TAG DI CATENA su `fatture`.
-- DA LANCIARE FUORI ORARIO: usano CREATE INDEX CONCURRENTLY, che NON può girare
-- dentro una transazione (quindi NON è una migration CLI) e che, pur non bloccando
-- le scritture, mette sotto carico la tabella. Eseguire una riga alla volta.
--
-- Coprono:
--   #12  ricerca prodotti "Aggiungi al tag" (ILIKE %testo% su descrizione)
--   #11  match esatto su descrizione normalizzata (gruppo_tag_analisi/fornitori/
--        trend/descrizioni) — indice funzionale sull'espressione usata dalle RPC.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- #12 — ricerca testo (ILIKE) sulle descrizioni
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fatture_descrizione_trgm
    ON public.fatture USING gin (descrizione gin_trgm_ops);

-- #11 — match esatto sulla chiave descrizione normalizzata, filtrato per sede
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fatture_descrizione_key
    ON public.fatture (
        ristorante_id,
        (upper(regexp_replace(btrim(descrizione), '\s+', ' ', 'g')))
    )
    WHERE deleted_at IS NULL AND prezzo_unitario > 0;
