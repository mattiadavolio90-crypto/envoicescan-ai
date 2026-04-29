-- 067_add_price_alert_threshold_users.sql
-- Soglia alert variazione prezzi personalizzabile per utente.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS price_alert_threshold NUMERIC(5,2) DEFAULT 5.0;

UPDATE users
SET price_alert_threshold = 5.0
WHERE price_alert_threshold IS NULL;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1
		FROM pg_constraint
		WHERE conname = 'users_price_alert_threshold_range'
	) THEN
		ALTER TABLE users
		ADD CONSTRAINT users_price_alert_threshold_range
		CHECK (price_alert_threshold >= 0 AND price_alert_threshold <= 100);
	END IF;
END $$;
