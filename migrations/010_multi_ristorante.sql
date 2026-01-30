-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRAZIONE 010: MULTI-RISTORANTE
-- ═══════════════════════════════════════════════════════════════════════════════
-- Obiettivo: 1 USER → N RISTORANTI (ciascuno con P.IVA unica)
-- Data: 2026-01-30
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- ────────────────────────────────────────────────────────────────────────────────
-- 1. TABELLA ristoranti (entità separata con P.IVA)
-- ────────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ristoranti (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    nome_ristorante TEXT NOT NULL,
    partita_iva VARCHAR(11) UNIQUE NOT NULL,
    ragione_sociale TEXT,
    attivo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index per performance
CREATE INDEX IF NOT EXISTS idx_ristoranti_user_id ON ristoranti(user_id);
CREATE INDEX IF NOT EXISTS idx_ristoranti_piva ON ristoranti(partita_iva);

-- ────────────────────────────────────────────────────────────────────────────────
-- 2. TABELLA piva_ristoranti (per utenti multi-ristorante - lookup veloce)
-- ────────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS piva_ristoranti (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ristorante_id UUID NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    piva VARCHAR(11) NOT NULL,
    nome_ristorante TEXT NOT NULL,
    UNIQUE(user_id, ristorante_id)
);

-- Index per performance
CREATE INDEX IF NOT EXISTS idx_piva_ristoranti_user_id ON piva_ristoranti(user_id);
CREATE INDEX IF NOT EXISTS idx_piva_ristoranti_piva ON piva_ristoranti(piva);

-- ────────────────────────────────────────────────────────────────────────────────
-- 3. AGGIUNGI campo piano a users (futuro pricing tiers)
-- ────────────────────────────────────────────────────────────────────────────────
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS piano VARCHAR(20) DEFAULT 'FREE';

COMMENT ON COLUMN users.piano IS 'Piano tariffario: FREE, PRO, ENTERPRISE';

-- ────────────────────────────────────────────────────────────────────────────────
-- 4. MIGRAZIONE DATI ESISTENTI (utenti attuali → 1 ristorante automatico)
-- ────────────────────────────────────────────────────────────────────────────────
INSERT INTO ristoranti (user_id, nome_ristorante, partita_iva, ragione_sociale, attivo)
SELECT 
    id,
    nome_ristorante,
    partita_iva,
    ragione_sociale,
    attivo
FROM users 
WHERE partita_iva IS NOT NULL
  AND partita_iva != ''
  AND NOT EXISTS (
      SELECT 1 FROM ristoranti WHERE ristoranti.user_id = users.id
  );

-- Popola lookup table piva_ristoranti
INSERT INTO piva_ristoranti (user_id, ristorante_id, piva, nome_ristorante)
SELECT 
    r.user_id,
    r.id,
    r.partita_iva,
    r.nome_ristorante
FROM ristoranti r
WHERE NOT EXISTS (
    SELECT 1 FROM piva_ristoranti pr 
    WHERE pr.user_id = r.user_id AND pr.ristorante_id = r.id
);

-- ────────────────────────────────────────────────────────────────────────────────
-- 5. TRIGGER: Sync automatico piva_ristoranti quando cambia ristoranti
-- ────────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION sync_piva_ristoranti()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO piva_ristoranti (user_id, ristorante_id, piva, nome_ristorante)
        VALUES (NEW.user_id, NEW.id, NEW.partita_iva, NEW.nome_ristorante);
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE piva_ristoranti
        SET piva = NEW.partita_iva,
            nome_ristorante = NEW.nome_ristorante
        WHERE ristorante_id = NEW.id;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM piva_ristoranti WHERE ristorante_id = OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_sync_piva_ristoranti
AFTER INSERT OR UPDATE OR DELETE ON ristoranti
FOR EACH ROW EXECUTE FUNCTION sync_piva_ristoranti();

-- ────────────────────────────────────────────────────────────────────────────────
-- 6. RLS POLICIES (Row Level Security)
-- ────────────────────────────────────────────────────────────────────────────────
ALTER TABLE ristoranti ENABLE ROW LEVEL SECURITY;
ALTER TABLE piva_ristoranti ENABLE ROW LEVEL SECURITY;

-- Policy: Utente vede solo i propri ristoranti
DROP POLICY IF EXISTS "User owns restaurants" ON ristoranti;
CREATE POLICY "User owns restaurants" ON ristoranti
FOR ALL USING (user_id IN (
    SELECT id FROM users WHERE id = user_id
));

DROP POLICY IF EXISTS "User owns piva restaurants" ON piva_ristoranti;
CREATE POLICY "User owns piva restaurants" ON piva_ristoranti
FOR ALL USING (user_id IN (
    SELECT id FROM users WHERE id = user_id
));

-- Policy: Admin vede tutto (bypass RLS)
DROP POLICY IF EXISTS "Admin sees all restaurants" ON ristoranti;
CREATE POLICY "Admin sees all restaurants" ON ristoranti
FOR ALL TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM users 
        WHERE users.id = ristoranti.user_id 
           OR users.email = 'mattiadavolio90@gmail.com'
    )
);

DROP POLICY IF EXISTS "Admin sees all piva restaurants" ON piva_ristoranti;
CREATE POLICY "Admin sees all piva restaurants" ON piva_ristoranti
FOR ALL TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM users 
        WHERE users.id = piva_ristoranti.user_id 
           OR users.email = 'mattiadavolio90@gmail.com'
    )
);

-- ────────────────────────────────────────────────────────────────────────────────
-- 7. FUNZIONE HELPER: Conta ristoranti per utente
-- ────────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION conta_ristoranti_utente(p_user_id UUID)
RETURNS INTEGER AS $$
    SELECT COUNT(*)::INTEGER FROM ristoranti WHERE user_id = p_user_id AND attivo = true;
$$ LANGUAGE SQL STABLE;

-- ────────────────────────────────────────────────────────────────────────────────
-- 8. VIEW: Riepilogo utenti con conteggio ristoranti
-- ────────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_users_ristoranti AS
SELECT 
    u.id AS user_id,
    u.email,
    u.nome_ristorante AS nome_utente,
    u.piano,
    COUNT(r.id) AS num_ristoranti,
    ARRAY_AGG(r.nome_ristorante ORDER BY r.created_at) AS ristoranti,
    ARRAY_AGG(r.partita_iva ORDER BY r.created_at) AS piva_list
FROM users u
LEFT JOIN ristoranti r ON r.user_id = u.id AND r.attivo = true
GROUP BY u.id, u.email, u.nome_ristorante, u.piano;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- VERIFICA MIGRAZIONE
-- ═══════════════════════════════════════════════════════════════════════════════
-- Esegui per verificare:
-- SELECT * FROM v_users_ristoranti;
-- SELECT * FROM ristoranti;
-- SELECT * FROM piva_ristoranti;
