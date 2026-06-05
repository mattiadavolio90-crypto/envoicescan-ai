"""
worker/email_queue_processor.py
═════════════════════════════════════════════════════════════════════════════
Processa la coda ricavi_email_queue: scarica gli XLS da Supabase Storage,
li parsa con i parser esistenti (Passbi v1 / generico) e fa l'upsert diretto
in ricavi_giornalieri con service_role_key.

NON passa per l'HTTP del worker FastAPI: quegli endpoint richiedono un token
di sessione utente (cookie), che un processo automatico non possiede. Qui
abbiamo ristorante_id + user_id dal record in coda (popolati dal mapping
ricavi_email_sender_map) e il service_role_key che bypassa RLS.

Riusa senza duplicare:
  - services.fastapi_worker._detect_gestionale_version
  - services.fastapi_worker._parse_passbi_v1
  - services.fastapi_worker._parse_generico

Flusso per ogni ciclo:
  1. claim batch (status pending/failed pronti)
  2. per ogni record:
       a. scarica XLS da Storage (bucket ricavi-xls)
       b. detect versione + parse → items
       c. upsert diretto in ricavi_giornalieri (trigger aggrega in margini_mensili)
       d. mark done / schedule_retry
  3. ritorna stats

ENV VARS:
  SUPABASE_URL                obbligatorio
  SUPABASE_SERVICE_ROLE_KEY   obbligatorio
  EMAIL_BATCH_SIZE            default 5
═════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import io
import logging
import os
import random
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STORAGE_BUCKET    = "ricavi-xls"
EMAIL_BATCH_SIZE  = int(os.environ.get("EMAIL_BATCH_SIZE", "5"))
_BACKOFF_BASE_SEC = 60
_BACKOFF_MAX_SEC  = 900


@dataclass
class EmailCycleStats:
    claimed: int = 0
    done: int = 0
    retry_scheduled: int = 0
    dead: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def log_summary(self) -> None:
        if self.claimed == 0:
            return
        logger.info(
            "email-cycle: claimed=%d done=%d retry=%d dead=%d skip=%d",
            self.claimed, self.done, self.retry_scheduled, self.dead, self.skipped,
        )
        for err in self.errors[:5]:
            logger.warning("email-cycle error: %s", err)


def run_email_cycle(supabase, worker_url: str = "", worker_secret: str = "") -> EmailCycleStats:
    """Processa un batch di ricavi_email_queue pending.

    worker_url/worker_secret sono accettati per compatibilità con la firma
    chiamata da run.py, ma non più usati (parsing e upsert sono in-process).
    """
    stats = EmailCycleStats()
    worker_id = f"email-worker-{os.getpid()}"

    # Import lazy dei parser (evita di caricare fastapi_worker se la coda è vuota)
    try:
        import pandas as pd
        from services.fastapi_worker import (
            _detect_gestionale_version,
            _parse_passbi_v1,
            _parse_generico,
        )
    except Exception as exc:
        logger.error("email-cycle: import parser fallito: %s", exc)
        stats.errors.append(f"import parser: {exc}")
        return stats

    # ── 1. Claim batch ────────────────────────────────────────────────────────
    try:
        result = (
            supabase.table("ricavi_email_queue")
            .select("id, email_sender, attachment_name, storage_path, ristorante_id, user_id, attempt_count, max_attempts")
            .in_("status", ["pending", "failed"])
            .lte("next_retry_at", "now()")
            .is_("locked_at", "null")
            .order("created_at")
            .limit(EMAIL_BATCH_SIZE)
            .execute()
        )
        items = result.data or []
    except Exception as exc:
        logger.error("email-cycle: errore claim batch: %s", exc)
        return stats

    if not items:
        return stats

    ids = [r["id"] for r in items]
    try:
        supabase.table("ricavi_email_queue").update({
            "status": "processing", "locked_at": "now()", "locked_by": worker_id,
        }).in_("id", ids).execute()
    except Exception as exc:
        logger.error("email-cycle: errore lock batch: %s", exc)
        return stats

    stats.claimed = len(items)

    # ── 2. Elabora ogni record ────────────────────────────────────────────────
    for item in items:
        record_id   = item["id"]
        filename    = item["attachment_name"] or "ricavi.xlsx"
        path        = item["storage_path"]
        ristorante  = item["ristorante_id"]
        user_id_val = item["user_id"]
        attempts    = item["attempt_count"] + 1
        max_att     = item["max_attempts"]

        if not path:
            _mark_dead(supabase, record_id, "storage_path NULL")
            stats.dead += 1
            stats.errors.append(f"{filename}: storage_path mancante")
            continue

        if not ristorante:
            _schedule_retry(supabase, record_id, "ristorante_id NULL — mittente non mappato", attempts, max_att)
            stats.retry_scheduled += 1
            continue

        # ── 2a. Scarica XLS da Storage ─────────────────────────────────────
        try:
            raw_bytes = bytes(supabase.storage.from_(STORAGE_BUCKET).download(path))
        except Exception as exc:
            err = f"download Storage fallito: {exc}"
            logger.warning("email-cycle [%s]: %s", record_id, err)
            _schedule_retry(supabase, record_id, err, attempts, max_att)
            stats.retry_scheduled += 1
            stats.errors.append(f"{filename}: {err}")
            continue

        # ── 2b. Parse ──────────────────────────────────────────────────────
        try:
            if filename.lower().endswith(".csv"):
                raw_df = pd.read_csv(io.BytesIO(raw_bytes), sep=None, engine="python", header=None)
            else:
                raw_df = pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl", header=None)

            if raw_df.empty:
                _mark_dead(supabase, record_id, "File vuoto")
                stats.dead += 1
                continue

            version = _detect_gestionale_version(raw_df)
            if version == "passbi_v1":
                parsed_items, errors, parsed_rows = _parse_passbi_v1(raw_df, ristorante, supabase)
            else:
                parsed_items, errors, parsed_rows = _parse_generico(raw_df)

        except Exception as exc:
            err = f"parsing fallito: {exc}"
            logger.warning("email-cycle [%s]: %s", record_id, err)
            _schedule_retry(supabase, record_id, err, attempts, max_att)
            stats.retry_scheduled += 1
            stats.errors.append(f"{filename}: {err}")
            continue

        if not parsed_items:
            _mark_dead(supabase, record_id, "Nessuna riga valida: " + "; ".join(errors[:3]))
            stats.dead += 1
            stats.errors.append(f"{filename}: nessuna riga valida")
            continue

        # ── 2c. Upsert in ricavi_giornalieri ───────────────────────────────
        try:
            imported = _upsert_ricavi(supabase, ristorante, user_id_val, parsed_items, filename, version)
        except Exception as exc:
            err = f"upsert DB fallito: {exc}"
            logger.warning("email-cycle [%s]: %s", record_id, err)
            _schedule_retry(supabase, record_id, err, attempts, max_att)
            stats.retry_scheduled += 1
            stats.errors.append(f"{filename}: {err}")
            continue

        # ── 2d. Mark done ──────────────────────────────────────────────────
        try:
            supabase.table("ricavi_email_queue").update({
                "status": "done", "imported_rows": imported, "processed_at": "now()",
                "locked_at": None, "locked_by": None, "last_error": None,
            }).eq("id", record_id).execute()
            logger.info("email-cycle [%s]: done — %d giorni importati da %s", record_id, imported, filename)
            stats.done += 1
        except Exception as exc:
            logger.error("email-cycle [%s]: errore mark done: %s", record_id, exc)
            stats.errors.append(f"{filename}: mark-done fallito: {exc}")

    return stats


# ─── Upsert diretto in ricavi_giornalieri ─────────────────────────────────────

def _upsert_ricavi(supabase, ristorante_id, user_id, parsed_items, filename, version) -> int:
    """Replica la logica di upsert_ricavi_batch ma con user_id esplicito.

    parsed_items: lista di RicavoGiornalieroItem (data, fatturato_iva10/22, altri).
    Ritorna il numero di giorni effettivamente scritti.
    """
    rows = []
    source_meta = {"filename": filename, "gestionale": version, "source_channel": "email"}
    for it in parsed_items:
        d = it.data
        if not d:
            continue
        iva10 = max(0.0, float(it.fatturato_iva10 or 0))
        iva22 = max(0.0, float(it.fatturato_iva22 or 0))
        altri = max(0.0, float(it.altri_ricavi_noiva or 0))
        if iva10 + iva22 + altri <= 0:
            continue
        rows.append({
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "data": d,
            "fatturato_iva10": iva10,
            "fatturato_iva22": iva22,
            "altri_ricavi_noiva": altri,
            "source": "email",
            "source_meta": source_meta,
        })

    if not rows:
        return 0

    resp = (
        supabase.table("ricavi_giornalieri")
        .upsert(rows, on_conflict="ristorante_id,data")
        .execute()
    )
    return len(resp.data or rows)


# ─── Helpers retry/dead ───────────────────────────────────────────────────────

def _schedule_retry(supabase, record_id: str, error: str, attempts: int, max_attempts: int) -> None:
    if attempts >= max_attempts:
        _mark_dead(supabase, record_id, error)
        return
    delay = min(_BACKOFF_BASE_SEC * (2 ** (attempts - 1)), _BACKOFF_MAX_SEC)
    jitter = delay * random.uniform(-0.25, 0.25)
    delay_secs = max(30, int(delay + jitter))
    try:
        supabase.table("ricavi_email_queue").update({
            "status": "failed", "attempt_count": attempts, "last_error": error[:500],
            "next_retry_at": f"now() + interval '{delay_secs} seconds'",
            "locked_at": None, "locked_by": None,
        }).eq("id", record_id).execute()
    except Exception as exc:
        logger.error("email-cycle: errore schedule_retry [%s]: %s", record_id, exc)


def _mark_dead(supabase, record_id: str, error: str) -> None:
    try:
        supabase.table("ricavi_email_queue").update({
            "status": "dead", "last_error": error[:500],
            "locked_at": None, "locked_by": None,
        }).eq("id", record_id).execute()
        logger.warning("email-cycle [%s]: dead — %s", record_id, error[:120])
    except Exception as exc:
        logger.error("email-cycle: errore mark_dead [%s]: %s", record_id, exc)
