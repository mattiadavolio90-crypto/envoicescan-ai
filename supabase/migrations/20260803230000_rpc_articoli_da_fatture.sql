-- Articoli unici per il foodcost, aggregati lato database.
--
-- Prima: get_articoli_da_fatture() scaricava TUTTE le righe fatture della sede
-- (9.015 su una sede reale, in 9 round-trip da 1000) per poi tenere in Python
-- solo la prima riga per descrizione -> 1.571 articoli utili, spreco ~5,7x, e
-- il costo cresce ogni mese mentre il risultato resta della stessa dimensione.
--
-- Qui la stessa domanda la risponde il database con DISTINCT ON: una riga per
-- descrizione, gia' quella con la data piu' recente. Stesso identico criterio
-- del loop Python (che teneva la prima riga incontrata con ORDER BY
-- data_documento DESC), quindi stesso risultato.
--
-- Le categorie da escludere restano un parametro (come costi_automatici_mensili)
-- e non una lista hardcoded: la fonte di verita' e' config/constants.py, il DB
-- non deve avere una seconda copia che diverge in silenzio.
--
-- "Da Classificare" viene escluso dal chiamante insieme alle spese generali:
-- una riga ancora in coda di revisione non deve entrare nel foodcost (CLAUDE.md §1).
--
-- SECURITY INVOKER (default): nessun bypass di RLS, come costi_automatici_mensili.

create or replace function public.articoli_da_fatture(
    p_user_id uuid,
    p_ristorante_id uuid,
    p_categorie_escluse text[]
)
returns table (
    descrizione text,
    prezzo_unitario numeric,
    unita_misura text,
    data_documento date
)
language sql
stable
as $$
    select distinct on (f.descrizione)
        f.descrizione,
        f.prezzo_unitario,
        f.unita_misura,
        f.data_documento
    from public.fatture f
    where f.user_id = p_user_id
      and f.ristorante_id = p_ristorante_id
      and f.deleted_at is null
      and f.descrizione is not null
      and btrim(f.descrizione) <> ''
      and not (f.categoria = any (p_categorie_escluse))
    order by f.descrizione, f.data_documento desc nulls last;
$$;

comment on function public.articoli_da_fatture is
    'Articoli unici (ultimo prezzo per descrizione) per il foodcost. Sostituisce il full-load + dedup in Python di services/foodcost_service.get_articoli_da_fatture.';
