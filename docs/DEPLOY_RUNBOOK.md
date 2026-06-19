# ONEFLUX — Deploy Runbook (Railway)

Procedura per ricreare/verificare i servizi Railway da zero. Fonte di verità del
deploy: questo file + `railway.toml` + `docker/Dockerfile`. Aggiornato 19/06/2026.

## Topologia

- **Frontend** → Next.js su **Vercel** (`app.oneflux.it`). Non su Railway. Streamlit eliminato.
- **Railway** → progetto `ingenious-fascination`, env `production`. Una sola immagine
  (`docker/Dockerfile`) alimenta **2 servizi**, distinti dallo Start Command:

| Servizio | Start Command | Espone HTTP | Ruolo |
|---|---|---|---|
| `worker` | `python -m services.fastapi_worker` | sì (`/health`, `/api/*`) | API: classify/parse, dati Home/Margini, webhook |
| `queue-worker` | `python worker/run.py` | no | Ingest coda fatture Invoicetronic |

Entrambi buildano da `docker/Dockerfile`. Il comando arriva all'entrypoint come `$@`
ed è eseguito; senza comando l'entrypoint **fallisce esplicito** (niente più default
Streamlit). L'entrypoint allinea `WORKER_PORT=$PORT` così l'API ascolta sulla porta
instradata da Railway.

## Variabili d'ambiente

### Comuni (obbligatorie su entrambi — l'entrypoint fail-close se mancano)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (service_role: bypassa RLS, `auth.uid()` è sempre NULL)
- `OPENAI_API_KEY`

### Solo `worker` (FastAPI)
- `PORT=8000` (iniettata da Railway; target della porta del servizio)
- `WORKER_WEB_CONCURRENCY=4` (numero processi uvicorn; default 1 in locale)
- `WORKER_SECRET_KEY` (gate route `/api/*`; il worker è fail-closed senza, salvo `WORKER_DEV_MODE=1`)
- `INVOICETRONIC_WEBHOOK_SECRET` (verifica firma webhook)
- `SUPABASE_ANON_KEY`
- `ENABLE_INLINE_QUEUE_PROCESSOR=0` (la coda la processa il servizio dedicato, non l'API)
- Brevo: `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`
- `ADMIN_EMAILS`, `CHAT_MODEL`

### Solo `queue-worker`
- `WORKER_ENABLED=1` — **killswitch**. A `0` la coda non viene drenata (causa incidente
  9-11/06: incassi clienti spariti per giorni). Il monitor `ricavi_queue_monitor.yml`
  allerta se la coda resta bloccata.
- `WORKER_POLL_INTERVAL_SECONDS` (default 15), `WORKER_ERROR_BACKOFF_SECONDS`,
  `WORKER_MAX_BACKOFF_SECONDS`, `WORKER_ID_PREFIX`
- Healthcheck del servizio: **DISABILITATO** (non espone HTTP).

## Ricreare un servizio da zero

1. Railway → progetto `ingenious-fascination` → New Service → da repo GitHub `main`.
2. Settings → Build: il `railway.toml` punta già a `docker/Dockerfile`.
3. Settings → Deploy → **Start Command**: imposta quello del servizio (tabella sopra).
   Questo passo è OBBLIGATORIO: senza, l'entrypoint fallisce di proposito.
4. Variables: copia il set del servizio (sopra). Mai esporre le chiavi lato client.
5. Per `queue-worker`: disabilita l'healthcheck HTTP.
6. Deploy. Verifica:
   - `worker`: log `Uvicorn running on http://0.0.0.0:8000`, poi `GET /health` → 200.
   - `queue-worker`: log di polling coda; nessun `WORKER_ENABLED` mancante.

## Verifica rapida stato (Railway CLI)

```powershell
railway whoami
railway status
railway variables --service worker --kv         # nomi+valori var
railway logs --service worker                    # conferma comando avviato
railway logs --service queue-worker
```

## Note

- Push su `main` → Vercel (frontend) + Railway (entrambi i servizi) rid/eployano auto.
- `docker/docker-compose*.yml` sono per sviluppo locale/VPS; non sono il path Railway.
- Deploy SOLO fuori orario lavorativo (clienti in uso di giorno).
