DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'margini_mensili'
          AND column_name = 'fatturato_bar'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'margini_mensili'
          AND column_name = 'fatturato_beverage'
    ) THEN
        ALTER TABLE public.margini_mensili
        RENAME COLUMN fatturato_bar TO fatturato_beverage;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'margini_mensili'
          AND column_name = 'fatturato_beverage'
    ) THEN
        ALTER TABLE public.margini_mensili
        ADD COLUMN fatturato_beverage NUMERIC(12,2) DEFAULT 0;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'margini_mensili'
          AND column_name = 'fatturato_bar'
    ) THEN
        EXECUTE '
            UPDATE public.margini_mensili
            SET fatturato_beverage = CASE
                WHEN COALESCE(fatturato_beverage, 0) = 0 THEN COALESCE(fatturato_bar, 0)
                ELSE fatturato_beverage
            END
        ';

        ALTER TABLE public.margini_mensili
        DROP COLUMN fatturato_bar;
    END IF;
END
$$;

COMMENT ON COLUMN public.margini_mensili.fatturato_beverage IS 'Fatturato netto attribuito al centro BEVERAGE';