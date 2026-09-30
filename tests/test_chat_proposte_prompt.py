"""Fase 3, step 2: cosa dice il prompt sulle cifre dettate.

Il prompt intero del ristorante e' confrontato byte per byte in
`test_chat_settore_retail.py`; qui le deviazioni: senza la pagina Margini le
regole non ci sono (gli strumenti non ci sono), il negozio chiede anche il 22%,
la catena rimanda al locale.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from tests.test_chat_settore_retail import USER, _kpi_mock, _sb

REGOLA = "usa proponi_incasso, proponi_personale o proponi_fatturato_mese"


def _prompt(monkeypatch, user=USER, settore=SETTORE_RISTORAZIONE, cifre=True):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    return fw._build_chat_system_prompt(user, _sb(), None, "r-1", settore, cifre_dettate=cifre)


def test_con_margini_le_regole_delle_cifre_dettate_ci_sono(monkeypatch):
    p = _prompt(monkeypatch)
    assert REGOLA in p
    assert "Non dire mai che la cifra e' registrata" in p
    assert "CHIEDIGLI quanto e' al 10% e quanto senza IVA" in p
    assert "Il 22% indicalo solo se lo nomina il cliente." in p


def test_senza_margini_niente_regole_ne_offerta_di_dettare(monkeypatch):
    senza = dict(USER, pagine_abilitate={"analisi_fatture": True, "agenda": True})
    p = _prompt(monkeypatch, user=senza)
    assert "proponi_" not in p
    assert "prepari tu la registrazione" not in p


def test_senza_card_nel_client_il_prompt_e_quello_di_prima(monkeypatch):
    """Il default (`/m`, ogni chiamante che non lo dichiara): niente regole e gli
    avvisi di ieri. Il confronto byte per byte col testo di ieri e' in
    test_chat_settore_retail.test_ramo_ristorazione_e_identico_a_prima."""
    p = _prompt(monkeypatch, cifre=False)
    assert "proponi_" not in p
    assert "prepari tu la registrazione" not in p
    assert "Suggerisci di registrare i ricavi in Movimenti → Ricavi." in p


def test_con_card_gli_avvisi_offrono_di_dettare(monkeypatch):
    p = _prompt(monkeypatch)
    assert "Movimenti → Ricavi, oppure di dettarti qui il fatturato del mese" in p
    assert "(sezione Personale), oppure di dirti qui la cifra" in p


def test_il_negozio_chiede_anche_il_22(monkeypatch):
    p = _prompt(monkeypatch, settore=SETTORE_RETAIL)
    assert REGOLA in p
    assert "CHIEDIGLI quanto e' al 22%, quanto al 10% e quanto senza IVA" in p
    assert "Il 22% indicalo solo se lo nomina il cliente." not in p


def _prompt_catena(monkeypatch, settore):
    monkeypatch.setattr(
        fw, "_gruppo_router_mod",
        lambda: MagicMock(gruppo_overview=MagicMock(side_effect=RuntimeError("no"))),
    )
    return fw._build_chat_system_prompt_catena(USER, _sb(), None, settore)


def test_la_catena_rimanda_alla_home_del_locale(monkeypatch):
    p = _prompt_catena(monkeypatch, SETTORE_RISTORAZIONE)
    assert "qui non si registra: spiega che basta aprire la Home di quel locale" in p
    assert "proponi_" not in p
    assert "aprire la Home di quel punto vendita" in _prompt_catena(monkeypatch, SETTORE_RETAIL)


def test_le_regole_nominano_solo_strumenti_che_esistono():
    nomi = {t["function"]["name"] for t in fw._CHAT_TOOLS_SEDE}
    assert set(fw._assistente.STRUMENTI_PROPOSTA) <= nomi
    for nome in fw._assistente.STRUMENTI_PROPOSTA:
        assert fw._CHAT_TOOL_FLAG[nome] == "margini"
        assert nome not in fw._CHAT_TOOLS_SEDE_IN_CATENA
