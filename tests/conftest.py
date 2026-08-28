"""conftest.py — Mock del solo Streamlit (l'unico modulo non installato).

Eseguito PRIMA di qualsiasi import dei test.

Cosa si mocka, e perche'
========================
`streamlit` NON e' nei requirements: la UI e' Next.js, e i moduli di business
logic che fanno ancora `import streamlit as st` girano in produzione con
`services/_streamlit_shim.py`. Qui si usa un MagicMock invece dello shim perche'
molti test sostituiscono `sys.modules['streamlit']` con un proprio fake e ne
configurano `session_state` a piacere: la superficie aperta del MagicMock
assorbe qualunque attributo, quella chiusa dello shim no.

Cosa NON si mocka, e perche' conta
==================================
Fino al 28/8/2026 questa lista conteneva anche supabase, postgrest, requests,
openai, tenacity, argon2, xmltodict e fitz, sotto la premessa "moduli non
disponibili nell'ambiente test puro". La premessa era FALSA: sono tutti
installati. Il costo non era la lentezza, era la correttezza dei test:

    except openai.RateLimitError:  ->  TypeError: catching classes that do not
                                       inherit from BaseException

Un attributo di MagicMock non eredita da BaseException, quindi ogni ramo
`except` su quelle eccezioni sollevava TypeError invece di catturare: i test che
li "coprivano" verificavano un TypeError. Stessa cosa per `@retry` di tenacity,
che non decorava affatto, e per `argon2.PasswordHasher`, il cui `verify` non
sollevava mai.

`tests/test_conftest_cache_guardia.py::test_conftest_mocka_solo_streamlit`
impedisce che la lista si riallunghi, e verifica che la premessa sia ancora vera
invece di darla per scontata.
"""
import os
import socket
import sys
import importlib
from unittest.mock import MagicMock

# Solo streamlit: vedi il docstring in cima. Ogni aggiunta qui va giustificata
# con "il modulo non e' installato", non con "e' pesante".
_MODULI_DA_MOCKARE = [
    "streamlit",
    "streamlit.cache_resource",
    "streamlit.cache_data",
]

# NOTA: pandas NON è nella lista di mock — è installato nel venv ed è necessario
# per i test che usano DataFrame reali (test_db_service.py, test_invoice_service.py).

for mod in _MODULI_DA_MOCKARE:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


# --- Nessun test puo' uscire in rete ----------------------------------------
# Senza il mock di supabase, create_client e' REALE e alcune funzioni memoizzate
# (_fetch_numero_documento_map_cached, db_service.py:265) non ricevono il client
# dal chiamante: se lo procurano con get_supabase_client(), ignorando il fake
# iniettato dal test. E services/fastapi_worker.py:72 fa load_dotenv(override=True),
# che rimette le credenziali di PRODUZIONE in os.environ (53 file di test
# importano il worker): senza questa guardia, in locale quelle query
# arriverebbero al DB dei clienti.
# getaddrinfo va bloccato oltre a connect: httpcore risolve il DNS prima di
# connettersi, quindi con il solo connect la guardia non scatterebbe.
class ReteVietataNeiTest(RuntimeError):
    """Un test ha provato a contattare la rete: iniettare un fake client."""


def _rete_vietata(*args, **kwargs):
    raise ReteVietataNeiTest(f"connessione di rete vietata nei test: {args[:1]}")


socket.getaddrinfo = _rete_vietata
socket.socket.connect = _rete_vietata
socket.socket.connect_ex = _rete_vietata

# --- st.secrets deve essere un dict di STRINGHE ------------------------------
# services._get_supabase_credentials() prova st.secrets PRIMA delle env var, e un
# MagicMock e' truthy: restituirebbe due MagicMock senza mai leggere l'ambiente.
# Con supabase reale, create_client valida l'URL con re.match(r"^(https?)://.+")
# (supabase/_sync/client.py:62) -> "expected string or bytes-like object, got
# 'MagicMock'". Credenziali finte ma sintatticamente valide; la guardia di rete
# qui sopra garantisce che non vengano mai usate per davvero.
sys.modules["streamlit"].secrets = {
    "supabase": {
        "url": "https://test.supabase.co",
        "service_role_key": "test-service-role-key",
    },
}
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


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
    # Trial per-utente durante l'upload multi-file: porta dati (is_trial), quindi
    # va svuotata o un test che simula un trial lo farebbe leggere al successivo.
    "_TRIAL_INFO_CACHE",
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
