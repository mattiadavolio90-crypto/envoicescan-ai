-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: multi-sede routing (P.IVA condivisa fra più ristoranti)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Obiettivo:
--   Permettere a un cliente con UNA sola P.IVA ma PIÙ ristoranti (sedi) di ricevere
--   le fatture SDI smistate alla sede corretta in base all'indirizzo del
--   CessionarioCommittente scritto in fattura dal fornitore.
--
-- Cosa fa:
--   1. Aggiunge a `ristoranti` i campi indirizzo strutturati (indirizzo, cap, comune)
--      + `indirizzo_match`: forma normalizzata usata dal webhook per il match per
--        similarità contro l'indirizzo estratto dall'XML.
--   2. Introduce lo stato `da_assegnare` su `fatture_queue`: usato quando la P.IVA
--      ha più sedi e il match per indirizzo NON è univoco → la fattura resta in
--      attesa che il cliente scelga la sede in UI (coda manuale = caso estremo).
--   3. Allenta `chk_fatture_queue_tenant_consistency` per ammettere il caso
--      `da_assegnare`: user_id NOTO (sappiamo il cliente) ma ristorante_id NULL
--      (non sappiamo ancora QUALE sede).
--
-- Idempotente: ri-eseguibile senza errori.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Campi indirizzo su `ristoranti`
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.ristoranti
    ADD COLUMN IF NOT EXISTS indirizzo        TEXT,
    ADD COLUMN IF NOT EXISTS cap              TEXT,
    ADD COLUMN IF NOT EXISTS comune           TEXT,
    ADD COLUMN IF NOT EXISTS indirizzo_match  TEXT;

COMMENT ON COLUMN public.ristoranti.indirizzo IS
    'Indirizzo della sede (via + civico) così come va mostrato all''utente.';
COMMENT ON COLUMN public.ristoranti.cap IS
    'CAP della sede. Usato come segnale forte nel match per indirizzo.';
COMMENT ON COLUMN public.ristoranti.comune IS
    'Comune della sede.';
COMMENT ON COLUMN public.ristoranti.indirizzo_match IS
    'Forma normalizzata di indirizzo+cap+comune (lowercase, no punteggiatura, '
    'spazi singoli) calcolata da normalizza_indirizzo_match(). Chiave di confronto '
    'usata dal webhook Invoicetronic per smistare le fatture fra sedi con stessa P.IVA. '
    'NULL/blank per i ristoranti mono-sede (match non necessario).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Funzione di normalizzazione indirizzo (SQL, deterministica)
-- ─────────────────────────────────────────────────────────────────────────────
-- Allinea via/civico/cap/comune a una forma confrontabile:
--   - lowercase
--   - rimuove accenti comuni
--   - espande/uniforma le abbreviazioni di toponimo (v.le→viale, c.so→corso, ecc.)
--   - tiene SOLO lettere/cifre/spazi, collassa spazi multipli
-- NB: la decisione vera (quale sede) la prende il webhook col punteggio di
-- similarità; questa funzione serve solo a dare una base pulita e stabile.
CREATE OR REPLACE FUNCTION public.normalizza_indirizzo_match(p_raw TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT NULLIF(
        trim(
            regexp_replace(
                regexp_replace(
                    -- espansione abbreviazioni toponomastiche più comuni
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        lower(coalesce(p_raw, '')),
                                        '\m(v\.?le)\M', 'viale', 'g'),
                                    '\m(c\.?so)\M', 'corso', 'g'),
                                '\m(p\.?zza|p\.?za)\M', 'piazza', 'g'),
                            '\m(v\.?)\M', 'via', 'g'),
                        '\m(str\.?)\M', 'strada', 'g'),
                    -- tieni solo alfanumerici e spazi
                    '[^a-z0-9 ]', ' ', 'g'),
                -- collassa spazi multipli
                '\s+', ' ', 'g')
        ),
        ''
    );
$$;

COMMENT ON FUNCTION public.normalizza_indirizzo_match(TEXT) IS
    'Normalizza un indirizzo a forma confrontabile (lowercase, abbreviazioni '
    'toponomastiche espanse, solo alfanumerici, spazi singoli). Usata per popolare '
    'ristoranti.indirizzo_match e — lato webhook — per costruire la chiave di match '
    'dell''indirizzo estratto dalla fattura.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Trigger: mantiene `indirizzo_match` sempre coerente con i campi sede
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.trg_ristoranti_indirizzo_match()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.indirizzo_match := public.normalizza_indirizzo_match(
        concat_ws(' ', NEW.indirizzo, NEW.cap, NEW.comune)
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS ristoranti_indirizzo_match_biu ON public.ristoranti;
CREATE TRIGGER ristoranti_indirizzo_match_biu
    BEFORE INSERT OR UPDATE OF indirizzo, cap, comune
    ON public.ristoranti
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_ristoranti_indirizzo_match();

-- Backfill: ricalcola per le righe esistenti che avessero già indirizzo valorizzato.
UPDATE public.ristoranti
SET indirizzo_match = public.normalizza_indirizzo_match(
        concat_ws(' ', indirizzo, cap, comune)
    )
WHERE indirizzo IS NOT NULL OR cap IS NOT NULL OR comune IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Stato `da_assegnare` su `fatture_queue`
-- ─────────────────────────────────────────────────────────────────────────────
-- 4a. Amplia il CHECK degli status ammessi.
ALTER TABLE public.fatture_queue
    DROP CONSTRAINT IF EXISTS chk_fatture_queue_status;

ALTER TABLE public.fatture_queue
    ADD CONSTRAINT chk_fatture_queue_status
        CHECK (status IN (
            'pending', 'processing', 'done',
            'failed', 'dead', 'unknown_tenant',
            'da_assegnare'
        ));

-- 4b. Allenta la consistenza tenant per ammettere `da_assegnare`:
--     in quello stato CONOSCIAMO il cliente (user_id) ma NON la sede (ristorante_id).
ALTER TABLE public.fatture_queue
    DROP CONSTRAINT IF EXISTS chk_fatture_queue_tenant_consistency;

ALTER TABLE public.fatture_queue
    ADD CONSTRAINT chk_fatture_queue_tenant_consistency
        CHECK (
            -- caso normale: entrambi NULL oppure entrambi valorizzati
            (user_id IS NULL AND ristorante_id IS NULL)
            OR
            (user_id IS NOT NULL AND ristorante_id IS NOT NULL)
            OR
            -- caso multi-sede in attesa di scelta: cliente noto, sede da decidere
            (status = 'da_assegnare' AND user_id IS NOT NULL AND ristorante_id IS NULL)
        );

-- 4c. Indice per la coda "da assegnare" (UI cliente).
CREATE INDEX IF NOT EXISTS idx_fatture_queue_da_assegnare
    ON public.fatture_queue (user_id, created_at)
    WHERE status = 'da_assegnare';
