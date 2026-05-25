-- ============================================================
-- MIGRATION 20260525110100: Hardening indici/policy suggerimenti tag
-- ============================================================
-- Obiettivi:
-- 1) Dedupe pending robusto lato DB
-- 2) Indici extra per query operativa
-- 3) Allineamento grant/policy con pattern security cleanup

BEGIN;

-- ============================================================
-- 1) Dedupe pending (no duplicati aperti per stesso cluster)
-- ============================================================
CREATE UNIQUE INDEX IF NOT EXISTS idx_cts_unique_pending_cluster
    ON public.custom_tag_suggestions (user_id, ristorante_id, suggestion_type, cluster_key)
    WHERE status = 'pending';

-- ============================================================
-- 2) Indici extra ottimizzazione
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cts_rist_status_updated
    ON public.custom_tag_suggestions (ristorante_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_cts_snooze_until
    ON public.custom_tag_suggestions (user_id, ristorante_id, snooze_until)
    WHERE status = 'snoozed';

CREATE INDEX IF NOT EXISTS idx_ctsi_rist_desc_key
    ON public.custom_tag_suggestion_items (ristorante_id, descrizione_key);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ctsi_unique_suggestion_desc_key
    ON public.custom_tag_suggestion_items (suggestion_id, descrizione_key);

-- ============================================================
-- 3) Grant espliciti a authenticated
-- ============================================================
REVOKE ALL ON public.custom_tag_suggestions FROM anon;
REVOKE ALL ON public.custom_tag_suggestion_items FROM anon;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.custom_tag_suggestions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.custom_tag_suggestion_items TO authenticated;

DO $$
DECLARE
    v_sequence TEXT;
BEGIN
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
          AND tbl.relname IN ('custom_tag_suggestions', 'custom_tag_suggestion_items')
    LOOP
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO authenticated', v_sequence);
    END LOOP;
END;
$$;

COMMIT;
