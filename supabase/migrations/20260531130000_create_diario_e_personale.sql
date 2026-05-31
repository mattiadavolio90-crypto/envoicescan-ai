-- ============================================================
-- MIGRATION: Diario eventi + Turni personale
-- ============================================================

-- -------------------------------------------------------
-- 1. DIARIO EVENTI
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS diario_eventi (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ristorante_id   UUID NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,
    data_evento     DATE NOT NULL,
    ora_inizio      TIME,
    ora_fine        TIME,
    titolo          TEXT NOT NULL,
    descrizione     TEXT,
    colore          TEXT DEFAULT 'sky',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diario_eventi_ristorante ON diario_eventi(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_diario_eventi_data ON diario_eventi(ristorante_id, data_evento);

ALTER TABLE diario_eventi ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "diario_eventi_all_service_role" ON diario_eventi;
CREATE POLICY "diario_eventi_all_service_role" ON diario_eventi
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION update_diario_eventi_timestamp()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_diario_eventi_updated_at ON diario_eventi;
CREATE TRIGGER trg_diario_eventi_updated_at
    BEFORE UPDATE ON diario_eventi
    FOR EACH ROW EXECUTE FUNCTION update_diario_eventi_timestamp();

-- Migra note_diario esistenti come eventi senza orario (data = created_at)
INSERT INTO diario_eventi (ristorante_id, user_id, data_evento, titolo, descrizione, colore, created_at, updated_at)
SELECT
    ristorante_id,
    userid,
    created_at::DATE AS data_evento,
    SUBSTRING(testo FROM 1 FOR 100) AS titolo,
    CASE WHEN LENGTH(testo) > 100 THEN testo ELSE NULL END AS descrizione,
    'gray' AS colore,
    created_at,
    updated_at
FROM note_diario
WHERE ristorante_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------
-- 2. TURNI PERSONALE
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS turni_personale (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ristorante_id   UUID NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,
    nome            TEXT NOT NULL,
    data_turno      DATE NOT NULL,
    ora_inizio      TIME NOT NULL,
    ora_fine        TIME NOT NULL,
    ora_inizio2     TIME,
    ora_fine2       TIME,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_turni_personale_ristorante ON turni_personale(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_turni_personale_data ON turni_personale(ristorante_id, data_turno);
CREATE INDEX IF NOT EXISTS idx_turni_personale_nome ON turni_personale(ristorante_id, nome);

ALTER TABLE turni_personale ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "turni_personale_all_service_role" ON turni_personale;
CREATE POLICY "turni_personale_all_service_role" ON turni_personale
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE diario_eventi IS 'Calendario condiviso per ristorante: eventi, note con data e orario opzionale';
COMMENT ON TABLE turni_personale IS 'Turni personale a nomi liberi: ore per monte ore mensile/settimanale';
