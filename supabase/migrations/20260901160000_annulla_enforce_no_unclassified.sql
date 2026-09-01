-- Annulla 20260429223000_enforce_no_unclassified_categoria.sql, che vietava a DB
-- la categoria "Da Classificare".
--
-- Quel vincolo contraddice la regola di dominio n.1 del progetto (CLAUDE.md,
-- "flusso categorizzazione = onesto"): una riga che ne' il dizionario ne' l'AI
-- riconoscono DEVE poter restare esplicitamente in coda, invece di ricevere una
-- categoria inventata. E' esattamente il "fallback travestito" che il progetto ha
-- eliminato il 23/06.
--
-- Stato accertato sul DB di produzione il 1/9/2026:
--   - il constraint attivo e' `fatture_categoria_not_empty_chk` (vieta solo
--     NULL/stringa vuota, consente "Da Classificare") — quello giusto;
--   - `fatture_categoria_not_unclassified_chk` NON risulta applicato;
--   - 172 righe di 3 clienti reali lo violerebbero all'istante.
--
-- Il file del 29/4 resta agli atti (e' storia), ma chiunque rilanci le migration
-- in ordine su un ambiente nuovo si troverebbe il vincolo sbagliato attivo e il
-- salvataggio fatture rotto per quelle righe. Questa migration, essendo
-- successiva, lo rimuove in ogni caso.

alter table public.fatture
    drop constraint if exists fatture_categoria_not_unclassified_chk;

-- Ribadisce il vincolo corretto (idempotente): categoria valorizzata, ma
-- "Da Classificare" e' un valore legittimo.
alter table public.fatture
    drop constraint if exists fatture_categoria_not_empty_chk;

alter table public.fatture
    add constraint fatture_categoria_not_empty_chk
    check (categoria is not null and btrim(categoria) <> '');
