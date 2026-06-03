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

## Perché non è stata cancellata/spostata

I file sono citati in `DOCUMENTAZIONE/` e in un messaggio UI di `pages/admin.py`
(Streamlit, in dismissione). Spostarli romperebbe quei riferimenti testuali senza
beneficio. Alla dismissione di Streamlit (Fase 10-11) questa cartella e i suoi
riferimenti possono essere archiviati/rimossi del tutto.

## Regola operativa

➡️ **Nuova migration = nuovo file in `supabase/migrations/AAAAMMGGHHMMSS_nome.sql`.**
