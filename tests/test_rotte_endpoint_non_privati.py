"""Nessuna rotta del worker e' servita da un helper privato.

Il 5/10/2026 (fase D3) `_ultima_domanda` e' stata inserita fra `@app.post("/api/chat", ...)`
e `def chat_ai`: il decoratore e' passato all'helper, `/api/chat` rispondeva con la
domanda dell'utente invece che con l'assistente, e `chat_ai` restava una funzione
nuda. Il codice si importava e i test, che chiamano `chat_ai` direttamente, erano
verdi; lo ha mostrato solo lo schema OpenAPI (`operationId` cambiato). Era gia'
successo il 10/9 con un `@retry`. Le rotte vere hanno nomi pubblici: un endpoint
che comincia con `_` e' quasi certamente un helper finito sotto un decoratore.
"""
from fastapi.routing import APIRoute

import services.fastapi_worker as fw


def _rotte():
    return [r for r in fw.app.routes if isinstance(r, APIRoute)]


def test_nessun_endpoint_e_un_helper_privato():
    privati = sorted((r.path, r.endpoint.__name__) for r in _rotte() if r.endpoint.__name__.startswith("_"))
    assert privati == []


def test_la_chat_e_servita_da_chat_ai():
    assert [r.endpoint for r in _rotte() if r.path == "/api/chat"] == [fw.chat_ai]
