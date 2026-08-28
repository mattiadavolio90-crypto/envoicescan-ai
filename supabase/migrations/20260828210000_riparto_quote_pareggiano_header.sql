-- Le quote di un costo di gruppo devono sommare all'importo del costo.
--
-- Audit 2026-08, finding F-DRIFT. Misurato sul DB live: 19 costi su 156 avevano
-- somma quote != importo_totale (scarto max 1 centesimo, 19 centesimi in tutto su
-- 67.591,75 EUR). Quel centesimo non resta nella tabella: riparto_quote_mensili
-- somma le quote dentro margini_mensili, quindi entra nel MOL mostrato al cliente.
--
-- CAUSA, riprodotta eseguendo (non dedotta):
-- `esplodi_quote_per_categoria(forza=True)` ricompone la quota di ogni sede
-- sommandone le porzioni per-categoria, e quella somma fa RIEMERGERE i mezzi
-- centesimi che l'esplosione precedente aveva diviso. Due sedi al 50% di 2,95
-- tornano 1,475 ciascuna -> arrotondate 1,48 + 1,48 = 2,96.
-- Il ramo che pareggia le quote-sede girava SOLO sotto `riallinea_al_netto`, cioe'
-- quando header e righe divergono: su questi costi coincidevano gia', quindi non
-- pareggiava nessuno. Tutti e 19 portano l'updated_at del batch di ri-esplosione
-- del 27/8 fra le 10:38 e le 10:40 -- non e' storia remota, e' codice vivo.
--
-- L'ipotesi a verbale in fase di planning (i round() per-categoria di
-- riparto.py:1231-1253) era sbagliata: quello e' codice di LETTURA, non scrive.
--
-- COSA FA QUESTA MIGRATION, e cosa NON fa:
--  1. sana i 19 gia' scritti (il codice non puo' riparare il passato);
--  2. aggiunge la classe `quote_non_pareggiano` a v_riparto_incoerenze.
--
-- NON aggiunge un CHECK ne' un RAISE EXCEPTION nelle RPC, ed e' una scelta:
-- `sostituisci_quote_riparto` sta nell'hot-path del worker
-- (worker/queue_processor.py:976). La migration 20260827214500 di ieri ha deciso
-- esattamente questo per il caso gemello ("non deve far fallire il worker in
-- hot-path: va segnalato dalla view, non bloccato dal DB"), e due migration
-- consecutive non possono esprimere politiche opposte sullo stesso dato. Il
-- fix vero sta nel codice (services/riparto_service.py, ramo `else`); qui si
-- rende l'eventuale residuo VISIBILE invece che silenzioso.

BEGIN;

-- ── 1. Sanatoria dei 19 storici ─────────────────────────────────────────────
-- Lo scarto va sulla quota di modulo maggiore, UNA sola riga per costo: e' la
-- convenzione gia' usata dal codice ("l'ultima assorbe") e il centesimo finisce
-- dove incide meno in percentuale.
WITH sbilanciati AS (
    SELECT c.id AS riparto_id,
           c.importo_totale,
           round(SUM(q.quota_importo), 2) AS somma_quote
    FROM public.riparto_costi_catena c
    JOIN public.riparto_costi_catena_quote q ON q.riparto_id = c.id
    GROUP BY c.id, c.importo_totale
    HAVING round(SUM(q.quota_importo), 2) <> c.importo_totale
),
da_correggere AS (
    SELECT DISTINCT ON (s.riparto_id)
           q.id AS quota_id,
           q.quota_importo + (s.importo_totale - s.somma_quote) AS nuovo_importo
    FROM sbilanciati s
    JOIN public.riparto_costi_catena_quote q ON q.riparto_id = s.riparto_id
    -- Per VALORE ASSOLUTO: su un header negativo (nota di credito) la quota
    -- "piu' grande" in senso algebrico e' la meno negativa. Lo scarto deve andare
    -- dove incide meno in percentuale, cioe' sulla quota di modulo maggiore.
    ORDER BY s.riparto_id, abs(q.quota_importo) DESC, q.id
)
UPDATE public.riparto_costi_catena_quote q
SET quota_importo = d.nuovo_importo
FROM da_correggere d
WHERE q.id = d.quota_id;
-- Nessun filtro sul segno: il CHECK (quota_importo >= 0) e' stato RIMOSSO il 27/8
-- da 20260827214500_riparto_consenti_note_credito.sql, proprio perche' una nota di
-- credito porta quote negative. Un filtro `>= 0` non proteggerebbe da niente e
-- farebbe danno all'opposto: su un header negativo (ne esistono 6 live) scarterebbe
-- in silenzio la correzione, lasciando il costo sbilanciato senza segnalarlo.

-- ── 2. La quinta classe di incoerenza ───────────────────────────────────────
CREATE OR REPLACE VIEW public.v_riparto_incoerenze AS
-- Classe 1: fatture vive marcate ripartite senza un riparto dietro.
SELECT
    f.user_id,
    'orfano'::text AS tipo_incoerenza,
    f.file_origine,
    NULL::uuid AS riparto_id,
    f.fornitore,
    round(sum(f.totale_riga)::numeric, 2) AS importo,
    min(f.data_documento) AS data_documento
FROM public.fatture f
WHERE f.ripartita_su_gruppo = true
  AND f.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.riparto_costi_catena r
      WHERE r.user_id = f.user_id AND r.file_origine = f.file_origine
  )
GROUP BY f.user_id, f.file_origine, f.fornitore

UNION ALL

-- Classe 2: riparti la cui fattura non ha più alcuna riga viva.
SELECT
    r.user_id,
    'riparto_senza_documento'::text AS tipo_incoerenza,
    r.file_origine,
    r.id AS riparto_id,
    r.fornitore,
    r.importo_totale AS importo,
    make_date(r.anno, r.mese, 1) AS data_documento
FROM public.riparto_costi_catena r
WHERE r.file_origine IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.fatture f
      WHERE f.user_id = r.user_id
        AND f.file_origine = r.file_origine
        AND f.deleted_at IS NULL
  )

UNION ALL

-- Classe 3 (nuova): header senza alcuna riga quota. Il costo resta nel totale del
-- gruppo ma non arriva a nessuna sede — né in margini_mensili né in Analisi Fatture.
-- esplodi_quote_per_categoria non lo ripara da solo: esce a `if not quote`.
-- Caso live: AUTOSTRADE luglio (riparto a8143a95), 96,80 € netti mai distribuiti.
SELECT
    r.user_id,
    'riparto_senza_quote'::text AS tipo_incoerenza,
    r.file_origine,
    r.id AS riparto_id,
    r.fornitore,
    r.importo_totale AS importo,
    make_date(r.anno, r.mese, 1) AS data_documento
FROM public.riparto_costi_catena r
WHERE NOT EXISTS (
      SELECT 1 FROM public.riparto_costi_catena_quote q WHERE q.riparto_id = r.id
  )

UNION ALL

-- Classe 4 (nuova): header con segno opposto al netto reale delle righe, oppure
-- netto reale ~0 con header non nullo. È la firma di una nota di credito ripartita
-- come costo positivo: il gruppo paga due volte invece di ricevere il rimborso.
-- Con i CHECK rimossi sopra, esplodi_quote_per_categoria riscrive il segno giusto
-- all'atterraggio delle righe; questa classe intercetta lo storico e ogni caso che
-- l'atterraggio non ha ricalcolato.
SELECT
    x.user_id,
    'riparto_segno_incoerente'::text AS tipo_incoerenza,
    x.file_origine,
    x.riparto_id,
    x.fornitore,
    x.netto_reale AS importo,
    make_date(x.anno, x.mese, 1) AS data_documento
FROM (
    SELECT
        r.user_id, r.id AS riparto_id, r.file_origine, r.fornitore, r.anno, r.mese,
        r.importo_totale,
        round(sum(f.totale_riga)::numeric, 2) AS netto_reale
    FROM public.riparto_costi_catena r
    JOIN public.fatture f
      ON f.user_id = r.user_id
     AND f.file_origine = r.file_origine
     AND f.deleted_at IS NULL
    WHERE r.origine = 'fattura'
    GROUP BY r.user_id, r.id, r.file_origine, r.fornitore, r.anno, r.mese, r.importo_totale
) x
WHERE sign(x.netto_reale) <> sign(x.importo_totale)
   OR (abs(x.netto_reale) < 0.01 AND abs(x.importo_totale) >= 0.01)

UNION ALL

-- Classe 5 (nuova, audit 2026-08 F-DRIFT): somma delle quote diversa dall'header.
-- Lo scarto entra nel MOL via riparto_quote_mensili, che somma le quote dentro
-- margini_mensili: non resta un dettaglio della tabella riparto.
-- Soglia 0,005: le quote sono NUMERIC(12,2), quindi qualunque scarto reale e' di
-- almeno un centesimo e viene intercettato; sotto c'e' solo rumore di
-- rappresentazione. Una soglia a 0,01 avrebbe lasciato passare tutti e 19 i casi
-- veri, che valgono esattamente un centesimo.
SELECT
    y.user_id,
    'quote_non_pareggiano'::text AS tipo_incoerenza,
    y.file_origine,
    y.riparto_id,
    y.fornitore,
    y.scarto AS importo,
    make_date(y.anno, y.mese, 1) AS data_documento
FROM (
    SELECT
        r.user_id, r.id AS riparto_id, r.file_origine, r.fornitore, r.anno, r.mese,
        round(SUM(q.quota_importo), 2) - r.importo_totale AS scarto
    FROM public.riparto_costi_catena r
    JOIN public.riparto_costi_catena_quote q ON q.riparto_id = r.id
    GROUP BY r.user_id, r.id, r.file_origine, r.fornitore, r.anno, r.mese, r.importo_totale
) y
WHERE abs(y.scarto) >= 0.005;

COMMENT ON VIEW public.v_riparto_incoerenze IS
    'Sola lettura. Cinque classi di incoerenza sulle fatture di gruppo: '
    'orfano (fattura marcata ripartita senza riparto -> costo sparito dal MOL); '
    'riparto_senza_documento (riparto senza righe vive -> costo fantasma); '
    'riparto_senza_quote (header senza quote -> costo che non arriva a nessuna sede); '
    'riparto_segno_incoerente (header di segno opposto al netto reale -> nota di '
    'credito contata come costo); '
    'quote_non_pareggiano (somma quote != header -> lo scarto entra nel MOL via '
    'riparto_quote_mensili). Base per GET /api/admin/riparto/incoerenze e per il '
    'workflow di alert giornaliero. Non modifica mai dati: la correzione resta un '
    'passo applicativo esplicito.';

-- SECURITY INVOKER esplicito: senza, CREATE VIEW eredita SECURITY DEFINER dal ruolo
-- di chi la crea, che bypasserebbe RLS. Stessa ragione di 20260827214500.
ALTER VIEW public.v_riparto_incoerenze SET (security_invoker = true);

COMMIT;
