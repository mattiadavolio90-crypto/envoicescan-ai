-- Registro delle modifiche di categoria: far dichiarare CHI scrive.
--
-- Il problema, misurato sul DB live l'08/09/2026: category_change_log ha 4.132
-- righe (29/04 -> 03/09) e ZERO valori su actor_email, actor_user_id, batch_id;
-- `source` ha un solo valore distinto ('db_trigger'). Il trigger
-- fn_log_category_change era gia' scritto per ricevere quei dati, ma li cercava
-- solo dove in questo progetto non possono esserci:
--   - request.jwt.claim.sub/email  -> l'auth e' custom, auth.uid() e' sempre NULL
--     e ogni scrittura passa dalla service_role key: nessun JWT utente arriva mai;
--   - app.category_change_source / _batch_id -> GUC che nessuno impostava
--     (0 occorrenze in services/ worker/ scripts/ supabase/functions/ apps/web/src/).
--
-- Perche' l'attribuzione nasce QUI e non nel client Python: il trigger legge GUC
-- di SESSIONE, e PostgREST prende una connessione dal pool per ogni richiesta.
-- Dal client non si possono mettere `SET LOCAL` e l'UPDATE nella stessa
-- transazione: il GUC finirebbe su un'altra connessione — o peggio su quella di
-- un'altra richiesta, attribuendo la scrittura all'utente sbagliato. Un registro
-- che attribuisce male e' peggio di uno vuoto, perche' sembra affidabile.
-- Dentro una funzione SQL, invece, set_config(...,true) e UPDATE sono per
-- costruzione la stessa transazione.
--
-- Modello: soft_delete_fatture_massivo (20260603190000), stessa forma di
-- SECURITY DEFINER + REVOKE nominale + GRANT a service_role.

-- 1) Il trigger impara a leggere anche l'attore dai GUC.
--    COALESCE sul JWT: dove un JWT ci fosse davvero, il comportamento storico
--    resta identico. Chi non dichiara continua a produrre una riga anonima
--    ('db_trigger', attore NULL): il registro resta onesto invece di inventare.
CREATE OR REPLACE FUNCTION public.fn_log_category_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $function$
DECLARE
    v_actor_sub_text TEXT;
    v_actor_email TEXT;
    v_source TEXT;
    v_batch_text TEXT;
    v_batch_id UUID;
    v_ristorante_id UUID;
    v_file_origine TEXT;
    v_numero_riga INTEGER;
    c_uuid CONSTANT TEXT := '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$';
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RETURN NEW;
    END IF;

    IF NEW.categoria IS NOT DISTINCT FROM OLD.categoria THEN
        RETURN NEW;
    END IF;

    -- L'attore dichiarato dallo scrittore ha la precedenza; il JWT resta come
    -- ripiego per non cambiare il comportamento dove un JWT esiste davvero.
    v_actor_sub_text := COALESCE(
        NULLIF(current_setting('app.category_change_actor_user_id', true), ''),
        NULLIF(current_setting('request.jwt.claim.sub', true), '')
    );
    v_actor_email := COALESCE(
        NULLIF(current_setting('app.category_change_actor_email', true), ''),
        NULLIF(current_setting('request.jwt.claim.email', true), '')
    );
    v_source := COALESCE(NULLIF(current_setting('app.category_change_source', true), ''), 'db_trigger');
    v_batch_text := NULLIF(current_setting('app.category_change_batch_id', true), '');

    IF v_batch_text ~* c_uuid THEN
        v_batch_id := v_batch_text::UUID;
    ELSE
        v_batch_id := NULL;
    END IF;

    -- Accesso SICURO ai campi che esistono solo su alcune tabelle (es. fatture ha
    -- ristorante_id/file_origine/numero_riga, prodotti_utente no). to_jsonb(...)->>'campo'
    -- ritorna NULL se il campo non esiste, evitando l'errore "record new has no field"
    -- che PL/pgSQL solleverebbe risolvendo NEW.<campo> a compile-time anche dentro un CASE.
    v_ristorante_id := NULLIF(COALESCE(to_jsonb(NEW)->>'ristorante_id', to_jsonb(OLD)->>'ristorante_id'), '')::UUID;

    IF TG_TABLE_NAME = 'fatture' THEN
        v_file_origine := COALESCE(to_jsonb(NEW)->>'file_origine', to_jsonb(OLD)->>'file_origine');
        v_numero_riga  := NULLIF(COALESCE(to_jsonb(NEW)->>'numero_riga', to_jsonb(OLD)->>'numero_riga'), '')::INTEGER;
    ELSE
        v_file_origine := NULL;
        v_numero_riga := NULL;
    END IF;

    INSERT INTO public.category_change_log (
        table_name, target_id, user_id, ristorante_id, descrizione,
        file_origine, numero_riga, old_categoria, new_categoria,
        actor_user_id, actor_email, source, batch_id, details
    )
    VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id::TEXT, OLD.id::TEXT),
        COALESCE(NEW.user_id, OLD.user_id),
        v_ristorante_id,
        COALESCE(NEW.descrizione, OLD.descrizione),
        v_file_origine,
        v_numero_riga,
        OLD.categoria,
        NEW.categoria,
        CASE WHEN v_actor_sub_text ~* c_uuid THEN v_actor_sub_text::UUID ELSE NULL END,
        v_actor_email,
        v_source,
        v_batch_id,
        jsonb_build_object('trigger', TG_NAME)
    );

    RETURN NEW;
END;
$function$;

-- 1-bis) Spegne la dichiarazione appena usata.
-- Non basta affidarsi a `is_local`: una transazione puo' contenere piu'
-- scritture (il worker ne fa a raffica sulla stessa connessione), e la
-- dichiarazione della prima resterebbe accesa per quelle dopo.
CREATE OR REPLACE FUNCTION public._azzera_attribuzione_categoria()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.category_change_source', '', true);
    PERFORM set_config('app.category_change_batch_id', '', true);
    PERFORM set_config('app.category_change_actor_email', '', true);
    PERFORM set_config('app.category_change_actor_user_id', '', true);
END;
$$;

-- 2) L'unico modo per scrivere `categoria` dichiarando chi sei.
--    p_extra porta i campi che accompagnano sempre la categoria
--    (needs_review, categoria_fonte, categoria_fiducia): restano un solo UPDATE,
--    quindi una sola riga di log per riga cambiata invece di due.
--    Nota: `categoria_fonte` dice QUALE REGOLA ha deciso (L2_locale, AI_alta...),
--    `p_source` dice CHI HA ESEGUITO la scrittura (worker_coda, correzione_cliente).
--    Sono due domande diverse e non vanno fuse.
CREATE OR REPLACE FUNCTION public.aggiorna_categoria_fatture_attribuita(
    p_ids bigint[],
    p_categoria text,
    p_source text,
    p_extra jsonb DEFAULT '{}'::jsonb,
    p_actor_email text DEFAULT NULL,
    p_actor_user_id uuid DEFAULT NULL,
    p_batch_id uuid DEFAULT NULL
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
      AND deleted_at IS NULL;

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

-- 3) La gemella per prodotti_utente (la memoria delle correzioni). Il trigger e'
--    attivo su entrambe le tabelle: dimenticare questa lascerebbe meta' registro cieco.
CREATE OR REPLACE FUNCTION public.aggiorna_categoria_prodotto_attribuita(
    p_user_id uuid,
    p_descrizione text,
    p_categoria text,
    p_source text,
    p_actor_email text DEFAULT NULL,
    p_actor_user_id uuid DEFAULT NULL,
    p_batch_id uuid DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count integer;
BEGIN
    PERFORM set_config('app.category_change_source', COALESCE(p_source, ''), true);
    PERFORM set_config('app.category_change_batch_id', COALESCE(p_batch_id::text, ''), true);
    PERFORM set_config('app.category_change_actor_email', COALESCE(p_actor_email, ''), true);
    PERFORM set_config('app.category_change_actor_user_id', COALESCE(p_actor_user_id::text, ''), true);

    UPDATE public.prodotti_utente
       SET categoria = p_categoria
     WHERE user_id = p_user_id
       AND descrizione = p_descrizione;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    PERFORM public._azzera_attribuzione_categoria();
    RETURN v_count;
END;
$$;

-- SECURITY DEFINER bypassa RLS: eseguibili solo da service_role (unico ruolo
-- usato da ONEFLUX, server-side).
-- Il solo FROM PUBLIC NON BASTA: le default privileges del progetto danno grant
-- NOMINALI ad anon/authenticated a ogni CREATE. Vanno nominati (buco del 07/09).
REVOKE ALL ON FUNCTION public.aggiorna_categoria_fatture_attribuita(bigint[], text, text, jsonb, text, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.aggiorna_categoria_fatture_attribuita(bigint[], text, text, jsonb, text, uuid, uuid) TO service_role;

REVOKE ALL ON FUNCTION public.aggiorna_categoria_prodotto_attribuita(uuid, text, text, text, text, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.aggiorna_categoria_prodotto_attribuita(uuid, text, text, text, text, uuid, uuid) TO service_role;

REVOKE ALL ON FUNCTION public._azzera_attribuzione_categoria() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public._azzera_attribuzione_categoria() TO service_role;
