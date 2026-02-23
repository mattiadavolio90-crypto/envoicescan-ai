-- ============================================================
-- MIGRATION 028: Aggiungi colonna altri_ricavi_noiva
-- ============================================================
-- Aggiunge campo per Altri ricavi (no iva) che viene sommato a
-- Fatt. IVA 10% e Fatt. IVA 22% per calcolare il Fatturato Netto
-- ============================================================

ALTER TABLE margini_mensili
ADD COLUMN IF NOT EXISTS altri_ricavi_noiva NUMERIC(10,2) DEFAULT 0;

COMMENT ON COLUMN margini_mensili.altri_ricavi_noiva IS 'Altri ricavi senza IVA (input manuale)';
