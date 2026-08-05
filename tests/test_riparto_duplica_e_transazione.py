"""Test di riparto_duplica (categoria preservata) e di _crea_riparto_con_quote
(scrittura transazionale via RPC), services/routers/riparto.py.

Guardia contro i 2 MEDIUM trovati nell'audit §1 2026-08-05:
  - riparto_duplica copiava le quote SENZA `categoria`: un riparto per-categoria
    duplicato ricadeva nel modello legacy monolitico (stessa classe del fix HIGH
    su riparto_modifica).
  - I 4 endpoint di creazione riparto facevano insert padre+quote come due
    statement PostgREST separati, senza transazione: un riparto "orfano" (padre
    scritto, quote no) diventava invisibile al motore MOL. Ora passano dalla RPC
    transazionale crea_riparto_con_quote (migration 20260805143000).
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
        self._filters = {}
        self._select_cols = ""

    def select(self, cols="", *a, **k):
        self._select_cols = cols or ""
        return self
    def eq(self, col, val):
        self._filters[col] = val
        return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        if self._t == "riparto_costi_catena" and "id" in self._filters:
            return SimpleNamespace(data=[self._c.riparto_row] if self._c.riparto_row else [])
        if self._t == "riparto_costi_catena_quote":
            # Simula PostgREST: proietta solo le colonne davvero richieste,
            # cosi' un test che dimentica "categoria" nella select se ne accorge.
            cols = [c.strip() for c in self._select_cols.split(",") if c.strip()]
            rows = [{k: v for k, v in r.items() if not cols or k in cols} for r in self._c.quote_rows]
            return SimpleNamespace(data=rows)
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, riparto_row, quote_rows):
        self.riparto_row = riparto_row
        self.quote_rows = quote_rows
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data="riparto-nuovo"))


_RIPARTO_MANUALE_PER_CATEGORIA = {
    "id": "riparto-1", "user_id": "user-1", "origine": "manuale",
    "descrizione": "Stipendi ufficio", "importo_totale": 1000.0,
    "tipo": "generale", "anno": 2026, "mese": 6, "regola": "equa",
}

_QUOTE_PER_CATEGORIA = [
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 300.0, "categoria": "CARNE"},
    {"ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 200.0, "categoria": "SERVIZI E CONSULENZE"},
    {"ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 500.0, "categoria": "CARNE"},
]


def _patch(riparto_row, quote_rows):
    sb = _FakeSB(riparto_row, quote_rows)
    return sb, patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=[
            {"id": "sede-a", "nome_ristorante": "A"}, {"id": "sede-b", "nome_ristorante": "B"},
        ]),
        _post_scrittura_riparto=MagicMock(return_value=None),
    )


# ─── MEDIUM: riparto_duplica preserva categoria ──────────────────────────────

def test_duplica_preserva_categoria_nelle_quote():
    sb, p = _patch(dict(_RIPARTO_MANUALE_PER_CATEGORIA), list(_QUOTE_PER_CATEGORIA))
    with p:
        out = riparto.riparto_duplica("riparto-1", authorization="Bearer x")
    assert out["ok"] is True
    # rollover mese: giugno → luglio, stesso anno
    assert out["anno"] == 2026 and out["mese"] == 7
    rpc_name, params = sb.rpc_calls[0]
    assert rpc_name == "crea_riparto_con_quote"
    categorie_passate = {q["categoria"] for q in params["p_quote"]}
    assert categorie_passate == {"CARNE", "SERVIZI E CONSULENZE"}


def test_duplica_senza_quote_rifiutata_400():
    sb, p = _patch(dict(_RIPARTO_MANUALE_PER_CATEGORIA), [])
    with p:
        with pytest.raises(HTTPException) as exc:
            riparto.riparto_duplica("riparto-1", authorization="Bearer x")
    assert exc.value.status_code == 400
    assert sb.rpc_calls == []  # nessuna chiamata RPC: nulla scritto


def test_duplica_riparto_da_fattura_rifiutato_400():
    rip = dict(_RIPARTO_MANUALE_PER_CATEGORIA, origine="fattura", file_origine="IT1_x.xml")
    sb, p = _patch(rip, list(_QUOTE_PER_CATEGORIA))
    with p:
        with pytest.raises(HTTPException) as exc:
            riparto.riparto_duplica("riparto-1", authorization="Bearer x")
    assert exc.value.status_code == 400


# ─── _crea_riparto_con_quote: scrittura transazionale ────────────────────────

def test_crea_riparto_con_quote_chiama_rpc_transazionale():
    sb = _FakeSB(None, [])
    quote = [{"ristorante_id": "sede-a", "quota_perc": 100.0, "quota_importo": 500.0}]
    riparto_id = riparto._crea_riparto_con_quote(
        sb, "user-1", "manuale", None, None, "Costo test", 500.0, "generale", 2026, 6, "equa", quote,
    )
    assert riparto_id == "riparto-nuovo"
    assert len(sb.rpc_calls) == 1
    name, params = sb.rpc_calls[0]
    assert name == "crea_riparto_con_quote"
    assert params["p_quote"] == quote
    assert params["p_user_id"] == "user-1"


def test_crea_riparto_con_quote_rpc_fallita_alza_500():
    class _FakeSBFallito:
        def rpc(self, name, params):
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))
    with pytest.raises(HTTPException) as exc:
        riparto._crea_riparto_con_quote(
            _FakeSBFallito(), "user-1", "manuale", None, None, "x", 1.0, "generale", 2026, 6, "equa",
            [{"ristorante_id": "sede-a", "quota_perc": 100.0, "quota_importo": 1.0}],
        )
    assert exc.value.status_code == 500
