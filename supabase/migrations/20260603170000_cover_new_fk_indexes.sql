-- Indici di copertura per le FK CASCADE aggiunte in 20260603150000.
-- Senza, le ON DELETE CASCADE (cancellazione account/sede) fanno seq-scan su queste
-- tabelle. Segnalati da Supabase performance advisor (unindexed_foreign_keys).

CREATE INDEX IF NOT EXISTS idx_category_change_log_ristorante_id
  ON public.category_change_log (ristorante_id);
CREATE INDEX IF NOT EXISTS idx_email_rate_log_ristorante_id
  ON public.email_rate_log (ristorante_id);
CREATE INDEX IF NOT EXISTS idx_email_rate_log_user_id
  ON public.email_rate_log (user_id);
CREATE INDEX IF NOT EXISTS idx_fornitori_pagamenti_config_ristorante_id
  ON public.fornitori_pagamenti_config (ristorante_id);
CREATE INDEX IF NOT EXISTS idx_notification_inbox_ristorante_id
  ON public.notification_inbox (ristorante_id);
