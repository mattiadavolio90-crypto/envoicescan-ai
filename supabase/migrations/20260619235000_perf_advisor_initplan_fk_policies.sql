-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: advisor PERFORMANCE — auth_rls_initplan + FK senza indice + policy
--            permissive duplicate su categorie
-- ═══════════════════════════════════════════════════════════════════════════════
-- Completamento audit 19/06 (passata performance, voci non-blocker pre go-live 1/7).
-- L'advisor security era gia' 0 ERROR; questi sono i WARN/INFO performance residui.
--
-- 1. auth_rls_initplan (49 policy su 12 tabelle): le RLS chiamavano auth.uid()/
--    auth.role() per OGNI riga. Avvolgendole in (select ...) Postgres le valuta
--    UNA volta (initplan) invece che per-riga. SEMANTICA IDENTICA: (select auth.uid())
--    e auth.uid() ritornano lo stesso valore; cambia solo il piano di esecuzione.
--    Verificato in transazione ROLLBACK sul DB live: ALTER POLICY accettato, qual
--    riscritto in (user_id = (SELECT auth.uid() AS uid)).
--    NB: con auth custom (auth.uid()=NULL, tutto via service_role che BYPASSA RLS)
--    queste policy non gateano il traffico reale, ma l'ottimizzazione e' corretta
--    e azzera il rumore dell'advisor. Uso ALTER POLICY (no DROP) → nessuna finestra
--    in cui la tabella resta senza policy.
--
-- 2. unindexed_foreign_keys (3): ricavi_email_queue(user_id, ristorante_id) e
--    ricavi_email_sender_map(ristorante_id) — FK senza indice di copertura.
--    Aggiunti indici (IF NOT EXISTS, idempotente). Tabelle code, basso volume, ma
--    l'indice e' un win gratuito e mette al sicuro i join/ON DELETE.
--
-- 3. multiple_permissive_policies su categorie (6, una per ruolo): la policy
--    categorie_write_admin era FOR ALL (qual=false) e quindi si SOVRAPPONEVA a
--    categorie_select_all anche in SELECT, costringendo Postgres a valutare due
--    policy permissive per ogni lettura. La sostituiamo con policy scoped ai soli
--    comandi di scrittura (INSERT/UPDATE/DELETE), cosi' la SELECT pubblica resta
--    governata da un'unica policy. La scrittura era gia' bloccata anche a livello
--    di GRANT (REVOKE round 1) e resta deny (qual=false) → nessun cambio di accesso.
--
-- SICURO: nessuna modifica al comportamento applicativo (service_role bypassa RLS
--   e grant). Idempotente per gli indici; gli ALTER POLICY sono ripetibili.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── 2. Indici di copertura per le FK ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ricavi_email_queue_user_id
    ON public.ricavi_email_queue (user_id);
CREATE INDEX IF NOT EXISTS idx_ricavi_email_queue_ristorante_id
    ON public.ricavi_email_queue (ristorante_id);
CREATE INDEX IF NOT EXISTS idx_ricavi_email_sender_map_ristorante_id
    ON public.ricavi_email_sender_map (ristorante_id);

-- ─── 3. categorie: rimuovi la sovrapposizione permissiva in SELECT ────────────
-- Sostituisce la policy FOR ALL con policy per i soli comandi di scrittura.
DROP POLICY IF EXISTS categorie_write_admin ON public.categorie;
CREATE POLICY categorie_write_admin_insert ON public.categorie
    FOR INSERT TO public WITH CHECK (false);
CREATE POLICY categorie_write_admin_update ON public.categorie
    FOR UPDATE TO public USING (false);
CREATE POLICY categorie_write_admin_delete ON public.categorie
    FOR DELETE TO public USING (false);

-- ─── 1. auth_rls_initplan: avvolgi auth.uid()/auth.role() in (select ...) ──────
ALTER POLICY "ai_usage_events_delete_own" ON public.ai_usage_events
  USING ((user_id = (select auth.uid())));
ALTER POLICY "ai_usage_events_insert_own" ON public.ai_usage_events
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "ai_usage_events_select_own" ON public.ai_usage_events
  USING ((user_id = (select auth.uid())));
ALTER POLICY "ai_usage_events_update_own" ON public.ai_usage_events
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "classificazioni_manuali_delete_own" ON public.classificazioni_manuali
  USING ((user_id = (select auth.uid())));
ALTER POLICY "classificazioni_manuali_insert_own" ON public.classificazioni_manuali
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "classificazioni_manuali_select_own" ON public.classificazioni_manuali
  USING (((user_id = (select auth.uid())) OR (user_id IS NULL)));
ALTER POLICY "classificazioni_manuali_update_own" ON public.classificazioni_manuali
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestion_items_delete_own" ON public.custom_tag_suggestion_items
  USING ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestion_items_insert_own" ON public.custom_tag_suggestion_items
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestion_items_select_own" ON public.custom_tag_suggestion_items
  USING ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestion_items_update_own" ON public.custom_tag_suggestion_items
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestions_delete_own" ON public.custom_tag_suggestions
  USING ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestions_insert_own" ON public.custom_tag_suggestions
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestions_select_own" ON public.custom_tag_suggestions
  USING ((user_id = (select auth.uid())));
ALTER POLICY "custom_tag_suggestions_update_own" ON public.custom_tag_suggestions
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "ingredienti_utente_delete_own" ON public.ingredienti_utente
  USING ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_utente_insert_own" ON public.ingredienti_utente
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_utente_select_own" ON public.ingredienti_utente
  USING ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_utente_update_own" ON public.ingredienti_utente
  USING ((userid = (select auth.uid())))
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_workspace_delete_own" ON public.ingredienti_workspace
  USING ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_workspace_insert_own" ON public.ingredienti_workspace
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_workspace_select_own" ON public.ingredienti_workspace
  USING ((userid = (select auth.uid())));
ALTER POLICY "ingredienti_workspace_update_own" ON public.ingredienti_workspace
  USING ((userid = (select auth.uid())))
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "margini_mensili_delete_own" ON public.margini_mensili
  USING ((user_id = (select auth.uid())));
ALTER POLICY "margini_mensili_insert_own" ON public.margini_mensili
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "margini_mensili_select_own" ON public.margini_mensili
  USING ((user_id = (select auth.uid())));
ALTER POLICY "margini_mensili_update_own" ON public.margini_mensili
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "note_diario_delete_own" ON public.note_diario
  USING ((userid = (select auth.uid())));
ALTER POLICY "note_diario_insert_own" ON public.note_diario
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "note_diario_select_own" ON public.note_diario
  USING ((userid = (select auth.uid())));
ALTER POLICY "note_diario_update_own" ON public.note_diario
  USING ((userid = (select auth.uid())))
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "notification_inbox_delete_own" ON public.notification_inbox
  USING ((user_id = (select auth.uid())));
ALTER POLICY "notification_inbox_insert_own" ON public.notification_inbox
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "notification_inbox_select_own" ON public.notification_inbox
  USING ((user_id = (select auth.uid())));
ALTER POLICY "notification_inbox_update_own" ON public.notification_inbox
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "piva_ristoranti_delete_own" ON public.piva_ristoranti
  USING ((user_id = (select auth.uid())));
ALTER POLICY "piva_ristoranti_insert_own" ON public.piva_ristoranti
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "piva_ristoranti_select_own" ON public.piva_ristoranti
  USING ((user_id = (select auth.uid())));
ALTER POLICY "piva_ristoranti_update_own" ON public.piva_ristoranti
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "prodotti_master_select_authenticated" ON public.prodotti_master
  USING (((select auth.role()) = 'authenticated'::text));
ALTER POLICY "ricette_delete_own" ON public.ricette
  USING ((userid = (select auth.uid())));
ALTER POLICY "ricette_insert_own" ON public.ricette
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "ricette_select_own" ON public.ricette
  USING ((userid = (select auth.uid())));
ALTER POLICY "ricette_update_own" ON public.ricette
  USING ((userid = (select auth.uid())))
  WITH CHECK ((userid = (select auth.uid())));
ALTER POLICY "upload_events_delete_own" ON public.upload_events
  USING ((user_id = (select auth.uid())));
ALTER POLICY "upload_events_insert_own" ON public.upload_events
  WITH CHECK ((user_id = (select auth.uid())));
ALTER POLICY "upload_events_select_own" ON public.upload_events
  USING ((user_id = (select auth.uid())));
ALTER POLICY "upload_events_update_own" ON public.upload_events
  USING ((user_id = (select auth.uid())))
  WITH CHECK ((user_id = (select auth.uid())));
