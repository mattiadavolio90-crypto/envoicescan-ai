-- ============================================================
-- 1) userid -> user_id su ricette, ingredienti_workspace,
--    ingredienti_utente, note_diario (coerenza con tutto il resto
--    dello schema, che usa gia' user_id).
-- 2) FK CASCADE mancanti su ingredienti_workspace e note_diario:
--    la migration GDPR 20260603200000 ne aggiunse una sola
--    (ingredienti_utente), queste due erano rimaste scoperte e
--    NON si pulivano alla cancellazione account.
--
-- RENAME COLUMN aggiorna automaticamente indici, FK e RLS policy
-- (legati per OID). Vanno riscritte a mano solo le 2 funzioni che
-- citano userid nel corpo, piu' i nomi degli indici (cosmetico).
--
-- ATTENZIONE DEPLOY: il rename rompe il codice Python che fa
-- .eq("userid", ...) nell'istante in cui viene applicato. Migration
-- e deploy del codice vanno nella stessa finestra.
-- ============================================================

ALTER TABLE public.ricette              RENAME COLUMN userid TO user_id;
ALTER TABLE public.ingredienti_workspace RENAME COLUMN userid TO user_id;
ALTER TABLE public.ingredienti_utente    RENAME COLUMN userid TO user_id;
ALTER TABLE public.note_diario           RENAME COLUMN userid TO user_id;

-- FK GDPR mancanti (0 righe orfane verificate prima dell'aggiunta)
ALTER TABLE public.ingredienti_workspace
  ADD CONSTRAINT ingredienti_workspace_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.note_diario
  ADD CONSTRAINT note_diario_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Indici allineati al nuovo nome colonna
ALTER INDEX IF EXISTS idx_ricette_userid_ristorante            RENAME TO idx_ricette_user_id_ristorante;
ALTER INDEX IF EXISTS idx_ricette_userid_categoria             RENAME TO idx_ricette_user_id_categoria;
ALTER INDEX IF EXISTS idx_ricette_userid_order                 RENAME TO idx_ricette_user_id_order;
ALTER INDEX IF EXISTS idx_ingredienti_utente_userid            RENAME TO idx_ingredienti_utente_user_id;
ALTER INDEX IF EXISTS idx_ingredienti_utente_unique_nome       RENAME TO idx_ingredienti_utente_unique_nome_v2;
ALTER INDEX IF EXISTS idx_ingredienti_utente_unique_nome_rist  RENAME TO idx_ingredienti_utente_unique_nome_rist_v2;
ALTER INDEX IF EXISTS idx_ingredienti_workspace_userid         RENAME TO idx_ingredienti_workspace_user_id;
ALTER INDEX IF EXISTS idx_ingredienti_workspace_unique_nome    RENAME TO idx_ingredienti_workspace_unique_nome_v2;
ALTER INDEX IF EXISTS idx_ingredienti_workspace_unique_nome_rist RENAME TO idx_ingredienti_workspace_unique_nome_rist_v2;
ALTER INDEX IF EXISTS idx_note_diario_userid                   RENAME TO idx_note_diario_user_id;

-- FK esistente: allinea anche il nome del constraint
ALTER TABLE public.ricette
  RENAME CONSTRAINT ricette_userid_fkey TO ricette_user_id_fkey;
ALTER TABLE public.ingredienti_utente
  RENAME CONSTRAINT ingredienti_utente_userid_fkey TO ingredienti_utente_user_id_fkey;

-- ============================================================
-- Funzioni che citano userid nel corpo: vanno riscritte.
-- Comportamento invariato, cambia solo il nome della colonna.
-- Il parametro p_userid diventa p_user_id: la firma cambia, quindi
-- DROP esplicito della vecchia versione (CREATE OR REPLACE non puo'
-- rinominare un parametro).
-- ============================================================
DROP FUNCTION IF EXISTS public.get_next_ordine_ricetta(uuid, uuid);

CREATE FUNCTION public.get_next_ordine_ricetta(p_user_id uuid, p_ristorante_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $function$
DECLARE
    v_max_ordine INTEGER;
BEGIN
    IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    IF p_ristorante_id IS NOT NULL
       AND COALESCE(auth.role(), '') <> 'service_role'
       AND NOT EXISTS (
            SELECT 1
            FROM public.ristoranti AS r
            WHERE r.id = p_ristorante_id
              AND r.user_id = p_user_id
       ) THEN
        RAISE EXCEPTION 'Ristorante non autorizzato';
    END IF;

    SELECT COALESCE(MAX(r.ordine_visualizzazione), 0)
    INTO v_max_ordine
    FROM public.ricette AS r
    WHERE r.user_id = p_user_id
      AND (
          r.ristorante_id = p_ristorante_id
          OR (r.ristorante_id IS NULL AND p_ristorante_id IS NULL)
      );

    RETURN v_max_ordine + 1;
END;
$function$;

CREATE OR REPLACE FUNCTION public.swap_ricette_order(ricetta_id_1 uuid, ricetta_id_2 uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $function$
DECLARE
    v_user_1 UUID;
    v_user_2 UUID;
    v_ordine_1 INTEGER;
    v_ordine_2 INTEGER;
BEGIN
    SELECT r.user_id, r.ordine_visualizzazione
    INTO v_user_1, v_ordine_1
    FROM public.ricette AS r
    WHERE r.id = ricetta_id_1
    FOR UPDATE;

    SELECT r.user_id, r.ordine_visualizzazione
    INTO v_user_2, v_ordine_2
    FROM public.ricette AS r
    WHERE r.id = ricetta_id_2
    FOR UPDATE;

    IF v_user_1 IS NULL OR v_user_2 IS NULL THEN
        RAISE EXCEPTION 'Ricette non trovate';
    END IF;

    IF v_user_1 IS DISTINCT FROM v_user_2 THEN
        RAISE EXCEPTION 'Le ricette non appartengono allo stesso utente';
    END IF;

    IF COALESCE(auth.role(), '') <> 'service_role' AND v_user_1 IS DISTINCT FROM auth.uid() THEN
        RAISE EXCEPTION 'Accesso negato';
    END IF;

    UPDATE public.ricette
    SET ordine_visualizzazione = v_ordine_2
    WHERE id = ricetta_id_1;

    UPDATE public.ricette
    SET ordine_visualizzazione = v_ordine_1
    WHERE id = ricetta_id_2;

    RETURN true;
END;
$function$;
