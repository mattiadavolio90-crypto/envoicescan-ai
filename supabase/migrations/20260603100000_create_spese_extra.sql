-- ============================================================
-- MIGRATION: Spese extra (F&B e Generali) — dettaglio analitico
-- ============================================================
-- Gemella di turni_personale: raccoglie le singole voci di spesa extra
-- (non da fattura) che il ristoratore inserisce a mano dal tab "Agenda e Spese".
-- Un endpoint aggrega per mese e tipo, alimentando le celle editabili di
-- margini_mensili: tipo='fb' -> altri_costi_fb, tipo='generale' -> altri_costi_spese.
-- margini_mensili resta l'unica fonte di verità del totale mensile.

CREATE TABLE IF NOT EXISTS spese_extra (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ristorante_id   UUID NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,
    data_spesa      DATE NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('fb', 'generale')),
    importo         NUMERIC(10, 2) NOT NULL CHECK (importo >= 0),
    descrizione     TEXT NOT NULL,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spese_extra_ristorante ON spese_extra(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_spese_extra_data ON spese_extra(ristorante_id, data_spesa);
CREATE INDEX IF NOT EXISTS idx_spese_extra_tipo ON spese_extra(ristorante_id, tipo);

ALTER TABLE spese_extra ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "spese_extra_all_service_role" ON spese_extra;
CREATE POLICY "spese_extra_all_service_role" ON spese_extra
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE spese_extra IS 'Voci di spesa extra (non da fattura) inserite a mano: tipo fb/generale, aggregate per mese in margini_mensili.';
COMMENT ON COLUMN spese_extra.tipo IS 'fb = Altri Costi F&B; generale = Altre Spese Generali.';
COMMENT ON COLUMN spese_extra.importo IS 'Importo della voce in EUR (>= 0).';
