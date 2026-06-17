-- RPC: pivot spesa per PUNTO VENDITA della modalità catena (finestra "Spesa per PV").
-- Aggregazione SQL pura: GROUP BY ristorante_id + dimensione (categoria|fornitore),
-- SUM(totale_riga). Sostituisce in radice il full-load del PV (_fetch_fatture_rows
-- carica le righe in RAM e cicla in Python): per una catena da N PV sarebbe lo
-- scenario "rallenta/crasha". Qui torna ~15 categorie × N PV, non decine di migliaia
-- di righe.
--
-- Coerente con il resto dell'app:
--   - data di riferimento = COALESCE(data_competenza, data_documento)
--   - filtri: ristorante_id ∈ array, deleted_at IS NULL, categoria <> 'Da Classificare',
--     totale_riga > 0, periodo [p_data_da, p_data_a] sull'effective date
--   - dimensione passata come testo ('categoria' | 'fornitore'); N/D se NULL/vuoto.

CREATE OR REPLACE FUNCTION gruppo_spesa_pivot(
    p_ristorante_ids uuid[],
    p_dimensione text,
    p_data_da date,
    p_data_a date
)
RETURNS TABLE (ristorante_id uuid, dim_val text, totale numeric)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
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
      AND f.totale_riga > 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, dim_val;
$$;

REVOKE ALL ON FUNCTION gruppo_spesa_pivot(uuid[], text, date, date) FROM public, anon, authenticated;
