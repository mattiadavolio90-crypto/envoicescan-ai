-- Riparto costi di gruppo: consentire le note di credito (TD04) e renderne
-- visibili le incoerenze residue.
--
-- PERCHÉ (27/8/2026, catena OFFSIDE)
-- In un conto MONO-sede una nota di credito si netta da sola: il parser inverte
-- il segno delle righe TD04 (services/invoice_service.py, nc_inverti_in_blocco) e
-- il costo mensile è una SUM pura di totale_riga (services/margine_service.py,
-- calcola_costi). Nessuna logica TD04 speciale: le righe negative sottraggono.
--
-- Il path di GRUPPO non poteva fare lo stesso: i CHECK (>= 0) su
-- riparto_costi_catena.importo_totale e riparto_costi_catena_quote.quota_importo
-- rifiutavano gli importi negativi. Risultato osservato su OFFSIDE: 6 note di
-- credito ripartite con header POSITIVO (il lordo provvisorio da coda) invece che
-- negativo → ~2.086 € di costo di troppo a carico dei 2 locali su feb/mar/giu.
-- Il backfill del netto (scripts/backfill_riparto_netto.py) le ha dovute saltare,
-- e esplodi_quote_per_categoria crashava sul constraint (IT05602710963_GGNTU,
-- netto -107,33).
--
-- COSA CAMBIA: si tolgono i due CHECK sul segno. La RPC riparto_quote_mensili
-- (20260724220100) somma già le quote senza abs(), quindi una quota negativa
-- riduce quote_riparto_* e il MOL del mese — esattamente come nel mono-sede.
--
-- COSA NON CAMBIA: quota_perc resta CHECK (>= 0 AND <= 100) — la percentuale di
-- una sede è sempre positiva, è l'importo a portare il segno.
--
-- PERCHÉ NON "<> 0": lo zero è un esito legittimo dello spezzamento per categoria.
-- Live c'è già una quota a 0,00 (riparto 2ca9bb34, residuo 0,01 € diviso 50/50 fra
-- due sedi): un CHECK (<> 0) l'avrebbe rifiutata in validazione. E un header a 0
-- (nota di credito che azzera esattamente un costo) non deve far fallire il worker
-- in hot-path: va segnalato dalla view qui sotto e chiuso dalla manutenzione.

BEGIN;

ALTER TABLE public.riparto_costi_catena
    DROP CONSTRAINT IF EXISTS riparto_costi_catena_importo_totale_check;

ALTER TABLE public.riparto_costi_catena_quote
    DROP CONSTRAINT IF EXISTS riparto_costi_catena_quote_quota_importo_check;

COMMENT ON COLUMN public.riparto_costi_catena.importo_totale IS
    'Netto della fattura-origine, con segno: negativo per una nota di credito (TD04), '
    'che così si netta nel mese come nel mono-sede. Zero ammesso (NC che azzera un '
    'costo): la view v_riparto_incoerenze lo segnala, non lo blocca il DB.';

COMMENT ON COLUMN public.riparto_costi_catena_quote.quota_importo IS
    'Quota della sede, con segno (negativa per una nota di credito). Zero ammesso: '
    'è un esito di arrotondamento normale nello spezzamento per categoria.';

-- ─────────────────────────────────────────────────────────────────────────────
-- v_riparto_incoerenze: due nuove classi, entrambe osservate live su OFFSIDE.
-- Le prime due (orfano, riparto_senza_documento) restano identiche a
-- 20260727230000: qui si aggiunge solo, non si tocca l'esistente.
-- ─────────────────────────────────────────────────────────────────────────────

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
   OR (abs(x.netto_reale) < 0.01 AND abs(x.importo_totale) >= 0.01);

COMMENT ON VIEW public.v_riparto_incoerenze IS
    'Sola lettura. Quattro classi di incoerenza sulle fatture di gruppo: '
    'orfano (fattura marcata ripartita senza riparto → costo sparito dal MOL); '
    'riparto_senza_documento (riparto senza righe vive → costo fantasma); '
    'riparto_senza_quote (header senza quote → costo che non arriva a nessuna sede); '
    'riparto_segno_incoerente (header di segno opposto al netto reale → nota di '
    'credito contata come costo). Base per GET /api/admin/riparto/incoerenze e per il '
    'workflow di alert giornaliero. Non modifica mai dati: la correzione resta un '
    'passo applicativo esplicito.';

-- SECURITY INVOKER esplicito: senza, CREATE VIEW eredita SECURITY DEFINER dal ruolo
-- di chi la crea, che bypasserebbe RLS come le 14 view chiuse nell'audit anti-hacker
-- del 20/6 (project_audit_antihacker_2026-06-20). Qui l'accesso passa comunque solo
-- dal worker con service_role_key, ma la view resta corretta per costruzione.
ALTER VIEW public.v_riparto_incoerenze SET (security_invoker = true);

COMMIT;
