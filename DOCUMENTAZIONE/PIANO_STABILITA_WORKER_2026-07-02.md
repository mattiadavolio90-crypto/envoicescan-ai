# PIANO STABILITÀ WORKER — "Servizio non raggiungibile" (2/7/2026)

> Documento operativo. Obiettivo: eliminare la causa di fondo della schermata
> "Servizio momentaneamente non raggiungibile" e della lentezza/crash percepiti,
> senza regressioni, con clienti paganti già live.

> **Verificato 17/7/2026 — piano PARZIALMENTE eseguito, non archiviabile.**
>
> - **Fase 1 (isolare admin): FATTA** — `admin_fatture_per_mese` RPC e `TTLCache`
>   confermati nel codice.
> - **Fase 1a, target "Full-load notifiche" (§6): FALSO ALLARME, chiuso.** Il
>   `.limit(50000)` in `notification_service.py` esiste ancora ma quel modulo
>   **non è nel percorso di produzione**: lo importa solo
>   `components/notifications_panel.py` (Streamlit, dismesso l'8/6/2026). Nessun
>   file di `services/`, `services/routers/` o `worker/` lo importa. Le notifiche
>   vive passano da `notification_inbox_service.py`. Non c'è niente da
>   ottimizzare: la migrazione a Next.js aveva già tolto questo codice dal
>   percorso servito. *(Una revisione precedente di questa nota lo dava per "bug
>   aperto" senza aver verificato i chiamanti — l'errore che questo piano stesso
>   avverte di non fare: "diagnosi accertata, non ipotizzata".)*
> - **Fase 2** (endpoint aggregato Home) e **Fase 4** (async percorsi caldi):
>   **NON FATTE e non necessarie allo stato attuale** — decisione 17/7 presa sui
>   numeri, come questo piano prescrive ("si potenzia sui numeri reali della spia
>   latenza, non a naso", §3 Fase 3a):
>
>   | Misura | Valore (17/7) | Soglia del piano |
>   |---|---|---|
>   | Risposta `app.oneflux.it` | **0,3–0,5s** | — |
>   | `worker_latency_check` (ogni 10 min dal 2/7) | **100 esecuzioni su 100 verdi** | 3s |
>   | Alert latenza scattati | **0** | — |
>
>   Il sintomo che questo piano doveva curare **non si manifesta più** dal
>   cuscinetto SSR + Fase 1. La Fase 4 tocca ~110 endpoint sincroni che servono
>   clienti reali (il piano stesso la marca "rischio MEDIO, ULTIMA, isolata"):
>   farla ora sarebbe rischio senza un problema da risolvere.
>
>   **Cosa le riapre** (non serve rileggere tutto il piano, basta uno di questi):
>   - la spia latenza scatta (alert Telegram "worker lento") più di una volta
>     isolata, oppure
>   - crescita clienti/carico oltre l'ordine di grandezza attuale (10 sedi), oppure
>   - ricompare la schermata "Servizio momentaneamente non raggiungibile".
>
>   In quel caso l'ordine resta quello di §4: prima Fase 2 (rischio basso), poi
>   Fase 3a (+1 replica Railway, costo €), Fase 4 solo per ultima.
>
> - **§5 "Verifica finale"**: le caselle restano non spuntate perché il piano non è
>   stato eseguito fino in fondo — ma il criterio pratico ("l'app non è più
>   irraggiungibile / lenta") è soddisfatto e misurato.

---

## 1. Diagnosi (accertata, non ipotizzata)

### Sintomo
Schermata **"Servizio momentaneamente non raggiungibile"** su tutte le pagine, da
PC e telefono, intermittente. L'app "riparte ma è lentissima e crasha".

### Catena tecnica accertata
1. Ogni pagina autenticata è renderizzata **server-side** da Next.js (Vercel). Il
   layout `apps/web/src/app/(app)/layout.tsx` chiama `verifySession()` →
   `fetch(WORKER_URL + /api/auth/me)`.
2. Se quella `fetch` va in **timeout** (era 8s, ora 12s) o torna 5xx →
   `session.status === "unavailable"` → schermata di errore. Essendo SSR, la si
   vede da **ogni** dispositivo, su **ogni** rete → sembra "app giù".
3. Il worker **non crasha**: `/health` risponde sempre 200 in ~0.3s, zero OOM/
   restart/502 nei log. È un problema di **latenza sotto contesa**, non di down.

### Causa di fondo (accertata leggendo il codice)
- **103 endpoint su 108 sono `def` sincroni** (`fastapi_worker.py`). FastAPI li
  esegue sul **threadpool AnyIO**. Ogni chiamata Supabase è **bloccante**
  (`.execute()` httpx sync) → **occupa un thread per tutta la durata della query**.
- Un singolo load Home spara **6-7 endpoint in parallelo** (`/auth/me`, `/home/kpi`,
  `/home/briefing`, `/home/salute`, `/home/config`, `/notifiche`, `/account/sedi`),
  e ognuno fa sotto-query → **~15-25 thread occupati per un solo utente che apre la Home**.
- Config attuale (già ottimizzata): threadpool **100** (`WORKER_THREADPOOL_SIZE`),
  **4 processi** uvicorn (`WORKER_WEB_CONCURRENCY=4`), cache sessione TTL 30s,
  micro-cache sede TTL 5s. **Non è codice ingenuo** — siamo vicini al tetto di un
  piano **Railway Hobby** (1 container, poche CPU/RAM) sotto carico reale.
- **Amplificatore**: gli endpoint **Admin** fanno **full-load pesanti** che tengono
  occupato un thread per **secondi**:
  - `admin.py:254/256` → `fatture_documenti`/`fatture` `.limit(50000)`
  - `admin.py:637/655/1254` → paginazioni a 1000 su `prodotti_utente`/`prodotti_master`
  - `notification_service.py:999` → `.limit(50000)`
  Quando **tu** (admin) navighi mentre i clienti usano l'app, questi svuotano il
  threadpool → le richieste dei clienti si accodano → superano il timeout → errore.

### Perché intermittente
Dipende dalla **coincidenza** di carico (più clienti + admin full-load nello stesso
istante). Da rete esterna, nei momenti buoni, tutto risponde <0.4s: infatti in fase
di diagnosi non si riproduceva a colpi singoli.

---

## 2. Interventi già fatti

### 2.1 Cuscinetto SSR (2/7, DEPLOYATO — commit `94c0042`)
| # | Intervento | File | Stato |
|---|---|---|---|
| A0 | Restart worker Railway (pulizia stato degradato) | — | ✅ fatto |
| A1 | Timeout SSR 8s → 12s | `apps/web/src/lib/auth.ts` | ✅ deployato |
| A2 | Retry 1× su timeout/5xx in `verifySession` (401/403 resta definitivo) | `apps/web/src/lib/auth.ts` | ✅ deployato |

**Effetto**: un singolo colpo di lentezza non butta più giù la pagina.

### 2.2 Leva 2 — Isolare Admin (2/7, PRONTO, non ancora deployato)
| # | Intervento | File | Stato |
|---|---|---|---|
| B1 | RPC `admin_fatture_per_mese`: GROUP BY nel DB al posto del full-load 50k | `supabase/migrations/20260702100000_*.sql` | ✅ applicata al DB live |
| B2 | Modulo cache riusabile thread-safe + single-flight | `utils/ttl_cache.py` (+test) | ✅ |
| B3 | Cache 45s su `admin_overview` e `admin_badges` (tolti dal percorso caldo) | `services/routers/admin.py` | ✅ |

### 2.3 Leva 1a — Load parallelo Home (2/7, PRONTO, non ancora deployato)
| # | Intervento | File | Stato |
|---|---|---|---|
| C1 | Single-flight su `TTLCache`: N richieste concorrenti stessa chiave → 1 query | `utils/ttl_cache.py` | ✅ |
| C2 | `_get_assistant_preferences` migrato a `TTLCache` single-flight | `services/fastapi_worker.py` | ✅ |
| C3 | Fixture test aggiornata a resettare dict E TTLCache + `_ADMIN_CACHE` | `tests/conftest.py` | ✅ |

**Verifica**: suite completa **9758 passed, 1 skipped**; test dedicati `TTLCache` verdi;
worker importa pulito. **DA DEPLOYARE fuori orario** (worker Railway + già fatto il DB).

### 2.4 Leva 3c/3d — Spia latenza + alert proattivi + runbook (2/7, DEPLOYATO — commit `852b970`, `c3229eb` + successivi)

Prima di oggi la scoperta di un incidente dipendeva dal caso (Mattia che guarda lo
schermo). Ora ci sono DUE meccanismi indipendenti:

| # | Intervento | File | Stato |
|---|---|---|---|
| D1 | Metriche latenza per rotta (p50/p95/max/lenti/errori), thread-safe | `services/worker_metrics.py` | ✅ deployato |
| D2 | Middleware che misura ogni richiesta (esclude `/health`, normalizza ID) | `services/fastapi_worker.py` (`_LatencyMetricsMiddleware`) | ✅ deployato |
| D3 | Endpoint + tab Admin "Salute worker" (p95 colorato verde/ambra/rosso) | `services/routers/admin.py`, `apps/web/.../sistema-tabs.tsx` | ✅ deployato |
| D4 | Modulo invio Telegram, fail-safe (mai rompe il chiamante) | `services/telegram_service.py` | ✅ |
| D5 | Bot Telegram `@Oneflux_alert_bot`, secrets `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` | GitHub Secrets + env Railway | ✅ configurato |
| D6 | `uptime_check.yml` esteso: Telegram in parallelo all'email su down | `.github/workflows/uptime_check.yml` | ✅ |
| D7 | **Nuovo** `worker_latency_check.yml`: rileva LENTO (non solo giù), ogni 10 min su `/health` | `.github/workflows/worker_latency_check.yml` | ✅ |
| D8 | Digest agent notturno via Telegram (successo silenzioso, fallimento con suono) | `services/fastapi_worker.py` (`_run_agent_notturno`) | ✅ |
| D9 | Runbook: cosa guardare in che ordine quando arriva un alert | `DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md` | ✅ |

**Perché due monitor separati (uptime_check + worker_latency_check)**: l'incidente
del 2/7 NON era "sito giù" (Vercel rispondeva 200) — era il worker Railway lento
sotto contesa. Un check binario su/giù non lo intercetta. `worker_latency_check.yml`
misura la latenza di `/health` (che non tocca il DB): se anche quello rallenta
sopra soglia (3s), è il segnale che il threadpool è sotto pressione.

**Verifica**: suite **9775 passed**; +12 test nuovi (`test_worker_metrics.py`,
`test_telegram_service.py`); YAML dei 3 workflow toccati validati; invio Telegram
reale confermato end-to-end (bug di quoting in un curl locale Windows, non
riproducibile su `ubuntu-latest` dove gira il workflow — confermato inviando lo
stesso testo via Python).

**Setup manuale richiesto per attivare gli alert** (Mattia, fuori da questo repo):
1. GitHub → repo → Settings → Secrets and variables → Actions → New repository secret:
   `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
2. Railway → servizio `worker` → Variables: stesse due variabili (per il digest
   agent notturno, che gira nel worker Python, non in GitHub Actions).

---

## 3. Piano di intervento (a freddo, fuori orario — regola Mattia)

Ordinato per **rapporto beneficio/rischio**. Ogni fase è indipendente e deployabile
da sola. Nessuna richiede migrazione DB distruttiva.

### FASE 1 — Isolare l'Admin dai clienti (rischio BASSO, beneficio ALTO)
Il full-load admin è l'amplificatore n.1. Va tolto dal percorso caldo.

- **1a. Cap + finestra sui full-load admin**: sostituire `.limit(50000)` con query
  aggregate SQL (RPC `count`/`group by`) o cap realistico (es. 5000) con avviso
  "dati troncati". Target: `admin.py:254,256`, `notification_service.py:999`.
- **1b. Cache in-process sugli endpoint Admin pesanti** (overview, badges,
  ricavi-salute): TTL 30-60s. Sono dati che tu guardi, non serve realtime.
- **1c. (opzionale) Isolamento a runtime**: instradare gli endpoint `/api/admin/*`
  su un **secondo processo/replica** dedicata, così un tuo full-load non tocca mai
  il threadpool che serve i clienti. Valutare dopo 1a/1b.

**Test**: mentre giri un full-load admin, misurare latenza `/api/home/kpi` da un
secondo client → deve restare < 1s.

### FASE 2 — Ridurre le query per-load lato client (rischio BASSO-MEDIO)
Ogni Home fa troppe chiamate separate worker→Supabase.

- **2a. Endpoint aggregato Home**: un solo `GET /api/home/bootstrap` che ritorna
  kpi+briefing+salute+config+notifiche in **una** risposta (già le fa il worker,
  ma in 6 round-trip separati). Il frontend passa da 6-7 fetch a 1-2.
- **2b. Deduplica sotto-query**: nei log stessi valori riletti 3-4× per load
  (`assistant_preferences`, `users`, `costi_automatici_mensili`). Verificare se le
  micro-cache (sess 30s, sede 5s) coprono davvero o se alcune callsite le bypassano.
- **2c. `costi_automatici_mensili` RPC** chiamata 3×/load: memoizzare per
  (ristorante, mese) entro la request.

**Test**: contare le righe `httpx — HTTP Request` nei log worker per un singolo
load Home prima/dopo. Target: ≥ −40%.

### FASE 3 — Capacità infrastruttura (rischio BASSO, costo €)
La cura strutturale al carico crescente col go-live.

- **3a. Railway: da Hobby a piano con più risorse** o **+1 replica** del servizio
  `worker`. Il codice è già multi-worker (`WORKER_WEB_CONCURRENCY`). Verificare
  che le cache in-process (per-processo) restino corrette con più repliche
  (già annotato a `fastapi_worker.py:5124` — sono best-effort, non correttezza).
  **Decisione rimandata volutamente**: si potenzia sui numeri reali della spia
  latenza (Fase 3c/3d già fatte), non a naso.
- **3b. Health check Railway** su `/health` con restart automatico (se non già
  attivo) → auto-recupero da stati degradati senza intervento manuale.
- **3c. ✅ FATTO (2/7) — Spia latenza worker**: `services/worker_metrics.py` +
  middleware + tab Admin "Salute worker". Vedi sezione 2.4.
- **3d. ✅ FATTO (2/7) — Alert proattivi + runbook**: bot Telegram
  `@Oneflux_alert_bot`, `services/telegram_service.py`, workflow
  `worker_latency_check.yml` (nuovo, ogni 10 min, rileva LENTO non solo giù),
  `uptime_check.yml` esteso con Telegram in parallelo all'email, digest agent
  notturno via Telegram, `DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md` (piano
  d'intervento con priorità). Vedi sezione 2.4.

### FASE 4 — Rendere async i percorsi caldi (rischio MEDIO, beneficio ALTO, ULTIMA)
Vera cura architetturale, ma tocca molto codice: farla per ultima, isolata.

- **4a.** Convertire **solo** i 6-7 endpoint del percorso Home da `def` sincrono a
  `async def` con client Supabase async (o `httpx.AsyncClient`), così non
  consumano thread. Non toccare gli altri 100 endpoint in questo giro.
- **4b.** In alternativa più leggera: mantenere `def` ma ridurre il numero di
  chiamate bloccanti per endpoint (dipende molto da Fase 2).

---

## 4. Ordine di esecuzione consigliato

```
Fatto:   A0, A1, A2  (cuscinetto, già live)
Sprint 1 (fuori orario, ~mezza serata):  FASE 1a + 1b  → toglie l'amplificatore admin
Sprint 2 (fuori orario):                 FASE 2a + 2b  → dimezza le query per-load
Decisione business:                      FASE 3a       → +risorse/replica Railway
Più avanti, isolato:                     FASE 4a       → async percorso Home
```

Regole rispettate: **infrastruttura prima delle feature**; **SQL > loop Python**;
**deploy solo fuori orario**; dopo ogni deploy che tocca il briefing → svuotare
`daily_briefing_state` della sede di test.

---

## 5. Verifica finale (criteri di "risolto")

- [ ] Con un full-load admin in corso, `/api/home/kpi` da altro client < 1s
- [ ] Righe `httpx` per singolo load Home ridotte ≥ 40%
- [ ] Nessuna schermata "non raggiungibile" in 200 load consecutivi simulati
- [ ] `/api/auth/me` p95 < 2s sotto carico di 3 clienti simultanei
- [ ] Suite `python -m pytest tests/` verde
- [ ] Advisor Supabase performance: 0 nuovi WARN

---

## 6. Riferimenti codice (per chi esegue)

| Cosa | Dove |
|---|---|
| Schermata errore SSR | `apps/web/src/app/(app)/layout.tsx:48-66` |
| Timeout/retry (già fatto) | `apps/web/src/lib/auth.ts:15, 79-104` |
| `/api/auth/me` | `services/fastapi_worker.py:1200-1255` |
| Risoluzione utente per-endpoint | `services/fastapi_worker.py:1338-1383` |
| Cache sessione TTL 30s | `services/auth_service.py:1137-1145` |
| Threadpool AnyIO (100) | `services/fastapi_worker.py:456-467` |
| Avvio uvicorn multi-worker | `services/fastapi_worker.py:7437-7453` |
| Full-load admin da tagliare | `services/routers/admin.py:254,256,637,655,1254` |
| Full-load notifiche | `services/notification_service.py:999` |
