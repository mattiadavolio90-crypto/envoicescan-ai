-- ============================================================
-- MIGRATION 042: Rimuovi vincolo UNIQUE su ristoranti.partita_iva
-- ============================================================
-- Motivo: L'admin deve poter creare una replica del ristorante di un cliente
-- (stessa P.IVA) per testare l'app prima del cliente.
-- La validazione duplicati è gestita a livello applicativo per i clienti normali.
-- Data: 2026-03-10
-- ============================================================

BEGIN;

-- 1. Rimuovi UNIQUE constraint dalla tabella ristoranti
ALTER TABLE ristoranti DROP CONSTRAINT IF EXISTS ristoranti_partita_iva_key;

-- 2. Rimuovi UNIQUE constraint dalla tabella users
--    (admin può avere stessa P.IVA di un cliente per replica di test)
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_partita_iva_unique;

-- 3. L'indice idx_ristoranti_piva (non-unique) rimane per performance
-- Se era stato creato come unique, ricrealo come non-unique
DROP INDEX IF EXISTS idx_ristoranti_piva;
CREATE INDEX idx_ristoranti_piva ON ristoranti(partita_iva);

-- 4. Assicurati che l'indice su users.partita_iva esista come non-unique
DROP INDEX IF EXISTS idx_users_partita_iva;
CREATE INDEX idx_users_partita_iva ON users(partita_iva) WHERE partita_iva IS NOT NULL;

COMMIT;

-- ============================================================
-- VERIFICA POST-MIGRAZIONE
-- ============================================================
-- SELECT conname, contype FROM pg_constraint
-- WHERE conrelid = 'ristoranti'::regclass;
