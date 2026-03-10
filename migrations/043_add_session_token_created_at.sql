-- Aggiunge colonna per tracciare quando il session token è stato creato
-- Permette di verificare la scadenza server-side (TTL 30 giorni)
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_token_created_at TIMESTAMPTZ;
