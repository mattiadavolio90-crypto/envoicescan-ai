-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: RPC transazionale per creare un riparto + le sue quote
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: audit §1 "perimetro mai letto" (services/routers/riparto.py), 5/8/2026.
--
-- I 4 endpoint di creazione riparto (da-fattura, da-coda, manuale, duplica) fanno
-- insert padre (riparto_costi_catena) + insert quote (riparto_costi_catena_quote)
-- come due statement PostgREST separati, senza transazione. Se il secondo fallisce
-- (rete, vincolo), il padre resta scritto SENZA quote: un riparto "orfano",
-- invisibile al motore MOL (la RPC riparto_quote_mensili fa JOIN sulle quote) ma con
-- fatture.ripartita_su_gruppo già marcato TRUE — il costo sparisce dal MOL di tutte
-- le sedi in silenzio. Stessa classe dell'incidente FASTWEB del 22/7 (Voce 7).
--
-- Questa RPC avvolge i due insert in una transazione: se le quote falliscono, il
-- padre non resta mai scritto. Le chiamate Python restano owner della logica
-- applicativa (lettura fattura, calcolo importo/periodo, validazione) — la RPC
-- riceve solo il payload finale già pronto.
-- ═══════════════════════════════════════════════════════════════════════════════

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
    p_quote          JSONB   -- [{"ristorante_id": "...", "quota_perc": .., "quota_importo": .., "categoria": ..|null}, ...]
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_riparto_id UUID;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;
    IF p_quote IS NULL OR jsonb_array_length(p_quote) = 0 THEN
        RAISE EXCEPTION 'p_quote non può essere vuoto';
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

COMMENT ON FUNCTION public.crea_riparto_con_quote(
    UUID, TEXT, TEXT, TEXT, TEXT, NUMERIC, TEXT, INTEGER, INTEGER, TEXT, JSONB
) IS
    'Crea un riparto_costi_catena + le sue riparto_costi_catena_quote in una singola '
    'transazione: se le quote falliscono, il padre non resta mai scritto senza di '
    'esse (niente riparto "orfano" invisibile al motore MOL). Usata dai 4 endpoint '
    'di creazione in services/routers/riparto.py.';

REVOKE ALL ON FUNCTION public.crea_riparto_con_quote(
    UUID, TEXT, TEXT, TEXT, TEXT, NUMERIC, TEXT, INTEGER, INTEGER, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.crea_riparto_con_quote(
    UUID, TEXT, TEXT, TEXT, TEXT, NUMERIC, TEXT, INTEGER, INTEGER, TEXT, JSONB
) TO service_role;
