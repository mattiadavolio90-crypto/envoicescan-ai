-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: piano per sede (ristoranti.piano + piano_inizio_at)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Obiettivo:
--   Spostare il piano tariffario dal livello account (users.piano) al livello SEDE
--   (ristoranti). Ogni sede di una catena ha il suo piano e i suoi limiti → la
--   fatturazione diventa per-sede. Per il ristorante singolo è 1 sede = 1 piano.
--
-- Transizione SICURA:
--   - Le colonne sono NULLABLE: una sede senza piano EREDITA da users.piano
--     (fallback nel worker), così i clienti esistenti non perdono i limiti finché
--     non si valorizza il piano della sede. Nessun backfill forzato qui.
--
-- Idempotente: ri-eseguibile senza errori.
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.ristoranti
    ADD COLUMN IF NOT EXISTS piano           TEXT,
    ADD COLUMN IF NOT EXISTS piano_inizio_at TIMESTAMPTZ;

COMMENT ON COLUMN public.ristoranti.piano IS
    'Piano tariffario della SEDE (free|base|plus|pro). NULL = eredita da users.piano '
    '(fallback durante la transizione al modello piano-per-sede).';
COMMENT ON COLUMN public.ristoranti.piano_inizio_at IS
    'Data di inizio piano della sede. NULL = non impostata.';
