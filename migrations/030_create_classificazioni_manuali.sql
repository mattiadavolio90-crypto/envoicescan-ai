-- ============================================================
-- MIGRATION 030: Ensure classificazioni_manuali table schema
-- ============================================================
-- Se la tabella esiste già (creata manualmente), aggiunge solo
-- le colonne/indici mancanti. Se non esiste, la crea da zero.
--
-- Colonne usate dal codice Python:
--   user_id (UUID)          — gestione_account.py, admin.py
--   descrizione (TEXT)      — ai_service.py
--   categoria_corretta (TEXT) — ai_service.py
--   is_dicitura (BOOLEAN)   — ai_service.py
-- ============================================================

-- Crea tabella solo se non esiste
CREATE TABLE IF NOT EXISTS public.classificazioni_manuali (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID,
    descrizione TEXT,
    categoria_corretta TEXT,
    is_dicitura BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Aggiunge colonne mancanti (safe: IF NOT EXISTS)
ALTER TABLE public.classificazioni_manuali
    ADD COLUMN IF NOT EXISTS user_id UUID,
    ADD COLUMN IF NOT EXISTS descrizione TEXT,
    ADD COLUMN IF NOT EXISTS categoria_corretta TEXT,
    ADD COLUMN IF NOT EXISTS is_dicitura BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Indici (safe: IF NOT EXISTS)
CREATE INDEX IF NOT EXISTS idx_classificazioni_manuali_user_id
    ON public.classificazioni_manuali (user_id);

CREATE INDEX IF NOT EXISTS idx_classificazioni_manuali_descrizione
    ON public.classificazioni_manuali (descrizione);

COMMENT ON TABLE public.classificazioni_manuali IS 'Classificazioni manuali admin - priorità assoluta su memoria globale/locale';

-- RLS
ALTER TABLE public.classificazioni_manuali ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all operations for authenticated users" ON public.classificazioni_manuali;
CREATE POLICY "Allow all operations for authenticated users"
ON public.classificazioni_manuali
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

GRANT ALL ON public.classificazioni_manuali TO anon;
GRANT ALL ON public.classificazioni_manuali TO authenticated;
GRANT ALL ON public.classificazioni_manuali TO service_role;

DO $$ BEGIN
    GRANT USAGE, SELECT ON SEQUENCE classificazioni_manuali_id_seq TO anon;
    GRANT USAGE, SELECT ON SEQUENCE classificazioni_manuali_id_seq TO authenticated;
    GRANT USAGE, SELECT ON SEQUENCE classificazioni_manuali_id_seq TO service_role;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'Sequence classificazioni_manuali_id_seq non trovata, skip grant';
END $$;
