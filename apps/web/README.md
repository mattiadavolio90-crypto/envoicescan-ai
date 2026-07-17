# ONEFLUX — Frontend Next.js

Frontend di produzione di ONEFLUX (SaaS analisi costi ristoranti), servito su
`app.oneflux.it` via Vercel. Next.js 16 (App Router) + Tailwind v4 + shadcn/ui v4.

Consuma le API del worker FastAPI (`services/fastapi_worker.py`, root del
repo) tramite proxy route in `src/app/api/*` — questo frontend non esegue
logica di business pesante.

## Setup locale

```bash
npm install
npm run dev          # :3000
```

Serve anche il worker FastAPI in esecuzione (`python -m services.fastapi_worker`,
root del repo) — vedi `DEV_SERVICES_GUIDE.md` per l'avvio di tutti i servizi
locali (worker, queue-worker, variabili d'ambiente).

## Riferimenti

- `CLAUDE.md` (root) — architettura, regole di dominio, convenzioni
- `DOCUMENTAZIONE/DOC COMPLETA/DOCUMENTAZIONE_COMPLETA.md` — documentazione tecnica completa
- `DEV_SERVICES_GUIDE.md` — guida servizi locali
