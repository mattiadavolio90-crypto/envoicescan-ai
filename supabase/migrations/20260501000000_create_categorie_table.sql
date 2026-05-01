-- ============================================================
-- MIGRATION: Crea tabella categorie con icone emoji
-- Data: 2026-05-01
-- Descrizione: Tabella per icone/ordinamento categorie
--   aggiungi_icona_categoria() in text_utils.py usa questa tabella.
--   Categorie allineate a config/constants.py (TUTTE_LE_CATEGORIE).
-- ============================================================

CREATE TABLE IF NOT EXISTS public.categorie (
    id          BIGSERIAL PRIMARY KEY,
    nome        TEXT NOT NULL UNIQUE,
    icona       TEXT NOT NULL DEFAULT '📦',
    ordinamento INTEGER NOT NULL DEFAULT 999,
    attiva      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_categorie_attiva       ON public.categorie (attiva);
CREATE INDEX IF NOT EXISTS idx_categorie_ordinamento  ON public.categorie (ordinamento);

-- RLS
ALTER TABLE public.categorie ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "categorie_select_all"  ON public.categorie;
DROP POLICY IF EXISTS "categorie_write_admin" ON public.categorie;

-- Tutti leggono (app usa service_role che bypassa RLS comunque)
CREATE POLICY "categorie_select_all"
    ON public.categorie FOR SELECT USING (true);

-- Scrittura solo via service_role (bypass automatico)
CREATE POLICY "categorie_write_admin"
    ON public.categorie FOR ALL USING (false);

GRANT SELECT ON public.categorie TO anon;
GRANT SELECT ON public.categorie TO authenticated;
GRANT ALL    ON public.categorie TO service_role;

-- ============================================================
-- POPOLAMENTO — categorie da TUTTE_LE_CATEGORIE (constants.py)
-- Allineato a CATEGORIE_FOOD_BEVERAGE + CATEGORIE_SPESE_GENERALI
-- ============================================================
INSERT INTO public.categorie (nome, icona, ordinamento, attiva) VALUES
    -- Food (CENTRI_DI_PRODUZIONE FOOD)
    ('CARNE',               '🍖', 10,  TRUE),
    ('PESCE',               '🐟', 20,  TRUE),
    ('LATTICINI',           '🧀', 30,  TRUE),
    ('SALUMI',              '🥓', 40,  TRUE),
    ('UOVA',                '🥚', 50,  TRUE),
    ('SCATOLAME E CONSERVE','🥫', 60,  TRUE),
    ('OLIO E CONDIMENTI',   '🫒', 70,  TRUE),
    ('PASTA E CEREALI',     '🍝', 80,  TRUE),
    ('VERDURE',             '🥬', 90,  TRUE),
    ('FRUTTA',              '🍎', 100, TRUE),
    ('SALSE E CREME',       '🧂', 110, TRUE),
    ('PRODOTTI DA FORNO',   '🍞', 120, TRUE),
    ('SPEZIE E AROMI',      '🌿', 130, TRUE),
    ('SUSHI VARIE',         '🍣', 140, TRUE),

    -- Beverage (CENTRI_DI_PRODUZIONE BEVERAGE)
    ('ACQUA',               '💧', 200, TRUE),
    ('BEVANDE',             '🥤', 210, TRUE),
    ('CAFFE E THE',         '☕', 220, TRUE),
    ('VARIE BAR',           '🍹', 230, TRUE),

    -- Alcolici (CENTRI_DI_PRODUZIONE ALCOLICI)
    ('BIRRE',               '🍺', 300, TRUE),
    ('VINI',                '🍷', 310, TRUE),
    ('DISTILLATI',          '🥃', 320, TRUE),
    ('AMARI/LIQUORI',       '🍸', 330, TRUE),

    -- Dolci (CENTRI_DI_PRODUZIONE DOLCI)
    ('PASTICCERIA',         '🍰', 400, TRUE),
    ('GELATI E DESSERT',    '🍦', 410, TRUE),

    -- Shop
    ('SHOP',                '🛍️', 500, TRUE),

    -- Spese generali
    ('MATERIALE DI CONSUMO',        '🧴', 900, TRUE),
    ('SERVIZI E CONSULENZE',        '🧾', 910, TRUE),
    ('UTENZE E LOCALI',             '🏠', 920, TRUE),
    ('MANUTENZIONE E ATTREZZATURE', '🔧', 930, TRUE),

    -- Speciali
    ('📝 NOTE E DICITURE', '📝', 990, TRUE),
    ('Da Classificare',    '❓', 999, TRUE)

ON CONFLICT (nome) DO NOTHING;

COMMENT ON TABLE  public.categorie          IS 'Categorie prodotti con icone emoji — gestite via pannello admin';
COMMENT ON COLUMN public.categorie.nome     IS 'Nome categoria (case-sensitive, come in constants.py)';
COMMENT ON COLUMN public.categorie.icona    IS 'Emoji icona (1-2 caratteri)';
COMMENT ON COLUMN public.categorie.attiva   IS 'FALSE = categoria disabilitata (soft delete)';
