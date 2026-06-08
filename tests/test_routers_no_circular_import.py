"""Guardia anti-import-circolare per i router di services/routers/.

Contesto (incidente 08/06/2026): services/routers/ricavi.py importava
`from services.fastapi_worker import (...)` al top, mentre fastapi_worker importa
i router in coda al file. Quando il WORKER (worker/email_queue_processor.py)
importava ricavi.py per i soli parser — cioe' FUORI dal contesto FastAPI e PRIMA
che fastapi_worker fosse caricato — il ciclo esplodeva con
"cannot import name 'router' from partially initialized module". Il ciclo email
ricavi falliva l'import e non processava mai la coda.

Il bug era attivo solo su ricavi.py (l'unico router importato anche fuori da
FastAPI), ma TUTTI i router hanno lo stesso pattern di import: e' una fragilita'
latente. Questo test la blinda.

Ogni router deve essere importabile DA SOLO, in un interprete fresco, senza che
fastapi_worker sia gia' in sys.modules. Va eseguito in un SUBPROCESS: importarlo
nello stesso processo del resto della suite non riprodurrebbe il problema, perche'
fastapi_worker potrebbe essere gia' caricato da un altro test (falso verde).
"""
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_ROUTERS = [
    "account",
    "admin",
    "cestino",
    "fatture",
    "margini",
    "prezzi",
    "ricavi",
    "scadenziario",
    "tag",
    "workspace",
]


@pytest.mark.parametrize("router_name", _ROUTERS)
def test_router_importabile_isolato(router_name: str) -> None:
    """Il router si importa in un processo fresco senza ciclo con fastapi_worker."""
    module = f"services.routers.{router_name}"
    code = (
        "import sys; "
        f"import {module}; "
        # fastapi_worker NON deve essere stato caricato dal solo import del router:
        # se lo fosse, basterebbe un loop diverso per reintrodurre il ciclo.
        "assert 'services.fastapi_worker' not in sys.modules, "
        f"'{module} carica fastapi_worker al top: rischio import circolare'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Import isolato di {module} fallito (possibile ciclo con fastapi_worker).\n"
        f"--- stderr ---\n{result.stderr}"
    )


def test_worker_importa_parser_ricavi_senza_fastapi_worker() -> None:
    """Riproduce il path del worker: i parser ricavi senza trascinare fastapi_worker.

    E' il caso reale che si era rotto: worker/email_queue_processor.py importa
    _detect_gestionale_version/_parse_passbi_v1/_parse_generico da services.routers.ricavi.
    """
    code = (
        "import sys; "
        "from services.routers.ricavi import ("
        "_detect_gestionale_version, _parse_passbi_v1, _parse_generico); "
        "assert 'services.fastapi_worker' not in sys.modules, "
        "'import parser ricavi trascina fastapi_worker'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Il worker non riesce a importare i parser ricavi senza fastapi_worker.\n"
        f"--- stderr ---\n{result.stderr}"
    )
