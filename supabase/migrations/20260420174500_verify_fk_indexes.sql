DO $$
DECLARE
    v_ai_usage_events_user_id BOOLEAN;
    v_piva_ristoranti_ristorante_id BOOLEAN;
    v_ricette_ristorante_id BOOLEAN;
    v_users_ultimo_ristorante_id BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_ai_usage_events_user_id'
    ) INTO v_ai_usage_events_user_id;

    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_piva_ristoranti_ristorante_id'
    ) INTO v_piva_ristoranti_ristorante_id;

    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_ricette_ristorante_id'
    ) INTO v_ricette_ristorante_id;

    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_users_ultimo_ristorante_id'
    ) INTO v_users_ultimo_ristorante_id;

    RAISE NOTICE 'idx_ai_usage_events_user_id = %', v_ai_usage_events_user_id;
    RAISE NOTICE 'idx_piva_ristoranti_ristorante_id = %', v_piva_ristoranti_ristorante_id;
    RAISE NOTICE 'idx_ricette_ristorante_id = %', v_ricette_ristorante_id;
    RAISE NOTICE 'idx_users_ultimo_ristorante_id = %', v_users_ultimo_ristorante_id;

    IF NOT v_ai_usage_events_user_id OR NOT v_piva_ristoranti_ristorante_id OR NOT v_ricette_ristorante_id OR NOT v_users_ultimo_ristorante_id THEN
        RAISE EXCEPTION 'Verification failed: one or more required indexes are missing';
    END IF;
END
$$;