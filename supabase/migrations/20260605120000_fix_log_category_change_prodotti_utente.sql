-- Fix: fn_log_category_change falliva su UPDATE di categoria in prodotti_utente
-- perché leggeva NEW.ristorante_id / NEW.file_origine / NEW.numero_riga, colonne che
-- prodotti_utente NON ha. PL/pgSQL risolve i riferimenti NEW.<campo> a compile-time
-- (anche dentro un CASE), quindi sollevava: record "new" has no field "...".
--
-- Conseguenza del bug: ogni correzione manuale di una categoria GIÀ esistente sulla
-- memoria locale (prodotti_utente) andava in errore, bloccando il salvataggio della
-- personalizzazione cliente. Non era mai emerso perché finora nessun UPDATE di categoria
-- aveva colpito prodotti_utente (le scritture erano INSERT/upsert nuovi).
--
-- Fix: ricavare i campi specifici-di-fatture via to_jsonb(NEW/OLD)->>'campo', che
-- ritorna NULL se il campo non esiste invece di sollevare errore.

CREATE OR REPLACE FUNCTION public.fn_log_category_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
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
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RETURN NEW;
    END IF;

    IF NEW.categoria IS NOT DISTINCT FROM OLD.categoria THEN
        RETURN NEW;
    END IF;

    v_actor_sub_text := NULLIF(current_setting('request.jwt.claim.sub', true), '');
    v_actor_email := NULLIF(current_setting('request.jwt.claim.email', true), '');
    v_source := COALESCE(NULLIF(current_setting('app.category_change_source', true), ''), 'db_trigger');
    v_batch_text := NULLIF(current_setting('app.category_change_batch_id', true), '');

    IF v_batch_text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
        v_batch_id := v_batch_text::UUID;
    ELSE
        v_batch_id := NULL;
    END IF;

    -- Accesso SICURO ai campi che esistono solo su alcune tabelle (fatture ha
    -- ristorante_id/file_origine/numero_riga, prodotti_utente no).
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
        CASE WHEN v_actor_sub_text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN v_actor_sub_text::UUID ELSE NULL END,
        v_actor_email,
        v_source,
        v_batch_id,
        jsonb_build_object('trigger', TG_NAME)
    );

    RETURN NEW;
END;
$function$;
