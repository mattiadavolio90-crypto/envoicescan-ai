-- Sync CLI migration for TD24 data_consegna rollout
-- Mirrors the application-side migration 056_add_data_consegna.sql

ALTER TABLE fatture
ADD COLUMN IF NOT EXISTS data_consegna DATE;

-- Colonna tracking alert data_consegna sugli eventi di upload.
-- Valori: 'ok' | 'warning' | 'missing' | NULL (non TD24).
ALTER TABLE upload_events
ADD COLUMN IF NOT EXISTS alert_data_consegna TEXT;

-- Indice parziale: solo TD24 con data_consegna presente (per query admin)
CREATE INDEX IF NOT EXISTS idx_fatture_td24_data_consegna
ON fatture (user_id, tipo_documento, data_consegna)
WHERE tipo_documento = 'TD24';
