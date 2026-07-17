# ONEFLUX — Infrastruttura

**Aggiornamento:** 17 luglio 2026 — verificato contro il repo.

**Cosa c'è qui:** la mappa di cosa gira dove, e perché.
**Cosa NON c'è qui:** la procedura operativa per creare/verificare i servizi
Railway e il contratto completo delle variabili d'ambiente — quelli stanno in
`docs/DEPLOY_RUNBOOK.md`, che è l'unico autorevole (aveva finito per divergere
da questo file, ora la duplicazione è rimossa).

---

## 1. Topologia

```
                  Vercel — app.oneflux.it
                  Next.js 16 (App Router)
                          │
                          │  proxy /api/*  (header X-Worker-Key)
                          ▼
        Railway — progetto ingenious-fascination
        ┌──────────────────────┬──────────────────────┐
        │ worker               │ queue-worker         │
        │ FastAPI, porta 8000  │ nessuna porta        │
        │ concurrency 4        │ loop 24/7, poll 15s  │
        └──────────┬───────────┴──────────┬───────────┘
                   │                      │
                   ▼                      ▼
              Supabase — vthikmfpywilukizputn
              PostgreSQL 15, EU Frankfurt
              Edge Functions (Deno):
                invoicetronic-webhook   (HMAC)
                ricavi-email-webhook
```

**Una sola immagine Docker** (`docker/Dockerfile`) alimenta entrambi i servizi
Railway; li distingue **solo lo Start Command**. Senza comando l'entrypoint
fallisce di proposito (fail-closed) — non esiste più alcun default Streamlit.

---

## 2. Perché è diviso così

**Frontend separato dal calcolo.** Vercel disegna, il worker calcola. Le route in
`apps/web/src/app/api/**` sono proxy deliberatamente stupidi: un solo posto dove
la logica di business può divergere.

**API separata dalla coda.** Un ingest di 400 fatture non deve rallentare la Home
di chi sta usando l'app. `ENABLE_INLINE_QUEUE_PROCESSOR=0` sul `worker` garantisce
che la coda la dreni solo il servizio dedicato.

**`WORKER_ENABLED` è un killswitch.** A `0` il queue-worker non drena la coda: è
successo il 9-11/06 e gli incassi dei clienti sono spariti per giorni. Il monitor
`ricavi_queue_monitor.yml` allerta se la coda resta ferma.

**Middleware a blacklist invertita.** Protegge tutto tranne login,
forgot-password e reset-password. Motivo: se aggiungi una pagina e dimentichi di
proteggerla, resta protetta comunque. Il default sicuro è "chiuso".

---

## 3. Piani e vincoli

| Servizio | Piano | Vincolo che conta |
|---|---|---|
| Vercel | Pro | — |
| Railway | Hobby (~$9/mese) | **1 container**: sotto contesa la latenza sale (vedi piano stabilità worker) |
| Supabase | Free | Niente PITR nativo → backup via `pg_dump` (`db_backup.yml`). Niente leaked-password protection. Pausa dopo 7gg di inattività |
| Brevo | Free | 300 email/giorno |
| OpenAI | Pay-per-use | ~€0,30/cliente/mese |

Il piano Supabase Pro è stato **volutamente rimandato**: il backup è stato risolto
in modo indipendente, e non vale $25/mese per la sola leaked-password protection.

---

## 4. GitHub Actions (10 workflow reali)

| Workflow | Ruolo |
|---|---|
| `tests.yml` | Suite Python + Deno in CI |
| `uptime_check.yml` | Curl su `app.oneflux.it` ogni 5 min → alert |
| `worker_latency_check.yml` | Allerta se il worker rallenta |
| `keepalive_worker.yml` | Tiene sveglio il worker |
| `ricavi_queue_monitor.yml` | Allerta se la coda ricavi si blocca |
| `db_backup.yml` | `pg_dump` giornaliero (sostituisce il PITR assente su Free) |
| `openapi-drift.yml` | Fallisce se lo schema OpenAPI diverge dal codice |
| `requirements-consistency.yml` | Coerenza dipendenze |
| `queue-worker.yml` | Drain manuale della coda (solo `workflow_dispatch`, se Railway è down) |
| `deploy-vercel.yml` | Deploy frontend |

> `openapi-drift.yml` è lo stesso principio di `tests/test_documentazione_onesta.py`:
> far fallire il CI quando una descrizione smette di corrispondere alla realtà,
> invece di sperare che qualcuno se ne accorga.

---

## 5. Deploy

Push su `main` → Vercel e Railway ridispiegano **automaticamente** entrambi.

> **Deploy solo fuori orario** (sera/notte/mattina presto): i clienti usano l'app
> durante il giorno. Dopo un deploy che tocca il briefing, svuota la cache della
> sede di test.

Procedura completa, variabili per servizio, ricreazione da zero:
`docs/DEPLOY_RUNBOOK.md`.

---

## 6. Nota sui nomi delle variabili

`SUPABASE_KEY` esiste ancora come fallback in `services/__init__.py` e contiene
la **`service_role_key`**, nonostante il nome. Il nome è un residuo storico
confuso: se lo leggi da qualche parte, non è la anon key.

---

## 7. Se il DB è in pausa (piano Free, 7gg di inattività)

Dashboard Supabase → progetto `vthikmfpywilukizputn` → **Restore project** → ~2 min.

---

*Monitoring e incidenti: `DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md`.*
