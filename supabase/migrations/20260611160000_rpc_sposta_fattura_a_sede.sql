-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: RPC sposta_fattura_a_sede()
-- ═══════════════════════════════════════════════════════════════════════════════
-- Correzione a posteriori del routing multi-sede.
--
-- Caso d'uso: una fattura GIÀ acquisita (righe in `fatture` + testata in
-- `fatture_documenti`) è finita nella sede sbagliata — tipicamente perché il
-- fornitore ha scritto un indirizzo errato ma abbastanza simile a una sede reale
-- da superare le soglie di assegnazione automatica del webhook. Lo switch di sede
-- in sidebar cambia solo la sede ATTIVA di visualizzazione, non riassegna le
-- fatture: serve quindi un'azione esplicita "Sposta in altra sede" dal dettaglio
-- fattura (Scadenziario).
--
-- Differenza da assegna_fattura_a_sede(): quella agisce sulla CODA (fatture non
-- ancora elaborate, identificate da queue_id). Questa agisce su una fattura GIÀ
-- nel DB operativo, identificata da (user_id, file_origine).
--
-- Cosa sposta: il campo `ristorante_id` su tutte le righe `fatture` e sulla
-- testata `fatture_documenti` con quel file_origine, dello stesso utente, NON in
-- cestino (deleted_at IS NULL). NON tocca:
--   - `prodotti`            → anagrafica per-utente, non per-sede (no ristorante_id)
--   - `category_change_log` → storico/audit: la storia resta dov'è avvenuta
--
-- Sicurezza:
--   - SECURITY DEFINER + search_path bloccato (coerente con le altre RPC).
--   - La sede di destinazione DEVE appartenere allo stesso user_id e essere attiva
--     (no cross-tenant: non si sposta la fattura verso il ristorante di un altro).
--   - Filtra sempre per user_id passato dal worker (risolto dal token di sessione):
--     un utente non può spostare fatture altrui.
--
-- Restituisce il numero di righe `fatture` aggiornate (0 = nessuna riga trovata
-- per quel file_origine, es. già in cestino o file_origine inesistente).
--
-- Idempotente nella definizione (CREATE OR REPLACE). Spostare verso la sede in cui
-- la fattura già si trova è un no-op sicuro (aggiorna a sé stesso).
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

    -- Sposta le righe della fattura (solo quelle attive, dello stesso utente).
    UPDATE public.fatture
    SET    ristorante_id = p_ristorante_id
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  deleted_at IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    -- Allinea la testata documento (stessa chiave logica).
    UPDATE public.fatture_documenti
    SET    ristorante_id = p_ristorante_id
    WHERE  user_id       = p_user_id
      AND  file_origine  = p_file_origine
      AND  deleted_at IS NULL;

    RETURN v_updated;
END;
$$;

COMMENT ON FUNCTION public.sposta_fattura_a_sede(UUID, TEXT, UUID) IS
    'Sposta una fattura già acquisita (tutte le righe fatture + testata '
    'fatture_documenti con quel file_origine) verso un''altra sede dello stesso '
    'utente. Usata dall''azione "Sposta in altra sede" nel dettaglio fattura '
    '(Scadenziario), per correggere assegnazioni automatiche sbagliate del routing '
    'multi-sede. Guard anti cross-tenant. Restituisce il numero di righe spostate.';
