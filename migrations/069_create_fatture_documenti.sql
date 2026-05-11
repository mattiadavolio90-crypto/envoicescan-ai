-- Migration 069: Tabella fatture_documenti per gestione scadenze e pagamenti
--
-- Contesto:
-- La nuova pagina "Gestione Fatture e Notifiche" introduce:
--   1. Scadenziario con override scadenza
--   2. Flag "pagato" e tracking pagamenti
--   3. Regole fornitore per calcolo scadenza automatico
--   4. Tracking source scadenza (override/fornitore/xml/none)
--
-- Tabella fatture_documenti è un "metadata header" per fattura (una riga per file_origine).
-- Contiene i dati di intestazione della fattura, aggregati dalle righe di fatture:
--   - Intestazione XML (tipo_documento, totale, data)
--   - Scadenza XML (da DatiPagamento se presente)
--   - Scadenza calcolata (override + regola fornitore + xml + default)
--   - Flag pagamento
--
-- Relazione con tabelle esistenti:
--   - Un record fatture_documenti corrisponde a 1..N record fatture (stesso file_origine)
--   - Chiave univoca: (user_id, ristorante_id, file_origine)
--   - Soft-delete sincronizzato: quando fatture.deleted_at cambia, propagare su fatture_documenti

-- ============================================================================
-- TABLE: fatture_documenti
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.fatture_documenti (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Chiave utente/ristorante/documento
    user_id UUID NOT NULL,
    ristorante_id UUID NOT NULL,
    file_origine TEXT NOT NULL,
    
    -- Metadati fornitori (intestazione XML)
    fornitore TEXT,
    piva_fornitore TEXT,  -- 11 cifre normalizzate (CedentePrestatore.IdFiscaleIVA.IdCodice)
    numero_documento TEXT,
    
    -- Date fattura (aggregate da fatture)
    data_documento DATE,
    data_competenza DATE,
    tipo_documento VARCHAR(4) NOT NULL DEFAULT 'TD01',
    
    -- Totali (aggregate da fatture)
    totale_documento NUMERIC(12, 2),
    totale_imponibile NUMERIC(12, 2),
    totale_iva NUMERIC(12, 2),
    
    -- Compensazione (nota di credito vs fattura normale)
    segno_compensazione SMALLINT NOT NULL DEFAULT 1,
    
    -- Scadenza da parsing XML DatiPagamento (se presente)
    scadenza_xml DATE,
    giorni_termini_xml INT,
    
    -- Scadenza override (utente clicca "modifica scadenza")
    scadenza_override DATE,
    
    -- Scadenza effettiva (calcolata: priorità override > regola_fornitore > xml > none)
    scadenza_effettiva DATE,
    
    -- Source della scadenza_effettiva per tracciamento
    scadenza_source TEXT NOT NULL DEFAULT 'none',
        CHECK (scadenza_source IN ('override', 'fornitore', 'xml', 'none')),
    
    -- Pagamento
    pagata BOOLEAN NOT NULL DEFAULT FALSE,
    pagata_at TIMESTAMPTZ,
    note_pagamento TEXT,
    
    -- Provenienza documento
    source_origin TEXT NOT NULL DEFAULT 'manual',
        CHECK (source_origin IN ('manual', 'invoicetronic')),
    
    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,  -- Soft delete sincronizzato con fatture
    
    -- UNIQUE tripla (user_id, ristorante_id, file_origine)
    UNIQUE (user_id, ristorante_id, file_origine),
    
    -- Check: almeno una scadenza definita se necessario
    CHECK (scadenza_xml IS NULL OR scadenza_xml >= data_documento OR data_documento IS NULL)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_fat_doc_user_rist_deleted_scadenza
    ON public.fatture_documenti (user_id, ristorante_id, deleted_at, scadenza_effettiva)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_fat_doc_user_rist_pagata_scadenza
    ON public.fatture_documenti (user_id, ristorante_id, pagata, scadenza_effettiva)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_fat_doc_user_rist_piva
    ON public.fatture_documenti (user_id, ristorante_id, piva_fornitore)
    WHERE piva_fornitore IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_fat_doc_user_rist_fornitore
    ON public.fatture_documenti (user_id, ristorante_id, fornitore)
    WHERE fornitore IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_fat_doc_scadenza_source
    ON public.fatture_documenti (user_id, ristorante_id, scadenza_source)
    WHERE deleted_at IS NULL;

-- ============================================================================
-- RLS
-- ============================================================================

ALTER TABLE public.fatture_documenti ENABLE ROW LEVEL SECURITY;

-- NO DEFAULT POLICY: accesso solo via service_role (come fatture)
-- La verifica user_id/ristorante_id avviene nel service layer Python
REVOKE ALL ON public.fatture_documenti FROM public, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fatture_documenti TO service_role;

-- ============================================================================
-- CACHE VERSION KEYS (per invalidazione cross-process)
-- ============================================================================

INSERT INTO public.cache_version (key, version)
VALUES ('fatture_documenti', 1)
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- TRIGGER: Bump cache version su fatture_documenti (nuove/modificate/cancellate)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_bump_cache_version_fatture_documenti()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE public.cache_version
        SET version = version + 1,
            updated_at = now()
    WHERE key = 'fatture_documenti';
    RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_bump_cache_version_fatture_documenti() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_bump_cache_version_fatture_documenti() TO service_role;

DROP TRIGGER IF EXISTS trg_bump_cache_fat_doc ON public.fatture_documenti;
CREATE TRIGGER trg_bump_cache_fat_doc
    AFTER INSERT OR UPDATE OR DELETE ON public.fatture_documenti
    FOR EACH STATEMENT EXECUTE FUNCTION public.fn_bump_cache_version_fatture_documenti();

-- ============================================================================
-- TRIGGER: Propaga deleted_at da fatture su fatture_documenti
-- ============================================================================
-- Quando un utente elimina/ripristina una fattura (soft-delete via elimina_fattura_completa),
-- propagare il cambio deleted_at su fatture_documenti per la tripla (user_id, ristorante_id, file_origine).

CREATE OR REPLACE FUNCTION public.fn_propagate_deleted_at_fatture()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Se deleted_at e' cambiato su fatture, aggiornare fatture_documenti
    IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
        UPDATE public.fatture_documenti
            SET deleted_at = NEW.deleted_at,
                updated_at = now()
        WHERE user_id = NEW.user_id
          AND ristorante_id = NEW.ristorante_id
          AND file_origine = NEW.file_origine;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_propagate_deleted_at_fatture() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_propagate_deleted_at_fatture() TO service_role;

DROP TRIGGER IF EXISTS trg_propagate_deleted_at_fatture ON public.fatture;
CREATE TRIGGER trg_propagate_deleted_at_fatture
    AFTER UPDATE OF deleted_at ON public.fatture
    FOR EACH ROW EXECUTE FUNCTION public.fn_propagate_deleted_at_fatture();

-- ============================================================================
-- COMMENT
-- ============================================================================

COMMENT ON TABLE public.fatture_documenti IS
    'Metadati header per fatture (una riga per file_origine). Contiene '
    'intestazione XML, scadenze (xml/override/calcolata) e pagamento. '
    'Soft-delete sincronizzato con tabella fatture via trigger.';

COMMENT ON COLUMN public.fatture_documenti.scadenza_source IS
    'Source della scadenza_effettiva: '
    '''override'' = utente ha modificato manualmente, '
    '''fornitore'' = calcolata da regola fornitore configurata, '
    '''xml'' = estratta da DatiPagamento XML, '
    '''none'' = nessuna scadenza disponibile (default 30gg se necessario lato UI)';

COMMENT ON COLUMN public.fatture_documenti.segno_compensazione IS
    'Moltiplicatore segno: -1 per note di credito (TD04), +1 per fatture normali';

COMMENT ON COLUMN public.fatture_documenti.source_origin IS
    '''manual'' = caricata da utente (manual_upload), '
    '''invoicetronic'' = ricevuta da edge function Invoicetronic';
