-- RPC: costo F&B per (PV, anno, mese, categoria) per la finestra "Spreco per
-- categoria" della modalità catena.
--
-- Perché esiste: l'handler gruppo_spreco_categorie chiamava
-- _load_fatture_fb_per_categoria_e_mese una volta PER PV, e ognuna paginava le
-- righe a 1000 in un loop `while True`. Su un gruppo reale (3 PV, ~16.800 righe
-- nell'anno) sono ~18 round-trip HTTP verso PostgREST in serie, più gli override
-- mensili per PV: le query costano 1-5 ms l'una (misurato con EXPLAIN ANALYZE),
-- ma la latenza di rete moltiplicata per il numero di chiamate avvicina la
-- risposta al budget di 12s del proxy Next (WORKER_TIMEOUT_MS), che scaduto
-- diventa un 502 in faccia al cliente. Qui torna ~15 categorie × 12 mesi × N PV
-- in UNA chiamata, non decine di migliaia di righe da macinare in pandas.
--
-- Coerente con _load_fatture_fb_per_categoria_e_mese (services/fastapi_worker.py),
-- di cui replica i filtri UNO A UNO — se quella cambia, va cambiata anche questa:
--   - data di riferimento = data_documento PURA (NON COALESCE con data_competenza:
--     l'aggregatore Python filtra e raggruppa su data_documento, e allinearla qui
--     a gruppo_spesa_pivot sposterebbe righe di mese senza che nessuno lo chieda)
--   - deleted_at IS NULL (soft delete, regola di dominio 5)
--   - categoria <> 'Da Classificare' (regola di dominio 1: le righe non
--     classificate restano fuori dai margini finché non vengono classificate)
--   - ripartita_su_gruppo IS DISTINCT FROM true (evita il doppio conteggio con le
--     quote già proiettate sui singoli PV da _righe_quote_gruppo)
--   - totale_riga > 0
--   - categoria ∈ centri di produzione F&B (_CATEGORIE_FB_M, da _CENTRI_DI_PRODUZIONE)
--
-- NON copre le quote di gruppo: le fatture di struttura vivono sulla sede tecnica
-- e una query per ristorante_id non le vede mai. Restano a carico di
-- _righe_quote_gruppo lato worker, che le somma a questo risultato.

CREATE OR REPLACE FUNCTION gruppo_spreco_fb_categorie(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date
)
RETURNS TABLE (
    ristorante_id uuid,
    anno int,
    mese int,
    categoria text,
    totale numeric
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT
        f.ristorante_id,
        EXTRACT(YEAR FROM f.data_documento)::int AS anno,
        EXTRACT(MONTH FROM f.data_documento)::int AS mese,
        f.categoria,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND f.categoria <> 'Da Classificare'
      AND f.ripartita_su_gruppo IS DISTINCT FROM true
      AND f.totale_riga > 0
      AND f.data_documento IS NOT NULL
      AND f.data_documento >= p_data_da
      AND f.data_documento <= p_data_a
      AND f.categoria IN (
          'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
          'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA',
          'SALSE E CREME','PRODOTTI DA FORNO','SPEZIE E AROMI','SUSHI VARIE',
          'ACQUA','BEVANDE','CAFFE E THE','VARIE BAR',
          'BIRRE','VINI','DISTILLATI','AMARI/LIQUORI',
          'PASTICCERIA','GELATI E DESSERT',
          'SHOP'
      )
    GROUP BY f.ristorante_id, anno, mese, f.categoria;
$$;

REVOKE ALL ON FUNCTION gruppo_spreco_fb_categorie(uuid[], date, date) FROM public, anon, authenticated;
