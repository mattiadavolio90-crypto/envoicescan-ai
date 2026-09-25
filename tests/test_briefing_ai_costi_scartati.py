"""I token del briefing AI si registrano anche quando la frase viene scartata.

Residuo della fase 4 del piano consulente, chiuso il 25/09/2026: in
`_narrate_with_ai` il tracking dei costi stava DOPO i tre ritorni al template
(risposta vuota, troncata, bocciata dal validatore). Quelle chiamate erano
pagate a OpenAI ma non finivano nel registro dei costi: il costo per cliente
risultava sottostimato proprio nei casi in cui l'AI lavorava male.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import services.daily_briefing_service as dbs


def _risposta(testo, finish="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=testo), finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=40),
    )


def _narra(risposta, valida=True):
    registrati = []

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**_k):
                    return risposta

    with patch("services.ai_service._get_openai_client", return_value=_Client()), \
         patch("services.ai_service._resolve_ristorante_id", return_value="r1"), \
         patch("services.ai_cost_service.track_ai_usage",
               lambda **k: registrati.append(k)), \
         patch.object(dbs, "_narrazione_e_valida", lambda *a, **k: (valida, "prova")):
        out = dbs._narrate_with_ai(["Manca l'incasso di ieri."], "TEMPLATE")
    return out, registrati


@pytest.mark.parametrize("risposta, valida, caso", [
    (_risposta(""), True, "vuota"),
    (_risposta("Frase a meta", finish="length"), True, "troncata"),
    (_risposta("Frase inventata con 999 euro."), False, "scartata dal validatore"),
])
def test_la_chiamata_scartata_si_paga_e_si_registra(risposta, valida, caso):
    out, registrati = _narra(risposta, valida)
    assert out == "TEMPLATE", caso
    assert len(registrati) == 1, f"{caso}: token non registrati"
    assert registrati[0]["prompt_tokens"] == 120 and registrati[0]["completion_tokens"] == 40


def test_la_chiamata_buona_si_registra_una_volta_sola():
    out, registrati = _narra(_risposta("Oggi manca l'incasso di ieri."))
    assert out == "Oggi manca l'incasso di ieri."
    assert len(registrati) == 1
    assert registrati[0]["operation_type"] == "daily_briefing"
