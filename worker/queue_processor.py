"""
worker/queue_processor.py
═════════════════════════════════════════════════════════════════════════════
Worker per elaborazione asincrona delle fatture ricevute via webhook.

Flusso per ogni ciclo:
  1. purge_processed_xml_content()    → GDPR cleanup (XML > 24h)
  2. release_stale_locks()            → libera worker bloccati > 10 min
  3. claim_batch_for_processing()     → acquisisce atomicamente N record
  4. Per ogni record:
       a. Legge xml_content da fatture_queue
       b. Chiama estrai_dati_da_xml() — parser esistente, zero duplicazione
       c. Chiama salva_fattura_processata() — insert in public.fatture
       d. mark_queue_item_done()       → status=done, xml nullificato (GDPR)
       e. Se errore → schedule_retry() con backoff esponenziale
  5. Ritorna stats del ciclo

Compatibilità:
  - Funziona sia da GitHub Actions che da terminale locale
  - Usa service_role key (bypass RLS) — mai anon key
  - Zero dipendenze da Streamlit: silent=True + user_id esplicito
  - Riutilizza invoice_service.py senza duplicare logica
═════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import io
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ─── Assicura che la root del progetto sia in sys.path ───────────────────────
# Necessario quando lo script viene eseguito da GitHub Actions (cwd = repo root)
# o da un percorso diverso.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from services import get_supabase_client
from services.invoice_service import estrai_dati_da_xml, salva_fattura_processata

logger = logging.getLogger(__name__)

# ─── Configurazione ───────────────────────────────────────────────────────────

BATCH_SIZE        = int(os.environ.get("WORKER_BATCH_SIZE", "10"))
XML_RETENTION_H   = int(os.environ.get("WORKER_XML_RETENTION_HOURS", "24"))
STALE_LOCK_MIN    = int(os.environ.get("WORKER_STALE_LOCK_MINUTES", "10"))
WORKER_ID_PREFIX  = os.environ.get("WORKER_ID_PREFIX", "gh-action")


# ─── Tipi di risultato ────────────────────────────────────────────────────────

@dataclass
class ItemResult:
    queue_id: int
    event_id: str
    status: str          # "done" | "retry" | "dead" | "skip"
    righe: int = 0
    error: str | None = None


@dataclass
class CycleStats:
    worker_id: str
    batch_claimed: int = 0
    done: int = 0
    retry_scheduled: int = 0
    dead: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.done + self.retry_scheduled + self.dead + self.skipped

    def log_summary(self) -> None:
        logger.info(
            "[worker=%s] Ciclo completato — claimed=%d done=%d retry=%d dead=%d skip=%d",
            self.worker_id,
            self.batch_claimed,
            self.done,
            self.retry_scheduled,
            self.dead,
            self.skipped,
        )
        for err in self.errors:
            logger.warning("[worker=%s] %s", self.worker_id, err)


# ─── Funzioni di manutenzione (chiamate RPC Supabase) ─────────────────────────

def _purge_xml(supabase, retention_hours: int) -> int:
    """Nullifica xml_content dei record done più vecchi di N ore (GDPR)."""
    try:
        res = supabase.rpc(
            "purge_processed_xml_content",
            {"p_retention_hours": retention_hours},
        ).execute()
        count = res.data or 0
        if count:
            logger.info("[maint] Purge GDPR: %d record xml nullificati", count)
        return count
    except Exception as exc:
        logger.warning("[maint] purge_processed_xml_content fallita: %s", exc)
        return 0


def _release_stale_locks(supabase, timeout_minutes: int) -> int:
    """Rilascia lock stale (worker crashati da più di N minuti)."""
    try:
        res = supabase.rpc(
            "release_stale_locks",
            {"p_timeout_minutes": timeout_minutes},
        ).execute()
        count = res.data or 0
        if count:
            logger.info("[maint] Stale locks rilasciati: %d", count)
        return count
    except Exception as exc:
        logger.warning("[maint] release_stale_locks fallita: %s", exc)
        return 0


def _claim_batch(supabase, worker_id: str, batch_size: int) -> list[dict[str, Any]]:
    """
    Acquisisce atomicamente fino a batch_size record pronti.
    Usa SELECT FOR UPDATE SKIP LOCKED → sicuro con worker paralleli.
    """
    res = supabase.rpc(
        "claim_batch_for_processing",
        {"p_worker_id": worker_id, "p_batch_size": batch_size},
    ).execute()
    return res.data or []


def _mark_done(supabase, queue_id: int, purge_xml: bool = True) -> None:
    supabase.rpc(
        "mark_queue_item_done",
        {"p_queue_id": queue_id, "p_purge_xml": purge_xml},
    ).execute()


def _schedule_retry(supabase, queue_id: int, error_msg: str) -> None:
    supabase.rpc(
        "schedule_retry",
        {"p_queue_id": queue_id, "p_error_msg": error_msg[:1000]},
    ).execute()


# ─── Elaborazione di un singolo item ─────────────────────────────────────────

def _process_item(supabase, item: dict[str, Any]) -> ItemResult:
    """
    Elabora un record di fatture_queue:
      1. Ottieni XML (da xml_content o xml_url come fallback)
      2. Parsa con estrai_dati_da_xml() — riuso diretto del parser esistente
      3. Salva in public.fatture con salva_fattura_processata()
      4. Segna come done o schedula retry

    Returns:
        ItemResult con esito dell'elaborazione
    """
    queue_id   = item["id"]
    event_id   = item["event_id"]
    user_id    = item.get("user_id")
    ristorante_id = item.get("ristorante_id")
    xml_content   = item.get("xml_content")
    xml_url       = item.get("xml_url")
    piva_raw      = item.get("piva_raw", "UNKNOWN")
    attempt       = item.get("attempt_count", 1)
    payload_meta  = item.get("payload_meta") or {}

    # ── Recupera XML ─────────────────────────────────────────────────────────
    if not xml_content:
        # xml_content è NULL: potrebbe essere stato purgato o non salvato
        if xml_url:
            # Tentativo fallback: ri-scarica da Invoicetronic
            # (solo se la API key è disponibile)
            xml_content = _fetch_xml_from_url(xml_url)
        if not xml_content:
            return ItemResult(
                queue_id=queue_id,
                event_id=event_id,
                status="retry",
                error=f"xml_content NULL e fallback url {'fallito' if xml_url else 'assente'} "
                      f"(attempt={attempt})",
            )

    # ── Costruisci un file-like per il parser ─────────────────────────────────
    # estrai_dati_da_xml() accetta UploadedFile (Streamlit) oppure BytesIO
    nome_file = payload_meta.get("nome_file") or f"webhook_{event_id}.xml"
    xml_bytes = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    xml_io    = _make_file_like(xml_bytes, nome_file)

    # ── Parsing XML ───────────────────────────────────────────────────────────
    try:
        dati_prodotti = estrai_dati_da_xml(xml_io)
    except Exception as exc:
        msg = f"Parsing XML fallito: {exc}"
        logger.error("[item=%d] %s", queue_id, msg)
        return ItemResult(queue_id=queue_id, event_id=event_id, status="retry", error=msg)

    if not dati_prodotti:
        # XML valido ma nessuna riga estratta (es. fattura senza DettaglioLinee)
        logger.warning("[item=%d] estrai_dati_da_xml ha restituito 0 righe — segno come done", queue_id)
        return ItemResult(queue_id=queue_id, event_id=event_id, status="done", righe=0)

    # ── Salva in public.fatture ───────────────────────────────────────────────
    if not user_id or not ristorante_id:
        msg = f"Tenant non risolto (user_id={user_id}, ristorante_id={ristorante_id}, piva={piva_raw})"
        logger.warning("[item=%d] %s", queue_id, msg)
        return ItemResult(queue_id=queue_id, event_id=event_id, status="retry", error=msg)

    try:
        result = salva_fattura_processata(
            nome_file=nome_file,
            dati_prodotti=dati_prodotti,
            supabase_client=supabase,
            silent=True,          # fuori Streamlit: no st.error/st.success
            ristoranteid=ristorante_id,
            user_id=user_id,      # passato esplicitamente (non via session_state)
        )
    except Exception as exc:
        msg = f"salva_fattura_processata eccezione: {exc}"
        logger.exception("[item=%d] %s", queue_id, msg)
        return ItemResult(queue_id=queue_id, event_id=event_id, status="retry", error=msg)

    if not result.get("success"):
        err = result.get("error", "unknown")
        return ItemResult(
            queue_id=queue_id, event_id=event_id, status="retry",
            error=f"salva_fattura_processata error={err}",
        )

    return ItemResult(
        queue_id=queue_id,
        event_id=event_id,
        status="done",
        righe=result.get("righe", 0),
    )


# ─── Utilità interne ─────────────────────────────────────────────────────────

class _FakeName:
    """Wrapper BytesIO con attributo .name (simula UploadedFile Streamlit)."""
    def __init__(self, data: bytes, name: str) -> None:
        self._buf  = io.BytesIO(data)
        self.name  = name

    def read(self, *a):  return self._buf.read(*a)
    def seek(self, *a):  return self._buf.seek(*a)
    def tell(self):      return self._buf.tell()
    def readable(self):  return True
    def getvalue(self):  return self._buf.getvalue()


def _make_file_like(data: bytes, name: str) -> "_FakeName":
    return _FakeName(data, name)


def _fetch_xml_from_url(url: str) -> str | None:
    """
    Fallback: ri-scarica XML da xml_url (es. dopo purge GDPR anticipata).
    Usa INVOICETRONIC_API_KEY dalle env vars se disponibile.
    """
    try:
        import urllib.request
        api_key = os.environ.get("INVOICETRONIC_API_KEY", "")
        req = urllib.request.Request(url)
        if api_key:
            import base64
            creds = base64.b64encode(f"{api_key}:".encode()).decode()
            req.add_header("Authorization", f"Basic {creds}")
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Fallback fetch xml_url fallito (%s): %s", url[:80], exc)
        return None


# ─── Entry point principale ───────────────────────────────────────────────────

def run_cycle() -> CycleStats:
    """
    Esegue un ciclo completo del worker:
      manutenzione → claim → elabora ogni item → stats

    Returns:
        CycleStats con i risultati del ciclo
    """
    worker_id = f"{WORKER_ID_PREFIX}-{uuid.uuid4().hex[:8]}"
    stats = CycleStats(worker_id=worker_id)

    supabase = get_supabase_client()

    # ── 1. Manutenzione ───────────────────────────────────────────────────────
    _purge_xml(supabase, XML_RETENTION_H)
    _release_stale_locks(supabase, STALE_LOCK_MIN)

    # ── 2. Claim batch ────────────────────────────────────────────────────────
    try:
        batch = _claim_batch(supabase, worker_id, BATCH_SIZE)
    except Exception as exc:
        logger.error("[worker=%s] claim_batch_for_processing fallita: %s", worker_id, exc)
        return stats

    stats.batch_claimed = len(batch)

    if not batch:
        logger.info("[worker=%s] Coda vuota — nessun record da elaborare", worker_id)
        return stats

    logger.info("[worker=%s] Claimati %d record", worker_id, len(batch))

    # ── 3. Elabora ogni item ──────────────────────────────────────────────────
    for item in batch:
        queue_id = item["id"]
        t0 = time.monotonic()

        try:
            result = _process_item(supabase, item)
        except Exception as exc:
            # Safety net: non deve mai crashare il ciclo
            logger.exception("[item=%d] Eccezione imprevista nel processor", queue_id)
            result = ItemResult(
                queue_id=queue_id,
                event_id=str(item.get("event_id", "?")),
                status="retry",
                error=f"Unhandled exception: {exc}",
            )

        elapsed = time.monotonic() - t0

        # ── Aggiorna stato in DB ───────────────────────────────────────────
        if result.status == "done":
            try:
                _mark_done(supabase, queue_id, purge_xml=True)
                stats.done += 1
                logger.info(
                    "[item=%d event=%s] Done — %d righe in %.1fs",
                    queue_id, result.event_id, result.righe, elapsed,
                )
            except Exception as exc:
                logger.error("[item=%d] mark_done fallita: %s", queue_id, exc)
                stats.errors.append(f"item={queue_id} mark_done={exc}")

        elif result.status == "retry":
            try:
                _schedule_retry(supabase, queue_id, result.error or "errore sconosciuto")
                # Controlla se è diventato dead (attempt >= max_attempts)
                updated = (
                    supabase.table("fatture_queue")
                    .select("status")
                    .eq("id", queue_id)
                    .single()
                    .execute()
                )
                final_status = (updated.data or {}).get("status", "failed")
                if final_status == "dead":
                    stats.dead += 1
                    logger.warning(
                        "[item=%d event=%s] DEAD — max tentativi raggiunto: %s",
                        queue_id, result.event_id, result.error,
                    )
                else:
                    stats.retry_scheduled += 1
                    logger.warning(
                        "[item=%d event=%s] Retry schedulato — %s",
                        queue_id, result.event_id, result.error,
                    )
            except Exception as exc:
                logger.error("[item=%d] schedule_retry fallita: %s", queue_id, exc)
                stats.errors.append(f"item={queue_id} schedule_retry={exc}")

        else:  # "skip" o altro
            stats.skipped += 1

    return stats
