-- Ricavi «senza IVA»: il cliente li elimina dalle Impostazioni e la sede non li
-- accetta piu' (12/10/2026).
--
-- Perche' un flag e non solo una DELETE: Passbi arriva via email ogni giorno e
-- l'upsert (`ricavi.py` _upsert_ricavi_ristorante, `email_queue_processor.py`
-- _upsert_ricavi) riscrive tutte e tre le colonne. Senza blocco, l'email del
-- giorno dopo — o un file vecchio re-inviato — rimette il no IVA. Misurato il
-- 12/10 sul live: 4 sedi di un account catena, circa il 25% del netto.
--
-- Il blocco sta nel DB e non nei sette canali di scrittura (import xls, email,
-- POST giornaliero, batch, modalita' mensile, assistente, POST /api/margini):
-- un trigger BEFORE copre anche i canali futuri.

ALTER TABLE public.ristoranti
  ADD COLUMN IF NOT EXISTS escludi_ricavi_noiva boolean NOT NULL DEFAULT false;

-- ── Trigger: la sede esclusa scrive sempre 0 nel no IVA ─────────────────────
CREATE OR REPLACE FUNCTION public.ricavi_noiva_esclusi_guardia()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $$
DECLARE
  v_escluso boolean;
BEGIN
  IF COALESCE(NEW.altri_ricavi_noiva, 0) = 0 THEN
    RETURN NEW;
  END IF;

  SELECT r.escludi_ricavi_noiva INTO v_escluso
  FROM public.ristoranti r
  WHERE r.id = NEW.ristorante_id;

  IF NOT COALESCE(v_escluso, false) THEN
    RETURN NEW;
  END IF;

  NEW.altri_ricavi_noiva := 0;

  IF TG_TABLE_NAME = 'margini_mensili' THEN
    -- Chi scrive il no IVA qui (POST /api/margini, il rollup dei giornalieri) ha
    -- calcolato il netto con il no IVA dentro. Si ricalcola con la formula di
    -- riparto_quote_mensili e non sottraendo la differenza: il rollup aggiorna
    -- solo il netto, e una sottrazione su primo margine e MOL si accumulerebbe.
    NEW.fatturato_netto := round(
      COALESCE(NEW.fatturato_iva10,0)/1.10 + COALESCE(NEW.fatturato_iva22,0)/1.22, 2);
    NEW.primo_margine := round(NEW.fatturato_netto
      - (COALESCE(NEW.costi_fb_auto,0) + COALESCE(NEW.altri_costi_fb,0) + COALESCE(NEW.quote_riparto_fb,0)), 2);
    NEW.mol := round(NEW.primo_margine
      - (COALESCE(NEW.costi_spese_auto,0) + COALESCE(NEW.altri_costi_spese,0) + COALESCE(NEW.quote_riparto_spese,0))
      - (COALESCE(NEW.costo_dipendenti,0) + COALESCE(NEW.costo_personale_extra,0) + COALESCE(NEW.costo_personale_chiamata,0)), 2);
  ELSIF TG_TABLE_NAME = 'ricavi_giornalieri'
        AND TG_OP = 'INSERT'
        AND COALESCE(NEW.fatturato_iva10, 0) = 0
        AND COALESCE(NEW.fatturato_iva22, 0) = 0
        AND NEW.coperti IS NULL THEN
    -- Un giorno fatto solo di no IVA non nasce: una riga a incasso zero il
    -- briefing la leggerebbe come un giorno di crollo. Stessa regola degli
    -- import, che scartano i giorni con totale <= 0. Con l'upsert il BEFORE
    -- INSERT scatta sulla riga proposta: la riga esistente resta com'e'.
    RETURN NULL;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ricavi_giornalieri_noiva_esclusi ON public.ricavi_giornalieri;
CREATE TRIGGER trg_ricavi_giornalieri_noiva_esclusi
  BEFORE INSERT OR UPDATE ON public.ricavi_giornalieri
  FOR EACH ROW EXECUTE FUNCTION public.ricavi_noiva_esclusi_guardia();

DROP TRIGGER IF EXISTS trg_ricavi_modalita_mensile_noiva_esclusi ON public.ricavi_modalita_mensile;
CREATE TRIGGER trg_ricavi_modalita_mensile_noiva_esclusi
  BEFORE INSERT OR UPDATE ON public.ricavi_modalita_mensile
  FOR EACH ROW EXECUTE FUNCTION public.ricavi_noiva_esclusi_guardia();

DROP TRIGGER IF EXISTS trg_margini_mensili_noiva_esclusi ON public.margini_mensili;
CREATE TRIGGER trg_margini_mensili_noiva_esclusi
  BEFORE INSERT OR UPDATE ON public.margini_mensili
  FOR EACH ROW EXECUTE FUNCTION public.ricavi_noiva_esclusi_guardia();

-- ── RPC: elimina il no IVA delle sedi scelte e le esclude ───────────────────
CREATE OR REPLACE FUNCTION public.elimina_ricavi_noiva(p_user_id uuid, p_ristorante_ids uuid[])
RETURNS TABLE (ristorante_id uuid, giorni integer, mesi integer, euro numeric)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
#variable_conflict use_column
DECLARE
  v_altrui integer;
BEGIN
  IF p_user_id IS NULL OR p_ristorante_ids IS NULL OR cardinality(p_ristorante_ids) = 0 THEN
    RAISE EXCEPTION 'utente e sedi obbligatori';
  END IF;

  -- Tutto o niente: anche un solo id non suo (o inesistente) ferma l'operazione.
  SELECT count(*) INTO v_altrui
  FROM unnest(p_ristorante_ids) AS s(id)
  WHERE NOT EXISTS (
    SELECT 1 FROM public.ristoranti r WHERE r.id = s.id AND r.user_id = p_user_id
  );
  IF v_altrui > 0 THEN
    RAISE EXCEPTION 'sede non dell''utente' USING ERRCODE = '42501';
  END IF;

  DROP TABLE IF EXISTS pg_temp._noiva_toccati;
  DROP TABLE IF EXISTS pg_temp._noiva_mesi;

  CREATE TEMP TABLE _noiva_toccati ON COMMIT DROP AS
  SELECT g.ristorante_id AS rid,
         EXTRACT(YEAR FROM g.data)::int AS anno,
         EXTRACT(MONTH FROM g.data)::int AS mese,
         count(*)::int AS giorni,
         SUM(g.altri_ricavi_noiva) AS euro
  FROM public.ricavi_giornalieri g
  WHERE g.ristorante_id = ANY(p_ristorante_ids)
    AND COALESCE(g.altri_ricavi_noiva, 0) <> 0
  GROUP BY 1, 2, 3;

  CREATE TEMP TABLE _noiva_mesi ON COMMIT DROP AS
  SELECT mm.ristorante_id AS rid, mm.anno, mm.mese
  FROM public.margini_mensili mm
  WHERE mm.ristorante_id = ANY(p_ristorante_ids)
    AND COALESCE(mm.altri_ricavi_noiva, 0) <> 0
  UNION
  SELECT m.ristorante_id, m.anno, m.mese
  FROM public.ricavi_modalita_mensile m
  WHERE m.ristorante_id = ANY(p_ristorante_ids)
    AND COALESCE(m.altri_ricavi_noiva, 0) <> 0
  UNION
  SELECT t.rid, t.anno, t.mese FROM pg_temp._noiva_toccati t;

  -- Il flag va prima degli update: da qui il trigger fa da secondo controllo.
  UPDATE public.ristoranti r
  SET escludi_ricavi_noiva = true
  WHERE r.id = ANY(p_ristorante_ids);

  -- I giorni fatti solo di no IVA spariscono; gli altri tengono 10% e 22%.
  -- Ogni scrittura fa ricostruire il mese a sync_margini_mensili_from_ricavi.
  DELETE FROM public.ricavi_giornalieri g
  WHERE g.ristorante_id = ANY(p_ristorante_ids)
    AND COALESCE(g.altri_ricavi_noiva, 0) <> 0
    AND COALESCE(g.fatturato_iva10, 0) = 0
    AND COALESCE(g.fatturato_iva22, 0) = 0
    AND g.coperti IS NULL;

  UPDATE public.ricavi_giornalieri g
  SET altri_ricavi_noiva = 0
  WHERE g.ristorante_id = ANY(p_ristorante_ids)
    AND COALESCE(g.altri_ricavi_noiva, 0) <> 0;

  UPDATE public.ricavi_modalita_mensile m
  SET altri_ricavi_noiva = 0, updated_at = now()
  WHERE m.ristorante_id = ANY(p_ristorante_ids)
    AND COALESCE(m.altri_ricavi_noiva, 0) <> 0;

  -- I mesi senza giornalieri (no IVA scritto direttamente in margini_mensili) e i
  -- totali salvati: stessa formula di riparto_quote_mensili, cosi' netto, primo
  -- margine e MOL salvati non tengono il no IVA dentro.
  UPDATE public.margini_mensili mm
  SET altri_ricavi_noiva = 0,
      fatturato_netto = round(
        COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22, 2),
      primo_margine = round(
        (COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22)
        - (COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0)), 2),
      mol = round(
        (COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22)
        - (COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0))
        - (COALESCE(mm.costi_spese_auto,0) + COALESCE(mm.altri_costi_spese,0) + COALESCE(mm.quote_riparto_spese,0))
        - (COALESCE(mm.costo_dipendenti,0) + COALESCE(mm.costo_personale_extra,0) + COALESCE(mm.costo_personale_chiamata,0)), 2),
      updated_at = now()
  FROM pg_temp._noiva_mesi k
  WHERE mm.ristorante_id = k.rid AND mm.anno = k.anno AND mm.mese = k.mese;

  RETURN QUERY
  SELECT s.id,
         COALESCE((SELECT SUM(t.giorni) FROM pg_temp._noiva_toccati t WHERE t.rid = s.id), 0)::int,
         (SELECT count(*) FROM pg_temp._noiva_mesi k WHERE k.rid = s.id)::int,
         COALESCE((SELECT SUM(t.euro) FROM pg_temp._noiva_toccati t WHERE t.rid = s.id), 0)::numeric
  FROM unnest(p_ristorante_ids) AS s(id);
END;
$$;

-- Su Supabase anon e authenticated hanno grant nominali su ogni funzione nuova:
-- il REVOKE dal solo PUBLIC non li toglie.
REVOKE ALL ON FUNCTION public.elimina_ricavi_noiva(uuid, uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.elimina_ricavi_noiva(uuid, uuid[]) TO service_role;
REVOKE ALL ON FUNCTION public.ricavi_noiva_esclusi_guardia() FROM PUBLIC, anon, authenticated;
