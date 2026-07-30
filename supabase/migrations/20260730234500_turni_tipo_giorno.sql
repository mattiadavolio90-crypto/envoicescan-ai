-- ============================================================
-- MIGRATION: Stati giorno espliciti (Fase 2a ristrutturazione Personale)
-- ============================================================
-- Introduce tipo_giorno per marcare esplicitamente riposo/ferie/malattia,
-- invece di dedurli dall'assenza di righe (stesso principio anti-pattern
-- gia' eliminato per "Da Classificare" nelle fatture).
--
-- importo_a_carico e' un dato SOLO registrato dall'utente, mai stimato o
-- calcolato automaticamente: NULL significa "non tracciato", non "zero".

ALTER TABLE turni_personale
    ADD COLUMN tipo_giorno TEXT NOT NULL DEFAULT 'turno'
        CHECK (tipo_giorno IN ('turno', 'riposo', 'ferie', 'malattia')),
    ADD COLUMN importo_a_carico NUMERIC(10, 2);

ALTER TABLE turni_personale
    ADD CONSTRAINT turni_personale_importo_a_carico_solo_assenze_chk
    CHECK (importo_a_carico IS NULL OR tipo_giorno IN ('ferie', 'malattia'));

COMMENT ON COLUMN turni_personale.tipo_giorno IS 'Stato esplicito del giorno: turno (default, lavorato) | riposo | ferie | malattia. Mai dedotto dal vuoto.';
COMMENT ON COLUMN turni_personale.importo_a_carico IS 'Costo extra registrato manualmente per ferie/malattia (es. quota TFR, indennita'). NULL = non tracciato, mai stimato automaticamente.';

CREATE INDEX IF NOT EXISTS idx_turni_personale_tipo_giorno
    ON turni_personale (ristorante_id, dipendente_id, tipo_giorno)
    WHERE tipo_giorno <> 'turno';
