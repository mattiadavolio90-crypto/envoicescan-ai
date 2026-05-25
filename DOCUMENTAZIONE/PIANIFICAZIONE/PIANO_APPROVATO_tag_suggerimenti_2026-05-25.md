# PIANO APPROVATO - Suggerimenti e Automazioni Tag
Data: 2026-05-25
Versione spec: PROPOSTA_ARCHITETTURALE_tag_suggerimenti_2026-05-25.md
Verifica: VERIFICA_CRITICA_tag_suggerimenti_2026-05-25.md

## Stato
- Blocchi residui: 0
- Ambiguita operative: 0
- Decisioni business pendenti: 0

## Decisioni operative congelate
1. Finestra analisi suggerimenti: 30 giorni.
2. Criterio minimo numero prodotti: 6 distinti.
3. Criterio minimo occorrenze cluster: 12.
4. Suggerimenti assistiti con conferma utente (no auto-aggancio silenzioso).
5. Notifiche doppio canale: inbox + callout in pagina Analisi e Tag.
6. Dedupe notifiche su bucket settimanale.

## Step plan approvato
### STEP 1 - Data model suggerimenti
**Obiettivo:** introdurre tabelle suggestion + RLS + indici base.
**File coinvolti:** migrations/080_create_custom_tag_suggestions.sql, migrations/081_add_tag_suggestion_indexes_and_rls_hardening.sql
**Operazioni in ordine:** create tabelle, trigger, policy, indici.
**Regole:** migrazioni sequenziali; no create index concurrently.
**Edge case:** replay migration idempotente.
**Test:** apply su Supabase locale, check RLS owner/service_role.
**Criterio di done:** schema disponibile e interrogabile.
**Rischio:** Medio
**Rollback:** drop oggetti introdotti.

### STEP 2 - Motore suggerimenti backend
**Obiettivo:** generare/upsert suggerimenti new_tag + extend_tag.
**File coinvolti:** services/tag_suggestion_service.py, services/db_service.py
**Operazioni in ordine:** pool 30g, scoring ibrido, upsert, API accept/dismiss/snooze.
**Regole:** nessuna modifica automatica alle associazioni senza accept esplicito.
**Edge case:** descrizioni vuote, match multipli, tag a limite max prodotti.
**Test:** unit test motore + workflow.
**Criterio di done:** endpoint/funzioni stabili e test verdi.
**Rischio:** Medio-Alto
**Rollback:** disable entrypoint UI e non invocare service.

### STEP 3 - UI Analisi e Tag
**Obiettivo:** rendere visibili e azionabili i suggerimenti in pagina 4.
**File coinvolti:** pages/4_analisi_personalizzata.py
**Operazioni in ordine:** sezione suggerimenti, CTA, conferme, refresh cache/version.
**Regole:** namespace session_state dedicato ap_sugg_*.
**Edge case:** nessun suggerimento, suggerimento stale, soglie trial.
**Test:** smoke UI + test helper puri nuovi.
**Criterio di done:** utente puo accettare/rinviare/ignorare senza regressioni gestione manuale.
**Rischio:** Medio
**Rollback:** feature flag off su sezione suggerimenti.

### STEP 4 - Notifiche inbox
**Obiettivo:** alert su entrambi i casi richiesti.
**File coinvolti:** services/notification_inbox_service.py, pages/5_notifiche_e_gestione.py, services/upload_handler.py
**Operazioni in ordine:** nuovi topic, bucket/dedupe, routing pagina, trigger post-upload.
**Regole:** anti-spam con dedupe settimanale.
**Edge case:** race su upload multipli ravvicinati.
**Test:** test topic + rendering pagina 5 + dedupe.
**Criterio di done:** badge/notifica corretti e navigazione a pagina 4.
**Rischio:** Medio
**Rollback:** disable topic generation.

### STEP 5 - Hardening e tuning
**Obiettivo:** calibrare soglie min_products/min_rows/min_score e ridurre falsi positivi.
**File coinvolti:** config/constants.py, services/tag_suggestion_service.py, test suite.
**Operazioni in ordine:** tuning soglie, metriche log, fix corner case.
**Regole:** mantenere default conservativi.
**Edge case:** tenant piccoli con bassa cardinalita.
**Test:** regression pack su custom tags e notifiche.
**Criterio di done:** precisione accettabile e UX non rumorosa.
**Rischio:** Medio
**Rollback:** reset soglie a default conservativo.

## Tech-debt tracciato
1. Introduzione source_type dedicato "tag" in notification_inbox_service per TTL esplicito.
2. Possibile ottimizzazione query con materializzazione giornaliera pool descrizioni (se carico aumenta).
3. Tuning progressivo fuzzy-score su dataset reali tenant piccoli/grandi.
4. Estensione export/delete account per includere eventuali campi feedback suggerimenti.

## Prontezza
Pronto per implementazione Step 1.
