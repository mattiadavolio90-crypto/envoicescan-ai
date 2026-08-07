-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: RPC scadenziario_fatture_aggregate — aggregazione SQL per lo Scadenziario
-- ═══════════════════════════════════════════════════════════════════════════════
-- PERFORMANCE: get_documenti_scadenziario() (services/documenti_service.py) faceva
-- full-load paginato (1000 righe/round-trip) di TUTTE le righe `fatture` del gruppo,
-- poi aggregava in Python per (file_origine, ristorante_id). Per SUSHILAND (4 sedi,
-- ~25.000 righe attive) questo superava il timeout della pagina "Gestione Fatture —
-- Gruppo" (8s hardcoded), che tornava 0 fatture con fallback silenzioso. Per OFFSIDE
-- (~3.700 righe) restava sotto soglia per puro caso di volume più basso.
--
-- Questa RPC fa lo STESSO aggregato dello Step 1+2 di get_documenti_scadenziario
-- lato DB in una query: SUM(totale_riga) per (file_origine, ristorante_id), con
-- fornitore/tipo_documento/data_documento/created_at presi dalla riga con
-- created_at più basso del gruppo (deterministico — la versione Python prendeva
-- "la prima riga incontrata", che con .range() senza .order() non era garantito).
--
-- Non copre Step 3-5 (merge con fatture_documenti, regole fornitore per scadenza
-- effettiva, calcolo stato_scadenza): quella logica resta in Python perché opera
-- già sul set aggregato (una riga per documento, non per riga fattura) — il suo
-- costo non è mai stato il problema di performance.
--
-- Guardia ownership coerente con le altre RPC (auth custom: uid()=NULL → inerte
-- per anon; l'app chiama via service_role). SET search_path fisso. EXECUTE solo
-- a service_role.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.scadenziario_fatture_aggregate(
    p_user_id uuid,
    p_ristorante_ids uuid[]
)
RETURNS TABLE (
    file_origine text,
    ristorante_id uuid,
    fornitore text,
    tipo_documento text,
    totale_documento numeric,
    data_documento date,
    created_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    RETURN QUERY
    WITH base AS (
        SELECT
            btrim(f.file_origine)                    AS file_origine,
            f.ristorante_id,
            COALESCE(f.fornitore, 'Sconosciuto')      AS fornitore,
            COALESCE(f.tipo_documento, 'TD01')        AS tipo_documento,
            COALESCE(f.totale_riga, 0)                AS totale_riga,
            f.data_documento,
            f.created_at
        FROM public.fatture f
        WHERE f.user_id = p_user_id
          AND f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.file_origine IS NOT NULL
          AND btrim(f.file_origine) <> ''
    ),
    prima_riga AS (
        SELECT DISTINCT ON (b.file_origine, b.ristorante_id)
            b.file_origine,
            b.ristorante_id,
            b.fornitore,
            b.tipo_documento,
            b.data_documento,
            b.created_at
        FROM base b
        ORDER BY b.file_origine, b.ristorante_id, b.created_at ASC NULLS LAST
    )
    SELECT
        p.file_origine,
        p.ristorante_id,
        p.fornitore,
        p.tipo_documento,
        ROUND(SUM(b.totale_riga), 2) AS totale_documento,
        p.data_documento,
        p.created_at
    FROM base b
    JOIN prima_riga p
      ON p.file_origine = b.file_origine AND p.ristorante_id = b.ristorante_id
    GROUP BY p.file_origine, p.ristorante_id, p.fornitore, p.tipo_documento, p.data_documento, p.created_at;
END;
$function$;

REVOKE ALL ON FUNCTION public.scadenziario_fatture_aggregate(uuid, uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.scadenziario_fatture_aggregate(uuid, uuid[]) TO service_role;
