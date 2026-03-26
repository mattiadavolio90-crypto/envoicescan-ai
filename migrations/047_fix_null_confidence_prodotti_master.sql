-- Migration 047: Normalizza confidence NULL in prodotti_master
-- Le classificazioni AI precedenti venivano salvate senza il campo confidence (NULL).
-- Le impostiamo a 'media' così entrano nel flywheel hint senza attendere review manuale.
-- Classificazioni verified=TRUE (admin) restano 'altissima' — non vengono toccate.

UPDATE prodotti_master
SET confidence = 'media'
WHERE confidence IS NULL;
