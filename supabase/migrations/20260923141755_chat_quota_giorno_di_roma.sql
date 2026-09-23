-- Il giorno della quota chat e' quello del ristoratore, non quello del server.
--
-- La finestra di conteggio era `date_trunc('day', now() AT TIME ZONE 'UTC')`:
-- mezzanotte UTC, cioe' l'01:00 di Roma d'inverno e le 02:00 d'estate. Un cliente
-- che chattava dopo mezzanotte spendeva la quota del giorno precedente, e il
-- messaggio "Riprova domani" era falso in entrambe le direzioni (chi finisce la
-- quota alle 23:00 riparte fra un'ora; chi la finisce alle 00:30 ha gia' "domani"
-- sul calendario ma aspetta fino all'01:00).
--
-- Misurato sul DB live il 23/09/2026: 1 riga su 95 era gia' stata addebitata al
-- giorno sbagliato (2026-06-17T23:25Z = 18/06 01:25 a Roma).
--
-- Non e' una convenzione del prodotto: due RPC calcolano gia' "oggi" con
-- `(now() AT TIME ZONE 'Europe/Rome')::date`
-- (20260620020000_rpc_dashboard_stats_aggregata.sql:32,
--  20260912075621_oscura_fattura.sql:186) e il backend ha `_oggi_rome()`, il cui
-- docstring descrive esattamente questo difetto. La quota chat era l'eccezione
-- rimasta indietro.
--
-- Il gemello Python `_chat_domande_oggi` (services/fastapi_worker.py) conta la
-- STESSA finestra: i due devono restare allineati, o il contatore mostrato al
-- cliente e quello applicato divergono.
--
-- Solo la finestra cambia: firma, pool, attribuzione della sede e semantica di
-- ritorno restano identiche. Idempotente. service_role only.

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
    -- Mezzanotte di Roma, riportata a timestamptz: il confronto con created_at
    -- (timestamptz) resta assoluto e corretto in entrambi i regimi CET/CEST.
    v_inizio  TIMESTAMPTZ := ((now() AT TIME ZONE 'Europe/Rome')::date)::timestamp
                             AT TIME ZONE 'Europe/Rome';
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
    'Rate limit chat atomico: conta+inserisce in un solo statement. La finestra e'' '
    'il giorno di Europe/Rome (non UTC): il contatore si azzera a mezzanotte per il '
    'ristoratore. p_pool=true conta per user_id (pool condiviso di gruppo) loggando '
    'la sede d''origine. Ritorna il nuovo conteggio (>=1) se sotto il limite, -1 se '
    'il limite e'' raggiunto.';

REVOKE ALL ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN) TO service_role;
