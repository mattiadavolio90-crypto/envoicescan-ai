"""L'ordine delle rotte del router riparto: le letterali prima delle parametriche.

Regressione 25/8/2026 (traceback Railway). `PATCH /api/riparto/riga-categoria` era
dichiarata 344 righe DOPO `PATCH /api/riparto/{riparto_id}`. FastAPI risolve le rotte
nell'ordine di dichiarazione, non per specificita': ogni richiesta alla rotta letterale
finiva in `riparto_modifica` con riparto_id="riga-categoria" e Postgres rispondeva
`invalid input syntax for type uuid` (22P02) — che senza handler globale il cliente
leggeva come "Worker unreachable", e con handler come "Errore interno (APIError)".

Nessun test sul comportamento dell'endpoint poteva accorgersene: chiamavano la funzione
direttamente, saltando il routing. L'unico modo di vederlo e' interrogare l'app montata.
"""
from fastapi.routing import APIRoute

from services.fastapi_worker import app


def _match(metodo: str, path: str):
    """Il primo endpoint che l'app sceglierebbe davvero per (metodo, path)."""
    scope = {"type": "http", "method": metodo, "path": path, "path_params": {}, "headers": []}
    for rotta in app.router.routes:
        if not isinstance(rotta, APIRoute):
            continue
        match, _ = rotta.matches(scope)
        if match.name == "FULL":
            return rotta
    return None


def test_patch_riga_categoria_non_finisce_nella_rotta_parametrica():
    rotta = _match("PATCH", "/api/riparto/riga-categoria")
    assert rotta is not None, "nessuna rotta risolve PATCH /api/riparto/riga-categoria"
    assert rotta.endpoint.__name__ == "riparto_riga_categoria", (
        f"risolta in {rotta.endpoint.__name__}: la parametrica {{riparto_id}} e' "
        "dichiarata prima della letterale e la intercetta"
    )


def test_le_rotte_letterali_di_riparto_precedono_la_parametrica():
    """Guardia generale: vale per ogni segmento letterale sotto /api/riparto/."""
    parametriche = [
        r for r in app.router.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/riparto/{")
    ]
    assert parametriche, "atteso almeno un /api/riparto/{riparto_id}"
    prima_parametrica = min(app.router.routes.index(r) for r in parametriche)

    letterali = [
        r for r in app.router.routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/api/riparto/")
        and "{" not in r.path
    ]
    tardive = [
        r.path for r in letterali
        if app.router.routes.index(r) > prima_parametrica
        and any(r.methods & p.methods for p in parametriche)
    ]
    assert not tardive, (
        f"rotte letterali dichiarate dopo la parametrica, con verbo in collisione: {tardive}"
    )


def test_patch_con_uuid_vero_resta_sulla_parametrica():
    """Confine: lo spostamento non deve rubare le richieste legittime."""
    rotta = _match("PATCH", "/api/riparto/9f3d0c1e-4b2a-4c11-9d77-2b6a5e0f1234")
    assert rotta is not None
    assert rotta.endpoint.__name__ == "riparto_modifica"
