-- chat_usage_log: una riga per ogni domanda alla Chat AI, per il rate limit
-- giornaliero (max domande/giorno per ristorante) e per mostrare al cliente
-- il contatore nelle Impostazioni.
-- RLS abilitata senza policy: accesso tramite service_role_key (vedi CLAUDE.md).

CREATE TABLE IF NOT EXISTS public.chat_usage_log (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID,
  ristorante_id  UUID,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_usage_ristorante_giorno
  ON public.chat_usage_log (ristorante_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_usage_user_giorno
  ON public.chat_usage_log (user_id, created_at DESC);

ALTER TABLE public.chat_usage_log ENABLE ROW LEVEL SECURITY;
