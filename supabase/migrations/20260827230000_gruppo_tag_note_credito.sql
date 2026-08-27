-- Tag di catena: le note di credito devono scalare la spesa.
--
-- PERCHÉ (27/8/2026, §3c — ultimo MEDIUM del ciclo audit 2026-07)
-- Le 4 RPC `gruppo_tag_*` filtrano `AND f.prezzo_unitario > 0` nella WHERE.
-- Il filtro è corretto sui calcoli di PREZZO (una nota di credito ha prezzo
-- negativo e falserebbe la media), ma queste RPC non calcolano prezzi: sono
-- aggregazioni di SPESA (`sum(f.totale_riga)`). Scartare le righe a prezzo <= 0
-- dalla somma significa non scalare i resi, cioè sovrastimare la spesa.
--
-- È lo STESSO filtro sulla grandezza sbagliata già corretto il 24/8 sul percorso
-- sede-singola (STORICO §22): lì `services/tag_analytics_service.py` ora marca le
-- righe con `PrezzoValido` e le esclude solo dai calcoli di prezzo, tenendole
-- nella spesa. Il percorso di catena era rimasto indietro: stessa domanda, due
-- risposte diverse a seconda che il cliente guardi la sede o il gruppo.
--
-- MISURATO SUL DB LIVE PRIMA DEL FIX (tag SALMONE, id=3, l'unico popolato):
--   7 righe con prezzo_unitario <= 0, tutte note di credito reali di ADC S.R.L.
--   LAND DEI SAPORI SRL       245.764,83 -> 245.518,38  (-246,45, 6 note)
--   SUSHILAND VILLA GUARDIA   103.860,66 -> 103.821,61  ( -39,05, 1 nota)
--   Totale spesa di catena:   -285,50 EUR
-- (Il verbale §25/§28 riportava 236,23 EUR su 3 righe: era corretto allora, sono
--  arrivate altre note di credito nel frattempo. Ricontato, non ereditato.)
--
-- COSA CAMBIA: i totali di catena dei tag CALANO dell'importo dei resi, cioè
-- diventano uguali a quelli già mostrati sulla sede singola. Non è una perdita
-- di dati: è la rimozione di una sovrastima.
--
-- IL PREZZO MEDIO RESTA COERENTE: `gruppo_tag_analisi` espone una colonna nuova
-- `spesa_prezzo_valido` (spesa delle sole righe a prezzo > 0). Il prezzo medio di
-- catena si calcola da quella diviso `quantita` — due termini omogenei — mentre
-- `spesa` resta la grandezza netta da mostrare al cliente. Senza questa colonna
-- il fix avrebbe allineato la spesa e disallineato il prezzo (numeratore netto,
-- denominatore lordo): distorsione misurata 0,10% su LAND DEI SAPORI, sotto
-- l'arrotondamento, ma ASIMMETRICA fra sedi — e la UI di catena colora min/max
-- per dire quale sede compra meglio.
--
-- COSA NON CAMBIA: `gruppo_prezzi_categoria` (20260617220000) mantiene il suo
-- `prezzo_unitario > 0` — lì la grandezza È un prezzo medio ponderato e le note
-- di credito vanno davvero escluse. `gruppo_tag_analisi.quantita` era già
-- protetta a parte da `CASE WHEN f.quantita > 0`, quindi un reso non sottrae
-- chili: scala la spesa, non il volume acquistato.

-- DROP necessario: `CREATE OR REPLACE` non puo' cambiare il tipo di ritorno, e
-- qui RETURNS TABLE guadagna la colonna `spesa_prezzo_valido` (errore 42P13).
-- La finestra fra DROP e CREATE e' dentro la transazione della migration.
DROP FUNCTION IF EXISTS public.gruppo_tag_analisi(uuid[], text[], date, date);

CREATE OR REPLACE FUNCTION public.gruppo_tag_analisi(
    p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
RETURNS TABLE(ristorante_id uuid, spesa numeric, spesa_prezzo_valido numeric, quantita numeric, n_righe bigint, n_fornitori bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        sum(f.totale_riga) AS spesa,
        -- Spesa delle sole righe a prezzo positivo: e' il numeratore da usare per
        -- il prezzo medio, che ha per denominatore una quantita' anch'essa al
        -- lordo dei resi. Dividere la spesa NETTA per la quantita' LORDA darebbe
        -- un prezzo sottostimato. La sede-singola fa gia' questa separazione
        -- (tag_analytics_service.py: `spesa_totale` da tutte le righe, prezzo da
        -- `_solo_prezzo_valido`); qui la si replica.
        sum(f.totale_riga) FILTER (WHERE f.prezzo_unitario > 0) AS spesa_prezzo_valido,
        sum(CASE WHEN f.quantita > 0 THEN f.quantita ELSE 0 END) AS quantita,
        count(*)::bigint AS n_righe,
        count(DISTINCT f.fornitore)::bigint AS n_fornitori
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id;
$function$;

CREATE OR REPLACE FUNCTION public.gruppo_tag_fornitori(
    p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
RETURNS TABLE(fornitore text, spesa numeric, n_righe bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $function$
    SELECT
        COALESCE(NULLIF(btrim(f.fornitore), ''), '—') AS fornitore,
        sum(f.totale_riga) AS spesa,
        count(*)::bigint AS n_righe
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1
    ORDER BY spesa DESC NULLS LAST
    LIMIT 20;
$function$;

CREATE OR REPLACE FUNCTION public.gruppo_tag_trend(
    p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
RETURNS TABLE(anno integer, mese integer, spesa numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $function$
    SELECT
        extract(year  FROM COALESCE(f.data_competenza, f.data_documento))::int AS anno,
        extract(month FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1, 2
    ORDER BY 1, 2;
$function$;

-- Selettore prodotti: la spesa mostrata accanto a ogni descrizione deve essere
-- la stessa che il tag mostrerà una volta creato, altrimenti i due numeri
-- divergono nella stessa schermata.
CREATE OR REPLACE FUNCTION public.gruppo_tag_descrizioni(
    p_ristorante_ids uuid[], p_q text DEFAULT NULL::text, p_limit integer DEFAULT 500)
RETURNS TABLE(descrizione text, descrizione_key text, n bigint, spesa numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $function$
    SELECT
        (array_agg(f.descrizione ORDER BY f.data_documento DESC))[1] AS descrizione,
        upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) AS descrizione_key,
        count(*)::bigint AS n,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND f.descrizione IS NOT NULL
      AND btrim(f.descrizione) <> ''
      AND (p_q IS NULL OR btrim(p_q) = '' OR f.descrizione ILIKE '%' || btrim(p_q) || '%')
    GROUP BY descrizione_key
    ORDER BY spesa DESC NULLS LAST
    LIMIT p_limit;
$function$;
