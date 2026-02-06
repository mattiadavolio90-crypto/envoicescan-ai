-- ============================================
-- MIGRATION 020: Fix Foreign Key Ricette
-- ============================================
-- Corregge il foreign key della tabella ricette
-- da auth.users(id) a users(id) perché l'app
-- usa autenticazione custom, non Supabase Auth

-- 1. Rimuovi vecchio constraint
ALTER TABLE ricette 
DROP CONSTRAINT IF EXISTS ricette_userid_fkey;

-- 2. Aggiungi nuovo constraint su tabella users custom
ALTER TABLE ricette
ADD CONSTRAINT ricette_userid_fkey 
FOREIGN KEY (userid) 
REFERENCES users(id) 
ON DELETE CASCADE;

-- 3. Verifica integrità dati esistenti
-- (opzionale - solo per verificare che tutti gli userid esistano in users)
DO $$
DECLARE
    orphan_count INT;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM ricette r
    LEFT JOIN users u ON r.userid = u.id
    WHERE u.id IS NULL;
    
    IF orphan_count > 0 THEN
        RAISE NOTICE 'ATTENZIONE: Trovate % righe ricette con userid non valido', orphan_count;
    ELSE
        RAISE NOTICE 'OK: Tutti gli userid in ricette sono validi';
    END IF;
END $$;
