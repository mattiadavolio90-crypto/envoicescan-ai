-- Riparto costi di gruppo: quote PER CATEGORIA (non più un solo `tipo` per documento).
--
-- PROBLEMA (Voce 6 gestione fatture di gruppo OFFSIDE, 24/7):
-- Una fattura ripartita ha oggi UN solo `tipo` (fb|generale) per l'intero documento.
-- Le quote per sede (riparto_costi_catena_quote) portano solo un importo, senza
-- categoria. Una fattura mista (es. METRO con VERDURE + detersivi, o CALCIO RETRÒ con
-- CARNE + MANUTENZIONE) ripartita 'generale' fa finire ANCHE il cibo nelle spese: il
-- MOL di ogni sede è falsato. Le righe sono già categorizzate correttamente in
-- `fatture` sulla sede tecnica, ma la RPC riparto_quote_mensili le ignora e usa il
-- `tipo` unico.
--
-- SOLUZIONE (additiva, retrocompatibile):
--   1. `riparto_costi_catena_quote.categoria` (nullable): quando valorizzata, la quota
--      è già instradabile per categoria. Quando NULL, vale il vecchio `tipo` del
--      riparto → i 137 riparti esistenti e ogni riparto non-catena restano identici.
--   2. helper `_riparto_categoria_is_fb(categoria)`: unica verità sul secchio F&B vs
--      Spese, allineata a config/constants.py (CATEGORIE_FOOD_BEVERAGE = 25 categorie).
--      "Da Classificare" e "📝 NOTE E DICITURE" → NON F&B (spese), coerente col fatto
--      che le righe non classificate non entrano nei margini F&B.
--
-- La RPC riparto_quote_mensili viene riscritta in una migration separata (stesso batch)
-- per usare questo helper. Qui solo schema + helper: nessun ricalcolo, nessun dato
-- toccato.

BEGIN;

-- ── 1. Colonna categoria sulle quote (nullable, additiva) ────────────────────
ALTER TABLE public.riparto_costi_catena_quote
    ADD COLUMN IF NOT EXISTS categoria text;

COMMENT ON COLUMN public.riparto_costi_catena_quote.categoria IS
    'Categoria della porzione di quota (Voce 6). NULL = quota legacy monolitica: '
    'il secchio MOL si deriva dal tipo del riparto padre. Valorizzata = la quota è '
    'una porzione per-categoria e va instradata via _riparto_categoria_is_fb().';

-- Il vincolo storico UNIQUE(riparto_id, ristorante_id) ammetteva UNA sola quota per
-- sede: incompatibile col modello per-categoria (N porzioni per sede). Lo si estende
-- includendo la categoria. Le quote legacy (categoria NULL) restano uniche per sede
-- perché una data sede ha al più una quota NULL: nessun conflitto con l'esistente.
ALTER TABLE public.riparto_costi_catena_quote
    DROP CONSTRAINT IF EXISTS uq_riparto_quota_sede;
ALTER TABLE public.riparto_costi_catena_quote
    ADD CONSTRAINT uq_riparto_quota_sede_categoria
    UNIQUE (riparto_id, ristorante_id, categoria);

-- ── 2. Helper: la categoria è Food & Beverage? ───────────────────────────────
-- Unica verità DB sul mapping categoria → secchio MOL. Allineata a
-- config/constants.py::CATEGORIE_FOOD_BEVERAGE. IMMUTABLE: dipende solo dall'input.
CREATE OR REPLACE FUNCTION public._riparto_categoria_is_fb(p_categoria text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT upper(btrim(coalesce(p_categoria, ''))) IN (
        'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
        'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA','SALSE E CREME',
        'ACQUA','BEVANDE','CAFFE E THE','BIRRE','VINI',
        'VARIE BAR','DISTILLATI','AMARI/LIQUORI','PASTICCERIA',
        'PRODOTTI DA FORNO','SPEZIE E AROMI','GELATI E DESSERT','SHOP','SUSHI VARIE'
    );
$$;

COMMENT ON FUNCTION public._riparto_categoria_is_fb(text) IS
    'TRUE se la categoria è Food & Beverage (25 cat. di CATEGORIE_FOOD_BEVERAGE). '
    'Spese generali, "Da Classificare", NOTE E DICITURE e ignoti → FALSE (secchio spese). '
    'Unica verità del mapping categoria→secchio MOL per il riparto per-categoria.';

COMMIT;
