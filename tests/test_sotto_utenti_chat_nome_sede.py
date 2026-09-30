"""Il prompt della chat nomina il locale di chi scrive, anche per un sotto-utente.

Un sotto-utente con una sola sede in un account catena riceve il prompt
mono-sede (niente rimandi alla vista catena, test_chat_vista_sede.py), e fino al
30/9/2026 con il nome dell'ACCOUNT (users.nome_ristorante = la prima sede del
titolare): a chi lavora a NAVIGLI l'assistente diceva di essere il gestionale di
CASATI. Qui: il nome e' quello della sua sede, e per tutti gli altri non cambia
niente (il builder e i suoi kwarg restano quelli di prima).
"""
import pytest

import services.fastapi_worker as fw
from tests.test_chat_vista_sede import ACCOUNT, _Fermo, _prepara, _req


def _cattura_utente(monkeypatch):
    visto = {}

    def _cattura(user, *a, **k):
        visto["nome"] = user.get("nome_ristorante")
        visto["kwargs"] = k
        raise _Fermo()

    monkeypatch.setattr(fw, "_build_chat_system_prompt", _cattura)
    return visto


def _chat(monkeypatch, *, pool, sotto_utente, sedi_sue=1):
    _prepara(monkeypatch, pool=pool)
    visto = _cattura_utente(monkeypatch)
    if sotto_utente:
        monkeypatch.setattr(fw._su, "e_sotto_utente", lambda u: True)
        monkeypatch.setattr(fw, "_num_sedi_sotto_utente", lambda u: sedi_sue)
    with pytest.raises(_Fermo):
        fw.chat_ai(_req(), authorization="Bearer t")
    return visto


def test_sotto_utente_con_una_sede_in_catena_sente_il_nome_della_sua_sede(monkeypatch):
    visto = _chat(monkeypatch, pool=True, sotto_utente=True)
    assert visto["nome"] == "NAVIGLI"
    assert visto["kwargs"]["sede_nome"] is None and visto["kwargs"]["multi_sede"] is False


def test_titolari_e_sotto_utenti_con_piu_sedi_come_prima(monkeypatch):
    assert _chat(monkeypatch, pool=False, sotto_utente=False)["nome"] == ACCOUNT["nome_ristorante"]
    assert _chat(monkeypatch, pool=True, sotto_utente=False)["nome"] == ACCOUNT["nome_ristorante"]
    assert _chat(monkeypatch, pool=True, sotto_utente=True, sedi_sue=2)["nome"] == ACCOUNT["nome_ristorante"]
    # Account con una sede sola: la sede e' l'account, nessuna lettura in piu'.
    assert _chat(monkeypatch, pool=False, sotto_utente=True)["nome"] == ACCOUNT["nome_ristorante"]


def test_nome_sede_non_letto_ripiega_sull_account(monkeypatch):
    monkeypatch.setattr(fw._su, "e_sotto_utente", lambda u: True)
    monkeypatch.setattr(fw, "_chat_nome_sede", lambda rid, sb: None)
    assert fw._utente_prompt_sede(ACCOUNT, True, False, "rid-2", None)["nome_ristorante"] == "CASATI 14"
    monkeypatch.setattr(fw, "_chat_nome_sede", lambda rid, sb: "NAVIGLI")
    assert fw._utente_prompt_sede(ACCOUNT, True, False, "rid-2", None)["nome_ristorante"] == "NAVIGLI"
