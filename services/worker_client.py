"""Worker HTTP client — proxy tra Streamlit e il FastAPI worker (Fase 3).

Quando WORKER_BASE_URL è impostato, le richieste vengono instradate al worker.
In assenza della variabile o in caso di errore HTTP, il fallback è automatico
sulle implementazioni locali (classifica_con_ai / estrai_dati_da_xml).

Uso in Docker:
    ohyeah-app  →  POST http://worker:8000/api/classify
                →  POST http://worker:8000/api/parse

Uso in sviluppo locale (senza Docker):
    WORKER_BASE_URL non impostato → funzioni locali usate direttamente.
"""

import io
import os
import logging
from contextvars import ContextVar
from typing import Any, List, Optional

import requests

logger = logging.getLogger("fci_app")

# API key condivisa con il worker FastAPI (opzionale — dev mode: skip se assente)
_WORKER_KEY = os.environ.get("WORKER_SECRET_KEY", "")

# Timeout per chiamate al worker (secondi)
_CLASSIFY_TIMEOUT = 90   # OpenAI può richiedere 30-60s per batch grandi
_PARSE_TIMEOUT = 30

# Override per-richiesta del path locale (vedi force_local_worker_path sotto):
# ContextVar invece di mutare os.environ, che e' globale al PROCESSO. FastAPI
# esegue le route sync in un threadpool che eredita il ContextVar corrente
# (stesso pattern di ai_service.set_ai_context) — quindi due upload concorrenti
# di tenant diversi non si "rubano" a vicenda lo stato, cosa che accadeva prima
# quando il worker faceva os.environ.pop("WORKER_BASE_URL") per la durata della
# chiamata: un secondo upload nello stesso processo poteva vedere la variabile
# gia' rimossa da un altro, o vedersela ripristinare a meta' esecuzione.
_force_local: ContextVar[bool] = ContextVar("worker_client_force_local", default=False)


def force_local_worker_path(active: bool) -> None:
    """Forza (True) o ripristina (False) il path locale per il thread/task corrente."""
    _force_local.set(active)


def _worker_base_url() -> str:
    """Restituisce WORKER_BASE_URL dall'ambiente, o stringa vuota se non configurato
    o se force_local_worker_path(True) e' attivo per la richiesta corrente."""
    if _force_local.get():
        return ""
    return os.environ.get("WORKER_BASE_URL", "").rstrip("/")


def classifica_via_worker(
    descrizioni: List[str],
    fornitori: Optional[List[str]] = None,
    iva: Optional[List[int]] = None,
    hint: Optional[List[Optional[str]]] = None,
    user_id: Optional[str] = None,
    ristorante_id: Optional[str] = None,
) -> List[str]:
    """Classifica prodotti via worker HTTP (con fallback locale su classifica_con_ai).

    Args:
        descrizioni: Lista descrizioni prodotti da classificare.
        fornitori:   Lista fornitori corrispondenti (opzionale).
        iva:         Lista aliquote IVA % (opzionale).
        hint:        Lista hint categoria (opzionale, può contenere None).
        user_id:     ID utente — usato dal worker per caricare la memoria classificazioni.
        ristorante_id: ID ristorante — usato per rate limit giornaliero AI.

    Returns:
        Lista di stringhe categoria, allineata con `descrizioni`.
    """
    base = _worker_base_url()
    if base:
        try:
            resp = requests.post(
                f"{base}/api/classify",
                json={
                    "descrizioni": descrizioni,
                    "fornitori": fornitori,
                    "iva": iva,
                    "hint": hint,
                    "user_id": user_id,
                    "ristorante_id": ristorante_id,
                },
                headers={"X-Worker-Key": _WORKER_KEY} if _WORKER_KEY else {},
                timeout=_CLASSIFY_TIMEOUT,
            )
            # Non fare fallback su 4xx (errore del client, non del server)
            if 400 <= resp.status_code < 500:
                resp.raise_for_status()
            resp.raise_for_status()
            categorie = resp.json()["categorie"]
            logger.info(
                f"✅ Worker classify: {len(categorie)} prodotti"
                + (f" user_id={user_id}" if user_id else "")
            )
            return categorie
        except Exception as exc:
            logger.warning(
                f"⚠️ Worker classify non disponibile ({exc}), uso locale",
                exc_info=False,
            )

    # ── Fallback: classificazione locale diretta ──────────────────────────
    from services.ai_service import classifica_con_ai  # import locale per evitare circolarità
    return classifica_con_ai(
        descrizioni,
        lista_fornitori=fornitori,
        lista_iva=iva,
        lista_hint=hint,
        ristorante_id=ristorante_id,
    )


def classifica_via_worker_con_confidenza(
    descrizioni: List[str],
    fornitori: Optional[List[str]] = None,
    iva: Optional[List[int]] = None,
    hint: Optional[List[Optional[str]]] = None,
    user_id: Optional[str] = None,
    ristorante_id: Optional[str] = None,
) -> tuple:
    """Come classifica_via_worker, ma ritorna (categorie, confidenze) come tuple.

    Le confidenze sono 'alta', 'media' o 'bassa' (una per descrizione).
    Se il worker HTTP non supporta ancora la confidence, usa 'media' come default.
    """
    base = _worker_base_url()
    if base:
        try:
            resp = requests.post(
                f"{base}/api/classify",
                json={
                    "descrizioni": descrizioni,
                    "fornitori": fornitori,
                    "iva": iva,
                    "hint": hint,
                    "user_id": user_id,
                    "ristorante_id": ristorante_id,
                },
                headers={"X-Worker-Key": _WORKER_KEY} if _WORKER_KEY else {},
                timeout=_CLASSIFY_TIMEOUT,
            )
            if 400 <= resp.status_code < 500:
                resp.raise_for_status()
            resp.raise_for_status()
            payload = resp.json()
            categorie = payload["categorie"]
            # Retrocompatibilità: worker più vecchi non includono "confidenze"
            confidenze = payload.get("confidenze") or ["media"] * len(categorie)
            logger.info(
                f"✅ Worker classify (con confidenza): {len(categorie)} prodotti"
                + (f" user_id={user_id}" if user_id else "")
            )
            return categorie, confidenze
        except Exception as exc:
            logger.warning(
                f"⚠️ Worker classify non disponibile ({exc}), uso locale",
                exc_info=False,
            )

    # ── Fallback: classificazione locale diretta ──────────────────────────
    from services.ai_service import classifica_con_ai  # import locale per evitare circolarità
    return classifica_con_ai(
        descrizioni,
        lista_fornitori=fornitori,
        lista_iva=iva,
        lista_hint=hint,
        ristorante_id=ristorante_id,
        return_confidenze=True,
    )


def parse_file_via_worker(
    file: Any,
    nome_file: str,
    user_id: Optional[str] = None,
) -> List[Any]:
    """Parsa un file XML o P7M via worker HTTP (con fallback locale).

    Il worker gestisce internamente l'estrazione P7M→XML.

    Args:
        file:       File-like object (st.UploadedFile, BytesIO, ecc.) con attributo .name.
        nome_file:  Nome del file (usato per determinare estensione e inviare al worker).
        user_id:    ID utente — propagato al worker per memoria classificazioni.

    Returns:
        Lista di dict prodotti (stessa struttura di estrai_dati_da_xml).
    """
    base = _worker_base_url()
    if base:
        try:
            # Leggi il contenuto del file
            if hasattr(file, "read"):
                contents = file.read()
                if hasattr(file, "seek"):
                    file.seek(0)  # riavvolgi per eventuali usi successivi
            else:
                contents = bytes(file)

            resp = requests.post(
                f"{base}/api/parse",
                files={"file": (nome_file, contents, "application/octet-stream")},
                data={"user_id": user_id or ""},
                headers={"X-Worker-Key": _WORKER_KEY} if _WORKER_KEY else {},
                timeout=_PARSE_TIMEOUT,
            )
            # Non fare fallback su 4xx (formato non valido, ecc.)
            if 400 <= resp.status_code < 500:
                resp.raise_for_status()
            resp.raise_for_status()
            fatture = resp.json()["fatture"]
            logger.info(
                f"✅ Worker parse: {nome_file} → {len(fatture)} righe"
                + (f" user_id={user_id}" if user_id else "")
            )
            return fatture
        except Exception as exc:
            logger.warning(
                f"⚠️ Worker parse non disponibile ({exc}), uso locale",
                exc_info=False,
            )

    # ── Fallback: parsing locale diretto ─────────────────────────────────
    from services.invoice_service import estrai_dati_da_xml, estrai_xml_da_p7m
    if nome_file.endswith(".p7m"):
        xml_stream = estrai_xml_da_p7m(file)
        return estrai_dati_da_xml(xml_stream, user_id=user_id)
    return estrai_dati_da_xml(file, user_id=user_id)
