-- Le cauzioni (depositi sui vuoti) escono dai prezzi di catena, come
-- dall'Osservatorio del PV (`VOCE_NON_PREZZO_REGEX` in utils/voci_prezzo.py): un
-- deposito vale 0,03 o 960 EUR a seconda dei fusti consegnati, e su OFFSIDE
-- «ADDEBITO CAUZIONI» (in VARIE BAR per scelta del cliente) ribaltava
-- l'impatto/mese da +55 a -599 EUR e faceva da solo 5.607 EUR di «pagato in
-- piu'». «CAUZION» e' l'unico pattern senza falsi positivi su tutto il DB
-- (11/10/2026): «VUOTO» prende i croissant vuoti, «TRASPORTO» il mango.
--
-- Firma invariata: CREATE OR REPLACE, nessun DROP, nessun ordine obbligato col
-- deploy (la versione precedente resta valida finche' il codice nuovo non arriva).

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
            upper(regexp_replace(f.descrizione, '^\s+|\s+$', '', 'g')) AS desc_key,
            upper(regexp_replace(f.fornitore, '^\s+|\s+$', '', 'g')) AS forn_key,
            f.descrizione,
            f.fornitore,
            f.prezzo_unitario,
            COALESCE(f.quantita, 1) AS quantita,
            f.data_documento,
            f.categoria,
            f.file_origine
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
    ordinate AS (
        SELECT
            r.*,
            row_number() OVER (
                PARTITION BY r.ristorante_id, r.desc_key, r.forn_key
                ORDER BY r.data_documento DESC, r.id DESC
            ) AS rn
        FROM righe r
    ),
    coppie AS (
        SELECT
            o.ristorante_id,
            o.desc_key,
            o.forn_key,
            mode() WITHIN GROUP (ORDER BY o.descrizione COLLATE "C") AS descrizione,
            mode() WITHIN GROUP (ORDER BY o.fornitore COLLATE "C") AS fornitore,
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
        GROUP BY o.ristorante_id, o.desc_key, o.forn_key
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

-- Le default privileges del progetto concedono EXECUTE ad anon e authenticated a
-- ogni funzione nuova: grant nominali, il REVOKE dal solo PUBLIC non li toglie.
REVOKE ALL ON FUNCTION public.gruppo_prezzi_catena(uuid[], date, date, text[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gruppo_prezzi_catena(uuid[], date, date, text[]) TO service_role;
