-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: FK GDPR su fatture_queue + tappo al loop di retry senza fine
-- ═══════════════════════════════════════════════════════════════════════════════
-- CONTESTO (audit Database, 30/7/2026 — remediation dei 2 HIGH)
--
-- HIGH #1 — fatture_queue non ha mai avuto FK verso users/ristoranti (scelta
--   esplicita di 045_create_fatture_queue.sql: "evita errori di integrita
--   referenziale quando il record arriva prima della registrazione del
--   ristorante"). Motivata all'epoca, ma mai rivista dopo l'introduzione della
--   cancellazione GDPR: sia /api/account/elimina (self-service Art.17) sia
--   admin_elimina_cliente NON ripulivano fatture_queue, lasciando in coda
--   righe con piva_raw/payload_meta/indirizzo_raw del cliente cancellato.
--   Verificato sul DB live prima di questa migration: 0 righe orfane su
--   user_id e su ristorante_id, quindi la FK non ha nulla da rifiutare.
--   Nullable per costruzione: il caso "record arriva prima della
--   registrazione" ha user_id/ristorante_id NULL, e una FK nullable non e
--   mai violata da NULL — il motivo originale della scelta 045 resta intatto.
--
-- HIGH #2 — release_stale_locks riporta gli item da 'processing' a 'failed'
--   senza mai controllare attempt_count >= max_attempts. Un item che ha gia
--   esaurito i tentativi ma viene ripescato per lock stale (worker crashato
--   a meta elaborazione) torna 'failed' con next_retry_at invariato: se era
--   gia passato, e immediatamente ri-claimabile da claim_batch_for_processing,
--   che filtra solo su status/next_retry_at — mai su attempt_count. Un item
--   "avvelenato" (che uccide il processo invece di sollevare un'eccezione
--   catturabile) puo quindi occupare uno slot di coda a tempo indeterminato
--   senza mai comparire fra i 'dead' che il monitoraggio guarda.
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. FK GDPR su fatture_queue (nullable, ON DELETE CASCADE)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.fatture_queue
    ADD CONSTRAINT fatture_queue_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.fatture_queue
    ADD CONSTRAINT fatture_queue_ristorante_id_fkey
    FOREIGN KEY (ristorante_id) REFERENCES public.ristoranti(id) ON DELETE CASCADE;

COMMENT ON CONSTRAINT fatture_queue_user_id_fkey ON public.fatture_queue IS
    'Aggiunta 30/7/2026 (audit Database): chiude il buco GDPR per cui la coda '
    'sopravviveva alla cancellazione account. Nullable: non rompe il caso '
    '"evento arriva prima della registrazione del ristorante".';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Tappo al retry: release_stale_locks rispetta max_attempts
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.release_stale_locks(
    p_timeout_minutes INTEGER DEFAULT 10
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE public.fatture_queue
    SET
        status     = CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END,
        last_error = format(
            'Lock stale rilasciato: worker %s bloccato da %s minuti (timeout: %s min)',
            locked_by,
            EXTRACT(EPOCH FROM (now() - locked_at)) / 60,
            p_timeout_minutes
        ),
        locked_at = NULL,
        locked_by = NULL,
        -- Se torna 'failed' rimandiamo il prossimo retry di 1 minuto: evita il
        -- re-claim immediato dello stesso worker/istanza appena riavviata, che
        -- altrimenti puo rientrare subito nello stesso ciclo crash → stale.
        -- Se va 'dead' next_retry_at non conta piu (claim_batch la esclude).
        next_retry_at = CASE
            WHEN attempt_count >= max_attempts THEN next_retry_at
            ELSE now() + INTERVAL '1 minute'
        END
    WHERE status    = 'processing'
      AND locked_at < now() - make_interval(mins => p_timeout_minutes);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$$;

COMMENT ON FUNCTION public.release_stale_locks(INTEGER) IS
    'Rilascia i lock di worker morti (status=processing da più di N min). '
    'Reimposta status=failed per permettere il retry, oppure status=dead se '
    'attempt_count ha gia raggiunto max_attempts (30/7/2026: prima restava '
    '''failed'' per sempre e poteva essere ri-claimata all''infinito). '
    'Chiamare all''avvio del worker come safety net contro crash.';

-- Difesa in profondità: anche claim_batch_for_processing non deve poter
-- ripescare un item che ha gia esaurito i tentativi, qualunque sia lo status
-- con cui vi e arrivato.
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
    UPDATE public.fatture_queue fq
    SET
        status        = 'processing',
        locked_at     = now(),
        locked_by     = p_worker_id,
        attempt_count = fq.attempt_count + 1
    WHERE fq.id IN (
        SELECT id
        FROM   public.fatture_queue
        WHERE  status IN ('pending', 'failed')
          AND  attempt_count < max_attempts
          AND  next_retry_at <= now()
          -- Recupera anche record con lock stale (worker crashato > 10 min fa)
          AND  (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
        ORDER BY next_retry_at ASC
        LIMIT  p_batch_size
        FOR UPDATE SKIP LOCKED   -- chiave: nessun blocco tra worker concorrenti
    )
    RETURNING fq.*;
END;
$$;

COMMENT ON FUNCTION public.claim_batch_for_processing(TEXT, INTEGER) IS
    'Acquisisce atomicamente un batch di record pending/failed per il worker. '
    'Usa FOR UPDATE SKIP LOCKED per concorrenza sicura tra più worker paralleli. '
    'Incrementa attempt_count e imposta il lock (locked_at, locked_by). '
    'Esclude attempt_count >= max_attempts (30/7/2026: difesa in profondità, '
    'nel caso un item esaurito torni a pending/failed per una via diversa da '
    'release_stale_locks).';

COMMIT;
