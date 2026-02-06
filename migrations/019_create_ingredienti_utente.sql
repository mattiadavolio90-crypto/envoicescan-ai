-- ============================================
-- MIGRATION 019: Tabella Ingredienti Utente
-- ============================================
-- Permette agli utenti di gestire i propri ingredienti
-- con prezzi personalizzati, indipendente dalle fatture

-- 1. Crea tabella ingredienti_utente
CREATE TABLE IF NOT EXISTS ingredienti_utente (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    userid UUID NOT NULL,
    ristorante_id UUID REFERENCES ristoranti(id) ON DELETE CASCADE,
    nome VARCHAR(255) NOT NULL,
    um VARCHAR(20) NOT NULL DEFAULT 'KG',  -- KG, LT, PZ, GR, ML
    prezzo_per_um DECIMAL(10,4) NOT NULL,  -- prezzo per unità di misura base
    categoria VARCHAR(100),  -- es. "Latticini", "Verdure", "Carni"
    fornitore VARCHAR(255),  -- opzionale
    note TEXT,
    attivo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Indici per performance
CREATE INDEX IF NOT EXISTS idx_ingredienti_utente_userid 
    ON ingredienti_utente(userid);
CREATE INDEX IF NOT EXISTS idx_ingredienti_utente_ristorante 
    ON ingredienti_utente(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_ingredienti_utente_nome 
    ON ingredienti_utente(nome);
CREATE INDEX IF NOT EXISTS idx_ingredienti_utente_categoria 
    ON ingredienti_utente(categoria);

-- 3. Vincolo unicità: stesso utente non può avere due ingredienti con stesso nome
CREATE UNIQUE INDEX IF NOT EXISTS idx_ingredienti_utente_unique_nome 
    ON ingredienti_utente(userid, LOWER(nome)) 
    WHERE ristorante_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ingredienti_utente_unique_nome_rist 
    ON ingredienti_utente(userid, ristorante_id, LOWER(nome)) 
    WHERE ristorante_id IS NOT NULL;

-- 4. RLS Policies
ALTER TABLE ingredienti_utente ENABLE ROW LEVEL SECURITY;

-- Policy SELECT: utente vede solo i propri ingredienti
DROP POLICY IF EXISTS "ingredienti_utente_select_policy" ON ingredienti_utente;
CREATE POLICY "ingredienti_utente_select_policy" ON ingredienti_utente
    FOR SELECT USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy INSERT: utente può inserire solo per sé
DROP POLICY IF EXISTS "ingredienti_utente_insert_policy" ON ingredienti_utente;
CREATE POLICY "ingredienti_utente_insert_policy" ON ingredienti_utente
    FOR INSERT WITH CHECK (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy UPDATE: utente può modificare solo i propri
DROP POLICY IF EXISTS "ingredienti_utente_update_policy" ON ingredienti_utente;
CREATE POLICY "ingredienti_utente_update_policy" ON ingredienti_utente
    FOR UPDATE USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy DELETE: utente può eliminare solo i propri
DROP POLICY IF EXISTS "ingredienti_utente_delete_policy" ON ingredienti_utente;
CREATE POLICY "ingredienti_utente_delete_policy" ON ingredienti_utente
    FOR DELETE USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- 5. Trigger per updated_at automatico
CREATE OR REPLACE FUNCTION update_ingredienti_utente_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_ingredienti_utente_timestamp ON ingredienti_utente;
CREATE TRIGGER trigger_update_ingredienti_utente_timestamp
    BEFORE UPDATE ON ingredienti_utente
    FOR EACH ROW
    EXECUTE FUNCTION update_ingredienti_utente_timestamp();

-- 6. Categorie predefinite (opzionale - per suggerimenti)
COMMENT ON TABLE ingredienti_utente IS 'Ingredienti personalizzati dell''utente con prezzi. Categorie suggerite: Latticini, Carni, Pesce, Verdure, Frutta, Cereali, Condimenti, Bevande, Altro';

-- 7. Grant permissions
GRANT ALL ON ingredienti_utente TO authenticated;
GRANT ALL ON ingredienti_utente TO service_role;
