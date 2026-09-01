-- Fase 2 — rendere visibile CHI ha deciso la categoria, e con quanta fiducia.
--
-- Problema (D1): `fatture` non ha alcun campo che registri quale livello ha deciso.
-- Su 39.143 righe non e' ricostruibile se una categoria venga da una regola certa,
-- dal dizionario, da memoria non verificata o dall'AI. Conseguenza: non si puo'
-- applicare la filosofia del progetto (non si puo' dubitare di cio' di cui non si
-- conosce l'origine), non si puo' misurare per fonte, non si puo' fare rollback
-- mirato di una regola sbagliata.
--
-- Il dato ESISTE gia' nel codice: ogni return di `categorizza_con_memoria` lo logga
-- con la sua emoji e `applica_regole_categoria_forti` restituisce 196 motivi distinti
-- che quasi tutti i chiamanti scartano con `_`. Non va ricostruito, va propagato.
--
-- ADD COLUMN senza DEFAULT: metadata-only da PG11, nessun rewrite della tabella
-- (28 MB, 39.155 righe). Nessun lock significativo.

alter table public.fatture
    add column if not exists categoria_fonte text,
    add column if not exists categoria_fiducia text;

-- Le righe preesistenti restano a NULL DI PROPOSITO, e NULL significa `legacy`.
--
-- Vincolo S3 del piano, fissato PRIMA di scrivere questa migration: provenienza
-- assente = `legacy`, trattata come `certa`. E' lo status quo, e la misura cieca su
-- 815 righe mai verificate dice che lo status quo e' accurato al 96,7%.
--
-- Nessun backfill retroattivo: assegnare una fonte a righe scritte da un codice che
-- non la registrava sarebbe un'invenzione, non un dato. Se la Fase 3 leggesse
-- "provenienza assente" come "non affidabile", l'intero storico diventerebbe dubbio
-- da un giorno all'altro — e i margini di aprile e maggio cambierebbero valore mesi
-- dopo che il cliente li ha letti.

comment on column public.fatture.categoria_fonte is
    'Livello che ha deciso la categoria: L0_fornitore, L1_admin, L1_5_non_negoziabile, '
    'L2_locale, L3_globale, L3_globale_non_verificata, L4_dicitura, L5_fornitore, '
    'L6_um, L7_dizionario, L7_regola_forte, AI_alta, AI_confermata, nessuna. '
    'NULL = legacy (riga scritta prima della Fase 2): si tratta come certa, mai come dubbia.';

comment on column public.fatture.categoria_fiducia is
    'certa | probabile | da_verificare. NULL = legacy, equivale a certa. '
    'La Fase 4 escludera'' dai margini le righe da_verificare, dietro flag.';

-- Vincoli di dominio: valori liberi diventerebbero inutilizzabili per le query di
-- Fase 3/4. NULL sempre consentito (e' il caso legacy).
alter table public.fatture
    drop constraint if exists fatture_categoria_fiducia_chk;

alter table public.fatture
    add constraint fatture_categoria_fiducia_chk
    check (categoria_fiducia is null
           or categoria_fiducia in ('certa', 'probabile', 'da_verificare'))
    not valid;

-- NOT VALID: il check vale sulle righe NUOVE senza scandire le 39.155 esistenti
-- (che sono tutte NULL e lo soddisfano comunque). Validazione esplicita subito dopo:
-- su una tabella di queste dimensioni costa nulla, e lascia il constraint pulito.
alter table public.fatture validate constraint fatture_categoria_fiducia_chk;

-- Indice parziale: serve alla Fase 4 (escludere le da_verificare dai margini) e alla
-- card in Home (contarle per sede). Parziale perche' interessa solo quella minoranza.
create index if not exists idx_fatture_da_verificare
    on public.fatture (ristorante_id, data_documento)
    where categoria_fiducia = 'da_verificare' and deleted_at is null;
