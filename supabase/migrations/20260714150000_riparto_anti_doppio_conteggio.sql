-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: anti-doppio-conteggio delle fatture ripartite sul gruppo
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: PIANO_OPERATIVO_RIPARTIZIONE_COSTI_CATENA.md (Fase 2, §1c).
--
-- Una fattura di struttura ripartita (fatture.ripartita_su_gruppo = TRUE) ha già i
-- suoi € nel costo AUTOMATICO della sede intestataria (quello che entra nel MOL).
-- La sua quota rientra anche via quote_riparto_* (motore riparto_quote_mensili) →
-- doppio conteggio nel MOL. Per evitarlo, le righe ripartite vanno ESCLUSE dal
-- calcolo del COSTO AUTOMATICO (MOL), ovunque avvenga.
--
-- AMBITO PRECISO: si tocca SOLO il calcolo del costo automatico che alimenta il MOL.
--   ✔ costi_automatici_mensili (RPC, pagina Margini / KPI Home) → filtro aggiunto qui
--   ✔ fallback pandas calcola_costi_automatici_per_anno → già aggiornato in
--     services/margine_service.py (.neq('ripartita_su_gruppo', True))
--
-- NON si tocca:
--   ✘ dashboard_stats_aggregata (spesa totale / top fornitori / top categorie della
--     Home) — è la vista DOCUMENTI/SPESA, dove la fattura deve restare INTERA e
--     visibile sulla sede intestataria (piano 1/7 §8: "Analisi Fatture resta grezza,
--     mostra la fattura intera"). Escluderla lì farebbe sparire spesa reale dai
--     totali documentali. Il doppio conteggio riguarda il MOL, non la spesa lorda.
--   ✘ Analisi Fatture (Articoli/Categorie/Fornitori) — stessa ragione.
--
-- CREATE OR REPLACE: ridefinisce la funzione senza toccare la migration originale
-- (20260617193347_rpc_costi_automatici_mensili.sql). Firma invariata.
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
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_food)), 0) AS food,
        COALESCE(SUM(base.totale_riga) FILTER (WHERE base.categoria = ANY(p_cat_spese)), 0) AS spese
    FROM base
    GROUP BY base.mese
    ORDER BY base.mese;
$$;
