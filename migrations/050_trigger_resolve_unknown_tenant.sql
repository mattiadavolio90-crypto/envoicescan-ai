-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRATION 050: Estende sync_piva_ristoranti per invocare resolve_unknown_tenant
-- ═══════════════════════════════════════════════════════════════════════════════
-- Problema: quando un ristorante viene creato/aggiornato con una P.IVA per la
-- quale esistono record fatture_queue in stato 'unknown_tenant', questi restano
-- bloccati per sempre. La funzione resolve_unknown_tenant() esiste (migration 045)
-- ma non viene mai invocata automaticamente.
--
-- Fix: estende sync_piva_ristoranti() per chiamare resolve_unknown_tenant()
-- dopo INSERT e dopo UPDATE della partita_iva.
--
-- Backward compatible: il trigger esistente viene sostituito (CREATE OR REPLACE).
-- Se la funzione resolve_unknown_tenant non esiste, la PERFORM fallisce e il
-- trigger va in errore — ma la funzione esiste dalla migration 045.
--
-- Data: 2026-04-03
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

CREATE OR REPLACE FUNCTION sync_piva_ristoranti()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO piva_ristoranti (user_id, ristorante_id, piva, nome_ristorante)
        VALUES (NEW.user_id, NEW.id, NEW.partita_iva, NEW.nome_ristorante);
        -- Risolvi fatture unknown_tenant arrivate prima della registrazione
        IF NEW.partita_iva IS NOT NULL AND trim(NEW.partita_iva) != '' THEN
            PERFORM resolve_unknown_tenant(trim(NEW.partita_iva));
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE piva_ristoranti
        SET piva = NEW.partita_iva,
            nome_ristorante = NEW.nome_ristorante
        WHERE ristorante_id = NEW.id;
        -- Risolvi solo se la P.IVA è cambiata
        IF NEW.partita_iva IS DISTINCT FROM OLD.partita_iva
           AND NEW.partita_iva IS NOT NULL
           AND trim(NEW.partita_iva) != '' THEN
            PERFORM resolve_unknown_tenant(trim(NEW.partita_iva));
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM piva_ristoranti WHERE ristorante_id = OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMIT;
