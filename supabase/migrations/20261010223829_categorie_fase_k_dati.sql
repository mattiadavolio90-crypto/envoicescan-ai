-- Fase K3 (10/10/2026, decisioni di Mattia): i DATI seguono il nuovo elenco.
--
--   1. tabella `categorie` (icone, menu "categorie disponibili"): SHOP diventa
--      RIVENDITA, nasce RAPPRESENTANZA, SUSHI VARIE si toglie. Va CANCELLATA e non
--      spenta: `get_categorie_disponibili` legge la tabella senza filtrare `attiva`.
--   2. SHOP -> RIVENDITA ovunque una riga porti il nome: fatture (anche nel
--      cestino), memoria globale e del cliente, conferme admin, quote di riparto.
--      E' una RINOMINA: vale anche per le righe decise a mano (la scelta del
--      cliente resta la stessa, cambia solo il nome), quindi niente salto delle
--      arbitrate. Il registro (`category_change_log`) le attribuisce a
--      `migrazione_fase_k` con un lotto unico, invece che a un anonimo db_trigger.
--
-- NON tocca SUSHI VARIE nelle righe: non ha un erede unico, ogni riga va nella sua
-- famiglia e lo decide `scripts/fase_k_categorie.py` (passo `giappone`), che in
-- K4 gira PRIMA di questa migration. Il registro storico non si tocca.
--
-- Idempotente: rieseguita non trova piu' niente da rinominare.
-- Senza BEGIN/COMMIT: apply_migration la esegue gia' in una transazione, e i test
-- `-m sql` la rieseguono dentro la loro (tests/test_sql_fase_k_dati.py).

-- 1. tabella delle categorie
UPDATE public.categorie SET nome = 'RIVENDITA', updated_at = now()
 WHERE nome = 'SHOP'
   AND NOT EXISTS (SELECT 1 FROM public.categorie WHERE nome = 'RIVENDITA');
DELETE FROM public.categorie WHERE nome IN ('SHOP', 'SUSHI VARIE');
INSERT INTO public.categorie (nome, icona, ordinamento, attiva)
VALUES ('RAPPRESENTANZA', '🤝', 940, true)
ON CONFLICT (nome) DO NOTHING;

-- 2a. fatture attive, attribuite (la RPC imposta e poi azzera i GUC del registro)
SELECT public.aggiorna_categoria_fatture_attribuita(
    p_ids => ARRAY(
        SELECT id FROM public.fatture WHERE categoria = 'SHOP' AND deleted_at IS NULL
    ),
    p_categoria => 'RIVENDITA',
    p_source => 'migrazione_fase_k',
    p_extra => '{}'::jsonb,
    p_actor_email => NULL,
    p_actor_user_id => NULL,
    p_batch_id => '9404d963-5cb3-4410-a552-b12043046eca'::uuid,
    p_salta_arbitrate => false
);

-- 2b. tutto il resto, con la stessa attribuzione nel registro
SELECT set_config('app.category_change_source', 'migrazione_fase_k', true);
SELECT set_config('app.category_change_batch_id', '9404d963-5cb3-4410-a552-b12043046eca', true);

UPDATE public.fatture SET categoria = 'RIVENDITA'
 WHERE categoria = 'SHOP' AND deleted_at IS NOT NULL;
UPDATE public.prodotti_master SET categoria = 'RIVENDITA' WHERE categoria = 'SHOP';
UPDATE public.prodotti_master SET categoria_suggerita = 'RIVENDITA' WHERE categoria_suggerita = 'SHOP';
UPDATE public.prodotti_utente SET categoria = 'RIVENDITA', updated_at = now() WHERE categoria = 'SHOP';
UPDATE public.classificazioni_manuali SET categoria_corretta = 'RIVENDITA' WHERE categoria_corretta = 'SHOP';
UPDATE public.review_confirmed SET categoria_finale = 'RIVENDITA' WHERE categoria_finale = 'SHOP';
UPDATE public.riparto_costi_catena_quote SET categoria = 'RIVENDITA' WHERE categoria = 'SHOP';
UPDATE public.spese_extra SET categoria = 'RIVENDITA' WHERE categoria = 'SHOP';

SELECT public._azzera_attribuzione_categoria();
