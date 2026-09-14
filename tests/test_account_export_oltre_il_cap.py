"""L'export art. 20 consegna TUTTE le righe, non le prime 1000.

Misurato il 14/09/2026: 4 clienti su 6 con fatture superano le 1000 righe
(29.911, 4.272, 3.888, 1.348) e la select senza .range() ne consegnava
esattamente 1000, etichettate come export completo. Il fake qui sotto fa cio'
che fa PostgREST: senza .range() risponde al massimo 1000 righe, senza errore.
Mutante: `fetch_all(...)` -> `.execute().data` fa tornare 1000 su 1500.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.routers.account as account

_MAX_ROWS_POSTGREST = 1000


class _Q:
    def __init__(self, store):
        self._store = store
        self._page = None
        self._op = "select"

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def delete(self):
        self._op = "delete"
        return self

    def range(self, a, b):
        self._page = (a, b)
        return self

    def execute(self):
        if self._op == "delete":
            return SimpleNamespace(data=[])
        if self._page is None:
            return SimpleNamespace(data=self._store[:_MAX_ROWS_POSTGREST])
        a, b = self._page
        return SimpleNamespace(data=self._store[a : b + 1])


class _SB:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table

    def table(self, name):
        return _Q(self.rows_by_table.get(name, []))


def test_export_con_1500_fatture_ne_consegna_1500():
    fatture = [{"id": i, "user_id": "u1", "categoria": "CARNE"} for i in range(1500)]
    sb = _SB({"fatture": fatture, "ristoranti": [{"id": "r1", "user_id": "u1"}]})
    with patch.multiple(
        account,
        _resolve_user_from_token=MagicMock(return_value={"id": "u1", "email": "c@x.it"}),
        _get_supabase_client=MagicMock(return_value=sb),
    ):
        out = account.account_esporta_dati(authorization="Bearer t")
    export = out.get("dati") or out.get("export") or out
    assert len(export["fatture"]) == 1500
    assert [r["id"] for r in export["fatture"]] == list(range(1500))
