-- Fase K (10/10/2026, decisioni di Mattia): gli elenchi di categorie RICOPIATI
-- dentro il database seguono config/constants.py.
--
--   * SHOP si chiama RIVENDITA (stesso contenuto);
--   * SUSHI VARIE non esiste piu' (ogni prodotto nella sua famiglia);
--   * nasce RAPPRESENTANZA, spesa generale.
--
-- Tre funzioni e una vista tengono una copia letterale delle liste (misurato su
-- pg_proc il 10/10): senza questa migration RIVENDITA conterebbe come spesa nel
-- riparto e sparirebbe dal cruscotto sprechi, e RAPPRESENTANZA entrerebbe nel
-- peso delle categorie F&B della catena. Presidio: tests/test_sql_categorie_fb.py.
--
-- Solo le liste: i DATI (righe SHOP -> RIVENDITA, tabella `categorie`) li sposta
-- la migration della fase K3, nella stessa finestra di deploy, subito dopo.
-- Corpi, firme e attributi identici a quelli live: cambia solo l'elenco.
-- Idempotente (CREATE OR REPLACE: i GRANT esistenti restano).

BEGIN;

CREATE OR REPLACE FUNCTION public._riparto_categoria_is_fb(p_categoria text)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT upper(btrim(coalesce(p_categoria, ''))) IN (
        'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
        'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA','SALSE E CREME',
        'ACQUA','BEVANDE','CAFFE E THE','BIRRE','VINI',
        'VARIE BAR','DISTILLATI','AMARI/LIQUORI','PASTICCERIA',
        'PRODOTTI DA FORNO','SPEZIE E AROMI','GELATI E DESSERT','RIVENDITA'
    );
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_spreco_fb_categorie(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
 RETURNS TABLE(ristorante_id uuid, anno integer, mese integer, categoria text, totale numeric)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT
        f.ristorante_id,
        EXTRACT(YEAR FROM f.data_documento)::int AS anno,
        EXTRACT(MONTH FROM f.data_documento)::int AS mese,
        f.categoria,
        SUM(f.totale_riga) AS totale
    FROM fatture f
    WHERE f.ristorante_id = ANY(p_ristorante_ids)
      AND f.deleted_at IS NULL
      AND NOT f.oscurata
      AND f.categoria <> 'Da Classificare'
      AND (NOT p_escludi_da_verificare OR COALESCE(f.categoria_fiducia, '') <> 'da_verificare')
      AND f.ripartita_su_gruppo IS DISTINCT FROM true
      AND f.totale_riga > 0
      AND f.data_documento IS NOT NULL
      AND f.data_documento >= p_data_da
      AND f.data_documento <= p_data_a
      AND f.categoria IN (
          'CARNE','PESCE','LATTICINI','SALUMI','UOVA','SCATOLAME E CONSERVE',
          'OLIO E CONDIMENTI','PASTA E CEREALI','VERDURE','FRUTTA',
          'SALSE E CREME','PRODOTTI DA FORNO','SPEZIE E AROMI',
          'ACQUA','BEVANDE','CAFFE E THE','VARIE BAR',
          'BIRRE','VINI','DISTILLATI','AMARI/LIQUORI',
          'PASTICCERIA','GELATI E DESSERT',
          'RIVENDITA'
      )
    GROUP BY f.ristorante_id, anno, mese, f.categoria;
$function$;


CREATE OR REPLACE FUNCTION public.gruppo_peso_categoria(p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean DEFAULT false)
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


-- La vista legge il REGISTRO dei cambi, che conserva i nomi di allora: SHOP e
-- SUSHI VARIE restano nell'elenco accanto a RIVENDITA, o un cambio storico verso
-- una categoria food su un negozio sparirebbe dal controllo.
CREATE OR REPLACE VIEW public.v_categorie_settore_incoerenti AS
WITH sedi AS (
    SELECT
        r.id,
        r.user_id,
        r.nome_ristorante,
        COALESCE(NULLIF(to_jsonb(r) ->> 'tipo_attivita', ''), 'ristorazione') AS tipo_attivita
    FROM public.ristoranti r
)
SELECT
    l.id                AS log_id,
    l.changed_at,
    s.user_id,
    l.ristorante_id,
    s.nome_ristorante,
    s.tipo_attivita,
    'ristorazione_con_categoria_retail'::text AS tipo_incoerenza,
    l.descrizione,
    l.old_categoria,
    l.new_categoria,
    l.file_origine,
    l.numero_riga,
    l.actor_email,
    l.source,
    l.batch_id
FROM public.category_change_log l
JOIN sedi s ON s.id = l.ristorante_id
WHERE l.table_name = 'fatture'
  AND s.tipo_attivita = 'ristorazione'
  AND l.new_categoria = 'ARTICOLO DI VENDITA'

UNION ALL

SELECT
    l.id                AS log_id,
    l.changed_at,
    s.user_id,
    l.ristorante_id,
    s.nome_ristorante,
    s.tipo_attivita,
    'retail_con_categoria_food'::text AS tipo_incoerenza,
    l.descrizione,
    l.old_categoria,
    l.new_categoria,
    l.file_origine,
    l.numero_riga,
    l.actor_email,
    l.source,
    l.batch_id
FROM public.category_change_log l
JOIN sedi s ON s.id = l.ristorante_id
WHERE l.table_name = 'fatture'
  AND s.tipo_attivita = 'retail'
  AND l.new_categoria IN (
      'CARNE', 'PESCE', 'LATTICINI', 'SALUMI', 'UOVA', 'SCATOLAME E CONSERVE',
      'OLIO E CONDIMENTI', 'PASTA E CEREALI', 'VERDURE', 'FRUTTA', 'SALSE E CREME',
      'ACQUA', 'BEVANDE', 'CAFFE E THE', 'BIRRE', 'VINI',
      'VARIE BAR', 'DISTILLATI', 'AMARI/LIQUORI', 'PASTICCERIA',
      'PRODOTTI DA FORNO', 'SPEZIE E AROMI', 'GELATI E DESSERT', 'RIVENDITA',
      'SHOP', 'SUSHI VARIE'
  );

ALTER VIEW public.v_categorie_settore_incoerenti SET (security_invoker = true);

COMMIT;
