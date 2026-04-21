"""Test per utils/formatters.py — safe_get navigazione dizionari annidati."""
import pytest
from utils.formatters import safe_get


class TestSafeGet:
    """Verifica navigazione sicura dizionari annidati (parsing XML)."""

    def test_chiave_semplice(self):
        assert safe_get({"a": 1}, ["a"]) == 1

    def test_chiavi_annidate(self):
        d = {"a": {"b": {"c": 42}}}
        assert safe_get(d, ["a", "b", "c"]) == 42

    def test_chiave_mancante(self):
        assert safe_get({"a": 1}, ["x"]) is None

    def test_chiave_mancante_con_default(self):
        assert safe_get({}, ["x", "y"], default="not_found") == "not_found"

    def test_lista_estrai_primo(self):
        """Senza keep_list, estrae il primo elemento dalla lista."""
        d = {"a": [{"b": 1}, {"b": 2}]}
        assert safe_get(d, ["a", "b"], keep_list=False) == 1

    def test_lista_keep_list(self):
        """Con keep_list=True, restituisce la lista intera."""
        d = {"a": [{"b": 1}, {"b": 2}]}
        result = safe_get(d, ["a"], keep_list=True)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_lista_vuota(self):
        d = {"a": []}
        assert safe_get(d, ["a", "b"], default="vuoto") == "vuoto"

    def test_dizionario_vuoto(self):
        assert safe_get({}, ["a"]) is None

    def test_none_dizionario(self):
        """safe_get con None come dizionario."""
        assert safe_get(None, ["a"], default="fallback") == "fallback"

    def test_valore_zero(self):
        """Zero è un valore valido, non deve restituire default."""
        d = {"prezzo": 0}
        assert safe_get(d, ["prezzo"], default=999) == 0

    def test_valore_stringa_vuota(self):
        """Stringa vuota è un valore valido."""
        d = {"nome": ""}
        assert safe_get(d, ["nome"], default="fallback") == ""
