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
    WORKER_POLL_INTERVAL_SECONDS      default 15    (attesa tra cicli a coda vuota)
    WORKER_ERROR_BACKOFF_SECONDS      default 30    (backoff iniziale su errore)
    WORKER_MAX_BACKOFF_SECONDS        default 300   (cap backoff su errore)
    WORKER_PURGE_INTERVAL_SECONDS     default 21600 (purge cestino ogni 6h)
    WORKER_RETENTION_INTERVAL_SECONDS default 86400 (retention fatture >2 anni ogni 24h)

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

# ─── Killswitch: WORKER_ENABLED=0 sospende il worker senza uscire ────────────
# Railway riavvierebbe il container se uscisse; con sleep infinito resta vivo
# ma senza consumare CPU o fare chiamate DB/API.
# Per riattivare: imposta WORKER_ENABLED=1 (o rimuovi la variabile) e redeploy.
#
# ATTENZIONE: con il worker in pausa la coda ricavi NON viene consumata e gli
# incassi dei clienti spariscono dall'app (incidente 9-11 giu 2026: killswitch
# lasciato attivo per sbaglio dopo un deploy). Il workflow ricavi_queue_monitor
# allarma via email se la coda resta bloccata, ma il killswitch va trattato
# come stato di manutenzione TEMPORANEO, mai permanente. Il loro qui sotto
# ribadisce ogni ora da quanto tempo siamo in pausa per renderlo evidente.
if os.environ.get("WORKER_ENABLED", "1").strip() in ("0", "false", "False", "no"):
    _paused_since = time.monotonic()
    while True:
        _hours_paused = int((time.monotonic() - _paused_since) // 3600)
        logger.warning(
            "⏸️  WORKER_ENABLED=0 — worker in PAUSA da %dh (killswitch attivo). "
            "La coda ricavi/fatture NON viene consumata. "
            "Per riattivare: imposta WORKER_ENABLED=1 e rideploya.",
            _hours_paused,
        )
        time.sleep(3600)  # dorme 1h alla volta, nessuna chiamata esterna

WORKER_POLL_INTERVAL_SECONDS = int(os.environ.get("WORKER_POLL_INTERVAL_SECONDS", "15"))
WORKER_ERROR_BACKOFF_SECONDS = int(os.environ.get("WORKER_ERROR_BACKOFF_SECONDS", "30"))
WORKER_MAX_BACKOFF_SECONDS = int(os.environ.get("WORKER_MAX_BACKOFF_SECONDS", "300"))
WORKER_PURGE_INTERVAL_SECONDS = int(os.environ.get("WORKER_PURGE_INTERVAL_SECONDS", str(6 * 3600)))  # default 6h
WORKER_RETENTION_INTERVAL_SECONDS = int(os.environ.get("WORKER_RETENTION_INTERVAL_SECONDS", str(24 * 3600)))  # default 24h

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

    # Import manutenzioni periodiche su fatture
    try:
        from services.db_service import purge_cestino_scaduto, purge_fatture_retention
    except Exception as exc:
        logger.warning("Impossibile importare funzioni manutenzione fatture: %s", exc)
        purge_cestino_scaduto = None
        purge_fatture_retention = None

    # Import ciclo email ricavi (parsing + upsert in-process, usa solo Supabase).
    # Killswitch: EMAIL_CYCLE_ENABLED=0 lo disattiva.
    try:
        from worker.email_queue_processor import run_email_cycle
        _email_cycle_enabled = os.environ.get("EMAIL_CYCLE_ENABLED", "1").strip() not in ("0", "false", "False", "no")
        if not _email_cycle_enabled:
            logger.info("email-cycle disabilitato via EMAIL_CYCLE_ENABLED=0")
    except Exception as exc:
        logger.warning("email-cycle non disponibile: %s", exc)
        run_email_cycle = None
        _email_cycle_enabled = False

    consecutive_failures = 0
    last_purge_time = 0.0
    last_retention_time = 0.0

    while True:
        cycle_started_at = time.monotonic()
        try:
            stats = run_cycle()
            stats.log_summary()
            consecutive_failures = 0

            # Ciclo email ricavi (ogni giro del worker, dopo le fatture)
            if _email_cycle_enabled and run_email_cycle:
                try:
                    from worker.queue_processor import get_supabase_client
                    _sb = get_supabase_client()
                    email_stats = run_email_cycle(_sb)
                    email_stats.log_summary()
                except Exception as email_exc:
                    logger.warning("email-cycle errore: %s", email_exc)

            # Purge periodico cestino fatture (ogni WORKER_PURGE_INTERVAL_SECONDS)
            now = time.monotonic()
            if purge_cestino_scaduto and (now - last_purge_time) >= WORKER_PURGE_INTERVAL_SECONDS:
                try:
                    purge_result = purge_cestino_scaduto()
                    if purge_result.get("righe_eliminate", 0) > 0:
                        logger.info(
                            "🗑️ Purge cestino: %d righe scadute eliminate",
                            purge_result["righe_eliminate"],
                        )
                except Exception as purge_exc:
                    logger.warning("Errore purge cestino: %s", purge_exc)
                last_purge_time = now

            # Retention fatture > 2 anni (batch sicuro da 500 righe, ogni 24h)
            if purge_fatture_retention and (now - last_retention_time) >= WORKER_RETENTION_INTERVAL_SECONDS:
                try:
                    retention_result = purge_fatture_retention(batch_size=500)
                    if retention_result.get("righe_eliminate", 0) > 0:
                        logger.info(
                            "🧹 Retention fatture: %d righe eliminate (%d dal cestino)",
                            retention_result["righe_eliminate"],
                            retention_result.get("righe_da_cestino", 0),
                        )
                except Exception as retention_exc:
                    logger.warning("Errore retention fatture: %s", retention_exc)
                last_retention_time = now

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
            # Backoff esponenziale + jitter per evitare thundering herd
            import random as _random
            _exp_factor = 2 ** min(consecutive_failures - 1, 8)
            _base = min(
                WORKER_ERROR_BACKOFF_SECONDS * _exp_factor,
                WORKER_MAX_BACKOFF_SECONDS,
            )
            backoff_seconds = _base * _random.uniform(0.5, 1.0)
            logger.exception(
                "Errore ciclo worker (failure=%d, backoff=%.1fs): %s",
                consecutive_failures,
                backoff_seconds,
                exc,
            )
            time.sleep(backoff_seconds)


if __name__ == "__main__":
    sys.exit(main())
