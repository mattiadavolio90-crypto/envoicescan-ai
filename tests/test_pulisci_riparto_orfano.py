"""Test guardia: eliminando una fattura si rimuove il suo riparto costi-catena
orfano (chiude il buco delete→riparto che lasciava costi fantasma nel MOL).

Contesto (OFFSIDE, 23/07/2026): riparto_costi_catena e' un aggregato a livello
account, senza FK a fatture. Prima, cancellare una fattura NON toccava il riparto
generato da quel documento → margini_mensili.quote_riparto_* teneva il costo come
fantasma (es. gennaio 2026 MOL −1921,34 in un mese senza fattura viva ripartita).
Ora l'eliminazione della fattura elimina anche il suo riparto orfano e ri-aggrega
le quote — MA solo se non resta piu' alcuna riga viva con quel file_origine
nell'account (altra sede che lo tiene = riparto ancora legittimo).

Copre:
  - riparto presente + nessuna fattura viva → riparti eliminati + RPC per periodo;
  - riparto presente + una fattura ancora viva → NON eliminato, nessuna RPC;
  - nessun riparto per quel file → no-op totale;
  - errore interno → non solleva (best-effort, l'eliminazione e' gia' avvenuta).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import services.db_service as db_service


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._mode = "select"
        self._count = False

    def select(self, *a, **k):
        self._mode = "select"
        if k.get("count") == "exact":
            self._count = True
        return self

    def eq(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def in_(self, _col, ids):
        self._c.deleted_ids.extend(ids)
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def execute(self):
        if self._t == "riparto_costi_catena" and self._mode == "delete":
            return SimpleNamespace(data=[{"id": i} for i in self._c.deleted_ids])
        if self._t == "riparto_costi_catena":
            return SimpleNamespace(data=list(self._c.riparti))
        if self._t == "fatture":
            n = self._c.n_vive
            if self._count:
                return SimpleNamespace(count=n, data=[])
            return SimpleNamespace(data=[{"id": x} for x in range(n)])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, riparti, n_vive):
        self.riparti = riparti
        self.n_vive = n_vive
        self.deleted_ids = []
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=1))


def test_riparto_orfano_rimosso_e_ricalcolo():
    sb = _FakeSB(
        riparti=[
            {"id": "r1", "anno": 2026, "mese": 1},
            {"id": "r2", "anno": 2026, "mese": 1},
        ],
        n_vive=0,
    )
    db_service._pulisci_riparto_orfano(sb, "user-1", "IT_x.xml")
    assert set(sb.deleted_ids) == {"r1", "r2"}
    # Un solo periodo distinto (2026-1) → una sola chiamata RPC.
    assert sb.rpc_calls == [
        ("riparto_quote_mensili", {"p_user_id": "user-1", "p_anno": 2026, "p_mese": 1}),
    ]


def test_periodi_distinti_una_rpc_ciascuno():
    sb = _FakeSB(
        riparti=[
            {"id": "r1", "anno": 2026, "mese": 1},
            {"id": "r2", "anno": 2026, "mese": 7},
        ],
        n_vive=0,
    )
    db_service._pulisci_riparto_orfano(sb, "user-1", "IT_x.xml")
    assert set(sb.deleted_ids) == {"r1", "r2"}
    periodi = sorted(p[1]["p_mese"] for p in sb.rpc_calls)
    assert periodi == [1, 7]


def test_riparto_non_toccato_se_resta_fattura_viva():
    sb = _FakeSB(riparti=[{"id": "r1", "anno": 2026, "mese": 1}], n_vive=3)
    db_service._pulisci_riparto_orfano(sb, "user-1", "IT_x.xml")
    assert sb.deleted_ids == []          # niente delete
    assert sb.rpc_calls == []            # niente ricalcolo


def test_nessun_riparto_noop():
    sb = _FakeSB(riparti=[], n_vive=0)
    db_service._pulisci_riparto_orfano(sb, "user-1", "IT_x.xml")
    assert sb.deleted_ids == []
    assert sb.rpc_calls == []


def test_errore_interno_non_solleva():
    sb = MagicMock()
    sb.table.side_effect = RuntimeError("boom")
    # Non deve propagare: l'eliminazione della fattura e' gia' avvenuta.
    db_service._pulisci_riparto_orfano(sb, "user-1", "IT_x.xml")
