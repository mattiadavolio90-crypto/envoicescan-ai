-- ═══════════════════════════════════════════════════════════════════════════════
-- Fix: costi_automatici_mensili[_gruppo] classificavano FOOD via whitelist chiusa
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: audit Bug su services/routers/margini.py (2026-08-05). Le due RPC
-- classificavano una riga come FOOD solo se categoria = ANY(p_cat_food) (whitelist
-- esplicita, oggi CATEGORIE_FOOD ~25 voci). Il fallback pandas
-- (margine_service.calcola_costi_automatici_per_anno) e la pagina Margini
-- (_calcola_costi_auto_per_mese/_per_periodo in fastapi_worker.py) usano invece un
-- CATCH-ALL: FOOD = ogni riga che non è Spese Generali e non è NOTE E DICITURE.
-- Una categoria fuori da entrambe le liste (categoria legacy non migrata, drift
-- futuro tra config/constants.py e le categorie realmente scritte) spariva
-- silenziosamente dal MOL solo quando risponde la RPC, mentre il fallback pandas la
-- contava come food — due percorsi diversi sullo stesso dato.
--
-- Fix: la RPC diventa catch-all come il fallback pandas. p_cat_food resta nella
-- firma (per compatibilità con i chiamanti Python esistenti) ma non è più usato
-- per il filtro FOOD, solo p_cat_spese (whitelist Spese Generali, intenzionalmente
-- chiusa) e l'esclusione esplicita di NOTE E DICITURE.
--
-- CREATE OR REPLACE: ridefinisce le funzioni senza toccare le migration originali
-- (20260617193347_rpc_costi_automatici_mensili.sql,
--  20260716095400_rpc_costi_automatici_gruppo.sql,
--  20260714150000_riparto_anti_doppio_conteggio.sql). Firme invariate.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION costi_automatici_mensili(
    p_user_id uuid,
    p_ristorante_id uuid,
    p_anno int,
    p_cat_food text[],
    p_cat_spese text[]
)
RETURNS TABLE (mese int, food numeric, spese numeric)
LANGUAGE sql
STABLE
AS $$
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
$$;

CREATE OR REPLACE FUNCTION costi_automatici_mensili_gruppo(
    p_user_id uuid,
    p_ristorante_ids uuid[],
    p_anno int,
    p_cat_food text[],
    p_cat_spese text[]
)
RETURNS TABLE (ristorante_id uuid, mese int, food numeric, spese numeric)
LANGUAGE sql
STABLE
AS $$
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
$$;
