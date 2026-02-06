-- Migration 021: Aggiorna categorie ricette con nuove opzioni ristorante
-- Data: 2026-02-05
-- Autore: Sistema FCI

-- Step 1: Drop vecchio constraint
ALTER TABLE ricette DROP CONSTRAINT IF EXISTS ricette_categoria_check;

-- Step 2: Aggiungi nuovo constraint con tutte le categorie (incluse vecchie per compatibilità)
ALTER TABLE ricette ADD CONSTRAINT ricette_categoria_check 
CHECK (categoria IN (
    -- Nuove categorie ristorante
    'BRACE',
    'CARNE',
    'CONTORNI',
    'CRUDI',
    'DOLCI',
    'FOCACCE',
    'FRITTI',
    'GRIGLIA',
    'INSALATE',
    'PANINI',
    'PESCE',
    'PIADINE',
    'PINZE',
    'PIZZE',
    'POKE',
    'RISOTTI',
    'SALTATI',
    'SEMILAVORATI',
    'SUSHI',
    'TEMPURA',
    'VAPORE',
    'VERDURE',
    -- Vecchie categorie (retrocompatibilità)
    'ANTIPASTI',
    'PRIMI',
    'SECONDI'
));

-- Verifica constraint applicato
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conname = 'ricette_categoria_check';
