-- Retail, Fase 5 — sorveglianza post-deploy: la view che rende visibile, senza
-- query manuali, una riga che ha cambiato categoria FINENDO NEL SETTORE SBAGLIATO.
--
-- Il danno che previene
-- ─────────────────────────────────────────────────────────────────────────────
-- Le Fasi 1-4 hanno dimostrato il vincolo «i ristoranti non cambiano» AL MOMENTO
-- DEL COMMIT: baseline a zero, 241 presidi, 43 mutanti. Ma i presidi girano sul
-- codice, non sui dati dei clienti dopo il deploy, e la baseline e' una fotografia
-- che scatta qualcuno a mano. Il caso da intercettare e' una riga di un RISTORANTE
-- che finisce in ARTICOLO DI VENDITA (la categoria che esiste solo per i negozi):
-- e' silenzioso — nessun errore, nessun test rosso — e il cliente lo scopre dal
-- MOL sbagliato settimane dopo.
--
-- Perche' il segnale e' SEMANTICO e non «senza attore»
-- ─────────────────────────────────────────────────────────────────────────────
-- Il primo disegno di questa fase doveva contare i cambi «senza un attore umano»
-- leggendo `actor_email`. MISURATO sul DB vivo l'11/09/2026: su 4.135 righe di
-- category_change_log, le righe con un attore sono ZERO — `source` vale
-- 'db_trigger' su tutte, comprese le 3 successive all'8/9. La colonna esiste e la
-- RPC `aggiorna_categoria_fatture_attribuita` (8 argomenti) e' sul DB, ma i GUC
-- che il trigger legge (`app.category_change_actor_*`) non sono ancora stati
-- valorizzati da nessuna scrittura reale. Un filtro su `actor_email IS NULL`
-- selezionerebbe quindi il 100% delle righe: sarebbe rumore puro, e il rumore
-- uccide un monitor entro una settimana.
-- Il settore, invece, e' un fatto: ARTICOLO DI VENDITA su una sede ristorazione
-- e' sbagliato CHIUNQUE l'abbia scritta — un umano che sbaglia e' comunque una
-- cosa da sapere. Quando l'attribuzione sara' popolata, `actor_email` e `source`
-- sono gia' esposti qui in dettaglio e il filtro si potra' stringere senza
-- toccare la forma della response.
--
-- Perche' NON scatta sui cambi legittimi
-- ─────────────────────────────────────────────────────────────────────────────
-- La classificazione di una fattura NUOVA non e' un'anomalia: e' il lavoro
-- normale. Misurato sullo storico (4.022 cambi su `fatture`): il 42,3% e'
-- 'Da Classificare' → categoria reale, il 55,7% reale → reale, il 2,0% torna a
-- 'Da Classificare'. Il segnale qui NON guarda nessuna di queste classi: guarda
-- solo l'INCROCIO fra la categoria d'arrivo e il settore della sede. Sullo
-- storico completo dei clienti attuali questa view ritorna ZERO righe
-- (verificato: 0 cambi da/verso ARTICOLO DI VENDITA in 4.135 righe di registro),
-- che e' esattamente il comportamento voluto: tace finche' non succede davvero.
--
-- Sola lettura: nessun trigger, nessuna scrittura, nessuna correzione automatica.
-- La view espone lo stato; cosa farne e' una decisione umana.
--
-- Compatibile con DB senza `tipo_attivita`: la colonna arriva con
-- 20260910163000_add_tipo_attivita.sql, che al momento in cui questo file viene
-- scritto NON e' ancora applicata (verificato su information_schema.columns).
-- Il to_jsonb(r)->>'tipo_attivita' legge la colonna se c'e' e vale NULL se non
-- c'e', senza che la view diventi non creabile: prima della migration ogni sede
-- e' letta come 'ristorazione', che e' il default della migration stessa.

BEGIN;

CREATE OR REPLACE VIEW public.v_categorie_settore_incoerenti AS
WITH sedi AS (
    SELECT
        r.id,
        r.user_id,
        r.nome_ristorante,
        COALESCE(NULLIF(to_jsonb(r) ->> 'tipo_attivita', ''), 'ristorazione') AS tipo_attivita
    FROM public.ristoranti r
)
-- Classe 1: una sede RISTORAZIONE riceve la categoria che esiste solo per i negozi.
-- E' il danno che il retail puo' fare ai clienti attuali, ed e' il motivo di questa fase.
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

-- Classe 2: la speculare. Una sede RETAIL riceve una categoria food, che per un
-- negozio non ha senso (la Fase 1 la esclude gia' in uscita dalla classificazione:
-- se ne arriva una, qualcosa ha aggirato il gate).
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
      'PRODOTTI DA FORNO', 'SPEZIE E AROMI', 'GELATI E DESSERT', 'SHOP', 'SUSHI VARIE'
  );

-- SECURITY INVOKER esplicito, per la stessa ragione scritta nella gemella
-- v_riparto_incoerenze (20260727230000:63): senza, CREATE VIEW eredita SECURITY
-- DEFINER dal ruolo di chi la crea e bypasserebbe RLS — come le 14 view chiuse
-- nell'audit anti-hacker del 20/6. Qui l'accesso passa comunque solo dal worker
-- con service_role_key, ma la view resta corretta per costruzione (e l'advisor
-- Supabase `security_definer_view` non la segnala appena applicata).
ALTER VIEW public.v_categorie_settore_incoerenti SET (security_invoker = true);

COMMENT ON VIEW public.v_categorie_settore_incoerenti IS
    'Retail Fase 5: cambi di categoria incoerenti col settore della sede. '
    'Sola lettura, alimenta GET /api/admin/retail/categorie-incoerenti e il '
    'workflow retail_settore_check.yml. Tace (0 righe) sui dati legittimi.';

COMMIT;
