-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: gruppo_assistant_config — Configura Assistente catena (per account)
-- ═══════════════════════════════════════════════════════════════════════════════
-- Config dell'assistente a livello GRUPPO (separata da assistant_preferences, che è
-- per-sede): quali segnali "Da vedere nella catena" sono attivi e quali punti
-- vendita escludere dai segnali. 1 riga per account (user_id).
--
-- I segnali di gruppo (services/routers/gruppo.py::_calcola_segnali) leggono questa
-- config: saltano i tipi in segnali_disattivati e i PV in pv_esclusi. Salvare la
-- config invalida lo snapshot di oggi (gruppo_segnali_state) così i segnali si
-- ricalcolano subito con le nuove regole.
--
-- service_role bypassa RLS (auth.uid() è sempre NULL — auth custom). RLS abilitata
-- senza policy = nega anon/authenticated, consente solo service_role. Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.gruppo_assistant_config (
    user_id uuid PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    segnali_disattivati text[] NOT NULL DEFAULT '{}',
    pv_esclusi uuid[] NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.gruppo_assistant_config IS
    'Config assistente catena per account: segnali "Da vedere" disattivati + PV esclusi dai segnali di gruppo.';

ALTER TABLE public.gruppo_assistant_config ENABLE ROW LEVEL SECURITY;
