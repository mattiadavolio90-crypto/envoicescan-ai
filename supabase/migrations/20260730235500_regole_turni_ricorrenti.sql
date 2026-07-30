-- ============================================================
-- MIGRATION: Regole turni ricorrenti (Fase 3a ristrutturazione Personale)
-- ============================================================
-- Template settimanale per dipendente: "ogni lunedi' turno 9-14" o "ogni
-- domenica riposo". Puro template, mai fonte di verita' sui turni storici
-- -> genera righe in turni_personale solo su richiesta esplicita (Fase 3b),
-- quindi qui FK CASCADE e' accettabile (a differenza di turni_personale.
-- dipendente_id che e' ON DELETE RESTRICT perche' protegge dati storici).

CREATE TABLE IF NOT EXISTS regole_turni_ricorrenti (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ristorante_id     UUID NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    dipendente_id     UUID NOT NULL REFERENCES dipendenti(id) ON DELETE CASCADE,
    giorno_settimana  SMALLINT NOT NULL CHECK (giorno_settimana BETWEEN 0 AND 6),
    tipo_giorno       TEXT NOT NULL CHECK (tipo_giorno IN ('turno', 'riposo')),
    ora_inizio        TEXT,  -- HH:MM, richiesto solo se tipo_giorno='turno'
    ora_fine          TEXT,
    ora_inizio2       TEXT,  -- secondo slot (turno spezzato), opzionale
    ora_fine2         TEXT,
    costo_orario      NUMERIC(6, 2),
    attiva            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT regole_turni_ricorrenti_orari_solo_turno_chk
        CHECK (
            (tipo_giorno = 'turno' AND ora_inizio IS NOT NULL AND ora_fine IS NOT NULL)
            OR (tipo_giorno = 'riposo' AND ora_inizio IS NULL AND ora_fine IS NULL
                AND ora_inizio2 IS NULL AND ora_fine2 IS NULL)
        )
);

COMMENT ON TABLE regole_turni_ricorrenti IS 'Template settimanale per dipendente (es. "ogni lunedi'' turno 9-14"). Puro template: non genera righe in turni_personale finche'' non richiesto esplicitamente (endpoint di generazione, Fase 3b). giorno_settimana: 0=lunedi''...6=domenica.';
COMMENT ON COLUMN regole_turni_ricorrenti.attiva IS 'Regola disattivata = ignorata dalla generazione, ma resta visibile/modificabile. Nessuna cancellazione implicita.';

CREATE INDEX IF NOT EXISTS idx_regole_turni_ricorrenti_ristorante
    ON regole_turni_ricorrenti(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_regole_turni_ricorrenti_dipendente
    ON regole_turni_ricorrenti(ristorante_id, dipendente_id);

ALTER TABLE regole_turni_ricorrenti ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "regole_turni_ricorrenti_all_service_role" ON regole_turni_ricorrenti;
CREATE POLICY "regole_turni_ricorrenti_all_service_role" ON regole_turni_ricorrenti
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION update_regole_turni_ricorrenti_timestamp()
RETURNS TRIGGER
SET search_path = public
AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_regole_turni_ricorrenti_updated_at ON regole_turni_ricorrenti;
CREATE TRIGGER trg_regole_turni_ricorrenti_updated_at
    BEFORE UPDATE ON regole_turni_ricorrenti
    FOR EACH ROW EXECUTE FUNCTION update_regole_turni_ricorrenti_timestamp();
