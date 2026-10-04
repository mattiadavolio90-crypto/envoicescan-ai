-- Personale in tre voci che si sommano: Lordo + Ore extra + Chiamata (04/10/2026).
--
-- margini_mensili:
--   costo_dipendenti          = «Lordo» (ordinario)
--   costo_personale_extra     = «Ore extra»
--   costo_personale_chiamata  = «Chiamata» (NUOVA)
-- Il totale personale e' la somma delle tre ovunque: MOL, % personale, «personale
-- inserito». Un mese con la sola chiamata conta come personale inserito.
--
-- turni_personale.importo_chiamata (NUOVA) e' la gemella di importo_extra: la
-- quota chiamata compresa nel lordo_mensile. Qui si crea solo la colonna; il
-- codice dei turni la usa dallo step C2, quando giornalieri e riga mensile
-- convivono nello stesso mese (vedi il nuovo commento su `mensile`).
--
-- Le due funzioni SQL che sommano il personale si riscrivono a firma e RETURNS
-- invariati, dal corpo LIVE (pg_get_functiondef del 04/10/2026, identico
-- all'ultimo del repo salvo il messaggio d'errore di riparto, che il live ha
-- senza accento): l'unico cambio e' l'addendo costo_personale_chiamata.
--   - riparto_quote_mensili    (ultima: 20260724220100) -> nel mol
--   - gruppo_salute_componenti (ultima: 20260912075621) -> nella somma personale
--
-- Additiva e idempotente. Nessun DROP, nessuna firma cambia.

ALTER TABLE public.margini_mensili
    ADD COLUMN IF NOT EXISTS costo_personale_chiamata numeric(10,2) DEFAULT 0;

ALTER TABLE public.turni_personale
    ADD COLUMN IF NOT EXISTS importo_chiamata numeric(10,2);

COMMENT ON COLUMN public.margini_mensili.costo_dipendenti IS
    'Personale «Lordo»: costo ordinario del mese (EUR). Totale personale = costo_dipendenti + costo_personale_extra + costo_personale_chiamata.';
COMMENT ON COLUMN public.margini_mensili.costo_personale_extra IS
    'Personale «Ore extra»: straordinari del mese (EUR). Si somma a Lordo e Chiamata.';
COMMENT ON COLUMN public.margini_mensili.costo_personale_chiamata IS
    'Personale «Chiamata»: costo del personale a chiamata del mese (EUR). Totale personale = somma delle tre voci (Lordo + Ore extra + Chiamata).';
COMMENT ON COLUMN public.turni_personale.importo_chiamata IS
    'Quota chiamata del mese (EUR) da busta paga, compresa in lordo_mensile come importo_extra. Solo righe mensili.';
COMMENT ON COLUMN public.turni_personale.mensile IS
    'TRUE = riga aggregata mensile (totali da busta paga), non un turno giornaliero. Puo'' convivere con i turni giornalieri dello stesso dipendente/mese: per il costo vince lo stipendio del mese sul costo orario dei giornalieri.';


CREATE OR REPLACE FUNCTION public.riparto_quote_mensili(p_user_id uuid, p_anno integer, p_mese integer)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_touched INTEGER := 0;
    r RECORD;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non puo'' essere NULL';
    END IF;

    FOR r IN
        WITH quote_agg AS (
            SELECT
                q.ristorante_id,
                COALESCE(SUM(q.quota_importo) FILTER (
                    WHERE (q.categoria IS NOT NULL AND public._riparto_categoria_is_fb(q.categoria))
                       OR (q.categoria IS NULL AND rc.tipo = 'fb')
                ), 0) AS q_fb,
                COALESCE(SUM(q.quota_importo) FILTER (
                    WHERE (q.categoria IS NOT NULL AND NOT public._riparto_categoria_is_fb(q.categoria))
                       OR (q.categoria IS NULL AND rc.tipo = 'generale')
                ), 0) AS q_spese
            FROM public.riparto_costi_catena rc
            JOIN public.riparto_costi_catena_quote q ON q.riparto_id = rc.id
            WHERE rc.user_id = p_user_id
              AND rc.anno = p_anno
              AND rc.mese = p_mese
            GROUP BY q.ristorante_id
        ),
        sedi_da_azzerare AS (
            SELECT mm.ristorante_id, 0::numeric AS q_fb, 0::numeric AS q_spese
            FROM public.margini_mensili mm
            WHERE mm.user_id = p_user_id
              AND mm.anno = p_anno
              AND mm.mese = p_mese
              AND (COALESCE(mm.quote_riparto_fb, 0) <> 0 OR COALESCE(mm.quote_riparto_spese, 0) <> 0)
              AND mm.ristorante_id NOT IN (SELECT ristorante_id FROM quote_agg)
        )
        SELECT ristorante_id, q_fb, q_spese FROM quote_agg
        UNION ALL
        SELECT ristorante_id, q_fb, q_spese FROM sedi_da_azzerare
    LOOP
        INSERT INTO public.margini_mensili AS mm (
            user_id, ristorante_id, anno, mese,
            quote_riparto_fb, quote_riparto_spese, updated_at
        )
        VALUES (
            p_user_id, r.ristorante_id, p_anno, p_mese,
            r.q_fb, r.q_spese, now()
        )
        ON CONFLICT (ristorante_id, anno, mese) DO UPDATE
        SET quote_riparto_fb    = EXCLUDED.quote_riparto_fb,
            quote_riparto_spese = EXCLUDED.quote_riparto_spese,
            updated_at          = now();

        UPDATE public.margini_mensili mm
        SET
            costi_fb_totali = round(
                COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0), 2),
            fatturato_netto = round(
                COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22 + COALESCE(mm.altri_ricavi_noiva,0), 2),
            primo_margine = round(
                (COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22 + COALESCE(mm.altri_ricavi_noiva,0))
                - (COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0)), 2),
            mol = round(
                (COALESCE(mm.fatturato_iva10,0)/1.10 + COALESCE(mm.fatturato_iva22,0)/1.22 + COALESCE(mm.altri_ricavi_noiva,0))
                - (COALESCE(mm.costi_fb_auto,0) + COALESCE(mm.altri_costi_fb,0) + COALESCE(mm.quote_riparto_fb,0))
                - (COALESCE(mm.costi_spese_auto,0) + COALESCE(mm.altri_costi_spese,0) + COALESCE(mm.quote_riparto_spese,0))
                - (COALESCE(mm.costo_dipendenti,0) + COALESCE(mm.costo_personale_extra,0) + COALESCE(mm.costo_personale_chiamata,0)), 2),
            updated_at = now()
        WHERE mm.user_id = p_user_id
          AND mm.ristorante_id = r.ristorante_id
          AND mm.anno = p_anno
          AND mm.mese = p_mese;

        v_touched := v_touched + 1;
    END LOOP;

    RETURN v_touched;
END;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_salute_componenti(p_ristorante_ids uuid[], p_inizio timestamp with time zone, p_anno integer, p_mese integer)
 RETURNS TABLE(ristorante_id uuid, n_fatture bigint, n_needs_review bigint, netto numeric, personale numeric)
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
          AND NOT fa.oscurata
          AND fa.created_at >= p_inizio
        GROUP BY fa.ristorante_id
    ),
    m AS (
        SELECT mm.ristorante_id AS rid,
               sum(coalesce(mm.fatturato_iva10, 0) + coalesce(mm.fatturato_iva22, 0)
                   + coalesce(mm.altri_ricavi_noiva, 0)) AS netto,
               sum(coalesce(mm.costo_dipendenti, 0) + coalesce(mm.costo_personale_extra, 0)
                   + coalesce(mm.costo_personale_chiamata, 0)) AS personale
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


REVOKE ALL ON FUNCTION public.riparto_quote_mensili(uuid, integer, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gruppo_salute_componenti(uuid[], timestamp with time zone, integer, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.riparto_quote_mensili(uuid, integer, integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.gruppo_salute_componenti(uuid[], timestamp with time zone, integer, integer) TO service_role;
