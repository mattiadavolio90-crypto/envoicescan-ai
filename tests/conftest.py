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
