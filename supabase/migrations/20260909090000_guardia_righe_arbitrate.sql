-- Guardia: gli script non devono poter riscrivere una riga gia' arbitrata.
--
-- Il precedente e' del 26/08: `scripts/ricategorizza_sede.py` avrebbe
-- sovrascritto 19 correzioni manuali, e fu trovato per caso leggendo il codice.
-- Misurato il 08/09/2026 il caso e' ancora vivo: la riga 128426 di VILLA GUARDIA
-- ("INVOLTINO VIETNAM (POLLO)", decisa a mano come CARNE il 25/06) oggi passa
-- nella pipeline dello script e ne esce "PASTA E CEREALI".
--
-- La regola di dominio che questa guardia implementa: cio' che un cliente
-- decide vale per LUI, non per gli altri clienti. Chi scrive per conto proprio
-- (la correzione dal frontend) deve poter riscrivere le proprie righe; chi
-- scrive per conto d'altri (uno script massivo) non deve.
--
-- Per questo il parametro e' OPT-IN e non un default. La correzione del cliente
-- passa dallo stesso chokepoint (`services/routers/fatture.py:944`,
-- source='correzione_cliente'): con la guardia sempre attiva il cliente non
-- potrebbe piu' correggere due volte la stessa riga, e la guardia diventerebbe
-- il bug che pretende di evitare.
--
-- `IS DISTINCT FROM` e non `<>`: le 318 righe con `reviewed_at` valorizzato
-- hanno tutte `categoria_fonte` NULL (misurato sul live il 08/09). Con `<>` il
-- predicato varrebbe NULL e la riga passerebbe: la guardia sarebbe inerte
-- proprio sul 96% del perimetro che deve proteggere.
--
-- Il parametro va IN CODA: i 13 chiamanti esistenti passano gli argomenti per
-- nome e non vedono differenza.
--
-- Il DROP della firma a 7 argomenti NON e' pulizia: e' obbligatorio. Un
-- `CREATE OR REPLACE` con un parametro in piu' non sostituisce la vecchia
-- funzione, ne aggiunge una in OVERLOAD — e resterebbero entrambe: la vecchia,
-- senza guardia, ancora chiamabile, e i chiamanti che passano 7 argomenti
-- diventerebbero ambigui (PostgREST risponde PGRST203, e chi ingoia l'errore
-- dichiara all'utente numeri che non sono avvenuti). E' esattamente il difetto
-- misurato il 07/09 su `get_distinct_files`, dove togliere una sola variante non
-- bastava perche' il DEFAULT NULL rende ambigue anche le rimanenti.
DROP FUNCTION IF EXISTS public.aggiorna_categoria_fatture_attribuita(bigint[], text, text, jsonb, text, uuid, uuid);

CREATE OR REPLACE FUNCTION public.aggiorna_categoria_fatture_attribuita(
    p_ids bigint[],
    p_categoria text,
    p_source text,
    p_extra jsonb DEFAULT '{}'::jsonb,
    p_actor_email text DEFAULT NULL,
    p_actor_user_id uuid DEFAULT NULL,
    p_batch_id uuid DEFAULT NULL,
    p_salta_arbitrate boolean DEFAULT false
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count integer;
BEGIN
    IF p_ids IS NULL OR array_length(p_ids, 1) IS NULL THEN
        RETURN 0;
    END IF;

    -- is_local = true: i GUC muoiono con la transazione, quindi non colano
    -- sulla richiesta successiva che riusa la stessa connessione del pool.
    PERFORM set_config('app.category_change_source', COALESCE(p_source, ''), true);
    PERFORM set_config('app.category_change_batch_id', COALESCE(p_batch_id::text, ''), true);
    PERFORM set_config('app.category_change_actor_email', COALESCE(p_actor_email, ''), true);
    PERFORM set_config('app.category_change_actor_user_id', COALESCE(p_actor_user_id::text, ''), true);

    UPDATE public.fatture SET
        categoria = p_categoria,
        needs_review = COALESCE((p_extra->>'needs_review')::boolean, needs_review),
        categoria_fonte = COALESCE(p_extra->>'categoria_fonte', categoria_fonte),
        categoria_fiducia = COALESCE(p_extra->>'categoria_fiducia', categoria_fiducia),
        reviewed_at = COALESCE((p_extra->>'reviewed_at')::timestamp, reviewed_at),
        reviewed_by = COALESCE(p_extra->>'reviewed_by', reviewed_by)
    WHERE id = ANY(p_ids)
      AND deleted_at IS NULL
      AND (
          NOT p_salta_arbitrate
          OR (categoria_fonte IS DISTINCT FROM 'correzione_cliente' AND reviewed_at IS NULL)
      );

    GET DIAGNOSTICS v_count = ROW_COUNT;

    -- I GUC vanno spenti QUI, non lasciati scadere con la transazione: PostgREST
    -- e il worker fanno piu' scritture sulla stessa connessione, e `is_local`
    -- copre la transazione, non la chiamata. Senza questo azzeramento la
    -- dichiarazione di questa chiamata verrebbe attribuita alla scrittura
    -- successiva, che magari e' di un altro utente. Misurato: senza, il test
    -- `test_la_dichiarazione_non_cola_sulla_scrittura_successiva` e' rosso.
    PERFORM public._azzera_attribuzione_categoria();

    RETURN v_count;
END;
$$;

-- Il REVOKE va ripetuto: `CREATE OR REPLACE` con una firma nuova (un parametro
-- in piu') crea una funzione nuova agli occhi del catalogo, e i grant di default
-- del progetto Supabase la riaprirebbero ad anon/authenticated. E' il buco
-- misurato il 07/09: `FROM PUBLIC` da solo non basta, i ruoli vanno nominati.
REVOKE ALL ON FUNCTION public.aggiorna_categoria_fatture_attribuita(bigint[], text, text, jsonb, text, uuid, uuid, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.aggiorna_categoria_fatture_attribuita(bigint[], text, text, jsonb, text, uuid, uuid, boolean) TO service_role;
