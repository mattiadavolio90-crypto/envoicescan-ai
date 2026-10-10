-- Crediti AI e ricariche (Boost AI, fase J del piano «Assistente consulente»).
--
-- Decisioni di Mattia del 10/10/2026:
--   * l'app conta CREDITI, come l'offerta commerciale: una domanda = 3 crediti;
--   * il Boost e' una RICARICA una tantum che non scade: si consuma solo
--     usandola, DOPO i crediti del mese, e il residuo passa ai mesi dopo;
--   * il tetto del giorno vale anche quando si spende la ricarica.
--
-- COSA FA:
--   1. `chat_usage_log` guadagna `crediti` (quanti ne ha speso la domanda) e
--      `da_ricarica` (pagata con la ricarica invece che coi crediti del mese).
--      Le righe gia' scritte e quelle del worker vecchio prendono il default 3:
--      e' il costo di una domanda, quindi i conteggi del mese in corso restano
--      giusti anche a cavallo del deploy.
--   2. `chat_ricariche`: una riga per ricarica attivata da Mattia (a mano, per
--      ora). Il residuo NON e' una colonna: e' la somma delle ricariche meno i
--      crediti spesi da ricarica. Un saldo salvato a parte divergerebbe al primo
--      errore; due somme sulla stessa verita' no.
--   3. `chat_crediti_stato`: i tre numeri che il cliente vede (crediti di oggi,
--      del mese, ricarica residua). Sola lettura.
--   4. `chat_crediti_check_and_log`: controlla e scrive in un solo passaggio,
--      come la vecchia `chat_usage_check_and_log`, leggendo i numeri da
--      `chat_crediti_stato` — le finestre (giorno e mese di Roma) stanno in UN
--      posto solo.
--
-- PERCHE' UNA FUNZIONE NUOVA E NON UNA FIRMA NUOVA: cambiare la firma della
-- vecchia richiede il DROP (vedi 20260923152816: con due firme Postgres si
-- rifiuta di scegliere) e fra migration e push il worker vecchio andrebbe in
-- errore, fail-closed: chat spenta per tutti. Con un nome nuovo il worker
-- vecchio continua sulla vecchia finche' il push non arriva. La vecchia si
-- toglie con una migration successiva, a deploy fatto.
--
-- ORDINE DI DEPLOY: applicare PRIMA del push (il worker nuovo chiama le due
-- funzioni nuove: senza, la chat e' fail-closed).
--
-- Idempotente. service_role only (auth custom, auth.uid() sempre NULL).

ALTER TABLE public.chat_usage_log
    ADD COLUMN IF NOT EXISTS crediti     INTEGER NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS da_ricarica BOOLEAN NOT NULL DEFAULT false;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chat_usage_log_crediti_positivi_chk'
    ) THEN
        ALTER TABLE public.chat_usage_log
            ADD CONSTRAINT chat_usage_log_crediti_positivi_chk CHECK (crediti > 0);
    END IF;
END $$;

-- Il residuo della ricarica somma le righe da_ricarica di un utente su tutta la
-- storia: l'indice parziale tiene la lettura piccola anche fra anni.
CREATE INDEX IF NOT EXISTS idx_chat_usage_da_ricarica
    ON public.chat_usage_log (user_id) WHERE da_ricarica;

CREATE TABLE IF NOT EXISTS public.chat_ricariche (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    crediti     integer     NOT NULL CHECK (crediti > 0),
    nota        text,
    creata_da   text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_ricariche_user ON public.chat_ricariche (user_id);

-- Su Supabase anon e authenticated hanno grant propri dalle default privileges:
-- REVOKE FROM PUBLIC da solo non basta, vanno nominati.
ALTER TABLE public.chat_ricariche ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_ricariche FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_ricariche TO service_role;


CREATE OR REPLACE FUNCTION public.chat_crediti_stato(
    p_user_id       UUID,
    p_ristorante_id UUID,
    p_pool          BOOLEAN DEFAULT false
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    -- Mezzanotte di Roma (giorno e primo del mese), come 20260923152816.
    v_inizio_giorno TIMESTAMPTZ := ((now() AT TIME ZONE 'Europe/Rome')::date)::timestamp
                                   AT TIME ZONE 'Europe/Rome';
    v_inizio_mese   TIMESTAMPTZ := (date_trunc('month', (now() AT TIME ZONE 'Europe/Rome')))::timestamp
                                   AT TIME ZONE 'Europe/Rome';
    v_oggi     INTEGER;
    v_mese     INTEGER;
    v_caricati INTEGER;
    v_spesi    INTEGER;
BEGIN
    -- Oggi: TUTTO cio' che e' stato speso (il tetto del giorno vale anche sulla
    -- ricarica). Mese: solo i crediti del piano, non quelli pagati con la
    -- ricarica — sono due salvadanai.
    -- Pool → per user_id (condiviso); altrimenti per sede (o utente se NULL).
    SELECT
        COALESCE(sum(crediti) FILTER (WHERE created_at >= v_inizio_giorno), 0)::int,
        COALESCE(sum(crediti) FILTER (WHERE NOT da_ricarica), 0)::int
      INTO v_oggi, v_mese
    FROM public.chat_usage_log
    WHERE created_at >= v_inizio_mese
      AND (
        (p_pool AND user_id = p_user_id)
        OR (NOT p_pool AND p_ristorante_id IS NOT NULL AND ristorante_id = p_ristorante_id)
        OR (NOT p_pool AND p_ristorante_id IS NULL AND user_id = p_user_id)
      );

    -- La ricarica e' dell'account, qualunque sede l'abbia spesa, e non scade.
    SELECT COALESCE(sum(crediti), 0)::int INTO v_caricati
    FROM public.chat_ricariche WHERE user_id = p_user_id;

    SELECT COALESCE(sum(crediti), 0)::int INTO v_spesi
    FROM public.chat_usage_log WHERE user_id = p_user_id AND da_ricarica;

    RETURN jsonb_build_object(
        'oggi', v_oggi,
        'mese', v_mese,
        'ricarica', v_caricati - v_spesi
    );
END;
$$;

COMMENT ON FUNCTION public.chat_crediti_stato(UUID, UUID, BOOLEAN) IS
    'Crediti chat: {oggi, mese, ricarica}. oggi = tutti i crediti spesi oggi (giorno di Roma); '
    'mese = crediti del piano spesi nel mese (esclusi quelli pagati con la ricarica); '
    'ricarica = ricariche dell''account meno i crediti spesi da ricarica (puo'' scendere sotto '
    'zero di meno di una domanda). Fase J, 10/10/2026.';


CREATE OR REPLACE FUNCTION public.chat_crediti_check_and_log(
    p_user_id        UUID,
    p_ristorante_id  UUID,
    p_pool           BOOLEAN,
    p_crediti_giorno INTEGER,
    p_crediti_mese   INTEGER,
    p_costo          INTEGER
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_stato       jsonb;
    v_oggi        INTEGER;
    v_mese        INTEGER;
    v_ricarica    INTEGER;
    v_da_ricarica BOOLEAN;
BEGIN
    IF p_crediti_giorno IS NULL OR p_crediti_giorno <= 0
       OR p_costo IS NULL OR p_costo <= 0 THEN
        RETURN jsonb_build_object('esito', 'giorno');
    END IF;

    -- Due domande dello stesso account nello stesso istante leggerebbero lo
    -- stesso stato e passerebbero entrambe: si mettono in fila per account.
    PERFORM pg_advisory_xact_lock(hashtext('chat_crediti:' || p_user_id::text));

    v_stato    := public.chat_crediti_stato(p_user_id, p_ristorante_id, p_pool);
    v_oggi     := (v_stato->>'oggi')::int;
    v_mese     := (v_stato->>'mese')::int;
    v_ricarica := (v_stato->>'ricarica')::int;

    -- Si spende finche' ne resta: prima il mese, poi la ricarica. Un budget
    -- mensile NULL o 0 (chiamante senza mese) non ferma niente.
    v_da_ricarica := p_crediti_mese IS NOT NULL AND p_crediti_mese > 0
                     AND v_mese >= p_crediti_mese;

    -- Il mese per primo: dura di piu', e il cliente deve leggere il vincolo
    -- vero (stessa scelta di 20260923152816).
    IF v_da_ricarica AND v_ricarica <= 0 THEN
        RETURN v_stato || jsonb_build_object('esito', 'mese');
    END IF;

    IF v_oggi >= p_crediti_giorno THEN
        RETURN v_stato || jsonb_build_object('esito', 'giorno');
    END IF;

    -- La riga conserva SEMPRE la sede d'origine (anche in pool), per l'attribuzione.
    INSERT INTO public.chat_usage_log (user_id, ristorante_id, crediti, da_ricarica)
    VALUES (p_user_id, p_ristorante_id, p_costo, v_da_ricarica);

    RETURN jsonb_build_object(
        'esito', 'ok',
        'oggi', v_oggi + p_costo,
        'mese', v_mese + CASE WHEN v_da_ricarica THEN 0 ELSE p_costo END,
        'ricarica', v_ricarica - CASE WHEN v_da_ricarica THEN p_costo ELSE 0 END,
        'da_ricarica', v_da_ricarica
    );
END;
$$;

COMMENT ON FUNCTION public.chat_crediti_check_and_log(UUID, UUID, BOOLEAN, INTEGER, INTEGER, INTEGER) IS
    'Rate limit chat in CREDITI (fase J, 10/10/2026). Spende prima i crediti del mese, poi la '
    'ricarica; il tetto del giorno vale su entrambi. Ritorna {esito: ok|giorno|mese, oggi, mese, '
    'ricarica[, da_ricarica]}; su ok i numeri includono la domanda appena scritta. '
    'esito mese = mese e ricarica finiti (vince sul giorno).';

REVOKE ALL ON FUNCTION public.chat_crediti_stato(UUID, UUID, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.chat_crediti_stato(UUID, UUID, BOOLEAN) TO service_role;
REVOKE ALL ON FUNCTION public.chat_crediti_check_and_log(UUID, UUID, BOOLEAN, INTEGER, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.chat_crediti_check_and_log(UUID, UUID, BOOLEAN, INTEGER, INTEGER, INTEGER) TO service_role;
