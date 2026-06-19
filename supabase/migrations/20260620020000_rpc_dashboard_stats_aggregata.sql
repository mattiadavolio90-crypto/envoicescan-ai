-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: RPC dashboard_stats_aggregata — aggregazione SQL per la Home
-- ═══════════════════════════════════════════════════════════════════════════════
-- PERFORMANCE: /api/dashboard/stats faceva full-load di TUTTE le righe fattura del
-- ristorante (LAND: 6.315 righe in 7 query paginate da 1000) + aggregazione in
-- Python a ogni apertura Home (cache TTL 60s). Su Railway = 1-3s a freddo, e
-- cresce col tempo. Questa RPC fa la STESSA aggregazione lato DB in una query:
-- spesa totale/mese corrente/precedente, spesa per mese (ultimi 12), top 5
-- fornitori, top 5 categorie, fatture uniche, prima/ultima data.
--
-- Replica fedele della logica Python (services/fastapi_worker.py dashboard_stats):
--   - fornitore/categoria: trim + fallback '—' se vuoto/null
--   - mese corrente/precedente sul fuso Europe/Rome (come _oggi_rome)
--   - ultimi 12 mesi con dati, ordinati
--   - top 5 per spesa desc
--
-- Guardia ownership coerente con le altre RPC (auth custom: uid()=NULL → inerte
-- per anon; l'app chiama via service_role). SET search_path fisso. EXECUTE solo
-- a service_role.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.dashboard_stats_aggregata(
    p_user_id uuid,
    p_ristorante_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
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

REVOKE ALL ON FUNCTION public.dashboard_stats_aggregata(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.dashboard_stats_aggregata(uuid, uuid) TO service_role;
