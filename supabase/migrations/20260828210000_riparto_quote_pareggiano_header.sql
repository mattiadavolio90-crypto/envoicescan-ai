-- Le quote di un costo di gruppo devono sommare all'importo del costo.
--
-- Audit 2026-08, finding F-DRIFT. Misurato sul DB live: 19 costi su 156 avevano
-- somma quote != importo_totale (scarto max 1 centesimo, 19 centesimi in tutto
-- su 67.591,75 €). Quel centesimo non resta nella tabella: riparto_quote_mensili
-- somma le quote dentro margini_mensili, quindi entra nel MOL mostrato al cliente.
--
-- La causa NON era quella ipotizzata in fase di planning (i round() per-categoria
-- nel percorso di lettura). Misurando: i 19 sono ESATTAMENTE i costi con centesimi
-- dispari, cioè quelli dove importo/2 cade su mezzo centesimo, e tutti e 19 sono
-- costi RI-SCRITTI dopo la creazione (zero drift fra quelli mai modificati). Gli
-- helper Python attuali (_quote_equa, _quote_percentuali, _spezza_importo_per_pesi)
-- pareggiano già tutti: riprodotti su tutti gli 11 casi reali, danno la somma
-- esatta. Il drift è dato storico, scritto da un percorso di ri-scrittura che non
-- esiste più nel repo.
--
-- Per questo la difesa va messa QUI e non in Python: il vincolo sopravvive al
-- percorso che l'ha violato, e vale per qualunque scrittore futuro — worker, RPC,
-- correzione manuale. Un invariante difeso solo dal chiamante è un invariante che
-- il prossimo chiamante non conosce.
--
-- Tolleranza 1 centesimo: le quote sono NUMERIC(12,2) e l'ultima assorbe
-- l'arrotondamento, quindi in condizioni normali lo scarto è zero. La tolleranza
-- serve a non trasformare in errore bloccante un residuo di rappresentazione,
-- lasciando comunque fuori ogni sbilanciamento reale.

-- ── 1. Sanatoria dei 19 storici ──────────────────────────────────────────────
-- Lo scarto va sulla quota PIÙ GRANDE della sede con più peso: è la convenzione
-- già usata dal codice ("l'ultima pareggia") e sposta il centesimo dove incide
-- meno in percentuale. Su una sola riga per costo, mai spalmato.
WITH sbilanciati AS (
    SELECT c.id AS riparto_id,
           c.importo_totale,
           round(SUM(q.quota_importo), 2) AS somma_quote
    FROM public.riparto_costi_catena c
    JOIN public.riparto_costi_catena_quote q ON q.riparto_id = c.id
    GROUP BY c.id, c.importo_totale
    HAVING round(SUM(q.quota_importo), 2) <> c.importo_totale
),
da_correggere AS (
    SELECT DISTINCT ON (s.riparto_id)
           q.id AS quota_id,
           q.quota_importo + (s.importo_totale - s.somma_quote) AS nuovo_importo
    FROM sbilanciati s
    JOIN public.riparto_costi_catena_quote q ON q.riparto_id = s.riparto_id
    ORDER BY s.riparto_id, q.quota_importo DESC, q.id
)
UPDATE public.riparto_costi_catena_quote q
SET quota_importo = d.nuovo_importo
FROM da_correggere d
WHERE q.id = d.quota_id
  -- Il CHECK sulla tabella vieta quota_importo < 0: non correggiamo un costo
  -- dove la sanatoria porterebbe la quota sotto zero (non ne esistono oggi, ma
  -- la migration non deve poter fallire su dati futuri).
  AND d.nuovo_importo >= 0;

-- ── 2. La guardia, sulle due RPC che scrivono quote ──────────────────────────

CREATE OR REPLACE FUNCTION public.crea_riparto_con_quote(
    p_user_id        UUID,
    p_origine        TEXT,
    p_file_origine   TEXT,
    p_fornitore      TEXT,
    p_descrizione    TEXT,
    p_importo_totale NUMERIC,
    p_tipo           TEXT,
    p_anno           INTEGER,
    p_mese           INTEGER,
    p_regola         TEXT,
    p_quote          JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_riparto_id UUID;
    v_somma      NUMERIC;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;
    IF p_quote IS NULL OR jsonb_array_length(p_quote) = 0 THEN
        RAISE EXCEPTION 'p_quote non può essere vuoto';
    END IF;

    SELECT round(COALESCE(SUM((q->>'quota_importo')::NUMERIC), 0), 2)
    INTO v_somma
    FROM jsonb_array_elements(p_quote) AS q;

    IF abs(v_somma - round(p_importo_totale, 2)) > 0.01 THEN
        RAISE EXCEPTION
            'Le quote non pareggiano il costo: somma % vs importo % (scarto %)',
            v_somma, round(p_importo_totale, 2), v_somma - round(p_importo_totale, 2);
    END IF;

    INSERT INTO public.riparto_costi_catena (
        user_id, origine, file_origine, fornitore, descrizione,
        importo_totale, tipo, anno, mese, regola
    )
    VALUES (
        p_user_id, p_origine, p_file_origine, p_fornitore, p_descrizione,
        p_importo_totale, p_tipo, p_anno, p_mese, p_regola
    )
    RETURNING id INTO v_riparto_id;

    INSERT INTO public.riparto_costi_catena_quote (
        riparto_id, ristorante_id, quota_perc, quota_importo, categoria
    )
    SELECT
        v_riparto_id,
        (q->>'ristorante_id')::UUID,
        (q->>'quota_perc')::NUMERIC,
        (q->>'quota_importo')::NUMERIC,
        NULLIF(q->>'categoria', '')
    FROM jsonb_array_elements(p_quote) AS q;

    -- Se l'insert delle quote fallisce (vincolo, tipo, ecc.) l'eccezione propaga e
    -- l'intera transazione (padre incluso) viene annullata da Postgres: nessun
    -- riparto orfano può esistere, per costruzione.
    RETURN v_riparto_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.sostituisci_quote_riparto(
    p_riparto_id     UUID,
    p_user_id        UUID,
    p_tipo           TEXT,
    p_regola         TEXT,
    p_importo_totale NUMERIC,
    p_quote          JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated_id UUID;
    v_somma      NUMERIC;
BEGIN
    IF p_user_id IS NULL OR p_riparto_id IS NULL THEN
        RAISE EXCEPTION 'p_riparto_id e p_user_id non possono essere NULL';
    END IF;
    IF p_quote IS NULL OR jsonb_array_length(p_quote) = 0 THEN
        RAISE EXCEPTION 'p_quote non può essere vuoto';
    END IF;

    -- Qui il controllo pesa più che nella crea: tutti e 19 gli sbilanciamenti
    -- storici erano su costi RI-SCRITTI, non su costi appena creati.
    SELECT round(COALESCE(SUM((q->>'quota_importo')::NUMERIC), 0), 2)
    INTO v_somma
    FROM jsonb_array_elements(p_quote) AS q;

    IF abs(v_somma - round(p_importo_totale, 2)) > 0.01 THEN
        RAISE EXCEPTION
            'Le quote non pareggiano il costo: somma % vs importo % (scarto %)',
            v_somma, round(p_importo_totale, 2), v_somma - round(p_importo_totale, 2);
    END IF;

    UPDATE public.riparto_costi_catena
    SET tipo = p_tipo, regola = p_regola, importo_totale = p_importo_totale
    WHERE id = p_riparto_id AND user_id = p_user_id
    RETURNING id INTO v_updated_id;

    IF v_updated_id IS NULL THEN
        RAISE EXCEPTION 'Riparto % non trovato per user %', p_riparto_id, p_user_id;
    END IF;

    DELETE FROM public.riparto_costi_catena_quote WHERE riparto_id = v_updated_id;

    INSERT INTO public.riparto_costi_catena_quote (
        riparto_id, ristorante_id, quota_perc, quota_importo, categoria
    )
    SELECT
        v_updated_id,
        (q->>'ristorante_id')::UUID,
        (q->>'quota_perc')::NUMERIC,
        (q->>'quota_importo')::NUMERIC,
        NULLIF(q->>'categoria', '')
    FROM jsonb_array_elements(p_quote) AS q;

    -- Se insert/delete fallisce, l'eccezione propaga e Postgres annulla anche
    -- l'UPDATE del padre: il riparto non può mai restare senza quote a metà.
    RETURN v_updated_id;
END;
$$;

COMMENT ON FUNCTION public.crea_riparto_con_quote(
    UUID, TEXT, TEXT, TEXT, TEXT, NUMERIC, TEXT, INTEGER, INTEGER, TEXT, JSONB
) IS
    'Crea un riparto_costi_catena e le sue quote in un''unica transazione. '
    'Rifiuta quote che non pareggiano l''importo del costo (tolleranza 1 cent): '
    'lo scarto finirebbe nel MOL via riparto_quote_mensili.';

COMMENT ON FUNCTION public.sostituisci_quote_riparto(
    UUID, UUID, TEXT, TEXT, NUMERIC, JSONB
) IS
    'Aggiorna un riparto_costi_catena e rimpiazza le sue quote in un''unica '
    'transazione. Rifiuta quote che non pareggiano l''importo del costo '
    '(tolleranza 1 cent): è il percorso da cui provenivano tutti e 19 gli '
    'sbilanciamenti storici sanati dalla migration 20260828210000.';
