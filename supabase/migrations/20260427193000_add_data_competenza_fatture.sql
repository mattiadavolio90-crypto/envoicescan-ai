-- Aggiunge data di competenza gestionale alle fatture.
-- Non sostituisce la data documento fiscale: serve solo per reportistica interna.

ALTER TABLE public.fatture
ADD COLUMN IF NOT EXISTS data_competenza date;
