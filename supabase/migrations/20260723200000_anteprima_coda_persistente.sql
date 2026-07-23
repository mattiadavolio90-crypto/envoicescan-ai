-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: anteprima coda persistente (Fase 4 — cura radice P1)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto (23/07/2026, richiesta OFFSIDE):
--   L'anteprima delle righe di una fattura in coda 'da_assegnare' oggi RI-PARSA
--   l'XML a caldo a OGNI apertura (endpoint sincrono riparto_anteprima_coda, unico
--   container Railway Hobby, nessuna cache). Sotto contesa un colpo di lentezza
--   supera il timeout → l'anteprima "sparisce" e rientrando ricompare: la firma
--   della contesa di risorse, non di un documento rotto. Messaggio "documento
--   firmato non leggibile" fuorviante.
--
-- Cura alla radice: parse UNA volta, salva le righe estratte. Le aperture
-- successive leggono dal DB → istantanee, zero contesa, zero ri-parse.
--
-- Cosa fa:
--   1. anteprima_righe JSONB   — le righe già parsate (stessa forma del payload che
--      l'endpoint ritorna: numero_riga, descrizione, quantita, ...). NULL = mai
--      parsata con successo (l'endpoint la calcolerà e la salverà al primo colpo).
--   2. anteprima_at TIMESTAMPTZ — quando è stata calcolata. Serve a invalidare la
--      cache se in futuro cambia la logica di parsing (finora non necessario, ma
--      tenerlo evita di dover indovinare a posteriori se un'anteprima è stantia).
--
-- La FATTURA RESTA SACRA: qui non si tocca né si riscrive nessuna riga fiscale.
-- anteprima_righe è una CACHE di sola visualizzazione, derivata dall'xml_content,
-- rigenerabile in qualsiasi momento (basta azzerarla → il prossimo accesso la
-- ricalcola). Non è una fonte di verità fiscale.
--
-- Nota purge: xml_content viene svuotato dopo xml_purged_at. Una volta salvata,
-- anteprima_righe sopravvive alla purge → l'anteprima resta consultabile anche
-- quando l'XML grezzo non c'è più. Beneficio collaterale, non un rischio.
--
-- Idempotente: ADD COLUMN IF NOT EXISTS.
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.fatture_queue
    ADD COLUMN IF NOT EXISTS anteprima_righe JSONB;

ALTER TABLE public.fatture_queue
    ADD COLUMN IF NOT EXISTS anteprima_at TIMESTAMPTZ;

COMMENT ON COLUMN public.fatture_queue.anteprima_righe IS
    'Cache delle righe già parsate dell''anteprima coda (Fase 4, 23/07/2026): '
    'array JSONB {numero_riga, descrizione, quantita, unita_misura, prezzo_unitario, '
    'iva_percentuale, totale_riga, categoria}. Popolata al primo parsing riuscito da '
    'riparto_anteprima_coda; le aperture successive leggono da qui (niente ri-parse '
    'a caldo → niente timeout/contesa). Sola visualizzazione, derivata da xml_content, '
    'rigenerabile azzerandola. NON è fonte di verità fiscale (la fattura resta sacra). '
    'Sopravvive alla purge di xml_content. NULL = mai parsata con successo.';

COMMENT ON COLUMN public.fatture_queue.anteprima_at IS
    'Istante in cui anteprima_righe è stata calcolata. Serve a individuare/invalidare '
    'anteprime stantie se cambia la logica di parsing. NULL se anteprima_righe è NULL.';
