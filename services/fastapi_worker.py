"""
services/fastapi_worker.py — FastAPI Worker per ONEFLUX (Fase 3)
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

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

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
WORKER_SECRET_KEY = os.getenv("WORKER_SECRET_KEY", "")
_QUEUE_LOOP_INTERVAL_SEC = int(os.getenv("QUEUE_LOOP_INTERVAL_SEC", "30"))
_ENABLE_INLINE_QUEUE_PROCESSOR = os.getenv("ENABLE_INLINE_QUEUE_PROCESSOR", "1").strip().lower() in {"1", "true", "yes", "on"}

# {ip: [timestamp, timestamp, ...]}
_rate_buckets: Dict[str, List[float]] = defaultdict(list)
_rate_lock = threading.Lock()  # protegge _rate_buckets da race condition multi-thread
_rate_buckets_last_cleanup: float = 0.0
_RATE_BUCKETS_CLEANUP_INTERVAL = 3600.0  # cleanup ogni ora
_RATE_BUCKETS_MAX_SIZE = 10000  # max IP tracciati simultaneamente


def _check_rate_limit(ip: str) -> None:
    """Solleva 429 se l'IP supera il limite configurato nella finestra temporale."""
    global _rate_buckets_last_cleanup
    now = time.time()
    with _rate_lock:
        # Cleanup periodico: rimuove bucket vuoti + cap dimensione totale
        if now - _rate_buckets_last_cleanup > _RATE_BUCKETS_CLEANUP_INTERVAL:
            _cleaned = {
                k: [t for t in v if now - t < _RATE_WINDOW]
                for k, v in _rate_buckets.items()
            }
            _cleaned = {k: v for k, v in _cleaned.items() if v}
            if len(_cleaned) > _RATE_BUCKETS_MAX_SIZE:
                # Tieni i bucket più recenti
                _sorted = sorted(
                    _cleaned.items(),
                    key=lambda x: max(x[1]) if x[1] else 0.0,
                    reverse=True,
                )
                _cleaned = dict(_sorted[:_RATE_BUCKETS_MAX_SIZE])
            _rate_buckets.clear()
            _rate_buckets.update(_cleaned)
            _rate_buckets_last_cleanup = now

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

async def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    """Verifica API key condivisa tra Streamlit e worker.
    Se WORKER_SECRET_KEY non è configurata (dev mode), il check è saltato.
    """
    if not WORKER_SECRET_KEY:
        return  # dev mode: skip
    if x_worker_key != WORKER_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    title="ONEFLUX — Worker API",
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
            "https://oneflux.it",
            "https://www.oneflux.it",
            "https://frontend-production-aa79.up.railway.app",
        ]

    if "*" in origins:
        raise RuntimeError("WORKER_ALLOWED_ORIGINS non puo' contenere '*'.")

    return list(dict.fromkeys(origins))

_MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB


class _ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rifiuta richieste con Content-Length > 50MB o mancante per POST/PUT/PATCH."""
    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        _method = request.method.upper()
        _needs_body = _method in ("POST", "PUT", "PATCH")
        if content_length:
            try:
                if int(content_length) > _MAX_BODY_BYTES:
                    return StarletteResponse("Payload too large", status_code=413)
            except ValueError:
                if _needs_body:
                    return StarletteResponse("Invalid Content-Length", status_code=411)
        elif _needs_body and request.headers.get("transfer-encoding", "").lower() != "chunked":
            # POST/PUT/PATCH senza Content-Length né chunked transfer
            return StarletteResponse("Length Required", status_code=411)
        return await call_next(request)


app.add_middleware(_ContentSizeLimitMiddleware)
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
    descrizioni: List[str] = Field(..., min_length=1, max_length=200, description="Lista descrizioni prodotti da classificare (max 200)")
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
    confidenze: Optional[List[str]] = None
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
    dependencies=[Depends(_verify_worker_key)],
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
        categorie, confidenze = classifica_con_ai(
            lista_descrizioni=body.descrizioni,
            lista_fornitori=body.fornitori,
            lista_iva=body.iva,
            lista_hint=body.hint,
            openai_client=openai_client,
            ristorante_id=body.ristorante_id,
            return_confidenze=True,
        )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"✅ /api/classify: {len(body.descrizioni)} descrizioni → {elapsed_ms}ms"
            + (f" user_id={body.user_id}" if body.user_id else "")
        )
        return ClassifyResponse(
            categorie=categorie,
            confidenze=confidenze,
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
    dependencies=[Depends(_verify_worker_key)],
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
    except Exception as e:
        # Fallback su ristoranti se la tabella lookup non e' disponibile.
        logger.debug("_resolve_tenant_by_piva: piva_ristoranti lookup fallita per piva '%s', uso fallback ristoranti: %s", piva, e)

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
# AUTH (usato da Next.js — server-to-server con WORKER_SECRET_KEY)
# ═══════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255, description="Email utente")
    password: str = Field(..., max_length=255, description="Password in chiaro")


class UserPublic(BaseModel):
    id: str
    email: str
    nome_ristorante: Optional[str] = None
    pagine_abilitate: Optional[List[str]] = None
    is_admin: bool = False


class LoginResponse(BaseModel):
    token: str = Field(..., description="Session token da settare in cookie HTTP-only")
    user: UserPublic


def _is_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    admin_emails_raw = os.getenv("ADMIN_EMAILS", "md@oneflux.it")
    admin_emails = {e.strip().lower() for e in admin_emails_raw.split(",") if e.strip()}
    return email.strip().lower() in admin_emails


def _normalize_pagine(raw) -> Optional[List[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(p) for p in raw]
    if isinstance(raw, dict):
        return [k for k, v in raw.items() if v]
    return None


@app.post(
    "/api/auth/login",
    response_model=LoginResponse,
    summary="Login utente — restituisce session token",
    tags=["Auth"],
    responses={
        401: {"description": "Credenziali errate"},
        429: {"description": "Rate limit superato (lockout)"},
        503: {"description": "Servizio auth non disponibile"},
    },
    dependencies=[Depends(_verify_worker_key)],
)
async def auth_login(body: LoginRequest, request: Request) -> LoginResponse:
    _check_rate_limit(request.client.host if request.client else "unknown")

    from services.auth_service import verifica_credenziali, AuthServiceUnavailableError
    from datetime import datetime, timezone
    import secrets as _secrets

    try:
        user, error = verifica_credenziali(body.email, body.password)
    except AuthServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if error or not user:
        raise HTTPException(status_code=401, detail=error or "Credenziali non valide")

    # Genera sempre session_token legacy (43 char base64url) e salvalo in DB.
    # Questo garantisce che verifica_sessione_da_cookie() funzioni via path legacy,
    # indipendentemente dal formato del refresh token Supabase Auth.
    token = _secrets.token_urlsafe(32)
    try:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
        supabase_client.table("users").update({
            "session_token": token,
            "session_token_created_at": datetime.now(timezone.utc).isoformat(),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", user["id"]).execute()
    except Exception:
        logger.exception("Errore creazione session_token")
        raise HTTPException(status_code=500, detail="Errore creazione sessione")

    return LoginResponse(
        token=token,
        user=UserPublic(
            id=str(user["id"]),
            email=user["email"],
            nome_ristorante=user.get("nome_ristorante"),
            pagine_abilitate=_normalize_pagine(user.get("pagine_abilitate")),
            is_admin=_is_admin_email(user.get("email")),
        ),
    )


@app.get(
    "/api/auth/me",
    response_model=UserPublic,
    summary="Verifica sessione corrente",
    tags=["Auth"],
    responses={401: {"description": "Sessione non valida"}},
    dependencies=[Depends(_verify_worker_key)],
)
async def auth_me(authorization: Optional[str] = Header(None)) -> UserPublic:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token mancante")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vuoto")

    from services.auth_service import verifica_sessione_da_cookie
    user = verifica_sessione_da_cookie(token)

    if not user:
        raise HTTPException(status_code=401, detail="Sessione non valida o scaduta")

    return UserPublic(
        id=str(user["id"]),
        email=user["email"],
        nome_ristorante=user.get("nome_ristorante"),
        pagine_abilitate=_normalize_pagine(user.get("pagine_abilitate")),
        is_admin=_is_admin_email(user.get("email")),
    )


@app.post(
    "/api/auth/logout",
    summary="Logout — invalida session_token legacy",
    tags=["Auth"],
    dependencies=[Depends(_verify_worker_key)],
)
async def auth_logout(authorization: Optional[str] = Header(None)) -> Dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"status": "ok"}

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return {"status": "ok"}

    try:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
        supabase_client.table("users").update({
            "session_token": None,
            "session_token_created_at": None,
        }).eq("session_token", token).execute()
    except Exception as exc:
        logger.warning(f"Logout: errore invalidazione session_token: {exc}")

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

class DashboardKpi(BaseModel):
    fatture_uniche: int
    righe_totali: int
    spesa_totale: float
    spesa_mese_corrente: float
    spesa_mese_precedente: float
    prima_fattura: Optional[str] = None
    ultima_fattura: Optional[str] = None


class SpesaMensilePoint(BaseModel):
    mese: str
    spesa: float


class TopItem(BaseModel):
    nome: str
    spesa: float
    righe: int


class DashboardStats(BaseModel):
    kpi: DashboardKpi
    spesa_mensile: List[SpesaMensilePoint]
    top_fornitori: List[TopItem]
    top_categorie: List[TopItem]


def _resolve_user_from_token(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token mancante")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vuoto")
    from services.auth_service import verifica_sessione_da_cookie
    user = verifica_sessione_da_cookie(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sessione non valida o scaduta")
    return user


@app.get(
    "/api/dashboard/stats",
    response_model=DashboardStats,
    summary="Statistiche dashboard utente — KPI + grafici",
    tags=["Dashboard"],
    dependencies=[Depends(_verify_worker_key)],
)
async def dashboard_stats(authorization: Optional[str] = Header(None)) -> DashboardStats:
    from datetime import date, timedelta
    from collections import defaultdict

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    from services import get_supabase_client
    supabase_client = get_supabase_client()

    rows: List[Dict[str, Any]] = []
    page_size = 1000
    start = 0
    while True:
        resp = (
            supabase_client.table("fatture")
            .select("file_origine,data_documento,fornitore,categoria,totale_riga")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    today = date.today()
    mese_corrente_key = today.strftime("%Y-%m")
    primo_giorno_mese = today.replace(day=1)
    ultimo_giorno_prec = primo_giorno_mese - timedelta(days=1)
    mese_precedente_key = ultimo_giorno_prec.strftime("%Y-%m")

    spesa_totale = 0.0
    spesa_mese_corr = 0.0
    spesa_mese_prec = 0.0
    file_origini = set()
    spesa_per_mese: Dict[str, float] = defaultdict(float)
    spesa_per_fornitore: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"spesa": 0.0, "righe": 0})
    spesa_per_categoria: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"spesa": 0.0, "righe": 0})
    prima_data: Optional[str] = None
    ultima_data: Optional[str] = None

    for r in rows:
        totale = float(r.get("totale_riga") or 0)
        data_doc = r.get("data_documento")
        fornitore = (r.get("fornitore") or "—").strip() or "—"
        categoria = (r.get("categoria") or "—").strip() or "—"
        file_o = r.get("file_origine")

        spesa_totale += totale
        if file_o:
            file_origini.add(file_o)

        if data_doc:
            mese_key = str(data_doc)[:7]
            spesa_per_mese[mese_key] += totale
            if mese_key == mese_corrente_key:
                spesa_mese_corr += totale
            elif mese_key == mese_precedente_key:
                spesa_mese_prec += totale
            if prima_data is None or str(data_doc) < prima_data:
                prima_data = str(data_doc)
            if ultima_data is None or str(data_doc) > ultima_data:
                ultima_data = str(data_doc)

        spesa_per_fornitore[fornitore]["spesa"] += totale
        spesa_per_fornitore[fornitore]["righe"] += 1
        spesa_per_categoria[categoria]["spesa"] += totale
        spesa_per_categoria[categoria]["righe"] += 1

    spesa_mensile_sorted = sorted(spesa_per_mese.items())[-12:]
    spesa_mensile = [SpesaMensilePoint(mese=m, spesa=round(s, 2)) for m, s in spesa_mensile_sorted]

    top_forn = sorted(spesa_per_fornitore.items(), key=lambda x: x[1]["spesa"], reverse=True)[:5]
    top_fornitori = [TopItem(nome=n, spesa=round(d["spesa"], 2), righe=d["righe"]) for n, d in top_forn]

    top_cat = sorted(spesa_per_categoria.items(), key=lambda x: x[1]["spesa"], reverse=True)[:5]
    top_categorie = [TopItem(nome=n, spesa=round(d["spesa"], 2), righe=d["righe"]) for n, d in top_cat]

    kpi = DashboardKpi(
        fatture_uniche=len(file_origini),
        righe_totali=len(rows),
        spesa_totale=round(spesa_totale, 2),
        spesa_mese_corrente=round(spesa_mese_corr, 2),
        spesa_mese_precedente=round(spesa_mese_prec, 2),
        prima_fattura=prima_data,
        ultima_fattura=ultima_data,
    )

    return DashboardStats(
        kpi=kpi,
        spesa_mensile=spesa_mensile,
        top_fornitori=top_fornitori,
        top_categorie=top_categorie,
    )


# ═══════════════════════════════════════════════════════════════════════════
# UPLOAD
# ═══════════════════════════════════════════════════════════════════════════

class UploadInvoiceResponse(BaseModel):
    success: bool
    filename: str
    righe_salvate: int
    righe_preesistenti: int = 0
    needs_review_count: int = 0
    fornitore: Optional[str] = None
    data_documento: Optional[str] = None
    error: Optional[str] = None
    elapsed_ms: int = 0


def _get_ristorante_id_for_user(user_id: str, supabase_client) -> Optional[str]:
    try:
        resp = supabase_client.table("users") \
            .select("ultimo_ristorante_id") \
            .eq("id", user_id) \
            .single() \
            .execute()
        if resp.data:
            return resp.data.get("ultimo_ristorante_id")
    except Exception:
        pass
    try:
        resp2 = supabase_client.table("ristoranti") \
            .select("id") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()
        if resp2.data:
            return resp2.data[0]["id"]
    except Exception:
        pass
    return None


@app.post(
    "/api/upload/invoice",
    response_model=UploadInvoiceResponse,
    summary="Upload fattura XML/P7M — parsing + salvataggio su DB",
    tags=["Upload"],
    dependencies=[Depends(_verify_worker_key)],
)
async def upload_invoice(
    request: Request,
    authorization: Optional[str] = Header(None),
    file: UploadFile = File(...),
) -> UploadInvoiceResponse:
    import time as _time
    t0 = _time.monotonic()

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    filename = file.filename or "fattura"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("xml", "p7m"):
        raise HTTPException(
            status_code=422,
            detail=f"Formato non supportato: '{ext}'. Carica un file XML o P7M.",
        )

    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File troppo grande (max 50MB).")

    from services import get_supabase_client
    supabase_client = get_supabase_client()

    ristorante_id = _get_ristorante_id_for_user(user_id, supabase_client)

    # Estrai XML da P7M se necessario
    if ext == "p7m":
        from services.invoice_service import estrai_xml_da_p7m
        xml_bytes = estrai_xml_da_p7m(io.BytesIO(contents))
        if xml_bytes is None:
            raise HTTPException(status_code=422, detail="Impossibile estrarre XML dal file P7M.")
        contents = xml_bytes.read() if hasattr(xml_bytes, "read") else xml_bytes
        filename = filename[:-4]

    # Parse fattura
    from services.invoice_service import estrai_dati_da_xml, salva_fattura_processata
    from services.ai_service import carica_memoria_completa

    try:
        carica_memoria_completa(user_id)
    except Exception:
        pass

    file_like = io.BytesIO(contents)
    file_like.name = filename  # type: ignore[attr-defined]

    import streamlit as _st
    _prev = _st.session_state.get("user_data")
    try:
        _st.session_state["user_data"] = {"id": user_id}
        righe = estrai_dati_da_xml(file_like)
    finally:
        if _prev is None:
            _st.session_state.pop("user_data", None)
        else:
            _st.session_state["user_data"] = _prev

    if not righe:
        return UploadInvoiceResponse(
            success=False,
            filename=filename,
            righe_salvate=0,
            error="Nessuna riga estratta dal file.",
            elapsed_ms=int((_time.monotonic() - t0) * 1000),
        )

    # Salva su DB (idempotente — rimuove eventuali duplicati)
    result = salva_fattura_processata(
        nome_file=filename,
        dati_prodotti=righe,
        supabase_client=supabase_client,
        silent=True,
        ristoranteid=ristorante_id,
        user_id=user_id,
        ingestion_source="nextjs_upload",
    )

    elapsed_ms = int((_time.monotonic() - t0) * 1000)

    if not result.get("success"):
        return UploadInvoiceResponse(
            success=False,
            filename=filename,
            righe_salvate=0,
            error=result.get("error", "Errore salvataggio"),
            elapsed_ms=elapsed_ms,
        )

    needs_review_count = sum(1 for r in righe if r.get("needs_review"))
    fornitore = righe[0].get("Fornitore") if righe else None
    data_doc = righe[0].get("Data_Documento") if righe else None

    return UploadInvoiceResponse(
        success=True,
        filename=filename,
        righe_salvate=result.get("righe", len(righe)),
        righe_preesistenti=result.get("righe_preesistenti", 0),
        needs_review_count=needs_review_count,
        fornitore=str(fornitore) if fornitore else None,
        data_documento=str(data_doc) if data_doc else None,
        elapsed_ms=elapsed_ms,
    )


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICHE
# ═══════════════════════════════════════════════════════════════════════════

class NotificaItem(BaseModel):
    id: str
    topic_key: Optional[str] = None
    source_type: Optional[str] = None
    severity: str = "info"
    title: str
    body: Optional[str] = None
    action_page: Optional[str] = None
    dismissed_at: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None


class NotificheResponse(BaseModel):
    notifiche: List[NotificaItem]
    total: int
    unread: int


@app.get(
    "/api/notifiche",
    response_model=NotificheResponse,
    summary="Lista notifiche utente (attive + non scadute)",
    tags=["Notifiche"],
    dependencies=[Depends(_verify_worker_key)],
)
async def get_notifiche(
    authorization: Optional[str] = Header(None),
    include_dismissed: bool = False,
) -> NotificheResponse:
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    from services import get_supabase_client
    supabase_client = get_supabase_client()

    query = (
        supabase_client.table("notification_inbox")
        .select("id,topic_key,source_type,severity,title,body,action_page,dismissed_at,expires_at,created_at")
        .eq("user_id", user_id)
        .or_("expires_at.is.null,expires_at.gt." + __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
        .order("created_at", desc=True)
        .limit(100)
    )

    resp = query.execute()
    rows = resp.data or []

    if not include_dismissed:
        rows = [r for r in rows if not r.get("dismissed_at")]

    notifiche = [
        NotificaItem(
            id=str(r["id"]),
            topic_key=r.get("topic_key"),
            source_type=r.get("source_type"),
            severity=r.get("severity") or "info",
            title=r.get("title") or "",
            body=r.get("body"),
            action_page=r.get("action_page"),
            dismissed_at=str(r["dismissed_at"]) if r.get("dismissed_at") else None,
            expires_at=str(r["expires_at"]) if r.get("expires_at") else None,
            created_at=str(r["created_at"]) if r.get("created_at") else None,
        )
        for r in rows
    ]

    unread = sum(1 for n in notifiche if not n.dismissed_at)

    return NotificheResponse(notifiche=notifiche, total=len(notifiche), unread=unread)


@app.post(
    "/api/notifiche/{notifica_id}/dismiss",
    summary="Segna notifica come letta/archiviata",
    tags=["Notifiche"],
    dependencies=[Depends(_verify_worker_key)],
)
async def dismiss_notifica(
    notifica_id: str,
    authorization: Optional[str] = Header(None),
) -> Dict[str, str]:
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    from services import get_supabase_client
    from datetime import datetime, timezone
    supabase_client = get_supabase_client()

    supabase_client.table("notification_inbox").update(
        {"dismissed_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", notifica_id).eq("user_id", user_id).execute()

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# FATTURE — lista righe con filtri, pivot categorie/fornitori, aggiorna categoria
# ═══════════════════════════════════════════════════════════════════════════

class RigaFattura(BaseModel):
    id: int
    file_origine: str
    numero_riga: int
    data_documento: Optional[str]
    fornitore: str
    descrizione: str
    quantita: Optional[float]
    unita_misura: Optional[str]
    prezzo_unitario: Optional[float]
    totale_riga: Optional[float]
    categoria: Optional[str]
    needs_review: Optional[bool]
    tipo_documento: Optional[str]
    data_competenza: Optional[str]
    piva_cedente: Optional[str]


class FattureListResponse(BaseModel):
    righe: List[RigaFattura]
    total: int
    page: int
    page_size: int


class PivotRow(BaseModel):
    dimensione: str
    mesi: Dict[str, float]
    totale: float


class PivotResponse(BaseModel):
    rows: List[PivotRow]
    mesi_disponibili: List[str]


class AggiornaCategoriaRequest(BaseModel):
    categoria: str


@app.get(
    "/api/fatture",
    response_model=FattureListResponse,
    summary="Lista righe fattura con filtri opzionali",
)
async def get_fatture(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    fornitore: Optional[str] = None,
    categoria: Optional[str] = None,
    needs_review: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    authorization: Optional[str] = Header(None),
) -> FattureListResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = user.get("ristorante_id")
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato all'utente")

    supabase_client = _get_supabase_client()

    q = (
        supabase_client.table("fatture")
        .select(
            "id,file_origine,numero_riga,data_documento,fornitore,descrizione,"
            "quantita,unita_misura,prezzo_unitario,totale_riga,categoria,"
            "needs_review,tipo_documento,data_competenza,piva_cedente"
        )
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .order("data_documento", desc=True)
        .order("id", desc=True)
    )

    if data_da:
        q = q.gte("data_documento", data_da)
    if data_a:
        q = q.lte("data_documento", data_a)
    if fornitore:
        q = q.ilike("fornitore", f"%{fornitore}%")
    if categoria:
        q = q.eq("categoria", categoria)
    if needs_review is not None:
        q = q.eq("needs_review", needs_review)

    offset = (page - 1) * page_size
    res = q.range(offset, offset + page_size - 1).execute()
    rows = res.data or []

    # count totale (senza paginazione)
    count_q = (
        supabase_client.table("fatture")
        .select("id", count="exact")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
    )
    if data_da:
        count_q = count_q.gte("data_documento", data_da)
    if data_a:
        count_q = count_q.lte("data_documento", data_a)
    if fornitore:
        count_q = count_q.ilike("fornitore", f"%{fornitore}%")
    if categoria:
        count_q = count_q.eq("categoria", categoria)
    if needs_review is not None:
        count_q = count_q.eq("needs_review", needs_review)
    count_res = count_q.execute()
    total = count_res.count or len(rows)

    righe = [RigaFattura(**{k: v for k, v in r.items() if k in RigaFattura.model_fields}) for r in rows]
    return FattureListResponse(righe=righe, total=total, page=page, page_size=page_size)


@app.get(
    "/api/fatture/pivot",
    response_model=PivotResponse,
    summary="Pivot spesa mensile per categoria o fornitore",
)
async def get_fatture_pivot(
    dimensione: str = "categoria",  # "categoria" | "fornitore"
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> PivotResponse:
    if dimensione not in ("categoria", "fornitore"):
        raise HTTPException(status_code=400, detail="dimensione deve essere 'categoria' o 'fornitore'")

    user = _resolve_user_from_token(authorization)
    ristorante_id = user.get("ristorante_id")
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato all'utente")

    supabase_client = _get_supabase_client()

    col = "categoria" if dimensione == "categoria" else "fornitore"
    q = (
        supabase_client.table("fatture")
        .select(f"{col},data_documento,totale_riga")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .gt("totale_riga", 0)
        .neq("categoria", "📝 NOTE E DICITURE")
        .neq("categoria", "NOTE E DICITURE")
    )
    if data_da:
        q = q.gte("data_documento", data_da)
    if data_a:
        q = q.lte("data_documento", data_a)

    res = q.execute()
    rows = res.data or []

    from collections import defaultdict
    import calendar

    # Aggrega: {dim_value: {YYYY-MM: totale}}
    agg: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    mesi_set: set = set()

    for r in rows:
        dim_val = r.get(col) or "N/D"
        data_raw = r.get("data_documento")
        totale = float(r.get("totale_riga") or 0)
        if not data_raw:
            continue
        mese_key = str(data_raw)[:7]  # YYYY-MM
        agg[dim_val][mese_key] += totale
        mesi_set.add(mese_key)

    mesi_disponibili = sorted(mesi_set)

    pivot_rows: List[PivotRow] = []
    for dim_val, mesi_dict in agg.items():
        totale = sum(mesi_dict.values())
        pivot_rows.append(PivotRow(dimensione=dim_val, mesi=dict(mesi_dict), totale=totale))

    pivot_rows.sort(key=lambda r: r.totale, reverse=True)
    return PivotResponse(rows=pivot_rows, mesi_disponibili=mesi_disponibili)


@app.get(
    "/api/fatture/categorie",
    summary="Lista categorie distinte presenti nelle fatture",
)
async def get_categorie_disponibili(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = user.get("ristorante_id")
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato all'utente")

    supabase_client = _get_supabase_client()
    res = (
        supabase_client.table("fatture")
        .select("categoria")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    rows = res.data or []
    categorie = sorted({r["categoria"] for r in rows if r.get("categoria")})
    return {"categorie": categorie}


@app.patch(
    "/api/fatture/{riga_id}/categoria",
    summary="Aggiorna categoria di una riga fattura",
)
async def aggiorna_categoria_riga(
    riga_id: int,
    body: AggiornaCategoriaRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = user.get("ristorante_id")
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato all'utente")

    categoria = body.categoria.strip()
    if not categoria or categoria in ("Da Clasificare", "Da Classificare"):
        raise HTTPException(status_code=400, detail="Categoria non valida")

    supabase_client = _get_supabase_client()
    # Verifica che la riga appartenga al ristorante
    check = (
        supabase_client.table("fatture")
        .select("id")
        .eq("id", riga_id)
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Riga non trovata")

    supabase_client.table("fatture").update(
        {"categoria": categoria, "needs_review": False}
    ).eq("id", riga_id).execute()

    return {"ok": True, "id": riga_id, "categoria": categoria}


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
