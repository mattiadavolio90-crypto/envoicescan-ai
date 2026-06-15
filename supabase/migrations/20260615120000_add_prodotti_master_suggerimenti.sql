-- ============================================================
-- MIGRATION: prodotti_master — suggerimenti AI (prepara, non scrive)
-- ============================================================
-- Lo strumento unico "Categorie" (admin) propone una categoria per le righe
-- dubbie (needs_review) tramite cascata regola -> memoria -> AI. Il livello AI
-- e l'Agent notturno NON scrivono mai la categoria definitiva: salvano un
-- SUGGERIMENTO che l'admin approva a mano. Mancavano le colonne per persisterlo.
--
-- Nota: la UI MemoriaTab leggeva gia' `categoria_suggerita` (stato "Sospetti AI"),
-- ma la colonna non esisteva -> il filtro era di fatto sempre vuoto. Questa
-- migration lo abilita.

ALTER TABLE prodotti_master
    ADD COLUMN IF NOT EXISTS categoria_suggerita TEXT,
    ADD COLUMN IF NOT EXISTS suggerimento_fonte  TEXT,
    ADD COLUMN IF NOT EXISTS suggerito_at        TIMESTAMP WITHOUT TIME ZONE;

COMMENT ON COLUMN prodotti_master.categoria_suggerita IS 'Categoria PROPOSTA (non applicata) da AI/agent notturno per voci dubbie. Va approvata a mano nello strumento Categorie. NULL = nessun suggerimento pendente.';
COMMENT ON COLUMN prodotti_master.suggerimento_fonte IS 'Origine del suggerimento: regola | memoria | ai. Mostrato in colonna Fonte.';
COMMENT ON COLUMN prodotti_master.suggerito_at IS 'Quando e'' stato calcolato il suggerimento. Usato per idempotenza (non ri-suggerire cio'' che ha gia'' un suggerimento fresco).';

-- Indice parziale: la coda lista solo le voci con suggerimento pendente.
CREATE INDEX IF NOT EXISTS prodotti_master_suggerimento_idx
    ON prodotti_master (suggerito_at)
    WHERE categoria_suggerita IS NOT NULL;
