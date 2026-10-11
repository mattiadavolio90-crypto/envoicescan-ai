-- Le quote di riparto «Da Classificare» restano FUORI dai margini (11/10/2026).
--
-- Regola di dominio 1: una riga «Da Classificare» non entra nei margini finche'
-- qualcuno non la classifica. Le RPC dei costi di sede (costi_automatici_mensili e
-- _gruppo) la escludono gia'; riparto_quote_mensili invece metteva la sua quota
-- fra le spese generali (NOT _riparto_categoria_is_fb), perche' «non food» e
-- «spesa generale» non sono la stessa cosa. Misurato sul live l'11/10: OFFSIDE e
-- OVERTIME, agosto 3,83 + 3,83 e settembre 8,19 + 8,18 EUR di quote «Da
-- Classificare» contate come spese. Le quote restano nella tabella (si vedono
-- in coda come le righe): cambia solo la somma che finisce in margini_mensili.
--
-- Corpo dal LIVE (pg_get_functiondef dell'11/10/2026, identico a
-- 20261004083133): l'unico cambio e' la condizione sul FILTER di q_spese.
-- Firma e RETURNS invariati, nessun DROP. Dopo l'applicazione i mesi con quote
-- «Da Classificare» vanno ricalcolati: SELECT public.riparto_quote_mensili(...).

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
                    WHERE (q.categoria IS NOT NULL
                           AND q.categoria <> 'Da Classificare'
                           AND NOT public._riparto_categoria_is_fb(q.categoria))
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
