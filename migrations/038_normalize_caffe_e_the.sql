-- Migration 038: normalizza 'CAFFÈ E THE' → 'CAFFE E THE' (rimuove accento per uniformità)
-- Impatta: ~137 righe in produzione (rilevato audit 2026-04-20)
-- Sicura: idempotente, nessun dato viene eliminato
-- Nota: classificazioni_manuali usa struttura diversa, non ha colonna 'categoria' diretta

UPDATE fatture
SET categoria = 'CAFFE E THE'
WHERE categoria = 'CAFFÈ E THE';

UPDATE prodotti_utente
SET categoria = 'CAFFE E THE'
WHERE categoria = 'CAFFÈ E THE';

UPDATE prodotti_master
SET categoria = 'CAFFE E THE'
WHERE categoria = 'CAFFÈ E THE';
