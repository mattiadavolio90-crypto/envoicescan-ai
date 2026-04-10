-- Migration 054: Assicura che RLS sia abilitato sulla tabella fatture
-- 
-- La migration 011 ha creato le policy (SELECT, INSERT, UPDATE, DELETE)
-- con filtro user_id + ristorante_id, ma non ha eseguito
-- ALTER TABLE ... ENABLE ROW LEVEL SECURITY.
--
-- Questa migration:
-- 1. Abilita RLS sulla tabella fatture (idempotente)  
-- 2. NON ricrea le policy — sono già presenti dalla migration 011
--    ("Users can view/insert/update/delete own fatture per ristorante")
-- 
-- Verifica pre-applicazione:
--   SELECT relname, relrowsecurity FROM pg_class WHERE relname = 'fatture';
--   Se relrowsecurity = true, la migration è un no-op sicuro.

ALTER TABLE public.fatture ENABLE ROW LEVEL SECURITY;

-- Policy di servizio per service_role (bypass automatico via SECURITY DEFINER,
-- ma aggiungiamo policy esplicita per chiarezza e per anon-blocked safety)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'fatture' AND policyname = 'Service role full access fatture'
    ) THEN
        EXECUTE 'CREATE POLICY "Service role full access fatture" ON public.fatture
            FOR ALL TO service_role USING (true) WITH CHECK (true)';
    END IF;
END $$;
