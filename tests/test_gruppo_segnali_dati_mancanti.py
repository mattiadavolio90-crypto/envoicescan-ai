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

    def test_mese_esplicito_passato_alla_rpc(self):
        # Selettore periodo nel dialog (es. "Giugno 2026"): la completezza deve
        # essere valutata sul mese scelto, non sempre sull'ultimo mese chiuso.
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 1000, "n_fatture": 5, "personale": 800},
        ])
        _completezza_dati_pv(sb, ["a"], anno=2026, mese=6)
        _, kwargs = sb.rpc.call_args
        assert kwargs == {}
        params = sb.rpc.call_args[0][1]
        assert params["p_anno"] == 2026
        assert params["p_mese"] == 6

    def test_senza_mese_esplicito_usa_comportamento_storico(self):
        sb = _sb_con_componenti([
            {"ristorante_id": "a", "netto": 1000, "n_fatture": 5, "personale": 800},
        ])
        _completezza_dati_pv(sb, ["a"])
        params = sb.rpc.call_args[0][1]
        assert "p_anno" in params and "p_mese" in params


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


class TestVociMancantiConNome:
    """Fase G (9/10/2026): il segnale porta `manca`, le voci con un nome stabile.
    La Home di catena lo toglie da una sede solo quando gli avvisi di quella sede
    dicono gia' OGNI voce: un nome sbagliato o mancante qui terrebbe il doppione,
    uno in piu' farebbe sparire un dato che nessun altro avviso dice."""

    def _dm(self, rows, monkeypatch, personale_dovuto=True):
        import services.routers.gruppo as g
        monkeypatch.setattr(
            g, "_personale_non_ancora_dovuto",
            lambda *a, **k: None if personale_dovuto else 9,
        )
        segnali = _calcola_segnali(_sb_con_componenti(rows), ["b"], {"b": "PV B"})
        return [s for s in segnali if s["tipo"] == "dati_mancanti"]

    def test_tutte_e_tre_le_voci(self, monkeypatch):
        dm = self._dm([{"ristorante_id": "b", "netto": 0, "n_fatture": 0, "personale": 0}], monkeypatch)
        assert dm[0]["manca"] == ["fatturato", "fatture", "personale"]

    def test_solo_le_voci_che_mancano(self, monkeypatch):
        dm = self._dm([{"ristorante_id": "b", "netto": 1000, "n_fatture": 0, "personale": 800}], monkeypatch)
        assert dm[0]["manca"] == ["fatture"]
        assert dm[0]["testo"].startswith("Mancano le fatture costo")

    def test_il_personale_non_ancora_dovuto_non_e_fra_le_voci(self, monkeypatch):
        """Prima del 15 la frase non lo dice: nemmeno `manca` deve dirlo, o la
        Home cercherebbe un avviso del personale che il PV non da'."""
        dm = self._dm(
            [{"ristorante_id": "b", "netto": 0, "n_fatture": 5, "personale": 0}],
            monkeypatch, personale_dovuto=False,
        )
        assert dm[0]["manca"] == ["fatturato"]
        assert "personale" not in dm[0]["testo"]

    def test_le_frasi_hanno_tutte_un_nome(self):
        """Ogni voce che `_completezza_dati_pv` puo' scrivere ha il suo nome."""
        from services.routers.gruppo import _CHIAVE_MANCA
        sb = _sb_con_componenti([{"ristorante_id": "a", "netto": 0, "n_fatture": 0, "personale": 0}])
        assert set(_completezza_dati_pv(sb, ["a"])["a"]) == set(_CHIAVE_MANCA)

    def test_il_campo_arriva_al_client(self):
        from services.routers.gruppo import Segnale
        s = Segnale(tipo="dati_mancanti", severity="warning", ristorante_id="b", pv_nome="PV B",
                    testo="Mancano le fatture costo", cta_page="/dashboard", manca=["fatture"])
        assert s.model_dump()["manca"] == ["fatture"]
        vecchio = Segnale(tipo="margine_calo", severity="warning", ristorante_id="b", pv_nome="PV B",
                          testo="Margine al 30%", cta_page="/margini")
        assert vecchio.manca == []
