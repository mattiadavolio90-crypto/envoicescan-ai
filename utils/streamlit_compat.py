"""Compatibilita per API Streamlit deprecate."""

from functools import wraps


def make_cache(**kwargs):
    """Restituisce st.cache_data se Streamlit e' disponibile, altrimenti un noop con .clear()."""
    try:
        import streamlit as _st
        return _st.cache_data(**kwargs)
    except Exception:
        def _noop(fn):
            fn.clear = lambda: None
            return fn
        return _noop


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