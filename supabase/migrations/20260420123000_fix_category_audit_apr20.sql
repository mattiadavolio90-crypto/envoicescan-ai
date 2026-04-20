-- Audit categorizzazione 20 aprile 2026
-- Corregge prodotti già presenti nel DB e rafforza la memoria globale.

-- 1) Allinea fatture storiche già salvate
UPDATE public.fatture
SET categoria = 'SCATOLAME E CONSERVE'
WHERE UPPER(COALESCE(descrizione, '')) LIKE '%CARPACCIO%TARTUF%';

UPDATE public.fatture
SET categoria = 'OLIO E CONDIMENTI'
WHERE UPPER(COALESCE(descrizione, '')) LIKE '%ACETO%RISO%';

UPDATE public.fatture
SET categoria = 'PESCE'
WHERE UPPER(COALESCE(descrizione, '')) LIKE '%UNAGI%';

UPDATE public.fatture
SET categoria = 'SECCO'
WHERE UPPER(COALESCE(descrizione, '')) ~ '(RAVIOLI|SHAO ?MAI|SIU ?MAI|GYOZA|HAUKAU|HAR ?GAU|DIM ?SUM)';

-- 2) Allinea memoria locale cliente già esistente
UPDATE public.prodotti_utente
SET categoria = 'SCATOLAME E CONSERVE',
    updated_at = NOW(),
    classificato_da = 'admin-audit'
WHERE UPPER(COALESCE(descrizione, '')) LIKE '%CARPACCIO%TARTUF%';

UPDATE public.prodotti_utente
SET categoria = 'OLIO E CONDIMENTI',
    updated_at = NOW(),
    classificato_da = 'admin-audit'
WHERE UPPER(COALESCE(descrizione, '')) LIKE '%ACETO%RISO%';

UPDATE public.prodotti_utente
SET categoria = 'PESCE',
    updated_at = NOW(),
    classificato_da = 'admin-audit'
WHERE UPPER(COALESCE(descrizione, '')) LIKE '%UNAGI%';

UPDATE public.prodotti_utente
SET categoria = 'SECCO',
    updated_at = NOW(),
    classificato_da = 'admin-audit'
WHERE UPPER(COALESCE(descrizione, '')) ~ '(RAVIOLI|SHAO ?MAI|SIU ?MAI|GYOZA|HAUKAU|HAR ?GAU|DIM ?SUM)';

-- 3) Rafforza memoria globale condivisa per ricorrenze future
INSERT INTO public.prodotti_master (descrizione, categoria, confidence, volte_visto, classificato_da)
VALUES
  ('G180CARPACCIO TARTUFO NERO EST', 'SCATOLAME E CONSERVE', 'alta', 1, 'admin-audit'),
  ('MIZKAN SHIRAGIKU ACETO DI RISO 20LT', 'OLIO E CONDIMENTI', 'alta', 1, 'admin-audit'),
  ('UNAGI KABAYAKI 240-275G #4968 (10KG)2*5KG', 'PESCE', 'alta', 1, 'admin-audit'),
  ('RAVIOLI DI GAMBERI HAUKAU - AT ( )5*2KG', 'SECCO', 'alta', 1, 'admin-audit')
ON CONFLICT (descrizione)
DO UPDATE SET
  categoria = EXCLUDED.categoria,
  confidence = 'alta',
  classificato_da = 'admin-audit',
  ultima_modifica = NOW();
