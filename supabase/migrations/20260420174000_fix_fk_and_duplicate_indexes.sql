-- ============================================================
-- MIGRATION 062: Add missing FK indexes + drop confirmed duplicate legacy index
-- Scope: structural only, no data changes
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1) Foreign keys without dedicated covering index
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ai_usage_events_user_id
    ON public.ai_usage_events(user_id);

CREATE INDEX IF NOT EXISTS idx_piva_ristoranti_ristorante_id
    ON public.piva_ristoranti(ristorante_id);

CREATE INDEX IF NOT EXISTS idx_ricette_ristorante_id
    ON public.ricette(ristorante_id);

CREATE INDEX IF NOT EXISTS idx_users_ultimo_ristorante_id
    ON public.users(ultimo_ristorante_id);

-- ------------------------------------------------------------
-- 2) Confirmed duplicate legacy index on prodotti_master
--    Keep the canonical index from migration 005, drop the old alias if present.
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_prodotti_master_descrizione
    ON public.prodotti_master(descrizione);

DROP INDEX IF EXISTS public.idx_prodotti_desc;

COMMIT;
