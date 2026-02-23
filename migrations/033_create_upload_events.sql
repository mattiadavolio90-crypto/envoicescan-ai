-- ============================================================
-- MIGRATION 033: Create upload_events table
-- ============================================================
-- Tabella per logging eventi upload fatture.
--
-- INSERT (formatters.py ~509):
--   .insert({
--       'user_id': user_id,           -- UUID (str passato come parametro)
--       'user_email': user_email,      -- TEXT
--       'file_name': file_name,        -- TEXT
--       'file_type': file_type,        -- TEXT ("xml"|"pdf"|"image"|"unknown")
--       'status': status,              -- TEXT ("SAVED_OK"|"SAVED_PARTIAL"|"FAILED")
--       'rows_parsed': rows_parsed,    -- INTEGER (default 0)
--       'rows_saved': rows_saved,      -- INTEGER (default 0)
--       'rows_excluded': rows_excluded, -- INTEGER (default 0)
--       'error_stage': error_stage,    -- TEXT nullable ("PARSING"|"VISION"|"SUPABASE_INSERT"|"POSTCHECK")
--       'error_message': error_message, -- TEXT nullable (max 500 chars)
--       'details': details             -- JSONB nullable (dict con dettagli aggiuntivi)
--   })
--
-- DELETE (admin.py ~1879, gestione_account.py ~305):
--   .delete().eq('user_id', user_id)
--   → DELETE RLS necessario, indice su user_id necessario
-- ============================================================

CREATE TABLE IF NOT EXISTS public.upload_events (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID,
    user_email TEXT,
    file_name TEXT,
    file_type TEXT DEFAULT 'unknown',
    status TEXT,
    rows_parsed INTEGER DEFAULT 0,
    rows_saved INTEGER DEFAULT 0,
    rows_excluded INTEGER DEFAULT 0,
    error_stage TEXT,
    error_message TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Aggiunge colonne mancanti se tabella esisteva già
ALTER TABLE public.upload_events
    ADD COLUMN IF NOT EXISTS user_id UUID,
    ADD COLUMN IF NOT EXISTS user_email TEXT,
    ADD COLUMN IF NOT EXISTS file_name TEXT,
    ADD COLUMN IF NOT EXISTS file_type TEXT DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS status TEXT,
    ADD COLUMN IF NOT EXISTS rows_parsed INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rows_saved INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rows_excluded INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS error_stage TEXT,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS details JSONB,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Indice su user_id per .delete().eq('user_id', ...) e filtri admin
CREATE INDEX IF NOT EXISTS idx_upload_events_user_id
    ON public.upload_events (user_id);

-- Indice su status per analisi/dashboard admin
CREATE INDEX IF NOT EXISTS idx_upload_events_status
    ON public.upload_events (status);

-- Indice su created_at per filtri temporali
CREATE INDEX IF NOT EXISTS idx_upload_events_created_at
    ON public.upload_events (created_at);

COMMENT ON TABLE public.upload_events IS 'Log eventi upload fatture - supporto tecnico e diagnostica';

-- RLS
ALTER TABLE public.upload_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated"
ON public.upload_events
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

GRANT ALL ON public.upload_events TO anon;
GRANT ALL ON public.upload_events TO authenticated;
GRANT ALL ON public.upload_events TO service_role;

DO $$ BEGIN
    GRANT USAGE, SELECT ON SEQUENCE upload_events_id_seq TO anon;
    GRANT USAGE, SELECT ON SEQUENCE upload_events_id_seq TO authenticated;
    GRANT USAGE, SELECT ON SEQUENCE upload_events_id_seq TO service_role;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'Sequence upload_events_id_seq non trovata, skip grant';
END $$;
