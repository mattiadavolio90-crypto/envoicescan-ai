-- Home AI Step 1: nome del referente per il saluto personalizzato
-- "Buongiorno {nome_referente}". Campo opzionale, popolato lato admin in fase
-- di account, sovrascrivibile dal cliente nel configuratore assistente (Step 6).
-- Modifica additiva e sicura: aggiunge una colonna nullable, nessun impatto
-- su dati o codice esistenti (Streamlit incluso).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS nome_referente text;

COMMENT ON COLUMN users.nome_referente IS
    'Nome della persona di riferimento, usato per il saluto della Home AI '
    '("Buongiorno {nome}"). Opzionale. Fallback: nessun nome -> saluto liscio.';
