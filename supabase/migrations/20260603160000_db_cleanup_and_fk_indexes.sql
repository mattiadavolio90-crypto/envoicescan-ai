-- Cleanup DB (post-audit DATABASE 03/06/2026), basato su uso reale degli indici e dati live.

-- 1) Drop indice mai usato: idx_fatture_sconto_piva = 0 scansioni (pg_stat_user_indexes).
--    NB: gli indici che l'audit teorico suggeriva di togliere (user_id, user_ristorante)
--    risultano tra i PIU' usati -> NON toccati.
DROP INDEX IF EXISTS public.idx_fatture_sconto_piva;

-- 2) Drop tabelle legacy VUOTE (0 righe, nessun riferimento nel codice runtime).
DROP TABLE IF EXISTS public.articoli;
DROP TABLE IF EXISTS public.fatture_processate;

-- 3) Drop backup datati (snapshot di gennaio, contengono dati utente reali -> igiene GDPR).
DROP TABLE IF EXISTS public.fatture_backup_20260130;
DROP TABLE IF EXISTS public.users_backup_20260129;
DROP TABLE IF EXISTS public.users_backup_20260130;

-- 4) Indici sulle FK non indicizzate (lookup inverse / ON DELETE piu' veloci).
CREATE INDEX IF NOT EXISTS idx_custom_tag_suggestions_target_tag_id
  ON public.custom_tag_suggestions (target_tag_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_ristorante_id
  ON public.marketplace_leads (ristorante_id);
CREATE INDEX IF NOT EXISTS idx_ricavi_ragione_sociale_map_ristorante_id
  ON public.ricavi_ragione_sociale_map (ristorante_id);
