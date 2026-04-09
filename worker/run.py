#!/usr/bin/env python3
r"""
worker/run.py — Entry point del worker fatture_queue
═════════════════════════════════════════════════════════════════════════════
Usato da GitHub Actions e opzionalmente da terminale locale.

USO LOCALE:
    # Attiva venv e imposta env vars
    .venv\Scripts\Activate.ps1
    $env:SUPABASE_URL              = "https://vthikmfpywilukizputn.supabase.co"
    $env:SUPABASE_SERVICE_ROLE_KEY = "eyJ..."   # da Supabase Dashboard → Settings → API
    python worker/run.py

    # Opzionale — Invoicetronic API key per fallback download XML
    $env:INVOICETRONIC_API_KEY = "..."

ENV VARS:
    SUPABASE_URL                  obbligatorio
    SUPABASE_SERVICE_ROLE_KEY     obbligatorio (service_role, non anon key)
    INVOICETRONIC_API_KEY         opzionale (solo per fallback xml_url)
    WORKER_BATCH_SIZE             default 10
    WORKER_XML_RETENTION_HOURS    default 24  (GDPR purge)
    WORKER_STALE_LOCK_MINUTES     default 10  (lock recovery)
    WORKER_ID_PREFIX              default "gh-action"
    WORKER_POLL_INTERVAL_SECONDS  default 15  (attesa tra cicli a coda vuota)
    WORKER_ERROR_BACKOFF_SECONDS  default 30  (backoff iniziale su errore)
    WORKER_MAX_BACKOFF_SECONDS    default 300 (cap backoff su errore)

EXIT CODES:
    0  — ciclo completato (anche se coda vuota)
    1  — env vars mancanti o errore DB critico
═════════════════════════════════════════════════════════════════════════════
"""

import logging
import os
import sys
import time

# Root progetto (usato per sys.path e .env)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Carica variabili da .env (se presente) ──────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass  # python-dotenv non installato: usa solo variabili di sistema

# ─── Logging ─────────────────────────────────────────────────────────────────
# Forza UTF-8 su Windows per evitare UnicodeEncodeError con cp1252
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker.run")

WORKER_POLL_INTERVAL_SECONDS = int(os.environ.get("WORKER_POLL_INTERVAL_SECONDS", "15"))
WORKER_ERROR_BACKOFF_SECONDS = int(os.environ.get("WORKER_ERROR_BACKOFF_SECONDS", "30"))
WORKER_MAX_BACKOFF_SECONDS = int(os.environ.get("WORKER_MAX_BACKOFF_SECONDS", "300"))

# ─── Assicura PROJECT_ROOT in sys.path ────────────────────────────────────────
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─── Compatibilità SUPABASE_KEY → SUPABASE_SERVICE_ROLE_KEY ─────────────────
# Il .env usa SUPABASE_KEY; il worker usa SUPABASE_SERVICE_ROLE_KEY
if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY") and os.environ.get("SUPABASE_KEY"):
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = os.environ["SUPABASE_KEY"]


def _check_env() -> bool:
    """Verifica env vars obbligatorie prima di connettere al DB."""
    missing = []
    if not os.environ.get("SUPABASE_URL"):
        missing.append("SUPABASE_URL")
    if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        logger.error(
            "❌ Env vars obbligatorie mancanti: %s\n"
            "   Imposta queste variabili prima di avviare il worker.\n"
            "   Vedi worker/run.py per le istruzioni.",
            ", ".join(missing),
        )
        return False
    return True


def _ensure_streamlit_available() -> bool:
    """Garantisce import streamlit in contesto worker CLI.

    Se streamlit non e' installato nella venv locale, installa uno stub minimale
    solo per consentire import dei moduli condivisi con l'app UI.
    """
    try:
        import streamlit  # noqa: F401
        return True
    except Exception:
        try:
            from worker.streamlit_stub import install_streamlit_stub
            install_streamlit_stub()
            logger.warning(
                "streamlit non disponibile: attivato stub compatibile per worker CLI"
            )
            return True
        except Exception as exc:
            logger.exception("Impossibile attivare fallback streamlit stub: %s", exc)
            return False


def main() -> int:
    logger.info("==== worker fatture_queue - loop continuo ====")

    # ── Validazione env vars ──────────────────────────────────────────────────
    if not _check_env():
        return 1

    # ── Import qui (dopo sys.path setup) ─────────────────────────────────────
    if not _ensure_streamlit_available():
        return 1

    try:
        from worker.queue_processor import run_cycle
    except Exception as exc:
        logger.exception("Impossibile importare queue_processor: %s", exc)
        return 1

    consecutive_failures = 0

    while True:
        cycle_started_at = time.monotonic()
        try:
            stats = run_cycle()
            stats.log_summary()
            consecutive_failures = 0

            sleep_seconds = 1 if stats.batch_claimed > 0 else WORKER_POLL_INTERVAL_SECONDS
            logger.info(
                "worker sleep=%ss elapsed=%.1fs claimed=%d done=%d retry=%d dead=%d skip=%d",
                sleep_seconds,
                time.monotonic() - cycle_started_at,
                stats.batch_claimed,
                stats.done,
                stats.retry_scheduled,
                stats.dead,
                stats.skipped,
            )
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            logger.info("Stop richiesto - chiusura pulita")
            return 0
        except Exception as exc:
            consecutive_failures += 1
            backoff_seconds = min(
                WORKER_ERROR_BACKOFF_SECONDS * consecutive_failures,
                WORKER_MAX_BACKOFF_SECONDS,
            )
            logger.exception(
                "Errore ciclo worker (failure=%d): %s",
                consecutive_failures,
                exc,
            )
            time.sleep(backoff_seconds)


if __name__ == "__main__":
    sys.exit(main())
