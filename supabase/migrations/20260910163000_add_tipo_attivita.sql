-- Retail, Fase 1.1 — il perno del settore sta sulla sede.
--
-- ONEFLUX apre ai negozi (DOCUMENTAZIONE/RETAIL_FASI.md). Ogni deviazione retail
-- nel codice scatta su `ristoranti.tipo_attivita = 'retail'`; il percorso comune
-- resta letteralmente quello di oggi. Il default 'ristorazione' col NOT NULL fa
-- si' che le 12 sedi esistenti (misurate sul live il 10/09/2026) e ogni sede che
-- il codice vecchio dovesse creare nascano ristorazione senza che nessuno debba
-- scriverlo.
--
-- La colonna sta sulla SEDE e non sull'account: in v1 le sedi di un utente sono
-- omogenee (vincolo nel router admin: un vincolo "per account" non si esprime
-- con un CHECK di riga), ma il campo sulla sede non chiude la porta ai misti.
--
-- Ordine di deploy (vincolo duro, RETAIL_FASI.md): questa migration si applica
-- sul DB PRIMA del push del branch. Il codice vecchio non la vede (seleziona
-- colonne esplicite, mai `*`); il codice nuovo senza la colonna fallirebbe.
--
-- Idempotente: ADD COLUMN IF NOT EXISTS e constraint guardato dal catalogo, cosi'
-- il harness dei test SQL (che la applica sopra lo snapshot) e una seconda
-- applicazione a mano non fanno danni.

ALTER TABLE public.ristoranti
    ADD COLUMN IF NOT EXISTS tipo_attivita text NOT NULL DEFAULT 'ristorazione';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conname  = 'ristoranti_tipo_attivita_chk'
          AND  conrelid = 'public.ristoranti'::regclass
    ) THEN
        ALTER TABLE public.ristoranti
            ADD CONSTRAINT ristoranti_tipo_attivita_chk
            CHECK (tipo_attivita IN ('ristorazione', 'retail'));
    END IF;
END
$$;

COMMENT ON COLUMN public.ristoranti.tipo_attivita IS
    'Settore della sede: ristorazione (default) o retail. In v1 tutte le sedi di un '
    'account hanno lo stesso valore (vincolo nel router admin, non a DB).';

-- ─────────────────────────────────────────────────────────────────────────────
-- assegna_fattura_a_sede_tecnica: la sede tecnica eredita il settore
-- ─────────────────────────────────────────────────────────────────────────────
-- L'INSERT che crea "Costi comuni di gruppo" elencava 6 colonne, e questa non
-- c'era: su un account retail la sede tecnica sarebbe nata 'ristorazione' per
-- default. Il settore si copia dalla stessa sede reale da cui gia' si copia la
-- P.IVA. Firma invariata (un solo chiamante: services/routers/riparto.py) e
-- corpo identico per il resto: per gli account ristorazione il risultato non
-- cambia. Provato in tests/test_sql_retail_tipo_attivita.py.
CREATE OR REPLACE FUNCTION public.assegna_fattura_a_sede_tecnica(p_queue_id bigint)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_queue_user_id UUID;
    v_queue_status  TEXT;
    v_tecnica_id    UUID;
    v_piva          TEXT;
    v_tipo          TEXT;
BEGIN
    SELECT user_id, status
    INTO   v_queue_user_id, v_queue_status
    FROM   public.fatture_queue
    WHERE  id = p_queue_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Record coda % inesistente', p_queue_id;
    END IF;

    IF v_queue_status <> 'da_assegnare' THEN
        RETURN NULL;
    END IF;

    SELECT id INTO v_tecnica_id
    FROM   public.ristoranti
    WHERE  user_id = v_queue_user_id AND sede_tecnica = TRUE
    LIMIT  1;

    IF v_tecnica_id IS NULL THEN
        SELECT partita_iva, tipo_attivita INTO v_piva, v_tipo
        FROM   public.ristoranti
        WHERE  user_id = v_queue_user_id AND COALESCE(sede_tecnica, FALSE) = FALSE
        ORDER  BY created_at
        LIMIT  1;

        IF v_piva IS NULL THEN
            RAISE EXCEPTION 'Nessuna sede reale per l''account %: impossibile creare la sede tecnica', v_queue_user_id;
        END IF;

        INSERT INTO public.ristoranti (
            user_id, nome_ristorante, partita_iva, attivo, sede_tecnica, sdi_attivo, tipo_attivita
        )
        VALUES (
            v_queue_user_id, 'Costi comuni di gruppo', v_piva, TRUE, TRUE, FALSE, v_tipo
        )
        RETURNING id INTO v_tecnica_id;
    END IF;

    UPDATE public.fatture_queue
    SET
        ristorante_id = v_tecnica_id,
        status        = 'pending',
        next_retry_at = now(),
        locked_at     = NULL,
        locked_by     = NULL,
        last_error    = NULL
    WHERE id = p_queue_id;

    RETURN v_tecnica_id;
END;
$function$;

-- Le default privileges del progetto danno EXECUTE nominale ad anon/authenticated
-- su ogni funzione creata: la revoca va ripetuta, nominando i ruoli.
REVOKE ALL ON FUNCTION public.assegna_fattura_a_sede_tecnica(bigint) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.assegna_fattura_a_sede_tecnica(bigint) TO service_role;
