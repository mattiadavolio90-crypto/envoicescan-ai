"""Stub minimale di Streamlit per esecuzione worker CLI.

Questo modulo viene usato solo se `import streamlit` fallisce nella venv locale.
Evita che i moduli condivisi con la UI blocchino il worker per dipendenze mancanti.
"""

from __future__ import annotations

import os
import types
from typing import Any, Callable


class _Secrets(dict):
    """Mappa compatibile con st.secrets usando env vars come fallback."""

    def __getitem__(self, key: str) -> Any:
        if key == "supabase":
            return {
                "url": os.environ.get("SUPABASE_URL", ""),
                "key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                or os.environ.get("SUPABASE_KEY", ""),
            }
        if key == "OPENAI_API_KEY":
            return os.environ.get("OPENAI_API_KEY", "")
        return os.environ.get(key, "")


class _SessionState(dict):
    pass


def _no_op(*_args: Any, **_kwargs: Any) -> None:
    return None


def _cache_resource(*_args: Any, **_kwargs: Any) -> Callable:
    def _decorator(fn: Callable) -> Callable:
        return fn

    return _decorator


def install_streamlit_stub() -> None:
    """Registra un modulo `streamlit` minimale in sys.modules."""
    import sys

    if "streamlit" in sys.modules:
        return

    module = types.ModuleType("streamlit")
    module.secrets = _Secrets()
    module.session_state = _SessionState()
    module.cache_resource = _cache_resource

    # API usate nel progetto, definite come no-op in contesto CLI
    module.info = _no_op
    module.warning = _no_op
    module.error = _no_op
    module.success = _no_op
    module.write = _no_op
    module.markdown = _no_op
    module.text = _no_op
    module.spinner = lambda *_a, **_k: types.SimpleNamespace(
        __enter__=lambda self: self,
        __exit__=lambda self, exc_type, exc, tb: False,
    )

    sys.modules["streamlit"] = module
