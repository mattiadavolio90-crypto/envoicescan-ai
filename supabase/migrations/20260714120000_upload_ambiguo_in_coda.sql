-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: upload manuale ambiguo → coda da_assegnare (invece di scartare)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto (14/07/2026):
--   Oggi l'upload MANUALE di una fattura multi-sede il cui indirizzo non fa match
--   univoco con nessuna sede viene SCARTATO (error=SEDE_AMBIGUA) — la fattura non
--   entra proprio in app. Caso reale: OFFSIDE SRL, ~240/383 fatture 1° sem 2026
--   intestate alla sede legale (Fulvio Testi/Montalbino), non ai locali fisici.
--
--   Il canale SDI invece NON scarta: mette l'ambiguo in fatture_queue con
--   status='da_assegnare' e attende che il cliente/admin scelga la sede
--   (assegna_fattura_a_sede → pending → worker crea la fattura). Questa migration
--   porta l'upload manuale sullo STESSO binario, così le fatture di struttura
--   entrano in coda e possono poi essere assegnate a un locale OPPURE ripartite
--   sul gruppo (piano PIANO_OPERATIVO_RIPARTIZIONE_COSTI_CATENA.md, Fase 1).
--
-- Cosa fa:
--   1. Aggiunge fatture_queue.indirizzo_raw: l'indirizzo del CessionarioCommittente
--      così com'è in fattura, mostrato in UI per far capire perché è ambiguo.
--   2. RPC accoda_upload_ambiguo(): inserisce (idempotente) un item manuale in coda
--      con status='da_assegnare', xml già decodificato, event_id sintetico basato
--      sull'hash XML → i re-upload dello stesso file NON duplicano.
--
-- La P.IVA è già stata validata come appartenente al cliente PRIMA di chiamare
-- questa RPC (il worker chiama decidi_destinazione_upload: 'ambiguo' implica P.IVA
-- nota, solo sede incerta — 'piva_estranea' continua a scartare, guardia intatta).
--
-- Idempotente: ri-eseguibile senza errori.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Colonna indirizzo_raw (contesto per la UI di assegnazione)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.fatture_queue
    ADD COLUMN IF NOT EXISTS indirizzo_raw TEXT;

COMMENT ON COLUMN public.fatture_queue.indirizzo_raw IS
    'Indirizzo del CessionarioCommittente estratto dalla fattura, non normalizzato. '
    'Popolato per gli item da_assegnare (SDI o upload manuale): la UI lo mostra '
    'accanto alle sedi per far capire all''utente perché lo smistamento automatico '
    'non è stato univoco. NULL per gli item non ambigui.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. RPC accoda_upload_ambiguo(): item manuale ambiguo in coda
-- ─────────────────────────────────────────────────────────────────────────────
-- Inserisce in fatture_queue un item con status='da_assegnare' proveniente
-- dall'upload manuale. event_id sintetico deterministico ('manual:<user>:<hash>')
-- → l'UNIQUE su event_id rende l'inserimento idempotente: ricaricare lo stesso
-- file non crea un secondo item in coda (ON CONFLICT DO NOTHING).
--
-- Ritorna:
--   { queue_id, created }  — created=false se l'item esisteva già (re-upload)
--
-- Sicurezza: SECURITY DEFINER + search_path bloccato (coerente con le altre RPC
-- della coda). Il chiamante (worker service_role) ha già verificato che user_id è
-- il tenant reale e che la P.IVA appartiene a una sede del cliente.
CREATE OR REPLACE FUNCTION public.accoda_upload_ambiguo(
    p_user_id       UUID,
    p_piva_raw      TEXT,
    p_xml_content   TEXT,
    p_nome_file     TEXT,
    p_indirizzo_raw TEXT,
    p_xml_hash      TEXT,
    p_payload_meta  JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE (queue_id BIGINT, created BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_event_id TEXT;
    v_id       BIGINT;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;
    IF p_piva_raw IS NULL OR length(trim(p_piva_raw)) = 0 THEN
        RAISE EXCEPTION 'p_piva_raw non può essere vuota';
    END IF;
    IF p_xml_hash IS NULL OR length(trim(p_xml_hash)) = 0 THEN
        RAISE EXCEPTION 'p_xml_hash non può essere vuoto (serve per idempotenza)';
    END IF;

    -- event_id sintetico: stesso file (stesso hash) dello stesso cliente → stesso
    -- event_id → ON CONFLICT lo intercetta. Namespace 'manual:' per non collidere
    -- mai con gli event_id reali di Invoicetronic.
    v_event_id := 'manual:' || p_user_id::text || ':' || p_xml_hash;

    INSERT INTO public.fatture_queue (
        event_id, user_id, ristorante_id, piva_raw,
        xml_content, xml_hash, indirizzo_raw, payload_meta,
        source, status, next_retry_at
    )
    VALUES (
        v_event_id, p_user_id, NULL, trim(p_piva_raw),
        p_xml_content, p_xml_hash, p_indirizzo_raw, COALESCE(p_payload_meta, '{}'::jsonb),
        'upload_manuale', 'da_assegnare', now()
    )
    ON CONFLICT (event_id) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT v_id, TRUE;
        RETURN;
    END IF;

    -- Conflitto: l'item esiste già (re-upload). Restituisci il suo id, created=false.
    SELECT fq.id INTO v_id
    FROM public.fatture_queue fq
    WHERE fq.event_id = v_event_id;

    RETURN QUERY SELECT v_id, FALSE;
END;
$$;

COMMENT ON FUNCTION public.accoda_upload_ambiguo(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB) IS
    'Accoda una fattura da upload manuale rimasta ambigua (multi-sede, indirizzo non '
    'univoco) in fatture_queue con status=da_assegnare, source=upload_manuale. '
    'event_id sintetico manual:<user>:<hash> → idempotente sui re-upload. La sede '
    'viene poi scelta con assegna_fattura_a_sede (assegna a un locale) o dal flusso '
    'di ripartizione costi di gruppo. Ritorna (queue_id, created).';

REVOKE ALL ON FUNCTION public.accoda_upload_ambiguo(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.accoda_upload_ambiguo(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB) TO service_role;
