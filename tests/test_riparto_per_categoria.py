"""Riparto per categoria (Voce 6, services/riparto_service.py).

Invariante non negoziabile: spezzando la quota di una sede nelle sue categorie, la
SOMMA delle porzioni pareggia SEMPRE la quota originale (nessun centesimo perso o
creato). È lo stesso principio di test_riparto_quote.py, un livello più in basso:
lì si spezza l'importo fra sedi, qui si spezza la quota di sede fra categorie.

_spezza_importo_per_pesi è pura (nessun DB). _pesi_categoria_fattura fa una query:
testata con un fake client minimale che ritorna righe predefinite.
"""
import pytest

from services.riparto_service import _spezza_importo_per_pesi, _pesi_categoria_fattura


# ─── _spezza_importo_per_pesi (puro) ─────────────────────────────────────────

def test_spezza_due_categorie_pareggia():
    # 60% cibo / 40% spese su 100 → 60 + 40, somma esatta.
    out = _spezza_importo_per_pesi(100.0, {"CARNE": 0.6, "SERVIZI E CONSULENZE": 0.4})
    imp = {o["categoria"]: o["quota_importo"] for o in out}
    assert sum(o["quota_importo"] for o in out) == 100.0
    assert imp["CARNE"] == pytest.approx(60.0, abs=0.01)
    assert imp["SERVIZI E CONSULENZE"] == pytest.approx(40.0, abs=0.01)


def test_spezza_tre_categorie_arrotondamento_pareggia():
    # pesi che danno centesimi non esatti: l'ultima categoria assorbe il resto.
    out = _spezza_importo_per_pesi(100.0, {"A": 1/3, "B": 1/3, "C": 1/3})
    assert sum(o["quota_importo"] for o in out) == pytest.approx(100.0, abs=1e-9)


def test_spezza_una_sola_categoria():
    out = _spezza_importo_per_pesi(250.0, {"UTENZE E LOCALI": 1.0})
    assert out == [{"categoria": "UTENZE E LOCALI", "quota_importo": 250.0}]


def test_spezza_pesi_vuoti():
    assert _spezza_importo_per_pesi(100.0, {}) == []


def test_spezza_importo_con_centesimi_dispari():
    out = _spezza_importo_per_pesi(105.58, {"VERDURE": 0.5, "MATERIALE DI CONSUMO": 0.5})
    assert sum(o["quota_importo"] for o in out) == pytest.approx(105.58, abs=1e-9)


def test_spezza_peso_trascurabile_scartato():
    # una categoria con peso ~0 non genera una riga da 0.00 spuria.
    out = _spezza_importo_per_pesi(100.0, {"CARNE": 1.0, "SHOP": 1e-12})
    cats = {o["categoria"] for o in out}
    assert cats == {"CARNE"}
    assert sum(o["quota_importo"] for o in out) == 100.0


# ─── _pesi_categoria_fattura (query fake) ────────────────────────────────────

class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
    def select(self, *a, **k):   return self
    def eq(self, *a, **k):       return self
    def is_(self, *a, **k):      return self
    def execute(self):
        class _R:  data = self._rows
        _R.data = self._rows
        return _R


class _FakeSB:
    def __init__(self, rows):
        self._rows = rows
    def table(self, *_):
        return _FakeQuery(self._rows)


def test_pesi_da_righe_reali_normalizzati():
    rows = [
        {"categoria": "VERDURE", "totale_riga": 30.0},
        {"categoria": "MATERIALE DI CONSUMO", "totale_riga": 70.0},
    ]
    pesi = _pesi_categoria_fattura(_FakeSB(rows), "u", "f.xml")
    assert pesi["VERDURE"] == pytest.approx(0.3, abs=1e-9)
    assert pesi["MATERIALE DI CONSUMO"] == pytest.approx(0.7, abs=1e-9)
    assert sum(pesi.values()) == pytest.approx(1.0, abs=1e-9)


def test_pesi_stessa_categoria_sommata():
    rows = [
        {"categoria": "SERVIZI E CONSULENZE", "totale_riga": 10.0},
        {"categoria": "SERVIZI E CONSULENZE", "totale_riga": 30.0},
        {"categoria": "UTENZE E LOCALI", "totale_riga": 40.0},
    ]
    pesi = _pesi_categoria_fattura(_FakeSB(rows), "u", "f.xml")
    assert pesi["SERVIZI E CONSULENZE"] == pytest.approx(0.5, abs=1e-9)
    assert pesi["UTENZE E LOCALI"] == pytest.approx(0.5, abs=1e-9)


def test_pesi_nessuna_riga_ritorna_none():
    # Storico purgato: nessuna riga viva → None → resta il modello legacy per-tipo.
    assert _pesi_categoria_fattura(_FakeSB([]), "u", "f.xml") is None


def test_pesi_totale_zero_ritorna_none():
    # Fattura interamente a importo nullo: non ripartibile in proporzione.
    rows = [{"categoria": "NOTE E DICITURE", "totale_riga": 0.0}]
    assert _pesi_categoria_fattura(_FakeSB(rows), "u", "f.xml") is None


def test_pesi_righe_senza_categoria_ignorate():
    rows = [
        {"categoria": "CARNE", "totale_riga": 50.0},
        {"categoria": "", "totale_riga": 50.0},   # riga senza categoria: non pesa
    ]
    pesi = _pesi_categoria_fattura(_FakeSB(rows), "u", "f.xml")
    assert set(pesi.keys()) == {"CARNE"}
    assert pesi["CARNE"] == pytest.approx(1.0, abs=1e-9)
