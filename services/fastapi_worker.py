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
import anyio
import io
import json
import logging
import os
import secrets
import sys
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _oggi_rome() -> date:
    """Data di oggi nel fuso Europe/Rome.

    Su Railway il server gira in UTC: date.today() nella finestra notturna
    (mezzanotte-02:00 ora italiana) restituisce il giorno precedente, sfasando
    di 1 giorno/1 mese i confronti "oggi/ieri/questo mese". Usare questo helper
    per ogni semantica di calendario rivolta al ristoratore italiano.
    """
    from zoneinfo import ZoneInfo
    return datetime.now(tz=ZoneInfo("Europe/Rome")).date()

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

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
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
# Fail-closed: senza WORKER_SECRET_KEY i guard server-to-server sarebbero saltati,
# esponendo il worker a chiamate dirette da Internet. Lo skip è consentito solo se
# lo sviluppatore lo dichiara esplicitamente con WORKER_DEV_MODE=1.
WORKER_DEV_MODE = os.getenv("WORKER_DEV_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
if not WORKER_SECRET_KEY and not WORKER_DEV_MODE:
    raise RuntimeError(
        "WORKER_SECRET_KEY non impostata. Configurala in produzione, "
        "oppure imposta WORKER_DEV_MODE=1 per saltare i guard worker-key in locale."
    )
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

def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    """Verifica API key condivisa tra Streamlit e worker.
    Lo skip è consentito solo in dev mode esplicito (WORKER_DEV_MODE=1);
    in assenza della chiave senza quel flag l'app non si avvia (fail-closed).
    """
    if WORKER_DEV_MODE and not WORKER_SECRET_KEY:
        return  # dev mode esplicito: skip
    # Confronto a tempo costante: evita timing attack sulla chiave condivisa
    # (coerente con l'HMAC del webhook, gia' time-safe).
    if not secrets.compare_digest(x_worker_key or "", WORKER_SECRET_KEY):
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


# ── Agent notturno — stato in-memory + loop ──────────────────────────────────

_agent_notturno_state: dict = {
    "enabled": False,
    "ora_utc": 2,
    "last_run_at": None,
    "last_digest": None,
    "running": False,
}


def _agent_notturno_load_from_db() -> None:
    """Legge la configurazione da app_settings al boot."""
    try:
        sb = get_supabase_client()
        resp = sb.table("app_settings").select("value").eq("key", "agent_notturno").limit(1).execute()
        if resp.data:
            v = resp.data[0]["value"]
            _agent_notturno_state["enabled"] = bool(v.get("enabled", False))
            _agent_notturno_state["ora_utc"] = int(v.get("ora_utc", 2))
            _agent_notturno_state["last_run_at"] = v.get("last_run_at")
            _agent_notturno_state["last_digest"] = v.get("last_digest")
    except Exception as exc:
        logger.warning("agent_notturno: impossibile caricare config da DB: %s", exc)


def _agent_notturno_persist() -> None:
    """Persiste lo stato corrente (escl. running) in app_settings."""
    try:
        sb = get_supabase_client()
        sb.table("app_settings").upsert({
            "key": "agent_notturno",
            "value": {
                "enabled": _agent_notturno_state["enabled"],
                "ora_utc": _agent_notturno_state["ora_utc"],
                "last_run_at": _agent_notturno_state["last_run_at"],
                "last_digest": _agent_notturno_state["last_digest"],
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "worker",
        }, on_conflict="key").execute()
    except Exception as exc:
        logger.warning("agent_notturno: impossibile persistere config: %s", exc)


def _run_agent_notturno() -> dict:
    """Esegue l'agent notturno: auto-review + pre-classificazione media + digest."""
    if _agent_notturno_state["running"]:
        logger.info("agent_notturno: già in esecuzione, skip")
        return {}

    _agent_notturno_state["running"] = True
    t0 = time.monotonic()
    logger.info("🤖 Agent notturno: avvio")

    try:
        import pandas as pd
        from utils.validation import classify_special_row_vectorized, SPECIAL_ROW_NORMALE, SPECIAL_ROW_DICITURA, SPECIAL_ROW_SCONTO_OMAGGIO
        from utils.text_utils import pulisci_caratteri_corrotti
        from utils.validation import is_dicitura_sicura, is_sconto_omaggio_sicuro
        from services.ai_service import applica_regole_categoria_forti, applica_correzioni_dizionario

        sb = get_supabase_client()
        admin_emails = _admin_emails_set()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Carica tutti gli utenti non-admin
        users_resp = sb.table("users").select("id,email").execute()
        allowed_ids = [u["id"] for u in (users_resp.data or []) if u.get("email", "").lower() not in admin_emails]
        if not allowed_ids:
            return {"classificate": 0, "errori": 0, "elapsed_s": 0}

        # Carica righe in coda (needs_review=True, non cancellate)
        all_rows: list = []
        page_size = 1000
        offset = 0
        while True:
            q = (sb.table("fatture")
                 .select("id,descrizione,categoria,prezzo_unitario,totale_riga,quantita,tipo_documento,needs_review")
                 .is_("deleted_at", "null")
                 .in_("user_id", allowed_ids)
                 .eq("needs_review", True)
                 .order("id")
                 .range(offset, offset + page_size - 1))
            resp = q.execute()
            chunk = resp.data or []
            if not chunk:
                break
            all_rows.extend(chunk)
            if len(chunk) < page_size:
                break
            offset += page_size

        if not all_rows:
            digest = {"classificate": 0, "auto_review": 0, "suggerite": 0, "errori": 0, "elapsed_s": 0}
            _agent_notturno_state["last_run_at"] = now_iso
            _agent_notturno_state["last_digest"] = digest
            _agent_notturno_persist()
            return digest

        df = pd.DataFrame(all_rows)
        df["descrizione"] = df["descrizione"].apply(lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x)

        meta = classify_special_row_vectorized(df)
        df["bucket"] = meta["bucket"]

        classificate_auto = 0
        classificate_suggerite = 0
        errori = 0

        # ── 1. Auto-review: diciture €0 e sconti/omaggi sicuri ─────────────
        auto_diciture = df[df["bucket"] == SPECIAL_ROW_DICITURA]["descrizione"].dropna().unique().tolist()
        auto_sconti = df[df["bucket"] == SPECIAL_ROW_SCONTO_OMAGGIO]["descrizione"].dropna().unique().tolist()

        for desc in auto_diciture:
            try:
                prezzo_max = float(df[df["descrizione"] == desc]["prezzo_unitario"].max() or 0)
                if prezzo_max > 0:
                    continue
                ids = df[df["descrizione"] == desc]["id"].tolist()
                cat_da = str(df[df["descrizione"] == desc]["categoria"].iloc[0] or "")
                sb.table("fatture").update({
                    "categoria": "📝 NOTE E DICITURE",
                    "needs_review": False,
                    "reviewed_at": now_iso,
                    "reviewed_by": "agent-notturno",
                }).in_("id", ids).is_("deleted_at", "null").execute()
                sb.table("prodotti_master").upsert({
                    "descrizione": desc, "categoria": "📝 NOTE E DICITURE",
                    "confidence": "altissima", "verified": True,
                    "classificato_da": "agent-notturno", "ultima_modifica": now_iso,
                }, on_conflict="descrizione").execute()
                _log_review_action(sb, "agent-notturno", "auto_review", "📝 NOTE E DICITURE", ids, desc, cat_da, "notturno:dicitura")
                classificate_auto += len(ids)
            except Exception as exc:
                errori += 1
                logger.warning("agent_notturno dicitura '%s': %s", desc[:40], exc)

        for desc in auto_sconti:
            try:
                row = df[df["descrizione"] == desc].iloc[0]
                cat = row.get("categoria") or ""
                if not cat or cat == "Da Clasificare":
                    continue
                ids = df[df["descrizione"] == desc]["id"].tolist()
                sb.table("fatture").update({
                    "needs_review": False,
                    "reviewed_at": now_iso,
                    "reviewed_by": "agent-notturno",
                }).in_("id", ids).is_("deleted_at", "null").execute()
                sb.table("prodotti_master").upsert({
                    "descrizione": desc, "categoria": cat,
                    "confidence": "alta", "verified": True,
                    "classificato_da": "agent-notturno", "ultima_modifica": now_iso,
                }, on_conflict="descrizione").execute()
                _log_review_action(sb, "agent-notturno", "auto_review", cat, ids, desc, cat, "notturno:sconto_omaggio")
                classificate_auto += len(ids)
            except Exception as exc:
                errori += 1
                logger.warning("agent_notturno sconto '%s': %s", desc[:40], exc)

        # ── 2. Suggerite: righe NORMALE con suggerimento deterministico forte ─
        df_normali = df[df["bucket"] == SPECIAL_ROW_NORMALE].copy()
        if not df_normali.empty:
            desc_unici = df_normali["descrizione"].dropna().unique().tolist()
            for desc in desc_unici:
                try:
                    cat_forte, _ = applica_regole_categoria_forti(desc, "Da Classificare")
                    if not cat_forte or cat_forte == "Da Classificare":
                        continue
                    ids = df_normali[df_normali["descrizione"] == desc]["id"].tolist()
                    cat_da = str(df_normali[df_normali["descrizione"] == desc]["categoria"].iloc[0] or "")
                    sb.table("fatture").update({
                        "categoria": cat_forte,
                        "needs_review": False,
                        "reviewed_at": now_iso,
                        "reviewed_by": "agent-notturno",
                    }).in_("id", ids).is_("deleted_at", "null").execute()
                    sb.table("prodotti_master").upsert({
                        "descrizione": desc, "categoria": cat_forte,
                        "confidence": "alta", "verified": True,
                        "classificato_da": "agent-notturno", "ultima_modifica": now_iso,
                    }, on_conflict="descrizione").execute()
                    _log_review_action(sb, "agent-notturno", "auto_review", cat_forte, ids, desc, cat_da, "notturno:regola_forte")
                    classificate_suggerite += len(ids)
                except Exception as exc:
                    errori += 1
                    logger.warning("agent_notturno suggerita '%s': %s", desc[:40], exc)

        # ── 3. Prepara suggerimenti AI per le righe ambigue (NON scrive) ───
        # Le righe 'da_verificare' senza soluzione deterministica vengono
        # proposte dall'AI: la categoria NON viene applicata, solo salvata come
        # suggerimento da approvare a mano nello strumento Categorie.
        suggerite_ai = 0
        try:
            from services.routers.admin import prepara_suggerimenti_ai
            res_ai = prepara_suggerimenti_ai(sb, list(allowed_ids), attore="agent-notturno")
            suggerite_ai = int(res_ai.get("suggerite", 0))
            errori += int(res_ai.get("errori", 0))
        except Exception as exc:
            logger.warning("agent_notturno suggerimenti AI: %s", exc)

        elapsed_s = round(time.monotonic() - t0, 1)
        digest = {
            "classificate": classificate_auto + classificate_suggerite,
            "auto_review": classificate_auto,
            "suggerite": classificate_suggerite,
            "suggerite_ai": suggerite_ai,
            "errori": errori,
            "elapsed_s": elapsed_s,
        }

        _log_review_action(
            sb, "agent-notturno", "digest_notturno",
            categoria_a="—",
            ids_fatture=[],
            descrizione="Digest notturno",
            nota=f"auto={classificate_auto} suggerite={classificate_suggerite} errori={errori} elapsed={elapsed_s}s",
        )

        _agent_notturno_state["last_run_at"] = now_iso
        _agent_notturno_state["last_digest"] = digest
        _agent_notturno_persist()

        logger.info("🤖 Agent notturno completato: %s", digest)
        return digest

    except Exception as exc:
        logger.exception("agent_notturno: errore critico: %s", exc)
        _agent_notturno_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        _agent_notturno_state["last_digest"] = {"errore": str(exc)[:200]}
        _agent_notturno_persist()
        return {}
    finally:
        _agent_notturno_state["running"] = False


async def _agent_notturno_loop() -> None:
    """Loop che controlla ogni minuto se è l'ora programmata per l'agent notturno."""
    await asyncio.sleep(30)  # breve attesa al boot
    last_run_date: Optional[date] = None
    while True:
        try:
            if _agent_notturno_state["enabled"] and not _agent_notturno_state["running"]:
                now = datetime.now(timezone.utc)
                if now.hour == _agent_notturno_state["ora_utc"] and now.minute < 10:
                    if last_run_date != now.date():
                        last_run_date = now.date()
                        asyncio.create_task(_run_agent_notturno(), name="agent-notturno-run")
        except Exception as exc:
            logger.warning("agent_notturno_loop: %s", exc)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Gli endpoint sono `def` sincroni: FastAPI li esegue nel threadpool di AnyIO.
    # Il default e' 40 thread; lo alziamo perche' la Home spara 6-7 chiamate in
    # parallelo e ogni richiesta occupa un thread per tutta la durata della query
    # Supabase (sincrona). Cosi' l'event loop resta sempre libero.
    try:
        _tp_size = int(os.getenv("WORKER_THREADPOOL_SIZE", "100"))
        anyio.to_thread.current_default_thread_limiter().total_tokens = _tp_size
        logger.info("Threadpool AnyIO impostato a %d thread", _tp_size)
    except Exception as exc:
        logger.warning("Impossibile impostare la dimensione del threadpool: %s", exc)

    _agent_notturno_load_from_db()

    tasks = []
    if _ENABLE_INLINE_QUEUE_PROCESSOR:
        tasks.append(asyncio.create_task(_queue_loop(), name="queue-processor-loop"))
    else:
        logger.info("ℹ️ Inline queue processor disabilitato (ENABLE_INLINE_QUEUE_PROCESSOR=0)")

    tasks.append(asyncio.create_task(_agent_notturno_loop(), name="agent-notturno-loop"))

    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
            try:
                await t
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
    # OpenAPI docs esposte solo in dev: in produzione rivelerebbero la mappa di
    # tutti gli endpoint (inclusi /api/admin/*) a chiunque, facilitando il recon.
    # Disabilitato anche openapi_url, altrimenti /openapi.json resterebbe pubblico
    # (FastAPI lo serve indipendentemente da docs_url) esponendo lo stesso schema.
    docs_url="/docs" if WORKER_DEV_MODE else None,
    redoc_url="/redoc" if WORKER_DEV_MODE else None,
    openapi_url="/openapi.json" if WORKER_DEV_MODE else None,
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
            "https://app.oneflux.it",
            "https://nuovo.oneflux.it",
        ]

    if "*" in origins:
        raise RuntimeError("WORKER_ALLOWED_ORIGINS non puo' contenere '*'.")

    return list(dict.fromkeys(origins))

from config.constants import MAX_UPLOAD_BYTES as _MAX_BODY_BYTES  # 50 MiB centralizzato


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
def health() -> Dict[str, str]:
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
def classify(request: Request, body: ClassifyRequest) -> ClassifyResponse:
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
        raise HTTPException(status_code=500, detail="Errore durante la classificazione.")


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
        if len(contents) > _MAX_BODY_BYTES:
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
        raise HTTPException(status_code=500, detail="Errore durante l'elaborazione del file.")


# ═══════════════════════════════════════════════════════════════════════════
# POST /webhook
# ═══════════════════════════════════════════════════════════════════════════

_SUPABASE_CLIENT_CACHE: Dict[str, Any] = {}


def _get_supabase_client():
    """Client Supabase service-role per operazioni backend del worker.

    Memoizzato per (url, key): create_client istanzia client PostgREST/Auth/Storage
    (setup connessione/TLS) e veniva chiamato piu' volte per request. Il client
    service-role e' stateless -> sicuro riusarlo. Chiave su (url,key) per gestire
    eventuali cambi di env senza riavvio.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase non configurato (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).")

    cache_key = f"{url}::{key[:8]}"
    cached = _SUPABASE_CLIENT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if SyncClientOptions is None:
        client = create_client(url, key)
    else:
        options = SyncClientOptions(
            postgrest_client_timeout=30,
            storage_client_timeout=30,
        )
        client = create_client(url, key, options=options)
    _SUPABASE_CLIENT_CACHE[cache_key] = client
    return client


# Alias modulo: gli endpoint admin chiamano get_supabase_client() senza import
# locale. Le funzioni che fanno `from services import get_supabase_client`
# lo shadowano localmente, quindi questo alias non altera il loro comportamento.
get_supabase_client = _get_supabase_client


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
def invoicetronic_webhook_disabled() -> JSONResponse:
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
    # Nome/id della SEDE attiva (clienti multi-sede). Per i mono-sede coincidono
    # con nome_ristorante / il loro unico ristorante: la UI puo' usarli sempre.
    sede_attiva_nome: Optional[str] = None
    sede_attiva_id: Optional[str] = None
    # Numero di sedi attive dell'account. ≥2 = cliente catena → la UI lo atterra
    # su /catena (vista gruppo) invece che sulla Home del singolo PV.
    num_sedi: int = 1
    pagine_abilitate: Optional[List[str]] = None
    is_admin: bool = False
    tema: str = "dark"


class LoginResponse(BaseModel):
    token: str = Field(..., description="Session token da settare in cookie HTTP-only")
    user: UserPublic


# Default admin se ADMIN_EMAILS non e' impostata (es. produzione Railway senza
# env): gli unici due admin del progetto. Centralizzato per evitare drift con
# l'altro default in _admin_emails_set().
_DEFAULT_ADMIN_EMAILS = "md@oneflux.it,mattiadavolio90@gmail.com"


def _is_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    admin_emails_raw = os.getenv("ADMIN_EMAILS", _DEFAULT_ADMIN_EMAILS)
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
def auth_login(body: LoginRequest, request: Request) -> LoginResponse:
    _check_rate_limit(request.client.host if request.client else "unknown")

    from services.auth_service import verifica_credenziali, AuthServiceUnavailableError

    try:
        user, error = verifica_credenziali(body.email, body.password)
    except AuthServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if error or not user:
        raise HTTPException(status_code=401, detail=error or "Credenziali non valide")

    # Crea una sessione multi-token (tabella sessioni): più dispositivi possono
    # restare loggati insieme. Sostituisce la scrittura su users.session_token.
    try:
        from services.session_service import crea_sessione
        _ua = request.headers.get("user-agent") if request else None
        _ip = request.client.host if (request and request.client) else None
        token = crea_sessione(user["id"], source="login", user_agent=_ua, ip=_ip)
    except Exception:
        logger.exception("Errore creazione sessione")
        raise HTTPException(status_code=500, detail="Errore creazione sessione")

    # num_sedi serve subito al client per atterrare i clienti catena (≥2 sedi) su
    # /catena invece che sulla Home del PV. Stessa count di auth_me.
    num_sedi = 1
    try:
        cnt = (
            _get_supabase_client()
            .table("ristoranti")
            .select("id", count="exact")
            .eq("user_id", user["id"])
            .eq("attivo", True)
            .execute()
        )
        if cnt.count is not None:
            num_sedi = int(cnt.count)
    except Exception:
        pass

    return LoginResponse(
        token=token,
        user=UserPublic(
            id=str(user["id"]),
            email=user["email"],
            nome_ristorante=user.get("nome_ristorante"),
            num_sedi=num_sedi,
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
def auth_me(authorization: Optional[str] = Header(None)) -> UserPublic:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token mancante")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vuoto")

    from services.auth_service import verifica_sessione_da_cookie
    user = verifica_sessione_da_cookie(token)

    if not user:
        raise HTTPException(status_code=401, detail="Sessione non valida o scaduta")

    # Sede attiva: per i clienti multi-sede la testata deve riflettere la sede
    # SELEZIONATA, non il nome account. Best-effort: se la risoluzione fallisce
    # si ricade sul nome account senza compromettere la verifica sessione.
    sede_id: Optional[str] = None
    sede_nome: Optional[str] = user.get("nome_ristorante")
    num_sedi = 1
    try:
        sb = _get_supabase_client()
        sede_id, sede_nome = _resolve_sede_attiva(user, sb)
        # Conteggio sedi attive: serve alla UI per atterrare i clienti catena
        # (≥2 sedi) su /catena. count="exact" con head → niente payload righe.
        cnt = (
            sb.table("ristoranti")
            .select("id", count="exact")
            .eq("user_id", user.get("id"))
            .eq("attivo", True)
            .execute()
        )
        if cnt.count is not None:
            num_sedi = int(cnt.count)
    except Exception:
        pass

    return UserPublic(
        id=str(user["id"]),
        email=user["email"],
        nome_ristorante=user.get("nome_ristorante"),
        sede_attiva_nome=sede_nome,
        sede_attiva_id=sede_id,
        num_sedi=num_sedi,
        pagine_abilitate=_normalize_pagine(user.get("pagine_abilitate")),
        is_admin=_is_admin_email(user.get("email")),
        tema=(user.get("tema") or "dark"),
    )


@app.post(
    "/api/auth/logout",
    summary="Logout — invalida session_token legacy",
    tags=["Auth"],
    dependencies=[Depends(_verify_worker_key)],
)
def auth_logout(authorization: Optional[str] = Header(None)) -> Dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"status": "ok"}

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return {"status": "ok"}

    try:
        from services.session_service import revoca_sessione
        revocata = revoca_sessione(token)
        if not revocata:
            # Fallback: sessione legacy ancora su users.session_token (pre multi-token).
            from services import get_supabase_client
            supabase_client = get_supabase_client()
            supabase_client.table("users").update({
                "session_token": None,
                "session_token_created_at": None,
            }).eq("session_token", token).execute()
    except Exception as exc:
        logger.warning(f"Logout: errore invalidazione sessione: {exc}")

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


# Micro-cache della sede attiva (ultimo_ristorante_id) keyed per token. La Home
# fa ~6 chiamate worker per load, ognuna passa di qui: senza cache erano 6 SELECT
# su users per render. TTL 5s: abbastanza per condividere il valore entro un
# singolo load (chiamate quasi simultanee) senza reintrodurre la stantia' che lo
# switch sede deve evitare. Invalidata esplicitamente al cambio sede.
_SEDE_ATTIVA_CACHE: Dict[str, tuple] = {}
_SEDE_ATTIVA_TTL = 5.0  # secondi


def _invalidate_sede_attiva_cache(token: Optional[str] = None) -> None:
    """Invalida la micro-cache della sede attiva (un token, o tutta)."""
    if token is None:
        _SEDE_ATTIVA_CACHE.clear()
    else:
        _SEDE_ATTIVA_CACHE.pop(token, None)


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

    # Rilettura FRESCA della sede attiva, scavalcando la cache di sessione (TTL
    # 30s, in-memory per-processo). Senza questo, dopo uno switch sede il valore
    # cached di ultimo_ristorante_id restava stantio fino a 30s — e su piu' worker
    # uvicorn la richiesta successiva poteva colpire un processo con cache calda,
    # mostrando in modo intermittente la sede VECCHIA (KPI, salute, notifiche,
    # testata). E' la causa del "devo ricaricare piu' volte e aspettare" sullo
    # switch. Micro-cache TTL 5s keyed per token: i ~6 endpoint di un singolo load
    # condividono una SELECT invece di rifarla 6 volte; lo switch invalida la cache
    # (account_cambia_sede), quindi resta immediato.
    # Non tocchiamo un eventuale ristorante_id esplicito (impersonazione admin).
    if not user.get("ristorante_id"):
        import time as _t
        _now = _t.monotonic()
        _cached = _SEDE_ATTIVA_CACHE.get(token)
        if _cached and (_now - _cached[0]) < _SEDE_ATTIVA_TTL:
            if _cached[1]:
                user["ultimo_ristorante_id"] = _cached[1]
        else:
            try:
                sb = _get_supabase_client()
                fresh = (
                    sb.table("users")
                    .select("ultimo_ristorante_id")
                    .eq("id", user.get("id"))
                    .single()
                    .execute()
                )
                rid_fresh = (fresh.data or {}).get("ultimo_ristorante_id")
                _SEDE_ATTIVA_CACHE[token] = (_now, rid_fresh)
                if rid_fresh:
                    user["ultimo_ristorante_id"] = rid_fresh
            except Exception as exc:
                logger.warning("_resolve_user_from_token: rilettura sede fresca fallita: %s", exc)

    return user


# Cache in-process per /api/dashboard/stats (full-load + aggregazione Python).
_DASHBOARD_STATS_CACHE: Dict[str, tuple] = {}
_DASHBOARD_STATS_TTL = 60.0  # secondi


@app.get(
    "/api/dashboard/stats",
    response_model=DashboardStats,
    summary="Statistiche dashboard utente — KPI + grafici",
    tags=["Dashboard"],
    dependencies=[Depends(_verify_worker_key)],
)
def dashboard_stats(authorization: Optional[str] = Header(None)) -> DashboardStats:
    from datetime import date, timedelta
    from collections import defaultdict
    import time as _time

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    from services import get_supabase_client
    supabase_client = get_supabase_client()

    # Scoping per ristorante: senza, la Home aggregava TUTTI i ristoranti dell'utente
    # mentre Margini/Fatture/Prezzi mostrano un solo ristorante -> KPI Home incoerenti
    # col resto dell'app appena attivo il multi-ristorante. Allineato a _build_fatture_base_query.
    ristorante_id = _resolve_ristorante_id(user, supabase_client)

    # Cache in-process: l'endpoint fa un full-load di tutte le righe del ristorante
    # e aggrega in Python. Su clienti grandi e' costoso; un TTL breve evita di
    # rieseguirlo a ogni richiesta ravvicinata (coerente con _HOME_KPI_CACHE).
    _cache_key = f"dashstats:{user_id}:{ristorante_id}"
    _cached = _DASHBOARD_STATS_CACHE.get(_cache_key)
    if _cached and (_time.monotonic() - _cached[0]) < _DASHBOARD_STATS_TTL:
        return _cached[1]

    rows: List[Dict[str, Any]] = []
    page_size = 1000
    start = 0
    while True:
        _q = (
            supabase_client.table("fatture")
            .select("file_origine,data_documento,fornitore,categoria,totale_riga")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
        )
        if ristorante_id:
            _q = _q.eq("ristorante_id", ristorante_id)
        resp = (
            _q
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    today = _oggi_rome()
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

    _result = DashboardStats(
        kpi=kpi,
        spesa_mensile=spesa_mensile,
        top_fornitori=top_fornitori,
        top_categorie=top_categorie,
    )
    _DASHBOARD_STATS_CACHE[_cache_key] = (_time.monotonic(), _result)
    return _result


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
    """Wrapper per firma (user_id, client): delega a _resolve_ristorante_id.

    Unificato per evitare divergenze: prima questa funzione NON filtrava
    attivo=True ne' ordinava, potendo restituire un ristorante diverso da quello
    usato da margini/fatture (che usano _resolve_ristorante_id) -> rischio di
    salvare spese/dati sul ristorante sbagliato nel modello multi-ristorante.
    """
    ultimo = None
    try:
        resp = supabase_client.table("users") \
            .select("ultimo_ristorante_id") \
            .eq("id", user_id) \
            .single() \
            .execute()
        if resp.data:
            ultimo = resp.data.get("ultimo_ristorante_id")
    except Exception:
        pass
    return _resolve_ristorante_id(
        {"id": user_id, "ultimo_ristorante_id": ultimo},
        supabase_client,
    )


@app.post("/api/upload/start-session", tags=["Upload"])
def upload_start_session(authorization: Optional[str] = Header(None)):
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
    if not contents:
        raise HTTPException(status_code=422, detail="File vuoto.")

    # Validazione magic bytes: il contenuto deve corrispondere all'estensione
    # (stessa logica del percorso Streamlit upload_handler). Difende il path di
    # upload diretto browser->worker da file con estensione mascherata.
    _magic_ok = False
    if ext == "xml":
        _head = contents[:200].lstrip(b"\xef\xbb\xbf").lstrip()
        _magic_ok = _head.startswith(b"<?xml") or (b"<" in _head[:10] and b"FatturaElettronica" in contents[:500])
    elif ext == "p7m":
        _raw_start = contents[:20].decode("ascii", errors="ignore").strip()
        _magic_ok = (contents[0:1] == b"\x30") or any(
            _raw_start.startswith(p) for p in ("MIIF", "MIIE", "MIIG", "MIIB", "MIIA", "-----")
        )
    if not _magic_ok:
        raise HTTPException(
            status_code=422,
            detail=f"Il contenuto del file non corrisponde all'estensione .{ext}.",
        )

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

    # Nuove righe salvate -> invalida la cache di lettura per questo ristorante,
    # altrimenti i KPI/articoli resterebbero stale fino allo scadere del TTL.
    _invalidate_fatture_rows_cache(ristorante_id)

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
    # Dati strutturati del topic (es. count righe da classificare): usati dai
    # trigger contestuali frontend (contaTopicAttivo). Prima non era serializzato
    # e il fallback su titolo falliva sui segnali live -> trigger mai scattati.
    payload: Optional[Dict[str, Any]] = None
    # False per i segnali LIVE ricalcolati (fatturato/fatture/righe mancanti...):
    # non hanno una riga in notification_inbox, quindi "archivia" non li
    # persisterebbe e riapparirebbero al refresh. Il frontend nasconde la X.
    # Si chiudono da soli quando il dato viene inserito.
    dismissible: bool = True


class NotificheResponse(BaseModel):
    notifiche: List[NotificaItem]
    total: int
    unread: int


class BriefingAzione(BaseModel):
    id: str
    topic_key: str
    severity: str = "info"
    testo: str
    cta_label: str
    cta_page: str


class BriefingResponse(BaseModel):
    saluto: str
    data: str
    narrativa: str
    severity_max: str = "info"
    tutto_ok: bool
    azioni: List[BriefingAzione]
    generated_at: Optional[str] = None


class SaluteVoce(BaseModel):
    """Una delle voci di completezza dati del mese."""
    key: str
    label: str
    ok: bool
    dettaglio: str
    cta_page: Optional[str] = None


class SaluteResponse(BaseModel):
    """Indice di salute della gestione — completezza dati del mese corrente."""
    indice: int
    colore: str  # "verde" | "giallo" | "rosso"
    mese_label: str
    voci: List[SaluteVoce]


class AlertPrezzo(BaseModel):
    """Un aumento prezzo rilevante per impatto €/mese (prodotto o tag)."""
    tipo: str  # "prodotto" | "tag"
    nome: str
    fornitore: str = ""
    aumento_pct: float
    impatto_mese: float


class AlertPrezziResponse(BaseModel):
    """Alert prezzi per impatto €/mese — solo food&beverage, top per impatto."""
    count: int
    alerts: List[AlertPrezzo]
    top: Optional[AlertPrezzo] = None


class ConfigTopic(BaseModel):
    """Un avviso configurabile dal cliente."""
    key: str
    label: str
    enabled: bool
    bloccato: bool = False  # True = sempre attivo, non spegnibile
    descrizione: str = ""   # micro-spiegazione per i ristoratori antitecnologici


class ConfigResponse(BaseModel):
    """Configurazione assistente: nome + interruttori topic + Chat AI."""
    nome_referente: str = ""
    topics: List[ConfigTopic]
    chat_ai_enabled: bool = True
    chat_limite_giorno: int = 10  # 0 = piano free, chat non disponibile
    # Domande gia' consumate oggi: valore iniziale del contatore "ti restano N"
    # del widget chat, mostrato gia' all'apertura (prima ancora di chattare).
    chat_domande_oggi: int = 0
    # Soglia % alert prezzi (users.price_alert_threshold): da qui si IMPOSTA quando
    # scatta l'avviso "Alert prezzi". In pagina Prezzi resta solo come filtro di
    # visualizzazione, non la salva piu'. Per-utente (non per-ristorante).
    price_alert_threshold: float = 5.0
    # Se true, gli avvisi prezzi (briefing + Home) si limitano ai prodotti
    # preferiti (stella in pagina Prezzi) + tag. Default false = Pareto + tag.
    alert_prezzi_solo_preferiti: bool = False


class ConfigUpdateRequest(BaseModel):
    nome_referente: Optional[str] = None
    topics_disabled: List[str] = []
    chat_ai_enabled: Optional[bool] = None
    # None = non toccare. Clamp [0,50] lato salvataggio (set_price_alert_threshold).
    price_alert_threshold: Optional[float] = None
    # None = non toccare.
    alert_prezzi_solo_preferiti: Optional[bool] = None


class MolMensilePoint(BaseModel):
    """Un punto dello sparkline MOL: mese (1-12) e relativo MOL dell'anno corrente."""
    mese: int
    mol: float


class HomeKpiResponse(BaseModel):
    """Fotografia LIVE dei conti del periodo per la Home AI.

    Periodo = mese in corso; se ancora troppo vuoto, ultimo mese completo
    (etichetta esplicita). I numeri arrivano dalle stesse fonti della pagina
    Margini, cosi' Home e Margini non si contraddicono mai.
    """
    periodo_label: str          # es. "Giugno" oppure "Maggio"
    is_mese_in_corso: bool      # False = stiamo mostrando l'ultimo mese completo
    fatturato: float
    food_cost_pct: Optional[float]   # None se fatturato 0 (non calcolabile)
    costo_personale: float           # costo del personale (dipendenti + extra)
    spese_generali: float
    mol: float
    has_data: bool
    # Confronto col mese precedente (per le frecce ↑↓). None = non confrontabile.
    confronto_label: Optional[str] = None        # es. "vs aprile"
    fatturato_delta_pct: Optional[float] = None  # variazione % fatturato
    food_cost_delta_pp: Optional[float] = None   # variazione in PUNTI di food cost %
    personale_delta_pct: Optional[float] = None   # variazione % costo personale
    spese_delta_pct: Optional[float] = None       # variazione % spese generali
    mol_delta_pct: Optional[float] = None         # variazione % MOL
    # True = il mese ha ricavi ma ZERO costi (food + spese): MOL e food cost non
    # sono reali. La Home lo segnala e non mostra le variazioni "in meglio"
    # (MOL/food/spese) che sarebbero solo l'effetto dei costi mancanti.
    costi_mancanti: bool = False
    # Sparkline andamento MOL dei mesi dell'ANNO CORRENTE con dati (da gennaio
    # all'ultimo mese completo). Vuoto se un solo mese (niente linea da disegnare).
    mol_mensile: List[MolMensilePoint] = []
    mol_mensile_anno: Optional[int] = None       # anno di riferimento dello sparkline


# Avvisi mostrabili nel configuratore, in ordine di gerarchia. I due upload
# falliti sono "bloccati": sempre attivi (guasti tecnici). Decisione Mattia.
_CONFIG_TOPICS: List[tuple] = [
    ("upload_failed",            "Upload fatture fallito",   True,
     "Ti avviso se una fattura inviata in automatico non viene caricata."),
    ("upload_ricavi_failed",     "Upload ricavi fallito",    True,
     "Ti avviso se i tuoi incassi automatici smettono di arrivare."),
    ("price_alert",              "Alert prezzi",             False,
     "Ti segnalo quando un prodotto che pesa sulla spesa rincara oltre la tua soglia."),
    ("uncategorized_rows",       "Righe da classificare",    False,
     "Ti ricordo le righe di fattura ancora senza categoria."),
    ("fatture_mancanti",         "Nessuna fattura recente",  False,
     "Ti avviso se non risultano fatture caricate negli ultimi 30 giorni."),
    ("fatturato_mancante",       "Fatturato mancante",       False,
     "Ti ricordo di inserire il fatturato del mese, serve per food cost e MOL."),
    ("incasso_mancante",         "Incasso di ieri mancante", False,
     "Ti ricordo di inserire l'incasso del giorno prima."),
    ("costo_personale_mancante", "Costo personale mancante", False,
     "Ti ricordo di inserire il costo del lavoro del mese, serve per il MOL."),
    ("scadenza_superata",        "Scadenze",                 False,
     "Ti avviso sulle fatture fornitori scadute o in scadenza a breve."),
    ("appuntamento_imminente",   "Promemoria appuntamenti",  False,
     "Ti ricordo gli appuntamenti che hai in agenda per oggi."),
    ("coperti_anomalia",         "Anomalia coperti",         False,
     "Ti avviso quando i coperti di ieri si scostano molto dal solito."),
]

# Topic "bloccati": sempre visibili, mai disattivabili (flag True in _CONFIG_TOPICS).
_CONFIG_TOPICS_BLOCCATI = frozenset(k for (k, _l, b, _d) in _CONFIG_TOPICS if b)


def _filtra_notifiche_topic_spenti(
    rows: List[Dict[str, Any]],
    topics_disabled: Optional[List[Any]],
) -> List[Dict[str, Any]]:
    """Rimuove dalle notifiche i topic spenti nel configuratore assistente.

    Filtro unico per campanella + pagina Avvisi (get_notifiche), gemello di quello
    del briefing. I topic bloccati (_CONFIG_TOPICS_BLOCCATI: upload falliti) NON
    vengono mai filtrati, anche se finiti per errore in topics_disabled. Input
    malformato (None / non-lista) = nessun filtro (fail-open)."""
    if not isinstance(topics_disabled, list):
        return rows
    # Espande le key dello stesso tema (es. "Scadenze" -> superata + imminente),
    # stessa logica del briefing: filtro coerente ovunque.
    from services.daily_briefing_service import espandi_topic_spenti
    spenti = {t for t in espandi_topic_spenti(topics_disabled) if t not in _CONFIG_TOPICS_BLOCCATI}
    if not spenti:
        return rows
    return [r for r in rows if str(r.get("topic_key") or "") not in spenti]


@app.get(
    "/api/notifiche",
    response_model=NotificheResponse,
    summary="Lista notifiche utente (attive + non scadute)",
    tags=["Notifiche"],
    dependencies=[Depends(_verify_worker_key)],
)
def get_notifiche(
    authorization: Optional[str] = Header(None),
    include_dismissed: bool = False,
) -> NotificheResponse:
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    from services import get_supabase_client
    supabase_client = get_supabase_client()

    # Filtro per SEDE attiva: un cliente multi-sede (stesso user_id, N ristoranti)
    # non deve vedere in campanella le notifiche delle ALTRE sedi. Senza questo
    # filtro una sede a 0 fatture mostrava i tag/scadenze di un'altra sede.
    ristorante_id = _resolve_ristorante_id(user, supabase_client)

    query = (
        supabase_client.table("notification_inbox")
        .select("id,topic_key,source_type,severity,title,body,action_page,dismissed_at,expires_at,created_at")
        .eq("user_id", user_id)
        .or_("expires_at.is.null,expires_at.gt." + __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
        .order("created_at", desc=True)
        .limit(100)
    )
    if ristorante_id:
        query = query.eq("ristorante_id", ristorante_id)

    resp = query.execute()
    rows = resp.data or []

    if not include_dismissed:
        rows = [r for r in rows if not r.get("dismissed_at")]

    # Toggle del configuratore assistente: gli avvisi spenti spariscono ANCHE da
    # qui (campanella mobile + pagina Avvisi), non solo dal briefing Home. Filtro
    # unico e centralizzato: vale per ogni topic e ogni sorgente (Streamlit,
    # worker, radar). Fail-open: se la lettura preferenze va male, non nascondo
    # nulla. La logica di filtro e' in _filtra_notifiche_topic_spenti (testata).
    td: Optional[List[Any]] = None  # topics_disabled, riusato anche per i live sotto
    try:
        if ristorante_id:
            td = _get_assistant_preferences(ristorante_id, supabase_client).get("topics_disabled")
            rows = _filtra_notifiche_topic_spenti(rows, td)
    except Exception as exc:
        logger.warning("get_notifiche: filtro topics_disabled fallito: %s", exc)

    # ── Fusione con i segnali LIVE (card) ────────────────────────────────────
    # La campanella deve essere la SOMMA reale: card live (sempre fresche) +
    # notifiche minori persistite. Prima mostrava solo le persistite, divergendo
    # dalle card (es. "manca costo personale" appariva nel briefing ma non in
    # campanella; e versioni persistite stantie restavano dopo l'inserimento del
    # dato). Scartiamo dai record persistiti i topic gestiti live (così non si
    # duplicano ne' restano stantii) e aggiungiamo i live ricalcolati. Niente
    # alert prezzi qui: pesante, la campanella non deve mai essere lenta.
    if ristorante_id and not include_dismissed:
        try:
            live = _segnali_live_dati_mancanti(ristorante_id, supabase_client)
            # Topic spenti dell'utente valgono anche per i live (coerenza col briefing).
            live = _filtra_notifiche_topic_spenti(live, td)
            # I topic live sono la fonte AUTOREVOLE: rimuovi SEMPRE le persistite di
            # questi topic (anche se il live ora e' vuoto), cosi' una versione
            # stantia — es. "manca fatturato" non aggiornata dopo l'inserimento —
            # sparisce dalla campanella invece di restare fino a expires_at.
            rows = [r for r in rows if r.get("topic_key") not in _LIVE_TOPICS_DATI_MANCANTI]
            _now_iso = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
            for s in live:
                rows.append({
                    "id": s.get("id"),
                    "topic_key": s.get("topic_key"),
                    "source_type": s.get("source_type") or "live",
                    "severity": s.get("severity") or "warning",
                    "title": s.get("title") or "",
                    "body": s.get("body"),
                    "action_page": s.get("action_page"),
                    "payload": s.get("payload"),
                    "dismissed_at": None,
                    "expires_at": None,
                    "created_at": _now_iso,
                })
        except Exception as exc:
            logger.warning("get_notifiche: fusione segnali live fallita: %s", exc)

    notifiche = [
        NotificaItem(
            id=str(r["id"]),
            topic_key=r.get("topic_key"),
            source_type=r.get("source_type"),
            severity=r.get("severity") or "info",
            title=r.get("title") or "",
            body=r.get("body"),
            action_page=r.get("action_page"),
            payload=r.get("payload"),
            # Un segnale live non e' archiviabile (non ha riga in inbox): la X
            # sparirebbe ma riapparirebbe al refresh. Si chiude da solo col dato.
            dismissible=(r.get("topic_key") not in _LIVE_TOPICS_DATI_MANCANTI),
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
def dismiss_notifica(
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
# MARKETPLACE / ASSISTENZA — richieste info sui servizi (lead)
# ═══════════════════════════════════════════════════════════════════════════

class MarketplaceLeadBody(BaseModel):
    servizio_key: str = Field(..., max_length=64)
    servizio_label: str = Field(..., max_length=120)
    messaggio: str = Field("", max_length=2000)


# NB: i modelli MarketplaceLeadItem/List/StatoBody sono stati spostati nel router
# admin (services/routers/admin.py), dove sono usati a import-time nei decorator —
# tenerli qui ricreava il ciclo admin<->fastapi_worker. Restano qui solo l'endpoint
# non-admin /api/assistenza/lead e il suo body MarketplaceLeadBody.


@app.post(
    "/api/assistenza/lead",
    summary="Invia una richiesta info su un servizio del marketplace",
    tags=["Assistenza"],
    dependencies=[Depends(_verify_worker_key)],
)
def crea_marketplace_lead(
    body: MarketplaceLeadBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])

    from services import get_supabase_client
    supabase_client = get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)

    contatto_nome = (
        user.get("nome_referente")
        or user.get("nome_ristorante")
        or user.get("email")
    )

    supabase_client.table("marketplace_leads").insert({
        "user_id": user_id,
        "ristorante_id": ristorante_id,
        "servizio_key": body.servizio_key.strip(),
        "servizio_label": body.servizio_label.strip(),
        "messaggio": (body.messaggio or "").strip(),
        "contatto_email": user.get("email"),
        "contatto_nome": contatto_nome,
        "stato": "nuovo",
    }).execute()

    logger.info("marketplace_lead: servizio=%s user=%s", body.servizio_key, user_id)
    return {"ok": True}


# Nota: gli endpoint admin del marketplace (e il loro body MarketplaceLeadStatoBody)
# sono nel router admin. Qui resta solo il lead non-admin sopra.


# ═══════════════════════════════════════════════════════════════════════════
# CHAT AI — assistente conversazionale sui dati del ristorante
# ═══════════════════════════════════════════════════════════════════════════

# Limite domande/giorno per piano: rete di sicurezza sui costi OpenAI e leva
# commerciale. Visibile al cliente nelle Impostazioni (contatore).
# free = chat disattivata; base 8, plus 15, pro 30.
# Tetto costi massimo assoluto con gpt-4.1-mini: base ~$0.58, plus ~$1.08, pro ~$2.16/mese.
CHAT_LIMITI_PIANO: Dict[str, int] = {
    "free": 0,
    "base": 8,
    "plus": 15,
    "pro": 30,
}

# Modello chat configurabile via env — default gpt-4.1-mini (migliore tool calling, ~2.7x gpt-4o-mini).
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")

# Budget di tempo per il motore alert prezzi dentro il briefing Home. Oltre questa
# soglia l'alert viene saltato per non far scadere il timeout frontend (8s).
import concurrent.futures as _concurrent_futures
from concurrent.futures import TimeoutError as _cf_TimeoutError
_ALERT_PREZZI_TIMEOUT_SEC = float(os.getenv("ALERT_PREZZI_TIMEOUT_SEC", "4.0"))
# Executor condiviso: i thread "fuggiti" (alert lento) finiscono in background
# senza bloccare la risposta. max_workers limita l'accumulo sotto carico.
_ALERT_PREZZI_EXECUTOR = _concurrent_futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="alert-prezzi",
)


def _chat_limite_per_piano(piano: Optional[str]) -> int:
    """Domande/giorno consentite per il piano del cliente.

    Default = limite "base" (8) per piani non riconosciuti: prima era 10, un
    valore fantasma non presente in CHAT_LIMITI_PIANO e superiore a base.
    """
    return CHAT_LIMITI_PIANO.get((piano or "base").lower().strip(), CHAT_LIMITI_PIANO["base"])


def _chat_limite_pool_gruppo(user: Dict[str, Any], supabase_client) -> int:
    """Limite chat del POOL di gruppo = SOMMA dei limiti effettivi di ogni sede.

    Modalità catena: un solo contatore condiviso, niente piano-catena. Ogni sede
    contribuisce col limite del SUO piano (es. 3 Base 8 + 1 Pro 30 = 54), non
    n×costante (i piani possono differire). Le sedi 'free' (limite 0) non
    contribuiscono. Fallback prudente al limite della sede attiva se la lettura
    sedi fallisce (non blocca la chat di gruppo)."""
    try:
        sedi = (
            supabase_client.table("ristoranti")
            .select("piano")
            .eq("user_id", str(user["id"]))
            .eq("attivo", True)
            .execute()
        ).data or []
        if sedi:
            # Risolve il piano per sede col fallback corretto (sede.piano →
            # users.piano → 'base'), mai users.piano diretto.
            tot = 0
            for s in sedi:
                piano_sede = (s.get("piano") or user.get("piano") or "base")
                tot += _chat_limite_per_piano(piano_sede)
            return tot
    except Exception as exc:
        logger.warning("chat: calcolo pool gruppo fallito, fallback sede: %s", exc)
    return _chat_limite_per_piano(_resolve_piano_effettivo(user, supabase_client))


def _chat_domande_oggi(ristorante_id: Optional[str], user_id: str, supabase_client) -> int:
    """Conta le domande alla chat fatte oggi (UTC) per il ristorante (o utente)."""
    from datetime import datetime as _dt, timezone as _tz
    inizio = _dt.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        q = (
            supabase_client.table("chat_usage_log")
            .select("id", count="exact")
            .gte("created_at", inizio)
        )
        if ristorante_id:
            q = q.eq("ristorante_id", ristorante_id)
        else:
            q = q.eq("user_id", user_id)
        return int(q.execute().count or 0)
    except Exception as exc:
        logger.warning("chat: conteggio domande oggi fallito: %s", exc)
        return 0


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, max_length=20)
    # "catena" = chat in modalità catena (/catena): tool di gruppo, pool AI unico
    # (SUM limiti effettivi sedi). Default "sede" = chat del singolo PV, invariata.
    contesto: str = Field("sede", pattern="^(sede|catena)$")


class ChatResponse(BaseModel):
    reply: str
    # Quota giornaliera: dopo ogni risposta il widget mostra quante domande
    # restano oggi, cosi' il limite non e' una sorpresa (prima si scopriva solo
    # sbattendo contro il 429). domande_oggi = quante gia' consumate oggi.
    domande_oggi: int = 0
    limite_giorno: int = 0


def _build_chat_system_prompt(
    user: Dict[str, Any], supabase_client, authorization: Optional[str],
    ristorante_id: Optional[str] = None,
) -> str:
    """Costruisce il system prompt con i dati freschi del ristorante.

    Usa ESATTAMENTE gli stessi KPI della Home (`home_kpi`): MOL, fatturato,
    food cost %, costo personale, spese — cosi' la chat dice gli stessi numeri
    che il cliente vede a schermo. Aggiunge il dettaglio costi per categoria e
    fornitore (per domande tipo "quanto ho speso in birra").
    """
    nome = user.get("nome_ristorante") or user.get("email", "")
    referente = user.get("nome_referente") or ""

    kpi_testo = ""

    # 1) KPI Home — stessa fonte, stessi numeri (margini_mensili + costi)
    try:
        kpi = home_kpi(authorization)
        if kpi.has_data:
            fc = f"{kpi.food_cost_pct:.1f}%" if kpi.food_cost_pct is not None else "n/d"
            kpi_testo += (
                f"\n\n## Conti del ristorante — {kpi.periodo_label} "
                f"(ultimo mese completo)\n"
                f"- Fatturato: €{kpi.fatturato:,.2f}\n"
                f"- Food cost: {fc}\n"
                f"- Costo personale: €{kpi.costo_personale:,.2f}\n"
                f"- Spese generali: €{kpi.spese_generali:,.2f}\n"
                f"- MOL (margine operativo lordo): €{kpi.mol:,.2f}\n"
            )
            if kpi.confronto_label:
                kpi_testo += f"  (confronto {kpi.confronto_label})\n"
    except Exception as exc:
        logger.warning("chat: KPI Home non disponibili: %s", exc)

    # 2) Dettaglio costi per categoria/fornitore dalle fatture (ultimi 90 gg)
    # Serve solo per le top-list nel prompt (food cost a colpo d'occhio, fornitore
    # piu' caro): NON carichiamo 'descrizione' ne' aggreghiamo per prodotto — quel
    # dettaglio lo da' il tool query_costi su richiesta. Senza descrizione e con
    # limit ridotto la query e' molto piu' leggera (era 3000 righe ad ogni domanda).
    try:
        from datetime import date as _date, timedelta as _td
        user_id = str(user["id"])
        da = (_date.today() - _td(days=90)).isoformat()
        q = (
            supabase_client.table("fatture")
            .select("totale_riga,categoria,fornitore")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .gte("data_documento", da)
        )
        if ristorante_id:
            q = q.eq("ristorante_id", ristorante_id)
        q = (
            q
            .limit(1500)
            .execute()
        )
        righe = q.data or []
        if righe:
            per_cat: Dict[str, float] = {}
            per_forn: Dict[str, float] = {}
            for r in righe:
                v = float(r.get("totale_riga") or 0)
                cat = (r.get("categoria") or "Altro").strip()
                forn = (r.get("fornitore") or "Sconosciuto").strip()
                per_cat[cat] = per_cat.get(cat, 0) + v
                per_forn[forn] = per_forn.get(forn, 0) + v
            top_cat = sorted(per_cat.items(), key=lambda x: x[1], reverse=True)[:5]
            top_forn = sorted(per_forn.items(), key=lambda x: x[1], reverse=True)[:5]

            kpi_testo += "\n## Costi per categoria (ultimi 90 giorni)\n"
            for cat, v in top_cat:
                kpi_testo += f"- {cat}: €{v:,.2f}\n"
            kpi_testo += "\n## Fornitori principali per spesa (ultimi 90 giorni)\n"
            for forn, v in top_forn:
                kpi_testo += f"- {forn}: €{v:,.2f}\n"
    except Exception as exc:
        logger.warning("chat: dettaglio fatture non disponibile: %s", exc)

    # 3) Agenda di oggi — solo se l'utente ha il flag 'agenda'. Inietta gli
    # appuntamenti odierni cosi' la chat risponde a "cosa ho oggi" senza tool-call.
    pagine = _normalize_pagine(user.get("pagine_abilitate"))
    if pagine is None or "agenda" in set(pagine):
        try:
            from datetime import date as _date_ag
            oggi_ag = _date_ag.today().isoformat()
            if ristorante_id:
                eventi = (
                    supabase_client.table("diario_eventi")
                    .select("titolo,ora_inizio")
                    .eq("ristorante_id", ristorante_id)
                    .eq("data_evento", oggi_ag)
                    .order("ora_inizio", nullsfirst=True)
                    .limit(20)
                    .execute()
                    .data or []
                )
                if eventi:
                    kpi_testo += "\n## Appuntamenti di oggi (agenda)\n"
                    for e in eventi:
                        ora = (e.get("ora_inizio") or "")[:5]
                        titolo = (e.get("titolo") or "").strip()
                        kpi_testo += f"- {ora + ' — ' if ora else ''}{titolo}\n"
        except Exception as exc:
            logger.warning("chat: agenda di oggi non disponibile: %s", exc)

    if not kpi_testo:
        kpi_testo = "\n\n(Nessun dato di costo o margine ancora registrato.)"

    # Data di oggi + intervallo dati: SENZA questo il modello usa il suo knowledge
    # cutoff (2024) come anno di default e cerca sistematicamente nell'anno
    # sbagliato -> "non risulta nulla" anche quando il dato c'e'.
    from datetime import date as _date_today
    oggi = _date_today.today()
    _MESI_NOMI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    oggi_str = f"{oggi.day} {_MESI_NOMI[oggi.month]} {oggi.year}"

    range_dati = ""
    try:
        user_id = str(user["id"])
        q_min = (
            supabase_client.table("fatture").select("data_documento")
            .eq("user_id", user_id).is_("deleted_at", "null")
            .order("data_documento", desc=False).limit(1)
        )
        q_max = (
            supabase_client.table("fatture").select("data_documento")
            .eq("user_id", user_id).is_("deleted_at", "null")
            .order("data_documento", desc=True).limit(1)
        )
        if ristorante_id:
            q_min = q_min.eq("ristorante_id", ristorante_id)
            q_max = q_max.eq("ristorante_id", ristorante_id)
        dmin = (q_min.execute().data or [{}])
        dmax = (q_max.execute().data or [{}])
        d0 = dmin[0].get("data_documento") if dmin else None
        d1 = dmax[0].get("data_documento") if dmax else None
        if d0 and d1:
            range_dati = f"Le fatture nel sistema vanno dal {d0} al {d1}."
    except Exception as exc:
        logger.warning("chat: range date non disponibile: %s", exc)

    sistema = f"""Sei l'assistente AI di ONEFLUX, integrato nel gestionale del ristorante "{nome}".
{f"Stai parlando con {referente}." if referente else ""}

## Data e periodo (IMPORTANTE)
Oggi e' {oggi_str}. L'anno corrente e' {oggi.year}. {range_dati}
Quando l'utente non specifica l'anno, usa SEMPRE l'anno corrente ({oggi.year}) — MAI un anno passato.
"Ultimo acquisto", "ultima fattura", "recente" NON sono un periodo: non filtrare per mese/anno, cerca il piu' recente in assoluto.
Non inventare anni: se dopo aver usato l'anno corrente non trovi nulla, dillo e proponi di cercare in tutto lo storico.
Il MESE CORRENTE e' quasi sempre incompleto: i ristoranti caricano le fatture a fine mese o in ritardo. Se cerchi "questo mese" e lo strumento risponde vuoto (o segnala "mese_non_ancora_caricato"), NON dire "non hai speso nulla": spiega che il mese in corso non e' ancora caricato e proponi l'ultimo mese disponibile.

Rispondi SOLO a domande sui dati del ristorante: costi, fornitori, food cost, margini, MOL, fatture, scadenze.
Per argomenti non pertinenti (ricette generiche, notizie, argomenti personali) rispondi educatamente che puoi aiutare solo sulla gestione del locale.

Tono: diretto, concreto, da collega esperto in F&B — non da chatbot generico. Risposte brevi (2-5 righe al massimo).
Importi sempre in euro con 2 decimali. Usa i dati qui sotto: sono gli stessi che il cliente vede nella sua schermata Home. Se un dato c'e' qui, NON dire che non hai dati.
Food cost a "0.0%" o "n/d" NON e' un valore reale: significa quasi sempre che manca il fatturato del mese (i ricavi non sono ancora stati inseriti), non che il cibo costi zero. In quel caso spiega il perche' in una riga ("il food cost non e' calcolabile finche' non inserisci i ricavi del mese") invece di riportare lo zero come se fosse un dato.

Regole per gli strumenti:
- Per qualsiasi numero specifico (categoria, fornitore, prodotto, periodo preciso) usa SEMPRE lo strumento giusto — non rispondere a memoria.
- Per domande generiche sull'andamento ("com'è il mio food cost?", "sto guadagnando?") usa i dati qui sotto.
- query_costi cerca in automatico tra categorie, fornitori e prodotti: se cerchi "birra" e non c'e' come categoria, prova anche come prodotto. Fidati del risultato dello strumento.
- Per CONFRONTARE due periodi ("ho speso più a marzo o ad aprile?", "quest'anno vs l'anno scorso") chiama query_costi DUE volte (una per periodo) e confronta tu i totali nella risposta.
- Per l'andamento del PREZZO di un prodotto nel tempo ("la mozzarella è aumentata?", "il prezzo di X è salito?") usa trend_prezzo, NON query_costi.
- Per "l'ultimo acquisto / l'ultima fattura / cosa ho comprato di recente" usa ultimi_acquisti.
- Per appuntamenti e impegni in agenda ("cosa ho oggi", "appuntamenti di questa settimana") usa query_appuntamenti.
- Per coperti e scontrino medio ("quanti coperti", "scontrino medio", "quante persone servo", "giorno più pieno") usa query_coperti. Il coperto è una persona servita; lo scontrino medio è quanto spende in media a testa. Se i coperti risultano None/assenti, spiega che il dato non è ancora arrivato dal gestionale o non è stato inserito, NON dire che sono zero.
- I dati qui sotto coprono periodi diversi (KPI = ultimo mese completo; categorie/fornitori = ultimi 90 giorni): non mescolarli.{kpi_testo}"""

    return sistema


# ─── Chat modalità CATENA: doppia competenza (tool di gruppo) ──────────────

def _build_chat_system_prompt_catena(
    user: Dict[str, Any], supabase_client, authorization: Optional[str]
) -> str:
    """System prompt per la chat in modalità catena: parla del GRUPPO, non del
    singolo PV. Inietta la sintesi di gruppo (KPI + ranking) come contesto, gli
    stessi numeri che il cliente vede su /catena."""
    from datetime import date as _date_today
    oggi = _date_today.today()
    referente = user.get("nome_referente") or ""

    contesto = ""
    nome_gruppo = "il gruppo"
    try:
        ov = _gruppo_router_mod().gruppo_overview(authorization)
        nome_gruppo = ov.nome_gruppo
        contesto += (
            f"\n\n## Sintesi della catena «{ov.nome_gruppo}» ({ov.num_pv} punti vendita, {ov.periodo_label})\n"
            f"- Fatturato gruppo: €{ov.kpi.fatturato:,.2f}\n"
            f"- Margine medio: {ov.kpi.margine_medio_perc:.1f}%\n"
            f"- Spesa fornitori: €{ov.kpi.spesa_fornitori:,.2f}\n"
            f"- Salute del gruppo: {ov.salute_indice}/100\n"
            "\n### Ranking punti vendita (per margine %)\n"
        )
        for r in ov.ranking:
            if r.dati_incompleti:
                contesto += f"- {r.nome}: dati incompleti\n"
            else:
                contesto += f"- {r.nome}: margine {r.margine_perc:.1f}%, fatturato €{r.fatturato:,.2f}\n"
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("chat catena: contesto overview non disponibile: %s", exc)

    return f"""Sei l'assistente AI di ONEFLUX in MODALITÀ CATENA: parli del GRUPPO di ristoranti «{nome_gruppo}», non di un singolo locale.
{f"Stai parlando con {referente}." if referente else ""}

## Data
Oggi è {oggi.day}/{oggi.month}/{oggi.year}. L'anno corrente è {oggi.year}.

Rispondi SOLO a domande sul confronto e l'andamento dei punti vendita del gruppo: chi va meglio/peggio, margini, spesa fornitori, coperti, segnalazioni. Per domande sul singolo locale invita ad aprire quel punto vendita.

Tono: diretto, concreto, da direttore di catena. Risposte brevi (2-5 righe). Importi in euro con 2 decimali. Confronta SEMPRE per percentuali/incidenze quando paragoni PV di taglia diversa (i valori assoluti in € ingannano).

Regole strumenti:
- Per il quadro d'insieme (KPI, ranking, salute) usa i dati qui sotto o gruppo_overview.
- Per "quale PV ha il margine/scontrino/coperti migliore o peggiore" usa gruppo_margini_coperti.
- Per "dove si spende di più per categoria/fornitore" usa gruppo_spesa.
- Per "cosa c'è da vedere/sistemare" usa gruppo_segnali.
- Non inventare numeri: se uno strumento torna vuoto, dillo.{contesto}"""


_CHAT_TOOLS_GRUPPO = [
    {
        "type": "function",
        "function": {
            "name": "gruppo_overview",
            "description": (
                "Quadro d'insieme della catena: fatturato di gruppo, margine medio, "
                "spesa fornitori, salute e ranking dei punti vendita per margine %. "
                "Usalo per 'come va il gruppo', 'qual è il quadro generale'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gruppo_margini_coperti",
            "description": (
                "Confronto per punto vendita di margine %, fatturato, coperti, scontrino "
                "medio e € materia prima per coperto. Usalo per 'quale PV ha il margine "
                "peggiore', 'chi ha lo scontrino più alto', 'dove costa di più la materia "
                "prima per coperto'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gruppo_spesa",
            "description": (
                "Spesa per punto vendita ripartita per categoria o fornitore. Usalo per "
                "'dove si spende di più in pesce', 'quale PV spende di più dal fornitore X', "
                "'come è distribuita la spesa fra i locali'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dimensione": {
                        "type": "string",
                        "enum": ["categoria", "fornitore"],
                        "description": "Raggruppa per 'categoria' (default) o 'fornitore'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gruppo_segnali",
            "description": (
                "Le segnalazioni aperte della catena (margine in calo, prezzi sopra la "
                "media, ricavi mancanti) con il punto vendita coinvolto. Usalo per 'cosa "
                "c'è da vedere', 'ci sono problemi', 'su quali locali devo intervenire'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _gruppo_router_mod():
    import services.routers.gruppo as g
    return g


def _chat_esegui_tool_gruppo(nome: str, args: Dict[str, Any], authorization: Optional[str]) -> Dict[str, Any]:
    """Dispatcher dei tool di gruppo: chiama gli endpoint /api/gruppo/* (sola
    lettura) e ritorna dict serializzabili. Stesso scope/auth della chat."""
    g = _gruppo_router_mod()
    try:
        if nome == "gruppo_overview":
            return g.gruppo_overview(authorization).model_dump()
        if nome == "gruppo_margini_coperti":
            return g.gruppo_margini_coperti(authorization).model_dump()
        if nome == "gruppo_spesa":
            dim = args.get("dimensione") if args.get("dimensione") in ("categoria", "fornitore") else "categoria"
            return g.gruppo_spesa_pivot(dimensione=dim, authorization=authorization).model_dump()
        if nome == "gruppo_segnali":
            return g.gruppo_segnali(authorization=authorization).model_dump()
    except HTTPException as exc:
        return {"errore": exc.detail}
    except Exception as exc:
        logger.warning("chat catena: tool %s fallito: %s", nome, exc)
        return {"errore": "strumento non disponibile al momento"}
    return {"errore": f"strumento sconosciuto: {nome}"}


def _chat_loop_openai(client, messages, tools, esegui_tool):
    """Loop di tool-calling OpenAI condiviso. Ritorna (reply, prompt_tok, completion_tok).
    Max 3 round, 1 retry su errori transienti. Usato dalla chat catena (la chat
    di sede mantiene il suo loop inline, invariato)."""
    import json as _json
    from openai import APITimeoutError as _OAITimeout, RateLimitError as _OAIRateLimit, APIError as _OAIError
    p_tok = 0
    c_tok = 0
    reply = ""
    try:
        for _ in range(3):
            for tentativo in range(2):
                try:
                    resp = client.chat.completions.create(
                        model=CHAT_MODEL, messages=messages, tools=tools,
                        max_tokens=900, temperature=0.3,
                    )
                    break
                except _OAITimeout:
                    if tentativo == 0:
                        continue
                    raise HTTPException(status_code=504, detail="L'assistente ha impiegato troppo tempo. Riprova.")
                except _OAIRateLimit:
                    raise HTTPException(status_code=429, detail="Servizio temporaneamente sovraccarico. Riprova tra qualche secondo.")
                except _OAIError as exc:
                    if tentativo == 0 and getattr(exc, "status_code", 0) >= 500:
                        continue
                    raise
            if resp.usage:
                p_tok += resp.usage.prompt_tokens or 0
                c_tok += resp.usage.completion_tokens or 0
            msg = resp.choices[0].message
            if not msg.tool_calls:
                reply = msg.content or ""
                break
            messages.append({
                "role": "assistant", "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = _json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                risultato = esegui_tool(tc.function.name, args)
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": _json.dumps(risultato, ensure_ascii=False, default=str),
                })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("chat _chat_loop_openai: errore inatteso: %s", exc)
        raise HTTPException(status_code=502, detail="Errore nella comunicazione con l'assistente. Riprova.")
    return reply, p_tok, c_tok


# Mesi italiani -> numero, per interpretare i periodi richiesti via chat.
_MESI_MAP = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}


def _chat_query_costi(
    user_id: str,
    supabase_client,
    mese: Optional[int] = None,
    anno: Optional[int] = None,
    categoria: Optional[str] = None,
    fornitore: Optional[str] = None,
    prodotto: Optional[str] = None,
    ristorante_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Interroga i costi fatturati con filtri opzionali (per il tool della chat).

    Ricerca TOLLERANTE: un termine generico (categoria/prodotto) viene cercato
    sia tra le categorie sia tra i nomi prodotto, e con fallback singolare/
    plurale. Cosi' "birra" trova la categoria "BIRRE" anche se l'utente non usa
    la parola esatta del DB (era il difetto che faceva dire "non risulta").
    Scoping per ristorante_id coerente con Margini/Prezzi.
    """
    from calendar import monthrange

    def _base_query():
        q = (
            supabase_client.table("fatture")
            .select("totale_riga,categoria,fornitore,descrizione,data_documento")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
        )
        if ristorante_id:
            q = q.eq("ristorante_id", ristorante_id)
        if mese and anno:
            ultimo = monthrange(anno, mese)[1]
            q = q.gte("data_documento", f"{anno}-{mese:02d}-01")
            q = q.lte("data_documento", f"{anno}-{mese:02d}-{ultimo:02d}")
        elif anno:
            q = q.gte("data_documento", f"{anno}-01-01").lte("data_documento", f"{anno}-12-31")
        return q

    if mese and anno:
        periodo_label = f"{[k for k, v in _MESI_MAP.items() if v == mese][0]} {anno}"
    elif anno:
        periodo_label = str(anno)
    else:
        periodo_label = "tutto lo storico"

    # Varianti del termine per tollerare singolare/plurale (birra<->birre,
    # pomodoro<->pomodori). Niente librerie: bastano poche desinenze italiane.
    def _varianti(term: str) -> List[str]:
        t = (term or "").strip()
        if not t:
            return []
        out = [t]
        base = t
        for suf in ("e", "i", "o", "a"):
            if t.lower().endswith(suf) and len(t) > 3:
                base = t[:-1]
                break
        if base != t:
            out.append(base)  # radice senza desinenza: ilike %radic% prende tutte le forme
        return out

    # Il termine "generico" che l'utente associa a categoria o prodotto.
    termine = categoria or prodotto

    def _esegui(filtro_fornitore: Optional[str], termine_su: Optional[str], termine_val: Optional[str]):
        q = _base_query()
        if filtro_fornitore:
            q = q.ilike("fornitore", f"%{filtro_fornitore}%")
        if termine_su and termine_val:
            if termine_su == "categoria":
                q = q.ilike("categoria", f"%{termine_val}%")
            elif termine_su == "prodotto":
                q = q.ilike("descrizione", f"%{termine_val}%")
            elif termine_su == "ovunque":
                # categoria OR descrizione: cattura sia "birra" categoria che prodotto
                q = q.or_(f"categoria.ilike.%{termine_val}%,descrizione.ilike.%{termine_val}%")
        # Ordina per data desc: se il limite tronca su clienti con molte righe,
        # conserva le piu' recenti invece di un taglio arbitrario.
        return (q.order("data_documento", desc=True).limit(5000).execute().data) or []

    righe: List[Dict[str, Any]] = []
    trovato_come = None  # "categoria" | "prodotto" | None

    if termine:
        # 1) prova esatta sul campo indicato; 2) ovunque; 3) varianti ovunque.
        campo_pref = "categoria" if categoria else "prodotto"
        for term_val in _varianti(termine):
            righe = _esegui(fornitore, campo_pref, term_val)
            if righe:
                trovato_come = campo_pref
                break
            righe = _esegui(fornitore, "ovunque", term_val)
            if righe:
                # capisce se ha matchato la categoria o il prodotto
                cat_match = any(term_val.lower() in str(r.get("categoria") or "").lower() for r in righe)
                trovato_come = "categoria" if cat_match else "prodotto"
                break
    else:
        righe = _esegui(fornitore, None, None)

    totale = sum(float(r.get("totale_riga") or 0) for r in righe)

    # Dettaglio: se cerca un termine specifico, raggruppa per prodotto;
    # altrimenti per categoria.
    dettaglio: Dict[str, float] = {}
    chiave = "descrizione" if (termine or fornitore) else "categoria"
    for r in righe:
        k = (r.get(chiave) or "?").strip()
        dettaglio[k] = dettaglio.get(k, 0) + float(r.get("totale_riga") or 0)
    top = sorted(dettaglio.items(), key=lambda x: x[1], reverse=True)[:15]

    risultato = {
        "periodo": periodo_label,
        "totale": round(totale, 2),
        "righe_trovate": len(righe),
        "trovato_come": trovato_come,
        "dettaglio": [{"voce": k, "spesa": round(v, 2)} for k, v in top],
    }

    # "Questo mese" e' quasi sempre vuoto: i ristoranti caricano le fatture a fine
    # mese o in ritardo. Se l'utente ha chiesto il mese corrente (o futuro) e non
    # c'e' nulla, NON e' un "non risulta": e' che il mese non e' ancora caricato.
    # Segnaliamo all'AI l'ultimo mese con acquisti, cosi' propone quello invece di
    # rispondere seccamente "non hai speso nulla".
    if not righe and mese and anno:
        from datetime import date as _date_q
        _oggi_q = _date_q.today()
        if (anno, mese) >= (_oggi_q.year, _oggi_q.month):
            q_ult = (
                supabase_client.table("fatture")
                .select("data_documento")
                .eq("user_id", user_id)
                .is_("deleted_at", "null")
            )
            if ristorante_id:
                q_ult = q_ult.eq("ristorante_id", ristorante_id)
            ult = (q_ult.order("data_documento", desc=True).limit(1).execute().data) or []
            ultima_data = ult[0].get("data_documento") if ult else None
            risultato["mese_non_ancora_caricato"] = True
            risultato["ultima_fattura_caricata"] = ultima_data
            risultato["suggerimento"] = (
                "Il mese richiesto e' quello corrente e non risulta ancora caricato "
                "(le fatture arrivano a fine mese/in ritardo). Proponi all'utente di "
                "guardare l'ultimo mese effettivamente disponibile invece di dire che "
                "non ha speso nulla."
            )

    return risultato


def _chat_query_scadenze(user: Dict[str, Any], supabase_client, solo_da_pagare: bool = True) -> Dict[str, Any]:
    """Scadenze del ristorante (per il tool della chat). Riusa la stessa fonte
    della pagina Gestione Fatture."""
    from services.documenti_service import get_documenti_scadenziario
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        return {"scadenze": [], "totale_da_pagare": 0.0}
    docs = get_documenti_scadenziario(str(user["id"]), ristorante_id)

    voci = []
    totale = 0.0
    for d in docs:
        if solo_da_pagare and d.get("pagata"):
            continue
        imp = float(d.get("totale_documento") or 0)
        if not d.get("pagata"):
            totale += imp
        voci.append({
            "fornitore": d.get("fornitore") or "?",
            "importo": round(imp, 2),
            "scadenza": d.get("scadenza_effettiva"),
            "pagata": bool(d.get("pagata")),
        })
    # Ordina per scadenza (le piu' vicine prima)
    voci.sort(key=lambda x: x.get("scadenza") or "9999")
    return {"scadenze": voci[:30], "totale_da_pagare": round(totale, 2)}


def _chat_query_appuntamenti(
    user: Dict[str, Any], supabase_client,
    ristorante_id: Optional[str] = None,
    da: Optional[str] = None, a: Optional[str] = None,
) -> Dict[str, Any]:
    """Appuntamenti dell'Agenda (diario_eventi) in un intervallo di date.

    Sola lettura. Default: da oggi ai prossimi 7 giorni — copre 'oggi' e 'questa
    settimana' senza affollare. Fonte = stessa tabella della vista Appuntamenti."""
    from datetime import date as _date, timedelta as _td
    if not ristorante_id:
        return {"appuntamenti": [], "da": da, "a": a}
    oggi = _date.today()
    d_da = da or oggi.isoformat()
    d_a = a or (oggi + _td(days=7)).isoformat()
    righe = (
        supabase_client.table("diario_eventi")
        .select("data_evento,titolo,descrizione,ora_inizio,ora_fine")
        .eq("ristorante_id", ristorante_id)
        .gte("data_evento", d_da)
        .lte("data_evento", d_a)
        .order("data_evento")
        .order("ora_inizio", nullsfirst=True)
        .limit(50)
        .execute()
        .data or []
    )
    appuntamenti = [{
        "data": r.get("data_evento"),
        "titolo": (r.get("titolo") or "").strip(),
        "ora": r.get("ora_inizio"),
        "descrizione": (r.get("descrizione") or "").strip() or None,
    } for r in righe]
    return {"appuntamenti": appuntamenti, "da": d_da, "a": d_a, "trovati": len(appuntamenti)}


def _chat_ultimi_acquisti(
    user_id: str,
    supabase_client,
    prodotto: Optional[str] = None,
    fornitore: Optional[str] = None,
    limite: int = 5,
    ristorante_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ultime righe d'acquisto in ordine cronologico (per il tool della chat).

    Risponde a "qual e' l'ultimo acquisto / l'ultima fattura / l'ultima volta
    che ho comprato X". Senza questo tool l'AI ripiegava su query_costi
    (aggregati) e non riusciva a dire data+prodotto+fornitore dell'ultima riga.
    """
    q = (
        supabase_client.table("fatture")
        .select("data_documento,descrizione,fornitore,categoria,totale_riga,quantita,unita_misura")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
    )
    if ristorante_id:
        q = q.eq("ristorante_id", ristorante_id)
    if prodotto:
        q = q.or_(f"descrizione.ilike.%{prodotto}%,categoria.ilike.%{prodotto}%")
    if fornitore:
        q = q.ilike("fornitore", f"%{fornitore}%")

    lim = max(1, min(int(limite or 5), 15))
    righe = (
        q.order("data_documento", desc=True).limit(lim).execute().data
    ) or []

    acquisti = [{
        "data": r.get("data_documento"),
        "prodotto": (r.get("descrizione") or "").strip(),
        "fornitore": (r.get("fornitore") or "").strip(),
        "categoria": (r.get("categoria") or "").strip(),
        "importo": round(float(r.get("totale_riga") or 0), 2),
        "quantita": r.get("quantita"),
        "unita": (r.get("unita_misura") or "").strip(),
    } for r in righe]

    return {"acquisti": acquisti, "trovati": len(acquisti)}


def _chat_trend_prezzo(
    user_id: str,
    supabase_client,
    prodotto: str,
    ristorante_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Andamento del prezzo unitario di un prodotto, mese per mese.

    Risponde a "la mozzarella e' aumentata?", "il prezzo del X e' salito?".
    Prezzo medio ponderato per mese (somma totale_riga / somma quantita') sugli
    ultimi 6 mesi con acquisti; confronta il primo mese utile con l'ultimo.
    """
    from datetime import date as _date, timedelta as _td

    if not prodotto or not prodotto.strip():
        return {"prodotto": prodotto, "punti": [], "variazione_pct": None}

    da = (_date.today() - _td(days=210)).isoformat()  # ~7 mesi di finestra
    q = (
        supabase_client.table("fatture")
        .select("descrizione,fornitore,prezzo_unitario,quantita,totale_riga,data_documento")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .gt("prezzo_unitario", 0)
        .gte("data_documento", da)
    )
    if ristorante_id:
        q = q.eq("ristorante_id", ristorante_id)
    # Cerca su descrizione OR categoria (tollerante come query_costi)
    q = q.or_(f"descrizione.ilike.%{prodotto}%,categoria.ilike.%{prodotto}%")
    # Ordina per data desc: il trend usa la finestra ~7 mesi, se tronca conserva
    # i mesi piu' recenti (quelli che servono al confronto primo<->ultimo).
    righe = (q.order("data_documento", desc=True).limit(5000).execute().data) or []
    if not righe:
        return {"prodotto": prodotto, "punti": [], "variazione_pct": None}

    # Aggrega per mese: prezzo medio ponderato sulla quantita'.
    per_mese: Dict[str, Dict[str, float]] = {}
    nomi_prod: set = set()
    for r in righe:
        data = str(r.get("data_documento") or "")
        if len(data) < 7:
            continue
        mese = data[:7]  # YYYY-MM
        prezzo = float(r.get("prezzo_unitario") or 0)
        qta = float(r.get("quantita") or 0)
        tot = float(r.get("totale_riga") or 0)
        if prezzo <= 0:
            continue
        agg = per_mese.setdefault(mese, {"somma_tot": 0.0, "somma_qta": 0.0, "somma_prezzi": 0.0, "n": 0.0})
        nomi_prod.add((r.get("descrizione") or "").strip())
        if qta > 0 and tot > 0:
            agg["somma_tot"] += tot
            agg["somma_qta"] += qta
        # fallback semplice se manca quantita': media aritmetica dei prezzi
        agg["somma_prezzi"] += prezzo
        agg["n"] += 1

    punti = []
    for mese in sorted(per_mese.keys()):
        a = per_mese[mese]
        if a["somma_qta"] > 0:
            prezzo_medio = a["somma_tot"] / a["somma_qta"]
        elif a["n"] > 0:
            prezzo_medio = a["somma_prezzi"] / a["n"]
        else:
            continue
        punti.append({"mese": mese, "prezzo_medio": round(prezzo_medio, 4)})

    variazione_pct = None
    if len(punti) >= 2:
        p0 = punti[0]["prezzo_medio"]
        p1 = punti[-1]["prezzo_medio"]
        if p0 > 0:
            variazione_pct = round((p1 - p0) / p0 * 100.0, 1)

    return {
        "prodotto": prodotto,
        "prodotti_trovati": sorted(nomi_prod)[:5],
        "punti": punti,
        "variazione_pct": variazione_pct,
        "nota": "prezzo unitario medio ponderato per mese" if punti else "nessun acquisto nel periodo",
    }


def _chat_query_margini(user: Dict[str, Any], supabase_client, authorization: Optional[str]) -> Dict[str, Any]:
    """Andamento margini/MOL degli ultimi mesi (per il tool della chat).
    Riusa margine_service, stessa fonte della pagina Margini e della Home."""
    from datetime import date as _date
    user_id = str(user["id"])
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        return {"mesi": []}

    from services.margine_service import carica_margini_anno, calcola_costi_automatici_per_anno_sql
    _MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
             "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    oggi = _oggi_rome()
    cache_anni: Dict[int, Any] = {}

    def _anno(a: int):
        if a not in cache_anni:
            try:
                m = carica_margini_anno(user_id, ristorante_id, a)
                fb, sp = calcola_costi_automatici_per_anno_sql(user_id, ristorante_id, a)
                cache_anni[a] = (m, fb, sp)
            except Exception:
                cache_anni[a] = ({}, {}, {})
        return cache_anni[a]

    risultati = []
    mm, aa = oggi.month, oggi.year
    for _ in range(6):
        margini, fb, sp = _anno(aa)
        k = _kpi_periodo(margini, fb, sp, mm)
        if k["has_data"]:
            risultati.append({
                "mese": f"{_MESI[mm]} {aa}",
                "fatturato": k["fatturato"],
                "food_cost_pct": k["food_cost_pct"],
                "mol": k["mol"],
            })
        mm -= 1
        if mm == 0:
            mm, aa = 12, aa - 1
    return {"mesi": risultati}


def _chat_query_coperti(user: Dict[str, Any], supabase_client, authorization: Optional[str]) -> Dict[str, Any]:
    """Coperti e scontrino medio degli ultimi mesi (per il tool della chat).
    Riusa l'endpoint coperti-analisi, stessa fonte del tab Coperti."""
    from datetime import date as _date
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        return {"mesi": [], "nota": "Nessun ristorante associato."}

    oggi = _oggi_rome()
    # Ultimi ~6 mesi: dal 1° di 5 mesi fa a oggi.
    aa, mm = oggi.year, oggi.month - 5
    while mm <= 0:
        mm += 12
        aa -= 1
    data_da = f"{aa:04d}-{mm:02d}-01"
    data_a = oggi.isoformat()
    try:
        from services.routers.ricavi import get_coperti_analisi
        resp = get_coperti_analisi(data_da=data_da, data_a=data_a, authorization=authorization)
    except Exception:
        return {"mesi": [], "nota": "Dati coperti non disponibili."}

    mesi = [
        {
            "mese": m.label,
            "coperti": m.coperti,
            "scontrino_medio_netto": m.scontrino_medio_netto,
            "scontrino_medio_lordo": m.scontrino_medio_lordo,
        }
        for m in resp.mesi if m.coperti
    ]
    k = resp.kpi
    return {
        "mesi": mesi,
        "coperti_totali_periodo": k.coperti_totali,
        "coperti_medi_giorno": k.coperti_medi_giorno,
        "scontrino_medio_netto": k.scontrino_medio_netto,
        "scontrino_medio_lordo": k.scontrino_medio_lordo,
        "giorno_piu_pieno": (
            {"data": k.giorno_top.data, "coperti": k.giorno_top.coperti} if k.giorno_top else None
        ),
        "nota": "Coperti = persone servite (somma di tutti i documenti). None = dato non disponibile per quel mese." if not mesi else None,
    }


def _chat_confronto_prezzi(
    user: Dict[str, Any], supabase_client, prodotto: str,
    ristorante_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Confronta il prezzo unitario di un prodotto tra i fornitori (ultimi 180gg).
    Cuore di ONEFLUX: trova chi lo fa al prezzo migliore."""
    from datetime import date as _date, timedelta as _td
    user_id = str(user["id"])
    da = (_date.today() - _td(days=180)).isoformat()
    q = (
        supabase_client.table("fatture")
        .select("descrizione,fornitore,prezzo_unitario,data_documento")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        # Tollerante come gli altri tool: cerca su descrizione OR categoria, cosi'
        # "mozzarella" trova anche righe categorizzate ma con descrizione diversa.
        .or_(f"descrizione.ilike.%{prodotto}%,categoria.ilike.%{prodotto}%")
        .gte("data_documento", da)
    )
    if ristorante_id:
        q = q.eq("ristorante_id", ristorante_id)
    # Ordina per data desc: se il limite tronca, tiene le righe piu' recenti
    # (quelle che contano per il prezzo attuale) invece di un taglio arbitrario.
    righe = q.order("data_documento", desc=True).limit(2000).execute().data or []

    # Miglior (ultimo) prezzo per fornitore
    per_forn: Dict[str, Dict[str, Any]] = {}
    for r in righe:
        forn = (r.get("fornitore") or "?").strip()
        prezzo = float(r.get("prezzo_unitario") or 0)
        if prezzo <= 0:
            continue
        data = r.get("data_documento") or ""
        cur = per_forn.get(forn)
        if cur is None or data > cur["data"]:
            per_forn[forn] = {"prezzo": round(prezzo, 4), "data": data, "descrizione": r.get("descrizione")}

    confronto = sorted(
        [{"fornitore": f, **v} for f, v in per_forn.items()],
        key=lambda x: x["prezzo"],
    )
    return {"prodotto": prodotto, "fornitori": confronto[:10], "trovati": len(confronto)}


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    summary="Chat AI sui dati del ristorante",
    tags=["Chat"],
    dependencies=[Depends(_verify_worker_key)],
)
def chat_ai(
    body: ChatRequest,
    authorization: Optional[str] = Header(None),
) -> ChatResponse:
    user = _resolve_user_from_token(authorization)
    from services import get_supabase_client
    supabase_client = get_supabase_client()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY non configurata")

    user_id = str(user["id"])
    # Risolto una sola volta e riusato ovunque (tool dispatcher incluso).
    ristorante_id = _resolve_ristorante_id(user, supabase_client)

    # Contesto: catena (vista gruppo /catena) o sede (singolo PV, default).
    is_catena = body.contesto == "catena"

    if is_catena:
        # Pool AI unico: limite = SOMMA dei limiti effettivi di ogni sede; il
        # conteggio è a livello ACCOUNT (p_ristorante_id NULL → la RPC conta per
        # user_id, cioè tutte le righe chat dell'account). Un solo contatore.
        limite = _chat_limite_pool_gruppo(user, supabase_client)
        rate_ristorante = None
    else:
        # Limite domande/giorno in base al piano EFFETTIVO del cliente: piano della
        # sede attiva (modello piano-per-sede), con fallback a users.piano.
        piano = _resolve_piano_effettivo(user, supabase_client)
        limite = _chat_limite_per_piano(piano)
        rate_ristorante = ristorante_id

    # Piano free: chat non disponibile.
    if limite <= 0:
        raise HTTPException(
            status_code=403,
            detail="La chat con l'assistente non è inclusa nel tuo piano. Passa a un piano superiore per attivarla.",
        )

    # Rate limit giornaliero atomico (RPC): conta+inserisce in un solo statement
    # PRIMA della chiamata OpenAI. Elimina la race (N richieste concorrenti che
    # leggono lo stesso conteggio) e il fail-open del vecchio INSERT post-chiamata.
    # Se la RPC fallisce -> fail-closed (rifiuta la domanda).
    try:
        _rpc = supabase_client.rpc("chat_usage_check_and_log", {
            "p_user_id": user_id,
            "p_ristorante_id": rate_ristorante,
            "p_limite": limite,
        }).execute()
        domande_oggi = int(_rpc.data) if _rpc.data is not None else -1
    except Exception as exc:
        logger.warning("chat: rate-limit RPC fallita (fail-closed): %s", exc)
        raise HTTPException(status_code=503, detail="Servizio temporaneamente non disponibile. Riprova.")
    if domande_oggi < 0:
        raise HTTPException(
            status_code=429,
            detail=f"Hai raggiunto il limite di {limite} domande per oggi. Riprova domani.",
        )

    system_prompt = (
        _build_chat_system_prompt_catena(user, supabase_client, authorization)
        if is_catena
        else _build_chat_system_prompt(user, supabase_client, authorization, ristorante_id)
    )

    from openai import OpenAI
    import json as _json
    # timeout esplicito: senza, il default OpenAI è 600s e il nostro handler 504
    # non scatterebbe mai in tempo utile.
    client = OpenAI(api_key=openai_api_key, timeout=30.0)

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m.role, "content": m.content} for m in body.messages]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "query_costi",
                "description": (
                    "Interroga i costi fatturati del ristorante con filtri opzionali. "
                    "Usalo per domande su un periodo specifico (un mese o un anno) o "
                    "per cercare la spesa su una categoria, un fornitore o un prodotto."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mese": {"type": "integer", "description": "Numero del mese 1-12 (opzionale)"},
                        "anno": {"type": "integer", "description": "Anno es. 2026 (opzionale)"},
                        "categoria": {"type": "string", "description": "Categoria di spesa, es. 'carne' (opzionale)"},
                        "fornitore": {"type": "string", "description": "Nome o parte del fornitore (opzionale)"},
                        "prodotto": {"type": "string", "description": "Nome o parte del prodotto, es. 'mozzarella' (opzionale)"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_scadenze",
                "description": (
                    "Elenco delle scadenze di pagamento (fatture fornitori) con importi "
                    "e date. Usalo per 'cosa devo pagare', 'quanto devo a X', 'scadenze "
                    "questa settimana'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "solo_da_pagare": {"type": "boolean", "description": "true (default) = solo non pagate"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_margini",
                "description": (
                    "Andamento di fatturato, food cost % e MOL negli ultimi mesi. "
                    "Usalo per 'com'è andato il MOL', 'andamento margini', 'food cost "
                    "nel tempo'."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_coperti",
                "description": (
                    "Coperti (persone servite) e scontrino medio negli ultimi mesi. "
                    "Usalo per 'quanti coperti ho fatto', 'qual e' il mio scontrino "
                    "medio', 'quante persone servo al giorno', 'qual e' il giorno piu' "
                    "pieno'. Diverso da query_margini (che da' fatturato/MOL)."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "confronto_prezzi",
                "description": (
                    "Confronta il prezzo di un prodotto tra i fornitori per trovare il "
                    "migliore. Usalo per 'chi mi fa X al prezzo migliore', 'confronta i "
                    "prezzi di Y'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prodotto": {"type": "string", "description": "Nome o parte del prodotto da confrontare"},
                    },
                    "required": ["prodotto"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ultimi_acquisti",
                "description": (
                    "Le ultime righe d'acquisto in ordine di data (piu' recente prima), "
                    "con data, prodotto, fornitore e importo. Usalo per 'qual e' l'ultimo "
                    "acquisto', 'ultima fattura', 'l'ultima volta che ho comprato X', "
                    "'cosa ho comprato di recente da Y'. NON usarlo per totali di spesa "
                    "(quello e' query_costi)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prodotto": {"type": "string", "description": "Nome o parte del prodotto (opzionale)"},
                        "fornitore": {"type": "string", "description": "Nome o parte del fornitore (opzionale)"},
                        "limite": {"type": "integer", "description": "Quante righe restituire, 1-15 (default 5)"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "trend_prezzo",
                "description": (
                    "Andamento del PREZZO UNITARIO di un prodotto mese per mese, con la "
                    "variazione % dal primo all'ultimo mese. Usalo per 'la mozzarella e' "
                    "aumentata?', 'il prezzo di X e' salito/sceso?', 'come e' cambiato il "
                    "prezzo di Y'. Diverso da query_costi (che da' la spesa totale)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prodotto": {"type": "string", "description": "Nome o parte del prodotto, es. 'mozzarella'"},
                    },
                    "required": ["prodotto"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_appuntamenti",
                "description": (
                    "Appuntamenti in agenda del ristorante (titolo, data, ora). Usalo per "
                    "'cosa ho oggi', 'che appuntamenti ho questa settimana', 'ho impegni "
                    "domani'. Sola lettura: non crea ne' modifica nulla."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "da": {"type": "string", "description": "Data inizio YYYY-MM-DD (opzionale, default oggi)"},
                        "a": {"type": "string", "description": "Data fine YYYY-MM-DD (opzionale, default +7 giorni)"},
                    },
                },
            },
        },
    ]

    # Doppia competenza per contesto (gate tool per "pagina"): in /catena la chat
    # accende SOLO i tool di gruppo (leggono /api/gruppo/*) e spegne quelli per-sede;
    # nei PV resta com'era. Stesso meccanismo del gate per flag pagina, applicato al
    # contesto. I tool di gruppo sono definiti/dispatchati a parte (_CHAT_TOOLS_GRUPPO).
    if is_catena:
        reply, p_tok, c_tok = _chat_loop_openai(
            client,
            messages,
            _CHAT_TOOLS_GRUPPO,
            lambda nome, args: _chat_esegui_tool_gruppo(nome, args, authorization),
        )
        try:
            from services.ai_cost_service import track_ai_usage
            track_ai_usage(
                operation_type="chat", prompt_tokens=p_tok, completion_tokens=c_tok,
                ristorante_id=ristorante_id, user_id=user_id, model=CHAT_MODEL,
            )
        except Exception as exc:
            logger.warning("chat catena: tracking costi fallito (non blocca): %s", exc)
        logger.info("chat_ai[catena]: user=%s domande_oggi=%d", user.get("email"), domande_oggi)
        return ChatResponse(
            reply=reply or "Non sono riuscito a elaborare la risposta, riprova.",
            domande_oggi=domande_oggi,
            limite_giorno=limite,
        )

    # Gate per permessi pagina: la chat offre al modello solo gli strumenti delle
    # pagine abilitate per l'utente. pagine_abilitate None (admin) => tutti i tool.
    # Coerente con la visibilita' della sidebar: chi non vede una pagina non puo'
    # nemmeno interrogarne i dati via chat.
    _TOOL_FLAG = {
        "query_costi": "analisi_fatture",
        "ultimi_acquisti": "analisi_fatture",
        "query_scadenze": "scadenziario",
        "query_margini": "margini",
        "query_coperti": "margini",
        "confronto_prezzi": "prezzi",
        "trend_prezzo": "prezzi",
        "query_appuntamenti": "agenda",
    }
    pagine = _normalize_pagine(user.get("pagine_abilitate"))
    if pagine is not None:
        pagine_set = set(pagine)
        tools = [
            t for t in tools
            if _TOOL_FLAG.get(t["function"]["name"]) in pagine_set
        ]

    def _esegui_tool(nome: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if nome == "query_costi":
            return _chat_query_costi(
                user_id=user_id,
                supabase_client=supabase_client,
                mese=args.get("mese"),
                anno=args.get("anno"),
                categoria=args.get("categoria"),
                fornitore=args.get("fornitore"),
                prodotto=args.get("prodotto"),
                ristorante_id=ristorante_id,
            )
        if nome == "query_scadenze":
            return _chat_query_scadenze(user, supabase_client, args.get("solo_da_pagare", True))
        if nome == "query_margini":
            return _chat_query_margini(user, supabase_client, authorization)
        if nome == "query_coperti":
            return _chat_query_coperti(user, supabase_client, authorization)
        if nome == "confronto_prezzi":
            return _chat_confronto_prezzi(user, supabase_client, args.get("prodotto", ""), ristorante_id)
        if nome == "ultimi_acquisti":
            return _chat_ultimi_acquisti(
                user_id=user_id,
                supabase_client=supabase_client,
                prodotto=args.get("prodotto"),
                fornitore=args.get("fornitore"),
                limite=args.get("limite", 5),
                ristorante_id=ristorante_id,
            )
        if nome == "trend_prezzo":
            return _chat_trend_prezzo(
                user_id=user_id,
                supabase_client=supabase_client,
                prodotto=args.get("prodotto", ""),
                ristorante_id=ristorante_id,
            )
        if nome == "query_appuntamenti":
            return _chat_query_appuntamenti(
                user, supabase_client, ristorante_id,
                da=args.get("da"), a=args.get("a"),
            )
        return {"errore": f"strumento sconosciuto: {nome}"}

    # Accumulatori token per il tracking costi (somma di tutti i round del loop).
    _prompt_tok = 0
    _completion_tok = 0
    try:
        from openai import APITimeoutError as _OAITimeout, RateLimitError as _OAIRateLimit, APIError as _OAIError
        reply = ""
        # Loop tool calling: max 3 round. 1 retry su errori transienti (timeout/5xx).
        for _ in range(3):
            for tentativo in range(2):
                try:
                    resp = client.chat.completions.create(
                        model=CHAT_MODEL,
                        messages=messages,  # type: ignore[arg-type]
                        tools=tools,  # type: ignore[arg-type]
                        max_tokens=900,
                        temperature=0.3,
                    )
                    break
                except _OAITimeout:
                    if tentativo == 0:
                        continue
                    raise HTTPException(status_code=504, detail="L'assistente ha impiegato troppo tempo. Riprova.")
                except _OAIRateLimit:
                    raise HTTPException(status_code=429, detail="Servizio temporaneamente sovraccarico. Riprova tra qualche secondo.")
                except _OAIError as exc:
                    if tentativo == 0 and getattr(exc, "status_code", 0) >= 500:
                        continue
                    raise
            if resp.usage:
                _prompt_tok += resp.usage.prompt_tokens or 0
                _completion_tok += resp.usage.completion_tokens or 0
            msg = resp.choices[0].message
            if not msg.tool_calls:
                reply = msg.content or ""
                break
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = _json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                risultato = _esegui_tool(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _json.dumps(risultato, ensure_ascii=False),
                })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("chat_ai: errore inatteso: %s", exc)
        raise HTTPException(status_code=502, detail="Errore nella comunicazione con l'assistente. Riprova.")

    # Tracking costi monetari nel ledger AI (fail-safe: non blocca la risposta).
    # Alimenta l'alert soglia costi mensile, come la categorizzazione.
    try:
        from services.ai_cost_service import track_ai_usage
        track_ai_usage(
            operation_type="chat",
            prompt_tokens=_prompt_tok,
            completion_tokens=_completion_tok,
            ristorante_id=ristorante_id,
            user_id=user_id,
            model=CHAT_MODEL,
        )
    except Exception as exc:
        logger.warning("chat: tracking costi fallito (non blocca): %s", exc)

    # Il log della domanda e' gia' stato scritto atomicamente dalla RPC di
    # rate-limit prima della chiamata OpenAI: niente INSERT qui.
    logger.info("chat_ai: user=%s model=%s messages=%d domande_oggi=%d",
                user.get("email"), CHAT_MODEL, len(body.messages), domande_oggi)
    return ChatResponse(
        reply=reply or "Non sono riuscito a elaborare la risposta, riprova.",
        domande_oggi=domande_oggi,
        limite_giorno=limite,
    )


def _saluto_per_ora(nome: Optional[str]) -> str:
    """Saluto adattivo all'ora corrente (fuso Europe/Rome)."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        ora = _dt.now(tz=ZoneInfo("Europe/Rome")).hour
    except Exception:
        ora = _dt.now().hour
    if ora < 12:
        base = "Buongiorno"
    elif ora < 18:
        base = "Buon pomeriggio"
    else:
        base = "Buonasera"
    nome = (nome or "").strip()
    return f"{base}, {nome}" if nome else base


_MESI_IT_BRIEFING = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def _scontrino_medio_significativo(
    ristorante_id: str, supabase_client, ieri_d, coperti_ieri, netto_ieri: float,
) -> Optional[Dict[str, Any]]:
    """Scontrino medio di ieri da includere nell'apertura SOLO se si scosta in
    modo importante dalla media del mese in corso (COPERTI_ALERT). Niente rumore:
    se manca il dato o lo scostamento è piccolo → None.

    Ritorna {'scontrino_medio': X, 'scontrino_delta_pct': N, 'scontrino_su': bool}.
    """
    from config.constants import COPERTI_ALERT
    if coperti_ieri is None:
        return None
    try:
        cop = int(coperti_ieri)
    except (ValueError, TypeError):
        return None
    if cop <= 0 or netto_ieri <= 0:
        return None
    sm_ieri = netto_ieri / cop

    soglia = float(COPERTI_ALERT["scontrino_medio_delta_pct"])
    min_base = int(COPERTI_ALERT["min_giorni_baseline"])

    # Baseline: scontrino medio dei giorni con coperti del mese in corso, ieri escluso.
    primo = ieri_d.replace(day=1)
    try:
        resp = (
            supabase_client.table("ricavi_giornalieri")
            .select("fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti,data")
            .eq("ristorante_id", ristorante_id)
            .gte("data", primo.isoformat())
            .lte("data", ieri_d.isoformat())
            .execute()
        )
    except Exception:
        return None
    valori = []
    for x in (resp.data or []):
        if str(x.get("data")) == ieri_d.isoformat():
            continue
        c = x.get("coperti")
        if c is None or int(c) <= 0:
            continue
        n = (float(x.get("fatturato_iva10") or 0) / 1.10
             + float(x.get("fatturato_iva22") or 0) / 1.22
             + float(x.get("altri_ricavi_noiva") or 0))
        if n > 0:
            valori.append(n / int(c))
    if len(valori) < min_base:
        return None
    base = sum(valori) / len(valori)
    if base <= 0:
        return None
    delta = (sm_ieri - base) / base
    if abs(delta) < soglia:
        return None
    return {
        "scontrino_medio": round(sm_ieri, 2),
        "scontrino_delta_pct": abs(round(delta * 100)),
        "scontrino_su": delta > 0,
    }


def _briefing_buona_notizia(
    user_id: str, ristorante_id: str, supabase_client,
) -> Optional[Dict[str, Any]]:
    """Apertura POSITIVA del briefing: un fatto vero e fresco con cui iniziare.

    Senza questa, il briefing e' una pura to-do list: quando va tutto bene
    diventa muto o si fissa sull'unica rogna residua (es. le scadute), facendo
    sembrare in difficolta' anche un'azienda che macina margine. Qui diamo
    all'AI UN fatto positivo consolidato da cui partire, prima delle cose da
    fare. Decisioni Mattia (09/06):

    - MAI confronti fuorvianti nel quotidiano (sagre/chiusure/meteo falsano il
      "vs ieri" / "vs settimana scorsa"). L'eco quotidiana e' solo il dato grezzo.
    - Priorita': 1) MOL del mese appena chiuso SE in crescita (la festa di
      inizio mese, confronto su orizzonte pulito); 2) altrimenti l'incasso di
      IERI, e SOLO di ieri (oltre non e' piu' una notizia fresca -> silenzio).
    - Niente apertura forzata: se non c'e' un fatto fresco e solido, si torna
      al to-do puro. Meglio sobri che fuorvianti.

    Restituisce un record-notifica (stesso formato degli altri segnali live) col
    topic_key 'buona_notizia', oppure None.
    """
    from datetime import datetime as _dt2, timedelta as _td2

    # ── 1) MOL del mese appena chiuso, SOLO se in crescita ──────────────────
    # Riusa la stessa logica/fonte di /api/home/kpi (margini_mensili) cosi' la
    # card "I tuoi conti" e il briefing non si contraddicono mai.
    try:
        from services.margine_service import (
            carica_margini_anno, calcola_costi_automatici_per_anno_sql,
        )
        oggi = _oggi_rome()
        mm, aa = (12, oggi.year - 1) if oggi.month == 1 else (oggi.month - 1, oggi.year)

        _cache_anno: Dict[int, tuple] = {}

        def _dati(anno: int):
            if anno not in _cache_anno:
                try:
                    m = carica_margini_anno(user_id, ristorante_id, anno)
                    fb, sp = calcola_costi_automatici_per_anno_sql(user_id, ristorante_id, anno)
                    _cache_anno[anno] = (m, fb, sp)
                except Exception:
                    _cache_anno[anno] = ({}, {}, {})
            return _cache_anno[anno]

        # Ultimo mese completo con dati (fino a 6 indietro), come home_kpi.
        kpi = mese_usato = anno_usato = None
        cm, ca = mm, aa
        for _ in range(6):
            margini, cfb, csp = _dati(ca)
            cand = _kpi_periodo(margini, cfb, csp, cm)
            if cand["has_data"]:
                kpi, mese_usato, anno_usato = cand, cm, ca
                break
            cm -= 1
            if cm == 0:
                cm, ca = 12, ca - 1

        if kpi is not None and kpi.get("mol") is not None:
            pm, pa = (mese_usato - 1, anno_usato) if mese_usato > 1 else (12, anno_usato - 1)
            p_margini, p_fb, p_sp = _dati(pa)
            kpi_prec = _kpi_periodo(p_margini, p_fb, p_sp, pm)
            mol_curr = float(kpi["mol"])
            if kpi_prec.get("has_data") and kpi_prec.get("mol") is not None:
                mol_prec = float(kpi_prec["mol"])
                # In crescita = MOL positivo E sopra il mese prima. Solo allora e'
                # una "buona notizia" da festeggiare in apertura.
                # Due freni: (1) NON festeggiamo se la Salute e' rossa (dati
                # inseriti a mano, mese non consolidato); (2) NON festeggiamo se i
                # COSTI del mese mancano (food + spese = 0): il MOL sarebbe solo
                # fatturato - personale, un "+172%!" falso accanto a un food cost
                # 0%. In entrambi i casi cadiamo sull'incasso di ieri (o sul
                # silenzio): l'incoerenza la risolve l'utente completando i dati.
                if (mol_curr > 0 and mol_prec > 0 and mol_curr > mol_prec
                        and not kpi.get("costi_mancanti")
                        and not _salute_indice_rosso(ristorante_id, supabase_client)):
                    delta_pct = round((mol_curr - mol_prec) / abs(mol_prec) * 100, 1)
                    return {
                        "id": f"buona-notizia-mol-{anno_usato}-{mese_usato:02d}",
                        "topic_key": "buona_notizia",
                        "source_type": "live",
                        "severity": "success",
                        "title": "",
                        "body": "",
                        "action_page": "/margini",
                        "payload": {
                            "tipo": "mol_mese",
                            "mese": _MESI_IT_BRIEFING[mese_usato],
                            "mol": round(mol_curr, 0),
                            "delta_pct": delta_pct,
                            "mese_prec": _MESI_IT_BRIEFING[pm],
                        },
                        "source_event_at": None,
                        "dedupe_key": f"buona-notizia-mol-{anno_usato}-{mese_usato:02d}",
                    }
                # Perdita in CALO: MOL ancora negativo ma migliore del mese prima.
                # E' incoraggiante ("sei sulla strada giusta") senza fingere che
                # vada bene. Decisione Mattia: segnalarlo come spinta.
                if (mol_curr < 0 and mol_prec < 0 and mol_curr > mol_prec
                        and not kpi.get("costi_mancanti")
                        and not _salute_indice_rosso(ristorante_id, supabase_client)):
                    return {
                        "id": f"buona-notizia-perdita-{anno_usato}-{mese_usato:02d}",
                        "topic_key": "buona_notizia",
                        "source_type": "live",
                        "severity": "success",
                        "title": "",
                        "body": "",
                        "action_page": "/margini",
                        "payload": {
                            "tipo": "perdita_in_calo",
                            "mese": _MESI_IT_BRIEFING[mese_usato],
                            "perdita": round(abs(mol_curr), 0),
                            "perdita_prec": round(abs(mol_prec), 0),
                            "mese_prec": _MESI_IT_BRIEFING[pm],
                        },
                        "source_event_at": None,
                        "dedupe_key": f"buona-notizia-perdita-{anno_usato}-{mese_usato:02d}",
                    }
    except Exception as exc:
        logger.warning("briefing buona notizia: blocco MOL fallito: %s", exc)

    # ── 2) Incasso di IERI (e solo di ieri) ─────────────────────────────────
    # Eco del dato fresco appena entrato/inserito. Nessun confronto: solo "ieri
    # sono entrati €X". Se l'ultimo incasso NON e' di ieri, niente eco (oltre il
    # giorno prima non e' piu' una notizia fresca -> decisione Mattia).
    try:
        ieri_d = _oggi_rome() - _td2(days=1)
        ieri = ieri_d.isoformat()
        ric = (
            supabase_client.table("ricavi_giornalieri")
            .select("fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti")
            .eq("ristorante_id", ristorante_id)
            .eq("data", ieri)
            .limit(1)
            .execute()
        )
        rows = ric.data or []
        if rows:
            r = rows[0]
            netto_ieri = (
                float(r.get("fatturato_iva10") or 0) / 1.10
                + float(r.get("fatturato_iva22") or 0) / 1.22
                + float(r.get("altri_ricavi_noiva") or 0)
            )
            incasso = (
                float(r.get("fatturato_iva10") or 0)
                + float(r.get("fatturato_iva22") or 0)
                + float(r.get("altri_ricavi_noiva") or 0)
            )
            if incasso > 0:
                payload: Dict[str, Any] = {"tipo": "incasso_ieri", "incasso": round(incasso, 0)}
                # Arricchimento scontrino medio: SOLO se ieri ha coperti e lo
                # scostamento dalla media del mese è importante (COPERTI_ALERT).
                sm = _scontrino_medio_significativo(
                    ristorante_id, supabase_client, ieri_d,
                    r.get("coperti"), netto_ieri,
                )
                if sm:
                    payload.update(sm)
                return {
                    "id": f"buona-notizia-incasso-{ieri}",
                    "topic_key": "buona_notizia",
                    "source_type": "live",
                    "severity": "success",
                    "title": "",
                    "body": "",
                    "action_page": "/margini",
                    "payload": payload,
                    "source_event_at": None,
                    "dedupe_key": f"buona-notizia-incasso-{ieri}",
                }
    except Exception as exc:
        logger.warning("briefing buona notizia: blocco incasso fallito: %s", exc)

    return None


def _briefing_appuntamenti_oggi(
    user_id: str, ristorante_id: str, supabase_client,
) -> List[Dict[str, Any]]:
    """Promemoria appuntamenti dell'Agenda IN PROGRAMMA OGGI (topic
    'appuntamento_imminente', severity 'info' = importanza medio/bassa).

    A differenza degli altri segnali del briefing (price-alert, dati mensili) qui
    PERSISTIAMO la notifica in notification_inbox: la pagina Avvisi legge solo dal
    DB, e il requisito e' che l'appuntamento compaia sia nel briefing sia li'.
    Bucket giornaliero + expires 1 giorno => una notifica per appuntamento al
    giorno, auto-pulente. Rispetta il flag pagina 'agenda': se il cliente non ha
    l'Agenda abilitata, niente promemoria. Il toggle del configuratore
    ('appuntamento_imminente' in topics_disabled) e' gestito a valle, come per
    tutti gli altri topic. Best-effort: ogni errore resta confinato qui."""
    try:
        urec = (
            supabase_client.table("users")
            .select("pagine_abilitate")
            .eq("id", user_id)
            .single()
            .execute()
        )
        pagine = _normalize_pagine((urec.data or {}).get("pagine_abilitate"))
    except Exception:
        pagine = None
    # pagine None = nessuna restrizione (tutte abilitate). Se c'e' una lista e
    # 'agenda' non e' dentro -> niente promemoria.
    if pagine is not None and "agenda" not in set(pagine):
        return []

    from datetime import datetime as _dt_ag
    try:
        from zoneinfo import ZoneInfo as _ZI_ag
        oggi = _dt_ag.now(tz=_ZI_ag("Europe/Rome")).date()
    except Exception:
        oggi = _dt_ag.now().date()
    oggi_iso = oggi.isoformat()

    try:
        eventi = (
            supabase_client.table("diario_eventi")
            .select("titolo,ora_inizio")
            .eq("ristorante_id", ristorante_id)
            .eq("data_evento", oggi_iso)
            .order("ora_inizio", nullsfirst=True)
            .limit(20)
            .execute()
            .data or []
        )
    except Exception as exc:
        logger.warning("briefing appuntamenti: lettura diario fallita: %s", exc)
        return []
    if not eventi:
        return []

    n = len(eventi)
    primo = (eventi[0].get("titolo") or "").strip() or "appuntamento"
    ora0 = (eventi[0].get("ora_inizio") or "")[:5]
    if n == 1:
        titolo = "Hai un appuntamento oggi"
        body = f"{ora0 + ' — ' if ora0 else ''}{primo}"
    else:
        titolo = f"Hai {n} appuntamenti oggi"
        body = f"A partire da {ora0 + ' — ' if ora0 else ''}{primo}"

    from services.notification_inbox_service import (
        build_notification_record, upsert_inbox_notifications,
    )
    record = build_notification_record(
        user_id=user_id,
        ristorante_id=ristorante_id,
        topic_key="appuntamento_imminente",
        source_type="agenda",
        severity="info",
        title=titolo,
        body=body,
        payload={"count": n, "primo": primo, "ora": ora0 or None},
        action_page="/agenda",
    )
    upsert_inbox_notifications([record], supabase_client)
    # Lo includo anche nella lista del briefing (forma effimera): _build_snapshot
    # lavora sui record passati, non rilegge il DB.
    return [{
        "id": record["dedupe_key"],
        "topic_key": "appuntamento_imminente",
        "source_type": "agenda",
        "severity": "info",
        "title": titolo,
        "body": body,
        "action_page": "/agenda",
        "payload": record["payload"],
        "source_event_at": None,
        "dedupe_key": record["dedupe_key"],
    }]


def _briefing_dati_mensili_mancanti(
    ristorante_id: str, supabase_client,
) -> List[Dict[str, Any]]:
    """Notifiche LIVE dati mancanti per il briefing Home: fatturato e costo
    personale del mese precedente (fonte: /api/home/salute) + incasso di ieri
    (fonte: /api/ricavi/notifica-mancante).

    Replica ESATTAMENTE la logica di quelle fonti (mese precedente, tabella
    margini_mensili, personale = dipendenti + extra; incasso = riga
    ricavi_giornalieri per ieri). Cosi' briefing e Salute non si contraddicono
    mai: prima il briefing leggeva solo notification_inbox, popolata pero'
    soltanto dalla vecchia pagina Streamlit / dall'endpoint dedicato -> sull'app
    nuova quelle notifiche non comparivano e il briefing diceva 'tutto ok'
    mentre la Salute segnalava il mese mancante.

    Niente persistenza: notifiche effimere come price-alert-live, ricalcolate a
    ogni briefing dalla fonte autorevole. Stesso formato dei record inbox cosi'
    _build_snapshot le tratta come tutte le altre.
    """
    from datetime import datetime as _dt2, timedelta as _td2
    try:
        from zoneinfo import ZoneInfo as _ZI
        oggi = _dt2.now(tz=_ZI("Europe/Rome")).date()
    except Exception:
        oggi = _dt2.now().date()
    if oggi.month == 1:
        mc_anno, mc_mese = oggi.year - 1, 12
    else:
        mc_anno, mc_mese = oggi.year, oggi.month - 1
    mese_label = _MESI_IT_BRIEFING[mc_mese]

    fatturato_ok = False
    personale_ok = False
    try:
        resp = (
            supabase_client.table("margini_mensili")
            .select("fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,"
                    "costo_dipendenti,costo_personale_extra")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", mc_anno)
            .eq("mese", mc_mese)
            .execute()
        )
        for r in (resp.data or []):
            netto = (
                float(r.get("fatturato_iva10") or 0)
                + float(r.get("fatturato_iva22") or 0)
                + float(r.get("altri_ricavi_noiva") or 0)
            )
            if netto > 0:
                fatturato_ok = True
            if (float(r.get("costo_dipendenti") or 0)
                    + float(r.get("costo_personale_extra") or 0)) > 0:
                personale_ok = True
    except Exception as exc:
        logger.warning("briefing dati mensili: lettura margini fallita: %s", exc)
        return []

    # Modalità 'mensile': il fatturato è in ricavi_modalita_mensile, non in
    # margini_mensili (l'aggregato del trigger resta a 0 perché non ci sono
    # giornalieri). Stessa fonte della pagina Margini (_load_mensile_overrides):
    # se una delle due modalità è soddisfatta, l'alert non deve comparire.
    if not fatturato_ok:
        try:
            ov = _load_mensile_overrides(supabase_client, ristorante_id, [mc_anno]).get((mc_anno, mc_mese))
            if ov and (ov.get("iva10", 0) + ov.get("iva22", 0) + ov.get("altri", 0)) > 0:
                fatturato_ok = True
        except Exception as exc:
            logger.warning("briefing dati mensili: lettura override mensile fallita: %s", exc)

    out: List[Dict[str, Any]] = []
    if not fatturato_ok:
        out.append({
            "id": f"fatturato-mancante-live-{mc_anno}-{mc_mese:02d}",
            "topic_key": "fatturato_mancante",
            "source_type": "live",
            "severity": "warning",
            "title": f"Fatturato di {mese_label} {mc_anno} non ancora inserito",
            "body": "",
            "action_page": "/margini",
            "payload": {"mese": mese_label, "anno": mc_anno},
            "source_event_at": None,
            "dedupe_key": f"fatturato-mancante-live-{mc_anno}-{mc_mese:02d}",
        })
    if not personale_ok:
        out.append({
            "id": f"costo-personale-mancante-live-{mc_anno}-{mc_mese:02d}",
            "topic_key": "costo_personale_mancante",
            "source_type": "live",
            "severity": "warning",
            "title": f"Costo del personale di {mese_label} {mc_anno} non ancora inserito",
            "body": "",
            "action_page": "/margini",
            "payload": {"mese": mese_label, "anno": mc_anno},
            "source_event_at": None,
            "dedupe_key": f"costo-personale-mancante-live-{mc_anno}-{mc_mese:02d}",
        })

    # Incasso di IERI mancante: stessa logica dell'endpoint dedicato
    # (/api/ricavi/notifica-mancante) ma calcolata live qui, cosi' compare nel
    # briefing anche sull'app nuova senza dipendere da quella chiamata. Niente
    # tolleranza weekend/chiusura: identico all'endpoint (non inventiamo qui una
    # semantica di chiusura che non esiste in DB).
    try:
        # Se il mese corrente è in modalità 'mensile' il cliente non inserisce i
        # giornalieri di proposito: l'incasso di ieri non mancherà mai davvero,
        # quindi niente alert (altrimenti tornerebbe ogni giorno).
        mese_corrente_mensile = (oggi.year, oggi.month) in _load_mensile_overrides(
            supabase_client, ristorante_id, [oggi.year]
        )
        ieri = (oggi - _td2(days=1)).isoformat()
        ric = (
            supabase_client.table("ricavi_giornalieri")
            .select("data")
            .eq("ristorante_id", ristorante_id)
            .eq("data", ieri)
            .limit(1)
            .execute()
        )
        if not mese_corrente_mensile and not (ric.data or []):
            out.append({
                "id": f"incasso-mancante-live-{ieri}",
                "topic_key": "incasso_mancante",
                "source_type": "live",
                "severity": "warning",
                "title": "Manca l'incasso di ieri",
                "body": "",
                "action_page": "/margini",
                "payload": {},
                "source_event_at": None,
                "dedupe_key": f"incasso-mancante-live-{ieri}",
            })
    except Exception as exc:
        logger.warning("briefing dati mensili: check incasso ieri fallito: %s", exc)

    # Anomalia COPERTI di ieri: notifica SOLO su scostamento forte vs riferimento
    # (settimana o mese precedente). Parametrizzata in COPERTI_ALERT, niente
    # rumore quotidiano. Best-effort: non blocca le altre notifiche.
    try:
        anomalia = _briefing_anomalia_coperti(ristorante_id, supabase_client, oggi)
        if anomalia:
            out.append(anomalia)
    except Exception as exc:
        logger.warning("briefing dati mensili: check anomalia coperti fallito: %s", exc)

    return out


def _briefing_righe_da_classificare(
    ristorante_id: str, supabase_client,
) -> Optional[Dict[str, Any]]:
    """Notifica LIVE 'righe da classificare', allineata alla card Salute.

    Stessa fonte e finestra della voce 4 di /api/home/salute: fatture con
    needs_review=True caricate (created_at) negli ultimi 30 giorni. Cosi' se la
    card mostra "N righe da controllare", anche briefing e campanella lo dicono.
    None se non c'e' nulla da classificare (zero rumore).
    """
    from datetime import datetime as _dt2, timedelta as _td2
    try:
        from zoneinfo import ZoneInfo as _ZI
        oggi = _dt2.now(tz=_ZI("Europe/Rome")).date()
    except Exception:
        oggi = _dt2.now().date()
    inizio_dt = _dt2.combine(oggi - _td2(days=29), _dt2.min.time())
    try:
        resp = (
            supabase_client.table("fatture")
            .select("id", count="exact")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .eq("needs_review", True)
            .gte("created_at", inizio_dt.isoformat())
            .execute()
        )
        n = resp.count if resp.count is not None else len(resp.data or [])
    except Exception as exc:
        logger.warning("briefing righe da classificare: lettura fallita: %s", exc)
        return None

    if not n or n <= 0:
        return None

    return {
        "id": f"uncategorized-rows-live-{ristorante_id}",
        "topic_key": "uncategorized_rows",
        "source_type": "live",
        "severity": "warning",
        "title": f"{n} {'riga' if n == 1 else 'righe'} da classificare",
        "body": "",
        "action_page": "/analisi-fatture?tab=articoli&verifica=1",
        "payload": {"uncategorized_rows": n, "count": n},
        "source_event_at": None,
        "dedupe_key": f"uncategorized-rows-live-{ristorante_id}",
    }


def _briefing_fatture_mancanti(
    ristorante_id: str, supabase_client,
) -> Optional[Dict[str, Any]]:
    """Notifica LIVE 'mancano fatture costo', coerente con la card Salute.

    Due casi, in ordine di priorita':
      B) Il MESE appena chiuso ha ricavi ma ZERO costi (food + spese): e' la
         causa del food cost 0% e del MOL gonfiato. Stessa fonte RPC della voce
         "Fatture caricate" della Salute -> mai una contraddizione fra card e
         notifica. payload['tipo'] = 'mese_senza_costi', payload['mese'].
      A) La pipeline e' ferma: nessuna fattura caricata negli ultimi 30 giorni
         (created_at). Per i clienti nuovi/pre-go-live senza ricavi nel mese, e'
         l'unico segnale (B non scatta su un mese vuoto).

    Distingue il CANALE di ricezione: con P.IVA configurata le fatture arrivano
    in automatico via SDI/Invoicetronic ("non stanno arrivando, verifica"), senza
    P.IVA il caricamento e' manuale ("carica le fatture"). payload['canale'].
    """
    from datetime import datetime as _dt2, timedelta as _td2
    try:
        from zoneinfo import ZoneInfo as _ZI
        oggi = _dt2.now(tz=_ZI("Europe/Rome")).date()
    except Exception:
        oggi = _dt2.now().date()

    # Ultimo mese completo (lo stesso di cui parlano la card KPI e la Salute).
    if oggi.month == 1:
        mc_anno, mc_mese = oggi.year - 1, 12
    else:
        mc_anno, mc_mese = oggi.year, oggi.month - 1

    # P.IVA + user_id in un colpo: la P.IVA decide il canale, l'user_id serve
    # alla RPC dei costi. Canale: P.IVA presente -> SDI; assente -> manuale.
    canale = "manuale"
    user_id_r = None
    try:
        rinfo = (
            supabase_client.table("ristoranti")
            .select("partita_iva,user_id")
            .eq("id", ristorante_id)
            .single()
            .execute()
        )
        rd = rinfo.data or {}
        if rd.get("partita_iva"):
            canale = "sdi"
        user_id_r = rd.get("user_id")
    except Exception as exc:
        logger.warning("briefing fatture mancanti: lettura ristorante fallita: %s", exc)

    # ── Caso B (prioritario): mese CHIUSO con ricavi ma ZERO costi ──
    # E' la causa del food cost 0% e del MOL gonfiato. Coerente con la voce
    # "Fatture caricate" della card Salute (stesso mese, stessa fonte RPC). Vale
    # solo se il mese e' "attivo" (ha fatturato): un mese vuoto non e' un buco da
    # segnalare, e' solo non ancora iniziato (clienti pre-go-live).
    try:
        fatt_resp = (
            supabase_client.table("margini_mensili")
            .select("fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", mc_anno)
            .eq("mese", mc_mese)
            .execute()
        )
        fatturato_mese = 0.0
        for r in (fatt_resp.data or []):
            fatturato_mese += (
                float(r.get("fatturato_iva10") or 0)
                + float(r.get("fatturato_iva22") or 0)
                + float(r.get("altri_ricavi_noiva") or 0)
            )
    except Exception as exc:
        logger.warning("briefing fatture mancanti: lettura fatturato fallita: %s", exc)
        fatturato_mese = 0.0

    if fatturato_mese > 0:
        costi_mese = _costi_automatici_mese(
            ristorante_id, mc_anno, mc_mese, supabase_client, user_id_r
        )
        if costi_mese is not None and costi_mese <= 0:
            mese_lbl = _MESI_IT_BRIEFING[mc_mese]
            return {
                "id": f"fatture-mancanti-live-{ristorante_id}",
                "topic_key": "fatture_mancanti",
                "source_type": "live",
                "severity": "warning",
                "title": f"Mancano le fatture costo di {mese_lbl}",
                "body": "",
                "action_page": "/analisi-fatture",
                "payload": {"canale": canale, "tipo": "mese_senza_costi", "mese": mese_lbl},
                "source_event_at": None,
                "dedupe_key": f"fatture-mancanti-live-{ristorante_id}",
            }

    # ── Caso A: pipeline ferma, nessuna fattura caricata negli ultimi 30 giorni ──
    inizio_dt = _dt2.combine(oggi - _td2(days=29), _dt2.min.time())
    try:
        resp = (
            supabase_client.table("fatture")
            .select("id", count="exact")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gte("created_at", inizio_dt.isoformat())
            .limit(1)
            .execute()
        )
        n = resp.count if resp.count is not None else len(resp.data or [])
    except Exception as exc:
        logger.warning("briefing fatture mancanti: lettura fallita: %s", exc)
        return None

    if n and n > 0:
        return None

    if canale == "sdi":
        title = "Non stanno arrivando fatture dal flusso automatico"
    else:
        title = "Nessuna fattura caricata di recente"

    return {
        "id": f"fatture-mancanti-live-{ristorante_id}",
        "topic_key": "fatture_mancanti",
        "source_type": "live",
        "severity": "warning",
        "title": title,
        "body": "",
        "action_page": "/analisi-fatture",
        "payload": {"canale": canale},
        "source_event_at": None,
        "dedupe_key": f"fatture-mancanti-live-{ristorante_id}",
    }


# Topic dei segnali LIVE "leggeri" (dati mancanti): ricalcolati dalla fonte
# autorevole, senza query pesanti. Sono le STESSE voci delle card Salute/briefing.
# La campanella (get_notifiche) li fonde con i record persistiti per essere la
# somma reale (card + notifiche minori), non un sottoinsieme divergente.
_LIVE_TOPICS_DATI_MANCANTI = frozenset({
    "fatturato_mancante", "costo_personale_mancante", "incasso_mancante",
    "uncategorized_rows", "fatture_mancanti", "coperti_anomalia",
})

# Cache in-process dei segnali live per sede: get_notifiche gira nel layout di
# OGNI pagina (badge campanella). Senza cache, ~7 query leggere ad ogni
# navigazione. TTL breve: al massimo 60s di ritardo dopo l'inserimento di un dato
# (poi la card e la campanella tornano allineate).
_LIVE_SEGNALI_CACHE: Dict[str, tuple] = {}
_LIVE_SEGNALI_TTL = 60.0  # secondi


def _segnali_live_dati_mancanti(
    ristorante_id: str, supabase_client,
) -> List[Dict[str, Any]]:
    """Raccoglie i segnali LIVE leggeri (dati mancanti) di una sede.

    Stesse voci che il briefing calcola live + le righe da classificare e le
    fatture mancanti. NIENTE alert prezzi (pesante, fino a 4s): la campanella non
    deve mai essere lenta. Usato da get_notifiche per fondere live + persistite.
    Best-effort: ogni blocco e' isolato, un errore non azzera gli altri segnali.
    Cache in-process TTL 60s, keyed per ristorante.
    """
    import time as _time
    _now = _time.monotonic()
    _cached = _LIVE_SEGNALI_CACHE.get(ristorante_id)
    if _cached and (_now - _cached[0]) < _LIVE_SEGNALI_TTL:
        return list(_cached[1])

    out: List[Dict[str, Any]] = []
    try:
        out.extend(_briefing_dati_mensili_mancanti(ristorante_id, supabase_client))
    except Exception as exc:
        logger.warning("segnali live: dati mensili falliti: %s", exc)
    try:
        r = _briefing_righe_da_classificare(ristorante_id, supabase_client)
        if r is not None:
            out.append(r)
    except Exception as exc:
        logger.warning("segnali live: righe da classificare fallite: %s", exc)
    try:
        f = _briefing_fatture_mancanti(ristorante_id, supabase_client)
        if f is not None:
            out.append(f)
    except Exception as exc:
        logger.warning("segnali live: fatture mancanti fallite: %s", exc)

    _LIVE_SEGNALI_CACHE[ristorante_id] = (_now, list(out))
    return out


def _briefing_anomalia_coperti(
    ristorante_id: str, supabase_client, oggi,
) -> Optional[Dict[str, Any]]:
    """Notifica anomalia coperti di ieri vs riferimento (COPERTI_ALERT).

    Ritorna un record notifica (stesso formato live) solo se:
      - ieri ha coperti valorizzati (> 0),
      - la baseline ha almeno min_giorni_baseline giorni con coperti,
      - |coperti_ieri - baseline| / baseline >= coperti_anomalia_delta_pct.
    Altrimenti None (nessun rumore). Il cooldown è gestito a valle dal dedupe_key
    giornaliero + filtro topic spenti dell'utente.
    """
    from datetime import timedelta as _td3
    from config.constants import COPERTI_ALERT

    soglia = float(COPERTI_ALERT["coperti_anomalia_delta_pct"])
    min_base = int(COPERTI_ALERT["min_giorni_baseline"])
    riferimento = str(COPERTI_ALERT["riferimento"])

    ieri = oggi - _td3(days=1)

    r_ieri = (
        supabase_client.table("ricavi_giornalieri")
        .select("coperti")
        .eq("ristorante_id", ristorante_id)
        .eq("data", ieri.isoformat())
        .limit(1)
        .execute()
    )
    rows = r_ieri.data or []
    if not rows or rows[0].get("coperti") is None:
        return None
    coperti_ieri = int(rows[0]["coperti"])
    if coperti_ieri <= 0:
        return None

    # Baseline: media dei coperti dei giorni di confronto.
    if riferimento == "mese_prec":
        primo_mese = ieri.replace(day=1)
        fine_prec = primo_mese - _td3(days=1)
        inizio_prec = fine_prec.replace(day=1)
        base_da, base_a = inizio_prec, fine_prec
    else:  # settimana_prec (default): i 7 giorni precedenti a ieri
        base_a = ieri - _td3(days=1)
        base_da = ieri - _td3(days=7)

    r_base = (
        supabase_client.table("ricavi_giornalieri")
        .select("coperti")
        .eq("ristorante_id", ristorante_id)
        .gte("data", base_da.isoformat())
        .lte("data", base_a.isoformat())
        .execute()
    )
    valori = [int(x["coperti"]) for x in (r_base.data or []) if x.get("coperti") is not None and int(x["coperti"]) > 0]
    if len(valori) < min_base:
        return None
    baseline = sum(valori) / len(valori)
    if baseline <= 0:
        return None

    delta = (coperti_ieri - baseline) / baseline
    if abs(delta) < soglia:
        return None

    su = delta > 0
    pct = abs(round(delta * 100))
    rif_label = "della settimana scorsa" if riferimento != "mese_prec" else "del mese scorso"
    titolo = (
        f"Ieri {coperti_ieri} coperti, {pct}% in più della media {rif_label}"
        if su else
        f"Ieri solo {coperti_ieri} coperti, {pct}% in meno della media {rif_label}"
    )
    return {
        "id": f"coperti-anomalia-live-{ieri.isoformat()}",
        "topic_key": "coperti_anomalia",
        "source_type": "live",
        "severity": "info" if su else "warning",
        "title": titolo,
        "body": "",
        "action_page": "/margini?tab=coperti",
        "payload": {"coperti": coperti_ieri, "baseline": round(baseline, 1), "delta_pct": pct, "su": su},
        "source_event_at": None,
        "dedupe_key": f"coperti-anomalia-live-{ieri.isoformat()}",
    }


def _briefing_response_from_snapshot(snapshot: Dict[str, Any], nome: Optional[str]) -> "BriefingResponse":
    """Costruisce la BriefingResponse da uno snapshot (cache o appena generato).

    Centralizza il mapping snapshot->response cosi' il fast-path (cache-first) e
    il path completo restituiscono ESATTAMENTE la stessa forma.
    """
    from services.daily_briefing_service import _today_rome
    azioni = [BriefingAzione(**a) for a in (snapshot.get("azioni") or [])]
    return BriefingResponse(
        saluto=_saluto_per_ora(nome),
        data=_today_rome().isoformat(),
        narrativa=str(snapshot.get("narrative") or ""),
        severity_max=str(snapshot.get("severity_max") or "info"),
        tutto_ok=bool(snapshot.get("tutto_ok", len(azioni) == 0)),
        azioni=azioni,
        generated_at=snapshot.get("generated_at"),
    )


# Cache in-process di assistant_preferences per ristorante. Un singolo load Home
# la legge da 4 punti (get_notifiche, briefing, salute, config): senza cache erano
# 4 SELECT identiche. TTL 30s; invalidata al salvataggio del configuratore.
#
# NOTA multi-worker (WORKER_WEB_CONCURRENCY=4 in prod): questa cache e' per-processo,
# come tutte le altre in-process del worker. L'invalidazione (home_config_post)
# tocca solo il processo che serve la POST: gli altri 3 possono servire il vecchio
# valore fino allo scadere del TTL. Accettato consapevolmente: il TTL e' breve e i
# dati (toggle/nome) cambiano di rado. Per coerenza immediata cross-processo
# servirebbe una cache condivisa (Redis), sproporzionata all'attuale scala.
_ASSIST_PREF_CACHE: Dict[str, tuple] = {}
_ASSIST_PREF_TTL = 30.0  # secondi


def _invalidate_assist_pref_cache(ristorante_id: Optional[str] = None) -> None:
    """Invalida la cache assistant_preferences (una sede, o tutta)."""
    if ristorante_id is None:
        _ASSIST_PREF_CACHE.clear()
    else:
        _ASSIST_PREF_CACHE.pop(str(ristorante_id), None)


def _get_assistant_preferences(ristorante_id: str, supabase_client) -> Dict[str, Any]:
    """Riga assistant_preferences della sede, cachata in-process (TTL 30s).

    Fonte unica condivisa dai 4 call-site della Home. Ritorna {} se assente o su
    errore (fail-open: nessun nome override, nessun topic spento). Seleziona tutte
    le colonne usate dai chiamanti, cosi' ognuno prende quello che gli serve.
    """
    if not ristorante_id:
        return {}
    import time as _t
    _now = _t.monotonic()
    _cached = _ASSIST_PREF_CACHE.get(str(ristorante_id))
    if _cached and (_now - _cached[0]) < _ASSIST_PREF_TTL:
        return dict(_cached[1])
    pref: Dict[str, Any] = {}
    try:
        resp = (
            supabase_client.table("assistant_preferences")
            .select("nome_referente,topics_disabled,chat_ai_enabled,alert_prezzi_solo_preferiti")
            .eq("ristorante_id", ristorante_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            pref = dict(resp.data[0])
    except Exception as exc:
        logger.warning("_get_assistant_preferences: lettura fallita: %s", exc)
    _ASSIST_PREF_CACHE[str(ristorante_id)] = (_now, dict(pref))
    return pref


def _briefing_nome_referente(
    nome: Optional[str], ristorante_id: Optional[str], supabase_client
) -> tuple[Optional[str], List[str]]:
    """Legge override nome + topic spenti da assistant_preferences (cachata).

    Estratta per essere riusabile sia dal fast-path cache-first (che serve lo
    snapshot di oggi senza ricalcolare nulla, ma ha comunque bisogno del nome
    corretto per il saluto) sia dal path completo.
    """
    topics_disabled: List[str] = []
    if not ristorante_id:
        return nome, topics_disabled
    pref = _get_assistant_preferences(ristorante_id, supabase_client)
    if pref.get("nome_referente"):
        nome = pref["nome_referente"]
    td = pref.get("topics_disabled") or []
    if isinstance(td, list):
        topics_disabled = [str(t) for t in td]
    return nome, topics_disabled


# Soglia di assenza oltre cui scatta il bentornato di rientro (giorni). Tenuta
# alta di proposito: il messaggio deve essere RARO, solo per assenze vere.
_RIENTRO_GIORNI = 7


def _costi_automatici_mese(
    ristorante_id: str, anno: int, mese: int, supabase_client,
    user_id: Optional[str] = None,
) -> Optional[float]:
    """Costi automatici (food + spese, dalle fatture) di un singolo mese.

    Stessa fonte della card 'I tuoi conti' (RPC costi_automatici_mensili, con
    COALESCE(data_competenza, data_documento) e categorie reali): cosi' la voce
    'Fatture caricate' della Salute e il KPI non si contraddicono mai. Un mese
    chiuso con ricavi ma zero qui = food cost 0% = dati incompleti, non un mese
    sano. None se non determinabile (RPC/utente non disponibili): il chiamante
    sceglie il fallback prudente. user_id opzionale: se assente lo ricava dal
    ristorante.
    """
    try:
        if not user_id:
            r = (
                supabase_client.table("ristoranti")
                .select("user_id")
                .eq("id", ristorante_id)
                .single()
                .execute()
            )
            user_id = (r.data or {}).get("user_id")
        if not user_id:
            return None
        from services.margine_service import calcola_costi_automatici_per_anno_sql
        cfb, csp = calcola_costi_automatici_per_anno_sql(str(user_id), ristorante_id, anno)
        return float(cfb.get(mese) or 0) + float(csp.get(mese) or 0)
    except Exception as exc:
        logger.warning("costi automatici mese fallito: %s", exc)
        return None


def _salute_indice_rosso(ristorante_id: str, supabase_client) -> bool:
    """True se l'indice di Salute della gestione e' 'rosso' (< 50).

    Duplicazione CONSAPEVOLE della sola SOGLIA dell'endpoint /api/home/salute
    (stesse 4 voci a peso uguale, stessa fonte margini_mensili + fatture): qui
    serve solo il colore, non le voci/CTA dell'endpoint, e quello non e' una
    funzione pura riusabile. Se la formula della Salute cambia, allineare anche
    qui. Best-effort: in caso di errore torna False (niente amo Assistenza, che
    e' il fallback prudente).
    """
    from datetime import datetime as _dt2, timedelta as _td2
    try:
        from zoneinfo import ZoneInfo as _ZI
        oggi = _dt2.now(tz=_ZI("Europe/Rome")).date()
    except Exception:
        oggi = _dt2.now().date()

    try:
        inizio = oggi - _td2(days=29)
        inizio_dt = _dt2.combine(inizio, _dt2.min.time())
        if oggi.month == 1:
            mc_anno, mc_mese = oggi.year - 1, 12
        else:
            mc_anno, mc_mese = oggi.year, oggi.month - 1

        # Voce 4: % righe classificate sulle fatture recenti (created_at 30gg).
        righe_mese: List[Dict[str, Any]] = []
        try:
            resp = (
                supabase_client.table("fatture")
                .select("needs_review,categoria")
                .eq("ristorante_id", ristorante_id)
                .is_("deleted_at", "null")
                .gte("created_at", inizio_dt.isoformat())
                .execute()
            )
            righe_mese = resp.data or []
        except Exception:
            righe_mese = []
        tot_righe = len(righe_mese)
        da_controllare = sum(1 for r in righe_mese if r.get("needs_review"))
        pct_classificate = (
            round((tot_righe - da_controllare) / tot_righe * 100) if tot_righe else 0
        )
        # Voce 1: fatture COSTO del mese analizzato (stessa fonte della card KPI),
        # non un caricamento recente qualsiasi. Se la fonte non e' disponibile,
        # ripiego sul caricamento recente (fail-open, niente rosso ingiusto).
        costi_mese = _costi_automatici_mese(ristorante_id, mc_anno, mc_mese, supabase_client)
        fatture_ok = (costi_mese > 0) if costi_mese is not None else (tot_righe > 0)

        # Voci 2 + 3: fatturato + costo personale dell'ultimo mese completo.
        fatturato_ok = False
        personale_ok = False
        try:
            resp = (
                supabase_client.table("margini_mensili")
                .select(
                    "fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,"
                    "costo_dipendenti,costo_personale_extra"
                )
                .eq("ristorante_id", ristorante_id)
                .eq("anno", mc_anno)
                .eq("mese", mc_mese)
                .execute()
            )
            netto = 0.0
            for r in (resp.data or []):
                netto += (
                    float(r.get("fatturato_iva10") or 0)
                    + float(r.get("fatturato_iva22") or 0)
                    + float(r.get("altri_ricavi_noiva") or 0)
                )
                if (float(r.get("costo_dipendenti") or 0)
                        + float(r.get("costo_personale_extra") or 0)) > 0:
                    personale_ok = True
            fatturato_ok = netto > 0
        except Exception:
            pass

        # Modalità 'mensile': fatturato in ricavi_modalita_mensile (vedi
        # home_salute). Senza questo fallback un cliente che inserisce il totale
        # mensile (es. CASATI 14) risulterebbe a fatturato mancante -> salute
        # rossa fasulla e briefing soppresso a torto.
        if not fatturato_ok:
            try:
                ov = _load_mensile_overrides(
                    supabase_client, ristorante_id, [mc_anno]
                ).get((mc_anno, mc_mese))
                if ov and (ov.get("iva10", 0) + ov.get("iva22", 0) + ov.get("altri", 0)) > 0:
                    fatturato_ok = True
            except Exception:
                pass

        score_fatture = 100 if fatture_ok else 0
        score_fatturato = 100 if fatturato_ok else 0
        score_personale = 100 if personale_ok else 0
        score_classificate = pct_classificate if tot_righe else 0
        indice = round(
            (score_fatture + score_fatturato + score_personale + score_classificate) / 4
        )
        return indice < 50
    except Exception as exc:
        logger.warning("briefing rientro: calcolo salute fallito: %s", exc)
        return False


def _briefing_rientro_assenza(
    user_id: str, ristorante_id: Optional[str], supabase_client,
) -> Optional[Dict[str, Any]]:
    """Apertura di RIENTRO: bentornato dopo un'assenza prolungata.

    Scatta se l'utente non vedeva un briefing da >= _RIENTRO_GIORNI giorni
    (users.last_briefing_seen, indipendente da last_seen_at/last_login che il
    login aggiorna prima del briefing). Il bentornato e' per TUTTI: mai un
    rimprovero. SOLO se anche la Salute della gestione e' rossa (app incompleta)
    il payload porta offri_assistenza=True, e il template aggiunge in coda l'amo
    SOFT dell'Assistenza Continuativa. Un cliente diligente in ferie riceve solo
    il bentornato (decisione Mattia: non insultare chi era solo via).

    NON aggiorna last_briefing_seen qui: lo fa il chiamante DOPO aver letto il
    valore, cosi' la lettura vede ancora il timestamp precedente. Best-effort:
    ogni errore -> None (niente rientro, briefing normale).
    """
    if not user_id:
        return None
    from datetime import datetime as _dt2, timezone as _tz2
    try:
        resp = (
            supabase_client.table("users")
            .select("last_briefing_seen")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        raw = rows[0].get("last_briefing_seen")
        if not raw:
            # Mai visto un briefing (utente nuovo / pre-feature): non e' un
            # "rientro". Si parte a contare da ora (lo scrive il chiamante).
            return None
        try:
            last = _dt2.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return None
        giorni = (_dt2.now(_tz2.utc) - last).days
        if giorni < _RIENTRO_GIORNI:
            return None

        offri = bool(ristorante_id) and _salute_indice_rosso(ristorante_id, supabase_client)
        return {
            "id": "rientro-assenza-live",
            "topic_key": "rientro_assenza",
            "source_type": "live",
            "severity": "info",
            "title": "",
            "body": "",
            # CTA verso l'Assistenza solo se offriamo l'amo; altrimenti la Home
            "action_page": "/assistenza?servizio=assistenza_continuativa" if offri else "/dashboard",
            "payload": {
                "giorni": giorni,
                "offri_assistenza": offri,
            },
            "source_event_at": None,
            "dedupe_key": "rientro-assenza-live",
        }
    except Exception as exc:
        logger.warning("home_briefing: rientro assenza fallito: %s", exc)
        return None


def _briefing_aggiorna_last_seen(user_id: str, supabase_client) -> None:
    """Segna 'ora' come ultima volta che l'utente ha visto un briefing.

    Chiamato DOPO _briefing_rientro_assenza (che ha gia' letto il valore vecchio).
    Best-effort: un errore non deve mai rompere il briefing.
    """
    if not user_id:
        return
    from datetime import datetime as _dt2, timezone as _tz2
    try:
        (
            supabase_client.table("users")
            .update({"last_briefing_seen": _dt2.now(_tz2.utc).isoformat()})
            .eq("id", user_id)
            .execute()
        )
    except Exception as exc:
        logger.warning("home_briefing: update last_briefing_seen fallito: %s", exc)


def _briefing_raccogli_notifiche(
    user_id: str, ristorante_id: Optional[str], supabase_client,
    includi_alert_prezzi: bool = True,
) -> List[Dict[str, Any]]:
    """Raccoglie le notifiche attive + i segnali LIVE che alimentano il briefing.

    Parte PESANTE della generazione: query notifiche, alert prezzi (budget 4s),
    check ricavi automatici, dati mensili mancanti. Estratta dall'endpoint cosi'
    puo' girare in BACKGROUND (vedi _briefing_rigenera_async) invece che in linea
    sul percorso della Home — che altrimenti sforerebbe il timeout di 8s.

    `includi_alert_prezzi=False` salta SOLO l'alert prezzi (l'unica parte lenta,
    budget 4s): tutti gli altri segnali live (fatture/righe/dati mancanti) sono
    leggeri. Serve al briefing ISTANTANEO del fast-path 2, che cosi' resta
    coerente (mai un falso "tutto in ordine") senza pagare i 4s dell'alert prezzi.
    """
    from datetime import datetime as _dt, timezone as _tz

    # Notifiche attive (stesso filtro di /api/notifiche, senza dismissed).
    # Filtro per SEDE: il briefing di una sede non deve includere le notifiche
    # persistite di un'altra sede dello stesso cliente multi-sede.
    notifications: List[Dict[str, Any]] = []
    try:
        q = (
            supabase_client.table("notification_inbox")
            .select("id,topic_key,source_type,severity,title,body,action_page,payload,dismissed_at,expires_at,created_at,source_event_at,dedupe_key")
            .eq("user_id", user_id)
            .or_("expires_at.is.null,expires_at.gt." + _dt.now(_tz.utc).isoformat())
            .order("created_at", desc=True)
            .limit(100)
        )
        if ristorante_id:
            q = q.eq("ristorante_id", ristorante_id)
        resp = q.execute()
        notifications = [r for r in (resp.data or []) if not r.get("dismissed_at")]
    except Exception as exc:
        logger.warning("home_briefing: lettura notifiche fallita: %s", exc)

    # Alert prezzi: il motore LIVE per impatto €/mese (Step 4) sostituisce la
    # vecchia notifica price_alert da upload. Solo food&beverage, soglia auto,
    # prodotti + tag. Se non ci sono alert rilevanti, rimuovo il price_alert
    # legacy (zero rumore). I numeri li calcola il backend, l'AI racconta.
    if ristorante_id:
        # Il legacy price_alert da upload NON ha filtro peso (Pareto): segnala
        # qualsiasi prodotto rincarato oltre soglia, marginali compresi (es.
        # "LIMONI TRATTATI"). Va rimosso SEMPRE che subentri il motore live, anche
        # se questo poi va in timeout/errore: meglio nessun alert prezzi che un
        # alert sbagliato sui marginali. Per questo la rimozione sta PRIMA del
        # calcolo, fuori dal try — altrimenti su un timeout il legacy resterebbe.
        notifications = [n for n in notifications if n.get("topic_key") != "price_alert"]
    if ristorante_id and includi_alert_prezzi:
        try:
            from services.price_impact_service import calcola_alert_prezzi_impatto
            # Budget di tempo: l'alert prezzi e' un "di piu'" del briefing, non deve
            # poterlo affossare. Su clienti con molte fatture puo' essere lento: se
            # sfora, lo saltiamo e il briefing esce comunque (la Home non si blocca).
            # NB: non usare ThreadPoolExecutor come context manager — il suo
            # shutdown(wait=True) all'uscita del 'with' aspetterebbe comunque il
            # thread lento, vanificando il timeout. Recuperiamo il risultato con
            # result(timeout=...) e lasciamo che il thread fuggito muoia da solo.
            _ex = _ALERT_PREZZI_EXECUTOR
            _fut = _ex.submit(
                calcola_alert_prezzi_impatto, user_id, ristorante_id,
                supabase_client=supabase_client,
            )
            ap = _fut.result(timeout=_ALERT_PREZZI_TIMEOUT_SEC)
            if ap.get("count") and ap.get("top"):
                top = ap["top"]
                notifications.append({
                    "id": "price-alert-live",
                    "topic_key": "price_alert",
                    "source_type": "live",
                    "severity": "warning",
                    "title": "Alert prezzi",
                    "body": "",
                    "action_page": "/prezzi",
                    "payload": {
                        "count": ap["count"],
                        "top_product": top.get("nome"),
                        "top_increase_pct": top.get("aumento_pct"),
                        "impatto_mese": top.get("impatto_mese"),
                        # 'prodotto' | 'tag': il template distingue il linguaggio.
                        # Senza questo l'alert su un TAG (es. "BAR, CAFFE'") veniva
                        # raccontato come se fosse un prodotto -> "1 prodotto
                        # (soprattutto BAR, CAFFE')", incoerente e confuso.
                        "top_tipo": top.get("tipo"),
                    },
                    "source_event_at": None,
                    "dedupe_key": "price-alert-live",
                })
        except _cf_TimeoutError:
            logger.warning(
                "home_briefing: alert prezzi oltre %ss per ristorante=%s — saltato (briefing comunque generato)",
                _ALERT_PREZZI_TIMEOUT_SEC, ristorante_id,
            )
        except Exception as exc:
            logger.warning("home_briefing: motore alert prezzi fallito: %s", exc)

    # Upload ricavi fallito (Step 5): SOLO per clienti mappati ai ricavi
    # automatici (riga in ricavi_ragione_sociale_map). "Fallito" = mappato ma
    # nessun ricavo negli ultimi giorni (la finestra tollera weekend/chiusura).
    if ristorante_id:
        try:
            mapres = (
                supabase_client.table("ricavi_ragione_sociale_map")
                .select("ristorante_id")
                .eq("ristorante_id", ristorante_id)
                .limit(1)
                .execute()
            )
            mappato = bool(mapres.data)
            if mappato:
                from datetime import date as _date, timedelta as _tdelta
                finestra_giorni = 3
                # _oggi_rome() (non date.today() = UTC su Railway): nella finestra
                # notturna italiana l'UTC e' ancora il giorno prima e l'avviso
                # comparirebbe/sparirebbe in modo incoerente con incasso_mancante.
                soglia_data = (_oggi_rome() - _tdelta(days=finestra_giorni)).isoformat()
                recres = (
                    supabase_client.table("ricavi_giornalieri")
                    .select("data")
                    .eq("ristorante_id", ristorante_id)
                    .gte("data", soglia_data)
                    .limit(1)
                    .execute()
                )
                if not (recres.data or []):
                    # da quanti giorni manca l'ultimo ricavo (per il testo)
                    ultres = (
                        supabase_client.table("ricavi_giornalieri")
                        .select("data")
                        .eq("ristorante_id", ristorante_id)
                        .order("data", desc=True)
                        .limit(1)
                        .execute()
                    )
                    giorni_senza = None
                    if ultres.data:
                        try:
                            ultima = _date.fromisoformat(str(ultres.data[0]["data"]))
                            giorni_senza = (_oggi_rome() - ultima).days
                        except Exception:
                            giorni_senza = None
                    notifications.append({
                        "id": "upload-ricavi-live",
                        "topic_key": "upload_ricavi_failed",
                        "source_type": "live",
                        "severity": "warning",
                        "title": "Ricavi automatici assenti",
                        "body": "",
                        "action_page": "/margini",
                        "payload": {"giorni_senza": giorni_senza},
                        "source_event_at": None,
                        "dedupe_key": "upload-ricavi-live",
                    })
        except Exception as exc:
            logger.warning("home_briefing: check ricavi automatici fallito: %s", exc)

    # Dati mensili mancanti (fatturato / costo personale del mese precedente):
    # calcolati LIVE dalla stessa fonte della Salute (margini_mensili), cosi' le
    # due sezioni Home non si contraddicono mai. Niente dipendenza dalla vecchia
    # pagina Streamlit, che era l'unico posto a popolare queste notifiche.
    #
    # PRIMA rimuovo le eventuali versioni LEGACY in inbox per questi due topic:
    # le ha scritte la vecchia pagina Streamlit e NESSUNO le aggiorna quando il
    # dato viene inserito (restano fino a expires_at). _build_snapshot tiene la
    # prima occorrenza per topic_key, quindi una legacy stantia vincerebbe sulla
    # versione live autorevole -> il briefing continuerebbe a dire "manca" anche
    # dopo l'inserimento. Stesso pattern del price_alert legacy qui sopra.
    if ristorante_id:
        try:
            notifications = [
                n for n in notifications
                if n.get("topic_key") not in (
                    "fatturato_mancante", "costo_personale_mancante", "incasso_mancante",
                )
            ]
            notifications.extend(
                _briefing_dati_mensili_mancanti(ristorante_id, supabase_client)
            )
        except Exception as exc:
            logger.warning("home_briefing: dati mensili mancanti falliti: %s", exc)

    # Righe da classificare: calcolate LIVE dalla STESSA fonte/finestra della card
    # Salute (fatture con needs_review caricate negli ultimi 30 giorni). Prima il
    # briefing/campanella leggevano solo la notifica 'uncategorized_rows' scritta
    # all'UPLOAD: se le righe finivano in needs_review per una rilavorazione AI su
    # fatture gia' caricate (nessun upload recente), la card Salute le mostrava ma
    # la campanella no -> incoerenza. Rimuovo la versione upload (puo' essere
    # stantia: non si aggiorna quando classifichi) e uso il conteggio live.
    if ristorante_id:
        try:
            notifications = [
                n for n in notifications if n.get("topic_key") != "uncategorized_rows"
            ]
            _n_da_class = _briefing_righe_da_classificare(ristorante_id, supabase_client)
            if _n_da_class is not None:
                notifications.append(_n_da_class)
        except Exception as exc:
            logger.warning("home_briefing: righe da classificare live fallite: %s", exc)

    # Nessuna fattura caricata di recente: stessa voce 1 della card Salute. Se la
    # card e' rossa su "Fatture caricate", anche il briefing deve segnalarlo —
    # tutte le sedi dentro l'app sono operative, non esiste lo stato "in avvio
    # silenzioso". Calcolo LIVE (created_at ultimi 30 gg), zero persistenza.
    if ristorante_id:
        try:
            _n_fatt = _briefing_fatture_mancanti(ristorante_id, supabase_client)
            if _n_fatt is not None:
                notifications.append(_n_fatt)
        except Exception as exc:
            logger.warning("home_briefing: fatture mancanti live fallite: %s", exc)

    # Promemoria appuntamenti di oggi (Agenda). Importanza medio/bassa: in fondo
    # alla gerarchia (_TOPIC_PRIORITY) e severity 'info'. Persiste in inbox cosi'
    # compare anche nella pagina Avvisi, non solo nel briefing. Rispetta il flag
    # 'agenda' dell'utente.
    if ristorante_id:
        try:
            notifications.extend(
                _briefing_appuntamenti_oggi(user_id, ristorante_id, supabase_client)
            )
        except Exception as exc:
            logger.warning("home_briefing: promemoria appuntamenti fallito: %s", exc)

    # Apertura POSITIVA: un fatto fresco e vero (MOL del mese in crescita o
    # incasso di ieri) con cui iniziare il briefing prima delle to-do. Best
    # effort: se manca, il briefing resta to-do puro come prima.
    if ristorante_id:
        try:
            buona = _briefing_buona_notizia(user_id, ristorante_id, supabase_client)
            if buona is not None:
                notifications.insert(0, buona)
        except Exception as exc:
            logger.warning("home_briefing: buona notizia fallita: %s", exc)

    # Apertura di RIENTRO dopo un'assenza prolungata: bentornato (+ amo soft
    # Assistenza se l'app e' incompleta). Letto PRIMA di aggiornare il timestamp,
    # poi marca "visto ora". Va in testa: "sei tornato" precede ogni altra cosa,
    # quindi la prepende anche alla buona notizia. last_briefing_seen si aggiorna
    # sempre (anche senza rientro), cosi' il contatore di assenza riparte ad ogni
    # briefing realmente generato.
    try:
        rientro = _briefing_rientro_assenza(user_id, ristorante_id, supabase_client)
        if rientro is not None:
            notifications.insert(0, rientro)
    except Exception as exc:
        logger.warning("home_briefing: rientro assenza fallito: %s", exc)
    _briefing_aggiorna_last_seen(user_id, supabase_client)

    return notifications


def _briefing_rigenera_async(user_id: str, ristorante_id: Optional[str]) -> None:
    """Rigenera e salva lo snapshot di OGGI fuori dal ciclo di risposta.

    Lanciata via BackgroundTasks DOPO che la Home ha gia' ricevuto un briefing
    (stale o template istantaneo). Qui dentro possiamo permetterci la parte lenta
    (alert prezzi fino a 4s + narrazione Ai) perche' nessuno aspetta: il
    risultato sara' servito istantaneo al load successivo dal fast-path cache.
    Best-effort: ogni errore resta confinato qui, non c'e' una request da rompere.
    """
    if not ristorante_id:
        return
    try:
        from services import get_supabase_client
        from services.daily_briefing_service import generate_and_save_briefing

        supabase_client = get_supabase_client()
        notifications = _briefing_raccogli_notifiche(user_id, ristorante_id, supabase_client)
        _, topics_disabled = _briefing_nome_referente(None, ristorante_id, supabase_client)
        generate_and_save_briefing(
            user_id, ristorante_id, notifications, supabase_client,
            topics_disabled=topics_disabled,
        )
    except Exception as exc:
        logger.warning("_briefing_rigenera_async fallita per ristorante=%s: %s", ristorante_id, exc)


@app.get(
    "/api/home/briefing",
    response_model=BriefingResponse,
    summary="Briefing giornaliero Home AI — saluto, narrativa, azioni",
    tags=["Home"],
    dependencies=[Depends(_verify_worker_key)],
)
def home_briefing(
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
) -> BriefingResponse:
    from services import get_supabase_client
    from services.daily_briefing_service import (
        get_today_briefing,
        _build_snapshot,
    )

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    # Saluto Home AI: SOLO il nome_referente scelto nel configuratore. Se manca,
    # saluto liscio ("Buongiorno") — mai la ragione sociale, che e' brutta da
    # leggere ("LAND DEI SAPORI SRL") e poco umana.
    nome = user.get("nome_referente")

    supabase_client = get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)

    # ── Fast-path 1: cache-first di OGGI ─────────────────────────────────────
    # Il briefing e' un dato GIORNALIERO: se lo snapshot di oggi esiste gia' in
    # daily_briefing_state, lo serviamo subito (~0.5s) senza ricalcolare nulla di
    # pesante. Caso normale dopo la prima apertura della giornata.
    if ristorante_id:
        cached_today = get_today_briefing(user_id, ristorante_id, supabase_client)
        if cached_today is not None:
            nome, _ = _briefing_nome_referente(nome, ristorante_id, supabase_client)
            return _briefing_response_from_snapshot(cached_today, nome)

    # ── Fast-path 2: "mai bloccante" MA coerente ─────────────────────────────
    # Manca lo snapshot di oggi (prima apertura del giorno, o cache invalidata da
    # un upload/inserimento). PRIMA qui si pagava in linea tutta la generazione
    # pesante (alert prezzi fino a 4s + OpenAI): su clienti grossi l'endpoint
    # sforava gli 8s e il briefing spariva. La prima soluzione (servire l'ultimo
    # snapshot o un template dalle sole notifiche persistite) era veloce ma
    # INCOERENTE: ignorava i segnali live, cosi' diceva "tutto in ordine" anche
    # con Salute rossa e dati mancanti. Ora costruiamo SEMPRE un briefing fresco
    # con TUTTI i segnali live tranne l'alert prezzi (l'unica parte da 4s) e senza
    # riscrittura AI: istantaneo E coerente con la card Salute. Il tono AI + alert
    # prezzi arrivano col load successivo (fast-path 1) dalla rigenerazione async.
    nome, topics_disabled = _briefing_nome_referente(nome, ristorante_id, supabase_client)

    if ristorante_id:
        background_tasks.add_task(_briefing_rigenera_async, user_id, ristorante_id)
        try:
            notifications = _briefing_raccogli_notifiche(
                user_id, ristorante_id, supabase_client, includi_alert_prezzi=False,
            )
        except Exception as exc:
            logger.warning("home_briefing: raccolta istantanea fallita: %s", exc)
            notifications = []
        snapshot = _build_snapshot(notifications, use_ai=False, topics_disabled=topics_disabled)
        return _briefing_response_from_snapshot(snapshot, nome)

    # Nessun ristorante associato: niente da raccogliere, briefing vuoto.
    snapshot = _build_snapshot([], use_ai=False, topics_disabled=topics_disabled)
    return _briefing_response_from_snapshot(snapshot, nome)


_MESI_IT_FULL = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


@app.get(
    "/api/home/salute",
    response_model=SaluteResponse,
    summary="Indice di salute della gestione — completezza dati del mese",
    tags=["Home"],
    dependencies=[Depends(_verify_worker_key)],
)
def home_salute(authorization: Optional[str] = Header(None)) -> SaluteResponse:
    """Misura quanto i dati recenti sono completi.

    Quattro voci a peso uguale (25% ciascuna): fatture caricate, fatturato
    inserito, costo personale inserito, righe classificate. Conta "a posto"
    SOLO se i dati sono davvero arrivati (non basta l'automatismo attivo).

    Finestra: ultimi 30 giorni mobili (non il mese di calendario), cosi' il
    giorno 1 del mese l'indice non si azzera di colpo. Tutti i calcoli qui nel
    backend; la Home si limita a mostrare.
    """
    from datetime import datetime as _dt, timedelta as _td

    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()
    inizio = oggi - _td(days=29)  # finestra mobile di 30 giorni inclusivi
    data_da = inizio.isoformat()
    data_a = oggi.isoformat()
    mese_label = "ultimi 30 giorni"

    # Fatturato e Personale si valutano sull'ULTIMO MESE COMPLETO (il mese
    # precedente), lo stesso di cui parlano le card "manca fatturato/personale".
    # Cosi' Salute e card non si contraddicono mai. Le altre due voci (fatture,
    # classificate) restano sulla finestra mobile di 30 giorni.
    _MESI_IT_SAL = [
        "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ]
    if oggi.month == 1:
        mc_anno, mc_mese = oggi.year - 1, 12
    else:
        mc_anno, mc_mese = oggi.year, oggi.month - 1
    mese_completo_label = _MESI_IT_SAL[mc_mese]
    mc_da = _dt(mc_anno, mc_mese, 1).date().isoformat()
    # ultimo giorno del mese completo = giorno prima del primo del mese corrente
    primo_mese_corrente = _dt(oggi.year, oggi.month, 1).date()
    mc_a = (primo_mese_corrente - _td(days=1)).isoformat()

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)

    # Senza ristorante non possiamo misurare: indice 0, tutto da fare.
    if not ristorante_id:
        voci = [
            SaluteVoce(key="fatture", label="Fatture caricate", ok=False,
                       dettaglio="Nessun ristorante associato", cta_page="/analisi-fatture"),
        ]
        return SaluteResponse(indice=0, colore="rosso", mese_label=mese_label, voci=voci)

    # Toggle del configuratore: una voce SPENTA sparisce dalla card E non pesa
    # sull'indice (decisione: tutta la Home e' soggetta ai toggle). Mappa
    # voce-Salute -> topic del configuratore. Best-effort: se la lettura fallisce,
    # nessuna voce viene esclusa (fail-open, mostra tutto).
    _VOCE_TOPIC = {
        "fatture": "fatture_mancanti",
        "fatturato": "fatturato_mancante",
        "personale": "costo_personale_mancante",
        "classificate": "uncategorized_rows",
    }
    voci_spente: set = set()
    try:
        from services.daily_briefing_service import espandi_topic_spenti
        _, _td_salute = _briefing_nome_referente(None, ristorante_id, sb)
        spenti = set(espandi_topic_spenti(_td_salute or []))
        voci_spente = {k for k, t in _VOCE_TOPIC.items() if t in spenti}
    except Exception as exc:
        logger.warning("home_salute: lettura topic spenti fallita: %s", exc)

    # ── Voce 4 (dati): fatture recenti per la % di righe classificate ──
    # Il CARICAMENTO recente (created_at) misura la pipeline: un cliente attivo
    # puo' caricare oggi fatture datate settimane fa, e quelle righe vanno
    # comunque classificate. Serve solo alla voce "Righe classificate".
    inizio_dt = _dt.combine(inizio, _dt.min.time())
    righe_mese: List[Dict[str, Any]] = []
    try:
        resp = (
            sb.table("fatture")
            .select("needs_review,categoria", count="exact")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gte("created_at", inizio_dt.isoformat())
            .execute()
        )
        righe_mese = resp.data or []
    except Exception as exc:
        logger.warning("home_salute: lettura fatture fallita: %s", exc)

    # ── Voce 1: Fatture COSTO del mese analizzato (ultimo mese completo) ──
    # Coerente con fatturato/personale e con la card "I tuoi conti": misura se le
    # fatture DEL MESE di cui parliamo sono arrivate (stessa fonte RPC del KPI),
    # non un caricamento recente qualsiasi. Cosi' una sede con maggio a food cost
    # 0% vede la voce ROSSA, non un falso verde da fatture di marzo caricate ieri.
    # Se la fonte RPC non e' disponibile, ripiego sul caricamento recente.
    costi_mese = _costi_automatici_mese(ristorante_id, mc_anno, mc_mese, sb, user_id)
    if costi_mese is None:
        fatture_ok = len(righe_mese) > 0
        fatture_dett = ("Fatture recenti registrate" if fatture_ok
                        else "Nessuna fattura recente")
    else:
        fatture_ok = costi_mese > 0
        fatture_dett = (f"{mese_completo_label.capitalize()} registrate" if fatture_ok
                        else f"Mancano le fatture di {mese_completo_label}")

    # ── Voci 2 e 3: Fatturato + Costo personale dell'ultimo mese completo ──
    # Unica query su margini_mensili (stessa fonte delle card "manca fatturato/
    # personale" e del KPI): prima erano due round-trip separati sullo STESSO
    # mese, ricaviamo entrambe le voci dalle stesse righe. I ricavi giornalieri
    # non sono usati dai clienti, sarebbe sempre "manca".
    fatturato_ok = False
    personale_ok = False
    try:
        resp = (
            sb.table("margini_mensili")
            .select(
                "fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,"
                "costo_dipendenti,costo_personale_extra"
            )
            .eq("ristorante_id", ristorante_id)
            .eq("anno", mc_anno)
            .eq("mese", mc_mese)
            .execute()
        )
        netto = 0.0
        for r in (resp.data or []):
            netto += (
                float(r.get("fatturato_iva10") or 0)
                + float(r.get("fatturato_iva22") or 0)
                + float(r.get("altri_ricavi_noiva") or 0)
            )
            if (float(r.get("costo_dipendenti") or 0)
                    + float(r.get("costo_personale_extra") or 0)) > 0:
                personale_ok = True
        fatturato_ok = netto > 0
    except Exception as exc:
        logger.warning("home_salute: lettura fatturato/personale margini fallita: %s", exc)

    # Modalità 'mensile': il fatturato NON sta in margini_mensili ma in
    # ricavi_modalita_mensile (il cliente inserisce il totale del mese, non i
    # giornalieri). La pagina Margini e il segnale del briefing lo considerano;
    # senza questo fallback la card Salute direbbe "manca maggio" anche se il
    # fatturato è inserito (caso CASATI 14). Stessa fonte di
    # _briefing_dati_mensili_mancanti -> card e briefing restano coerenti.
    if not fatturato_ok:
        try:
            ov = _load_mensile_overrides(sb, ristorante_id, [mc_anno]).get((mc_anno, mc_mese))
            if ov and (ov.get("iva10", 0) + ov.get("iva22", 0) + ov.get("altri", 0)) > 0:
                fatturato_ok = True
        except Exception as exc:
            logger.warning("home_salute: lettura override mensile fallita: %s", exc)

    # ── Voce 4: Righe classificate (% righe del mese senza needs_review) ──
    tot_righe = len(righe_mese)
    da_controllare = sum(1 for r in righe_mese if r.get("needs_review"))
    if tot_righe == 0:
        pct_classificate = 0
        classificate_ok = False
    else:
        pct_classificate = round((tot_righe - da_controllare) / tot_righe * 100)
        classificate_ok = da_controllare == 0

    # ── Indice: voci ATTIVE a peso uguale. Le voci binarie valgono 0/100;
    #    le righe usano la loro %. Senza fatture, le righe valgono 0. Le voci
    #    spente nel configuratore non pesano (e non compaiono nella card). ──
    _score = {
        "fatture": 100 if fatture_ok else 0,
        "fatturato": 100 if fatturato_ok else 0,
        "personale": 100 if personale_ok else 0,
        "classificate": pct_classificate if tot_righe else 0,
    }
    _attive = [k for k in _score if k not in voci_spente]
    # Se l'utente ha spento TUTTE le voci, l'indice non e' misurabile: 100 (verde),
    # niente da completare per sua scelta.
    indice = round(sum(_score[k] for k in _attive) / len(_attive)) if _attive else 100

    if indice >= 80:
        colore = "verde"
    elif indice >= 50:
        colore = "giallo"
    else:
        colore = "rosso"

    _voci_tutte = {
        "fatture": SaluteVoce(
            key="fatture",
            label="Fatture caricate",
            ok=fatture_ok,
            dettaglio=fatture_dett,
            cta_page="/analisi-fatture",
        ),
        "fatturato": SaluteVoce(
            key="fatturato",
            label="Fatturato inserito",
            ok=fatturato_ok,
            dettaglio=f"{mese_completo_label.capitalize()} inserito" if fatturato_ok
                      else f"Manca {mese_completo_label}",
            cta_page="/margini",
        ),
        "personale": SaluteVoce(
            key="personale",
            label="Costo personale inserito",
            ok=personale_ok,
            dettaglio=f"{mese_completo_label.capitalize()} inserito" if personale_ok
                      else f"Manca {mese_completo_label}",
            cta_page="/margini",
        ),
        "classificate": SaluteVoce(
            key="classificate",
            label="Righe classificate",
            ok=classificate_ok,
            dettaglio="Tutte le righe sono classificate" if classificate_ok
                      else (f"{da_controllare} righe da controllare" if tot_righe
                            else "Nessuna riga da classificare"),
            # Deep-link al tab Articoli gia' filtrato sulle righe da controllare,
            # quando ce ne sono; pagina liscia altrimenti.
            cta_page=("/analisi-fatture?tab=articoli&verifica=1"
                      if da_controllare else "/analisi-fatture"),
        ),
    }
    voci = [_voci_tutte[k] for k in _voci_tutte if k not in voci_spente]

    return SaluteResponse(
        indice=indice, colore=colore, mese_label=mese_label, voci=voci
    )


@app.get(
    "/api/home/alert-prezzi",
    response_model=AlertPrezziResponse,
    summary="Alert prezzi per impatto €/mese (prodotti + tag, food&beverage)",
    tags=["Home"],
    dependencies=[Depends(_verify_worker_key)],
)
def home_alert_prezzi(authorization: Optional[str] = Header(None)) -> AlertPrezziResponse:
    """Motore live degli alert prezzi ordinati per impatto economico mensile.

    Solo Food & Beverage, soglia di rilevanza automatica (frazione della spesa
    food del periodo), monitora prodotti e custom tag. Tutto calcolato nel
    backend (price_impact_service); la Home si limita a mostrare.
    """
    from services.price_impact_service import calcola_alert_prezzi_impatto

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        return AlertPrezziResponse(count=0, alerts=[], top=None)

    try:
        res = calcola_alert_prezzi_impatto(user_id, ristorante_id, supabase_client=sb)
    except Exception as exc:
        logger.warning("home_alert_prezzi: calcolo fallito: %s", exc)
        return AlertPrezziResponse(count=0, alerts=[], top=None)

    alerts = [AlertPrezzo(**a) for a in (res.get("alerts") or [])]
    top = res.get("top")
    return AlertPrezziResponse(
        count=int(res.get("count") or 0),
        alerts=alerts,
        top=AlertPrezzo(**top) if top else None,
    )


# Cache in-memoria dei KPI Home: i conti cambiano lentamente, un TTL breve
# abbatte il carico (query + aggregazioni) anche con centinaia di clienti che
# riaprono la Home. Niente tabella DB: sopravvive senza migration, e al massimo
# si perde al redeploy (ricalcolo trasparente). Chiave = "{ristorante}:{anno}:{mese}".
_HOME_KPI_CACHE: Dict[str, tuple] = {}
_HOME_KPI_TTL = 120.0  # secondi


def _invalidate_home_kpi_cache(ristorante_id: Optional[str] = None) -> None:
    """Invalida la cache KPI Home (tutto, o solo un ristorante).

    Va chiamata quando cambiano i dati che alimentano i KPI (inserimento
    fatturato/personale/centri, upload fatture): senza questo la card "I tuoi
    conti" restava ferma fino al TTL (2 min) mostrando numeri stantii anche dopo
    l'inserimento — l'utente vedeva il briefing aggiornarsi ma il MOL no. La
    chiave include anno:mese, quindi per un singolo ristorante togliamo tutte le
    sue entry (mese mostrato + eventuali mesi vicini precaricati nel fallback).
    """
    if ristorante_id is None:
        _HOME_KPI_CACHE.clear()
        return
    prefisso = f"{ristorante_id}:"
    for k in [k for k in _HOME_KPI_CACHE if k.startswith(prefisso)]:
        _HOME_KPI_CACHE.pop(k, None)


def _kpi_periodo(margini_anno: dict, costi_fb: dict, costi_spese: dict, mese: int) -> dict:
    """Compone i 4 KPI per un mese di calendario.

    Fonte universale: margini_mensili (fatturato + MOL, gli stessi della pagina
    Margini) e costi food/spese dalle fatture aggregate per mese. Nessun cliente
    usa i ricavi giornalieri, quindi il mese e' l'unica fotografia affidabile.
    """
    row = margini_anno.get(mese, {}) or {}
    fatturato = (
        float(row.get("fatturato_iva10") or 0)
        + float(row.get("fatturato_iva22") or 0)
        + float(row.get("altri_ricavi_noiva") or 0)
    )
    fb = float(costi_fb.get(mese) or 0) + float(row.get("altri_costi_fb") or 0)
    spese = float(costi_spese.get(mese) or 0) + float(row.get("altri_costi_spese") or 0)
    # Costo personale: stessa fonte e formula della pagina Margini, cosi' il
    # conto economico della Home torna esattamente (Fatturato - F&B - Personale
    # - Spese = MOL). Senza questa voce il MOL non quadrava con le righe mostrate.
    personale = (
        float(row.get("costo_dipendenti") or 0)
        + float(row.get("costo_personale_extra") or 0)
    )
    mol = float(row.get("mol") or 0)
    food_cost_pct = round(fb / fatturato * 100, 1) if fatturato > 0 else None
    return {
        "fatturato": round(fatturato, 2),
        "food_cost_pct": food_cost_pct,
        "costo_personale": round(personale, 2),
        "spese_generali": round(spese, 2),
        "mol": round(mol, 2),
        # Mese con ricavi ma SENZA alcun costo automatico (food + spese = 0): il
        # MOL e' fatturato - personale, non un margine reale. Un ristorante ha
        # sempre food cost -> e' un mese a dati incompleti, non una buona notizia
        # da festeggiare (il briefing non deve dire "+172%!" su costi mancanti).
        "costi_mancanti": fatturato > 0 and fb <= 0 and spese <= 0,
        "has_data": fatturato > 0 or fb > 0 or spese > 0 or personale > 0,
    }


@app.get(
    "/api/home/kpi",
    response_model=HomeKpiResponse,
    summary="KPI live Home — fatturato, food cost %, spese generali, MOL",
    tags=["Home"],
    dependencies=[Depends(_verify_worker_key)],
)
def home_kpi(authorization: Optional[str] = Header(None)) -> HomeKpiResponse:
    """Fotografia dei conti dell'ULTIMO MESE COMPLETO, con confronto.

    Fonte: margini_mensili (fatturato + MOL, come la pagina Margini) e costi
    food/spese dalle fatture. E' l'unica fonte affidabile: nessun cliente usa i
    ricavi giornalieri. Confronto vs il mese precedente (frecce ↑↓).
    """
    import time as _time
    from datetime import date as _date

    _MESI_IT = [
        "", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
    ]
    _vuoto = HomeKpiResponse(
        periodo_label="", is_mese_in_corso=False, fatturato=0.0,
        food_cost_pct=None, costo_personale=0.0, spese_generali=0.0,
        mol=0.0, has_data=False,
    )

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        return _vuoto

    oggi = _oggi_rome()
    cache_key = f"{ristorante_id}:{oggi.year}:{oggi.month}"
    cached = _HOME_KPI_CACHE.get(cache_key)
    if cached and (_time.monotonic() - cached[0]) < _HOME_KPI_TTL:
        return cached[1]

    from services.margine_service import (
        carica_margini_anno,
        calcola_costi_automatici_per_anno_sql,
    )

    def _dati_anno(anno: int):
        try:
            m = carica_margini_anno(user_id, ristorante_id, anno)
            # Variante SQL (RPC): aggrega i costi food/spese lato DB invece del
            # full-load + pandas. home_kpi puo' toccare 2 anni (mostrato + confronto)
            # -> evita 2 full-load di tutte le righe fattura. Ha fallback pandas
            # interno, quindi non puo' rompersi.
            fb, sp = calcola_costi_automatici_per_anno_sql(user_id, ristorante_id, anno)
            return m, fb, sp
        except Exception as exc:
            logger.warning("home_kpi: caricamento anno %s fallito: %s", anno, exc)
            return {}, {}, {}

    cache_anni: dict = {}

    def _anno(anno: int):
        if anno not in cache_anni:
            cache_anni[anno] = _dati_anno(anno)
        return cache_anni[anno]

    # Parti dall'ultimo mese completo (mese precedente) e, se vuoto, vai indietro
    # fino a 6 mesi: cosi' mostriamo sempre l'ultima fotografia reale disponibile.
    mese_usato = anno_usato = None
    kpi = None
    mm, aa = oggi.month - 1, oggi.year
    if mm == 0:
        mm, aa = 12, oggi.year - 1
    for _ in range(6):
        margini, costi_fb, costi_spese = _anno(aa)
        cand = _kpi_periodo(margini, costi_fb, costi_spese, mm)
        if cand["has_data"]:
            kpi, mese_usato, anno_usato = cand, mm, aa
            break
        mm -= 1
        if mm == 0:
            mm, aa = 12, aa - 1

    if kpi is None:
        return _vuoto

    # ── Confronto col mese precedente a quello mostrato ──
    def _delta_pct(curr: float, prev: float) -> Optional[float]:
        if prev and prev != 0:
            return round((curr - prev) / abs(prev) * 100, 1)
        return None

    cmp_mese, cmp_anno = mese_usato - 1, anno_usato
    if cmp_mese == 0:
        cmp_mese, cmp_anno = 12, anno_usato - 1
    c_margini, c_fb, c_spese = _anno(cmp_anno)
    kpi_cmp = _kpi_periodo(c_margini, c_fb, c_spese, cmp_mese)

    confronto_label = None
    fatturato_delta = food_cost_delta = personale_delta = spese_delta = mol_delta = None
    if kpi_cmp["has_data"]:
        confronto_label = f"vs {_MESI_IT[cmp_mese].lower()}"
        fatturato_delta = _delta_pct(kpi["fatturato"], kpi_cmp["fatturato"])
        personale_delta = _delta_pct(kpi["costo_personale"], kpi_cmp["costo_personale"])
        spese_delta = _delta_pct(kpi["spese_generali"], kpi_cmp["spese_generali"])
        mol_delta = _delta_pct(kpi["mol"], kpi_cmp["mol"])
        if kpi["food_cost_pct"] is not None and kpi_cmp["food_cost_pct"] is not None:
            food_cost_delta = round(kpi["food_cost_pct"] - kpi_cmp["food_cost_pct"], 1)

    # Mese con costi mancanti: MOL, food cost e spese non sono reali. Non mostriamo
    # le variazioni "in meglio" (un +172% di MOL accanto a un food cost 0% e' una
    # bugia: e' solo l'effetto dei costi assenti). La card espone costi_mancanti
    # cosi' la Home spiega il perche'. Fatturato e personale (inseriti a mano)
    # restano confrontabili.
    if kpi.get("costi_mancanti"):
        mol_delta = None
        food_cost_delta = None
        spese_delta = None

    # ── Sparkline: MOL mese per mese dell'anno mostrato, da gennaio al mese
    #    mostrato. Solo i mesi con dati (un mese senza dati non e' uno zero reale,
    #    spezzerebbe la linea con un falso crollo). Riusa i margini gia' caricati
    #    in cache_anni via _anno() -> nessuna query in piu'. Lista vuota se c'e'
    #    un solo punto (niente andamento da disegnare). ──
    spark_margini, spark_fb, spark_spese = _anno(anno_usato)
    mol_mensile: List[MolMensilePoint] = []
    for m in range(1, mese_usato + 1):
        p = _kpi_periodo(spark_margini, spark_fb, spark_spese, m)
        if p["has_data"]:
            mol_mensile.append(MolMensilePoint(mese=m, mol=p["mol"]))
    if len(mol_mensile) < 2:
        mol_mensile = []

    resp = HomeKpiResponse(
        periodo_label=_MESI_IT[mese_usato],
        is_mese_in_corso=False,
        fatturato=kpi["fatturato"],
        food_cost_pct=kpi["food_cost_pct"],
        costo_personale=kpi["costo_personale"],
        spese_generali=kpi["spese_generali"],
        mol=kpi["mol"],
        has_data=kpi["has_data"],
        confronto_label=confronto_label,
        fatturato_delta_pct=fatturato_delta,
        food_cost_delta_pp=food_cost_delta,
        personale_delta_pct=personale_delta,
        spese_delta_pct=spese_delta,
        mol_delta_pct=mol_delta,
        costi_mancanti=bool(kpi.get("costi_mancanti")),
        mol_mensile=mol_mensile,
        mol_mensile_anno=anno_usato if mol_mensile else None,
    )
    # Eviction opportunistica delle entry scadute: la chiave include anno:mese,
    # quindi col passare dei giorni si accumulerebbero chiavi morte mai rimosse
    # (la cache cresceva senza limite). Pulendo ad ogni miss restano solo le
    # entry vive — costo trascurabile (poche chiavi per cliente).
    now = _time.monotonic()
    for k in [k for k, v in _HOME_KPI_CACHE.items() if (now - v[0]) >= _HOME_KPI_TTL]:
        _HOME_KPI_CACHE.pop(k, None)
    _HOME_KPI_CACHE[cache_key] = (now, resp)
    return resp


@app.get(
    "/api/home/config",
    response_model=ConfigResponse,
    summary="Configurazione assistente Home — nome + interruttori avvisi",
    tags=["Home"],
    dependencies=[Depends(_verify_worker_key)],
)
def home_config_get(authorization: Optional[str] = Header(None)) -> ConfigResponse:
    """Legge la configurazione dell'assistente per il ristorante corrente.

    Default AI-first: tutti gli avvisi attivi. nome_referente prende prima
    l'override del configuratore, poi quello impostato lato admin su users.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)

    nome = ""
    disabled: set = set()
    chat_ai_enabled = True
    solo_preferiti = False
    if ristorante_id:
        pref = _get_assistant_preferences(ristorante_id, sb)
        if pref:
            nome = str(pref.get("nome_referente") or "")
            td = pref.get("topics_disabled") or []
            if isinstance(td, list):
                disabled = {str(t) for t in td}
            if pref.get("chat_ai_enabled") is not None:
                chat_ai_enabled = bool(pref["chat_ai_enabled"])
            solo_preferiti = bool(pref.get("alert_prezzi_solo_preferiti"))

    if not nome:
        nome = str(user.get("nome_referente") or "")

    # Limite chat dal piano EFFETTIVO (sede attiva, fallback account). DEVE usare
    # la stessa risoluzione dell'endpoint chat, altrimenti il "ti restano N" mostrato
    # in Home non combacia col limite realmente applicato. (0 = free, chat off)
    chat_limite = _chat_limite_per_piano(_resolve_piano_effettivo(user, sb))

    # Domande gia' fatte oggi, solo se la chat e' disponibile (piano > 0 e attiva):
    # evita una query inutile per i piani free / chat spenta.
    domande_oggi = 0
    if chat_limite > 0 and chat_ai_enabled:
        domande_oggi = _chat_domande_oggi(ristorante_id, str(user["id"]), sb)

    # Soglia alert prezzi (per-utente): qui si IMPOSTA quando scatta l'avviso.
    try:
        from services.db_service import get_price_alert_threshold
        price_alert_threshold = get_price_alert_threshold(str(user["id"]))
    except Exception as exc:
        logger.warning("home_config_get: lettura soglia alert fallita: %s", exc)
        price_alert_threshold = 5.0

    topics = [
        ConfigTopic(key=key, label=label, enabled=key not in disabled, bloccato=bloccato, descrizione=descrizione)
        for (key, label, bloccato, descrizione) in _CONFIG_TOPICS
    ]
    return ConfigResponse(
        nome_referente=nome, topics=topics,
        chat_ai_enabled=chat_ai_enabled, chat_limite_giorno=chat_limite,
        chat_domande_oggi=domande_oggi,
        price_alert_threshold=price_alert_threshold,
        alert_prezzi_solo_preferiti=solo_preferiti,
    )


@app.post(
    "/api/home/config",
    response_model=ConfigResponse,
    summary="Salva la configurazione assistente Home",
    tags=["Home"],
    dependencies=[Depends(_verify_worker_key)],
)
def home_config_post(
    body: ConfigUpdateRequest,
    authorization: Optional[str] = Header(None),
) -> ConfigResponse:
    """Salva nome + avvisi spenti. I topic bloccati non vengono mai salvati
    come spenti (restano sempre attivi). Upsert per ristorante.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    bloccati = {k for (k, _l, b, _d) in _CONFIG_TOPICS if b}
    validi = {k for (k, _l, _b, _d) in _CONFIG_TOPICS}
    disabled = [
        t for t in (body.topics_disabled or [])
        if t in validi and t not in bloccati
    ]
    nome = (body.nome_referente or "").strip() or None

    from datetime import datetime as _dt2, timezone as _tz2
    record = {
        "ristorante_id": ristorante_id,
        "nome_referente": nome,
        "topics_disabled": disabled,
        "updated_at": _dt2.now(_tz2.utc).isoformat(),
    }
    # chat_ai_enabled: aggiornato solo se passato (None = non toccare).
    if body.chat_ai_enabled is not None:
        record["chat_ai_enabled"] = bool(body.chat_ai_enabled)
    # alert_prezzi_solo_preferiti: aggiornato solo se passato (None = non toccare).
    if body.alert_prezzi_solo_preferiti is not None:
        record["alert_prezzi_solo_preferiti"] = bool(body.alert_prezzi_solo_preferiti)

    try:
        sb.table("assistant_preferences").upsert(
            record, on_conflict="ristorante_id"
        ).execute()
    except Exception as exc:
        logger.error("home_config_post: salvataggio fallito: %s", exc)
        raise HTTPException(status_code=500, detail="Salvataggio fallito")

    # Le preferenze appena salvate guidano nome, topic spenti e (via toggle) i
    # segnali live mostrati: invalida entrambe le cache cosi' la Home riflette
    # subito il cambiamento invece di aspettare il TTL.
    _invalidate_assist_pref_cache(ristorante_id)
    _LIVE_SEGNALI_CACHE.pop(ristorante_id, None)

    # Cambiare quali prodotti generano avvisi (preferiti vs Pareto) cambia il
    # briefing di oggi -> invalidalo cosi' si rigenera con la nuova logica.
    if body.alert_prezzi_solo_preferiti is not None:
        try:
            from services.daily_briefing_service import invalidate_today_briefing
            invalidate_today_briefing(str(user["id"]), ristorante_id, sb)
        except Exception as exc:
            logger.warning("home_config_post: invalidazione briefing (preferiti) fallita: %s", exc)

    # Soglia alert prezzi (per-utente). Qui e' l'UNICO punto che la imposta: in
    # pagina Prezzi e' solo un filtro di visualizzazione. Cambiarla cambia quali
    # rincari diventano avvisi -> invalida il briefing di oggi.
    soglia = 5.0
    try:
        from services.db_service import get_price_alert_threshold, set_price_alert_threshold
        if body.price_alert_threshold is not None:
            set_price_alert_threshold(str(user["id"]), float(body.price_alert_threshold), sb)
            try:
                from services.daily_briefing_service import invalidate_today_briefing
                invalidate_today_briefing(str(user["id"]), ristorante_id, sb)
            except Exception as exc:
                logger.warning("home_config_post: invalidazione briefing fallita: %s", exc)
        soglia = get_price_alert_threshold(str(user["id"]))
    except Exception as exc:
        logger.warning("home_config_post: soglia alert non aggiornata: %s", exc)

    disabled_set = set(disabled)
    topics = [
        ConfigTopic(key=key, label=label, enabled=key not in disabled_set, bloccato=bloccato, descrizione=descrizione)
        for (key, label, bloccato, descrizione) in _CONFIG_TOPICS
    ]
    chat_ai = True if body.chat_ai_enabled is None else bool(body.chat_ai_enabled)
    # Piano EFFETTIVO (sede attiva, fallback account): coerente con l'endpoint chat.
    chat_limite = _chat_limite_per_piano(_resolve_piano_effettivo(user, sb))
    domande_oggi = 0
    if chat_limite > 0 and chat_ai:
        domande_oggi = _chat_domande_oggi(ristorante_id, str(user["id"]), sb)
    # Rileggi la flag effettiva: il body puo' non averla passata (None=non toccare),
    # quindi il valore corrente sta nel record salvato o resta quello esistente.
    solo_preferiti = False
    try:
        rr = (
            sb.table("assistant_preferences").select("alert_prezzi_solo_preferiti")
            .eq("ristorante_id", ristorante_id).limit(1).execute()
        )
        if rr.data:
            solo_preferiti = bool(rr.data[0].get("alert_prezzi_solo_preferiti"))
    except Exception:
        if body.alert_prezzi_solo_preferiti is not None:
            solo_preferiti = bool(body.alert_prezzi_solo_preferiti)

    return ConfigResponse(
        nome_referente=str(nome or ""), topics=topics,
        chat_ai_enabled=chat_ai, chat_limite_giorno=chat_limite,
        chat_domande_oggi=domande_oggi,
        price_alert_threshold=soglia,
        alert_prezzi_solo_preferiti=solo_preferiti,
    )


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


def _resolve_sede_attiva(user: Dict[str, Any], supabase_client) -> tuple[Optional[str], Optional[str]]:
    """(id, nome_ristorante) della sede attiva del cliente.

    Per i clienti multi-sede la testata deve mostrare la sede SELEZIONATA, non il
    nome account (users.nome_ristorante = prima sede). Gira nel layout di OGNI
    pagina autenticata (via /api/auth/me) -> deve costare AL PIU' una query.

    Strategia a 1 query:
      - se conosciamo gia' l'id della sede attiva (ultimo_ristorante_id) leggiamo
        id+nome in un colpo;
      - altrimenti prendiamo la prima sede attiva (id+nome) sempre in 1 query;
      - nessuna sede -> nome account (0 query in piu').

    Nota: ultimo_ristorante_id qui e' gia' FRESCO — _resolve_user_from_token lo
    rilegge dal DB ad ogni richiesta, scavalcando la cache di sessione (vedi li').
    """
    explicit = user.get("ristorante_id") or user.get("ultimo_ristorante_id")
    try:
        if explicit:
            resp = (
                supabase_client.table("ristoranti")
                .select("id, nome_ristorante")
                .eq("id", str(explicit))
                .single()
                .execute()
            )
            row = resp.data or {}
            if row:
                return str(row["id"]), (row.get("nome_ristorante") or user.get("nome_ristorante"))
            # id stantio (sede eliminata): ricadi sulla prima sede sotto.
        uid = user.get("id")
        if uid:
            resp = (
                supabase_client.table("ristoranti")
                .select("id, nome_ristorante")
                .eq("user_id", uid)
                .eq("attivo", True)
                .order("created_at")
                .limit(1)
                .execute()
            )
            if resp.data:
                r = resp.data[0]
                return str(r["id"]), (r.get("nome_ristorante") or user.get("nome_ristorante"))
    except Exception:
        pass
    return (str(explicit) if explicit else None), user.get("nome_ristorante")


def _resolve_piano_effettivo(user: Dict[str, Any], supabase_client) -> str:
    """Piano tariffario EFFETTIVO del cliente nel modello piano-per-sede.

    Il piano vive sulla SEDE attiva (ristoranti.piano). Se la sede non ha un piano
    proprio (NULL, transizione in corso) si EREDITA da users.piano. Se nemmeno
    quello c'e', default 'base'. Mai solleva: il piano guida limiti chat/fatture e
    un errore qui non deve bloccare l'endpoint chiamante.
    """
    fallback = (user.get("piano") or "base")
    try:
        rid = _resolve_ristorante_id(user, supabase_client)
        if rid:
            resp = (
                supabase_client.table("ristoranti")
                .select("piano")
                .eq("id", rid)
                .single()
                .execute()
            )
            sede_piano = (resp.data or {}).get("piano")
            if sede_piano:
                return str(sede_piano).lower().strip()
        # Sede senza piano proprio: eredita dall'account.
        if not user.get("piano"):
            urow = (
                supabase_client.table("users")
                .select("piano")
                .eq("id", user.get("id"))
                .single()
                .execute()
            )
            fallback = (urow.data or {}).get("piano") or "base"
    except Exception:
        pass
    return str(fallback).lower().strip()


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


_FATTURE_ROWS_CACHE: Dict[str, tuple] = {}  # key -> (expires_at, rows)
# TTL corto: abbatte i 4 full-scan dello STESSO caricamento pagina (che avvengono
# in pochi secondi) senza tenere dati stale a lungo dopo una modifica categoria/
# cestino dell'utente. Invalidazione esplicita su upload + cambio categoria singolo;
# per gli altri update (batch/cestino) ci si affida al TTL corto.
_FATTURE_ROWS_TTL = 15.0  # secondi


def _invalidate_fatture_rows_cache(ristorante_id: Optional[str] = None) -> None:
    """Invalida la cache righe fatture (tutto, o solo un ristorante)."""
    if ristorante_id is None:
        _FATTURE_ROWS_CACHE.clear()
        return
    for k in [k for k in _FATTURE_ROWS_CACHE if k.startswith(f"{ristorante_id}::")]:
        _FATTURE_ROWS_CACHE.pop(k, None)


def _fetch_fatture_rows(
    supabase_client,
    ristorante_id: str,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Recupera righe fattura filtrate con paginazione interna per superare il limite Supabase di 1000.

    Cache TTL in-process (90s) chiavata sui parametri: aprire un tab faceva 4
    scansioni complete della tabella (KPI corrente+precedente, articoli+pivot)
    senza riuso. App di analisi non-critica -> un ritardo di 90s e' accettabile.
    Invalidata su upload via _invalidate_fatture_rows_cache.
    """
    import time as _time
    cache_key = f"{ristorante_id}::{data_da}::{data_a}::{tipo_prodotti}::{search}"
    _now = _time.time()
    _cached = _FATTURE_ROWS_CACHE.get(cache_key)
    if _cached is not None and _cached[0] > _now:
        return _cached[1]

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
    _FATTURE_ROWS_CACHE[cache_key] = (_now + _FATTURE_ROWS_TTL, all_rows)
    return all_rows


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
            .select("anno,mese,modalita,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti")
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
            "coperti": (int(r["coperti"]) if r.get("coperti") is not None else None),
        }
    return out


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


# ═══════════════════════════════════════════════════════════════════════════
# PREZZI — estratto in services/routers/prezzi.py
# (_load_num_documento_map resta qui: condiviso con la sezione FATTURE)
# ═══════════════════════════════════════════════════════════════════════════

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


def _calcola_costi_auto_per_periodo(sb, ristorante_id: str, mesi_target: list) -> dict:
    """Aggrega costi auto F&B/Spese per TUTTI i mesi del periodo in UNA passata.

    Prima get_margini_analisi chiamava _calcola_costi_auto_per_mese mese-per-mese:
    12 scansioni della tabella fatture per un anno. Qui carichiamo le righe
    dell'intero range una volta sola e raggruppiamo per (anno, mese) in Python.
    Ritorna {(anno, mese): (fb_tot, spese_tot)}.
    """
    from calendar import monthrange
    if not mesi_target:
        return {}

    y0, m0 = min(mesi_target)
    y1, m1 = max(mesi_target)
    data_da = f"{y0}-{m0:02d}-01"
    last_day = monthrange(y1, m1)[1]
    data_a = f"{y1}-{m1:02d}-{last_day:02d}"

    spese_gen_categorie = {
        "SERVIZI E CONSULENZE", "UTENZE E LOCALI",
        "MANUTENZIONE E ATTREZZATURE", "MATERIALE DI CONSUMO",
    }

    acc: dict = {(y, m): [0.0, 0.0] for (y, m) in mesi_target}
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
            # data di competenza (fallback documento) -> (anno, mese)
            _dt = str(r.get("data_competenza") or r.get("data_documento") or "")[:7]
            try:
                yy, mm = int(_dt[:4]), int(_dt[5:7])
            except (ValueError, IndexError):
                continue
            bucket = acc.get((yy, mm))
            if bucket is None:
                continue
            cat = str(r.get("categoria") or "")
            try:
                tot = float(r.get("totale_riga") or 0)
            except (TypeError, ValueError):
                tot = 0.0
            if cat in spese_gen_categorie:
                bucket[1] += tot
            elif cat and cat != "📝 NOTE E DICITURE":
                bucket[0] += tot
        if len(rows) < page_size:
            break
        page += 1

    return {k: (round(v[0], 2), round(v[1], 2)) for k, v in acc.items()}


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


# ═══════════════════════════════════════════════════════════════════════════
# RICAVI (giornalieri, batch, import-xls, modalita + parser gestionale)
#   -> estratto in services/routers/ricavi.py
#   I parser sono importati da li' anche da worker/email_queue_processor.py
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# AUTH — Reset password
# ═══════════════════════════════════════════════════════════════════════════


class ResetRequestBody(BaseModel):
    email: str


class ResetConfirmBody(BaseModel):
    token: str
    password: str
    # GDPR Art. 7(1): valorizzato dal flusso di onboarding (primo accesso), dove
    # l'utente accetta esplicitamente l'informativa privacy. Resta False per il
    # semplice reset password di un account già attivato (nessun nuovo consenso).
    privacy_accepted: bool = False


@app.post("/api/auth/reset-request", tags=["Auth"])
def reset_password_request(body: ResetRequestBody, request: Request):
    """Invia email con link di reset. Non richiede auth — qualsiasi email può richiederlo.
    Risponde sempre con successo generico per non rivelare se l'email è registrata.
    """
    from services.auth_service import invia_codice_reset
    # Rate limit per IP: impedisce di spammare il servizio email variando l'email.
    _check_rate_limit(request.client.host if request.client else request.headers.get("X-Forwarded-For", "unknown").split(",")[0].strip())
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email non valida")
    ok, msg = invia_codice_reset(email)
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/api/auth/reset-confirm", tags=["Auth"])
def reset_password_confirm(body: ResetConfirmBody, request: Request):
    """Verifica token e imposta nuova password."""
    from services.auth_service import imposta_password_da_token
    # Rate limit per IP: throttla i tentativi di conferma (anti-abuso sul token).
    _check_rate_limit(request.client.host if request.client else request.headers.get("X-Forwarded-For", "unknown").split(",")[0].strip())
    token = (body.token or "").strip()
    password = body.password or ""
    if not token or not password:
        raise HTTPException(status_code=400, detail="Token e password obbligatori")
    ok, msg, _ = imposta_password_da_token(
        token, password, privacy_accepted=body.privacy_accepted
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


# ═══════════════════════════════════════════════════════════════════════════
# TAG — estratto in services/routers/tag.py (montato con include_router in fondo)
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# SCADENZIARIO + /api/ricavi/notifica-mancante — estratti in services/routers/scadenziario.py
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# CESTINO + soft-delete FATTURE -> services/routers/cestino.py
# ACCOUNT -> services/routers/account.py
# ═══════════════════════════════════════════════════════════════════════════

# ===========================================================================
# ADMIN -> estratto in services/routers/admin.py (montato con include_router in fondo).
# _verify_admin e i model/endpoint admin sono nel router. Restano QUI solo i due
# helper condivisi col worker (_run_agent_notturno li usa): _admin_emails_set e
# _log_review_action. Il router admin li importa da questo modulo.
# ===========================================================================

def _admin_emails_set() -> set:
    raw = os.getenv("ADMIN_EMAILS", _DEFAULT_ADMIN_EMAILS)
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _log_review_action(
    sb,
    attore: str,
    azione: str,
    categoria_a: str,
    ids_fatture: list,
    descrizione: str = "",
    categoria_da: str = "",
    nota: str = "",
) -> Optional[int]:
    """Scrive una riga in ai_review_log. Ritorna l'id inserito o None in caso di errore."""
    try:
        res = sb.table("ai_review_log").insert({
            "attore": attore,
            "azione": azione,
            "descrizione": descrizione[:200] if descrizione else "",
            "categoria_da": categoria_da or "",
            "categoria_a": categoria_a,
            "ids_fatture": ids_fatture,
            "righe_count": len(ids_fatture),
            "nota": nota[:200] if nota else "",
        }).execute()
        return (res.data[0]["id"] if res.data else None)
    except Exception as exc:
        logger.warning("_log_review_action failed: %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# WORKSPACE — estratto in services/routers/workspace.py (montato in fondo).
# _ore_turno resta qui sotto perche' condiviso col router margini.
# ═══════════════════════════════════════════════════════════════════════════

def _ore_turno(t: dict) -> float:
    """Calcola le ore TOTALI di un turno.

    Modello: le ore extra sono AGGIUNTIVE, non un sottoinsieme.
      - mensile=True: ore_dichiarate (gia' totale ord+extra dalla busta paga).
      - giornaliero: ore dagli orari (= ordinarie del turno) + ore_extra del giorno.

    Tutti i consumer ricavano l'ordinario come (ore_totali - ore_extra), quindi
    questa definizione mantiene corretto sia il totale sia lo split ord/extra.
    Usato da Personale e Margini.
    """
    if t.get("mensile"):
        try:
            return round(float(t.get("ore_dichiarate") or 0), 2)
        except (TypeError, ValueError):
            return 0.0
    from datetime import datetime as _dt
    def slot_ore(inizio: Optional[str], fine: Optional[str]) -> float:
        if not inizio or not fine:
            return 0.0
        try:
            i = _dt.strptime(inizio[:5], "%H:%M")
            f = _dt.strptime(fine[:5], "%H:%M")
            minuti = (f - i).seconds // 60
            return round(minuti / 60, 2)
        except Exception:
            return 0.0
    ore_orari = slot_ore(t.get("ora_inizio"), t.get("ora_fine")) + slot_ore(t.get("ora_inizio2"), t.get("ora_fine2"))
    try:
        extra = float(t.get("ore_extra") or 0)
    except (TypeError, ValueError):
        extra = 0.0
    return round(ore_orari + extra, 2)


# ═══════════════════════════════════════════════════════════════════════════
# ROUTER PER DOMINIO — estratti da questo file (split god file, vedi services/routers/)
# Montati qui in fondo: app e tutti gli helper condivisi sono gia' definiti, cosi'
# i router possono importarli senza ciclo. Comportamento HTTP invariato.
# ═══════════════════════════════════════════════════════════════════════════
from services.routers.tag import router as _tag_router  # noqa: E402
from services.routers.scadenziario import router as _scadenziario_router  # noqa: E402
from services.routers.cestino import router as _cestino_router  # noqa: E402
from services.routers.account import router as _account_router  # noqa: E402
from services.routers.prezzi import router as _prezzi_router  # noqa: E402
from services.routers.ricavi import router as _ricavi_router  # noqa: E402
from services.routers.fatture import router as _fatture_router  # noqa: E402
from services.routers.margini import router as _margini_router  # noqa: E402
from services.routers.workspace import router as _workspace_router  # noqa: E402
from services.routers.admin import router as _admin_router  # noqa: E402
from services.routers.gruppo import router as _gruppo_router  # noqa: E402
app.include_router(_tag_router)
app.include_router(_scadenziario_router)
app.include_router(_cestino_router)
app.include_router(_account_router)
app.include_router(_prezzi_router)
app.include_router(_ricavi_router)
app.include_router(_fatture_router)
app.include_router(_margini_router)
app.include_router(_workspace_router)
app.include_router(_admin_router)
app.include_router(_gruppo_router)


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    _reload = os.getenv("WORKER_RELOAD", "false").lower() == "true"
    # Multi-worker solo in produzione (Linux/Railway), impostando WORKER_WEB_CONCURRENCY.
    # In locale Windows resta a 1 worker (il multi-worker su Windows e' problematico)
    # e comunque non e' compatibile con reload.
    _workers = int(os.getenv("WORKER_WEB_CONCURRENCY", "1"))

    uvicorn.run(
        "services.fastapi_worker:app",
        host="0.0.0.0",
        port=int(os.getenv("WORKER_PORT", "8000")),
        reload=_reload,
        workers=_workers if (_workers > 1 and not _reload) else None,
        log_level="info",
    )
