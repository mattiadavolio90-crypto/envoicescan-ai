-- marketplace_leads: richieste di informazioni sui servizi del marketplace
-- (Assistenza). Una riga per ogni "Richiedi info" inviato da un cliente.
-- I dati anagrafici sono denormalizzati allo snapshot della richiesta, cosi'
-- la coda admin resta leggibile anche se l'utente cambia email/nome dopo.
-- RLS abilitata senza policy: accesso tramite service_role_key (vedi CLAUDE.md).

CREATE TABLE IF NOT EXISTS public.marketplace_leads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID,
  ristorante_id   UUID REFERENCES public.ristoranti(id) ON DELETE SET NULL,
  servizio_key    TEXT NOT NULL,
  servizio_label  TEXT NOT NULL,
  messaggio       TEXT NOT NULL DEFAULT '',
  contatto_email  TEXT,
  contatto_nome   TEXT,
  stato           TEXT NOT NULL DEFAULT 'nuovo'
                  CHECK (stato IN ('nuovo', 'gestito', 'archiviato')),
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_marketplace_leads_stato_created
  ON public.marketplace_leads (stato, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_user_id
  ON public.marketplace_leads (user_id);

ALTER TABLE public.marketplace_leads ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.set_marketplace_leads_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_marketplace_leads_updated_at ON public.marketplace_leads;
CREATE TRIGGER trg_marketplace_leads_updated_at
  BEFORE UPDATE ON public.marketplace_leads
  FOR EACH ROW EXECUTE FUNCTION public.set_marketplace_leads_updated_at();
