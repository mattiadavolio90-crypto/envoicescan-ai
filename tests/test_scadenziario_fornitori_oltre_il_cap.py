"""La mappa nome -> P.IVA dei fornitori dello scadenziario legge oltre le 1000 righe.

Misurato il 14/09/2026: la sede piu' grande aveva 938 documenti con P.IVA,
+214 negli ultimi 30 giorni; oltre il cap i fornitori presenti solo dopo la
millesima riga uscivano con piva_fornitore=None. Il fake risponde come
PostgREST: senza .range() al massimo 1000 righe, senza errore.
Mutante: togliere fetch_all dallo Step 2 fa perdere la P.IVA dell'ultimo fornitore.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.routers.scadenziario as scad

_MAX_ROWS_POSTGREST = 1000


class _Q:
    def __init__(self, store):
        self._store = store
        self._page = None

    def __getattr__(self, name):
        # select/eq/is_/order/... : filtri ininfluenti per il fake; `not_` e'
        # un attributo (non una chiamata) nel builder postgrest vero.
        if name == "not_":
            return self

        def _f(*_a, **_k):
            return self
        return _f

    def range(self, a, b):
        self._page = (a, b)
        return self

    def execute(self):
        if self._page is None:
            return SimpleNamespace(data=self._store[:_MAX_ROWS_POSTGREST])
        a, b = self._page
        return SimpleNamespace(data=self._store[a : b + 1])


class _SB:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Q(self._tables.get(name, []))


def test_il_fornitore_oltre_la_millesima_riga_ha_la_sua_piva():
    fatture = [{"fornitore": f"FORN {i}"} for i in range(1001)]
    documenti = [{"fornitore": f"FORN {i}", "piva_fornitore": f"{i:011d}"} for i in range(1001)]
    sb = _SB({"fatture": fatture, "fatture_documenti": documenti})
    with patch.multiple(
        scad,
        _resolve_user_from_token=MagicMock(return_value={"id": "u1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _resolve_ristorante_id=MagicMock(return_value="r1"),
    ):
        out = scad.get_fornitori_scadenziario(authorization="Bearer t")
    lista = out["fornitori"] if isinstance(out, dict) else out
    per_nome = {f["fornitore"]: f.get("piva_fornitore") for f in lista}
    assert len(per_nome) == 1001
    assert per_nome["FORN 1000"] == f"{1000:011d}"
