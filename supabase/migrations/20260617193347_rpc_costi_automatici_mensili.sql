-- RPC: aggregazione costi food/spese per mese, calcolata in SQL invece che con
-- full-load + pandas in Python (home_kpi era l'endpoint piu' pesante della Home:
-- scaricava tutte le righe fattura dell'anno e aggregava con DataFrame.groupby).
--
-- Replica ESATTAMENTE calcola_costi_automatici_per_anno (services/margine_service.py):
--   - data di riferimento = COALESCE(data_competenza, data_documento)
--   - filtro: user_id, ristorante_id, deleted_at IS NULL, categoria <> 'Da Classificare'
--   - solo l'anno richiesto sull'effective date
--   - split food/spese per appartenenza alle liste categorie (passate come array,
--     cosi' la fonte di verita' resta config/constants.py: la RPC e' generica)
--   - SUM(totale_riga) GROUP BY mese
--
-- Ritorna una riga per mese con i due totali. I mesi senza righe non compaiono
-- (come il dict Python che ha solo i mesi presenti).

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
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_food)), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.mese
    ORDER BY base.mese;
$$;
