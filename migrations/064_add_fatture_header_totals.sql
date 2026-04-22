-- ============================================================
-- MIGRATION 064: Totali header fattura su tabella fatture
-- ============================================================
-- Aggiunge 3 colonne per memorizzare i valori dal nodo XML header:
-- - ImportoTotaleDocumento  -> totale_documento
-- - Somma DatiRiepilogo.ImponibileImporto -> totale_imponibile
-- - Somma DatiRiepilogo.Imposta -> totale_iva

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS totale_documento NUMERIC;

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS totale_imponibile NUMERIC;

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS totale_iva NUMERIC;

COMMENT ON COLUMN fatture.totale_documento IS 'ImportoTotaleDocumento da DatiGeneraliDocumento XML';
COMMENT ON COLUMN fatture.totale_imponibile IS 'Somma ImponibileImporto da DatiRiepilogo XML';
COMMENT ON COLUMN fatture.totale_iva IS 'Somma Imposta da DatiRiepilogo XML';

-- Verifica rapida
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'fatture'
  AND column_name IN ('totale_documento', 'totale_imponibile', 'totale_iva')
ORDER BY column_name;
