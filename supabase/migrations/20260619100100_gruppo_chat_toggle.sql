-- Toggle on/off della chat di catena nel «Configura assistente» (per account).
--
-- La chat di gruppo si accende automaticamente quando il pool AI è > 0 (somma dei
-- piani delle sedi). Questo flag permette di spegnerla manualmente anche con pool
-- positivo — parità col toggle "Chat AI in Home" del singolo PV.
-- Default false (chat accesa). Idempotente.

ALTER TABLE public.gruppo_assistant_config
    ADD COLUMN IF NOT EXISTS chat_disabilitata boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.gruppo_assistant_config.chat_disabilitata IS
    'true = chat assistente di catena spenta dal Configura assistente (anche con pool > 0).';
