"""Dopo una domanda andata a buon fine la chat rimanda i crediti aggiornati.

Il contatore a schermo (Home, `/m`, catena) si aggiorna da `ChatResponse`: se i
numeri della RPC non arrivano, il cliente legge il conteggio di prima e scopre
il limite solo sbattendoci contro. Fase J, 10/10/2026.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw


def _chat(monkeypatch, *, contesto, esito_rpc):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "order", "limit", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(
        data=[{"id": "rid-1", "nome_ristorante": "A"}, {"id": "rid-2", "nome_ristorante": "B"}],
        count=2,
    )
    sb.table.return_value = q
    chiamate = []

    def consuma(*a, **k):
        chiamate.append(a)
        return esito_rpc

    user = {"id": "u-1", "email": "u@x.it", "nome_ristorante": "A", "pagine_abilitate": None}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(user))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (150, contesto == "catena"))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 1500)
    monkeypatch.setattr(fw, "_chat_crediti_consuma", consuma)
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, s: {"chat_ai_enabled": True})
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)
    monkeypatch.setattr(fw._su, "verifica_catena", lambda u: None)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s=None: "ristorazione")
    monkeypatch.setattr(fw, "_build_chat_system_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr(fw, "_build_chat_system_prompt_catena", lambda *a, **k: "prompt")
    monkeypatch.setattr(fw, "_chat_loop_openai", lambda *a, **k: ("Fatto.", 1, 1))
    req = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="ciao")], contesto=contesto)
    return fw.chat_ai(req, authorization="Bearer t"), chiamate, sb


@pytest.mark.parametrize("contesto", ["sede", "catena"])
def test_la_risposta_porta_i_crediti_della_rpc(monkeypatch, contesto):
    r, chiamate, sb = _chat(
        monkeypatch, contesto=contesto,
        esito_rpc={"esito": "ok", "oggi": 9, "mese": 1500, "ricarica": 297, "da_ricarica": True},
    )
    assert (r.limite_giorno, r.limite_mese) == (150, 1500)
    assert (r.crediti_oggi, r.crediti_mese, r.crediti_ricarica) == (9, 1500, 297)
    assert chiamate == [("u-1", "rid-1", contesto == "catena", 150, 1500, sb)]


def test_la_ricarica_sotto_zero_si_mostra_zero(monkeypatch):
    r, _, _ = _chat(
        monkeypatch, contesto="sede",
        esito_rpc={"esito": "ok", "oggi": 3, "mese": 1500, "ricarica": -2},
    )
    assert r.crediti_ricarica == 0
