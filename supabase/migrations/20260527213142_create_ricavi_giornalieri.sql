-- ============================================================================
-- Sprint 0 — Ricavi a granularità giornaliera
--
-- ricavi_giornalieri è la sorgente di verità dei ricavi (una riga per giorno).
-- Un trigger aggrega automaticamente per (ristorante, anno, mese) e fa upsert
-- in margini_mensili, così Streamlit continua a leggere i ricavi mensili senza
-- modifiche e le query KPI restano veloci.
--
-- NB: RLS è abilitata ma senza policy, coerente con il resto del progetto:
-- auth.uid() è sempre NULL (auth custom), l'accesso avviene via service_role_key
-- che bypassa RLS. Vedi CLAUDE.md.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.ricavi_giornalieri (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID,
  ristorante_id      UUID REFERENCES public.ristoranti(id) ON DELETE CASCADE,
  data               DATE NOT NULL,
  fatturato_iva10    NUMERIC(12,2) DEFAULT 0,
  fatturato_iva22    NUMERIC(12,2) DEFAULT 0,
  altri_ricavi_noiva NUMERIC(12,2) DEFAULT 0,
  source             TEXT DEFAULT 'manuale',   -- 'manuale' | 'xls' | 'email'
  source_meta        JSONB,
  created_at         TIMESTAMPTZ DEFAULT now(),
  updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ricavi_giornalieri_unique
  ON public.ricavi_giornalieri (ristorante_id, data);
CREATE INDEX IF NOT EXISTS idx_ricavi_giornalieri_ristorante_data
  ON public.ricavi_giornalieri (ristorante_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_ricavi_giornalieri_user
  ON public.ricavi_giornalieri (user_id);

ALTER TABLE public.ricavi_giornalieri ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- updated_at automatico
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_ricavi_giornalieri_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ricavi_giornalieri_updated_at ON public.ricavi_giornalieri;
CREATE TRIGGER trg_ricavi_giornalieri_updated_at
  BEFORE UPDATE ON public.ricavi_giornalieri
  FOR EACH ROW EXECUTE FUNCTION public.set_ricavi_giornalieri_updated_at();

-- ----------------------------------------------------------------------------
-- Sync aggregato mensile → margini_mensili
-- Ricalcola il totale del mese toccato dalla riga e fa upsert in margini_mensili.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.sync_margini_mensili_from_ricavi()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_user_id UUID;
  v_ristorante_id UUID;
  v_anno INT;
  v_mese INT;
  v_iva10 NUMERIC(12,2);
  v_iva22 NUMERIC(12,2);
  v_altri NUMERIC(12,2);
BEGIN
  IF TG_OP = 'DELETE' THEN
    v_user_id := OLD.user_id;
    v_ristorante_id := OLD.ristorante_id;
    v_anno := EXTRACT(YEAR FROM OLD.data);
    v_mese := EXTRACT(MONTH FROM OLD.data);
  ELSE
    v_user_id := NEW.user_id;
    v_ristorante_id := NEW.ristorante_id;
    v_anno := EXTRACT(YEAR FROM NEW.data);
    v_mese := EXTRACT(MONTH FROM NEW.data);
  END IF;

  SELECT
    COALESCE(SUM(fatturato_iva10), 0),
    COALESCE(SUM(fatturato_iva22), 0),
    COALESCE(SUM(altri_ricavi_noiva), 0)
  INTO v_iva10, v_iva22, v_altri
  FROM public.ricavi_giornalieri
  WHERE ristorante_id = v_ristorante_id
    AND EXTRACT(YEAR FROM data) = v_anno
    AND EXTRACT(MONTH FROM data) = v_mese;

  INSERT INTO public.margini_mensili (
    user_id, ristorante_id, anno, mese,
    fatturato_iva10, fatturato_iva22, altri_ricavi_noiva,
    fatturato_netto, updated_at
  )
  VALUES (
    v_user_id, v_ristorante_id, v_anno, v_mese,
    v_iva10, v_iva22, v_altri,
    (v_iva10 / 1.10) + (v_iva22 / 1.22) + v_altri,
    now()
  )
  ON CONFLICT (ristorante_id, anno, mese)
  DO UPDATE SET
    fatturato_iva10 = EXCLUDED.fatturato_iva10,
    fatturato_iva22 = EXCLUDED.fatturato_iva22,
    altri_ricavi_noiva = EXCLUDED.altri_ricavi_noiva,
    fatturato_netto = EXCLUDED.fatturato_netto,
    updated_at = now();

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ricavi_giornalieri_sync_margini ON public.ricavi_giornalieri;
CREATE TRIGGER trg_ricavi_giornalieri_sync_margini
  AFTER INSERT OR UPDATE OR DELETE ON public.ricavi_giornalieri
  FOR EACH ROW EXECUTE FUNCTION public.sync_margini_mensili_from_ricavi();
