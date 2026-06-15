-- ============================================================
-- MIGRATION: Turni personale — inserimento mensile aggregato
-- ============================================================
-- Il cliente, invece di inserire i turni giorno per giorno, puo' leggere la
-- busta paga e inserire una sola riga col totale del mese per dipendente:
-- lordo, ore totali, importo extra, ore extra.
--
-- Regola di dominio (esclusivita' per dipendente/mese):
--   un dipendente in un dato mese e' GIORNALIERO (N righe mensile=false) OPPURE
--   MENSILE (1 riga mensile=true). Mai entrambi. La guardia e' applicata lato
--   worker (POST giornaliero / POST mensile si rifiutano a vicenda).
--
-- Righe mensili: data_turno = 1 del mese, ora_inizio/ora_fine placeholder
-- ('00:00'), ore prese da ore_dichiarate (non calcolate dagli orari).

ALTER TABLE turni_personale
    ADD COLUMN IF NOT EXISTS mensile        BOOLEAN        NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ore_dichiarate NUMERIC(7, 2),
    ADD COLUMN IF NOT EXISTS lordo_mensile  NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS importo_extra  NUMERIC(10, 2);

COMMENT ON COLUMN turni_personale.mensile IS 'TRUE = riga aggregata mensile (totali da busta paga), non un turno giornaliero. Esclusiva per dipendente/mese.';
COMMENT ON COLUMN turni_personale.ore_dichiarate IS 'Monte ore totali del mese per le righe mensili. NULL sulle righe giornaliere (le ore si calcolano dagli orari).';
COMMENT ON COLUMN turni_personale.lordo_mensile IS 'Importo lordo totale del mese da busta paga (EUR), incl. quota ordinaria. Solo righe mensili.';
COMMENT ON COLUMN turni_personale.importo_extra IS 'Importo straordinario del mese (EUR) da busta paga. Solo righe mensili.';

-- Un dipendente/mese puo' avere al massimo UNA riga mensile (no doppioni).
CREATE UNIQUE INDEX IF NOT EXISTS turni_personale_mensile_unico
    ON turni_personale (ristorante_id, nome, data_turno)
    WHERE mensile = TRUE;
