"""Settore di un account: ristorazione o retail (DOCUMENTAZIONE/RETAIL_FASI.md, 1.2).

Modulo separato da `ai_service` — che e' importato da mezzo mondo — perche' il
settore serve anche a router che non fanno AI. Si risolve UNA volta per
documento o per richiesta, fuori dal loop righe, e viaggia come argomento:
MAI negli header del client Supabase, che e' un singleton condiviso e i cui
header sono stato globale (hanno gia' rotto la produzione).

In v1 le sedi di un account sono omogenee (vincolo in `routers/admin.py`): il
settore dell'account e' quello della sua prima sede reale attiva. La sede
tecnica "Costi comuni di gruppo" non conta: la crea una funzione SQL.

Fail-safe nella direzione giusta: senza sedi (`auth_service` crea account senza
sedi se manca la P.IVA), con un valore sconosciuto o su errore si risponde
'ristorazione'. Un negozio visto da ristorante e' un'etichetta sbagliata; un
ristorante visto da negozio e' un'analisi spenta per un cliente pagante.

Cache di modulo con lock e TTL di 300 s (pattern di `_memoria_cache`): il
settore cambia solo per mano dell'admin, che invalida la cache del suo
processo; gli altri processi (queue-worker) la vedono entro il TTL. Un errore
NON si mette in cache: la chiamata successiva ritenta.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE, SETTORI_SEDE
from config.logger_setup import get_logger

logger = get_logger("settore")

TTL_SECONDS = 300

_lock = threading.Lock()
_cache_utenti: dict[str, tuple[str, float]] = {}
_cache_sedi: dict[str, tuple[str, float]] = {}


def _client(supabase_client):
    if supabase_client is not None:
        return supabase_client
    from services import get_supabase_client

    return get_supabase_client()


def _normalizza(valore) -> str:
    settore = str(valore or "").strip().lower()
    return settore if settore in SETTORI_SEDE else SETTORE_RISTORAZIONE


def _da_cache(cache: dict, chiave: str) -> Optional[str]:
    with _lock:
        voce = cache.get(chiave)
    if voce and (time.time() - voce[1]) < TTL_SECONDS:
        return voce[0]
    return None


def _in_cache(cache: dict, chiave: str, settore: str) -> str:
    with _lock:
        cache[chiave] = (settore, time.time())
    return settore


def settore_utente(user_id: Optional[str], supabase_client=None) -> str:
    """Settore dell'account: quello della prima sede reale attiva, o 'ristorazione'."""
    if not user_id:
        return SETTORE_RISTORAZIONE
    uid = str(user_id)
    noto = _da_cache(_cache_utenti, uid)
    if noto is not None:
        return noto
    try:
        resp = (
            _client(supabase_client).table("ristoranti").select("tipo_attivita")
            .eq("user_id", uid).eq("attivo", True).eq("sede_tecnica", False)
            .order("created_at").limit(1).execute()
        )
        righe = resp.data or []
    except Exception as exc:
        logger.warning("settore_utente: lettura fallita per %s, uso '%s': %s", uid[:8], SETTORE_RISTORAZIONE, exc)
        return SETTORE_RISTORAZIONE
    settore = _normalizza(righe[0].get("tipo_attivita")) if righe else SETTORE_RISTORAZIONE
    return _in_cache(_cache_utenti, uid, settore)


def settore_sede(ristorante_id: Optional[str], supabase_client=None) -> str:
    """Settore di una sede precisa, o 'ristorazione' se non esiste."""
    if not ristorante_id:
        return SETTORE_RISTORAZIONE
    rid = str(ristorante_id)
    noto = _da_cache(_cache_sedi, rid)
    if noto is not None:
        return noto
    try:
        resp = (
            _client(supabase_client).table("ristoranti").select("tipo_attivita")
            .eq("id", rid).limit(1).execute()
        )
        righe = resp.data or []
    except Exception as exc:
        logger.warning("settore_sede: lettura fallita per %s, uso '%s': %s", rid[:8], SETTORE_RISTORAZIONE, exc)
        return SETTORE_RISTORAZIONE
    settore = _normalizza(righe[0].get("tipo_attivita")) if righe else SETTORE_RISTORAZIONE
    return _in_cache(_cache_sedi, rid, settore)


def is_retail(user_id: Optional[str], supabase_client=None) -> bool:
    return settore_utente(user_id, supabase_client) == SETTORE_RETAIL


def invalida_cache(user_id: Optional[str] = None) -> None:
    """Dopo una scrittura dell'admin: tutto l'account (le sue sedi sono omogenee)."""
    with _lock:
        if user_id is None:
            _cache_utenti.clear()
            _cache_sedi.clear()
            return
        _cache_utenti.pop(str(user_id), None)
        _cache_sedi.clear()
