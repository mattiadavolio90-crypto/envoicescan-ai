-- daily_briefing_state aveva user_id/ristorante_id di tipo TEXT: impediva la FK
-- CASCADE -> alla cancellazione account restavano dati residui (GDPR). Completa il
-- fix tabelle orfane (20260603150000) per l'ultima tabella rimasta scoperta.
-- Verificato: 19 righe, tutti i valori sono uuid validi, nessun orfano.

ALTER TABLE public.daily_briefing_state
  ALTER COLUMN user_id TYPE uuid USING user_id::uuid,
  ALTER COLUMN ristorante_id TYPE uuid USING ristorante_id::uuid;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_daily_briefing_state_user') THEN
    ALTER TABLE public.daily_briefing_state
      ADD CONSTRAINT fk_daily_briefing_state_user
      FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_daily_briefing_state_rist') THEN
    ALTER TABLE public.daily_briefing_state
      ADD CONSTRAINT fk_daily_briefing_state_rist
      FOREIGN KEY (ristorante_id) REFERENCES public.ristoranti(id) ON DELETE CASCADE;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_daily_briefing_state_ristorante_id
  ON public.daily_briefing_state (ristorante_id);
