-- Ricerca server-side per le descrizioni di catena (Aggiungi prodotti al tag).
--
-- Prima la finestra caricava le prime 500 descrizioni per spesa e filtrava lato
-- client: per i gruppi con molti prodotti (es. SUSHILAND ~1400 descrizioni
-- distinte) i prodotti meno costosi oltre la 500ª non erano cercabili. Ora il
-- testo digitato (p_q) filtra direttamente nel DB su TUTTE le sedi del gruppo.
--
-- p_q NULL/'' = comportamento precedente (top per spesa). Idempotente.

DROP FUNCTION IF EXISTS public.gruppo_tag_descrizioni(uuid[], int);

CREATE OR REPLACE FUNCTION public.gruppo_tag_descrizioni(
    p_ristorante_ids uuid[],
    p_q              text DEFAULT NULL,
    p_limit          int  DEFAULT 500
)
RETURNS TABLE (descrizione text, descrizione_key text, n bigint, spesa numeric)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT
        (array_agg(f.descrizione ORDER BY f.data_documento DESC))[1] AS descrizione,
        upper(regexp_replace(btrim(f.descrizione), '\s+', ' ', 'g')) AS descrizione_key,
        count(*)::bigint AS n,
        sum(f.totale_riga) AS spesa
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND f.descrizione IS NOT NULL
      AND btrim(f.descrizione) <> ''
      AND f.prezzo_unitario > 0
      AND (p_q IS NULL OR btrim(p_q) = '' OR f.descrizione ILIKE '%' || btrim(p_q) || '%')
    GROUP BY descrizione_key
    ORDER BY spesa DESC NULLS LAST
    LIMIT p_limit;
$$;

REVOKE ALL ON FUNCTION public.gruppo_tag_descrizioni(uuid[], text, int) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_tag_descrizioni(uuid[], text, int) TO service_role;
