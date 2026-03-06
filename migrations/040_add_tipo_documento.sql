-- ============================================================
-- MIGRATION 040: Aggiungi colonna Tipo Documento
-- ============================================================
-- Descrizione: Aggiunge la colonna "tipo_documento" per distinguere
--              fatture (TD01) da note di credito (TD04) e altri tipi.
--              Questo permette di invertire i segni per le note di credito
--              e calcolare correttamente i costi nel MOL.
-- Data: 2026-03-06
-- ============================================================

-- Aggiungi colonna tipo_documento
ALTER TABLE fatture 
ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(4) DEFAULT 'TD01';

-- Commento colonna
COMMENT ON COLUMN fatture.tipo_documento IS 'Tipo documento XML: TD01=Fattura, TD02=Acconto, TD04=Nota Credito, TD05=Nota Debito, TD06=Parcella';

-- Indice per query filtrate per tipo documento
CREATE INDEX IF NOT EXISTS idx_fatture_tipo_documento ON fatture(tipo_documento);

-- Verifica colonna creata
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'fatture' 
AND column_name = 'tipo_documento';
