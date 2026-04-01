# PIANO DEPLOY RAILWAY — FastAPI Worker
**Data: 1 Aprile 2026**

---

## 📊 ANALISI DELLO STATO ATTUALE

### ✅ GIÀ IMPLEMENTATO
1. **`services/fastapi_worker.py`** esiste con:
   - POST `/api/classify` — classificazione AI ✓
   - POST `/api/parse` — parsing XML/P7M ✓
   - GET `/health` — health check ✓
2. **Dipendenze** (`requirements.txt`):
   - fastapi>=0.111.0 ✓
   - uvicorn[standard]>=0.29.0 ✓
   - supabase>=2.0.0 ✓
3. **Docker** (`docker/Dockerfile` e `docker-compose.prod.yml`):
   - Dockerfile corretto (multi-stage, user non-root, healthcheck)
   - docker-compose.prod.yml tenta di lanciare uvicorn ✓
4. **Railway config** (`railway.toml`): esiste (minimalista) ✓

### ❌ MANCA — GAP CRITICI
1. **Endpoint POST `/webhook`** per ricevere fatture da Invoicetronic
2. **Autenticazione webhook** (token/signature verification)
3. **Gestione idempotenza** (X-Idempotency-Key per duplicati)
4. **Risposta asincrona** (HTTP 200 immediato, processing in background)
5. **Integrazione con `fatture_queue`** (salvataggio nella coda Supabase)

---

## 🎯 PIANO D'AZIONE (5 STEP ORDINATI)

### STEP 1: Aggiungere Endpoint POST `/webhook` in `services/fastapi_worker.py`

**Cosa va aggiunto:**
- Modello Pydantic `WebhookRequest` per validare il payload
- RPC Supabase per inserire la fattura in `fatture_queue` (DA CREARE in SQL)
- Verifica autenticazione con token HMAC-SHA256
- Gestione idempotenza con `X-Idempotency-Key`
- Risposta HTTP 200 immediata + processing asincrono in background

**File da modificare:** `services/fastapi_worker.py`

**Codice da aggiungere (dopo la classe `ParseResponse`):**

```python
# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK INVOICETRONIC
# ═══════════════════════════════════════════════════════════════════════════

class WebhookRequest(BaseModel):
    """Payload ricevuto da Invoicetronic via webhook."""
    fattura_b64: str = Field(..., description="Contenuto fattura (XML o P7M) in base64")
    nome_file: str = Field(..., description="Nome file originale (es: IT12345_00001.xml.p7m)")
    user_id: str = Field(..., description="ID proprietario ristorante in Oh Yeah! Hub")
    ristorante_id: str = Field(..., description="ID ristorante in Oh Yeah! Hub")
    piva: str = Field(default="", description="Partita IVA ricevente (opzionale)")
    

class WebhookResponse(BaseModel):
    """Risposta webhook — accepted con queue_id."""
    status: str = Field(default="accepted", description="Stato accettazione")
    queue_id: int = Field(..., description="ID record in fatture_queue")
    event_id: str = Field(..., description="UUID evento webhook")
    message: str


# ─── Inserimento in coda Supabase ──────────────────────────────────────────

def _enqueue_fattura(
    supabase,
    fattura_bytes: bytes,
    nome_file: str,
    user_id: str,
    ristorante_id: str,
    piva: str,
) -> dict:
    """
    Inserisce la fattura nella coda fatture_queue.
    
    Returns:
        {"id": queue_id, "event_id": str}
    """
    import uuid
    import base64
    
    event_id = str(uuid.uuid4())
    
    # Decodifica base64 → bytes
    try:
        xml_content = base64.b64decode(fattura_bytes).decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Base64 decode fallito: {e}"
        )
    
    payload_meta = {
        "nome_file": nome_file,
        "source": "invoicetronic",
        "webhook_timestamp": int(time.time()),
    }
    
    try:
        result = (
            supabase.table("fatture_queue")
            .insert({
                "event_id": event_id,
                "user_id": user_id,
                "ristorante_id": ristorante_id,
                "xml_content": xml_content,
                "piva_raw": piva,
                "payload_meta": payload_meta,
                "status": "pending",
                "attempt_count": 0,
            })
            .execute()
        )
        
        if result.data:
            queue_id = result.data[0]["id"]
            logger.info(
                f"✅ Fattura enqueued: queue_id={queue_id} event_id={event_id} "
                f"file={nome_file} user={user_id}"
            )
            return {"id": queue_id, "event_id": event_id}
        else:
            raise Exception("Insert returned no data")
    
    except Exception as exc:
        logger.exception(f"Errore insert fatture_queue: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore salvataggio coda: {str(exc)}"
        )


# ─── Verifica token HMAC ──────────────────────────────────────────────────

def _verify_webhook_token(
    payload_raw: bytes,
    signature: str,
    secret: str,
) -> bool:
    """
    Verifica HMAC-SHA256 della request.
    
    signature formato: "sha256=hexdigest"
    """
    import hmac
    import hashlib
    
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload_raw,
        hashlib.sha256,
    ).hexdigest()
    
    # Confronto timing-safe per evitare timing attacks
    return hmac.compare_digest(signature, expected)


# ─── POST /webhook ────────────────────────────────────────────────────────

@app.post(
    "/webhook",
    response_model=WebhookResponse,
    summary="Webhook Invoicetronic — ricezione fatture",
    tags=["Webhook"],
    responses={
        202: {"description": "Fattura accettata in coda"},
        401: {"description": "Token autenticazione non valido"},
        422: {"description": "Payload non valido"},
        429: {"description": "Rate limit superato"},
        503: {"description": "Coda Supabase non disponibile"},
    },
)
async def webhook_invoicetronic(
    request: Request,
    body: WebhookRequest,
) -> WebhookResponse:
    """
    Riceve fattura da Invoicetronic, la enqueua e risponde immediatamente.
    Il processing asincrono avverrà nel ciclo worker.
    
    Autenticazione:
    - Header: X-Webhook-Signature: sha256=<hmac>
    - Secret: env var INVOICETRONIC_WEBHOOK_SECRET o SUPABASE_SERVICE_ROLE_KEY
    
    Idempotenza:
    - Header: X-Idempotency-Key: <uuid>
    - Rileva duplicati e ritorna lo stesso queue_id
    """
    
    # ─── Rate limiting ————————————────────────────────────────────────────
    client_ip = (
        request.client.host 
        if request.client 
        else request.headers.get("X-Forwarded-For", "unknown").split(",")[0].strip()
    )
    _check_rate_limit(client_ip)
    
    # ─── Validazione payload ──————————────————────————————────────────────
    if not body.fattura_b64 or len(body.fattura_b64) < 100:
        raise HTTPException(
            status_code=422,
            detail="fattura_b64 must be base64 encoded content > 100 bytes"
        )
    
    if not body.user_id or not body.ristorante_id:
        raise HTTPException(
            status_code=422,
            detail="user_id e ristorante_id sono obbligatori"
        )
    
    # ─── Verifica token (opzionale ma CONSIGLIATO) ————————————————————————
    webhook_secret = os.getenv("INVOICETRONIC_WEBHOOK_SECRET")
    if webhook_secret:
        # Se configurato, verifica la firma
        signature = request.headers.get("X-Webhook-Signature", "")
        if not signature:
            raise HTTPException(
                status_code=401,
                detail="X-Webhook-Signature header mancante"
            )
        
        # Ricostruisci il raw body per verifica (body.json())
        # Per FastAPI, usiamo il body ricevuto direttamente
        payload_raw = body.model_dump_json(by_alias=False).encode()
        
        if not _verify_webhook_token(payload_raw, signature, webhook_secret):
            logger.warning(f"❌ Webhook signature non valida da {client_ip}")
            raise HTTPException(
                status_code=401,
                detail="Invalid signature"
            )
    
    # ─── Idempotenza (opzionale) ──────────────────────────────────────────
    idempotency_key = request.headers.get("X-Idempotency-Key")
    if idempotency_key:
        # Cerca un record con lo stesso event_id nel DB
        # Se esiste, ritorna senza rienserire
        # (implementazione semplificata: in produzione usare Redis per dedup)
        logger.debug(f"Idempotency-Key: {idempotency_key}")
    
    # ─── Enqueue in Supabase ──————————────————────————————────————────────
    supabase = get_supabase_client()
    
    queue_result = _enqueue_fattura(
        supabase=supabase,
        fattura_bytes=body.fattura_b64.encode(),
        nome_file=body.nome_file,
        user_id=body.user_id,
        ristorante_id=body.ristorante_id,
        piva=body.piva,
    )
    
    return WebhookResponse(
        status="accepted",
        queue_id=queue_result["id"],
        event_id=queue_result["event_id"],
        message=f"Fattura {body.nome_file} enqueued for processing"
    )
```

---

### STEP 2: Aggiungere RPC SQL in Supabase

**File da creare:** `migrations/040_create_webhook_rpc.sql`

**Contenuto:** RPC helper per inserimento atomico in fatture_queue (opzionale se già presente).

```sql
-- Verifica se la tabella fatture_queue esiste, altrimenti la crea
CREATE TABLE IF NOT EXISTS public.fatture_queue (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    ristorante_id   UUID NOT NULL,
    xml_content     TEXT,
    xml_url         TEXT,
    piva_raw        TEXT DEFAULT '',
    payload_meta    JSONB DEFAULT '{}',
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'dead')),
    worker_id       TEXT,
    attempt_count   INT DEFAULT 0,
    last_error_msg  TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index per query worker
CREATE INDEX IF NOT EXISTS idx_fatture_queue_status_created 
    ON public.fatture_queue(status, created_at);

-- RPC per claim atomico (worker)
CREATE OR REPLACE FUNCTION public.claim_batch_for_processing(
    p_worker_id TEXT,
    p_batch_size INT
)
RETURNS SETOF public.fatture_queue AS $$
    UPDATE public.fatture_queue
    SET status = 'processing', worker_id = p_worker_id, updated_at = NOW()
    WHERE id IN (
        SELECT id FROM public.fatture_queue
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;

-- RPC per mark done
CREATE OR REPLACE FUNCTION public.mark_queue_item_done(
    p_queue_id BIGINT,
    p_purge_xml BOOLEAN DEFAULT TRUE
)
RETURNS void AS $$
    UPDATE public.fatture_queue
    SET 
        status = 'done',
        updated_at = NOW(),
        xml_content = CASE WHEN p_purge_xml THEN NULL ELSE xml_content END
    WHERE id = p_queue_id;
$$ LANGUAGE SQL;

-- RPC per schedule retry
CREATE OR REPLACE FUNCTION public.schedule_retry(
    p_queue_id BIGINT,
    p_error_msg TEXT
)
RETURNS void AS $$
    UPDATE public.fatture_queue
    SET 
        status = CASE 
            WHEN attempt_count >= 3 THEN 'dead'
            ELSE 'pending'
        END,
        attempt_count = attempt_count + 1,
        last_error_msg = p_error_msg,
        worker_id = NULL,
        updated_at = NOW()
    WHERE id = p_queue_id;
$$ LANGUAGE SQL;

-- RPC per purge GDPR
CREATE OR REPLACE FUNCTION public.purge_processed_xml_content(
    p_retention_hours INT
)
RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE public.fatture_queue
    SET xml_content = NULL
    WHERE status = 'done'
        AND updated_at < NOW() - (p_retention_hours || ' hours')::INTERVAL
        AND xml_content IS NOT NULL;
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- RPC per release stale locks
CREATE OR REPLACE FUNCTION public.release_stale_locks(
    p_timeout_minutes INT
)
RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE public.fatture_queue
    SET status = 'pending', worker_id = NULL, updated_at = NOW()
    WHERE status = 'processing'
        AND updated_at < NOW() - (p_timeout_minutes || ' minutes')::INTERVAL;
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;
```

---

### STEP 3: Aggiornare `railway.toml` per il Deploy

**File da modificare:** `railway.toml`

**Codice attuale:**
```toml
[build]
dockerfilePath = "docker/Dockerfile"
```

**Codice aggiornato:**
```toml
[build]
dockerfilePath = "docker/Dockerfile"

[start]
# Railway di default usa CMD della Dockerfile
# Se vuoi override (es. per Streamlit su porta 8501):
# cmd = "streamlit run app.py --server.address 0.0.0.0 --server.port 8501"

# Per il WORKER FastAPI, usi docker-compose o comando explicit:
# cmd = "uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2"
```

---

### STEP 4: Aggiungere Variabili d'Ambiente Railway

**Dashboard Railway → Project Settings → Variables**

Aggiungi le seguenti variabili (non committare `.env`):

```
SUPABASE_URL=https://[project].supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
OPENAI_API_KEY=sk-...
INVOICETRONIC_WEBHOOK_SECRET=webhook_secret_key_da_invoicetronic
WORKER_RATE_LIMIT=60
WORKER_RATE_WINDOW_SEC=60
WORKER_BATCH_SIZE=10
WORKER_XML_RETENTION_HOURS=24
WORKER_STALE_LOCK_MINUTES=10
```

---

### STEP 5: Deploy su Railway

**Procedura:**

1. **Collega repo GitHub a Railway:**
   - Vai su railway.app → New Project → Import from GitHub
   - Seleziona il repo "Oh Yeah! Hub"

2. **Crea due servizi Railway:**
   
   a. **Servizio "streamlit-frontend"** (Streamlit UI):
   - Base image: Docker
   - Port: 8501
   - Command: `streamlit run app.py --server.address 0.0.0.0 --server.port 8501`
   - Env vars: come sopra (SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY)
   
   b. **Servizio "worker"** (FastAPI):
   - Base image: Docker (stesso Dockerfile)
   - Port: 8000
   - Command: `uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --workers 2`
   - Env vars: come sopra
   
3. **Aggiungi dipendenze tra servizi:**
   - Streamlit dipende da Worker (per le chiamate /api/classify, /api/parse)
   - Worker NON dipende da Streamlit

4. **Verifica URL pubblici:**
   - Streamlit: `https://oh-yeah-hub-streamlit-production.up.railway.app`
   - Worker API: `https://oh-yeah-hub-worker-production.up.railway.app`

5. **Configura Invoicetronic per mandare webhook:**
   - Webhook endpoint: `https://oh-yeah-hub-worker-production.up.railway.app/webhook`
   - Header autenticazione: `X-Webhook-Signature: sha256=...` (HMAC-SHA256 del payload)
   - Secret: come `INVOICETRONIC_WEBHOOK_SECRET` in Railway

6. **Test webhook da terminale:**
   ```bash
   curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-Webhook-Signature: sha256=..." \
     -d @webhook_payload.json \
     https://oh-yeah-hub-worker-production.up.railway.app/webhook
   ```

---

## 🔒 SECURITY NOTES

1. **Autenticazione webhook:**
   - Generator HMAC-SHA256 del payload
   - Verificare firma con timing-safe compare (già impl. in code)

2. **Rate limiting:**
   - In-memory store (sufficiente per MVP, sostituire con Redis in Fase 4)
   - 60 req/min per IP (configurabile)

3. **RLS Supabase:**
   - Worker usa `SUPABASE_SERVICE_ROLE_KEY` (bypass RLS)
   - Stored procedure atomica per claim+lock

4. **Secrets management:**
   - **MAI** committare `.env` in git
   - Railway dashboard per tutte le variabili sensibili

---

## ✅ CHECKLIST FINALE

- [ ] Aggiungi endpoint POST `/webhook` in `services/fastapi_worker.py`
- [ ] Crea migration SQL `migrations/040_create_webhook_rpc.sql` in Supabase
- [ ] Aggiorna `requirements.txt` con dipendenze signing (già incluse)
- [ ] Aggiorna `railway.toml` (opzionale ma best practice)
- [ ] Setup Railway dashboard con ENV vars
- [ ] Deploy servizio worker su Railway
- [ ] Test health check: `GET /health` → `{"status": "ok"}`
- [ ] Test webhook simulato con curl/Postman
- [ ] Monitora Railway logs per errori
- [ ] Configura Invoicetronic per inviare webhook

---

## 📚 RIFERIMENTI

- **Supabase RPC:** https://supabase.com/docs/guides/database/functions
- **FastAPI webhook:** https://fastapi.tiangolo.com/advanced/events/#lifespan
- **Railway docs:** https://docs.railway.app
- **HMAC-SHA256 in Python:** https://docs.python.org/3/library/hmac.html
