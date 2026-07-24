-- RPC riparto_quote_mensili: instradamento F&B vs Spese PER CATEGORIA della quota.
--
-- Cambio rispetto alla versione 20260714140000 (una sola riga di logica, il resto
-- IDENTICO): l'aggregazione quote_agg non usa più SOLO il `tipo` del riparto padre,
-- ma:
--   - se la quota ha `categoria` valorizzata → il secchio (fb/spese) si decide con
--     _riparto_categoria_is_fb(categoria)  [modello nuovo Voce 6, per-categoria];
--   - se `categoria` è NULL → si usa il `tipo` del riparto padre  [modello legacy,
--     IDENTICO a prima: i 137 riparti esistenti e ogni cliente non-catena non cambiano].
--
-- Tutto il resto (azzeramento sedi non più coperte, ricalcolo costi_fb_totali/
-- fatturato_netto/primo_margine/mol, ON CONFLICT su margini_mensili) è invariato:
-- il MOL è ricalcolato con la STESSA formula, cambiano solo i due addendi
-- quote_riparto_fb / quote_riparto_spese quando le quote sono per-categoria.

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
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;

    FOR r IN
        WITH quote_agg AS (
            SELECT
                q.ristorante_id,
                -- Secchio F&B: quota per-categoria F&B, OPPURE quota legacy (categoria
                -- NULL) di un riparto tipo='fb'. Le due condizioni sono mutuamente
                -- esclusive per una data quota, quindi niente doppio conteggio.
                COALESCE(SUM(q.quota_importo) FILTER (
                    WHERE (q.categoria IS NOT NULL AND public._riparto_categoria_is_fb(q.categoria))
                       OR (q.categoria IS NULL AND rc.tipo = 'fb')
                ), 0) AS q_fb,
                -- Secchio Spese: quota per-categoria NON-F&B (spese, Da Classificare,
                -- NOTE, ignoti), OPPURE quota legacy di un riparto tipo='generale'.
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
                - (COALESCE(mm.costo_dipendenti,0) + COALESCE(mm.costo_personale_extra,0)), 2),
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
