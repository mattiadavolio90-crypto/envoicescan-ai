-- ============================================================
-- MIGRATION 053: stato notifiche viste lato utente
-- ============================================================

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS dismissed_notification_ids JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.users.dismissed_notification_ids IS 'Mappa notification_id -> timestamp dismiss da usare per notifiche in-app gia viste';
