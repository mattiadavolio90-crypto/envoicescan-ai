-- Preferenza tema (chiaro/scuro) per ogni cliente, impostabile in Impostazioni.
-- Segue l'account: salvata sul DB, applicata a ogni dispositivo dove accede.
-- Modifica additiva e sicura: colonna con default, nessun impatto su dati o
-- codice esistente (Streamlit incluso, che ignora il campo).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS tema text NOT NULL DEFAULT 'dark';

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_tema_chk;

ALTER TABLE users
    ADD CONSTRAINT users_tema_chk CHECK (tema IN ('dark', 'light'));

COMMENT ON COLUMN users.tema IS
    'Preferenza tema dell''interfaccia Next.js: ''dark'' (default) o ''light''. '
    'Impostata dal cliente in Impostazioni, applicata via next-themes.';
