-- Le code non prendono piu' elementi del lotto chiesto.
--
-- `claim_batch_for_processing` (fatture_queue) e `claim_ricavi_email_batch`
-- (ricavi_email_queue) erano scritte come
--     UPDATE ... WHERE id IN (SELECT id ... LIMIT n FOR UPDATE SKIP LOCKED)
-- Se il planner esegue la IN come nested loop con la sottoquery all'interno, la
-- sottoquery col LIMIT si rivaluta a ogni giro; le righe gia' aggiornate dallo
-- stesso statement vengono saltate dal LockRows, quindi ogni giro ne porta di
-- nuove e il lotto sfonda (12 fatture con un lotto da 10). Il piano dipende
-- dalle statistiche della tabella: e' uscito nella CI del 10/10/2026
-- (`test_sql_concorrenza_coda`, `test_sql_funzioni_soldi`), rosso
-- intermittente gia' visto il 30/09.
--
-- Effetto in produzione: un worker poteva prendere piu' item del lotto (mai lo
-- stesso item due volte: le righe restano bloccate da chi le prende).
--
-- FIX: la scelta delle righe in una CTE MATERIALIZED, eseguita una volta sola,
-- poi UPDATE ... FROM la CTE. Firma, grant e comportamento invariati.
-- Idempotente (CREATE OR REPLACE con la stessa firma: i grant restano).

CREATE OR REPLACE FUNCTION public.claim_batch_for_processing(
    p_worker_id  TEXT,
    p_batch_size INTEGER DEFAULT 10
)
RETURNS SETOF public.fatture_queue
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_worker_id IS NULL OR trim(p_worker_id) = '' THEN
        RAISE EXCEPTION 'p_worker_id non può essere NULL o vuoto';
    END IF;
    IF p_batch_size < 1 OR p_batch_size > 100 THEN
        RAISE EXCEPTION 'p_batch_size deve essere tra 1 e 100, ricevuto: %', p_batch_size;
    END IF;

    RETURN QUERY
    WITH scelti AS MATERIALIZED (
        SELECT id
        FROM   public.fatture_queue
        WHERE  status IN ('pending', 'failed')
          AND  attempt_count < max_attempts
          AND  next_retry_at <= now()
          -- Recupera anche record con lock stale (worker crashato > 10 min fa)
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED   -- nessun blocco tra worker concorrenti
    )
    UPDATE public.fatture_queue fq
    SET
        status        = 'processing',
        locked_at     = now(),
        locked_by     = p_worker_id,
        attempt_count = fq.attempt_count + 1
    FROM scelti
    WHERE fq.id = scelti.id
    RETURNING fq.*;
END;
$$;

COMMENT ON FUNCTION public.claim_batch_for_processing(TEXT, INTEGER) IS
    'Acquisisce atomicamente un batch di record pending/failed per il worker. '
    'FOR UPDATE SKIP LOCKED in una CTE MATERIALIZED (10/10/2026: con IN (... LIMIT) '
    'un nested loop rivalutava il LIMIT e il lotto sfondava). '
    'Incrementa attempt_count e imposta il lock (locked_at, locked_by). '
    'Esclude attempt_count >= max_attempts.';

CREATE OR REPLACE FUNCTION public.claim_ricavi_email_batch(
    p_worker_id  TEXT,
    p_batch_size INTEGER DEFAULT 5
)
RETURNS SETOF public.ricavi_email_queue
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_worker_id IS NULL OR trim(p_worker_id) = '' THEN
        RAISE EXCEPTION 'p_worker_id non può essere NULL o vuoto';
    END IF;
    IF p_batch_size < 1 OR p_batch_size > 100 THEN
        RAISE EXCEPTION 'p_batch_size deve essere tra 1 e 100, ricevuto: %', p_batch_size;
    END IF;

    RETURN QUERY
    WITH scelti AS MATERIALIZED (
        SELECT id
        FROM   public.ricavi_email_queue
        WHERE  status IN ('pending', 'failed')
          AND  next_retry_at <= now()
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC, created_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE public.ricavi_email_queue q
    SET
        status        = 'processing',
        locked_at     = now(),
        locked_by     = p_worker_id,
        attempt_count = q.attempt_count + 1
    FROM scelti
    WHERE q.id = scelti.id
    RETURNING q.*;
END;
$$;

COMMENT ON FUNCTION public.claim_ricavi_email_batch(TEXT, INTEGER) IS
    'Acquisisce atomicamente un batch di ricavi_email_queue pending/failed per il worker. '
    'FOR UPDATE SKIP LOCKED in una CTE MATERIALIZED (10/10/2026, come '
    'claim_batch_for_processing); recupera lock stantii > 10 min.';

REVOKE ALL ON FUNCTION public.claim_batch_for_processing(TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_batch_for_processing(TEXT, INTEGER) TO service_role;
REVOKE ALL ON FUNCTION public.claim_ricavi_email_batch(TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_ricavi_email_batch(TEXT, INTEGER) TO service_role;
