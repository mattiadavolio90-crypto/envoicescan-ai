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

EXIT CODES:
    0  — ciclo completato (anche se coda vuota)
    1  — env vars mancanti o errore DB critico
═════════════════════════════════════════════════════════════════════════════
"""

import logging
import os
import sys
import time

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker.run")

# ─── Assicura PROJECT_ROOT in sys.path ────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


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


def main() -> int:
    t_start = time.monotonic()
    logger.info("════ worker fatture_queue — avvio ════")

    # ── Validazione env vars ──────────────────────────────────────────────────
    if not _check_env():
        return 1

    # ── Import qui (dopo sys.path setup) ─────────────────────────────────────
    try:
        from worker.queue_processor import run_cycle
    except Exception as exc:
        logger.exception("Impossibile importare queue_processor: %s", exc)
        return 1

    # ── Esegui ciclo ─────────────────────────────────────────────────────────
    try:
        stats = run_cycle()
    except Exception as exc:
        logger.exception("Errore critico durante run_cycle: %s", exc)
        return 1

    elapsed = time.monotonic() - t_start
    stats.log_summary()

    logger.info(
        "════ worker completato in %.1fs — done=%d retry=%d dead=%d skip=%d ════",
        elapsed,
        stats.done,
        stats.retry_scheduled,
        stats.dead,
        stats.skipped,
    )

    # Exit 0 sempre (anche coda vuota): GitHub Actions non deve fallire per coda vuota
    return 0


if __name__ == "__main__":
    sys.exit(main())
