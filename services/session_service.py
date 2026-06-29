"""
Gestione sessioni multi-token (un utente -> N dispositivi attivi).

Sostituisce il modello a token singolo su users.session_token. Ogni login crea una
riga in public.sessioni; la validazione cerca qui e fa fallback alla vecchia colonna
per le sessioni create prima del deploy (vedi migration 20260606130000).

Funzioni pubbliche:
- crea_sessione(user_id, ...) -> token        : nuovo token + evict oltre il cap
- risolvi_sessione(token) -> user_id | None    : valida (attiva + non scaduta per inattività)
- tocca_sessione(token)                        : aggiorna last_seen_at (throttled)
- revoca_sessione(token) -> bool               : revoca la singola sessione (logout/exit)
"""

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from config.constants import (
    SESSION_INACTIVITY_HOURS,
    LAST_SEEN_WRITE_THROTTLE_SECONDS,
    MAX_SESSIONI_ATTIVE,
)
from config.logger_setup import get_logger

logger = get_logger('session')

# Throttle in-process per le scritture di last_seen_at: {token: last_write_epoch}.
_LAST_SEEN_THROTTLE: dict = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client(supabase_client=None):
    if supabase_client is not None:
        return supabase_client
    from services import get_supabase_client
    return get_supabase_client()


def crea_sessione(
    user_id: str,
    source: str = "login",
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
    supabase_client=None,
) -> str:
    """Crea una nuova sessione per l'utente e ritorna il token opaco.

    Dopo l'inserimento applica il cap MAX_SESSIONI_ATTIVE: se l'utente supera il
    numero di sessioni attive, revoca le più vecchie per last_seen_at (evict).
    """
    if not user_id:
        raise ValueError("user_id obbligatorio per crea_sessione")

    sb = _client(supabase_client)
    token = secrets.token_urlsafe(32)

    sb.table("sessioni").insert({
        "user_id": str(user_id),
        "token": token,
        "source": source,
        "user_agent": (user_agent or "")[:500] or None,
        "ip": (ip or "")[:100] or None,
    }).execute()

    _evict_oltre_cap(str(user_id), sb)
    return token


def _evict_oltre_cap(user_id: str, sb) -> None:
    """Revoca le sessioni attive più vecchie oltre il cap (per last_seen_at desc)."""
    try:
        resp = (
            sb.table("sessioni")
            .select("id")
            .eq("user_id", user_id)
            .is_("revoked_at", "null")
            .order("last_seen_at", desc=True)
            .execute()
        )
        rows = resp.data or []
        if len(rows) <= MAX_SESSIONI_ATTIVE:
            return
        da_revocare = [r["id"] for r in rows[MAX_SESSIONI_ATTIVE:]]
        sb.table("sessioni").update({"revoked_at": _now_iso()}).in_("id", da_revocare).execute()
        logger.info("Evict sessioni: revocate %d sessioni oltre il cap per user=%s", len(da_revocare), user_id)
    except Exception:
        logger.exception("Errore evict sessioni oltre il cap (non bloccante)")


def risolvi_sessione(token: str, supabase_client=None) -> Optional[str]:
    """Ritorna user_id se il token è una sessione attiva e non scaduta per inattività.

    Se la sessione è scaduta per inattività la revoca e ritorna None.
    Ritorna None anche se il token non esiste in `sessioni` (il chiamante applica
    il fallback legacy su users.session_token).
    """
    if not token:
        return None

    sb = _client(supabase_client)
    try:
        resp = (
            sb.table("sessioni")
            .select("id, user_id, last_seen_at")
            .eq("token", token)
            .is_("revoked_at", "null")
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("Errore lookup sessione")
        return None

    if not resp.data:
        return None

    row = resp.data[0]
    last_seen_raw = row.get("last_seen_at")
    if last_seen_raw:
        try:
            last_seen_dt = datetime.fromisoformat(str(last_seen_raw).replace("Z", "+00:00"))
            if last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
            scaduta = (datetime.now(timezone.utc) - last_seen_dt) > timedelta(hours=SESSION_INACTIVITY_HOURS)
        except (ValueError, TypeError):
            scaduta = True
    else:
        scaduta = True

    if scaduta:
        try:
            sb.table("sessioni").update({"revoked_at": _now_iso()}).eq("id", row["id"]).execute()
        except Exception:
            logger.exception("Errore revoca sessione scaduta")
        logger.info("Sessione scaduta per inattività (>%sh) revocata: user=%s", SESSION_INACTIVITY_HOURS, row.get("user_id"))
        return None

    return str(row["user_id"])


def tocca_sessione(token: str, supabase_client=None) -> None:
    """Aggiorna last_seen_at della sessione corrente, con throttle in-process."""
    if not token:
        return
    now = time.time()
    last = _LAST_SEEN_THROTTLE.get(token)
    if last is not None and (now - last) < LAST_SEEN_WRITE_THROTTLE_SECONDS:
        return
    _LAST_SEEN_THROTTLE[token] = now
    try:
        sb = _client(supabase_client)
        sb.table("sessioni").update({"last_seen_at": _now_iso()}).eq("token", token).is_("revoked_at", "null").execute()
    except Exception:
        logger.exception("Errore aggiornamento last_seen_at sessione (non bloccante)")


def revoca_tutte_sessioni(user_id: str, supabase_client=None, escludi_token: str | None = None) -> int:
    """Revoca le sessioni attive di un utente (logout globale: cambio password,
    trial scaduto, logout forzato di sicurezza). Ritorna il numero di sessioni revocate.

    `escludi_token`: se passato, NON revoca quella sessione (per il cambio password
    self-service: slogga gli altri dispositivi ma tiene attivo quello corrente).
    """
    if not user_id:
        return 0
    try:
        sb = _client(supabase_client)
        q = (
            sb.table("sessioni")
            .update({"revoked_at": _now_iso()})
            .eq("user_id", str(user_id))
            .is_("revoked_at", "null")
        )
        if escludi_token:
            q = q.neq("token", escludi_token)
        res = q.execute()
        return len(res.data or [])
    except Exception:
        logger.exception("Errore revoca tutte le sessioni")
        return 0


def revoca_sessione(token: str, supabase_client=None) -> bool:
    """Revoca (logout) la singola sessione. Ritorna True se ne è stata revocata una."""
    if not token:
        return False
    try:
        sb = _client(supabase_client)
        res = (
            sb.table("sessioni")
            .update({"revoked_at": _now_iso()})
            .eq("token", token)
            .is_("revoked_at", "null")
            .execute()
        )
        _LAST_SEEN_THROTTLE.pop(token, None)
        return bool(res.data)
    except Exception:
        logger.exception("Errore revoca sessione")
        return False
