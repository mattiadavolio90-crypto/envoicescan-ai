# ONEFLUX — Deploy e Infrastruttura

Versione: 6.0 | Aggiornamento: 5 Giugno 2026

---

## 1. Panoramica Infrastruttura

```
                    ┌─────────────────────────┐
                    │    Vercel                │
                    │    nuovo.oneflux.it      │
                    │    Next.js 16.2.6        │
                    └──────────┬──────────────┘
                               │ HTTP proxy /api/*
         ┌─────────────────────┼─────────────────────────┐
         │                     │                         │
         │    ┌────────────────▼────────────────────┐    │
         │    │    Railway (ingenious-fascination)  │    │
         │    │                                     │    │
         │    │  ┌─────────────────────────────┐   │    │
         │    │  │ service: worker              │   │    │
         │    │  │ FastAPI + Uvicorn            │   │    │
         │    │  │ PORT 8000 (interna)          │   │    │
         │    │  │ WORKER_WEB_CONCURRENCY=4     │   │    │
         │    │  └─────────────────────────────┘   │    │
         │    │                                     │    │
         │    │  ┌─────────────────────────────┐   │    │
         │    │  │ service: queue-worker        │   │    │
         │    │  │ python worker/run.py         │   │    │
         │    │  │ loop 24/7, ogni 15 secondi   │   │    │
         │    │  │ nessuna porta pubblica       │   │    │
         │    │  └─────────────────────────────┘   │    │
         │    │                                     │    │
         │    │  ┌─────────────────────────────┐   │    │
         │    │  │ service: ohyeah (legacy)     │   │    │
         │    │  │ Streamlit + FastAPI locale   │   │    │
         │    │  │ app.oneflux.it               │   │    │
         │    │  └─────────────────────────────┘   │    │
         │    └────────────────────────────────────┘    │
         │                     │                         │
         │    ┌────────────────▼────────────────────┐   │
         │    │    Supabase                         │   │
         │    │    vthikmfpywilukizputn.supabase.co │   │
         │    │    PostgreSQL 15, EU Frankfurt       │   │
         │    │    Edge Functions (Deno)             │   │
         │    └─────────────────────────────────────┘   │
         │                                               │
         └───────────────────────────────────────────────┘
```

---

## 2. Vercel — Next.js Frontend

| Parametro | Valore |
|-----------|--------|
| Piattaforma | Vercel |
| Piano | Free → Pro €20/mese quando serve |
| URL produzione | `nuovo.oneflux.it` |
| Branch | `main` → deploy automatico |
| Framework | Next.js 16.2.6 con Turbopack |
| Region | Edge (auto) |

### Variabili d'ambiente Vercel

```
WORKER_BASE_URL=https://[railway-worker-url].up.railway.app
WORKER_SECRET_KEY=[64 char]
NEXT_PUBLIC_APP_URL=https://nuovo.oneflux.it
```

### Proxy routes

Ogni route in `apps/web/src/app/api/*/route.ts` proxia al FastAPI Worker:

```typescript
// Esempio: apps/web/src/app/api/home/briefing/route.ts
import { workerGet } from "@/lib/worker"

export async function GET(req: Request) {
    return workerGet(req, "/api/home/briefing")
}
```

`lib/worker.ts` (`workerGet<T>`) centralizza cookie + header `X-Worker-Key` + `res.ok` + error handling.

### Middleware (proxy.ts)

Protegge tutte le route tranne le 3 pubbliche (login, forgot-password, reset-password):
- Blacklist invertita: protegge tutto tranne i percorsi pubblici
- Redirect a edge senza colpire Railway (risparmio di latenza)
- Logica auth dal middleware, non duplicata in ogni page

---

## 3. Railway — FastAPI Worker e Queue Worker

### Service: `worker` (FastAPI)

| Parametro | Valore |
|-----------|--------|
| Entry point | `uvicorn services.fastapi_worker:app` |
| Dockerfile | `docker/Dockerfile` (percorso in `railway.toml`) |
| Porta | 8000 (interna alla rete Railway) |
| URL pubblico | `https://[nome].up.railway.app` |
| Concorrenza | `WORKER_WEB_CONCURRENCY=4` (multi-processo) |
| Threadpool | `WORKER_THREADPOOL_SIZE=100` (AnyIO) |

### Service: `queue-worker` (Invoicetronic)

| Parametro | Valore |
|-----------|--------|
| Entry point | `python worker/run.py` |
| Modalità | Loop continuo 24/7 |
| Intervallo poll | 15 secondi |
| Porta | Nessuna (no HTTP) |
| `ENABLE_INLINE_QUEUE_PROCESSOR` | `0` (disabilitato nel service `worker`) |

### Service: `ohyeah` (Streamlit legacy)

| Parametro | Valore |
|-----------|--------|
| Entry point | `streamlit run app.py` |
| URL | `app.oneflux.it` |
| Stato | Attivo fino al completamento Fase 10 |

### `railway.toml`

```toml
[build]
dockerfilePath = "docker/Dockerfile"

[deploy]
startCommand = "uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000"
```

### Variabili d'ambiente Railway (service `worker`)

```
SUPABASE_URL=https://vthikmfpywilukizputn.supabase.co
SUPABASE_SERVICE_ROLE_KEY=[service role key]
OPENAI_API_KEY=sk-...
WORKER_SECRET_KEY=[64 char, identico a Vercel]
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=noreply@oneflux.it
BREVO_SENDER_NAME=ONEFLUX
WORKER_WEB_CONCURRENCY=4
WORKER_THREADPOOL_SIZE=100
ENABLE_INLINE_QUEUE_PROCESSOR=0
ADMIN_EMAILS=md@oneflux.it
```

### Variabili d'ambiente Railway (service `queue-worker`)

```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
INVOICETRONIC_API_KEY=...
OPENAI_API_KEY=...
WORKER_BATCH_SIZE=10
WORKER_XML_RETENTION_HOURS=24
WORKER_STALE_LOCK_MINUTES=10
WORKER_SECRET_KEY=[identico]
```

---

## 4. Supabase — Database e Edge Functions

### Database

| Parametro | Valore |
|-----------|--------|
| Piano | Free → Pro €25/mese SOLO se free dà problemi reali |
| Region | EU Frankfurt |
| PostgreSQL | v15 |
| RLS | Attivo su tutte le tabelle |
| Backup | Automatici giornalieri (piano free) |
| Limite storage | 500 MB |
| Limite transfer | 2 GB |
| Pausa | Dopo 7 giorni di inattività (free tier) |
| Accesso | Solo via `service_role_key` (bypass RLS) |
| Progetto | `vthikmfpywilukizputn.supabase.co` |

### Edge Function: `invoicetronic-webhook`

| Parametro | Valore |
|-----------|--------|
| Runtime | Deno (TypeScript) |
| File | `supabase/functions/invoicetronic-webhook/index.ts` |
| Deploy | `supabase functions deploy invoicetronic-webhook --no-verify-jwt` |
| Sviluppo locale | `.\scripts\dev-serve.ps1` (porta 54321) |
| Test locale | `.\scripts\dev-serve.ps1 -Test` |

### Secrets Edge Function

```bash
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=[...]
supabase secrets set INVOICETRONIC_WEBHOOK_SECRET=[...]
supabase secrets set INVOICETRONIC_API_KEY=[...]
# SUPABASE_URL è iniettato automaticamente
```

### Checklist pausa Supabase

Se il database è in pausa (free tier, 7gg inattività):
1. Accedere a [supabase.com/dashboard](https://supabase.com/dashboard)
2. Trovare il progetto `vthikmfpywilukizputn`
3. Cliccare "Restore project"
4. Attendere ~2 minuti per il riavvio

---

## 5. Docker

File nella cartella `docker/`:

| File | Uso |
|------|-----|
| `Dockerfile` | Build immagine unica (Streamlit + FastAPI worker) |
| `docker-compose.yml` | Stack sviluppo locale completo |
| `docker-compose.prod.yml` | Stack produzione (porta worker non esposta) |
| `docker-entrypoint.sh` | Script avvio container |

### `docker-compose.prod.yml` — 3 service

```yaml
services:
  ohyeah:       # Streamlit, porta 8501 esposta
  worker:        # FastAPI, porta 8000 NON esposta (solo rete interna)
  queue-worker:  # Worker asincrono, nessuna porta
```

**Comunicazione:** `WORKER_BASE_URL=http://worker:8000` — le route `/api/classify` e `/api/parse` raggiungibili solo dall'interno della rete Docker privata.

### Sviluppo locale

```powershell
# Stack completo locale
docker-compose -f docker/docker-compose.yml up

# Solo FastAPI worker (porta 8003)
uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8003

# Solo Streamlit
streamlit run app.py

# Solo Next.js (in apps/web/)
npm run dev   # Turbopack attivo automaticamente
```

---

## 6. Secrets Management

### Streamlit Cloud

File `.streamlit/secrets.toml` (non versionato):

```toml
SUPABASE_URL = "https://vthikmfpywilukizputn.supabase.co"
SUPABASE_KEY = "eyJhbG..."            # service_role_key
OPENAI_API_KEY = "sk-..."
WORKER_BASE_URL = "http://worker:8000"
ADMIN_EMAILS = "md@oneflux.it"
WORKER_SECRET_KEY = "[64 char]"

[brevo]
api_key = "xkeysib-..."
sender_email = "noreply@oneflux.it"
sender_name = "ONEFLUX"
reply_to_email = "md@oneflux.it"
reply_to_name = "ONEFLUX Support"
```

### GitHub Actions (Settings → Secrets → Actions)

```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
INVOICETRONIC_API_KEY
OPENAI_API_KEY
BREVO_API_KEY
```

### Regole fondamentali sui secrets

- Mai hardcoded nel codice
- Mai nel repository Git
- `SUPABASE_KEY` nel codice = sempre `service_role_key` (non la anon key)
- `WORKER_SECRET_KEY`: identico su Railway (worker) e Vercel (Next.js)

---

## 7. Variabili d'Ambiente — Riferimento Completo

| Variabile | Dove | Descrizione |
|-----------|------|-------------|
| `SUPABASE_URL` | Tutti i service | URL progetto Supabase |
| `SUPABASE_KEY` | Streamlit | `service_role_key` (confusamente chiamata "KEY" in Streamlit) |
| `SUPABASE_SERVICE_ROLE_KEY` | Railway, GitHub, Supabase EF | `service_role_key` |
| `OPENAI_API_KEY` | Worker, Streamlit, GitHub | Chiave API OpenAI |
| `WORKER_BASE_URL` | Streamlit, Next.js | URL FastAPI worker |
| `WORKER_SECRET_KEY` | Worker (Railway), Next.js (Vercel) | Chiave 64 char, fail-closed |
| `WORKER_DEV_MODE` | Solo sviluppo locale | Se `1`, worker si avvia senza `WORKER_SECRET_KEY` |
| `WORKER_WEB_CONCURRENCY` | Railway service worker | Numero processi Uvicorn (prod: 4) |
| `WORKER_THREADPOOL_SIZE` | Railway service worker | Thread pool AnyIO (default: 100) |
| `ENABLE_INLINE_QUEUE_PROCESSOR` | Railway service worker | `0` = delegato al queue-worker separato |
| `INVOICETRONIC_API_KEY` | Worker, GitHub, Supabase EF | API Key Invoicetronic |
| `INVOICETRONIC_WEBHOOK_SECRET` | Supabase EF | Segreto firma HMAC webhook |
| `BREVO_API_KEY` | Worker (Railway) | API key Brevo SMTP |
| `BREVO_SENDER_EMAIL` | Worker (Railway) | Email mittente |
| `BREVO_SENDER_NAME` | Worker (Railway) | Nome mittente |
| `WORKER_BATCH_SIZE` | queue-worker | Record per ciclo (default: 10) |
| `WORKER_XML_RETENTION_HOURS` | queue-worker | Ore prima del purge GDPR (default: 24) |
| `WORKER_STALE_LOCK_MINUTES` | queue-worker | Timeout lock su crash (default: 10) |
| `ADMIN_EMAILS` | Streamlit | Email admin (separati da virgola, lowercase) |

---

## 8. GitHub Actions

### Uptime Check (automatico ogni 5 min)

File: `.github/workflows/uptime_check.yml`

```yaml
on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:
```

- Curl su `https://app.oneflux.it/`
- HTTP ≠ 200 → email alert via Brevo a `md@oneflux.it`

### Worker fallback manuale

File: `.github/workflows/queue-worker.yml`

- Solo `workflow_dispatch` (trigger manuale)
- Da usare solo se il service Railway `queue-worker` è down
- Specifica `batch_size` personalizzato per drain forzato della coda

---

## 9. Domini e DNS

| Dominio | Destinazione | Stato |
|---------|-------------|-------|
| `nuovo.oneflux.it` | Vercel (Next.js) | Attivo — clienti di test |
| `app.oneflux.it` | Railway (Streamlit) | Attivo — clienti operativi |
| `old.oneflux.it` | Railway (Streamlit) | Pianificato per Fase 10 (backup 30gg) |

**Fase 10 (switch DNS):**
1. `app.oneflux.it` → punterà a Next.js (Vercel)
2. `old.oneflux.it` → punterà a Streamlit (backup 30 giorni)
3. Dopo 30 giorni senza problemi → Streamlit spento (Fase 11)

---

## 10. Monitoring

### Uptime

GitHub Actions ogni 5 minuti. Email alert automatica su down.

### Logging applicativo

`RotatingFileHandler`, 50 MB × 10 backup (~550 MB max), livello INFO.

Logger modulari: `app`, `ai`, `auth`, `invoice`, `db`, `admin`, `email`, `margine_service`, `fastapi_worker`, `worker.queue_processor`

### Monitoring strategy (nessun Sentry — filosofia semplicità)

Script on-demand da implementare progressivamente:
- `/oneflux-health` — stato generale
- `/oneflux-costs` — costi AI e infrastruttura
- `/oneflux-usage` — utilizzo per cliente
- `/oneflux-anomalies` — anomalie nei dati
- `/oneflux-tests` — esecuzione test
- `/oneflux-backup` — stato backup DB

---

## 11. Comandi di Deploy e Sviluppo

```powershell
# Test suite completa
pytest tests/ -v --tb=short

# Check drift OpenAPI (dopo ogni modifica a fastapi_worker.py)
python scripts/export_openapi.py --check-drift

# Verifica oggetti DB da migration legacy
python tools/check_migrations.py

# Deploy Edge Function Supabase
.\scripts\dev-serve.ps1 -Deploy

# Test Edge Function locale
.\scripts\dev-serve.ps1        # Terminale 1 — webhook handler
.\scripts\dev-serve.ps1 -Test  # Terminale 2 — esegue test.ts

# Avvia worker FastAPI locale (porta 8003)
$env:WORKER_DEV_MODE = "1"
uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8003

# Avvia worker coda locale
$env:SUPABASE_URL = "..."
$env:SUPABASE_SERVICE_ROLE_KEY = "..."
python worker/run.py

# Next.js sviluppo locale
cd apps/web
npm run dev      # Turbopack attivo

# Next.js build e type-check
cd apps/web
npm run build
npx tsc --noEmit
```

---

*Deploy e Infrastruttura v6.0 — 5 Giugno 2026*
