-- Pagina Prezzi: prodotti "preferiti" (stella) per filtrare la lista variazioni.
-- I prodotti qui non hanno un ID stabile: sono identificati al volo da
-- (descrizione, fornitore) e raggruppati con chiave normalizzata UPPER(TRIM(...)).
-- Quindi un preferito si salva come coppia normalizzata (descrizione_key,
-- fornitore_key). Chiave PER-RISTORANTE (come assistant_preferences): il preferito
-- e' del locale, lo vedono tutti gli operatori della sede; user_id traccia solo
-- chi l'ha aggiunto. Modifica additiva e isolata: nessun impatto su dati o codice
-- esistente.

CREATE TABLE IF NOT EXISTS prezzi_preferiti (
    id              bigserial PRIMARY KEY,
    ristorante_id   uuid NOT NULL REFERENCES ristoranti(id) ON DELETE CASCADE,
    user_id         uuid NOT NULL,
    descrizione_key text NOT NULL,
    fornitore_key   text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ristorante_id, descrizione_key, fornitore_key)
);

CREATE INDEX IF NOT EXISTS idx_prezzi_preferiti_rist ON prezzi_preferiti(ristorante_id);

COMMENT ON TABLE prezzi_preferiti IS
    'Prodotti preferiti (stella) della pagina Prezzi, per ristorante. Chiave = coppia normalizzata (descrizione, fornitore).';
COMMENT ON COLUMN prezzi_preferiti.descrizione_key IS
    'UPPER(TRIM(descrizione)) senza suffissi UI (es. " ⚠️ >6m"). Match con il raggruppamento delle variazioni.';
COMMENT ON COLUMN prezzi_preferiti.fornitore_key IS
    'UPPER(TRIM(fornitore)).';
COMMENT ON COLUMN prezzi_preferiti.user_id IS
    'Traccia di chi ha aggiunto il preferito. Il preferito vale per tutto il ristorante.';
