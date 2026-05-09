-- Add upload dedup/idempotency indexes for faster duplicate checks

CREATE INDEX IF NOT EXISTS idx_fatture_upload_dedup_active
ON public.fatture (user_id, ristorante_id, file_origine)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_fatture_upload_dedup_active_lower
ON public.fatture (user_id, ristorante_id, lower(file_origine))
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_fatture_upload_replace_lookup
ON public.fatture (user_id, ristorante_id, file_origine);

CREATE INDEX IF NOT EXISTS idx_upload_events_saved_ok_lookup
ON public.upload_events (user_id, status, file_name)
WHERE status = 'SAVED_OK';
