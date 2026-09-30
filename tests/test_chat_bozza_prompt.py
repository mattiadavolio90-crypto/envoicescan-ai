"""Fase 3, step 4: cosa dice il prompt sulla bozza al fornitore.

Il prompt senza card e' confrontato byte per byte in
`test_chat_settore_retail.py`; qui le deviazioni: la regola c'e' solo con le card
e la pagina Prezzi, la catena rimanda alla Home del locale.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from services.routers.prezzi import _bozza_trattativa
from tests.test_chat_settore_retail import USER, _kpi_mock, _sb

REGOLA = "usa bozza_fornitore: il testo lo vede in una card con il pulsante Copia"
RINVIO = "Se il cliente ti chiede una bozza per trattare con un fornitore, qui non si prepara"


def _prompt(monkeypatch, user=USER, settore=SETTORE_RISTORAZIONE, card=True):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    return fw._build_chat_system_prompt(user, _sb(), None, "r-1", settore, cifre_dettate=card)


def _prompt_catena(monkeypatch, user=USER, settore=SETTORE_RISTORAZIONE, card=True):
    monkeypatch.setattr(
        fw, "_gruppo_router_mod",
        lambda: MagicMock(gruppo_overview=MagicMock(side_effect=RuntimeError("no"))),
    )
    return fw._build_chat_system_prompt_catena(user, _sb(), None, settore, cifre_dettate=card)


def _con_prezzi(prezzi: bool):
    return dict(USER, pagine_abilitate={"margini": True, "analisi_fatture": True, "prezzi": prezzi})


def test_con_prezzi_e_card_la_regola_c_e(monkeypatch):
    p = _prompt(monkeypatch, user=_con_prezzi(True))
    assert REGOLA in p
    assert "Non scrivere mai una bozza tua, nemmeno per accorciarla o cambiarla dopo" in p
    assert "Se lo strumento dice che non c'e' niente da trattare, spiegagli il motivo." in p


def test_senza_prezzi_niente_regola(monkeypatch):
    assert "bozza_fornitore" not in _prompt(monkeypatch, user=_con_prezzi(False))


def test_senza_card_niente_regola(monkeypatch):
    assert "bozza_fornitore" not in _prompt(monkeypatch, user=_con_prezzi(True), card=False)


def test_il_negozio_ha_la_stessa_regola(monkeypatch):
    assert REGOLA in _prompt(monkeypatch, user=_con_prezzi(True), settore=SETTORE_RETAIL)


def test_la_catena_rimanda_alla_home_del_locale(monkeypatch):
    p = _prompt_catena(monkeypatch, user=_con_prezzi(True))
    assert RINVIO in p
    assert "nella Home di quel locale la trova pronta da copiare" in p
    assert "bozza_fornitore" not in p
    assert "nella Home di quel punto vendita" in _prompt_catena(
        monkeypatch, user=_con_prezzi(True), settore=SETTORE_RETAIL)


def test_la_catena_senza_prezzi_o_senza_card_non_rimanda(monkeypatch):
    assert RINVIO not in _prompt_catena(monkeypatch, user=_con_prezzi(False))
    assert RINVIO not in _prompt_catena(monkeypatch, user=_con_prezzi(True), card=False)


def test_lo_strumento_sta_su_prezzi_e_fuori_dalla_catena():
    nomi = {t["function"]["name"] for t in fw._CHAT_TOOLS_SEDE}
    assert fw._assistente.STRUMENTO_BOZZA in nomi
    assert fw._CHAT_TOOL_FLAG["bozza_fornitore"] == "prezzi"
    assert "bozza_fornitore" not in fw._CHAT_TOOLS_SEDE_IN_CATENA
    assert "bozza_fornitore" in fw._assistente.STRUMENTI_CARD


def test_il_testo_della_bozza_non_parla_di_ristorazione():
    """Regola 7: nessuna deviazione per i negozi perche' il testo e' neutro."""
    b = _bozza_trattativa("ittica marina", "feb–ago 2026", [("salmone", 16.0, 30.0)], 30.0, ["orata"], "instabile")
    assert b.attiva
    testo = b.testo.lower()
    for parola in ("ristorant", "cucina", "food", "coperti", "locale", "menu"):
        assert parola not in testo, parola


# ─── Il nome del fornitore detto dal cliente ────────────────────────────────
class _F:
    def __init__(self, nome, spesa=0.0):
        self.fornitore = nome
        self.spesa_periodo = spesa


FORNITORI = [_F("ITTICA MARINA SRL", 100), _F("ITTICA DEL SUD", 900), _F("PANIFICIO  ROSSI", 50)]


def _trova(q):
    return fw._assistente._trova_fornitore(q, FORNITORI)


def test_nome_esatto_senza_maiuscole_e_spazi():
    assert _trova("panificio rossi")[0].fornitore == "PANIFICIO  ROSSI"


def test_il_nome_esatto_vince_su_chi_lo_contiene():
    """«Bar» e' BAR, non un'ambiguita' con BARILLA."""
    trovato, _ = fw._assistente._trova_fornitore("bar", [_F("BARILLA SPA"), _F("BAR")])
    assert trovato.fornitore == "BAR"


def test_un_pezzo_di_nome_che_ne_identifica_uno():
    assert _trova("Ittica Marina")[0].fornitore == "ITTICA MARINA SRL"


def test_un_pezzo_ambiguo_chiede_quale():
    trovato, al_modello = _trova("ittica")
    assert trovato is None
    assert "chiedi al cliente quale" in al_modello["errore"]
    assert al_modello["fornitori"] == ["ITTICA MARINA SRL", "ITTICA DEL SUD"]


def test_meno_di_tre_lettere_non_basta():
    """«pa» identificherebbe il solo PANIFICIO: due lettere indovinano, non riconoscono."""
    assert _trova("pa")[0] is None


def test_nome_vuoto_nessun_fornitore():
    assert _trova("")[0] is None
    assert _trova(None)[0] is None


def test_non_trovato_elenco_per_spesa():
    trovato, al_modello = _trova("macelleria")
    assert trovato is None
    assert al_modello["fornitori"] == ["ITTICA DEL SUD", "ITTICA MARINA SRL", "PANIFICIO  ROSSI"]


def test_lettura_fallita_nessuna_bozza_e_si_riprova(monkeypatch):
    from services.routers import prezzi

    def _rotta(*_a, **_k):
        raise RuntimeError("timeout PostgREST")

    monkeypatch.setattr(prezzi, "_load_fatture_for_prezzi", _rotta)
    monkeypatch.setattr(fw._assistente, "_oggi", lambda: __import__("datetime").date(2026, 9, 30))
    bozza, al_modello = fw._assistente.prepara_bozza({"fornitore": "x"}, sb=None, ristorante_id="r-1", sede_nome=None)
    assert bozza is None
    assert "riprovare" in al_modello["errore"]


def test_senza_locale_aperto_nessuna_bozza():
    bozza, al_modello = fw._assistente.prepara_bozza({"fornitore": "x"}, sb=None, ristorante_id=None, sede_nome=None)
    assert bozza is None and "nessun locale" in al_modello["errore"]
