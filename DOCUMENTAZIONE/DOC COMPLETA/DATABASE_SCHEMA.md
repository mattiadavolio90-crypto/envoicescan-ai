# ONEFLUX — Schema Database Completo

Versione: 6.0 | Aggiornamento: 5 Giugno 2026

Supabase PostgreSQL 15, EU Frankfurt. RLS attivo su tutte le tabelle.
`auth.uid()` sempre NULL (auth custom). Accesso solo via `service_role_key`.
Soft-delete: query su `fatture` e `prodotti` filtrare sempre `deleted_at IS NULL`.

---

## Tabelle Core

### `users` — Utenti del sistema

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | Generato automaticamente |
| email | TEXT UNIQUE | Login, sempre lowercase |
| password_hash | TEXT | Argon2id hash |
| nome_ristorante | TEXT | Nome locale (legacy — ora in `ristoranti`) |
| partita_iva | TEXT | P.IVA (legacy — ora in `ristoranti`) |
| ragione_sociale | TEXT | Ragione sociale |
| attivo | BOOLEAN | Account attivo/disattivato |
| created_at | TIMESTAMPTZ | Data creazione |
| reset_code | TEXT | Codice reset password temporaneo |
| reset_expires | TIMESTAMPTZ | Scadenza codice reset (15 min) |
| login_attempts | INT | Contatore legacy (sostituito da tabella `login_attempts`) |
| password_changed_at | TIMESTAMPTZ | Ultima modifica password |
| last_login | TIMESTAMPTZ | Timestamp ultimo login riuscito |
| last_logout | TIMESTAMPTZ | Timestamp ultimo logout (invalida sessioni) |
| session_token | TEXT | Token sessione cookie |
| session_token_created_at | TIMESTAMPTZ | Creazione token sessione |
| ultimo_ristorante_id | UUID (FK → ristoranti) | Ultimo ristorante usato |
| pagine_abilitate | JSONB | Feature flags Next.js: `{"analisi_fatture": true, "prezzi": true, ...}` |
| dismissed_notification_ids | JSONB | Notifiche nascoste: `{id: dismissed_at}` |
| trial_activated_at | TIMESTAMPTZ | Data attivazione trial |
| trial_active | BOOLEAN | Account in periodo trial |
| price_alert_threshold | NUMERIC(5,2) | Soglia % variazione prezzi (default 5.0) |
| nome_referente | TEXT | Nome persona per il saluto AI del briefing |
| is_admin | BOOLEAN | Flag admin (DEFAULT false) |
| piano | TEXT | Piano sottoscrizione: `base`, `plus`, `pro` |
| piano_inizio | DATE | Data inizio piano |
| limite_fatture_mese | INT | Fatture consentite per mese dal piano |
| privacy_accepted_at | TIMESTAMPTZ | Timestamp accettazione privacy (scritto solo con consenso reale) |

**Feature flags in `pagine_abilitate`:** `analisi_fatture`, `prezzi`, `margini`, `foodcost`, `analisi_e_tag`, `scadenziario`, `blocco_anno_precedente`, `blocco_mesi_precedenti`

### `ristoranti` — Locali (multi-ristorante)

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | Generato automaticamente |
| user_id | UUID (FK → users) | Proprietario |
| nome_ristorante | TEXT | Nome locale |
| partita_iva | TEXT | P.IVA per validazione fatture SDI |
| ragione_sociale | TEXT | Ragione sociale |
| attivo | BOOLEAN | Ristorante attivo/disattivato |
| created_at | TIMESTAMPTZ | Data creazione |

### `fatture` — Righe di fattura (core data)

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | Auto-increment |
| user_id | UUID (FK → users) | Proprietario |
| ristorante_id | UUID (FK → ristoranti) | Ristorante associato |
| file_origine | TEXT | Nome file originale (chiave dedup) |
| numero_riga | INT | Numero riga nella fattura |
| data_documento | DATE | Data documento fattura |
| fornitore | TEXT | Nome fornitore |
| descrizione | TEXT | Descrizione prodotto (normalizzata) |
| quantita | NUMERIC | Quantità |
| unita_misura | TEXT | UM normalizzata (KG, LT, PZ, CF…) |
| prezzo_unitario | NUMERIC | Prezzo per unità |
| iva_percentuale | NUMERIC | % IVA |
| totale_riga | NUMERIC | Importo totale riga |
| categoria | TEXT | Categoria assegnata |
| codice_articolo | TEXT | Codice EAN/fornitore |
| prezzo_standard | NUMERIC | Prezzo standardizzato per confronto |
| needs_review | BOOLEAN | Flag revisione admin (routing confidenza) |
| tipo_documento | TEXT | TD01, TD04, ecc. |
| sconto_percentuale | NUMERIC | % sconto applicato |
| totale_documento | NUMERIC | ImportoTotaleDocumento da header XML |
| totale_imponibile | NUMERIC | Somma ImponibileImporto da DatiRiepilogo |
| totale_iva | NUMERIC | Somma Imposta da DatiRiepilogo |
| data_consegna | DATE | Data consegna/ritiro (TD24, da DatiDDT o regex) |
| data_competenza | DATE | Data competenza gestionale per reportistica |
| deleted_at | TIMESTAMPTZ | Soft-delete: NULL = attiva; valorizzata = nel cestino |
| created_at | TIMESTAMPTZ | Inserimento |

**Constraint:** `fatture_categoria_not_unclassified_chk` — `categoria != 'Da Clasificare'`
**Dedup:** `UNIQUE(file_origine, numero_riga, user_id, ristorante_id)`

---

## Memoria Classificazione AI

### `prodotti_master` — Memoria globale AI

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | Auto-increment |
| descrizione | TEXT UNIQUE | Chiave matching |
| categoria | TEXT | Categoria assegnata |
| classificato_da | TEXT | "AI", "keyword", "Utente (email)" |
| confidence | TEXT | "altissima", "alta", "media" |
| verified | BOOLEAN | Verificato da admin |
| volte_visto | INT | Counter occorrenze |
| created_at | TIMESTAMPTZ | Prima occorrenza |
| ultima_modifica | TIMESTAMPTZ | Ultimo aggiornamento |

### `prodotti_utente` — Memoria locale cliente

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | |
| user_id | UUID (FK → users) | |
| descrizione | TEXT | Chiave matching |
| categoria | TEXT | Categoria personalizzata |
| updated_at | TIMESTAMPTZ | |
| — | UNIQUE(user_id, descrizione) | Constraint |

### `classificazioni_manuali` — Override admin

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | |
| descrizione | TEXT UNIQUE | Chiave matching |
| categoria_corretta | TEXT | Categoria imposta da admin |
| is_dicitura | BOOLEAN | Se TRUE: riga trattata come nota/dicitura (solo €0) |

### `categorie` — Elenco centralizzato categorie

31 righe, allineate a `config/constants.py`. Usata come reference per validazione e UI.

### `brand_ambigui` — Brand multi-categoria (machine learning)

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| brand | TEXT UNIQUE | Nome brand estratto |
| num_correzioni | INTEGER | Numero totale correzioni ricevute |
| categorie_viste | TEXT[] | Array categorie in cui il brand è stato visto |
| tasso_correzione | NUMERIC(6,4) | % correzioni manuali (0.0–1.0) |
| aggiunto_automaticamente | BOOLEAN | Se TRUE: dizionario bypassato → diretta a GPT |
| prima_vista | TIMESTAMPTZ | |
| ultima_modifica | TIMESTAMPTZ | |

**Logica:** brand con ≥3 correzioni su ≥2 categorie diverse con tasso >20% → `aggiunto_automaticamente=TRUE`.

### `category_change_log` — Audit storico categorie

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| fattura_id | BIGINT (FK → fatture) | |
| user_id | UUID | Chi ha modificato |
| old_categoria | TEXT | Categoria precedente |
| new_categoria | TEXT | Categoria nuova |
| changed_at | TIMESTAMPTZ | Timestamp modifica |
| source | TEXT | "manual", "ai", "admin" |

---

## Margini e Ricavi

### `margini_mensili` — MOL mensile

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | |
| user_id | UUID (FK) | |
| ristorante_id | UUID (FK) | |
| anno | INT | |
| mese | INT CHECK(1-12) | |
| **INPUT MANUALI** | | |
| fatturato_iva10 | NUMERIC(10,2) | Fatturato soggetto IVA 10% |
| fatturato_iva22 | NUMERIC(10,2) | Fatturato soggetto IVA 22% |
| altri_ricavi_noiva | NUMERIC(10,2) | Altri ricavi non soggetti IVA |
| altri_costi_fb | NUMERIC(10,2) | Costi F&B extra non in fatture |
| altri_costi_spese | NUMERIC(10,2) | Spese extra non in fatture |
| costo_dipendenti | NUMERIC(10,2) | Costo personale lordo mensile |
| costo_personale_extra | NUMERIC(10,2) | Costo ore extra (da turni o manuale) |
| **SNAPSHOT AUTOMATICI** | | |
| costi_fb_auto | NUMERIC(10,2) | Costi F&B da `fatture` (ricalcolati) |
| costi_spese_auto | NUMERIC(10,2) | Costi Spese da `fatture` (ricalcolati) |
| **CENTRI DI PRODUZIONE** | | |
| fatturato_food | NUMERIC(12,2) | Fatturato centro FOOD |
| fatturato_beverage | NUMERIC(12,2) | Fatturato centro BEVERAGE |
| fatturato_alcolici | NUMERIC(12,2) | Fatturato centro ALCOLICI |
| fatturato_dolci | NUMERIC(12,2) | Fatturato centro DOLCI |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |
| — | UNIQUE(ristorante_id, anno, mese) | |

### `ricavi_giornalieri` — Ricavi day-by-day

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | |
| user_id | UUID | |
| ristorante_id | UUID (FK) | |
| data | DATE | |
| iva10 | NUMERIC(10,2) | |
| iva22 | NUMERIC(10,2) | |
| altri_ricavi | NUMERIC(10,2) | |
| created_at | TIMESTAMPTZ | |
| — | UNIQUE(ristorante_id, data) | |

### `ricavi_modalita_mensile` — Override modalità mensile

Indica per quali mesi/ristorante usare la somma dei giornalieri o il valore mensile totale.

### `ricavi_ragione_sociale_map` — Mapping ragione sociale per catene

Mappa ragione sociale (dal gestionale) → `ristorante_id`. Usato nell'import XLS Passbi per catene con più locali.

---

## Coda Invoicetronic

### `fatture_queue` — Buffer webhook SDI

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT IDENTITY (PK) | |
| event_id | TEXT UNIQUE | ID evento Invoicetronic (idempotenza) |
| user_id | UUID (nullable) | NULL se P.IVA non trovata |
| ristorante_id | UUID (nullable) | NULL se P.IVA non trovata |
| piva_raw | TEXT | P.IVA destinatario estratta dall'XML |
| xml_content | TEXT (nullable) | XML grezzo; nullificato dopo 24h (GDPR) |
| xml_url | TEXT (nullable) | URL download su Invoicetronic (fallback) |
| xml_hash | TEXT (nullable) | SHA-256 per deduplicazione |
| payload_meta | JSONB | Metadati non-PII (tipo_doc, data, importo, piva_cedente) |
| status | TEXT CHECK | `pending` / `processing` / `done` / `retry` / `dead` / `unknown_tenant` |
| attempt_count | INT DEFAULT 1 | Numero tentativi |
| worker_id | TEXT (nullable) | ID worker che ha acquisito il lock |
| locked_at | TIMESTAMPTZ (nullable) | Timestamp acquisizione lock |
| error_message | TEXT (nullable) | Dettaglio ultimo errore |
| created_at | TIMESTAMPTZ | Ricezione webhook |
| processed_at | TIMESTAMPTZ (nullable) | Completamento elaborazione |

**RLS:** Solo `service_role` accede.

**Stored Procedure RPC:**
- `claim_batch_for_processing(p_worker_id, p_batch_size)` — `SELECT FOR UPDATE SKIP LOCKED`
- `mark_queue_item_done(p_queue_id, p_purge_xml)` — status + nullifica XML
- `schedule_retry(p_queue_id, p_error_msg)` — backoff esponenziale
- `purge_processed_xml_content(p_retention_hours)` — GDPR cleanup
- `release_stale_locks(p_timeout_minutes)` — recovery crash worker
- `resolve_unknown_tenant(p_piva)` — rimette in pending i record con P.IVA non ancora registrata

---

## Autenticazione e Sicurezza

### `login_attempts` — Rate limiting persistente

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT IDENTITY (PK) | |
| email | TEXT NOT NULL | Email del tentativo |
| attempted_at | TIMESTAMPTZ | Timestamp |
| success | BOOLEAN | Successo o fallimento |

Indice su `(email, attempted_at DESC)`. Solo `service_role` può scrivere.

### `upload_events` — Log upload fatture

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| user_id | UUID | |
| user_email | TEXT | |
| file_name | TEXT | |
| file_type | TEXT | `xml` / `pdf` / `image` / `unknown` |
| status | TEXT | `SAVED_OK` / `SAVED_PARTIAL` / `FAILED` |
| rows_parsed | INT | |
| rows_saved | INT | |
| rows_excluded | INT | |
| error_stage | TEXT | `PARSING` / `VISION` / `SUPABASE_INSERT` / `POSTCHECK` |
| error_message | TEXT | Max 500 char |
| details | JSONB | Info aggiuntive |
| created_at | TIMESTAMPTZ | |

---

## Costi AI e Review

### `ai_usage_events` — Ledger costi OpenAI

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| ristorante_id | UUID (FK) | |
| user_id | UUID (FK) | |
| operation_type | TEXT | `pdf` / `categorization` / `chat` / `briefing` / `other` |
| prompt_tokens | INT | |
| completion_tokens | INT | |
| total_tokens | INT | |
| input_cost | NUMERIC | $0.15/1M token GPT-4o-mini |
| output_cost | NUMERIC | $0.60/1M token GPT-4o-mini |
| total_cost | NUMERIC | |
| model | TEXT | Es. `gpt-4o-mini` |
| source_file | TEXT | File origine |
| metadata | JSONB | |
| created_at | TIMESTAMPTZ | |

Indici: `(ristorante_id, created_at DESC)`, `(operation_type)`.

### `ai_review_log` — Audit log azioni AI admin

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| admin_user_id | UUID | Admin che ha eseguito l'azione |
| action_type | TEXT | `classify`, `auto_review`, `promote_conflict`, `delete_memory` |
| target_id | BIGINT | ID record modificato |
| old_value | JSONB | Stato precedente (per undo) |
| new_value | JSONB | Stato nuovo |
| undone_at | TIMESTAMPTZ (nullable) | Se annullata |
| created_at | TIMESTAMPTZ | |

### `chat_usage_log` — Contatore chat AI per piano

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| user_id | UUID | |
| ristorante_id | UUID | |
| data | DATE | Giorno (reset a mezzanotte) |
| count | INT | Domande effettuate |
| — | UNIQUE(user_id, ristorante_id, data) | |

---

## Strumenti Operativi

### `diario_eventi` — Calendario eventi ristorante

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| ristorante_id | UUID (FK CASCADE) | |
| user_id | UUID | |
| data_evento | DATE | |
| ora_inizio | TIME (nullable) | |
| ora_fine | TIME (nullable) | |
| titolo | TEXT NOT NULL | |
| descrizione | TEXT (nullable) | |
| colore | TEXT | sky/green/amber/red/purple/gray |
| created_at | TIMESTAMPTZ | |

Migrazione automatica da `note_diario` → `diario_eventi` nella migration SQL.

### `turni_personale` — Turni staff

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| ristorante_id | UUID (FK CASCADE) | |
| user_id | UUID | |
| nome | TEXT NOT NULL | Nome dipendente (libero) |
| data_turno | DATE | |
| ora_inizio | TIME | |
| ora_fine | TIME | |
| ore_extra | NUMERIC(5,2) DEFAULT 0 | Di cui ore straordinario |
| costo_orario | NUMERIC(6,2) (nullable) | €/h, opzionale |
| note | TEXT (nullable) | |

### `inventario_voci` — Giacenze

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| ristorante_id | UUID (FK CASCADE) | |
| user_id | UUID | |
| data_inventario | DATE | Data snapshot |
| nome | TEXT NOT NULL | Nome articolo |
| quantita | NUMERIC NOT NULL | |
| unita_misura | TEXT | |
| prezzo_unitario | NUMERIC | |
| valore_totale | NUMERIC | **GENERATED ALWAYS AS** (quantita × prezzo_unitario) STORED |
| categoria | TEXT (nullable) | Dalla fattura di origine |
| da_fattura | BOOLEAN DEFAULT false | Se selezionato da autocomplete fatture |
| created_at | TIMESTAMPTZ | |

---

## Ricette e Foodcost

### `ricette` — Ricette con ingredienti

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| user_id | UUID | |
| ristorante_id | UUID | |
| nome | TEXT | |
| categoria | TEXT | Antipasto, Primo, Secondo, Dolce, Bevanda, ecc. |
| note | TEXT (nullable) | |
| prezzo_vendita | NUMERIC | IVA inclusa |
| ingredienti | JSONB | Array ingredienti con quantità, UM, costo |
| foodcost | NUMERIC | Calcolato |
| margine | NUMERIC | Calcolato |
| created_at | TIMESTAMPTZ | |

### `ingredienti_workspace` — Ingredienti manuali

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| user_id | UUID | |
| nome | TEXT | |
| prezzo_per_um | NUMERIC | |
| um | TEXT | Unità di misura |

---

## Notifiche e Assistente AI

### `assistant_preferences` — Configurazione assistente per ristorante

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | |
| user_id | UUID | |
| ristorante_id | UUID | |
| nome_referente | TEXT (nullable) | Nome per saluto AI |
| topics_disabled | TEXT[] | Topic notifiche disabilitate (tranne "upload falliti") |
| chat_ai_enabled | BOOLEAN DEFAULT true | Toggle chat AI |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `daily_briefing_state` — Cache briefing giornaliero

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | |
| ristorante_id | UUID UNIQUE | |
| briefing_date | DATE | Giorno del briefing |
| content | JSONB | Briefing generato (saluto + narrativa + azioni) |
| notif_fingerprint | TEXT | Hash delle notifiche usate per generarlo |
| created_at | TIMESTAMPTZ | |

Logica: se `briefing_date = oggi` E `notif_fingerprint` invariato → restituisce cache senza chiamare OpenAI.

---

## Marketplace e Sistema

### `marketplace_leads` — Lead da form Servizi

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| user_id | UUID | |
| ristorante_id | UUID | |
| servizio | TEXT | Nome del servizio richiesto |
| messaggio | TEXT | Testo del form |
| status | TEXT | `nuovo` / `gestito` / `archiviato` |
| created_at | TIMESTAMPTZ | |

### `system_announcements` — Annunci di sistema

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| tipo | TEXT | `manutenzione` / `feature` / `aggiornamento_maggiore` |
| titolo | TEXT | |
| corpo | TEXT | |
| valido_dal | TIMESTAMPTZ | |
| valido_al | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

### `system_maintenance_status` — Stato retention automatica

| Colonna | Tipo | Note |
|---------|------|------|
| id | INT PRIMARY KEY DEFAULT 1 | Singleton |
| last_run_at | TIMESTAMPTZ | Data ultima esecuzione |
| rows_deleted | INT | Righe eliminate nell'ultimo ciclo |
| cestino_rows_deleted | INT | Di cui dal cestino |
| status | TEXT | `ok` / `error` |
| error_message | TEXT (nullable) | |

---

## Custom Tags

### `custom_tags` — Tag personalizzati per ristorante

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| ristorante_id | UUID (FK) | |
| nome | TEXT | |
| emoji | TEXT (nullable) | |
| colore | TEXT (nullable) | Hex color |
| created_at | TIMESTAMPTZ | |

### `custom_tag_prodotti` — Associazioni tag ↔ prodotti

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | |
| tag_id | BIGINT (FK → custom_tags) | |
| ristorante_id | UUID (FK) | |
| descrizione | TEXT | Descrizione prodotto da `fatture` |
| created_at | TIMESTAMPTZ | |

---

## Infrastruttura Cache

### `cache_version` — Versioning cache classificazione

| Colonna | Tipo | Note |
|---------|------|------|
| id | INT PRIMARY KEY DEFAULT 1 | Singleton |
| version | BIGINT DEFAULT 0 | Incrementato da trigger DB |
| updated_at | TIMESTAMPTZ | |

Trigger su `prodotti_utente`, `prodotti_master`, `classificazioni_manuali`: ogni modifica → `fn_bump_cache_version()` → incrementa `cache_version.version`. Il worker controlla la versione e invalida la cache in-memory se cambiata.

---

## Migration SQL

**68 file legacy** (`migrations/001_*.sql` → `migrations/068_*.sql`) + **file timestamp-based Supabase** (`supabase/migrations/20260417*.sql` → `20260601*.sql`)

### Stored Procedure / RPC principali

| RPC | Scopo |
|-----|-------|
| `create_ristorante(...)` | Creazione atomica ristorante con validazione P.IVA |
| `get_distinct_files(user_id, ristorante_id)` | File distinti per deduplicazione upload |
| `claim_batch_for_processing(worker_id, batch_size)` | Lock atomico coda Invoicetronic |
| `mark_queue_item_done(queue_id, purge_xml)` | Completamento elaborazione + purge XML |
| `schedule_retry(queue_id, error_msg)` | Backoff esponenziale su errore |
| `purge_processed_xml_content(retention_hours)` | GDPR: nullifica xml_content |
| `release_stale_locks(timeout_minutes)` | Recovery lock su worker crashati |
| `resolve_unknown_tenant(piva)` | Rimette in pending i record P.IVA non trovata |
| `fn_bump_cache_version()` | Trigger: incrementa cache_version |
| `get_ai_costs_summary(...)` | Aggregazione costi AI per admin |
| `get_ai_costs_timeseries(...)` | Serie temporale costi AI |
| `get_retention_last_status()` | Stato ultimo ciclo retention |

---

*Database Schema v6.0 — 5 Giugno 2026*
