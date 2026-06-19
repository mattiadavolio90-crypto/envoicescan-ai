-- Analisi ricca dei tag di catena: oltre alla spesa per PV (gruppo_tag_analisi),
-- aggiunge la classifica fornitori e il trend mensile, sempre via SQL aggregato
-- (GROUP BY) sulle stesse condizioni — niente full-load delle righe fattura.

-- Classifica fornitori del tag su tutte le sedi del gruppo nel periodo.
CREATE OR REPLACE FUNCTION public.gruppo_tag_fornitori(
    p_ristorante_ids   uuid[],
    p_descrizione_keys text[],
    p_data_da          date,
    p_data_a           date
)
RETURNS TABLE (fornitore text, spesa numeric, n_righe bigint)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT
        COALESCE(NULLIF(btrim(f.fornitore), ''), '—') AS fornitore,
        sum(f.totale_riga) AS spesa,
        count(*)::bigint AS n_righe
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.prezzo_unitario > 0
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1
    ORDER BY spesa DESC NULLS LAST
    LIMIT 20;
$$;

REVOKE ALL ON FUNCTION public.gruppo_tag_fornitori(uuid[], text[], date, date) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_fornitori(uuid[], text[], date, date) TO service_role;


-- Trend mensile della spesa del tag (gruppo intero) nel periodo.
CREATE OR REPLACE FUNCTION public.gruppo_tag_trend(
    p_ristorante_ids   uuid[],
    p_descrizione_keys text[],
    p_data_da          date,
    p_data_a           date
)
RETURNS TABLE (anno int, mese int, spesa numeric)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT
        extract(year  FROM COALESCE(f.data_competenza, f.data_documento))::int AS anno,
        extract(month FROM COALESCE(f.data_competenza, f.data_documento))::int AS mese,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.prezzo_unitario > 0
      AND upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) = ANY(p_descrizione_keys)
      AND COALESCE(f.data_competenza, f.data_documento) BETWEEN p_data_da AND p_data_a
    GROUP BY 1, 2
    ORDER BY 1, 2;
$$;

REVOKE ALL ON FUNCTION public.gruppo_tag_trend(uuid[], text[], date, date) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_trend(uuid[], text[], date, date) TO service_role;
