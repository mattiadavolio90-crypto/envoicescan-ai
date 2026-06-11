-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: RPC assegna_fattura_a_sede()
-- ═══════════════════════════════════════════════════════════════════════════════
-- Controparte manuale del routing multi-sede (migration 20260611140000):
-- quando il webhook NON riesce a smistare automaticamente una fattura fra le sedi
-- di un cliente (status='da_assegnare'), il cliente sceglie la sede in UI e questa
-- RPC completa l'assegnazione → la fattura torna 'pending' e il worker la elabora.
--
-- Gemella di resolve_unknown_tenant(): stessa filosofia (riattiva il record in coda),
-- ma qui la sede la decide un umano, non la P.IVA.
--
-- Sicurezza:
--   - SECURITY DEFINER + search_path bloccato (coerente con le altre RPC della coda).
--   - Verifica che il ristorante di destinazione appartenga allo STESSO user_id
--     del record in coda (no cross-tenant: non si può dirottare la fattura di un
--     cliente verso il ristorante di un altro).
--   - Verifica che il record sia davvero in stato 'da_assegnare'.
--
-- Idempotente nella definizione (CREATE OR REPLACE).
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.assegna_fattura_a_sede(
    p_queue_id      BIGINT,
    p_ristorante_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_queue_user_id UUID;
    v_queue_status  TEXT;
    v_rist_user_id  UUID;
    v_rist_attivo   BOOLEAN;
BEGIN
    -- Carica il record di coda (lock per evitare doppia assegnazione concorrente)
    SELECT user_id, status
    INTO   v_queue_user_id, v_queue_status
    FROM   public.fatture_queue
    WHERE  id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record coda % inesistente', p_queue_id;
    END IF;

    IF v_queue_status <> 'da_assegnare' THEN
        -- Non è in attesa di assegnazione: no-op sicuro (es. già assegnata da un
        -- altro click concorrente). Non solleviamo errore per non rompere la UI.
        RETURN FALSE;
    END IF;

    -- Carica la sede di destinazione
    SELECT user_id, attivo
    INTO   v_rist_user_id, v_rist_attivo
    FROM   public.ristoranti
    WHERE  id = p_ristorante_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ristorante % inesistente', p_ristorante_id;
    END IF;

    -- Guard cross-tenant: la sede deve appartenere allo stesso cliente della fattura.
    IF v_rist_user_id IS DISTINCT FROM v_queue_user_id THEN
        RAISE EXCEPTION 'Ristorante % non appartiene al cliente della fattura', p_ristorante_id;
    END IF;

    IF v_rist_attivo IS NOT TRUE THEN
        RAISE EXCEPTION 'Ristorante % non attivo', p_ristorante_id;
    END IF;

    -- Assegna e rimetti in coda di elaborazione.
    UPDATE public.fatture_queue
    SET
        ristorante_id = p_ristorante_id,
        status        = 'pending',
        next_retry_at = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        last_error    = NULL
    WHERE id = p_queue_id;

    RETURN TRUE;
END;
$$;

COMMENT ON FUNCTION public.assegna_fattura_a_sede(BIGINT, UUID) IS
    'Assegna manualmente una fattura in stato da_assegnare a una sede (ristorante) '
    'dello stesso cliente e la rimette in pending per il worker. Usata dalla UI '
    'della coda "fatture da assegnare". Restituisce TRUE se assegnata, FALSE se il '
    'record non era più in stato da_assegnare (assegnazione concorrente).';
