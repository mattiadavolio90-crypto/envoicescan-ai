-- ============================================================
-- MIGRATION 032: Create review_ignored table
-- ============================================================
-- Tabella per righe ignorate temporaneamente dall'admin.
--
-- INSERT (admin.py ~246):
--   .insert({
--       'row_id': row_id,                                        -- TEXT/INTEGER (riga fattura ID)
--       'descrizione': descrizione,                               -- TEXT
--       'ignored_by': admin_email,                                -- TEXT (email)
--       'ignored_at': datetime.now().isoformat(),                 -- TIMESTAMP
--       'ignored_until': (datetime.now() + timedelta(days)).iso() -- TIMESTAMP
--   })
--   ignored_until calcolato da giorni parametro (default 30)
--
-- No SELECT/DELETE trovati nel codice → solo INSERT, no DELETE RLS strettamente necessario
-- ma lo includiamo per completezza futura.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.review_ignored (
    id BIGSERIAL PRIMARY KEY,
    row_id TEXT,
    descrizione TEXT,
    ignored_by TEXT,
    ignored_at TIMESTAMPTZ DEFAULT NOW(),
    ignored_until TIMESTAMPTZ
);

-- Aggiunge colonne mancanti se tabella esisteva già
ALTER TABLE public.review_ignored
    ADD COLUMN IF NOT EXISTS row_id TEXT,
    ADD COLUMN IF NOT EXISTS descrizione TEXT,
    ADD COLUMN IF NOT EXISTS ignored_by TEXT,
    ADD COLUMN IF NOT EXISTS ignored_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS ignored_until TIMESTAMPTZ;

-- Indice per filtraggio temporale (scadenza ignore)
CREATE INDEX IF NOT EXISTS idx_review_ignored_until
    ON public.review_ignored (ignored_until);

-- Indice per lookup per row_id
CREATE INDEX IF NOT EXISTS idx_review_ignored_row_id
    ON public.review_ignored (row_id);

COMMENT ON TABLE public.review_ignored IS 'Righe ignorate temporaneamente dall admin - nascoste dalla review per N giorni';

-- RLS
ALTER TABLE public.review_ignored ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated"
ON public.review_ignored
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

GRANT ALL ON public.review_ignored TO anon;
GRANT ALL ON public.review_ignored TO authenticated;
GRANT ALL ON public.review_ignored TO service_role;

DO $$ BEGIN
    GRANT USAGE, SELECT ON SEQUENCE review_ignored_id_seq TO anon;
    GRANT USAGE, SELECT ON SEQUENCE review_ignored_id_seq TO authenticated;
    GRANT USAGE, SELECT ON SEQUENCE review_ignored_id_seq TO service_role;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'Sequence review_ignored_id_seq non trovata, skip grant';
END $$;
