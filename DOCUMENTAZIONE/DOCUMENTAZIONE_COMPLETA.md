# OH YEAH! — Documentazione Completa

**Sistema di Analisi Fatture e Controllo Costi per la Ristorazione**

Versione: 4.1  
Ultimo aggiornamento: Marzo 2026  
Autore: Mattia D'Avolio  
Repository: `mattiadavolio90-crypto/envoicescan-ai` (privato)  
URL Produzione: https://ohyeah.streamlit.app/

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

---

## 1. Panoramica del Progetto

### Cos'è OH YEAH!

OH YEAH! è una piattaforma SaaS web-based progettata specificamente per ristoratori italiani che necessitano di analizzare, categorizzare e controllare i costi derivanti dalle fatture elettroniche dei propri fornitori.

L'applicazione consente di:

- **Caricare fatture elettroniche** nei formati XML (FatturaPA), P7M (firma digitale CAdES), PDF e immagini (JPG/PNG)
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

I ristoratori italiani ricevono decine/centinaia di fatture elettroniche XML al mese dai fornitori. Queste fatture contengono righe di prodotti con descrizioni spesso abbreviate, non standardizzate e difficili da classificare. OH YEAH! automatizza completamente l'analisi di queste fatture, trasformando dati grezzi XML in informazioni azionabili per il controllo dei costi.

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
| Modello AI | OpenAI GPT-4o-mini |
| Copertura test automatici | 172 test, 10 moduli di test |
| Tempo medio classificazione | < 5 secondi per 50 prodotti (batch) |

---

## 3. Architettura del Sistema

### Diagramma di Flusso Generale

```
┌─────────────────────────────────────────────────────────┐
│                     UTENTE (Browser)                     │
│                  https://ohyeah.streamlit.app            │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
                       ▼
┌─────────────────────────────────────────────────────────┐
│               STREAMLIT CLOUD (Frontend + Backend)       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │  app.py   │ │ admin.py │ │calcolo_  │ │workspace │  │
│  │  (4080L)  │ │  (6 tab) │ │margine   │ │  .py     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       │             │            │             │         │
│  ┌────▼─────────────▼────────────▼─────────────▼────┐   │
│  │              Service Layer                        │   │
│  │  ai_service │ auth_service │ invoice │ db │ email │   │
│  └────┬────────────┬───────────────┬────────────────┘   │
└───────┼────────────┼───────────────┼────────────────────┘
        │            │               │
        ▼            ▼               ▼
┌──────────┐  ┌──────────┐   ┌──────────┐
│ OpenAI   │  │ Supabase │   │  Brevo   │
│ GPT-4o-  │  │ PostgreSQL│   │  SMTP    │
│  mini    │  │  + RLS   │   │  API v3  │
└──────────┘  └──────────┘   └──────────┘
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
| Framework Web | Streamlit | latest | SPA con auto-reload |
| Database | Supabase (PostgreSQL 15) | Free tier | EU region, Row Level Security |
| AI/ML | OpenAI API | GPT-4o-mini | Batch classification, ~0.15$/1M token |
| Email | Brevo SMTP API v3 | Free tier | 300 email/giorno |
| Hashing | Argon2id | m=65536, t=3, p=4 | OWASP raccomandato 2026 |
| CI/CD | GitHub Actions | — | Uptime check ogni 5 minuti |
| Deploy | Streamlit Community Cloud | Free tier | Auto-deploy da branch main |

### Dipendenze Python Principali (91 pacchetti lockati)

| Pacchetto | Uso |
|-----------|-----|
| `streamlit` | Framework web UI |
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
| `requests` | HTTP client per Brevo API |

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
FCI_PROJECT/
│
├── app.py                          # Entry point principale (~1.651 righe)
│                                   # - Autenticazione e gestione sessioni
│                                   # - Dashboard con KPI, grafici, pivot
│                                   # - Pipeline classificazione AI
│                                   # - Upload e parsing fatture
│                                   # - Data editor con salvataggio
│                                   # - Gestione fatture (elimina, export)
│
├── pages/                          # Pagine multi-page Streamlit
│   ├── admin.py                    # Pannello admin (6 tab, ~3.650 righe)
│   ├── 1_calcolo_margine.py        # Calcolo MOL e centri di produzione (~1.546 righe)
│   ├── 2_workspace.py              # Workspace ricette, ingredienti, diario (~2.125 righe)
│   ├── 3_controllo_prezzi.py       # Variazioni prezzi, sconti, note di credito (~584 righe)
│   ├── gestione_account.py         # Cambio password e impostazioni (~384 righe)
│   └── privacy_policy.py           # Privacy Policy + Terms of Service
│
├── services/                       # Business logic layer
│   ├── __init__.py                 # get_supabase_client() singleton
│   ├── ai_service.py              # Classificazione AI + memoria 3 livelli (~980 righe)
│   ├── auth_service.py            # Login, password, reset, GDPR, rate limiting DB (~841 righe)
│   ├── invoice_service.py         # Parsing XML/P7M/PDF/Vision (~1.246 righe)
│   ├── db_service.py              # Query Supabase + cache + paginazione (~972 righe)
│   ├── margine_service.py         # Calcoli MOL + export Excel (~1.126 righe)
│   ├── upload_handler.py          # Gestione upload file, batch, deduplicazione (~620 righe)
│   └── email_service.py           # Brevo SMTP API con retry (~106 righe)
│
├── utils/                          # Utility e helper functions
│   ├── formatters.py              # Formattazione numeri, base64, categorie DB
│   ├── text_utils.py              # Normalizzazione testo, estrazione fornitore
│   ├── validation.py              # Validazione diciture, integrità fatture
│   ├── piva_validator.py          # Validazione P.IVA italiana (algoritmo Luhn)
│   ├── sidebar_helper.py          # Sidebar condivisa + header OH YEAH!
│   ├── ristorante_helper.py       # Helper multi-ristorante
│   ├── period_helper.py           # Filtri temporali (mese, trimestre, anno)
│   ├── ui_helpers.py              # CSS loader, hide sidebar
│   └── page_setup.py             # Check pagine abilitate per utente
│
├── config/                         # Configurazione centralizzata
│   ├── constants.py               # 29 categorie, 600+ keyword, regex, KPI soglie
│   ├── logger_setup.py            # RotatingFileHandler (50MB, 10 backup)
│   └── prompt_ai_potenziato.py    # Prompt GPT per classificazione (con esempi)
│
├── static/                         # Asset statici
│   ├── branding.css               # Logo e branding OH YEAH!
│   ├── common.css                 # Stili condivisi (bottoni, KPI card)
│   └── layout.css                 # Layout responsive
│
├── tests/                          # Test automatici (pytest)
│   ├── conftest.py                # Fixtures condivise (mock Supabase, OpenAI)
│   ├── test_ai_service.py         # Test classificazione AI
│   ├── test_auth_service.py       # Test autenticazione e rate limiting
│   ├── test_constants.py          # Test integrità categorie
│   ├── test_formatters.py         # Test formattazione
│   ├── test_invoice_service.py    # Test parsing fatture
│   ├── test_piva_validator.py     # Test validazione P.IVA
│   ├── test_text_utils.py         # Test normalizzazione testo
│   └── test_validation.py         # Test validazione diciture
│
├── migrations/                     # SQL migrations manuali (44 file)
│   ├── 001_add_reset_columns.sql
│   ├── ...
│   └── 044_create_login_attempts.sql
│
├── .github/workflows/
│   └── uptime_check.yml           # Uptime monitoring ogni 5 minuti
│
├── .streamlit/
│   ├── config.toml                # Configurazione server Streamlit
│   └── secrets.toml               # Secrets (non versionato)
│
├── requirements.txt               # Dipendenze principali
├── requirements-lock.txt          # 91 pacchetti con versioni freezate
├── pytest.ini                     # Configurazione pytest
└── README.md                      # README sintetico
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

### 6.2 Bottone "🧠 Avvia AI per Categorizzare"

Il bottone triggerà la pipeline completa di classificazione AI:

1. **Pre-step Memoria**: Check cache in-memory (admin > locale > globale)
2. **Step 1 Dizionario**: 600+ keyword matches deterministici
3. **Step 2 AI Batch**: OpenAI GPT-4o-mini per i restanti (50 articoli/call)
4. **Salvataggio Batch**: Upsert memoria globale per keyword e AI
5. **Update DB**: Batch UPDATE per categoria su fatture Supabase
6. **Fallback**: Secondo tentativo dizionario per articoli rimasti
7. **Verifica Post-Update**: Count righe ancora "Da Classificare"

Banner orizzontale animato con cervello pulsante 🧠 e percentuale in tempo reale.

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
| BAR | Acqua, Bevande, Caffè e The, Varie Bar |
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
| Time cost | 3 iterazioni |
| Parallelism | 4 thread |
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

1. Utente inserisce email → sistema genera codice 6 cifre con `secrets.randbelow()`
2. Email inviata via Brevo SMTP API con codice e scadenza 15 minuti
3. Utente inserisce codice + nuova password → verifica HMAC constant-time
4. Password validata secondo compliance GDPR → hash Argon2id salvato atomicamente
5. Token reset invalidato → login automatico

### Gestione Cookie di Sessione

- **session_token**: UUID4, salvato in DB + cookie browser (30 giorni)
- **impersonation_user_id**: Solo per admin che impersonano clienti
- Verifica TTL 30 giorni al ripristino sessione
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
| fatturato_bar | NUMERIC(12,2) | Fatturato centro BAR |
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

### Migrazioni SQL (44 file)

Le migrazioni sono numerate progressivamente da `001` a `044` e gestiscono:

- Aggiunta colonne incrementali (reset, sconto, needs_review, verified, P.IVA, altri_ricavi_noiva, tipo_documento)
- Creazione tabelle (categorie, prodotti_master, prodotti_utente, ristoranti, ricette, ingredienti_workspace, note_diario, margini_mensili, login_attempts)
- Policy RLS per multi-tenancy e autenticazione custom
- Stored procedure RPC (create_ristorante, get_distinct_files)
- Indici di performance
- Fix retroattivi (diciture corrotte, permessi RLS, foreign key)
- Tracking costi AI
- Sessioni e token
- Rate limiting persistente su DB

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
- Gestione pagine abilitate per cliente (Marginalità, Workspace)

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
- Input per mese selezionato, salvato su `margini_mensili.fatturato_food/bar/alcolici/dolci`
- Analisi aggregata su range di periodo via `carica_fatturato_centri_periodo()`
- Calcolo Food Cost % e margine per singolo centro
- Grafici a barre comparativi per centro

#### 🔬 Analisi Avanzate

- Trend temporale costi per categoria F&B via `carica_costi_per_categoria()`
- Breakdown mensile con grafici Plotly interattivi
- Export Excel formattato

---

## 14. Pagine Secondarie

### 2_workspace.py — Workspace Ricette e Diario (~2.125 righe)

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

### privacy_policy.py — Privacy e Condizioni

Due tab:
- **Privacy Policy**: Informativa GDPR completa (titolare, base giuridica, diritti, data retention)
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

### Suite di Test (172 test totali, confermati da pytest)

| File | Test approx. | Copertura |
|------|------|-----------| 
| `test_text_utils.py` | 30 | Normalizzazione, estrazione fornitore, pulizia |
| `test_piva_validator.py` | 18 | Validazione P.IVA (Luhn), normalizzazione |
| `test_ai_service.py` | 15 | Classificazione AI, memoria 3 livelli, quarantena |
| `test_validation.py` | 14 | Diciture, sconti, integrità fattura |
| `test_constants.py` | 13 | Integrità categorie, regex compilate, KPI soglie |
| `test_db_service.py` | 12 | Alert variazioni prezzo, normalizzazione categorie |
| `test_invoice_service.py` | 11 | Parsing XML, P7M, encoding, tipo documento |
| `test_formatters.py` | 11 | Formattazione numeri, base64, prezzo standard |
| `test_auth_service.py` | 11 | Login, rate limiting, GDPR password, reset |

> I conteggi per file sono basati su funzioni `test_*`; il totale di 172 include test parametrizzati espansi da pytest.

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

Ultimo risultato: **172/172 PASSED** (~1.46s)

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

### Secrets Management

I secrets sono gestiti tramite Streamlit Secrets (`st.secrets`), configurati nell'interfaccia Streamlit Cloud:

```toml
# .streamlit/secrets.toml (NON versionato)
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "eyJhbG..."
OPENAI_API_KEY = "sk-..."

[brevo]
api_key = "xkeysib-..."
sender_email = "noreply@ohyeah.app"
sender_name = "OH YEAH!"
reply_to_email = "support@ohyeah.app"
reply_to_name = "Support OH YEAH!"
```

### Dipendenze Lockate

Il file `requirements-lock.txt` contiene 91 pacchetti con versioni esatte per build riproducibili:

```
argon2-cffi==25.1.0
openai==1.x.x
streamlit==1.x.x
supabase==2.x.x
pandas==2.x.x
...
```

### Supabase

| Parametro | Valore |
|-----------|--------|
| Piano | Free Tier |
| Region | EU (Frankfurt) |
| PostgreSQL | v15 |
| RLS | Attivo su tutte le tabelle |
| Backup | Automatici giornalieri (piano free) |
| Limite | 500 MB storage, 2 GB transfer, pausa dopo 7 giorni inattività |

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
              -d '{"sender":{"email":"alerts@ohyeah.app","name":"OH YEAH! Monitor"},
                   "to":[{"email":"mattiadavolio90@gmail.com"}],
                   "subject":"🚨 OH YEAH! DOWN",
                   "htmlContent":"<p>Status: '$STATUS'</p>"}'
            exit 1
          fi
          echo "Site OK - Status: $STATUS"
```

### Logging Applicativo

| Componente | Configurazione |
|-----------|---------------|
| File handler | `RotatingFileHandler` |
| Max dimensione | 50 MB per file |
| Backup files | 10 (totale max ~550 MB) |
| Livello | INFO in produzione |
| Format | `%(asctime)s [%(name)s] %(levelname)s %(message)s` |
| Logger modulari | `app`, `ai`, `auth`, `invoice`, `db`, `admin`, `email`, `margine_service` |

---

## 18. Sicurezza e Compliance GDPR

### Misure di Sicurezza Implementate

| Categoria | Misura | Dettaglio |
|-----------|--------|-----------|
| **Autenticazione** | Argon2id | m=65536, t=3, p=4 (OWASP 2026) |
| **Sessioni** | Token UUID4 + Cookie 30gg | Invalidazione esplicita su logout |
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
| **Cookie** | HttpOnly session token | Non accessibile da JavaScript |
| **Secrets** | Streamlit Secrets | Variables d'ambiente, mai hardcoded |
| **Dependencies** | `requirements-lock.txt` | 91 pacchetti freezati per supply chain security |

### Compliance GDPR

- **Privacy Policy**: Pagina dedicata con informativa completa
- **Terms of Service**: Condizioni d'uso con clausole legali italiane
- **Data Retention**: Le fatture restano nel DB finché l'utente le elimina
- **Diritto all'oblio**: L'admin può eliminare completamente un account
- **Portabilità**: Export Excel di tutti i dati
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
- Svuotare cache browser per problemi persistenti

### Comandi Utili per Sviluppatori

```bash
# Avviare l'app in locale
streamlit run app.py

# Eseguire i test
pytest tests/ -v --tb=short

# Controllare errori di import
python -c "import app"

# Contare righe di codice
find . -name "*.py" -not -path "./.venv/*" -not -path "./__pycache__/*" | xargs wc -l

# Verificare dipendenze
pip freeze > requirements-lock.txt
```

### Variabili d'Ambiente

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `ADMIN_EMAILS` | Lista email admin (separati da virgola) | `mattiadavolio90@gmail.com` |
| `SUPABASE_URL` | URL progetto Supabase | In `st.secrets` |
| `SUPABASE_KEY` | Chiave API Supabase | In `st.secrets` |
| `OPENAI_API_KEY` | Chiave API OpenAI | In `st.secrets` |

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

*Documento generato automaticamente dall'analisi completa del codice sorgente.*
*Per aggiornamenti, modifiche o domande: mattiadavolio90@gmail.com*
