-- ========================================
-- 🧠 AGGIUNGI COLONNA STATO per tracciamento AI
-- ========================================
-- Esegui questo script su Supabase Dashboard → SQL Editor

-- Verifica se la colonna esiste già
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'fatture' 
        AND column_name = 'stato'
    ) THEN
        -- Aggiungi colonna stato (vuota di default)
        ALTER TABLE fatture 
        ADD COLUMN stato TEXT DEFAULT '';
        
        RAISE NOTICE '✅ Colonna "stato" aggiunta con successo';
    ELSE
        RAISE NOTICE 'ℹ️ Colonna "stato" già esistente';
    END IF;
END $$;

-- Crea indice per performance (opzionale ma consigliato)
CREATE INDEX IF NOT EXISTS idx_fatture_stato ON fatture(stato);

-- Verifica risultato
SELECT 
    column_name, 
    data_type, 
    column_default,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'fatture' 
AND column_name = 'stato';
