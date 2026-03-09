"""
conftest.py — Mock moduli pesanti non disponibili nell'ambiente test puro.
Questo file viene eseguito PRIMA di qualsiasi import dei test.
"""
import sys
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
    "pandas",
    "xmltodict",
    "requests",
]

for mod in _MODULI_DA_MOCKARE:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
