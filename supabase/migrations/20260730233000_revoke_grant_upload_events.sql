-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: revoca grant residui anon/authenticated su upload_events
-- ═══════════════════════════════════════════════════════════════════════════════
-- CONTESTO (audit Database, 30/7/2026 — remediation LOW)
--   upload_events aveva GRANT ALL su anon/authenticated dalla migration legacy
--   033. L'hardening RLS del 22/4 (20260422143000) ha sostituito la policy
--   permissiva con policy user_id = auth.uid(), ma non ha revocato i grant.
--   L'audit del 5/6 (20260605180000) aveva gia' fatto la stessa pulizia su
--   ristoranti/margini_mensili/category_change_log con la motivazione "RLS e'
--   gia' ON con policy auth.uid()-based (deny in custom-auth), quindi i grant
--   erano inerti, ma vanno tolti per igiene" — applichiamo lo stesso qui.
--
--   Impatto reale: nullo. Con auth custom auth.uid() e' sempre NULL, le policy
--   negano tutto e i grant erano inerti sia prima che dopo questa migration.
--   upload_events.id e' uuid (default gen_random_uuid()): nessuna sequence
--   associata da revocare.
-- ═══════════════════════════════════════════════════════════════════════════════

REVOKE ALL ON public.upload_events FROM anon, authenticated;
