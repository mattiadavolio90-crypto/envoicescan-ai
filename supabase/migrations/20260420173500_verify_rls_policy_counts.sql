DO $$
DECLARE
    v_fatture INT;
    v_ristoranti INT;
BEGIN
    SELECT COUNT(*) INTO v_fatture
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'fatture';

    SELECT COUNT(*) INTO v_ristoranti
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'ristoranti';

    RAISE NOTICE 'fatture policy count = %', v_fatture;
    RAISE NOTICE 'ristoranti policy count = %', v_ristoranti;

    IF v_fatture <> 4 THEN
        RAISE EXCEPTION 'Verification failed: fatture has % policies, expected 4', v_fatture;
    END IF;

    IF v_ristoranti <> 2 THEN
        RAISE EXCEPTION 'Verification failed: ristoranti has % policies, expected 2', v_ristoranti;
    END IF;
END
$$;