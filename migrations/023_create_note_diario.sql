-- ============================================
-- MIGRATION 023: Tabella Note Diario
-- ============================================
-- Permette agli utenti di creare note/appunti cronologici
-- nel workspace per tenere traccia di attività e decisioni

-- 1. Crea tabella note_diario
CREATE TABLE IF NOT EXISTS note_diario (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    userid UUID NOT NULL,
    ristorante_id UUID REFERENCES ristoranti(id) ON DELETE CASCADE,
    testo TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Indici per performance
CREATE INDEX IF NOT EXISTS idx_note_diario_userid 
    ON note_diario(userid);
CREATE INDEX IF NOT EXISTS idx_note_diario_ristorante 
    ON note_diario(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_note_diario_created_at 
    ON note_diario(created_at DESC);

-- 3. RLS Policies
ALTER TABLE note_diario ENABLE ROW LEVEL SECURITY;

-- Policy SELECT: utente vede solo le proprie note
DROP POLICY IF EXISTS "note_diario_select_policy" ON note_diario;
CREATE POLICY "note_diario_select_policy" ON note_diario
    FOR SELECT USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy INSERT: utente può inserire solo per sé
DROP POLICY IF EXISTS "note_diario_insert_policy" ON note_diario;
CREATE POLICY "note_diario_insert_policy" ON note_diario
    FOR INSERT WITH CHECK (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy UPDATE: utente può modificare solo le proprie
DROP POLICY IF EXISTS "note_diario_update_policy" ON note_diario;
CREATE POLICY "note_diario_update_policy" ON note_diario
    FOR UPDATE USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- Policy DELETE: utente può eliminare solo le proprie
DROP POLICY IF EXISTS "note_diario_delete_policy" ON note_diario;
CREATE POLICY "note_diario_delete_policy" ON note_diario
    FOR DELETE USING (
        userid = auth.uid() 
        OR userid::text = current_setting('app.current_user_id', true)
    );

-- 4. Trigger per updated_at automatico
CREATE OR REPLACE FUNCTION update_note_diario_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_note_diario_timestamp ON note_diario;
CREATE TRIGGER trigger_update_note_diario_timestamp
    BEFORE UPDATE ON note_diario
    FOR EACH ROW
    EXECUTE FUNCTION update_note_diario_timestamp();

-- 5. Commenti
COMMENT ON TABLE note_diario IS 'Note e appunti cronologici dell''utente per il workspace';
COMMENT ON COLUMN note_diario.testo IS 'Contenuto testuale della nota';
COMMENT ON COLUMN note_diario.created_at IS 'Data e ora di creazione';
COMMENT ON COLUMN note_diario.updated_at IS 'Data e ora ultima modifica';

-- 6. Grant permissions
GRANT ALL ON note_diario TO authenticated;
GRANT ALL ON note_diario TO service_role;
