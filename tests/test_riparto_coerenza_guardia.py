"""Test di guardia — Voce 7 (27/7): rete di sicurezza sulle fatture di gruppo.

Due incoerenze osservate live su OFFSIDE fra `fatture` e `riparto_costi_catena`
(tabelle senza FK fra loro, aggregato a livello account):

  1. ORFANO: fattura viva marcata ripartita_su_gruppo=true ma senza alcun riparto
     dietro (FASTWEB, 362,04€, 22/7) → il costo sparisce dal MOL di ogni sede.
  2. RIPARTO SENZA DOCUMENTO: riparto creato DOPO che le righe erano già state
     soft-deleted (4 Amazon, 20→23/7, tutti via /api/riparto/da-coda) → il MOL lo
     conta comunque (margini_mensili è materializzato), costo fantasma.

Copre:
  - da-coda su un documento già atterrato e già cestinato → 409, nessun riparto scritto;
  - da-coda su un documento mai atterrato (coda pura) → passa, comportamento invariato;
  - _smarca_fatture_senza_riparto: fattura marcata senza riparto → smarcata;
  - _smarca_fatture_senza_riparto: riparto ancora presente → nessun tocco (no falso positivo);
  - riparto_elimina: smarca solo le righe VIVE (filtro deleted_at, non le già cestinate).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.db_service as db_service
import services.routers.riparto as riparto


# ─── Fake Supabase stateful per riparto_da_coda ──────────────────────────────

class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._is_insert = False
        self._is_count = False

    def select(self, *a, **k):
        if k.get("count") == "exact":
            self._is_count = True
        return self

    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self, *a, **k): return self

    def insert(self, payload):
        self._is_insert = True
        self._c.inserts.setdefault(self._t, []).append(payload)
        return self

    def update(self, payload):
        self._c.updates.setdefault(self._t, []).append(payload)
        return self

    def upsert(self, payload, **k):
        self._c.upserts.setdefault(self._t, []).append(payload)
        return self

    def delete(self, *a, **k): return self

    def execute(self):
        if self._is_insert and self._t == "riparto_costi_catena":
            return SimpleNamespace(data=[{"id": "riparto-1"}])
        if self._t == "fatture_queue":
            return SimpleNamespace(data=self._c.queue_rows)
        if self._t == "fatture" and self._is_count:
            return SimpleNamespace(count=self._c.n_atterrate, data=[])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, queue_rows, n_atterrate=0):
        self.queue_rows = queue_rows
        self.n_atterrate = n_atterrate  # righe già atterrate (vive+cestinate insieme, non conta deleted_at)
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


def _patch(queue_rows, n_atterrate=0, doc_vivo=0):
    sb = _FakeSB(queue_rows, n_atterrate=n_atterrate)
    return sb, patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI_REALI),
        _post_scrittura_riparto=MagicMock(return_value=None),
    ), doc_vivo


def _body(**over):
    base = dict(queue_id=223, descrizione="Commercialista giugno", tipo="generale", regola="equa")
    base.update(over)
    return riparto.RipartoDaCodaBody(**base)


# ─── 1. da-coda su documento già cestinato → 409, nessuna scrittura ──────────

def test_da_coda_documento_gia_cestinato_409():
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": _META_OK}]
    # n_atterrate>0: una riga con questo file_origine esiste nella tabella (anche
    # cestinata); verifica_documento_vivo la filtra via deleted_at e la conterebbe
    # come viva SOLO se non è cestinata. Qui mockiamo verifica_documento_vivo a 0
    # (nessuna riga viva) mentre la select "grezza" (senza filtro deleted_at) trova
    # comunque 1 riga → è esattamente la firma del caso Amazon: il documento è
    # esistito, ma oggi non c'è più nulla di vivo.
    sb, p, _ = _patch(queue, n_atterrate=1)
    with p, patch("services.riparto_service.verifica_documento_vivo", return_value=0), \
         pytest.raises(HTTPException) as exc:
        riparto.riparto_da_coda(_body(), authorization="Bearer x")
    assert exc.value.status_code == 409
    assert sb.inserts.get("riparto_costi_catena") is None


# ─── 2. da-coda su documento mai atterrato (coda pura) → comportamento invariato ──

def test_da_coda_documento_mai_atterrato_passa():
    queue = [{"id": 223, "user_id": "user-1", "status": "da_assegnare", "payload_meta": _META_OK}]
    # n_atterrate=0: nessuna riga con questo file_origine in `fatture` ancora →
    # il guard non scatta (n_atterrate==0 salta la verifica), comportamento
    # identico a prima della Fase 1.
    sb, p, _ = _patch(queue, n_atterrate=0)
    with p:
        out = riparto.riparto_da_coda(_body(), authorization="Bearer x")
    assert out["ok"] is True
    assert sb.inserts["riparto_costi_catena"][0]["file_origine"] == "IT123_abc.xml"


# ─── 3. _smarca_fatture_senza_riparto: fattura marcata senza riparto → smarcata ──

class _QuerySmarca:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._is_count = False
        self._is_update = False

    def select(self, *a, **k):
        if k.get("count") == "exact":
            self._is_count = True
        return self

    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def update(self, payload):
        self._is_update = True
        self._c.update_payload = payload
        return self

    def execute(self):
        if self._t == "riparto_costi_catena" and self._is_count:
            return SimpleNamespace(count=self._c.n_riparti, data=[])
        if self._t == "fatture" and self._is_update:
            return SimpleNamespace(data=[{"id": i} for i in range(self._c.n_marcate)])
        return SimpleNamespace(data=[])


class _FakeSBSmarca:
    def __init__(self, n_riparti, n_marcate):
        self.n_riparti = n_riparti
        self.n_marcate = n_marcate
        self.update_payload = None

    def table(self, name):
        return _QuerySmarca(self, name)


def test_smarca_fattura_senza_riparto():
    sb = _FakeSBSmarca(n_riparti=0, n_marcate=1)
    n = db_service._smarca_fatture_senza_riparto(sb, "user-1", "webhook_sig:fastweb.xml")
    assert n == 1
    assert sb.update_payload == {"ripartita_su_gruppo": False}


# ─── 4. _smarca_fatture_senza_riparto: riparto presente → nessun tocco ────────

def test_smarca_nessun_falso_positivo_se_riparto_esiste():
    sb = _FakeSBSmarca(n_riparti=1, n_marcate=0)
    n = db_service._smarca_fatture_senza_riparto(sb, "user-1", "IT_metro.xml")
    assert n == 0
    assert sb.update_payload is None


def test_smarca_errore_interno_non_solleva():
    sb = MagicMock()
    sb.table.side_effect = RuntimeError("boom")
    n = db_service._smarca_fatture_senza_riparto(sb, "user-1", "x.xml")
    assert n == 0


# ─── 5. riparto_elimina: smarca solo le righe vive ────────────────────────────

class _QueryElimina:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._is_update = False

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def delete(self, *a, **k): return self

    def is_(self, *a, **k):
        if self._is_update:
            self._c.update_filtered_deleted_at = True
        return self

    def update(self, payload):
        self._is_update = True
        self._c.update_payload = payload
        return self

    def execute(self):
        if self._t == "riparto_costi_catena":
            return SimpleNamespace(data=[{
                "id": "rip-1", "origine": "fattura", "file_origine": "IT_x.xml",
                "anno": 2026, "mese": 7,
            }])
        return SimpleNamespace(data=[])


class _FakeSBElimina:
    def __init__(self):
        self.update_payload = None
        self.update_filtered_deleted_at = False

    def table(self, name):
        return _QueryElimina(self, name)

    def rpc(self, name, params):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=1))


def test_riparto_elimina_smarca_solo_righe_vive():
    sb = _FakeSBElimina()
    with patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=_SEDI_REALI),
    ):
        out = riparto.riparto_elimina("rip-1", authorization="Bearer x")
    assert out["ok"] is True
    assert sb.update_payload == {"ripartita_su_gruppo": False}
    assert sb.update_filtered_deleted_at is True
