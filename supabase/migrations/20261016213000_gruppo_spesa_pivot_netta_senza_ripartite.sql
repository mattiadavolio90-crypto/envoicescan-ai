-- Spesa per PV della catena: le note di credito scalano, le fatture ripartite no.
--
-- Audit di ottobre 2026, due difetti della stessa RPC:
--
-- * F1a-02: una fattura ripartita sul gruppo (`ripartita_su_gruppo`) che vive su
--   un PV, non sulla sede tecnica, era contata intera nella sua colonna E come
--   quote su tutte (gruppo.py aggiunge `_righe_quote_gruppo`): 456,30 EUR doppi a
--   gennaio 2026 su una catena. I costi di Margini e Home la escludevano gia'
--   (`costi_automatici_mensili`); qui mancava il filtro.
-- * F4 (#17): `totale_riga > 0` scartava note di credito e sconti, che Analisi
--   Fatture invece sottrae: stesse sedi e stesso periodo davano 3.543.394 EUR in
--   catena e 3.432.058 EUR sommando le sedi. Decisione di Mattia (16/10/2026):
--   si sottraggono anche qui, i due numeri devono coincidere.
--
-- `gruppo_peso_categoria` riceve solo il filtro sulle ripartite: e' il peso di una
-- categoria sul F&B della sede, gli importi negativi li tiene fuori di proposito
-- (una percentuale di peso negativa non ha senso a video).
--
-- Firma, tipo di ritorno, SECURITY DEFINER e search_path invariati: CREATE OR
-- REPLACE tiene i GRANT esistenti.

CREATE OR REPLACE FUNCTION public.gruppo_spesa_pivot(
    p_ristorante_ids uuid[], p_dimensione text, p_data_da date, p_data_a date,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, dim_val text, totale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        COALESCE(
            NULLIF(CASE WHEN p_dimensione = 'fornitore' THEN f.fornitore ELSE f.categoria END, ''),
            'N/D'
        ) AS dim_val,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND NOT f.oscurata
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)
      AND f.totale_riga <> 0
      AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
      AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
      AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
    GROUP BY f.ristorante_id, dim_val;
$function$;

CREATE OR REPLACE FUNCTION public.gruppo_peso_categoria(
    p_ristorante_ids uuid[], p_data_da date, p_data_a date,
    p_escludi_da_verificare boolean DEFAULT false
)
 RETURNS TABLE(ristorante_id uuid, categoria text, spesa numeric, peso_perc numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH righe AS (
        SELECT
            f.ristorante_id AS rid,
            f.categoria AS cat,
            SUM(f.totale_riga) AS tot
        FROM fatture f
        WHERE f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND NOT f.oscurata
          AND f.categoria <> 'Da Classificare'
          AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
          AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)
          AND f.totale_riga > 0
          AND UPPER(f.categoria) NOT IN (
                'SERVIZI E CONSULENZE',
                'UTENZE E LOCALI',
                'MANUTENZIONE E ATTREZZATURE',
                'RAPPRESENTANZA',
                'MATERIALE DI CONSUMO'
          )
          AND f.categoria NOT LIKE '%NOTE E DICITURE%'
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
          AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
        GROUP BY 1, 2
    ),
    tot_pv AS (
        SELECT rid, SUM(tot) AS tot_fb FROM righe GROUP BY 1
    )
    SELECT
        r.rid AS ristorante_id,
        r.cat AS categoria,
        r.tot AS spesa,
        (100.0 * r.tot / t.tot_fb)::numeric AS peso_perc
    FROM righe r
    JOIN tot_pv t ON t.rid = r.rid
    WHERE t.tot_fb > 0;
$function$;
