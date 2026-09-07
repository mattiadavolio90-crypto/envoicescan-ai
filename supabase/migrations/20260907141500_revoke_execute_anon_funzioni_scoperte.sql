-- Chiude l'accesso con la chiave pubblica a 6 funzioni rimaste scoperte.
--
-- Misurato il 07/09/2026 sul DB live: 6 funzioni su 56 eseguibili dal ruolo
-- `anon`, cioe' dalla chiave che sta nel browser. Due sono SECURITY DEFINER,
-- quindi girano coi privilegi del proprietario e ignorano RLS:
--
--   * gruppo_tag_analisi(ristorante_ids, descrizione_keys, da, a) e' la grave:
--     dato un id di sede e una descrizione prodotto restituisce spesa,
--     quantita' e numero fornitori di quella sede, senza verificare che il
--     chiamante sia il proprietario. Raggiungibile via /rest/v1/rpc/.
--   * get_next_ordine_ricetta espone solo un contatore di ordinamento.
--
-- Le altre quattro non espongono dati di un cliente (due normalizzatori di
-- stringhe puri, una lookup costante di categorie, e articoli_da_fatture che
-- legge `fatture` ma NON e' SECURITY DEFINER, quindi da anon vedrebbe solo cio'
-- che RLS concede). Si revocano lo stesso: il criterio e' "nessuna funzione
-- raggiungibile dalla chiave pubblica", non "nessuna funzione pericolosa oggi".
--
-- PERCHE' i REVOKE del 19-20/06 non bastavano
-- ===========================================
-- Non e' il DROP+CREATE a riaprire da solo. La causa vera sono le DEFAULT
-- PRIVILEGES del progetto Supabase: `pg_default_acl` per `defaclobjtype='f'`
-- nello schema public concede EXECUTE ad anon, authenticated e service_role su
-- OGNI funzione creata da `postgres`. L'ACL reale delle sei lo mostra:
--
--   {=X/postgres, postgres=X/postgres, anon=X/postgres,
--    authenticated=X/postgres, service_role=X/postgres}
--
-- `=X/postgres` e' PUBLIC, ma `anon=X` e `authenticated=X` sono GRANT NOMINALI
-- distinti. Un `REVOKE ... FROM PUBLIC` da solo toglie il primo e lascia gli
-- altri due: la funzione resta aperta. Per questo i ruoli vanno nominati, come
-- gia' facevano 20260617230000_gruppo_tags.sql e
-- 20260620011000_hardening_revoke_rpc_residue_anon.sql.
--
-- Ne segue che ogni funzione FUTURA nascera' di nuovo aperta, finche' le
-- default privileges restano quelle. Non si toccano qui: sono impostazione del
-- progetto Supabase, valgono anche per tabelle e sequenze, e cambiarle e' una
-- decisione di piattaforma, non di questa migration. Il presidio contro la
-- ricomparsa e' tests/test_sql_funzioni_permessi.py, che diventa rosso alla
-- prima funzione nuova lasciata scoperta.
--
-- Nessun impatto sull'applicazione: ogni client di ONEFLUX usa service_role
-- (CLAUDE.md, "Chiave Supabase"), incluse le due Edge Functions
-- (SUPABASE_SERVICE_ROLE_KEY). Verificato il 07/09: zero chiamate a queste sei
-- funzioni da apps/web, e i chiamanti Python passano tutti dal worker.

REVOKE ALL ON FUNCTION public.gruppo_tag_analisi(uuid[], text[], date, date)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_next_ordine_ricetta(uuid, uuid)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.articoli_da_fatture(uuid, uuid, text[])
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public._riparto_categoria_is_fb(text)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.normalize_custom_tag_key(text)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.normalizza_indirizzo_match(text)
    FROM PUBLIC, anon, authenticated;

-- I chiamanti veri, esplicitamente: dopo la REVOKE service_role non eredita
-- piu' nulla da PUBLIC su queste funzioni. Senza questi GRANT il worker
-- riceverebbe "permission denied for function" in produzione.
GRANT EXECUTE ON FUNCTION public.gruppo_tag_analisi(uuid[], text[], date, date) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_next_ordine_ricetta(uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.articoli_da_fatture(uuid, uuid, text[]) TO service_role;
GRANT EXECUTE ON FUNCTION public._riparto_categoria_is_fb(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.normalize_custom_tag_key(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.normalizza_indirizzo_match(text) TO service_role;

-- _riparto_categoria_is_fb e normalizza_indirizzo_match sono chiamate DENTRO
-- altre funzioni (riparto_quote_mensili, trg_ristoranti_indirizzo_match): quelle
-- sono SECURITY DEFINER o trigger e girano coi privilegi del proprietario, che
-- li ha comunque. La revoca non le tocca.
