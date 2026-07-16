-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: via d'uscita dalla coda "da assegnare" (scarto senza assegnazione)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto (16/07/2026):
--   La coda da_assegnare esiste solo per le catene same-P.IVA (OFFSIDE: 2 sedi,
--   P.IVA 07863990961). Oggi da quella coda si esce SOLO assegnando la fattura a
--   un locale o ripartendola sul gruppo: entrambe la fanno ENTRARE nei costi.
--   Non esiste alcun modo di dire "questa non c'entra" — né in UI, né via API, né
--   in DB (le RPC della coda sono claim/retry/done/resolve_unknown_tenant/assegna:
--   nessuna porta 'da_assegnare' a uno stato terminale senza sede).
--
--   Conseguenza reale: un documento finito in coda per errore (già presente con
--   altro nome file, documento non pertinente, fattura da non contabilizzare)
--   resta lì per sempre e sporca il conteggio del briefing di gruppo.
--
-- Cosa fa:
--   RPC scarta_fattura_da_coda(): porta un item 'da_assegnare' a 'scartata',
--   stato TERMINALE — il worker non claima quello stato (claim_batch_for_processing
--   filtra status='pending'), quindi la fattura non entrerà mai in fatture.
--
-- Perché uno stato nuovo e non un DELETE:
--   l'event_id resta in tabella, e l'UNIQUE su event_id è ciò che rende idempotente
--   il re-upload (accoda_upload_ambiguo, 'manual:<user>:<hash>'). Cancellando la riga
--   lo stesso file ricaricato rientrerebbe in coda: lo scarto non "terrebbe". Con lo
--   stato terminale invece il ri-upload trova il conflitto e non ricrea nulla —
--   ed è anche ciò che permette all'upload di dire "l'avevi scartata" invece di
--   riproporla in silenzio.
--
-- xml_content viene azzerato: la fattura non entrerà mai in app, tenerne il
-- contenuto è solo peso e superficie dati inutile (stessa logica di
-- purge_processed_xml_content per gli item 'done').
--
-- Due vincoli della tabella vanno estesi, non solo lo status (scoperti provando la
-- RPC su una fattura reale — senza, ogni scarto falliva):
--   - chk_fatture_queue_tenant_consistency: pretende user_id e ristorante_id
--     entrambi valorizzati o entrambi NULL. Una scartata ha il cliente ma NESSUNA
--     sede (è il senso dello scarto), esattamente come 'da_assegnare' → stessa
--     eccezione, altrimenti 23514.
--   - next_retry_at è NOT NULL: non si tocca (mark_queue_item_done fa lo stesso
--     sugli item 'done'; per uno stato terminale è un campo irrilevante).
--
-- Verificato in produzione il 16/7 su OFFSIDE (queue_id 223, poi ripristinata):
-- scarto OK, xml azzerato, xml_hash/event_id conservati, riscarto → false,
-- 0 righe pending (il worker non la prende), coda 20 → 19.
--
-- Idempotente: ri-eseguibile senza errori.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Nuovo stato terminale 'scartata' nel CHECK di fatture_queue.status
-- ─────────────────────────────────────────────────────────────────────────────
-- Il constraint si chiama chk_fatture_queue_status (creato in 045, ampliato da
-- 20260611140000_multi_sede_routing.sql): va droppato per nome esatto, altrimenti
-- il vecchio sopravvive accanto al nuovo e continua a vietare 'scartata'.
ALTER TABLE public.fatture_queue
    DROP CONSTRAINT IF EXISTS chk_fatture_queue_status;

ALTER TABLE public.fatture_queue
    ADD CONSTRAINT chk_fatture_queue_status CHECK (status IN (
        'pending', 'processing', 'done',
        'failed', 'dead', 'unknown_tenant',
        'da_assegnare', 'scartata'
    ));

-- ─────────────────────────────────────────────────────────────────────────────
-- 1b. Coerenza tenant: ammetti anche 'scartata' senza sede
-- ─────────────────────────────────────────────────────────────────────────────
-- chk_fatture_queue_tenant_consistency pretende che user_id e ristorante_id siano
-- entrambi NULL o entrambi valorizzati; 20260611140000 ha aggiunto l'eccezione per
-- 'da_assegnare' (cliente noto, sede ancora ignota). Una fattura SCARTATA è nella
-- stessa identica condizione — non le viene mai assegnata una sede, è il senso
-- dello scarto — quindi le serve la stessa eccezione, o l'UPDATE della RPC viola
-- il CHECK (23514) e ogni scarto fallisce.
ALTER TABLE public.fatture_queue
    DROP CONSTRAINT IF EXISTS chk_fatture_queue_tenant_consistency;

ALTER TABLE public.fatture_queue
    ADD CONSTRAINT chk_fatture_queue_tenant_consistency CHECK (
        (user_id IS NULL AND ristorante_id IS NULL)
        OR (user_id IS NOT NULL AND ristorante_id IS NOT NULL)
        OR (status IN ('da_assegnare', 'scartata') AND user_id IS NOT NULL AND ristorante_id IS NULL)
    );

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. RPC scarta_fattura_da_coda()
-- ─────────────────────────────────────────────────────────────────────────────
-- Guard cross-tenant lato DB (p_user_id nel WHERE): un utente non può scartare la
-- coda di un altro cliente nemmeno se indovinasse il queue_id.
--
-- Ritorna TRUE se ha scartato, FALSE se l'item non esiste, non è del chiamante o
-- non è più 'da_assegnare' (race con un'assegnazione: chi assegna vince, lo scarto
-- diventa un no-op — la UI lo tratta come "già gestita", non come errore).
CREATE OR REPLACE FUNCTION public.scarta_fattura_da_coda(
    p_queue_id BIGINT,
    p_user_id  UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_updated INTEGER := 0;
BEGIN
    IF p_queue_id IS NULL OR p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_queue_id e p_user_id sono obbligatori';
    END IF;

    -- next_retry_at NON si tocca: è NOT NULL (default now()) e per uno stato
    -- terminale è irrilevante — mark_queue_item_done, che chiude gli item 'done',
    -- lo lascia dov'è per lo stesso motivo. Metterlo a NULL violava il vincolo e
    -- faceva fallire ogni scarto (23502).
    -- xml_purged_at traccia l'azzeramento come per gli item done (purge_processed_
    -- xml_content); xml_hash resta, ed è ciò che rende idempotente il re-upload.
    UPDATE public.fatture_queue
    SET status        = 'scartata',
        xml_content   = NULL,
        xml_purged_at = now(),
        processed_at  = now(),
        locked_at     = NULL,
        locked_by     = NULL
    WHERE id = p_queue_id
      AND user_id = p_user_id
      AND status = 'da_assegnare';

    -- Stesso pattern di sposta_fattura_a_sede/assegna_fattura_a_sede (RPC gemelle
    -- sulla stessa tabella): ROW_COUNT è un item valido di GET DIAGNOSTICS.
    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated > 0;
END;
$$;

COMMENT ON FUNCTION public.scarta_fattura_da_coda(BIGINT, UUID) IS
    'Scarta una fattura ferma in coda da_assegnare senza assegnarla ad alcuna sede: '
    'status diventa ''scartata'' (terminale, mai claimato dal worker) e xml_content '
    'viene azzerato. La riga resta in tabella perché l''UNIQUE su event_id è ciò che '
    'rende idempotenti i re-upload. Guard cross-tenant via p_user_id. '
    'Ritorna FALSE se l''item non è del chiamante o non è più da_assegnare (race con '
    'un''assegnazione concorrente).';

REVOKE ALL ON FUNCTION public.scarta_fattura_da_coda(BIGINT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.scarta_fattura_da_coda(BIGINT, UUID) TO service_role;
