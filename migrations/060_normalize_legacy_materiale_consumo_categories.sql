-- MIGRAZIONE 060: Normalizza categorie legacy per clienti esistenti
-- Converte eventuali alias storici in 'MATERIALE DI CONSUMO'
-- senza toccare la logica corrente di raggruppamento.

-- Assicura la presenza della categoria canonica nella tabella categorie
INSERT INTO public.categorie (nome, icona, ordinamento, attiva)
VALUES ('MATERIALE DI CONSUMO', '📦', 900, TRUE)
ON CONFLICT (nome) DO UPDATE
SET icona = EXCLUDED.icona,
    ordinamento = LEAST(public.categorie.ordinamento, EXCLUDED.ordinamento),
    attiva = TRUE,
    updated_at = NOW();

-- Disattiva alias storici nella lookup table categorie (se presenti)
UPDATE public.categorie
SET attiva = FALSE,
    updated_at = NOW()
WHERE nome IN ('NO FOOD', 'MATERIALI', 'MATERIALE CONSUMO', 'MATERIALI CONSUMO');

-- Allinea le fatture storiche già caricate dai clienti
UPDATE public.fatture
SET categoria = 'MATERIALE DI CONSUMO'
WHERE UPPER(TRIM(COALESCE(categoria, ''))) IN (
    'NO FOOD',
    'MATERIALI',
    'MATERIALE CONSUMO',
    'MATERIALI CONSUMO'
);

DO $$
BEGIN
    -- Memoria globale condivisa
    IF to_regclass('public.prodotti_master') IS NOT NULL THEN
        UPDATE public.prodotti_master
        SET categoria = 'MATERIALE DI CONSUMO'
        WHERE UPPER(TRIM(COALESCE(categoria, ''))) IN (
            'NO FOOD',
            'MATERIALI',
            'MATERIALE CONSUMO',
            'MATERIALI CONSUMO'
        );
    END IF;

    -- Memoria locale dei singoli clienti
    IF to_regclass('public.prodotti_utente') IS NOT NULL THEN
        UPDATE public.prodotti_utente
        SET categoria = 'MATERIALE DI CONSUMO',
            updated_at = NOW()
        WHERE UPPER(TRIM(COALESCE(categoria, ''))) IN (
            'NO FOOD',
            'MATERIALI',
            'MATERIALE CONSUMO',
            'MATERIALI CONSUMO'
        );
    END IF;

    -- Correzioni manuali admin storiche
    IF to_regclass('public.classificazioni_manuali') IS NOT NULL THEN
        UPDATE public.classificazioni_manuali
        SET categoria_corretta = 'MATERIALE DI CONSUMO'
        WHERE UPPER(TRIM(COALESCE(categoria_corretta, ''))) IN (
            'NO FOOD',
            'MATERIALI',
            'MATERIALE CONSUMO',
            'MATERIALI CONSUMO'
        );
    END IF;
END $$;