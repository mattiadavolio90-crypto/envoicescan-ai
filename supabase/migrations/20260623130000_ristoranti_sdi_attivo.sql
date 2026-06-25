-- Flag esplicito "ricezione SDI automatica attiva" per sede.
--
-- Perche': il briefing decideva il canale di ricezione fatture (SDI vs manuale)
-- dalla sola presenza della P.IVA -> tutti trattati come "flusso automatico",
-- ma in realta' NESSUN cliente ha (ancora) la ricezione SDI attiva: caricano a
-- mano. Risultato: messaggio fuorviante "verifica il flusso automatico" a chi un
-- flusso non ce l'ha. piva_ristoranti non aiuta (contiene tutte le sedi, serve
-- solo a smistare eventuali fatture) e source_origin non basta nei primi giorni
-- dopo l'attivazione (prima che arrivi il primo documento invoicetronic).
--
-- Soluzione: un flag esplicito che l'admin accende quando attiva davvero il
-- servizio per quel PV (a breve: 3 SUSHILAND + 2 OFFSIDE). Default false = stato
-- attuale reale (tutti manuali), nessun falso allarme.

ALTER TABLE ristoranti
  ADD COLUMN IF NOT EXISTS sdi_attivo boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS sdi_attivo_dal date;

COMMENT ON COLUMN ristoranti.sdi_attivo IS
  'True = la sede riceve fatture in automatico via SDI/Invoicetronic. Lo accende l''admin all''attivazione del servizio. Decide il canale del briefing fatture-mancanti (sdi -> "verifica flusso", false -> "carica a mano").';
COMMENT ON COLUMN ristoranti.sdi_attivo_dal IS
  'Data di attivazione della ricezione SDI (informativa).';
