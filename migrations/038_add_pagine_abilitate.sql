-- Migration 038: Aggiunge colonna pagine_abilitate alla tabella users
-- Permette all'admin di abilitare/disabilitare pagine per ogni cliente
-- Default: tutte abilitate (marginalita + workspace)
-- Analisi Fatture è sempre attiva e non è inclusa nel toggle

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS pagine_abilitate JSONB 
DEFAULT '{"marginalita": true, "workspace": true}'::jsonb;

-- Aggiorna tutti gli utenti esistenti che hanno null
UPDATE users 
SET pagine_abilitate = '{"marginalita": true, "workspace": true}'::jsonb 
WHERE pagine_abilitate IS NULL;
