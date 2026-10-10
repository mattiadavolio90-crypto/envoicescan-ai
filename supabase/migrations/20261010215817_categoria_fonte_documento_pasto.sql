-- Fase K2 (10/10/2026): nuova fonte di categoria `L0_documento_pasto`.
--
-- La fattura di un locale dove si e' mangiato (c'e' la riga del coperto) va tutta
-- in RAPPRESENTANZA, decisione di Mattia: lo fa `applica_regola_documento_pasto`
-- (services/ai_service.py), che scrive questa fonte con fiducia "certa". Il comment
-- della colonna elenca le fonti che il codice emette: senza questa riga mentirebbe
-- (presidio: tests/test_provenienza_categoria.py, nei due versi).
--
-- Solo documentazione nel DB: nessun dato cambia. Idempotente.

comment on column public.fatture.categoria_fonte is
    'Livello che ha deciso la categoria. Valori emessi dal codice: '
    'correzione_cliente, correzione_admin (un umano ha guardato la riga: fonte piu'' attendibile); '
    'L0_fornitore, L0_documento_pasto, L1_admin, L1_5_non_negoziabile, L2_locale, L4_dicitura, '
    'L7_regola_forte, AI_confermata (fiducia "certa"); '
    'L3_globale, L5_fornitore, L6_um, L7_dizionario, AI_alta (fiducia "probabile"); '
    'nessuna (riga rimasta in coda: nessun livello l''ha decisa). '
    'NULL = legacy (riga scritta prima della Fase 2, o decisione annullata): '
    'si tratta come certa, mai come dubbia.';
