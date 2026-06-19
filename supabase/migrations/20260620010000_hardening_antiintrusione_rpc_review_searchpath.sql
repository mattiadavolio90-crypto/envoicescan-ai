-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: HARDENING ANTI-INTRUSIONE — RPC residue anon, review_ignored, search_path
-- ═══════════════════════════════════════════════════════════════════════════════
-- Audit anti-hacker 20/06 (pre go-live 1/7). Completa la passata DATABASE: la
-- migration 20260619230000 aveva chiuso il vettore HIGH (RPC coda fatture che
-- leakava xml_content cross-tenant ad anon). Lo scan live di OGGI ha trovato i
-- residui ancora raggiungibili con la ANON KEY pubblica via PostgREST.
--
-- MODELLO DI MINACCIA: attaccante che conosce il project URL Supabase (pubblico) e
-- usa la anon key (pubblica per definizione) per chiamare /rest/v1/rpc/<f> o
-- /rest/v1/<tabella>, BYPASSANDO il worker, l'auth applicativa, il rate limit e
-- ogni controllo. Difesa-in-profondità: togliere queste superfici dal ruolo anon.
--
-- NOTA: l'auth è custom (auth.uid() = NULL), tutto l'accesso applicativo passa da
-- service_role che IGNORA i grant per-ruolo e le policy RLS. NESSUNA funzionalità
-- si rompe. Le RPC sotto hanno GIÀ una guardia ownership interna (controllano
-- auth.uid()/auth.role()=service_role) → erano già inerti per anon, ma la revoca
-- le rimuove dalla superficie e protegge da regressioni future (es. una nuova RPC
-- aggiunta domani senza guardia eredita comunque la superficie ristretta).
--
-- Idempotente: REVOKE/GRANT/ALTER/DROP POLICY ripetibili.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── 1. RPC applicative residue eseguibili da anon/authenticated ───────────────
-- Hanno guardia ownership interna ma restano nella superficie pubblica: revoca.
REVOKE ALL ON FUNCTION public.create_ristorante_for_user(uuid, text, character varying, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.conta_ristoranti_utente(uuid)                                    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.sposta_fattura_a_sede(uuid, text, uuid)                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.assegna_fattura_a_sede(bigint, uuid)                             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_ai_costs_summary(integer)                                    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.chat_usage_check_and_log(uuid, uuid, integer, boolean)           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.swap_ricette_order(uuid, uuid)                                   FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.create_ristorante_for_user(uuid, text, character varying, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.conta_ristoranti_utente(uuid)                                    TO service_role;
GRANT EXECUTE ON FUNCTION public.sposta_fattura_a_sede(uuid, text, uuid)                          TO service_role;
GRANT EXECUTE ON FUNCTION public.assegna_fattura_a_sede(bigint, uuid)                             TO service_role;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_summary(integer)                                    TO service_role;
GRANT EXECUTE ON FUNCTION public.chat_usage_check_and_log(uuid, uuid, integer, boolean)           TO service_role;
GRANT EXECUTE ON FUNCTION public.swap_ricette_order(uuid, uuid)                                   TO service_role;

-- ─── 2. review_ignored: policy "USING(true)" aperta a authenticated + grant anon ─
-- Tabella di servizio interna (0 righe, nessun dato cliente) ma la policy ALL
-- USING(true)/CHECK(true) per authenticated è un buco di principio (chiunque si
-- registri via Supabase Auth potrebbe leggerla/scriverla). La ristringiamo a
-- service_role come tutte le altre tabelle di servizio e togliamo i grant client.
DROP POLICY IF EXISTS review_ignored_all_authenticated ON public.review_ignored;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'review_ignored'
          AND policyname = 'review_ignored_all_service_role'
    ) THEN
        CREATE POLICY review_ignored_all_service_role ON public.review_ignored
            FOR ALL TO service_role USING (true) WITH CHECK (true);
    END IF;
END$$;

REVOKE ALL ON TABLE public.review_ignored FROM anon, authenticated;

-- ─── 3. function_search_path_mutable: SET search_path sui trigger residui ───────
-- Trigger SECURITY DEFINER/INVOKER senza search_path fisso → rischio teorico di
-- search_path hijack (uno schema malevolo in search prima di public). Lo fissiamo.
ALTER FUNCTION public.normalize_custom_tag_key(text)             SET search_path = public;
ALTER FUNCTION public.custom_tag_prodotti_prepare_row()          SET search_path = public;
ALTER FUNCTION public.custom_tag_suggestions_set_updated_at()    SET search_path = public;
ALTER FUNCTION public.custom_tag_suggestion_items_prepare_row()  SET search_path = public;
ALTER FUNCTION public.set_ricavi_giornalieri_updated_at()        SET search_path = public;
ALTER FUNCTION public.set_inventario_voci_updated_at()           SET search_path = public;
ALTER FUNCTION public.update_diario_eventi_timestamp()           SET search_path = public;
ALTER FUNCTION public.set_marketplace_leads_updated_at()         SET search_path = public;
ALTER FUNCTION public.normalizza_indirizzo_match(text)           SET search_path = public;
ALTER FUNCTION public.trg_ristoranti_indirizzo_match()           SET search_path = public;
ALTER FUNCTION public.sync_margini_mensili_from_ricavi()         SET search_path = public;
ALTER FUNCTION public.costi_automatici_mensili(uuid, uuid, integer, text[], text[]) SET search_path = public;
ALTER FUNCTION public.chat_top_categoria_fornitore(uuid, uuid, integer, integer)    SET search_path = public;
