-- ============================================================================
-- COPERTI — Feature coperti giornalieri/mensili
--
-- Passbi ha aggiunto al file export la colonna "Coperti ristorante". I coperti
-- vengono salvati per giorno in ricavi_giornalieri (come fatturato_*), aggregati
-- nel mese in margini_mensili dal trigger esistente, e — per i mesi in modalità
-- 'mensile' — inseribili come totale in ricavi_modalita_mensile.
--
-- NULL (non 0) = il dato coperti non è pervenuto (gestionale vecchio / non
-- inserito a mano): distinguibile da "0 coperti reali". Lo scontrino medio si
-- calcola solo quando coperti > 0, così un NULL non falsa la media.
--
-- Il percorso dei coperti replica ESATTAMENTE quello del fatturato: trigger di
-- rollup per i mesi giornalieri, override mensile in lettura per i mesi mensili.
-- Così coperti e ricavi restano sempre coerenti (scontrino medio affidabile).
-- ============================================================================

-- ── 1. Colonne coperti ──────────────────────────────────────────────────────
ALTER TABLE public.ricavi_giornalieri
  ADD COLUMN IF NOT EXISTS coperti INTEGER DEFAULT NULL;

ALTER TABLE public.margini_mensili
  ADD COLUMN IF NOT EXISTS coperti INTEGER DEFAULT NULL;

ALTER TABLE public.ricavi_modalita_mensile
  ADD COLUMN IF NOT EXISTS coperti INTEGER DEFAULT NULL;

-- ── 2. Trigger rollup: aggiunge SUM(coperti) all'aggregato mensile ───────────
-- Stesso pattern dei tre campi fatturato. Se nel mese nessun giorno ha coperti
-- valorizzati, SUM(...) è NULL → margini_mensili.coperti resta NULL ("—" in UI),
-- non 0.
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
  v_coperti INT;
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
    COALESCE(SUM(altri_ricavi_noiva), 0),
    SUM(coperti)   -- NULL se nessun giorno del mese ha coperti
  INTO v_iva10, v_iva22, v_altri, v_coperti
  FROM public.ricavi_giornalieri
  WHERE ristorante_id = v_ristorante_id
    AND EXTRACT(YEAR FROM data) = v_anno
    AND EXTRACT(MONTH FROM data) = v_mese;

  INSERT INTO public.margini_mensili (
    user_id, ristorante_id, anno, mese,
    fatturato_iva10, fatturato_iva22, altri_ricavi_noiva,
    fatturato_netto, coperti, updated_at
  )
  VALUES (
    v_user_id, v_ristorante_id, v_anno, v_mese,
    v_iva10, v_iva22, v_altri,
    (v_iva10 / 1.10) + (v_iva22 / 1.22) + v_altri,
    v_coperti, now()
  )
  ON CONFLICT (ristorante_id, anno, mese)
  DO UPDATE SET
    fatturato_iva10 = EXCLUDED.fatturato_iva10,
    fatturato_iva22 = EXCLUDED.fatturato_iva22,
    altri_ricavi_noiva = EXCLUDED.altri_ricavi_noiva,
    fatturato_netto = EXCLUDED.fatturato_netto,
    coperti = EXCLUDED.coperti,
    updated_at = now();

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;

-- Il trigger trg_ricavi_giornalieri_sync_margini punta già a questa funzione:
-- la CREATE OR REPLACE basta, non serve ricrearlo.
