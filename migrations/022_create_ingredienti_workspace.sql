-- ============================================
-- MIGRATION 022: Tabella Ingredienti Workspace
-- ============================================
-- Permette agli utenti di creare ingredienti manuali
-- per ricette quando non hanno ancora fatture/prodotti reali
-- Questi ingredienti rimangono ISOLATI nella sezione Workspace

-- 1. Crea tabella ingredienti_workspace
CREATE TABLE IF NOT EXISTS ingredienti_workspace (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    userid UUID NOT NULL,
    ristorante_id UUID REFERENCES ristoranti(id) ON DELETE CASCADE,
    nome VARCHAR(255) NOT NULL,
    prezzo_per_um DECIMAL(10,4) NOT NULL,
    um VARCHAR(20) NOT NULL DEFAULT 'KG',
    categoria VARCHAR(100),
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Indici per performance
CREATE INDEX IF NOT EXISTS idx_ingredienti_workspace_userid 
    ON ingredienti_workspace(userid);
CREATE INDEX IF NOT EXISTS idx_ingredienti_workspace_ristorante 
    ON ingredienti_workspace(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_ingredienti_workspace_nome 
    ON ingredienti_workspace(nome);

-- 3. Vincolo unicità: stesso utente/ristorante non può avere due ingredienti con stesso nome
CREATE UNIQUE INDEX IF NOT EXISTS idx_ingredienti_workspace_unique_nome 
    ON ingredienti_workspace(userid, LOWER(nome)) 
    WHERE ristorante_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ingredienti_workspace_unique_nome_rist 
    ON ingredienti_workspace(userid, ristorante_id, LOWER(nome)) 
    WHERE ristorante_id IS NOT NULL;

-- 4. RLS Policies
ALTER TABLE ingredienti_workspace ENABLE ROW LEVEL SECURITY;

-- Policy SELECT: utente vede solo i propri ingredienti
DROP POLICY IF EXISTS "ingredienti_workspace_select_policy" ON ingredienti_workspace;
CREATE POLICY "ingredienti_workspace_select_policy" ON ingredienti_workspace
    FOR SELECT USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy INSERT: utente può inserire solo per sé
DROP POLICY IF EXISTS "ingredienti_workspace_insert_policy" ON ingredienti_workspace;
CREATE POLICY "ingredienti_workspace_insert_policy" ON ingredienti_workspace
    FOR INSERT WITH CHECK (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy UPDATE: utente può modificare solo i propri
DROP POLICY IF EXISTS "ingredienti_workspace_update_policy" ON ingredienti_workspace;
CREATE POLICY "ingredienti_workspace_update_policy" ON ingredienti_workspace
    FOR UPDATE USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy DELETE: utente può eliminare solo i propri
DROP POLICY IF EXISTS "ingredienti_workspace_delete_policy" ON ingredienti_workspace;
CREATE POLICY "ingredienti_workspace_delete_policy" ON ingredienti_workspace
    FOR DELETE USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- 5. Trigger per updated_at automatico
CREATE OR REPLACE FUNCTION update_ingredienti_workspace_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_ingredienti_workspace_timestamp ON ingredienti_workspace;
CREATE TRIGGER trigger_update_ingredienti_workspace_timestamp
    BEFORE UPDATE ON ingredienti_workspace
    FOR EACH ROW
    EXECUTE FUNCTION update_ingredienti_workspace_timestamp();

-- 6. Commenti
COMMENT ON TABLE ingredienti_workspace IS 'Ingredienti manuali creati dall''utente per uso esclusivo nel Workspace Ricette. Non derivano da fatture.';
COMMENT ON COLUMN ingredienti_workspace.nome IS 'Nome ingrediente personalizzato';
COMMENT ON COLUMN ingredienti_workspace.prezzo_per_um IS 'Prezzo stimato per unità di misura (KG/LT/PZ)';
COMMENT ON COLUMN ingredienti_workspace.um IS 'Unità di misura (KG, LT, PZ, etc.)';

-- 7. Grant permissions
GRANT ALL ON ingredienti_workspace TO authenticated;
GRANT ALL ON ingredienti_workspace TO service_role;
