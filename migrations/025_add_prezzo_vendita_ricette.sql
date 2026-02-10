-- ============================================================
-- MIGRATION 025: Aggiunta prezzo di vendita alle ricette
-- ============================================================
-- Aggiunge colonna prezzo_vendita_ivainc (IVA 10% inclusa)
-- per calcolo margine e incidenza % food cost

ALTER TABLE ricette 
ADD COLUMN IF NOT EXISTS prezzo_vendita_ivainc NUMERIC(10,2) DEFAULT NULL;

-- Commento esplicativo
COMMENT ON COLUMN ricette.prezzo_vendita_ivainc IS 'Prezzo di vendita al pubblico IVA 10% inclusa. Usato per calcolo margine e incidenza food cost.';
