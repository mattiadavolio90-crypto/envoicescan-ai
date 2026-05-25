-- ============================================================
-- MIGRATION 080: Suggerimenti automatici per Custom Tag
-- ============================================================
-- Obiettivi:
-- 1) Introdurre tabella suggerimenti (header)
-- 2) Introdurre tabella item suggeriti (dettaglio prodotti)
-- 3) Garantire ownership user_id + ristorante_id e normalizzazione descrizione_key
-- 4) Applicare RLS owner-based coerente al pattern esistente

BEGIN;

-- ============================================================
-- 0) Tabelle
-- ============================================================
CREATE TABLE IF NOT EXISTS public.custom_tag_suggestions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ristorante_id UUID NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    suggestion_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    suggested_tag_name TEXT,
    target_tag_id BIGINT REFERENCES public.custom_tags(id) ON DELETE SET NULL,
    cluster_key TEXT NOT NULL,
    confidence_score NUMERIC(5,2),
    detection_window_days INT NOT NULL DEFAULT 30,
    matched_products_count INT NOT NULL DEFAULT 0,
    matched_rows_count INT NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snooze_until TIMESTAMPTZ,
    feedback_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT custom_tag_suggestions_type_chk CHECK (suggestion_type IN ('new_tag', 'extend_tag')),
    CONSTRAINT custom_tag_suggestions_status_chk CHECK (status IN ('pending', 'accepted', 'dismissed', 'snoozed')),
    CONSTRAINT custom_tag_suggestions_cluster_key_nonempty_chk CHECK (btrim(cluster_key) <> ''),
    CONSTRAINT custom_tag_suggestions_window_positive_chk CHECK (detection_window_days > 0),
    CONSTRAINT custom_tag_suggestions_products_nonnegative_chk CHECK (matched_products_count >= 0),
    CONSTRAINT custom_tag_suggestions_rows_nonnegative_chk CHECK (matched_rows_count >= 0),
    CONSTRAINT custom_tag_suggestions_confidence_range_chk CHECK (
        confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)
    )
);

COMMENT ON TABLE public.custom_tag_suggestions
IS 'Suggerimenti automatici di creazione/estensione tag per user+ristorante con stato workflow.';

CREATE TABLE IF NOT EXISTS public.custom_tag_suggestion_items (
    id BIGSERIAL PRIMARY KEY,
    suggestion_id BIGINT NOT NULL REFERENCES public.custom_tag_suggestions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ristorante_id UUID NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    descrizione TEXT NOT NULL,
    descrizione_key TEXT NOT NULL,
    occorrenze INT NOT NULL DEFAULT 1,
    fornitori_count INT NOT NULL DEFAULT 0,
    last_seen_date DATE,
    selected_by_default BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT custom_tag_suggestion_items_descrizione_nonempty_chk CHECK (btrim(descrizione) <> ''),
    CONSTRAINT custom_tag_suggestion_items_descrizione_key_nonempty_chk CHECK (btrim(descrizione_key) <> ''),
    CONSTRAINT custom_tag_suggestion_items_occorrenze_positive_chk CHECK (occorrenze >= 1),
    CONSTRAINT custom_tag_suggestion_items_fornitori_nonnegative_chk CHECK (fornitori_count >= 0)
);

COMMENT ON TABLE public.custom_tag_suggestion_items
IS 'Dettaglio descrizioni/prodotti che compongono ciascun suggerimento tag.';

-- ============================================================
-- 1) Trigger helper: updated_at su custom_tag_suggestions
-- ============================================================
CREATE OR REPLACE FUNCTION public.custom_tag_suggestions_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_custom_tag_suggestions_set_updated_at ON public.custom_tag_suggestions;

CREATE TRIGGER trg_custom_tag_suggestions_set_updated_at
    BEFORE UPDATE ON public.custom_tag_suggestions
    FOR EACH ROW
    EXECUTE FUNCTION public.custom_tag_suggestions_set_updated_at();

-- ============================================================
-- 2) Trigger helper: allineamento ownership + normalizzazione item
-- ============================================================
CREATE OR REPLACE FUNCTION public.custom_tag_suggestion_items_prepare_row()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id UUID;
    v_ristorante_id UUID;
BEGIN
    NEW.descrizione := btrim(COALESCE(NEW.descrizione, ''));
    NEW.descrizione_key := public.normalize_custom_tag_key(NEW.descrizione);

    IF NEW.descrizione_key IS NULL THEN
        RAISE EXCEPTION 'descrizione_key vuota non consentita';
    END IF;

    SELECT s.user_id, s.ristorante_id
      INTO v_user_id, v_ristorante_id
      FROM public.custom_tag_suggestions AS s
     WHERE s.id = NEW.suggestion_id;

    IF v_user_id IS NULL OR v_ristorante_id IS NULL THEN
        RAISE EXCEPTION 'suggestion_id % non valido o ownership non trovata', NEW.suggestion_id;
    END IF;

    NEW.user_id := v_user_id;
    NEW.ristorante_id := v_ristorante_id;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_custom_tag_suggestion_items_prepare_row ON public.custom_tag_suggestion_items;

CREATE TRIGGER trg_custom_tag_suggestion_items_prepare_row
    BEFORE INSERT OR UPDATE ON public.custom_tag_suggestion_items
    FOR EACH ROW
    EXECUTE FUNCTION public.custom_tag_suggestion_items_prepare_row();

-- ============================================================
-- 3) Indici base
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cts_user_rist_status_updated
    ON public.custom_tag_suggestions (user_id, ristorante_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_cts_user_rist_type_status
    ON public.custom_tag_suggestions (user_id, ristorante_id, suggestion_type, status);

CREATE INDEX IF NOT EXISTS idx_cts_user_rist_last_seen
    ON public.custom_tag_suggestions (user_id, ristorante_id, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_ctsi_suggestion_id
    ON public.custom_tag_suggestion_items (suggestion_id);

CREATE INDEX IF NOT EXISTS idx_ctsi_user_rist_desc_key
    ON public.custom_tag_suggestion_items (user_id, ristorante_id, descrizione_key);

-- ============================================================
-- 4) RLS owner-based + service role full access
-- ============================================================
ALTER TABLE public.custom_tag_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tag_suggestions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.custom_tag_suggestion_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tag_suggestion_items FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS custom_tag_suggestions_select_own ON public.custom_tag_suggestions;
DROP POLICY IF EXISTS custom_tag_suggestions_insert_own ON public.custom_tag_suggestions;
DROP POLICY IF EXISTS custom_tag_suggestions_update_own ON public.custom_tag_suggestions;
DROP POLICY IF EXISTS custom_tag_suggestions_delete_own ON public.custom_tag_suggestions;

CREATE POLICY custom_tag_suggestions_select_own
    ON public.custom_tag_suggestions
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY custom_tag_suggestions_insert_own
    ON public.custom_tag_suggestions
    FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY custom_tag_suggestions_update_own
    ON public.custom_tag_suggestions
    FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY custom_tag_suggestions_delete_own
    ON public.custom_tag_suggestions
    FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS custom_tag_suggestion_items_select_own ON public.custom_tag_suggestion_items;
DROP POLICY IF EXISTS custom_tag_suggestion_items_insert_own ON public.custom_tag_suggestion_items;
DROP POLICY IF EXISTS custom_tag_suggestion_items_update_own ON public.custom_tag_suggestion_items;
DROP POLICY IF EXISTS custom_tag_suggestion_items_delete_own ON public.custom_tag_suggestion_items;

CREATE POLICY custom_tag_suggestion_items_select_own
    ON public.custom_tag_suggestion_items
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY custom_tag_suggestion_items_insert_own
    ON public.custom_tag_suggestion_items
    FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY custom_tag_suggestion_items_update_own
    ON public.custom_tag_suggestion_items
    FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY custom_tag_suggestion_items_delete_own
    ON public.custom_tag_suggestion_items
    FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'custom_tag_suggestions'
          AND policyname = 'Service role full access custom_tag_suggestions'
    ) THEN
        EXECUTE 'CREATE POLICY "Service role full access custom_tag_suggestions"
            ON public.custom_tag_suggestions
            FOR ALL TO service_role USING (true) WITH CHECK (true)';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'custom_tag_suggestion_items'
          AND policyname = 'Service role full access custom_tag_suggestion_items'
    ) THEN
        EXECUTE 'CREATE POLICY "Service role full access custom_tag_suggestion_items"
            ON public.custom_tag_suggestion_items
            FOR ALL TO service_role USING (true) WITH CHECK (true)';
    END IF;
END;
$$;

COMMIT;
