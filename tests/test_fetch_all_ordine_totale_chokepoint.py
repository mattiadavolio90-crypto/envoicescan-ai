"""fetch_all aggiunge `.order("id")` quando la query non dichiara un ordine.

OFFSET/LIMIT senza ORDER BY non garantisce pagine dello stesso elenco (10/09/2026:
653 id mancanti su 3.067 col totale identico). Il 14/09/2026 28 chiamanti su 35
paginavano senza ordine: il punto unico che li chiude e' `_con_ordine_totale`.

Tre comportamenti, ognuno con il suo mutante:
- builder senza ordine -> ordine aggiunto PRIMA della prima pagina;
- builder con ordine proprio -> lasciato intatto (mutante "aggiungi sempre");
- builder RPC -> mai toccato: le RPC non hanno la colonna id e risponderebbero
  400 (`articoli_da_fatture` in foodcost_service).
"""
from types import SimpleNamespace

from utils.supabase_paging import fetch_all


class _Builder:
    """Fake che espone `request.params` come il builder postgrest vero."""

    def __init__(self, rows, params=None, name=None):
        self._rows = rows
        self.request = SimpleNamespace(params=dict(params or {"select": "*"}))
        self.chiamate = []
        if name:
            self.__class__ = type(name, (_Builder,), {})

    def order(self, col, **kw):
        self.chiamate.append(("order", col))
        self.request.params["order"] = col
        return self

    def range(self, a, b):
        self.chiamate.append(("range", a, b))
        self._page = (a, b)
        return self

    def execute(self):
        a, b = self._page
        return SimpleNamespace(data=self._rows[a : b + 1])


def _righe(n):
    return [{"id": i} for i in range(n)]


def test_senza_ordine_aggiunge_order_id_prima_della_prima_pagina():
    b = _Builder(_righe(5))
    assert fetch_all(b, page_size=2) == _righe(5)
    assert b.chiamate[0] == ("order", "id")
    assert b.chiamate[1][0] == "range"


def test_con_ordine_proprio_non_ne_aggiunge_un_secondo():
    b = _Builder(_righe(3), params={"select": "*", "order": "data_documento.desc"})
    fetch_all(b, page_size=10)
    assert all(c[0] != "order" for c in b.chiamate), b.chiamate


def test_le_rpc_non_vengono_ordinate_per_id():
    b = _Builder(_righe(3), name="SyncRPCFilterRequestBuilder")
    fetch_all(b, page_size=10)
    assert all(c[0] != "order" for c in b.chiamate), b.chiamate


def test_un_builder_che_non_espone_i_parametri_resta_intatto():
    class _Muto:
        def __init__(self):
            self.chiamate = []

        def range(self, a, b):
            self.chiamate.append(("range", a, b))
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    b = _Muto()
    assert fetch_all(b) == []
    assert b.chiamate == [("range", 0, 999)]
