-- ============================================================
-- MIGRATION: Anagrafica dipendenti (Fase 0 ristrutturazione Personale)
-- ============================================================
-- Sostituisce turni_personale.nome (testo libero) con un'entita' dipendente
-- reale (dipendente_id), prerequisito per rinomina pulita, stati-giorno
-- espliciti (riposo/ferie/malattia) e regole ricorrenti.
--
-- Nessuna migrazione dati: verificato sul DB live (30/7/2026) che le uniche
-- righe esistenti in turni_personale (TIME CAFE, CASATI 14, LAND DEI SAPORI)
-- sono dati di prova, autorizzati alla cancellazione dal titolare del
-- prodotto. TRUNCATE esplicito invece di backfill/deduplica.

-- -------------------------------------------------------
-- 1. TABELLA DIPENDENTI
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS dipendenti (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ristorante_id         UUID NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    nome                  TEXT NOT NULL,
    costo_orario_default  NUMERIC(6, 2),
    attivo                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE dipendenti IS 'Anagrafica dipendenti per ristorante. Mai cancellazione hard: disattivare (attivo=false) per chi lascia, i turni storici restano collegati via turni_personale.dipendente_id (ON DELETE RESTRICT).';
COMMENT ON COLUMN dipendenti.costo_orario_default IS 'Prefill nel dialog di inserimento turno. Non e'' fonte di verita'' per il costo storico: ogni riga di turni_personale congela il proprio costo_orario/lordo_mensile.';

-- Unicita' solo tra attivi: un disattivato non blocca la creazione di un
-- omonimo, ma l'endpoint di creazione controlla prima tra i disattivati e
-- propone la riattivazione invece di duplicare silenziosamente.
CREATE UNIQUE INDEX IF NOT EXISTS dipendenti_nome_norm_unico
    ON dipendenti (ristorante_id, lower(trim(nome)))
    WHERE attivo = TRUE;

CREATE INDEX IF NOT EXISTS idx_dipendenti_ristorante ON dipendenti(ristorante_id);
CREATE INDEX IF NOT EXISTS idx_dipendenti_attivo ON dipendenti(ristorante_id, attivo);

ALTER TABLE dipendenti ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "dipendenti_all_service_role" ON dipendenti;
CREATE POLICY "dipendenti_all_service_role" ON dipendenti
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION update_dipendenti_timestamp()
RETURNS TRIGGER
SET search_path = public
AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_dipendenti_updated_at ON dipendenti;
CREATE TRIGGER trg_dipendenti_updated_at
    BEFORE UPDATE ON dipendenti
    FOR EACH ROW EXECUTE FUNCTION update_dipendenti_timestamp();

-- -------------------------------------------------------
-- 2. TURNI_PERSONALE: nome -> dipendente_id
-- -------------------------------------------------------
-- Nessun dato reale da preservare (verificato, vedi header) -> truncate
-- diretto invece di backfill. Rimuove anche il vincolo mensile legacy
-- prima del truncate per evitare conflitti nella ricreazione sotto.
DROP INDEX IF EXISTS turni_personale_mensile_unico;
TRUNCATE TABLE turni_personale;

ALTER TABLE turni_personale
    DROP COLUMN IF EXISTS nome,
    ADD COLUMN dipendente_id UUID NOT NULL REFERENCES dipendenti(id) ON DELETE RESTRICT;

COMMENT ON COLUMN turni_personale.dipendente_id IS 'FK anagrafica dipendenti. ON DELETE RESTRICT: un dipendente con turni storici non puo'' essere cancellato, solo disattivato (dipendenti.attivo=false).';

CREATE INDEX IF NOT EXISTS idx_turni_personale_dipendente ON turni_personale(ristorante_id, dipendente_id);

-- Vincolo mensile riscritto sulla chiave stabile dipendente_id.
CREATE UNIQUE INDEX turni_personale_mensile_unico
    ON turni_personale (ristorante_id, dipendente_id, data_turno)
    WHERE mensile = TRUE;

-- L'indice legacy su nome non ha piu' senso (colonna rimossa).
DROP INDEX IF EXISTS idx_turni_personale_nome;
