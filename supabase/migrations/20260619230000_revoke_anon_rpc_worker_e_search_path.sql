-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: REVOKE EXECUTE da anon/authenticated su RPC worker-internal + search_path
-- ═══════════════════════════════════════════════════════════════════════════════
-- Completamento audit 19/06 (passata DATABASE di copertura). L'hardening RLS aveva
-- chiuso le TABELLE esposte ad anon; restavano esposte delle FUNZIONI.
--
-- PROBLEMA (confermato sul DB live impersonando il ruolo anon):
--   Diverse RPC nascono con GRANT EXECUTE TO PUBLIC (default PostgreSQL) e non sono
--   mai state revocate. Sono raggiungibili via PostgREST con la ANON KEY pubblica.
--   La più grave, claim_batch_for_processing (SECURITY DEFINER → bypassa RLS),
--   restituisce xml_content / piva_raw / user_id / payload_meta dei record di coda
--   di QUALSIASI tenant: un anon può claimare batch e leggere il contenuto delle
--   fatture di tutti i clienti. Le altre RPC della coda permettono manipolazione di
--   stato (schedule_retry → 'dead', mark_queue_item_done → perdita fattura + purge
--   XML, release_stale_locks, purge_processed_xml_content, resolve_unknown_tenant).
--   Provato in transazione con ROLLBACK: anon NON riceve insufficient_privilege.
--
-- Inoltre 2 RPC nuove (costi_automatici_mensili, chat_top_categoria_fornitore) sono
-- SECURITY INVOKER ma EXECUTE TO PUBLIC e senza guard cross-tenant: accettano
-- p_user_id arbitrario. Vanno revocate da anon (l'app le chiama via service_role).
--
-- FIX:
--   1. REVOKE EXECUTE da public/anon/authenticated su tutte le RPC solo-worker e
--      sulle 2 RPC analitiche; GRANT solo a service_role (= il client dell'app).
--   2. SET search_path sulle 2 SECURITY DEFINER che ne erano prive
--      (fn_log_category_change, get_distinct_files(text) legacy) — chiude il rischio
--      di search_path hijack segnalato dall'advisor.
--   3. get_distinct_files(uuid) e (uuid,uuid) hanno già un guard auth ma sono
--      eseguibili da anon: REVOKE da anon per difesa in profondità (l'app le chiama
--      via service_role; nessun client è 'authenticated' con auth custom).
--
-- SICURO: l'auth è custom (auth.uid()=NULL), tutto l'accesso applicativo passa da
--   service_role che IGNORA i grant per-ruolo. Nessuna funzionalità si rompe.
--
-- Idempotente: REVOKE/GRANT/ALTER ripetibili.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── 1. RPC coda fatture (worker-internal) — il vettore HIGH ──────────────────
REVOKE ALL ON FUNCTION public.claim_batch_for_processing(text, integer)   FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.schedule_retry(bigint, text)                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.mark_queue_item_done(bigint, boolean)       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.resolve_unknown_tenant(text)                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.release_stale_locks(integer)                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.purge_processed_xml_content(integer)        FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.claim_batch_for_processing(text, integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.schedule_retry(bigint, text)              TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_queue_item_done(bigint, boolean)     TO service_role;
GRANT EXECUTE ON FUNCTION public.resolve_unknown_tenant(text)              TO service_role;
GRANT EXECUTE ON FUNCTION public.release_stale_locks(integer)              TO service_role;
GRANT EXECUTE ON FUNCTION public.purge_processed_xml_content(integer)      TO service_role;

-- ─── 2. RPC analitiche SECURITY INVOKER senza guard cross-tenant ──────────────
REVOKE ALL ON FUNCTION public.costi_automatici_mensili(uuid, uuid, integer, text[], text[]) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.chat_top_categoria_fornitore(uuid, uuid, integer, integer)    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.costi_automatici_mensili(uuid, uuid, integer, text[], text[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.chat_top_categoria_fornitore(uuid, uuid, integer, integer)    TO service_role;

-- ─── 3. search_path mancante su SECURITY DEFINER ──────────────────────────────
ALTER FUNCTION public.fn_log_category_change()  SET search_path = public;
ALTER FUNCTION public.get_distinct_files(text)  SET search_path = '';

-- ─── 4. get_distinct_files con guard auth: REVOKE anon (difesa in profondità) ──
REVOKE ALL ON FUNCTION public.get_distinct_files(text)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_distinct_files(uuid)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_distinct_files(uuid, uuid)  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_distinct_files(uuid)       TO service_role;
GRANT EXECUTE ON FUNCTION public.get_distinct_files(uuid, uuid) TO service_role;
