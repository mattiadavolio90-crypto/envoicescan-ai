-- Aggiunge nuovi_da a ristoranti: timestamp dal quale i prodotti sono considerati "Nuovo".
-- Viene aggiornato all'inizio di ogni sessione di caricamento fatture.
ALTER TABLE ristoranti ADD COLUMN IF NOT EXISTS nuovi_da timestamptz;
