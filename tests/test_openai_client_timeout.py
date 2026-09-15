"""Il client OpenAI non aspetta dieci minuti (lente L6, 15/09/2026).

`openai.DEFAULT_TIMEOUT` e' 600 s in lettura: un batch di classificazione appeso
teneva un processo del worker (sono 4) per dieci minuti, per tre volte con i retry
del SDK, per tre volte con quelli di tenacity. Il budget AI dell'upload (25 s)
tronca le attese fra un tentativo e l'altro ma non puo' interrompere la richiesta
in volo: solo il timeout del client lo fa.
"""
from __future__ import annotations

import ast
import pathlib

import openai

from config.constants import OPENAI_TIMEOUT_SECONDS
from services import ai_service

RADICE = pathlib.Path(__file__).resolve().parents[1]


def test_il_default_del_sdk_e_davvero_dieci_minuti():
    """Se un giorno il SDK cambiasse default, il resto di questo file avrebbe meno senso."""
    assert openai.DEFAULT_TIMEOUT.read == 600


def test_il_client_di_classificazione_ha_il_timeout_del_progetto():
    # `_get_openai_client` e' sotto `st.cache_resource`, che nei test e' un MagicMock:
    # si prova la fabbrica che costruisce davvero il client.
    client = ai_service._nuovo_client_openai("sk-test-l6")

    assert client.timeout == OPENAI_TIMEOUT_SECONDS
    assert 0 < OPENAI_TIMEOUT_SECONDS <= 120, "un batch non deve tenere un processo piu' di due minuti"


def _nome(func):
    if isinstance(func, ast.Attribute):
        return _nome(func.value) + "." + func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_nessun_client_openai_costruito_senza_timeout():
    """Ogni `OpenAI(...)` nel codice di produzione dichiara un timeout."""
    senza = []
    for cartella in ("services", "worker", "utils"):
        for percorso in sorted((RADICE / cartella).rglob("*.py")):
            albero = ast.parse(percorso.read_text(encoding="utf-8-sig"))
            for nodo in ast.walk(albero):
                if not isinstance(nodo, ast.Call):
                    continue
                if _nome(nodo.func) not in ("OpenAI", "openai.OpenAI"):
                    continue
                if not any(k.arg == "timeout" for k in nodo.keywords):
                    senza.append(f"{percorso.relative_to(RADICE)}:{nodo.lineno}")
    assert senza == [], f"client OpenAI col timeout di default (600 s): {senza}"
