"""
conftest.py — Mock streamlit per i test in questa cartella.
Va replicato qui perché pytest non eredita conftest.py da tests/
(directory sorella, non antenata). Stesso mock di tests/conftest.py,
ridotto a streamlit perché è l'unico modulo pesante richiesto da
questo pacchetto legacy.
"""
import sys
from unittest.mock import MagicMock

if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = MagicMock()
