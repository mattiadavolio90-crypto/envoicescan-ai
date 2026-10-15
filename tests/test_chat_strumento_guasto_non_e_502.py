"""Un guasto di uno strumento di sede torna al modello, non diventa un 502.

Perche' esiste
==============
Audit di ottobre 2026 (K17): i crediti si scalano PRIMA del giro con OpenAI. Solo
gli strumenti della fase F avevano un try: un'eccezione negli altri otto
risaliva a `_chat_loop_openai` e diventava un 502, con i 3 crediti gia' spesi e
nessuna risposta. Ora ogni strumento di sede ha la stessa rete della catena: il
modello riceve `errore` e lo dice.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import services.fastapi_worker as fw

STRUMENTI = {
    "query_costi": "_chat_query_costi",
    "query_scadenze": "_chat_query_scadenze",
    "query_margini": "_chat_query_margini",
    "confronto_prezzi": "_chat_confronto_prezzi",
    "ultimi_acquisti": "_chat_ultimi_acquisti",
    "trend_prezzo": "_chat_trend_prezzo",
    "query_appuntamenti": "_chat_query_appuntamenti",
    "query_coperti": "_chat_query_coperti",
}


def _esegui(nome):
    return fw._chat_esegui_tool_sede(
        nome, {"prodotto": "x"}, user={"id": "u"}, supabase_client=MagicMock(),
        authorization=None, ristorante_id="rid-1", settore="ristorazione")


@pytest.mark.parametrize("nome,funzione", sorted(STRUMENTI.items()))
def test_un_eccezione_diventa_un_errore_per_il_modello(nome, funzione, monkeypatch, caplog):
    monkeypatch.setattr(fw, funzione, MagicMock(side_effect=RuntimeError("timeout supabase")))
    with caplog.at_level("WARNING"):
        out = _esegui(nome)
    assert "non dire che non c'e'" in out["errore"]
    assert "timeout supabase" in caplog.text


def test_un_rifiuto_http_passa_il_suo_messaggio(monkeypatch):
    monkeypatch.setattr(fw, "_chat_query_costi", MagicMock(side_effect=HTTPException(403, "pagina non attiva")))
    assert _esegui("query_costi") == {"errore": "pagina non attiva"}


def test_la_fase_f_resta_protetta(monkeypatch):
    monkeypatch.setattr(fw, "_chat_query_tag", MagicMock(side_effect=RuntimeError("pandas")))
    out = fw._chat_esegui_tool_sede(
        "query_tag", {}, user={"id": "u", "pagine_abilitate": None}, supabase_client=MagicMock(),
        authorization=None, ristorante_id="rid-1", settore="ristorazione")
    assert "non dire che non c'e'" in out["errore"]
