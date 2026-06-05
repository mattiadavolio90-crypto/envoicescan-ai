# ONEFLUX — Documentazione Tecnica Completa

**Sistema SaaS di Analisi Fatture e Controllo Costi per la Ristorazione**

Versione: 6.0
Ultimo aggiornamento: 5 Giugno 2026
Autore: Mattia D'Avolio
Repository: `mattiadavolio90-crypto/envoicescan-ai` (privato)
Titolare: Recoma System S.r.l. (P.IVA IT09599210961)
URL Streamlit (legacy): https://app.oneflux.it
URL Next.js (produzione): https://nuovo.oneflux.it

> **v6.0** — Documentazione riscritta e aggiornata. Riflette lo stato reale al 5 giugno 2026:
> migrazione Next.js Fasi 0–8 completate, PWA mobile, Chat AI, Marketplace, Admin Panel completo,
> Privacy v4.0 (Recoma System S.r.l.), 760+ test, 122+ endpoint worker.
> Streamlit resta attivo in parallelo su `app.oneflux.it` fino al completamento della Fase 10 (switch DNS).

---

## Indice

1. [Panoramica del Progetto](#1-panoramica-del-progetto)
2. [Business Model e Posizionamento](#2-business-model-e-posizionamento)
3. [Architettura del Sistema](#3-architettura-del-sistema)
4. [Stack Tecnologico](#4-stack-tecnologico)
5. [Struttura del Codice Sorgente](#5-struttura-del-codice-sorgente)
6. [Funzionalità per Sezione](#6-funzionalità-per-sezione)
7. [Pipeline di Classificazione AI](#7-pipeline-di-classificazione-ai)
8. [Sistema di Autenticazione e Sicurezza](#8-sistema-di-autenticazione-e-sicurezza)
9. [Parsing delle Fatture Elettroniche](#9-parsing-delle-fatture-elettroniche)
10. [Multi-Tenancy e Multi-Ristorante](#10-multi-tenancy-e-multi-ristorante)
11. [Schema Database](#11-schema-database)
12. [Pannello di Amministrazione](#12-pannello-di-amministrazione)
13. [Calcolo Marginalità e KPI](#13-calcolo-marginalità-e-kpi)
14. [Sistema di Notifiche](#14-sistema-di-notifiche)
15. [Integrazione Invoicetronic — SDI](#15-integrazione-invoicetronic--sdi)
16. [FastAPI Worker](#16-fastapi-worker)
17. [Chat AI e Marketplace Servizi](#17-chat-ai-e-marketplace-servizi)
18. [PWA Mobile](#18-pwa-mobile)
19. [Testing e Qualità](#19-testing-e-qualità)
20. [Deploy e Infrastruttura](#20-deploy-e-infrastruttura)
21. [Monitoraggio e Logging](#21-monitoraggio-e-logging)
22. [Compliance GDPR](#22-compliance-gdpr)
23. [Troubleshooting](#23-troubleshooting)
24. [Limiti Tecnici](#24-limiti-tecnici)

---

## 1. Panoramica del Progetto

### Cos'è ONEFLUX

ONEFLUX è una piattaforma SaaS web-based per ristoratori italiani che automatizza l'analisi delle fatture elettroniche dei fornitori. Non è un gestionale: è una **piattaforma di servizi orchestrata da AI** che affianca il ristoratore nella gestione economica quotidiana.

**Funzionalità core:**
- Ricezione automatica fatture via SDI (Invoicetronic, codice dest. `7HD37X0`)
- Upload manuale di fatture (XML, P7M, PDF, JPG/PNG)
- Classificazione AI automatica in 31 categorie merceologiche (600+ keyword + GPT-4o-mini)
- Dashboard KPI, grafici, pivot mensili per categoria e fornitore
- Calcolo Margine Operativo Lordo (MOL) con centri di produzione
- Import ricavi da gestionali (XLS Passbi v1, email automatica)
- Gestione multi-ristorante (un account, più locali)
- Controllo prezzi, sconti, note di credito
- Briefing AI giornaliero con salute della gestione
- Chat AI sui dati del ristorante (function calling)
- Strumenti operativi: Foodcost, Inventario, Diario, Personale/Turni
- Marketplace servizi (consulenza F&B, studi menù, comparatori)
- PWA mobile installabile (5 sezioni: Oggi, Avvisi, Diario, Turni, Assistente)

### Filosofia portante

1. **App di analisi, NON live critica** — nessuno strumento operativo tipo cassa/comande
2. **Ristoratori antitecnologici** — soluzioni smart ma semplici, mai complicare
3. **AI-first** — l'AI orchestra, non è un addon
4. **Dati macro** — nessuna granularità "quanti spaghetti hai venduto" (per quello c'è il gestionale)
5. **Modulare** — mai più riscrivere da zero come è successo con Streamlit

### Pubblico target

| Segmento | Descrizione |
|----------|-------------|
| Ristoratori | Proprietari di ristoranti, pizzerie, bar, pasticcerie |
| Catene piccole | Aziende con 2–5 locali |
| Consulenti F&B | Professionisti che seguono più locali |

---

## 2. Business Model e Posizionamento

### Struttura commerciale

- **Prodotto**: ONEFLUX — by Mattia & RECOMA
- **Mattia D'Avolio**: P.IVA personale, sviluppa e mantiene ONEFLUX
- **Recoma System S.r.l.**: rivende ONEFLUX ai propri clienti; Mattia fattura a RECOMA, RECOMA fattura al cliente finale
- **Mattia diretto**: vende anche a clienti non-RECOMA
- **Costi infrastruttura**: intestati a Mattia personalmente

### Pricing (3 tier)

| Piano | Prezzo | Fatture/mese | Note |
|-------|--------|--------------|------|
| Base | €39/mese | fino a 50 | |
| Plus | €49/mese | fino a 100 | |
| Pro | €69/mese | fino a 200 | |

- Costo variabile principale: Invoicetronic (€0,10–0,15/fattura)
- Multi-ristorante stessa P.IVA: abbonamento × N locali + vista catena inclusa
- Multi-ristorante P.IVA diverse: abbonamenti separati
- Counter "fatture usate / limite piano" sempre visibile nell'account

### Modello a 3 strati

```
STRATO 1 — AUTOMAZIONE (biglietto d'ingresso ricorrente)
   Fatture, Scadenze, Margini, Foodcost, Prezzi, Ricavi

STRATO 2 — INTELLIGENZA (incluso nel pricing)
   Briefing AI, notifiche smart, alert prezzi, suggerimenti

STRATO 3 — SERVIZI (pay-per-use, upselling)
   Consulenza, studi menù, comparatori utenze/POS, formazione
```

### Clienti attuali (giugno 2026)

- 2 clienti in fase di test su `nuovo.oneflux.it`
- 1 cliente operativo su Streamlit (`app.oneflux.it`)
- Streamlit resta acceso in parallelo fino al completamento Fase 10

---

## 3. Architettura del Sistema

### Visione d'insieme

```
┌─────────────────────────────────────────────────────────────┐
│                    UTENTE (Browser)                          │
│         nuovo.oneflux.it  |  app.oneflux.it                 │
└──────────────┬──────────────────────┬───────────────────────┘
               │ HTTPS                │ HTTPS
               ▼                      ▼
┌──────────────────────┐  ┌───────────────────────────────────┐
│ Next.js 16 (Vercel)  │  │  Streamlit Cloud (legacy)         │
│ apps/web/            │  │  app.py + pages/*.py              │
│ - Route /api/* proxy │  │  - Service layer Python           │
│   → FastAPI Worker   │  │  - Stesse API FastAPI             │
└──────────┬───────────┘  └───────────────┬───────────────────┘
           │                              │
           └──────────────┬───────────────┘
                          │ HTTP interno
                          ▼
           ┌──────────────────────────────┐
           │   FastAPI Worker (Railway)   │
           │   services/fastapi_worker.py │
           │   122+ endpoint REST         │
           │   POST /api/classify         │
           │   POST /api/parse            │
           │   GET  /api/home/briefing    │
           │   ... (tutti i service)      │
           └───────┬──────────────────────┘
                   │
        ┌──────────┼──────────────┐
        ▼          ▼              ▼
 ┌──────────┐ ┌──────────┐ ┌───────────────────────┐
 │ Supabase │ │ OpenAI   │ │ Brevo SMTP API         │
 │ PostgreSQL│ │ GPT-4o-  │ │ Email transazionali    │
 │ + RLS    │ │ mini     │ │                        │
 └──────────┘ └──────────┘ └───────────────────────┘

           ┌──────────────────────────────────────┐
           │    FLUSSO INVOICETRONIC (automatico)  │
           │                                      │
           │  SDI → Invoicetronic → POST webhook  │
           │  → Edge Function Supabase (Deno/TS)  │
           │    HMAC-SHA256 + anti-replay         │
           │    lookup P.IVA → INSERT fatture_queue│
           │                                      │
           │  Railway queue-worker (24/7)          │
           │  → worker/run.py ogni 15 secondi      │
           │  → parsing + classificazione AI       │
           │  → purge XML (GDPR, 24h)              │
           └──────────────────────────────────────┘
```

### Coesistenza Streamlit + Next.js

Durante il periodo di migrazione (Fasi 1–9), entrambi i frontend coesistono e puntano allo **stesso database Supabase**. Un cliente che carica una fattura su Streamlit la vede immediatamente anche su Next.js.

- `app.oneflux.it` → Streamlit (clienti attivi, legacy)
- `nuovo.oneflux.it` → Next.js (nuovo frontend, clienti di test)
- Switch DNS definitivo → Fase 10 (previsto dopo test completi)

### Pattern architetturali

| Pattern | Dove | Descrizione |
|---------|------|-------------|
| MVC-like | Globale | Pages=View, Services=Model, Utils=Helper |
| Singleton | `get_supabase_client()` | Unica istanza Supabase per sessione |
| Proxy | Next.js `/api/*` | Ogni route Next proxia al FastAPI Worker |
| Cache-aside | `@st.cache_data` (Streamlit) | TTL 120s fatture, 300s margini |
| 3-tier Memory | `ai_service.py` | Admin > Locale > Globale per classificazione |
| Thread-safe Lock | `_cache_lock` | `threading.Lock()` per dati condivisi |
| Batch Processing | Classificazione AI | 50 articoli per chiamata API |
| Confidenza routing | `upload_handler.py` | altissima/alta → no review; media/bassa → coda admin |

---

## 4. Stack Tecnologico

### Frontend

| Componente | Tecnologia | Note |
|-----------|-----------|------|
| Framework | Next.js 16.2.6 | App Router, Turbopack attivo |
| Styling | Tailwind v4 | |
| UI Components | shadcn/ui v4 | Button, Card, Dialog, Table, Sidebar, Sheet, Popover, ecc. |
| Icone | Lucide React | |
| Grafici | Recharts | Sparkline, line chart, donut |
| Export XLS | SheetJS | Client-side, 3 fogli |
| Legacy frontend | Streamlit | Resta attivo fino Fase 10 |
| Grafici legacy | Plotly | Solo su Streamlit |

### Backend

| Componente | Tecnologia | Note |
|-----------|-----------|------|
| Linguaggio | Python 3.12.8 | Type hints, f-strings |
| API Framework | FastAPI + Uvicorn | 122+ endpoint, threadpool 100 thread |
| Database | Supabase (PostgreSQL 15) | EU Frankfurt, RLS attivo |
| Edge Functions | Deno / TypeScript | Supabase Edge, invoicetronic-webhook |
| AI/ML | OpenAI GPT-4o-mini | Batch 50 articoli, $0.15/1M token input |
| Email | Brevo SMTP API v3 | 300 email/giorno (free tier) |
| Password | Argon2id | m=65536, parametri default `argon2-cffi` |
| SDI | Invoicetronic | Codice dest. `7HD37X0` |

### Deploy

| Servizio | Piano | Uso |
|---------|-------|-----|
| Vercel | Free (Pro quando serve, €20) | Next.js frontend `nuovo.oneflux.it` |
| Railway `ingenious-fascination` | €5/mese | Streamlit + FastAPI worker + queue-worker |
| Supabase | Free (Pro solo se problemi reali, €25) | Database + Edge Functions |
| Brevo | Free tier | Email transazionali |
| GitHub Actions | Free | Uptime check ogni 5 min + fallback worker manuale |
| Invoicetronic | A consumo | SDI intermediario |

### Dipendenze Python principali

| Pacchetto | Uso |
|-----------|-----|
| `fastapi` + `uvicorn` | Worker REST API |
| `supabase` | Client PostgreSQL managed |
| `openai` | Client GPT-4o-mini |
| `argon2-cffi` | Password hashing sicuro |
| `pandas` | Data processing e aggregazione |
| `plotly` | Grafici interattivi (Streamlit) |
| `openpyxl` | Export Excel |
| `xmltodict` | Parsing XML fatture |
| `asn1crypto` | Estrazione XML da file P7M |
| `PyMuPDF (fitz)` | Parsing PDF fatture |
| `tenacity` | Retry logic per API OpenAI |
| `requests` | HTTP client |
| `pydantic` | Validazione modelli dati FastAPI |
| `charset-normalizer` | Rilevamento encoding XML |
| `streamlit` | Legacy frontend (fino Fase 11) |

---

## 5. Struttura del Codice Sorgente

```
ONEFLUX/
│
├── apps/web/                          # Next.js 16 frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── (app)/                 # Layout autenticato (sidebar)
│   │   │   │   ├── dashboard/         # Home AI
│   │   │   │   ├── analisi-fatture/   # Fatture + upload
│   │   │   │   ├── prezzi/            # Variazioni, sconti, NC
│   │   │   │   ├── margini/           # MOL + Ricavi
│   │   │   │   ├── workspace/         # Strumenti (4 tab)
│   │   │   │   ├── analisi-e-tag/     # Custom tags + analytics
│   │   │   │   ├── scadenziario/      # Gestione fatture + cestino
│   │   │   │   ├── notifiche/         # Inbox notifiche
│   │   │   │   ├── impostazioni/      # Account + dati ristorante
│   │   │   │   ├── assistenza/        # Marketplace servizi + Chat AI
│   │   │   │   └── admin/             # Panel admin (solo admin)
│   │   │   ├── (legal)/               # Pagine legali pubbliche
│   │   │   │   ├── privacy/           # Privacy & Cookie Policy v4.0
│   │   │   │   └── termini/           # Terms of Service
│   │   │   ├── (mobile)/              # PWA mobile route group
│   │   │   │   └── m/                 # 5 sezioni: Oggi/Avvisi/Diario/Turni/Assistente
│   │   │   ├── api/                   # Proxy routes → FastAPI Worker
│   │   │   │   ├── auth/              # login, logout, me, reset
│   │   │   │   ├── home/              # briefing, salute, kpi, config
│   │   │   │   ├── fatture/           # CRUD fatture, upload
│   │   │   │   ├── margini/           # MOL, ricavi, centri
│   │   │   │   ├── prezzi/            # alert, sconti, NC
│   │   │   │   ├── tag/               # Custom tags CRUD + analytics
│   │   │   │   ├── workspace/         # foodcost, inventario, diario, personale
│   │   │   │   ├── notifiche/         # inbox + dismiss
│   │   │   │   ├── chat/              # Chat AI
│   │   │   │   ├── assistenza/        # Marketplace leads
│   │   │   │   └── admin/             # Admin CRUD + impersonazione + qualità AI
│   │   │   ├── login/
│   │   │   ├── forgot-password/
│   │   │   └── reset-password/
│   │   ├── components/
│   │   │   ├── ui/                    # shadcn components
│   │   │   ├── admin/                 # impersona-banner.tsx, ecc.
│   │   │   └── ...
│   │   └── lib/
│   │       ├── auth.ts                # Cookie HttpOnly, getCurrentUser
│   │       ├── worker.ts              # workerGet<T> — helper HTTP verso FastAPI
│   │       ├── home.ts                # fetcher briefing/salute/kpi
│   │       ├── admin.ts               # tipi Cliente, ClienteDettaglio, Sede
│   │       ├── tag.ts                 # tipi tag analytics
│   │       ├── inventario.ts          # tipi + UM_INVENTARIO
│   │       ├── scadenziario.ts        # tipi + parseLocalDate()
│   │       └── assistenza.ts          # catalogo 6 servizi statici
│   ├── public/
│   │   ├── manifest.json              # PWA manifest (start_url /m)
│   │   ├── sw.js                      # Service Worker manuale (network-first)
│   │   ├── offline.html               # Fallback offline
│   │   └── icons/                     # Icone maskable 192/512
│   └── next.config.ts
│
├── app.py                             # Entry point Streamlit (legacy)
├── pages/                             # Pagine Streamlit multi-page
│   ├── admin.py                       # Pannello admin Streamlit (6 tab)
│   ├── 1_calcolo_margine.py           # MOL e centri di produzione
│   ├── 2_foodcost.py                  # Foodcost, ricette, diario
│   ├── 3_controllo_prezzi.py          # Variazioni prezzi, sconti, NC
│   ├── gestione_account.py            # Cambio password, export GDPR
│   └── privacy_policy.py              # Privacy Policy Streamlit
│
├── services/                          # Business logic layer (condiviso)
│   ├── __init__.py                    # get_supabase_client() singleton
│   ├── fastapi_worker.py              # FastAPI 122+ endpoint
│   ├── ai_service.py                  # Classificazione AI + memoria 3 livelli
│   ├── ai_cost_service.py             # Tracking costi OpenAI
│   ├── auth_service.py                # Login, reset, rate limiting, GDPR
│   ├── invoice_service.py             # Parsing XML/P7M/PDF/Vision
│   ├── db_service.py                  # Query Supabase + cache
│   ├── margine_service.py             # Calcoli MOL + export Excel
│   ├── upload_handler.py              # Upload file + confidenza routing
│   ├── email_service.py               # Brevo SMTP con retry
│   ├── notification_service.py        # Notifiche in-app (finestra 90gg)
│   ├── daily_briefing_service.py      # Pipeline briefing AI giornaliero
│   ├── price_impact_service.py        # Alert prezzi per impatto €/mese
│   ├── tag_analytics_service.py       # KPI + trend + analisi fornitori per tag
│   ├── tag_suggestion_service.py      # Algoritmo suggerimenti tag automatici
│   └── worker_client.py               # Proxy Streamlit → FastAPI (con fallback)
│
├── worker/                            # Worker asincrono coda Invoicetronic
│   ├── run.py                         # Entry point Railway queue-worker
│   └── queue_processor.py             # Elaborazione coda + GDPR purge
│
├── supabase/
│   ├── config.toml
│   ├── functions/
│   │   ├── .env.local.template
│   │   └── invoicetronic-webhook/     # Edge Function Deno/TypeScript
│   │       ├── index.ts               # HMAC, lookup P.IVA, INSERT fatture_queue
│   │       ├── test.ts
│   │       └── test.http
│   └── migrations/                    # Migration timestamp-based Supabase
│       └── 20260601*.sql ...
│
├── utils/                             # Helper e utility Python
│   ├── formatters.py
│   ├── text_utils.py
│   ├── validation.py
│   ├── piva_validator.py
│   ├── sidebar_helper.py
│   ├── ristorante_helper.py
│   ├── period_helper.py
│   ├── ui_helpers.py
│   ├── page_setup.py
│   └── app_controllers.py             # Controller estratto da app.py
│
├── components/                        # Componenti UI riusabili Streamlit
│   ├── category_editor.py             # Data editor categorie
│   └── dashboard_renderer.py          # KPI, grafici, pivot
│
├── config/
│   ├── constants.py                   # 31 categorie, 600+ keyword, regex, soglie KPI
│   ├── logger_setup.py                # RotatingFileHandler (50 MB × 10)
│   └── prompt_ai_potenziato.py        # Prompt GPT-4o-mini classificazione
│
├── migrations/                        # SQL legacy (001→068)
├── tests/                             # 760+ test pytest
├── docker/                            # Dockerfile + docker-compose
├── scripts/                           # Script PowerShell operativi
├── tools/                             # Script manutenzione DB
├── static/                            # CSS Streamlit
├── .github/workflows/                 # uptime_check.yml + queue-worker.yml
├── railway.toml                       # Config deploy Railway
├── requirements.txt / requirements-lock.txt
├── pytest.ini
├── ONEFLUX_MASTER.md                  # Documento vision + piano + stato (fonte unica)
└── CLAUDE.md                          # Istruzioni per Claude Code
```

---

## 6. Funzionalità per Sezione

### Home / Dashboard (Next.js: `/dashboard`, Streamlit: `app.py`)

La Home è il cuore dell'esperienza: non mostra solo KPI ma è la voce quotidiana dell'assistente AI.

**Componenti:**
- **Briefing AI giornaliero** — saluto adattivo all'ora (fuso Europe/Rome, solo `nome_referente`), narrativa AI con azioni "da fare oggi". Cache giornaliera su `daily_briefing_state`: l'AI viene chiamata ~1 volta/giorno per cliente, si rigenera solo se cambiano notifiche o preferenze
- **Salute della gestione** — indice di completezza dati (4 voci a peso uguale: fatture caricate ultimi 30gg, fatturato ultimo mese completo, costo personale ultimo mese, % righe classificate). Colore adattivo verde/giallo/rosso su soglie 80/50
- **Conto economico del mese** — MOL gigante centrale (verde/rosso) + breakdown Fatturato − Food cost − Personale − Spese = MOL, con confronto vs mese precedente (delta %). Fonte: `margini_mensili`
- **Notifiche actionable** — card "Da fare oggi" con CTA dirette alle sezioni
- **Widget notifiche** — Dialog lazy-load inbox completa
- **Configuratore assistente** — nome referente + toggle topic avvisi
- **Chat AI** — widget flottante in basso a destra (solo Home)

**KPI dashboard Streamlit (legacy):** 6 metriche (Spesa Totale, F&B, Fornitori F&B, Fornitori Spese, Spesa Generale, Media Mensile) + 3 sezioni (Dettaglio Articoli, Categorie, Fornitori)

### Analisi Fatture (`/analisi-fatture`)

- KPI bar (spesa totale, food cost, fornitori, media/mese)
- Filtro periodo: chip mese + selezione anno
- 3 tab: **Articoli** (data editor con categoria editabile, ricerca, filtro F&B/Spese), **Categorie** (pivot mensile), **Fornitori** (pivot mensile)
- Edit categoria batch con propagazione in DB
- Upload modal drag-and-drop (XML, P7M, PDF, JPG/PNG, max 100 file / 200 MB)
- Progress bar upload in tempo reale
- Validazione P.IVA destinatario vs ristorante attivo
- Deduplicazione automatica (stesso `file_origine + user_id + ristorante_id`)
- Bottone recovery AI "Riprova" — visibile solo se rimangono righe non classificate

### Gestione Fatture / Scadenziario (`/scadenziario`)

- Vista agenda (bucket urgenza: scadute / oggi / 7gg / 30gg / future)
- Vista calendario cash-flow mensile
- KPI bar (4 card reattive ai filtri: da pagare, scadute, pagate, totale)
- Filtri: chip periodo + multi-fornitore (popover)
- Scadenza override manuale
- Bulk "Segna pagata" + select-all per sezione
- Regole fornitore (dialog centrato, termini di pagamento automatici)
- Anteprima fattura lazy-load nel peek laterale (50% schermo)
- Elimina fattura dal peek (soft-delete → cestino)
- **Cestino integrato**: widget collassabile accanto ad "Aggiorna" (ripristina / elimina definitivo / svuota tutto)

### Ricavi e Margini (`/margini`)

**Tab Marginalità:**
- Tabella ricavi/costi 12 mesi trasposta
- Input manuali: Fatturato IVA 10%/22%, Altri Ricavi, Costi extra F&B/Spese, Costo Personale
- Dati automatici da fatture: `costi_fb_auto`, `costi_spese_auto`
- KPI calcolati: Fatturato Netto, Food Cost %, 1° Margine %, Spese Gen. %, MOL %
- Dialog "Carica ricavi": calendario mensile visuale + XLS Passbi v1 + modalità giornaliero/mensile
- Widget "Costo personale" nelle celle Marginalità — recupero automatico dai turni o inserimento manuale
- Soglie colorate: Food Cost (🟢<28%, 🟡28-33%, 🟠33-38%, 🔴>38%), MOL (🟢>20%, 🟡12-20%, 🟠5-12%, 🔴<5%)

**Tab Analisi Avanzate:**
- Donut centri di produzione (FOOD/BEVERAGE/ALCOLICI/DOLCI)
- Line chart trend temporale costi per categoria
- Performance card per centro con food cost %
- Commenti AI automatici sui KPI
- Ripartizione centri mensile (€/%), dettaglio giornaliero derivato

### Prezzi (`/prezzi`)

3 tab:
- **Variazioni prezzo**: storico ultimi 5 prezzi per prodotto, alert > soglia configurabile (default 5%, `users.price_alert_threshold`), ordinati per impatto €/mese
- **Sconti e Omaggi**: righe con totale negativo (sconti) + prezzo=€0 (omaggi), valore stimato, KPI totale risparmiato
- **Note di Credito**: filtro `tipo_documento=TD04` o `totale_riga<0`, KPI, ricerca, export

### Analisi e Tag (`/analisi-e-tag`)

- Chip tag selezionabili (custom tags del ristorante)
- Pill periodo (anno + singoli mesi)
- KPI bar (5 card): spesa totale, incidenza %, ultimo prezzo medio, n. prodotti, n. fornitori
- Trend prezzi collassabile (recharts + linea media)
- Tabella fornitori con barre incidenza %
- Sezione prodotti inline (ricerca + aggiungi/rimuovi da tag)
- Banner suggerimenti automatici (widget ambra + card espandibile, checkbox per accettare)
- Export XLS client-side (3 fogli: prodotti, fornitori, trend)

### Strumenti / Workspace (`/workspace`)

Pagina-contenitore con 4 tab:

**Foodcost:**
- Ricette con ingredienti da 3 fonti: fatture reali, ingredienti workspace, semilavorati
- Calcolo foodcost: grammatura, conversione UM, foodcost/margine/incidenza per piatto
- Ricette annidate (semilavorati come ingredienti)
- Matrice menu engineering (Stelle/Cavalli/Enigmi/Cani — popolarità × marginalità)
- Analisi ricette: KPI menu, distribuzione categorie, margine netto per piatto
- Export Excel

**Inventario:**
- Conta-giacenze semplice (articolo + quantità + valore), non movimentazione live
- Articoli pescabili dai prodotti delle fatture (autocomplete, UM bloccata da fattura)
- Date picker custom con pallini sui giorni con inventario
- KPI cards (valore magazzino, prodotti, categorie)
- Analisi per categoria collapsabile
- Copia da snapshot (articoli con qty=0 da data precedente)
- Export CSV per Excel

**Diario:**
- Calendario mensile a griglia con pallini colorati sui giorni con eventi
- Pannello laterale lista eventi del giorno selezionato
- Dialog aggiungi/modifica (titolo, data, orario opzionale, note, 6 colori)
- Migrazione automatica da vecchia tabella `note_diario` → `diario_eventi`

**Personale:**
- Turni a nomi liberi con autocomplete dai nomi già usati
- Vista settimana (griglia 7 colonne) + vista mese (lista per data)
- Campi: ore, di cui extra, costo orario (€/h, autocompila dal nome)
- KPI cards: monte ore, totale extra, costo lavoro
- Copia settimana precedente
- Export CSV per ufficio paghe

### Admin Panel (`/admin`)

Accessibile solo agli admin (`is_admin=True` verificato lato worker). Vedi sezione dedicata [§12](#12-pannello-di-amministrazione).

### Impostazioni / Account (`/impostazioni`)

- Dati ristorante (nome, P.IVA, ragione sociale)
- Piano + contatore fatture usate/mese (barra reattiva verde/amber/rosso)
- Contatore chat AI (X/limite, si azzera a mezzanotte)
- Cambio password
- Export GDPR Art.20 (Streamlit: JSON 10 tabelle)

### Pagine legali (pubbliche, senza login)

- `/privacy` — Privacy & Cookie Policy v4.0 (Recoma System S.r.l., P.IVA IT09599210961)
- `/termini` — Terms of Service

---

## 7. Pipeline di Classificazione AI

Vedi documento dedicato: [AI_PIPELINE.md](AI_PIPELINE.md)

### Riepilogo

**5 livelli di priorità (dall'alto al basso):**
1. Memoria Admin (`classificazioni_manuali`) — globale, priorità massima
2. Memoria Locale (`prodotti_utente`) — per singolo cliente
3. Memoria Globale (`prodotti_master`) — per tutti i clienti
4. Dizionario keyword (`constants.py`) — 600+ regole deterministiche
5. GPT-4o-mini — batch 50 articoli, retry con backoff esponenziale

**Routing confidenza (sull'ingest):**
- `altissima / alta` → `needs_review=False`, bypassa coda admin
- `media / bassa` → `needs_review=True`, entra nella coda review admin

**31 categorie:** 25 Food & Beverage + 1 Materiale di Consumo + 3 Spese Operative + 2 speciali (Note e Diciture solo per €0, Da Classificare vietata per constraint DB — fallback: "SERVIZI E CONSULENZE")

---

## 8. Sistema di Autenticazione e Sicurezza

Vedi documento dedicato: [SICUREZZA_GDPR.md](SICUREZZA_GDPR.md)

### Riepilogo auth

**Streamlit (legacy):**
- Cookie `session_token` (30 giorni, `secrets.token_urlsafe(32)`)
- Argon2id m=65536
- Auto-logout 8h inattività
- Cookie: Secure=True, SameSite=Strict (no HttpOnly — limitazione `extra-streamlit-components`)

**Next.js:**
- Cookie HttpOnly (sicurezza superiore a Streamlit)
- Stesse sessioni Supabase, compatibili con il worker FastAPI
- Header sicurezza: CSP, HSTS, X-Frame-Options

**Rate limiting:**
- Login: 5 tentativi → 15 min lockout (persistente su tabella `login_attempts`)
- Reset password: 1 richiesta / 5 min (in-memory thread-safe)

**Admin guard (`_verify_admin` in FastAPI):**
- Verifica worker key + bearer token → identità utente → `is_admin`
- Introdotto in Fase 7: prima il guard non verificava l'identità admin

---

## 9. Parsing delle Fatture Elettroniche

Vedi documento dedicato: [AI_PIPELINE.md](AI_PIPELINE.md) (sezione Parsing)

### Formati supportati

| Formato | Libreria | Note |
|---------|----------|------|
| XML (FatturaPA) | `xmltodict` | Auto-detect encoding (UTF-8, cp1252, GB2312, GBK) |
| P7M (firma CAdES) | `asn1crypto` + fallback pattern | Max 50 MB |
| PDF | `PyMuPDF` + OpenAI Vision | Vision come fallback se testo insufficiente |
| JPG/PNG | OpenAI Vision | Base64 + prompt estrazione |

### Tipi documento gestiti

| Codice | Tipo | Trattamento |
|--------|------|-------------|
| TD01 | Fattura | Importi positivi |
| TD02 | Acconto | Importi positivi |
| TD04 | Nota di Credito | Importi invertiti (negativi) |
| TD05 | Nota di Debito | Importi positivi |
| TD06 | Parcella | Importi positivi |
| TD16–TD27 | Autofatture | Importi positivi |

---

## 10. Multi-Tenancy e Multi-Ristorante

### Isolamento dati

Ogni query include obbligatoriamente:
```python
supabase.table("fatture")
    .eq("user_id", user_id)
    .eq("ristorante_id", ristorante_id)
    .not_.is_("deleted_at", "null")   # soft-delete filter
```

RLS Supabase attivo su tutte le tabelle come secondo livello di protezione. `auth.uid()` è sempre NULL (auth custom, non Supabase Auth) — accesso solo via `service_role_key` che bypassa RLS.

### Modello multi-ristorante

```
UTENTE (users)
  └── Ristorante 1 (ristoranti) ──→ Fatture ristorante 1
  └── Ristorante 2 (ristoranti) ──→ Fatture ristorante 2
```

- Dropdown selezione visibile solo con 2+ ristoranti
- Persistenza ultimo ristorante usato: `users.ultimo_ristorante_id`
- Admin vede tutti i ristoranti di tutti i clienti
- Multi-ristorante dropdown in Next.js: non ancora implementato (dropdown switch) — pianificato

### Import ricavi multi-ristorante

L'import XLS Passbi ignora le righe di ristoranti diversi da quello attivo, con avviso esplicito all'utente (non le somma erroneamente).

---

## 11. Schema Database

Vedi documento dedicato: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)

### Tabelle principali (riepilogo)

| Tabella | Scopo |
|---------|-------|
| `users` | Utenti: email, password_hash, session_token, pagine_abilitate, nome_referente |
| `ristoranti` | Locali: user_id, nome, P.IVA, attivo |
| `fatture` | Righe fattura (core data): descrizione, prezzo, categoria, deleted_at, needs_review |
| `prodotti_master` | Memoria globale AI: descrizione→categoria, verified, volte_visto |
| `prodotti_utente` | Memoria locale per cliente |
| `classificazioni_manuali` | Override admin con flag `is_dicitura` |
| `margini_mensili` | MOL: input manuali + costi auto + KPI calcolati + centri produzione |
| `ricavi_giornalieri` | Ricavi giorno per giorno (import gestionale o manuale) |
| `ricavi_modalita_mensile` | Override modalità mensile ricavi |
| `ricavi_ragione_sociale_map` | Mapping ragione sociale → ristorante (catene) |
| `fatture_queue` | Buffer webhook Invoicetronic |
| `login_attempts` | Rate limiting persistente |
| `upload_events` | Log upload con status e dettagli |
| `brand_ambigui` | Tracking brand multi-categoria (machine learning) |
| `ai_usage_events` | Ledger costi OpenAI |
| `ai_review_log` | Audit log azioni AI admin (annullabili) |
| `categorie` | Elenco centralizzato 31 categorie |
| `custom_tags` + `custom_tag_prodotti` | Tag personalizzati + associazioni |
| `cache_version` | Versioning cache classificazione cross-process |
| `category_change_log` | Storico append-only modifiche categoria |
| `system_maintenance_status` | Stato retention automatica fatture > 2 anni |
| `assistant_preferences` | Config assistente AI per ristorante (nome referente, topic disabilitati) |
| `daily_briefing_state` | Cache briefing giornaliero |
| `diario_eventi` | Eventi calendario per ristorante (migrata da `note_diario`) |
| `turni_personale` | Turni con ore, extra, costo orario |
| `inventario_voci` | Voci inventario con `valore_totale` GENERATED ALWAYS AS |
| `chat_usage_log` | Contatore domande chat AI per giorno/piano |
| `marketplace_leads` | Lead da form Servizi (coda admin) |
| `system_announcements` | Annunci di sistema (manutenzione, novità) |
| `ricette` | Ricette con ingredienti JSON, foodcost, prezzo vendita |
| `ingredienti_workspace` | Ingredienti manuali (nome, prezzo_per_um, um) |

**Migration SQL:** 68 file legacy (001→068) + migration timestamp-based Supabase (`20260417*.sql` → `20260601*.sql`)

---

## 12. Pannello di Amministrazione

Accessibile solo agli utenti con `is_admin=True`. Next.js: route `/admin/*` gated da layout. FastAPI: guard `_verify_admin` (worker key + bearer token → identità → `is_admin`).

### Funzioni principali

**Clienti (`/admin/clienti`):**
- Lista clienti (ricercabile per nome/email/P.IVA), filtro stato, colonne piano/attività/fatture
- Creazione nuovo cliente: Dialog centrato con form (email, nome, P.IVA, piano, ragione sociale)
- Flusso onboarding GDPR: admin non imposta password → sistema crea account `attivo=False` → email con token 24h → cliente imposta password → account attivo
- Impersonazione: genera session_token per cliente target, salva token admin in backup, banner sticky arancione "Stai impersonando [cliente]"
- Attiva/Disattiva account
- Feature flags per cliente (8 toggle): `analisi_fatture`, `prezzi`, `margini`, `foodcost`, `analisi_e_tag`, `scadenziario`, `blocco_anno_precedente`, `blocco_mesi_precedenti`
- Gestione sedi (add/delete)
- Mapping ragione sociale → ristorante (per catene)
- Trial 7 giorni attivabile per cliente

**Qualità AI (`/admin/qualita-ai` — 3 tab):**
- **Coda review**: righe con `needs_review=True` classificate per confidenza (dicitura/sconto_omaggio/storno/da_verificare); suggerimento categoria automatico + "Accetta" 1-click; bottone "Auto-review" per diciture sicure e sconti/omaggi verificati
- **Memoria globale**: browse paginato `prodotti_master` con ricerca, filtri (verified/non_verified/sospetti — confronta con dizionario/regole forti per trovare divergenze), edit inline + delete
- **Conflitti**: descrizioni in `prodotti_utente` con categoria diversa da `prodotti_master` → "Promuovi" (locale→globale) o "Ignora"
- **Audit log + undo**: tabella `ai_review_log` — ogni azione AI admin è loggata e annullabile

**Sistema/Salute (`/admin/sistema` — 3 tab):**
- **Costi AI**: KPI (totale, vision, categorizzazioni, token) + quota vision oggi per ristorante + dettaglio per cliente. Periodi: 7/30/90 giorni
- **Integrità DB**: scan on-demand (5 check: date invalide, importi estremi >€50k, quantità negative, descrizioni vuote, totali non corrispondenti)
- **Retention**: stato ultimo ciclo automatico (data, righe eliminate, status). Agent notturno: toggle on/off + "Esegui ora"

**Richieste Servizi (`/admin/richieste-servizi`):**
- Coda lead da marketplace (`marketplace_leads`)
- Filtri: nuovo/gestito/archiviato

---

## 13. Calcolo Marginalità e KPI

### Formule MOL

| Voce | Formula |
|------|---------|
| Fatturato Netto | (IVA10 / 1.10) + (IVA22 / 1.22) + altri_ricavi |
| Food Cost % | (Costi F&B Totali / Fatturato Netto) × 100 |
| 1° Margine | Fatturato Netto − Costi F&B Totali |
| 1° Margine % | 1° Margine / Fatturato Netto × 100 |
| MOL | Fatturato Netto − F&B − Spese − Personale |
| MOL % | MOL / Fatturato Netto × 100 |

**Costi F&B:** `costi_fb_auto` (da fatture) + `altri_costi_fb` (input manuale)
**Costi Spese:** `costi_spese_auto` (da fatture) + `altri_costi_spese` (input manuale)
**Costo Personale:** `costo_dipendenti` + `costo_personale_extra` (da `margini_mensili`, recuperabile dai turni)

### Centri di produzione

| Centro | Categorie incluse |
|--------|-------------------|
| FOOD | Carne, Pesce, Latticini, Salumi, Uova, Scatolame, Olio, Secco, Verdure, Frutta, Salse, Prodotti da Forno, Spezie, Sushi |
| BEVERAGE | Acqua, Bevande, Caffè e The, Varie Bar |
| ALCOLICI | Birre, Vini, Distillati, Amari/Liquori |
| DOLCI | Pasticceria, Gelati |
| SHOP | Solo centro di costo (nessun fatturato proprio) |

Ripartizione: solo mensile (%), derivata in giornaliera al momento della visualizzazione — zero tabelle DB extra.

### Soglie KPI

| KPI | 🟢 Eccellente | 🟡 Norma | 🟠 Attenzione | 🔴 Critico |
|-----|-------------|-----------|-------------|-----------|
| Food Cost % | < 28% | 28–33% | 33–38% | > 38% |
| Spese Gen. % | < 15% | 15–22% | 22–28% | > 28% |
| 1° Margine % | > 70% | 62–70% | 55–62% | < 55% |
| MOL % | > 20% | 12–20% | 5–12% | < 5% |

---

## 14. Sistema di Notifiche

### Tipologie (6)

| Tipo | Trigger |
|------|---------|
| Upload con file scartati | File duplicati, falliti o bloccati |
| Alert prezzi > soglia | Prodotto con aumento > `price_alert_threshold` (default 5%) |
| Ricavi mensili mancanti | Mese precedente senza fatturato in `margini_mensili` |
| Costo personale mancante | Mese precedente senza `costo_dipendenti` |
| Esito upload complessivo | Riepilogo per categoria (duplicati, errori) |
| Azione Controllo Prezzi | Link diretto alla sezione Prezzi |

### Caratteristiche

- **Finestra 90 giorni** — scadute storiche non gonfiano il totale "scaduto"
- **Dismiss persistente** — `users.dismissed_notification_ids` (JSONB) con timestamp
- **Scoped per ristorante** — ID stabile con `ristorante_id`
- **Topic disabilitabili** — tranne "upload falliti" (guasti tecnici non disattivabili)
- **Badge unificato** — header/widget/pagina leggono la stessa fonte `notification_inbox.unread`
- **Raggruppamento per origine** — Fatture / Anomalie / Da sistemare / Scadenze
- **Priorità colori** — 🔴 urgenti, 🟡 importanti, 🔵 info

### Next.js v2 (implementata rev. 23)

- Filtri con count per categoria
- CTA inline con azioni dirette
- Badge contatore unificato su header/sidebar/pagina
- Raggruppamento intelligente per origine

---

## 15. Integrazione Invoicetronic — SDI

### Flusso completo

```
Fornitore → SDI → Invoicetronic (codice dest. 7HD37X0)
                       │
                       │ POST HTTPS firmato (HMAC-SHA256)
                       ▼
          Supabase Edge Function: invoicetronic-webhook
          1. Verifica HMAC-SHA256 + anti-replay 5 min
          2. Filtra: solo endpoint="receive" + success
          3. GET api.invoicetronic.com/receive/{id}
             (SSRF whitelist: solo *.invoicetronic.com/.it)
          4. Estrai P.IVA destinatario dall'XML
          5. Lookup P.IVA → tabella ristoranti
          6. INSERT fatture_queue (ON CONFLICT DO NOTHING)
          7. Risponde 200 SEMPRE (evita retry storm)
                       │
                       │ loop 15 secondi
                       ▼
          Railway queue-worker: worker/run.py
          → worker/queue_processor.py
          → purge_processed_xml_content() (GDPR 24h)
          → release_stale_locks() (recovery crash)
          → claim_batch_for_processing() (SELECT FOR UPDATE SKIP LOCKED)
          → estrai_dati_da_xml() → salva_fattura_processata()
          → mark_queue_item_done() + purge XML
```

### Stati `fatture_queue`

`pending` → `processing` → `done` / `retry` / `dead` / `unknown_tenant`

### RPC associate

- `claim_batch_for_processing(p_worker_id, p_batch_size)` — lock atomico
- `mark_queue_item_done(p_queue_id, p_purge_xml)` — status + nullifica XML
- `schedule_retry(p_queue_id, p_error_msg)` — backoff esponenziale
- `purge_processed_xml_content(p_retention_hours)` — GDPR cleanup
- `release_stale_locks(p_timeout_minutes)` — recovery crash worker
- `resolve_unknown_tenant(p_piva)` — rimette in pending record con P.IVA non ancora registrata

---

## 16. FastAPI Worker

Il cuore del backend. Unico punto di accesso per entrambi i frontend (Streamlit via `worker_client.py`, Next.js via route proxy `/api/*`).

### Caratteristiche

- 122+ endpoint REST (aggiornato al 2 giugno 2026)
- Thread pool AnyIO: 100 thread (`WORKER_THREADPOOL_SIZE`)
- 148 endpoint dichiarati `def` (non `async def`) per evitare blocking sull'event loop (fix rev. 22: da 9,5s a 0,21s su `/health` sotto carico)
- 6 endpoint `async` con `await` reali: `_queue_loop`, `_agent_notturno_loop`, `lifespan`, `parse_invoice`, `upload_invoice`, `import_ricavi_xls`
- Multi-worker in produzione: `WORKER_WEB_CONCURRENCY=4` su Railway
- Autenticazione: `WORKER_SECRET_KEY` (64 char, fail-closed senza chiave salvo `WORKER_DEV_MODE=1`)
- Admin guard: `_verify_admin` — worker key + bearer token → utente → `is_admin`

### Endpoint principali (per area)

| Area | Endpoint chiave |
|------|----------------|
| Auth | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `POST /api/auth/reset-request`, `POST /api/auth/reset-confirm` |
| Home | `GET /api/home/briefing`, `GET /api/home/salute`, `GET /api/home/kpi`, `GET/POST /api/home/config` |
| Fatture | `GET /api/fatture`, `POST /api/fatture/upload`, `POST /api/fatture/elimina`, `GET /api/fatture/cestino` |
| Margini | `GET/POST /api/margini/cella`, `GET /api/margini/fatturato-centri-giorni`, `GET /api/margini/costo-personale-turni` |
| Ricavi | `POST /api/ricavi/import-xls`, `POST /api/ricavi/giornaliero`, `POST /api/ricavi/mensile` |
| AI | `POST /api/classify`, `POST /api/parse` |
| Tag | 14 endpoint `/api/tag/*` (CRUD + analytics + suggerimenti) |
| Workspace | 8+ endpoint per foodcost, inventario (7), diario (4), personale (4+) |
| Notifiche | `GET /api/notifiche`, `POST /api/notifiche/{id}/dismiss` |
| Chat | `POST /api/chat` |
| Assistenza | `POST /api/assistenza/lead` |
| Admin | 30+ endpoint `/api/admin/*` (clienti, impersonazione, qualità AI, sistema) |
| Health | `GET /health` |

---

## 17. Chat AI e Marketplace Servizi

### Chat AI

Widget flottante solo sulla Home (bottone a contorno col logo ONEFLUX). Cronologia nella sessione (no DB messaggi).

**Function calling (`gpt-4o-mini`):** 4 strumenti
- `query_costi` — periodo/categoria/fornitore/prodotto
- `query_scadenze` — fatture in scadenza
- `query_margini` — andamento MOL/food cost ultimi 6 mesi
- `confronto_prezzi` — chi fa un prodotto al prezzo migliore

**Limiti domande/giorno per piano:**
| Piano | Limite |
|-------|--------|
| Free | 0 (chat nascosta, 403) |
| Base | 10 |
| Plus | 20 |
| Pro | 30 |

- Costo ~€0,0007/domanda, budget Pro ≤ €3/mese
- Toggle on/off per cliente (`assistant_preferences.chat_ai_enabled`, default true)
- Contatore visibile in Impostazioni, si azzera a mezzanotte
- 429 al limite del piano, 403 se free

**Proattività:** messaggio di benvenuto + 4 domande suggerite (chip) all'apertura.

**Anonimizzazione:** nomi prodotti → segnaposto prima di inviare a OpenAI.

### Marketplace Servizi (`/assistenza`)

Catalogo statico in `lib/assistenza.ts` (editabile in 1 file). 6 servizi:
1. Consulenza F&B
2. Studio menù (ricerca di zona)
3. Comparatori utenze/POS
4. Rifacimento sito web
5. Gestione social e foto
6. Analisi listini fornitori

**Contatto:** form "Richiedi info" → lead in `marketplace_leads` → coda Admin "Richieste servizi". Alternativa: WhatsApp diretto. Pagamenti esterni all'app (no Stripe).

---

## 18. PWA Mobile

Route group `(mobile)` servito su `/m`. Layout dedicato (no sidebar — bottom nav 5 tab).

**5 sezioni:**
- **Oggi** — briefing AI giornaliero
- **Avvisi** — notifiche (riusa `NotificheList` desktop)
- **Diario** — eventi calendario
- **Turni** — turni personale (modifica preservando costo/extra)
- **Assistente** — chat AI

**Caratteristiche:**
- Installabile: `manifest.json` (start_url `/m`, standalone, icone maskable 192/512), service worker manuale network-first + `offline.html`, `PwaRegister` (solo produzione)
- Banner installazione: Android intercetta `beforeinstallprompt` (1 tap); iOS mostra istruzioni "Condividi → Aggiungi a Home"
- Redirect mobile→`/m` lato client (`MobileRedirect`, esclude `/admin`; voce "Vista completa" lo disattiva)
- Zero nuovi endpoint backend: riusa tutti i proxy esistenti
- Niente azioni pesanti da mobile (upload, costo orario) — restano su desktop

---

## 19. Testing e Qualità

### Suite di test (760+ test pytest)

| File | Copertura |
|------|-----------|
| `test_trial.py` | Gestione trial, attivazione, scadenza |
| `test_text_utils.py` | Normalizzazione, estrazione fornitore, pulizia |
| `test_piva_validator.py` | Validazione P.IVA (Luhn), normalizzazione |
| `test_notification_service.py` | Notifiche in-app: upload, prezzi, dismiss, mensili |
| `test_ai_service.py` | Classificazione AI, memoria 3 livelli, quarantena |
| `test_validation.py` | Diciture, sconti, integrità fattura |
| `test_constants.py` | Integrità categorie, regex compilate, soglie KPI |
| `test_db_service.py` | Alert variazioni prezzo, normalizzazione categorie |
| `test_auth_service.py` | Login, rate limiting, GDPR password, reset, consenso |
| `test_invoice_service.py` | Parsing XML, P7M, encoding, tipo documento |
| `test_formatters.py` | Formattazione numeri, base64, prezzo standard |

Fixtures (`conftest.py`): mock completi Supabase e OpenAI — nessun test tocca servizi esterni.

```bash
pytest tests/ -v --tb=short
pytest tests/ --cov=services --cov=utils --cov-report=html
```

### Qualità codice Next.js

- `tsc --noEmit` — type check completo
- ESLint — lint
- `next build` — build completo con type-check
- OpenAPI drift check: `python scripts/export_openapi.py --check-drift` dopo ogni modifica a `fastapi_worker.py`

---

## 20. Deploy e Infrastruttura

Vedi documento dedicato: [DEPLOY_INFRASTRUTTURA.md](DEPLOY_INFRASTRUTTURA.md)

### Riepilogo

| Componente | Piattaforma | URL |
|-----------|------------|-----|
| Next.js frontend | Vercel | nuovo.oneflux.it |
| Streamlit (legacy) | Railway / Streamlit Cloud | app.oneflux.it |
| FastAPI Worker | Railway | Railway interno + URL pubblico |
| Queue Worker | Railway | Nessun URL pubblico |
| Database | Supabase | vthikmfpywilukizputn.supabase.co |
| Edge Function | Supabase | Deno serverless EU |

---

## 21. Monitoraggio e Logging

### Uptime Check

GitHub Actions `uptime_check.yml`: curl ogni 5 min su `app.oneflux.it`; HTTP ≠ 200 → email alert via Brevo.

### Worker fatture_queue (fallback)

GitHub Actions `queue-worker.yml`: solo trigger manuale (fallback di emergenza, non su schedule automatico — il primario è Railway).

### Logging applicativo

| Parametro | Valore |
|-----------|--------|
| Handler | `RotatingFileHandler` |
| Max size | 50 MB per file |
| Backup | 10 file (~550 MB max) |
| Livello | INFO in produzione |
| Logger modulari | `app`, `ai`, `auth`, `invoice`, `db`, `admin`, `email`, `margine_service`, `fastapi_worker`, `worker.queue_processor` |

**Regola**: nessun PII nei log. Email troncate, password mai loggate, user_id nei log operativi.

### Monitoring strategy (nessun Sentry)

Script on-demand da implementare progressivamente:
`/oneflux-health` · `/oneflux-costs` · `/oneflux-usage` · `/oneflux-anomalies` · `/oneflux-tests` · `/oneflux-backup`

---

## 22. Compliance GDPR

**Titolare del trattamento:** Recoma System S.r.l., P.IVA IT09599210961, referente Mattia D'Avolio, md@oneflux.it

### Documenti legali

- **Privacy & Cookie Policy v4.0** — `/privacy` (Next.js) + `privacy_policy.py` (Streamlit)
- **Terms of Service** — `/termini` (Next.js) + sezione in `privacy_policy.py`
- Base giuridica: Contratto Art. 6.1.b per il servizio, consenso per marketing

### Data retention

- Fatture nel DB finché l'utente le elimina (soft-delete `deleted_at`)
- Cestino: 30 giorni
- Retention automatica: fatture > 2 anni eliminate dal worker (`system_maintenance_status`)
- XML Invoicetronic: purge GDPR dopo 24h (`purge_processed_xml_content`)

### Diritti utente

- **Art. 17 (Oblio)**: "Elimina Account" self-service — eliminazione permanente a cascata su 16+ tabelle
- **Art. 20 (Portabilità)**: export JSON da Impostazioni (10+ tabelle)
- **Art. 7 (Consenso)**: checkbox obbligatorio all'onboarding; `privacy_accepted_at` scritto solo con consenso reale

### Cookie

- Banner dismissibile (no cookie-wall — cookie solo tecnici, Provvedimento Garante 10/06/2021)
- Cookie HttpOnly (Next.js): sessione, impersonazione
- Cookie impersonazione: flag tecnico `"1"` HttpOnly — email derivata server-side (no PII in chiaro in JS)
- Nessun cookie di tracking o marketing

### Note legale

"Non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014"

---

## 23. Troubleshooting

Vedi documento dedicato: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### Problemi comuni

| Problema | Causa / Soluzione |
|----------|-------------------|
| Pagina bianca | Supabase in pausa (free tier 7gg inattività) → riattivare dal pannello |
| Fattura "P.IVA non corrispondente" | P.IVA cedente ≠ ristorante attivo → cambiare ristorante |
| Fattura "già caricata" | Dedup su `file_origine + user_id + ristorante_id` |
| AI classifica male | Correggere manualmente → sistema apprende in memoria locale/globale |
| Sessione scaduta | Token 30gg o auto-logout 8h inattività → svuotare cache browser |
| Fatture Invoicetronic non appaiono | Verificare `fatture_queue.status` → se `unknown_tenant` aggiungere ristorante con P.IVA corretta e chiamare `resolve_unknown_tenant(piva)` |
| Worker lento | Verificare `GET /health` → se 9+ secondi, probabile blocco event loop (async su def) |

---

## 24. Limiti Tecnici

| Limite | Valore |
|--------|--------|
| Max file per upload | 100 file / 200 MB totale / 50 MB per P7M |
| Max righe per utente | 100.000 |
| Chiamate AI classificazione/giorno | 1.000 per ristorante |
| Domande chat AI/giorno | 0–30 (per piano) |
| Batch AI | 50 articoli per chiamata |
| TTL cache fatture | 120 s |
| TTL cache margini | 300 s |
| TTL sessione cookie | 30 giorni |
| Inattività sessione | 8 ore |
| Lockout login | 15 min dopo 5 tentativi |
| Cooldown reset password | 5 minuti |
| Descrizione max DB | 500 caratteri |
| Descrizione max AI input | 300 caratteri |
| Paginazione DB | 1.000 righe per pagina |
| Log rotation | 50 MB × 10 backup |
| Upload XLS ricavi | Max 10 MB, timeout 30s |
| Finestra notifiche scadute | 90 giorni |
| XML Invoicetronic purge | 24h (GDPR) |
| Anti-replay webhook | 5 minuti |

---

*Documentazione tecnica completa v6.0 — 5 Giugno 2026*
*Per lo stato dettagliato della migrazione Next.js: [MIGRAZIONE_NEXTJS.md](MIGRAZIONE_NEXTJS.md)*
*Documento di riferimento vision/piano: `ONEFLUX_MASTER.md`*
