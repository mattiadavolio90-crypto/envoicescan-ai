-- ============================================================
-- MIGRATION: add ristorante_id to upload_events
-- Data: 2026-05-13
-- Scopo: aggiungere colonna ristorante_id a upload_events per
--        consentire filtro per-ristorante in riepilogo_fatture_auto_da_ultimo_login
--        e ingestion notification_inbox upload-specific.
--
-- La colonna era già presente in details->>'ristorante_id' come campo JSONB.
-- Questo step la promuove a colonna tabellare indicizzata e la backfilla dai dati
-- già presenti. Nessun dato viene perso.
-- ============================================================

-- 1. Aggiunge colonna (nullable: righe storiche prima del deploy restano NULL)
ALTER TABLE public.upload_events
    ADD COLUMN IF NOT EXISTS ristorante_id uuid NULL;

-- 2. Backfill dalle righe esistenti dove details contiene ristorante_id valido
UPDATE public.upload_events
SET    ristorante_id = (details->>'ristorante_id')::uuid
WHERE  ristorante_id IS NULL
  AND  details->>'ristorante_id' IS NOT NULL
  AND  (details->>'ristorante_id') ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$';

-- 3. Indice per query riepilogo post-login (filtra needs_ack=true per ristorante)
CREATE INDEX IF NOT EXISTS idx_upload_events_ristorante_needs_ack
    ON public.upload_events (ristorante_id, needs_ack)
    WHERE needs_ack = TRUE;

-- 4. Indice per lookup notifiche upload per ristorante (ingestion inbox)
CREATE INDEX IF NOT EXISTS idx_upload_events_ristorante_status
    ON public.upload_events (ristorante_id, status, created_at DESC)
    WHERE ristorante_id IS NOT NULL;
