-- "Escludi dai conti" — una fattura che il cliente vuole conservare e consultare,
-- ma che non deve entrare in NESSUN conteggio dell'app.
--
-- Perche' una colonna e non il cestino: il cestino la fa SPARIRE (e dopo 30gg la
-- cancella). Qui serve l'opposto: resta visibile in Gestione Fatture, marcata e
-- ri-attivabile con un click, ma fuori da margini/MOL, foodcost, analisi fatture,
-- prezzi fornitori, dashboard, briefing e catena.
--
-- Modello copiato: `ripartita_su_gruppo` (colonna booleana su `fatture` che esclude
-- righe dai costi lasciando la fattura visibile). NON il modello Fase 4: quello e'
-- dietro feature flag perche' era una decisione di dominio reversibile in massa, e
-- ha richiesto un parametro nuovo alle RPC -> DROP+CREATE+ri-GRANT per l'overload
-- ambiguo (vedi 20260903210000_fase4_escludi_da_verificare_flag.sql righe 15-19).
-- Qui il filtro e' INCONDIZIONATO (una fattura esclusa e' sempre fuori dai conti),
-- quindi le RPC si riscrivono con CREATE OR REPLACE a FIRMA INVARIATA: zero
-- ambiguita' PostgREST, e nessun ordine obbligato fra migration e deploy.
--
-- La regola, per chi legge dopo:
--   `oscurata` vive su `fatture` e SOLO li'. Chi conta soldi filtra oscurata=false.
--   Chi mostra la lista di Gestione Fatture, il cestino e l'anteprima righe: NO.
--
-- Perche' NON su `fatture_documenti`: nessun consumatore che conta soldi legge solo
-- quella tabella (il radar anomalie confronta lo storico all'upload, la lista NC di
-- prezzi.py e' un insieme di file, non una somma). Aggiungerla avrebbe richiesto di
-- toccare fn_propagate_deleted_at_fatture, cioe' rischiare la propagazione del
-- soft-delete per un beneficio che non esiste.

ALTER TABLE public.fatture
    ADD COLUMN IF NOT EXISTS oscurata boolean NOT NULL DEFAULT false;

-- Quando e' stata esclusa: e' la domanda che arriva quando un margine non torna
-- ("da quando questa fattura non conta?"). Costo zero adesso, irricostruibile dopo.
ALTER TABLE public.fatture
    ADD COLUMN IF NOT EXISTS oscurata_at timestamptz;

-- Indice PARZIALE (come idx_fatture_ripartita_su_gruppo): le escluse sono una
-- manciata su ~39.500 righe attive. Serve alla query della lista, che chiede
-- "quali sono escluse?" — non ai filtri `oscurata = false`, per cui il planner usa
-- gli indici esistenti.
CREATE INDEX IF NOT EXISTS idx_fatture_oscurata
    ON public.fatture (user_id, ristorante_id, file_origine)
    WHERE oscurata = true;

-- ── Le 13 RPC che CONTANO: filtro `NOT <alias>.oscurata` accanto a deleted_at ──
--
-- La colonna e' NOT NULL DEFAULT false, quindi niente COALESCE: e' la differenza
-- con `ripartita_su_gruppo`, che era nullable e obbliga i suoi filtri a COALESCE.
--
-- I corpi sono ripresi dal DB LIVE (pg_get_functiondef, verificati identici allo
-- schema_snapshot.sql del 2026-09-08), non dai file di migration che le hanno
-- create: lo stato reale applicato e' il DB, non il repo.
--
-- NON filtrate, deliberatamente:
--   scadenziario_fatture_aggregate  -> e' la lista di Gestione Fatture: deve
--                                      continuare a mostrare le escluse
--   get_distinct_files, admin_*     -> volumi per fatturazione, non costi
CREATE OR REPLACE FUNCTION public.articoli_da_fatture(p_user_id uuid, p_ristorante_id uuid, p_categorie_escluse text[])
 RETURNS TABLE(descrizione text, prezzo_unitario numeric, unita_misura text, data_documento date)
 LANGUAGE sql
 STABLE
AS $function$
    select distinct on (f.descrizione)
        f.descrizione,
        f.prezzo_unitario,
        f.unita_misura,
        f.data_documento
    from public.fatture f
    where f.user_id = p_user_id
      and f.ristorante_id = p_ristorante_id
      and f.deleted_at is null
      and not f.oscurata
      and f.descrizione is not null
      and btrim(f.descrizione) <> ''
      and not (f.categoria = any (p_categorie_escluse))
    order by f.descrizione, f.data_documento desc nulls last;
$function$;


CREATE OR REPLACE FUNCTION public.chat_top_categoria_fornitore(p_user_id uuid, p_ristorante_id uuid, p_giorni integer DEFAULT 90, p_top integer DEFAULT 5)
 RETURNS TABLE(tipo text, voce text, spesa numeric)
 LANGUAGE sql
 STABLE
 SET search_path TO 'public'
AS $function$
    WITH base AS (
        SELECT
            COALESCE(NULLIF(TRIM(f.categoria), ''), 'Altro') AS categoria,
            COALESCE(NULLIF(TRIM(f.fornitore), ''), 'Sconosciuto') AS fornitore,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.deleted_at IS NULL
          AND NOT f.oscurata
          AND f.data_documento >= (CURRENT_DATE - p_giorni)
          AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
    ),
    top_cat AS (
        SELECT 'categoria'::text AS tipo, categoria AS voce, SUM(totale_riga) AS spesa
        FROM base GROUP BY categoria ORDER BY SUM(totale_riga) DESC LIMIT p_top
    ),
    top_forn AS (
        SELECT 'fornitore'::text AS tipo, fornitore AS voce, SUM(totale_riga) AS spesa
        FROM base GROUP BY fornitore ORDER BY SUM(totale_riga) DESC LIMIT p_top
    )
    SELECT tipo, voce, ROUND(spesa, 2) AS spesa FROM top_cat
    UNION ALL
    SELECT tipo, voce, ROUND(spesa, 2) AS spesa FROM top_forn;
$function$;


CREATE OR REPLACE FUNCTION public.costi_automatici_mensili(p_user_id uuid, p_ristorante_id uuid, p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean DEFAULT false)
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
          AND NOT f.oscurata
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


CREATE OR REPLACE FUNCTION public.costi_automatici_mensili_gruppo(p_user_id uuid, p_ristorante_ids uuid[], p_anno integer, p_cat_food text[], p_cat_spese text[], p_escludi_da_verificare boolean DEFAULT false)
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
          AND NOT f.oscurata
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


CREATE OR REPLACE FUNCTION public.dashboard_stats_aggregata(p_user_id uuid, p_ristorante_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    v_oggi          date := (now() AT TIME ZONE 'Europe/Rome')::date;
    v_mese_corr     text := to_char(v_oggi, 'YYYY-MM');
    v_mese_prec     text := to_char((date_trunc('month', v_oggi) - interval '1 day')::date, 'YYYY-MM');
    v_result        jsonb;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;
    WITH base AS (
        SELECT
            COALESCE(f.totale_riga, 0)                         AS totale,
            f.data_documento,
            to_char(f.data_documento, 'YYYY-MM')               AS mese_key,
            NULLIF(btrim(COALESCE(f.fornitore, '')), '')       AS fornitore,
            NULLIF(btrim(COALESCE(f.categoria, '')), '')       AS categoria,
            f.file_origine
        FROM public.fatture f
        WHERE f.user_id = p_user_id
          AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
          AND f.deleted_at IS NULL
          AND NOT f.oscurata
    ),
    kpi AS (
        SELECT
            COUNT(DISTINCT file_origine)                                          AS fatture_uniche,
            COUNT(*)                                                              AS righe_totali,
            COALESCE(SUM(totale), 0)                                              AS spesa_totale,
            COALESCE(SUM(totale) FILTER (WHERE mese_key = v_mese_corr), 0)        AS spesa_mese_corrente,
            COALESCE(SUM(totale) FILTER (WHERE mese_key = v_mese_prec), 0)        AS spesa_mese_precedente,
            MIN(data_documento)                                                   AS prima_fattura,
            MAX(data_documento)                                                   AS ultima_fattura
        FROM base
    ),
    per_mese AS (
        SELECT mese_key, ROUND(SUM(totale), 2) AS spesa
        FROM base
        WHERE mese_key IS NOT NULL
        GROUP BY mese_key
        ORDER BY mese_key DESC
        LIMIT 12
    ),
    per_mese_asc AS (
        SELECT mese_key, spesa FROM per_mese ORDER BY mese_key ASC
    ),
    per_fornitore AS (
        SELECT COALESCE(fornitore, '—') AS nome, ROUND(SUM(totale), 2) AS spesa, COUNT(*) AS righe
        FROM base
        GROUP BY COALESCE(fornitore, '—')
        ORDER BY SUM(totale) DESC
        LIMIT 5
    ),
    per_categoria AS (
        SELECT COALESCE(categoria, '—') AS nome, ROUND(SUM(totale), 2) AS spesa, COUNT(*) AS righe
        FROM base
        GROUP BY COALESCE(categoria, '—')
        ORDER BY SUM(totale) DESC
        LIMIT 5
    )
    SELECT jsonb_build_object(
        'kpi', jsonb_build_object(
            'fatture_uniche',       (SELECT fatture_uniche FROM kpi),
            'righe_totali',         (SELECT righe_totali FROM kpi),
            'spesa_totale',         ROUND((SELECT spesa_totale FROM kpi), 2),
            'spesa_mese_corrente',  ROUND((SELECT spesa_mese_corrente FROM kpi), 2),
            'spesa_mese_precedente',ROUND((SELECT spesa_mese_precedente FROM kpi), 2),
            'prima_fattura',        (SELECT prima_fattura FROM kpi),
            'ultima_fattura',       (SELECT ultima_fattura FROM kpi)
        ),
        'spesa_mensile', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('mese', mese_key, 'spesa', spesa))
            FROM per_mese_asc
        ), '[]'::jsonb),
        'top_fornitori', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('nome', nome, 'spesa', spesa, 'righe', righe))
            FROM per_fornitore
        ), '[]'::jsonb),
        'top_categorie', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('nome', nome, 'spesa', spesa, 'righe', righe))
            FROM per_categoria
        ), '[]'::jsonb)
    )
    INTO v_result;
    RETURN v_result;
END;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_peso_categoria(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
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
          AND NOT f.oscurata
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


CREATE OR REPLACE FUNCTION public.gruppo_salute_componenti(p_ristorante_ids uuid[], p_inizio timestamp with time zone, p_anno integer, p_mese integer)
 RETURNS TABLE(ristorante_id uuid, n_fatture bigint, n_needs_review bigint, netto numeric, personale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH f AS (
        SELECT fa.ristorante_id AS rid,
               count(*) AS n_fatture,
               count(*) FILTER (WHERE fa.needs_review) AS n_needs_review
        FROM fatture fa
        WHERE fa.ristorante_id = ANY(p_ristorante_ids)
          AND fa.deleted_at IS NULL
          AND NOT fa.oscurata
          AND fa.created_at >= p_inizio
        GROUP BY fa.ristorante_id
    ),
    m AS (
        SELECT mm.ristorante_id AS rid,
               sum(coalesce(mm.fatturato_iva10, 0) + coalesce(mm.fatturato_iva22, 0)
                   + coalesce(mm.altri_ricavi_noiva, 0)) AS netto,
               sum(coalesce(mm.costo_dipendenti, 0) + coalesce(mm.costo_personale_extra, 0)) AS personale
        FROM margini_mensili mm
        WHERE mm.ristorante_id = ANY(p_ristorante_ids)
          AND mm.anno = p_anno AND mm.mese = p_mese
        GROUP BY mm.ristorante_id
    )
    SELECT r AS ristorante_id,
           coalesce(f.n_fatture, 0)::bigint AS n_fatture,
           coalesce(f.n_needs_review, 0)::bigint AS n_needs_review,
           coalesce(m.netto, 0)::numeric AS netto,
           coalesce(m.personale, 0)::numeric AS personale
    FROM unnest(p_ristorante_ids) AS r
    LEFT JOIN f ON f.rid = r
    LEFT JOIN m ON m.rid = r;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_spesa_pivot(p_ristorante_ids uuid[], p_dimensione text, p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
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
      AND NOT f.oscurata
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.totale_riga > 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, dim_val;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_spreco_fb_categorie(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
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
      AND NOT f.oscurata
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


CREATE OR REPLACE FUNCTION public.gruppo_tag_analisi(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
 RETURNS TABLE(ristorante_id uuid, spesa numeric, spesa_prezzo_valido numeric, quantita numeric, n_righe bigint, n_fornitori bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        sum(f.totale_riga) AS spesa,
        sum(f.totale_riga) FILTER (WHERE f.prezzo_unitario > 0) AS spesa_prezzo_valido,
        sum(CASE WHEN f.quantita > 0 THEN f.quantita ELSE 0 END) AS quantita,
        count(*)::bigint AS n_righe,
        count(DISTINCT f.fornitore)::bigint AS n_fornitori
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND NOT f.oscurata
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_tag_descrizioni(p_ristorante_ids uuid[], p_q text DEFAULT NULL::text, p_limit integer DEFAULT 500, p_escludi_da_verificare boolean DEFAULT false)
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
      AND NOT f.oscurata
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.descrizione IS NOT NULL
      AND btrim(f.descrizione) <> ''
      AND (p_q IS NULL OR btrim(p_q) = '' OR f.descrizione ILIKE '%' || btrim(p_q) || '%')
    GROUP BY descrizione_key
    ORDER BY spesa DESC NULLS LAST
    LIMIT p_limit;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_tag_fornitori(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
 RETURNS TABLE(fornitore text, spesa numeric, n_righe bigint)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        COALESCE(NULLIF(btrim(f.fornitore), ''), '—') AS fornitore,
        sum(f.totale_riga) AS spesa,
        count(*)::bigint AS n_righe
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND NOT f.oscurata
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1
    ORDER BY spesa DESC NULLS LAST
    LIMIT 20;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_tag_trend(p_ristorante_ids uuid[], p_descrizione_keys text[], p_data_da date, p_data_a date)
 RETURNS TABLE(anno integer, mese integer, spesa numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        extract(year  FROM COALESCE(f.data_competenza, f.data_documento))::int AS anno,
        extract(month FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND NOT f.oscurata
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1, 2
    ORDER BY 1, 2;
$function$;
