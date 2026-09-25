# RUNBOOK INCIDENTI — ONEFLUX

> Cosa fare, in che ordine, quando arriva un alert (Telegram/email) o un cliente
> segnala "l'app non va". Scritto sulla base dell'incidente reale del 2/7/2026
> (analisi completa: memoria `project_stabilita_worker_2026-07-02`).

---

## 0. Da dove arriva l'alert e cosa significa

| Alert | Sorgente | Significa |
|---|---|---|
| 🚨 "ONEFLUX è offline" | `uptime_check.yml` (ogni 15 min) | Vercel/frontend non risponde HTTP 200 |
| ⚠️ "worker LENTO" | `worker_latency_check.yml` (ogni 10 min) | Il worker Railway risponde ma sopra soglia (3s su `/health`, che non tocca nemmeno il DB) — i clienti probabilmente vedono già "Servizio non raggiungibile" |
| 🚨 "Coda ricavi bloccata" | `ricavi_queue_monitor.yml` (ogni ora) | Il queue-worker non sta consumando `ricavi_email_queue` — gli incassi non entrano in app |
| 🤖 "Agent notturno completato/FALLITO" | agent notturno (worker, ogni notte) | Riepilogo categorizzazione automatica; se FALLITO è un'anomalia da controllare |
| ⚠️/🚨 "Saldo Invoicetronic basso / ESAURITO" | queue-worker (ogni 6 ore) e webhook (al primo 403) — **solo Telegram** | Crediti in esaurimento o finiti: a zero le fatture in arrivo non si scaricano — vedi §4bis |

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

## 3bis. I clienti non riescono ad accedere — "Errore creazione sessione"

Sintomo: la pagina di login mostra **"Errore creazione sessione"**, il worker e
Vercel rispondono 200 e veloci (il punto 1 non trova niente).

**Il redeploy NON risolve.** È la trappola di questo incidente: sembra un pool di
connessioni "avvelenato" dall'uptime, ma l'errore si ripresenta su un worker
appena riavviato.

```bash
railway logs --service worker | grep -iE "Errore creazione sessione|ConnectionTerminated"
```

Se compare `httpx.RemoteProtocolError: <ConnectionTerminated error_code:0>`:

1. **Guarda `last_stream_id`.** Se è **basso e sempre uguale** (es. `:3`) anche
   dopo un riavvio, non è una connessione vecchia rimasta in cache: muore la
   n-esima richiesta di una connessione **nuova**. Il problema è a monte, in chi
   apre le connessioni.
2. **Conta i client Supabase creati nel percorso caldo.** Un `create_client()`
   dentro una funzione chiamata a ogni richiesta (o dentro un `while True`) apre
   un pool nuovo che non viene mai chiuso: è una perdita di connessioni.
3. Verifica che le credenziali passino comunque:
   ```sql
   SELECT email, last_login FROM users WHERE last_login > now() - interval '1 hour';
   SELECT count(*) FROM sessioni WHERE created_at > now() - interval '1 hour';
   ```
   `last_login` aggiornato + zero sessioni nuove = le password sono verificate e
   si rompe **solo** la creazione della sessione.

**Rimedio immediato senza deploy** (incidente 11/09/2026): il bridge Supabase
Auth creava un client nuovo a ogni login e falliva comunque (400 su
`/auth/v1/token`, 404 su `/auth/v1/admin/users`, perché `auth.uid()` è sempre
NULL qui). Si spegne con il killswitch già previsto dal codice:

```bash
railway variables --service worker --set "SKIP_SUPABASE_AUTH=1"
```

Misurato dopo: zero `ConnectionTerminated` su `crea_sessione`, latenza login da
~4s a 0,78s. Il login resta pienamente funzionante (path Argon2).

> ⚠️ **Non testare il login con password sbagliate.** Dopo 5 tentativi scatta il
> lockout di 15 minuti sull'account (`login_attempts`), e da quel momento
> nemmeno la password giusta entra — sembra che il fix non abbia funzionato.
> Successo l'11/09/2026. Per verificare basta il codice di risposta: **401** =
> catena sana (credenziali rifiutate), **500** = il bug è ancora lì, **429** =
> account bloccato, aspetta 15 minuti.

Nota: `ConnectionTerminated` su `login_attempts` (cleanup / `registra_tentativo`)
è dentro try/except non bloccanti e **non** impedisce il login. Va però ricordato
che in quel caso `controlla_rate_limit` ritorna `(False, 0)`: il lockout si apre
proprio mentre il sistema è sotto stress.

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

## 4bis. Saldo crediti Invoicetronic (alert dedicato)

A saldo zero Invoicetronic risponde 403 `usage_limit_exceeded` a **ogni** download:
il webhook segna la fattura `failed`, il worker ritenta e in circa 2 ore ogni fattura
in arrivo è `dead`, per tutti i clienti. Non è persa: Invoicetronic la conserva 2 anni.

1. **Ricarica subito** dal dashboard Invoicetronic: ogni ora di saldo a zero è una
   fattura in più da recuperare. La conferma che è ripartito è il saldo nel
   dashboard; il messaggio «di nuovo sopra soglia» arriva solo se il queue-worker
   non è stato riavviato dopo l'avviso (lo stato degli avvisi vive nel processo).
2. **Le fatture già ferme NON ripartono da sole, e «Riprova» non basta.** Il webhook
   le ha salvate senza cliente (`user_id` NULL, `piva_raw` `UNKNOWN`) perché senza
   saldo non ha potuto leggere l'XML: il worker lo riscarica, ma poi si ferma a
   «Tenant non risolto». Un recupero automatico ancora non c'è. **Non assegnare il
   cliente a mano** nella riga di coda: il worker salva la fattura sul cliente
   scritto lì senza ricontrollare la P.IVA dell'XML. Per contarle:
   ```sql
   SELECT id, status, user_id, created_at FROM fatture_queue
   WHERE payload_meta->>'api_error_code' = 'usage_limit_exceeded'
      OR last_error LIKE '%usage_limit_exceeded%'
   ORDER BY created_at;
   ```
   Le righe **con** `user_id` valorizzato (fermate dal worker, non dal webhook) il
   cliente ce l'hanno: per quelle, dopo la ricarica, «Riprova» funziona.

«Non riesco a leggere il saldo» (due controlli falliti di fila): quasi sempre
`INVOICETRONIC_API_KEY` assente o scaduta sul queue-worker. Soglia e intervallo:
`docs/DEPLOY_RUNBOOK.md`.

---

## 5. Dopo aver risolto — SEMPRE

1. Verifica che l'alert non si ripresenti (aspetta il prossimo ciclo del monitor, 10-15 min).
2. Se hai deployato un fix: **svuota `daily_briefing_state`** della sede di test se il fix tocca il briefing (regola esistente, vedi memoria `feedback_svuota_cache_briefing_dopo_deploy`).
3. Se la causa era saturazione ricorrente → considera se è il momento di potenziare Railway: i dati storici del p95 nella tab "Salute worker" sono l'evidenza su cui decidere, non l'intuito.
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
