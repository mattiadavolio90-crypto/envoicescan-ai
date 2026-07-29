-- fatture.sconto_percentuale: double precision -> numeric(5,2)
-- Coerenza di tipo con gli altri campi percentuali/importo della tabella
-- (es. iva_percentuale). Valore sempre arrotondato a 2 decimali in Python
-- (services/invoice_service.py), range 0-100 salvo maggiorazioni negative.
ALTER TABLE fatture
ALTER COLUMN sconto_percentuale TYPE numeric(6,2)
USING ROUND(sconto_percentuale::numeric, 2);

COMMENT ON COLUMN fatture.sconto_percentuale IS 'Sconto percentuale applicato: ((PrezzoBase - PrezzoEffettivo) / PrezzoBase) * 100. Era double precision fino al 29/7/2026.';
