"""
conftest.py — Mock moduli pesanti non disponibili nell'ambiente test puro.
Questo file viene eseguito PRIMA di qualsiasi import dei test.
"""
import sys
import importlib
from unittest.mock import MagicMock

# Lista moduli che richiedono l'app runtime (Streamlit, PyMuPDF, Supabase, ecc.)
# Li mockiamo per permettere l'import delle funzioni pure
_MODULI_DA_MOCKARE = [
    "streamlit",
    "streamlit.cache_resource",
    "streamlit.cache_data",
    "fitz",          # PyMuPDF
    "supabase",
    "supabase.lib",
    "supabase.lib.client_options",
    "supabase._sync",
    "supabase._sync.client",
    "postgrest",
    "openai",
    "tenacity",
    "argon2",
    "argon2.exceptions",
    "xmltodict",
    "requests",
]

# NOTA: pandas NON è nella lista di mock — è installato nel venv ed è necessario
# per i test che usano DataFrame reali (test_db_service.py, test_invoice_service.py).

for mod in _MODULI_DA_MOCKARE:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


import pytest


@pytest.fixture(autouse=True)
def _reset_worker_caches():
    """Svuota le cache in-process del worker prima di OGNI test.

    Le cache (assistant_preferences TTL 30s, sede attiva TTL 5s, segnali live,
    KPI) sono legittime in produzione ma globali per-processo: senza reset, un
    test che cacha un valore per un ristorante_id lo farebbe leggere stantio al
    test successivo che usa lo stesso id (isolamento rotto).
    """
    def _reset(_c):
        # Le cache in-process sono dict ad-hoc oppure TTLCache (utils/ttl_cache):
        # svuotiamo entrambe le forme.
        if isinstance(_c, dict):
            _c.clear()
        elif hasattr(_c, "invalidate"):
            _c.invalidate()

    try:
        import services.fastapi_worker as _fw
        for _name in ("_ASSIST_PREF_CACHE", "_SEDE_ATTIVA_CACHE",
                      "_LIVE_SEGNALI_CACHE", "_HOME_KPI_CACHE",
                      "_DASHBOARD_STATS_CACHE"):
            _reset(getattr(_fw, _name, None))
    except Exception:
        pass
    try:
        import services.routers.admin as _admin
        _reset(getattr(_admin, "_ADMIN_CACHE", None))
    except Exception:
        pass
    yield
