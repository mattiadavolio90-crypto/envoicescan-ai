-- Allinea la classificazione food della RPC costi_automatici_mensili alla pagina
-- Margini (_calcola_costi_auto_per_periodo): FOOD = ogni costo che NON è una
-- categoria di spese generali e non è "NOTE E DICITURE" (catch-all).
--
-- Prima la RPC (e la funzione pandas calcola_costi_automatici_per_anno) usavano
-- la lista esplicita delle 25 categorie food (p_cat_food). Questo SOTTOSTIMAVA il
-- food per i clienti col vocabolario legacy (VERDURE, LATTICINI, SUSHI VARIE,
-- BEVANDE, CAFFE E THE…): quelle righe non erano né food né spese -> food ~0,
-- MOL gonfiato, e la card KPI della Home divergeva dalla pagina Margini (che usa
-- il catch-all). Caso reale: CASATI 14, maggio 2026 -> RPC food 430€ vs Margini
-- 2068€. Dopo il fix la RPC torna 2067.85€, identico a Margini.
--
-- Firma INVARIATA (p_cat_food resta ma è IGNORATO) per non toccare il chiamante
-- calcola_costi_automatici_per_anno_sql.
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
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(f.data_competenza, f.data_documento)) = p_anno
    )
    SELECT
        base.mese,
        -- FOOD = catch-all: tutto ciò che non è spese generali né NOTE E DICITURE.
        COALESCE(SUM(base.totale_riga) FILTER (
            WHERE base.categoria <> ALL(p_cat_spese)
              AND base.categoria <> '📝 NOTE E DICITURE'
        ), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.mese
    ORDER BY base.mese;
$$;
