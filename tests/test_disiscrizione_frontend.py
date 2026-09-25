"""Parametri della disiscrizione dall'email settimanale — `lib/disiscrizione.ts`.

Eseguito con node via `tests/helpers_ts.py` (vedi
test_catena_segnali_raggruppati_frontend.py per il perche' non in apps/web).
La route `/api/email/disiscrizione` e la pagina `/disiscrizione` passano da qui:
id e token vanno validati PRIMA di chiamare il worker, e la query vince sul
corpo perche' e' la query che il worker ha firmato dentro il link.
"""

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/disiscrizione"
U = "11111111-1111-4111-8111-111111111111"
T = "a" * 64


def _parametri(query, corpo=None):
    return esegui_ts(
        MODULO,
        "const q = input.query === null ? null : new URLSearchParams(input.query);"
        "emit(m.parametriDisiscrizione(q, input.corpo));",
        argomento={"query": query, "corpo": corpo},
        richiede=["parametriDisiscrizione"],
    )


def test_dalla_query_del_link():
    assert _parametri(f"u={U}&t={T}") == {"u": U, "t": T}


def test_dal_corpo_quando_la_query_manca():
    assert _parametri("", {"u": U, "t": T}) == {"u": U, "t": T}
    assert _parametri(None, {"u": U, "t": T}) == {"u": U, "t": T}


def test_la_query_vince_sul_corpo():
    altro = "22222222-2222-4222-8222-222222222222"
    assert _parametri(f"u={U}&t={T}", {"u": altro, "t": "b" * 64}) == {"u": U, "t": T}


def test_spazi_attorno_si_tolgono():
    assert _parametri(f"u=%20{U}%20&t={T}%20") == {"u": U, "t": T}


@pytest.mark.parametrize("query", [
    f"t={T}",                                  # senza utente
    f"u={U}",                                  # senza token
    f"u=non-un-uuid&t={T}",
    f"u={U}&t={'a' * 63}",                     # token corto
    f"u={U}&t={'g' * 64}",                     # non esadecimale
    f"u={U}'--&t={T}",
])
def test_parametri_malformati_non_arrivano_al_worker(query):
    assert _parametri(query) is None


@pytest.mark.parametrize("corpo", [None, "stringa", 42, [U, T], {"u": 1, "t": 2}])
def test_corpo_strano_non_rompe(corpo):
    assert _parametri("", corpo) is None
