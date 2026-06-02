-- chat_ai_enabled: interruttore della Chat AI in Home, per ristorante.
-- Default true (filosofia AI-first): la chat e' attiva salvo che il cliente
-- la spenga dal configuratore assistente.

ALTER TABLE public.assistant_preferences
  ADD COLUMN IF NOT EXISTS chat_ai_enabled BOOLEAN NOT NULL DEFAULT true;
