-- Migration 048: Tabella brand_ambigui per rilevazione automatica brand multi-categoria
-- Tiene traccia delle correzioni manuali per brand specifici.
-- Quando un brand accumula >= 3 correzioni su >= 2 categorie diverse con tasso > 20%,
-- viene marcato aggiunto_automaticamente=TRUE ed entra nel bypass del dizionario.

CREATE TABLE IF NOT EXISTS brand_ambigui (
    id                      BIGSERIAL PRIMARY KEY,
    brand                   TEXT NOT NULL,
    num_correzioni          INTEGER NOT NULL DEFAULT 0,
    categorie_viste         TEXT[] NOT NULL DEFAULT '{}',
    tasso_correzione        NUMERIC(6,4) NOT NULL DEFAULT 0,
    aggiunto_automaticamente BOOLEAN NOT NULL DEFAULT FALSE,
    prima_vista             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultima_modifica         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT brand_ambigui_brand_unique UNIQUE (brand)
);

-- Index per lookup rapido
CREATE INDEX IF NOT EXISTS idx_brand_ambigui_aggiunto
    ON brand_ambigui (aggiunto_automaticamente)
    WHERE aggiunto_automaticamente = TRUE;

-- RLS: abilitato, solo service_role può scrivere, authenticated può leggere
ALTER TABLE brand_ambigui ENABLE ROW LEVEL SECURITY;

CREATE POLICY brand_ambigui_service_all ON brand_ambigui
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY brand_ambigui_read ON brand_ambigui
    FOR SELECT
    TO authenticated
    USING (true);

-- Commento sulla tabella
COMMENT ON TABLE brand_ambigui IS
    'Tracking automatico brand multi-categoria. Popolata da salva_correzione_* in ai_service.py.
     Quando num_correzioni >= 3 AND len(categorie_viste) >= 2 AND tasso_correzione > 0.20,
     aggiunto_automaticamente viene impostato a TRUE e il brand bypassa il dizionario keyword.';
