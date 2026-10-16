-- Tag ordinabili a mano dentro la loro cartella, in «Analisi e Tag» e nei «Tag
-- di catena» (Mattia, 16/10/2026: «trascinandoli come per le cartelle»).
--
-- `ordine` e' la posizione del tag nel suo gruppo: la cartella, o «Senza
-- cartella». La lista si ordina per (ordine, nome, id), quindi con tutti a 0
-- resta l'ordine alfabetico di oggi: i tag esistenti NON si numerano qui, e a
-- schermo non cambia niente finche' qualcuno non trascina. Il primo
-- trascinamento in un gruppo scrive l'ordine di tutto il gruppo (PUT
-- /api/tag/ordine e /api/gruppo/tag/ordine).
--
-- Un tag nuovo va in fondo al suo gruppo: lo fa il trigger, cosi' vale per
-- ogni strada che crea tag (sede: `db_service.crea_tag`; catena: POST
-- /api/gruppo/tag) senza toccarle. Lo spostamento di cartella dal riquadro
-- «Modifica tag» lo mette in fondo il worker (`aggiorna_tag_parziale_in`),
-- non un trigger: il riordino scrive cartella e ordine insieme e un trigger su
-- UPDATE non saprebbe distinguere i due casi.
--
-- Pura visualizzazione: niente analisi, briefing o margini leggono `ordine`.
-- Idempotente. Va applicata al live PRIMA del push (il worker la seleziona).

ALTER TABLE public.custom_tags ADD COLUMN IF NOT EXISTS ordine integer NOT NULL DEFAULT 0;
ALTER TABLE public.gruppo_tags ADD COLUMN IF NOT EXISTS ordine integer NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION public.custom_tags_in_fondo()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
  SELECT COALESCE(MAX(ordine), -1) + 1 INTO NEW.ordine
  FROM public.custom_tags
  WHERE user_id = NEW.user_id
    AND ristorante_id = NEW.ristorante_id
    AND cartella_id IS NOT DISTINCT FROM NEW.cartella_id;
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.gruppo_tags_in_fondo()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
BEGIN
  SELECT COALESCE(MAX(ordine), -1) + 1 INTO NEW.ordine
  FROM public.gruppo_tags
  WHERE user_id = NEW.user_id
    AND cartella_id IS NOT DISTINCT FROM NEW.cartella_id;
  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.custom_tags_in_fondo() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gruppo_tags_in_fondo() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE TRIGGER trg_custom_tags_in_fondo
  BEFORE INSERT ON public.custom_tags
  FOR EACH ROW EXECUTE FUNCTION public.custom_tags_in_fondo();

CREATE OR REPLACE TRIGGER trg_gruppo_tags_in_fondo
  BEFORE INSERT ON public.gruppo_tags
  FOR EACH ROW EXECUTE FUNCTION public.gruppo_tags_in_fondo();

COMMENT ON COLUMN public.custom_tags.ordine IS
  'Posizione del tag nella sua cartella (o in «Senza cartella»). La lista ordina per (ordine, nome, id): a 0 per tutti resta alfabetica. Solo visualizzazione.';
COMMENT ON COLUMN public.gruppo_tags.ordine IS
  'Posizione del tag di catena nella sua cartella (o in «Senza cartella»). Come custom_tags.ordine.';
