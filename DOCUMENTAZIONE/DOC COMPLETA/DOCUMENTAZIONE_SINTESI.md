# OH YEAH! Hub — Documentazione Sintetica

**Sistema di Analisi Fatture e Controllo Costi per la Ristorazione**

Versione: 5.1 | Ultimo aggiornamento: 9 Aprile 2026 | Autore: Mattia D'Avolio  
Repository: `mattiadavolio90-crypto/envoicescan-ai` (privato) | URL: https://ohyeah.streamlit.app/

---

## 1. Panoramica

OH YEAH! Hub è una piattaforma SaaS web-based per ristoratori italiani che analizza, categorizza e controlla i costi dalle fatture elettroniche dei fornitori.

**Funzionalità principali:**
- Caricamento fatture (XML/FatturaPA, P7M, PDF, JPG/PNG)
- Ricezione automatica fatture via Invoicetronic (codice dest. `7HD37X0`)
- Classificazione automatica AI in 29 categorie merceologiche (600+ keyword + GPT-4o-mini)
- Dashboard KPI, grafici Plotly, pivot mensili per categoria e fornitore
- Notifiche in-app per upload, prezzi, dati mancanti (6 tipologie)
- Calcolo Margine Operativo Lordo (MOL) con centri di produzione
- Gestione multi-ristorante (un account, più locali)
- Controllo variazioni prezzi, sconti, note di credito
- Export Excel, Privacy Policy GDPR v3.2, Terms of Service

**Pubblico target:** ristoratori, piccole catene (2–5 locali), consulenti F&B

---

## 2. Stack Tecnologico

| Componente | Tecnologia | Note |
|-----------|-----------|------|
| Linguaggio | Python 3.12.8 | Type hints, f-strings |
| Framework web | Streamlit | SPA con auto-reload |
| Database | Supabase (PostgreSQL 15) | EU Frankfurt, RLS attivo |
| AI/ML | OpenAI GPT-4o-mini | Batch 50 articoli, ~0.15$/1M token |
| Email | Brevo SMTP API v3 | 300 email/giorno, free tier |
| Password hashing | Argon2id | m=65536, parametri default libreria (OWASP) |
| CI/CD | GitHub Actions | Uptime check ogni 5 min + Worker coda ogni 15 min |
| Deploy frontend | Streamlit Community Cloud | Auto-deploy da branch `main` |
| Deploy worker | Railway | FastAPI Worker Docker (classificazione AI scalabile) |
| SDI Intermediario | Invoicetronic | Ricezione fatture SDI, codice dest. `7HD37X0` |
| Cookie | extra-streamlit-components | Secure=True, SameSite=Strict (no HttpOnly) |

**Pacchetti chiave:** `supabase`, `openai`, `argon2-cffi`, `pandas`, `plotly`, `openpyxl`, `xmltodict`, `asn1crypto`, `PyMuPDF`, `tenacity`, `charset-normalizer`, `requests`

---

## 3. Struttura del Codice Sorgente

```
Oh Yeah! Hub/
├── app.py                    # Entry point (~2.492 righe): auth, dashboard, upload, AI, export
├── pages/
│   ├── admin.py              # Pannello admin 6 tab (~4.470 righe)
│   ├── 1_calcolo_margine.py  # MOL e centri di produzione (~1.604 righe)
│   ├── 2_foodcost.py         # Foodcost, ricette, ingredienti, diario (~2.139 righe)
│   ├── 3_controllo_prezzi.py # Variazioni prezzi, sconti, NC (~586 righe)
│   ├── gestione_account.py   # Cambio password, export GDPR (~457 righe)
│   └── privacy_policy.py     # Privacy Policy v3.2 + Terms of Service
├── services/
│   ├── ai_service.py         # Classificazione AI + memoria 3 livelli (~1.908 righe)
│   ├── ai_cost_service.py    # Tracking costi OpenAI per ristorante (~94 righe)
│   ├── auth_service.py       # Login, reset, rate limiting, GDPR (~1.143 righe)
│   ├── invoice_service.py    # Parsing XML/P7M/PDF/Vision (~1.272 righe)
│   ├── db_service.py         # Query Supabase + cache + paginazione (~977 righe)
│   ├── margine_service.py    # Calcoli MOL + export Excel (~1.126 righe)
│   ├── upload_handler.py     # Upload, batch, deduplicazione (~882 righe)
│   ├── email_service.py      # Brevo SMTP con retry (~106 righe)
│   ├── notification_service.py # Notifiche in-app 6 tipologie (~201 righe)
│   ├── fastapi_worker.py     # FastAPI Worker REST API (~649 righe)
│   └── worker_client.py      # Proxy Streamlit → Worker con fallback (~127 righe)
├── components/                # Componenti UI riutilizzabili
│   ├── category_editor.py    # Data editor categorie (~958 righe)
│   └── dashboard_renderer.py # KPI, grafici, pivot dashboard (~964 righe)
├── worker/                    # Worker asincrono fatture_queue
│   ├── run.py                # Entry point GitHub Actions
│   └── queue_processor.py    # Elaborazione coda Invoicetronic (~440 righe)
├── utils/                    # formatters, text_utils, validation, piva_validator,
│                             # sidebar_helper, ristorante_helper, period_helper,
│                             # ui_helpers, page_setup, app_controllers (~1.555 righe)
├── config/
│   ├── constants.py          # 29 categorie, 600+ keyword, regex, KPI soglie
│   ├── logger_setup.py       # RotatingFileHandler (50 MB × 10 backup)
│   └── prompt_ai_potenziato.py # Prompt GPT con esempi per 29 categorie
├── supabase/                  # Edge Function invoicetronic-webhook (Deno/TypeScript)
├── static/                   # branding.css, common.css, layout.css
├── tests/                    # 194 test automatici pytest (11 moduli)
├── migrations/               # 58 SQL migrations numerate (001→053)
├── docker/                   # Dockerfile, docker-compose.yml, docker-compose.prod.yml
├── scripts/                  # comandi.ps1, dev-serve.ps1, run-tests.ps1
├── .github/workflows/        # uptime_check.yml, queue-worker.yml
├── .streamlit/               # config.toml, secrets.toml (non versionato)
├── railway.toml              # Configurazione deploy Railway
├── requirements.txt / requirements-lock.txt (100 pacchetti freezati)
└── DOCUMENTAZIONE/
```

---

## 4. Funzionalità per Pagina

### app.py — Dashboard Principale
- **6 KPI**: Spesa Totale, F&B, Fornitori F&B, Fornitori Spese, Spesa Generali, Media Mensile
- **3 sezioni**: Dettaglio Articoli (data editor interattivo) | Categorie (pivot mensile) | Fornitori (pivot mensile)
- **Filtro temporale**: Mese corrente/precedente, Trimestre, Semestre, Anno, Personalizzato
- **Upload**: fino a 100 file / 200 MB; formati XML, P7M, PDF, JPG, PNG; validazione P.IVA; deduplicazione; progress bar
- **Bottone AI**: pipeline completa con banner animato e percentuale in tempo reale
- **Gestione fatture**: eliminazione singola o massiva, verifica post-eliminazione
- **Export Excel**: con ordinamento selezionabile

### pages/1_calcolo_margine.py — MOL
- Tabella ricavi/costi 12 mesi (Input manuale + dati automatici da fatture)
- Calcolo: Fatturato Netto, Food Cost %, 1° Margine, MOL % con soglie colorate
- Centri di produzione: FOOD, BAR, ALCOLICI, DOLCI — fatturato mensile + food cost %
- Grafici Plotly trend temporale, export Excel

### pages/2_foodcost.py — Foodcost, Ricette e Diario
- **Tab Analisi**: KPI menu, distribuzione categorie, margine netto per piatto
- **Tab Lab Ricette**: CRUD completo, ingredienti da 3 fonti (fatture, workspace, semilavorati), calcolo foodcost automatico, ricette annidate
- **Tab Diario**: note operative giornaliere (CRUD), sanitizzazione XSS
- **Tab Export**: Excel con ricette espanse e foodcost

### pages/3_controllo_prezzi.py — Prezzi
- Variazioni prezzo: storico ultimi 5 prezzi, alert soglia configurabile (default 5%)
- Sconti e omaggi: KPI totale risparmiato, valore stimato omaggi
- Note di credito (TD04): KPI, ricerca, export Excel

### pages/admin.py — Pannello Admin (solo ADMIN_EMAILS)
- **Tab 1 — Clienti**: lista, creazione GDPR (token attivazione email), impersonazione, attivazione/disattivazione, pagine abilitate
- **Tab 2 — Review €0**: classifica righe con prezzo=0 come prodotto o dicitura → `classificazioni_manuali`
- **Tab 3 — Memoria AI**: data editor `prodotti_master`, propagazione modifiche a tutte le fatture
- **Tab 4 — Memoria Clienti**: visualizzazione `prodotti_utente` per cliente
- **Tab 5 — Integrità DB**: conteggi, verifica NULL, fix automatici
- **Tab 6 — Costi AI**: tracking OpenAI per cliente/ristorante, aggregazione giornaliera/mensile

---

## 5. Pipeline di Classificazione AI

**Priorità (dall'alto al basso):**
1. Memoria Admin (`classificazioni_manuali`) — priorità massima, globale
2. Memoria Locale (`prodotti_utente`) — per singolo cliente
3. Memoria Globale (`prodotti_master`) — per tutti i clienti
4. Dizionario keyword (`constants.py`) — 600+ regole deterministiche
5. GPT-4o-mini — batch 50 articoli, retry con backoff esponenziale

**Cache in-memory** thread-safe (`threading.Lock()`), caricamento lazy, invalidazione esplicita.  
**Quarantena**: descrizioni con prezzo=€0 classificate ma non salvate in memoria globale.  
**Budget**: 1.000 classificazioni/giorno per ristorante.

### 29 Categorie Merceologiche

**Food & Beverage (25):** ACQUA, AMARI/LIQUORI, BEVANDE, BIRRE, CAFFÈ E THE, CARNE, DISTILLATI, FRUTTA, GELATI, LATTICINI, OLIO E CONDIMENTI, PASTICCERIA, PESCE, PRODOTTI DA FORNO, SALSE E CREME, SALUMI, SCATOLAME E CONSERVE, SECCO, SHOP, SPEZIE E AROMI, SUSHI VARIE, UOVA, VARIE BAR, VERDURE, VINI

**Materiali (1):** MATERIALE DI CONSUMO

**Spese Operative (3):** SERVIZI E CONSULENZE, UTENZE E LOCALI, MANUTENZIONE E ATTREZZATURE

**Centri di produzione:** FOOD | BAR | ALCOLICI | DOLCI | MATERIALE DI CONSUMO | SHOP

---

## 6. Autenticazione e Sicurezza

### Flusso Login
1. Check cookie `session_token` (30 giorni TTL) → login automatico
2. Form email + password → rate limit check → verifica Argon2id → genera token + cookie

### Specifiche tecniche auth
| Elemento | Valore |
|----------|--------|
| Password hashing | Argon2id m=65536, parametri default libreria |
| Migrazione legacy | Auto da SHA256 al primo login |
| Password policy | Min 10 char, 3/4 complessità, blacklist 24+ password, no dati personali |
| Rate limiting login | 5 tentativi → 15 min lockout (persistente su DB `login_attempts`) |
| Rate limiting reset | 1 richiesta / 5 min (in-memory thread-safe) |
| Session cookie | UUID4, Secure=True, SameSite=Strict, 30 giorni |
| Inattività sessione | Auto-logout dopo 8 ore (`SESSION_INACTIVITY_HOURS = 8`) |
| Token invalido | Sessione revocata immediatamente se token non in DB |
| Reset token | `secrets.token_urlsafe(32)` — 256 bit entropia, verifica HMAC constant-time |
| Reset scadenza | 15 minuti |

### Misure di sicurezza complete

| Categoria | Misura | Dettaglio |
|-----------|--------|-----------|
| Autenticazione | Argon2id | m=65536, parametri default libreria (OWASP) |
| Sessioni | Token UUID4 + Cookie 30gg | Auto-logout inattività 8h, invalidazione su token mancante |
| Cookie | Secure + SameSite=Strict | `extra-streamlit-components` non supporta HttpOnly |
| Rate Limiting | Login DB + Reset in-memory | Tabella `login_attempts`; dict thread-safe |
| IDOR | `.eq('userid', user_id)` su UPDATE/DELETE | Ogni scrittura workspace include filtro owner |
| XSS | `html.escape()` | Su tutti gli output user-generated in HTML (sidebar, admin, categorie, P.IVA) |
| Path Traversal | Sanitizzazione percorsi | `nome_file` e `File_Origine` sanificati |
| Worker API | Porta 8000 interna | Non esposta in produzione (`docker-compose.prod.yml`) |
| Input Validation | Sanitizzazione AI | Control char removal + 300 char truncation |
| CSRF Protection | `enableXsrfProtection = true` | Streamlit nativo |
| SQL Injection | Parametrized queries | Supabase client non permette raw SQL |
| File Upload | Magic bytes validation | Verifica header + size limits (100 file, 200 MB, 50 MB P7M) |
| Error Handling | `showErrorDetails = false` | Mai esporre stack trace in produzione |
| Logging | No PII nei log | Email troncate, password mai loggate |
| CORS | `enableCORS = false` | Disabilitato |
| Reset Token | `secrets.token_urlsafe(32)` | 256 bit entropia |
| Secrets | Streamlit Secrets | Mai hardcoded nel codice |
| Dependencies | `requirements-lock.txt` | 100 pacchetti freezati (supply chain security) |

---

## 7. Parsing Fatture Elettroniche

| Formato | Metodo | Note |
|---------|--------|------|
| XML (FatturaPA) | `xmltodict` | Auto-detect encoding (UTF-8, cp1252, GB2312, GBK) |
| P7M (CAdES) | `asn1crypto` + fallback pattern | Max 50 MB |
| PDF | `PyMuPDF` + OpenAI Vision | Vision come fallback se testo insufficiente |
| JPG/PNG | OpenAI Vision | Base64 + prompt estrazione |

**Tipi documento gestiti:** TD01 (fattura), TD02 (acconto), TD04 (nota credito — importi negativi), TD05, TD06, TD16–TD27 (autofatture)

**Pipeline XML:** lettura → encoding → parse → metadati → validazione P.IVA → estrazione righe (descrizione, qtà, prezzo, IVA, sconto, UM, codice) → filtro diciture → calcolo prezzo effettivo → categorizzazione cache → salvataggio batch

---

## 8. Multi-Tenancy e Multi-Ristorante

- Ogni query include `.eq("user_id", user_id)` + `.eq("ristorante_id", ristorante_id)`
- RLS attivo su Supabase come secondo livello di isolamento
- Dropdown ristorante visibile con 2+ locali; persistenza su `users.ultimo_ristorante_id`
- Admin vede tutti i ristoranti di tutti i clienti
- Utenti legacy: creazione automatica record `ristoranti` se mancante

---

## 9. Schema Database (tabelle principali)

| Tabella | Scopo |
|---------|-------|
| `users` | Utenti: email, password_hash, session_token, pagine_abilitate, login/logout timestamps |
| `ristoranti` | Locali: user_id, nome, P.IVA, attivo |
| `fatture` | Righe fattura: user_id, ristorante_id, fornitore, descrizione, prezzo, categoria, tipo_documento |
| `prodotti_master` | Memoria globale AI: descrizione→categoria, verified, volte_visto |
| `prodotti_utente` | Memoria locale per cliente: UNIQUE(user_id, descrizione) |
| `classificazioni_manuali` | Override admin: descrizione→categoria, flag `is_dicitura` |
| `margini_mensili` | MOL mensile: fatturato manuale + costi auto + KPI calcolati + centri produzione |
| `login_attempts` | Rate limiting persistente: email, attempted_at, success |
| `upload_events` | Log upload: file, status, rows_parsed/saved/excluded, error details |
| `ricette` | Ricette: ingredienti JSON, foodcost, prezzo_vendita |
| `ingredienti_workspace` | Ingredienti manuali: nome, prezzo_per_um, um |
| `note_diario` | Note operative giornaliere per ristorante |
| `review_confirmed/ignored` | Righe confermate/ignorate dopo review admin €0 |
| `fatture_queue` | Buffer webhook Invoicetronic (pending → processing → done) |
| `brand_ambigui` | Tracking brand multi-categoria (machine learning) |
| `ai_usage_events` | Ledger costi OpenAI: token, costi per operazione AI |

**58 migrazioni SQL** (001→053): aggiunta colonne, nuove tabelle, RLS policy, stored procedure RPC, indici performance, fix retroattivi, hardening sicurezza.

---

## 10. Testing

- **194 test automatici** (pytest) — tutti PASSED
- 11 moduli: `test_trial` (39), `test_text_utils` (30), `test_piva_validator` (18), `test_notification_service` (18), `test_ai_service` (16), `test_validation` (14), `test_constants` (13), `test_db_service` (12), `test_auth_service` (12), `test_invoice_service` (11), `test_formatters` (11)
- Mock completi per Supabase e OpenAI (nessun servizio esterno toccato)

```bash
pytest tests/ -v --tb=short          # tutti i test
.\scripts\run-tests.ps1               # via script
pytest tests/ --cov=services --cov=utils --cov-report=html  # con coverage
```

---

## 11. Deploy e Infrastruttura

### Streamlit Community Cloud
- Branch `main` → deploy automatico | URL: `https://ohyeah.streamlit.app/` | Python 3.12 | Region US
- Secrets via `st.secrets` (mai nel codice): `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`, `brevo.*`

### Supabase
- Free Tier, EU Frankfurt, PostgreSQL 15, RLS attivo
- Backup automatici giornalieri | Limite: 500 MB storage, pausa dopo 7 gg inattività

### Docker (cartella `docker/`)
| File | Descrizione |
|------|-------------|
| `Dockerfile` | Build immagine app Streamlit e worker FastAPI |
| `docker-compose.yml` | Stack sviluppo locale |
| `docker-compose.prod.yml` | Stack produzione — porta 8000 worker **non esposta** pubblicamente |
| `docker-entrypoint.sh` | Script avvio container |

### Railway — Deploy FastAPI Worker
- Docker image da `docker/Dockerfile` (configurato in `railway.toml`)
- Due servizi: `ohyeah` (Streamlit) + `worker` (FastAPI)
- Comunicazione interna: `WORKER_BASE_URL` → `http://worker:8000`

---

## 12. Integrazione Invoicetronic — Ricezione Automatica SDI

- **Flusso**: SDI → Invoicetronic → POST webhook → Supabase Edge Function (Deno/TypeScript) → `fatture_queue`
- **Sicurezza webhook**: HMAC-SHA256, anti-replay, verifica payload
- **Worker coda**: GitHub Actions ogni 15 min → `worker/queue_processor.py` → parsing + classificazione
- **GDPR**: XML raw purificato dopo 24h tramite RPC `purge_processed_xml_content()`
- **Codice destinatario SDI**: `7HD37X0`

---

## 13. Sistema di Notifiche In-App

6 tipologie di notifica (`services/notification_service.py`, ~201 righe):

| Tipo | Trigger |
|------|---------|
| Upload con file scartati | File duplicati, falliti o bloccati durante upload |
| Alert prezzi > +5% | Prodotti con aumento prezzo sopra soglia |
| Ricavi mensili mancanti | Mese precedente senza fatturato in `margini_mensili` |
| Costo personale mancante | Mese precedente senza `costo_dipendenti` |
| Esito upload complessivo | Riepilogo per categoria (duplicati, errori) |
| Azione Controllo Prezzi | Link diretto a `3_controllo_prezzi.py` |

- **Dismiss persistente**: `users.dismissed_notification_ids` (JSONB) con timestamp
- **Scoped per ristorante**: ID stabile con `ristorante_id`
- **XSS safe**: `html.escape()` su nomi prodotto

---

## 14. Tracking Costi AI

- `services/ai_cost_service.py` registra ogni chiamata OpenAI in `ai_usage_events`
- Costi: $0.15/1M input + $0.60/1M output (GPT-4o-mini)
- Tab 6 pannello admin: report giornalieri/mensili per cliente/ristorante
- Budget: 1.000 classificazioni/giorno per ristorante

---

*Documento sintetico v5.1 — 9 Aprile 2026*
*Per la documentazione completa, vedere `DOCUMENTAZIONE_COMPLETA.md`*

---

## 12. Monitoraggio

- **GitHub Actions** `uptime_check.yml`: curl ogni 5 minuti su `https://ohyeah.streamlit.app/`; se HTTP ≠ 200 → email alert via Brevo
- **Logging applicativo**: `RotatingFileHandler`, 50 MB × 10 backup (~550 MB max), livello INFO, logger modulari per ogni componente (`app`, `ai`, `auth`, `invoice`, `db`, `admin`, `email`, `margine_service`)

---

## 13. Compliance GDPR

- **Privacy Policy + ToS**: pagina in-app (`privacy_policy.py`), versione HTML (`PrivacyPolicy_CookiePolicy_OHHYEAH.html`)
- **Data retention**: fatture nel DB finché l'utente le elimina esplicitamente
- **Diritto all'oblio**: l'admin può eliminare completamente un account (tutti i dati correlati)
- **Portabilità**: export JSON dati da `gestione_account.py` (Art. 15 GDPR)
- **Creazione client GDPR**: l'admin non conosce mai la password del cliente (token attivazione via email)
- **Nota legale**: "Non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014"

---

## 14. Limiti Tecnici

| Limite | Valore |
|--------|--------|
| Max file per upload | 100 file / 200 MB totale / 50 MB per P7M |
| Max righe per utente | 100.000 |
| Chiamate AI/giorno | 1.000 per ristorante |
| Batch AI | 50 articoli per chiamata |
| TTL cache fatture | 120 s |
| TTL cache margini | 300 s |
| TTL sessione cookie | 30 giorni |
| Inattività sessione | 8 ore |
| Lockout login | 15 min dopo 5 tentativi |
| Cooldown reset password | 5 minuti |
| Descrizione max DB | 500 caratteri |
| Descrizione max AI | 300 caratteri (sanitizzazione) |
| Paginazione DB | 1.000 righe per pagina |
| Log rotation | 50 MB × 10 backup |

---

## 15. Troubleshooting Rapido

| Problema | Causa / Soluzione |
|----------|-------------------|
| Pagina bianca | Supabase in pausa (free tier 7gg) → riattivare dal pannello Supabase |
| Fattura scartata "P.IVA non corrispondente" | P.IVA cedente ≠ ristorante attivo; cambiare ristorante attivo |
| Fattura scartata "già caricata" | Deduplicazione su `file_origine + user_id + ristorante_id` |
| Celle bianche in colonna Categoria | `valida_categoria()` forzato a "Da Classificare" automaticamente |
| AI classifica male | Correggere manualmente → il sistema impara (memoria locale/globale) |
| Sessione scaduta | Token 30 gg o auto-logout 8h inattività; svuotare cache browser |
| Encoding non supportato | `charset-normalizer` rileva automaticamente; raramente fallisce |

---

## 16. Comandi Sviluppo

```bash
streamlit run app.py          # avvia in locale (porta 8501)
.\scripts\dev-serve.ps1       # avvia con script
pytest tests/ -v --tb=short   # esegui test
.\scripts\run-tests.ps1       # test via script
python -c "import app"        # verifica import
```

---

*Documentazione sintetica — per il dettaglio completo vedere `DOCUMENTAZIONE_COMPLETA.md`*  
*Contatti: mattiadavolio90@gmail.com*
