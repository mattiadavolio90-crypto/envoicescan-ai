-- L'«ultimo prezzo» del foodcost: l'ultima FATTURA con un prezzo pagato, a
-- prezzo ponderato (gemella di `ultimo_acquisto_per_descrizione` in
-- utils/voci_prezzo.py, usata dal ripiego Python e dall'inventario).
-- Prima: DISTINCT ON sulla prima RIGA della data piu' recente. Con lo stesso
-- articolo su piu' righe dell'ultima fattura il prezzo dipendeva dall'ordine del
-- database, e un omaggio a 0 € accanto alla riga pagata poteva proporre 0 €
-- (misurato il 14/10/2026: 76 articoli). Ora per descrizione si sceglie
-- l'ultima fattura (data, poi file e unita' di misura COLLATE "C") fra quelle
-- con un prezzo positivo; un articolo di soli omaggi resta con prezzo 0.
-- Prezzo: media ponderata sulle quantita' positive (quantita' mancante = 1),
-- media semplice se nessuna lo e', 6 decimali — la regola dell'Osservatorio.
--
-- Firma e colonne restituite invariate (CREATE OR REPLACE). Parte dalla
-- versione live (20260912075621_oscura_fattura.sql: esclude le oscurate).
-- Nessun ordine obbligato col deploy: il worker vecchio legge la stessa forma.

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
    with righe as (
        select
            f.descrizione,
            f.prezzo_unitario,
            coalesce(f.quantita, 1) as quantita,
            f.unita_misura,
            f.data_documento,
            f.file_origine,
            upper(btrim(coalesce(f.unita_misura, ''))) as unita_key,
            -- una riga senza file e' un acquisto a se', come `chiave_documento`
            case when btrim(coalesce(f.file_origine, '')) = '' then f.id else -1 end as solo
        from public.fatture f
        where f.user_id = p_user_id
          and f.ristorante_id = p_ristorante_id
          and f.deleted_at is null
          and not f.oscurata
          and f.descrizione is not null
          and btrim(f.descrizione) <> ''
          and not (f.categoria = any (p_categorie_escluse))
    ),
    documenti as (
        select
            r.descrizione,
            r.file_origine,
            r.data_documento,
            r.unita_key,
            r.solo,
            min(r.unita_misura) as unita_misura,
            coalesce(bool_or(r.prezzo_unitario > 0), false) as pagato,
            coalesce(round(case
                when sum(r.quantita) filter (where r.prezzo_unitario > 0 and r.quantita > 0) > 0
                then sum(r.prezzo_unitario * r.quantita) filter (where r.prezzo_unitario > 0 and r.quantita > 0)
                     / sum(r.quantita) filter (where r.prezzo_unitario > 0 and r.quantita > 0)
                else avg(r.prezzo_unitario) filter (where r.prezzo_unitario > 0)
            end, 6), 0) as prezzo_unitario
        from righe r
        group by r.descrizione, r.file_origine, r.data_documento, r.unita_key, r.solo
    )
    select distinct on (d.descrizione)
        d.descrizione,
        d.prezzo_unitario,
        d.unita_misura,
        d.data_documento
    from documenti d
    order by d.descrizione, d.pagato desc, d.data_documento desc nulls last,
             d.file_origine collate "C" desc, d.unita_key collate "C" desc, d.solo desc;
$$;

comment on function public.articoli_da_fatture is
    'Articoli unici per il foodcost: per descrizione l''ultima fattura con un prezzo pagato, a prezzo ponderato. Gemella di utils/voci_prezzo.ultimo_acquisto_per_descrizione.';

REVOKE ALL ON FUNCTION public.articoli_da_fatture(uuid, uuid, text[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.articoli_da_fatture(uuid, uuid, text[]) TO service_role;
