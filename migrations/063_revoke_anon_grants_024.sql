-- ============================================================
-- MIGRATION 063: Revoca GRANT ALL TO anon introdotti in 024
-- ============================================================
-- Migration 024 ha concesso GRANT ALL su tabelle operative al ruolo
-- anon (richieste non autenticate via PostgREST). Questo consente
-- accesso e modifica dei dati di qualsiasi utente senza autenticazione.
--
-- Questo fix:
-- 1. Revoca tutti i permessi al ruolo anon su quelle tabelle
-- 2. Concede solo SELECT, INSERT, UPDATE, DELETE al ruolo authenticated
--    (non TRUNCATE né REFERENCES né TRIGGER)
-- 3. Mantiene GRANT ALL a service_role (necessario per il worker)
-- ============================================================

BEGIN;

-- ============================================================
-- ingredienti_workspace
-- ============================================================
REVOKE ALL ON public.ingredienti_workspace FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingredienti_workspace TO authenticated;
GRANT ALL ON public.ingredienti_workspace TO service_role;

-- ============================================================
-- ricette
-- ============================================================
REVOKE ALL ON public.ricette FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ricette TO authenticated;
GRANT ALL ON public.ricette TO service_role;

-- ============================================================
-- note_diario
-- ============================================================
REVOKE ALL ON public.note_diario FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.note_diario TO authenticated;
GRANT ALL ON public.note_diario TO service_role;

-- ============================================================
-- ingredienti_utente
-- ============================================================
REVOKE ALL ON public.ingredienti_utente FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ingredienti_utente TO authenticated;
GRANT ALL ON public.ingredienti_utente TO service_role;

-- ============================================================
-- Revoca anche da classificazioni_manuali (migration 030 ha GRANT ALL TO anon)
-- ============================================================
REVOKE ALL ON public.classificazioni_manuali FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.classificazioni_manuali TO authenticated;
GRANT ALL ON public.classificazioni_manuali TO service_role;

-- ============================================================
-- Verifica post-revoca (output nei logs di migrazione)
-- ============================================================
DO $$
DECLARE
    v_table TEXT;
    v_has_anon_grants BOOLEAN;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'ingredienti_workspace',
        'ricette',
        'note_diario',
        'ingredienti_utente',
        'classificazioni_manuali'
    ]
    LOOP
        IF to_regclass('public.' || v_table) IS NULL THEN
            RAISE NOTICE 'SKIP %: tabella non trovata', v_table;
            CONTINUE;
        END IF;

        SELECT EXISTS (
            SELECT 1
            FROM information_schema.role_table_grants AS g
            WHERE g.table_schema = 'public'
              AND g.table_name   = v_table
              AND g.grantee      = 'anon'
        ) INTO v_has_anon_grants;

        IF v_has_anon_grants THEN
            RAISE WARNING 'ATTENZIONE: anon ha ancora grants su public.%', v_table;
        ELSE
            RAISE NOTICE 'OK: anon non ha grants su public.%', v_table;
        END IF;
    END LOOP;
END;
$$;

COMMIT;
