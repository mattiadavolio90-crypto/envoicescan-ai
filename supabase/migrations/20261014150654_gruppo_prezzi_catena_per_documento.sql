-- Un acquisto = una fattura anche in catena (gemella di `una_riga_per_documento`
-- in utils/voci_prezzo.py, usata dall'Osservatorio del PV).
-- Lo stesso prodotto su piu' righe della stessa fattura contava come piu'
-- acquisti: misurato il 14/10/2026 su 2.947 prodotti di catena, in 556 l'ultimo
-- e il penultimo «acquisto» stavano nella stessa fattura (522 a prezzo uguale:
-- variazione vera nascosta), a soglia 5% 34 variazioni nascoste e 13 finte.
-- La CTE `documenti` fonde per sede+prodotto+fornitore+file+data+unita' di
-- misura (unita' diverse NON si fondono, decisione di Mattia), con prezzo
-- ponderato sulle quantita' positive (media semplice se nessuna lo e'),
-- arrotondato a 6 decimali come pandas; righe senza file restano acquisti a se'. Spareggio a parita' di
-- data: file, poi unita', COLLATE "C" (= ordine di codepoint di Python).
-- I nomi a video (`mode()`) restano calcolati sulle RIGHE, come in pandas.
-- `acquisti` resta il conteggio delle righe del periodo (lo legge solo il
-- frontend per distinguere zero da non zero).
--
-- Firma invariata: CREATE OR REPLACE. Da applicare sul live AL MOMENTO DEL PUSH
-- del worker che aggrega allo stesso modo: prima, PV e catena mostrerebbero
-- numeri diversi per la stessa sede.

CREATE OR REPLACE FUNCTION public.gruppo_prezzi_catena(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date,
    p_categorie_escluse text[]
)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    WITH righe AS (
        SELECT
            f.id,
            f.ristorante_id,
            upper(regexp_replace(
                regexp_replace(f.descrizione, '\s*\mORDER\s*\d+(\s*\(\s*\d+\s*\))?', '', 'gi'),
                '^\s+|\s+$', '', 'g'
            )) AS desc_key,
            upper(regexp_replace(f.fornitore, '^\s+|\s+$', '', 'g')) AS forn_key,
            f.descrizione,
            f.fornitore,
            f.prezzo_unitario,
            COALESCE(f.quantita, 1) AS quantita,
            f.data_documento,
            f.categoria,
            f.file_origine,
            CASE WHEN f.file_origine IS NULL OR btrim(f.file_origine) = '' THEN '' ELSE f.file_origine END AS file_key,
            CASE WHEN f.file_origine IS NULL OR btrim(f.file_origine) = '' THEN f.id ELSE -1 END AS solo,
            upper(regexp_replace(COALESCE(f.unita_misura, ''), '^\s+|\s+$', '', 'g')) AS unita_key
        FROM fatture f
        WHERE f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND NOT f.oscurata
          AND f.data_documento BETWEEN p_data_da AND p_data_a
          AND f.prezzo_unitario > 0
          AND (f.categoria IS NULL OR NOT (f.categoria = ANY(p_categorie_escluse)))
          AND upper(COALESCE(f.tipo_documento, '')) !~ 'TD04|NOTA DI CREDITO|NOTA CREDITO|\mNC\M|CREDIT'
          AND upper(f.descrizione) !~ 'CAUZION'
    ),
    documenti AS (
        SELECT
            r.ristorante_id, r.desc_key, r.forn_key, r.file_key, r.data_documento, r.unita_key, r.solo,
            -- Pesano le sole quantita' positive; 6 decimali come pandas
            -- (`round(6)` in una_riga_per_documento): senza, il float di
            -- Python e il numeric esatto finivano ai due lati di una soglia.
            round(CASE WHEN sum(r.quantita) FILTER (WHERE r.quantita > 0) > 0
                 THEN sum(r.prezzo_unitario * r.quantita) FILTER (WHERE r.quantita > 0)
                      / sum(r.quantita) FILTER (WHERE r.quantita > 0)
                 ELSE avg(r.prezzo_unitario) END, 6) AS prezzo_unitario,
            sum(r.quantita) AS quantita,
            max(r.categoria COLLATE "C") AS categoria,
            CASE WHEN r.solo < 0 THEN r.file_key END AS file_origine
        FROM righe r
        GROUP BY r.ristorante_id, r.desc_key, r.forn_key, r.file_key, r.data_documento, r.unita_key, r.solo
    ),
    ordinate AS (
        SELECT
            d.*,
            row_number() OVER (
                PARTITION BY d.ristorante_id, d.desc_key, d.forn_key
                ORDER BY d.data_documento DESC, d.file_key COLLATE "C" DESC,
                         d.unita_key COLLATE "C" DESC, d.solo DESC
            ) AS rn
        FROM documenti d
    ),
    nomi AS (
        SELECT
            r.ristorante_id,
            r.desc_key,
            r.forn_key,
            mode() WITHIN GROUP (ORDER BY r.descrizione COLLATE "C") AS descrizione,
            mode() WITHIN GROUP (ORDER BY r.fornitore COLLATE "C") AS fornitore
        FROM righe r
        GROUP BY r.ristorante_id, r.desc_key, r.forn_key
    ),
    coppie AS (
        SELECT
            o.ristorante_id,
            o.desc_key,
            o.forn_key,
            n.descrizione,
            n.fornitore,
            count(*)::int AS n_acquisti,
            array_agg(o.prezzo_unitario ORDER BY o.rn DESC) FILTER (WHERE o.rn <= 5) AS ultimi_prezzi,
            avg(o.prezzo_unitario) AS media,
            avg(o.quantita) AS qta_media,
            sum(o.quantita) AS qta_totale,
            min(o.data_documento) AS prima_data,
            max(o.data_documento) AS ultima_data,
            max(o.data_documento) FILTER (WHERE o.rn = 2) AS penultima_data,
            max(o.categoria) FILTER (WHERE o.rn = 1) AS categoria,
            max(o.file_origine) FILTER (WHERE o.rn = 1) AS file_origine
        FROM ordinate o
        JOIN nomi n USING (ristorante_id, desc_key, forn_key)
        GROUP BY o.ristorante_id, o.desc_key, o.forn_key, n.descrizione, n.fornitore
    ),
    utili AS (
        SELECT c.*, count(*) OVER (PARTITION BY c.desc_key, c.forn_key) AS n_sedi
        FROM coppie c
    )
    SELECT jsonb_build_object(
        'acquisti', (SELECT count(*) FROM righe),
        'coppie', COALESCE(
            (SELECT jsonb_agg(to_jsonb(u) - 'n_sedi' ORDER BY u.ristorante_id, u.desc_key, u.forn_key)
             FROM utili u
             WHERE u.n_acquisti >= 2 OR u.n_sedi >= 2),
            '[]'::jsonb
        )
    );
$function$;

REVOKE ALL ON FUNCTION public.gruppo_prezzi_catena(uuid[], date, date, text[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_prezzi_catena(uuid[], date, date, text[]) TO service_role;
