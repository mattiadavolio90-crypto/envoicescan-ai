"""Il prompt che parte davvero verso GPT e' quello del settore (RETAIL_FASI.md Fase 2).

Il test precedente (`test_retail_prompt_coerenza_dominio.py`) legge il TESTO dei
due prompt; questo esegue il classificatore vero con un client OpenAI finto e
guarda il `messages[0]["content"]` effettivamente inviato. Sono due cose diverse:
un prompt retail perfetto che nessuno seleziona non classifica niente, e il
sintomo sarebbe indistinguibile da "il prompt non funziona".

Si copre anche il RETRY: `classifica_con_ai` richiama GPT sui "Da Classificare"
residui, e un retry che perde il settore rimanderebbe il prompt dei ristoranti
(e' esattamente il mutante sopravvissuto al primo giro nella 1.4).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.ai_service as ai
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from config.prompt_ai_potenziato import (
    PROMPT_CLASSIFICAZIONE_AI,
    PROMPT_CLASSIFICAZIONE_RETAIL,
)


@pytest.fixture(autouse=True)
def _niente_tracking_costi(monkeypatch):
    import services.ai_cost_service as cost

    monkeypatch.setattr(cost, "track_ai_usage", lambda *a, **k: None)


def _client(*risposte_per_chiamata):
    """Client finto che risponde con una lista di categorie per ogni chiamata."""
    def _resp(categorie):
        payload = {"risultati": [{"idx": i, "categoria": c, "confidence": "alta"}
                                 for i, c in enumerate(categorie)]}
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload)),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
        )

    client = MagicMock()
    client.chat.completions.create.side_effect = [_resp(r) for r in risposte_per_chiamata]
    return client


def _prompt_inviati(client) -> list[str]:
    return [
        c.kwargs["messages"][0]["content"]
        for c in client.chat.completions.create.call_args_list
    ]


# ── la prima chiamata ────────────────────────────────────────────────────────

def test_per_un_negozio_parte_il_prompt_retail():
    client = _client(["ARTICOLO DI VENDITA"])
    ai._chiama_gpt_classificazione(["TRAPANO AVVITATORE 18V"], client, settore=SETTORE_RETAIL)

    inviato = _prompt_inviati(client)[0]
    assert "ARTICOLO DI VENDITA" in inviato
    assert "Sei un esperto di controllo di gestione per negozi" in inviato
    assert "Sei un esperto classifier per ristoranti" not in inviato


@pytest.mark.parametrize("settore", [None, SETTORE_RISTORAZIONE])
def test_per_un_ristorante_parte_il_prompt_di_sempre(settore):
    """Uguaglianza col testo di oggi, non `in`: il vincolo assoluto della fase.

    La descrizione e' scelta fra quelle che `normalizza_descrizione` lascia
    intatte (espande le abbreviazioni PRIMA dell'invio: "BISTECCA DI MANZO"
    diventa "BISTECCA MANZO"), cosi' l'uguaglianza misura il TEMPLATE e non la
    normalizzazione del payload.
    """
    from utils.text_utils import normalizza_descrizione

    desc = "POLLO"
    assert normalizza_descrizione(desc) == desc, "descrizione non piu' stabile: sceglierne un'altra"

    client = _client(["CARNE"])
    ai._chiama_gpt_classificazione([desc], client, settore=settore)

    inviato = _prompt_inviati(client)[0]
    articoli = json.dumps([{"idx": 0, "articolo": desc}], ensure_ascii=False)
    assert inviato == PROMPT_CLASSIFICAZIONE_AI.replace("{ARTICOLI}", articoli)


def test_il_prompt_retail_inviato_e_letteralmente_la_costante():
    from utils.text_utils import normalizza_descrizione

    desc = "VITI TSP 4X40"
    assert normalizza_descrizione(desc) == desc

    client = _client(["ARTICOLO DI VENDITA"])
    ai._chiama_gpt_classificazione([desc], client, settore=SETTORE_RETAIL)

    articoli = json.dumps([{"idx": 0, "articolo": desc}], ensure_ascii=False)
    assert _prompt_inviati(client)[0] == PROMPT_CLASSIFICAZIONE_RETAIL.replace("{ARTICOLI}", articoli)


# ── il retry ─────────────────────────────────────────────────────────────────

def test_anche_il_retry_manda_il_prompt_retail(monkeypatch):
    """Il primo giro lascia un "Da Classificare": il retry deve ripartire con
    lo stesso prompt, non con quello dei ristoranti."""
    monkeypatch.setattr(ai, "ai_deadline_scaduta", lambda: False)
    monkeypatch.setattr(ai, "_azzera_cache_memoria", lambda *a, **k: None, raising=False)
    client = _client(["Da Classificare"], ["ARTICOLO DI VENDITA"])

    ai.classifica_con_ai(
        ["ARTICOLO IGNOTO XZ99"], openai_client=client, settore=SETTORE_RETAIL,
    )

    inviati = _prompt_inviati(client)
    assert len(inviati) >= 2, "il retry non e' partito: il test non misura niente"
    for prompt in inviati:
        assert "Sei un esperto di controllo di gestione per negozi" in prompt
        assert "Sei un esperto classifier per ristoranti" not in prompt


def test_per_un_ristorante_anche_il_retry_resta_quello_di_oggi(monkeypatch):
    monkeypatch.setattr(ai, "ai_deadline_scaduta", lambda: False)
    client = _client(["Da Classificare"], ["CARNE"])

    ai.classifica_con_ai(
        ["DESCRIZIONE ILLEGGIBILE 77"], openai_client=client, settore=SETTORE_RISTORAZIONE,
    )

    inviati = _prompt_inviati(client)
    assert len(inviati) >= 2
    for prompt in inviati:
        assert "Sei un esperto classifier per ristoranti" in prompt
        assert PROMPT_CLASSIFICAZIONE_RETAIL[:60] not in prompt


# ── il giro completo: prompt + validazione ───────────────────────────────────

def test_una_riga_di_ferramenta_esce_come_articolo_di_vendita():
    """End-to-end del settore: il prompt retail parte, GPT risponde con la sola
    categoria merce del negozio, e la validazione per settore la accetta."""
    client = _client(["ARTICOLO DI VENDITA"])
    out = ai._chiama_gpt_classificazione(
        ["MARTELLO DA CARPENTIERE MANICO LEGNO"], client, settore=SETTORE_RETAIL,
    )
    assert out == ["ARTICOLO DI VENDITA"]


def test_se_gpt_risponde_food_a_un_negozio_la_riga_resta_in_coda():
    """Il prompt le vieta, ma un modello puo' sempre disobbedire: la rete a
    valle (1.4) tiene. Regola di dominio #1 — meglio in coda che in CARNE."""
    client = _client(["CARNE"])
    out = ai._chiama_gpt_classificazione(
        ["PROSCIUTTO CRUDO 24 MESI"], client, settore=SETTORE_RETAIL,
    )
    assert out == ["Da Classificare"]
