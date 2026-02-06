-- ============================================================
-- MIGRATION 018: Sistema Gestione Ricette e Food Cost
-- ============================================================
-- Creazione tabella ricette con supporto multi-ristorante
-- Include RLS policies, indici performance e RPC functions

-- ============================================================
-- STEP 1: Creazione tabella ricette
-- ============================================================
CREATE TABLE IF NOT EXISTS ricette (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    userid UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ristorante_id UUID REFERENCES ristoranti(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL CHECK (categoria IN (
        'ANTIPASTI',
        'PRIMI',
        'SECONDI',
        'PIZZE',
        'DOLCI',
        'SEMILAVORATI'
    )),
    ingredienti JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Formato: [{"nome":"Mozzarella","quantita":200,"um":"g","prezzo_unitario":8.5,"is_ricetta":false,"ricetta_id":null}]
    foodcost_totale NUMERIC(10,2) NOT NULL DEFAULT 0,
    ordine_visualizzazione INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- STEP 2: Indici per performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_ricette_userid_ristorante 
    ON ricette(userid, ristorante_id);

CREATE INDEX IF NOT EXISTS idx_ricette_userid_categoria 
    ON ricette(userid, categoria);

CREATE INDEX IF NOT EXISTS idx_ricette_userid_order 
    ON ricette(userid, ordine_visualizzazione);

-- Indice GIN per query JSONB su ingredienti
CREATE INDEX IF NOT EXISTS idx_ricette_ingredienti_gin 
    ON ricette USING gin(ingredienti);

-- ============================================================
-- STEP 3: Row Level Security (RLS)
-- ============================================================
ALTER TABLE ricette ENABLE ROW LEVEL SECURITY;

-- Policy SELECT: Utente vede solo sue ricette del ristorante corrente
CREATE POLICY ricette_select_policy ON ricette
    FOR SELECT
    USING (
        userid = auth.uid() AND
        (ristorante_id IS NULL OR ristorante_id = NULLIF(current_setting('app.ristorante_id', true), '')::uuid)
    );

-- Policy INSERT: Utente può creare ricette solo per sé
CREATE POLICY ricette_insert_policy ON ricette
    FOR INSERT
    WITH CHECK (userid = auth.uid());

-- Policy UPDATE: Utente può modificare solo proprie ricette
CREATE POLICY ricette_update_policy ON ricette
    FOR UPDATE
    USING (userid = auth.uid())
    WITH CHECK (userid = auth.uid());

-- Policy DELETE: Utente può eliminare solo proprie ricette
CREATE POLICY ricette_delete_policy ON ricette
    FOR DELETE
    USING (userid = auth.uid());

-- ============================================================
-- STEP 4: Trigger per updated_at automatico
-- ============================================================
CREATE OR REPLACE FUNCTION update_ricette_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_ricette_timestamp
    BEFORE UPDATE ON ricette
    FOR EACH ROW
    EXECUTE FUNCTION update_ricette_timestamp();

-- ============================================================
-- STEP 5: RPC Function per swap ordine (transazione atomica)
-- ============================================================
CREATE OR REPLACE FUNCTION swap_ricette_order(
    ricetta_id_1 UUID,
    ricetta_id_2 UUID
)
RETURNS BOOLEAN AS $$
DECLARE
    ordine_1 INTEGER;
    ordine_2 INTEGER;
BEGIN
    -- Recupera ordini attuali
    SELECT ordine_visualizzazione INTO ordine_1 
    FROM ricette 
    WHERE id = ricetta_id_1 AND userid = auth.uid();
    
    SELECT ordine_visualizzazione INTO ordine_2 
    FROM ricette 
    WHERE id = ricetta_id_2 AND userid = auth.uid();
    
    -- Verifica che entrambe le ricette esistano e appartengano all'utente
    IF ordine_1 IS NULL OR ordine_2 IS NULL THEN
        RAISE EXCEPTION 'Ricette non trovate o accesso negato';
    END IF;
    
    -- Swap atomico con transazione
    UPDATE ricette SET ordine_visualizzazione = ordine_2 
    WHERE id = ricetta_id_1 AND userid = auth.uid();
    
    UPDATE ricette SET ordine_visualizzazione = ordine_1 
    WHERE id = ricetta_id_2 AND userid = auth.uid();
    
    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Errore swap ordine: %', SQLERRM;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- STEP 6: Funzione helper per prossimo ordine disponibile
-- ============================================================
CREATE OR REPLACE FUNCTION get_next_ordine_ricetta(
    p_userid UUID,
    p_ristorante_id UUID
)
RETURNS INTEGER AS $$
DECLARE
    max_ordine INTEGER;
BEGIN
    SELECT COALESCE(MAX(ordine_visualizzazione), 0) INTO max_ordine
    FROM ricette
    WHERE userid = p_userid 
      AND (ristorante_id = p_ristorante_id OR (ristorante_id IS NULL AND p_ristorante_id IS NULL));
    
    RETURN max_ordine + 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- STEP 7: Commenti documentazione
-- ============================================================
COMMENT ON TABLE ricette IS 'Gestione ricette e calcolo food cost con supporto multi-ristorante';
COMMENT ON COLUMN ricette.ingredienti IS 'Array JSONB ingredienti: [{"nome":"..","quantita":N,"um":"g/kg/ml/lt/pz","prezzo_unitario":X.XX,"is_ricetta":bool,"ricetta_id":uuid}]';
COMMENT ON COLUMN ricette.ordine_visualizzazione IS 'Ordine custom per sorting UI (gestito da swap_ricette_order RPC)';
COMMENT ON FUNCTION swap_ricette_order IS 'Scambia ordine tra 2 ricette con transazione atomica (evita race condition)';
