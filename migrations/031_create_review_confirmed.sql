-- ============================================================
-- MIGRATION 031: Create review_confirmed table
-- ============================================================
-- Tabella per righe confermate dall'admin nella review.
--
-- INSERT (admin.py ~159):
--   .insert({
--       'descrizione': descrizione.strip(),        -- TEXT
--       'categoria_finale': categoria,              -- TEXT
--       'is_correct': True,                         -- BOOLEAN
--       'confirmed_by': admin_email,                -- TEXT (email)
--       'confirmed_at': datetime.now().isoformat(), -- TIMESTAMP
--       'note': 'Confermato corretto da admin'      -- TEXT
--   })
--   Gestisce errore "duplicate key" → serve UNIQUE su descrizione
--
-- SELECT (admin.py ~207):
--   .select('descrizione')
--   Risultato usato per filtrare DataFrame via .str.strip().isin()
-- ============================================================

CREATE TABLE IF NOT EXISTS public.review_confirmed (
    id BIGSERIAL PRIMARY KEY,
    descrizione TEXT UNIQUE,
    categoria_finale TEXT,
    is_correct BOOLEAN DEFAULT TRUE,
    confirmed_by TEXT,
    confirmed_at TIMESTAMPTZ DEFAULT NOW(),
    note TEXT
);

-- Aggiunge colonne mancanti se tabella esisteva già
ALTER TABLE public.review_confirmed
    ADD COLUMN IF NOT EXISTS descrizione TEXT,
    ADD COLUMN IF NOT EXISTS categoria_finale TEXT,
    ADD COLUMN IF NOT EXISTS is_correct BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS confirmed_by TEXT,
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS note TEXT;

COMMENT ON TABLE public.review_confirmed IS 'Righe confermate dall admin durante review - escluse dalle successive revisioni';

-- RLS
ALTER TABLE public.review_confirmed ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated"
ON public.review_confirmed
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

GRANT ALL ON public.review_confirmed TO anon;
GRANT ALL ON public.review_confirmed TO authenticated;
GRANT ALL ON public.review_confirmed TO service_role;

DO $$ BEGIN
    GRANT USAGE, SELECT ON SEQUENCE review_confirmed_id_seq TO anon;
    GRANT USAGE, SELECT ON SEQUENCE review_confirmed_id_seq TO authenticated;
    GRANT USAGE, SELECT ON SEQUENCE review_confirmed_id_seq TO service_role;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'Sequence review_confirmed_id_seq non trovata, skip grant';
END $$;
