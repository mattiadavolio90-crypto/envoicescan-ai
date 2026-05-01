-- ============================================================
-- Migration: add_category_change_log
-- Data: 2026-04-29
-- Scopo: Storico cronologico append-only delle modifiche categoria
--        con old/new per audit forense e confronto delta preciso.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.category_change_log (
    id BIGSERIAL PRIMARY KEY,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    table_name TEXT NOT NULL,
    target_id TEXT,
    user_id UUID,
    ristorante_id UUID,
    descrizione TEXT,
    file_origine TEXT,
    numero_riga INTEGER,
    old_categoria TEXT,
    new_categoria TEXT,
    actor_user_id UUID,
    actor_email TEXT,
    source TEXT NOT NULL DEFAULT 'db_trigger',
    batch_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_category_change_log_changed_at
    ON public.category_change_log (changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_category_change_log_user_changed_at
    ON public.category_change_log (user_id, changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_category_change_log_batch_id
    ON public.category_change_log (batch_id);

CREATE INDEX IF NOT EXISTS idx_category_change_log_table_target
    ON public.category_change_log (table_name, target_id);

COMMENT ON TABLE public.category_change_log IS
    'Log append-only delle modifiche categoria (old/new) per audit cronologico preciso.';

COMMENT ON COLUMN public.category_change_log.source IS
    'Origine evento: db_trigger, ui_cliente, ui_admin, script, migration, ecc.';

CREATE OR REPLACE FUNCTION public.fn_log_category_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_actor_sub_text TEXT;
    v_actor_email TEXT;
    v_source TEXT;
    v_batch_text TEXT;
    v_batch_id UUID;
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

    INSERT INTO public.category_change_log (
        table_name,
        target_id,
        user_id,
        ristorante_id,
        descrizione,
        file_origine,
        numero_riga,
        old_categoria,
        new_categoria,
        actor_user_id,
        actor_email,
        source,
        batch_id,
        details
    )
    VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id::TEXT, OLD.id::TEXT),
        COALESCE(NEW.user_id, OLD.user_id),
        COALESCE(NEW.ristorante_id, OLD.ristorante_id),
        COALESCE(NEW.descrizione, OLD.descrizione),
        CASE
            WHEN TG_TABLE_NAME = 'fatture' THEN COALESCE(NEW.file_origine, OLD.file_origine)
            ELSE NULL
        END,
        CASE
            WHEN TG_TABLE_NAME = 'fatture' THEN COALESCE(NEW.numero_riga, OLD.numero_riga)
            ELSE NULL
        END,
        OLD.categoria,
        NEW.categoria,
        CASE
            WHEN v_actor_sub_text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                THEN v_actor_sub_text::UUID
            ELSE NULL
        END,
        v_actor_email,
        v_source,
        v_batch_id,
        jsonb_build_object('trigger', TG_NAME)
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_log_category_change_fatture ON public.fatture;
CREATE TRIGGER trg_log_category_change_fatture
AFTER UPDATE OF categoria ON public.fatture
FOR EACH ROW
EXECUTE FUNCTION public.fn_log_category_change();

DROP TRIGGER IF EXISTS trg_log_category_change_prodotti_utente ON public.prodotti_utente;
CREATE TRIGGER trg_log_category_change_prodotti_utente
AFTER UPDATE OF categoria ON public.prodotti_utente
FOR EACH ROW
EXECUTE FUNCTION public.fn_log_category_change();

ALTER TABLE public.category_change_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS category_change_log_select_authenticated ON public.category_change_log;
CREATE POLICY category_change_log_select_authenticated
ON public.category_change_log
FOR SELECT
TO authenticated
USING (true);

DROP POLICY IF EXISTS category_change_log_insert_service_role ON public.category_change_log;
CREATE POLICY category_change_log_insert_service_role
ON public.category_change_log
FOR INSERT
TO service_role
WITH CHECK (true);

REVOKE ALL ON public.category_change_log FROM anon;
GRANT SELECT ON public.category_change_log TO authenticated;
GRANT SELECT, INSERT ON public.category_change_log TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.category_change_log_id_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.category_change_log_id_seq TO service_role;

COMMIT;
