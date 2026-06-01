-- Home AI Step 6: configuratore assistente.
-- Preferenze per-ristorante dell'assistente Home: nome del referente (override
-- del saluto) e interruttori ON/OFF per ogni topic. Default AI-first: tutto
-- attivo. Un topic conta spento SOLO se presente in topics_disabled.
-- Modifica additiva e sicura: nuova tabella isolata, nessun impatto su dati o
-- codice esistente (Streamlit incluso).

CREATE TABLE IF NOT EXISTS assistant_preferences (
    ristorante_id   uuid PRIMARY KEY REFERENCES ristoranti(id) ON DELETE CASCADE,
    nome_referente  text,
    topics_disabled jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE assistant_preferences IS
    'Preferenze Home AI per ristorante (Step 6): nome referente + topic spenti.';
COMMENT ON COLUMN assistant_preferences.nome_referente IS
    'Override del nome per il saluto. Se valorizzato vince su users.nome_referente.';
COMMENT ON COLUMN assistant_preferences.topics_disabled IS
    'Array JSON dei topic_key disattivati dal cliente. Default-on: ciò che non è qui resta attivo.';
