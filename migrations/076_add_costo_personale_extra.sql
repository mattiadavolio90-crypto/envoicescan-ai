-- 076: Aggiunge costo_personale_extra a margini_mensili
-- Permette di registrare separatamente i costi extra del personale
-- (straordinari, bonus, collaboratori occasionali, ecc.)
-- Il campo è incluso nel calcolo MOL: MOL = 1°Margine - Spese - Personale_Lordo - Personale_Extra

ALTER TABLE margini_mensili ADD COLUMN IF NOT EXISTS costo_personale_extra NUMERIC DEFAULT 0;
