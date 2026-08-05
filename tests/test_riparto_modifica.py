"""Test dell'endpoint PATCH /api/riparto/{riparto_id} (services/routers/riparto.py).

Guardia contro la regressione HIGH trovata nell'audit §1 2026-08-05: la PATCH
ricalcola le quote (delete+insert) SEMPRE senza `categoria` (_quote_equa/
_quote_percentuali non la producono). Se il riparto originale era esploso per
categoria (origine="fattura"), va ri-esploso subito dopo, altrimenti la RPC
mensile instrada l'intero importo in un solo secchio F&B/spese invece che per
categoria — il MOL si sposta in silenzio. Copre anche il fallback (l'esplosione
non deve mai far fallire la PATCH né saltare _post_scrittura_riparto).
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

    def select(self, *a, **k): return self
    def eq(self, col, val):
        self._filters[col] = val
        return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self, *a, **k): return self

    def insert(self, payload):
        self._c.inserts.setdefault(self._t, []).append(payload)
        return self

    def update(self, payload):
        self._c.updates.setdefault(self._t, []).append(payload)
        return self

    def delete(self, *a, **k):
        self._c.deletes.setdefault(self._t, 0)
        self._c.deletes[self._t] += 1
        return self

    def execute(self):
        if self._t == "riparto_costi_catena" and "id" in self._filters:
            return SimpleNamespace(data=[self._c.riparto_row] if self._c.riparto_row else [])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, riparto_row):
        self.riparto_row = riparto_row
        self.inserts = {}
        self.updates = {}
        self.deletes = {}

    def table(self, name):
        return _Query(self, name)


_SEDI = [
    {"id": "sede-a", "nome_ristorante": "Locale A"},
    {"id": "sede-b", "nome_ristorante": "Locale B"},
]

_RIPARTO_DA_FATTURA = {
    "id": "riparto-1", "user_id": "user-1", "origine": "fattura",
    "file_origine": "IT123_abc.xml", "tipo": "generale", "regola": "equa",
    "importo_totale": 1000.0, "anno": 2026, "mese": 6,
}

_RIPARTO_MANUALE = {
    "id": "riparto-2", "user_id": "user-1", "origine": "manuale",
    "file_origine": None, "tipo": "generale", "regola": "equa",
    "importo_totale": 500.0, "anno": 2026, "mese": 6,
}


def _patch(riparto_row):
    sb = _FakeSB(riparto_row)
    mock_post_scrittura = MagicMock(return_value=None)
    patches = dict(
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI),
        _post_scrittura_riparto=mock_post_scrittura,
    )
    return sb, patch.multiple(riparto, **patches), mock_post_scrittura


def _body(**over):
    return riparto.RipartoModificaBody(**over)


# ─── HIGH: riparto da fattura deve essere ri-esploso per categoria ───────────

def test_modifica_riparto_da_fattura_richiama_esplosione():
    sb, p, mock_post_scrittura = _patch(dict(_RIPARTO_DA_FATTURA))
    with p, patch(
        "services.riparto_service.esplodi_quote_per_categoria", MagicMock(return_value=True)
    ) as mock_esplodi:
        out = riparto.riparto_modifica(
            "riparto-1", _body(regola="percentuali", percentuali={"sede-a": 70.0, "sede-b": 30.0}),
            authorization="Bearer x",
        )
    assert out["ok"] is True
    mock_esplodi.assert_called_once_with(sb, "user-1", "riparto-1", "IT123_abc.xml")
    # _post_scrittura_riparto deve girare comunque (invariante: il MOL va sempre ricalcolato)
    mock_post_scrittura.assert_called_once_with(sb, "user-1", 2026, 6)


def test_modifica_riparto_manuale_non_richiama_esplosione():
    # origine="manuale" non ha file_origine: nulla da esplodere, l'helper non va chiamato.
    sb, p, _ = _patch(dict(_RIPARTO_MANUALE))
    with p, patch(
        "services.riparto_service.esplodi_quote_per_categoria", MagicMock(return_value=False)
    ) as mock_esplodi:
        riparto.riparto_modifica("riparto-2", _body(regola="equa"), authorization="Bearer x")
    mock_esplodi.assert_not_called()


def test_modifica_esplosione_fallita_non_blocca_la_patch():
    # Se l'esplosione solleva (timeout PostgREST, ecc.) la PATCH non deve fallire e
    # _post_scrittura_riparto deve girare comunque — stesso pattern try/except del
    # gemello riparto_da_fattura (riga 254-258).
    sb, p, mock_post_scrittura = _patch(dict(_RIPARTO_DA_FATTURA))
    with p, patch(
        "services.riparto_service.esplodi_quote_per_categoria",
        MagicMock(side_effect=RuntimeError("PostgREST timeout")),
    ):
        out = riparto.riparto_modifica(
            "riparto-1", _body(regola="equa"), authorization="Bearer x",
        )
    assert out["ok"] is True
    mock_post_scrittura.assert_called_once_with(sb, "user-1", 2026, 6)


def test_modifica_riparto_non_trovato_404():
    sb, p, _ = _patch(None)
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_modifica("riparto-x", _body(regola="equa"), authorization="Bearer x")
    assert exc.value.status_code == 404
