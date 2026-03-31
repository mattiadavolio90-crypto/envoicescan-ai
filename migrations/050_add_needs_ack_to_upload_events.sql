-- Migration 050: Aggiunge flag needs_ack a upload_events
-- Obiettivo: tracciare quali fatture auto-ricevute (source=invoicetronic) devono
-- ancora essere confermate dall'utente, indipendentemente dal timestamp di login.
-- Questo risolve il bug: dopo "Elimina Tutto" + re-run worker, la notifica
-- non riappariva perché upload_events.created_at cadeva fuori dalla finestra
-- [last_login_precedente, login_at].

ALTER TABLE public.upload_events
    ADD COLUMN IF NOT EXISTS needs_ack boolean NOT NULL DEFAULT false;

-- Solo i record source=invoicetronic già presenti vengono marcati needs_ack=true
-- (retrocompatibilità: chi aveva già fatture worker non viste le vedrà di nuovo)
UPDATE public.upload_events
    SET needs_ack = true
    WHERE details->>'source' = 'invoicetronic'
      AND status IN ('SAVED_OK', 'SAVED_PARTIAL');

-- Indice per query frequente: "fatture worker non ancora confermate per utente"
CREATE INDEX IF NOT EXISTS idx_upload_events_needs_ack
    ON public.upload_events (user_id, needs_ack)
    WHERE needs_ack = true;

COMMENT ON COLUMN public.upload_events.needs_ack IS
    'true = fattura auto-ricevuta (source=invoicetronic) non ancora confermata dall''utente. '
    'Viene settato a false quando l''utente clicca Salva, Rifiuta o Salva tutte nella UI.';
