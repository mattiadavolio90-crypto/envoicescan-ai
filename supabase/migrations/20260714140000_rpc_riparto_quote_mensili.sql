-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration: motore di aggregazione quote di riparto → margini_mensili
-- ═══════════════════════════════════════════════════════════════════════════════
-- Contesto: PIANO_OPERATIVO_RIPARTIZIONE_COSTI_CATENA.md (Fase 2, §1d).
--
-- Somma le quote di ripartizione (riparto_costi_catena_quote) per sede/anno/mese e
-- le scrive nelle colonne dedicate margini_mensili.quote_riparto_fb/spese, poi
-- RICALCOLA lo snapshot mol/costi/percentuali del record toccato — perché la vista
-- gruppo (gruppo.py) legge lo snapshot pre-aggregato margini_mensili.mol, non
-- ricalcola. Senza il ricalcolo, il MOL di gruppo resterebbe stantìo dopo un
-- riparto finché l'utente non risalva i margini di quella sede.
--
-- Gemella concettuale del modo in cui il worker margini alimenta altri_costi_*:
-- aggregazione SQL 1×, mai loop Python (regola catena "aggregazione, non loop").
--
-- Da chiamare dopo ogni scrittura riparto (crea/modifica/elimina/duplica) per le
-- sedi + periodo coinvolti. Idempotente: ricalcola sempre da zero le quote del
-- periodo, quindi doppie chiamate non accumulano.
--
-- Nota MOL: la formula replica services/routers/margini.py:save_margini
--   fatt_netto = iva10/1.10 + iva22/1.22 + altri_ricavi_noiva
--   costi_fb   = costi_fb_auto + altri_costi_fb + quote_riparto_fb
--   costi_spese= costi_spese_auto + altri_costi_spese + quote_riparto_spese
--   mol        = (fatt_netto - costi_fb) - costi_spese - (dipendenti + pers_extra)
-- ATTENZIONE: costi_fb_auto/costi_spese_auto qui sono lo SNAPSHOT salvato in
-- margini_mensili; il valore "vivo" è ricalcolato al load da costi_automatici_mensili.
-- Lo snapshot basta a tenere allineata la vista gruppo, che legge comunque lo snapshot.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.riparto_quote_mensili(
    p_user_id UUID,
    p_anno    INTEGER,
    p_mese    INTEGER
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_touched INTEGER := 0;
    r RECORD;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'p_user_id non può essere NULL';
    END IF;

    -- Somma quote per sede/tipo nel periodo. Una sede senza quote in questo mese
    -- deve comunque essere azzerata (es. dopo un elimina): per questo partiamo
    -- dalle sedi che hanno GIÀ un valore quote non-zero nel margine + quelle con
    -- quote nuove nel periodo, e per tutte riscriviamo il valore ricalcolato.
    FOR r IN
        WITH quote_agg AS (
            SELECT
                q.ristorante_id,
                COALESCE(SUM(q.quota_importo) FILTER (WHERE rc.tipo = 'fb'), 0)       AS q_fb,
                COALESCE(SUM(q.quota_importo) FILTER (WHERE rc.tipo = 'generale'), 0) AS q_spese
            FROM public.riparto_costi_catena rc
            JOIN public.riparto_costi_catena_quote q ON q.riparto_id = rc.id
            WHERE rc.user_id = p_user_id
              AND rc.anno = p_anno
              AND rc.mese = p_mese
            GROUP BY q.ristorante_id
        ),
        sedi_da_azzerare AS (
            -- Sedi che avevano quote nel margine ma non compaiono più in quote_agg
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
        -- Upsert del record margine con quote aggiornate + ricalcolo snapshot MOL.
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

        -- Ricalcola lo snapshot MOL/costi/percentuali del record appena toccato,
        -- includendo le nuove quote. Legge i valori correnti (fatturato, costi auto
        -- snapshot, altri costi manuali) e riscrive i campi derivati.
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
$$;

COMMENT ON FUNCTION public.riparto_quote_mensili(UUID, INTEGER, INTEGER) IS
    'Aggrega le quote di riparto costi di gruppo per sede nel periodo e le scrive in '
    'margini_mensili.quote_riparto_fb/spese, ricalcolando lo snapshot mol/costi. '
    'Chiamare dopo ogni scrittura riparto per il periodo coinvolto. Azzera le sedi '
    'che non hanno più quote (dopo elimina). Idempotente.';

REVOKE ALL ON FUNCTION public.riparto_quote_mensili(UUID, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.riparto_quote_mensili(UUID, INTEGER, INTEGER) TO service_role;
