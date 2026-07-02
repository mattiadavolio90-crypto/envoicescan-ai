# RUNBOOK INCIDENTI — ONEFLUX

> Cosa fare, in che ordine, quando arriva un alert (Telegram/email) o un cliente
> segnala "l'app non va". Scritto sulla base dell'incidente reale del 2/7/2026
> (vedi `PIANO_STABILITA_WORKER_2026-07-02.md` per l'analisi completa).

---

## 0. Da dove arriva l'alert e cosa significa

| Alert | Sorgente | Significa |
|---|---|---|
| 🚨 "ONEFLUX è offline" | `uptime_check.yml` (ogni 15 min) | Vercel/frontend non risponde HTTP 200 |
| ⚠️ "worker LENTO" | `worker_latency_check.yml` (ogni 10 min) | Il worker Railway risponde ma sopra soglia (3s su `/health`, che non tocca nemmeno il DB) — i clienti probabilmente vedono già "Servizio non raggiungibile" |
| 🚨 "Coda ricavi bloccata" | `ricavi_queue_monitor.yml` (ogni ora) | Il queue-worker non sta consumando `ricavi_email_queue` — gli incassi non entrano in app |
| 🤖 "Agent notturno completato/FALLITO" | agent notturno (worker, ogni notte) | Riepilogo categorizzazione automatica; se FALLITO è un'anomalia da controllare |

**Canali**: email (`md@oneflux.it`, via Brevo) + Telegram (bot `@Oneflux_alert_bot`). Ridondanti: se uno dei due è giù, l'altro arriva comunque.

---

## 1. PRIMO STEP SEMPRE — capire se è down o solo lento

```bash
curl -sL -o /dev/null -w "vercel: %{http_code} %{time_total}s\n" https://app.oneflux.it/login
curl -sL -o /dev/null -w "worker: %{http_code} %{time_total}s\n" https://worker-production-a552.up.railway.app/health
```

- **Entrambi veloci (<1s) e 200** → probabilmente falso allarme/blip transitorio già rientrato. Verifica comunque il punto 4 (metriche worker) prima di chiudere.
- **Vercel 200 ma worker lento/errore** → il problema è il worker Railway. Vai al punto 2.
- **Vercel non risponde** → problema Vercel/DNS, molto più raro. Controlla [Vercel Dashboard](https://vercel.com) → Deployments, l'ultimo deploy potrebbe essere fallito.

---

## 2. Il worker è lento o giù — diagnosi in ordine di probabilità

Basato sull'incidente reale: **quasi sempre è saturazione, non crash**.

### 2a. Il worker sta crashando/riavviandosi? (raro)
```bash
railway logs --service worker
```
Cerca: `OOM`, `killed`, `SIGTERM`, `Traceback`, righe che si fermano di colpo.
- Se **sì** → `railway redeploy --service=worker --yes` (riavvio pulito), poi torna al punto 1 per confermare.

### 2b. Il worker è sano ma sovraccarico? (caso più probabile)
Controlla la spia integrata: **Admin → Clienti → scheda "Salute worker"** (`/api/admin/sistema/salute-worker`).
- Guarda il **p95** delle rotte in cima alla lista (ordinate dalla più lenta).
- Se `/api/auth/me` o le rotte `/api/home/*` hanno p95 vicino a 4s (giallo) o oltre (rosso) → il threadpool è sotto pressione.

**Causa più probabile**: qualcuno (tu) sta usando l'Admin con un'operazione pesante nello stesso momento in cui i clienti caricano l'app. Chiudi/aspetta operazioni Admin pesanti (full-load, export) e ricontrolla il p95 dopo 1-2 minuti.

### 2c. Il database è il collo di bottiglia? (raro, ma verificalo)
```sql
-- Query attive da più di 2 secondi
SELECT pid, now() - query_start AS duration, state, left(query, 200)
FROM pg_stat_activity
WHERE state != 'idle' AND now() - query_start > interval '2 seconds'
ORDER BY duration DESC;
```
Via Supabase MCP (`execute_sql`) o dashboard Supabase. Se ci sono query bloccate da molto → capire quale endpoint le genera (guarda la query stessa) e se serve un `KILL` (con cautela, solo se davvero bloccante).

---

## 3. Il worker torna 5xx / eccezioni reali

```bash
railway logs --service worker | grep -iE "ERROR|Traceback|Exception"
```
Se compaiono errori tipo `column X does not exist` o `relation Y does not exist` → è un **disallineamento schema/codice** (migration non applicata, o codice che punta a una colonna rimossa). Non è un problema di carico: serve intervento sul codice o sulla migration, non un riavvio.

---

## 4. Coda ricavi bloccata (alert dedicato)

```sql
SELECT id, email_subject, status, created_at, attempt_count, last_error
FROM ricavi_email_queue
WHERE status IN ('pending','processing')
ORDER BY created_at ASC LIMIT 10;
```
Causa storica nota (incidente 9-11/6/2026): `queue-worker` fermo per killswitch `WORKER_ENABLED=0` lasciato attivo dopo un deploy. Verifica:
```bash
railway variables --service queue-worker | grep WORKER_ENABLED
```
Deve essere `1`. Se è `0` o assente → il queue-worker non processa nulla, riattivalo e riavvia.

---

## 5. Dopo aver risolto — SEMPRE

1. Verifica che l'alert non si ripresenti (aspetta il prossimo ciclo del monitor, 10-15 min).
2. Se hai deployato un fix: **svuota `daily_briefing_state`** della sede di test se il fix tocca il briefing (regola esistente, vedi memoria `feedback_svuota_cache_briefing_dopo_deploy`).
3. Se la causa era saturazione ricorrente → considera se è il momento di potenziare Railway (vedi `PIANO_STABILITA_WORKER_2026-07-02.md`, Leva 3): i dati storici del p95 nella tab "Salute worker" sono l'evidenza su cui decidere, non l'intuito.
4. Annota nel changelog/memoria se l'incidente ha rivelato qualcosa di nuovo (nuova causa, nuova soglia da tarare).

---

## 6. Riferimenti rapidi

| Cosa | Comando/Link |
|---|---|
| Log worker | `railway logs --service worker` |
| Log queue-worker | `railway logs --service queue-worker` |
| Riavvio worker | `railway redeploy --service=worker --yes` |
| Variabili worker | `railway variables --service worker` |
| Spia latenza | Admin → Clienti → "Salute worker" (o `GET /api/admin/sistema/salute-worker`) |
| Vercel deployments | https://vercel.com dashboard progetto |
| DB / query live | Supabase MCP `execute_sql`, o dashboard Supabase → SQL Editor |
| Piano stabilità completo | `DOCUMENTAZIONE/PIANO_STABILITA_WORKER_2026-07-02.md` |
