-- Claim atomico della coda ricavi_email_queue (SELECT FOR UPDATE SKIP LOCKED).
--
-- Prima il worker faceva SELECT + UPDATE separati (non atomici): due esecuzioni
-- concorrenti potevano claimare lo stesso record -> doppio import dello stesso XLS
-- ricavi -> ricavi giornalieri raddoppiati (e via trigger, margini gonfiati).
-- Questa RPC replica il pattern gia' usato per fatture_queue
-- (claim_batch_for_processing, migrations/045): un solo statement atomico,
-- recupera anche i lock stantii (worker crashato > 10 min fa).

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
    UPDATE public.ricavi_email_queue q
    SET
        status        = 'processing',
        locked_at     = now(),
        locked_by     = p_worker_id,
        attempt_count = q.attempt_count + 1
    WHERE q.id IN (
        SELECT id
        FROM   public.ricavi_email_queue
        WHERE  status IN ('pending', 'failed')
          AND  next_retry_at <= now()
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC, created_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING q.*;
END;
$$;

COMMENT ON FUNCTION public.claim_ricavi_email_batch(TEXT, INTEGER) IS
    'Acquisisce atomicamente un batch di ricavi_email_queue pending/failed per il worker. '
    'FOR UPDATE SKIP LOCKED per concorrenza sicura; recupera lock stantii > 10 min. '
    'Allinea la coda ricavi al pattern di claim_batch_for_processing (fatture_queue).';

-- GRANT espliciti coerenti col pattern di fatture_queue (045): service_role usa la
-- RPC; anon/authenticated non devono poterla invocare.
REVOKE ALL ON FUNCTION public.claim_ricavi_email_batch(TEXT, INTEGER) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_ricavi_email_batch(TEXT, INTEGER) TO service_role;
