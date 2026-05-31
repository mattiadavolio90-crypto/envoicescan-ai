-- inventario_voci: snapshot periodico delle giacenze (tipicamente mensile).
-- Una riga per ogni prodotto contato in una data specifica.
-- valore_totale è colonna generata (quantita * prezzo_unitario, 2 decimali).
-- RLS abilitata senza policy: accesso tramite service_role_key (vedi CLAUDE.md).

CREATE TABLE IF NOT EXISTS public.inventario_voci (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID,
  ristorante_id    UUID REFERENCES public.ristoranti(id) ON DELETE CASCADE,
  data_inventario  DATE NOT NULL,
  nome             TEXT NOT NULL,
  categoria        TEXT NOT NULL DEFAULT '',
  quantita         NUMERIC(10,3) NOT NULL DEFAULT 0,
  um               TEXT NOT NULL DEFAULT 'KG',
  prezzo_unitario  NUMERIC(10,4) NOT NULL DEFAULT 0,
  valore_totale    NUMERIC(10,2) GENERATED ALWAYS AS (ROUND(quantita * prezzo_unitario, 2)) STORED,
  note             TEXT,
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inventario_voci_ristorante_data
  ON public.inventario_voci (ristorante_id, data_inventario DESC);
CREATE INDEX IF NOT EXISTS idx_inventario_voci_user_id
  ON public.inventario_voci (user_id);

ALTER TABLE public.inventario_voci ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.set_inventario_voci_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_inventario_voci_updated_at ON public.inventario_voci;
CREATE TRIGGER trg_inventario_voci_updated_at
  BEFORE UPDATE ON public.inventario_voci
  FOR EACH ROW EXECUTE FUNCTION public.set_inventario_voci_updated_at();
