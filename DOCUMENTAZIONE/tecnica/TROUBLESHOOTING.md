# ONEFLUX — Troubleshooting e limiti

**Aggiornamento:** 17 luglio 2026 — verificato contro il codice.

Sintomi già visti e cosa farci, più la tabella dei limiti tecnici (l'unica del
repo). Le regole di dominio **non** stanno qui: stanno in `CLAUDE.md`.

---

## 1. Problemi Comuni

### L'app non si carica (pagina bianca / errore connessione)

**In locale, primo passo sempre:** `.\scripts\start-local.ps1 -Check`. Il sintomo più
frequente in locale è la `WORKER_SECRET_KEY` disallineata tra `.env` (root) e
`apps/web/.env.local` (il worker risponde 401 a ogni chiamata dopo il login) o
`WORKER_URL` che punta al worker di produzione invece che a `127.0.0.1:8000`.
`start-local.ps1` corregge la chiave in automatico e blocca con messaggio
esplicito se `WORKER_URL` è sbagliata — non serve diagnosticare a mano.

**In produzione, causa più probabile:** Supabase in pausa (free tier: pausa automatica dopo 7 giorni di inattività).

**Soluzione:**
1. Accedere a [supabase.com/dashboard](https://supabase.com/dashboard)
2. Trovare progetto `vthikmfpywilukizputn`
3. Cliccare "Restore project"
4. Attendere ~2 minuti

**Altre cause:**
- Railway service down → verificare status su Railway dashboard
- Vercel deployment fallito → verificare build logs Vercel

---

### Fattura scartata durante upload

| Messaggio | Causa | Soluzione |
|----------|-------|-----------|
| "P.IVA non corrispondente" | P.IVA cedente ≠ P.IVA ristorante attivo | Cambiare ristorante attivo o verificare P.IVA in Impostazioni |
| "File già caricato" | Dedup su `file_origine + user_id + ristorante_id` | Normale — il file era già presente |
| "Encoding non supportato" | Charset esotico nel file XML | `charset-normalizer` lo rileva automaticamente; se fallisce, ri-esportare il file |
| "Firma non valida (P7M)" | File P7M corrotto o > 50 MB | Verificare integrità file, o usare il PDF/XML equivalente |

---

### Fatture Invoicetronic non appaiono in dashboard

1. Verificare `fatture_queue.status` su Supabase:
   - `pending` → non ancora processati, attendere il ciclo 15s
   - `processing` → in elaborazione, attendere
   - `done` → elaborati correttamente
   - `retry` → errore temporaneo, il worker riproverà
   - `dead` → troppi tentativi falliti → vedere `error_message`
   - `unknown_tenant` → P.IVA destinatario non registrata su ONEFLUX
   - `da_assegnare` → **normale, non è un errore**: P.IVA condivisa fra più sedi
     e indirizzo ambiguo. La fattura aspetta in coda che tu scelga la sede
     (Admin → Flusso dati). Vale per i clienti catena tipo OFFSIDE.

2. Se `unknown_tenant`: aggiungere il ristorante con P.IVA corretta, poi:
   ```sql
   SELECT resolve_unknown_tenant('PARTITA_IVA_QUI');
   ```

3. Verificare che Edge Function risponda:
   ```
   GET https://vthikmfpywilukizputn.supabase.co/functions/v1/invoicetronic-webhook
   → deve ritornare 200 OK
   ```

4. Verificare service `queue-worker` su Railway (deve essere Online).

---

### AI classifica male un prodotto

1. Correggere manualmente la categoria nel data editor → cliccare "Salva"
2. Il sistema salva la correzione in `prodotti_utente` (memoria locale del cliente)
3. La prossima volta quel prodotto sarà classificato correttamente senza AI
4. Se il problema è sistematico (molti clienti) → pannello admin Qualità AI → Memoria Globale → correggere in `prodotti_master`

---

### Sessione scaduta o login ripetuto

- Token sessione dura 30 giorni
- Auto-logout per inattività: 8 ore senza interazioni
- **Soluzione**: svuotare cache browser / cancellare cookie, poi login di nuovo

---

### "Errore creazione sessione" subito dopo il login (500)

Sintomo: credenziali giuste, il login arriva in fondo, poi 500 e
`permission denied for table sessioni` nei log del worker.

**Il segnale che discrimina** — guarda l'ordine delle chiamate nel log httpx:
se tutto ciò che precede `POST /auth/v1/token` è `200` e tutto ciò che segue è
`403`, il problema NON è nei permessi della tabella: è il client Supabase che
ha cambiato identità a metà richiesta.

**Causa (5/8/2026).** `sign_in_with_password()` sostituisce il token del client
su cui viene chiamato con il JWT dell'utente. Se lo si chiama sul singleton
`service_role` (cachato per processo da `get_supabase_client()`), da quel
momento **ogni** query del worker gira come `authenticated`: niente bypass RLS,
niente GRANT di `service_role`. `sessioni` non ha GRANT per `authenticated` →
`permission denied`; `login_attempts` invece li ha ma ha RLS → errore diverso
(`new row violates row-level security policy`) sullo stesso identico guasto.

Innescato da `SUPABASE_ANON_KEY`/`SUPABASE_KEY` assente: senza,
`_get_supabase_anon_client()` tornava `None` e il codice ripiegava in silenzio
sul client `service_role`.

**Fix in essere** (se il sintomo torna, verifica che siano ancora lì):
- `services/auth_service.py::_tenta_login_supabase_auth` — il bridge usa SOLO il
  client anon; se manca la chiave si salta e resta Argon2 (con WARNING nei log).
- `services/__init__.py::_riallinea_auth_header` — rete di sicurezza: rimette la
  `service_role` key negli header ad ogni `get_supabase_client()`. Va risanato
  **sia** `options.headers` **sia** `postgrest.session.headers`: il primo è la
  sorgente da cui PostgREST viene ricostruito.
- `tests/test_auth_service.py` — classi `TestBridgeSupabaseAuthNonAvvelenaIlSingleton`
  e `TestGuardiaAuthHeaderServiceRole`.

**Due piste sbagliate già battute — non ripercorrerle:**

1. **`FORCE ROW LEVEL SECURITY` su `sessioni`** (accusato da una sessione
   precedente). È attivo e senza policy, ma è **irrilevante**: `service_role` ha
   `rolbypassrls = true`, che ha priorità su FORCE. Verificato anche con INSERT
   reale via curl → `201`. Non toccare il DB per questo.
2. **Chiave sbagliata o disallineata** fra `.env` e `.streamlit/secrets.toml`.
   Escluso: le stesse credenziali funzionano se usate *prima* del login. Il
   discriminante è il **momento**, non la chiave.

**Come catturare il traceback vero.** `config/logger_setup.py` non ha FileHandler:
il traceback va solo su console, e con `--reload` WatchFiles riavvia il processo
a metà test perdendo la redirezione. Avvia il worker **senza `--reload`**
redirigendo su file:

```powershell
$env:ENABLE_INLINE_QUEUE_PROCESSOR = "0"
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","services.fastapi_worker:app","--host","127.0.0.1","--port","8000" `
  -RedirectStandardOutput "$env:TEMP\worker-stdout.log" `
  -RedirectStandardError "$env:TEMP\worker-stderr.log" -WindowStyle Minimized
```

---

### Firma webhook Invoicetronic non valida

- Verificare che `INVOICETRONIC_WEBHOOK_SECRET` nella Edge Function Supabase corrisponda a quello configurato nel dashboard Invoicetronic → Webhooks
- Anti-replay: timestamp webhook > 5 minuti → rifiutato (protocollo normale — Invoicetronic ri-invia automaticamente)

---

### FastAPI Worker non raggiungibile

1. Verificare `GET /health` sul worker → deve rispondere `{"status": "ok"}`
2. Se timeout o errore: verificare service `worker` su Railway dashboard

> ⚠️ **"Servizio non raggiungibile" non significa che il worker è down.**
> L'incidente del 2/7 era un **timeout SSR** su `/api/auth/me`: il worker era
> vivo ma saturo (Railway Hobby = 1 container, endpoint sincroni su threadpool,
> full-load admin). Prima di riavviare, guarda la latenza — non solo lo stato.

---

### Worker FastAPI lento (9+ secondi su /health)

**Causa:** endpoint `async def` che chiamano codice sincrono bloccante (fix introdotto in rev. 22).

**Sintomo:** ogni richiesta serializzata sull'event loop → `/health` impiega secondi invece di millisecondi.

**Verifica:** `GET /health` dovrebbe rispondere < 100ms. Se > 1s, c'è un blocco.

**Fix (già applicato):** tutti gli endpoint dichiarati `def` (non `async def`), tranne 6 con `await` reali.

---

### Briefing AI non si aggiorna

Il briefing ha una cache giornaliera (`daily_briefing_state`). Si auto-scarta se:
- Cambia la data (nuovo giorno)
- **Cambia `_BRIEFING_CODE_VERSION`** (auto-invalidazione su deploy, dal 19/6)
- Scade il TTL di 30 minuti
- Un evento chiama `invalidate_today_briefing` (upload fatture, inserimento
  ricavi/costi manuale, ricavi batch)

> ⚠️ **Se hai modificato la logica del briefing e non vedi il cambiamento:**
> hai dimenticato di bumpare `_BRIEFING_CODE_VERSION`. Senza quel bump lo
> snapshot vecchio resta valido e il cliente vede il testo pre-deploy.

Forzare a mano: `DELETE FROM daily_briefing_state` per la sede interessata.

---

### Import XLS ricavi fallisce

| Problema | Soluzione |
|---------|-----------|
| File > 10 MB | Ridurre il file o dividere per periodo |
| Timeout (> 30s) | File troppo grande, ridurre il range di date |
| Righe di altri ristoranti | Normale — vengono ignorate con avviso esplicito |
| Colonne non riconosciute | Verificare che sia formato Passbi v1 (struttura colonne specifica) |

---

## 2. Comandi di Sviluppo

```powershell
# ── TEST ──────────────────────────────────────────────────────
# Suite completa
pytest tests/ -v --tb=short

# Modulo specifico
pytest tests/test_ai_service.py -v

# Con coverage
pytest tests/ --cov=services --cov=utils --cov-report=html

# Tramite script
.\scripts\run-tests.ps1

# ── AVVIO LOCALE ──────────────────────────────────────────────
# Avvio completo (worker + frontend, sync automatica WORKER_SECRET_KEY, apre browser)
.\scripts\start-local.ps1

# Solo verifica configurazione, senza avviare nulla
.\scripts\start-local.ps1 -Check

# Ferma tutto
.\scripts\start-local.ps1 -Stop

# Finestre PowerShell visibili invece di minimizzate (debug)
.\scripts\start-local.ps1 -Visible

# (Streamlit dismesso: `app.py`/`pages/` non più serviti)

# Worker coda (richiede env vars, va avviato a mano se serve: nessuno script lo fa)
$env:SUPABASE_URL = "..."
$env:SUPABASE_SERVICE_ROLE_KEY = "..."
python worker/run.py

# Debug avanzato: worker isolato senza script (dev mode senza chiave)
$env:WORKER_DEV_MODE = "1"
python -m services.fastapi_worker

# ── QUALITY CHECK ──────────────────────────────────────────────
# Verifica drift schema OpenAPI (dopo modifiche a fastapi_worker.py)
python scripts/export_openapi.py --check-drift

# Verifica oggetti DB da migration legacy (65 check)
python tools/check_migrations.py

# Import check
python -c "import app"

# Next.js type check
cd apps/web
npx tsc --noEmit

# Next.js build completo
cd apps/web
npm run build

# ── EDGE FUNCTION ─────────────────────────────────────────────
# Avvio locale (porta 54321)
.\scripts\dev-serve.ps1

# Test Edge Function
.\scripts\dev-serve.ps1 -Test

# Deploy su Supabase Cloud (verify_jwt=false è in supabase/config.toml)
supabase functions deploy invoicetronic-webhook --project-ref vthikmfpywilukizputn

# Test unit Edge Functions (HMAC + routing)
deno test --allow-env --allow-net supabase/functions/**/*_test.ts

# ── DOCKER ────────────────────────────────────────────────────
# Sviluppo locale
docker-compose -f docker/docker-compose.yml up

# Produzione
docker-compose -f docker/docker-compose.prod.yml up -d
```

---

## 3. Variabili d'Ambiente — Riferimento Rapido

| Variabile | Dove | Descrizione |
|-----------|------|-------------|
| `SUPABASE_URL` | Ovunque | URL progetto Supabase |
| `SUPABASE_KEY` | Fallback in `services/__init__.py` | Contiene la `service_role_key` **nonostante il nome** (residuo storico) |
| `SUPABASE_SERVICE_ROLE_KEY` | Railway, GitHub, Supabase EF | `service_role_key` |
| `OPENAI_API_KEY` | Worker, GitHub | Chiave API OpenAI |
| `WORKER_BASE_URL` | Worker, `worker_client.py` | URL FastAPI worker |
| `WORKER_SECRET_KEY` | Worker (Railway), Next.js (Vercel) | Chiave 64 char, fail-closed |
| `WORKER_DEV_MODE` | Solo sviluppo | `1` = boot senza chiave |
| `WORKER_WEB_CONCURRENCY` | Railway service worker | Processi Uvicorn (prod: 4) |
| `WORKER_THREADPOOL_SIZE` | Railway service worker | Thread AnyIO (default: 100) |
| `ENABLE_INLINE_QUEUE_PROCESSOR` | Railway service worker | `0` = usa queue-worker separato |
| `INVOICETRONIC_API_KEY` | Worker, GitHub, Supabase EF | API Key Invoicetronic |
| `INVOICETRONIC_WEBHOOK_SECRET` | Supabase EF | Segreto HMAC webhook |
| `BREVO_API_KEY` | Worker (Railway) | API key Brevo |
| `BREVO_SENDER_EMAIL` | Worker (Railway) | Email mittente |
| `BREVO_SENDER_NAME` | Worker (Railway) | Nome mittente |
| `WORKER_BATCH_SIZE` | queue-worker | Record per ciclo (default: 10) |
| `WORKER_XML_RETENTION_HOURS` | queue-worker | Ore prima del purge XML (default: 24) |
| `WORKER_STALE_LOCK_MINUTES` | queue-worker | Timeout lock crash (default: 10) |
| `WORKER_PURGE_INTERVAL_SECONDS` | queue-worker (`worker/run.py`) | Intervallo purge cestino fatture (default: 21600 = 6h) |
| `WORKER_RETENTION_INTERVAL_SECONDS` | queue-worker (`worker/run.py`) | Intervallo retention fatture >2 anni (default: 86400 = 24h) |
| `WORKER_QUEUE_PURGE_INTERVAL_SECONDS` | queue-worker (`worker/run.py`) | Intervallo purge `xml_content`/`raw_body_sample` su `fatture_queue` (default: 21600 = 6h) |
| `ADMIN_EMAILS` | Worker (Railway) | Email admin (lowercase, virgola-separati) |

---

## 4. Limiti Tecnici — Tabella Completa

| Limite | Valore | Configurato in |
|--------|--------|----------------|
| Max file per upload | 100 | `constants.py` |
| Max dimensione upload totale | 200 MB | `constants.py` + `config.toml` |
| Max dimensione P7M | 50 MB | `constants.py` |
| Max dimensione upload Next.js | 4.5 MB | Vercel default |
| Max righe per utente | 100.000 | `app.py` |
| Max chiamate AI classificazione/giorno | 1.000 per ristorante | `constants.py` |
| Max domande chat AI/giorno | 0–30 (per piano) | `CHAT_LIMITI_PIANO` |
| Batch AI | 50 articoli per chiamata | `ai_service.py` |
| TTL cache fatture | 120 secondi | `db_service.py` |
| TTL cache margini | 300 secondi | `margine_service.py` |
| TTL sessione cookie | 30 giorni | `auth_service.py` |
| Inattività auto-logout | 8 ore | `SESSION_INACTIVITY_HOURS` |
| Lockout login | 15 min dopo 5 tentativi | `auth_service.py` |
| Cooldown reset password | 5 minuti | `auth_service.py` |
| Scadenza reset token | 15 minuti | `auth_service.py` |
| Descrizione max DB | 500 caratteri | `constants.py` |
| Descrizione max AI input | 300 caratteri | `ai_service.py` |
| Paginazione DB | 1.000 righe per pagina | `db_service.py` |
| Log rotation | 50 MB × 10 backup | `logger_setup.py` |
| Upload XLS ricavi | Max 10 MB, timeout 30s | Route proxy Next.js |
| Finestra notifiche scadute | 90 giorni | `notification_service.py` |
| XML Invoicetronic purge | 24 ore | `WORKER_XML_RETENTION_HOURS` |
| Anti-replay webhook | 5 minuti | Edge Function |
| Cookie impersonazione TTL | 30 minuti | FastAPI |

---

## 5. Accessi e Contatti

| Risorsa | Dettaglio |
|---------|-----------|
| Email admin | md@oneflux.it |
| Email sistema (import ricavi) | agent@oneflux.it |
| Email backup | mattiadavolio90@gmail.com |
| GitHub | mattiadavolio90-crypto |
| Vercel | Account Mattia — progetto `oneflux-web` |
| Railway | Account Mattia — progetto `ingenious-fascination` |
| Supabase | Account Mattia — progetto `vthikmfpywilukizputn` |
| Invoicetronic | Account Mattia — codice dest. `7HD37X0` |

---

## 6. Regole di dominio

Stanno in **`CLAUDE.md`**, che è l'unica copia.

Erano duplicate anche qui, ed è esattamente così che nasce il drift: due copie
della stessa regola divergono, e quella sbagliata corrompe i dati in silenzio.
Questo file era rimasto indietro sul fallback `"SERVIZI E CONSULENZE"`, eliminato
dal prodotto ma ancora descritto qui come attivo.

7. **Password Argon2id** — parametri `m=65536, t=3` non vanno mai modificati.

8. **Anonimizzazione AI** — mai inviare nomi reali di prodotti o fornitori a OpenAI.

---

*Troubleshooting v6.0 — 5 Giugno 2026*
