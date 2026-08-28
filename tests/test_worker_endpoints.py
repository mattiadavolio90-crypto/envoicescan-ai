"""Contratto dei tre endpoint storici del worker: /health, /api/classify, /api/parse.

Sostituisce `tests/worker_test.py` (cancellato il 28/8/2026), che era uno script
di smoke manuale: parlava via `requests` con un worker vero su localhost:8000,
con `print()` e un blocco `__main__`. Non veniva raccolto da pytest — `testpaths`
scandisce le directory applicando `python_files = test_*.py`, e il *suffisso*
`_test.py` non matcha — quindi non girava ne' in locale ne' in CI. Rinominarlo
sarebbe stato peggio che cancellarlo: in CI nessuno ascolta su :8000, e i tre
test sarebbero stati rossi fissi (oggi falliscono sulla guardia di rete del
conftest, che e' esattamente il punto).

Qui gli stessi tre endpoint sono guidati in-process con `TestClient`, come gia'
fa `test_worker_metrics.py`: nessuna socket, nessun worker da avviare, nessuna
chiamata a GPT.

Cosa NON si copre, deliberatamente: la classificazione AI vera e il parsing di
una fattura vera. Il primo costa una chiamata a GPT, il secondo e' gia' coperto
in profondita' dai test di `invoice_service`. Qui si verifica il contratto
dell'endpoint — auth, validazione, forma della risposta — non la logica a valle.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def worker():
    import os

    os.environ.setdefault("WORKER_DEV_MODE", "1")
    os.environ.setdefault("SUPABASE_URL", "http://x")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
    import services.fastapi_worker as fw

    return fw


@pytest.fixture
def client(worker):
    """Client senza credenziali: `_verify_worker_key` e' attivo."""
    return TestClient(worker.app, raise_server_exceptions=False)


@pytest.fixture
def client_autenticato(worker):
    """Client con `_verify_worker_key` neutralizzato via dependency_overrides.

    Non si passa una X-Worker-Key vera: la chiave che il worker ha in memoria
    arriva da `.env` (load_dotenv(override=True) all'import) ed e' quella di
    PRODUZIONE. Un test non deve dipendere da un segreto reale ne' scriverlo nel
    repo; l'override e' il modo pulito di dire "qui l'auth non e' il soggetto".
    """
    worker.app.dependency_overrides[worker._verify_worker_key] = lambda: None
    yield TestClient(worker.app, raise_server_exceptions=False)
    worker.app.dependency_overrides.clear()


def test_health_risponde_ok(client):
    """`/health` e' la sonda di Railway: deve restare pubblica e dire status=ok."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.parametrize(
    "metodo, path, kwargs",
    [
        ("post", "/api/classify", {"json": {"descrizioni": ["Olio evo"], "user_id": "u"}}),
        ("post", "/api/parse", {"files": {"file": ("t.xml", b"<x/>", "application/xml")}}),
    ],
)
def test_endpoint_protetti_rifiutano_senza_chiave(client, metodo, path, kwargs):
    """Senza X-Worker-Key valida entrambi gli endpoint devono dare 401.

    E' la proprieta' che lo script vecchio non verificava affatto: girando in
    locale con la chiave in ambiente, il 401 non lo vedeva mai.
    """
    r = getattr(client, metodo)(path, **kwargs)
    assert r.status_code == 401


def test_classify_rifiuta_lista_vuota(client_autenticato):
    """Lista vuota = 422 dal modello Pydantic (min_length=1), non un 200 con
    lista vuota: un batch vuoto che passa silenzioso maschera un bug a monte."""
    r = client_autenticato.post("/api/classify", json={"descrizioni": [], "user_id": "u"})
    assert r.status_code == 422


def test_parse_rifiuta_estensione_non_supportata(client_autenticato):
    """Solo XML e P7M. Un .txt deve essere respinto con un messaggio che nomina
    il formato ricevuto — serve a chi legge i log dell'upload."""
    r = client_autenticato.post(
        "/api/parse",
        files={"file": ("t.txt", b"non sono una fattura", "text/plain")},
        data={"user_id": "u"},
    )
    assert r.status_code == 422
    assert "txt" in r.json()["detail"]
