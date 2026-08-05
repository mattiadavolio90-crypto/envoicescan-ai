-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: RPC transazionale per sostituire le quote di un riparto esistente
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: audit §1 "perimetro mai letto" (services/routers/riparto.py), 5/8/2026,
-- chiusura completa (HIGH+MEDIUM+gap residuo dallo stesso audit).
--
-- riparto_modifica (PATCH /api/riparto/{id}) aggiorna il padre, poi rimpiazza le
-- quote con delete + insert come due statement PostgREST separati, senza
-- transazione. Se l'insert fallisce dopo il delete, il riparto resta scritto
-- SENZA quote: stesso rischio "orfano invisibile al motore MOL" già risolto in
-- creazione da crea_riparto_con_quote (migration 20260805143000), qui sul lato
-- modifica.
--
-- Questa RPC avvolge update padre + delete quote + insert quote in un'unica
-- transazione: se una fase fallisce, tutte vengono annullate e il riparto resta
-- nello stato precedente (mai "orfano" a metà). Le chiamate Python restano owner
-- della logica applicativa (validazione, calcolo quote) — la RPC riceve solo il
-- payload finale già pronto.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.sostituisci_quote_riparto(
    p_riparto_id     UUID,
    p_user_id        UUID,
    p_tipo           TEXT,
    p_regola         TEXT,
    p_importo_totale NUMERIC,
    p_quote          JSONB   -- [{"ristorante_id": "...", "quota_perc": .., "quota_importo": .., "categoria": ..|null}, ...]
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated_id UUID;
BEGIN
    IF p_riparto_id IS NULL OR p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_riparto_id e p_user_id non possono essere NULL';
    END IF;
    IF p_quote IS NULL OR jsonb_array_length(p_quote) = 0 THEN
        RAISE EXCEPTION 'p_quote non può essere vuoto';
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

COMMENT ON FUNCTION public.sostituisci_quote_riparto(
    UUID, UUID, TEXT, TEXT, NUMERIC, JSONB
) IS
    'Aggiorna un riparto_costi_catena e rimpiazza le sue riparto_costi_catena_quote '
    'in una singola transazione: se il rimpiazzo fallisce, il riparto non resta mai '
    'senza quote (niente stato "orfano" invisibile al motore MOL). Usata da '
    'riparto_modifica in services/routers/riparto.py.';

REVOKE ALL ON FUNCTION public.sostituisci_quote_riparto(
    UUID, UUID, TEXT, TEXT, NUMERIC, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sostituisci_quote_riparto(
    UUID, UUID, TEXT, TEXT, NUMERIC, JSONB
) TO service_role;
