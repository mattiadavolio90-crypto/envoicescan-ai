"""Riparto per categoria (Voce 6, services/riparto_service.py).

Invariante non negoziabile: spezzando la quota di una sede nelle sue categorie, la
SOMMA delle porzioni pareggia SEMPRE la quota originale (nessun centesimo perso o
creato). È lo stesso principio di test_riparto_quote.py, un livello più in basso:
lì si spezza l'importo fra sedi, qui si spezza la quota di sede fra categorie.

_spezza_importo_per_pesi è pura (nessun DB). _pesi_categoria_fattura fa una query:
testata con un fake client minimale che ritorna righe predefinite.
"""
import pytest

from services.riparto_service import (
    _spezza_importo_per_pesi,
    _pesi_categoria_fattura,
    _proietta_riparto,
    _mesi_nella_finestra,
)


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


# ─── _proietta_riparto (Lettura B: quote → righe sul PV) ─────────────────────
#
# Invariante non negoziabile: la SOMMA dei totali delle righe proiettate di una
# categoria pareggia AL CENTESIMO la quota_importo di quella categoria per il PV.
# È ciò che garantisce che il PV non veda né più né meno della sua quota reale.

def _id_gen():
    c = {"n": 0}
    def _next():
        c["n"] -= 1
        return c["n"]
    return _next


def _righe(*coppie):
    """helper: crea righe reali (categoria, quantita, prezzo, totale)."""
    return [
        {"categoria": cat, "quantita": q, "prezzo_unitario": p, "totale_riga": t,
         "descrizione": f"{cat} art", "fornitore": "METRO", "unita_misura": "KG",
         "file_origine": "f.xml", "numero_riga": i}
        for i, (cat, q, p, t) in enumerate(coppie)
    ]


def test_proietta_pareggia_la_quota_per_categoria():
    # 3 righe VERDURE reali (tot 100), il PV ne prende il 65% → 65.00 esatti.
    reali = _righe(
        ("VERDURE", 10, 3.0, 30.0),
        ("VERDURE", 20, 2.0, 40.0),
        ("VERDURE", 15, 2.0, 30.0),
    )
    quote = [{"categoria": "VERDURE", "quota_importo": 65.00}]
    out = _proietta_riparto(reali, quote, 65.0, _id_gen())
    somma = round(sum(r["totale_riga"] for r in out), 2)
    assert somma == 65.00
    # prezzo unitario REALE (non scalato), quantità scalata del 65%
    assert out[0]["prezzo_unitario"] == 3.0
    assert out[0]["quantita"] == pytest.approx(6.5, abs=1e-6)
    # id sintetici negativi (inerti alle batch operations)
    assert all(r["id"] < 0 for r in out)
    assert all(r["ripartita_su_gruppo"] for r in out)


def test_proietta_piu_categorie_ognuna_pareggia():
    reali = _righe(
        ("VERDURE", 10, 5.0, 50.0),
        ("CARNE", 4, 25.0, 100.0),
    )
    quote = [
        {"categoria": "VERDURE", "quota_importo": 25.00},  # 50% di 50
        {"categoria": "CARNE", "quota_importo": 50.00},    # 50% di 100
    ]
    out = _proietta_riparto(reali, quote, 50.0, _id_gen())
    per_cat = {}
    for r in out:
        per_cat.setdefault(r["categoria"], 0.0)
        per_cat[r["categoria"]] += r["totale_riga"]
    assert round(per_cat["VERDURE"], 2) == 25.00
    assert round(per_cat["CARNE"], 2) == 50.00


def test_proietta_arrotondamento_ultima_riga_pareggia():
    # quota che non si divide in centesimi netti: l'ultima riga assorbe il resto.
    reali = _righe(
        ("VERDURE", 1, 1.0, 33.33),
        ("VERDURE", 1, 1.0, 33.33),
        ("VERDURE", 1, 1.0, 33.34),
    )
    quote = [{"categoria": "VERDURE", "quota_importo": 21.67}]  # 21.666 arrotondato
    out = _proietta_riparto(reali, quote, 21.667, _id_gen())
    assert round(sum(r["totale_riga"] for r in out), 2) == 21.67


def test_proietta_fallback_sintetico_senza_righe_vive():
    # storico purgato (GDPR): nessuna riga reale → una riga sintetica per categoria.
    quote = [{"categoria": "MANUTENZIONE E ATTREZZATURE", "quota_importo": 120.00}]
    out = _proietta_riparto([], quote, 40.0, _id_gen())
    assert len(out) == 1
    r = out[0]
    assert r["totale_riga"] == 120.00
    assert r["prezzo_unitario"] == 120.00
    assert r["categoria"] == "MANUTENZIONE E ATTREZZATURE"
    assert r["ripartita_su_gruppo"] is True
    assert "Quota di gruppo" in r["descrizione"]
    # categoria valorizzata → non serve verifica manuale
    assert r["needs_review"] is False


def test_proietta_quota_categoria_senza_righe_reali_corrispondenti():
    # il PV ha una quota per una categoria che non compare fra le righe reali
    # (es. classificazione cambiata): fallback sintetico, quadra comunque.
    reali = _righe(("VERDURE", 10, 3.0, 30.0))
    quote = [{"categoria": "CARNE", "quota_importo": 15.00}]
    out = _proietta_riparto(reali, quote, 50.0, _id_gen())
    assert len(out) == 1
    assert out[0]["categoria"] == "CARNE"
    assert out[0]["totale_riga"] == 15.00
    assert out[0]["needs_review"] is False


def test_proietta_quota_senza_categoria_marcata_needs_review():
    # quota legacy con categoria NULL/vuota: la riga sintetica generica NON può
    # presentarsi al cliente come "confermata" — deve restare da verificare.
    quote = [{"categoria": None, "quota_importo": 80.00}]
    out = _proietta_riparto([], quote, 40.0, _id_gen())
    assert len(out) == 1
    r = out[0]
    assert r["categoria"] is None
    assert r["totale_riga"] == 80.00
    assert r["needs_review"] is True


# ─── _mesi_nella_finestra ────────────────────────────────────────────────────

def test_mesi_finestra_singolo_mese():
    assert _mesi_nella_finestra("2026-03-01", "2026-03-31") == {(2026, 3)}


def test_mesi_finestra_a_cavallo_anno():
    m = _mesi_nella_finestra("2025-12-15", "2026-02-10")
    assert m == {(2025, 12), (2026, 1), (2026, 2)}


def test_mesi_finestra_aperta_none():
    assert _mesi_nella_finestra(None, None) is None
