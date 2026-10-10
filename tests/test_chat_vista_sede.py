"""L'assistente nella vista punto vendita parla solo del locale aperto
(step 5 dell'interfaccia, decisione di Mattia del 28/9/2026, fatto il 29/9).

Due difetti chiusi:
- il prompt della vista PV nominava l'ACCOUNT (users.nome_ristorante, cioe'
  la prima sede), non la sede aperta: un cliente catena dentro NAVIGLI parlava
  con «il gestionale del ristorante CASATI»;
- nessuna regola diceva cosa fare se si chiedeva di un altro locale: gli
  strumenti sono legati alla sede attiva, quindi rispondevano con i numeri di
  questo locale a una domanda su un altro.

Una guardia 409 sulla sede a schermo (`sede_id`) e' stata scritta e tolta
prima del push: /auth/me e chat_ai leggono la sede attiva da cache per processo
diverse, e subito dopo un cambio di sede divergono — la guardia bloccava la chat
proprio nel passaggio catena -> punto vendita (revisore, 29/9). Il test in fondo
fissa che il campo non torni senza una fonte unica della sede.

Gli account mono-sede non vedono cambiamenti: il loro prompt e' byte per byte
quello di prima (lo fissa anche test_chat_settore_retail.py).
"""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import services.fastapi_worker as fw
from services.fastapi_worker import _build_chat_system_prompt
from tests.test_chat_gate_permessi_pagina import USER_TUTTO, _kpi_mock, _sb_dati_puliti

ACCOUNT = dict(USER_TUTTO, nome_ristorante="CASATI 14")


@pytest.fixture(autouse=True)
def _dati(monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))


def _prompt(**kw):
    return _build_chat_system_prompt(ACCOUNT, _sb_dati_puliti(), None, ristorante_id="rid-2", **kw)


def _intestazione(prompt: str) -> str:
    return prompt.splitlines()[0]


# ─── Il prompt ──────────────────────────────────────────────────────────────


def test_catena_in_vista_pv_nomina_la_sede_aperta():
    p = _prompt(sede_nome="NAVIGLI", multi_sede=True)
    assert _intestazione(p) == 'Sei l\'assistente AI di ONEFLUX, integrato nel gestionale del ristorante "NAVIGLI".'
    assert "CASATI 14" not in p


def test_catena_in_vista_pv_rimanda_alla_catena_per_gli_altri_locali():
    p = _prompt(sede_nome="NAVIGLI", multi_sede=True)
    assert "## Solo questo locale (IMPORTANTE)" in p
    assert 'da qui vedi solo "NAVIGLI"' in p
    assert "deve passare alla vista catena" in p
    # Niente pulsanti del menu desktop: su /m non c'e' la sidebar.
    assert "menu a sinistra" not in p
    assert "NON rispondere con i numeri di \"NAVIGLI\"" in p


def test_mono_sede_prompt_identico_a_prima():
    """Nessuna riga nuova per chi ha un locale solo, e il nome resta quello
    dell'account anche se per sbaglio arrivasse un nome di sede."""
    prima = _build_chat_system_prompt(ACCOUNT, _sb_dati_puliti(), None, ristorante_id="rid-2")
    assert _prompt(sede_nome="ALTRO", multi_sede=False) == prima
    assert "Solo questo" not in prima
    assert '"CASATI 14"' in _intestazione(prima)


def test_nome_sede_non_letto_ripiega_sull_account():
    p = _prompt(sede_nome=None, multi_sede=True)
    assert '"CASATI 14"' in _intestazione(p)
    assert "## Solo questo locale" in p


def test_negozio_dice_negozio():
    p = _prompt(sede_nome="CENTRO", multi_sede=True, settore="retail")
    assert "## Solo questo negozio (IMPORTANTE)" in p
    assert "Solo questo locale" not in p


def test_nome_sede_letto_dalla_tabella_ristoranti():
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"nome_ristorante": "  NAVIGLI "}])
    sb.table.return_value = q
    assert fw._chat_nome_sede("rid-2", sb) == "NAVIGLI"
    q.eq.assert_called_with("id", "rid-2")


@pytest.mark.parametrize("dati", [[], [{"nome_ristorante": ""}], [{"nome_ristorante": None}]])
def test_nome_sede_assente_e_none(dati):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=dati)
    sb.table.return_value = q
    assert fw._chat_nome_sede("rid-2", sb) is None


def test_nome_sede_lettura_fallita_non_rompe_la_chat():
    sb = MagicMock()
    sb.table.side_effect = RuntimeError("db giu'")
    assert fw._chat_nome_sede("rid-2", sb) is None
    assert fw._chat_nome_sede(None, sb) is None


# ─── chat_ai: cosa passa al prompt, e la guardia sulla sede a schermo ───────


class _Fermo(Exception):
    pass


def _prepara(monkeypatch, *, pool, attiva="rid-2"):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "limit", "order", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"nome_ristorante": "NAVIGLI"}], count=2)
    sb.table.return_value = q
    sb.rpc.return_value.execute.return_value = MagicMock(data=1)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(ACCOUNT, id="u-1"))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: attiva)
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, pool))
    monkeypatch.setattr(fw, "_chat_crediti_consuma", lambda *a, **k: {"esito": "ok", "oggi": 3, "mese": 3, "ricarica": 0})
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 600)
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, s: {"chat_ai_enabled": True})
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s: "ristorazione")
    visto = {}

    def _cattura(*a, **k):
        visto.update(k)
        raise _Fermo()

    monkeypatch.setattr(fw, "_build_chat_system_prompt", _cattura)
    return sb, visto


def _req():
    return fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="ciao")], contesto="sede")


def test_account_catena_passa_nome_sede_e_multi_sede(monkeypatch):
    _, visto = _prepara(monkeypatch, pool=True)
    with pytest.raises(_Fermo):
        fw.chat_ai(_req(), authorization="Bearer t")
    assert visto == {"sede_nome": "NAVIGLI", "multi_sede": True, "cifre_dettate": False, "mobile": False}


def test_mono_sede_non_legge_il_nome_ne_cambia_il_prompt(monkeypatch):
    sb, visto = _prepara(monkeypatch, pool=False)
    with pytest.raises(_Fermo):
        fw.chat_ai(_req(), authorization="Bearer t")
    assert visto == {"sede_nome": None, "multi_sede": False, "cifre_dettate": False, "mobile": False}


def test_sotto_utente_con_una_sola_sede_non_viene_mandato_alla_catena(monkeypatch):
    """Il pool conta le sedi del titolare; il sotto-utente con una sede sola
    non ha altri locali ne' la vista catena."""
    _, visto = _prepara(monkeypatch, pool=True)
    monkeypatch.setattr(fw._su, "e_sotto_utente", lambda u: True)
    monkeypatch.setattr(fw, "_num_sedi_sotto_utente", lambda u: 1)
    with pytest.raises(_Fermo):
        fw.chat_ai(_req(), authorization="Bearer t")
    assert visto == {"sede_nome": None, "multi_sede": False, "cifre_dettate": False, "mobile": False}


def test_sotto_utente_con_piu_sedi_resta_nella_regola(monkeypatch):
    _, visto = _prepara(monkeypatch, pool=True)
    monkeypatch.setattr(fw._su, "e_sotto_utente", lambda u: True)
    monkeypatch.setattr(fw, "_num_sedi_sotto_utente", lambda u: 2)
    with pytest.raises(_Fermo):
        fw.chat_ai(_req(), authorization="Bearer t")
    assert visto == {"sede_nome": "NAVIGLI", "multi_sede": True, "cifre_dettate": False, "mobile": False}


def test_la_guardia_sulla_sede_a_schermo_non_torna():
    """Tolta il 29/9: le due letture della sede attiva non hanno una fonte
    unica. Se si vuole rimetterla, prima serve quella."""
    assert "sede_id" not in fw.ChatRequest.model_fields
