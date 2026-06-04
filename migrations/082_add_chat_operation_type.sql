-- ============================================================
-- MIGRATION 082: Aggiunge 'chat' ai tipi operazione AI tracciabili
-- ============================================================
-- La chat con l'assistente AI ora traccia i costi nel ledger ai_usage_events
-- (operation_type='chat'). Il CHECK originale (migration 051) ammetteva solo
-- 'pdf', 'categorization', 'other' e avrebbe rifiutato l'INSERT.

ALTER TABLE public.ai_usage_events
    DROP CONSTRAINT IF EXISTS ai_usage_events_operation_type_check;

ALTER TABLE public.ai_usage_events
    ADD CONSTRAINT ai_usage_events_operation_type_check
    CHECK (operation_type IN ('pdf', 'categorization', 'chat', 'other'));
