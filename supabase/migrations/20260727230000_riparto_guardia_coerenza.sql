-- Rete di sicurezza sulle fatture di gruppo (Voce 7, 27/7): view diagnostica sola
-- lettura per rendere visibili senza query manuali le due classi di incoerenza già
-- osservate live su OFFSIDE tra riparto_costi_catena e fatture:
--
--   1. ORFANO: fattura marcata ripartita_su_gruppo=true, VIVA, ma nessun riparto
--      esiste per il suo file_origine → il costo sparisce sia dalla porta automatica
--      sia da ogni PV (caso FASTWEB 362,04€, 22/7).
--   2. RIPARTO SENZA DOCUMENTO: riparto_costi_catena esiste ma non resta alcuna riga
--      viva con quel file_origine → il MOL conta comunque le quote via
--      margini_mensili (materializzato), costo fantasma (4 Amazon, 182,64€/sede).
--
-- Principio "la fattura resta sacra": nessun trigger che cancella o riscrive righe.
-- La view espone solo lo stato; la correzione applicativa vive nel codice Python
-- (verifica_documento_vivo, _pulisci_riparto_orfano, _smarca_fatture_senza_riparto).

BEGIN;

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
  );

COMMENT ON VIEW public.v_riparto_incoerenze IS
    'Sola lettura: fatture di gruppo marcate ripartita_su_gruppo senza riparto dietro '
    '(orfano) e riparti_costi_catena senza più alcuna riga viva (riparto_senza_documento). '
    'Base per GET /api/admin/riparto/incoerenze e per il workflow di alert giornaliero. '
    'Non modifica mai dati: la correzione resta un passo applicativo esplicito.';

-- SECURITY INVOKER esplicito: senza, CREATE VIEW eredita SECURITY DEFINER dal ruolo
-- di chi la crea, che bypasserebbe RLS come le 14 view chiuse nell'audit anti-hacker
-- del 20/6 (project_audit_antihacker_2026-06-20). Qui l'accesso passa comunque solo
-- dal worker con service_role_key, ma la view resta corretta per costruzione.
ALTER VIEW public.v_riparto_incoerenze SET (security_invoker = true);

COMMIT;
