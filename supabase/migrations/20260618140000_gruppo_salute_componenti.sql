-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: gruppo_salute_componenti — salute gruppo in UNA query (perf)
-- ═══════════════════════════════════════════════════════════════════════════════
-- L'overview catena calcolava la salute chiamando _salute_indice_sede N volte in
-- serie (2 query a sede, incl. una full-load di fatture): lento a worker freddo su
-- catene con molte fatture. Questa RPC restituisce, PER SEDE e in un solo
-- round-trip, le 4 componenti dell'indice di salute; l'indice si calcola poi in
-- Python con la STESSA formula 4-voci di /api/home/salute.
--
--   - n_fatture / n_needs_review: fatture caricate negli ultimi 30g (created_at >=
--     p_inizio), deleted_at IS NULL → % classificate.
--   - netto / personale: dell'ultimo mese completo (p_anno, p_mese) da
--     margini_mensili (1 riga per sede×mese).
--
-- STABLE SECURITY DEFINER, search_path bloccato, REVOKE da public/anon/authenticated
-- (solo service_role la usa). Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.gruppo_salute_componenti(
    p_ristorante_ids uuid[],
    p_inizio timestamptz,
    p_anno int,
    p_mese int
)
RETURNS TABLE(
    ristorante_id uuid,
    n_fatture bigint,
    n_needs_review bigint,
    netto numeric,
    personale numeric
)
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path TO 'public'
AS $function$
    WITH f AS (
        SELECT fa.ristorante_id AS rid,
               count(*) AS n_fatture,
               count(*) FILTER (WHERE fa.needs_review) AS n_needs_review
        FROM fatture fa
        WHERE fa.ristorante_id = ANY(p_ristorante_ids)
          AND fa.deleted_at IS NULL
          AND fa.created_at >= p_inizio
        GROUP BY fa.ristorante_id
    ),
    m AS (
        SELECT mm.ristorante_id AS rid,
               sum(coalesce(mm.fatturato_iva10, 0) + coalesce(mm.fatturato_iva22, 0)
                   + coalesce(mm.altri_ricavi_noiva, 0)) AS netto,
               sum(coalesce(mm.costo_dipendenti, 0) + coalesce(mm.costo_personale_extra, 0)) AS personale
        FROM margini_mensili mm
        WHERE mm.ristorante_id = ANY(p_ristorante_ids)
          AND mm.anno = p_anno AND mm.mese = p_mese
        GROUP BY mm.ristorante_id
    )
    SELECT r AS ristorante_id,
           coalesce(f.n_fatture, 0)::bigint AS n_fatture,
           coalesce(f.n_needs_review, 0)::bigint AS n_needs_review,
           coalesce(m.netto, 0)::numeric AS netto,
           coalesce(m.personale, 0)::numeric AS personale
    FROM unnest(p_ristorante_ids) AS r
    LEFT JOIN f ON f.rid = r
    LEFT JOIN m ON m.rid = r;
$function$;

REVOKE ALL ON FUNCTION public.gruppo_salute_componenti(uuid[], timestamptz, int, int) FROM public, anon, authenticated;
