-- Pool chat condiviso per gli account multi-sede (catene).
--
-- Prima il rate limit aveva due basi di conteggio incoerenti: la chat di sede
-- contava per ristorante_id (es. 30/giorno per PV, indipendenti), la chat di
-- catena contava per user_id (somma sedi) MA, passando p_ristorante_id NULL,
-- inseriva righe senza ristorante_id (persa l'attribuzione del PV d'origine).
--
-- Nuovo modello: UN SOLO pool per account. `p_pool = true` (account multi-sede)
-- conta per user_id — lo stesso pool è speso tra catena e tutti i PV — ma la riga
-- è SEMPRE loggata con la sede d'origine (p_ristorante_id) per l'attribuzione.
-- `p_pool = false` (default, sede singola) mantiene il conteggio per ristorante.
--
-- Idempotente. service_role only (auth custom, auth.uid() sempre NULL).

DROP FUNCTION IF EXISTS public.chat_usage_check_and_log(UUID, UUID, INTEGER);

CREATE OR REPLACE FUNCTION public.chat_usage_check_and_log(
    p_user_id       UUID,
    p_ristorante_id UUID,
    p_limite        INTEGER,
    p_pool          BOOLEAN DEFAULT false
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_inizio  TIMESTAMPTZ := date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
    v_count   INTEGER;
BEGIN
    IF p_limite IS NULL OR p_limite <= 0 THEN
        RETURN -1;
    END IF;

    -- Conteggio odierno con lock implicito della transazione.
    -- Pool → per user_id (condiviso); altrimenti per ristorante (o user se NULL).
    SELECT count(*)::int INTO v_count
    FROM public.chat_usage_log
    WHERE created_at >= v_inizio
      AND (
        (p_pool AND user_id = p_user_id)
        OR (NOT p_pool AND p_ristorante_id IS NOT NULL AND ristorante_id = p_ristorante_id)
        OR (NOT p_pool AND p_ristorante_id IS NULL AND user_id = p_user_id)
      );

    IF v_count >= p_limite THEN
        RETURN -1;
    END IF;

    -- La riga conserva SEMPRE la sede d'origine (anche in pool), per l'attribuzione.
    INSERT INTO public.chat_usage_log (user_id, ristorante_id)
    VALUES (p_user_id, p_ristorante_id);

    RETURN v_count + 1;
END;
$$;

COMMENT ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN) IS
    'Rate limit chat atomico: conta+inserisce in un solo statement. p_pool=true conta '
    'per user_id (pool condiviso di gruppo) loggando la sede d''origine. Ritorna il '
    'nuovo conteggio (>=1) se sotto il limite, -1 se il limite e'' raggiunto.';

REVOKE ALL ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN) TO service_role;
