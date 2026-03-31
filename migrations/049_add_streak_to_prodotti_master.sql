-- Migration 049: Aggiunge contatore streak classificazioni GPT a prodotti_master
-- Obiettivo: prodotti con streak >= 3 classificazioni GPT consistenti vengono
-- auto-promossi a confidence='alta' (bypass cache), riducendo chiamate GPT del 60-70%.

ALTER TABLE public.prodotti_master
    ADD COLUMN IF NOT EXISTS consecutive_correct_classifications integer NOT NULL DEFAULT 0;

-- Indice parziale: solo le righe con streak >= 3 (promozione automatica)
CREATE INDEX IF NOT EXISTS idx_pm_streak_promo
    ON public.prodotti_master (consecutive_correct_classifications)
    WHERE consecutive_correct_classifications >= 3;

COMMENT ON COLUMN public.prodotti_master.consecutive_correct_classifications IS
    'Numero di volte consecutive che il GPT ha assegnato la stessa categoria. '
    'Raggiunto 3: il prodotto viene promosso a bypass automatico (confidence alta).';
