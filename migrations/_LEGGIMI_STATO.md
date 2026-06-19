# ⚠️ Cartella `migrations/` — LEGACY (storica)

**Questa cartella NON è più la fonte autorevole delle migration.**

## Stato (dal 2026-06-03)

- La **fonte unica** delle migration è `supabase/migrations/` (formato timestamp,
  gestita dalla Supabase CLI). Tutte le migration nuove vanno **solo** lì.
- Questa cartella `migrations/` (numerazione `001`–`081`) è **storica**: contiene
  migration già applicate al DB di produzione in passato. Alcuni numeri sono
  **duplicati** (due `003`, `005`, `022`, `033`, `038`, `039`, `050`, `071`, `072`)
  — residuo di sviluppo, non affidarsi alla numerazione per dedurre l'ordine reale.
- **Lo stato reale applicato** è quello del DB live: verificarlo con
  `supabase migration list` o interrogando lo schema, NON leggendo questi file.

## Perché non è ancora stata rimossa

Nessun runtime, CI o `supabase/config.toml` legge questa cartella (verificato
19/06): è inerte. Gli unici riferimenti residui sono testo in `DOCUMENTAZIONE/` e
un messaggio UI in `pages/admin.py:2683` — **codice Streamlit ormai morto** (frontend
migrato a Next.js, container Streamlit eliminato).

Le condizioni per la rimozione/archiviazione completa sono quindi soddisfatte. Non
è stata fatta ora solo per non muovere 91 file storici a ridosso del go-live (1/7) e
perdere la traccia di audit. **Da archiviare con calma dopo il go-live** (es.
`git mv migrations/ docs/legacy_migrations/`), insieme alla pulizia delle pagine
Streamlit residue in `pages/`.

## Riconciliazione repo ↔ DB live (19/06)

Confrontato `supabase/migrations/` (92 file) con la storia applicata sul DB live
(90 migration, `supabase migration list`). Esito:
- **Nessuna migration "fantasma" pericolosa**: il DB live è la fonte di verità e
  combacia con lo schema atteso.
- Alcune migration applicate hanno **timestamp/nome di file diverso** da quello
  registrato in `schema_migrations` (es. live `rpc_costi_automatici_mensili_food_catchall`
  = file `20260618120000_rpc_costi_food_catchall.sql`): è il comportamento normale di
  `apply_migration`, NON un buco.
- Colmato il solo buco pulito dell'audit odierno: ricreato il file
  `20260619154015_fix_rls_tabelle_nuove_app_settings_assistant_prezzi.sql` dal contenuto
  reale in `schema_migrations` (era applicato senza file repo).
- Restano alcune migration STORICHE applicate senza file canonico (`add_piano_inizio_at_to_users`,
  `082_add_chat_operation_type`, `remove_pagine_abilitate_default`, `restrict_soft_delete_rpc_grants`,
  `create_app_settings`, `fix_log_category_change_all_optional_fields`, `rpc_costi_automatici_mensili_food_catchall`).
  Il loro SQL è recuperabile da `supabase_migrations.schema_migrations.statements`.
  NON ricostruite ora: pre-esistenti, non-blocker, alcune di dominio chat (sessione
  parallela). Da fare con calma post go-live se si vuole parità 1:1 file↔DB.

## Regola operativa

➡️ **Nuova migration = nuovo file in `supabase/migrations/AAAAMMGGHHMMSS_nome.sql`.**
