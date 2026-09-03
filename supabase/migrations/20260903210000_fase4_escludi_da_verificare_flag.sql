-- Fase 4 piano categorizzazione (decisione Mattia 1/9/2026): le righe con
-- categoria_fiducia = 'da_verificare' escono dai calcoli margini COME le
-- 'Da Classificare' — ma dietro flag, e il flag di default è SPENTO.
--
-- Meccanica del flag: parametro `p_escludi_da_verificare boolean DEFAULT false`
-- su ognuna delle 7 RPC vive che oggi filtrano 'Da Classificare' (misurate su
-- pg_proc il 3/9/2026, non sui file: costi_automatici_mensili,
-- costi_automatici_mensili_gruppo, gruppo_peso_categoria, gruppo_prezzi_categoria,
-- gruppo_spesa_pivot, gruppo_spreco_fb_categorie, gruppo_tag_descrizioni).
-- Il Python passa il parametro SOLO quando la costante
-- ESCLUDI_DA_VERIFICARE_DAI_MARGINI (config/constants.py) è True: a flag spento
-- le chiamate restano identiche a prima, quindi il codice può essere deployato
-- prima o dopo questa migration senza rotture in nessun ordine.
--
-- DROP + CREATE (non CREATE OR REPLACE): aggiungere un parametro con DEFAULT a
-- una funzione esistente creerebbe un OVERLOAD, e PostgREST non saprebbe più
-- risolvere la chiamata (ambiguità). Il DROP richiede di ristabilire i GRANT:
-- come da migration 20260619230000, EXECUTE al solo service_role. Nota: questo
-- chiude anche il residuo su costi_automatici_mensili_gruppo, che a DB aveva
-- ancora EXECUTE per anon/authenticated/PUBLIC.
--
-- La condizione è NULL-safe per costruzione (COALESCE): le righe legacy con
-- categoria_fiducia NULL sono 'certa' per la regola S3 e RESTANO nei margini.
-- gruppo_prezzi_categoria risulta senza chiamanti nel repo (3/9): riceve
-- comunque il parametro per coerenza, così un eventuale ritorno in vita non
-- diverge dalla regola.

-- ============================================================
-- 1. costi_automatici_mensili
-- ============================================================
DROP FUNCTION IF EXISTS public.costi_automatici_mensili(uuid, uuid, integer, text[], text[]);

CREATE FUNCTION public.costi_automatici_mensili(
    p_user_id uuid,
    p_ristorante_id uuid,
    p_anno integer,
    p_cat_food text[],
    p_cat_spese text[],
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(mese integer, food numeric, spese numeric)
 LANGUAGE sql
 STABLE
AS $function$
    WITH base AS (
        SELECT
            EXTRACT(MONTH FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
            f.categoria,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = p_ristorante_id
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)   -- anti-doppio-conteggio (MOL)
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(f.data_competenza, f.data_documento)) = p_anno
    )
    SELECT
        base.mese,
        COALESCE(SUM(base.totale_riga) FILTER (
            WHERE base.categoria <> ALL(p_cat_spese) AND base.categoria <> '📝 NOTE E DICITURE'
        ), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.mese
    ORDER BY base.mese;
$function$;

REVOKE ALL ON FUNCTION public.costi_automatici_mensili(uuid, uuid, integer, text[], text[], boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.costi_automatici_mensili(uuid, uuid, integer, text[], text[], boolean) TO service_role;

-- ============================================================
-- 2. costi_automatici_mensili_gruppo
-- ============================================================
DROP FUNCTION IF EXISTS public.costi_automatici_mensili_gruppo(uuid, uuid[], integer, text[], text[]);

CREATE FUNCTION public.costi_automatici_mensili_gruppo(
    p_user_id uuid,
    p_ristorante_ids uuid[],
    p_anno integer,
    p_cat_food text[],
    p_cat_spese text[],
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, mese integer, food numeric, spese numeric)
 LANGUAGE sql
 STABLE
AS $function$
    WITH base AS (
        SELECT
            f.ristorante_id,
            EXTRACT(MONTH FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
            f.categoria,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)   -- anti-doppio-conteggio (MOL)
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(f.data_competenza, f.data_documento)) = p_anno
    )
    SELECT
        base.ristorante_id,
        base.mese,
        COALESCE(SUM(base.totale_riga) FILTER (
            WHERE base.categoria <> ALL(p_cat_spese) AND base.categoria <> '📝 NOTE E DICITURE'
        ), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.ristorante_id, base.mese
    ORDER BY base.ristorante_id, base.mese;
$function$;

REVOKE ALL ON FUNCTION public.costi_automatici_mensili_gruppo(uuid, uuid[], integer, text[], text[], boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.costi_automatici_mensili_gruppo(uuid, uuid[], integer, text[], text[], boolean) TO service_role;

-- ============================================================
-- 3. gruppo_peso_categoria
-- ============================================================
DROP FUNCTION IF EXISTS public.gruppo_peso_categoria(uuid[], date, date);

CREATE FUNCTION public.gruppo_peso_categoria(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, categoria text, spesa numeric, peso_perc numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH righe AS (
        SELECT
            f.ristorante_id AS rid,
            f.categoria AS cat,
            SUM(f.totale_riga) AS tot
        FROM fatture f
        WHERE f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND f.totale_riga > 0
          AND UPPER(f.categoria) NOT IN (
                'SERVIZI E CONSULENZE',
                'UTENZE E LOCALI',
                'MANUTENZIONE E ATTREZZATURE',
                'MATERIALE DI CONSUMO'
          )
          AND f.categoria NOT LIKE '%NOTE E DICITURE%'
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
          AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
        GROUP BY 1, 2
    ),
    tot_pv AS (
        SELECT rid, SUM(tot) AS tot_fb FROM righe GROUP BY 1
    )
    SELECT
        r.rid AS ristorante_id,
        r.cat AS categoria,
        r.tot AS spesa,
        (100.0 * r.tot / t.tot_fb)::numeric AS peso_perc
    FROM righe r
    JOIN tot_pv t ON t.rid = r.rid
    WHERE t.tot_fb > 0;
$function$;

REVOKE ALL ON FUNCTION public.gruppo_peso_categoria(uuid[], date, date, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_peso_categoria(uuid[], date, date, boolean) TO service_role;

-- ============================================================
-- 4. gruppo_prezzi_categoria (oggi senza chiamanti nel repo)
-- ============================================================
DROP FUNCTION IF EXISTS public.gruppo_prezzi_categoria(uuid[], date, date);

CREATE FUNCTION public.gruppo_prezzi_categoria(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, categoria text, prezzo_medio numeric, n_righe bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        f.categoria,
        CASE
            WHEN SUM(CASE WHEN f.quantita > 0 THEN f.quantita ELSE 0 END) > 0
            THEN SUM(CASE WHEN f.quantita > 0 THEN f.totale_riga ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN f.quantita > 0 THEN f.quantita ELSE 0 END), 0)
            ELSE AVG(f.prezzo_unitario)
        END AS prezzo_medio,
        COUNT(*)::bigint AS n_righe
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.prezzo_unitario > 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, f.categoria;
$function$;

REVOKE ALL ON FUNCTION public.gruppo_prezzi_categoria(uuid[], date, date, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_prezzi_categoria(uuid[], date, date, boolean) TO service_role;

-- ============================================================
-- 5. gruppo_spesa_pivot
-- ============================================================
DROP FUNCTION IF EXISTS public.gruppo_spesa_pivot(uuid[], text, date, date);

CREATE FUNCTION public.gruppo_spesa_pivot(
    p_ristorante_ids uuid[],
    p_dimensione text,
    p_data_da date,
    p_data_a date,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, dim_val text, totale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        COALESCE(
            NULLIF(CASE WHEN p_dimensione = 'fornitore' THEN f.fornitore ELSE f.categoria END, ''),
            'N/D'
        ) AS dim_val,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.totale_riga > 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, dim_val;
$function$;

REVOKE ALL ON FUNCTION public.gruppo_spesa_pivot(uuid[], text, date, date, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_spesa_pivot(uuid[], text, date, date, boolean) TO service_role;

-- ============================================================
-- 6. gruppo_spreco_fb_categorie
-- ============================================================
DROP FUNCTION IF EXISTS public.gruppo_spreco_fb_categorie(uuid[], date, date);

CREATE FUNCTION public.gruppo_spreco_fb_categorie(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, anno integer, mese integer, categoria text, totale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        EXTRACT(YEAR FROM f.data_documento)::int AS anno,
        EXTRACT(MONTH FROM f.data_documento)::int AS mese,
        f.categoria,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.ripartita_su_gruppo IS DISTINCT FROM true
      AND f.totale_riga > 0
      AND f.data_documento IS NOT NULL
      AND f.data_documento >= p_data_da
      AND f.data_documento <= p_data_a
      AND f.categoria IN (
          'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
          'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA',
          'SALSE E CREME','PRODOTTI DA FORNO','SPEZIE E AROMI','SUSHI VARIE',
          'ACQUA','BEVANDE','CAFFE E THE','VARIE BAR',
          'BIRRE','VINI','DISTILLATI','AMARI/LIQUORI',
          'PASTICCERIA','GELATI E DESSERT',
          'SHOP'
      )
    GROUP BY f.ristorante_id, anno, mese, f.categoria;
$function$;

REVOKE ALL ON FUNCTION public.gruppo_spreco_fb_categorie(uuid[], date, date, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_spreco_fb_categorie(uuid[], date, date, boolean) TO service_role;

-- ============================================================
-- 7. gruppo_tag_descrizioni
-- ============================================================
DROP FUNCTION IF EXISTS public.gruppo_tag_descrizioni(uuid[], text, integer);

CREATE FUNCTION public.gruppo_tag_descrizioni(
    p_ristorante_ids uuid[],
    p_q text DEFAULT NULL::text,
    p_limit integer DEFAULT 500,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(descrizione text, descrizione_key text, n bigint, spesa numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
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
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.descrizione IS NOT NULL
      AND btrim(f.descrizione) <> ''
      AND (p_q IS NULL OR btrim(p_q) = '' OR f.descrizione ILIKE '%' || btrim(p_q) || '%')
    GROUP BY descrizione_key
    ORDER BY spesa DESC NULLS LAST
    LIMIT p_limit;
$function$;

REVOKE ALL ON FUNCTION public.gruppo_tag_descrizioni(uuid[], text, integer, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_descrizioni(uuid[], text, integer, boolean) TO service_role;
