"""Test guardia: alert 7 di _build_chat_system_prompt (audit §3b chat, F3 — MEDIUM).

Difetto trovato (25/8/2026): l'alert contava needs_review=True ma il testo
diceva "righe fattura 'Da Classificare': non rientrano nei calcoli di food
cost e margine" — falso per le righe needs_review gia' categorizzate (es.
sconti marcati per revisione), che nei margini rientrano regolarmente
(margine_service esclude solo su .neq('categoria', 'Da Classificare')).

Confermato sul DB live: SAN GIULIANO aveva 187 righe needs_review ma solo 46
con categoria='Da Classificare' — l'alert gonfiava il numero di 4.1x e
attribuiva l'esclusione dai margini a 141 righe che invece vi rientravano.
Su TIME CAFE l'alert diceva 10 righe quando ce n'erano zero.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw
from services.fastapi_worker import _build_chat_system_prompt

FRASE_ALERT = "'Da Classificare'"


@pytest.fixture(autouse=True)
def _isola_contorno(monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: MagicMock(has_data=False))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))


def _sb(fatture_count_da_classificare, fatture_count_needs_review=None):
    """Simula fatture con conteggio distinto per query .eq('categoria', ...)
    vs .eq('needs_review', True): se il codice torna a interrogare needs_review
    invece di categoria, il test lo intercetta con un conteggio diverso."""
    sb = MagicMock()
    state = {"filters": {}}

    def _table(name):
        state["filters"] = {"table": name}
        return q

    def _eq(field, value):
        state["filters"][field] = value
        return q

    def _execute():
        f = state["filters"]
        if f.get("table") == "fatture":
            if "categoria" in f:
                return MagicMock(data=[{"id": 1}], count=fatture_count_da_classificare)
            if "needs_review" in f:
                cnt = (
                    fatture_count_needs_review
                    if fatture_count_needs_review is not None
                    else fatture_count_da_classificare
                )
                return MagicMock(data=[{"id": 1}], count=cnt)
            # Alert 1 (fatture nel mese precedente): conta > 0 per non sporcare
            return MagicMock(data=[{"id": 1}], count=5)
        if f.get("table") == "margini_mensili":
            return MagicMock(data=[{
                "fatturato_iva10": 1000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
                "costo_dipendenti": 500, "costo_personale_extra": 0,
                "altri_costi_spese": 100,
            }], count=None)
        return MagicMock(data=[], count=0)

    q = MagicMock()
    sb.table.side_effect = _table
    for m in ("select", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.eq.side_effect = _eq
    q.execute.side_effect = _execute
    return sb


def _prompt(count_categoria, count_needs_review=None):
    user = {"id": "u-test", "nome_ristorante": "TEST", "email": "t@x.it"}
    return _build_chat_system_prompt(
        user, _sb(count_categoria, count_needs_review), None, ristorante_id="rid-1",
    )


def test_alert_conta_categoria_da_classificare_non_needs_review():
    """Se needs_review ha molte piu' righe di categoria='Da Classificare' (come
    su SAN GIULIANO: 187 vs 46), l'alert deve riportare il numero di categoria,
    non quello gonfiato di needs_review."""
    prompt = _prompt(count_categoria=46, count_needs_review=187)
    assert "46 righe fattura 'Da Classificare'" in prompt
    assert "187 righe fattura 'Da Classificare'" not in prompt


def test_zero_da_classificare_ma_needs_review_presenti_non_genera_alert():
    """Caso TIME CAFE: 0 righe davvero Da Classificare, 10 needs_review.
    L'alert non deve comparire (prima del fix compariva con '10 righe')."""
    prompt = _prompt(count_categoria=0, count_needs_review=10)
    assert FRASE_ALERT not in prompt


def test_alert_compare_quando_ci_sono_righe_da_classificare():
    prompt = _prompt(count_categoria=5)
    assert "5 righe fattura 'Da Classificare'" in prompt
    assert "non rientrano nei calcoli di food cost e margine" in prompt
