-- Sync CLI migration for fatture header totals
-- Mirrors application migration 064_add_fatture_header_totals.sql

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS totale_documento NUMERIC;

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS totale_imponibile NUMERIC;

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS totale_iva NUMERIC;

COMMENT ON COLUMN fatture.totale_documento IS 'ImportoTotaleDocumento da DatiGeneraliDocumento XML';
COMMENT ON COLUMN fatture.totale_imponibile IS 'Somma ImponibileImporto da DatiRiepilogo XML';
COMMENT ON COLUMN fatture.totale_iva IS 'Somma Imposta da DatiRiepilogo XML';
