"""Compatibilita per API Streamlit deprecate.

`make_cache` nasce come ponte verso `st.cache_data` quando il frontend era
Streamlit. Streamlit e' stato rimosso dal repo (17/7/2026) e NON e' installato:
per anni il fallback e' stato un no-op, quindi 14 funzioni decorate con
`@_make_cache(ttl=...)` dichiaravano un TTL e **non cachavano niente** — con
docstring che affermavano il falso ("I risultati sono cachati per 5 minuti").

Oggi il fallback e' una cache vera basata su `utils.ttl_cache.TTLCache`
(thread-safe, single-flight), che rispetta il TTL dichiarato. L'interfaccia
resta identica — decoratore con `ttl=` e metodo `.clear()` sulla funzione — cosi'
i chiamanti esistenti non cambiano.

Nota: la cache e' PER-PROCESSO. Con `WORKER_WEB_CONCURRENCY > 1` ogni worker ha
la sua copia, quindi vale solo per dati dove una divergenza breve fra processi e'
accettabile (esattamente il criterio gia' scritto in `utils/ttl_cache.py`).
"""

from functools import wraps

from utils.ttl_cache import TTLCache


def _key_part(value) -> str:
    """Rappresentazione stabile di un singolo argomento.

    Due insidie, entrambe presenti nel codice reale:

    1. Gli oggetti senza `__repr__` proprio (tipico: il client Supabase passato
       come argomento a `get_fatture_cestino`) hanno un repr con l'indirizzo di
       memoria: la chiave cambierebbe a ogni istanza e la cache non colpirebbe
       mai, occupando memoria senza servire a niente. Questi argomenti si
       identificano per TIPO, non per valore: non fanno parte dell'identita'
       della domanda, sono solo il mezzo per rispondere.
    2. Liste e dict non sono hashabili: con `hash()` alzerebbero TypeError e una
       cache mancata diventerebbe un errore 500. Vanno normalizzati, con i dict
       ordinati per chiave perche' `{'a':1,'b':2}` e `{'b':2,'a':1}` sono la
       stessa domanda.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return repr(value)
    if isinstance(value, dict):
        return "{" + ",".join(f"{_key_part(k)}:{_key_part(v)}" for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))) + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=repr) if isinstance(value, (set, frozenset)) else value
        return "[" + ",".join(_key_part(v) for v in items) + "]"
    # Client, connessioni, oggetti opachi: identificati dal tipo.
    return f"<{type(value).__name__}>"


def _cache_key(args, kwargs) -> str:
    """Chiave stabile dagli argomenti della chiamata."""
    return (
        ",".join(_key_part(a) for a in args)
        + "|"
        + ",".join(f"{k}={_key_part(v)}" for k, v in sorted(kwargs.items()))
    )


def make_cache(ttl=None, **_kwargs):
    """Decoratore di cache con TTL. `show_spinner` e simili sono accettati e
    ignorati: erano parametri di presentazione di Streamlit."""
    ttl_seconds = float(ttl) if ttl is not None else 60.0

    def _decorator(fn):
        cache = TTLCache(ttl=ttl_seconds)

        @wraps(fn)
        def _wrapped(*args, **kwargs):
            return cache.get_or_set(_cache_key(args, kwargs), lambda: fn(*args, **kwargs))

        _wrapped.clear = lambda: cache.invalidate()
        _wrapped.cache_invalidate = cache.invalidate
        return _wrapped

    return _decorator


_PATCH_FLAG = "_ohh_width_compat_patched"
_WIDTH_COMPAT_METHODS = (
    "button",
    "dataframe",
    "download_button",
    "form_submit_button",
    "plotly_chart",
    "popover",
)


def _normalize_width_kwargs(kwargs):
    if "use_container_width" in kwargs and "width" not in kwargs:
        kwargs["width"] = "stretch" if kwargs.pop("use_container_width") else "content"


def patch_streamlit_width_api() -> None:
    try:
        from streamlit.delta_generator import DeltaGenerator
    except Exception:
        return

    for method_name in _WIDTH_COMPAT_METHODS:
        original_method = getattr(DeltaGenerator, method_name, None)
        if original_method is None or getattr(original_method, _PATCH_FLAG, False):
            continue

        @wraps(original_method)
        def _wrapped_method(self, *args, __original=original_method, **kwargs):
            _normalize_width_kwargs(kwargs)
            return __original(self, *args, **kwargs)

        setattr(_wrapped_method, _PATCH_FLAG, True)
        setattr(DeltaGenerator, method_name, _wrapped_method)
