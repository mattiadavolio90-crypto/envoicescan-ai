# OH YEAH! Hub — Documentazione Completa

**Sistema di Analisi Fatture e Controllo Costi per la Ristorazione**

Versione: 5.4  
Ultimo aggiornamento: 1 Maggio 2026  
Autore: Mattia D'Avolio  
Repository: `mattiadavolio90-crypto/envoicescan-ai` (privato)  
URL Produzione: https://ohyeah.streamlit.app/

> **Novità v5.4**: Tabella `categorie` centralizzata nel DB (31 righe, allineata a `config/constants.py`); soft-delete fatture (`deleted_at`) con cestino 30 gg + retention automatica 2 anni (`system_maintenance_status`); sistema Custom Tags (`custom_tags` + `custom_tag_prodotti`) per aggregare prodotti equivalenti per ristorante; cache versioning cross-process (`cache_version` + triggers DB) per invalidazione memoria classificazione multi-worker; `category_change_log` per audit storico modifiche categorie; nuove colonne su `fatture` (`data_consegna` TD24, `data_competenza`, `totale_documento/imponibile/iva`); `margini_mensili.fatturato_bar` rinominato in `fatturato_beverage`; `users.price_alert_threshold` (soglia variazione prezzi personalizzabile per utente); Privacy Policy v3.4 (1 Maggio 2026) con cookie impersonazione corretto a 30 minuti; tool `tools/check_migrations.py` per verifica oggetti DB (65/65 OK). 85 file SQL totali (68 legacy + 17 Supabase timestamp-based).
>
> **Novità v5.3**: Audit sicurezza e privacy completo — protezione XXE (defusedxml), protezione SSRF (whitelist host Invoicetronic), minimizzazione PII nei log, session token migrato a `secrets.token_urlsafe(32)`, reset token con `secrets.token_urlsafe(32)` + `datetime.now(timezone.utc)`, GDPR Art.17 esteso a 14 tabelle (custom_tags, ai_usage_events, login_attempts), export GDPR Art.20 esteso (prodotti_utente, custom_tags), Privacy Policy v3.3. 330 test automatici.
>
> **Novità v5.2**: Il worker `fatture_queue` è stato migrato da GitHub Actions a un service Railway dedicato `queue-worker`, con loop continuo ogni 15 secondi. Il service FastAPI `worker` usa `ENABLE_INLINE_QUEUE_PROCESSOR=0` e `.github/workflows/queue-worker.yml` resta solo come fallback manuale di emergenza.
>
> **Novità v5.1**: Sistema di notifiche in-app (6 tipologie: upload, prezzi, ricavi, costi, alert), tracking costi AI con tabella `ai_usage_events`, layer controller (`app_controllers.py`), componenti riutilizzabili (`category_editor.py`, `dashboard_renderer.py`), hardening sicurezza Supabase (migration 052), Privacy Policy v3.3 con sub-processori Invoicetronic/Railway/Streamlit Cloud.
>
> **Novità v5.0**: Integrazione Invoicetronic (ricezione automatica fatture SDI), FastAPI Worker per classificazione AI scalabile, deploy Railway, nuova tabella `fatture_queue` con worker asincrono GitHub Actions, tabella `brand_ambigui` per apprendimento automatico.

---

## Indice

1. [Panoramica del Progetto](#1-panoramica-del-progetto)
2. [Business Model e Proposta di Valore](#2-business-model-e-proposta-di-valore)
3. [Architettura del Sistema](#3-architettura-del-sistema)
4. [Stack Tecnologico](#4-stack-tecnologico)
5. [Struttura del Codice Sorgente](#5-struttura-del-codice-sorgente)
6. [Funzionalità Complete dell'Applicazione](#6-funzionalità-complete-dellapplicazione)
7. [Pipeline di Classificazione AI](#7-pipeline-di-classificazione-ai)
8. [Sistema di Autenticazione e Sicurezza](#8-sistema-di-autenticazione-e-sicurezza)
9. [Parsing delle Fatture Elettroniche](#9-parsing-delle-fatture-elettroniche)
10. [Multi-Tenancy e Multi-Ristorante](#10-multi-tenancy-e-multi-ristorante)
11. [Schema Database Completo](#11-schema-database-completo)
12. [Pannello di Amministrazione](#12-pannello-di-amministrazione)
13. [Calcolo Marginalità e KPI](#13-calcolo-marginalità-e-kpi)
14. [Pagine Secondarie](#14-pagine-secondarie)
15. [Testing e Qualità del Codice](#15-testing-e-qualità-del-codice)
16. [Deploy e Infrastruttura](#16-deploy-e-infrastruttura)
17. [Monitoraggio e Alerting](#17-monitoraggio-e-alerting)
18. [Sicurezza e Compliance GDPR](#18-sicurezza-e-compliance-gdpr)
19. [Troubleshooting e FAQ Tecniche](#19-troubleshooting-e-faq-tecniche)
20. [Integrazione Invoicetronic — Ricezione Automatica SDI](#20-integrazione-invoicetronic--ricezione-automatica-sdi)
21. [FastAPI Worker — Classificazione AI Scalabile](#21-fastapi-worker--classificazione-ai-scalabile)
22. [Sistema di Notifiche In-App](#22-sistema-di-notifiche-in-app)
23. [Tracking Costi AI](#23-tracking-costi-ai)
24. [Componenti Riutilizzabili](#24-componenti-riutilizzabili)

---

## 1. Panoramica del Progetto

### Cos'è OH YEAH! Hub

OH YEAH! Hub è una piattaforma SaaS web-based progettata specificamente per ristoratori italiani che necessitano di analizzare, categorizzare e controllare i costi derivanti dalle fatture elettroniche dei propri fornitori.

L'applicazione consente di:

- **Caricare fatture elettroniche** nei formati XML (FatturaPA), P7M (firma digitale CAdES), PDF e immagini (JPG/PNG)
- **Ricevere fatture automaticamente** tramite integrazione Invoicetronic (codice dest. `7HD37X0`) — nessun upload manuale richiesto
- **Classificare automaticamente** ogni riga di fattura in una delle 29 categorie merceologiche tramite AI + regole deterministiche
- **Visualizzare dashboard interattive** con KPI, grafici a torta, pivot mensili e confronti tra fornitori
- **Calcolare il Margine Operativo Lordo (MOL)** con tabelle ricavi/costi mensili e analisi centri di produzione
- **Gestire più ristoranti** sotto un singolo account utente (multi-ristorante)
- **Controllare i prezzi** dei prodotti confrontando diversi fornitori
- **Esportare dati** in formato Excel per analisi esterne

### Pubblico Target

| Segmento | Descrizione |
|----------|-------------|
| Ristoratori | Proprietari di ristoranti, pizzerie, bar, pasticcerie |
| Catene piccole | Aziende con 2-5 locali sotto la stessa P.IVA o P.IVA diverse |
| Consulenti F&B | Professionisti che seguono più locali |

### Problema Risolto

I ristoratori italiani ricevono decine/centinaia di fatture elettroniche XML al mese dai fornitori. Queste fatture contengono righe di prodotti con descrizioni spesso abbreviate, non standardizzate e difficili da classificare. OH YEAH! Hub automatizza completamente l'analisi di queste fatture, trasformando dati grezzi XML in informazioni azionabili per il controllo dei costi.

---

## 2. Business Model e Proposta di Valore

### Modello di Revenue

Il servizio è attualmente in fase di lancio. Il modello previsto è **SaaS a subscription mensile** per cliente/ristorante.

### Value Proposition

1. **Automazione totale**: Da file XML grezzi a dashboard in un click
2. **AI specializzata**: Classificazione addestrata su 600+ keyword del settore ristorazione italiano
3. **Apprendimento continuo**: Il sistema impara dalle correzioni manuali (admin e utenti)
4. **Multi-ristorante**: Un account, molti locali
5. **Zero installazione**: Web-based, accessibile da qualsiasi browser
6. **Conformità italiana**: Supporta FatturaPA, P7M firmati, validazione P.IVA italiana

### Metriche Chiave

| Metrica | Valore |
|---------|--------|
| Categorie merceologiche | 29 (25 F&B + 1 Materiali + 3 Spese) |
| Keyword nel dizionario | 600+ regole deterministiche |
| Formati fattura supportati | XML, P7M, PDF, JPG, PNG |
| Ricezione automatica SDI | Invoicetronic — codice dest. `7HD37X0` |
| Modello AI | OpenAI GPT-4o-mini |
| Copertura test automatici | 330 test, 11 moduli di test |
| Tempo medio classificazione | < 5 secondi per 50 prodotti (batch) |
| Migrazioni DB | 85 file SQL (68 legacy 001→068 + 17 timestamp-based Supabase) |
| Ritardo ricezione fattura automatica | ≤ 15 secondi (loop continuo Railway) |

---

## 3. Architettura del Sistema

### Diagramma di Flusso Generale

```
┌──────────────────────────────────────────────────────────────────────┐
│                         UTENTE (Browser)                              │
│                    https://ohyeah.streamlit.app                       │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ HTTPS
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│              STREAMLIT CLOUD (Frontend + Backend)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │  app.py   │ │ admin.py │ │calcolo_  │ │workspace │               │
│  │           │ │  (6 tab) │ │margine   │ │  .py     │               │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘               │
│       │             │            │             │                      │
│  ┌────▼─────────────▼────────────▼─────────────▼────┐                │
│  │              Service Layer                        │                │
│  │  ai_service │ auth_service │ invoice │ db │ email │                │
│  │  worker_client (proxy → FastAPI Worker)           │                │
│  └────┬────────────┬───────────────┬────────────────┘                │
└───────┼────────────┼───────────────┼────────────────────────────────┘
        │            │               │         │
        ▼            ▼               ▼         ▼
┌──────────┐  ┌──────────┐   ┌──────────┐  ┌──────────────────────────┐
│ OpenAI   │  │ Supabase │   │  Brevo   │  │  FastAPI Worker           │
│ GPT-4o-  │  │ PostgreSQL│  │  SMTP    │  │  (Railway / Docker)       │
│  mini    │  │  + RLS   │   │  API v3  │  │  POST /api/classify       │
└──────────┘  └──────┬───┘   └──────────┘  │  POST /api/parse         │
                     │                      └──────────────────────────┘
                     │
         ┌───────────▼───────────────────────────────────┐
         │           FLUSSO INVOICETRONIC (nuovo)         │
         │                                               │
         │  SDI → Invoicetronic → POST webhook           │
         │    → Supabase Edge Function (Deno/TypeScript) │
         │      verifica HMAC-SHA256 + anti-replay       │
         │      GET api.invoicetronic.com/receive/{id}   │
         │      lookup P.IVA → ristoranti                │
         │      INSERT fatture_queue (pending)           │
         │           │                                   │
         │  Railway service: queue-worker                │
         │    → python worker/run.py                     │
         │    → loop continuo ogni 15 secondi            │
         │    → queue_processor.py                       │
         │      claim_batch_for_processing()             │
         │      estrai_dati_da_xml() → salva_fattura()   │
         │      mark_queue_item_done() (purge XML GDPR)  │
         └───────────────────────────────────────────────┘
```

### Pattern Architetturali

| Pattern | Dove | Descrizione |
|---------|------|-------------|
| **MVC-like** | Globale | Pages = View, Services = Model/Controller, Utils = Helper |
| **Singleton** | `get_supabase_client()` | Unica istanza Supabase per sessione |
| **Dependency Injection** | Tutti i service | `supabase_client=None` come parametro opzionale |
| **Cache-aside** | `@st.cache_data` | TTL 120s per fatture, 300s per margini |
| **3-tier Memory** | `ai_service.py` | Admin > Locale > Globale per classificazione |
| **Thread-safe Lock** | `_cache_lock`, `_login_attempts_lock` | `threading.Lock()` per dati condivisi |
| **Batch Processing** | Classificazione AI | 50 articoli per chiamata API |
| **Rate Limiting** | Login + Reset + Upload + AI | Login: persistente su DB (`login_attempts`); Reset: in-memory thread-safe |

---

## 4. Stack Tecnologico

### Runtime e Framework

| Componente | Tecnologia | Versione | Note |
|-----------|-----------|---------|------|
| Linguaggio | Python | 3.12.8 | Type hints, f-strings, walrus operator |
| Framework Web | Streamlit | latest | SPA con auto-reload (frontend) |
| Framework API | FastAPI + Uvicorn | latest | Worker REST API AI/parsing |
| Runtime Edge | Deno (TypeScript) | latest | Supabase Edge Function webhook |
| Database | Supabase (PostgreSQL 15) | Free tier | EU region, Row Level Security |
| Edge Functions | Supabase Edge Functions | Deno | invoicetronic-webhook (TypeScript) |
| AI/ML | OpenAI API | GPT-4o-mini | Batch classification, ~0.15$/1M token |
| Email | Brevo SMTP API v3 | Free tier | 300 email/giorno |
| Hashing | Argon2id | m=65536 | Parametri default libreria argon2-cffi (OWASP raccomandato) |
| CI/CD | GitHub Actions | — | Uptime check + fallback manuale queue-worker |
| Deploy Frontend | Streamlit Community Cloud | Free tier | Auto-deploy da branch main |
| Deploy Worker | Railway | Hobby/Pro | Tre service separati: `ohyeah` (frontend), `worker` (FastAPI), `queue-worker` (fatture_queue) |
| SDI Intermediario | Invoicetronic | SaaS | Ricezione fatture SDI, codice dest. `7HD37X0` |

### Dipendenze Python Principali (100 pacchetti lockati)

| Pacchetto | Uso |
|-----------|-----|
| `streamlit` | Framework web UI |
| `fastapi` + `uvicorn` | Worker REST API |
| `supabase` | Client PostgreSQL managed |
| `openai` | Client API GPT-4o-mini |
| `argon2-cffi` | Password hashing sicuro |
| `pandas` | Data processing e aggregazione |
| `plotly` | Grafici interattivi dashboard |
| `openpyxl` | Export Excel |
| `xmltodict` | Parsing XML fatture |
| `asn1crypto` | Estrazione XML da file P7M |
| `PyMuPDF (fitz)` | Parsing PDF fatture |
| `tenacity` | Retry logic per API OpenAI |
| `extra-streamlit-components` | Cookie manager per sessioni |
| `charset-normalizer` | Rilevamento encoding file XML |
| `requests` | HTTP client per Brevo API e worker_client |
| `pydantic` | Validazione modelli dati FastAPI |

### Configurazione Streamlit (.streamlit/config.toml)

```toml
[server]
port = 8501
maxUploadSize = 200         # MB
enableCORS = false
enableXsrfProtection = true  # Protezione CSRF attiva
maxConcurrentUsers = 100

[browser]
gatherUsageStats = false     # No tracking utenti

[client]
showErrorDetails = false     # Mai esporre errori interni in produzione
toolbarMode = "viewer"       # Nasconde developer toolbar
```

---

## 5. Struttura del Codice Sorgente

```
Oh Yeah! Hub/
│
├── app.py                          # Entry point principale
│                                   # - Autenticazione e gestione sessioni
│                                   # - Dashboard con KPI, grafici, pivot
│                                   # - Upload e parsing fatture
│                                   # - Data editor con salvataggio
│                                   # - Gestione fatture (elimina, export)
│
├── pages/                          # Pagine multi-page Streamlit
│   ├── admin.py                    # Pannello admin (6 tab)
│   ├── 1_calcolo_margine.py        # Calcolo MOL e centri di produzione
│   ├── 2_foodcost.py               # Foodcost, ricette, ingredienti, diario
│   ├── 3_controllo_prezzi.py       # Variazioni prezzi, sconti, note di credito
│   ├── gestione_account.py         # Cambio password e impostazioni
│   └── privacy_policy.py           # Privacy Policy + Terms of Service
│
├── services/                       # Business logic layer
│   ├── __init__.py                 # get_supabase_client() singleton
│   ├── ai_service.py              # Classificazione AI + memoria 3 livelli
│   ├── ai_cost_service.py         # Tracking costi OpenAI per ristorante (NUOVO v5.1)
│   ├── auth_service.py            # Login, password, reset, GDPR, rate limiting DB
│   ├── invoice_service.py         # Parsing XML/P7M/PDF/Vision
│   ├── db_service.py              # Query Supabase + cache + paginazione
│   ├── margine_service.py         # Calcoli MOL + export Excel
│   ├── upload_handler.py          # Gestione upload file, batch, deduplicazione
│   ├── email_service.py           # Brevo SMTP API con retry
│   ├── notification_service.py    # Notifiche in-app: upload, prezzi, dati mancanti (NUOVO v5.1)
│   ├── fastapi_worker.py          # FastAPI Worker REST API (AI + parsing)
│   │                              # - POST /api/classify
│   │                              # - POST /api/parse
│   │                              # - GET  /health
│   │                              # Avvio: uvicorn services.fastapi_worker:app
│   └── worker_client.py           # Proxy Streamlit → FastAPI Worker
│                                   # Fallback automatico su funzioni locali
│
├── worker/                         # Worker asincrono fatture_queue (Railway queue-worker)
│   ├── __init__.py
│   ├── run.py                      # Entry point Railway queue-worker / terminale
│   └── queue_processor.py          # Logica elaborazione coda Invoicetronic
│                                   # - run_cycle(): ciclo completo con stats
│                                   # - claim_batch_for_processing() via RPC
│                                   # - GDPR purge xml_content dopo 24h
│
├── supabase/                       # Configurazione e funzioni Supabase
│   ├── config.toml                 # Configurazione locale Supabase
│   └── functions/
│       ├── .env                    # Secrets locali (non versionato)
│       ├── .env.local.template     # Template secrets
│       └── invoicetronic-webhook/  # Edge Function (Deno/TypeScript) (NUOVO)
│           ├── index.ts            # Handler webhook: HMAC, lookup P.IVA, queue insert
│           ├── test.ts             # Test automatici
│           └── test.http           # Test HTTP manuale
│
├── utils/                          # Utility e helper functions
│   ├── formatters.py
│   ├── text_utils.py
│   ├── validation.py
│   ├── piva_validator.py
│   ├── sidebar_helper.py
│   ├── ristorante_helper.py
│   ├── period_helper.py
│   ├── ui_helpers.py
│   ├── page_setup.py
│   └── app_controllers.py         # Controller layer estratto da app.py (NUOVO v5.1)
│                                   # Upload, AI, filtro temporale, gestione fatture
│
├── components/                     # Componenti UI riutilizzabili (NUOVO v5.1)
│   ├── __init__.py
│   ├── category_editor.py         # Data editor categorie con salvataggio (~958 righe)
│   └── dashboard_renderer.py      # Rendering KPI, grafici, pivot dashboard (~964 righe)
│
├── config/                         # Configurazione centralizzata
│   ├── constants.py               # 29 categorie, 600+ keyword, regex, KPI soglie
│   ├── logger_setup.py            # RotatingFileHandler (50MB, 10 backup)
│   └── prompt_ai_potenziato.py    # Prompt GPT per classificazione (con esempi)
│
├── static/                         # Asset statici CSS
│
├── tests/                          # Test automatici (pytest)
│
├── migrations/                     # SQL migrations manuali (68 file, 001→068)
│   ├── 001_add_reset_columns.sql ... 053_add_dismissed_notifications.sql
│   ├── 054_ensure_fatture_rls_enabled.sql
│   ├── 055_create_custom_tags.sql          # Custom Tags + custom_tag_prodotti (NUOVO v5.4)
│   ├── 056_add_data_consegna.sql           # data_consegna fatture TD24 (NUOVO v5.4)
│   ├── 057_add_soft_delete_fatture.sql     # Soft-delete cestino fatture (NUOVO v5.4)
│   ├── 058_add_fatture_retention_status.sql# Retention auto 2 anni (NUOVO v5.4)
│   ├── 059_add_ai_usage_events_operation_index.sql
│   ├── 060_normalize_legacy_materiale_consumo_categories.sql
│   ├── 061_fix_rls_policy_cleanup.sql
│   ├── 062_fix_fk_and_duplicate_indexes.sql
│   ├── 063_revoke_anon_grants_024.sql
│   ├── 064_add_fatture_header_totals.sql   # totale_documento/imponibile/iva (NUOVO v5.4)
│   ├── 065_rename_bar_to_beverage.sql      # fatturato_bar→fatturato_beverage (NUOVO v5.4)
│   ├── 066_add_data_competenza_fatture.sql # data_competenza gestionale (NUOVO v5.4)
│   ├── 067_add_price_alert_threshold_users.sql  # Soglia alert prezzi per utente (NUOVO v5.4)
│   └── 068_create_cache_version.sql        # Cache versioning cross-process (NUOVO v5.4)
│
├── supabase/migrations/             # Migration timestamp-based Supabase (17 file)
│   ├── 20260417190000_add_data_consegna_td24.sql
│   ├── 20260420120000_fix_category_audit_apr20.sql
│   ├── 20260422143000_hardening_rls_policy.sql
│   ├── 20260422150000_add_fatture_header_totals.sql
│   ├── 20260423120000_rename_bar_to_beverage.sql
│   ├── 20260427193000_add_data_competenza_fatture.sql
│   ├── 20260429181500_add_category_change_log.sql  # Audit storico categorie (NUOVO v5.4)
│   ├── 20260429210000_create_cache_version.sql
│   ├── 20260429223000_enforce_no_unclassified_categoria.sql
│   └── 20260501000000_create_categorie_table.sql   # Tabella categorie centralizzata (NUOVO v5.4)
│
├── docker/                         # Docker
│   ├── Dockerfile                 # Build app Streamlit + FastAPI worker
│   ├── docker-compose.yml         # Stack sviluppo locale
│   ├── docker-compose.prod.yml    # Stack produzione (Railway / VPS)
│   └── docker-entrypoint.sh
│
├── scripts/
│   ├── comandi.ps1
│   ├── dev-serve.ps1              # Avvia Edge Function localmente (Deno)
│   └── run-tests.ps1              # Esegue suite test + test Edge Function
│
├── .github/workflows/
│   ├── uptime_check.yml           # Uptime monitoring ogni 5 minuti
│   └── queue-worker.yml           # Fallback manuale di emergenza per fatture_queue
│
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml               # Secrets (non versionato)
│
├── railway.toml                    # Configurazione deploy Railway (NUOVO)
│                                   # build.dockerfilePath = "docker/Dockerfile"
│
├── requirements.txt
├── requirements-lock.txt          # 100 pacchetti lockati
├── pytest.ini
├── tools/
│   └── check_migrations.py          # Verifica oggetti DB da migration legacy 001-068 (NUOVO v5.4)
│                                     # 65 check, usa try/select + APIError PGRST202
└── README.md
```

---

## 6. Funzionalità Complete dell'Applicazione

### 6.1 Dashboard Principale (app.py)

La dashboard è il cuore dell'applicazione. Dopo l'autenticazione, l'utente accede a:

#### KPI Box (6 metriche in una riga)

| KPI | Descrizione |
|-----|-------------|
| 💰 Spesa Totale | Somma di tutti gli importi nel periodo |
| 🔥 Spesa F&B | Solo categorie Food & Beverage |
| 🏪 Fornitori F&B | Numero fornitori distinti Food |
| 🏢 Fornitori Sp.Gen. | Numero fornitori Spese Generali |
| 🛒 Spesa Generale | Solo le 3 categorie operative |
| 📊 Media Mensile | Spesa media per mese nel periodo |

#### Navigazione a 3 Sezioni

1. **📦 Dettaglio Articoli**
   - Data editor Streamlit interattivo con tutte le righe fattura
   - Colonna `Categoria` editabile con dropdown (29 opzioni)
   - Sistema di raggruppamento prodotti unici (checkbox, default ON)
   - Ricerca per Prodotto, Categoria o Fornitore
   - Filtro Food & Beverage / Spese Generali / Tutti
   - Colonna `Fonte` con icone: 📚 Memoria, 🧠 AI, ✋ Manuale
   - Bottone "💾 Salva Modifiche" con propagazione batch
   - Export Excel con ordinamento selezionabile

2. **📈 Categorie**
   - Pivot mensile per categoria (tabella con mesi come colonne)
   - Totali per categoria su tutto il periodo
   - Filtro F&B / Spese / Tutti

3. **🚚 Fornitori**
   - Pivot mensile per fornitore
   - Stesso layout e filtri della vista Categorie

#### Filtro Temporale

- Mese Corrente, Mese Precedente, Trimestre in Corso, Semestre, Anno in Corso, Personalizzato
- Box informativo con conteggio giorni, righe e fatture

#### Upload Fatture

- Drag-and-drop o click "Sfoglia"
- Formati: XML, P7M, PDF, JPG, JPEG, PNG
- Limite: 100 file per upload, 200 MB totale
- Validazione P.IVA destinatario vs ristorante attivo
- Progress bar in tempo reale durante l'elaborazione
- Rilevamento duplicati (stessa fattura già caricata)
- Log dettagliato per ogni file (successo/errore/scartato)

#### Gestione Fatture Caricate

- Expander "🗂️ Gestione Fatture" con:
  - Box statistiche (numero fatture + righe)
  - Eliminazione singola fattura (dropdown con filtro fornitore)
  - Eliminazione massiva "ELIMINA TUTTO" (solo admin)
  - Verifica post-eliminazione (count righe residue)

### 6.2 Classificazione AI Automatica e Recovery

#### Comportamento default: AI integrata nell'upload

A partire dalla versione corrente, **la classificazione AI è integrata direttamente nel flusso di upload**. Non esiste più un bottone separato "Avvia AI" da premere manualmente: ogni file caricato viene classificato automaticamente al momento del parsing, combinando la pipeline memoria → dizionario → GPT-4o-mini.

Il vecchio bottone "🧠 Avvia AI per Categorizzare" è stato ritirato.

#### Bottone Recovery "🧠 Riprova AI per Categorizzare"

Compare **esclusivamente come opzione di ripristino**: viene mostrato accanto al file uploader soltanto se, dopo l'upload e la classificazione automatica, rimangono righe con categoria "Da Classificare" (ad esempio per timeout OpenAI, rate limit o errori di rete).

```
┌──────────────────────────────┐  ┌────────────────────────────────┐
│  📂 Trascina file qui...      │  │  🧠 Riprova AI per Categorizzare│
│     XML, P7M, PDF, JPG, PNG  │  │   (visibile SOLO se rimangono   │
│     Max 200MB                │  │    righe "Da Classificare")     │
└──────────────────────────────┘  └────────────────────────────────┘
```

Quando premuto, setta `st.session_state.trigger_ai_categorize = True` e fa `st.rerun()`, ri-eseguendo la pipeline di classificazione solo sulle righe non ancora classificate.

#### Pipeline classificazione durante l'upload

1. **Pre-step Memoria**: Check cache in-memory (admin > locale > globale)
2. **Step 1 Dizionario**: 600+ keyword matches deterministici
3. **Step 2 AI Batch via worker_client**: Prova prima il FastAPI Worker (se `WORKER_BASE_URL` configurato), con fallback automatico su `classifica_con_ai()` locale
4. **Salvataggio Batch**: Upsert memoria globale per keyword e AI
5. **Update DB**: Batch UPDATE categorie su `fatture`
6. **Fallback**: Secondo tentativo dizionario per articoli rimasti

Banner orizzontale animato con percentuale in tempo reale visibile durante la riclassificazione da recovery.

### 6.3 Upload Handler (services/upload_handler.py)

Gestisce l'intero flusso di upload file (`handle_uploaded_files()`):

1. **Rate limiting upload**: max 100 file per volta, max 200 MB → blocco con messaggio errore
2. **Blocco post-delete**: se `force_empty_until_upload` in session_state → `st.stop()`
3. **Deduplicazione**: confronto nome file completo (con estensione) + nome base (senza, per match XML/PDF/P7M) vs DB e sessione corrente
4. **Elaborazione batch**: `BATCH_FILE_SIZE=20` file per batch con delay rate-limiting tra batch
5. **Delega parsing**: per ogni file → `invoice_service.py` (XML/P7M/PDF/Vision)
6. **Log eventi**: ogni file genera un record in `upload_events` con status/rows_parsed/rows_saved
7. **Progressbar**: aggiornata in tempo reale con nome file corrente e contatore

---

## 7. Pipeline di Classificazione AI

### Architettura Memoria a 3 Livelli

```
┌─────────────────────────────────────────────────┐
│              PRIORITÀ CLASSIFICAZIONE            │
│                                                  │
│  1️⃣ MEMORIA ADMIN (classificazioni_manuali)     │
│     Priorità: MASSIMA                            │
│     Scope: Globale per tutti i clienti            │
│     Trigger: Admin modifica da Tab "Memoria"      │
│                                                  │
│  2️⃣ MEMORIA LOCALE (prodotti_utente)             │
│     Priorità: ALTA                               │
│     Scope: Solo per il cliente specifico          │
│     Trigger: Cliente modifica categoria manualmente│
│                                                  │
│  3️⃣ MEMORIA GLOBALE (prodotti_master)            │
│     Priorità: MEDIA                              │
│     Scope: Tutti i clienti                        │
│     Trigger: AI e dizionario salvano risultati   │
│                                                  │
│  4️⃣ DIZIONARIO KEYWORD (config/constants.py)     │
│     600+ regole: "SALMONE" → PESCE               │
│     Priorità alimenti > contenitori              │
│                                                  │
│  5️⃣ AI GPT-4o-mini (ultima risorsa)              │
│     Batch da 50, prompt con 29 categorie + esempi │
│     Retry con exponential backoff (tenacity)      │
└─────────────────────────────────────────────────┘
```

### Cache In-Memory Thread-Safe

```python
_memoria_cache = {
    'prodotti_utente':       {},      # {user_id: {descrizione: categoria}}
    'prodotti_master':       {},      # {descrizione: categoria}
    'classificazioni_manuali': {},    # {descrizione: {categoria, is_dicitura}}
    'version': 0,                     # Incrementato ad ogni invalidazione
    'loaded': False
}
```

- Caricamento lazy (1 volta per sessione, 3 query DB totali)
- Invalidazione esplicita dopo ogni modifica (`invalida_cache_memoria()`)
- Thread-safe con `threading.Lock()`
- Elimina completamente il problema N+1 query

### 29 Categorie Merceologiche

#### Food & Beverage (25 categorie)

| # | Categoria | Esempi |
|---|-----------|--------|
| 1 | ACQUA | Acqua naturale, frizzante |
| 2 | AMARI/LIQUORI | Limoncello, Baileys, Sambuca |
| 3 | BEVANDE | Coca Cola, Aranciata, Succhi |
| 4 | BIRRE | Lager, Weiss, Stout |
| 5 | CAFFE E THE | Espresso, Capsule, Tisane, Camomilla |
| 6 | CARNE | Pollo, Manzo, Vitello, Salsiccia |
| 7 | DISTILLATI | Vodka, Gin, Whisky, Grappa |
| 8 | FRUTTA | Mele, Arance, Fragole, Avocado |
| 9 | GELATI | Gelato, Sorbetto, Semifreddo, Coppa |
| 10 | LATTICINI | Parmigiano, Mozzarella, Burrata, Tofu |
| 11 | OLIO E CONDIMENTI | Olio EVO, Aceto Balsamico |
| 12 | PASTICCERIA | Torte, Cannoli, Cheesecake, Tiramisù |
| 13 | PESCE | Salmone, Gamberi, Calamari, Polpo |
| 14 | PRODOTTI DA FORNO | Pane, Focaccia, Baguette, Pizza |
| 15 | SALSE E CREME | Pesto, Ragù, Besciamella, Ketchup |
| 16 | SALUMI | Prosciutto, Mortadella, Speck, Pancetta |
| 17 | SCATOLAME E CONSERVE | Pelati, Tonno, Fagioli, Olive |
| 18 | SECCO | Pasta, Riso, Farina, Zucchero |
| 19 | SHOP | Sigarette, Caramelle, Snack, Gomme |
| 20 | SPEZIE E AROMI | Pepe, Origano, Curry, Zafferano |
| 21 | SUSHI VARIE | Nori, Panko, Wasabi, Tobiko, Tempura |
| 22 | UOVA | Uova fresche, biologiche |
| 23 | VARIE BAR | Ghiaccio, Zucchero bustine |
| 24 | VERDURE | Insalata, Pomodori, Zucchine, Funghi |
| 25 | VINI | Prosecco, Chianti, Barolo, Champagne |

#### Materiali (1 categoria)

| 26 | MATERIALE DI CONSUMO | Tovaglioli, Pellicola, Guanti, Detersivo, Bicchieri |

#### Spese Operative (3 categorie — NON Food & Beverage)

| 27 | SERVIZI E CONSULENZE | Commercialista, HACCP, POS, Marketing |
| 28 | UTENZE E LOCALI | Bollette, Affitto, Telefono, Gas |
| 29 | MANUTENZIONE E ATTREZZATURE | Riparazione forno, Lavastoviglie, Arredi |

### Centri di Produzione (aggregazione macro)

| Centro | Categorie Incluse |
|--------|-------------------|
| FOOD | Carne, Pesce, Latticini, Salumi, Uova, Scatolame, Olio, Secco, Verdure, Frutta, Salse, Prodotti da Forno, Spezie, Sushi |
| BEVERAGE | Acqua, Bevande, Caffè e The, Varie Bar |
| ALCOLICI | Birre, Vini, Distillati, Amari/Liquori |
| DOLCI | Pasticceria, Gelati |
| MATERIALE DI CONSUMO | Materiale di Consumo |
| SHOP | Shop |

### Prompt AI (config/prompt_ai_potenziato.py)

Il prompt fornito a GPT-4o-mini contiene:
- Lista completa 29 categorie con descrizione dettagliata
- 3+ esempi reali per ogni categoria
- Istruzioni per formati tipici fattura italiano (abbreviazioni, unità di misura)
- Regole speciali (SALSICCIA → CARNE non SALUMI, MATERIALE DI CONSUMO è F&B)
- Output atteso: JSON con array `categorie` allineato 1:1 con input

### Sistema Quarantena (descrizioni €0)

Le descrizioni con prezzo unitario = €0 vengono classificate ma **NON salvate** in memoria globale. Questo previene che diciture, bolle di consegna e righe informative inquinino la memoria condivisa.

---

## 8. Sistema di Autenticazione e Sicurezza

### Flusso di Autenticazione

```
UTENTE → Cookie session_token (30 giorni)
              │
              ▼
         Cookie valido? ──YES──→ Login automatico (ripristino sessione)
              │
              NO
              ▼
         Form Login (email + password)
              │
              ▼
         Rate Limit check (5 tentativi → 15 min lockout)
              │
              ▼
         Verifica Argon2id hash
              │
              ▼
         Login OK → session_token generato + cookie 30 gg
```

### Password Hashing

| Parametro | Valore |
|-----------|--------|
| Algoritmo | Argon2id |
| Memory cost | 65536 KB (64 MB) |
| Time cost / Parallelism | Parametri default libreria `argon2-cffi` |
| Migrazione | Auto da SHA256 legacy al primo login |

### Validazione Password (GDPR Art.32 + Garante Privacy)

- Lunghezza minima: 10 caratteri
- Complessità: almeno 3/4 tra maiuscola, minuscola, numero, simbolo
- Blacklist: 24 password comuni (OWASP + varianti italiane come "ristorante", "pizzeria")
- No dati personali: email e nome ristorante vietati nella password
- No pattern semplici: sequenze numeriche e caratteri ripetuti bloccati

### Rate Limiting

| Funzione | Limite | Lockout |
|----------|--------|---------|
| Login | 5 tentativi | 15 minuti |
| Reset password | 1 richiesta | 5 minuti cooldown |
| Upload file | 100 file / 200 MB | Per singolo upload |
| AI classificazione | 1.000 chiamate/giorno | Per ristorante |

### Reset Password via Email

1. Utente inserisce email → sistema genera token sicuro con `secrets.token_urlsafe(32)` (256 bit di entropia) + codice 6 cifre con `secrets.randbelow()`
2. Email inviata via Brevo SMTP API con codice e scadenza 15 minuti
3. Utente inserisce codice + nuova password → verifica HMAC constant-time (confronto timing-safe)
4. Password validata secondo compliance GDPR → hash Argon2id salvato atomicamente
5. Token reset invalidato immediatamente → login automatico

### Gestione Cookie di Sessione

- **session_token**: Token opaco ad alta entropia (`secrets.token_urlsafe(32)`), salvato in DB + cookie browser (30 giorni)
- **impersonation_user_id**: Solo per admin che impersonano clienti — TTL **30 minuti** (Secure + SameSite=Strict)
- Cookie impostato con `Secure=True` e `SameSite=strict` (la libreria `extra-streamlit-components` **non supporta** `HttpOnly`)
- Verifica TTL 30 giorni al ripristino sessione
- **Auto-logout per inattività**: dopo 8 ore di inattività la sessione viene invalidata (`SESSION_INACTIVITY_HOURS = 8`)
- Invalidazione immediata se il token non è trovato in DB (sessione già revocata o token manomesso)
- Invalidazione cookie su logout esplicito (cookie impostato con expiry 1970)

---

## 9. Parsing delle Fatture Elettroniche

### Formati Supportati

| Formato | Metodo | Libreria | Note |
|---------|--------|----------|------|
| XML (FatturaPA) | Parsing diretto | `xmltodict` | Encoding auto-detect (UTF-8, cp1252, GB2312, GBK) |
| P7M (firma digitale) | Estrazione ASN.1 + fallback pattern | `asn1crypto` | CAdES/PKCS#7, max 50 MB |
| PDF | Estrazione testo + OCR Vision | `PyMuPDF (fitz)` + OpenAI Vision | Fallback Vision se testo insufficiente |
| JPG/PNG (immagini) | OCR Vision API | OpenAI Vision | Conversione base64 + prompt estrazione |

### Pipeline di Parsing XML

1. **Lettura file**: Byte stream dal file uploader Streamlit
2. **Rilevamento encoding**: Prolog XML → charset-normalizer → fallback UTF-8
3. **Parsing XML**: `xmltodict.parse()` → dizionario Python
4. **Estrazione metadati**: Data documento, tipo documento (TD01/TD04), fornitore
5. **Validazione P.IVA**: Confronto cedente/prestatore vs P.IVA ristorante attivo
6. **Estrazione righe**: Per ogni `DettaglioLinee`:
   - Descrizione (con pulizia caratteri corrotti)
   - Quantità, Prezzo Unitario, IVA%
   - Sconto percentuale (campo dedicato)
   - Unità di misura normalizzata (KG, LT, PZ, CF...)
   - Codice articolo (se presente)
7. **Filtro diciture**: Esclusione automatica righe informative (regex pattern bolla, meno di 3 lettere)
8. **Calcolo prezzo effettivo**: `totale_riga / quantità` per gestire sconti
9. **Categorizzazione immediata**: Check memoria cache → keyword → "Da Classificare"
10. **Salvataggio batch**: Upsert su tabella `fatture` con dedup per `file_origine + numero_riga`

### Tipi Documento Gestiti

| Codice | Tipo | Trattamento |
|--------|------|-------------|
| TD01 | Fattura | Importi positivi normali |
| TD02 | Acconto su fattura | Importi positivi |
| TD04 | Nota di Credito | **Importi invertiti** (negativi) |
| TD05 | Nota di Debito | Importi positivi |
| TD06 | Parcella | Importi positivi |
| TD16-TD27 | Autofatture/Integrazioni | Importi positivi |

### Estrazione P7M (Firma Digitale CAdES)

**Metodo 1 — ASN.1/CMS** (preferito):
```python
from asn1crypto import cms
content_info = cms.ContentInfo.load(contenuto_bytes)
signed_data = content_info['content']
xml_bytes = signed_data['encap_content_info']['content'].native
```

**Metodo 2 — Pattern matching** (fallback):
- Ricerca pattern `<?xml` o `<FatturaElettronica` nel binario
- Estrazione fino al tag di chiusura corrispondente
- Validazione XML con `xml.etree.ElementTree`

---

## 10. Multi-Tenancy e Multi-Ristorante

### Isolamento Dati

Ogni query al database include **obbligatoriamente** il filtro `user_id`:

```python
supabase.table("fatture")
    .select("*")
    .eq("user_id", user_id)           # Isolamento utente
    .eq("ristorante_id", ristorante_id) # Isolamento ristorante
```

Inoltre, Supabase PostgreSQL ha **Row Level Security (RLS)** attivo su tutte le tabelle, che funge da secondo livello di protezione.

### Multi-Ristorante

Un utente può avere più ristoranti (es. catena con 3 locali):

```
UTENTE (users)
  └── Ristorante 1 (ristoranti) ──→ Fatture ristorante 1
  └── Ristorante 2 (ristoranti) ──→ Fatture ristorante 2
  └── Ristorante 3 (ristoranti) ──→ Fatture ristorante 3
```

- **Dropdown selezione**: Visibile solo con 2+ ristoranti
- **Persistenza ultimo usato**: Salvato in `users.ultimo_ristorante_id`
- **Pulizia contesto**: Al cambio ristorante, cache e stato sessione vengono resettati
- **Admin**: Vede TUTTI i ristoranti di tutti i clienti

### Utenti Legacy

Se un utente pre-migrazione non ha record in `ristoranti`, il sistema tenta la creazione automatica:
1. Cerca ristorante con stessa P.IVA dello stesso utente
2. Se non trovato, crea nuovo record in `ristoranti`
3. Fallback: usa dati dalla tabella `users` per compatibilità

---

## 11. Schema Database Completo

### Tabelle Principali

#### `users` — Utenti del sistema

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | Generato automaticamente |
| email | TEXT UNIQUE | Login, lowercase |
| password_hash | TEXT | Argon2id hash |
| nome_ristorante | TEXT | Nome locale (legacy) |
| partita_iva | TEXT | P.IVA (legacy, ora in ristoranti) |
| ragione_sociale | TEXT | Ragione sociale |
| attivo | BOOLEAN | Account attivo/disattivato |
| created_at | TIMESTAMPTZ | Data creazione |
| reset_code | TEXT | Codice reset password temporaneo |
| reset_expires | TIMESTAMPTZ | Scadenza codice reset |
| login_attempts | INT | Contatore tentativi login (**legacy** — sostituito da tabella `login_attempts`) |
| password_changed_at | TIMESTAMPTZ | Ultima modifica password |
| last_login | TIMESTAMPTZ | Timestamp ultimo login riuscito |
| last_logout | TIMESTAMPTZ | Timestamp ultimo logout (invalida sessioni) |
| session_token | TEXT | Token sessione cookie |
| session_token_created_at | TIMESTAMPTZ | Creazione token sessione |
| ultimo_ristorante_id | UUID (FK) | Ultimo ristorante usato |
| pagine_abilitate | JSONB | Es: `{"marginalita": true, "workspace": true}` |
| dismissed_notification_ids | JSONB | Mappa notifiche nascoste `{id: dismissed_at}` (NUOVO v5.1) |
| trial_activated_at | TIMESTAMPTZ | Data attivazione trial (NUOVO v5.1) |
| trial_active | BOOLEAN | Account in periodo trial (NUOVO v5.1) |
| price_alert_threshold | NUMERIC(5,2) | Soglia % variazione prezzi (default 5.0, personalizzabile) (NUOVO v5.4) |

#### `ristoranti` — Locali (multi-ristorante)

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | Generato automaticamente |
| user_id | UUID (FK → users) | Proprietario |
| nome_ristorante | TEXT | Nome locale |
| partita_iva | TEXT | P.IVA per validazione fatture |
| ragione_sociale | TEXT | Ragione sociale |
| attivo | BOOLEAN | Ristorante attivo |
| created_at | TIMESTAMPTZ | Data creazione |

#### `fatture` — Righe di fattura (core data)

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | Auto-increment |
| user_id | UUID (FK → users) | Proprietario |
| ristorante_id | UUID (FK → ristoranti) | Ristorante associato |
| file_origine | TEXT | Nome file originale |
| numero_riga | INT | Numero riga nella fattura |
| data_documento | DATE | Data documento fattura |
| fornitore | TEXT | Nome fornitore |
| descrizione | TEXT | Descrizione prodotto (normalizzata) |
| quantita | NUMERIC | Quantità |
| unita_misura | TEXT | Unità di misura normalizzata |
| prezzo_unitario | NUMERIC | Prezzo per unità |
| iva_percentuale | NUMERIC | % IVA |
| totale_riga | NUMERIC | Importo totale riga |
| categoria | TEXT | Categoria assegnata |
| codice_articolo | TEXT | Codice EAN/fornitore |
| prezzo_standard | NUMERIC | Prezzo standardizzato per confronto |
| needs_review | BOOLEAN | Flag revisione admin |
| tipo_documento | TEXT | TD01, TD04, etc. |
| sconto_percentuale | NUMERIC | % sconto applicato |
| totale_documento | NUMERIC | ImportoTotaleDocumento da header XML (NUOVO v5.4) |
| totale_imponibile | NUMERIC | Somma ImponibileImporto da DatiRiepilogo (NUOVO v5.4) |
| totale_iva | NUMERIC | Somma Imposta da DatiRiepilogo (NUOVO v5.4) |
| data_consegna | DATE | Data consegna/ritiro (TD24, da DatiDDT o regex) (NUOVO v5.4) |
| data_competenza | DATE | Data competenza gestionale per reportistica (NUOVO v5.4) |
| deleted_at | TIMESTAMPTZ | Soft-delete: NULL = attiva; valorizzata = nel cestino (NUOVO v5.4) |
| created_at | TIMESTAMPTZ | Inserimento |

#### `prodotti_master` — Memoria globale AI

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

#### `prodotti_utente` — Memoria locale cliente

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | Auto-increment |
| user_id | UUID (FK → users) | Proprietario |
| descrizione | TEXT | Chiave matching |
| categoria | TEXT | Categoria personalizzata |
| updated_at | TIMESTAMPTZ | Ultimo aggiornamento |
| UNIQUE(user_id, descrizione) | | Constraint |

#### `classificazioni_manuali` — Memoria admin

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT (PK) | Auto-increment |
| descrizione | TEXT UNIQUE | Chiave matching |
| categoria_corretta | TEXT | Categoria imposta da admin |
| is_dicitura | BOOLEAN | Se True, riga trattata come nota/dicitura |

#### `margini_mensili` — Dati MOL

| Colonna | Tipo | Note |
|---------|------|------|
| id | UUID (PK) | Generato automaticamente |
| user_id | UUID (FK) | Proprietario |
| ristorante_id | UUID (FK) | Ristorante |
| anno | INT | Anno |
| mese | INT CHECK(1-12) | Mese |
| **INPUT MANUALE** | | |
| fatturato_iva10 | NUMERIC(10,2) | Fatturato soggetto IVA 10% |
| fatturato_iva22 | NUMERIC(10,2) | Fatturato soggetto IVA 22% |
| altri_ricavi_noiva | NUMERIC(10,2) | Altri ricavi non soggetti IVA |
| altri_costi_fb | NUMERIC(10,2) | Costi F&B extra non in fatture |
| altri_costi_spese | NUMERIC(10,2) | Spese extra non in fatture |
| costo_dipendenti | NUMERIC(10,2) | Costo personale lordo mensile |
| **SNAPSHOT AUTOMATICI** (da fatture) | | |
| costi_fb_auto | NUMERIC(10,2) | Costi F&B da `fatture` (ricalcolati) |
| costi_spese_auto | NUMERIC(10,2) | Costi Spese da `fatture` (ricalcolati) |
| **SNAPSHOT CALCOLATI** (ricalcolati on-the-fly) | | |
| fatturato_netto | NUMERIC(10,2) | Fatturato netto IVA |
| costi_fb_totali | NUMERIC(10,2) | F&B auto + altri_costi_fb |
| primo_margine | NUMERIC(10,2) | Fatturato netto - costi F&B totali |
| mol | NUMERIC(10,2) | Margine Operativo Lordo |
| food_cost_perc | NUMERIC(5,2) | Food Cost % |
| spese_perc | NUMERIC(5,2) | Spese Generali % |
| personale_perc | NUMERIC(5,2) | Costo personale % |
| mol_perc | NUMERIC(5,2) | MOL % |
| **CENTRI DI PRODUZIONE** | | |
| fatturato_food | NUMERIC(12,2) | Fatturato centro FOOD |
| fatturato_beverage | NUMERIC(12,2) | Fatturato centro BEVERAGE (rinominato da `fatturato_bar` in v5.4) |
| fatturato_alcolici | NUMERIC(12,2) | Fatturato centro ALCOLICI |
| fatturato_dolci | NUMERIC(12,2) | Fatturato centro DOLCI |
| created_at | TIMESTAMP | Data creazione |
| updated_at | TIMESTAMP | Ultimo salvataggio |
| UNIQUE(ristorante_id, anno, mese) | | Constraint |

#### `upload_events` — Log upload fatture

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | Auto-increment |
| user_id | UUID | Chi ha caricato |
| user_email | TEXT | Email dell'utente |
| file_name | TEXT | Nome file |
| file_type | TEXT | `xml` \| `pdf` \| `image` \| `unknown` |
| status | TEXT | `SAVED_OK` \| `SAVED_PARTIAL` \| `FAILED` |
| rows_parsed | INT | Righe estratte dal file |
| rows_saved | INT | Righe salvate con successo |
| rows_excluded | INT | Righe escluse (diciture, duplicati) |
| error_stage | TEXT | `PARSING` \| `VISION` \| `SUPABASE_INSERT` \| `POSTCHECK` |
| error_message | TEXT | Dettaglio errore (max 500 char) |
| details | JSONB | Info aggiuntive strutturate |
| created_at | TIMESTAMPTZ | Timestamp upload |

#### `login_attempts` — Tentativi di login (rate limiting persistente)

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT IDENTITY (PK) | Auto-increment |
| email | TEXT NOT NULL | Email tentativo |
| attempted_at | TIMESTAMPTZ | Timestamp tentativo |
| success | BOOLEAN | Successo o fallimento |

Indice su `(email, attempted_at DESC)` per query veloci. Solo `service_role` può scrivere (RLS, nessuna policy per anon/authenticated).

### Altre Tabelle

| Tabella | Scopo |
|---------|-------|
| `ricette` | Ricette con ingredienti (JSON), foodcost, prezzo vendita |
| `ingredienti_utente` | Ingredienti personalizzati legacy |
| `ingredienti_workspace` | Ingredienti manuali del Workspace (nome, prezzo_per_um, um) |
| `note_diario` | Diario operativo per ristorante |
| `review_confirmed` | Righe confermate dopo review admin |
| `review_ignored` | Righe ignorate in review admin |
| `login_attempts` | Tentativi login per rate limiting persistente su DB |
| `fatture_queue` | Buffer webhook Invoicetronic — vedere Sezione 20 |
| `brand_ambigui` | Tracking automatico brand multi-categoria (machine learning) |
| `ai_usage_events` | Ledger costi OpenAI: token, costi per operazione AI (NUOVO v5.1) |
| `categorie` | Elenco centralizzato delle 31 categorie standard (NUOVO v5.4) |
| `custom_tags` | Tag personalizzati per ristorante (nome, emoji, colore) (NUOVO v5.4) |
| `custom_tag_prodotti` | Associazioni tag ↔ descrizioni fattura (NUOVO v5.4) |
| `cache_version` | Versione cache classificazione per invalidazione cross-process (NUOVO v5.4) |
| `category_change_log` | Storico append-only modifiche categoria (audit forense) (NUOVO v5.4) |
| `system_maintenance_status` | Stato retention automatica fatture > 2 anni (NUOVO v5.4) |

#### `fatture_queue` — Buffer webhook Invoicetronic (migration 045)

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGINT IDENTITY (PK) | Auto-increment |
| event_id | TEXT NOT NULL UNIQUE | ID evento da Invoicetronic (idempotenza) |
| user_id | UUID (nullable) | FK logica → users; NULL se P.IVA non trovata |
| ristorante_id | UUID (nullable) | FK logica → ristoranti; NULL se P.IVA non trovata |
| piva_raw | TEXT NOT NULL | P.IVA destinatario estratta dall'XML |
| xml_content | TEXT (nullable) | XML grezzo FatturaPA; nullificato dopo 24h (GDPR) |
| xml_url | TEXT (nullable) | URL download su Invoicetronic (fallback) |
| xml_hash | TEXT (nullable) | SHA-256 dell'xml_content (deduplicazione) |
| payload_meta | JSONB | Metadati non-PII (tipo_doc, data, importo, piva_cedente) |
| status | TEXT CHECK | `pending` \| `processing` \| `done` \| `retry` \| `dead` \| `unknown_tenant` |
| attempt_count | INT DEFAULT 1 | Numero tentativi elaborazione |
| worker_id | TEXT (nullable) | ID worker che ha acquisito il record (lock pessimistico) |
| locked_at | TIMESTAMPTZ (nullable) | Timestamp acquisizione lock |
| error_message | TEXT (nullable) | Dettaglio ultimo errore |
| created_at | TIMESTAMPTZ | Ricezione webhook |
| processed_at | TIMESTAMPTZ (nullable) | Completamento elaborazione |

**RLS**: Attiva, nessuna policy per anon/authenticated — solo `service_role` accede.

**Stored Procedure RPC associate**:
- `claim_batch_for_processing(p_worker_id, p_batch_size)` — atomico con `SELECT FOR UPDATE SKIP LOCKED`
- `mark_queue_item_done(p_queue_id, p_purge_xml)` — aggiorna status + nullifica XML
- `schedule_retry(p_queue_id, p_error_msg)` — backoff esponenziale
- `purge_processed_xml_content(p_retention_hours)` — GDPR cleanup
- `release_stale_locks(p_timeout_minutes)` — recovery worker crashati
- `resolve_unknown_tenant(p_piva)` — ri-mette in pending i record con P.IVA non ancora registrata

#### `brand_ambigui` — Brand multi-categoria (migration 048)

Tabella di machine learning: traccia automaticamente i brand che vengono spesso corretti dall'utente in categorie diverse (es. un fornitore che vende sia carne che verdure).

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | Auto-increment |
| brand | TEXT NOT NULL UNIQUE | Nome brand estratto dalla descrizione |
| num_correzioni | INTEGER | Numero totale correzioni ricevute |
| categorie_viste | TEXT[] | Array categorie in cui il brand è stato classificato |
| tasso_correzione | NUMERIC(6,4) | Percentuale di correzioni manuale (0.0-1.0) |
| aggiunto_automaticamente | BOOLEAN | Se `TRUE`: il dizionario viene bypassato per questo brand |
| prima_vista | TIMESTAMPTZ | Prima occorrenza nelle fatture |
| ultima_modifica | TIMESTAMPTZ | Ultimo aggiornamento contatori |

**Logica**: Quando un brand accumula ≥ 3 correzioni su ≥ 2 categorie diverse con tasso > 20%, `aggiunto_automaticamente` diventa `TRUE` e il brand viene escluso dal matching deterministico del dizionario (passa direttamente al GPT-4o-mini per massima flessibilità).

#### `ai_usage_events` — Ledger costi AI (migration 051)

| Colonna | Tipo | Note |
|---------|------|------|
| id | BIGSERIAL (PK) | Auto-increment |
| ristorante_id | UUID (FK) | Ristorante associato |
| user_id | UUID (FK) | Utente che ha generato la spesa |
| operation_type | TEXT | `pdf` \| `categorization` \| `other` |
| prompt_tokens | INT | Token prompt inviati |
| completion_tokens | INT | Token risposta ricevuti |
| total_tokens | INT | Totale token |
| input_cost | NUMERIC | Costo input ($0.15/1M token GPT-4o-mini) |
| output_cost | NUMERIC | Costo output ($0.60/1M token GPT-4o-mini) |
| total_cost | NUMERIC | Costo totale operazione |
| model | TEXT | Modello AI usato (es. `gpt-4o-mini`) |
| source_file | TEXT | File origine operazione |
| metadata | JSONB | Metadati aggiuntivi strutturati |
| created_at | TIMESTAMPTZ | Timestamp operazione |

**Indici**: `(ristorante_id, created_at DESC)`, `(operation_type)` per aggregazioni veloci.

**Service associato**: `services/ai_cost_service.py` — funzione `track_ai_usage()` registra ogni chiamata OpenAI nel ledger. Utilizzato da Tab 6 del pannello admin per report costi per cliente/ristorante.

### Migrazioni SQL (85 file totali)

**68 file legacy** (001→068) + **17 file timestamp-based Supabase** gestiscono:

- Aggiunta colonne incrementali (reset, sconto, needs_review, verified, P.IVA, altri_ricavi_noiva, tipo_documento, dismissed_notification_ids, trial, data_consegna, data_competenza, totali header XML, price_alert_threshold)
- Creazione tabelle (categorie, prodotti_master, prodotti_utente, ristoranti, ricette, ingredienti_workspace, note_diario, margini_mensili, login_attempts, fatture_queue, brand_ambigui, ai_usage_events, custom_tags, custom_tag_prodotti, cache_version, category_change_log, system_maintenance_status)
- Policy RLS per multi-tenancy e autenticazione custom
- Stored procedure RPC (create_ristorante, get_distinct_files, claim_batch_for_processing, mark_queue_item_done, schedule_retry, purge_processed_xml_content, release_stale_locks, resolve_unknown_tenant, fn_bump_cache_version)
- Indici di performance
- Fix retroattivi (diciture corrotte, permessi RLS, foreign key, duplicate P.IVA ristoranti, normalizzazione categorie legacy)
- Tracking costi AI (`ai_usage_events`), sessioni, token, rate limiting
- Soft-delete fatture con cestino + retention 2 anni (`deleted_at`, `system_maintenance_status`)
- Cache versioning cross-process (`cache_version` + triggers su prodotti_utente/prodotti_master/classificazioni_manuali)
- Category change log per audit storico modifiche
- Rinomina `fatturato_bar` → `fatturato_beverage` (migration 065)

---

## 12. Pannello di Amministrazione

Il pannello admin (`pages/admin.py`) è accessibile solo agli utenti con email in `ADMIN_EMAILS`.

### Tab 1: 📊 Gestione Clienti

- Lista completa clienti con statistiche (fatture, righe, costi, ultimo caricamento)
- Creazione nuovo cliente GDPR-compliant (l'admin non imposta la password)
- Token di attivazione via email (24 ore validità)
- Impersonazione clienti (l'admin vede l'app come il cliente)
- Cookie impersonazione per sopravvivere a refresh pagina
- Attivazione/Disattivazione account
- Gestione pagine abilitate per cliente (Marginalità, Foodcost)

### Tab 2: 💰 Review Righe €0

- Lista righe fattura con prezzo = €0 (potenziali diciture/note)
- Classificazione diretta: "È un prodotto" (assegna categoria) o "È una dicitura" (escludi)
- Salvataggio in `classificazioni_manuali` con flag `is_dicitura`
- Review permanente: righe confermate e ignorate tracciate

### Tab 3: 🧠 Memoria Globale AI

- Data editor con tutti i record di `prodotti_master`
- Modifica categoria direttamente nella tabella
- Propagazione modifica a tutte le fatture nel database
- Filtro per descrizione e categoria
- Conteggio record e statistiche

### Tab 4: 📝 Memoria Clienti

- Visualizzazione `prodotti_utente` per ogni cliente
- Utile per diagnosticare classificazioni personalizzate

### Tab 5: 🔍 Integrità Database

- Conteggio righe per tabella
- Verifica fatture con categoria NULL
- Verifica ristoranti senza utente
- Verifica utenti senza ristoranti
- Fix automatici disponibili

### Tab 6: 💳 Costi AI

- Tracciamento costi OpenAI per cliente/ristorante
- Aggregazione giornaliera e mensile
- Budget giornaliero: 1.000 classificazioni per ristorante

---

## 13. Calcolo Marginalità e KPI

### Pagina Calcolo Margine (pages/1_calcolo_margine.py, ~1.546 righe)

3 sotto-tab:

#### 📊 Calcolo Ricavi-Costi-Margini

Tabella trasposta 12 mesi. Le voci di input si dividono in **manuali** (fatturato, costi extra, personale) e **automatici** (costi da fatture):

| Voce | Fonte | Formula |
|------|-------|---------|
| Fatturato IVA 10% | Input manuale | su `margini_mensili.fatturato_iva10` |
| Fatturato IVA 22% | Input manuale | su `margini_mensili.fatturato_iva22` |
| Altri Ricavi (no IVA) | Input manuale | su `margini_mensili.altri_ricavi_noiva` |
| Costi F&B | Auto da fatture + manuale | `costi_fb_auto` + `altri_costi_fb` |
| Costi Spese Generali | Auto da fatture + manuale | `costi_spese_auto` + `altri_costi_spese` |
| Costo Personale | Input manuale | su `margini_mensili.costo_dipendenti` |
| **Fatturato Netto** | **Calcolato** | **(IVA10 / 1.10) + (IVA22 / 1.22) + altri_ricavi** |
| **Food Cost %** | **Calcolato** | **(Costi F&B Totali / Fatturato Netto) × 100** |
| **1° Margine** | **Calcolato** | **Fatturato Netto - Costi F&B Totali** |
| **1° Margine %** | **Calcolato** | **1° Margine / Fatturato Netto × 100** |
| **Spese Gen. %** | **Calcolato** | **Spese / Fatturato Netto × 100** |
| **MOL** | **Calcolato** | **Fatturato Netto - F&B - Spese - Personale** |
| **MOL %** | **Calcolato** | **MOL / Fatturato Netto × 100** |

#### Soglie KPI con Commenti Automatici

| KPI | 🟢 Eccellente | 🟡 Norma | 🟠 Attenzione | 🔴 Critico |
|-----|-------------|-----------|-------------|-----------|
| Food Cost % | < 28% | 28-33% | 33-38% | > 38% |
| Spese Gen. % | < 15% | 15-22% | 22-28% | > 28% |
| 1° Margine % | > 70% | 62-70% | 55-62% | < 55% |
| MOL % | > 20% | 12-20% | 5-12% | < 5% |

#### 🏭 Centri di Produzione

- Suddivisione fatturato mensile per centro: FOOD, BAR, ALCOLICI, DOLCI
- Input per mese selezionato, salvato su `margini_mensili.fatturato_food/beverage/alcolici/dolci` (nota: `fatturato_bar` rinominato in `fatturato_beverage` da migration 065)
- Analisi aggregata su range di periodo via `carica_fatturato_centri_periodo()`
- Calcolo Food Cost % e margine per singolo centro
- Grafici a barre comparativi per centro

#### 🔬 Analisi Avanzate

- Trend temporale costi per categoria F&B via `carica_costi_per_categoria()`
- Breakdown mensile con grafici Plotly interattivi
- Export Excel formattato

---

## 14. Pagine Secondarie

### 2_foodcost.py — Foodcost, Ricette e Diario (~2.125 righe)

**4 Tab con navigazione a bottoni:**

**Tab 1 — 📋 Analisi Ricette e Menù:**
- KPI globali menù: numero ricette, foodcost totale, costo medio, margine medio, incidenza foodcost %
- Tabella riepilogativa per categoria con emoji mapping
- Grafici Plotly: distribuzione categorie, margine netto per piatto

**Tab 2 — 🧪 Lab Ricette (CRUD completo):**
- Form inserimento/modifica ricetta: nome, categoria, note, prezzo vendita IVA inc.
- Ingredienti con selezione da 3 fonti: 🟢 da fatture, 📝 ingredienti workspace, 🥘 semilavorati
- Calcolo foodcost per ingrediente: gestione grammatura confezione, conversione UM
- Ricette annidate (semilavorati come ingredienti di altre ricette)
- Calcolo automatico foodcost totale e margine
- Logica `estrai_grammatura_da_nome()`: regex per KG/GR/LT/ML/CL da descrizione

**Tab 3 — 📓 Diario:**
- Note operative giornaliere salvate su tabella `note_diario`
- CRUD: crea, modifica, elimina note per data
- Sanitizzazione XSS via `html.escape()`

**Tab 4 — 📊 Export Excel:**
- Export ricette con ingredienti e foodcost in formato strutturato
- Include: nome, categoria, ingredienti (espansi), foodcost, prezzo vendita, margine

**Ingredienti Workspace:**
- Tabella `ingredienti_workspace` per ingredienti non presenti nelle fatture
- Campi: nome, prezzo_per_um, um (unità di misura)
- Cache `_get_ingredienti_workspace_cached()` con TTL=300s

### 3_controllo_prezzi.py — Controllo Prezzi (~584 righe)

**3 Tab con navigazione a bottoni:**

**Tab 1 — 📈 Variazioni Prezzo:**
- Chiama `calcola_alert(df, soglia_aumento, filtro_prodotto)` da `db_service.py`
- Soglia minima alert configurabile (default 5%)
- Ricerca per nome prodotto
- Tabella con: storico ultimi 5 prezzi, media storica, ultimo prezzo, variazione %
- Formattazione: 🔴 aumento, 🟢 ribasso
- Export Excel

**Tab 2 — 🎁 Sconti e Omaggi:**
- KPI: 💸 Sconti Applicati (righe con totale negativo), 🎁 Omaggi Ricevuti (prezzo =€0), ✅ Totale Risparmiato
- Dettaglio sconti in expander
- Omaggi con ultimo prezzo storico e valore stimato calcolato
- Export Excel separato per sconti e omaggi

**Tab 3 — 📋 Note di Credito:**
- Filtra per `tipo_documento == 'TD04'` oppure `totale_riga < 0` (retrocompatibilità)
- Search descrizione + filtro fornitore
- KPI: totale importo NC, numero documenti, numero righe
- Export Excel

### gestione_account.py — Gestione Account

- Cambio password con validazione GDPR
- Visualizzazione dati account
- Gestione ristoranti (nome, P.IVA, ragione sociale)
- **Export dati GDPR Art. 15** (JSON): account, ristoranti, fatture, classificazioni_manuali, upload_events, ai_usage_events, ricette, note_diario, margini_mensili, prodotti_utente, custom_tags

### privacy_policy.py — Privacy e Condizioni

Due tab:
- **Privacy Policy** (v3.4, 1 Maggio 2026): Informativa GDPR completa (titolare, base giuridica, diritti, data retention, sub-processori: Supabase, OpenAI, Brevo, Invoicetronic, Railway, Streamlit Cloud). Cookie impersonazione admin: 30 minuti.
- **Terms of Service**: Condizioni d'uso, limitazioni, clausola "non conservazione sostitutiva"

---

## 15. Testing e Qualità del Codice

### Framework e Configurazione

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
```

### Suite di Test (330 test totali, confermati da pytest)

| File | Test approx. | Copertura |
|------|------|-----------| 
| `test_trial.py` | 39 | Gestione trial, attivazione, scadenza, logiche temporali |
| `test_text_utils.py` | 30 | Normalizzazione, estrazione fornitore, pulizia |
| `test_piva_validator.py` | 18 | Validazione P.IVA (Luhn), normalizzazione |
| `test_notification_service.py` | 18 | Notifiche in-app: upload, prezzi, dismiss, mensili (NUOVO v5.1) |
| `test_ai_service.py` | 16 | Classificazione AI, memoria 3 livelli, quarantena |
| `test_validation.py` | 14 | Diciture, sconti, integrità fattura |
| `test_constants.py` | 13 | Integrità categorie, regex compilate, KPI soglie |
| `test_db_service.py` | 12 | Alert variazioni prezzo, normalizzazione categorie |
| `test_auth_service.py` | 12 | Login, rate limiting, GDPR password, reset |
| `test_invoice_service.py` | 11 | Parsing XML, P7M, encoding, tipo documento |
| `test_formatters.py` | 11 | Formattazione numeri, base64, prezzo standard |

> I conteggi per file sono basati su funzioni `test_*`; il totale di 330 include test parametrizzati espansi da pytest.

### Fixtures (conftest.py)

- `mock_supabase`: Mock completo del client Supabase con risposte predefinite
- `mock_openai`: Mock OpenAI che simula risposte di classificazione
- `sample_xml`: Fattura XML di esempio per test parsing
- Isolamento completo: nessun test tocca servizi esterni

### Esecuzione

```bash
# Tutti i test
pytest tests/ -v --tb=short

# Test specifico
pytest tests/test_ai_service.py -v

# Con coverage
pytest tests/ --cov=services --cov=utils --cov-report=html
```

Ultimo risultato: **330/330 PASSED**

---

## 16. Deploy e Infrastruttura

### Streamlit Community Cloud

| Parametro | Valore |
|-----------|--------|
| Piattaforma | Streamlit Community Cloud (Free Tier) |
| Repository | GitHub (branch `main`) |
| Auto-deploy | Push su `main` → deploy automatico |
| URL | https://ohyeah.streamlit.app/ |
| Region | US (default Streamlit) |
| Python version | 3.12 |

### Railway — Deploy Worker FastAPI

Railway è la piattaforma utilizzata per deployare i servizi Docker separati dal frontend Streamlit. L'architettura aggiornata usa tre service distinti: frontend Streamlit, FastAPI Worker per classificazione/parsing e `queue-worker` dedicato al consumo continuo di `fatture_queue`.

| Parametro | Valore |
|-----------|--------|
| Piattaforma | Railway (Hobby o Pro plan) |
| Build | `docker/Dockerfile` (percorso configurato in `railway.toml`) |
| Servizi | Tre servizi separati: `ohyeah` (Streamlit) + `worker` (FastAPI) + `queue-worker` (worker asincrono) |
| Comunicazione interna | `WORKER_BASE_URL` → `http://worker:8000` (rete privata Railway) |
| URL worker esterno | `https://envoicescan-ai-production.up.railway.app` (CORS configurato) |
| Configurazione | `railway.toml`: `build.dockerfilePath = "docker/Dockerfile"` |

**Setup Railway**:
1. Collega repo GitHub a Railway
2. Crea tre service: app Streamlit, worker FastAPI, queue-worker dedicato
3. Imposta le env vars nel dashboard Railway (NON committare `.env`)
4. Il service `worker` espone solo le API FastAPI; il service `queue-worker` non richiede dominio pubblico
5. Sul service `worker` imposta `ENABLE_INLINE_QUEUE_PROCESSOR=0`

**Dettagli tecnici queue-worker Railway**:

| Parametro | Valore |
|-----------|--------|
| Entry point | `python worker/run.py` |
| Logica | `worker/queue_processor.py` |
| Modalità | Loop continuo 24/7 |
| Intervallo poll | 15 secondi |
| Env vars richieste | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `INVOICETRONIC_API_KEY`, `OPENAI_API_KEY` |
| Env vars operative | `WORKER_BATCH_SIZE=10`, `WORKER_XML_RETENTION_HOURS=24`, `WORKER_STALE_LOCK_MINUTES=10` |

### Supabase Edge Functions — invoicetronic-webhook

La Edge Function è scritta in **TypeScript/Deno** e gira sull'infrastruttura serverless di Supabase (regione EU). Viene innescata da ogni POST webhook proveniente da Invoicetronic.

| Parametro | Valore |
|-----------|--------|
| Runtime | Deno (Supabase Edge Functions) |
| File | `supabase/functions/invoicetronic-webhook/index.ts` |
| Deploy | `supabase functions deploy invoicetronic-webhook --no-verify-jwt` |
| Sviluppo locale | `.\scripts\dev-serve.ps1` (porta 54321) |
| Test | `.\scripts\dev-serve.ps1 -Test` (esegue `test.ts` con Deno) |
| Secrets richiesti | `SUPABASE_SERVICE_ROLE_KEY`, `INVOICETRONIC_WEBHOOK_SECRET`, `INVOICETRONIC_API_KEY` |

### Secrets Management

I secrets sono gestiti su due livelli:

**Streamlit Cloud** (`st.secrets`):
```toml
# .streamlit/secrets.toml (NON versionato)
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "eyJhbG..."
OPENAI_API_KEY = "sk-..."
WORKER_BASE_URL = "http://worker:8000"   # oppure URL Railway

[brevo]
api_key = "xkeysib-..."
sender_email = "noreply@ohyeah.app"
sender_name = "OH YEAH! Hub"
reply_to_email = "support@ohyeah.app"
reply_to_name = "Support OH YEAH! Hub"
```

**Supabase Edge Function** (via `supabase secrets set`):
```
SUPABASE_URL                    → iniettato automaticamente
SUPABASE_SERVICE_ROLE_KEY       → Supabase Dashboard → Settings → API
INVOICETRONIC_WEBHOOK_SECRET    → Dashboard Invoicetronic → Webhook
INVOICETRONIC_API_KEY           → Dashboard Invoicetronic → API Keys
```

**GitHub Actions** (Settings → Secrets → Actions):
```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
INVOICETRONIC_API_KEY
OPENAI_API_KEY
```

### Dipendenze Lockate

Il file `requirements-lock.txt` contiene 100 pacchetti con versioni esatte per build riproducibili.

### Supabase

| Parametro | Valore |
|-----------|--------|
| Piano | Free Tier |
| Region | EU (Frankfurt) |
| PostgreSQL | v15 |
| RLS | Attivo su tutte le tabelle |
| Backup | Automatici giornalieri (piano free) |
| Limite | 500 MB storage, 2 GB transfer, pausa dopo 7 giorni inattività |

### Struttura Docker

I file Docker sono organizzati nella cartella `docker/`:

| File | Descrizione |
|------|-------------|
| `docker/Dockerfile` | Build immagine unica per app Streamlit e worker FastAPI |
| `docker/docker-compose.yml` | Stack completo per sviluppo locale |
| `docker/docker-compose.prod.yml` | Stack produzione Railway/VPS — porta worker 8000 **non esposta** |
| `docker/docker-entrypoint.sh` | Script avvio container |

Il `docker-compose.prod.yml` definisce tre servizi:
- `ohyeah`: Streamlit su porta 8501 (esposta)
- `worker`: FastAPI su porta 8000 (**non esposta** — solo rete Docker interna)
- `queue-worker`: worker asincrono `fatture_queue` senza porta pubblica

La comunicazione applicativa avviene via `WORKER_BASE_URL=http://worker:8000`, garantendo che le route `/api/classify` e `/api/parse` siano raggiungibili solo dall'interno della rete privata, mentre il consumo della coda resta interamente delegato al service `queue-worker`.

---

## 17. Monitoraggio e Alerting

### GitHub Actions — Uptime Check

File: `.github/workflows/uptime_check.yml`

```yaml
name: Uptime Check
on:
  schedule:
    - cron: '*/5 * * * *'         # Ogni 5 minuti
  workflow_dispatch:               # Trigger manuale

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Check site
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            --max-time 30 \
            "https://ohyeah.streamlit.app/")
          if [ "$STATUS" -ne 200 ]; then
            echo "SITE DOWN - Status: $STATUS"
            # Invio alert email via Brevo API
            curl -X POST "https://api.brevo.com/v3/smtp/email" \
              -H "api-key: ${{ secrets.BREVO_API_KEY }}" \
              -H "Content-Type: application/json" \
              -d '{"sender":{"email":"alerts@ohyeah.app","name":"OH YEAH! Hub Monitor"},
                   "to":[{"email":"mattiadavolio90@gmail.com"}],
                   "subject":"🚨 OH YEAH! Hub DOWN",
                   "htmlContent":"<p>Status: '$STATUS'</p>"}'
            exit 1
          fi
          echo "Site OK - Status: $STATUS"
```

### GitHub Actions — Worker fatture_queue

File: `.github/workflows/queue-worker.yml`

Questo workflow non è più il worker primario della coda. Dal 10 Aprile 2026 resta solo come fallback manuale di emergenza per drain forzato di `fatture_queue` quando il service Railway `queue-worker` non è disponibile.

```yaml
name: Worker — fatture_queue processor
on:
  workflow_dispatch:          # Trigger manuale con parametro batch_size

jobs:
  process-queue:
    runs-on: ubuntu-latest
    timeout-minutes: 10       # Safeguard: kill dopo 10 minuti
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: 'pip' }
      - run: pip install -r requirements.txt
      - name: Run queue worker
        env:
          SUPABASE_URL:              ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          INVOICETRONIC_API_KEY:     ${{ secrets.INVOICETRONIC_API_KEY }}
          OPENAI_API_KEY:            ${{ secrets.OPENAI_API_KEY }}
          WORKER_BATCH_SIZE:         ${{ github.event.inputs.batch_size || '10' }}
          WORKER_XML_RETENTION_HOURS: '24'
          WORKER_STALE_LOCK_MINUTES:  '10'
        run: python worker/run.py
```

**Nota operativa**: l'elaborazione continua della coda ora gira su Railway tramite il service dedicato `queue-worker`. GitHub Actions non consuma più minuti su schedule automatico per questo flusso.

**Trigger manuale**: dal tab "Actions" su GitHub è possibile avviare il worker manualmente, specificando un `batch_size` personalizzato per drain forzato della coda.

### Logging Applicativo

| Componente | Configurazione |
|-----------|---------------|
| File handler | `RotatingFileHandler` |
| Max dimensione | 50 MB per file |
| Backup files | 10 (totale max ~550 MB) |
| Livello | INFO in produzione |
| Format | `%(asctime)s [%(name)s] %(levelname)s %(message)s` |
| Logger modulari | `app`, `ai`, `auth`, `invoice`, `db`, `admin`, `email`, `margine_service`, `fastapi_worker`, `worker.queue_processor` |

---

## 18. Sicurezza e Compliance GDPR

### Misure di Sicurezza Implementate

| Categoria | Misura | Dettaglio |
|-----------|--------|-----------|
| **Autenticazione** | Argon2id | m=65536, parametri default libreria (OWASP) |
| **Sessioni** | Token opaco ad alta entropia + Cookie 30gg | Invalidazione esplicita su logout |
| **Rate Limiting** | Login: DB persistente; Reset: in-memory | Login usa tabella `login_attempts` su Supabase; Reset usa dict in-memory thread-safe |
| **Input Validation** | Sanitizzazione AI | Control char removal + 300 char truncation |
| **XSS Prevention** | `html.escape()` | Su tutti gli output user-generated |
| **CSRF Protection** | `enableXsrfProtection = true` | Streamlit nativo |
| **SQL Injection** | Parametrized queries | Supabase client non permette raw SQL |
| **File Upload** | Magic bytes validation | Verifica header file oltre all'estensione |
| **File Upload** | Size limits | 100 file, 200 MB totale, 50 MB per P7M |
| **Error Handling** | `showErrorDetails = false` | Mai esporre stack trace in produzione |
| **Password** | GDPR Art.32 compliance | 10+ char, 3/4 complessità, blacklist |
| **Logging** | No PII nei log | Email troncate, password mai loggate |
| **CORS** | `enableCORS = false` | Disabilitato (non necessario per SPA) |
| **Cookie** | Secure + SameSite=Strict | `extra-streamlit-components` non supporta HttpOnly; protetti da interception (Secure) e CSRF (SameSite=Strict) |
| **Inattività sessione** | Auto-logout 8 ore | `SESSION_INACTIVITY_HOURS = 8`; sessione invalida anche se il token non esiste in DB |
| **IDOR** | `.eq('userid', user_id)` su UPDATE/DELETE | Ogni scrittura workspace include filtro owner; previene accesso ai dati altrui |
| **Path Traversal** | Sanitizzazione percorsi | `nome_file` e `File_Origine` sanificati prima dell'utilizzo nel file system |
| **Worker API** | Porta 8000 interna | In produzione il worker FastAPI non espone la porta 8000 all'esterno; accesso solo via rete Docker interna |
| **Reset Token** | `secrets.token_urlsafe(32)` | 256 bit di entropia; verifica constant-time (HMAC) |
| **Secrets** | Streamlit Secrets | Variables d'ambiente, mai hardcoded |
| **XXE Protection** | defusedxml | Validazione XML con defusedxml prima del parsing — prevenzione XML External Entity attacks |
| **SSRF Protection** | Whitelist host | Solo `*.invoicetronic.com/.it` su HTTPS per fetch XML remoti |
| **Dependencies** | `requirements-lock.txt` | 100 pacchetti freezati per supply chain security |

### Compliance GDPR

- **Privacy Policy**: Pagina dedicata con informativa completa
- **Terms of Service**: Condizioni d'uso con clausole legali italiane
- **Data Retention**: Le fatture restano nel DB finché l'utente le elimina; dopo soft-delete nel cestino per 30 gg, poi eliminazione definitiva
- **Retention automatica**: Fatture > 2 anni eliminate automaticamente dal worker (job `fatture_retention_2y`)
- **Diritto all'oblio**: Funzione "Elimina Account" self-service — eliminazione permanente a cascata su 16 tabelle (fatture, prodotti_utente, classificazioni_manuali, upload_events, margini_mensili, review_confirmed, review_ignored, ricette, ingredienti_workspace, note_diario, custom_tags, ai_usage_events, login_attempts, ristoranti, category_change_log, cache_version) + riga users
- **Portabilità**: Export JSON GDPR di tutti i dati (10 tabelle) da Gestione Account
- **Base giuridica**: Contratto (Art. 6.1.b) per il servizio, consenso per marketing
- **Nota legale**: "Non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014"
- **Creazione client GDPR**: L'admin non conosce mai la password del cliente

---

## 19. Troubleshooting e FAQ Tecniche

### Problemi Comuni

#### L'app non si carica (pagina bianca)
1. Verificare che Supabase non sia in pausa (free tier: 7 giorni inattività)
2. Controllare status su https://status.streamlit.io
3. Verificare GitHub Actions per alert automatici

#### Fattura scartata durante upload
- **"P.IVA non corrispondente"**: La P.IVA del cedente non corrisponde al ristorante attivo
- **"File già caricato"**: Deduplicazione basata su `file_origine + user_id + ristorante_id`
- **"Encoding non supportato"**: File con charset esotico → charset-normalizer rileva automaticamente

#### Celle bianche nella colonna Categoria
- Bug noto di Streamlit: se il valore non è nelle opzioni del SelectboxColumn, appare vuoto
- Il sistema applica automaticamente `valida_categoria()` per forzare "Da Classificare"

#### L'AI non classifica correttamente un prodotto
1. **Correggi manualmente**: Modifica la categoria nel data editor e clicca "Salva"
2. **Il sistema impara**: La correzione viene salvata in memoria locale (cliente) o globale (admin)
3. **Prossima volta**: Il prodotto sarà classificato correttamente senza chiamata AI

#### Sessione scaduta (login ripetuto)
- Il token sessione dura 30 giorni. Se scade, il cookie viene invalidato
- L'auto-logout per inattività scatta dopo 8 ore senza interazioni
- Svuotare cache browser per problemi persistenti

#### Fatture Invoicetronic non appaiono in dashboard
1. Verificare status `fatture_queue`: record con `status=pending` → non ancora processati
2. Il service Railway `queue-worker` polla la coda ogni 15 secondi → attendere il ciclo successivo
3. `status=failed` o `status=dead` → vedere `error_message` nella tabella
4. `status=unknown_tenant` → P.IVA del ristorante non ancora registrata su OH YEAH! Hub; aggiungere il ristorante con la P.IVA corretta, poi chiamare la RPC `resolve_unknown_tenant(piva)` per rimettere in `pending`
5. Verificare che la Edge Function `invoicetronic-webhook` risponda (GET `/functions/v1/invoicetronic-webhook` → `200 OK`)

#### Firma webhook Invoicetronic non valida
- Verificare che `INVOICETRONIC_WEBHOOK_SECRET` nella Edge Function Supabase corrisponda a quello configurato nel dashboard Invoicetronic → Webhooks
- Anti-replay: se il timestamp del webhook è più vecchio di 5 minuti, viene rifiutato (protocollo normale → Invoicetronic ri-invia)

#### FastAPI Worker non raggiungibile
- Se `WORKER_BASE_URL` è impostato ma il worker non risponde, `worker_client.py` fa fallback automatico sulle funzioni Python locali
- Verificare `GET /health` sul worker → `{"status": "ok"}`
- In Docker: verificare che il servizio `worker` sia `healthy` prima di avviare `ohyeah`

### Comandi Utili per Sviluppatori

```bash
# Avviare l'app in locale
streamlit run app.py
# oppure tramite script dedicato
.\scripts\dev-serve.ps1

# Avviare la Edge Function localmente (Deno)
.\scripts\dev-serve.ps1              # Terminale 1 — avvia webhook handler
.\scripts\dev-serve.ps1 -Test        # Terminale 2 — esegue test.ts
.\scripts\dev-serve.ps1 -Deploy      # Deploy su Supabase Cloud

# Eseguire i test
pytest tests/ -v --tb=short
# oppure tramite script dedicato
.\scripts\run-tests.ps1

# Avviare il FastAPI Worker in locale
uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --reload

# Avviare il worker coda manualmente (test locale)
$env:SUPABASE_URL = "..."
$env:SUPABASE_SERVICE_ROLE_KEY = "..."
python worker/run.py

# Docker compose sviluppo
docker-compose -f docker/docker-compose.yml up

# Docker compose produzione
docker-compose -f docker/docker-compose.prod.yml up -d

# Controllare errori di import
python -c "import app"

# Verificare dipendenze
pip freeze > requirements-lock.txt
```

### Variabili d'Ambiente

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `ADMIN_EMAILS` | Lista email admin (separati da virgola) | `mattiadavolio90@gmail.com` |
| `SUPABASE_URL` | URL progetto Supabase | In `st.secrets` |
| `SUPABASE_KEY` | Chiave API Supabase (anon) | In `st.secrets` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (worker + Edge Function) | In secrets Railway / GitHub |
| `OPENAI_API_KEY` | Chiave API OpenAI | In `st.secrets` |
| `WORKER_BASE_URL` | URL FastAPI Worker | `http://worker:8000` (Docker) |
| `INVOICETRONIC_API_KEY` | API Key Invoicetronic (fallback download XML) | In GitHub Secrets / Supabase Secrets |
| `INVOICETRONIC_WEBHOOK_SECRET` | Segreto firma HMAC webhook | In Supabase Secrets (Edge Function) |
| `WORKER_BATCH_SIZE` | Record da processare per ciclo worker queue | `10` |
| `WORKER_XML_RETENTION_HOURS` | Ore prima del purge GDPR dei contenuti XML | `24` |
| `WORKER_RATE_LIMIT` | Max richieste/minuto per IP al FastAPI Worker | `30` |
| `WORKER_RATE_WINDOW_SEC` | Finestra rate limit FastAPI Worker (secondi) | `60` |

### Limiti dell'Applicazione

| Limite | Valore | Configurato in |
|--------|--------|----------------|
| Max file per upload | 100 | `constants.py` |
| Max dimensione upload | 200 MB | `constants.py` + `config.toml` |
| Max dimensione P7M | 50 MB | `constants.py` |
| Max righe per utente | 100.000 | `app.py` |
| Max chiamate AI/giorno | 1.000 per ristorante | `constants.py` |
| TTL cache fatture | 120 secondi | `db_service.py` |
| TTL cache margini | 300 secondi | `margine_service.py` |
| TTL sessione cookie | 30 giorni | `app.py` |
| Lockout login | 15 minuti dopo 5 tentativi | `auth_service.py` |
| Cooldown reset password | 5 minuti | `auth_service.py` |
| Descrizione max DB | 500 caratteri | `constants.py` |
| Descrizione max AI input | 300 caratteri | Sanitizzazione `ai_service.py` |
| Cap memoria sessione | 500 righe tracking | `constants.py` |
| Batch AI | 50 articoli per chiamata | `app.py` |
| Paginazione DB | 1.000 righe per pagina | `db_service.py` |
| Log file rotation | 50 MB × 10 backup | `logger_setup.py` |

---

## 20. Integrazione Invoicetronic — Ricezione Automatica SDI

### Cos'è Invoicetronic

Invoicetronic è un servizio SaaS italiano che funge da **intermediario SDI** (Sistema di Interscambio): riceve le fatture elettroniche indirizzate al codice destinatario `7HD37X0` e le notifica via webhook HTTPS firmato.

Grazie a questa integrazione, i ristoratori che comunicano ai propri fornitori il codice destinatario `7HD37X0` **ricevono le fatture automaticamente** in OH YEAH! Hub senza dover caricare manualmente i file XML.

### Flusso Completo

```
Fornitore → SDI → Invoicetronic (codice dest. 7HD37X0)
                       │
                       │ POST HTTPS firmato (HMAC-SHA256)
                       ▼
          Supabase Edge Function: invoicetronic-webhook
          ┌────────────────────────────────────────────┐
          │ 1. Legge body RAW (necesssario per HMAC)   │
          │ 2. Verifica HMAC-SHA256 + anti-replay 5min │
          │ 3. Filtra: solo endpoint="receive"+success  │
          │ 4. GET api.invoicetronic.com/receive/{id}  │
          │    (SSRF whitelist: solo *.invoicetronic.com│
          │     redirect: 'error', timeout 3s)         │
          │ 5. Ottieni xml_file (base64) o xml_url     │
          │ 6. Estrai P.IVA destinatario dall'XML      │
          │    (CessionarioCommittente → IdCodice/CF)  │
          │ 7. Lookup P.IVA → tabella ristoranti       │
          │    → se trovata: user_id + ristorante_id   │
          │    → se non trovata: status=unknown_tenant │
          │ 8. INSERT fatture_queue (idempotente)       │
          │    ON CONFLICT (event_id) DO NOTHING       │
          │ 9. Risponde 200 SEMPRE (evita retry Storm) │
          └────────────────────────────────────────────┘
                       │ (loop continuo ogni 15 secondi)
                       ▼
          Railway service: queue-worker
          ┌────────────────────────────────────────────┐
          │ python worker/run.py                       │
          │ loop continuo 24/7                         │
          │ → purge_processed_xml_content() GDPR       │
          │ → release_stale_locks() recovery           │
          │ → claim_batch_for_processing()             │
          │   (SELECT FOR UPDATE SKIP LOCKED)          │
          │ Per ogni record:                           │
          │   → estrai_dati_da_xml() — parser esistente│
          │   → salva_fattura_processata()             │
          │   → mark_queue_item_done() + purge XML     │
          │   → se errore: schedule_retry() backoff    │
          └────────────────────────────────────────────┘
                       │
                       ▼
          public.fatture (visibile in dashboard utente)
```

### Edge Function — Sicurezza

La Edge Function implementa le seguenti misure di sicurezza OWASP:

| Misura | Implementazione |
|--------|----------------|
| **Autenticità webhook** | HMAC-SHA256 con segreto condiviso; comparazione timing-safe (`timingSafeEqual`) |
| **Anti-replay** | Rifiuta eventi con timestamp > 5 minuti dalla ricezione |
| **SSRF Prevention** | Whitelist host `*.invoicetronic.com` HTTPS only; `redirect: 'error'` su tutti i fetch |
| **DoS Protection** | XML max 10 MB; timeout API 3s; timeout download XML 2s |
| **Idempotenza** | `ON CONFLICT (event_id) DO NOTHING` — ri-invii multipli non causano duplicati |
| **Risposta neutrale** | Risponde sempre 200 dopo INSERT (evita retry aggressivi da Invoicetronic) |
| **Zero PII nei log** | Mai loggare XML, nomi, IBAN, codici fiscali o API keys |
| **Service role isolato** | Il client Supabase usa `service_role` — mai `anon key` in contesto server |

### Worker Python — Elaborazione Asincrona

Il worker (`worker/queue_processor.py`) è progettato per operare in modo robusto in ambienti multi-istanza:

#### Lock Pessimistico
```sql
-- claim_batch_for_processing() usa:
SELECT ... FOR UPDATE SKIP LOCKED
```
Più istanze del worker (es. più container Railway o fallback manuale GitHub Actions) non processano mai lo stesso record.

#### Retry con Backoff Esponenziale
I record falliti vengono ri-schedulati con `schedule_retry()`. Il numero di tentativi è tracciato in `attempt_count`. Dopo N tentativi massimi il record diventa `dead` (non viene perso, è ancora consultabile in DB).

#### GDPR Purge
Dopo 24 ore dall'elaborazione, `purge_processed_xml_content()` nullifica il campo `xml_content` (dati sensibili). L'`xml_url` viene conservata per eventuale re-download, ma l'XML grezzo non resta in DB.

#### Recovery Tenant Sconosciuto
Se una fattura arriva per una P.IVA non ancora registrata in OH YEAH! Hub, il record viene salvato con `status=unknown_tenant`. Quando il ristorante si registra con quella P.IVA, l'admin può chiamare:
```sql
SELECT resolve_unknown_tenant('01234567890');
-- Aggiorna user_id/ristorante_id e rimette in pending per rielaborazione
```

### Configurazione Invoicetronic

1. Accedere al dashboard Invoicetronic
2. **Webhooks** → aggiungi webhook URL: `https://<project>.supabase.co/functions/v1/invoicetronic-webhook`
3. Copiare il **Webhook Secret** → salvare in Supabase come `INVOICETRONIC_WEBHOOK_SECRET`
4. **API Keys** → copiare API Key → salvare in Supabase come `INVOICETRONIC_API_KEY` e, solo se vuoi un fallback manuale, in GitHub Secrets
5. Comunicare il **codice destinatario `7HD37X0`** ai fornitori del ristorante

### Test Locale Edge Function

```powershell
# Terminale 1: avvia la funzione
.\scripts\dev-serve.ps1

# Terminale 2: esegui i test automatici
.\scripts\dev-serve.ps1 -Test

# Deploy su Supabase Cloud
.\scripts\dev-serve.ps1 -Deploy
```

---

## 21. FastAPI Worker — Classificazione AI Scalabile

### Scopo

Il FastAPI Worker (`services/fastapi_worker.py`) separa la logica di classificazione AI e parsing XML dal frontend Streamlit. Questo consente di:

- **Scalare indipendentemente** il layer AI dal frontend
- **Isolare il carico** OpenAI/parsing in un container dedicato
- **Evitare timeout** di Streamlit su classificazioni batch grandi
- **Separare chiaramente** il worker interno dal flusso webhook pubblico Invoicetronic

### Modalità Operativa

```
┌─────────────────┐     WORKER_BASE_URL impostata     ┌─────────────────┐
│  Streamlit UI   │ ──── POST /api/classify ─────────▶ │  FastAPI Worker │
│ worker_client.py│ ──── POST /api/parse ────────────▶ │  (porta 8000)   │
└─────────────────┘                                    └─────────────────┘

┌────────────────────┐   POST webhook firmato    ┌────────────────────────────┐
│    Invoicetronic   │ ────────────────────────▶ │ Supabase Edge Function      │
└────────────────────┘                           │ invoicetronic-webhook       │
                                                 └────────────┬───────────────┘
                                                              │
                                                              ▼
                                                 ┌────────────────────────────┐
                                                 │ public.fatture_queue       │
                                                 └────────────┬───────────────┘
                                                              │
                                                              ▼
                                                 ┌────────────────────────────┐
                                                 │ Railway queue worker       │
                                                 │ python worker/run.py       │
                                                 └────────────────────────────┘

              WORKER_BASE_URL NON impostata (sviluppo locale)
┌─────────────────┐
│  Streamlit UI   │ ──── classifica_con_ai() locale ── (nessun worker)
│ worker_client.py│       fallback automatico
└─────────────────┘
```

Nota architetturale aggiornata:
- Il webhook pubblico Invoicetronic vive esclusivamente nella Supabase Edge Function.
- Il FastAPI worker non e' piu' un endpoint webhook pubblico.
- `worker/run.py` esegue un loop continuo su Railway come SERVICE DEDICATO (`queue-worker`) e consuma `fatture_queue` ogni 15 secondi.
- Il service worker FastAPI ha `ENABLE_INLINE_QUEUE_PROCESSOR=0`.
- `.github/workflows/queue-worker.yml` resta solo come fallback manuale.

### Endpoints REST

#### `GET /health`
```json
{"status": "ok", "version": "1.0.0"}
```
Usato da Docker healthcheck e load balancer.

#### `POST /api/classify`

Classifica una lista di descrizioni prodotti con la pipeline memoria + GPT-4o-mini.

**Request body (JSON)**:
```json
{
  "descrizioni": ["FARINA 00 KG 25", "VINO CHIANTI 0.75L"],
  "fornitori":   ["MOLINO SPADONI", "ANTINORI"],
  "iva":         [10, 22],
  "hint":        [null, "BEVANDE"],
  "user_id":     "abc-123-uuid"
}
```

**Response**:
```json
{
  "categorie": ["SECCO", "VINI"],
  "count": 2,
  "elapsed_ms": 342
}
```

- `user_id` opzionale: se fornito, precarica la memoria classificazioni dell'utente (prodotti_utente + classificazioni_manuali)
- Restituisce le categorie nello stesso ordine dell'input

#### `POST /api/parse`

Estrae le righe prodotto da una fattura XML o P7M.

**Request**: `multipart/form-data`
- `file`: file XML o P7M (max 50 MB)
- `user_id`: opzionale, per precarico memoria

**Response**:
```json
{
  "fatture": [{"descrizione": "OLIO EVO LT 5", "categoria": "OLIO E CONDIMENTI", ...}],
  "count": 12,
  "elapsed_ms": 890
}
```

### Rate Limiting Worker

Il worker implementa rate limiting in-memory per IP:

| Parametro | Default | Env Var |
|-----------|---------|---------|
| Max richieste | 30 | `WORKER_RATE_LIMIT` |
| Finestra (sec) | 60 | `WORKER_RATE_WINDOW_SEC` |

Superato il limite: risponde `HTTP 429 Too Many Requests`.

**Nota**: in Fase 4 (high-availability) il rate limiter va sostituito con Redis per supportare worker distribuiti.

### worker_client.py — Proxy con Fallback

`services/worker_client.py` è il punto di accesso unico dal frontend. Implementa:

1. **Routing condizionale**: se `WORKER_BASE_URL` è impostata, usa il worker HTTP; altrimenti usa le funzioni locali
2. **Fallback automatico**: qualsiasi errore HTTP 5xx o timeout → esegue localmente senza interrompere il flusso
3. **Non fa fallback su 4xx**: errori client (422, 429) vengono propagati
4. **Timeout configurati**: 90s per `/classify` (OpenAI può richiedere 30-60s), 30s per `/parse`

```python
# Uso in app.py (via worker_client):
from services.worker_client import classifica_via_worker, parsa_via_worker

categorie = classifica_via_worker(
    descrizioni=["PARMIGIANO 1KG"],
    user_id=st.session_state["user_data"]["id"]
)
```

### Avvio Locale (senza Docker)

```bash
# Attiva venv
.venv\Scripts\Activate.ps1

# Avvia worker
uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --reload

# Documentazione interattiva Swagger UI
http://localhost:8000/docs
http://localhost:8000/redoc
```

### Avvio con Docker Compose

```bash
# Sviluppo (con hot-reload)
docker-compose -f docker/docker-compose.yml up

# Produzione
docker-compose -f docker/docker-compose.prod.yml up -d
```

Il container worker viene definito con `command: uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2` nel `docker-compose.prod.yml`.

### Sicurezza Worker

- **Porta 8000 non esposta in produzione**: inaccessibile dall'esterno; comunicazione solo via rete Docker interna
- **CORS ristretto**: origins whitelist configurata su `https://envoicescan-ai-production.up.railway.app`
- **Nessuna autenticazione JWT sulle route**: il worker si fida della rete interna Docker (non esposto)
- **Service role key**: usa `SUPABASE_SERVICE_ROLE_KEY` (non anon key) per caricare la memoria classificazioni

---

## 22. Sistema di Notifiche In-App

### Scopo

Il sistema di notifiche (`services/notification_service.py`, ~201 righe) fornisce promemoria operativi in-app per guidare il ristoratore verso azioni correttive. Le notifiche appaiono nella dashboard principale e possono essere nascoste (dismiss) dall'utente.

### Architettura

- **Stateless**: le notifiche vengono ri-calcolate ad ogni caricamento pagina, non sono persistenti in DB
- **Dismiss persistente**: le notifiche nascoste vengono salvate in `users.dismissed_notification_ids` (JSONB) con timestamp ISO 8601
- **Scoped per ristorante**: ogni notifica ha un ID stabile che include il `ristorante_id` corrente, tramite `build_scoped_notification_id()`
- **XSS safe**: i nomi prodotto vengono sanitizzati con `html.escape()` prima dell'inserimento nel body HTML

### 6 Tipologie di Notifica

| # | Tipo | Trigger | Livello |
|---|------|---------|---------|
| 1 | Upload con file scartati | Upload con file duplicati, falliti o bloccati | ⚠️ warning |
| 2 | Alert prezzi > soglia | Upload con prodotti che superano +5% rispetto al prezzo precedente | 📈 warning |
| 3 | Ricavi mensili mancanti | Mese precedente senza fatturato compilato in `margini_mensili` | 💰 info |
| 4 | Costo personale mancante | Mese precedente senza `costo_dipendenti` compilato in `margini_mensili` | 👥 info |
| 5 | Esito upload complessivo | Riepilogo upload con conteggio per categoria (duplicati, errori, bloccati) | ⚠️ warning |
| 6 | Azione dal Controllo Prezzi | Link diretto alla pagina `3_controllo_prezzi.py` per gli alert rilevati | 📈 warning |

### Funzioni Principali

| Funzione | Scopo |
|----------|-------|
| `build_upload_outcome_notifications()` | Genera notifica per upload falliti/duplicati |
| `build_price_alert_notifications()` | Genera notifica per aumenti prezzo rilevanti |
| `build_monthly_data_notifications()` | Controlla ricavi e costi mancanti del mese precedente |
| `build_scoped_notification_id()` | Crea ID stabile nel contesto del ristorante |
| `get_dismissed_notification_ids()` | Carica le notifiche già nascoste dall'utente |
| `dismiss_notification_ids()` | Segna notifiche come viste (salvataggio su DB) |

### Schema Dismiss

```python
# users.dismissed_notification_ids (JSONB)
{
    "rist:abc-123:upload-outcome-xyz": "2026-04-09T10:30:00+00:00",
    "rist:abc-123:price-alerts-xyz": "2026-04-09T11:00:00+00:00"
}
```

### Test

18 test in `tests/test_notification_service.py`: upload outcome, price alerts, monthly data, dismiss, scoped IDs, edge cases (empty data, missing context, XSS prevention).

---

## 23. Tracking Costi AI

### Scopo

Il sistema di tracking costi AI (`services/ai_cost_service.py`, ~94 righe) registra ogni chiamata OpenAI in un ledger persistente (`ai_usage_events`) per consentire agli admin di monitorare i costi per cliente e ristorante.

### Funzionamento

1. Ogni operazione AI (classificazione batch, parsing PDF/Vision) chiama `track_ai_usage()`
2. La funzione calcola i costi in base ai token usati: **$0.15/1M input** + **$0.60/1M output** (GPT-4o-mini)
3. Il record viene inserito in `ai_usage_events` con `operation_type`, token counts, costi e metadati
4. Il Tab 6 del pannello admin aggrega questi dati per report giornalieri/mensili per cliente

### Tabella `ai_usage_events` (migration 051)

Vedi Sezione 11 — Schema Database Completo per lo schema dettagliato della tabella.

### Budget

- **Limite**: 1.000 classificazioni/giorno per ristorante
- **Alert admin**: visibile in Tab 6 del pannello admin

---

## 24. Componenti Riutilizzabili

### Scopo

La cartella `components/` contiene componenti UI estratti per ridurre la complessità delle pagine principali e favorire il riuso.

### components/category_editor.py (~958 righe)

Data editor specializzato per la gestione delle categorie nelle righe fattura:
- Rendering colonna Categoria con dropdown 29 opzioni
- Sistema raggruppamento prodotti unici (checkbox, default ON)
- Ricerca per Prodotto, Categoria o Fornitore
- Salvataggio batch con propagazione in memoria locale/globale
- Icone fonte classificazione: 📚 Memoria, 🧠 AI, ✋ Manuale

### components/dashboard_renderer.py (~964 righe)

Rendering KPI e grafici per la dashboard principale:
- 6 KPI box (Spesa Totale, F&B, Fornitori, Spese Generali, Media Mensile)
- Grafici Plotly: pivot categorie, pivot fornitori
- Filtro temporale e selezione vista
- Export Excel con ordinamento selezionabile

### utils/app_controllers.py (~1.555 righe)

Layer controller estratto da `app.py` per separare logica di business da rendering UI:
- Controller upload: orchestrazione parsing, deduplicazione, classificazione AI
- Controller filtro temporale: costruzione query per periodo selezionato
- Controller gestione fatture: eliminazione singola/massiva, verifica post-delete
- Controller classificazione AI: recovery pipeline per righe "Da Classificare"

---

## 25. Funzionalità Aggiunte in v5.4

### 25.1 Tabella `categorie` Centralizzata

Una nuova tabella DB `categorie` (31 righe) specchia le categorie definite in `config/constants.py`. Consente join diretti, foreign key constraint e gestione centralizzata senza duplicazioni in codice. Migration: `supabase/migrations/20260501000000_create_categorie_table.sql`.

### 25.2 Soft-Delete Fatture (Cestino)

Le fatture eliminate non vengono più rimosse immediatamente ma spostate nel "cestino" tramite la colonna `fatture.deleted_at`:

- **Eliminazione normale**: imposta `deleted_at = NOW()`
- **Cestino 30 giorni**: fatture nel cestino visibili in una vista separata
- **Pulizia definitiva**: il job `fatture_retention_2y` elimina definitivamente le fatture con `deleted_at IS NOT NULL` dopo 30 gg
- **Retention 2 anni**: fatture attive più vecchie di 2 anni eliminate automaticamente dallo stesso job
- **Tracking**: tabella `system_maintenance_status` registra ogni esecuzione del job (ultima data, righe eliminate, eventuale errore)
- **Query**: tutte le query dell'app filtrano `deleted_at IS NULL` (indice parziale `idx_fatture_active`)

### 25.3 Custom Tags

Sistema di tagging personalizzato per aggregare prodotti equivalenti all'interno dello stesso ristorante:

| Componente | Descrizione |
|-----------|-------------|
| `custom_tags` | Tag con nome, emoji e colore HEX per utente + ristorante |
| `custom_tag_prodotti` | Associazione tag ↔ descrizione fattura con `descrizione_key` normalizzata |
| `normalize_custom_tag_key()` | Funzione SQL: trim + uppercase + collapse spaces |
| Trigger `trg_custom_tag_prodotti_prepare_row` | Auto-normalizza `descrizione_key` e allinea `user_id/ristorante_id` al tag padre |

**Esempio d'uso**: creare un tag "Formaggi freschi" e associarvi tutte le varianti di descrizione ("MOZZARELLA", "MOZZARELLA DI BUFALA", "FIOR DI LATTE") per aggregarle in analisi personalizzate.

### 25.4 Cache Versioning Cross-Process

Soluzione al problema di cache obsoleta in deploy multi-worker:

| Elemento | Funzione |
|----------|----------|
| `cache_version` | Tabella con 1 riga per chiave (`memoria_classificazione`) |
| `fn_bump_cache_version()` | SECURITY DEFINER: incrementa `version` ad ogni modifica |
| Triggers su `prodotti_utente`, `prodotti_master`, `classificazioni_manuali` | Chiamano `fn_bump_cache_version()` dopo ogni INSERT/UPDATE/DELETE |
| **Comportamento client** | Legge `version` ogni ~30s; se diversa dall'ultima vista, ricarica la cache locale |

**Beneficio**: il frontend Streamlit e il worker Railway condividono sempre la stessa visione aggiornata della memoria classificazione.

### 25.5 Category Change Log

Tabella `category_change_log` (append-only) per audit forense delle modifiche categoria:

| Colonna chiave | Contenuto |
|----------------|-----------|
| `changed_at` | Timestamp modifica |
| `old_categoria` / `new_categoria` | Prima e dopo la modifica |
| `actor_user_id` / `actor_email` | Chi ha modificato |
| `source` | `db_trigger` / `api` / `manual` |
| `batch_id` | UUID per raggruppare modifiche batch |

Utilizzato per analisi retroattive, debugging classificazione e confronto delta preciso.

### 25.6 Nuove Colonne su `fatture`

| Colonna | Scopo |
|---------|-------|
| `data_consegna` | Estratta da `DatiDDT` o regex nella descrizione (solo fatture TD24); NULL per le altre |
| `data_competenza` | Data competenza gestionale per reportistica interna (non sostituisce la data documento fiscale) |
| `totale_documento` | `ImportoTotaleDocumento` dall'header XML |
| `totale_imponibile` | Somma `ImponibileImporto` da `DatiRiepilogo` |
| `totale_iva` | Somma `Imposta` da `DatiRiepilogo` |

### 25.7 Soglia Alert Prezzi Personalizzabile

La colonna `users.price_alert_threshold` (default 5.0, range 0–100) consente a ogni utente di impostare la propria soglia percentuale di variazione prezzi in `3_controllo_prezzi.py`. Prima era hardcoded a 5% per tutti.

### 25.8 Tool `check_migrations.py`

`tools/check_migrations.py` — script di verifica che tutte le migration legacy (001–068) abbiano correttamente creato gli oggetti DB attesi:
- **65 check** su tabelle, colonne, funzioni RPC e tabelle di sistema
- Usa `try/select + APIError PGRST202` come discriminante "oggetto mancante"
- Eseguibile con: `python tools/check_migrations.py`
- Risultato atteso: **65/65 OK** (verificato al 1 Maggio 2026)

---

*Documento generato automaticamente dall'analisi completa del codice sorgente.*
*Versione 5.4 — 1 Maggio 2026*
*Per aggiornamenti, modifiche o domande: mattiadavolio90@gmail.com*
