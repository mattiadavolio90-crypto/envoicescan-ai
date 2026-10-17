-- La testata di una fattura sparisce con la sua ultima riga (17/10/2026).
--
-- Svuota cestino, purge del cestino scaduto, retention GDPR, elimina definitiva
-- (services/db_service.py) cancellano le righe di `fatture` e lasciano la testata
-- in `fatture_documenti`: sul live 331 testate archiviate senza nessuna riga, di 5
-- clienti, con fornitore, numero, importo e stato «pagata». Una fattura ricaricata
-- con lo stesso nome ritrovava quella testata, e dal fix n. 38 (l'upsert riattiva
-- la testata) anche il vecchio «pagata» e la vecchia scadenza. La retention, poi,
-- non toglieva i dati del documento.
--
-- Un trigger e non cinque modifiche in Python: copre anche le cancellazioni che
-- verranno. Una riga rimasta, anche nel cestino, tiene la testata: il ricaricamento
-- con meno righe cancella solo quelle in piu', e il cestino resta ripristinabile.

CREATE OR REPLACE FUNCTION public.fn_elimina_testate_senza_righe()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    DELETE FROM public.fatture_documenti d
    USING (SELECT DISTINCT user_id, ristorante_id, file_origine FROM righe_cancellate) o
    WHERE d.user_id = o.user_id
      AND d.ristorante_id IS NOT DISTINCT FROM o.ristorante_id
      AND d.file_origine = o.file_origine
      AND NOT EXISTS (
          SELECT 1 FROM public.fatture f
          WHERE f.user_id = d.user_id
            AND f.ristorante_id IS NOT DISTINCT FROM d.ristorante_id
            AND f.file_origine = d.file_origine
      );
    RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.fn_elimina_testate_senza_righe() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_elimina_testate_senza_righe ON public.fatture;
CREATE TRIGGER trg_elimina_testate_senza_righe
    AFTER DELETE ON public.fatture
    REFERENCING OLD TABLE AS righe_cancellate
    FOR EACH STATEMENT
    EXECUTE FUNCTION public.fn_elimina_testate_senza_righe();

-- Le testate gia' rimaste senza righe e nel cestino (331 il 17/10/2026). Quelle
-- ATTIVE senza righe (20) hanno ciascuna un caso suo e le sistema lo script del
-- verbale n. 36: qui non si toccano.
DELETE FROM public.fatture_documenti d
WHERE d.deleted_at IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.fatture f
      WHERE f.user_id = d.user_id
        AND f.ristorante_id IS NOT DISTINCT FROM d.ristorante_id
        AND f.file_origine = d.file_origine
  );
