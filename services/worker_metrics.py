"""Metriche di latenza del worker, in-process e thread-safe.

Scopo: dare all'Admin la visibilità di QUANDO il worker inizia a soffrire, così
il potenziamento Railway si decide sui numeri reali (non a naso). Nessun servizio
esterno, nessun costo: si tiene una finestra scorrevole degli ultimi N campioni
per rotta e si calcolano p50/p95 al volo.

Per-processo (come le altre strutture in-memory del worker, multi-worker in prod):
i numeri sono un campione rappresentativo del processo che risponde, sufficiente
per capire l'andamento. Non è un sistema di osservabilità completo, è una spia.

Uso: il middleware chiama `record(route, ms, status)` a ogni richiesta; l'endpoint
admin chiama `snapshot()` per leggere l'aggregato.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Dict, List, Tuple

# Quanti campioni per rotta tenere (finestra scorrevole). ~500 basta per p95 stabile
# senza consumo di memoria significativo.
_MAX_SAMPLES = 500

# Sopra questa soglia una richiesta è "lenta": è il primo segnale di saturazione.
# Allineata al timeout SSR lato Next.js (12s): se ci avviciniamo, l'utente rischia
# la schermata "non raggiungibile".
SLOW_MS = 4000


class _RouteStats:
    __slots__ = ("samples", "count", "slow", "errors", "max_ms")

    def __init__(self) -> None:
        self.samples: Deque[float] = deque(maxlen=_MAX_SAMPLES)
        self.count = 0
        self.slow = 0
        self.errors = 0
        self.max_ms = 0.0


_stats: Dict[str, _RouteStats] = {}
_lock = threading.Lock()


def record(route: str, ms: float, status: int) -> None:
    with _lock:
        st = _stats.get(route)
        if st is None:
            st = _RouteStats()
            _stats[route] = st
        st.samples.append(ms)
        st.count += 1
        if ms >= SLOW_MS:
            st.slow += 1
        if status >= 500:
            st.errors += 1
        if ms > st.max_ms:
            st.max_ms = ms


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def snapshot() -> Dict[str, object]:
    """Aggregato leggibile: per rotta count/p50/p95/max/slow/errors, ordinato per
    p95 discendente (le rotte più a rischio in cima). Include un totale."""
    rows: List[Dict[str, object]] = []
    tot_count = tot_slow = tot_errors = 0
    with _lock:
        items: List[Tuple[str, _RouteStats]] = list(_stats.items())
        for route, st in items:
            vals = sorted(st.samples)
            rows.append({
                "route": route,
                "count": st.count,
                "p50_ms": round(_percentile(vals, 0.50)),
                "p95_ms": round(_percentile(vals, 0.95)),
                "max_ms": round(st.max_ms),
                "slow": st.slow,
                "errors": st.errors,
            })
            tot_count += st.count
            tot_slow += st.slow
            tot_errors += st.errors
    rows.sort(key=lambda r: r["p95_ms"], reverse=True)
    return {
        "routes": rows,
        "totale": {"count": tot_count, "slow": tot_slow, "errors": tot_errors},
        "slow_soglia_ms": SLOW_MS,
    }


def reset() -> None:
    with _lock:
        _stats.clear()
