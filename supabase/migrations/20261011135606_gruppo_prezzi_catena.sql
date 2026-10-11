-- Prezzi di catena: una riga per sede x prodotto x fornitore, gia' aggregata.
--
-- Serve alla scheda «Prezzi» di Analisi catena (/api/gruppo/prezzi). Il router
-- della catena non carica righe di fattura in Python: questa funzione riduce le
-- righe del periodo a una per coppia, e il worker ci calcola sopra la variazione
-- con la STESSA funzione dell'Osservatorio del PV (`_deriva_variazione`).
--
-- I filtri sono quelli di `_calcola_variazioni_prezzi_sync` (routers/prezzi.py),
-- e le differenze di scrittura sono volute:
--   - categoria NULL resta dentro, come `~isin()` in pandas: un `NOT (x = ANY())`
--     nudo su NULL dara' NULL e la scarterebbe;
--   - la nota di credito si riconosce col regex di `_NC_TIPO_REGEX`, con `\m`/`\M`
--     al posto di `\b` (che in Postgres e' il backspace, non il bordo di parola);
--   - la chiave e' UPPER+TRIM come `.str.strip().str.upper()`;
--   - `mode()` ordinato COLLATE "C" sceglie fra i pari merito come pandas, che
--     ordina per codepoint.
--
-- UN valore jsonb, non un insieme di righe. Misurato l'11/10/2026 sull'account da
-- 5 sedi: 5.071 coppie, cioe' 6 pagine da 1000 (il `max_rows` di PostgREST), e
-- la funzione — SECURITY DEFINER, quindi mai inlined — si rieseguiva intera a
-- ogni pagina: 0,7 s x 6 = 4,8 s. Un valore solo e' una chiamata sola, e non ha
-- un tetto di righe da cui farsi troncare in silenzio.
--
-- Restano fuori le coppie che non servono a nessuna delle due viste: comprate
-- una volta sola E da una sola sede (niente variazione, niente confronto).
-- `acquisti` conta comunque tutte le righe del periodo: distingue «nessun
-- acquisto» da «prezzi stabili».
--
-- Nome nuovo, non `gruppo_prezzi_coppie`: la prima stesura di questa funzione
-- (stesso giorno, una TABLE invece di un jsonb) e' stata applicata al live col
-- nome vecchio, e cambiarne il tipo di ritorno richiede un DROP che dal MCP
-- viene rifiutato. Quella resta sul live ORFANA — mai chiamata dal codice,
-- EXECUTE solo a service_role — finche' non si lancia dall'SQL Editor:
--   DROP FUNCTION IF EXISTS public.gruppo_prezzi_coppie(uuid[], date, date, text[]);

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
