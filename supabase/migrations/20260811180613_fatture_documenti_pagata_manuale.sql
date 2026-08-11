-- Distingue "pagata mai toccata dall'utente" da "utente ha dichiarato esplicitamente
-- lo stato di pagamento" su fatture_documenti.
--
-- Prima di questa colonna, pagata=false + pagata_at=NULL era lo stato sia di una
-- fattura mai gestita sia di una fattura che l'utente aveva appena "de-pagato" a mano
-- (segna_fattura_pagata scrive sempre pagata_at=NULL quando pagata=false). Per i
-- fornitori con regola di pagamento 'rid', get_documenti_scadenziario forzava
-- pagata=True incondizionatamente, sovrascrivendo qualunque dichiarazione manuale
-- dell'utente e rendendo il bottone "segna come non pagata" inefficace al reload.
--
-- pagata_manuale_at viene valorizzato SOLO dalla scrittura esplicita dell'utente
-- (segna_fattura_pagata), mai dall'automatismo RID: la lettura può quindi far
-- vincere il dato esplicito sull'inferenza quando presente.

ALTER TABLE public.fatture_documenti
    ADD COLUMN IF NOT EXISTS pagata_manuale_at TIMESTAMPTZ;
