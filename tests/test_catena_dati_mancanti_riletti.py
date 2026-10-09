"""«Mancano …» della catena si rilegge quando la Home si apre (residuo 4 della fase G).

Lo snapshot dei segnali vale fino a mezzanotte, gli avvisi delle sedi si
ricalcolano ogni minuto. Se il cliente inseriva il fatturato in giornata, la riga
della sede continuava a dire «Mancano il fatturato» mentre l'avviso della sede si
era gia' spento. Ora l'endpoint e il conteggio del briefing tolgono le voci che,
rilette, non mancano piu'. Si toglie soltanto: mai una voce in piu' dello
snapshot, e una lettura fallita lascia lo snapshot com'e'.

I test eseguono il codice vero (helper, endpoint, overview) con un finto client.
"""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from services.routers import gruppo
from tests.test_catena_errore_non_diventa_tutto_ok import _overview_con_completezza
from tests.test_segnali_catena_snapshot_versionato import _FakeSB, _snapshot

FRASE = {v: k for k, v in gruppo._CHIAVE_MANCA.items()}


def _dm(rid="a", manca=("fatturato", "fatture"), **extra):
    manca = list(manca)
    s = {
        "tipo": "dati_mancanti", "severity": "warning", "ristorante_id": rid,
        "pv_nome": f"PV {rid}", "testo": gruppo._testo_dati_mancanti([FRASE[k] for k in manca]),
        "cta_page": "/dashboard", "manca": manca, "mese": 9,
    }
    s.update(extra)
    return s


ALTRO = {
    "tipo": "margine_calo", "severity": "warning", "ristorante_id": "a",
    "pv_nome": "PV a", "testo": "Margine 60%, era 70%", "cta_page": "/margini",
}


# ── L'helper ────────────────────────────────────────────────────────────────

class TestRestringi:
    def test_lettura_fallita_lascia_lo_snapshot(self):
        segnali = [_dm()]
        assert gruppo._restringi_dati_mancanti(segnali, None) == segnali

    def test_sede_ora_completa_esce(self):
        assert gruppo._restringi_dati_mancanti([_dm()], {}) == []

    def test_voce_inserita_esce_e_la_frase_si_rifa(self):
        out = gruppo._restringi_dati_mancanti([_dm()], {"a": ["le fatture costo"]})
        assert len(out) == 1
        assert out[0]["manca"] == ["fatture"]
        assert out[0]["testo"] == "Mancano le fatture costo — vai a completare nel punto vendita"
        assert out[0]["mese"] == 9 and out[0]["pv_nome"] == "PV a"

    def test_niente_di_nuovo_resta_identico(self):
        s = _dm()
        out = gruppo._restringi_dati_mancanti([s], {"a": ["il fatturato", "le fatture costo"]})
        assert out == [s]

    def test_non_aggiunge_voci_che_lo_snapshot_non_aveva(self):
        # Il personale che non era nello snapshot (es. non ancora dovuto prima
        # del 15) non rientra dalla rilettura.
        out = gruppo._restringi_dati_mancanti(
            [_dm(manca=["fatturato"])], {"a": ["il fatturato", gruppo._MANCA_PERSONALE]},
        )
        assert out[0]["manca"] == ["fatturato"]
        assert out[0]["testo"] == "Mancano il fatturato — vai a completare nel punto vendita"

    def test_sede_assente_dalla_rilettura_non_vale_per_le_altre(self):
        out = gruppo._restringi_dati_mancanti(
            [_dm("a"), _dm("b")], {"b": ["il fatturato", "le fatture costo"]},
        )
        assert [s["ristorante_id"] for s in out] == ["b"]

    def test_altri_segnali_restano(self):
        assert gruppo._restringi_dati_mancanti([ALTRO], {}) == [ALTRO]

    def test_segnale_di_errore_resta(self):
        errore = _dm(rid="", manca=[])
        errore.pop("manca")
        assert gruppo._restringi_dati_mancanti([errore], {}) == [errore]

    def test_snapshot_senza_manca_resta(self):
        vecchio = _dm()
        vecchio.pop("manca")
        assert gruppo._restringi_dati_mancanti([vecchio], {}) == [vecchio]

    def test_voce_sconosciuta_non_si_verifica_e_resta(self):
        strano = _dm(manca=["fatturato"])
        strano["manca"] = ["fatturato", "magazzino"]
        assert gruppo._restringi_dati_mancanti([strano], {}) == [strano]

    @pytest.mark.parametrize("chiave", sorted(gruppo._CHIAVE_MANCA.values()))
    def test_ogni_voce_si_spegne_da_sola(self, chiave):
        altre = [k for k in sorted(gruppo._CHIAVE_MANCA.values()) if k != chiave]
        out = gruppo._restringi_dati_mancanti(
            [_dm(manca=sorted(gruppo._CHIAVE_MANCA.values()))],
            {"a": [FRASE[k] for k in altre]},
        )
        assert chiave not in out[0]["manca"]
        assert sorted(out[0]["manca"]) == altre


# ── L'endpoint: la cache del giorno si rilegge ──────────────────────────────

def _endpoint(segnali, completezza=None, errore=None):
    sb = _FakeSB(_snapshot(gruppo._SEGNALI_CODE_VERSION, segnali))
    chiamate = {}

    def finta_completezza(_sb, ids, **kw):
        chiamate["ids"] = list(ids)
        chiamate["costi_mese"] = kw.get("costi_mese")
        if errore:
            raise errore
        return completezza

    def finti_costi(user_id, ids, anno, mese, costi_auto=None):
        chiamate["mese_costi"] = (anno, mese)
        return {"marker": 1.0}

    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, "user-1", [], "Catena", {}, ["a", "b", "c"])), \
         patch.object(gruppo, "_completezza_dati_pv", side_effect=finta_completezza), \
         patch.object(gruppo, "_costi_mese_per_sede", side_effect=finti_costi), \
         patch.object(gruppo, "_calcola_segnali", side_effect=AssertionError("ricalcolo")):
        resp = gruppo.gruppo_segnali(force=False, authorization="Bearer t")
    return resp, chiamate


def test_endpoint_toglie_il_dato_inserito_in_giornata():
    resp, _ = _endpoint([_dm("a"), ALTRO], completezza={"a": ["le fatture costo"]})
    dm = [s for s in resp.segnali if s.tipo == "dati_mancanti"]
    assert [s.manca for s in dm] == [["fatture"]]
    assert dm[0].testo.startswith("Mancano le fatture costo")
    assert any(s.tipo == "margine_calo" for s in resp.segnali)


def test_endpoint_toglie_la_sede_completata():
    resp, _ = _endpoint([_dm("a")], completezza={})
    assert resp.segnali == []


def test_endpoint_rilegge_solo_le_sedi_dello_snapshot_e_il_mese_chiuso():
    _, chiamate = _endpoint([_dm("b"), _dm("a"), ALTRO], completezza={})
    assert chiamate["ids"] == ["a", "b"]
    assert chiamate["costi_mese"] == {"marker": 1.0}
    assert chiamate["mese_costi"] == gruppo._mese_chiuso(datetime.now(ZoneInfo("Europe/Rome")).date())


def test_endpoint_senza_dati_mancanti_non_fa_query():
    _, chiamate = _endpoint([ALTRO], completezza={})
    assert chiamate == {}


def test_endpoint_con_rilettura_fallita_serve_lo_snapshot():
    resp, _ = _endpoint([_dm("a")], errore=RuntimeError("rpc giu'"))
    assert [s.manca for s in resp.segnali] == [["fatturato", "fatture"]]


def test_endpoint_con_completezza_non_determinabile_serve_lo_snapshot():
    resp, _ = _endpoint([_dm("a")], completezza=None)
    assert len(resp.segnali) == 1


# ── Il briefing conta come la Home ──────────────────────────────────────────

def test_conteggio_toglie_le_sedi_completate():
    sb = _FakeSB(_snapshot(gruppo._SEGNALI_CODE_VERSION, [_dm("a"), _dm("b"), ALTRO]))
    n, _ = gruppo._conta_segnali_cache(sb, "u1", {"b": ["il fatturato"]})
    assert n == 2


def test_la_gravita_si_calcola_sui_segnali_rimasti():
    sb = _FakeSB(_snapshot(gruppo._SEGNALI_CODE_VERSION, [_dm("a", severity="error"), ALTRO]))
    assert gruppo._conta_segnali_cache(sb, "u1", {}) == (1, "warning")
    assert gruppo._conta_segnali_cache(sb, "u1", None) == (2, "error")


def test_conteggio_senza_completezza_conta_lo_snapshot():
    sb = _FakeSB(_snapshot(gruppo._SEGNALI_CODE_VERSION, [_dm("a"), _dm("b"), ALTRO]))
    assert gruppo._conta_segnali_cache(sb, "u1")[0] == 3
    assert gruppo._conta_segnali_cache(sb, "u1", None)[0] == 3


@pytest.mark.parametrize("completezza", [{}, {"a": ["il fatturato"]}, None])
def test_l_overview_passa_la_completezza_letta(completezza):
    visti = []

    def spia(sb, user_id, completezza_viva=None):
        visti.append(completezza_viva)
        return 0, "info"

    with patch.object(gruppo, "_conta_segnali_cache", side_effect=spia):
        _overview_con_completezza(completezza)
    assert visti == [completezza]
