BEGIN;

-- 1. Vista invoker-safe
CREATE OR REPLACE VIEW public.v_users_ristoranti
WITH (security_invoker = true) AS
SELECT
    u.id AS user_id,
    u.email,
    u.nome_ristorante AS nome_utente,
    u.piano,
    COUNT(r.id) AS num_ristoranti,
    COALESCE(
        ARRAY_AGG(r.nome_ristorante ORDER BY r.created_at) FILTER (WHERE r.id IS NOT NULL),
        ARRAY[]::text[]
    ) AS ristoranti,
    COALESCE(
        ARRAY_AGG(r.partita_iva ORDER BY r.created_at) FILTER (WHERE r.id IS NOT NULL),
        ARRAY[]::text[]
    ) AS piva_list
FROM public.users AS u
LEFT JOIN public.ristoranti AS r
    ON r.user_id = u.id
   AND r.attivo = true
GROUP BY u.id, u.email, u.nome_ristorante, u.piano;

REVOKE ALL ON public.v_users_ristoranti FROM anon;
GRANT SELECT ON public.v_users_ristoranti TO authenticated;

-- 2. Hardening RLS su public.users
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users FORCE ROW LEVEL SECURITY;

DO $$
DECLARE
    v_policy RECORD;
BEGIN
    FOR v_policy IN
        SELECT p.policyname
        FROM pg_policies AS p
        WHERE p.schemaname = 'public'
          AND p.tablename = 'users'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.users', v_policy.policyname);
    END LOOP;
END;
$$;

REVOKE ALL ON public.users FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.users TO authenticated;

CREATE POLICY users_select_self
ON public.users
FOR SELECT
TO authenticated
USING (id = auth.uid());

CREATE POLICY users_insert_self
ON public.users
FOR INSERT
TO authenticated
WITH CHECK (id = auth.uid());

CREATE POLICY users_update_self
ON public.users
FOR UPDATE
TO authenticated
USING (id = auth.uid())
WITH CHECK (id = auth.uid());

CREATE POLICY users_delete_self
ON public.users
FOR DELETE
TO authenticated
USING (id = auth.uid());

-- session_token e session_token_created_at restano accessibili solo sulla riga del proprietario.
-- Se devono essere invisibili anche al proprietario, spostarli in uno schema privato o in una tabella dedicata.

-- 3. Hardening RLS su public.prodotti_master (tabella globale condivisa, read-only lato client)
DO $$
DECLARE
    v_policy RECORD;
BEGIN
    IF to_regclass('public.prodotti_master') IS NULL THEN
        RAISE NOTICE 'Skip public.prodotti_master: tabella non trovata';
        RETURN;
    END IF;

    EXECUTE 'ALTER TABLE public.prodotti_master ENABLE ROW LEVEL SECURITY';
    EXECUTE 'ALTER TABLE public.prodotti_master FORCE ROW LEVEL SECURITY';

    FOR v_policy IN
        SELECT p.policyname
        FROM pg_policies AS p
        WHERE p.schemaname = 'public'
          AND p.tablename = 'prodotti_master'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.prodotti_master', v_policy.policyname);
    END LOOP;

    EXECUTE 'REVOKE ALL ON public.prodotti_master FROM anon';
    EXECUTE 'REVOKE INSERT, UPDATE, DELETE ON public.prodotti_master FROM authenticated';
    EXECUTE 'GRANT SELECT ON public.prodotti_master TO authenticated';

    EXECUTE $sql$
        CREATE POLICY prodotti_master_select_authenticated
        ON public.prodotti_master
        FOR SELECT
        TO authenticated
        USING (auth.role() = 'authenticated')
    $sql$;
END;
$$;

-- 4. RLS owner-based per tabelle operative esposte via PostgREST
DO $$
DECLARE
    v_table TEXT;
    v_policy RECORD;
    v_sequence TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['fatture_processate', 'articoli', 'memoria_ai_categorie']
    LOOP
        IF to_regclass('public.' || v_table) IS NULL THEN
            RAISE NOTICE 'Skip public.%: tabella non trovata', v_table;
            CONTINUE;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns AS c
            WHERE c.table_schema = 'public'
              AND c.table_name = v_table
              AND c.column_name = 'user_id'
        ) THEN
            RAISE NOTICE 'Skip public.%: colonna user_id non trovata', v_table;
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', v_table);

        FOR v_policy IN
            SELECT p.policyname
            FROM pg_policies AS p
            WHERE p.schemaname = 'public'
              AND p.tablename = v_table
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_policy.policyname, v_table);
        END LOOP;

        EXECUTE format('REVOKE ALL ON public.%I FROM anon', v_table);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', v_table);

        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (user_id = auth.uid())',
            v_table || '_select_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid())',
            v_table || '_insert_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())',
            v_table || '_update_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (user_id = auth.uid())',
            v_table || '_delete_own',
            v_table
        );

        FOR v_sequence IN
            SELECT format('%I.%I', seq_ns.nspname, seq.relname)
            FROM pg_class AS seq
            JOIN pg_namespace AS seq_ns
              ON seq_ns.oid = seq.relnamespace
            JOIN pg_depend AS dep
              ON dep.objid = seq.oid
             AND dep.deptype = 'a'
            JOIN pg_class AS tbl
              ON tbl.oid = dep.refobjid
            JOIN pg_namespace AS tbl_ns
              ON tbl_ns.oid = tbl.relnamespace
            WHERE seq.relkind = 'S'
              AND tbl_ns.nspname = 'public'
              AND tbl.relname = v_table
        LOOP
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO authenticated', v_sequence);
        END LOOP;
    END LOOP;
END;
$$;

-- 5. Backup tables: blocco completo accesso API
DO $$
DECLARE
    v_table TEXT;
    v_policy RECORD;
    v_sequence TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['users_backup_20260129', 'users_backup_20260130', 'fatture_backup_20260130']
    LOOP
        IF to_regclass('public.' || v_table) IS NULL THEN
            RAISE NOTICE 'Skip public.%: tabella backup non trovata', v_table;
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', v_table);

        FOR v_policy IN
            SELECT p.policyname
            FROM pg_policies AS p
            WHERE p.schemaname = 'public'
              AND p.tablename = v_table
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_policy.policyname, v_table);
        END LOOP;

        EXECUTE format('REVOKE ALL ON public.%I FROM anon', v_table);
        EXECUTE format('REVOKE ALL ON public.%I FROM authenticated', v_table);
        EXECUTE format('GRANT ALL ON public.%I TO service_role', v_table);

        FOR v_sequence IN
            SELECT format('%I.%I', seq_ns.nspname, seq.relname)
            FROM pg_class AS seq
            JOIN pg_namespace AS seq_ns
              ON seq_ns.oid = seq.relnamespace
            JOIN pg_depend AS dep
              ON dep.objid = seq.oid
             AND dep.deptype = 'a'
            JOIN pg_class AS tbl
              ON tbl.oid = dep.refobjid
            JOIN pg_namespace AS tbl_ns
              ON tbl_ns.oid = tbl.relnamespace
            WHERE seq.relkind = 'S'
              AND tbl_ns.nspname = 'public'
              AND tbl.relname = v_table
        LOOP
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', v_sequence);
        END LOOP;
    END LOOP;
END;
$$;

-- 6. Funzioni con search_path vuoto e riferimenti qualificati
DROP FUNCTION IF EXISTS public.get_distinct_files(UUID);
DROP FUNCTION IF EXISTS public.get_distinct_files(UUID, UUID);

CREATE OR REPLACE FUNCTION public.get_distinct_files(
    p_user_id UUID,
    p_ristorante_id UUID DEFAULT NULL
)
RETURNS TABLE(file_origine TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF p_ristorante_id IS NOT NULL
       AND COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = p_user_id
       ) THEN
        RAISE EXCEPTION 'Ristorante non autorizzato';
    END IF;

    RETURN QUERY
    SELECT DISTINCT f.file_origine
    FROM public.fatture AS f
    WHERE f.user_id = p_user_id
      AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
      AND f.file_origine IS NOT NULL
      AND f.file_origine <> ''
    ORDER BY f.file_origine;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_distinct_files(
    p_user_id UUID
)
RETURNS TABLE(file_origine TEXT)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT f.file_origine
    FROM public.get_distinct_files(p_user_id, NULL::uuid) AS f;
$$;

GRANT EXECUTE ON FUNCTION public.get_distinct_files(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_distinct_files(UUID, UUID) TO authenticated;

CREATE OR REPLACE FUNCTION public.create_ristorante_for_user(
    p_user_id UUID,
    p_nome TEXT,
    p_piva VARCHAR(11),
    p_ragione_sociale TEXT DEFAULT NULL
)
RETURNS TABLE(id UUID, nome_ristorante TEXT, partita_iva VARCHAR(11))
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    RETURN QUERY
    INSERT INTO public.ristoranti (
        user_id,
        nome_ristorante,
        partita_iva,
        ragione_sociale,
        attivo
    )
    VALUES (
        p_user_id,
        p_nome,
        p_piva,
        p_ragione_sociale,
        true
    )
    RETURNING public.ristoranti.id, public.ristoranti.nome_ristorante, public.ristoranti.partita_iva;
END;
$$;

GRANT EXECUTE ON FUNCTION public.create_ristorante_for_user(UUID, TEXT, VARCHAR(11), TEXT) TO authenticated;

CREATE OR REPLACE FUNCTION public.conta_ristoranti_utente(
    p_user_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    SELECT COUNT(*)::INTEGER
    INTO v_count
    FROM public.ristoranti AS r
    WHERE r.user_id = p_user_id
      AND r.attivo = true;

    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_ricette_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_ingredienti_workspace_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_ingredienti_utente_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_note_diario_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_next_ordine_ricetta(
    p_userid UUID,
    p_ristorante_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_max_ordine INTEGER;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_userid IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF p_ristorante_id IS NOT NULL
       AND COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = p_userid
       ) THEN
        RAISE EXCEPTION 'Ristorante non autorizzato';
    END IF;

    SELECT COALESCE(MAX(r.ordine_visualizzazione), 0)
    INTO v_max_ordine
    FROM public.ricette AS r
    WHERE r.userid = p_userid
      AND (
          r.ristorante_id = p_ristorante_id
          OR (r.ristorante_id IS NULL AND p_ristorante_id IS NULL)
      );

    RETURN v_max_ordine + 1;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_next_ordine_ricetta(UUID, UUID) TO authenticated;

CREATE OR REPLACE FUNCTION public.swap_ricette_order(
    ricetta_id_1 UUID,
    ricetta_id_2 UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_user_1 UUID;
    v_user_2 UUID;
    v_ordine_1 INTEGER;
    v_ordine_2 INTEGER;
BEGIN
    SELECT r.userid, r.ordine_visualizzazione
    INTO v_user_1, v_ordine_1
    FROM public.ricette AS r
    WHERE r.id = ricetta_id_1
    FOR UPDATE;

    SELECT r.userid, r.ordine_visualizzazione
    INTO v_user_2, v_ordine_2
    FROM public.ricette AS r
    WHERE r.id = ricetta_id_2
    FOR UPDATE;

    IF v_user_1 IS NULL OR v_user_2 IS NULL THEN
        RAISE EXCEPTION 'Ricette non trovate';
    END IF;

    IF v_user_1 IS DISTINCT FROM v_user_2 THEN
        RAISE EXCEPTION 'Le ricette non appartengono allo stesso utente';
    END IF;

    IF COALESCE(auth.role(), '') <> 'service_role' AND v_user_1 IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    UPDATE public.ricette
    SET ordine_visualizzazione = v_ordine_2
    WHERE id = ricetta_id_1;

    UPDATE public.ricette
    SET ordine_visualizzazione = v_ordine_1
    WHERE id = ricetta_id_2;

    RETURN true;
END;
$$;

GRANT EXECUTE ON FUNCTION public.swap_ricette_order(UUID, UUID) TO authenticated;

CREATE OR REPLACE FUNCTION public.sync_piva_ristoranti()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.piva_ristoranti (
            user_id,
            ristorante_id,
            piva,
            nome_ristorante
        )
        VALUES (
            NEW.user_id,
            NEW.id,
            NEW.partita_iva,
            NEW.nome_ristorante
        );

        IF NEW.partita_iva IS NOT NULL AND trim(NEW.partita_iva) <> '' THEN
            PERFORM public.resolve_unknown_tenant(trim(NEW.partita_iva));
        END IF;

        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE public.piva_ristoranti
        SET piva = NEW.partita_iva,
            nome_ristorante = NEW.nome_ristorante
        WHERE ristorante_id = NEW.id;

        IF NEW.partita_iva IS DISTINCT FROM OLD.partita_iva
           AND NEW.partita_iva IS NOT NULL
           AND trim(NEW.partita_iva) <> '' THEN
            PERFORM public.resolve_unknown_tenant(trim(NEW.partita_iva));
        END IF;

        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM public.piva_ristoranti
        WHERE ristorante_id = OLD.id;

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

DROP FUNCTION IF EXISTS public.increment_ai_cost(UUID, DECIMAL, INT);
DROP FUNCTION IF EXISTS public.increment_ai_cost(UUID, DECIMAL, INT, TEXT);
DROP FUNCTION IF EXISTS public.get_ai_costs_summary();
DROP FUNCTION IF EXISTS public.get_ai_costs_summary(INTEGER);
DROP FUNCTION IF EXISTS public.get_ai_costs_timeseries();
DROP FUNCTION IF EXISTS public.get_ai_costs_timeseries(INTEGER);
DROP FUNCTION IF EXISTS public.get_ai_recent_operations();
DROP FUNCTION IF EXISTS public.get_ai_recent_operations(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS public.track_ai_usage_event(UUID, TEXT, TEXT, INT, INT, DECIMAL, DECIMAL, DECIMAL, UUID, TEXT, INT, JSONB);

CREATE OR REPLACE FUNCTION public.track_ai_usage_event(
    p_ristorante_id UUID,
    p_operation_type TEXT DEFAULT 'pdf',
    p_model TEXT DEFAULT 'gpt-4o-mini',
    p_prompt_tokens INT DEFAULT 0,
    p_completion_tokens INT DEFAULT 0,
    p_input_cost DECIMAL DEFAULT 0,
    p_output_cost DECIMAL DEFAULT 0,
    p_total_cost DECIMAL DEFAULT 0,
    p_user_id UUID DEFAULT NULL,
    p_source_file TEXT DEFAULT NULL,
    p_item_count INT DEFAULT 1,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event_id BIGINT;
    v_total_tokens INT;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = auth.uid()
       ) THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF COALESCE(auth.role(), '') <> 'service_role'
       AND p_user_id IS NOT NULL
       AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'user_id non autorizzato';
    END IF;

    v_total_tokens := COALESCE(p_prompt_tokens, 0) + COALESCE(p_completion_tokens, 0);

    INSERT INTO public.ai_usage_events (
        ristorante_id,
        user_id,
        operation_type,
        model,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        input_cost,
        output_cost,
        total_cost,
        item_count,
        source_file,
        metadata
    )
    VALUES (
        p_ristorante_id,
        COALESCE(p_user_id, auth.uid()),
        COALESCE(NULLIF(p_operation_type, ''), 'other'),
        COALESCE(NULLIF(p_model, ''), 'gpt-4o-mini'),
        COALESCE(p_prompt_tokens, 0),
        COALESCE(p_completion_tokens, 0),
        v_total_tokens,
        COALESCE(p_input_cost, 0),
        COALESCE(p_output_cost, 0),
        COALESCE(p_total_cost, 0),
        GREATEST(COALESCE(p_item_count, 1), 1),
        NULLIF(p_source_file, ''),
        COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_event_id;

    UPDATE public.ristoranti
    SET ai_cost_total = COALESCE(ai_cost_total, 0) + COALESCE(p_total_cost, 0),
        ai_pdf_count = CASE
            WHEN p_operation_type = 'pdf' THEN COALESCE(ai_pdf_count, 0) + 1
            ELSE COALESCE(ai_pdf_count, 0)
        END,
        ai_categorization_count = CASE
            WHEN p_operation_type = 'categorization' THEN COALESCE(ai_categorization_count, 0) + 1
            ELSE COALESCE(ai_categorization_count, 0)
        END,
        ai_last_usage = NOW()
    WHERE id = p_ristorante_id;

    RETURN v_event_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.increment_ai_cost(
    p_ristorante_id UUID,
    p_cost DECIMAL,
    p_tokens INT DEFAULT 0,
    p_operation_type TEXT DEFAULT 'pdf'
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    PERFORM public.track_ai_usage_event(
        p_ristorante_id := p_ristorante_id,
        p_operation_type := p_operation_type,
        p_model := 'gpt-4o-mini',
        p_prompt_tokens := 0,
        p_completion_tokens := 0,
        p_input_cost := 0,
        p_output_cost := 0,
        p_total_cost := COALESCE(p_cost, 0),
        p_user_id := auth.uid(),
        p_source_file := NULL,
        p_item_count := 1,
        p_metadata := jsonb_build_object(
            'legacy_tokens', COALESCE(p_tokens, 0),
            'tracking_mode', 'legacy_increment'
        )
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.get_ai_costs_summary(
    p_days INTEGER DEFAULT NULL
)
RETURNS TABLE (
    ristorante_id UUID,
    nome_ristorante TEXT,
    ragione_sociale TEXT,
    ai_cost_total DECIMAL,
    ai_pdf_count INT,
    ai_categorization_count INT,
    ai_last_usage TIMESTAMPTZ,
    ai_avg_cost_per_operation DECIMAL,
    pdf_cost_total DECIMAL,
    categorization_cost_total DECIMAL,
    avg_cost_per_pdf DECIMAL,
    avg_cost_per_categorization DECIMAL,
    total_tokens BIGINT,
    prompt_tokens BIGINT,
    completion_tokens BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    WITH scoped_ristoranti AS (
        SELECT r.*
        FROM public.ristoranti AS r
        WHERE r.attivo = true
          AND (
              COALESCE(auth.role(), '') = 'service_role'
              OR r.user_id = auth.uid()
          )
    ),
    filtered_events AS (
        SELECT e.*
        FROM public.ai_usage_events AS e
        JOIN scoped_ristoranti AS sr
          ON sr.id = e.ristorante_id
        WHERE p_days IS NULL
           OR e.created_at >= NOW() - make_interval(days => p_days)
    ),
    agg AS (
        SELECT
            e.ristorante_id,
            SUM(e.total_cost)::DECIMAL(12,6) AS total_cost,
            COUNT(*) FILTER (WHERE e.operation_type = 'pdf')::INT AS pdf_count,
            COUNT(*) FILTER (WHERE e.operation_type = 'categorization')::INT AS categorization_count,
            MAX(e.created_at) AS last_usage,
            SUM(e.total_cost) FILTER (WHERE e.operation_type = 'pdf')::DECIMAL(12,6) AS pdf_cost_total,
            SUM(e.total_cost) FILTER (WHERE e.operation_type = 'categorization')::DECIMAL(12,6) AS categorization_cost_total,
            SUM(e.total_tokens)::BIGINT AS total_tokens,
            SUM(e.prompt_tokens)::BIGINT AS prompt_tokens,
            SUM(e.completion_tokens)::BIGINT AS completion_tokens
        FROM filtered_events AS e
        GROUP BY e.ristorante_id
    )
    SELECT
        sr.id,
        sr.nome_ristorante,
        sr.ragione_sociale,
        COALESCE(a.total_cost, 0)::DECIMAL(12,6) AS ai_cost_total,
        COALESCE(a.pdf_count, 0)::INT AS ai_pdf_count,
        COALESCE(a.categorization_count, 0)::INT AS ai_categorization_count,
        a.last_usage,
        CASE
            WHEN (COALESCE(a.pdf_count, 0) + COALESCE(a.categorization_count, 0)) > 0
            THEN ROUND(COALESCE(a.total_cost, 0) / (COALESCE(a.pdf_count, 0) + COALESCE(a.categorization_count, 0)), 6)
            ELSE 0
        END::DECIMAL(12,6) AS ai_avg_cost_per_operation,
        COALESCE(a.pdf_cost_total, 0)::DECIMAL(12,6) AS pdf_cost_total,
        COALESCE(a.categorization_cost_total, 0)::DECIMAL(12,6) AS categorization_cost_total,
        CASE
            WHEN COALESCE(a.pdf_count, 0) > 0 THEN ROUND(COALESCE(a.pdf_cost_total, 0) / a.pdf_count, 6)
            ELSE 0
        END::DECIMAL(12,6) AS avg_cost_per_pdf,
        CASE
            WHEN COALESCE(a.categorization_count, 0) > 0 THEN ROUND(COALESCE(a.categorization_cost_total, 0) / a.categorization_count, 6)
            ELSE 0
        END::DECIMAL(12,6) AS avg_cost_per_categorization,
        COALESCE(a.total_tokens, 0)::BIGINT,
        COALESCE(a.prompt_tokens, 0)::BIGINT,
        COALESCE(a.completion_tokens, 0)::BIGINT
    FROM scoped_ristoranti AS sr
    LEFT JOIN agg AS a
      ON a.ristorante_id = sr.id
    WHERE COALESCE(a.total_cost, 0) > 0
    ORDER BY COALESCE(a.total_cost, 0) DESC, sr.nome_ristorante;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_ai_costs_timeseries(
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE (
    usage_date DATE,
    total_cost DECIMAL,
    pdf_cost DECIMAL,
    categorization_cost DECIMAL,
    operations_count INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.created_at::DATE AS usage_date,
        SUM(e.total_cost)::DECIMAL(12,6) AS total_cost,
        SUM(e.total_cost) FILTER (WHERE e.operation_type = 'pdf')::DECIMAL(12,6) AS pdf_cost,
        SUM(e.total_cost) FILTER (WHERE e.operation_type = 'categorization')::DECIMAL(12,6) AS categorization_cost,
        COUNT(*)::INT AS operations_count
    FROM public.ai_usage_events AS e
    JOIN public.ristoranti AS r
      ON r.id = e.ristorante_id
    WHERE e.created_at >= NOW() - make_interval(days => COALESCE(p_days, 30))
      AND (
          COALESCE(auth.role(), '') = 'service_role'
          OR r.user_id = auth.uid()
      )
    GROUP BY e.created_at::DATE
    ORDER BY usage_date;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_ai_recent_operations(
    p_days INTEGER DEFAULT 30,
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    created_at TIMESTAMPTZ,
    nome_ristorante TEXT,
    ragione_sociale TEXT,
    operation_type TEXT,
    model TEXT,
    source_file TEXT,
    item_count INT,
    prompt_tokens INT,
    completion_tokens INT,
    total_tokens INT,
    total_cost DECIMAL
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.created_at,
        r.nome_ristorante,
        r.ragione_sociale,
        e.operation_type,
        e.model,
        e.source_file,
        e.item_count,
        e.prompt_tokens,
        e.completion_tokens,
        e.total_tokens,
        e.total_cost
    FROM public.ai_usage_events AS e
    JOIN public.ristoranti AS r
      ON r.id = e.ristorante_id
    WHERE e.created_at >= NOW() - make_interval(days => COALESCE(p_days, 30))
      AND (
          COALESCE(auth.role(), '') = 'service_role'
          OR r.user_id = auth.uid()
      )
    ORDER BY e.created_at DESC
    LIMIT COALESCE(p_limit, 100);
END;
$$;

GRANT EXECUTE ON FUNCTION public.track_ai_usage_event(UUID, TEXT, TEXT, INT, INT, DECIMAL, DECIMAL, DECIMAL, UUID, TEXT, INT, JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION public.increment_ai_cost(UUID, DECIMAL, INT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_summary(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_timeseries(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_ai_recent_operations(INTEGER, INTEGER) TO authenticated;

COMMIT;