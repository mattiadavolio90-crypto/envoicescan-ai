-- UNIQUE anti-duplicato su fatture per abilitare upsert atomico in salva_fattura_processata.
-- Risolve i due CRITICAL del salvataggio:
--   1) elimina il bisogno del hard-delete (che ignorava il cestino)
--   2) rende il salvataggio atomico per-riga (no finestra delete->insert non transazionale)
--
-- Scope: solo righe attive (deleted_at IS NULL), così una versione cestinata dello
-- stesso file puo' coesistere senza bloccare un nuovo upload (il cestino e' un'altra cosa).
-- Verificato pre-creazione: nessun duplicato attivo presente sul DB live.

CREATE UNIQUE INDEX IF NOT EXISTS uq_fatture_dedup_active
ON public.fatture (user_id, ristorante_id, file_origine, numero_riga)
WHERE deleted_at IS NULL;
