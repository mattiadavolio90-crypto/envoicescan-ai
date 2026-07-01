# ONEFLUX — Troubleshooting e Riferimento Tecnico

Versione: 6.0 | Aggiornamento: 5 Giugno 2026

---

## 1. Problemi Comuni

### L'app non si carica (pagina bianca / errore connessione)

**Causa più probabile:** Supabase in pausa (free tier: pausa automatica dopo 7 giorni di inattività).

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

### Firma webhook Invoicetronic non valida

- Verificare che `INVOICETRONIC_WEBHOOK_SECRET` nella Edge Function Supabase corrisponda a quello configurato nel dashboard Invoicetronic → Webhooks
- Anti-replay: timestamp webhook > 5 minuti → rifiutato (protocollo normale — Invoicetronic ri-invia automaticamente)

---

### FastAPI Worker non raggiungibile

1. Verificare `GET /health` sul worker → deve rispondere `{"status": "ok"}`
2. Se timeout o errore: verificare service `worker` su Railway dashboard
3. Se `worker_client.py` (Streamlit) → ha fallback automatico sulle funzioni Python locali
4. In Docker: verificare che il service `worker` sia `healthy` prima di avviare `ohyeah`

---

### Worker FastAPI lento (9+ secondi su /health)

**Causa:** endpoint `async def` che chiamano codice sincrono bloccante (fix introdotto in rev. 22).

**Sintomo:** ogni richiesta serializzata sull'event loop → `/health` impiega secondi invece di millisecondi.

**Verifica:** `GET /health` dovrebbe rispondere < 100ms. Se > 1s, c'è un blocco.

**Fix (già applicato):** tutti gli endpoint dichiarati `def` (non `async def`), tranne 6 con `await` reali.

---

### Celle categoria bianche in Streamlit

Bug noto di Streamlit: se il valore non è nelle opzioni del SelectboxColumn, appare vuoto. Il sistema applica automaticamente `valida_categoria()` per forzare un valore valido.

---

### Briefing AI non si aggiorna

Il briefing ha una cache giornaliera (`daily_briefing_state`). Si rigenera solo se:
- Cambia la data (nuovo giorno)
- Cambiano le notifiche attive (nuovo `notif_fingerprint`)
- Cambiano le preferenze assistente

Se si vuole forzare la rigenerazione: modificare una preferenza assistente (es. nome referente) → salva → briefing si rigenera.

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
# FastAPI Worker (dev mode senza chiave; legge WORKER_PORT, default 8000)
$env:WORKER_DEV_MODE = "1"
python -m services.fastapi_worker

# Next.js (frontend)
cd apps/web
npm run dev      # Turbopack

# (Streamlit dismesso: `app.py`/`pages/` non più serviti)

# Worker coda (richiede env vars)
$env:SUPABASE_URL = "..."
$env:SUPABASE_SERVICE_ROLE_KEY = "..."
python worker/run.py

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
| `SUPABASE_KEY` | Streamlit | `service_role_key` |
| `SUPABASE_SERVICE_ROLE_KEY` | Railway, GitHub, Supabase EF | `service_role_key` |
| `OPENAI_API_KEY` | Worker, Streamlit | Chiave API OpenAI |
| `WORKER_BASE_URL` | Streamlit, Next.js | URL FastAPI worker |
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
| `ADMIN_EMAILS` | Streamlit | Email admin (lowercase, virgola-separati) |

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

## 6. Regole di Dominio — NON Violare Mai

Queste regole sono critiche e violarne anche una può corrompere i dati o rompere il sistema:

1. **`categoria = 'Da Classificare'` è uno stato LEGITTIMO** (categorizzazione onesta, rev. 23/06) — una riga che né dizionario/regole né AI riconoscono con sicurezza resta `Da Classificare`, visibile in coda di verifica. **NIENTE fallback travestito in `"SERVIZI E CONSULENZE"`** (comportamento eliminato). Constraint DB reale: `fatture_categoria_not_empty_chk` (vieta solo NULL/vuoto). Costante: `CATEGORIA_NON_CLASSIFICATA` in `config/constants.py`.

2. **`"📝 NOTE E DICITURE"` solo per `totale_riga == 0`** — su qualsiasi importo > 0 va usata una categoria reale.

3. **`service_role_key` sempre** — non usare la anon key. Non toccare `services/__init__.py` senza capire l'auth flow.

4. **`ADMIN_EMAILS` normalizzato lowercase** — confronti email sempre con `.strip().lower()`.

5. **Soft-delete**: query su `fatture` e `prodotti` devono filtrare `deleted_at IS NULL`. Usare `filter_active()` da `services.db_service`. Non rimuovere `.not_.is_("deleted_at", "null")` nelle query cestino (quelle sono intenzionali).

6. **Worker separato**: operazioni pesanti (classificazione AI, parsing fatture) vanno nel worker — non bloccare il thread Streamlit o l'event loop Next.js.

7. **Password Argon2id** — parametri `m=65536, t=3` non vanno mai modificati.

8. **Anonimizzazione AI** — mai inviare nomi reali di prodotti o fornitori a OpenAI.

---

*Troubleshooting v6.0 — 5 Giugno 2026*
