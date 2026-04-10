"""
services/fastapi_worker.py — FastAPI Worker per Oh Yeah! Hub (Fase 3)
═══════════════════════════════════════════════════════════════════════════
Separa la logica AI/parsing pesante dal frontend Streamlit.

Streamlit UI  →  POST /api/classify   →  classifica_con_ai()
              →  POST /api/parse      →  estrai_dati_da_xml(file, user_id=user_id)
              →  GET  /health         →  {"status": "ok"}

Avvio locale:
    uvicorn services.fastapi_worker:app --host 0.0.0.0 --port 8000 --reload

Avvio Docker:
    docker-compose up worker

ENV VARS richieste:
    OPENAI_API_KEY          — chiave OpenAI
    SUPABASE_URL            — URL progetto Supabase
    SUPABASE_SERVICE_ROLE_KEY — service role key (non anon key)
    WORKER_RATE_LIMIT       — max richieste per minuto per IP (default: 30)
    WORKER_RATE_WINDOW_SEC  — finestra rate limit in secondi (default: 60)
"""

import asyncio
import io
import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Carica .env dalla root progetto indipendentemente dalla working directory.
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

try:
    from supabase import create_client
except Exception:  # pragma: no cover - compat con versioni precedenti
    from supabase.client import create_client

try:
    from supabase.lib.client_options import SyncClientOptions
except Exception:  # pragma: no cover - supabase v1
    SyncClientOptions = None

# ─── Path setup ────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("fastapi_worker")


# ═══════════════════════════════════════════════════════════════════════════
# RATE LIMITER (in-memory — sufficiente per Fase 3, sostituire con Redis in Fase 4)
# ═══════════════════════════════════════════════════════════════════════════

_RATE_LIMIT = int(os.getenv("WORKER_RATE_LIMIT", "30"))
_RATE_WINDOW = int(os.getenv("WORKER_RATE_WINDOW_SEC", "60"))
_QUEUE_LOOP_INTERVAL_SEC = int(os.getenv("QUEUE_LOOP_INTERVAL_SEC", "30"))
_ENABLE_INLINE_QUEUE_PROCESSOR = os.getenv("ENABLE_INLINE_QUEUE_PROCESSOR", "1").strip().lower() in {"1", "true", "yes", "on"}

# {ip: [timestamp, timestamp, ...]}
_rate_buckets: Dict[str, List[float]] = defaultdict(list)
_rate_lock = threading.Lock()  # protegge _rate_buckets da race condition multi-thread


def _check_rate_limit(ip: str) -> None:
    """Solleva 429 se l'IP supera il limite configurato nella finestra temporale."""
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets[ip]
        # Rimuovi timestamp fuori dalla finestra
        _rate_buckets[ip] = [t for t in bucket if now - t < _RATE_WINDOW]
        if len(_rate_buckets[ip]) >= _RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit: max {_RATE_LIMIT} richieste ogni {_RATE_WINDOW}s per IP.",
            )
        _rate_buckets[ip].append(now)


# ═══════════════════════════════════════════════════════════════════════════
# APP FASTAPI
# ═══════════════════════════════════════════════════════════════════════════

async def _queue_loop() -> None:
    """Esegue ciclicamente il processor coda senza bloccare l'event loop FastAPI."""
    from worker.queue_processor import run_cycle

    logger.info("🔄 Queue processor background loop avviato (intervallo=%ss)", _QUEUE_LOOP_INTERVAL_SEC)
    while True:
        try:
            stats = await asyncio.to_thread(run_cycle)
            processed = int(getattr(stats, "done", 0))
            logger.info("🔄 Queue processor cycle — pending processed: %d", processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("❌ Queue processor cycle fallito: %s", exc)

        await asyncio.sleep(_QUEUE_LOOP_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if _ENABLE_INLINE_QUEUE_PROCESSOR:
        task = asyncio.create_task(_queue_loop(), name="queue-processor-loop")
    else:
        logger.info("ℹ️ Inline queue processor disabilitato (ENABLE_INLINE_QUEUE_PROCESSOR=0)")

    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

app = FastAPI(
    lifespan=lifespan,
    title="Oh Yeah! Hub — Worker API",
    description=(
        "Worker API per classificazione AI e parsing fatture. "
        "Usato da Streamlit come backend separato in Fase 3 (50+ utenti)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


def _build_allowed_origins() -> List[str]:
    raw = os.getenv("WORKER_ALLOWED_ORIGINS", "").strip()
    if raw:
        origins = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        origins = [
            "https://ohyeah.streamlit.app",
            "https://ohyeah.app",
            "https://envoicescan-ai-production.up.railway.app",
        ]

    if "*" in origins:
        raise RuntimeError("WORKER_ALLOWED_ORIGINS non puo' contenere '*'.")

    return list(dict.fromkeys(origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════
# MODELLI PYDANTIC
# ═══════════════════════════════════════════════════════════════════════════

class ClassifyRequest(BaseModel):
    descrizioni: List[str] = Field(..., min_length=1, description="Lista descrizioni prodotti da classificare")
    fornitori: Optional[List[str]] = Field(None, description="Lista fornitori (allineata con descrizioni)")
    iva: Optional[List[int]] = Field(None, description="Lista aliquote IVA % (4, 10, 22)")
    hint: Optional[List[Optional[str]]] = Field(None, description="Lista hint categoria (o null)")
    user_id: Optional[str] = Field(None, description="ID utente — usato per caricare memoria classificazioni")
    ristorante_id: Optional[str] = Field(None, description="ID ristorante — usato per rate limit giornaliero AI")

    model_config = {"json_schema_extra": {"example": {
        "descrizioni": ["FARINA 00 KG 25", "VINO CHIANTI 0.75L"],
        "fornitori": ["MOLINO SPADONI", "ANTINORI"],
        "iva": [10, 22],
        "hint": [None, "BEVANDE"],
        "user_id": "abc-123",
        "ristorante_id": "rist-456"
    }}}


class ClassifyResponse(BaseModel):
    categorie: List[str]
    count: int
    elapsed_ms: int


class ParseResponse(BaseModel):
    fatture: List[Dict[str, Any]]
    count: int
    elapsed_ms: int


class WebhookResponse(BaseModel):
    status: str
    event_id: str
    queue_id: Optional[int] = None
    message: str


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════

@app.get(
    "/health",
    summary="Health check",
    tags=["System"],
    response_description="Stato del worker",
)
async def health() -> Dict[str, str]:
    """Endpoint di health check — usato da Docker healthcheck e load balancer."""
    return {"status": "ok", "version": app.version}


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/classify
# ═══════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/classify",
    response_model=ClassifyResponse,
    summary="Classificazione AI prodotti",
    tags=["AI"],
    responses={
        422: {"description": "Payload non valido"},
        429: {"description": "Rate limit superato"},
        500: {"description": "Errore interno classificazione"},
    },
)
async def classify(request: Request, body: ClassifyRequest) -> ClassifyResponse:
    """
    Classifica una lista di descrizioni prodotti usando GPT con memoria Supabase.

    - Carica automaticamente la memoria classificazioni dell'utente (se `user_id` fornito)
    - Applica correzioni dizionario prima della risposta
    - Ritorna le categorie nello stesso ordine dell'input
    """
    _check_rate_limit(request.client.host if request.client else request.headers.get("X-Forwarded-For", "unknown").split(",")[0].strip())

    if not body.descrizioni:
        raise HTTPException(status_code=422, detail="Lista descrizioni vuota.")

    t0 = time.monotonic()
    try:
        # Import lazy — evita carico all'avvio del worker
        from openai import OpenAI
        from services.ai_service import classifica_con_ai, carica_memoria_completa

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY non configurata.")

        # Precarica memoria classificazioni utente (se disponibile)
        if body.user_id:
            try:
                carica_memoria_completa(body.user_id)
                logger.info(f"✅ Memoria precaricata per user_id={body.user_id}")
            except Exception as mem_err:
                logger.warning(f"⚠️ Memoria non caricata per user_id={body.user_id}: {mem_err}")

        openai_client = OpenAI(api_key=openai_api_key)
        categorie = classifica_con_ai(
            lista_descrizioni=body.descrizioni,
            lista_fornitori=body.fornitori,
            lista_iva=body.iva,
            lista_hint=body.hint,
            openai_client=openai_client,
            ristorante_id=body.ristorante_id,
        )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"✅ /api/classify: {len(body.descrizioni)} descrizioni → {elapsed_ms}ms"
            + (f" user_id={body.user_id}" if body.user_id else "")
        )
        return ClassifyResponse(
            categorie=categorie,
            count=len(categorie),
            elapsed_ms=elapsed_ms,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"❌ /api/classify errore: {exc}")
        raise HTTPException(status_code=500, detail=f"Errore classificazione: {str(exc)}")


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/parse
# ═══════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/parse",
    response_model=ParseResponse,
    summary="Parsing fattura XML / P7M",
    tags=["Parsing"],
    responses={
        422: {"description": "File non valido o formato non supportato"},
        429: {"description": "Rate limit superato"},
        500: {"description": "Errore interno parsing"},
    },
)
async def parse_invoice(
    request: Request,
    file: UploadFile = File(..., description="File XML o P7M (fattura elettronica italiana)"),
    user_id: Optional[str] = Form(None, description="ID utente per precarico memoria"),
) -> ParseResponse:
    """
    Estrae le righe prodotto da una fattura elettronica XML o P7M.

    - Supporta XML fattura elettronica italiana (FatturaPA)
    - Supporta P7M (busta CAdES — estrae XML interno automaticamente)
    - Categorizza automaticamente con memoria utente (keyword + DB)
    - Non richiede Streamlit session_state — user_id passato esplicitamente
    """
    _check_rate_limit(request.client.host if request.client else request.headers.get("X-Forwarded-For", "unknown").split(",")[0].strip())

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("xml", "p7m"):
        raise HTTPException(
            status_code=422,
            detail=f"Formato non supportato: '{ext}'. Carica un file XML o P7M.",
        )

    t0 = time.monotonic()
    try:
        contents = await file.read()

        # Limite dimensione upload: 50MB
        if len(contents) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="File troppo grande (max 50MB).",
            )

        # Estrai XML da busta P7M (se necessario)
        if ext == "p7m":
            from services.invoice_service import estrai_xml_da_p7m

            xml_bytes = estrai_xml_da_p7m(io.BytesIO(contents))
            if xml_bytes is None:
                raise HTTPException(
                    status_code=422,
                    detail="Impossibile estrarre XML dal file P7M.",
                )
            contents = xml_bytes.read() if hasattr(xml_bytes, "read") else xml_bytes
            filename = filename[:-4]  # rimuove .p7m → .xml

        # ── Wrapper senza session_state ───────────────────────────────────
        # estrai_dati_da_xml legge st.session_state internamente per il user_id.
        # Qui giriamo intorno iniettando user_id nella memoria prima della chiamata.
        from services.ai_service import carica_memoria_completa
        from services.invoice_service import estrai_dati_da_xml

        if user_id:
            try:
                carica_memoria_completa(user_id)
            except Exception as mem_err:
                logger.warning(f"⚠️ Memoria non caricata: {mem_err}")

        # Wrap contents in un file-like con attributo .name (richiesto da estrai_dati_da_xml)
        file_like = io.BytesIO(contents)
        file_like.name = filename  # type: ignore[attr-defined]

        # Patch temporanea session_state (solo per la durata della chiamata)
        # Necessaria perché estrai_dati_da_xml accede a st.session_state.
        # Alternativa a lungo termine: fare PR su invoice_service per accettare user_id param.
        import streamlit as _st
        _previous_user_data = _st.session_state.get("user_data")
        try:
            _st.session_state["user_data"] = {"id": user_id} if user_id else {}
            righe = estrai_dati_da_xml(file_like)
        finally:
            # Ripristina sempre lo state precedente (safe anche in caso di eccezione)
            if _previous_user_data is None:
                _st.session_state.pop("user_data", None)
            else:
                _st.session_state["user_data"] = _previous_user_data

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"✅ /api/parse: {filename} → {len(righe)} righe in {elapsed_ms}ms"
            + (f" user_id={user_id}" if user_id else "")
        )

        # Serializza righe (potrebbero contenere tipi non-JSON come Decimal/date)
        righe_serial = _serialize_rows(righe)

        return ParseResponse(
            fatture=righe_serial,
            count=len(righe_serial),
            elapsed_ms=elapsed_ms,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"❌ /api/parse errore: {exc}")
        raise HTTPException(status_code=500, detail=f"Errore parsing: {str(exc)}")


# ═══════════════════════════════════════════════════════════════════════════
# POST /webhook
# ═══════════════════════════════════════════════════════════════════════════

def _get_supabase_client():
    """Client Supabase service-role per operazioni backend del worker."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase non configurato (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).")

    if SyncClientOptions is None:
        return create_client(url, key)

    options = SyncClientOptions(
        postgrest_client_timeout=30,
        storage_client_timeout=30,
    )
    return create_client(url, key, options=options)


def _looks_like_supabase_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "invalid api key" in msg
        or "401" in msg
        or "service_role" in msg
        or "anon" in msg
    )


def _normalize_piva(value: str) -> str:
    raw = (value or "").strip().upper().replace(" ", "")
    if raw.startswith("IT"):
        raw = raw[2:]
    return "".join(ch for ch in raw if ch.isalnum())


def _extract_piva_from_xml(xml_text: str) -> str:
    """Estrae la P.IVA del destinatario: CessionarioCommittente, con fallback finale sul Cedente."""
    import xmltodict

    def _dig(obj: Any, path: List[str]) -> str:
        cur = obj
        for key in path:
            if not isinstance(cur, dict):
                return ""
            cur = cur.get(key)
        return str(cur or "").strip()

    data = xmltodict.parse(xml_text)

    fattura = data.get("FatturaElettronica") or data.get("p:FatturaElettronica") or {}
    header = (
        fattura.get("FatturaElettronicaHeader")
        or fattura.get("p:FatturaElettronicaHeader")
        or {}
    )

    for path in (
        [
            "CessionarioCommittente",
            "DatiAnagrafici",
            "IdFiscaleIVA",
            "IdCodice",
        ],
        [
            "p:CessionarioCommittente",
            "p:DatiAnagrafici",
            "p:IdFiscaleIVA",
            "p:IdCodice",
        ],
        [
            "CedentePrestatore",
            "DatiAnagrafici",
            "IdFiscaleIVA",
            "IdCodice",
        ],
        [
            "p:CedentePrestatore",
            "p:DatiAnagrafici",
            "p:IdFiscaleIVA",
            "p:IdCodice",
        ],
    ):
        piva = _dig(header, path)
        if piva:
            return _normalize_piva(piva)

    return ""


def _resolve_tenant_by_piva(supabase, piva_raw: str) -> tuple[Optional[str], Optional[str]]:
    """Risoluzione tenant: prima piva_ristoranti, poi fallback ristoranti."""
    piva = _normalize_piva(piva_raw)
    if not piva:
        return None, None

    try:
        lookup = (
            supabase.table("piva_ristoranti")
            .select("user_id,ristorante_id")
            .eq("piva", piva)
            .limit(1)
            .execute()
        )
        rows = lookup.data or []
        if rows:
            return rows[0].get("user_id"), rows[0].get("ristorante_id")
    except Exception:
        # Fallback su ristoranti se la tabella lookup non e' disponibile.
        pass

    try:
        lookup = (
            supabase.table("ristoranti")
            .select("id,user_id")
            .eq("partita_iva", piva)
            .eq("attivo", True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if _looks_like_supabase_auth_error(exc):
            raise HTTPException(
                status_code=500,
                detail="Supabase auth non valida nel worker (controlla SUPABASE_SERVICE_ROLE_KEY su Railway).",
            )
        raise
    rows = lookup.data or []
    if not rows:
        return None, None
    return rows[0].get("user_id"), rows[0].get("id")


def _verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Verifica HMAC-SHA256 con formato Invoicetronic: t=...,v1=..."""
    import hashlib
    import hmac as _hmac

    header = (signature_header or "").strip()
    if not header:
        return False

    parts: dict[str, str] = {}
    for seg in header.split(","):
        idx = seg.find("=")
        if idx > 0:
            parts[seg[:idx].strip()] = seg[idx + 1:].strip()

    ts = parts.get("t", "")
    sig = parts.get("v1", "")
    if not ts or not sig:
        return False

    # Anti-replay: rifiuta timestamp fuori finestra 5 min
    try:
        ts_num = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_num) > 300:
        return False

    # HMAC-SHA256("{ts}.{rawBody}", secret) — formato Invoicetronic
    message = f"{ts}.".encode("utf-8") + raw_body
    expected = _hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, sig)


def _load_xml_from_payload(payload: dict[str, Any]) -> str:
    import base64

    xml_base64 = (
        payload.get("xml_base64")
        or payload.get("fattura_b64")
        or payload.get("xmlContentBase64")
        or payload.get("xml_content_base64")
    )
    if xml_base64:
        try:
            xml_bytes = base64.b64decode(str(xml_base64), validate=False)
            return xml_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"xml base64 non valido: {exc}")

    xml_text = payload.get("xml_content") or payload.get("xml")
    if xml_text:
        return str(xml_text)

    raise HTTPException(status_code=422, detail="Payload webhook privo di XML (xml_base64/fattura_b64/xml_content).")


def _extract_event_id(payload: dict[str, Any]) -> str:
    event_id = payload.get("event_id") or payload.get("eventId") or payload.get("id")
    event_id = str(event_id or "").strip()
    if not event_id:
        raise HTTPException(status_code=422, detail="event_id mancante nel payload webhook.")
    return event_id


@app.post(
    "/webhook",
    include_in_schema=False,
)
async def invoicetronic_webhook_disabled() -> JSONResponse:
    """Endpoint dismesso: il webhook pubblico vive nella Supabase Edge Function."""
    raise HTTPException(
        status_code=410,
        detail="Webhook Invoicetronic disattivato su FastAPI worker. Usa la Supabase Edge Function.",
    )


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def _serialize_rows(rows: List[Any]) -> List[Dict[str, Any]]:
    """
    Converte righe fattura in dizionari JSON-safe.
    Gestisce Decimal, date, datetime e altri tipi non serializzabili.
    """
    import decimal
    from datetime import date, datetime

    def _convert(v: Any) -> Any:
        if isinstance(v, decimal.Decimal):
            return float(v)
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v

    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append({k: _convert(v) for k, v in row.items()})
        else:
            result.append(row)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT (avvio diretto: python services/fastapi_worker.py)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.fastapi_worker:app",
        host="0.0.0.0",
        port=int(os.getenv("WORKER_PORT", "8000")),
        reload=os.getenv("WORKER_RELOAD", "false").lower() == "true",
        log_level="info",
    )
