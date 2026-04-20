-- Migration 039: uniforma 'NOTE E DICITURE' (senza emoji) → '📝 NOTE E DICITURE'
-- Impatta: ~10 righe in produzione (rilevato audit 2026-04-20)
-- Sicura: idempotente, nessun dato viene eliminato
-- Nota: classificazioni_manuali usa struttura diversa, non ha colonna 'categoria' diretta

UPDATE fatture
SET categoria = '📝 NOTE E DICITURE'
WHERE categoria = 'NOTE E DICITURE';

UPDATE prodotti_utente
SET categoria = '📝 NOTE E DICITURE'
WHERE categoria = 'NOTE E DICITURE';

UPDATE prodotti_master
SET categoria = '📝 NOTE E DICITURE'
WHERE categoria = 'NOTE E DICITURE';
