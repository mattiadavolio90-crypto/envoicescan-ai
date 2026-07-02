"""Cache TTL in-process, thread-safe, riutilizzabile.

Il worker FastAPI serve gli endpoint su un threadpool (endpoint `def` sincroni):
piu' thread possono leggere/scrivere la stessa cache in parallelo, quindi serve un
lock. Il worker gira anche multi-processo (WORKER_WEB_CONCURRENCY): questa cache e'
PER-PROCESSO, quindi va usata solo per dati dove un TTL breve e una piccola
divergenza fra processi sono accettabili (overview admin, breakdown, badge...),
MAI per dati dove serve coerenza forte immediata.

Uso tipico:
    from utils.ttl_cache import TTLCache
    _overview_cache = TTLCache(ttl=45.0)

    def admin_overview():
        return _overview_cache.get_or_set("overview", _compute_overview)

`get_or_set` valuta il producer FUORI dal lock: una computazione lenta non blocca
gli altri thread che leggono chiavi diverse. Piccola race possibile (due thread
calcolano la stessa chiave insieme al primo miss): accettabile, il risultato e'
identico e idempotente.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, ttl: float) -> None:
        self._ttl = float(ttl)
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        # Single-flight: un lock PER-CHIAVE creato al bisogno. Quando N thread
        # chiedono la stessa chiave fredda insieme (tipico: la Home spara 6-7
        # richieste in parallelo prima che la cache si scaldi), solo il primo
        # calcola; gli altri aspettano il SUO risultato invece di rifare la stessa
        # query. Chiavi diverse non si bloccano a vicenda.
        self._flight_locks: Dict[str, threading.Lock] = {}
        self._flight_guard = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Valore cached se presente e non scaduto, altrimenti None."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is not None and entry[0] > now:
                return entry[1]
        return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def _flight_lock_for(self, key: str) -> threading.Lock:
        with self._flight_guard:
            lk = self._flight_locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._flight_locks[key] = lk
            return lk

    def get_or_set(self, key: str, producer: Callable[[], Any]) -> Any:
        """Ritorna il valore cached; se assente/scaduto chiama `producer` UNA sola
        volta anche sotto richieste concorrenti (single-flight), lo memorizza e lo
        ritorna. Il producer gira fuori dal lock globale della cache."""
        cached = self.get(key)
        if cached is not None:
            return cached
        # Solo un thread per chiave entra qui; gli altri aspettano e poi trovano
        # il valore gia' in cache (ricontrollo dopo aver preso il lock).
        with self._flight_lock_for(key):
            cached = self.get(key)
            if cached is not None:
                return cached
            value = producer()
            self.set(key, value)
            return value

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalida una chiave, o tutta la cache se key is None."""
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
