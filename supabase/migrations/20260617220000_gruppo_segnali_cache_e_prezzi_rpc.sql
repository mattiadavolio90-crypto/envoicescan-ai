-- MODALITÀ CATENA — Fase 2: motore segnali.
--
-- 1) Cache giornaliera dei segnali di gruppo (stile daily_briefing_state, ma per
--    ACCOUNT: la catena è una sola, non per-sede). Calcolo 1×/giorno, payload
--    JSON piccolo. Upsert su (user_id, generated_for_date).
-- 2) RPC gruppo_prezzi_categoria: prezzo medio unitario per (ristorante_id,
--    categoria) su una finestra, in SQL (no full-load: torna ~N_categorie×N_PV
--    righe). Serve al segnale "prezzi sopra la media catena".

CREATE TABLE IF NOT EXISTS gruppo_segnali_state (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             text        NOT NULL,
    generated_for_date  date        NOT NULL,
    snapshot            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gruppo_segnali_state_unique
    ON gruppo_segnali_state (user_id, generated_for_date);

ALTER TABLE gruppo_segnali_state ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON gruppo_segnali_state TO service_role;
REVOKE ALL ON gruppo_segnali_state FROM anon;
REVOKE ALL ON gruppo_segnali_state FROM authenticated;

COMMENT ON TABLE gruppo_segnali_state IS
    'Snapshot giornaliero dei segnali della modalità catena, per ACCOUNT. '
    'Upsert su (user_id, generated_for_date). service_role (bypassa RLS).';


-- Prezzo medio unitario per (ristorante_id, categoria) su [p_data_da, p_data_a].
-- Pesato per quantità (Σ totale_riga / Σ quantità) quando la quantità è valida,
-- così il "prezzo medio" non è distorto dalle righe a quantità anomala; ricade
-- sulla media semplice di prezzo_unitario se la quantità non è utilizzabile.
-- Solo righe con prezzo_unitario > 0, deleted_at IS NULL, categoria reale.
CREATE OR REPLACE FUNCTION gruppo_prezzi_categoria(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date
)
RETURNS TABLE (ristorante_id uuid, categoria text, prezzo_medio numeric, n_righe bigint)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
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
      AND f.prezzo_unitario > 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, f.categoria;
$$;

REVOKE ALL ON FUNCTION gruppo_prezzi_categoria(uuid[], date, date) FROM public, anon, authenticated;
