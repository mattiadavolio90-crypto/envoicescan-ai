-- ============================================================
-- MIGRATION 061: Cleanup policy duplicate legacy names + optimize auth.uid() in RLS
-- Scope: structural only, no data changes
-- Notes:
--   - Keeps current/canonical policy behavior for each table
--   - Drops stale/legacy policy names if they survived on remote
--   - Rewrites direct auth.uid() calls in active RLS policies to (select auth.uid())
--   - Leaves permissive custom-auth compatibility policies unchanged where they are the current repo baseline
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1) USERS — keep only canonical self policies, optimized
-- ------------------------------------------------------------
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    v_policy RECORD;
BEGIN
    IF to_regclass('public.users') IS NULL THEN
        RETURN;
    END IF;

    FOR v_policy IN
        SELECT p.policyname
        FROM pg_policies AS p
        WHERE p.schemaname = 'public'
          AND p.tablename = 'users'
          AND p.policyname NOT IN (
                'users_select_self',
                'users_insert_self',
                'users_update_self',
                'users_delete_self'
          )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.users', v_policy.policyname);
    END LOOP;
END
$$;

DROP POLICY IF EXISTS users_select_self ON public.users;
DROP POLICY IF EXISTS users_insert_self ON public.users;
DROP POLICY IF EXISTS users_update_self ON public.users;
DROP POLICY IF EXISTS users_delete_self ON public.users;

CREATE POLICY users_select_self
ON public.users
FOR SELECT
TO authenticated
USING (id = (select auth.uid()));

CREATE POLICY users_insert_self
ON public.users
FOR INSERT
TO authenticated
WITH CHECK (id = (select auth.uid()));

CREATE POLICY users_update_self
ON public.users
FOR UPDATE
TO authenticated
USING (id = (select auth.uid()))
WITH CHECK (id = (select auth.uid()));

CREATE POLICY users_delete_self
ON public.users
FOR DELETE
TO authenticated
USING (id = (select auth.uid()));

-- ------------------------------------------------------------
-- 2) FATTURE — drop stale names and recreate canonical policies
-- ------------------------------------------------------------
ALTER TABLE public.fatture ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    v_policy RECORD;
BEGIN
    IF to_regclass('public.fatture') IS NULL THEN
        RETURN;
    END IF;

    FOR v_policy IN
        SELECT p.policyname
        FROM pg_policies AS p
        WHERE p.schemaname = 'public'
          AND p.tablename = 'fatture'
          AND p.policyname NOT IN (
                'Users can view own fatture per ristorante',
                'Users can insert own fatture per ristorante',
                'Users can update own fatture per ristorante',
                'Users can delete own fatture per ristorante',
                'Service role full access fatture'
          )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.fatture', v_policy.policyname);
    END LOOP;
END
$$;

DROP POLICY IF EXISTS "allow_select_own_fatture" ON public.fatture;
DROP POLICY IF EXISTS "allow_insert_own_fatture" ON public.fatture;
DROP POLICY IF EXISTS "allow_update_own_fatture" ON public.fatture;
DROP POLICY IF EXISTS "allow_delete_own_fatture" ON public.fatture;
DROP POLICY IF EXISTS "select_fatture_with_valid_user" ON public.fatture;
DROP POLICY IF EXISTS "insert_fatture_with_valid_user" ON public.fatture;
DROP POLICY IF EXISTS "update_fatture_with_valid_user" ON public.fatture;
DROP POLICY IF EXISTS "delete_fatture_with_valid_user" ON public.fatture;
DROP POLICY IF EXISTS "Users can view own fatture" ON public.fatture;
DROP POLICY IF EXISTS "Users can insert own fatture" ON public.fatture;
DROP POLICY IF EXISTS "Users can update own fatture" ON public.fatture;
DROP POLICY IF EXISTS "Users can delete own fatture" ON public.fatture;
DROP POLICY IF EXISTS "Users can view own fatture per ristorante" ON public.fatture;
DROP POLICY IF EXISTS "Users can insert own fatture per ristorante" ON public.fatture;
DROP POLICY IF EXISTS "Users can update own fatture per ristorante" ON public.fatture;
DROP POLICY IF EXISTS "Users can delete own fatture per ristorante" ON public.fatture;

CREATE POLICY "Users can view own fatture per ristorante"
ON public.fatture
FOR SELECT
TO authenticated
USING (
    user_id = (select auth.uid())
    AND ristorante_id IN (
        SELECT r.id
        FROM public.ristoranti AS r
        WHERE r.user_id = (select auth.uid())
    )
);

CREATE POLICY "Users can insert own fatture per ristorante"
ON public.fatture
FOR INSERT
TO authenticated
WITH CHECK (
    user_id = (select auth.uid())
    AND ristorante_id IN (
        SELECT r.id
        FROM public.ristoranti AS r
        WHERE r.user_id = (select auth.uid())
    )
);

CREATE POLICY "Users can update own fatture per ristorante"
ON public.fatture
FOR UPDATE
TO authenticated
USING (
    user_id = (select auth.uid())
    AND ristorante_id IN (
        SELECT r.id
        FROM public.ristoranti AS r
        WHERE r.user_id = (select auth.uid())
    )
)
WITH CHECK (
    user_id = (select auth.uid())
    AND ristorante_id IN (
        SELECT r.id
        FROM public.ristoranti AS r
        WHERE r.user_id = (select auth.uid())
    )
);

CREATE POLICY "Users can delete own fatture per ristorante"
ON public.fatture
FOR DELETE
TO authenticated
USING (
    user_id = (select auth.uid())
    AND ristorante_id IN (
        SELECT r.id
        FROM public.ristoranti AS r
        WHERE r.user_id = (select auth.uid())
    )
);

-- ------------------------------------------------------------
-- 3) RISTORANTI — keep only 2 policies: user_own + admin_all
-- ------------------------------------------------------------
ALTER TABLE public.ristoranti ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    v_policy RECORD;
BEGIN
    IF to_regclass('public.ristoranti') IS NULL THEN
        RETURN;
    END IF;

    FOR v_policy IN
        SELECT p.policyname
        FROM pg_policies AS p
        WHERE p.schemaname = 'public'
          AND p.tablename = 'ristoranti'
          AND p.policyname NOT IN (
                'user_own_restaurants',
                'admin_all_restaurants'
          )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.ristoranti', v_policy.policyname);
    END LOOP;
END
$$;

DROP POLICY IF EXISTS "User owns restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "Users can select own restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "Users can insert own restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "Users can update own restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "Users can delete own restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "Admin sees all restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "Admin full access restaurants" ON public.ristoranti;
DROP POLICY IF EXISTS "ristoranti_select_policy" ON public.ristoranti;
DROP POLICY IF EXISTS "ristoranti_insert_policy" ON public.ristoranti;
DROP POLICY IF EXISTS "ristoranti_update_policy" ON public.ristoranti;
DROP POLICY IF EXISTS "ristoranti_delete_policy" ON public.ristoranti;
DROP POLICY IF EXISTS user_own_restaurants ON public.ristoranti;
DROP POLICY IF EXISTS admin_all_restaurants ON public.ristoranti;

CREATE POLICY user_own_restaurants
ON public.ristoranti
FOR ALL
TO authenticated
USING (user_id = (select auth.uid()))
WITH CHECK (user_id = (select auth.uid()));

CREATE POLICY admin_all_restaurants
ON public.ristoranti
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- ------------------------------------------------------------
-- 4) PRODOTTI_UTENTE — canonical owner policies, optimized
-- ------------------------------------------------------------
ALTER TABLE public.prodotti_utente ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    v_policy RECORD;
BEGIN
    IF to_regclass('public.prodotti_utente') IS NULL THEN
        RETURN;
    END IF;

    FOR v_policy IN
        SELECT p.policyname
        FROM pg_policies AS p
        WHERE p.schemaname = 'public'
          AND p.tablename = 'prodotti_utente'
          AND p.policyname NOT IN (
                'prodotti_utente_select_policy',
                'prodotti_utente_insert_policy',
                'prodotti_utente_update_policy',
                'prodotti_utente_delete_policy'
          )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.prodotti_utente', v_policy.policyname);
    END LOOP;
END
$$;

DROP POLICY IF EXISTS "Users see own products" ON public.prodotti_utente;
DROP POLICY IF EXISTS prodotti_utente_select_policy ON public.prodotti_utente;
DROP POLICY IF EXISTS prodotti_utente_insert_policy ON public.prodotti_utente;
DROP POLICY IF EXISTS prodotti_utente_update_policy ON public.prodotti_utente;
DROP POLICY IF EXISTS prodotti_utente_delete_policy ON public.prodotti_utente;

CREATE POLICY prodotti_utente_select_policy
ON public.prodotti_utente
FOR SELECT
TO authenticated
USING (user_id = (select auth.uid()));

CREATE POLICY prodotti_utente_insert_policy
ON public.prodotti_utente
FOR INSERT
TO authenticated
WITH CHECK (user_id = (select auth.uid()));

CREATE POLICY prodotti_utente_update_policy
ON public.prodotti_utente
FOR UPDATE
TO authenticated
USING (user_id = (select auth.uid()))
WITH CHECK (user_id = (select auth.uid()));

CREATE POLICY prodotti_utente_delete_policy
ON public.prodotti_utente
FOR DELETE
TO authenticated
USING (user_id = (select auth.uid()));

-- ------------------------------------------------------------
-- 5) CUSTOM_TAGS + CUSTOM_TAG_PRODOTTI — optimize active owner policies
-- ------------------------------------------------------------
DO $$
DECLARE
    v_table TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['custom_tags', 'custom_tag_prodotti']
    LOOP
        IF to_regclass('public.' || v_table) IS NULL THEN
            CONTINUE;
        END IF;

        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_select_own', v_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_insert_own', v_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_update_own', v_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_delete_own', v_table);

        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (user_id = (select auth.uid()))',
            v_table || '_select_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (user_id = (select auth.uid()))',
            v_table || '_insert_own',
            v_table
        );
        EXECUTE format(
            '' ||
            'CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated ' ||
            'USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()))',
            v_table || '_update_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (user_id = (select auth.uid()))',
            v_table || '_delete_own',
            v_table
        );
    END LOOP;
END
$$;

-- ------------------------------------------------------------
-- 6) Optional legacy tables referenced by hardening migration 052
--    Only if they exist remotely
-- ------------------------------------------------------------
DO $$
DECLARE
    v_table TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['articoli', 'fatture_processate', 'memoria_ai_categorie']
    LOOP
        IF to_regclass('public.' || v_table) IS NULL THEN
            CONTINUE;
        END IF;

        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_select_own', v_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_insert_own', v_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_update_own', v_table);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_table || '_delete_own', v_table);

        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (user_id = (select auth.uid()))',
            v_table || '_select_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (user_id = (select auth.uid()))',
            v_table || '_insert_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (user_id = (select auth.uid())) WITH CHECK (user_id = (select auth.uid()))',
            v_table || '_update_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (user_id = (select auth.uid()))',
            v_table || '_delete_own',
            v_table
        );
    END LOOP;
END
$$;

COMMIT;
