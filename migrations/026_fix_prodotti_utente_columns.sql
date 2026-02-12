-- ========================================
-- MIGRAZIONE 026: FIX COLONNE MANCANTI prodotti_utente
-- ========================================
-- La tabella esiste già ma mancano alcune colonne definite nella migrazione 006.
-- ALTER TABLE aggiunge le colonne mancanti in modo sicuro.

-- Aggiungi volte_visto se non esiste
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'prodotti_utente' AND column_name = 'volte_visto'
    ) THEN
        ALTER TABLE prodotti_utente ADD COLUMN volte_visto INTEGER DEFAULT 1;
        RAISE NOTICE 'Colonna volte_visto aggiunta';
    ELSE
        RAISE NOTICE 'Colonna volte_visto già presente';
    END IF;
END $$;

-- Aggiungi classificato_da se non esiste
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'prodotti_utente' AND column_name = 'classificato_da'
    ) THEN
        ALTER TABLE prodotti_utente ADD COLUMN classificato_da TEXT;
        RAISE NOTICE 'Colonna classificato_da aggiunta';
    ELSE
        RAISE NOTICE 'Colonna classificato_da già presente';
    END IF;
END $$;

-- Aggiungi updated_at se non esiste
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'prodotti_utente' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE prodotti_utente ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
        RAISE NOTICE 'Colonna updated_at aggiunta';
    ELSE
        RAISE NOTICE 'Colonna updated_at già presente';
    END IF;
END $$;

-- Verifica finale
SELECT column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'prodotti_utente'
ORDER BY ordinal_position;
