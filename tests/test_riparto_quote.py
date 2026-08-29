"""Unit del calcolo quote di ripartizione costi di gruppo (services/routers/riparto.py).

Invariante non negoziabile: la somma delle quote_importo pareggia SEMPRE l'importo
totale (nessun centesimo perso o creato per arrotondamento), sia per 'equa' che per
'percentuali'. Questo evita che il MOL di gruppo sia diverso dalla somma dei MOL di
sede. Funzioni pure: nessun DB.
"""
import pytest

from services.routers.riparto import _quote_equa, _quote_percentuali
from fastapi import HTTPException


# ─── _quote_equa ──────────────────────────────────────────────────────────────

def test_equa_due_sedi_pari():
    q = _quote_equa(1000.0, ["A", "B"])
    assert [x["quota_importo"] for x in q] == [500.0, 500.0]
    assert sum(x["quota_importo"] for x in q) == 1000.0
    assert [x["ristorante_id"] for x in q] == ["A", "B"]


def test_equa_tre_sedi_arrotondamento_pareggia():
    # 1000 / 3 = 333.33... : l'ultima quota assorbe il resto → somma = 1000 esatta.
    q = _quote_equa(1000.0, ["A", "B", "C"])
    importi = [x["quota_importo"] for x in q]
    assert importi[0] == 333.33
    assert importi[1] == 333.33
    assert importi[2] == 333.34  # l'ultima pareggia
    assert sum(importi) == 1000.0


def test_equa_importo_dispari_centesimi():
    q = _quote_equa(100.01, ["A", "B", "C"])
    assert sum(x["quota_importo"] for x in q) == pytest.approx(100.01, abs=1e-9)


def test_equa_una_sede():
    q = _quote_equa(750.0, ["A"])
    assert q == [{"ristorante_id": "A", "quota_perc": 100.0, "quota_importo": 750.0}]


def test_equa_zero_sedi():
    assert _quote_equa(500.0, []) == []


# ─── _quote_percentuali ───────────────────────────────────────────────────────

def test_percentuali_70_30():
    q = _quote_percentuali(1000.0, {"A": 70.0, "B": 30.0}, {"A", "B"})
    importi = {x["ristorante_id"]: x["quota_importo"] for x in q}
    assert importi["A"] == 700.0
    assert importi["B"] == 300.0
    assert sum(x["quota_importo"] for x in q) == 1000.0


def test_percentuali_pareggio_su_terzi():
    # 33.33/33.33/33.34 su 900 → l'ultima pareggia, somma = 900 esatta.
    q = _quote_percentuali(900.0, {"A": 33.33, "B": 33.33, "C": 33.34}, {"A", "B", "C"})
    assert sum(x["quota_importo"] for x in q) == pytest.approx(900.0, abs=1e-9)


def test_percentuali_escludi_una_sede_con_zero():
    # "solo 2 sedi su 3": la terza a 0% non riceve quota.
    q = _quote_percentuali(500.0, {"A": 50.0, "B": 50.0, "C": 0.0}, {"A", "B", "C"})
    ids = {x["ristorante_id"] for x in q}
    assert ids == {"A", "B"}
    assert sum(x["quota_importo"] for x in q) == 500.0


def test_percentuali_somma_diversa_da_100_errore():
    with pytest.raises(HTTPException) as exc:
        _quote_percentuali(1000.0, {"A": 60.0, "B": 30.0}, {"A", "B"})  # somma 90
    assert exc.value.status_code == 400


def test_percentuali_vuote():
    assert _quote_percentuali(1000.0, {}, set()) == []


def test_percentuali_tolleranza_arrotondamento():
    # 99.9 e 100.1 devono passare (tolleranza 0.5); 99.4 no.
    _quote_percentuali(100.0, {"A": 49.95, "B": 49.95}, {"A", "B"})  # somma 99.9: ok
    with pytest.raises(HTTPException):
        _quote_percentuali(100.0, {"A": 50.0, "B": 49.4}, {"A", "B"})  # somma 99.4: ko


def test_percentuali_sede_estranea_rifiutata():
    # CRITICAL fix (audit Security 29/7): un ristorante_id fuori dalle sedi
    # del chiamante deve essere rifiutato con 400, non silenziosamente accettato
    # (altrimenti si scrive nel MOL di un altro account).
    with pytest.raises(HTTPException) as exc:
        _quote_percentuali(1000.0, {"A": 50.0, "SEDE-ALTRUI": 50.0}, {"A", "B"})
    assert exc.value.status_code == 400


def test_percentuali_tutte_sedi_estranee_rifiutate():
    with pytest.raises(HTTPException) as exc:
        _quote_percentuali(1000.0, {"SEDE-ALTRUI": 100.0}, {"A", "B"})
    assert exc.value.status_code == 400


# ─── Percentuali negative ─────────────────────────────────────────────────────
# Il filtro `if float(p) > 0` SCARTAVA le negative invece di rifiutarle, quindi
# il controllo sulla somma non le vedeva mai. Provato per mutazione il
# 29/8/2026 sui casi qui sotto: i primi due venivano ACCETTATI.

class TestPercentualiNegative:

    def test_negativa_non_fa_sparire_una_sede_dal_riparto(self):
        """{A:50, B:50, C:-30}: i positivi fanno 100, quindi il controllo sulla
        somma passava e il costo finiva su due sedi invece di tre. Il cliente
        vedeva un riparto su tre sedi e il MOL della terza non riceveva nulla."""
        with pytest.raises(HTTPException) as exc:
            _quote_percentuali(1000.0, {"A": 50, "B": 50, "C": -30}, {"A", "B", "C"})
        assert exc.value.status_code == 400
        assert "negative" in exc.value.detail.lower()

    def test_tutte_negative_non_restituiscono_lista_vuota(self):
        """Prima: nessun errore e nessuna quota — il costo spariva in silenzio."""
        with pytest.raises(HTTPException) as exc:
            _quote_percentuali(1000.0, {"A": -50, "B": -50}, {"A", "B"})
        assert exc.value.status_code == 400

    def test_negativa_compensata_da_un_eccesso(self):
        """{A:-20, B:120}: somma 100 lato client, ma il riparto reale sarebbe 120."""
        with pytest.raises(HTTPException) as exc:
            _quote_percentuali(1000.0, {"A": -20, "B": 120}, {"A", "B"})
        assert exc.value.status_code == 400
        assert "negative" in exc.value.detail.lower()

    def test_il_messaggio_dice_quante_sedi(self):
        with pytest.raises(HTTPException) as exc:
            _quote_percentuali(1000.0, {"A": -10, "B": -10, "C": 120}, {"A", "B", "C"})
        assert "2" in exc.value.detail

    def test_le_percentuali_valide_restano_accettate(self):
        q = _quote_percentuali(1000.0, {"A": 50, "B": 30, "C": 20}, {"A", "B", "C"})
        assert sum(x["quota_importo"] for x in q) == 1000.0
        assert len(q) == 3

    def test_lo_zero_resta_ammesso_e_non_crea_quota(self):
        """Zero non e' negativo: la sede semplicemente non partecipa."""
        q = _quote_percentuali(1000.0, {"A": 100, "B": 0}, {"A", "B"})
        assert [x["ristorante_id"] for x in q] == ["A"]
        assert sum(x["quota_importo"] for x in q) == 1000.0
