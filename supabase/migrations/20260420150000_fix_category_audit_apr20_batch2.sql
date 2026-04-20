-- ============================================================
-- Migration: fix_category_audit_apr20_batch2
-- Data: 20 aprile 2026
-- Scopo: Correzione 7 prodotti "Da Classificare" + 2 errori categorizzazione
-- ============================================================

BEGIN;

-- 1. DENTICI / PAGARO / PAGRUS → PESCE
UPDATE fatture
SET categoria = 'PESCE'
WHERE UPPER(descrizione) LIKE '%DENTICI%PAGARO%'
   OR UPPER(descrizione) LIKE '%PAGRO MAGGIORE%'
   OR UPPER(descrizione) LIKE '%PAGRUS MAJOR%';

-- 2. UNICUM → AMARI/LIQUORI
UPDATE fatture
SET categoria = 'AMARI/LIQUORI'
WHERE UPPER(descrizione) LIKE '%UNICUM%CL%';

-- 3. MALIBU' → AMARI/LIQUORI
UPDATE fatture
SET categoria = 'AMARI/LIQUORI'
WHERE UPPER(descrizione) LIKE '%MALIBU%CL%';

-- 4. LIQ.ANIMA NERA MARZADRO → AMARI/LIQUORI
UPDATE fatture
SET categoria = 'AMARI/LIQUORI'
WHERE UPPER(descrizione) LIKE '%LIQ%ANIMA NERA%MARZADRO%';

-- 5. PISELLI FINI → VERDURE
UPDATE fatture
SET categoria = 'VERDURE'
WHERE UPPER(descrizione) LIKE '%PISELLI FINI%KG%';

-- 6. LIEVITO FRESCO LIEVITAL → SECCO
UPDATE fatture
SET categoria = 'SECCO'
WHERE UPPER(descrizione) LIKE '%LIEVITO%LIEVITAL%';

-- 7. SALV.LIMONE TNT → MATERIALE DI CONSUMO
UPDATE fatture
SET categoria = 'MATERIALE DI CONSUMO'
WHERE UPPER(descrizione) LIKE '%SALV%TNT%';

-- 8. TORTELLI SURGITAL → SECCO
UPDATE fatture
SET categoria = 'SECCO'
WHERE UPPER(descrizione) LIKE '%TORTELLI%SURGITAL%';

-- ============================================================
-- Aggiorna prodotti_utente corrispondenti
-- ============================================================

UPDATE prodotti_utente
SET categoria = 'PESCE'
WHERE UPPER(descrizione) LIKE '%DENTICI%PAGARO%'
   OR UPPER(descrizione) LIKE '%PAGRO MAGGIORE%'
   OR UPPER(descrizione) LIKE '%PAGRUS MAJOR%';

UPDATE prodotti_utente
SET categoria = 'AMARI/LIQUORI'
WHERE UPPER(descrizione) LIKE '%UNICUM%CL%'
   OR UPPER(descrizione) LIKE '%MALIBU%CL%'
   OR UPPER(descrizione) LIKE '%LIQ%ANIMA NERA%MARZADRO%';

UPDATE prodotti_utente
SET categoria = 'VERDURE'
WHERE UPPER(descrizione) LIKE '%PISELLI FINI%KG%';

UPDATE prodotti_utente
SET categoria = 'SECCO'
WHERE UPPER(descrizione) LIKE '%LIEVITO%LIEVITAL%'
   OR UPPER(descrizione) LIKE '%TORTELLI%SURGITAL%';

UPDATE prodotti_utente
SET categoria = 'MATERIALE DI CONSUMO'
WHERE UPPER(descrizione) LIKE '%SALV%TNT%';

-- ============================================================
-- Upsert prodotti_master per prodotti nuovi
-- ============================================================

INSERT INTO prodotti_master (descrizione, categoria, confidence)
VALUES
  ('DENTICI O PAGARO MAGGIORE 1000+ FRESCO PAGRUS MAJOR ALLEVATE GRECIA', 'PESCE', 'alta'),
  ('PAGRO MAGGIORE 600+ FRESCO ALLEVATO PAGRUS MAJOR ALLEVATE GRECIA', 'PESCE', 'alta'),
  ('UNICUM CL.70', 'AMARI/LIQUORI', 'alta'),
  ('MALIBU'' CL.100', 'AMARI/LIQUORI', 'alta'),
  ('LIQ.ANIMA NERA CL.70 21GR MARZADRO', 'AMARI/LIQUORI', 'alta'),
  ('PISELLI FINI KG.2,5', 'VERDURE', 'alta'),
  ('LIEVITO FRESCO G.25X2 LIEVITAL', 'SECCO', 'alta'),
  ('SALV.LIMONE X100 TNT 70X100', 'MATERIALE DI CONSUMO', 'alta'),
  ('TORTELLI AL RADICCH.ROSSO KG.3 SURGITAL', 'SECCO', 'alta')
ON CONFLICT (descrizione) DO UPDATE SET
  categoria = EXCLUDED.categoria,
  confidence = EXCLUDED.confidence;

COMMIT;
