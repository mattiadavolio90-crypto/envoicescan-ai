-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: sede tecnica "Costi comuni di gruppo" + assegnazione dalla coda
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto (15/07/2026): PIANO ripartire-dalla-coda.
--
--   Una fattura di struttura di catena (commercialista, auto aziendale…) intestata
--   alla sede legale finisce in coda 'da_assegnare' senza sede. Per RIPARTIRLA sul
--   gruppo deve prima atterrare in public.fatture, dove ristorante_id è NOT NULL →
--   oggi si è costretti a scegliere UN locale a caso, e la fattura del commercialista
--   compare "dentro" quel locale (confusionario).
--
--   Rendere ristorante_id nullable è escluso (1368 riferimenti in tutta l'app la
--   presumono valorizzata). Soluzione: una SEDE TECNICA per account, contenitore dei
--   soli costi comuni, che soddisfa la FK/NOT NULL ma è ESCLUSA da tutte le viste
--   rivolte al cliente (selettore sede, gating catena, quote). ristorante_id resta
--   NOT NULL → zero rischio sull'app esistente.
--
-- Cosa fa:
--   1. Aggiunge ristoranti.sede_tecnica (default FALSE): flag della sede-contenitore.
--   2. RPC assegna_fattura_a_sede_tecnica(): gemella di assegna_fattura_a_sede, ma
--      trova/crea la sede tecnica dell'account e ci assegna l'item di coda → pending.
--      Il worker poi la processa normalmente (e la auto-marca ripartita_su_gruppo
--      perché la sede è tecnica — vedi worker/queue_processor.py).
--
-- Idempotente: ri-eseguibile senza errori.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Colonna sede_tecnica
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.ristoranti
    ADD COLUMN IF NOT EXISTS sede_tecnica BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.ristoranti.sede_tecnica IS
    'TRUE = sede tecnica "Costi comuni di gruppo": contenitore delle fatture di '
    'struttura di catena ripartite dalla coda. Soddisfa la FK/NOT NULL di '
    'fatture.ristorante_id ma è ESCLUSA da selettore sede, gating catena e quote '
    '(non è un locale reale, non ha incassi). Ogni fattura che vi atterra viene '
    'auto-marcata fatture.ripartita_su_gruppo dal worker.';

-- Al più una sede tecnica per account.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ristoranti_sede_tecnica_per_account
    ON public.ristoranti (user_id)
    WHERE sede_tecnica = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. RPC assegna_fattura_a_sede_tecnica()
-- ─────────────────────────────────────────────────────────────────────────────
-- Assegna un item 'da_assegnare' alla sede tecnica dell'account (creandola se serve)
-- e lo rimette 'pending' per il worker. Ritorna l'id della sede tecnica usata.
--
-- Sicurezza: SECURITY DEFINER + search_path bloccato (coerente con assegna_fattura_a_sede).
-- Il chiamante (worker service_role, dietro endpoint /api/riparto/da-coda) ha già
-- verificato ownership del record di coda.
CREATE OR REPLACE FUNCTION public.assegna_fattura_a_sede_tecnica(
    p_queue_id BIGINT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_queue_user_id UUID;
    v_queue_status  TEXT;
    v_tecnica_id    UUID;
    v_piva          TEXT;
BEGIN
    -- Record di coda (lock per evitare doppia assegnazione concorrente).
    SELECT user_id, status
    INTO   v_queue_user_id, v_queue_status
    FROM   public.fatture_queue
    WHERE  id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record coda % inesistente', p_queue_id;
    END IF;

    IF v_queue_status <> 'da_assegnare' THEN
        -- Già assegnata da un altro click concorrente: no-op sicuro.
        RETURN NULL;
    END IF;

    -- Trova la sede tecnica dell'account, o creala.
    SELECT id INTO v_tecnica_id
    FROM   public.ristoranti
    WHERE  user_id = v_queue_user_id AND sede_tecnica = TRUE
    LIMIT  1;

    IF v_tecnica_id IS NULL THEN
        -- partita_iva è NOT NULL su ristoranti: riusa quella di una sede reale
        -- dell'account (la sede tecnica non riceve fatture da SDI, la P.IVA serve
        -- solo a soddisfare il vincolo).
        SELECT partita_iva INTO v_piva
        FROM   public.ristoranti
        WHERE  user_id = v_queue_user_id AND COALESCE(sede_tecnica, FALSE) = FALSE
        ORDER  BY created_at
        LIMIT  1;

        IF v_piva IS NULL THEN
            RAISE EXCEPTION 'Nessuna sede reale per l''account %: impossibile creare la sede tecnica', v_queue_user_id;
        END IF;

        INSERT INTO public.ristoranti (
            user_id, nome_ristorante, partita_iva, attivo, sede_tecnica, sdi_attivo
        )
        VALUES (
            v_queue_user_id, 'Costi comuni di gruppo', v_piva, TRUE, TRUE, FALSE
        )
        RETURNING id INTO v_tecnica_id;
    END IF;

    -- Assegna e rimetti in coda di elaborazione.
    UPDATE public.fatture_queue
    SET
        ristorante_id = v_tecnica_id,
        status        = 'pending',
        next_retry_at = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        last_error    = NULL
    WHERE id = p_queue_id;

    RETURN v_tecnica_id;
END;
$$;

COMMENT ON FUNCTION public.assegna_fattura_a_sede_tecnica(BIGINT) IS
    'Assegna una fattura da_assegnare alla sede tecnica "Costi comuni di gruppo" '
    'dell''account (creandola se non esiste) e la rimette pending per il worker. '
    'Usata dal flusso "ripartisci dalla coda". Ritorna l''id della sede tecnica, '
    'oppure NULL se il record non era più da_assegnare (assegnazione concorrente).';

REVOKE ALL ON FUNCTION public.assegna_fattura_a_sede_tecnica(BIGINT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.assegna_fattura_a_sede_tecnica(BIGINT) TO service_role;
