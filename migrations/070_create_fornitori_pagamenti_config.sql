-- Migration 070: Tabella fornitori_pagamenti_config per regole scadenza automatiche
--
-- Contesto:
-- Utente configurare regole di pagamento per singoli fornitori (per ristorante).
-- Regola: dato un fornitore (identificato da piva_fornitore o fornitore_norm),
-- calcola scadenza automatica = data_riferimento + giorni_pagamento.
--
-- Es. "FORNITORE: FASTWEB IVA 12345678901 → pagamento a 30gg fine mese"
--
-- Una fattura viene matchata alla regola e la sua scadenza_effettiva calcolata
-- da calcola_scadenza_effettiva() nel service layer.
--
-- Relazione con fatture_documenti: tripla (user_id, ristorante_id, piva_fornitore)
-- per lookup della regola durante upsert documento.

-- ============================================================================
-- TABLE: fornitori_pagamenti_config
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.fornitori_pagamenti_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Chiave: utente + ristorante
    user_id UUID NOT NULL,
    ristorante_id UUID NOT NULL,
    
    -- Identificazione fornitore (almeno uno valorizzato)
    piva_fornitore TEXT,  -- 11 cifre normalizzate (CedentePrestatore), preferito
    fornitore_norm TEXT,  -- normalizza_stringa(fornitore), fallback se piva NULL
    
    -- Regola pagamento
    giorni_pagamento INT NOT NULL,
        CHECK (giorni_pagamento BETWEEN 0 AND 365),
    
    data_riferimento TEXT NOT NULL DEFAULT 'data_documento',
        CHECK (data_riferimento IN ('data_documento', 'fine_mese', 'fine_mese_successivo')),
    
    -- Attivazione e metadati
    attiva BOOLEAN NOT NULL DEFAULT TRUE,
    note TEXT,
    
    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- UNIQUE parziali (uno tra piva_fornitore e fornitore_norm deve essere valorizzato)
    CHECK (piva_fornitore IS NOT NULL OR fornitore_norm IS NOT NULL)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Indice primario per lookup regola dato piva_fornitore (preferito)
CREATE UNIQUE INDEX IF NOT EXISTS idx_frn_pag_cfg_piva_unique
    ON public.fornitori_pagamenti_config (user_id, ristorante_id, piva_fornitore)
    WHERE piva_fornitore IS NOT NULL;

-- Indice secondario per lookup regola dato fornitore_norm (fallback)
CREATE UNIQUE INDEX IF NOT EXISTS idx_frn_pag_cfg_norm_unique
    ON public.fornitori_pagamenti_config (user_id, ristorante_id, fornitore_norm)
    WHERE piva_fornitore IS NULL AND fornitore_norm IS NOT NULL;

-- Indice per filtrare regole attive per ristorante
CREATE INDEX IF NOT EXISTS idx_frn_pag_cfg_user_rist_attiva
    ON public.fornitori_pagamenti_config (user_id, ristorante_id, attiva);

-- ============================================================================
-- RLS
-- ============================================================================

ALTER TABLE public.fornitori_pagamenti_config ENABLE ROW LEVEL SECURITY;

-- NO DEFAULT POLICY: accesso solo via service_role (come fatture)
-- La verifica user_id/ristorante_id avviene nel service layer Python
REVOKE ALL ON public.fornitori_pagamenti_config FROM public, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fornitori_pagamenti_config TO service_role;

-- ============================================================================
-- CACHE VERSION KEYS (per invalidazione cross-process)
-- ============================================================================

INSERT INTO public.cache_version (key, version)
VALUES ('fornitori_pagamenti_config', 1)
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- TRIGGER: Bump cache version su fornitori_pagamenti_config
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_bump_cache_version_fornitori_config()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE public.cache_version
        SET version = version + 1,
            updated_at = now()
    WHERE key = 'fornitori_pagamenti_config';
    RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_bump_cache_version_fornitori_config() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_bump_cache_version_fornitori_config() TO service_role;

DROP TRIGGER IF EXISTS trg_bump_cache_frn_cfg ON public.fornitori_pagamenti_config;
CREATE TRIGGER trg_bump_cache_frn_cfg
    AFTER INSERT OR UPDATE OR DELETE ON public.fornitori_pagamenti_config
    FOR EACH STATEMENT EXECUTE FUNCTION public.fn_bump_cache_version_fornitori_config();

-- ============================================================================
-- COMMENT
-- ============================================================================

COMMENT ON TABLE public.fornitori_pagamenti_config IS
    'Regole di pagamento automatiche per singoli fornitori per ristorante. '
    'Calcola scadenza = data_riferimento + giorni_pagamento. '
    'Match via (user_id, ristorante_id, piva_fornitore OR fornitore_norm).';

COMMENT ON COLUMN public.fornitori_pagamenti_config.piva_fornitore IS
    'P.IVA fornitore (11 cifre normalizzate, preferito). '
    'Se valorizzato, match ha priorita su fornitore_norm.';

COMMENT ON COLUMN public.fornitori_pagamenti_config.fornitore_norm IS
    'Nome fornitore normalizzato (fallback se piva_fornitore NULL).';

COMMENT ON COLUMN public.fornitori_pagamenti_config.data_riferimento IS
    '''data_documento'' = scadenza = data_documento + giorni_pagamento; '
    '''fine_mese'' = scadenza = ultimo giorno mese + giorni_pagamento; '
    '''fine_mese_successivo'' = scadenza = ultimo giorno mese successivo + giorni_pagamento';

COMMENT ON COLUMN public.fornitori_pagamenti_config.giorni_pagamento IS
    'Numero giorni di pagamento (0..365). Es. 30 = 30 giorni dalla data_riferimento.';

COMMENT ON COLUMN public.fornitori_pagamenti_config.attiva IS
    'Se FALSE, regola ignorata. Usare per disattivare temporaneamente senza eliminare.';
