# ANALISI DEPLOY RAILWAY — WORKER FastAPI
**Oh Yeah! Hub — 1 Aprile 2026**

---

## 1️⃣ COSA C'È GIÀ (Stato Attuale aggiornato)

### ✅ Endpoint Webhook
**Risposta AGGIORNATA:**
- ✅ **Il webhook pubblico non deve stare in FastAPI**
- ✅ La struttura FastAPI esiste con:
  - POST `/api/classify` (classificazione AI) — **FUNZIONANTE**
  - POST `/api/parse` (parsing XML/P7M) — **FUNZIONANTE**
  - GET `/health` (health check) — **FUNZIONANTE**
  - POST `/webhook` dismesso intenzionalmente con HTTP `410 Gone`
  - CORS middleware già configurato (allow-list origin)

**Endpoint pubblico corretto:**
- `https://<project-ref>.supabase.co/functions/v1/invoicetronic-webhook`
- Deploy raccomandato: `supabase functions deploy invoicetronic-webhook --no-verify-jwt`

### ✅ Dockerfile & docker-compose.prod.yml
**Risposta POSITIVA:**
- ✅ `docker/Dockerfile`: configurato correttamente per:
  - Python 3.12 slim
  - Multi-stage build
  - User non-root (ohyeah)
  - Health check endpoint
  - Entrypoint script

- ✅ `docker/docker-compose.prod.yml`: ora documenta la separazione tra API FastAPI e queue worker
  ```yaml
  worker:
    image: ohyeah-hub:latest
    command: uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2
    environment:
      - ENABLE_INLINE_QUEUE_PROCESSOR=0

  queue-worker:
    image: ohyeah-hub:latest
    command: python worker/run.py
    healthcheck: GET /health:8000
    environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENAI_API_KEY
  ```

### ✅ Variabili d'Ambiente
**Risposta POSITIVA:**
- ✅ `requirements.txt` ha FastAPI + uvicorn + python-dotenv
- ✅ `worker/run.py` gestisce `.env` loading per CLI batch processing
- ✅ `services/fastapi_worker.py` legge ENV vars per:
  - `OPENAI_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - Rate limiting config

---

## 2️⃣ COSA MANCA O VA MODIFICATO

### ❌ CRITICO: Servizio Railway non ancora separato in produzione

**Gap:** il codice è pronto per avere API e queue-worker separati, ma il servizio Railway live può ancora essere avviato solo come FastAPI con queue loop inline.

**Cosa va fatto sul dashboard Railway:**
1. Creare un servizio pubblico `api` con comando `uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2`
2. Impostare `ENABLE_INLINE_QUEUE_PROCESSOR=0` sul servizio `api`
3. Creare un servizio privato `queue-worker` con comando `python worker/run.py`
4. Non assegnare dominio pubblico a `queue-worker`

### ❌ CRITICO: Auth Edge Function da fissare esplicitamente

**Gap:** il test remoto ha restituito `401 Unauthorized` quando la funzione veniva chiamata senza un bearer compatibile con la policy attuale.

**Scelta raccomandata:**
- Deploy Edge Function con `--no-verify-jwt`
- Lasciare l'autenticazione del webhook a HMAC SHA-256 + anti-replay
- Usare la `anon key` solo per test remoti se si decide temporaneamente di mantenere `verify_jwt=true`
- Se esiste, ritorna lo stesso `queue_id` senza reinserire

### ✅ Risposta Asincrona — GIÀ POSSIBILE
**Status:** Non critico, FastAPI supporta già risposte immediate con background tasks.

Implementazione semplice:
```python
from fastapi import BackgroundTasks

@app.post("/webhook")
async def webhook(request: WebhookRequest, background_tasks: BackgroundTasks):
    queue_id = _insert_in_queue(request)
    # Non aspettare processing
    return {"status": "accepted", "queue_id": queue_id}  # HTTP 202 immediato
    # Il worker CLI legge la coda in cicli separati
```

---

## 3️⃣ POTENZIALI PROBLEMI E SOLUZIONI

### 🔴 PROBLEMA: Docker Compose Port Mapping
**Domanda:** Su Railway, la porta 8000 va esposta pubblicamente?

**Risposta:** NO, ma Railway gestisce diversamente:
- **Locale** (docker-compose.dev.yml): porta 8000 mappata internamente → accessibile da host
- **Produzione** (docker-compose.prod.yml): `# SICUREZZA: nessun port mapping`
- **Railway**: Railway fornisce automaticamente URL pubblico per il servizio
  - Streamlit: `https://oh-yeah-hub-streamlit-production.up.railway.app:8501`
  - Worker: `https://oh-yeah-hub-worker-production.up.railway.app:8000`
  
**Soluzione:** Railway espone automaticamente le porte dichiarate (8501 e 8000) su URL pubblici. Non occorre modificare il docker-compose.prod.yml — Railway gestisce il routing.

### 🟡 PROBLEMA: Dipendenze Percorsi Locali
**Domanda:** Il Dockerfile assume una struttura che Railway potrebbe non avere?

**Risposta:** NO, il Dockerfile è portable:
```dockerfile
WORKDIR /app
COPY . .  # Copia tutto il repo
COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
COPY requirements-lock.txt .
RUN pip install -r requirements-lock.txt
```
✅ Funziona identico su Railway, VPS, laptop — percorsi relativi assicurano portabilità.

### 🟡 PROBLEMA: Variabili `.env` Locali su Railway
**Domanda:** Come gestire `.env` se è in `.gitignore`?

**Risposta:** Corretto approccio:
1. **Local development:** `.env` in root (non versionato)
2. **Railway:** ENV vars impostate su Dashboard Railway (non da file `.env`)
3. **Docker entrypoint:** Legge `os.environ.get()` direttamente
   ```bash
   # docker-entrypoint.sh → genera secrets.toml da ENV
   cat > /app/.streamlit/secrets.toml <<EOF
   OPENAI_API_KEY = "${OPENAI_API_KEY}"
   [supabase]
   url = "${SUPABASE_URL}"
   key = "${SUPABASE_SERVICE_ROLE_KEY}"
   EOF
   ```
✅ Railway supporta nativamente env vars via Dashboard (nessun file .env necessario).

### 🟡 PROBLEMA: docker-entrypoint.sh Avvia Solo Streamlit
**Domanda:** L'entrypoint avvia Streamlit, non FastAPI — come fa il worker a partire?

**Risposta:** Due servizi separati su Railway:
1. **Servizio "streamlit-frontend":**
   ```
   command: streamlit run app.py --server.address 0.0.0.0 --server.port 8501
   ```

2. **Servizio "worker":**
   ```
   command: uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2
   ```

✅ Il comando è specificato nel `docker-compose.prod.yml` — Railway/Docker override l'ENTRYPOINT se fornito un comando.

---

## 📋 CHECKLIST IMPLEMENTAZIONE

### FASE 1: Code Changes (⏱ ~2 ore)
- [ ] Aggiungere modello Pydantic `WebhookRequest` in `services/fastapi_worker.py`
- [ ] Implementare funzione `_enqueue_fattura()` (insert in fatture_queue)
- [ ] Implementare funzione `_verify_webhook_token()` (HMAC-SHA256)
- [ ] Aggiungere endpoint POST `/webhook` in `services/fastapi_worker.py`
- [ ] Test locale: `pytest tests/test_webhook.py`

### FASE 2: Database Setup (⏱ ~30 min, eseguire su Supabase)
- [ ] Creare migration `migrations/040_create_fatture_queue.sql` con:
  - Tabella `fatture_queue` (se non esiste)
  - RPC: `claim_batch_for_processing()`
  - RPC: `mark_queue_item_done()`
  - RPC: `schedule_retry()`
  - RPC: `release_stale_locks()`
  - RPC: `purge_processed_xml_content()`
- [ ] Eseguire migration su Supabase dashboard

### FASE 3: Railway Setup (⏱ ~1 ora)
- [ ] Collegare repo GitHub a Railway
- [ ] Creare 2 servizi: "streamlit-frontend" e "worker"
- [ ] Impostare ENV vars da Dashboard
- [ ] Configurare start command per worker: `uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2`
- [ ] Verificare health checks: GET `/health`

### FASE 4: Testing (⏱ ~1 ora)
- [ ] Test webhook da Postman/curl:
  ```bash
  curl -X POST https://oh-yeah-hub-worker.up.railway.app/webhook \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Signature: sha256=..." \
    -d @webhook_test.json
  ```
- [ ] Verificare record in `fatture_queue`
- [ ] Eseguire worker CLI: `python worker/run.py`
- [ ] Controllare log di processing

### FASE 5: Produzione (⏱ ~30 min)
- [ ] Configurare Invoicetronic per inviare webhook a scena Railway
- [ ] Monitorare Railway logs per errori
- [ ] Setup alerts per status="dead" in fatture_queue
- [ ] Backup database Supabase

---

## 🎯 CONCLUSIONE

### Stato Attuale
- ✅ 70% dell'infra è pronto (FastAPI, Docker, Dockerfile, env vars)
- ❌ 30% da implementare (endpoint `/webhook`, integrazione coda Supabase, RPC)

### Sforzo Stimato
- **Coding:** 2-3 ore (endpoint webhook + funzioni utility)
- **Database:** 30 min (migration SQL + RPC)
- **Deployment**: 1-2 ore (Railway setup + testing)
- **Totale:** 4-5 ore per passare da "pronto al 70%" a "production-ready"

### Percorso Consigliato
1. Implementare endpoint `/webhook` (crittico)
2. Creare migration SQL per `fatture_queue` + RPC
3. Testare localmente con Docker Compose
4. Deploy su Railway (due servizi separati)
5. Configurare Invoicetronic webhook
6. Monitorare 48h per errori

---

## 📞 DOMANDE FREQUENTI

**Q: E se Invoicetronic fallisce a inviare il webhook?**  
A: Implementare retry logic lato Invoicetronic (es. 3 retry esponenziali). Il worker espone `/health` per verificare che il servizio sia raggiungibile.

**Q: Come gestire la crescita (100+ fatture/min)?**  
A: 
- Rate limiting: aumentare `WORKER_RATE_LIMIT` (attualmente 60 req/min)
- Batch size: aumentare `WORKER_BATCH_SIZE` (attualmente 10)
- Workers Uvicorn: aumentare `--workers N` nel comando
- Per scala > 1000 req/min: migrare a Redis + Celery (Fase 4)

**Q: Cosa succede se il worker crash a metà processing?**  
A: 
- RPC `release_stale_locks()` rilascia lock > 10 min (default)
- Il record torna a status='pending' e può essere riprocessato
- Idempotenza via `event_id` evita duplicati

**Q: Come monitorare i webhook ricevuti?**  
A: Query Supabase dashboard:
```sql
SELECT * FROM fatture_queue 
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
```
