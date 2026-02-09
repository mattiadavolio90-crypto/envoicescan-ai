-- ============================================================
-- MIGRATION 022: Aggiunta campo note a tabella ricette
-- ============================================================
-- Permette di aggiungere annotazioni libere alle ricette

-- Aggiungi colonna note
ALTER TABLE ricette 
ADD COLUMN IF NOT EXISTS note TEXT DEFAULT NULL;

-- Commento documentazione
COMMENT ON COLUMN ricette.note IS 'Note libere e annotazioni per la ricetta (opzionale)';
