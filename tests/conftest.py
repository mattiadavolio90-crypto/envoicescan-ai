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


# Cache in-process che portano DATI e vanno svuotate fra un test e l'altro.
# L'elenco e' esposto come costante (non inline nella fixture) perche'
# test_conftest_cache_guardia.py lo confronta con le cache realmente presenti nei
# moduli: senza quel confronto, una cache aggiunta in futuro resterebbe fuori dal
# reset in silenzio — che e' esattamente come _SESSIONE_CACHE e
# _FATTURE_ROWS_CACHE erano sfuggite fino all'audit Test del 3/8/2026.
CACHE_WORKER = (
    "_ASSIST_PREF_CACHE",
    "_SEDE_ATTIVA_CACHE",
    "_LIVE_SEGNALI_CACHE",
    "_HOME_KPI_CACHE",
    "_DASHBOARD_STATS_CACHE",
    "_FATTURE_ROWS_CACHE",
)
CACHE_AUTH = ("_SESSIONE_CACHE",)
CACHE_ADMIN = ("_ADMIN_CACHE",)

# `services/ai_service.py` non segue la convenzione MAIUSCOLO_CACHE: usa
# `_memoria_cache` (minuscolo), che contiene la memoria di categorizzazione
# PER UTENTE (`prodotti_utente[user_id]`) piu' prodotti_master e
# classificazioni_manuali. E' la cache piu' sensibile alla contaminazione fra
# test — un user_id gia' caricato da un test precedente fa saltare il
# ricaricamento — e va svuotata con la sua funzione ufficiale
# `invalida_cache_memoria()`, non azzerando il dict a mano (il contatore
# `version` deve avanzare, altrimenti `_brand_union_cache` resta stantia).
CACHE_AI_MINUSCOLE = ("_memoria_cache", "_brand_union_cache")

# Esclusa deliberatamente dal reset: memoizza un client Supabase stateless per
# (url, key), non dati del test. Svuotarla ricreerebbe solo il mock, senza
# togliere alcuna contaminazione.
CACHE_ESCLUSE = {"_SUPABASE_CLIENT_CACHE"}


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
        for _name in CACHE_WORKER:
            _reset(getattr(_fw, _name, None))
    except Exception:
        pass
    try:
        import services.routers.admin as _admin
        _reset(getattr(_admin, "_ADMIN_CACHE", None))
    except Exception:
        pass
    try:
        import services.auth_service as _auth
        for _name in CACHE_AUTH:
            _reset(getattr(_auth, _name, None))
    except Exception:
        pass
    try:
        import services.ai_service as _ai
        _ai.invalida_cache_memoria()
    except Exception:
        pass
    yield
