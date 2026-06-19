-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: hardening sposta_fattura_a_sede() — gestione collisione dedup
-- ═══════════════════════════════════════════════════════════════════════════════
-- Corregge un bug latente del routing multi-sede (P.IVA condivisa fra più sedi).
--
-- PROBLEMA:
--   La RPC 20260611160000_rpc_sposta_fattura_a_sede sposta tutte le righe `fatture`
--   di un file_origine verso un'altra sede cambiandone il ristorante_id. Se nella
--   sede DESTINAZIONE esiste già una fattura con lo STESSO file_origine e gli stessi
--   numero_riga (stesso file caricato/smistato su entrambe le sedi di un account
--   multi-sede — es. OFFSIDE/OVERTIME, stessa P.IVA), l'UPDATE viola il vincolo
--   unique uq_fatture_dedup (user_id, ristorante_id, file_origine, numero_riga).
--   Risultato attuale: eccezione non gestita → HTTP 500 opaco e — peggio — se
--   l'errore arrivasse a metà UPDATE, lo spostamento resterebbe parziale (alcune
--   righe sulla nuova sede, altre sulla vecchia). Lo stesso rischio vale per la
--   testata fatture_documenti.
--
-- FIX:
--   Pre-controllo esplicito: se la sede destinazione contiene già righe ATTIVE con
--   lo stesso file_origine, si solleva un'eccezione DEDICATA e LEGGIBILE
--   ('collisione_file_in_sede_destinazione') PRIMA di toccare i dati. La funzione è
--   in una singola transazione PL/pgSQL: qualsiasi RAISE fa rollback automatico,
--   quindi lo spostamento è atomico (tutto o niente) — niente più stato parziale.
--   Lo spostamento verso la sede in cui la fattura GIÀ si trova resta un no-op
--   sicuro (la collisione con sé stessa viene esclusa: si confronta una sede
--   DIVERSA da quella di partenza).
--
-- NB: il caso d'uso "stesso file legittimamente presente su due sedi" è raro (il
--   routing automatico smista una fattura a UNA sola sede); quando accade è quasi
--   sempre un doppione da risolvere a mano, non un merge automatico. Bloccare con
--   messaggio chiaro è il comportamento corretto: il worker può tradurlo in un 409
--   con spiegazione, invece di un 500.
--
-- Sicurezza: invariata rispetto all'originale (SECURITY DEFINER, search_path
--   bloccato, guard anti cross-tenant su sede destinazione).
--
-- Idempotente (CREATE OR REPLACE).
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.sposta_fattura_a_sede(
    p_user_id       UUID,
    p_file_origine  TEXT,
    p_ristorante_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_rist_user_id UUID;
    v_rist_attivo  BOOLEAN;
    v_updated      INTEGER;
    v_collisioni   INTEGER;
BEGIN
    IF p_user_id IS NULL OR p_file_origine IS NULL OR p_ristorante_id IS NULL THEN
        RAISE EXCEPTION 'Parametri mancanti per sposta_fattura_a_sede';
    END IF;

    -- La sede di destinazione deve esistere, appartenere all'utente ed essere attiva.
    SELECT user_id, attivo
    INTO   v_rist_user_id, v_rist_attivo
    FROM   public.ristoranti
    WHERE  id = p_ristorante_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ristorante % inesistente', p_ristorante_id;
    END IF;

    IF v_rist_user_id IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'Ristorante % non appartiene all''utente', p_ristorante_id;
    END IF;

    IF v_rist_attivo IS NOT TRUE THEN
        RAISE EXCEPTION 'Ristorante % non attivo', p_ristorante_id;
    END IF;

    -- Pre-controllo collisione: la sede destinazione contiene già righe attive con
    -- questo file_origine? (escludendo il caso no-op "sposta verso la stessa sede",
    -- gestito naturalmente: lì le righe da spostare SONO quelle già lì).
    -- Se la collisione esiste su una sede diversa da quelle di partenza, lo spostamento
    -- violerebbe uq_fatture_dedup → blocchiamo prima di toccare i dati.
    SELECT count(*)
    INTO   v_collisioni
    FROM   public.fatture
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  ristorante_id = p_ristorante_id
      AND  deleted_at IS NULL;

    IF v_collisioni > 0 THEN
        -- Esistono già righe di questo file nella sede destinazione. Spostarci sopra
        -- le righe di un'altra sede creerebbe duplicati (stesso numero_riga) → blocco.
        -- Se TUTTE le righe da spostare sono GIÀ in questa sede (no-op reale), non
        -- c'è nulla da spostare da altre sedi: controlliamo che esista almeno una
        -- riga del file in una sede DIVERSA prima di considerarla una vera collisione.
        PERFORM 1
        FROM   public.fatture
        WHERE  user_id       = p_user_id
          AND  file_origine  = p_file_origine
          AND  ristorante_id IS DISTINCT FROM p_ristorante_id
          AND  deleted_at IS NULL
        LIMIT 1;

        IF FOUND THEN
            RAISE EXCEPTION 'collisione_file_in_sede_destinazione'
                USING DETAIL = format(
                    'Il file %s esiste già nella sede destinazione %s: '
                    'spostamento bloccato per evitare duplicati.',
                    p_file_origine, p_ristorante_id
                );
        END IF;
        -- Altrimenti: il file è SOLO nella sede destinazione → no-op, esce con 0.
    END IF;

    -- Sposta le righe della fattura (solo quelle attive, dello stesso utente).
    UPDATE public.fatture
    SET    ristorante_id = p_ristorante_id
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  ristorante_id IS DISTINCT FROM p_ristorante_id
      AND  deleted_at IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    -- Allinea la testata documento (stessa chiave logica).
    UPDATE public.fatture_documenti
    SET    ristorante_id = p_ristorante_id
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  ristorante_id IS DISTINCT FROM p_ristorante_id
      AND  deleted_at IS NULL;

    RETURN v_updated;
END;
$$;

COMMENT ON FUNCTION public.sposta_fattura_a_sede(UUID, TEXT, UUID) IS
    'Sposta una fattura già acquisita (tutte le righe fatture + testata '
    'fatture_documenti con quel file_origine) verso un''altra sede dello stesso '
    'utente. Usata dall''azione "Sposta in altra sede" nel dettaglio fattura '
    '(Scadenziario), per correggere assegnazioni automatiche sbagliate del routing '
    'multi-sede. Guard anti cross-tenant. Se la sede destinazione contiene già lo '
    'stesso file_origine solleva collisione_file_in_sede_destinazione (atomico, '
    'nessuno spostamento parziale). Restituisce il numero di righe spostate.';
