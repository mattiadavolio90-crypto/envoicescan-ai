-- RPC per il system prompt della chat: top categorie e top fornitori per spesa in
-- un intervallo di giorni, aggregati LATO DB (zero troncamento).
--
-- Prima _build_chat_system_prompt caricava fino a 1500 righe fattura degli ultimi
-- 90 giorni e le aggregava in Python ad OGNI domanda. Su clienti reali con molte
-- righe (caso top: 2070 righe/90gg) il limit 1500 TRONCAVA: le top-list nel prompt
-- erano sottostimate (categorie/fornitori "a colpo d'occhio" sbagliati). Aggregando
-- in SQL il totale è completo e si trasferiscono solo le 5+5 righe finali.
--
-- Una sola scansione, due aggregazioni: ritorna due "blocchi" (tipo='categoria' |
-- 'fornitore'), ognuno con voce + spesa, già ordinati per spesa desc. Il chiamante
-- prende i top-N per tipo. Coerente con il system prompt: filtro su data_documento,
-- deleted_at IS NULL, scoping opzionale per ristorante_id (NULL = tutte le sedi).
CREATE OR REPLACE FUNCTION chat_top_categoria_fornitore(
    p_user_id uuid,
    p_ristorante_id uuid,
    p_giorni int DEFAULT 90,
    p_top int DEFAULT 5
)
RETURNS TABLE (tipo text, voce text, spesa numeric)
LANGUAGE sql
STABLE
AS $$
    WITH base AS (
        SELECT
            COALESCE(NULLIF(TRIM(f.categoria), ''), 'Altro') AS categoria,
            COALESCE(NULLIF(TRIM(f.fornitore), ''), 'Sconosciuto') AS fornitore,
            f.totale_riga
        FROM fatture f
        WHERE f.user_id = p_user_id
          AND f.deleted_at IS NULL
          AND f.data_documento >= (CURRENT_DATE - p_giorni)
          AND (p_ristorante_id IS NULL OR f.ristorante_id = p_ristorante_id)
    ),
    top_cat AS (
        SELECT 'categoria'::text AS tipo, categoria AS voce, SUM(totale_riga) AS spesa
        FROM base GROUP BY categoria ORDER BY SUM(totale_riga) DESC LIMIT p_top
    ),
    top_forn AS (
        SELECT 'fornitore'::text AS tipo, fornitore AS voce, SUM(totale_riga) AS spesa
        FROM base GROUP BY fornitore ORDER BY SUM(totale_riga) DESC LIMIT p_top
    )
    SELECT tipo, voce, ROUND(spesa, 2) AS spesa FROM top_cat
    UNION ALL
    SELECT tipo, voce, ROUND(spesa, 2) AS spesa FROM top_forn;
$$;
