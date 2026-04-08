-- ============================================================
-- MIGRATION 051: Ledger eventi costi AI + RPC reporting
-- ============================================================

CREATE TABLE IF NOT EXISTS public.ai_usage_events (
    id BIGSERIAL PRIMARY KEY,
    ristorante_id UUID NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    user_id UUID NULL REFERENCES public.users(id) ON DELETE SET NULL,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('pdf', 'categorization', 'other')),
    model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    input_cost DECIMAL(12,6) NOT NULL DEFAULT 0,
    output_cost DECIMAL(12,6) NOT NULL DEFAULT 0,
    total_cost DECIMAL(12,6) NOT NULL DEFAULT 0,
    item_count INT NOT NULL DEFAULT 1,
    source_file TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_ristorante_created_at
    ON public.ai_usage_events (ristorante_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_created_at
    ON public.ai_usage_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_operation_type
    ON public.ai_usage_events (operation_type);

COMMENT ON TABLE public.ai_usage_events IS 'Ledger eventi AI: un record per chiamata AI con costo, token e metadati operativi';

ALTER TABLE public.ai_usage_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for authenticated" ON public.ai_usage_events;
CREATE POLICY "Allow all for authenticated"
ON public.ai_usage_events
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

GRANT ALL ON public.ai_usage_events TO anon;
GRANT ALL ON public.ai_usage_events TO authenticated;
GRANT ALL ON public.ai_usage_events TO service_role;

DO $$ BEGIN
    GRANT USAGE, SELECT ON SEQUENCE ai_usage_events_id_seq TO anon;
    GRANT USAGE, SELECT ON SEQUENCE ai_usage_events_id_seq TO authenticated;
    GRANT USAGE, SELECT ON SEQUENCE ai_usage_events_id_seq TO service_role;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'Sequence ai_usage_events_id_seq non trovata, skip grant';
END $$;

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
AS $$
DECLARE
    v_event_id BIGINT;
    v_total_tokens INT;
BEGIN
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
    ) VALUES (
        p_ristorante_id,
        p_user_id,
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
    SET
        ai_cost_total = COALESCE(ai_cost_total, 0) + COALESCE(p_total_cost, 0),
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

DROP FUNCTION IF EXISTS public.increment_ai_cost(UUID, DECIMAL, INT, TEXT);
DROP FUNCTION IF EXISTS public.increment_ai_cost(UUID, DECIMAL, INT);
CREATE OR REPLACE FUNCTION public.increment_ai_cost(
    p_ristorante_id UUID,
    p_cost DECIMAL,
    p_tokens INT DEFAULT 0,
    p_operation_type TEXT DEFAULT 'pdf'
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
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
        p_user_id := NULL,
        p_source_file := NULL,
        p_item_count := 1,
        p_metadata := jsonb_build_object('legacy_tokens', COALESCE(p_tokens, 0), 'tracking_mode', 'legacy_increment')
    );
END;
$$;

DROP FUNCTION IF EXISTS public.get_ai_costs_summary(INTEGER);
DROP FUNCTION IF EXISTS public.get_ai_costs_summary();
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
AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT e.*
        FROM public.ai_usage_events e
        WHERE p_days IS NULL OR e.created_at >= NOW() - make_interval(days => p_days)
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
        FROM filtered e
        GROUP BY e.ristorante_id
    )
    SELECT
        r.id,
        r.nome_ristorante,
        r.ragione_sociale,
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
    FROM public.ristoranti r
    LEFT JOIN agg a ON a.ristorante_id = r.id
    WHERE r.attivo = true
      AND COALESCE(a.total_cost, 0) > 0
    ORDER BY COALESCE(a.total_cost, 0) DESC, r.nome_ristorante;
END;
$$;

DROP FUNCTION IF EXISTS public.get_ai_costs_timeseries(INTEGER);
DROP FUNCTION IF EXISTS public.get_ai_costs_timeseries();
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
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.created_at::DATE AS usage_date,
        SUM(e.total_cost)::DECIMAL(12,6) AS total_cost,
        SUM(e.total_cost) FILTER (WHERE e.operation_type = 'pdf')::DECIMAL(12,6) AS pdf_cost,
        SUM(e.total_cost) FILTER (WHERE e.operation_type = 'categorization')::DECIMAL(12,6) AS categorization_cost,
        COUNT(*)::INT AS operations_count
    FROM public.ai_usage_events e
    WHERE e.created_at >= NOW() - make_interval(days => COALESCE(p_days, 30))
    GROUP BY e.created_at::DATE
    ORDER BY usage_date;
END;
$$;

DROP FUNCTION IF EXISTS public.get_ai_recent_operations(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS public.get_ai_recent_operations();
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
    FROM public.ai_usage_events e
    JOIN public.ristoranti r ON r.id = e.ristorante_id
    WHERE e.created_at >= NOW() - make_interval(days => COALESCE(p_days, 30))
    ORDER BY e.created_at DESC
    LIMIT COALESCE(p_limit, 100);
END;
$$;

GRANT EXECUTE ON FUNCTION public.track_ai_usage_event(UUID, TEXT, TEXT, INT, INT, DECIMAL, DECIMAL, DECIMAL, UUID, TEXT, INT, JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION public.increment_ai_cost(UUID, DECIMAL, INT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_summary(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_ai_costs_timeseries(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_ai_recent_operations(INTEGER, INTEGER) TO authenticated;