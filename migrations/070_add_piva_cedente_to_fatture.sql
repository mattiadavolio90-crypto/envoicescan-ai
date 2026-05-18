-- Migration 069.5: Aggiunge colonna piva_cedente a tabella fatture
--
-- Contesto:
-- La nuova pagina "Gestione Fatture e Notifiche" (Step 2) richiede di salvare
-- la P.IVA del cedente (fornitore che emette la fattura) a livello di riga.
-- Questa colonna viene estratta dal parsing XML (CedentePrestatore.IdFiscaleIVA.IdCodice)
-- e usata da migration 071 per popolare fatture_documenti.piva_cedente.
--
-- Per righe storiche, il valore sarà NULL; il backfill 071 le propagherà come NULL.
-- Il matching con fornitori_pagamenti_config userà fornitore_norm come fallback.

ALTER TABLE public.fatture 
ADD COLUMN IF NOT EXISTS piva_cedente TEXT DEFAULT NULL;

COMMENT ON COLUMN public.fatture.piva_cedente IS
    'P.IVA del cedente (fornitore che emette la fattura). '
    'Estratto da CedentePrestatore.IdFiscaleIVA.IdCodice nel parsing XML. '
    'Usato per matching con regole fornitore in fatture_documenti.';
