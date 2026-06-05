-- Hardening DB dall'audit del 2026-06-05.
-- Idempotente dove possibile. Applicata anche al DB live via MCP.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Difesa in profondita': revoca i grant ad anon/authenticated sulle tabelle
--    con dati sensibili. RLS e' gia' ON con policy auth.uid()-based (deny in
--    custom-auth), quindi i grant erano inerti, ma vanno tolti per igiene.
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON public.ristoranti        FROM anon, authenticated;
REVOKE ALL ON public.margini_mensili   FROM anon, authenticated;
-- category_change_log: tabella di audit cross-tenant. La policy SELECT USING(true)
-- per authenticated e' troppo larga; la audit la legge l'admin via service_role.
REVOKE ALL ON public.category_change_log FROM anon, authenticated;
DROP POLICY IF EXISTS category_change_log_select_authenticated ON public.category_change_log;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Constraint dominio #2: "📝 NOTE E DICITURE" consentita SOLO su importo 0.
--    (regola finora enforced solo applicativamente). Le righe violanti sono state
--    sanificate prima di creare il constraint.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.fatture
  DROP CONSTRAINT IF EXISTS fatture_note_diciture_solo_importo_zero_chk;
ALTER TABLE public.fatture
  ADD CONSTRAINT fatture_note_diciture_solo_importo_zero_chk
  CHECK (categoria <> '📝 NOTE E DICITURE' OR COALESCE(totale_riga, 0) = 0);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. FK coda ricavi: allinea al pattern delle altre tabelle ricavi (CASCADE).
--    ricavi_email_queue.ristorante_id era NO ACTION -> bloccava la cancellazione
--    del ristorante (e a catena dell'account). user_id non aveva FK -> orfani.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.ricavi_email_queue
  DROP CONSTRAINT IF EXISTS ricavi_email_queue_ristorante_id_fkey;
ALTER TABLE public.ricavi_email_queue
  ADD CONSTRAINT ricavi_email_queue_ristorante_id_fkey
  FOREIGN KEY (ristorante_id) REFERENCES public.ristoranti(id) ON DELETE CASCADE;

ALTER TABLE public.ricavi_email_queue
  DROP CONSTRAINT IF EXISTS ricavi_email_queue_user_id_fkey;
ALTER TABLE public.ricavi_email_queue
  ADD CONSTRAINT ricavi_email_queue_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. GRANT espliciti coerenti col pattern di fatture_queue (045): service_role
--    usa queste tabelle ricavi; anon/authenticated no.
-- ─────────────────────────────────────────────────────────────────────────────
GRANT ALL ON public.ricavi_email_queue      TO service_role;
GRANT ALL ON public.ricavi_email_sender_map TO service_role;
REVOKE ALL ON public.ricavi_email_queue      FROM anon, authenticated;
REVOKE ALL ON public.ricavi_email_sender_map FROM anon, authenticated;

-- Nota: l'indice caldo (ristorante_id, data_documento DESC) esiste gia' come
-- idx_fatture_filtro_rapido -> nessun nuovo indice (verificato sul DB live).
