"""Bozze al fornitore spente (Mattia, 3/10/2026; prima: fase 3, step 4).

L'assistente non scrive bozze per trattare con un fornitore e non si offre di
farlo: se gliele chiedono rimanda a Osservatorio → Score Fornitori, dove sono
gia' pronte — ma solo a chi quella scheda la vede. Lo strumento `bozza_fornitore`
e il campo `bozze` della risposta non esistono piu'.

Il prompt di un ristorante senza Osservatorio e' confrontato byte per byte in
`test_chat_settore_retail.py`; qui le varianti.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from services.routers.prezzi import _bozza_trattativa
from tests.test_chat_settore_retail import USER, _kpi_mock, _sb

NON_SCRIVERE = "- Non scrivere messaggi o bozze per trattare con un fornitore e non offrirti di farlo"
RIMANDO = (NON_SCRIVERE + ": se il cliente te li chiede, digli che li trova pronti, con i suoi "
           "acquisti, in Osservatorio → Score Fornitori")


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


def _utente(prezzi: bool, score_spento: bool = False):
    pagine = {"margini": True, "analisi_fatture": True, "prezzi": prezzi}
    if score_spento:
        pagine["tab_off_prezzi_score"] = True
    return dict(USER, pagine_abilitate=pagine)


def test_con_lo_score_rimanda_allo_score(monkeypatch):
    assert RIMANDO + ".\n" in _prompt(monkeypatch, user=_utente(True))


def test_l_admin_senza_restrizioni_e_rimandato_allo_score(monkeypatch):
    assert RIMANDO + ".\n" in _prompt(monkeypatch, user=dict(USER, pagine_abilitate=None))


def test_con_lo_score_spento_non_ci_rimanda(monkeypatch):
    p = _prompt(monkeypatch, user=_utente(True, score_spento=True))
    assert NON_SCRIVERE + ".\n" in p
    assert "Score Fornitori" not in p


def test_senza_osservatorio_non_ci_rimanda(monkeypatch):
    p = _prompt(monkeypatch, user=_utente(False))
    assert NON_SCRIVERE + ".\n" in p
    assert "Score Fornitori" not in p


def test_la_regola_vale_anche_senza_card(monkeypatch):
    """`/m` non mostra card: anche li' l'assistente non deve scrivere bozze."""
    assert RIMANDO + ".\n" in _prompt(monkeypatch, user=_utente(True), card=False)


def test_il_negozio_ha_la_stessa_regola(monkeypatch):
    assert RIMANDO + ".\n" in _prompt(monkeypatch, user=_utente(True), settore=SETTORE_RETAIL)


def test_la_catena_rimanda_allo_score_del_locale(monkeypatch):
    assert RIMANDO + ", aprendo quel locale." in _prompt_catena(monkeypatch, user=_utente(True))
    assert RIMANDO + ", aprendo quel punto vendita." in _prompt_catena(
        monkeypatch, user=_utente(True), settore=SETTORE_RETAIL)
    assert RIMANDO + ", aprendo quel locale." in _prompt_catena(monkeypatch, user=_utente(True), card=False)


def test_la_catena_senza_score_non_ci_rimanda(monkeypatch):
    for u in (_utente(False), _utente(True, score_spento=True)):
        p = _prompt_catena(monkeypatch, user=u)
        assert NON_SCRIVERE + "." in p
        assert "Score Fornitori" not in p


def test_nessuna_traccia_della_vecchia_regola(monkeypatch):
    for p in (_prompt(monkeypatch, user=_utente(True)), _prompt_catena(monkeypatch, user=_utente(True))):
        assert "bozza_fornitore" not in p
        assert "pulsante Copia" not in p
        assert "la trova pronta da copiare" not in p


def test_lo_strumento_non_esiste_piu():
    nomi = {t["function"]["name"] for t in fw._CHAT_TOOLS_SEDE + fw._CHAT_TOOLS_GRUPPO}
    assert "bozza_fornitore" not in nomi
    assert "bozza_fornitore" not in fw._CHAT_TOOL_FLAG
    assert not hasattr(fw._assistente, "prepara_bozza")
    assert "bozze" not in fw.ChatResponse.model_fields


def test_il_testo_della_bozza_non_parla_di_ristorazione():
    """Regola 7: la bozza dello Score non devia per i negozi perche' il testo e' neutro."""
    b = _bozza_trattativa("ittica marina", "feb–ago 2026", [("salmone", 16.0, 30.0)], 30.0, ["orata"], "instabile")
    assert b.attiva
    testo = b.testo.lower()
    for parola in ("ristorant", "cucina", "food", "coperti", "locale", "menu"):
        assert parola not in testo, parola
