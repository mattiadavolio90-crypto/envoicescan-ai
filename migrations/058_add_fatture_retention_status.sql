-- MIGRAZIONE 058: Retention automatica fatture > 2 anni
-- Elimina in background le righe storiche di fatture senza toccare margini_mensili.
-- Stato esecuzione salvato in un singolo record aggiornato ad ogni ciclo.

CREATE TABLE IF NOT EXISTS public.system_maintenance_status (
    job_name TEXT PRIMARY KEY,
    last_run_at TIMESTAMPTZ NULL,
    rows_deleted INTEGER NOT NULL DEFAULT 0,
    rows_from_trash INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    error_message TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_fatture_created_at
    ON public.fatture (created_at);

INSERT INTO public.system_maintenance_status (
    job_name,
    last_run_at,
    rows_deleted,
    rows_from_trash,
    status,
    error_message,
    updated_at
)
VALUES (
    'fatture_retention_2y',
    NULL,
    0,
    0,
    'ok',
    NULL,
    timezone('utc', now())
)
ON CONFLICT (job_name) DO NOTHING;

ALTER TABLE public.system_maintenance_status ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Solo service_role può scrivere retention status"
  ON public.system_maintenance_status
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
