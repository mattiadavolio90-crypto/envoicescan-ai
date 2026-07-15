"""Test dell'endpoint POST /api/riparto/da-coda (services/routers/riparto.py).

Ripartire una fattura ambigua DIRETTAMENTE dalla coda 'da_assegnare', senza prima
assegnarla a un locale reale: la fattura atterra sulla sede tecnica "Costi comuni di
gruppo". Qui verifichiamo il WIRING dell'endpoint con un fake Supabase stateful:
  - registra subito il riparto dai metadati della coda (importo/data/fornitore);
  - le quote pareggiano l'importo (riuso _quote_equa);
  - chiama assegna_fattura_a_sede_tecnica sulla RPC;
  - errori chiari se i metadati sono incompleti;
  - la sede tecnica NON entra fra le sedi destinatarie di quota (_carica_sedi_attive).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


# ─── Fake Supabase stateful ───────────────────────────────────────────────────

class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._payload = None
        self._is_insert = False

    # builder no-op che ritorna self
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self, *a, **k): return self

    def insert(self, payload):
        self._is_insert = True
        self._payload = payload
        self._c.inserts.setdefault(self._t, []).append(payload)
        return self

    def update(self, payload):
        self._c.updates.setdefault(self._t, []).append(payload)
        return self

    def upsert(self, payload, **k):
        self._c.upserts.setdefault(self._t, []).append(payload)
        return self

    def delete(self, *a, **k):
        return self

    def execute(self):
        if self._is_insert and self._t == "riparto_costi_catena":
            return SimpleNamespace(data=[{"id": "riparto-1"}])
        if self._t == "fatture_queue":
            return SimpleNamespace(data=self._c.queue_rows)
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, queue_rows):
        self.queue_rows = queue_rows
        self.inserts = {}
        self.updates = {}
        self.upserts = {}
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data="sede-tecnica-1"))


_SEDI_REALI = [
    {"id": "sede-a", "nome_ristorante": "Locale A"},
    {"id": "sede-b", "nome_ristorante": "Locale B"},
]

_META_OK = {
    "nome_file": "IT123_abc.xml",
    "importo_totale": "1000.00",
    "data_fattura": "2026-06-07",
    "piva_cedente": "09408560960",
}


def _patch(queue_rows, sedi=_SEDI_REALI):
    sb = _FakeSB(queue_rows)
    return sb, patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
        _post_scrittura_riparto=MagicMock(return_value=None),
    )


def _body(**over):
    base = dict(queue_id=223, descrizione="Commercialista giugno", tipo="generale", regola="equa")
    base.update(over)
    return riparto.RipartoDaCodaBody(**base)


# ─── Happy path ───────────────────────────────────────────────────────────────

def test_da_coda_registra_riparto_e_chiama_sede_tecnica():
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": _META_OK}]
    sb, p = _patch(queue)
    with p:
        out = riparto.riparto_da_coda(_body(), authorization="Bearer x")

    assert out["ok"] is True
    assert out["anno"] == 2026 and out["mese"] == 6
    assert out["importo"] == 1000.0
    # riparto creato con file_origine dai metadati
    rip = sb.inserts["riparto_costi_catena"][0]
    assert rip["file_origine"] == "IT123_abc.xml"
    assert rip["origine"] == "fattura"
    # quote su 2 sedi reali, pareggiano l'importo
    quote = sb.inserts["riparto_costi_catena_quote"][0]
    assert len(quote) == 2
    assert sum(q["quota_importo"] for q in quote) == 1000.0
    assert {q["ristorante_id"] for q in quote} == {"sede-a", "sede-b"}
    # RPC sede tecnica chiamata col queue_id
    assert ("assegna_fattura_a_sede_tecnica", {"p_queue_id": 223}) in sb.rpc_calls
    # marcatura idempotente delle righe (per file_origine)
    assert any(u.get("ripartita_su_gruppo") is True for u in sb.updates.get("fatture", []))


def test_da_coda_percentuali():
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": _META_OK}]
    sb, p = _patch(queue)
    with p:
        out = riparto.riparto_da_coda(
            _body(regola="percentuali", percentuali={"sede-a": 70.0, "sede-b": 30.0}),
            authorization="Bearer x",
        )
    quote = {q["ristorante_id"]: q["quota_importo"] for q in sb.inserts["riparto_costi_catena_quote"][0]}
    assert quote["sede-a"] == 700.0
    assert quote["sede-b"] == 300.0


# ─── Errori ───────────────────────────────────────────────────────────────────

def test_da_coda_queue_non_trovata_404():
    sb, p = _patch([])  # nessun record in coda
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_coda(_body(), authorization="Bearer x")
    assert exc.value.status_code == 404


def test_da_coda_importo_mancante_400():
    meta = dict(_META_OK); meta.pop("importo_totale")
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": meta}]
    sb, p = _patch(queue)
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_coda(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_da_coda_data_mancante_400():
    meta = dict(_META_OK); meta.pop("data_fattura")
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": meta}]
    sb, p = _patch(queue)
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_coda(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400


def test_da_coda_gating_una_sola_sede_reale():
    # _require_catena usa _carica_sedi_attive: con 1 sola sede reale → 400.
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": _META_OK}]
    sb, p = _patch(queue, sedi=[{"id": "sede-a", "nome_ristorante": "Unico"}])
    with p, pytest.raises(HTTPException) as exc:
        riparto.riparto_da_coda(_body(), authorization="Bearer x")
    assert exc.value.status_code == 400
