-- ============================================================
-- MIGRATION 055: Custom Tags per Analisi Personalizzata
-- ============================================================
-- Obiettivi:
-- 1. Creare i tag personalizzati per utente + ristorante
-- 2. Creare le associazioni tag <-> descrizioni fattura
-- 3. Salvare una descrizione_key normalizzata per matching robusto
-- 4. Aggiungere indici per lookup, join e aggregazioni
-- 5. Applicare RLS owner-based con pattern coerente alla migration 052

BEGIN;

-- ============================================================
-- 0. Funzione di normalizzazione descrizione_key
-- ============================================================
-- Normalizzazione minima e deterministica:
-- - trim spazi esterni
-- - uppercase
-- - collasso spazi multipli interni
CREATE OR REPLACE FUNCTION public.normalize_custom_tag_key(input_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT NULLIF(
        regexp_replace(
            upper(btrim(COALESCE(input_text, ''))),
            '\s+',
            ' ',
            'g'
        ),
        ''
    )
$$;

COMMENT ON FUNCTION public.normalize_custom_tag_key(TEXT)
IS 'Normalizza una descrizione libera in chiave stabile per custom tags (trim + uppercase + collapse spaces).';


-- ============================================================
-- 1. Tabella custom_tags
-- ============================================================
CREATE TABLE IF NOT EXISTS public.custom_tags (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ristorante_id UUID NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    emoji TEXT,
    colore TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT custom_tags_nome_non_vuoto CHECK (btrim(nome) <> ''),
    CONSTRAINT custom_tags_colore_hex_valido CHECK (
        colore IS NULL OR colore ~* '^#[0-9A-F]{6}$'
    )
);

COMMENT ON TABLE public.custom_tags
IS 'Tag personalizzati per aggregare descrizioni fattura equivalenti all interno dello stesso ristorante.';

COMMENT ON COLUMN public.custom_tags.nome
IS 'Nome libero del tag, con unicita case-insensitive per utente + ristorante.';

COMMENT ON COLUMN public.custom_tags.emoji
IS 'Emoji opzionale usata come indicatore visuale del tag.';

COMMENT ON COLUMN public.custom_tags.colore
IS 'Colore opzionale del tag in formato HEX #RRGGBB.';

-- Unicita case-insensitive senza introdurre estensioni tipo citext
CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_tags_unique_nome_ci
    ON public.custom_tags (user_id, ristorante_id, lower(btrim(nome)));

-- Indici operativi
CREATE INDEX IF NOT EXISTS idx_custom_tags_user_ristorante_created
    ON public.custom_tags (user_id, ristorante_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_custom_tags_ristorante_created
    ON public.custom_tags (ristorante_id, created_at DESC);


-- ============================================================
-- 2. Tabella custom_tag_prodotti
-- ============================================================
CREATE TABLE IF NOT EXISTS public.custom_tag_prodotti (
    id BIGSERIAL PRIMARY KEY,
    tag_id BIGINT NOT NULL REFERENCES public.custom_tags(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ristorante_id UUID NOT NULL REFERENCES public.ristoranti(id) ON DELETE CASCADE,
    descrizione TEXT NOT NULL,
    descrizione_key TEXT NOT NULL,
    fattore_kg NUMERIC(12,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT custom_tag_prodotti_descrizione_non_vuota CHECK (btrim(descrizione) <> ''),
    CONSTRAINT custom_tag_prodotti_descrizione_key_non_vuota CHECK (btrim(descrizione_key) <> ''),
    CONSTRAINT custom_tag_prodotti_fattore_kg_positivo CHECK (
        fattore_kg IS NULL OR fattore_kg > 0
    )
);

COMMENT ON TABLE public.custom_tag_prodotti
IS 'Associazioni tra tag personalizzati e descrizioni fattura, con chiave normalizzata per matching interno.';

COMMENT ON COLUMN public.custom_tag_prodotti.descrizione
IS 'Descrizione originale selezionata dall utente e mostrata in UI.';

COMMENT ON COLUMN public.custom_tag_prodotti.descrizione_key
IS 'Chiave interna normalizzata usata per matching, deduplica e filtri.';

COMMENT ON COLUMN public.custom_tag_prodotti.fattore_kg
IS 'Conversione manuale opzionale verso unita base normalizzata (es. 0.25 per confezione da 250g).';

-- Unicita per tag sulla chiave normalizzata
CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_tag_prodotti_unique_tag_desc_key
    ON public.custom_tag_prodotti (tag_id, descrizione_key);

-- Indici per query applicative e aggregazioni
CREATE INDEX IF NOT EXISTS idx_custom_tag_prodotti_tag_id
    ON public.custom_tag_prodotti (tag_id);

CREATE INDEX IF NOT EXISTS idx_custom_tag_prodotti_user_rist_desc_key
    ON public.custom_tag_prodotti (user_id, ristorante_id, descrizione_key);

CREATE INDEX IF NOT EXISTS idx_custom_tag_prodotti_rist_desc_key
    ON public.custom_tag_prodotti (ristorante_id, descrizione_key);

CREATE INDEX IF NOT EXISTS idx_custom_tag_prodotti_user_rist_created
    ON public.custom_tag_prodotti (user_id, ristorante_id, created_at DESC);


-- ============================================================
-- 3. Trigger di allineamento e normalizzazione
-- ============================================================
CREATE OR REPLACE FUNCTION public.custom_tag_prodotti_prepare_row()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id UUID;
    v_ristorante_id UUID;
BEGIN
    NEW.descrizione := btrim(NEW.descrizione);
    NEW.descrizione_key := public.normalize_custom_tag_key(NEW.descrizione);

    IF NEW.descrizione_key IS NULL THEN
        RAISE EXCEPTION 'descrizione_key vuota non consentita';
    END IF;

    SELECT ct.user_id, ct.ristorante_id
      INTO v_user_id, v_ristorante_id
      FROM public.custom_tags AS ct
     WHERE ct.id = NEW.tag_id;

    IF v_user_id IS NULL OR v_ristorante_id IS NULL THEN
        RAISE EXCEPTION 'tag_id % non valido o ownership non trovata', NEW.tag_id;
    END IF;

    NEW.user_id := v_user_id;
    NEW.ristorante_id := v_ristorante_id;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.custom_tag_prodotti_prepare_row()
IS 'Normalizza descrizione_key e riallinea user_id + ristorante_id al tag padre prima di INSERT o UPDATE.';

DROP TRIGGER IF EXISTS trg_custom_tag_prodotti_prepare_row ON public.custom_tag_prodotti;

CREATE TRIGGER trg_custom_tag_prodotti_prepare_row
    BEFORE INSERT OR UPDATE ON public.custom_tag_prodotti
    FOR EACH ROW
    EXECUTE FUNCTION public.custom_tag_prodotti_prepare_row();


-- ============================================================
-- 4. RLS owner-based (pattern coerente alla migration 052)
-- ============================================================
DO $$
DECLARE
    v_table TEXT;
    v_policy RECORD;
    v_sequence TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['custom_tags', 'custom_tag_prodotti']
    LOOP
        IF to_regclass('public.' || v_table) IS NULL THEN
            RAISE NOTICE 'Skip public.%: tabella non trovata', v_table;
            CONTINUE;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns AS c
            WHERE c.table_schema = 'public'
              AND c.table_name = v_table
              AND c.column_name = 'user_id'
        ) THEN
            RAISE NOTICE 'Skip public.%: colonna user_id non trovata', v_table;
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', v_table);

        FOR v_policy IN
            SELECT p.policyname
            FROM pg_policies AS p
            WHERE p.schemaname = 'public'
              AND p.tablename = v_table
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', v_policy.policyname, v_table);
        END LOOP;

        EXECUTE format('REVOKE ALL ON public.%I FROM anon', v_table);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', v_table);

        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (user_id = auth.uid())',
            v_table || '_select_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid())',
            v_table || '_insert_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())',
            v_table || '_update_own',
            v_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (user_id = auth.uid())',
            v_table || '_delete_own',
            v_table
        );

        FOR v_sequence IN
            SELECT format('%I.%I', seq_ns.nspname, seq.relname)
            FROM pg_class AS seq
            JOIN pg_namespace AS seq_ns
              ON seq_ns.oid = seq.relnamespace
            JOIN pg_depend AS dep
              ON dep.objid = seq.oid
             AND dep.deptype = 'a'
            JOIN pg_class AS tbl
              ON tbl.oid = dep.refobjid
            JOIN pg_namespace AS tbl_ns
              ON tbl_ns.oid = tbl.relnamespace
            WHERE seq.relkind = 'S'
              AND tbl_ns.nspname = 'public'
              AND tbl.relname = v_table
        LOOP
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO authenticated', v_sequence);
        END LOOP;
    END LOOP;
END;
$$;

-- Policy esplicita service_role per chiarezza operativa e coerenza con migration 054.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'custom_tags' AND policyname = 'Service role full access custom_tags'
    ) THEN
        EXECUTE 'CREATE POLICY "Service role full access custom_tags" ON public.custom_tags
            FOR ALL TO service_role USING (true) WITH CHECK (true)';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'custom_tag_prodotti' AND policyname = 'Service role full access custom_tag_prodotti'
    ) THEN
        EXECUTE 'CREATE POLICY "Service role full access custom_tag_prodotti" ON public.custom_tag_prodotti
            FOR ALL TO service_role USING (true) WITH CHECK (true)';
    END IF;
END $$;

COMMIT;