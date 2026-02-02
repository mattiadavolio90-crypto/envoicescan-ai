-- ═══════════════════════════════════════════════════════════════════════════════
-- MIGRAZIONE 015: Popola ristoranti mancanti
-- ═══════════════════════════════════════════════════════════════════════════════
-- Obiettivo: Creare record ristoranti per utenti esistenti senza ristoranti
-- Data: 2026-02-02
-- ═══════════════════════════════════════════════════════════════════════════════

BEGIN;

-- Inserisci ristoranti per utenti che non hanno record nella tabella ristoranti
INSERT INTO ristoranti (user_id, nome_ristorante, partita_iva, ragione_sociale, attivo)
SELECT 
    u.id,
    u.nome_ristorante,
    u.partita_iva,
    u.ragione_sociale,
    u.attivo
FROM users u
WHERE u.partita_iva IS NOT NULL
  AND u.partita_iva != ''
  AND NOT EXISTS (
      SELECT 1 
      FROM ristoranti r 
      WHERE r.user_id = u.id
  );

-- Verifica quanti record sono stati inseriti
-- SELECT COUNT(*) as ristoranti_creati FROM ristoranti;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- VERIFICA POST-MIGRAZIONE
-- ═══════════════════════════════════════════════════════════════════════════════
-- Esegui questa query per verificare:
-- SELECT u.email, u.nome_ristorante, r.id as ristorante_id
-- FROM users u
-- LEFT JOIN ristoranti r ON r.user_id = u.id
-- WHERE u.partita_iva IS NOT NULL
-- ORDER BY u.created_at DESC;
