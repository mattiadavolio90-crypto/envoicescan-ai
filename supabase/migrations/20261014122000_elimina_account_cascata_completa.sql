-- «Elimina account» (cliente e admin) e «Elimina sede» (admin) contano sul
-- CASCADE da `users` e da `ristoranti`. Trovati il 14/10/2026 tre buchi che
-- li facevano fallire (500) o lasciavano dati del cliente nel DB:
--
-- 1. `riparto_costi_catena_quote.ristorante_id` era l'unica FK verso
--    `ristoranti` senza ON DELETE (su 66): un account di catena col riparto,
--    o una sua sede, non si cancellava. La FK nacque (20260729195932) per
--    impedire quote verso sedi inesistenti, non per proteggere le quote: il
--    CASCADE tiene quella garanzia.
--
-- 2. Cancellando una sede (o l'account) la cascata su `ricavi_giornalieri`
--    fa scattare `trg_ricavi_giornalieri_sync_margini`, che ricalcola e
--    REINSERISCE `margini_mensili` per una sede gia' cancellata: violazione di
--    FK, e la cancellazione intera fallisce. Ora il ricalcolo si salta quando
--    la sede non c'e' piu' (solo in DELETE: in INSERT/UPDATE la FK di
--    `ricavi_giornalieri` garantisce che ci sia). Basta la sede: i trigger di
--    riga dei ricavi scattano dopo TUTTE le cascate dello statement, anche
--    quando la FK dei ricavi verso `users` viene prima di quella delle sedi
--    (com'e' sul live) — misurato il 14/10/2026 con una sonda su Postgres 16.
--    Il resto del corpo e' identico a quello sul live (pg_get_functiondef).
--
-- 3. Otto tabelle con `user_id` senza FK verso `users`: restavano dopo la
--    cancellazione dell'account (GDPR art. 17). Sul live 0 righe orfane in
--    tutte e otto (misurato il 14/10/2026); `classificazioni_manuali` ha 4
--    righe globali con user_id NULL, che la FK lascia stare.
--    `gruppo_segnali_state.user_id` era TEXT: diventa uuid (70 righe, tutte
--    uuid valide; nessuna funzione, vista o policy la legge).
--
-- 4. Tre tabelle con `ristorante_id` senza FK verso `ristoranti`
--    (`fatture_documenti`, `upload_events`, `upload_locks`): restavano dopo
--    «Elimina sede». Sul live 0 righe orfane; `upload_events` ha 811 righe con
--    ristorante_id NULL, che la FK lascia stare.
--
-- Idempotente. Va applicata al live PRIMA del push.

-- 1. Riparto: le quote di una sede cancellata se ne vanno con lei.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'riparto_costi_catena_quote_ristorante_id_fkey'
          AND conrelid = 'public.riparto_costi_catena_quote'::regclass
          AND confdeltype <> 'c'
    ) THEN
        ALTER TABLE public.riparto_costi_catena_quote
            DROP CONSTRAINT riparto_costi_catena_quote_ristorante_id_fkey;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'riparto_costi_catena_quote_ristorante_id_fkey'
          AND conrelid = 'public.riparto_costi_catena_quote'::regclass
    ) THEN
        ALTER TABLE public.riparto_costi_catena_quote
            ADD CONSTRAINT riparto_costi_catena_quote_ristorante_id_fkey
            FOREIGN KEY (ristorante_id) REFERENCES public.ristoranti(id) ON DELETE CASCADE;
    END IF;
END
$$;

-- 2. Margini: niente ricalcolo per una sede appena cancellata.
CREATE OR REPLACE FUNCTION public.sync_margini_mensili_from_ricavi()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
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
    IF NOT EXISTS (SELECT 1 FROM public.ristoranti WHERE id = v_ristorante_id) THEN
      RETURN OLD;
    END IF;
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
    SUM(coperti)
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
$function$;

-- 3. Le otto tabelle seguono l'account.
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'gruppo_segnali_state' AND column_name = 'user_id') = 'text' THEN
        ALTER TABLE public.gruppo_segnali_state
            ALTER COLUMN user_id TYPE uuid USING user_id::uuid;
    END IF;
END
$$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'classificazioni_manuali', 'fatture_documenti', 'gruppo_segnali_state',
        'prezzi_preferiti', 'riparto_costi_catena', 'riparto_regole_fornitore',
        'upload_events', 'upload_locks'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = t || '_user_id_fkey'
              AND conrelid = ('public.' || t)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE',
                t, t || '_user_id_fkey'
            );
        END IF;
    END LOOP;
END
$$;

-- 4. Le tre tabelle seguono la sede.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['fatture_documenti', 'upload_events', 'upload_locks'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = t || '_ristorante_id_fkey'
              AND conrelid = ('public.' || t)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (ristorante_id) REFERENCES public.ristoranti(id) ON DELETE CASCADE',
                t, t || '_ristorante_id_fkey'
            );
        END IF;
    END LOOP;
END
$$;

-- Il CASCADE cerca per user_id: le due tabelle che non avevano un indice
-- che cominci da user_id.
CREATE INDEX IF NOT EXISTS idx_prezzi_preferiti_user ON public.prezzi_preferiti (user_id);
CREATE INDEX IF NOT EXISTS idx_upload_locks_user ON public.upload_locks (user_id);
