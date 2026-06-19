-- Giorni di chiusura settimanali della sede, impostati nel "Configura assistente".
-- Soglia per l'avviso "ricavi automatici assenti": 0 = sede sempre aperta -> avviso
-- dopo 1 giorno senza ricavi; 1 = tollera 1 giorno; 2 = 2 giorni; ecc. Cosi' una
-- sede con un giorno di chiusura fisso non riceve falsi allarmi.
ALTER TABLE assistant_preferences
    ADD COLUMN IF NOT EXISTS giorni_chiusura_settimanali smallint NOT NULL DEFAULT 0;

-- Vincolo di sanita': 0..6 giorni di chiusura a settimana.
ALTER TABLE assistant_preferences
    DROP CONSTRAINT IF EXISTS assistant_giorni_chiusura_range_chk;
ALTER TABLE assistant_preferences
    ADD CONSTRAINT assistant_giorni_chiusura_range_chk
    CHECK (giorni_chiusura_settimanali BETWEEN 0 AND 6);
