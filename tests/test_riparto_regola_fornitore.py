"""Test dell'endpoint GET /api/riparto/regola-fornitore (services/routers/riparto.py).

Sola lettura: ritorna la regola di ripartizione memorizzata per un fornitore
("fai sempre così"), usata dal dialog per PRE-COMPILARE il criterio. NON applica
nulla. Verifichiamo:
  - regola attiva presente → ritorna regola/tipo/percentuali;
  - nessuna regola → {regola: None};
  - fornitore vuoto → {regola: None} (nessuna query inutile);
  - gating catena: con una sola sede reale → 400.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        if self._t == "riparto_regole_fornitore":
            return SimpleNamespace(data=self._c.regola_rows)
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, regola_rows):
        self.regola_rows = regola_rows

    def table(self, name):
        return _Query(self, name)


_SEDI_REALI = [
    {"id": "sede-a", "nome_ristorante": "Locale A"},
    {"id": "sede-b", "nome_ristorante": "Locale B"},
]


def _patch(regola_rows, sedi=_SEDI_REALI):
    sb = _FakeSB(regola_rows)
    return sb, patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
    )


def test_regola_presente_ritorna_criterio():
    rows = [{"regola": "percentuali", "tipo": "generale",
             "percentuali": {"sede-a": 70, "sede-b": 30}}]
    sb, p = _patch(rows)
    with p:
        out = riparto.riparto_regola_fornitore(fornitore="09408560960", authorization="Bearer x")
    assert out["regola"] == "percentuali"
    assert out["tipo"] == "generale"
    assert out["percentuali"] == {"sede-a": 70, "sede-b": 30}


def test_nessuna_regola_ritorna_none():
    sb, p = _patch([])
    with p:
        out = riparto.riparto_regola_fornitore(fornitore="09408560960", authorization="Bearer x")
    assert out == {"regola": None}


def test_fornitore_vuoto_ritorna_none():
    sb, p = _patch([{"regola": "equa", "tipo": "generale", "percentuali": None}])
    with p:
        out = riparto.riparto_regola_fornitore(fornitore="   ", authorization="Bearer x")
    assert out == {"regola": None}


def test_gating_una_sola_sede_reale():
    sb, p = _patch([], sedi=[{"id": "sede-a", "nome_ristorante": "Unico"}])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_regola_fornitore(fornitore="09408560960", authorization="Bearer x")
    assert exc.value.status_code == 400
