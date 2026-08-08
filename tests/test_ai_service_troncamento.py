"""Test della diagnostica di troncamento in `_chiama_gpt_classificazione`
(services/ai_service.py), aggiunta l'8/8/2026 dall'audit ONEFLUX §1.

Contesto: quando l'AI esaurisce `max_tokens` a meta' lista, `finish_reason` vale
'length' e il JSON puo' essere sintatticamente VALIDO ma incompleto. Il codice
gia' gestiva il caso in modo sicuro — gli idx mancanti finiscono in
"Da Classificare", nessuno slittamento di categoria — ma `finish_reason` non
veniva mai letto, quindi la causa era invisibile nei log: sembrava che l'AI non
sapesse classificare, mentre il batch era solo troppo grande.

Questi test verificano le DUE proprieta' che contano:
- la sicurezza (nessuna categoria sbagliata assegnata) resta garantita;
- il troncamento viene ora loggato con batch_size e max_tokens.
"""
import importlib
import json
import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="module")
def ai():
    """`services.ai_service` ricaricato con `tenacity.retry` pass-through.

    Il conftest globale mocka l'intero modulo `tenacity`, quindi il decoratore
    `@retry` su `_chiama_gpt_classificazione` diventa un MagicMock e la funzione
    vera non e' piu' chiamabile: qualunque assert sul suo risultato confronterebbe
    un MagicMock. Qui si sostituisce solo `retry` con l'identita' e si ricarica il
    modulo, ripristinando poi lo stato precedente per non alterare gli altri test.
    """
    ten_orig = sys.modules.get("tenacity")
    ten = MagicMock()
    ten.retry = lambda *a, **k: (lambda f: f)
    ten.stop_after_attempt = MagicMock()
    ten.wait_exponential = MagicMock()
    ten.retry_if_exception_type = MagicMock()
    sys.modules["tenacity"] = ten

    import services.ai_service as _ai
    modulo = importlib.reload(_ai)
    try:
        yield modulo
    finally:
        if ten_orig is not None:
            sys.modules["tenacity"] = ten_orig
        importlib.reload(_ai)


def _fake_client(payload: dict, finish_reason: str):
    """Client OpenAI finto: risponde con `payload` e il finish_reason richiesto."""
    msg = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    resp = SimpleNamespace(
        choices=[choice],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=4096),
    )
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


_ARTICOLI = ["POMODORI PELATI", "MOZZARELLA FIORDILATTE", "OLIO EVO", "BIRRA MEDIA"]


def _payload_parziale():
    """Solo i primi 2 idx su 4: e' come si presenta una risposta troncata."""
    return {"risultati": [
        {"idx": 0, "categoria": "SCATOLAME E CONSERVE", "confidenza": "alta"},
        {"idx": 1, "categoria": "LATTICINI", "confidenza": "alta"},
    ]}


def test_troncamento_logga_batch_e_max_tokens(ai, caplog):
    client = _fake_client(_payload_parziale(), finish_reason="length")
    with caplog.at_level(logging.WARNING, logger=ai.logger.name):
        ai._chiama_gpt_classificazione(_ARTICOLI, client, max_tokens=4096)

    troncamento = [r for r in caplog.records if "TRONCATA" in r.getMessage()]
    assert len(troncamento) == 1, "il troncamento deve essere loggato una volta"
    msg = troncamento[0].getMessage()
    assert "finish_reason=length" in msg
    assert "4" in msg and "4096" in msg, "servono batch_size e max_tokens nel log"


def test_nessun_log_troncamento_quando_la_risposta_e_completa(ai, caplog):
    payload = {"risultati": [
        {"idx": 0, "categoria": "SCATOLAME E CONSERVE", "confidenza": "alta"},
        {"idx": 1, "categoria": "LATTICINI", "confidenza": "alta"},
        {"idx": 2, "categoria": "OLIO E CONDIMENTI", "confidenza": "alta"},
        {"idx": 3, "categoria": "BIRRE", "confidenza": "alta"},
    ]}
    client = _fake_client(payload, finish_reason="stop")
    with caplog.at_level(logging.WARNING, logger=ai.logger.name):
        out = ai._chiama_gpt_classificazione(_ARTICOLI, client, max_tokens=4096)

    assert not [r for r in caplog.records if "TRONCATA" in r.getMessage()]
    assert out == ["SCATOLAME E CONSERVE", "LATTICINI", "OLIO E CONDIMENTI", "BIRRE"]


def test_righe_mancanti_restano_da_classificare_non_slittano(ai):
    """Regola di dominio #1: mai una categoria inventata al posto di quella vera.
    Le righe non restituite devono valere "Da Classificare", NON la categoria
    dell'articolo successivo."""
    client = _fake_client(_payload_parziale(), finish_reason="length")
    out = ai._chiama_gpt_classificazione(_ARTICOLI, client, max_tokens=4096)

    assert out[0] == "SCATOLAME E CONSERVE"
    assert out[1] == "LATTICINI"
    assert out[2] == "Da Classificare"
    assert out[3] == "Da Classificare"


def test_finish_reason_assente_non_solleva(ai):
    """Un client/SDK che non espone finish_reason non deve rompere la chiamata."""
    msg = SimpleNamespace(content=json.dumps(_payload_parziale()))
    choice = SimpleNamespace(message=msg)  # nessun finish_reason
    resp = SimpleNamespace(choices=[choice], usage=None)
    client = MagicMock()
    client.chat.completions.create.return_value = resp

    out = ai._chiama_gpt_classificazione(_ARTICOLI, client, max_tokens=4096)
    assert len(out) == len(_ARTICOLI)
