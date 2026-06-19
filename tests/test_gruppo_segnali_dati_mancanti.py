"""Test guardia: la CATENA segnala i dati mancanti per PV e li mette PRIMI.

Decisione 19/06 (Mattia): la catena è MACRO e INDIRIZZA ("vai a completare il PV X").
La completezza è per PRESENZA di dati (fatturato + fatture costo + costo personale),
non per % salute. Senza questi, margine/MOL del PV e del gruppo sono falsi: il
segnale dati_mancanti viene PRIMA di ogni confronto, e fa sì che la card "Da vedere
nella catena" non mostri il verde "tutto sotto controllo".
"""
from unittest.mock import MagicMock

from services.routers.gruppo import (
    _calcola_segnali,
    _completezza_dati_pv,
    _elenco_it,
)


class TestElencoIt:
    def test_uno(self):
        assert _elenco_it(["a"]) == "a"

    def test_due(self):
        assert _elenco_it(["a", "b"]) == "a e b"

    def test_tre(self):
        assert _elenco_it(["a", "b", "c"]) == "a, b e c"


def _sb_con_componenti(rows):
    """Mock di sb: sb.rpc(...).execute().data = rows. Le altre table-query usate da
    _calcola_segnali (margini_mensili, ricavi_giornalieri) tornano vuote."""
    sb = MagicMock()

    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=rows)
    sb.rpc.return_value = rpc_res

    tbl = MagicMock()
    tbl.select.return_value = tbl
    tbl.in_.return_value = tbl
    tbl.eq.return_value = tbl
    tbl.gte.return_value = tbl
    tbl.lte.return_value = tbl
    tbl.execute.return_value = MagicMock(data=[], count=0)
    sb.table.return_value = tbl
    return sb


class TestCompletezzaDatiPv:
    def test_pv_completo_non_compare(self):
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 1000, "n_fatture": 5, "personale": 800},
        ])
        out = _completezza_dati_pv(sb, ["a"])
        assert out == {}

    def test_pv_senza_nulla_elenca_tutto(self):
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 0, "n_fatture": 0, "personale": 0},
        ])
        out = _completezza_dati_pv(sb, ["a"])
        assert out["a"] == ["il fatturato", "le fatture costo", "il costo del personale"]

    def test_pv_solo_personale_mancante(self):
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 1000, "n_fatture": 3, "personale": 0},
        ])
        out = _completezza_dati_pv(sb, ["a"])
        assert out["a"] == ["il costo del personale"]


class TestSegnaleDatiMancanti:
    def test_segnale_generato_e_primo(self):
        # PV "b" incompleto (manca tutto), PV "a" completo. Il segnale dati_mancanti
        # per "b" deve esistere ed essere il PRIMO della lista.
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 1000, "n_fatture": 5, "personale": 800},
            {"ristorante_id": "b", "netto": 0, "n_fatture": 0, "personale": 0},
        ])
        segnali = _calcola_segnali(sb, ["a", "b"], {"a": "PV A", "b": "PV B"})
        dm = [s for s in segnali if s["tipo"] == "dati_mancanti"]
        assert len(dm) == 1
        assert dm[0]["ristorante_id"] == "b"
        assert "vai a completare nel punto vendita" in dm[0]["testo"]
        assert segnali[0]["tipo"] == "dati_mancanti"  # priorità: primo in assoluto

    def test_nessun_segnale_se_tutti_completi(self):
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 1000, "n_fatture": 5, "personale": 800},
        ])
        segnali = _calcola_segnali(sb, ["a"], {"a": "PV A"})
        assert [s for s in segnali if s["tipo"] == "dati_mancanti"] == []

    def test_segnale_disattivabile_da_config(self):
        sb = _sb_con_componenti([
            {"ristorante_id": "b", "netto": 0, "n_fatture": 0, "personale": 0},
        ])
        segnali = _calcola_segnali(
            sb, ["b"], {"b": "PV B"}, segnali_off={"dati_mancanti"},
        )
        assert [s for s in segnali if s["tipo"] == "dati_mancanti"] == []
