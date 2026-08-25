"""Test guardia: endpoint chat_ai non consuma quota per un account single-sede
che invia contesto="catena" (audit §3b chat, F5 — MEDIUM).

Difetto trovato (25/8/2026): is_catena veniva impostato dal solo body.contesto,
senza verificare che l'account fosse davvero multi-sede. La quota (RPC
chat_usage_check_and_log) veniva consumata PRIMA che
_build_chat_system_prompt_catena -> _resolve_gruppo sollevasse il 400 "Account
non multi-sede" — un utente single-sede che provasse contesto="catena" pagava
una domanda della sua quota giornaliera per un errore di validazione.

Fix: verificare il numero di sedi PRIMA della RPC di quota, stessa condizione
di _resolve_gruppo (routers/gruppo.py:627, <2 sedi attive non tecniche).
"""
import os
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import services.fastapi_worker as fw


def _chat_request(contesto="catena"):
    return fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="ciao")], contesto=contesto)


def _sb_n_sedi(n):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"id": i} for i in range(n)], count=n)
    sb.table.return_value = q
    return sb


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_single_sede_in_contesto_catena_rifiutata_senza_consumare_quota(monkeypatch):
    sb = _sb_n_sedi(1)
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: {"id": "u-1", "email": "u@x.it"})
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, False))
    rpc_spy = MagicMock()
    sb.rpc = rpc_spy

    with pytest.raises(HTTPException) as exc_info:
        fw.chat_ai(_chat_request(contesto="catena"), authorization="Bearer t")

    assert exc_info.value.status_code == 400
    assert "multi-sede" in exc_info.value.detail
    rpc_spy.assert_not_called()


def test_multi_sede_in_contesto_catena_procede_oltre_la_validazione(monkeypatch):
    """2 sedi: la guardia NON deve bloccare (verifica che il fix non sia troppo
    aggressivo). Il flusso arriva alla RPC di quota (che qui fa fallire con
    503 fail-closed, dimostrando che il codice e' arrivato oltre il gate)."""
    sb = _sb_n_sedi(2)
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: {"id": "u-1", "email": "u@x.it"})
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, True))
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)

    sb.rpc.side_effect = RuntimeError("rpc non disponibile in questo test")

    with pytest.raises(HTTPException) as exc_info:
        fw.chat_ai(_chat_request(contesto="catena"), authorization="Bearer t")

    # 503 (fail-closed della RPC), non 400: prova che la guardia multi-sede
    # NON ha bloccato un account che invece ha 2 sedi.
    assert exc_info.value.status_code == 503


def test_contesto_sede_non_e_toccato_dalla_guardia(monkeypatch):
    """La guardia si applica solo a contesto='catena': un account single-sede
    in contesto 'sede' (l'uso normale) non deve mai vedere il 400 multi-sede."""
    sb = _sb_n_sedi(1)
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: {"id": "u-1", "email": "u@x.it"})
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, False))
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, s: {"chat_ai_enabled": True})

    sb.rpc.side_effect = RuntimeError("rpc non disponibile in questo test")

    with pytest.raises(HTTPException) as exc_info:
        fw.chat_ai(_chat_request(contesto="sede"), authorization="Bearer t")

    # Se fosse 400 "multi-sede" vorrebbe dire che la guardia si applica anche
    # al contesto sede, bloccando erroneamente l'uso normale.
    assert exc_info.value.status_code == 503
