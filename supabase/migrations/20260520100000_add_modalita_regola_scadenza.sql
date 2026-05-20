-- Migration 20260520100000: Aggiunge colonna `modalita` a fornitori_pagamenti_config
--
-- Contesto:
-- Sostituisce il sistema "giorni_pagamento + data_riferimento" con una modalità
-- discreta a scelta tra 7 opzioni predefinite, allineate alla realtà dei pagamenti
-- in ambito ristorativo (RID, 30/60/90 gg, fine mese successivo, ecc.).
--
-- Valori modalita:
--   'rid'      → Automatico/RID: fattura già pagata alla ricezione
--   '30gg'     → 30 giorni dalla data fattura
--   '60gg'     → 60 giorni dalla data fattura
--   '90gg'     → 90 giorni dalla data fattura
--   '30gg_fm'  → Fine del mese successivo alla data fattura
--   '60gg_fm'  → Fine del 2° mese successivo
--   '90gg_fm'  → Fine del 3° mese successivo
--
-- Backward-compat: le righe esistenti senza modalita continuano a usare
-- giorni_pagamento + data_riferimento (logica legacy nel service layer).

ALTER TABLE public.fornitori_pagamenti_config
    ADD COLUMN IF NOT EXISTS modalita TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fpc_modalita_check'
          AND table_name = 'fornitori_pagamenti_config'
    ) THEN
        ALTER TABLE public.fornitori_pagamenti_config
            ADD CONSTRAINT fpc_modalita_check
            CHECK (
                modalita IS NULL
                OR modalita IN ('rid', '30gg', '60gg', '90gg', '30gg_fm', '60gg_fm', '90gg_fm')
            );
    END IF;
END $$;
