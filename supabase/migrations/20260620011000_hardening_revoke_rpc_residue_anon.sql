-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: HARDENING — REVOKE RPC residue eseguibili da anon/authenticated
-- ═══════════════════════════════════════════════════════════════════════════════
-- Completa l'audit anti-hacker 20/06. La 20260620010000 ha revocato le RPC
-- applicative; il re-scan advisor ha mostrato 7 RPC residue ancora ESECUTABILI
-- via PostgREST con la anon key pubblica. Tutte worker-internal o di tracking:
-- l'app le chiama via service_role, nessun client le usa direttamente.
--
--   - claim_ricavi_email_batch: GEMELLA di claim_batch_for_processing (il vettore
--     HIGH già chiuso). Claima batch dalla coda email ricavi → un anon potrebbe
--     leggere/manipolare la coda di QUALSIASI tenant. PRIORITARIA.
--   - track_ai_usage_event / increment_ai_cost: un anon potrebbe gonfiare i
--     contatori di costo AI di un ristorante arbitrario (avvelenamento dati/budget).
--   - get_ai_costs_timeseries / get_ai_recent_operations: lettura costi AI; hanno
--     scope auth.uid() interno (inerte per anon) ma vanno tolte dalla superficie.
--   - get_next_ordine_ricetta: SECURITY DEFINER, usata solo dal worker.
--   - fn_log_category_change: trigger function (i trigger girano nel contesto DML,
--     NON dipendono dal grant) → revocare l'EXECUTE diretto non rompe i trigger.
--
-- SICURO: auth custom (auth.uid()=NULL), accesso applicativo solo via service_role
-- che ignora i grant per-ruolo. Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════════

REVOKE ALL ON FUNCTION public.claim_ricavi_email_batch(text, integer)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_log_category_change()                       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_ai_costs_timeseries(integer)               FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_ai_recent_operations(integer, integer)     FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_next_ordine_ricetta(uuid, uuid)            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.increment_ai_cost(uuid, numeric, integer, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.track_ai_usage_event(uuid, text, text, integer, integer, numeric, numeric, numeric, uuid, text, integer, jsonb) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.claim_ricavi_email_batch(text, integer)        TO service_role;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_timeseries(integer)               TO service_role;
GRANT EXECUTE ON FUNCTION public.get_ai_recent_operations(integer, integer)     TO service_role;
GRANT EXECUTE ON FUNCTION public.get_next_ordine_ricetta(uuid, uuid)            TO service_role;
GRANT EXECUTE ON FUNCTION public.increment_ai_cost(uuid, numeric, integer, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.track_ai_usage_event(uuid, text, text, integer, integer, numeric, numeric, numeric, uuid, text, integer, jsonb) TO service_role;
-- fn_log_category_change: nessun GRANT — è una trigger function, gira nel contesto DML.
