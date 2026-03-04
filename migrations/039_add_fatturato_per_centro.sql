-- ============================================================
-- MIGRATION 039: Aggiungi fatturato suddiviso per centro di produzione
-- ============================================================
-- Aggiunge colonne per salvare la ripartizione del fatturato
-- netto per centro (FOOD, BAR, ALCOLICI, DOLCI).
-- Il Materiale di Consumo non ha fatturato proprio.
-- ============================================================

ALTER TABLE margini_mensili
ADD COLUMN IF NOT EXISTS fatturato_food NUMERIC(12,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS fatturato_bar NUMERIC(12,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS fatturato_alcolici NUMERIC(12,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS fatturato_dolci NUMERIC(12,2) DEFAULT 0;

COMMENT ON COLUMN margini_mensili.fatturato_food IS 'Fatturato netto attribuito al centro FOOD';
COMMENT ON COLUMN margini_mensili.fatturato_bar IS 'Fatturato netto attribuito al centro BAR';
COMMENT ON COLUMN margini_mensili.fatturato_alcolici IS 'Fatturato netto attribuito al centro ALCOLICI';
COMMENT ON COLUMN margini_mensili.fatturato_dolci IS 'Fatturato netto attribuito al centro DOLCI';
