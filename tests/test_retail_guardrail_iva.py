"""Il guardrail IVA bassa sta a valle di ogni filtro retail (RETAIL_FASI.md, quarta lettura).

`_applica_guardrail_iva_bassa_spese_generali` ragiona da ristorante: una spesa
generale con IVA 4/5/10 e' sospetta, e prova a recuperare una categoria food dal
dizionario. In `classifica_con_ai` gira sul percorso di successo DOPO la
validazione per settore, e in `categorizza_con_memoria` sul livello L7: per un
negozio riportava MATERIALE DI CONSUMO in CAFFE E THE, o SERVIZI E CONSULENZE in
CARNE, con l'IVA 10 che e' un dato normale di fattura. Con `settore='retail'` il
guardrail non tocca la categoria; per i ristoranti (None o 'ristorazione') fa
esattamente quello di prima.
"""
from __future__ import annotations

import time

import pytest

import services.ai_service as ai
from tests.test_retail_post_ai import _gpt

UTENTE = "u-retail-iva"


@pytest.fixture(autouse=True)
def _niente_tracking_costi(monkeypatch):
    import services.ai_cost_service as cost

    monkeypatch.setattr(cost, "track_ai_usage", lambda *a, **k: None)


@pytest.fixture
def memoria_vuota():
    ai.invalida_cache_memoria()
    with ai._cache_lock:
        ai._memoria_cache["prodotti_utente"][UTENTE] = {}
        ai._memoria_cache["prodotti_utente_norm"][UTENTE] = {}
        ai._memoria_cache["loaded"] = True
        ai._memoria_cache["_loaded_at"] = time.time()
        ai._memoria_cache["_loaded_user_ids"] = {UTENTE}
    yield
    ai.invalida_cache_memoria()


# ── il guardrail da solo ─────────────────────────────────────────────────────

def test_per_un_negozio_il_guardrail_non_tocca_la_spesa_generale():
    assert ai._applica_guardrail_iva_bassa_spese_generali(
        "HEINZ BUST. KETCHUP 10MLX200PZ 76023044", "MATERIALE DI CONSUMO", 10, settore="retail"
    ) == "MATERIALE DI CONSUMO"


@pytest.mark.parametrize("settore", [None, "ristorazione"])
def test_per_un_ristorante_il_guardrail_recupera_il_food_come_prima(settore):
    assert ai._applica_guardrail_iva_bassa_spese_generali(
        "HEINZ BUST. KETCHUP 10MLX200PZ 76023044", "MATERIALE DI CONSUMO", 10, settore=settore
    ) == "SALSE E CREME"


def test_il_wrapper_dei_guardrail_passa_il_settore():
    args = ("HEINZ BUST. KETCHUP 10MLX200PZ 76023044", "MATERIALE DI CONSUMO", 5.0, 10)
    assert ai._applica_tutti_guardrail(*args, settore="retail") == "MATERIALE DI CONSUMO"
    assert ai._applica_tutti_guardrail(*args) == "SALSE E CREME"


# ── classifica_con_ai: il percorso di successo ───────────────────────────────

DESCRIZIONI = ["CAFFE MISCELA BAR 1KG", "VINO ROSSO BOTTIGLIA", "TRAPANO AVVITATORE 18V"]
IVA = [10, 10, 22]


def _classifica_ai(settore, **kw):
    gpt = _gpt("MATERIALE DI CONSUMO", "MATERIALE DI CONSUMO", "MATERIALE DI CONSUMO")
    return ai.classifica_con_ai(DESCRIZIONI, lista_iva=IVA, openai_client=gpt, settore=settore, **kw)


def test_retail_una_spesa_generale_dell_ai_con_iva_10_resta_tale():
    assert _classifica_ai("retail") == ["MATERIALE DI CONSUMO"] * 3


def test_retail_anche_con_le_confidenze():
    out, conf = _classifica_ai("retail", return_confidenze=True)
    assert out == ["MATERIALE DI CONSUMO"] * 3
    assert "bassa" not in conf


@pytest.mark.parametrize("settore", [None, "ristorazione"])
def test_per_un_ristorante_l_iva_10_riporta_il_caffe_e_il_vino_in_food(settore):
    # Il trapano lo sposta l'override post-AI delle regole forti (spento nel retail, 1.4).
    assert _classifica_ai(settore) == ["CAFFE E THE", "VINI", "MANUTENZIONE E ATTREZZATURE"]


# ── categorizza_con_memoria: il livello L7 passa dal wrapper ─────────────────

def _classifica_memoria(settore, pending):
    out = ai.categorizza_con_memoria(
        "SERVIZIO DI PRODUZIONE POLLO", 10.0, 1.0, user_id=UTENTE, supabase_client=object(),
        fornitore="FORNITORE SRL", iva_percentuale=10, pending_local_saves=pending,
        return_fallback_flag=True, totale_riga=10.0, settore=settore,
    )
    return out, ai.ultima_provenienza()


def test_retail_sul_livello_l7_la_spesa_generale_resta_e_va_in_memoria_locale(memoria_vuota):
    pending: list = []
    out, prov = _classifica_memoria("retail", pending)
    assert out == ("SERVIZI E CONSULENZE", False)
    assert prov[0] == "L7_dizionario"
    assert [p["categoria"] for p in pending] == ["SERVIZI E CONSULENZE"]


def test_per_un_ristorante_sul_livello_l7_l_iva_10_riporta_in_carne(memoria_vuota):
    pending: list = []
    out, _ = _classifica_memoria(None, pending)
    assert out == ("CARNE", False)
    assert [p["categoria"] for p in pending] == ["CARNE"]
