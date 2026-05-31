-- ============================================================
-- MIGRATION: Turni personale — costo orario + ore extra
-- ============================================================
-- costo_orario: costo orario lordo del dipendente per quel turno (opzionale)
-- ore_extra: quota delle ore totali del turno considerate straordinario (sottoinsieme, opzionale)

ALTER TABLE turni_personale
    ADD COLUMN IF NOT EXISTS costo_orario NUMERIC(6, 2),
    ADD COLUMN IF NOT EXISTS ore_extra    NUMERIC(5, 2) DEFAULT 0;

COMMENT ON COLUMN turni_personale.costo_orario IS 'Costo orario lordo del dipendente per il turno (EUR/h). NULL = non impostato.';
COMMENT ON COLUMN turni_personale.ore_extra IS 'Ore di straordinario incluse nelle ore totali del turno (di cui). Default 0.';
