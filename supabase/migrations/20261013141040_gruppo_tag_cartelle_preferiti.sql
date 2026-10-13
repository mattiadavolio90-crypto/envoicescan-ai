-- Tag di catena: cartelle per ordinare i tag e stella «preferito».
--
-- Calco di 20261013082535_tag_cartelle_preferiti.sql (tag di sede) sui tag di
-- catena, che sono dell'ACCOUNT (`gruppo_tags.user_id`, niente ristorante_id):
-- titolare e sotto-utenti con la Catena vedono la stessa organizzazione.
-- Pura visualizzazione: cartelle e stella non entrano in gruppo_tag_analisi,
-- nei fornitori, nel trend o nel briefing di catena.
--
-- Un tag sta in una sola cartella o in nessuna («Senza cartella»). La FK e'
-- COMPOSTA su (cartella_id, user_id): e' il DB stesso a rifiutare un tag nella
-- cartella di un altro account, anche se un endpoint dimenticasse il controllo.
-- Eliminare una cartella NON elimina i tag: `ON DELETE SET NULL (cartella_id)`
-- (PG >= 15) azzera solo la cartella e lascia user_id dov'e'.
--
-- Va applicata al live PRIMA del push: GET /api/gruppo/tag legge le colonne
-- nuove. Idempotente. service_role only: anon/authenticated nominati nella
-- REVOKE, perche' su Supabase hanno grant propri dalle default privileges.

CREATE TABLE IF NOT EXISTS public.gruppo_tag_cartelle (
    id         bigserial   PRIMARY KEY,
    user_id    uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    nome       text        NOT NULL,
    ordine     integer     NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT gruppo_tag_cartelle_nome_non_vuoto CHECK (btrim(nome) <> ''),
    CONSTRAINT gruppo_tag_cartelle_id_account_key UNIQUE (id, user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gruppo_tag_cartelle_unique_nome_ci
    ON public.gruppo_tag_cartelle (user_id, lower(btrim(nome)));

ALTER TABLE public.gruppo_tags ADD COLUMN IF NOT EXISTS cartella_id bigint;
ALTER TABLE public.gruppo_tags ADD COLUMN IF NOT EXISTS preferito boolean NOT NULL DEFAULT false;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'gruppo_tags_cartella_fkey'
          AND conrelid = 'public.gruppo_tags'::regclass
    ) THEN
        ALTER TABLE public.gruppo_tags
            ADD CONSTRAINT gruppo_tags_cartella_fkey
            FOREIGN KEY (cartella_id, user_id)
            REFERENCES public.gruppo_tag_cartelle (id, user_id)
            ON DELETE SET NULL (cartella_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_gruppo_tags_cartella
    ON public.gruppo_tags (cartella_id) WHERE cartella_id IS NOT NULL;

ALTER TABLE public.gruppo_tag_cartelle ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gruppo_tag_cartelle FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.gruppo_tag_cartelle FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.gruppo_tag_cartelle_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.gruppo_tag_cartelle TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.gruppo_tag_cartelle_id_seq TO service_role;

COMMENT ON TABLE public.gruppo_tag_cartelle IS
    'Cartelle dei tag di catena (scheda Tag di catena): solo ordine e visualizzazione, '
    'mai analisi. Per account (user_id). service_role only.';
COMMENT ON COLUMN public.gruppo_tag_cartelle.ordine IS
    'Posizione della cartella nella lista (0 = prima). Riscritta per intero dal riordino.';
COMMENT ON COLUMN public.gruppo_tags.cartella_id IS
    'Cartella del tag di catena; NULL = «Senza cartella». FK composta con user_id: '
    'la cartella e'' sempre dello stesso account del tag.';
COMMENT ON COLUMN public.gruppo_tags.preferito IS
    'Stella della vista «Preferiti» dei tag di catena. Per account, pura visualizzazione.';
