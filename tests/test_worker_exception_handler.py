"""L'handler globale del worker: un'eccezione non gestita deve tornare JSON.

Regressione 25/8/2026. Senza handler, un'eccezione non gestita tornava con corpo
NON-JSON: lato Next `res.json()` sollevava SyntaxError, che finiva nel catch di rete
e mostrava al cliente "Worker unreachable" — un errore di TRASPORTO — per un errore
APPLICATIVO del worker. Causa invisibile e messaggio falso: sono serviti i log
Railway per scoprire che il worker rispondeva eccome, con un 500.
"""
from fastapi.testclient import TestClient

from services.fastapi_worker import app


def _client() -> TestClient:
    # raise_server_exceptions=False: senza, TestClient rilancia l'eccezione invece
    # di far rispondere l'handler, che e' proprio cio' che vogliamo osservare.
    return TestClient(app, raise_server_exceptions=False)


def test_eccezione_non_gestita_torna_json_e_non_corpo_illeggibile():
    @app.get("/__test_boom")
    def _boom():
        raise RuntimeError("giu'")

    try:
        res = _client().get("/__test_boom")
        assert res.status_code == 500
        body = res.json()  # deve essere JSON: è il punto del test
        assert "RuntimeError" in body["detail"]
        assert body["path"] == "/__test_boom"
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/__test_boom"
        ]


def test_il_traceback_non_finisce_nella_risposta():
    """Il dettaglio tecnico sta nei log, non a video al cliente."""
    @app.get("/__test_boom2")
    def _boom2():
        raise RuntimeError("segreto-da-non-esporre")

    try:
        res = _client().get("/__test_boom2")
        assert "segreto-da-non-esporre" not in res.text
        assert "Traceback" not in res.text
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/__test_boom2"
        ]


def test_httpexception_resta_invariata():
    """L'handler generico non deve inghiottire i 404/422 espliciti dei router,
    trasformandoli tutti in 500 anonimi."""
    @app.get("/__test_404")
    def _notfound():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="non trovato")

    try:
        res = _client().get("/__test_404")
        assert res.status_code == 404
        assert res.json()["detail"] == "non trovato"
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/__test_404"
        ]
