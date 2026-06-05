-- Rate limit chat atomico: conta+inserisce in un solo statement.
--
-- Prima il worker faceva SELECT count + (dopo OpenAI) INSERT separati: N richieste
-- concorrenti dello stesso utente leggevano lo stesso conteggio e passavano tutte
-- il gate, superando il limite (e il tetto costi OpenAI). Inoltre l'INSERT post-
-- chiamata in try/except non bloccante rendeva il limite aggirabile se falliva.
--
-- Questa RPC, chiamata PRIMA della chiamata OpenAI:
--   - conta le richieste di oggi (UTC) per ristorante (o utente se ristorante NULL)
--   - se >= limite: NON inserisce e ritorna -1 (il worker risponde 429)
--   - altrimenti: inserisce la riga e ritorna il nuovo conteggio (>=1)
-- Eseguita in una sola transazione: niente race, fail-closed (se solleva, il
-- worker rifiuta la domanda).

CREATE OR REPLACE FUNCTION public.chat_usage_check_and_log(
    p_user_id       UUID,
    p_ristorante_id UUID,
    p_limite        INTEGER
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

    -- Conteggio odierno con lock implicito della transazione
    SELECT count(*)::int INTO v_count
    FROM public.chat_usage_log
    WHERE created_at >= v_inizio
      AND (
        (p_ristorante_id IS NOT NULL AND ristorante_id = p_ristorante_id)
        OR (p_ristorante_id IS NULL AND user_id = p_user_id)
      );

    IF v_count >= p_limite THEN
        RETURN -1;
    END IF;

    INSERT INTO public.chat_usage_log (user_id, ristorante_id)
    VALUES (p_user_id, p_ristorante_id);

    RETURN v_count + 1;
END;
$$;

COMMENT ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER) IS
    'Rate limit chat atomico: conta+inserisce in un solo statement. Ritorna il '
    'nuovo conteggio (>=1) se sotto il limite, -1 se il limite e'' raggiunto.';

REVOKE ALL ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER) TO service_role;
