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
  - services.routers.ricavi._detect_gestionale_version
  - services.routers.ricavi._parse_generico (file senza colonna ragione sociale)

Per Passbi v1 usa un parser dedicato (_parse_passbi_email) che — a differenza
della UI — smista ogni riga sul ristorante giusto via ragione sociale, così un
singolo file di una catena alimenta tutti i locali. Ownership garantita dal
join su ristoranti.user_id.

Flusso per ogni ciclo:
  1. claim batch atomico via RPC claim_ricavi_email_batch (FOR UPDATE SKIP LOCKED)
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
        from services.routers.ricavi import (
            _detect_gestionale_version,
            _parse_generico,
        )
    except Exception as exc:
        logger.error("email-cycle: import parser fallito: %s", exc)
        stats.errors.append(f"import parser: {exc}")
        return stats

    # ── 1. Claim batch (atomico: FOR UPDATE SKIP LOCKED via RPC) ────────────────
    # Prima era SELECT + UPDATE separati: due worker concorrenti potevano claimare
    # lo stesso record -> doppio import dello stesso XLS ricavi. La RPC
    # claim_ricavi_email_batch (allineata a claim_batch_for_processing delle fatture)
    # fa il claim in un solo statement atomico e recupera i lock stantii.
    try:
        result = supabase.rpc(
            "claim_ricavi_email_batch",
            {"p_worker_id": worker_id, "p_batch_size": EMAIL_BATCH_SIZE},
        ).execute()
        items = result.data or []
    except Exception as exc:
        logger.error("email-cycle: errore claim batch (RPC): %s", exc)
        return stats

    if not items:
        return stats

    # attempt_count e' gia' stato incrementato dalla RPC al claim.
    stats.claimed = len(items)

    # ── 2. Elabora ogni record ────────────────────────────────────────────────
    for item in items:
        record_id   = item["id"]
        filename    = item["attachment_name"] or "ricavi.xlsx"
        path        = item["storage_path"]
        ristorante  = item["ristorante_id"]
        user_id_val = item["user_id"]
        # attempt_count gia' incrementato dalla RPC di claim: e' il numero del
        # tentativo corrente (non sommare di nuovo +1).
        attempts    = item["attempt_count"]
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
                # Parser email-aware: smista ogni riga sul ristorante giusto via
                # ragione sociale (catena multi-locale). `ristorante` (dal mittente)
                # è solo il fallback per righe senza ragione sociale mappata.
                per_ristorante, errors, parsed_rows = _parse_passbi_email(
                    raw_df, ristorante, user_id_val, supabase
                )
            else:
                # Formato generico: niente colonna ragione sociale → tutto sul mittente.
                generic_items, errors, parsed_rows = _parse_generico(raw_df)
                per_ristorante = {ristorante: generic_items} if generic_items else {}

        except Exception as exc:
            err = f"parsing fallito: {exc}"
            logger.warning("email-cycle [%s]: %s", record_id, err)
            _schedule_retry(supabase, record_id, err, attempts, max_att)
            stats.retry_scheduled += 1
            stats.errors.append(f"{filename}: {err}")
            continue

        if not per_ristorante:
            _mark_dead(supabase, record_id, "Nessuna riga valida: " + "; ".join(errors[:3]))
            stats.dead += 1
            stats.errors.append(f"{filename}: nessuna riga valida")
            continue

        # ── 2c. Upsert in ricavi_giornalieri (uno o più ristoranti) ────────
        try:
            imported = 0
            for rid, parsed_items in per_ristorante.items():
                imported += _upsert_ricavi(supabase, rid, user_id_val, parsed_items, filename, version)
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


# ─── Parser Passbi email-aware (multi-ristorante) ─────────────────────────────

class _RicavoRow:
    """Riga aggregata per giorno. Stesso shape di RicavoUpsertRequest ma standalone."""
    __slots__ = ("data", "fatturato_iva10", "fatturato_iva22", "altri_ricavi_noiva", "coperti")

    def __init__(self, data, iva10, iva22, altri, coperti=None):
        self.data = data
        self.fatturato_iva10 = iva10
        self.fatturato_iva22 = iva22
        self.altri_ricavi_noiva = altri
        self.coperti = coperti


def _parse_passbi_email(raw_df, fallback_ristorante_id: str, user_id, supabase):
    """Parser Passbi v1 per il flusso email, multi-ristorante.

    Differenza dal _parse_passbi_v1 della UI: quello collassa tutto su un solo
    ristorante (l'import manuale ha il token di un ristorante). Qui il worker ha
    service_role + user_id, quindi può smistare ogni riga sul ristorante corretto
    via ragione sociale — così un singolo file di una catena alimenta tutti i locali.

    Sicurezza: ogni ristorante_id di destinazione deve appartenere allo stesso
    user_id della coda. Righe che mappano a ristoranti di altri utenti vengono
    scartate (difesa contro un mapping errato che scriverebbe su dati altrui).

    Ritorna (per_ristorante: dict[rid -> list[_RicavoRow]], errors, parsed_rows).
    """
    import pandas as pd
    from datetime import date as _date, datetime as _dt
    from collections import defaultdict

    headers = None
    header_idx = None
    for i, row in raw_df.iterrows():
        vals = [str(v).strip().lower() for v in row.tolist()]
        if any("data" in v for v in vals):
            header_idx = i
            headers = [str(v).strip() for v in raw_df.iloc[i].tolist()]
            break
    if header_idx is None:
        return {}, ["Header colonne non trovato nel file Passbi"], len(raw_df)

    data_rows = raw_df.iloc[header_idx + 1:].reset_index(drop=True)
    parsed_rows = len(data_rows)

    def _find_col(names):
        for idx, h in enumerate(headers):
            norm = h.lower().replace("\n", " ").replace("  ", " ").strip()
            for n in names:
                if n in norm:
                    return idx
        return None

    idx_data = _find_col(["data"])
    idx_ragione = _find_col(["ragione sociale", "azienda"])
    idx_tipo = _find_col(["tipo documento", "testata", "tipo_documento"])
    idx_iva = _find_col(["codice", "iva"])
    idx_importo = _find_col(["importo", "totale"])
    idx_coperti = _find_col(["coperti"])  # colonna opzionale

    if idx_data is None or idx_importo is None:
        return {}, ["Colonne Data o Importo non trovate nel file Passbi"], parsed_rows

    # Mapping ragione_sociale → ristorante_id, filtrato sui ristoranti di QUESTO utente.
    # Il join su ristoranti.user_id è la barriera di sicurezza: una ragione sociale
    # che punta a un ristorante di un altro utente non entra nemmeno nel dizionario.
    ragione_map = {}
    try:
        owned = supabase.table("ristoranti").select("id").eq("user_id", user_id).execute()
        owned_ids = {str(r["id"]) for r in (owned.data or [])}
    except Exception as exc:
        return {}, [f"Lookup ristoranti utente fallito: {exc}"], parsed_rows

    # Nessun ristorante per questo utente → niente destinazione valida.
    # Senza questo, righe non mappate ricadrebbero sul mittente senza controllo.
    if not owned_ids:
        return {}, [f"Utente {user_id} non ha ristoranti: import scartato"], parsed_rows

    try:
        mp = supabase.table("ricavi_ragione_sociale_map").select("ragione_sociale_norm,ristorante_id").execute()
        for r in (mp.data or []):
            rid = str(r["ristorante_id"])
            if rid in owned_ids:
                ragione_map[str(r["ragione_sociale_norm"]).strip().lower()] = rid
    except Exception as exc:
        return {}, [f"Lookup mapping ragione sociale fallito: {exc}"], parsed_rows

    def _parse_date(v):
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

    def _to_float(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        try:
            return max(0.0, float(str(v).replace(",", ".")))
        except Exception:
            return 0.0

    aggregato = defaultdict(lambda: {"iva10": 0.0, "iva22": 0.0, "altri": 0.0, "coperti": 0.0})
    coperti_seen = set()  # giorni con almeno una riga coperti valorizzata
    unmapped = set()
    foreign = set()
    errors = []

    for _, row in data_rows.iterrows():
        vals = row.tolist()

        data_iso = _parse_date(vals[idx_data] if idx_data < len(vals) else None)
        if data_iso is None:
            continue
        importo = _to_float(vals[idx_importo] if idx_importo < len(vals) else None)
        if importo <= 0:
            continue

        raw_ragione = ""
        if idx_ragione is not None and idx_ragione < len(vals):
            raw_ragione = str(vals[idx_ragione]).strip()

        if not raw_ragione or raw_ragione.lower() in ("nan", "none"):
            target = fallback_ristorante_id  # riga senza ragione sociale → mittente
        else:
            target = ragione_map.get(raw_ragione.lower().strip())
            if target is None:
                # Non mappata o mappata a ristorante di un altro utente.
                # Fallback al mittente solo se appartiene a questo utente (sempre vero).
                unmapped.add(raw_ragione)
                target = fallback_ristorante_id

        # Difesa: la destinazione (anche il fallback) deve appartenere all'utente.
        # owned_ids è garantito non vuoto qui sopra.
        if target not in owned_ids:
            foreign.add(str(target))
            continue

        tipo_doc = ""
        if idx_tipo is not None and idx_tipo < len(vals):
            tipo_doc = str(vals[idx_tipo]).strip().lower()
        raw_iva = vals[idx_iva] if (idx_iva is not None and idx_iva < len(vals)) else None
        iva_str = "" if raw_iva is None or (isinstance(raw_iva, float) and pd.isna(raw_iva)) else str(raw_iva).strip()

        key = (target, data_iso)

        # Coperti: somma su tutti i tipi documento del giorno (frazionari per riga).
        if idx_coperti is not None and idx_coperti < len(vals):
            cop_val = vals[idx_coperti]
            if not (cop_val is None or (isinstance(cop_val, float) and pd.isna(cop_val))):
                try:
                    aggregato[key]["coperti"] += float(str(cop_val).replace(",", "."))
                    coperti_seen.add(key)
                except (ValueError, TypeError):
                    pass

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

    if unmapped:
        errors.append(f"Ragioni sociali non mappate (usato ristorante del mittente): {', '.join(sorted(unmapped))}")
    if foreign:
        errors.append(f"{len(foreign)} ristoranti di altri utenti ignorati (sicurezza ownership)")

    per_ristorante = defaultdict(list)
    for (rid, data_iso), b in aggregato.items():
        if b["iva10"] + b["iva22"] + b["altri"] <= 0:
            continue
        coperti_giorno = round(b["coperti"]) if (rid, data_iso) in coperti_seen else None
        per_ristorante[rid].append(_RicavoRow(
            data_iso, round(b["iva10"], 4), round(b["iva22"], 4), round(b["altri"], 4),
            coperti_giorno,
        ))

    return dict(per_ristorante), errors, parsed_rows


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
        coperti = getattr(it, "coperti", None)
        coperti = max(0, int(coperti)) if coperti is not None else None
        rows.append({
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "data": d,
            "fatturato_iva10": iva10,
            "fatturato_iva22": iva22,
            "altri_ricavi_noiva": altri,
            "coperti": coperti,
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
