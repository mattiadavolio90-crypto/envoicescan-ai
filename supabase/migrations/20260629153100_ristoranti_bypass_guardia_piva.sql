-- Flag per ambienti di TEST a caricamento manuale: quando true, l'upload manuale
-- NON applica la guardia P.IVA (non scarta le fatture intestate a una P.IVA che
-- non corrisponde alla sede) e dirotta tutto sulla sede stessa. Default false:
-- i clienti reali restano protetti dalla guardia (anti caricamento su sede
-- sbagliata). Si accende SOLO sulle sedi di test.
ALTER TABLE public.ristoranti
  ADD COLUMN IF NOT EXISTS bypass_guardia_piva boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.ristoranti.bypass_guardia_piva IS
  'Ambiente test: se true, l''upload manuale ignora la guardia P.IVA e accetta qualsiasi fattura sulla sede. Default false (clienti reali protetti).';
