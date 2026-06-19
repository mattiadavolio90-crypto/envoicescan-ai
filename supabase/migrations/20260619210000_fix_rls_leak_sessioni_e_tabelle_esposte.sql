-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: chiusura leak sessioni + hardening tabelle esposte ad anon/authenticated
-- ═══════════════════════════════════════════════════════════════════════════════
-- BLOCKER go-live (audit 19/06, advisor Supabase su DB live).
--
-- PROBLEMA:
--   5 tabelle public concedono privilegi (SELECT/INSERT/UPDATE/DELETE) ai ruoli
--   `anon` e `authenticated`, raggiungibili via PostgREST con la ANON KEY (che è
--   pubblica per costruzione: vive nel frontend). La più grave è `sessioni`, che
--   ha RLS DISABILITATA e contiene la colonna `token` (token di sessione in chiaro):
--   un `GET /rest/v1/sessioni?select=token` con la anon key permetterebbe di
--   rubare le sessioni attive di TUTTI i clienti → account takeover senza password.
--
-- CONTESTO AUTH (perché il fix è sicuro):
--   ONEFLUX usa auth CUSTOM, non Supabase Auth → `auth.uid()` è SEMPRE NULL.
--   Tutto l'accesso dati applicativo passa dal client `service_role`
--   (services.get_supabase_client / session_service._client), che BYPASSA sia RLS
--   sia i grant per-ruolo. Quindi revocare ogni privilegio ad anon/authenticated
--   NON rompe il backend: le tabelle `users`/`fatture`/`ristoranti` funzionano già
--   così (RLS on, accesso solo via service_role). I ruoli anon/authenticated non
--   devono toccare NULLA: la loro presenza nei grant è solo il default ereditato
--   alla creazione tabella, mai usato dall'app.
--
-- FIX (difesa in profondità):
--   1. REVOKE di tutti i privilegi DML da anon + authenticated sulle 5 tabelle
--      (la difesa vera: niente grant = PostgREST risponde 401/permission denied).
--   2. ENABLE + FORCE RLS dove mancava (sessioni, ai_review_log) — cintura+bretelle.
--   3. Rimozione delle policy permissive `USING (true)` su review_confirmed
--      (l'accesso resta solo via service_role).
--   4. categorie: la SELECT pubblica è innocua (lista categorie, non dati cliente)
--      e serve eventualmente a letture leggere; si revoca però la SCRITTURA da
--      anon/authenticated (INSERT/UPDATE/DELETE) che non deve esistere.
--
-- Idempotente: REVOKE IF EXISTS implicito, ENABLE/FORCE ripetibili, DROP POLICY IF EXISTS.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. sessioni — il leak critico: RLS off + token esposto
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON TABLE public.sessioni FROM anon, authenticated;
ALTER TABLE public.sessioni ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessioni FORCE ROW LEVEL SECURITY;
-- Nessuna policy: con auth.uid() sempre NULL nessun ruolo applicativo deve leggere
-- la tabella. L'accesso è esclusivamente via service_role (che ignora RLS).

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. ai_review_log — RLS off + DML aperto ad anon
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON TABLE public.ai_review_log FROM anon, authenticated;
ALTER TABLE public.ai_review_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_review_log FORCE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. review_confirmed — RLS on ma policy ALL USING(true) = accesso illimitato
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON TABLE public.review_confirmed FROM anon, authenticated;
DROP POLICY IF EXISTS review_confirmed_all_authenticated ON public.review_confirmed;
ALTER TABLE public.review_confirmed FORCE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. chat_usage_log — RLS on senza policy (già bloccata): pulizia grant residui
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON TABLE public.chat_usage_log FROM anon, authenticated;
ALTER TABLE public.chat_usage_log FORCE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. categorie — SELECT pubblica innocua, ma la SCRITTURA non deve essere di anon
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.categorie FROM anon, authenticated;
-- SELECT resta concessa (lista categorie pubblica, nessun dato cliente).
-- La policy categorie_write_admin (ALL USING false) resta come blocco esplicito.
