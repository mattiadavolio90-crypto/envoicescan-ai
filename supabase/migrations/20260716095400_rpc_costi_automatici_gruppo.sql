-- ═══════════════════════════════════════════════════════════════════════════════
-- RPC: costi automatici food/spese per (ristorante, mese) su un GRUPPO di sedi
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: la Sintesi di catena (gruppo_overview) leggeva lo SNAPSHOT
-- margini_mensili.costi_fb_totali / mol, che è popolato solo quando qualcuno
-- salva la pagina Margini di ogni sede (POST /api/margini o cella). Per un cliente
-- appena partito lo snapshot è a 0 → la Sintesi mostrava costi/MOL a zero mentre la
-- pagina Margini del PV, che ricalcola LIVE, mostrava i numeri veri: due MOL diversi.
--
-- Questa RPC porta la Sintesi allo stesso calcolo LIVE delle altre viste, SENZA
-- violare la regola della catena ("aggregazione SQL, mai loop Python sulle righe"):
-- una sola query aggrega i costi auto di TUTTE le sedi del gruppo in un colpo
-- (IN (...) + GROUP BY ristorante_id, mese), invece di N chiamate per sede.
--
-- Replica ESATTAMENTE costi_automatici_mensili (stessa data di riferimento, stessi
-- filtri, stesso split food/spese, stesso anti-doppio-conteggio ripartite): è la
-- stessa logica, allargata a più ristoranti. Le quote_riparto_* e gli altri_costi_*
-- NON entrano qui: restano su margini_mensili (1 riga per sede×mese) e si sommano
-- in Python senza toccare le righe fattura.

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
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_food)), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.ristorante_id, base.mese
    ORDER BY base.ristorante_id, base.mese;
$$;
