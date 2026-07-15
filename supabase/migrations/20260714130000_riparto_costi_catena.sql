-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: ripartizione costi di gruppo sulle catene (modello dati)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: PIANO_OPERATIVO_RIPARTIZIONE_COSTI_CATENA.md (Fase 2) + decisione
-- PIANO_RIPARTIZIONE_COSTI_CATENA.md (1/7, Proposta 2).
--
-- Un costo di struttura (commercialista, auto aziendale, ecc.) intestato alla sede
-- legale di una catena serve TUTTO il gruppo. Oggi entrerebbe intero nel MOL della
-- sede intestataria → MOL falsato. Questo modello lo divide in quote per sede.
--
-- Principio non negoziabile: LA FATTURA RESTA SACRA. Non si spezzano/riscrivono le
-- righe della fattura elettronica (integrità fiscale). Le quote vivono in tabelle
-- separate a livello ACCOUNT (non sede) e alimentano il MOL via colonne dedicate su
-- margini_mensili (vedi migration successiva del motore).
--
-- Tabelle:
--   riparto_costi_catena        — 1 riga per costo da ripartire (da fattura o manuale)
--   riparto_costi_catena_quote  — N righe: la quota di ogni sede per quel costo
--   riparto_regole_fornitore    — memoria "fai sempre così per questo fornitore"
--
-- + flag fatture.ripartita_su_gruppo per l'anti-doppio-conteggio (le righe di una
--   fattura ripartita vengono escluse dal costo automatico della sede intestataria,
--   così il costo esce dalla porta automatica e rientra distribuito dalle quote).
--
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. riparto_costi_catena — il costo da ripartire
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.riparto_costi_catena (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL,               -- account (contenitore catena)
    origine        TEXT NOT NULL DEFAULT 'fattura'
                       CHECK (origine IN ('fattura', 'manuale')),
    file_origine   TEXT,                         -- se da fattura; NULL se voce manuale
    fornitore      TEXT,                         -- P.IVA/nome cedente (per regola fornitore)
    descrizione    TEXT NOT NULL,                -- "Commercialista giugno", "Stipendi ufficio"
    importo_totale NUMERIC(12,2) NOT NULL CHECK (importo_totale >= 0),
    tipo           TEXT NOT NULL DEFAULT 'generale'
                       CHECK (tipo IN ('generale', 'fb')),  -- quale cella del MOL alimenta
    anno           INTEGER NOT NULL,
    mese           INTEGER NOT NULL CHECK (mese >= 1 AND mese <= 12),
    regola         TEXT NOT NULL DEFAULT 'equa'
                       CHECK (regola IN ('equa', 'percentuali')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Una fattura si ripartisce una volta sola: no doppioni sullo stesso documento.
    -- (le voci manuali hanno file_origine NULL → il vincolo non le tocca)
    CONSTRAINT uq_riparto_file_origine UNIQUE (user_id, file_origine)
);

COMMENT ON TABLE public.riparto_costi_catena IS
    'Costi di struttura di una catena da ripartire fra i punti vendita. Uno per '
    'costo (fattura o voce manuale). Le quote per sede stanno in '
    'riparto_costi_catena_quote. Alimenta il MOL via margini_mensili (motore SQL).';

CREATE INDEX IF NOT EXISTS idx_riparto_user_periodo
    ON public.riparto_costi_catena (user_id, anno, mese);

CREATE INDEX IF NOT EXISTS idx_riparto_file_origine
    ON public.riparto_costi_catena (user_id, file_origine)
    WHERE file_origine IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. riparto_costi_catena_quote — la quota di ogni sede
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.riparto_costi_catena_quote (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    riparto_id    UUID NOT NULL
                      REFERENCES public.riparto_costi_catena(id) ON DELETE CASCADE,
    ristorante_id UUID NOT NULL,
    quota_perc    NUMERIC(6,3) NOT NULL CHECK (quota_perc >= 0 AND quota_perc <= 100),
    quota_importo NUMERIC(12,2) NOT NULL CHECK (quota_importo >= 0),

    -- Una sede compare una volta sola per costo.
    CONSTRAINT uq_riparto_quota_sede UNIQUE (riparto_id, ristorante_id)
);

COMMENT ON TABLE public.riparto_costi_catena_quote IS
    'Quota (% e €) di una sede per un costo di gruppo. La somma delle quota_importo '
    'di un riparto deve pareggiare importo_totale (garantito a livello applicativo/RPC).';

CREATE INDEX IF NOT EXISTS idx_riparto_quote_riparto
    ON public.riparto_costi_catena_quote (riparto_id);

CREATE INDEX IF NOT EXISTS idx_riparto_quote_sede
    ON public.riparto_costi_catena_quote (ristorante_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. riparto_regole_fornitore — "fai sempre così per questo fornitore"
-- ─────────────────────────────────────────────────────────────────────────────
-- La regola PROPONE il riparto alla ricezione di una nuova fattura del fornitore;
-- non lo applica mai da sola (filosofia ONEFLUX: l'AI propone, il cliente decide).
CREATE TABLE IF NOT EXISTS public.riparto_regole_fornitore (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    fornitore    TEXT NOT NULL,                  -- P.IVA cedente normalizzata
    regola       TEXT NOT NULL DEFAULT 'equa'
                     CHECK (regola IN ('equa', 'percentuali')),
    tipo         TEXT NOT NULL DEFAULT 'generale'
                     CHECK (tipo IN ('generale', 'fb')),
    percentuali  JSONB,                          -- {ristorante_id: %} solo se regola='percentuali'
    attiva       BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_riparto_regola_fornitore UNIQUE (user_id, fornitore)
);

COMMENT ON TABLE public.riparto_regole_fornitore IS
    'Memoria di ripartizione per fornitore: quando arriva una nuova fattura di quel '
    'fornitore, l''app PROPONE il riparto pronto (badge/coda), il cliente conferma. '
    'Mai applicazione automatica silenziosa.';

CREATE INDEX IF NOT EXISTS idx_riparto_regole_user
    ON public.riparto_regole_fornitore (user_id)
    WHERE attiva = true;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Flag anti-doppio-conteggio su fatture (livello riga)
-- ─────────────────────────────────────────────────────────────────────────────
-- Le righe di una fattura ripartita vengono escluse dal costo automatico della
-- sede intestataria (il costo rientra distribuito dalle quote). Stesso pattern di
-- needs_review: colonna booleana + indice parziale.
ALTER TABLE public.fatture
    ADD COLUMN IF NOT EXISTS ripartita_su_gruppo BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.fatture.ripartita_su_gruppo IS
    'TRUE = questa riga appartiene a una fattura ripartita sul gruppo (costo di '
    'struttura di catena). Esclusa dal costo automatico della sede intestataria per '
    'non contarla due volte: il costo rientra distribuito via riparto_costi_catena_quote.';

CREATE INDEX IF NOT EXISTS idx_fatture_ripartita_su_gruppo
    ON public.fatture (ristorante_id)
    WHERE ripartita_su_gruppo = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Colonne quote su margini_mensili (destinazione del motore)
-- ─────────────────────────────────────────────────────────────────────────────
-- SEPARATE da altri_costi_fb/altri_costi_spese (che sono input MANUALI dell'utente):
-- così un riparto non corrompe le spese extra manuali, ed è ricalcolabile/azzerabile
-- in autonomia dal motore. Il calcolo MOL somma queste accanto agli "altri costi".
ALTER TABLE public.margini_mensili
    ADD COLUMN IF NOT EXISTS quote_riparto_fb    NUMERIC(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS quote_riparto_spese NUMERIC(12,2) NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.margini_mensili.quote_riparto_fb IS
    'Quota € dei costi di gruppo di tipo F&B attribuita a questa sede nel mese. '
    'Popolata SOLO dal motore riparto (riparto_quote_mensili), mai dall''utente. '
    'Sommata a costi_fb_auto + altri_costi_fb nel calcolo MOL.';
COMMENT ON COLUMN public.margini_mensili.quote_riparto_spese IS
    'Quota € dei costi di gruppo di tipo generale attribuita a questa sede nel mese. '
    'Popolata SOLO dal motore riparto, mai dall''utente. Sommata a costi_spese_auto '
    '+ altri_costi_spese nel calcolo MOL.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. RLS: solo service_role (coerente con le altre tabelle worker-only)
-- ─────────────────────────────────────────────────────────────────────────────
-- Auth custom (auth.uid() sempre NULL): il worker opera con service_role, che
-- bypassa RLS. Niente policy per anon/authenticated → accesso negato di default.
ALTER TABLE public.riparto_costi_catena        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.riparto_costi_catena_quote  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.riparto_regole_fornitore    ENABLE ROW LEVEL SECURITY;

GRANT ALL ON public.riparto_costi_catena       TO service_role;
GRANT ALL ON public.riparto_costi_catena_quote TO service_role;
GRANT ALL ON public.riparto_regole_fornitore   TO service_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. Trigger updated_at
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.trg_riparto_touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS riparto_costi_catena_touch ON public.riparto_costi_catena;
CREATE TRIGGER riparto_costi_catena_touch
    BEFORE UPDATE ON public.riparto_costi_catena
    FOR EACH ROW EXECUTE FUNCTION public.trg_riparto_touch_updated_at();

DROP TRIGGER IF EXISTS riparto_regole_fornitore_touch ON public.riparto_regole_fornitore;
CREATE TRIGGER riparto_regole_fornitore_touch
    BEFORE UPDATE ON public.riparto_regole_fornitore
    FOR EACH ROW EXECUTE FUNCTION public.trg_riparto_touch_updated_at();
