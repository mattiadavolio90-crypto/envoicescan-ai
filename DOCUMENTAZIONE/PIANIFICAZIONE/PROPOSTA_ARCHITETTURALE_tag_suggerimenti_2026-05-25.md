# PROPOSTA ARCHITETTURALE - Suggerimenti e Automazioni Tag
Data: 2026-05-25
Input approvato: BRIEFING_tag_suggerimenti_2026-05-24.md

## 0) Obiettivo implementativo
Introdurre in Analisi e Tag due automazioni assistite:
1. Suggerimento creazione nuovo tag quando emerge un cluster coerente di prodotti.
2. Suggerimento aggiunta prodotti a tag esistenti quando arrivano nuove descrizioni reclutabili.

Vincoli confermati:
- finestra analisi = ultimi 30 giorni
- criterio temporale + criterio minimo numero prodotti
- nessun auto-aggancio silenzioso: sempre conferma utente
- notifiche su entrambi i casi

## 1) Mappatura file coinvolti
### File da modificare
- pages/4_analisi_personalizzata.py
- services/db_service.py
- services/notification_inbox_service.py
- pages/5_notifiche_e_gestione.py
- config/constants.py
- tests/test_custom_tags.py
- tests/test_db_service.py
- tests/test_notification_inbox_service.py

### File nuovi proposti
- services/tag_suggestion_service.py
- migrations/080_create_custom_tag_suggestions.sql
- migrations/081_add_tag_suggestion_indexes_and_rls_hardening.sql
- tests/test_tag_suggestion_service.py

### File candidati a cleanup (dopo stabilizzazione)
- nessuno in questa fase (no rimozioni necessarie)

## 2) Analisi modello dati reale (stato attuale)
Stato verificato:
- custom_tags: tag per user_id + ristorante_id, nome univoco case-insensitive.
- custom_tag_prodotti: associazioni tag-descrizione_key, con trigger di normalizzazione e allineamento ownership.
- RLS owner-based gia presente su entrambe le tabelle.
- notification_inbox gia attiva con dedupe_key + topic_key + source_type.

Gap funzionale:
- manca persistenza strutturata dei suggerimenti (pending/accepted/dismissed/snooze).
- manca storico feedback utile a ridurre falsi positivi.

## 3) Schema dati proposto (definitivo)
### 3.1 Nuova tabella: custom_tag_suggestions
Scopo: rappresentare il suggerimento ad alto livello.

Campi principali:
- id BIGSERIAL PK
- user_id UUID NOT NULL
- ristorante_id UUID NOT NULL
- suggestion_type TEXT NOT NULL
  - valori: new_tag | extend_tag
- status TEXT NOT NULL DEFAULT 'pending'
  - valori: pending | accepted | dismissed | snoozed
- suggested_tag_name TEXT NULL
- target_tag_id BIGINT NULL (FK custom_tags.id)
- cluster_key TEXT NOT NULL
- confidence_score NUMERIC(5,2) NULL
- detection_window_days INT NOT NULL DEFAULT 30
- matched_products_count INT NOT NULL DEFAULT 0
- matched_rows_count INT NOT NULL DEFAULT 0
- first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
- last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
- snooze_until TIMESTAMPTZ NULL
- feedback_note TEXT NULL
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()
- updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

Vincoli:
- check su suggestion_type/status
- unique (user_id, ristorante_id, suggestion_type, cluster_key, status='pending') via indice parziale

### 3.2 Nuova tabella: custom_tag_suggestion_items
Scopo: dettaglio prodotti/descrizioni inclusi nel suggerimento.

Campi principali:
- id BIGSERIAL PK
- suggestion_id BIGINT NOT NULL FK custom_tag_suggestions(id) ON DELETE CASCADE
- user_id UUID NOT NULL
- ristorante_id UUID NOT NULL
- descrizione TEXT NOT NULL
- descrizione_key TEXT NOT NULL
- occorrenze INT NOT NULL DEFAULT 1
- fornitori_count INT NOT NULL DEFAULT 0
- last_seen_date DATE NULL
- selected_by_default BOOLEAN NOT NULL DEFAULT true
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()

Vincoli:
- unique (suggestion_id, descrizione_key)
- check occorrenze >= 1

### 3.3 RLS e indici obbligatori
- RLS owner-based user_id = auth.uid() coerente con pattern migration 055/061.
- Indici obbligatori su:
  - (user_id, ristorante_id, status, updated_at desc)
  - (user_id, ristorante_id, suggestion_type, status)
  - (user_id, ristorante_id, last_seen_at desc)
  - (ristorante_id, status)
- Indici items:
  - (suggestion_id)
  - (user_id, ristorante_id, descrizione_key)
  - (ristorante_id, descrizione_key)

Nota multi-tenant: ogni record suggestion/items include user_id + ristorante_id espliciti.

## 4) Migration plan numerato
1. 080_create_custom_tag_suggestions.sql
   - create custom_tag_suggestions
   - create custom_tag_suggestion_items
   - trigger updated_at
   - trigger normalizzazione descrizione_key (riuso normalize_custom_tag_key)
   - RLS base + policy service_role
2. 081_add_tag_suggestion_indexes_and_rls_hardening.sql
   - indici addizionali performance
   - unique parziale pending per dedupe applicativa
   - cleanup eventuali policy duplicate e allineamento pattern security

Rollback:
- migrazione inversa: drop tabelle nuove + trigger + policy create in 080/081.
- nessun impatto su tabelle esistenti custom_tags/custom_tag_prodotti.

## 5) Motore suggerimenti (logica proposta)
### 5.1 Input dati
Fonte primaria: fatture ultimi 30 giorni (deleted_at is null) aggregata per descrizione_key, con campi:
- descrizione canonica
- occorrenze
- fornitori_count
- ultima_data

### 5.2 Regole core (v1)
- Criterio temporale: riga in finestra 30 giorni.
- Criterio quantita prodotti: minimo prodotti distinti per suggerimento (default proposto = 6).
- Criterio robustezza: minimo occorrenze aggregate cluster (default proposto = 12).

### 5.3 Tipi suggerimento
A) new_tag
- cluster di descrizioni non ancora mappate in tag coerente per token dominante/fuzzy.
- nome suggerito derivato dal token principale (es. SALMONE).

B) extend_tag
- descrizioni recenti non associate ma ad alta similarita con descrizioni gia associate a un tag.
- suggerimento collegato a target_tag_id esistente.

### 5.4 Similarita (ibrida confermata)
Score finale = max(score_rule_based, score_fuzzy)
- rule-based:
  - token overlap pesato
  - prefisso/suffisso normalizzato
  - bonus stesso fornitore prevalente
- fuzzy:
  - similarita lessicale su descrizione normalizzata

Soglie iniziali proposte:
- extend_tag: score >= 0.82
- new_tag cluster inclusion: score >= 0.76

### 5.5 Anti-spam e dedupe
- fingerprint cluster_key deterministico (tipo + token/tag + hash descrizione_key ordinate).
- se pending esiste: update last_seen_at e contatori, no nuovo record.
- se dismissed recente: cooldown 14 giorni prima di riproporre.
- se snoozed: non mostrare fino a snooze_until.

## 6) Firme funzioni canoniche
## 6.1 services/tag_suggestion_service.py
- def build_recent_product_pool(user_id: str, ristorante_id: str, window_days: int = 30, supabase_client=None) -> list[dict]
- def suggest_new_tags(user_id: str, ristorante_id: str, min_products: int, min_rows: int, supabase_client=None) -> list[dict]
- def suggest_extend_existing_tags(user_id: str, ristorante_id: str, min_products: int, min_score: float, supabase_client=None) -> list[dict]
- def upsert_tag_suggestions(user_id: str, ristorante_id: str, suggestions: list[dict], supabase_client=None) -> int
- def list_pending_tag_suggestions(user_id: str, ristorante_id: str, supabase_client=None) -> list[dict]
- def accept_suggestion_create_tag(suggestion_id: int, tag_name: str | None, user_id: str, ristorante_id: str, supabase_client=None) -> dict
- def accept_suggestion_extend_tag(suggestion_id: int, tag_id: int | None, user_id: str, ristorante_id: str, supabase_client=None) -> dict
- def dismiss_tag_suggestion(suggestion_id: int, user_id: str, ristorante_id: str, reason: str | None = None, supabase_client=None) -> bool
- def snooze_tag_suggestion(suggestion_id: int, user_id: str, ristorante_id: str, days: int = 30, supabase_client=None) -> bool
- def generate_tag_suggestion_notifications(user_id: str, ristorante_id: str, supabase_client=None) -> list[dict]

## 6.2 services/db_service.py (integrazione)
- def clear_tag_suggestions_cache() -> None
- def get_tag_suggestion_thresholds(user_id: str) -> dict
- def set_tag_suggestion_thresholds(user_id: str, min_products: int, min_rows: int, min_score: float) -> bool

## 6.3 services/notification_inbox_service.py (topic)
Aggiunte topic_key:
- tag_suggestion_new_tag
- tag_suggestion_extend_tag

Bucket consigliato:
- settimana ISO (ricorrente ma non rumoroso)

## 7) Pipeline ingestione (upload/API/worker)
Stato reale:
- upload handler gia ingesta notifiche post-upload.
- worker converge su salvataggio fatture e poi passa da flussi comuni.

Proposta:
1. Trigger suggerimenti dopo upload completato (stesso punto dove oggi nascono alert upload).
2. Esecuzione leggera:
   - costruzione pool ultimi 30 giorni
   - upsert suggerimenti (pending)
   - generazione record inbox solo per nuovi pending o pending aggiornati oltre soglia delta.
3. Hook ulteriore on-demand in apertura pagina Analisi e Tag con TTL sessione (es. 10 min) per evitare drift.

## 8) Cache + session state + cache_version
### Cache
- Nuove cache_data dedicate suggerimenti (TTL 120s) keyate da user_id + ristorante_id + suggestion_version.
- suggestion_version su public.cache_version key:
  - custom_tag_suggestions

### Invalidation
- bump suggestion_version quando:
  - si accetta/dismiss/snooze suggerimento
  - si crea/modifica/elimina tag
  - si aggiungono/rimuovono associazioni

### Session state pagina 4
Namespace nuovo proposto: ap_sugg_*
- ap_sugg_last_refresh_ts
- ap_sugg_filters
- ap_sugg_selected_ids

Reset al cambio ristorante coerente al pattern pagine esistenti.

## 9) UX grafica proposta (pagina Analisi e Tag)
### 9.1 Posizionamento
In tab Gestione Tag, sopra la sezione "Cerca Prodotti da Fatture":
- box "Suggerimenti intelligenti" con due sotto-tab:
  - Nuovi Tag
  - Aggiungi a Tag Esistenti

### 9.2 Componenti
Per ogni suggerimento card:
- titolo (nome tag suggerito o tag target)
- badge confidenza (Alta/Media)
- KPI mini: prodotti, occorrenze, fornitori, ultima data
- preview prime descrizioni
- CTA:
  - Accetta (bulk)
  - Rivedi selezione (apre lista checkbox items)
  - Snooze 30g
  - Ignora

### 9.3 Coerenza visuale
- usare stile card KPI gia presente su pagine 3/5 (no nuovo design language)
- spacing compatto come ultime revisioni UX
- nessuna linea hr non voluta

## 10) Notifiche
### 10.1 Tipi alert richiesti
1. Alert "Nuovo tag suggerito"
2. Alert "Nuovi prodotti suggeriti per tag esistente"

### 10.2 Topic + severita
- tag_suggestion_new_tag -> info
- tag_suggestion_extend_tag -> info

### 10.3 Copy suggerito
- Nuovo Tag: "Rilevati {N} prodotti coerenti negli ultimi 30 giorni: suggerito tag '{X}'."
- Estensione: "Il tag '{X}' ha {N} nuovi prodotti reclutabili negli ultimi 30 giorni."

### 10.4 Navigazione
action_page: pages/4_analisi_personalizzata.py

### 10.5 Dedupe
- dedupe_key su settimana ISO + cluster_key sintetico
- refresh_on_conflict true per aggiornare contatori senza moltiplicare card

## 11) Auth + multi-tenant
- tutte le query suggestion filtrate obbligatoriamente per user_id + ristorante_id.
- nessuna suggestion cross-ristorante.
- ownership enforced anche in accept/dismiss/snooze.

## 12) Test esistenti e lacune
Esistente:
- test_custom_tags.py copre helper puri pagina 4.
- test_db_service.py copre parti base custom tags.

Lacune:
- nessun test su motore suggerimenti.
- nessun test su workflow accept/dismiss/snooze.
- nessun test topic notifiche nuovi.
- nessun test anti-spam/dedupe su suggerimenti.

Nuovi test minimi richiesti:
1. clustering new_tag con dataset sintetico salmone.
2. extend_tag su nuove descrizioni simili.
3. dedupe pending (no duplicati).
4. accetta suggerimento crea tag + associazioni.
5. accetta suggerimento estende tag esistente.
6. dismiss/snooze e cooldown.
7. generazione notifiche topic nuovi e routing pagina 5.

## 13) Step plan proposto (implementazione)
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
**File coinvolti:** services/notification_inbox_service.py, pages/5_notifiche_e_gestione.py, services/upload_handler.py (hook)
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

## 14) Parametri v1 proposti
- window_days = 30
- min_products_for_suggestion = 6 (confermato)
- min_rows_for_suggestion = 12
- min_score_extend = 0.82
- min_score_new_cluster = 0.76
- snooze_default_days = 30

Decisione confermata il 2026-05-25:
- soglia minima prodotti in finestra 30 giorni impostata a 6 per v1.

## 15) Rischi principali e mitigazioni
1. Falsi positivi cluster.
   - Mitigazione: soglie conservative + feedback dismiss/snooze + revisione selezione pre-accept.
2. Spam notifiche.
   - Mitigazione: dedupe settimanale + cooldown + first-time only.
3. Regressioni performance pagina 4.
   - Mitigazione: cache TTL + versioning + no full scan non filtrata.
4. Collisioni con limiti trial/tag max.
   - Mitigazione: validazioni centralizzate prima di accept.

## 16) Blocchi residui prima Fase 3
Nessun blocco tecnico critico emerso in Fase 2.

Decisione operativa consigliata:
- avviare Fase 3 (verifica critica multi-livello) sulla presente proposta.
