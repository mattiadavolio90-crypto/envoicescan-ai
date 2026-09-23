-- Budget chat MENSILE, col tetto giornaliero come freno.
--
-- Prima esisteva solo il tetto giornaliero e il mese non aveva alcun limite: un
-- cliente poteva fare 30 domande al giorno per 30 giorni senza che nulla lo
-- fermasse. Ora il vincolo vero e' il mese; il giorno serve solo perche' nessuno
-- bruci il budget in due giorni e resti fermo per ventotto.
--
-- PERCHE' DUE PARAMETRI NUOVI E NON UNO: il messaggio al cliente e' diverso.
-- «hai finito per oggi, torna domani» e «hai finito il mese, riparti il 1°» non
-- sono la stessa frase, e il codice deve poterle distinguere senza indovinare.
-- Percio' il ritorno NON e' piu' un -1 secco:
--     >= 1  -> ok, e' il numero di domande consumate OGGI
--     -1    -> fermato dal tetto GIORNALIERO
--     -2    -> fermato dal budget MENSILE
-- Il chiamante che conosce solo il vecchio contratto tratta -2 come «negativo»
-- e quindi blocca comunque: il fail-safe resta dalla parte giusta.
--
-- ORDINE DI CONTROLLO: prima il mese, poi il giorno. Se sono finiti entrambi, il
-- cliente deve leggere quello che dura di piu' — dirgli «torna domani» quando il
-- budget mensile e' esaurito sarebbe una promessa falsa, lo stesso difetto del
-- «Riprova domani» corretto stamattina.
--
-- FINESTRE: entrambe sul fuso Europe/Rome, come la migration del giorno
-- (20260923141755). Il mese e' quello del calendario del ristoratore: il budget
-- riparte a mezzanotte del 1°, non alle 02:00 del 1° come farebbe l'UTC.
--
-- ORDINE DI DEPLOY — OBBLIGATO, ed e' la differenza rispetto alla migration
-- precedente: quella non cambiava la firma, questa SI'. Il call site passa due
-- parametri nuovi; finche' questa migration non e' applicata, PostgREST non
-- trova la funzione con quella firma, la RPC fallisce e il codice e' fail-closed
-- -> la chat si spegne per tutti. **Applicare questa migration PRIMA del push.**
-- La vecchia firma a 4 parametri resta viva apposta (nessun DROP): durante la
-- finestra di deploy un worker non ancora aggiornato continua a funzionare.
--
-- Idempotente. service_role only (auth custom, auth.uid() sempre NULL).

CREATE OR REPLACE FUNCTION public.chat_usage_check_and_log(
    p_user_id        UUID,
    p_ristorante_id  UUID,
    p_limite         INTEGER,
    p_pool           BOOLEAN DEFAULT false,
    p_limite_mensile INTEGER DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    -- Mezzanotte di Roma (giorno e primo del mese), riportate a timestamptz: il
    -- confronto con created_at resta assoluto e corretto nei regimi CET/CEST.
    v_inizio_giorno TIMESTAMPTZ := ((now() AT TIME ZONE 'Europe/Rome')::date)::timestamp
                                   AT TIME ZONE 'Europe/Rome';
    v_inizio_mese   TIMESTAMPTZ := (date_trunc('month', (now() AT TIME ZONE 'Europe/Rome')))::timestamp
                                   AT TIME ZONE 'Europe/Rome';
    v_count_giorno  INTEGER;
    v_count_mese    INTEGER;
BEGIN
    IF p_limite IS NULL OR p_limite <= 0 THEN
        RETURN -1;
    END IF;

    -- Un solo passaggio sulla tabella per entrambe le finestre: il mese contiene
    -- il giorno, quindi il FILTER sul giorno non costa una seconda scansione.
    -- Lock implicito della transazione, come prima: conta+inserisce atomico.
    -- Pool → per user_id (condiviso); altrimenti per ristorante (o user se NULL).
    SELECT
        count(*) FILTER (WHERE created_at >= v_inizio_giorno)::int,
        count(*)::int
      INTO v_count_giorno, v_count_mese
    FROM public.chat_usage_log
    WHERE created_at >= v_inizio_mese
      AND (
        (p_pool AND user_id = p_user_id)
        OR (NOT p_pool AND p_ristorante_id IS NOT NULL AND ristorante_id = p_ristorante_id)
        OR (NOT p_pool AND p_ristorante_id IS NULL AND user_id = p_user_id)
      );

    -- Il mese per primo: dura di piu', e il cliente deve sapere il vincolo vero.
    -- p_limite_mensile NULL = chiamante vecchio, nessun budget mensile: si
    -- comporta esattamente come prima di questa migration.
    IF p_limite_mensile IS NOT NULL AND p_limite_mensile > 0
       AND v_count_mese >= p_limite_mensile THEN
        RETURN -2;
    END IF;

    IF v_count_giorno >= p_limite THEN
        RETURN -1;
    END IF;

    -- La riga conserva SEMPRE la sede d'origine (anche in pool), per l'attribuzione.
    INSERT INTO public.chat_usage_log (user_id, ristorante_id)
    VALUES (p_user_id, p_ristorante_id);

    RETURN v_count_giorno + 1;
END;
$$;

COMMENT ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN, INTEGER) IS
    'Rate limit chat atomico su DUE finestre, entrambe sul giorno di Europe/Rome: '
    'budget mensile (p_limite_mensile, controllato per primo perche'' dura di piu'') '
    'e tetto giornaliero (p_limite). Ritorna il conteggio di oggi (>=1) se sotto '
    'entrambi, -1 se e'' finito il giorno, -2 se e'' finito il mese. '
    'p_limite_mensile NULL = nessun budget mensile (comportamento pre-23/09/2026).';

REVOKE ALL ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.chat_usage_check_and_log(UUID, UUID, INTEGER, BOOLEAN, INTEGER) TO service_role;
