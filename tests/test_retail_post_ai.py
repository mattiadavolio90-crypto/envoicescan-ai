"""I quattro punti post-AI che riporterebbero una riga retail in food (RETAIL_FASI.md 1.4).

  1. La validazione dell'output GPT (`_chiama_gpt_classificazione`) usa la
     whitelist del SETTORE: per un negozio ARTICOLO DI VENDITA e' valida, una
     food no, e una categoria inventata NON viene recuperata dal dizionario dei
     ristoranti (resta "Da Classificare"). Senza questo, il prompt retail della
     Fase 2 non produrrebbe nulla e il sintomo sarebbe indistinguibile da "il
     prompt non funziona".
  2. Il safety net sui "Da Classificare" residui resta spento per il retail.
  3. L'override post-AI delle regole forti resta spento per il retail.
  4. Nel worker, l'override deterministico che scavalca la proposta AI resta
     spento per il retail.

Piu' il cablaggio: /api/classify e il fallback locale di worker_client
risolvono il settore dall'user_id e lo passano a `classifica_con_ai`.

Per i ristoranti (settore None o 'ristorazione') ogni punto si comporta come prima:
ogni test lo prova affiancando i due settori sullo stesso input.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.ai_service as ai
import services.fastapi_worker as fw
import services.settore_service as ss
import services.worker_client as wc
from tests.test_worker_guardrail_note import _run as _run_worker


@pytest.fixture(autouse=True)
def _niente_tracking_costi(monkeypatch):
    import services.ai_cost_service as cost

    monkeypatch.setattr(cost, "track_ai_usage", lambda *a, **k: None)


def _gpt(*categorie, conf="alta"):
    """Client OpenAI finto: risponde sempre con queste categorie, in ordine."""
    payload = {"risultati": [{"idx": i, "categoria": c, "confidenza": conf} for i, c in enumerate(categorie)]}
    msg = SimpleNamespace(content=json.dumps(payload))
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
    )
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def _valida(desc, risposta_gpt, settore):
    return ai._chiama_gpt_classificazione([desc], _gpt(risposta_gpt), settore=settore)


# ── 1. validazione dell'output GPT ───────────────────────────────────────────

def test_retail_accetta_articolo_di_vendita_i_ristoranti_no():
    assert _valida("MARTELLO DA CARPENTIERE", "ARTICOLO DI VENDITA", "retail") == ["ARTICOLO DI VENDITA"]
    # Per un ristorante non e' una categoria: recupero deterministico come oggi.
    assert _valida("MARTELLO DA CARPENTIERE", "ARTICOLO DI VENDITA", None) == ["MANUTENZIONE E ATTREZZATURE"]


def test_retail_una_food_dell_ai_torna_da_classificare():
    assert _valida("BISTECCA DI MANZO", "CARNE", "retail") == ["Da Classificare"]
    assert _valida("BISTECCA DI MANZO", "CARNE", None) == ["CARNE"]
    assert _valida("BISTECCA DI MANZO", "CARNE", "ristorazione") == ["CARNE"]


def test_retail_una_categoria_inventata_non_viene_recuperata_dal_dizionario():
    assert _valida("POLLO INTERO", "FOOBAR", "retail") == ["Da Classificare"]
    assert _valida("POLLO INTERO", "FOOBAR", None) == ["CARNE"]


@pytest.mark.parametrize("cat", ["MANUTENZIONE E ATTREZZATURE", "UTENZE E LOCALI", "SERVIZI E CONSULENZE", "MATERIALE DI CONSUMO"])
def test_retail_una_spesa_generale_passa(cat):
    assert _valida("QUALCOSA", cat, "retail") == [cat]


def test_categorie_ammesse_per_settore():
    from config.constants import CATEGORIE_SPESE_GENERALI, TUTTE_LE_CATEGORIE

    assert ss.categorie_ammesse(None) == list(TUTTE_LE_CATEGORIE)
    assert ss.categorie_ammesse("ristorazione") == list(TUTTE_LE_CATEGORIE)
    retail = ss.categorie_ammesse("retail")
    assert retail == ["ARTICOLO DI VENDITA"] + list(CATEGORIE_SPESE_GENERALI)
    assert "ARTICOLO DI VENDITA" not in TUTTE_LE_CATEGORIE
    assert not (set(retail) & set(ai.CATEGORIE_FOOD_BEVERAGE))


# ── 2. safety net e 3. override post-AI ──────────────────────────────────────

def test_retail_il_safety_net_non_riporta_in_food():
    assert ai.classifica_con_ai(["POLLO INTERO"], openai_client=_gpt("Da Classificare"), settore="retail") == ["Da Classificare"]
    assert ai.classifica_con_ai(["POLLO INTERO"], openai_client=_gpt("Da Classificare"), settore=None) == ["CARNE"]


def test_retail_l_override_delle_regole_forti_resta_spento():
    # "BLACK BURGER": la regola forte burger_composto scavalca l'AI verso CARNE.
    assert ai.classifica_con_ai(["BLACK BURGER"], openai_client=_gpt("MATERIALE DI CONSUMO"), settore="retail") == ["MATERIALE DI CONSUMO"]
    assert ai.classifica_con_ai(["BLACK BURGER"], openai_client=_gpt("MATERIALE DI CONSUMO"), settore=None) == ["CARNE"]


# ── 4. override deterministico del worker ────────────────────────────────────

def _riga_worker():
    return [{"id": 1, "descrizione": "BLACK BURGER", "fornitore": "X", "iva_percentuale": 22,
             "totale_riga": 15.0, "categoria": None}]


def test_nel_worker_l_override_deterministico_resta_spento_per_il_retail():
    with patch.object(ss, "settore_utente", return_value="retail"):
        sb = _run_worker(_riga_worker(), categorie=["MATERIALE DI CONSUMO"])
    assert sb._rows[0]["categoria"] == "MATERIALE DI CONSUMO"


def test_nel_worker_l_override_deterministico_vale_per_i_ristoranti():
    with patch.object(ss, "settore_utente", return_value="ristorazione"):
        sb = _run_worker(_riga_worker(), categorie=["MATERIALE DI CONSUMO"])
    assert sb._rows[0]["categoria"] == "CARNE"


# ── cablaggio ────────────────────────────────────────────────────────────────

def _cattura_classifica(monkeypatch):
    ricevuti: list = []

    def _finta(**kw):
        ricevuti.append(kw)
        return ["ARTICOLO DI VENDITA"] * len(kw["lista_descrizioni"]), ["alta"] * len(kw["lista_descrizioni"])

    monkeypatch.setattr(ai, "classifica_con_ai", _finta)
    return ricevuti


def test_l_endpoint_classify_risolve_il_settore_dall_user_id(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(fw, "_check_rate_limit", lambda _h: None)
    monkeypatch.setattr(ai, "carica_memoria_completa", lambda *_a, **_k: None)
    chiamate: list = []
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: chiamate.append(uid) or "retail")
    ricevuti = _cattura_classifica(monkeypatch)
    richiesta = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})

    fw.classify(richiesta, fw.ClassifyRequest(descrizioni=["MARTELLO"], user_id="u-retail"))

    assert chiamate == ["u-retail"]
    assert ricevuti[0]["settore"] == "retail"


def test_l_endpoint_classify_senza_user_id_non_ha_settore(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(fw, "_check_rate_limit", lambda _h: None)
    monkeypatch.setattr(ss, "settore_utente", lambda *_a, **_k: pytest.fail("non deve chiedere il settore"))
    ricevuti = _cattura_classifica(monkeypatch)
    richiesta = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})

    fw.classify(richiesta, fw.ClassifyRequest(descrizioni=["MARTELLO"]))

    assert ricevuti[0]["settore"] is None


def test_il_fallback_locale_del_client_passa_il_settore(monkeypatch):
    ricevuti: list = []

    def _finta(descrizioni, **kw):
        ricevuti.append(kw)
        return ["ARTICOLO DI VENDITA"] * len(descrizioni), ["alta"] * len(descrizioni)

    monkeypatch.setattr(ai, "classifica_con_ai", _finta)
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: "retail" if uid == "u-retail" else "ristorazione")
    wc.force_local_worker_path(True)
    try:
        wc.classifica_via_worker_con_confidenza(["MARTELLO"], user_id="u-retail")
        wc.classifica_via_worker_con_confidenza(["MARTELLO"], user_id=None)
    finally:
        wc.force_local_worker_path(False)
    assert [r["settore"] for r in ricevuti] == ["retail", None]


def _gpt_sequenza(*risposte, conf="alta"):
    """Client finto che risponde una categoria diversa a ogni chiamata (prima
    chiamata, poi i retry): serve a provare che anche i RETRY validano col settore."""
    def _resp(cat):
        payload = {"risultati": [{"idx": 0, "categoria": cat, "confidenza": conf}]}
        msg = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
        )
    client = MagicMock()
    client.chat.completions.create.side_effect = [_resp(c) for c in risposte]
    return client


def test_retail_anche_il_retry_valida_col_settore():
    # Prima risposta "Da Classificare" -> retry -> GPT propone CARNE.
    risposte = ("Da Classificare", "CARNE", "CARNE", "CARNE", "CARNE")
    assert ai.classifica_con_ai(["BISTECCA DI MANZO"], openai_client=_gpt_sequenza(*risposte), settore="retail") == ["Da Classificare"]
    assert ai.classifica_con_ai(["BISTECCA DI MANZO"], openai_client=_gpt_sequenza(*risposte), settore=None) == ["CARNE"]
