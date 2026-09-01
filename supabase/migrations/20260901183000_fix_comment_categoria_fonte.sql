-- Il comment di `fatture.categoria_fonte` (migration 20260901170000) elencava valori
-- che il codice non emette e ne ometteva uno che emette. Trovato in code review.
--
-- Un comment di colonna e' documentazione che vive nel DB: se mente, mente a chiunque
-- ispezioni lo schema per capire cosa contiene quel campo — ed e' esattamente il tipo
-- di documentazione che nessun test copre.
--
-- Divergenze corrette:
--   - `L3_globale_non_verificata`: MAI emesso (0 occorrenze nel codice). Era previsto
--     dal piano ma non implementato: la distinzione verified/non-verified della memoria
--     globale non e' mai stata portata nella provenienza.
--   - `correzione_cliente` / `correzione_admin`: OMESSI, ma sono i valori scritti dai
--     quattro endpoint di correzione manuale e dalla propagazione admin.
--
-- Elenco allineato a `_FONTI_CERTE | _FONTI_PROBABILI | {nessuna}` in services/ai_service.py.

comment on column public.fatture.categoria_fonte is
    'Livello che ha deciso la categoria. Valori emessi dal codice: '
    'correzione_cliente, correzione_admin (un umano ha guardato la riga: fonte piu'' attendibile); '
    'L0_fornitore, L1_admin, L1_5_non_negoziabile, L2_locale, L4_dicitura, L7_regola_forte, '
    'AI_confermata (fiducia "certa"); '
    'L3_globale, L5_fornitore, L6_um, L7_dizionario, AI_alta (fiducia "probabile"); '
    'nessuna (riga rimasta in coda: nessun livello l''ha decisa). '
    'NULL = legacy (riga scritta prima della Fase 2, o decisione annullata): '
    'si tratta come certa, mai come dubbia.';
