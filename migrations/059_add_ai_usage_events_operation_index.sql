-- MIGRAZIONE 059: Indice per quota Vision e conteggi per tipo operazione
-- Nessuna nuova configurazione DB: il limite Vision resta nel codice.

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_rist_type_created
    ON public.ai_usage_events (ristorante_id, operation_type, created_at DESC);
