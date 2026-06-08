"""Shim Streamlit per i processi non-UI (worker FastAPI, queue-worker).

Perche' esiste
==============
Il worker importa `services.*`, e diversi moduli di business logic fanno
`import streamlit as st` a livello top-level (per `st.secrets`, `st.session_state`
e decoratori `@st.cache_resource`/`@st.cache_data`). Importare il pacchetto
Streamlit reale nel worker costa ~350-400ms di import a freddo e, soprattutto,
produce a ogni cold-start una cascata di centinaia di
`WARNING streamlit.runtime.caching: No runtime found` (le funzioni cached girano
fuori dal runtime Streamlit). Su Railway Hobby, dove il container va in sleep e
fa cold-start, questo overhead concorre a far sforare il timeout di login da 8s.

Cosa fa
=======
Registra in `sys.modules['streamlit']` un modulo fittizio con la sola superficie
usata dalla business logic:
- `cache_resource` / `cache_data`: decoratori passthrough (no caching, ma il
  worker non ha bisogno del caching UI di Streamlit).
- `session_state`: dict vuoto (nel worker il contesto utente passa via ContextVar,
  non via session_state — vedi ai_service._get_ristorante_id/_get_user_id).
- `secrets`: vuoto (nel worker i segreti arrivano da env / .env, non da secrets.toml).
- no-op per le funzioni di rendering (`empty`, `warning`, `spinner`, ...).

Sicurezza
=========
`install()` e' idempotente e si auto-disabilita se il pacchetto Streamlit reale
e' GIA' in `sys.modules`: sotto la UI (`app.py` fa `import streamlit` come prima
riga, prima di importare `services`) lo shim non viene mai installato e il
comportamento resta identico a prima.
"""
from __future__ import annotations

import os
import sys
import types
from typing import Any, Callable


def _passthrough_decorator(*args: Any, **kwargs: Any) -> Any:
    # Supporta sia @st.cache_data sia @st.cache_data(ttl=...): nel primo caso
    # arriva direttamente la funzione, nel secondo arrivano gli argomenti e va
    # restituito un wrapper.
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def _wrap(func: Callable) -> Callable:
        return func

    return _wrap


class _SessionState(dict):
    """Sostituto di st.session_state: dict semplice con .get/attr access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - parita' con AttributeError
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _noop(*args: Any, **kwargs: Any) -> None:
    return None


class _Secrets(dict):
    """Sostituto di st.secrets nel worker: fallback su variabili d'ambiente.

    Sotto Streamlit, `st.secrets` e' popolato da `.streamlit/secrets.toml` (che
    nel container worker era generato da docker-entrypoint.sh dalle env var).
    Nel worker non c'e' runtime Streamlit, quindi ricostruiamo qui la stessa
    superficie leggendo direttamente da os.environ, cosi' che `_get_openai_client`
    (st.secrets["OPENAI_API_KEY"]) e la config Brevo/Supabase continuino a
    funzionare identiche a prima.
    """

    def __init__(self) -> None:
        super().__init__()
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            self["OPENAI_API_KEY"] = openai_key

        supabase_section = {
            "url": os.environ.get("SUPABASE_URL", ""),
            "key": os.environ.get("SUPABASE_KEY", ""),
            "anon_key": os.environ.get("SUPABASE_ANON_KEY", "")
            or os.environ.get("SUPABASE_KEY", ""),
            "service_role_key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        }
        if any(supabase_section.values()):
            self["supabase"] = {k: v for k, v in supabase_section.items() if v}

        brevo_section = {
            "api_key": os.environ.get("BREVO_API_KEY", ""),
            "sender_email": os.environ.get("BREVO_SENDER_EMAIL", "agent@oneflux.it"),
            "sender_name": os.environ.get("BREVO_SENDER_NAME", "ONEFLUX"),
            "reply_to_email": os.environ.get("BREVO_REPLY_TO_EMAIL", "md@oneflux.it"),
            "reply_to_name": os.environ.get("BREVO_REPLY_TO_NAME", "ONEFLUX"),
            "bcc_email": os.environ.get("BREVO_BCC_EMAIL", ""),
        }
        if brevo_section["api_key"]:
            self["brevo"] = brevo_section


def install() -> bool:
    """Installa lo shim se Streamlit reale non e' gia' caricato.

    Ritorna True se lo shim e' stato (o era gia') installato, False se e'
    presente il pacchetto Streamlit reale e quindi lo shim e' stato saltato.
    """
    existing = sys.modules.get("streamlit")
    if existing is not None:
        # Gia' nostro shim -> idempotente; pacchetto reale -> non lo tocchiamo.
        return getattr(existing, "_ONEFLUX_STREAMLIT_SHIM", False)

    st = types.ModuleType("streamlit")
    st._ONEFLUX_STREAMLIT_SHIM = True  # type: ignore[attr-defined]

    st.cache_resource = _passthrough_decorator  # type: ignore[attr-defined]
    st.cache_data = _passthrough_decorator  # type: ignore[attr-defined]
    st.session_state = _SessionState()  # type: ignore[attr-defined]
    st.secrets = _Secrets()  # type: ignore[attr-defined]

    # Funzioni di rendering / controllo flusso usate sparsamente: no-op nel worker.
    for name in (
        "empty", "warning", "error", "info", "success", "spinner", "write",
        "markdown", "caption", "stop", "rerun", "experimental_rerun", "toast",
        "progress", "container", "columns", "expander", "code",
    ):
        setattr(st, name, _noop)

    sys.modules["streamlit"] = st
    return True
