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
            "https://nuovo.oneflux.it",
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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


@app.post("/api/upload/start-session", tags=["Upload"])
async def upload_start_session(authorization: Optional[str] = Header(None)):
    """Marca l'inizio di una nuova sessione di caricamento: aggiorna nuovi_da = now().
    I prodotti caricati in questa sessione avranno created_at >= nuovi_da → badge 'Nuovo'.
    I prodotti delle sessioni precedenti avranno created_at < nuovi_da → badge rimosso."""
    from datetime import datetime, timezone
    user = _resolve_user_from_token(authorization)
    supabase_client = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase_client.table("ristoranti").update({"nuovi_da": now_iso}).eq("id", ristorante_id).execute()
    return {"ok": True, "nuovi_da": now_iso}


@app.post(
    "/api/upload/invoice",
    response_model=UploadInvoiceResponse,
    summary="Upload fattura XML/P7M — parsing + salvataggio su DB (auth solo via Bearer per upload diretto dal browser)",
    tags=["Upload"],
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

    # Calcola nome canonico (dopo eventuale .p7m → .xml) per check duplicati
    filename_canonico = filename[:-4] if ext == "p7m" else filename

    # Genera variante "normalizzata" rimuovendo suffissi tipo " (1)", " (2)" ecc.
    import re as _re
    def _strip_suffix_n(name: str) -> str:
        return _re.sub(r"\s*\(\d+\)(\.[^.]+)$", r"\1", name, count=1)

    nomi_da_controllare = list({filename_canonico, _strip_suffix_n(filename_canonico)})

    # Check duplicato: se gia esiste una fattura con stesso nome (o nome senza suffisso (N)), scarta
    if ristorante_id:
        try:
            existing = (
                supabase_client.table("fatture")
                .select("file_origine")
                .eq("ristorante_id", ristorante_id)
                .is_("deleted_at", "null")
                .in_("file_origine", nomi_da_controllare)
                .limit(1)
                .execute()
            )
            if existing.data:
                trovato = existing.data[0].get("file_origine", "")
                return UploadInvoiceResponse(
                    success=False,
                    filename=filename_canonico,
                    righe_salvate=0,
                    error=f"ALREADY_LOADED:{trovato}",
                    elapsed_ms=int((_time.monotonic() - t0) * 1000),
                )
        except Exception as dup_err:
            logger.warning(f"Check duplicato fallito (non bloccante): {dup_err}")

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
# FATTURE — analisi, KPI, articoli aggregati, pivot, trend, batch update
# ═══════════════════════════════════════════════════════════════════════════

# Categorie classificate come "Spese Generali" (NON Food & Beverage)
CATEGORIE_SPESE_GENERALI_WORKER = {
    "SERVIZI E CONSULENZE",
    "UTENZE E LOCALI",
    "MANUTENZIONE E ATTREZZATURE",
    "MATERIALE DI CONSUMO",
}
CATEGORIE_NOTE_WORKER = {"📝 NOTE E DICITURE", "NOTE E DICITURE"}


def _resolve_ristorante_id(user: Dict[str, Any], supabase_client) -> Optional[str]:
    """Risolve ristorante_id dal dict user (chiamato da _resolve_user_from_token).

    Priorita:
      1) user.ristorante_id (impostato esplicitamente)
      2) user.ultimo_ristorante_id (selezione utente)
      3) primo ristorante attivo dell'utente
    """
    rid = user.get("ristorante_id") or user.get("ultimo_ristorante_id")
    if rid:
        return str(rid)
    uid = user.get("id")
    if not uid:
        return None
    try:
        resp = (
            supabase_client.table("ristoranti")
            .select("id")
            .eq("user_id", uid)
            .eq("attivo", True)
            .order("created_at")
            .limit(1)
            .execute()
        )
        if resp.data:
            return str(resp.data[0]["id"])
    except Exception:
        pass
    return None


def _build_fatture_base_query(supabase_client, ristorante_id: str):
    """Query base righe attive per il ristorante (no deleted, no NOTE)."""
    return (
        supabase_client.table("fatture")
        .select(
            "id,file_origine,numero_riga,data_documento,fornitore,descrizione,"
            "quantita,unita_misura,prezzo_unitario,totale_riga,categoria,"
            "needs_review,tipo_documento,data_competenza,piva_cedente,created_at"
        )
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
    )


def _apply_tipo_prodotti_filter(rows: List[Dict[str, Any]], tipo: Optional[str]) -> List[Dict[str, Any]]:
    """Filtra le righe per tipo prodotti: food_beverage / spese_generali / tutti."""
    if not tipo or tipo == "tutti":
        return rows
    if tipo == "food_beverage":
        return [r for r in rows if (r.get("categoria") or "") not in CATEGORIE_SPESE_GENERALI_WORKER]
    if tipo == "spese_generali":
        return [r for r in rows if (r.get("categoria") or "") in CATEGORIE_SPESE_GENERALI_WORKER]
    return rows


def _exclude_note_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if (r.get("categoria") or "") not in CATEGORIE_NOTE_WORKER]


def _fetch_fatture_rows(
    supabase_client,
    ristorante_id: str,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Recupera righe fattura filtrate con paginazione interna per superare il limite Supabase di 1000."""
    all_rows: List[Dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while True:
        q = _build_fatture_base_query(supabase_client, ristorante_id)
        if data_da:
            q = q.gte("data_documento", data_da)
        if data_a:
            q = q.lte("data_documento", data_a)
        if search:
            term = search.strip()
            if term:
                # cerca trasversalmente in descrizione, fornitore, categoria
                q = q.or_(
                    f"descrizione.ilike.%{term}%,fornitore.ilike.%{term}%,categoria.ilike.%{term}%"
                )
        q = q.order("data_documento", desc=True).order("id", desc=True)
        res = q.range(offset, offset + page_size - 1).execute()
        batch = res.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        if offset >= 50000:  # safety cap
            break

    all_rows = _exclude_note_rows(all_rows)
    all_rows = _apply_tipo_prodotti_filter(all_rows, tipo_prodotti)
    return all_rows


# ─── Modelli pydantic ──────────────────────────────────────────────────────

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
    created_at: Optional[str] = None


class ArticoloAggregato(BaseModel):
    descrizione: str
    categoria: Optional[str]
    fornitore_principale: str
    altri_fornitori: List[str]
    ultimo_acquisto: Optional[str]
    quantita_totale: float
    unita_misura: Optional[str]
    prezzo_unit_medio: Optional[float]
    prezzo_unit_trend_pct: Optional[float]  # % rispetto al periodo precedente
    totale_speso: float
    num_acquisti: int
    righe_ids: List[int]  # per batch operations
    needs_review: bool
    is_nuovo: bool  # arrivato dopo l'ultimo accesso utente


class ArticoliResponse(BaseModel):
    articoli: List[ArticoloAggregato]
    total: int


class KpiResponse(BaseModel):
    totale: float
    num_righe: int
    num_prodotti: int
    media_mensile: float
    delta_totale_pct: Optional[float]
    delta_righe_pct: Optional[float]
    delta_prodotti_pct: Optional[float]
    delta_media_pct: Optional[float]
    confronto_label: str = "periodo prec."


class MesiDisponibiliResponse(BaseModel):
    mesi: List[Dict[str, Any]]  # [{year, month, label, count}, ...]


class PivotRow(BaseModel):
    dimensione: str
    periodi: Dict[str, float]  # chiave: YYYY-MM o YYYY-Qn o YYYY
    totale: float
    media: float
    incidenza_pct: float  # % sul grand total
    sparkline: List[float]  # ultimi N periodi per mini-grafico


class PivotResponse(BaseModel):
    rows: List[PivotRow]
    periodi: List[str]
    periodi_labels: List[str]
    granularita: str  # "mese" | "trimestre" | "anno"
    totali_periodo: Dict[str, float]
    grand_total: float


class TrendPunto(BaseModel):
    periodo: str
    label: str
    valore: float


class TrendSerie(BaseModel):
    valore: str
    punti: List[TrendPunto]
    media: float
    totale: float


class TrendResponse(BaseModel):
    serie: List[TrendSerie]
    periodi: List[str]
    periodi_labels: List[str]


class CategoriaBatchRequest(BaseModel):
    descrizione: str
    nuova_categoria: str
    riga_ids: Optional[List[int]] = None  # se fornito, aggiorna solo questi id


_MESI_LABEL_IT = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
                  "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def _period_key(date_str: str, granularita: str) -> str:
    """Restituisce chiave periodo per granularita selezionata."""
    if not date_str or len(date_str) < 10:
        return ""
    y = date_str[:4]
    m = int(date_str[5:7])
    if granularita == "anno":
        return y
    if granularita == "trimestre":
        q = (m - 1) // 3 + 1
        return f"{y}-Q{q}"
    return f"{y}-{m:02d}"  # mese


def _period_label(key: str, granularita: str) -> str:
    if not key:
        return ""
    if granularita == "anno":
        return key
    if granularita == "trimestre":
        return key.replace("-Q", " T")  # "2026 T1"
    # mese
    y, m = key.split("-")
    return f"{_MESI_LABEL_IT[int(m)]} {y[2:]}"


def _scegli_granularita(periodi_set: set) -> str:
    """Sceglie granularita automatica basata sul numero di mesi nel periodo."""
    n = len(periodi_set)
    if n <= 12:
        return "mese"
    if n <= 36:
        return "trimestre"
    return "anno"


def _compute_periodo_precedente(data_da: Optional[str], data_a: Optional[str]) -> tuple:
    """Calcola il periodo precedente di stessa durata."""
    from datetime import date, timedelta
    if not data_da or not data_a:
        return None, None
    try:
        d_da = date.fromisoformat(data_da)
        d_a = date.fromisoformat(data_a)
        durata = (d_a - d_da).days + 1
        prev_a = d_da - timedelta(days=1)
        prev_da = prev_a - timedelta(days=durata - 1)
        return prev_da.isoformat(), prev_a.isoformat()
    except Exception:
        return None, None


# ─── Endpoint: lista mesi disponibili ──────────────────────────────────────

@app.get("/api/fatture/mesi-disponibili", response_model=MesiDisponibiliResponse)
async def get_mesi_disponibili(
    authorization: Optional[str] = Header(None),
) -> MesiDisponibiliResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    res = (
        supabase_client.table("fatture")
        .select("data_documento")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .not_.is_("data_documento", "null")
        .execute()
    )
    rows = res.data or []
    counts: Dict[str, int] = {}
    for r in rows:
        d = r.get("data_documento")
        if d and len(d) >= 7:
            counts[d[:7]] = counts.get(d[:7], 0) + 1

    mesi = []
    for ym in sorted(counts.keys(), reverse=True):
        y, m = ym.split("-")
        mesi.append({
            "year": int(y),
            "month": int(m),
            "label": f"{_MESI_LABEL_IT[int(m)]} {y}",
            "count": counts[ym],
        })
    return MesiDisponibiliResponse(mesi=mesi)


# ─── Endpoint: KPI con delta vs periodo precedente ─────────────────────────

@app.get("/api/fatture/kpi", response_model=KpiResponse)
async def get_fatture_kpi(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> KpiResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()

    def _calc(rows):
        rows_valid = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) > 0]
        totale = sum(float(r["totale_riga"]) for r in rows_valid)
        num_righe = len(rows_valid)
        prodotti = {r.get("descrizione", "").strip().lower() for r in rows_valid if r.get("descrizione")}
        mesi = {(r.get("data_documento") or "")[:7] for r in rows_valid if r.get("data_documento")}
        num_mesi = max(len(mesi), 1)
        media = totale / num_mesi
        return totale, num_righe, len(prodotti), media

    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    tot, nr, np, med = _calc(rows)

    from datetime import date as _date, timedelta as _timedelta

    delta_tot = delta_nr = delta_np = delta_med = None
    confronto_label = "periodo prec."
    use_media_anno = False

    # Per periodi brevi (≤ 31 giorni) confronta vs media mensile dell'anno in corso
    if data_da and data_a:
        try:
            d_da = _date.fromisoformat(data_da)
            d_a = _date.fromisoformat(data_a)
            durata = (d_a - d_da).days + 1
            if durata <= 31:
                anno_inizio = _date(d_da.year, 1, 1)
                giorno_prima = d_da - _timedelta(days=1)
                if giorno_prima >= anno_inizio:
                    prev_da = anno_inizio.isoformat()
                    prev_a = giorno_prima.isoformat()
                    use_media_anno = True
                    confronto_label = "media anno in corso"
                else:
                    prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
            else:
                prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
        except Exception:
            prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
    else:
        prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)

    if prev_da and prev_a:
        prev_rows = _fetch_fatture_rows(supabase_client, ristorante_id, prev_da, prev_a, tipo_prodotti)
        ptot, pnr, pnp, pmed = _calc(prev_rows)

        def _delta(curr, prev_val):
            if prev_val == 0:
                return None
            return round((curr - prev_val) / prev_val * 100, 1)

        if use_media_anno:
            # pmed = media mensile del periodo baseline (gen→giorno prima)
            prev_mesi_set = {(r.get("data_documento") or "")[:7] for r in prev_rows if r.get("data_documento")}
            num_prev_mesi = max(len(prev_mesi_set), 1)
            pmed_righe = pnr / num_prev_mesi
            pmed_prod = pnp / num_prev_mesi
            delta_tot = _delta(tot, pmed)
            delta_nr = _delta(nr, pmed_righe)
            delta_np = _delta(np, pmed_prod)
            delta_med = _delta(med, pmed)
        else:
            delta_tot = _delta(tot, ptot)
            delta_nr = _delta(nr, pnr)
            delta_np = _delta(np, pnp)
            delta_med = _delta(med, pmed)

    return KpiResponse(
        totale=round(tot, 2),
        num_righe=nr,
        num_prodotti=np,
        media_mensile=round(med, 2),
        delta_totale_pct=delta_tot,
        delta_righe_pct=delta_nr,
        delta_prodotti_pct=delta_np,
        delta_media_pct=delta_med,
        confronto_label=confronto_label,
    )


# ─── Endpoint: articoli aggregati (vista default tab Articoli) ─────────────

@app.get("/api/fatture/articoli-aggregati", response_model=ArticoliResponse)
async def get_articoli_aggregati(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    categoria: Optional[str] = None,
    fornitore: Optional[str] = None,
    search: Optional[str] = None,
    solo_nuovi: bool = False,
    solo_da_verificare: bool = False,
    authorization: Optional[str] = Header(None),
) -> ArticoliResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()

    # cutoff "Nuovo": usa nuovi_da dal ristorante (impostato all'inizio di ogni sessione upload).
    # Fallback a 24h se nuovi_da non è ancora impostato (primo avvio).
    from datetime import datetime, timedelta, timezone
    ristorante_row = supabase_client.table("ristoranti").select("nuovi_da").eq("id", ristorante_id).single().execute()
    nuovi_da_raw = (ristorante_row.data or {}).get("nuovi_da")
    if nuovi_da_raw:
        cutoff_nuovo = nuovi_da_raw
    else:
        cutoff_nuovo = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    rows = _fetch_fatture_rows(
        supabase_client, ristorante_id, data_da, data_a, tipo_prodotti, search
    )
    if categoria:
        rows = [r for r in rows if r.get("categoria") == categoria]
    if fornitore:
        rows = [r for r in rows if r.get("fornitore") == fornitore]
    if solo_da_verificare:
        rows = [r for r in rows if r.get("needs_review")]

    # Aggrega per descrizione normalizzata
    from collections import defaultdict
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        desc = (r.get("descrizione") or "").strip()
        if not desc:
            continue
        groups[desc].append(r)

    # Periodo precedente per trend prezzo
    prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
    prev_prices: Dict[str, float] = {}
    if prev_da and prev_a:
        prev_rows = _fetch_fatture_rows(
            supabase_client, ristorante_id, prev_da, prev_a, tipo_prodotti
        )
        prev_groups: Dict[str, List[float]] = defaultdict(list)
        for pr in prev_rows:
            desc = (pr.get("descrizione") or "").strip()
            pu = pr.get("prezzo_unitario")
            if desc and pu is not None and float(pu) > 0:
                prev_groups[desc].append(float(pu))
        for desc, prices in prev_groups.items():
            if prices:
                prev_prices[desc] = sum(prices) / len(prices)

    articoli: List[ArticoloAggregato] = []
    for desc, items in groups.items():
        # fornitori
        forn_counts: Dict[str, int] = defaultdict(int)
        for it in items:
            f = (it.get("fornitore") or "").strip()
            if f:
                forn_counts[f] += 1
        forn_sorted = sorted(forn_counts.items(), key=lambda x: -x[1])
        forn_principale = forn_sorted[0][0] if forn_sorted else ""
        altri_forn = [f for f, _ in forn_sorted[1:]]

        # categoria piu frequente
        cat_counts: Dict[str, int] = defaultdict(int)
        for it in items:
            c = it.get("categoria")
            if c:
                cat_counts[c] += 1
        categoria_principale = max(cat_counts.items(), key=lambda x: x[1])[0] if cat_counts else None

        # date e quantita
        date_list = [it.get("data_documento") for it in items if it.get("data_documento")]
        ultimo_acq = max(date_list) if date_list else None
        qta_totale = sum(float(it.get("quantita") or 0) for it in items)
        um = next((it.get("unita_misura") for it in items if it.get("unita_misura")), None)
        prezzi = [float(it["prezzo_unitario"]) for it in items if it.get("prezzo_unitario") and float(it["prezzo_unitario"]) > 0]
        prezzo_medio = sum(prezzi) / len(prezzi) if prezzi else None
        totale_speso = sum(float(it.get("totale_riga") or 0) for it in items)
        num_acq = len(items)

        # trend prezzo vs periodo precedente
        trend_pct = None
        if prezzo_medio is not None and desc in prev_prices and prev_prices[desc] > 0:
            trend_pct = round((prezzo_medio - prev_prices[desc]) / prev_prices[desc] * 100, 1)

        # needs_review se almeno una riga
        nr = any(it.get("needs_review") for it in items)

        # is_nuovo: created_at di almeno una riga nelle ultime 24h
        is_nuovo = False
        for it in items:
            ca = it.get("created_at")
            if ca and ca >= cutoff_nuovo:
                is_nuovo = True
                break

        if solo_nuovi and not is_nuovo:
            continue

        articoli.append(ArticoloAggregato(
            descrizione=desc,
            categoria=categoria_principale,
            fornitore_principale=forn_principale,
            altri_fornitori=altri_forn,
            ultimo_acquisto=ultimo_acq,
            quantita_totale=round(qta_totale, 2),
            unita_misura=um,
            prezzo_unit_medio=round(prezzo_medio, 2) if prezzo_medio else None,
            prezzo_unit_trend_pct=trend_pct,
            totale_speso=round(totale_speso, 2),
            num_acquisti=num_acq,
            righe_ids=[int(it["id"]) for it in items if it.get("id")],
            needs_review=nr,
            is_nuovo=is_nuovo,
        ))

    # Ordina per totale_speso desc (i piu impattanti in alto)
    articoli.sort(key=lambda a: -a.totale_speso)
    return ArticoliResponse(articoli=articoli, total=len(articoli))


# ─── Endpoint: righe singole (per espansione articolo) ─────────────────────

@app.get("/api/fatture/righe-articolo", response_model=List[RigaFattura])
async def get_righe_articolo(
    descrizione: str,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> List[RigaFattura]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    q = _build_fatture_base_query(supabase_client, ristorante_id).eq("descrizione", descrizione)
    if data_da:
        q = q.gte("data_documento", data_da)
    if data_a:
        q = q.lte("data_documento", data_a)
    q = q.order("data_documento", desc=True)
    res = q.execute()
    return [RigaFattura(**{k: v for k, v in r.items() if k in RigaFattura.model_fields}) for r in (res.data or [])]


# ─── Endpoint: pivot estesa (mese/trimestre/anno auto) ─────────────────────

@app.get("/api/fatture/pivot", response_model=PivotResponse)
async def get_fatture_pivot(
    dimensione: str = "categoria",  # "categoria" | "fornitore"
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> PivotResponse:
    if dimensione not in ("categoria", "fornitore"):
        raise HTTPException(status_code=400, detail="dimensione deve essere 'categoria' o 'fornitore'")

    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    rows = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) > 0]

    # Determina granularita dai mesi presenti
    mesi_presenti = {(r.get("data_documento") or "")[:7] for r in rows if r.get("data_documento")}
    mesi_presenti.discard("")
    granularita = _scegli_granularita(mesi_presenti)

    col = "categoria" if dimensione == "categoria" else "fornitore"
    from collections import defaultdict
    agg: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    periodi_set: set = set()
    for r in rows:
        d = r.get("data_documento")
        if not d:
            continue
        key = _period_key(d, granularita)
        if not key:
            continue
        dim_val = (r.get(col) or "N/D")
        agg[dim_val][key] += float(r.get("totale_riga") or 0)
        periodi_set.add(key)

    periodi = sorted(periodi_set)
    periodi_labels = [_period_label(p, granularita) for p in periodi]

    grand_total = sum(sum(d.values()) for d in agg.values())
    totali_periodo: Dict[str, float] = {p: 0.0 for p in periodi}
    for d in agg.values():
        for k, v in d.items():
            totali_periodo[k] = totali_periodo.get(k, 0) + v

    # sparkline: ultimi min(12, len(periodi)) periodi
    spark_n = min(12, len(periodi))
    spark_periodi = periodi[-spark_n:] if spark_n > 0 else []

    pivot_rows: List[PivotRow] = []
    for dim_val, periodi_dict in agg.items():
        tot = sum(periodi_dict.values())
        media = tot / len(periodi) if periodi else 0
        inc = (tot / grand_total * 100) if grand_total > 0 else 0
        spark = [round(periodi_dict.get(p, 0), 2) for p in spark_periodi]
        pivot_rows.append(PivotRow(
            dimensione=dim_val,
            periodi={k: round(v, 2) for k, v in periodi_dict.items()},
            totale=round(tot, 2),
            media=round(media, 2),
            incidenza_pct=round(inc, 1),
            sparkline=spark,
        ))
    pivot_rows.sort(key=lambda x: -x.totale)

    return PivotResponse(
        rows=pivot_rows,
        periodi=periodi,
        periodi_labels=periodi_labels,
        granularita=granularita,
        totali_periodo={k: round(v, 2) for k, v in totali_periodo.items()},
        grand_total=round(grand_total, 2),
    )


# ─── Endpoint: trend temporale (grafico multi-select) ──────────────────────

@app.get("/api/fatture/trend", response_model=TrendResponse)
async def get_fatture_trend(
    dimensione: str = "categoria",
    valori: Optional[str] = None,  # CSV: "CARNE,PESCE,..." o "Marini,Demare"
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> TrendResponse:
    if dimensione not in ("categoria", "fornitore"):
        raise HTTPException(status_code=400, detail="dimensione invalida")

    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    rows = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) > 0]

    mesi_presenti = {(r.get("data_documento") or "")[:7] for r in rows if r.get("data_documento")}
    mesi_presenti.discard("")
    granularita = _scegli_granularita(mesi_presenti)
    periodi = sorted(mesi_presenti) if granularita == "mese" else sorted({_period_key(r.get("data_documento", ""), granularita) for r in rows if r.get("data_documento")})
    periodi_labels = [_period_label(p, granularita) for p in periodi]

    col = "categoria" if dimensione == "categoria" else "fornitore"
    selected = [v.strip() for v in (valori or "").split(",") if v.strip()] if valori else []
    if not selected:
        # top 3 di default
        from collections import defaultdict
        tots = defaultdict(float)
        for r in rows:
            tots[(r.get(col) or "N/D")] += float(r.get("totale_riga") or 0)
        selected = [k for k, _ in sorted(tots.items(), key=lambda x: -x[1])[:3]]

    serie: List[TrendSerie] = []
    for val in selected:
        from collections import defaultdict
        per_periodo = defaultdict(float)
        for r in rows:
            if (r.get(col) or "N/D") != val:
                continue
            d = r.get("data_documento")
            if not d:
                continue
            key = _period_key(d, granularita)
            if key:
                per_periodo[key] += float(r.get("totale_riga") or 0)
        punti = [TrendPunto(periodo=p, label=_period_label(p, granularita), valore=round(per_periodo.get(p, 0), 2)) for p in periodi]
        tot = sum(per_periodo.values())
        media = tot / len(periodi) if periodi else 0
        serie.append(TrendSerie(valore=val, punti=punti, media=round(media, 2), totale=round(tot, 2)))

    return TrendResponse(serie=serie, periodi=periodi, periodi_labels=periodi_labels)


# ─── Endpoint: fornitori distinti del ristorante ───────────────────────────

@app.get("/api/fatture/fornitori")
async def get_fornitori_disponibili(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    supabase_client = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    rows: List[Dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            supabase_client.table("fatture")
            .select("fornitore")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        if offset >= 50000:
            break
    fornitori = sorted({(r.get("fornitore") or "").strip() for r in rows if r.get("fornitore")}, key=lambda s: s.casefold())
    return {"fornitori": fornitori}


# ─── Endpoint: categorie disponibili ───────────────────────────────────────

@app.get("/api/fatture/categorie")
async def get_categorie_disponibili(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    # Categorie usate dal ristorante
    res = (
        supabase_client.table("fatture")
        .select("categoria")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    rows = res.data or []
    categorie_usate = sorted({
        r["categoria"] for r in rows
        if r.get("categoria") and r["categoria"] not in CATEGORIE_NOTE_WORKER
    })

    # Categorie canoniche (lista master) — facciamo query semplice
    try:
        res_master = supabase_client.table("categorie").select("nome").execute()
        canoniche = sorted({c["nome"] for c in (res_master.data or []) if c.get("nome") and "DICITURE" not in c["nome"].upper()})
    except Exception:
        canoniche = []

    # Unione
    tutte = sorted(set(categorie_usate) | set(canoniche))
    return {"categorie": tutte, "usate": categorie_usate}


# ─── Endpoint: batch update categoria (stessa descrizione) + memoria AI ────

@app.post("/api/fatture/categoria-batch")
async def categoria_batch(
    body: CategoriaBatchRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    user_id = user.get("id")
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id or not user_id:
        raise HTTPException(status_code=400, detail="Utente o ristorante mancante")

    nuova_cat = body.nuova_categoria.strip()
    if not nuova_cat or nuova_cat in ("Da Clasificare", "Da Classificare"):
        raise HTTPException(status_code=400, detail="Categoria non valida")

    descrizione = body.descrizione.strip()
    if not descrizione:
        raise HTTPException(status_code=400, detail="Descrizione mancante")

    supabase_client = _get_supabase_client()
    # Aggiorna tutte le righe con stessa descrizione del ristorante
    update_q = (
        supabase_client.table("fatture")
        .update({"categoria": nuova_cat, "needs_review": False})
        .eq("ristorante_id", ristorante_id)
        .eq("descrizione", descrizione)
        .is_("deleted_at", "null")
    )
    res_update = update_q.execute()
    righe_aggiornate = len(res_update.data or [])

    # Salva memoria AI locale (prodotti_utente)
    try:
        existing = (
            supabase_client.table("prodotti_utente")
            .select("id")
            .eq("user_id", user_id)
            .eq("descrizione", descrizione)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase_client.table("prodotti_utente").update({
                "categoria": nuova_cat,
                "classificato_da": "User",
                "updated_at": "now()",
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase_client.table("prodotti_utente").insert({
                "user_id": user_id,
                "descrizione": descrizione,
                "categoria": nuova_cat,
                "classificato_da": "User",
                "volte_visto": 1,
            }).execute()
    except Exception as e:
        logger.warning(f"Memoria AI non salvata per '{descrizione}': {e}")

    return {"ok": True, "righe_aggiornate": righe_aggiornate, "descrizione": descrizione, "nuova_categoria": nuova_cat}


# ─── Endpoint: lista righe paginata (compat con vecchio /api/fatture) ──────

class FattureListResponse(BaseModel):
    righe: List[RigaFattura]
    total: int
    page: int
    page_size: int


@app.get("/api/fatture", response_model=FattureListResponse)
async def get_fatture(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    fornitore: Optional[str] = None,
    categoria: Optional[str] = None,
    needs_review: Optional[bool] = None,
    tipo_prodotti: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    authorization: Optional[str] = Header(None),
) -> FattureListResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti, search)
    if fornitore:
        rows = [r for r in rows if fornitore.lower() in (r.get("fornitore") or "").lower()]
    if categoria:
        rows = [r for r in rows if r.get("categoria") == categoria]
    if needs_review is not None:
        rows = [r for r in rows if bool(r.get("needs_review")) == bool(needs_review)]

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    righe = [RigaFattura(**{k: v for k, v in r.items() if k in RigaFattura.model_fields}) for r in page_rows]
    return FattureListResponse(righe=righe, total=total, page=page, page_size=page_size)


# ─── Endpoint legacy compat: PATCH categoria singola riga ──────────────────

class AggiornaCategoriaRequest(BaseModel):
    categoria: str


@app.patch("/api/fatture/{riga_id}/categoria")
async def aggiorna_categoria_riga(
    riga_id: int,
    body: AggiornaCategoriaRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    categoria = body.categoria.strip()
    if not categoria or categoria in ("Da Clasificare", "Da Classificare"):
        raise HTTPException(status_code=400, detail="Categoria non valida")

    supabase_client = _get_supabase_client()
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
# MARGINALITÀ
# ═══════════════════════════════════════════════════════════════════════════

_CENTRI_DI_PRODUZIONE: Dict[str, List[str]] = {
    "FOOD": ["CARNE","PESCE","LATTICINI","SALUMI","UOVA","SCATOLAME E CONSERVE","OLIO E CONDIMENTI","PASTA E CEREALI","VERDURE","FRUTTA","SALSE E CREME","PRODOTTI DA FORNO","SPEZIE E AROMI","SUSHI VARIE"],
    "BEVERAGE": ["ACQUA","BEVANDE","CAFFE E THE","VARIE BAR"],
    "ALCOLICI": ["BIRRE","VINI","DISTILLATI","AMARI/LIQUORI"],
    "DOLCI": ["PASTICCERIA","GELATI E DESSERT"],
    "SHOP": ["SHOP"],
}
_CAT_TO_CENTRO: Dict[str, str] = {cat: c for c, cats in _CENTRI_DI_PRODUZIONE.items() for cat in cats}
_CATEGORIE_FB_M: List[str] = list(_CAT_TO_CENTRO.keys())
_CATEGORIE_SPESE_M: List[str] = ["SERVIZI E CONSULENZE","UTENZE E LOCALI","MANUTENZIONE E ATTREZZATURE","MATERIALE DI CONSUMO"]
_CENTRI_CON_FATTURATO = ["FOOD","BEVERAGE","ALCOLICI","DOLCI"]


def _load_mensile_overrides(sb, ristorante_id: str, annos: List[int]) -> Dict[tuple, Dict[str, float]]:
    """Mesi in modalità 'mensile': i ricavi vengono dal totale mensile inserito,
    non dall'aggregato giornaliero. Ritorna {(anno,mese): {iva10,iva22,altri}}."""
    if not annos:
        return {}
    try:
        resp = (
            sb.table("ricavi_modalita_mensile")
            .select("anno,mese,modalita,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
            .eq("ristorante_id", ristorante_id)
            .in_("anno", annos)
            .eq("modalita", "mensile")
            .execute()
        )
    except Exception:
        return {}
    out: Dict[tuple, Dict[str, float]] = {}
    for r in (resp.data or []):
        out[(int(r["anno"]), int(r["mese"]))] = {
            "iva10": float(r.get("fatturato_iva10") or 0),
            "iva22": float(r.get("fatturato_iva22") or 0),
            "altri": float(r.get("altri_ricavi_noiva") or 0),
        }
    return out


class MarginiMeseData(BaseModel):
    mese: int
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    altri_costi_fb: float = 0.0
    altri_costi_spese: float = 0.0
    costo_dipendenti: float = 0.0
    costo_personale_extra: float = 0.0
    costi_fb_auto: float = 0.0
    costi_spese_auto: float = 0.0


class MarginiAnnoResponse(BaseModel):
    anno: int
    mesi: List[MarginiMeseData]


class SalvaMarginiRequest(BaseModel):
    anno: int
    mesi: List[MarginiMeseData]


class FatturatoCentriData(BaseModel):
    anno: int
    mese: int
    fatturato_food: float = 0.0
    fatturato_beverage: float = 0.0
    fatturato_alcolici: float = 0.0
    fatturato_dolci: float = 0.0


class CentroCostoItem(BaseModel):
    centro: str
    categorie: List[str]
    costo_totale: float
    fatturato: float = 0.0
    margine: float = 0.0
    incidenza_su_fatt: float = 0.0
    incidenza_su_fb: float = 0.0


class AnalisiCentriResponse(BaseModel):
    centri: List[CentroCostoItem]
    totale_costi_fb: float
    fatturato_netto_periodo: float
    primo_margine: float
    primo_margine_pct: float
    mesi_con_dati: List[int]


def _load_fatture_fb_for_period(
    sb, ristorante_id: str, data_da: str, data_a: str
) -> "Dict[str, float]":
    import pandas as pd
    page_size = 1000
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            sb.table("fatture")
            .select("data_documento,totale_riga,categoria")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .neq("categoria", "Da Classificare")
            .gte("data_documento", data_da)
            .lte("data_documento", data_a)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = q.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    if not all_rows:
        return {}
    df = pd.DataFrame(all_rows)
    df["totale_riga"] = pd.to_numeric(df.get("totale_riga"), errors="coerce").fillna(0)
    df = df[df["categoria"].isin(_CATEGORIE_FB_M) & (df["totale_riga"] > 0)]
    return df.groupby("categoria")["totale_riga"].sum().to_dict()


@app.get("/api/margini", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_margini(
    anno: Optional[int] = None,
    authorization: Optional[str] = Header(None),
) -> MarginiAnnoResponse:
    import pandas as pd
    from datetime import datetime as _dt
    if anno is None:
        anno = _dt.now().year
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    resp = (
        sb.table("margini_mensili")
        .select("mese,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,altri_costi_fb,altri_costi_spese,costo_dipendenti,costo_personale_extra")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .execute()
    )
    saved = {int(r["mese"]): r for r in (resp.data or [])}

    page_size = 1000
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            sb.table("fatture")
            .select("data_documento,data_competenza,totale_riga,categoria")
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .neq("categoria", "Da Classificare")
            .or_(
                f"and(data_documento.gte.{anno}-01-01,data_documento.lt.{anno+1}-01-01),"
                f"and(data_competenza.gte.{anno}-01-01,data_competenza.lt.{anno+1}-01-01)"
            )
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = q.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    costi_fb_auto: Dict[int, float] = {}
    costi_spese_auto: Dict[int, float] = {}
    if all_rows:
        df = pd.DataFrame(all_rows)
        df["data_documento"] = pd.to_datetime(df.get("data_documento"), errors="coerce")
        df["data_competenza"] = pd.to_datetime(df.get("data_competenza"), errors="coerce")
        df["data_rif"] = df["data_competenza"].combine_first(df["data_documento"])
        df = df.dropna(subset=["data_rif"])
        df = df[df["data_rif"].dt.year == anno]
        df["mese"] = df["data_rif"].dt.month
        df["totale_riga"] = pd.to_numeric(df.get("totale_riga"), errors="coerce").fillna(0)
        costi_fb_auto = df[df["categoria"].isin(_CATEGORIE_FB_M)].groupby("mese")["totale_riga"].sum().to_dict()
        costi_spese_auto = df[df["categoria"].isin(_CATEGORIE_SPESE_M)].groupby("mese")["totale_riga"].sum().to_dict()

    mesi = []
    for m in range(1, 13):
        s = saved.get(m, {})
        mesi.append(MarginiMeseData(
            mese=m,
            fatturato_iva10=float(s.get("fatturato_iva10") or 0),
            fatturato_iva22=float(s.get("fatturato_iva22") or 0),
            altri_ricavi_noiva=float(s.get("altri_ricavi_noiva") or 0),
            altri_costi_fb=float(s.get("altri_costi_fb") or 0),
            altri_costi_spese=float(s.get("altri_costi_spese") or 0),
            costo_dipendenti=float(s.get("costo_dipendenti") or 0),
            costo_personale_extra=float(s.get("costo_personale_extra") or 0),
            costi_fb_auto=float(costi_fb_auto.get(m, 0)),
            costi_spese_auto=float(costi_spese_auto.get(m, 0)),
        ))

    return MarginiAnnoResponse(anno=anno, mesi=mesi)


@app.post("/api/margini", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def save_margini(
    body: SalvaMarginiRequest,
    authorization: Optional[str] = Header(None),
):
    from datetime import datetime as _dt, timezone as _tz
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        ex_resp = (
            sb.table("margini_mensili")
            .select("mese,fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", body.anno)
            .execute()
        )
        existing_centri = {int(r["mese"]): r for r in (ex_resp.data or [])}
    except Exception:
        existing_centri = {}

    now_iso = _dt.now(_tz.utc).isoformat()
    records = []
    for m in body.mesi:
        if not 1 <= m.mese <= 12:
            continue
        fatt_netto = (m.fatturato_iva10 / 1.10) + (m.fatturato_iva22 / 1.22) + m.altri_ricavi_noiva
        costi_fb_tot = m.costi_fb_auto + m.altri_costi_fb
        costi_spese_tot = m.costi_spese_auto + m.altri_costi_spese
        costi_pers = m.costo_dipendenti + m.costo_personale_extra
        primo_margine = fatt_netto - costi_fb_tot
        mol = primo_margine - costi_spese_tot - costi_pers
        fn = fatt_netto if fatt_netto > 0 else 1.0
        ec = existing_centri.get(m.mese, {})
        records.append({
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "anno": body.anno,
            "mese": m.mese,
            "fatturato_iva10": m.fatturato_iva10,
            "fatturato_iva22": m.fatturato_iva22,
            "altri_ricavi_noiva": m.altri_ricavi_noiva,
            "altri_costi_fb": m.altri_costi_fb,
            "altri_costi_spese": m.altri_costi_spese,
            "costo_dipendenti": m.costo_dipendenti,
            "costo_personale_extra": m.costo_personale_extra,
            "costi_fb_auto": m.costi_fb_auto,
            "costi_spese_auto": m.costi_spese_auto,
            "fatturato_netto": round(fatt_netto, 2),
            "costi_fb_totali": round(costi_fb_tot, 2),
            "primo_margine": round(primo_margine, 2),
            "mol": round(mol, 2),
            "food_cost_perc": round(costi_fb_tot / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "spese_perc": round(costi_spese_tot / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "personale_perc": round(costi_pers / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "mol_perc": round(mol / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "fatturato_food": float(ec.get("fatturato_food") or 0),
            "fatturato_beverage": float(ec.get("fatturato_beverage") or 0),
            "fatturato_alcolici": float(ec.get("fatturato_alcolici") or 0),
            "fatturato_dolci": float(ec.get("fatturato_dolci") or 0),
            "updated_at": now_iso,
        })

    sb.table("margini_mensili").upsert(records, on_conflict="ristorante_id,anno,mese").execute()
    return {"ok": True, "saved": len(records)}


@app.get("/api/margini/fatturato-centri", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_fatturato_centri(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
) -> FatturatoCentriData:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        resp = (
            sb.table("margini_mensili")
            .select("fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", anno)
            .eq("mese", mese)
            .execute()
        )
        row = (resp.data or [{}])[0]
    except Exception:
        row = {}

    return FatturatoCentriData(
        anno=anno, mese=mese,
        fatturato_food=float(row.get("fatturato_food") or 0),
        fatturato_beverage=float(row.get("fatturato_beverage") or 0),
        fatturato_alcolici=float(row.get("fatturato_alcolici") or 0),
        fatturato_dolci=float(row.get("fatturato_dolci") or 0),
    )


@app.post("/api/margini/fatturato-centri", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def save_fatturato_centri(
    body: FatturatoCentriData,
    authorization: Optional[str] = Header(None),
):
    from datetime import datetime as _dt, timezone as _tz
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    sb.table("margini_mensili").upsert({
        "user_id": user_id,
        "ristorante_id": ristorante_id,
        "anno": body.anno,
        "mese": body.mese,
        "fatturato_food": body.fatturato_food,
        "fatturato_beverage": body.fatturato_beverage,
        "fatturato_alcolici": body.fatturato_alcolici,
        "fatturato_dolci": body.fatturato_dolci,
        "updated_at": _dt.now(_tz.utc).isoformat(),
    }, on_conflict="ristorante_id,anno,mese").execute()
    return {"ok": True}


class FatturatoCentriGiornoItem(BaseModel):
    data: str
    food: float = 0.0
    beverage: float = 0.0
    alcolici: float = 0.0
    dolci: float = 0.0
    shop: float = 0.0


@app.get("/api/margini/fatturato-centri-giorni", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_fatturato_centri_giorni(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
) -> List[FatturatoCentriGiornoItem]:
    """Fatturato giornaliero stimato per centro.

    Non esiste uno split per singolo giorno: la ripartizione è mensile (% per
    centro su margini_mensili). Il valore giornaliero per centro è derivato
    distribuendo la quota mensile del centro sul fatturato netto di ogni giorno.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    from calendar import monthrange
    mese_str = f"{mese:02d}"
    last_day = monthrange(anno, mese)[1]
    data_da = f"{anno}-{mese_str}-01"
    data_a = f"{anno}-{mese_str}-{last_day:02d}"

    # Ricavi giornalieri → netto per giorno
    ric_resp = (
        sb.table("ricavi_giornalieri")
        .select("data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
        .eq("ristorante_id", ristorante_id)
        .gte("data", data_da)
        .lte("data", data_a)
        .order("data", desc=False)
        .execute()
    )
    netto_per_giorno: Dict[str, float] = {}
    for r in (ric_resp.data or []):
        netto_per_giorno[str(r.get("data"))] = _calc_netto(
            float(r.get("fatturato_iva10") or 0),
            float(r.get("fatturato_iva22") or 0),
            float(r.get("altri_ricavi_noiva") or 0),
        )
    netto_mese = sum(netto_per_giorno.values())
    if netto_mese <= 0:
        return []

    # Quote mensili per centro (euro) → frazione sul netto del mese
    mc_resp = (
        sb.table("margini_mensili")
        .select("fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    mc = (mc_resp.data or [{}])[0]
    frazioni = {
        "food": float(mc.get("fatturato_food") or 0) / netto_mese,
        "beverage": float(mc.get("fatturato_beverage") or 0) / netto_mese,
        "alcolici": float(mc.get("fatturato_alcolici") or 0) / netto_mese,
        "dolci": float(mc.get("fatturato_dolci") or 0) / netto_mese,
    }

    items: List[FatturatoCentriGiornoItem] = []
    for data_iso, netto_g in sorted(netto_per_giorno.items()):
        items.append(FatturatoCentriGiornoItem(
            data=data_iso,
            food=round(netto_g * frazioni["food"], 2),
            beverage=round(netto_g * frazioni["beverage"], 2),
            alcolici=round(netto_g * frazioni["alcolici"], 2),
            dolci=round(netto_g * frazioni["dolci"], 2),
            shop=0.0,
        ))
    return items


@app.get("/api/margini/analisi-centri", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_analisi_centri(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> AnalisiCentriResponse:
    from datetime import date as _date
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    costi_per_cat = _load_fatture_fb_for_period(sb, ristorante_id, data_da, data_a)

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)
    margini_resp = (
        sb.table("margini_mensili")
        .select("anno,mese,fatturato_netto,fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
        .eq("ristorante_id", ristorante_id)
        .gte("anno", d_da.year)
        .lte("anno", d_a.year)
        .execute()
    )

    fatturato_netto_periodo = 0.0
    fatturato_per_centro: Dict[str, float] = {c: 0.0 for c in _CENTRI_CON_FATTURATO}
    mesi_con_dati: List[int] = []

    for r in (margini_resp.data or []):
        anno_r, mese_r = int(r.get("anno", 0)), int(r.get("mese", 0))
        if not (1 <= mese_r <= 12):
            continue
        row_d = _date(anno_r, mese_r, 1)
        if not (_date(d_da.year, d_da.month, 1) <= row_d <= _date(d_a.year, d_a.month, 1)):
            continue
        fatt = float(r.get("fatturato_netto") or 0)
        fatturato_netto_periodo += fatt
        if fatt > 0:
            mesi_con_dati.append(mese_r)
        for c in _CENTRI_CON_FATTURATO:
            fatturato_per_centro[c] += float(r.get(f"fatturato_{c.lower()}") or 0)

    totale_costi_fb = sum(costi_per_cat.values())
    centri_out = []
    for centro, cats in _CENTRI_DI_PRODUZIONE.items():
        costo = sum(costi_per_cat.get(cat, 0) for cat in cats)
        fatt_c = fatturato_per_centro.get(centro, 0.0)
        margine = fatt_c - costo
        centri_out.append(CentroCostoItem(
            centro=centro,
            categorie=cats,
            costo_totale=round(costo, 2),
            fatturato=round(fatt_c, 2),
            margine=round(margine, 2),
            incidenza_su_fatt=round(costo / fatt_c * 100, 2) if fatt_c > 0 else 0.0,
            incidenza_su_fb=round(costo / totale_costi_fb * 100, 2) if totale_costi_fb > 0 else 0.0,
        ))

    primo_margine = fatturato_netto_periodo - totale_costi_fb
    return AnalisiCentriResponse(
        centri=centri_out,
        totale_costi_fb=round(totale_costi_fb, 2),
        fatturato_netto_periodo=round(fatturato_netto_periodo, 2),
        primo_margine=round(primo_margine, 2),
        primo_margine_pct=round(primo_margine / fatturato_netto_periodo * 100, 2) if fatturato_netto_periodo > 0 else 0.0,
        mesi_con_dati=sorted(set(mesi_con_dati)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# ANALISI AVANZATA CENTRI — drill-down categorie + andamento mensile + commenti
# ═══════════════════════════════════════════════════════════════════════════

_ICONE_CENTRI = {"FOOD": "🍖", "BEVERAGE": "☕", "ALCOLICI": "🍷", "DOLCI": "🍰", "SHOP": "🛒"}


class CategoriaDetail(BaseModel):
    categoria: str
    costo: float
    pct_su_centro: float


class CentroDetailItem(BaseModel):
    centro: str
    icona: str
    categorie_def: List[str]
    categorie_dettaglio: List[CategoriaDetail]
    costo_totale: float
    fatturato: float
    margine: float
    margine_pct: float
    incidenza_su_fatt: float
    incidenza_su_fb: float
    has_fatturato: bool


class AndamentoMese(BaseModel):
    anno: int
    mese: int
    label: str
    food: float
    beverage: float
    alcolici: float
    dolci: float
    shop: float


class CommentoKpi(BaseModel):
    kpi_nome: str
    percentuale: str
    commento: str
    emoji: str
    colore: str


class AnalisiAvanzataResponse(BaseModel):
    centri: List[CentroDetailItem]
    andamento_mensile: List[AndamentoMese]
    commenti: List[CommentoKpi]
    totale_costi_fb: float
    fatturato_netto_periodo: float
    fatturato_per_centro_totale: float
    primo_margine: float
    primo_margine_pct: float
    fatturato_split_attivo: bool
    mesi_con_dati: List[int]


def _load_fatture_fb_per_categoria_e_mese(
    sb, ristorante_id: str, data_da: str, data_a: str,
) -> "Dict[tuple, float]":
    """Ritorna dict {(anno, mese, categoria): totale}."""
    import pandas as pd
    page_size = 1000
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = (
            sb.table("fatture")
            .select("data_documento,totale_riga,categoria")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .neq("categoria", "Da Classificare")
            .gte("data_documento", data_da)
            .lte("data_documento", data_a)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = q.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    if not all_rows:
        return {}
    df = pd.DataFrame(all_rows)
    df["totale_riga"] = pd.to_numeric(df.get("totale_riga"), errors="coerce").fillna(0)
    df = df[df["categoria"].isin(_CATEGORIE_FB_M) & (df["totale_riga"] > 0)].copy()
    if df.empty:
        return {}
    df["data_documento"] = pd.to_datetime(df["data_documento"], errors="coerce")
    df = df.dropna(subset=["data_documento"])
    df["anno"] = df["data_documento"].dt.year
    df["mese"] = df["data_documento"].dt.month
    grouped = df.groupby(["anno", "mese", "categoria"])["totale_riga"].sum()
    return {(int(a), int(m), str(c)): float(v) for (a, m, c), v in grouped.items()}


@app.get("/api/margini/analisi-avanzata", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_analisi_avanzata(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> AnalisiAvanzataResponse:
    from datetime import date as _date
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)

    # Lista (anno, mese) target
    mesi_target = []
    y, m = d_da.year, d_da.month
    while (y, m) <= (d_a.year, d_a.month):
        mesi_target.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    # Costi mensili per categoria
    costi_map = _load_fatture_fb_per_categoria_e_mese(sb, ristorante_id, data_da, data_a)

    # Aggregato per categoria periodo
    costi_per_cat: Dict[str, float] = {}
    for (_a, _m, cat), tot in costi_map.items():
        costi_per_cat[cat] = costi_per_cat.get(cat, 0) + tot

    # Carica margini_mensili per ricavi e split centri
    annos = sorted({y for y, _ in mesi_target})
    margini_resp = (
        sb.table("margini_mensili")
        .select("anno,mese,fatturato_netto,fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )

    mensile_overrides = _load_mensile_overrides(sb, ristorante_id, annos)

    fatturato_netto_periodo = 0.0
    fatturato_per_centro: Dict[str, float] = {c: 0.0 for c in _CENTRI_CON_FATTURATO}
    mesi_con_dati: List[int] = []
    split_attivo = False

    mesi_target_set = {(y, m) for y, m in mesi_target}
    margini_map = {}
    for r in (margini_resp.data or []):
        anno_r = int(r.get("anno", 0))
        mese_r = int(r.get("mese", 0))
        if (anno_r, mese_r) in mesi_target_set:
            margini_map[(anno_r, mese_r)] = r
            ov = mensile_overrides.get((anno_r, mese_r))
            fatt = _calc_netto(ov["iva10"], ov["iva22"], ov["altri"]) if ov else float(r.get("fatturato_netto") or 0)
            fatturato_netto_periodo += fatt
            if fatt > 0:
                mesi_con_dati.append(mese_r)
            for c in _CENTRI_CON_FATTURATO:
                v = float(r.get(f"fatturato_{c.lower()}") or 0)
                fatturato_per_centro[c] += v
                if v > 0:
                    split_attivo = True

    fatturato_per_centro_tot = sum(fatturato_per_centro.values())
    totale_costi_fb = sum(costi_per_cat.values())

    # Costruisci CentroDetailItem
    centri_out: List[CentroDetailItem] = []
    for centro, cats in _CENTRI_DI_PRODUZIONE.items():
        costo = sum(costi_per_cat.get(cat, 0) for cat in cats)
        fatt_c = fatturato_per_centro.get(centro, 0.0)
        has_fatt = centro in _CENTRI_CON_FATTURATO and split_attivo and fatt_c > 0
        margine = fatt_c - costo if has_fatt else 0.0
        margine_pct = (margine / fatt_c * 100) if fatt_c > 0 else 0.0
        incidenza = (costo / fatt_c * 100) if fatt_c > 0 else 0.0
        # Per centri senza fatt proprio: % su fatturato totale split
        if not has_fatt and fatturato_per_centro_tot > 0:
            incidenza = (costo / fatturato_per_centro_tot * 100)

        # Categorie con dettaglio
        cat_details = []
        for cat in cats:
            c_cost = costi_per_cat.get(cat, 0)
            if c_cost > 0:
                cat_details.append(CategoriaDetail(
                    categoria=cat,
                    costo=round(c_cost, 2),
                    pct_su_centro=round(c_cost / costo * 100, 2) if costo > 0 else 0.0,
                ))
        cat_details.sort(key=lambda x: x.costo, reverse=True)

        centri_out.append(CentroDetailItem(
            centro=centro,
            icona=_ICONE_CENTRI.get(centro, "📁"),
            categorie_def=cats,
            categorie_dettaglio=cat_details,
            costo_totale=round(costo, 2),
            fatturato=round(fatt_c, 2),
            margine=round(margine, 2),
            margine_pct=round(margine_pct, 2),
            incidenza_su_fatt=round(incidenza, 2),
            incidenza_su_fb=round(costo / totale_costi_fb * 100, 2) if totale_costi_fb > 0 else 0.0,
            has_fatturato=has_fatt,
        ))

    primo_margine = fatturato_netto_periodo - totale_costi_fb
    primo_margine_pct = (primo_margine / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0

    # Andamento mensile per centro
    andamento: List[AndamentoMese] = []
    MESI_NOMI_BR = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    for (yy, mm) in mesi_target:
        costi_centri = {c: 0.0 for c in _CENTRI_DI_PRODUZIONE.keys()}
        for (a2, m2, cat), tot in costi_map.items():
            if a2 == yy and m2 == mm:
                centro_n = _CAT_TO_CENTRO.get(cat)
                if centro_n:
                    costi_centri[centro_n] += tot
        andamento.append(AndamentoMese(
            anno=yy, mese=mm, label=f"{MESI_NOMI_BR[mm-1]} {yy}",
            food=round(costi_centri.get("FOOD", 0), 2),
            beverage=round(costi_centri.get("BEVERAGE", 0), 2),
            alcolici=round(costi_centri.get("ALCOLICI", 0), 2),
            dolci=round(costi_centri.get("DOLCI", 0), 2),
            shop=round(costi_centri.get("SHOP", 0), 2),
        ))

    # Commenti automatici per centro
    commenti: List[CommentoKpi] = []
    for c in centri_out:
        if not c.has_fatturato or c.costo_totale == 0:
            continue
        fc = c.incidenza_su_fatt
        emoji, testo = _valuta_soglia_margine(fc, "food_cost", crescente=True)
        commenti.append(CommentoKpi(
            kpi_nome=f"{c.icona} {c.centro} — Incidenza costi",
            percentuale=f"{fc:.1f}%",
            commento=testo,
            emoji=emoji,
            colore=_COLORI_EMOJI.get(emoji, "#6b7280"),
        ))

    # Centro più performante / meno performante
    centri_con_fatt = [c for c in centri_out if c.has_fatturato and c.fatturato > 0]
    if centri_con_fatt:
        best = max(centri_con_fatt, key=lambda x: x.margine_pct)
        worst = min(centri_con_fatt, key=lambda x: x.margine_pct)
        if best.centro != worst.centro:
            commenti.append(CommentoKpi(
                kpi_nome=f"{best.icona} Centro più performante",
                percentuale=f"{best.margine_pct:.1f}%",
                commento=f"{best.centro} ha il margine % più alto del periodo",
                emoji="🟢",
                colore=_COLORI_EMOJI["🟢"],
            ))
            commenti.append(CommentoKpi(
                kpi_nome=f"{worst.icona} Centro più critico",
                percentuale=f"{worst.margine_pct:.1f}%",
                commento=f"{worst.centro} ha il margine % più basso — verificare costi e prezzi",
                emoji="🔴",
                colore=_COLORI_EMOJI["🔴"],
            ))

    return AnalisiAvanzataResponse(
        centri=centri_out,
        andamento_mensile=andamento,
        commenti=commenti,
        totale_costi_fb=round(totale_costi_fb, 2),
        fatturato_netto_periodo=round(fatturato_netto_periodo, 2),
        fatturato_per_centro_totale=round(fatturato_per_centro_tot, 2),
        primo_margine=round(primo_margine, 2),
        primo_margine_pct=round(primo_margine_pct, 2),
        fatturato_split_attivo=split_attivo,
        mesi_con_dati=sorted(set(mesi_con_dati)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PREZZI — Variazioni, Sconti, Omaggi, Note di Credito
# ═══════════════════════════════════════════════════════════════════════════

_CATEGORIE_SPESE_PREZZI = [
    "SERVIZI E CONSULENZE", "UTENZE E LOCALI",
    "MANUTENZIONE E ATTREZZATURE", "MATERIALE DI CONSUMO",
]
_PRICE_ALERT_DEFAULT = 5.0


class VariazionePrezzo(BaseModel):
    prodotto: str
    categoria: str
    fornitore: str
    storico: str
    media: float
    penultimo: float
    ultimo: float
    aumento_perc: float
    data: str
    n_fattura: str
    trend: str
    impatto_stimato: float
    delta_euro: float


class VariazioniResponse(BaseModel):
    variazioni: List[VariazionePrezzo]
    scostamento_medio: float
    impatto_netto: float
    fornitori_coinvolti: int
    soglia: float


class ScontoOmaggioItem(BaseModel):
    tipo: str
    descrizione: str
    categoria: str
    fornitore: str
    quantita: Optional[float]
    valore: float
    data: str
    numero_documento: str
    fattura: str


class ScontiOmaggiResponse(BaseModel):
    items: List[ScontoOmaggioItem]
    totale_risparmiato: float
    n_sconti: int
    n_omaggi: int


class NotaCreditoItem(BaseModel):
    documento: str
    data: str
    fornitore: str
    descrizione: str
    categoria: str
    quantita: Optional[float]
    credito: float
    numero_documento: str


class NoteCreditoResponse(BaseModel):
    note: List[NotaCreditoItem]
    totale_credito: float
    n_documenti: int


class StoricoPrezzoPoint(BaseModel):
    data: str
    prezzo_unitario: float


class StoricoPrezzoResponse(BaseModel):
    prodotto: str
    fornitore: str
    punti: List[StoricoPrezzoPoint]
    prezzo_medio: float


class SogliaAlertRequest(BaseModel):
    soglia: float


class SogliaAlertResponse(BaseModel):
    soglia: float


def _calcola_variazioni_prezzi_sync(rows: list, soglia: float) -> list:
    import pandas as pd

    if not rows:
        return []

    df = pd.DataFrame(rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce').fillna(1.0)

    df = df[~df['categoria'].isin(_CATEGORIE_SPESE_PREZZI)].copy()
    df = df[df['prezzo_unitario'] > 0].copy()

    if df.empty:
        return []

    df['_desc_key'] = df['descrizione'].astype(str).str.strip().str.upper()
    df['_forn_key'] = df['fornitore'].astype(str).str.strip().str.upper()

    alert_list = []

    for (_dk, _fk), group in df.groupby(['_desc_key', '_forn_key']):
        group = group.sort_values('data_documento')
        acquisti = group[group['prezzo_unitario'] > 0].copy()

        if len(acquisti) < 2:
            continue

        ultimo = acquisti.iloc[-1]
        penultimo = acquisti.iloc[-2]
        prezzo_ult = float(ultimo['prezzo_unitario'])
        prezzo_pen = float(penultimo['prezzo_unitario'])
        delta = prezzo_ult - prezzo_pen
        var_pct = (delta / prezzo_pen) * 100

        if abs(var_pct) < soglia:
            continue

        nota = ""
        try:
            d_pen = pd.to_datetime(penultimo['data_documento'], utc=True)
            d_ult = pd.to_datetime(ultimo['data_documento'], utc=True)
            if (d_ult - d_pen).days > 180:
                nota = " ⚠️ >6m"
        except Exception:
            pass

        storico = " → ".join(f"€{p:.2f}" for p in acquisti.tail(5)['prezzo_unitario'])
        media = float(acquisti['prezzo_unitario'].mean())

        prezzi_rec = pd.to_numeric(acquisti['prezzo_unitario'].tail(4), errors='coerce').dropna().tolist()
        var_rec = [
            prezzi_rec[i] - prezzi_rec[i - 1]
            for i in range(1, len(prezzi_rec))
            if abs(prezzi_rec[i] - prezzi_rec[i - 1]) > 0.0001
        ]
        if len(var_rec) >= 3 and all(v > 0 for v in var_rec[-3:]):
            trend = "⬆⬆"
        elif len(var_rec) >= 3 and all(v < 0 for v in var_rec[-3:]):
            trend = "⬇⬇"
        elif var_rec and any(v > 0 for v in var_rec) and any(v < 0 for v in var_rec):
            trend = "↕"
        elif delta > 0:
            trend = "⬆"
        elif delta < 0:
            trend = "⬇"
        else:
            trend = "↕"

        qta_all = pd.to_numeric(acquisti['quantita'], errors='coerce').dropna()
        qta_ref = float(qta_all.mean()) if not qta_all.empty else 1.0

        date_all = pd.to_datetime(acquisti['data_documento'], errors='coerce').dropna().sort_values()
        freq = 1.0
        if len(date_all) >= 2:
            n_mesi = max(1.0, (date_all.iloc[-1] - date_all.iloc[0]).days / 30.0)
            freq = len(date_all) / n_mesi

        alert_list.append({
            'prodotto': (str(group['descrizione'].mode()[0]) + nota)[:60],
            'categoria': str(ultimo.get('categoria', ''))[:25],
            'fornitore': str(group['fornitore'].mode()[0])[:30],
            'storico': storico,
            'media': round(media, 4),
            'penultimo': round(prezzo_pen, 4),
            'ultimo': round(prezzo_ult, 4),
            'aumento_perc': round(var_pct, 2),
            'data': str(ultimo.get('data_documento', '')),
            'n_fattura': str(ultimo.get('file_origine', '')),
            'trend': trend,
            'impatto_stimato': round(float(delta * qta_ref * freq), 2),
            'delta_euro': round(delta, 4),
        })

    alert_list.sort(key=lambda x: x['aumento_perc'], reverse=True)
    return alert_list


def _load_fatture_for_prezzi(
    sb, ristorante_id: str, data_da: str, data_a: str,
    extra_cols: str = "",
) -> list:
    cols = (
        "descrizione,categoria,fornitore,prezzo_unitario,quantita,"
        "totale_riga,data_documento,file_origine,tipo_documento"
        + (f",{extra_cols}" if extra_cols else "")
    )
    all_rows: list = []
    page = 0
    page_size = 1000
    while True:
        resp = (
            sb.table("fatture")
            .select(cols)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gte("data_documento", data_da)
            .lte("data_documento", data_a)
            .order("data_documento", desc=False)
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        page += 1
    return all_rows


def _load_num_documento_map(sb, ristorante_id: str) -> dict:
    """Restituisce {file_origine: numero_documento} da fatture_documenti (tutto il ristorante).
    Nessun filtro date: file_origine è univoco per ristorante, il filtro date era ridondante
    e causava miss su documenti ai bordi del periodo.
    """
    resp = (
        sb.table("fatture_documenti")
        .select("file_origine,numero_documento")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return {r["file_origine"]: (r.get("numero_documento") or "") for r in (resp.data or [])}


def _load_nc_file_origini(sb, ristorante_id: str, data_da: str, data_a: str) -> set:
    """Set di file_origine che sono vere note di credito (segno_compensazione=-1).
    Usato per distinguere sconti su fattura normale (→ Sconti tab) da NC reali.
    """
    resp = (
        sb.table("fatture_documenti")
        .select("file_origine")
        .eq("ristorante_id", ristorante_id)
        .eq("segno_compensazione", -1)
        .is_("deleted_at", "null")
        .gte("data_documento", data_da)
        .lte("data_documento", data_a)
        .execute()
    )
    return {r["file_origine"] for r in (resp.data or [])}


@app.get("/api/prezzi/soglia-alert", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
async def get_soglia_alert(
    authorization: Optional[str] = Header(None),
) -> SogliaAlertResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    resp = sb.table("users").select("price_alert_threshold").eq("id", user["id"]).limit(1).execute()
    val = _PRICE_ALERT_DEFAULT
    if resp.data:
        raw = resp.data[0].get("price_alert_threshold")
        if raw is not None:
            try:
                val = max(0.0, min(50.0, float(raw)))
            except (TypeError, ValueError):
                pass
    return SogliaAlertResponse(soglia=val)


@app.post("/api/prezzi/soglia-alert", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
async def set_soglia_alert(
    body: SogliaAlertRequest,
    authorization: Optional[str] = Header(None),
) -> SogliaAlertResponse:
    user = _resolve_user_from_token(authorization)
    val = max(0.0, min(50.0, float(body.soglia)))
    sb = _get_supabase_client()
    sb.table("users").update({"price_alert_threshold": val}).eq("id", user["id"]).execute()
    return SogliaAlertResponse(soglia=val)


@app.get("/api/prezzi/variazioni", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
async def get_variazioni_prezzi(
    data_da: str,
    data_a: str,
    soglia: float = _PRICE_ALERT_DEFAULT,
    authorization: Optional[str] = Header(None),
) -> VariazioniResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    variazioni = _calcola_variazioni_prezzi_sync(all_rows, soglia)

    scostamento_medio = 0.0
    impatto_netto = 0.0
    fornitori: set = set()
    if variazioni:
        pct_vals = [v['aumento_perc'] for v in variazioni]
        scostamento_medio = round(sum(pct_vals) / len(pct_vals), 2)
        impatto_netto = round(sum(v['impatto_stimato'] for v in variazioni), 2)
        fornitori = {v['fornitore'] for v in variazioni}

    return VariazioniResponse(
        variazioni=[VariazionePrezzo(**v) for v in variazioni],
        scostamento_medio=scostamento_medio,
        impatto_netto=impatto_netto,
        fornitori_coinvolti=len(fornitori),
        soglia=soglia,
    )


@app.get("/api/prezzi/sconti-omaggi", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
async def get_sconti_omaggi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> ScontiOmaggiResponse:
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    if not all_rows:
        return ScontiOmaggiResponse(items=[], totale_risparmiato=0.0, n_sconti=0, n_omaggi=0)

    num_map = _load_num_documento_map(sb, ristorante_id)

    df = pd.DataFrame(all_rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['totale_riga'] = pd.to_numeric(df['totale_riga'], errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce').fillna(1.0)
    df = df[~df['categoria'].isin(_CATEGORIE_SPESE_PREZZI)].copy()

    mask_sconto = (df['prezzo_unitario'] < -1e-9) | (df['totale_riga'] < -1e-9)
    mask_omaggio = (
        ~mask_sconto
        & (df['totale_riga'].abs() < 1e-9)
        & (df['prezzo_unitario'].abs() < 1e-9)
        & (df['descrizione'].astype(str).str.strip().str.len() > 3)
        & (~df['categoria'].astype(str).str.contains("NOTE E DICITURE", na=False))
    )

    df_sconti = df[mask_sconto].copy()
    df_omaggi = df[mask_omaggio].copy()

    items = []
    for _, r in df_sconti.iterrows():
        fo = str(r.get('file_origine', ''))
        items.append(ScontoOmaggioItem(
            tipo="sconto",
            descrizione=str(r.get('descrizione', '')),
            categoria=str(r.get('categoria', '')),
            fornitore=str(r.get('fornitore', '')),
            quantita=float(r['quantita']) if pd.notna(r['quantita']) else None,
            valore=round(abs(float(r['totale_riga'])), 2),
            data=str(r.get('data_documento', '')),
            numero_documento=num_map.get(fo, ''),
            fattura=fo,
        ))
    for _, r in df_omaggi.iterrows():
        fo = str(r.get('file_origine', ''))
        items.append(ScontoOmaggioItem(
            tipo="omaggio",
            descrizione=str(r.get('descrizione', '')),
            categoria=str(r.get('categoria', '')),
            fornitore=str(r.get('fornitore', '')),
            quantita=float(r['quantita']) if pd.notna(r['quantita']) else None,
            valore=0.0,
            data=str(r.get('data_documento', '')),
            numero_documento=num_map.get(fo, ''),
            fattura=fo,
        ))

    items.sort(key=lambda x: x.data, reverse=True)
    totale = round(sum(abs(float(r['totale_riga'])) for _, r in df_sconti.iterrows()), 2)

    return ScontiOmaggiResponse(
        items=items,
        totale_risparmiato=totale,
        n_sconti=len(df_sconti),
        n_omaggi=len(df_omaggi),
    )


@app.get("/api/prezzi/note-credito", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
async def get_note_credito(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> NoteCreditoResponse:
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    if not all_rows:
        return NoteCreditoResponse(note=[], totale_credito=0.0, n_documenti=0)

    num_map = _load_num_documento_map(sb, ristorante_id)
    # NC reali identificate via segno_compensazione=-1 in fatture_documenti.
    # Evita doppio conteggio con tab Sconti: righe negative su fatture normali
    # finivano sia in Sconti sia qui. Ora mask_totale_neg è limitata ai file NC.
    nc_files = _load_nc_file_origini(sb, ristorante_id, data_da, data_a)

    df = pd.DataFrame(all_rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['totale_riga'] = pd.to_numeric(df['totale_riga'], errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce').fillna(1.0)

    mask_tipo_nc = df['tipo_documento'].astype(str).str.upper().str.contains("NC|NOTA DI CREDITO|CREDIT", na=False)
    mask_totale_neg = (df['totale_riga'] < -0.01) & (df['file_origine'].isin(nc_files))
    df_nc = df[mask_tipo_nc | mask_totale_neg].copy()

    if df_nc.empty:
        return NoteCreditoResponse(note=[], totale_credito=0.0, n_documenti=0)

    note = []
    for _, r in df_nc.iterrows():
        fo = str(r.get('file_origine', ''))
        note.append(NotaCreditoItem(
            documento=fo,
            data=str(r.get('data_documento', '')),
            fornitore=str(r.get('fornitore', '')),
            descrizione=str(r.get('descrizione', '')),
            categoria=str(r.get('categoria', '')),
            quantita=float(r['quantita']) if pd.notna(r['quantita']) else None,
            credito=round(abs(float(r['totale_riga'])), 2),
            numero_documento=num_map.get(fo, ''),
        ))

    note.sort(key=lambda x: x.data, reverse=True)
    n_docs = df_nc['file_origine'].nunique()
    totale = round(df_nc['totale_riga'].abs().sum(), 2)

    return NoteCreditoResponse(note=note, totale_credito=totale, n_documenti=n_docs)


@app.get("/api/prezzi/storico-prodotto", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
async def get_storico_prodotto(
    prodotto: str,
    fornitore: str = "",
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> StoricoPrezzoResponse:
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    # Pulisce il nome prodotto dai suffissi UI prima di usarlo nei filtri DB
    prod_upper = prodotto.strip().upper()
    for suffix in [" ⚠️ >6M", " ⚠ >6M"]:
        if prod_upper.endswith(suffix):
            prod_upper = prod_upper[:-len(suffix)].strip()
    # Prefisso per ilike (primi 40 chars, sicuro per Supabase)
    prod_prefix = prod_upper[:40]

    all_rows: list = []
    page = 0
    page_size = 1000
    while True:
        q = (
            sb.table("fatture")
            .select("descrizione,fornitore,prezzo_unitario,data_documento")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gt("prezzo_unitario", 0)
            .ilike("descrizione", f"{prod_prefix}%")
            .order("data_documento", desc=False)
            .range(page * page_size, (page + 1) * page_size - 1)
        )
        if data_da:
            q = q.gte("data_documento", data_da)
        if data_a:
            q = q.lte("data_documento", data_a)
        if fornitore:
            q = q.eq("fornitore", fornitore.strip())
        resp = q.execute()
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        page += 1

    if not all_rows:
        return StoricoPrezzoResponse(prodotto=prodotto, fornitore=fornitore, punti=[], prezzo_medio=0.0)

    df = pd.DataFrame(all_rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['_desc'] = df['descrizione'].astype(str).str.strip().str.upper()
    df['_forn'] = df['fornitore'].astype(str).str.strip().str.upper()

    # Corrispondenza esatta prima, fallback su startswith
    mask = df['_desc'] == prod_upper
    if mask.sum() == 0:
        mask = df['_desc'].str.startswith(prod_upper[:30], na=False)

    if fornitore:
        mask = mask & (df['_forn'] == fornitore.strip().upper())

    df = df[mask & (df['prezzo_unitario'] > 0)].copy()

    if df.empty:
        return StoricoPrezzoResponse(prodotto=prodotto, fornitore=fornitore, punti=[], prezzo_medio=0.0)

    prezzo_medio = round(float(df['prezzo_unitario'].mean()), 4)
    punti = [
        StoricoPrezzoPoint(
            data=str(r['data_documento']),
            prezzo_unitario=round(float(r['prezzo_unitario']), 4),
        )
        for _, r in df.iterrows()
    ]

    return StoricoPrezzoResponse(
        prodotto=prodotto,
        fornitore=fornitore,
        punti=punti,
        prezzo_medio=prezzo_medio,
    )


# ═══════════════════════════════════════════════════════════════════════════
# MARGINI — analisi completa per periodo + cell update + commenti
# ═══════════════════════════════════════════════════════════════════════════

_KPI_SOGLIE_MARGINI = {
    "food_cost": [
        (28, "🟢", "Food cost eccellente — ottimo controllo acquisti e sprechi"),
        (33, "🟡", "Food cost nella norma per il settore ristorazione"),
        (38, "🟠", "Food cost sopra la media — valutare ottimizzazione acquisti o menù"),
        (100, "🔴", "Food cost critico — necessaria revisione fornitori, porzioni e sprechi"),
    ],
    "spese_generali": [
        (15, "🟢", "Spese generali contenute — gestione efficiente"),
        (22, "🟡", "Spese generali nella norma"),
        (28, "🟠", "Spese generali elevate — verificare utenze e contratti"),
        (100, "🔴", "Spese generali fuori controllo — necessaria rinegoziazione"),
    ],
    "personale": [
        (24, "🟢", "Costo del lavoro contenuto — buona efficienza del personale"),
        (30, "🟡", "Costo del lavoro nella norma per il settore"),
        (35, "🟠", "Costo del lavoro elevato — verificare turni, produttività e coperti"),
        (100, "🔴", "Costo del lavoro critico — incidenza troppo alta sul fatturato"),
    ],
    "primo_margine": [
        (55, "🔴", "1° Margine molto basso — costi F&B troppo alti rispetto al fatturato"),
        (62, "🟠", "1° Margine sotto la media — margine di miglioramento sui costi"),
        (70, "🟡", "1° Margine nella norma per il settore"),
        (200, "🟢", "1° Margine eccellente — ottima marginalità sui prodotti"),
    ],
    "mol": [
        (5, "🔴", "MOL critico — l'attività non genera margine sufficiente"),
        (12, "🟠", "MOL basso — necessario contenere costi o incrementare ricavi"),
        (20, "🟡", "MOL nella norma — margine operativo adeguato"),
        (200, "🟢", "MOL eccellente — ottima redditività operativa"),
    ],
}

_COLORI_EMOJI = {"🟢": "#16a34a", "🟡": "#ca8a04", "🟠": "#ea580c", "🔴": "#dc2626", "ℹ️": "#2563eb"}

_CELL_FIELDS_EDITABILI = {
    "altri_costi_fb", "altri_costi_spese", "costo_dipendenti", "costo_personale_extra",
}


def _valuta_soglia_margine(valore: float, key: str, crescente: bool = True) -> tuple:
    soglie = _KPI_SOGLIE_MARGINI.get(key, [])
    if not soglie:
        return ("ℹ️", "")
    for soglia, emoji, testo in soglie:
        if valore <= soglia:
            return (emoji, testo)
    return (soglie[-1][1], soglie[-1][2])


class MarginiCellaRequest(BaseModel):
    anno: int = Field(..., ge=2000, le=2100)
    mese: int = Field(..., ge=1, le=12)
    field: str
    value: float


class MarginiCellaResponse(BaseModel):
    anno: int
    mese: int
    field: str
    value: float


class MesiPivot(BaseModel):
    anno: int
    mese: int
    label: str
    fatturato_iva10: float
    fatturato_iva22: float
    altri_ricavi_noiva: float
    fatturato_netto: float
    costi_fb_auto: float
    altri_costi_fb: float
    costi_fb_totali: float
    primo_margine: float
    costi_spese_auto: float
    altri_costi_spese: float
    costi_spese_totali: float
    costo_dipendenti: float
    costo_personale_extra: float
    costi_personale: float
    mol: float


class MarginiAnalisiResponse(BaseModel):
    mesi: List[MesiPivot]
    totali: MesiPivot
    fatt_medio_mensile: float
    food_cost_perc: float
    primo_margine_perc: float
    spese_gen_perc: float
    personale_perc: float
    mol_perc: float
    num_mesi_attivi: int
    commenti: List[CommentoKpi]


def _calcola_costi_auto_per_mese(sb, ristorante_id: str, anno: int, mese: int) -> tuple:
    """Aggrega costi F&B e Spese Generali dalle fatture per il mese specifico."""
    from datetime import date as _date
    from calendar import monthrange
    last_day = monthrange(anno, mese)[1]
    data_da = f"{anno}-{mese:02d}-01"
    data_a = f"{anno}-{mese:02d}-{last_day:02d}"

    spese_gen_categorie = {
        "SERVIZI E CONSULENZE", "UTENZE E LOCALI",
        "MANUTENZIONE E ATTREZZATURE", "MATERIALE DI CONSUMO",
    }

    fb_tot = 0.0
    spese_tot = 0.0
    page = 0
    page_size = 1000
    while True:
        resp = (
            sb.table("fatture")
            .select("categoria,totale_riga,data_documento,data_competenza")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .or_(
                f"and(data_competenza.gte.{data_da},data_competenza.lte.{data_a}),"
                f"and(data_competenza.is.null,data_documento.gte.{data_da},data_documento.lte.{data_a})"
            )
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        for r in rows:
            cat = str(r.get("categoria") or "")
            try:
                tot = float(r.get("totale_riga") or 0)
            except (TypeError, ValueError):
                tot = 0.0
            if cat in spese_gen_categorie:
                spese_tot += tot
            elif cat and cat != "📝 NOTE E DICITURE":
                fb_tot += tot
        if len(rows) < page_size:
            break
        page += 1

    return round(fb_tot, 2), round(spese_tot, 2)


@app.post("/api/margini/cella", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def update_margini_cella(
    body: MarginiCellaRequest,
    authorization: Optional[str] = Header(None),
) -> MarginiCellaResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if body.field not in _CELL_FIELDS_EDITABILI:
        raise HTTPException(status_code=400, detail=f"Field non editable: {body.field}")

    val = max(0.0, float(body.value))

    # Upsert preservando altri campi: prima leggi riga esistente, poi update
    existing = (
        sb.table("margini_mensili")
        .select("*")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", body.anno)
        .eq("mese", body.mese)
        .limit(1)
        .execute()
    )

    if existing.data:
        sb.table("margini_mensili").update({
            body.field: val,
            "updated_at": "now()",
        }).eq("ristorante_id", ristorante_id).eq("anno", body.anno).eq("mese", body.mese).execute()
    else:
        new_row = {
            "user_id": user["id"],
            "ristorante_id": ristorante_id,
            "anno": body.anno,
            "mese": body.mese,
            body.field: val,
        }
        sb.table("margini_mensili").insert(new_row).execute()

    return MarginiCellaResponse(anno=body.anno, mese=body.mese, field=body.field, value=val)


@app.get("/api/margini/analisi", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_margini_analisi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> MarginiAnalisiResponse:
    from datetime import date as _date
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)

    # Costruisci lista (anno, mese) in range
    mesi_target = []
    y, m = d_da.year, d_da.month
    while (y, m) <= (d_a.year, d_a.month):
        mesi_target.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    # Carica margini_mensili (manuali + ricavi sincronizzati)
    annos = sorted({y for y, _ in mesi_target})
    margini_resp = (
        sb.table("margini_mensili")
        .select("*")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    margini_map = {(int(r["anno"]), int(r["mese"])): r for r in (margini_resp.data or [])}
    mensile_overrides = _load_mensile_overrides(sb, ristorante_id, annos)

    mesi_pivot: List[MesiPivot] = []
    for (y, m) in mesi_target:
        r = margini_map.get((y, m), {})
        fb_auto, spese_auto = _calcola_costi_auto_per_mese(sb, ristorante_id, y, m)

        ov = mensile_overrides.get((y, m))
        iva10 = ov["iva10"] if ov else float(r.get("fatturato_iva10") or 0)
        iva22 = ov["iva22"] if ov else float(r.get("fatturato_iva22") or 0)
        altri = ov["altri"] if ov else float(r.get("altri_ricavi_noiva") or 0)
        netto = (iva10 / 1.10) + (iva22 / 1.22) + altri

        altri_fb = float(r.get("altri_costi_fb") or 0)
        altri_sp = float(r.get("altri_costi_spese") or 0)
        cd = float(r.get("costo_dipendenti") or 0)
        cpe = float(r.get("costo_personale_extra") or 0)

        fb_tot = fb_auto + altri_fb
        sp_tot = spese_auto + altri_sp
        pers = cd + cpe
        pm = netto - fb_tot
        mol_v = pm - sp_tot - pers

        MESI_NOMI_BR = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
        mesi_pivot.append(MesiPivot(
            anno=y, mese=m, label=f"{MESI_NOMI_BR[m-1]} {y}",
            fatturato_iva10=round(iva10, 2),
            fatturato_iva22=round(iva22, 2),
            altri_ricavi_noiva=round(altri, 2),
            fatturato_netto=round(netto, 2),
            costi_fb_auto=fb_auto,
            altri_costi_fb=round(altri_fb, 2),
            costi_fb_totali=round(fb_tot, 2),
            primo_margine=round(pm, 2),
            costi_spese_auto=spese_auto,
            altri_costi_spese=round(altri_sp, 2),
            costi_spese_totali=round(sp_tot, 2),
            costo_dipendenti=round(cd, 2),
            costo_personale_extra=round(cpe, 2),
            costi_personale=round(pers, 2),
            mol=round(mol_v, 2),
        ))

    # Totali periodo
    tot_iva10 = sum(p.fatturato_iva10 for p in mesi_pivot)
    tot_iva22 = sum(p.fatturato_iva22 for p in mesi_pivot)
    tot_altri = sum(p.altri_ricavi_noiva for p in mesi_pivot)
    tot_netto = sum(p.fatturato_netto for p in mesi_pivot)
    tot_fb_auto = sum(p.costi_fb_auto for p in mesi_pivot)
    tot_altri_fb = sum(p.altri_costi_fb for p in mesi_pivot)
    tot_fb_totali = sum(p.costi_fb_totali for p in mesi_pivot)
    tot_pm = sum(p.primo_margine for p in mesi_pivot)
    tot_spese_auto = sum(p.costi_spese_auto for p in mesi_pivot)
    tot_altri_spese = sum(p.altri_costi_spese for p in mesi_pivot)
    tot_spese_totali = sum(p.costi_spese_totali for p in mesi_pivot)
    tot_cd = sum(p.costo_dipendenti for p in mesi_pivot)
    tot_cpe = sum(p.costo_personale_extra for p in mesi_pivot)
    tot_pers = sum(p.costi_personale for p in mesi_pivot)
    tot_mol = sum(p.mol for p in mesi_pivot)

    totali = MesiPivot(
        anno=0, mese=0, label="Totale periodo",
        fatturato_iva10=round(tot_iva10, 2), fatturato_iva22=round(tot_iva22, 2),
        altri_ricavi_noiva=round(tot_altri, 2), fatturato_netto=round(tot_netto, 2),
        costi_fb_auto=round(tot_fb_auto, 2), altri_costi_fb=round(tot_altri_fb, 2),
        costi_fb_totali=round(tot_fb_totali, 2), primo_margine=round(tot_pm, 2),
        costi_spese_auto=round(tot_spese_auto, 2), altri_costi_spese=round(tot_altri_spese, 2),
        costi_spese_totali=round(tot_spese_totali, 2),
        costo_dipendenti=round(tot_cd, 2), costo_personale_extra=round(tot_cpe, 2),
        costi_personale=round(tot_pers, 2), mol=round(tot_mol, 2),
    )

    # KPI medie sui mesi attivi (fatturato > 0)
    mesi_attivi = [p for p in mesi_pivot if p.fatturato_netto > 0]
    n_attivi = len(mesi_attivi)

    if n_attivi > 0:
        fatt_medio = sum(p.fatturato_netto for p in mesi_attivi) / n_attivi
        fc_perc = (tot_fb_totali / tot_netto * 100) if tot_netto > 0 else 0.0
        pm_perc = (tot_pm / tot_netto * 100) if tot_netto > 0 else 0.0
        sg_perc = (tot_spese_totali / tot_netto * 100) if tot_netto > 0 else 0.0
        pers_perc = (tot_pers / tot_netto * 100) if tot_netto > 0 else 0.0
        mol_perc = (tot_mol / tot_netto * 100) if tot_netto > 0 else 0.0
    else:
        fatt_medio = 0.0
        fc_perc = pm_perc = sg_perc = pers_perc = mol_perc = 0.0

    # Commenti automatici
    commenti: List[CommentoKpi] = []
    if n_attivi > 0:
        for key, val, crescente, nome in [
            ("food_cost", fc_perc, True, "Food Cost"),
            ("primo_margine", pm_perc, False, "1° Margine"),
            ("spese_generali", sg_perc, True, "Spese Generali"),
            ("personale", pers_perc, True, "Costo del Lavoro"),
            ("mol", mol_perc, False, "MOL"),
        ]:
            emoji, testo = _valuta_soglia_margine(val, key, crescente)
            commenti.append(CommentoKpi(
                kpi_nome=nome,
                percentuale=f"{val:.1f}%",
                commento=testo,
                emoji=emoji,
                colore=_COLORI_EMOJI.get(emoji, "#6b7280"),
            ))

    return MarginiAnalisiResponse(
        mesi=mesi_pivot,
        totali=totali,
        fatt_medio_mensile=round(fatt_medio, 2),
        food_cost_perc=round(fc_perc, 2),
        primo_margine_perc=round(pm_perc, 2),
        spese_gen_perc=round(sg_perc, 2),
        personale_perc=round(pers_perc, 2),
        mol_perc=round(mol_perc, 2),
        num_mesi_attivi=n_attivi,
        commenti=commenti,
    )


# ═══════════════════════════════════════════════════════════════════════════
# KPI condivisi (hub Ricavi e Margini) — 6 metriche + delta vs periodo prec.
# ═══════════════════════════════════════════════════════════════════════════

class MarginiKpiResponse(BaseModel):
    fatturato_lordo: float
    fatturato_netto: float
    costi_fb: float
    primo_margine: float
    spese_generali: float
    costo_personale: float
    mol: float
    food_cost_perc: float
    primo_margine_perc: float
    spese_perc: float
    personale_perc: float
    mol_perc: float
    delta_lordo_pct: Optional[float] = None
    delta_fb_pct: Optional[float] = None
    delta_margine_pct: Optional[float] = None
    delta_spese_pct: Optional[float] = None
    delta_personale_pct: Optional[float] = None
    delta_mol_pct: Optional[float] = None
    confronto_label: str
    spark_lordo: List[float] = []
    spark_fb: List[float] = []
    spark_margine: List[float] = []
    spark_spese: List[float] = []
    spark_personale: List[float] = []
    spark_mol: List[float] = []


def _aggrega_mensili_margini(sb, ristorante_id: str, d_da, d_a) -> dict:
    """Come _aggrega_totali_margini ma ritorna anche i valori per singolo mese (per le sparkline)."""
    mesi_target = []
    y, m = d_da.year, d_da.month
    while (y, m) <= (d_a.year, d_a.month):
        mesi_target.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    annos = sorted({yy for yy, _ in mesi_target}) or [d_da.year]
    margini_resp = (
        sb.table("margini_mensili")
        .select("*")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    margini_map = {(int(r["anno"]), int(r["mese"])): r for r in (margini_resp.data or [])}
    mensile_overrides = _load_mensile_overrides(sb, ristorante_id, annos)

    tot = {"lordo": 0.0, "netto": 0.0, "fb": 0.0, "pm": 0.0,
           "spese": 0.0, "pers": 0.0, "mol": 0.0, "mesi_attivi": 0,
           "spark_lordo": [], "spark_fb": [], "spark_margine": [],
           "spark_spese": [], "spark_personale": [], "spark_mol": []}
    for (yy, mm) in mesi_target:
        r = margini_map.get((yy, mm), {})
        fb_auto, spese_auto = _calcola_costi_auto_per_mese(sb, ristorante_id, yy, mm)
        ov = mensile_overrides.get((yy, mm))
        iva10 = ov["iva10"] if ov else float(r.get("fatturato_iva10") or 0)
        iva22 = ov["iva22"] if ov else float(r.get("fatturato_iva22") or 0)
        altri = ov["altri"] if ov else float(r.get("altri_ricavi_noiva") or 0)
        lordo = iva10 + iva22 + altri
        netto = (iva10 / 1.10) + (iva22 / 1.22) + altri
        fb_tot = fb_auto + float(r.get("altri_costi_fb") or 0)
        sp_tot = spese_auto + float(r.get("altri_costi_spese") or 0)
        pers = float(r.get("costo_dipendenti") or 0) + float(r.get("costo_personale_extra") or 0)
        pm = netto - fb_tot
        mol_v = pm - sp_tot - pers
        tot["lordo"] += lordo
        tot["netto"] += netto
        tot["fb"] += fb_tot
        tot["pm"] += pm
        tot["spese"] += sp_tot
        tot["pers"] += pers
        tot["mol"] += mol_v
        if netto > 0:
            tot["mesi_attivi"] += 1
        tot["spark_lordo"].append(round(lordo, 2))
        tot["spark_fb"].append(round(fb_tot, 2))
        tot["spark_margine"].append(round(pm, 2))
        tot["spark_spese"].append(round(sp_tot, 2))
        tot["spark_personale"].append(round(pers, 2))
        tot["spark_mol"].append(round(mol_v, 2))
    return tot


def _aggrega_totali_margini(sb, ristorante_id: str, d_da, d_a) -> dict:
    """Aggrega i totali del conto economico nel periodo [d_da, d_a] (oggetti date)."""
    mesi_target = []
    y, m = d_da.year, d_da.month
    while (y, m) <= (d_a.year, d_a.month):
        mesi_target.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    annos = sorted({yy for yy, _ in mesi_target}) or [d_da.year]
    margini_resp = (
        sb.table("margini_mensili")
        .select("*")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    margini_map = {(int(r["anno"]), int(r["mese"])): r for r in (margini_resp.data or [])}
    mensile_overrides = _load_mensile_overrides(sb, ristorante_id, annos)

    tot = {"lordo": 0.0, "netto": 0.0, "fb": 0.0, "pm": 0.0,
           "spese": 0.0, "pers": 0.0, "mol": 0.0, "mesi_attivi": 0}
    for (yy, mm) in mesi_target:
        r = margini_map.get((yy, mm), {})
        fb_auto, spese_auto = _calcola_costi_auto_per_mese(sb, ristorante_id, yy, mm)
        ov = mensile_overrides.get((yy, mm))
        iva10 = ov["iva10"] if ov else float(r.get("fatturato_iva10") or 0)
        iva22 = ov["iva22"] if ov else float(r.get("fatturato_iva22") or 0)
        altri = ov["altri"] if ov else float(r.get("altri_ricavi_noiva") or 0)
        lordo = iva10 + iva22 + altri
        netto = (iva10 / 1.10) + (iva22 / 1.22) + altri
        fb_tot = fb_auto + float(r.get("altri_costi_fb") or 0)
        sp_tot = spese_auto + float(r.get("altri_costi_spese") or 0)
        pers = float(r.get("costo_dipendenti") or 0) + float(r.get("costo_personale_extra") or 0)
        pm = netto - fb_tot
        mol_v = pm - sp_tot - pers
        tot["lordo"] += lordo
        tot["netto"] += netto
        tot["fb"] += fb_tot
        tot["pm"] += pm
        tot["spese"] += sp_tot
        tot["pers"] += pers
        tot["mol"] += mol_v
        if netto > 0:
            tot["mesi_attivi"] += 1
    return tot


@app.get("/api/margini/kpi", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
async def get_margini_kpi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> MarginiKpiResponse:
    from datetime import date as _date, timedelta as _timedelta
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)
    cur = _aggrega_mensili_margini(sb, ristorante_id, d_da, d_a)

    netto = cur["netto"]
    return MarginiKpiResponse(
        fatturato_lordo=round(cur["lordo"], 2),
        fatturato_netto=round(cur["netto"], 2),
        costi_fb=round(cur["fb"], 2),
        primo_margine=round(cur["pm"], 2),
        spese_generali=round(cur["spese"], 2),
        costo_personale=round(cur["pers"], 2),
        mol=round(cur["mol"], 2),
        food_cost_perc=round(cur["fb"] / netto * 100, 1) if netto > 0 else 0.0,
        primo_margine_perc=round(cur["pm"] / netto * 100, 1) if netto > 0 else 0.0,
        spese_perc=round(cur["spese"] / netto * 100, 1) if netto > 0 else 0.0,
        personale_perc=round(cur["pers"] / netto * 100, 1) if netto > 0 else 0.0,
        mol_perc=round(cur["mol"] / netto * 100, 1) if netto > 0 else 0.0,
        confronto_label="",
        spark_lordo=cur["spark_lordo"],
        spark_fb=cur["spark_fb"],
        spark_margine=cur["spark_margine"],
        spark_spese=cur["spark_spese"],
        spark_personale=cur["spark_personale"],
        spark_mol=cur["spark_mol"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# RICAVI GIORNALIERI — sorgente di verità ricavi (sync mensile via trigger DB)
# ═══════════════════════════════════════════════════════════════════════════

class RicavoGiornalieroItem(BaseModel):
    id: Optional[str] = None
    data: str  # YYYY-MM-DD
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    source: str = "manuale"


class RicaviGiornalieriResponse(BaseModel):
    items: List[RicavoGiornalieroItem]
    totale_iva10: float
    totale_iva22: float
    totale_altri: float
    totale_netto: float
    giorni_con_dati: int


class RicavoUpsertRequest(BaseModel):
    data: str
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0


class RicaviBatchUpsertRequest(BaseModel):
    items: List[RicavoUpsertRequest]
    source: str = "manuale"
    source_meta: Optional[Dict[str, Any]] = None


class RicaviBatchUpsertResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []


class RicaviImportXlsResponse(BaseModel):
    parsed_rows: int
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []
    preview: List[RicavoGiornalieroItem] = []


def _calc_netto(iva10: float, iva22: float, altri: float) -> float:
    return round((iva10 / 1.10) + (iva22 / 1.22) + altri, 2)


@app.get("/api/ricavi/giornalieri", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def get_ricavi_giornalieri(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> RicaviGiornalieriResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    resp = (
        sb.table("ricavi_giornalieri")
        .select("id,data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,source")
        .eq("ristorante_id", ristorante_id)
        .gte("data", data_da)
        .lte("data", data_a)
        .order("data", desc=False)
        .execute()
    )
    rows = resp.data or []

    items = [
        RicavoGiornalieroItem(
            id=str(r.get("id")),
            data=str(r.get("data")),
            fatturato_iva10=float(r.get("fatturato_iva10") or 0),
            fatturato_iva22=float(r.get("fatturato_iva22") or 0),
            altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
            source=str(r.get("source") or "manuale"),
        )
        for r in rows
    ]

    tot10 = sum(x.fatturato_iva10 for x in items)
    tot22 = sum(x.fatturato_iva22 for x in items)
    tot_altri = sum(x.altri_ricavi_noiva for x in items)

    return RicaviGiornalieriResponse(
        items=items,
        totale_iva10=round(tot10, 2),
        totale_iva22=round(tot22, 2),
        totale_altri=round(tot_altri, 2),
        totale_netto=_calc_netto(tot10, tot22, tot_altri),
        giorni_con_dati=len(items),
    )


@app.post("/api/ricavi/giornalieri", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def upsert_ricavo_giornaliero(
    body: RicavoUpsertRequest,
    authorization: Optional[str] = Header(None),
) -> RicavoGiornalieroItem:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    payload = {
        "user_id": user["id"],
        "ristorante_id": ristorante_id,
        "data": body.data,
        "fatturato_iva10": max(0.0, float(body.fatturato_iva10)),
        "fatturato_iva22": max(0.0, float(body.fatturato_iva22)),
        "altri_ricavi_noiva": max(0.0, float(body.altri_ricavi_noiva)),
        "source": "manuale",
    }

    resp = (
        sb.table("ricavi_giornalieri")
        .upsert(payload, on_conflict="ristorante_id,data")
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Salvataggio fallito")

    r = resp.data[0]
    return RicavoGiornalieroItem(
        id=str(r.get("id")),
        data=str(r.get("data")),
        fatturato_iva10=float(r.get("fatturato_iva10") or 0),
        fatturato_iva22=float(r.get("fatturato_iva22") or 0),
        altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
        source=str(r.get("source") or "manuale"),
    )


@app.delete("/api/ricavi/giornalieri", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def delete_ricavo_giornaliero(
    data: str,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    sb.table("ricavi_giornalieri").delete()\
      .eq("ristorante_id", ristorante_id)\
      .eq("data", data).execute()
    return {"deleted": True, "data": data}


@app.post("/api/ricavi/batch", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def upsert_ricavi_batch(
    body: RicaviBatchUpsertRequest,
    authorization: Optional[str] = Header(None),
) -> RicaviBatchUpsertResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    inserted = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    source = body.source if body.source in ("manuale", "xls", "email") else "manuale"

    # Pre-check esistenti per contare inserted vs updated
    if body.items:
        dates = [it.data for it in body.items]
        existing = (
            sb.table("ricavi_giornalieri")
            .select("data")
            .eq("ristorante_id", ristorante_id)
            .in_("data", dates)
            .execute()
        )
        existing_set = {str(r["data"]) for r in (existing.data or [])}
    else:
        existing_set = set()

    rows_to_upsert = []
    for it in body.items:
        try:
            d = it.data
            if not d:
                skipped += 1
                continue
            iva10 = max(0.0, float(it.fatturato_iva10 or 0))
            iva22 = max(0.0, float(it.fatturato_iva22 or 0))
            altri = max(0.0, float(it.altri_ricavi_noiva or 0))
            if iva10 + iva22 + altri <= 0:
                skipped += 1
                continue
            rows_to_upsert.append({
                "user_id": user["id"],
                "ristorante_id": ristorante_id,
                "data": d,
                "fatturato_iva10": iva10,
                "fatturato_iva22": iva22,
                "altri_ricavi_noiva": altri,
                "source": source,
                "source_meta": body.source_meta or None,
            })
        except Exception as e:
            errors.append(f"riga {it.data}: {e}")

    if rows_to_upsert:
        try:
            resp = (
                sb.table("ricavi_giornalieri")
                .upsert(rows_to_upsert, on_conflict="ristorante_id,data")
                .execute()
            )
            for row in (resp.data or []):
                if str(row.get("data")) in existing_set:
                    updated += 1
                else:
                    inserted += 1
        except Exception as e:
            errors.append(f"upsert: {e}")

    return RicaviBatchUpsertResponse(
        inserted=inserted, updated=updated, skipped=skipped, errors=errors,
    )


@app.post("/api/ricavi/import-xls", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def import_ricavi_xls(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
) -> RicaviImportXlsResponse:
    """Importa ricavi giornalieri da XLS/XLSX.

    Riconosce automaticamente il formato del gestionale:
      - Passbi v1: colonne Data|Ragione sociale|Tipo documento|Codice (IVA)|Importo
      - Generico: colonne data|iva10|iva22|altri (formato precedente)
    """
    import io as _io
    from datetime import date, datetime as _dt
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    content = await file.read()
    filename = (file.filename or "ricavi.xlsx").lower()

    try:
        if filename.endswith(".csv"):
            raw_df = pd.read_csv(_io.BytesIO(content), sep=None, engine="python", header=None)
        else:
            raw_df = pd.read_excel(_io.BytesIO(content), engine="openpyxl", header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File non leggibile: {e}")

    if raw_df.empty:
        return RicaviImportXlsResponse(parsed_rows=0, inserted=0, updated=0, skipped=0,
                                       errors=["File vuoto"])

    # ── Riconoscimento versione gestionale ───────────────────────────────────
    gestionale_version = _detect_gestionale_version(raw_df)

    if gestionale_version == "passbi_v1":
        items, errors, parsed_rows = _parse_passbi_v1(raw_df, ristorante_id, sb)
    else:
        items, errors, parsed_rows = _parse_generico(raw_df)

    if not items:
        return RicaviImportXlsResponse(parsed_rows=parsed_rows, inserted=0, updated=0,
                                       skipped=parsed_rows, errors=errors or ["Nessuna riga valida"])

    batch_req = RicaviBatchUpsertRequest(
        items=items,
        source="xls",
        source_meta={"filename": file.filename or "", "gestionale": gestionale_version},
    )
    batch_res = await upsert_ricavi_batch(batch_req, authorization=authorization)

    preview = [RicavoGiornalieroItem(
        data=it.data,
        fatturato_iva10=it.fatturato_iva10,
        fatturato_iva22=it.fatturato_iva22,
        altri_ricavi_noiva=it.altri_ricavi_noiva,
        source="xls",
    ) for it in items[:10]]

    return RicaviImportXlsResponse(
        parsed_rows=parsed_rows,
        inserted=batch_res.inserted,
        updated=batch_res.updated,
        skipped=batch_res.skipped + (parsed_rows - len(items)),
        errors=errors + batch_res.errors,
        preview=preview,
    )


def _detect_gestionale_version(raw_df) -> str:
    """Identifica il formato del file dal contenuto della prima riga."""
    import pandas as pd
    first_row_vals = [str(v).strip().lower() for v in raw_df.iloc[0].tolist() if pd.notna(v)]
    # Passbi v1: prima cella contiene "oneflux export" oppure le colonne header
    # tipiche sono data/ragione sociale/tipo documento
    combined = " ".join(first_row_vals)
    if "oneflux export" in combined:
        return "passbi_v1"
    # Controlla anche la riga header (riga 3 in Passbi v1)
    if len(raw_df) >= 4:
        header_row = [str(v).strip().lower() for v in raw_df.iloc[3].tolist() if str(v).strip()]
        header_combined = " ".join(header_row)
        if "ragione sociale" in header_combined or "tipo documento" in header_combined:
            return "passbi_v1"
    return "generico"


def _parse_passbi_v1(raw_df, ristorante_id: str, sb) -> tuple:
    """
    Parser per Passbi v1.
    Struttura: righe 0-2 header/metadati, riga 3 colonne, righe 4..N dati, ultima riga footer.
    Colonne: Data | Ragione sociale | Tipo documento | Codice (IVA) | Importo
    Regole mapping:
      - tipo_doc 'proforma' o vuoto, oppure IVA vuota → altri_ricavi_noiva (importo = netto già)
      - tipo_doc 'fattura'/'scontrino' + IVA 10 → fatturato_iva10 (lordo, scorporare)
      - tipo_doc 'fattura'/'scontrino' + IVA 22 → fatturato_iva22 (lordo, scorporare)
    """
    import pandas as pd
    from datetime import date, datetime as _dt
    from collections import defaultdict

    # Trova riga header cercando colonna "data" (tollerante)
    header_idx = None
    for i, row in raw_df.iterrows():
        vals = [str(v).strip().lower() for v in row.tolist()]
        if any("data" in v for v in vals):
            header_idx = i
            break
    if header_idx is None:
        return [], ["Header colonne non trovato nel file Passbi"], len(raw_df)

    headers = [str(v).strip() for v in raw_df.iloc[header_idx].tolist()]
    data_rows = raw_df.iloc[header_idx + 1:].reset_index(drop=True)
    parsed_rows = len(data_rows)

    # Mappa colonne per nome (tollerante a newline e varianti)
    def _find_col(names: list) -> Optional[int]:
        for i, h in enumerate(headers):
            norm = h.lower().replace("\n", " ").replace("  ", " ").strip()
            for n in names:
                if n in norm:
                    return i
        return None

    idx_data = _find_col(["data"])
    idx_ragione = _find_col(["ragione sociale", "azienda"])
    idx_tipo = _find_col(["tipo documento", "testata", "tipo_documento"])
    idx_iva = _find_col(["codice", "iva"])
    idx_importo = _find_col(["importo", "totale"])

    if idx_data is None or idx_importo is None:
        return [], ["Colonne Data o Importo non trovate nel file Passbi"], parsed_rows

    # Carica mapping ragione_sociale → ristorante_id
    mapping_resp = sb.table("ricavi_ragione_sociale_map").select("ragione_sociale_norm,ristorante_id").execute()
    ragione_map: Dict[str, str] = {
        str(r["ragione_sociale_norm"]).strip().lower(): str(r["ristorante_id"])
        for r in (mapping_resp.data or [])
    }

    def _parse_date(v) -> Optional[str]:
        from datetime import date as _date, datetime as _dt2
        if isinstance(v, (_date, _dt)):
            d = v.date() if isinstance(v, _dt) else v
            return d.isoformat()
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return _dt.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    def _to_float(v) -> float:
        if v is None:
            return 0.0
        import pandas as pd
        if isinstance(v, float) and pd.isna(v):
            return 0.0
        try:
            return max(0.0, float(str(v).replace(",", ".")))
        except Exception:
            return 0.0

    # Aggrega per (ristorante_id, data) → {iva10, iva22, altri}
    aggregato: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {"iva10": 0.0, "iva22": 0.0, "altri": 0.0})
    warnings_ragione: set = set()
    errors: List[str] = []

    for i, row in data_rows.iterrows():
        vals = row.tolist()

        # Scarta footer (data vuota + importo non vuoto)
        raw_data_val = vals[idx_data] if idx_data < len(vals) else None
        data_iso = _parse_date(raw_data_val)
        if data_iso is None:
            continue

        importo = _to_float(vals[idx_importo] if idx_importo < len(vals) else None)
        if importo <= 0:
            continue

        # Risolvi ristorante
        raw_ragione = str(vals[idx_ragione]).strip() if idx_ragione is not None and idx_ragione < len(vals) else ""
        import pandas as pd
        if not raw_ragione or raw_ragione.lower() in ("nan", "none"):
            target_ristorante = ristorante_id
        else:
            norm_ragione = raw_ragione.lower().strip()
            target_ristorante = ragione_map.get(norm_ragione)
            if target_ristorante is None:
                warnings_ragione.add(raw_ragione)
                target_ristorante = ristorante_id  # fallback: usa ristorante corrente

        tipo_doc = str(vals[idx_tipo]).strip().lower() if idx_tipo is not None and idx_tipo < len(vals) else ""
        raw_iva = vals[idx_iva] if idx_iva is not None and idx_iva < len(vals) else None
        iva_str = "" if raw_iva is None or (isinstance(raw_iva, float) and pd.isna(raw_iva)) else str(raw_iva).strip()

        key = (target_ristorante, data_iso)

        # Applica regole mapping
        if tipo_doc in ("proforma", "") or iva_str == "":
            aggregato[key]["altri"] += importo
        else:
            try:
                iva_val = int(float(iva_str))
            except (ValueError, TypeError):
                aggregato[key]["altri"] += importo
                continue
            if iva_val == 10:
                aggregato[key]["iva10"] += importo
            elif iva_val == 22:
                aggregato[key]["iva22"] += importo
            else:
                aggregato[key]["altri"] += importo

    if warnings_ragione:
        errors.append(f"Ragioni sociali non mappate (usato ristorante corrente): {', '.join(sorted(warnings_ragione))}")

    # L'import salva solo sul ristorante corrente. Le righe mappate ad altri
    # ristoranti vengono ignorate (il batch upsert non sa scrivere su ristoranti
    # diversi da quello del token): l'utente importa il file dal ristorante giusto.
    items: List[RicavoUpsertRequest] = []
    giorni_altri_ristoranti = 0
    for (rid, data_iso), buckets in aggregato.items():
        if buckets["iva10"] + buckets["iva22"] + buckets["altri"] <= 0:
            continue
        if rid != ristorante_id:
            giorni_altri_ristoranti += 1
            continue
        # Salva lordi; il calcolo netto avviene in lettura con scorporo
        items.append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=round(buckets["iva10"], 4),
            fatturato_iva22=round(buckets["iva22"], 4),
            altri_ricavi_noiva=round(buckets["altri"], 4),
        ))

    if giorni_altri_ristoranti:
        errors.append(
            f"{giorni_altri_ristoranti} giorni di altri ristoranti (mappati via ragione sociale) "
            f"ignorati: importa il file dal ristorante corrispondente."
        )

    return items, errors, parsed_rows


def _parse_generico(raw_df) -> tuple:
    """Parser generico per file con colonne data|iva10|iva22|altri (formato precedente)."""
    import pandas as pd
    from datetime import date, datetime as _dt

    df = raw_df.copy()
    # Prova a usare prima riga come header se sembra tale
    first_row = [str(v).strip().lower() for v in df.iloc[0].tolist()]
    if any(v in ("data", "date", "giorno") for v in first_row):
        df.columns = first_row
        df = df.iloc[1:].reset_index(drop=True)
    else:
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    col_data = next((c for c in df.columns if c in ("data", "date", "giorno", "data_documento")), None)
    col_iva10 = next((c for c in df.columns if c in ("iva10", "iva_10", "fatturato_iva10")), None)
    col_iva22 = next((c for c in df.columns if c in ("iva22", "iva_22", "fatturato_iva22")), None)
    col_altri = next((c for c in df.columns if c in ("altri", "altri_ricavi", "altri_ricavi_noiva", "noiva")), None)

    if not col_data:
        return [], ["Colonna 'data' non trovata"], len(df)

    items: List[RicavoUpsertRequest] = []
    errors: List[str] = []

    def _f(v) -> float:
        try:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return 0.0
            return max(0.0, float(str(v).replace(",", ".")))
        except Exception:
            return 0.0

    for idx, row in df.iterrows():
        raw_data = row.get(col_data)
        try:
            if isinstance(raw_data, (_dt,)):
                data_iso = raw_data.date().isoformat()
            elif hasattr(raw_data, "isoformat"):
                data_iso = raw_data.isoformat()
            else:
                s = str(raw_data).strip()
                if not s or s.lower() in ("nan", "none", ""):
                    continue
                parsed = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
                    try:
                        parsed = _dt.strptime(s, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    errors.append(f"riga {idx + 2}: data non riconosciuta '{s}'")
                    continue
                data_iso = parsed.isoformat()
        except Exception as e:
            errors.append(f"riga {idx + 2}: {e}")
            continue

        iva10 = _f(row.get(col_iva10)) if col_iva10 else 0.0
        iva22 = _f(row.get(col_iva22)) if col_iva22 else 0.0
        altri = _f(row.get(col_altri)) if col_altri else 0.0

        if iva10 + iva22 + altri <= 0:
            continue

        items.append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=iva10,
            fatturato_iva22=iva22,
            altri_ricavi_noiva=altri,
        ))

    return items, errors, len(df)


# ── Modalità ricavi mensili ──────────────────────────────────────────────────

class RicaviModalitaResponse(BaseModel):
    anno: int
    mese: int
    modalita: str  # "giornaliero" | "mensile"
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0


class RicaviModalitaUpsertRequest(BaseModel):
    anno: int
    mese: int
    modalita: str = "giornaliero"
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0


@app.get("/api/ricavi/modalita", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def get_ricavi_modalita(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
) -> RicaviModalitaResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    resp = (
        sb.table("ricavi_modalita_mensile")
        .select("anno,mese,modalita,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    if resp.data:
        r = resp.data[0]
        return RicaviModalitaResponse(
            anno=r["anno"], mese=r["mese"],
            modalita=str(r.get("modalita") or "giornaliero"),
            fatturato_iva10=float(r.get("fatturato_iva10") or 0),
            fatturato_iva22=float(r.get("fatturato_iva22") or 0),
            altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
        )
    return RicaviModalitaResponse(anno=anno, mese=mese, modalita="giornaliero")


@app.post("/api/ricavi/modalita", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def upsert_ricavi_modalita(
    body: RicaviModalitaUpsertRequest,
    authorization: Optional[str] = Header(None),
) -> RicaviModalitaResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if body.modalita not in ("giornaliero", "mensile"):
        raise HTTPException(status_code=400, detail="modalita deve essere 'giornaliero' o 'mensile'")
    if not 1 <= body.mese <= 12:
        raise HTTPException(status_code=400, detail="mese deve essere tra 1 e 12")

    payload = {
        "ristorante_id": ristorante_id,
        "anno": body.anno,
        "mese": body.mese,
        "modalita": body.modalita,
        "fatturato_iva10": max(0.0, float(body.fatturato_iva10)),
        "fatturato_iva22": max(0.0, float(body.fatturato_iva22)),
        "altri_ricavi_noiva": max(0.0, float(body.altri_ricavi_noiva)),
    }

    resp = (
        sb.table("ricavi_modalita_mensile")
        .upsert(payload, on_conflict="ristorante_id,anno,mese")
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Salvataggio modalità fallito")

    r = resp.data[0]
    return RicaviModalitaResponse(
        anno=r["anno"], mese=r["mese"],
        modalita=str(r.get("modalita") or "giornaliero"),
        fatturato_iva10=float(r.get("fatturato_iva10") or 0),
        fatturato_iva22=float(r.get("fatturato_iva22") or 0),
        altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
    )


# ═══════════════════════════════════════════════════════════════════════════
# AUTH — Reset password
# ═══════════════════════════════════════════════════════════════════════════


class ResetRequestBody(BaseModel):
    email: str


class ResetConfirmBody(BaseModel):
    token: str
    password: str


@app.post("/api/auth/reset-request", tags=["Auth"])
async def reset_password_request(body: ResetRequestBody):
    """Invia email con link di reset. Non richiede auth — qualsiasi email può richiederlo.
    Risponde sempre con successo generico per non rivelare se l'email è registrata.
    """
    from services.auth_service import invia_codice_reset
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email non valida")
    ok, msg = invia_codice_reset(email)
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/auth/reset-confirm", tags=["Auth"])
async def reset_password_confirm(body: ResetConfirmBody):
    """Verifica token e imposta nuova password."""
    from services.auth_service import imposta_password_da_token
    token = (body.token or "").strip()
    password = body.password or ""
    if not token or not password:
        raise HTTPException(status_code=400, detail="Token e password obbligatori")
    ok, msg, _ = imposta_password_da_token(token, password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ═══════════════════════════════════════════════════════════════════════════
# TAG — Analisi e Tag (custom tag prodotto + analisi + suggerimenti)
# ═══════════════════════════════════════════════════════════════════════════


class TagCreateRequest(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class TagUpdateRequest(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class AssociazioneItem(BaseModel):
    descrizione: str
    descrizione_key: Optional[str] = None
    fattore_kg: Optional[float] = None


class AggiungiAssociazioniRequest(BaseModel):
    descrizioni: List[AssociazioneItem]


class AcceptSuggestionRequest(BaseModel):
    suggestion_type: Optional[str] = None  # "new_tag" | "extend_tag"
    tag_name: Optional[str] = None
    tag_id: Optional[int] = None


class SnoozeSuggestionRequest(BaseModel):
    days: int = 30


def _assert_tag_ownership(sb, tag_id: int, user_id: str, ristorante_id: str) -> None:
    """Verifica che il tag appartenga all'utente/ristorante; alza 404 altrimenti."""
    resp = (
        sb.table("custom_tags")
        .select("id")
        .eq("id", int(tag_id))
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .limit(1)
        .execute()
    )
    if not (resp.data or []):
        raise HTTPException(status_code=404, detail="Tag non trovato")


def _parse_date_param(value: str, name: str):
    from datetime import datetime as _dt
    try:
        return _dt.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Parametro {name} non valido (atteso YYYY-MM-DD)")


@app.get("/api/tag", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def list_tags(authorization: Optional[str] = Header(None)):
    from services.db_service import get_custom_tags
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    return {"tags": get_custom_tags(str(user["id"]), ristorante_id)}


@app.post("/api/tag", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def create_tag(body: TagCreateRequest, authorization: Optional[str] = Header(None)):
    from services.db_service import crea_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome tag obbligatorio")
    tag = crea_tag(str(user["id"]), ristorante_id, nome, body.emoji, body.colore)
    return {"tag": tag}


@app.put("/api/tag/{tag_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def update_tag(tag_id: int, body: TagUpdateRequest, authorization: Optional[str] = Header(None)):
    from services.db_service import aggiorna_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome tag obbligatorio")
    tag = aggiorna_tag(int(tag_id), str(user["id"]), nome, body.emoji, body.colore)
    return {"tag": tag}


@app.delete("/api/tag/{tag_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def delete_tag(tag_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import elimina_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    elimina_tag(int(tag_id), str(user["id"]))
    return {"ok": True}


@app.get("/api/tag/descrizioni", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def list_descrizioni_distinte(authorization: Optional[str] = Header(None)):
    from services.db_service import get_descrizioni_distinte
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    return {"descrizioni": get_descrizioni_distinte(str(user["id"]), ristorante_id)}


@app.get("/api/tag/{tag_id}/prodotti", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def list_tag_prodotti(tag_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import get_custom_tag_prodotti
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    return {"prodotti": get_custom_tag_prodotti(int(tag_id), str(user["id"]))}


@app.post("/api/tag/{tag_id}/prodotti", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def add_tag_prodotti(
    tag_id: int, body: AggiungiAssociazioniRequest, authorization: Optional[str] = Header(None)
):
    from services.db_service import aggiungi_associazioni
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    descrizioni = [
        {
            "descrizione": i.descrizione,
            "descrizione_key": i.descrizione_key,
            "fattore_kg": i.fattore_kg,
        }
        for i in body.descrizioni
    ]
    try:
        created = aggiungi_associazioni(int(tag_id), descrizioni, user_id=str(user["id"]))
    except PermissionError:
        raise HTTPException(status_code=404, detail="Tag non trovato")
    return {"associazioni": created, "aggiunte": len(created)}


@app.delete("/api/tag/prodotti/{assoc_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def remove_tag_prodotto(assoc_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import rimuovi_associazione
    user = _resolve_user_from_token(authorization)
    rimuovi_associazione(int(assoc_id), str(user["id"]))
    return {"ok": True}


@app.get("/api/tag/{tag_id}/analisi", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def analizza_tag_endpoint(
    tag_id: int,
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
):
    from services.tag_analytics_service import analizza_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    d_da = _parse_date_param(data_da, "data_da")
    d_a = _parse_date_param(data_a, "data_a")
    return analizza_tag(str(user["id"]), ristorante_id, int(tag_id), d_da, d_a)


@app.get("/api/tag/{tag_id}/orfani", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def tag_orfani_endpoint(tag_id: int, authorization: Optional[str] = Header(None)):
    from services.tag_analytics_service import compute_orfani
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    orfani = compute_orfani(str(user["id"]), ristorante_id, int(tag_id))
    return {"orfani": orfani, "count": len(orfani)}


@app.get("/api/tag/suggestions", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
async def list_tag_suggestions(
    refresh: bool = False, authorization: Optional[str] = Header(None)
):
    from services.tag_suggestion_service import (
        list_pending_tag_suggestions,
        run_tag_suggestion_pipeline,
    )
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    if refresh:
        run_tag_suggestion_pipeline(user_id=str(user["id"]), ristorante_id=ristorante_id)
    suggestions = list_pending_tag_suggestions(user_id=str(user["id"]), ristorante_id=ristorante_id)
    return {"suggestions": suggestions}


@app.post(
    "/api/tag/suggestions/{sid}/accept", tags=["Tag"], dependencies=[Depends(_verify_worker_key)]
)
async def accept_tag_suggestion(
    sid: int,
    body: AcceptSuggestionRequest,
    authorization: Optional[str] = Header(None),
):
    from services.tag_suggestion_service import (
        accept_suggestion_create_tag,
        accept_suggestion_extend_tag,
    )
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    s_type = (body.suggestion_type or "").strip()
    if not s_type:
        row = (
            sb.table("custom_tag_suggestions")
            .select("suggestion_type")
            .eq("id", int(sid))
            .eq("user_id", str(user["id"]))
            .eq("ristorante_id", ristorante_id)
            .limit(1)
            .execute()
        )
        if not (row.data or []):
            raise HTTPException(status_code=404, detail="Suggerimento non trovato")
        s_type = str(row.data[0].get("suggestion_type") or "")

    if s_type == "new_tag":
        result = accept_suggestion_create_tag(
            suggestion_id=int(sid),
            tag_name=body.tag_name,
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
        )
    elif s_type == "extend_tag":
        result = accept_suggestion_extend_tag(
            suggestion_id=int(sid),
            tag_id=body.tag_id,
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
        )
    else:
        raise HTTPException(status_code=400, detail="suggestion_type non valido")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Operazione non riuscita"))
    return result


@app.post(
    "/api/tag/suggestions/{sid}/snooze", tags=["Tag"], dependencies=[Depends(_verify_worker_key)]
)
async def snooze_tag_suggestion_endpoint(
    sid: int,
    body: SnoozeSuggestionRequest,
    authorization: Optional[str] = Header(None),
):
    from services.tag_suggestion_service import snooze_tag_suggestion
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    snooze_tag_suggestion(
        int(sid), user_id=str(user["id"]), ristorante_id=ristorante_id, days=int(body.days)
    )
    return {"ok": True}


@app.post(
    "/api/tag/suggestions/{sid}/dismiss", tags=["Tag"], dependencies=[Depends(_verify_worker_key)]
)
async def dismiss_tag_suggestion_endpoint(sid: int, authorization: Optional[str] = Header(None)):
    from services.tag_suggestion_service import dismiss_tag_suggestion
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    dismiss_tag_suggestion(int(sid), user_id=str(user["id"]), ristorante_id=ristorante_id)
    return {"ok": True}


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
