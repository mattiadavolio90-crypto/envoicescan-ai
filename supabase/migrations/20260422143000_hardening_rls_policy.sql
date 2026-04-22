BEGIN;

-- =========================================================
-- HARDENING RLS — tabelle con owner in colonna user_id
-- =========================================================

-- 1) ai_usage_events
ALTER TABLE public.ai_usage_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all for authenticated" ON public.ai_usage_events;
CREATE POLICY ai_usage_events_select_own ON public.ai_usage_events
  FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY ai_usage_events_insert_own ON public.ai_usage_events
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY ai_usage_events_update_own ON public.ai_usage_events
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY ai_usage_events_delete_own ON public.ai_usage_events
  FOR DELETE TO authenticated USING (user_id = auth.uid());

-- 2) classificazioni_manuali
-- NOTA: record con user_id IS NULL = memoria globale AI, visibile a tutti
ALTER TABLE public.classificazioni_manuali ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all operations for authenticated users"
  ON public.classificazioni_manuali;
CREATE POLICY classificazioni_manuali_select_own
  ON public.classificazioni_manuali
  FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR user_id IS NULL);
CREATE POLICY classificazioni_manuali_insert_own
  ON public.classificazioni_manuali
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());
CREATE POLICY classificazioni_manuali_update_own
  ON public.classificazioni_manuali
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
CREATE POLICY classificazioni_manuali_delete_own
  ON public.classificazioni_manuali
  FOR DELETE TO authenticated
  USING (user_id = auth.uid());

-- 3) margini_mensili
ALTER TABLE public.margini_mensili ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS margini_mensili_select_policy ON public.margini_mensili;
DROP POLICY IF EXISTS margini_mensili_insert_policy ON public.margini_mensili;
DROP POLICY IF EXISTS margini_mensili_update_policy ON public.margini_mensili;
DROP POLICY IF EXISTS margini_mensili_delete_policy ON public.margini_mensili;
CREATE POLICY margini_mensili_select_own ON public.margini_mensili
  FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY margini_mensili_insert_own ON public.margini_mensili
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY margini_mensili_update_own ON public.margini_mensili
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY margini_mensili_delete_own ON public.margini_mensili
  FOR DELETE TO authenticated USING (user_id = auth.uid());

-- 4) piva_ristoranti
-- NOTA: admin (service_role) vede tutto; utenti normali solo i propri
ALTER TABLE public.piva_ristoranti ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Admin sees all piva restaurants" ON public.piva_ristoranti;
DROP POLICY IF EXISTS "User owns piva restaurants" ON public.piva_ristoranti;
CREATE POLICY piva_ristoranti_select_own ON public.piva_ristoranti
  FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY piva_ristoranti_insert_own ON public.piva_ristoranti
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY piva_ristoranti_update_own ON public.piva_ristoranti
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY piva_ristoranti_delete_own ON public.piva_ristoranti
  FOR DELETE TO authenticated USING (user_id = auth.uid());
CREATE POLICY piva_ristoranti_service_all ON public.piva_ristoranti
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 5) upload_events
ALTER TABLE public.upload_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all for authenticated" ON public.upload_events;
CREATE POLICY upload_events_select_own ON public.upload_events
  FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY upload_events_insert_own ON public.upload_events
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY upload_events_update_own ON public.upload_events
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY upload_events_delete_own ON public.upload_events
  FOR DELETE TO authenticated USING (user_id = auth.uid());

-- =========================================================
-- HARDENING RLS — tabelle con owner in colonna userid
-- =========================================================

-- 6) ingredienti_utente
ALTER TABLE public.ingredienti_utente ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ingredienti_utente_select_policy ON public.ingredienti_utente;
DROP POLICY IF EXISTS ingredienti_utente_insert_policy ON public.ingredienti_utente;
DROP POLICY IF EXISTS ingredienti_utente_update_policy ON public.ingredienti_utente;
DROP POLICY IF EXISTS ingredienti_utente_delete_policy ON public.ingredienti_utente;
CREATE POLICY ingredienti_utente_select_own ON public.ingredienti_utente
  FOR SELECT TO authenticated USING (userid = auth.uid());
CREATE POLICY ingredienti_utente_insert_own ON public.ingredienti_utente
  FOR INSERT TO authenticated WITH CHECK (userid = auth.uid());
CREATE POLICY ingredienti_utente_update_own ON public.ingredienti_utente
  FOR UPDATE TO authenticated
  USING (userid = auth.uid()) WITH CHECK (userid = auth.uid());
CREATE POLICY ingredienti_utente_delete_own ON public.ingredienti_utente
  FOR DELETE TO authenticated USING (userid = auth.uid());

-- 7) ingredienti_workspace
ALTER TABLE public.ingredienti_workspace ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ingredienti_workspace_select_policy
  ON public.ingredienti_workspace;
DROP POLICY IF EXISTS ingredienti_workspace_insert_policy
  ON public.ingredienti_workspace;
DROP POLICY IF EXISTS ingredienti_workspace_update_policy
  ON public.ingredienti_workspace;
DROP POLICY IF EXISTS ingredienti_workspace_delete_policy
  ON public.ingredienti_workspace;
CREATE POLICY ingredienti_workspace_select_own ON public.ingredienti_workspace
  FOR SELECT TO authenticated USING (userid = auth.uid());
CREATE POLICY ingredienti_workspace_insert_own ON public.ingredienti_workspace
  FOR INSERT TO authenticated WITH CHECK (userid = auth.uid());
CREATE POLICY ingredienti_workspace_update_own ON public.ingredienti_workspace
  FOR UPDATE TO authenticated
  USING (userid = auth.uid()) WITH CHECK (userid = auth.uid());
CREATE POLICY ingredienti_workspace_delete_own ON public.ingredienti_workspace
  FOR DELETE TO authenticated USING (userid = auth.uid());

-- 8) note_diario
ALTER TABLE public.note_diario ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS note_diario_select_policy ON public.note_diario;
DROP POLICY IF EXISTS note_diario_insert_policy ON public.note_diario;
DROP POLICY IF EXISTS note_diario_update_policy ON public.note_diario;
DROP POLICY IF EXISTS note_diario_delete_policy ON public.note_diario;
CREATE POLICY note_diario_select_own ON public.note_diario
  FOR SELECT TO authenticated USING (userid = auth.uid());
CREATE POLICY note_diario_insert_own ON public.note_diario
  FOR INSERT TO authenticated WITH CHECK (userid = auth.uid());
CREATE POLICY note_diario_update_own ON public.note_diario
  FOR UPDATE TO authenticated
  USING (userid = auth.uid()) WITH CHECK (userid = auth.uid());
CREATE POLICY note_diario_delete_own ON public.note_diario
  FOR DELETE TO authenticated USING (userid = auth.uid());

-- 9) ricette
ALTER TABLE public.ricette ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ricette_select_policy ON public.ricette;
DROP POLICY IF EXISTS ricette_insert_policy ON public.ricette;
DROP POLICY IF EXISTS ricette_update_policy ON public.ricette;
DROP POLICY IF EXISTS ricette_delete_policy ON public.ricette;
CREATE POLICY ricette_select_own ON public.ricette
  FOR SELECT TO authenticated USING (userid = auth.uid());
CREATE POLICY ricette_insert_own ON public.ricette
  FOR INSERT TO authenticated WITH CHECK (userid = auth.uid());
CREATE POLICY ricette_update_own ON public.ricette
  FOR UPDATE TO authenticated
  USING (userid = auth.uid()) WITH CHECK (userid = auth.uid());
CREATE POLICY ricette_delete_own ON public.ricette
  FOR DELETE TO authenticated USING (userid = auth.uid());

-- =========================================================
-- HARDENING RLS — tabelle senza owner UUID
-- (solo authenticated, nessun binding per user)
-- =========================================================

-- 10) review_confirmed
ALTER TABLE public.review_confirmed ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all for authenticated" ON public.review_confirmed;
CREATE POLICY review_confirmed_all_authenticated ON public.review_confirmed
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- 11) review_ignored
ALTER TABLE public.review_ignored ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all for authenticated" ON public.review_ignored;
CREATE POLICY review_ignored_all_authenticated ON public.review_ignored
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

COMMIT;
