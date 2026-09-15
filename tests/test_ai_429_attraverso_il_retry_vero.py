"""Un 429 di OpenAI a meta' lotto, attraverso il `@retry` VERO del call site (L6).

`test_ai_deadline_retry` prova stop e wait di tenacity su una funzione sintetica
che solleva ValueError. Qui l'errore e' `openai.RateLimitError`, sollevato dal
client sotto `_chiama_gpt_classificazione`, e il decoratore che lo vede e' quello
che gira in produzione: se qualcuno lo sposta, lo rimuove o cambia le classi
ritentabili, questi test lo dicono.

Dal 28/8/2026 il conftest mocka solo streamlit: `tenacity` e `openai` sono veri.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
import tenacity
from openai import RateLimitError

from services import ai_service

IGNOTO = "ZZQX ARTICOLO IGNOTO AL DIZIONARIO 1"


def _errore_429():
    richiesta = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return RateLimitError(
        "Rate limit reached", response=httpx.Response(429, request=richiesta), body=None,
    )


def _risposta(categorie):
    dati = {
        "risultati": [
            {"idx": i, "categoria": c, "confidence": "alta"} for i, c in enumerate(categorie)
        ]
    }
    messaggio = SimpleNamespace(content=json.dumps(dati))
    return SimpleNamespace(
        choices=[SimpleNamespace(message=messaggio, finish_reason="stop")], usage=None,
    )


class _ClientOpenAI:
    """Risponde secondo la sequenza data: un'eccezione si solleva, il resto si ritorna."""

    def __init__(self, esiti):
        self._esiti = list(esiti)
        self.chiamate = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chiamate += 1
        esito = self._esiti.pop(0)
        if isinstance(esito, BaseException):
            raise esito
        return esito


@pytest.fixture(autouse=True)
def _retry_vero_senza_attese(monkeypatch):
    # stop e predicato restano quelli di produzione; solo l'attesa (2..30 s) va a zero,
    # altrimenti ogni test dormirebbe sei secondi.
    monkeypatch.setattr(
        ai_service._chiama_gpt_classificazione.retry, "wait", tenacity.wait_none(),
    )
    monkeypatch.setattr("services.ai_cost_service.track_ai_usage", lambda **k: None)
    ai_service.clear_ai_deadline()
    yield
    ai_service.clear_ai_deadline()


def _una_categoria_ammessa():
    return next(
        c for c in ai_service._categorie_ammesse_per(None)
        if c != "Da Classificare" and "NOTE" not in c
    )


def test_due_429_poi_una_risposta_valida_non_perdono_il_lotto():
    categoria = _una_categoria_ammessa()
    client = _ClientOpenAI([_errore_429(), _errore_429(), _risposta([categoria])])

    categorie, confidenze = ai_service._chiama_gpt_classificazione(
        [IGNOTO], client, return_confidenze=True,
    )

    assert categorie == [categoria]
    assert confidenze == ["alta"]
    assert client.chiamate == 3, "il terzo tentativo non e' partito"


def test_tre_429_di_fila_esauriscono_i_tentativi_veri():
    client = _ClientOpenAI([_errore_429()] * 5)

    with pytest.raises(tenacity.RetryError):
        ai_service._chiama_gpt_classificazione([IGNOTO], client, return_confidenze=True)

    assert client.chiamate == 3, "il tetto e' tre tentativi, ne sono partiti altri"


def test_la_quota_giornaliera_esaurita_non_viene_ritentata():
    """Un RuntimeError non e' transitorio: ritentarlo pagherebbe tre volte la stessa risposta."""
    client = _ClientOpenAI([RuntimeError("quota giornaliera esaurita")] * 3)

    with pytest.raises(RuntimeError):
        ai_service._chiama_gpt_classificazione([IGNOTO], client, return_confidenze=True)

    assert client.chiamate == 1


def test_429_persistente_lascia_la_riga_da_classificare_e_lo_dichiara():
    """Regola di dominio #1: dopo i tre tentativi la riga resta 'Da Classificare',
    visibile in coda, e il degrado e' leggibile dal chiamante — nessuna categoria inventata."""
    ai_service.reset_ai_degradata()
    client = _ClientOpenAI([_errore_429()] * 9)

    categorie, confidenze = ai_service.classifica_con_ai(
        [IGNOTO], openai_client=client, return_confidenze=True,
    )

    assert categorie == ["Da Classificare"]
    assert len(confidenze) == 1
    assert ai_service.ai_degradata() is True
    assert client.chiamate == 3, "classifica_con_ai ha ritentato oltre il retry del call site"
