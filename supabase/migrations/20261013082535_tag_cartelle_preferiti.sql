-- Analisi e Tag: cartelle per ordinare i tag di sede e stella «preferito».
--
-- Pura visualizzazione: cartelle e stella non entrano in analizza_tag, nel
-- briefing, nella catena o nei margini. Sono PER SEDE come i tag
-- (`custom_tags.user_id + ristorante_id`): titolare e sotto-utenti della sede
-- vedono la stessa organizzazione.
--
-- Un tag sta in una sola cartella o in nessuna («Senza cartella»). La FK e'
-- COMPOSTA su (cartella_id, user_id, ristorante_id): e' il DB stesso a rifiutare
-- un tag nella cartella di un'altra sede o di un altro cliente, anche se un
-- endpoint dimenticasse il controllo. Eliminare una cartella NON elimina i tag:
-- `ON DELETE SET NULL (cartella_id)` (PG >= 15) azzera solo la cartella e lascia
-- user_id e ristorante_id dove sono — un SET NULL sull'intera chiave li
-- annullerebbe e violerebbe il NOT NULL.
--
-- Va applicata al live PRIMA del push: GET /api/tag legge le colonne nuove.
-- Idempotente. service_role only: anon/authenticated nominati nella REVOKE,
-- perche' su Supabase hanno grant propri dalle default privileges.

CREATE TABLE IF NOT EXISTS public.custom_tag_cartelle (
    id            bigserial   PRIMARY KEY,
    user_id       uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ristorante_id uuid        NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    nome          text        NOT NULL,
    ordine        integer     NOT NULL DEFAULT 0,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT custom_tag_cartelle_nome_non_vuoto CHECK (btrim(nome) <> ''),
    CONSTRAINT custom_tag_cartelle_id_tenant_key UNIQUE (id, user_id, ristorante_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_tag_cartelle_unique_nome_ci
    ON public.custom_tag_cartelle (user_id, ristorante_id, lower(btrim(nome)));

ALTER TABLE public.custom_tags ADD COLUMN IF NOT EXISTS cartella_id bigint;
ALTER TABLE public.custom_tags ADD COLUMN IF NOT EXISTS preferito boolean NOT NULL DEFAULT false;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'custom_tags_cartella_fkey'
          AND conrelid = 'public.custom_tags'::regclass
    ) THEN
        ALTER TABLE public.custom_tags
            ADD CONSTRAINT custom_tags_cartella_fkey
            FOREIGN KEY (cartella_id, user_id, ristorante_id)
            REFERENCES public.custom_tag_cartelle (id, user_id, ristorante_id)
            ON DELETE SET NULL (cartella_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_custom_tags_cartella
    ON public.custom_tags (cartella_id) WHERE cartella_id IS NOT NULL;

ALTER TABLE public.custom_tag_cartelle ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_tag_cartelle FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.custom_tag_cartelle FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.custom_tag_cartelle_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.custom_tag_cartelle TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.custom_tag_cartelle_id_seq TO service_role;

COMMENT ON TABLE public.custom_tag_cartelle IS
    'Cartelle dei tag di sede (Analisi e Tag): solo ordine e visualizzazione, mai '
    'analisi. Per sede (user_id + ristorante_id). service_role only.';
COMMENT ON COLUMN public.custom_tag_cartelle.ordine IS
    'Posizione della cartella nella barra (0 = prima). Riscritta per intero dal riordino.';
COMMENT ON COLUMN public.custom_tags.cartella_id IS
    'Cartella del tag; NULL = «Senza cartella». FK composta con user_id e '
    'ristorante_id: la cartella e'' sempre della stessa sede del tag.';
COMMENT ON COLUMN public.custom_tags.preferito IS
    'Stella della vista «Preferiti» di Analisi e Tag. Per sede, pura visualizzazione.';
