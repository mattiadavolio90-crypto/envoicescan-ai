"""Test Fase 2 catena/fatture: endpoint aggregato /api/gruppo/scadenziario e
/api/gruppo/cestino, e ownership check su ristorante_id opzionale in
/api/scadenziario/pagata e /scadenza.

Pattern di test: fake client in-memory (stesso schema di test_flusso_dati_admin.
FakeClient) + monkeypatch dei wrapper lazy dei router, per esercitare la logica
reale senza sollevare un server HTTP.
"""
import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.gruppo as gruppo
import services.routers.scadenziario as scadenziario
import pytest
from fastapi import HTTPException

from tests.test_flusso_dati_admin import FakeClient


# ─── /api/gruppo/scadenziario ──────────────────────────────────────────────


def _bind_gruppo(monkeypatch, sb, user):
    monkeypatch.setattr(gruppo, "_resolve_user_from_token", lambda *a, **k: user)
    monkeypatch.setattr(gruppo, "_get_supabase_client", lambda *a, **k: sb)


def _sedi_offside():
    return [
        {"id": "pv1", "nome_ristorante": "OFFSIDE San Giuliano", "user_id": "u1", "attivo": True, "sede_tecnica": False, "created_at": "2026-01-01"},
        {"id": "pv2", "nome_ristorante": "OFFSIDE Villaguardia", "user_id": "u1", "attivo": True, "sede_tecnica": False, "created_at": "2026-01-02"},
        {"id": "tecnica", "nome_ristorante": "Costi comuni di gruppo", "user_id": "u1", "attivo": True, "sede_tecnica": True, "created_at": "2026-01-03"},
    ]


def _scadenziario_fatture_aggregate_handler(fatture_rows):
    """Replica la RPC SQL scadenziario_fatture_aggregate sulle righe fake, per i
    test che passano da get_documenti_scadenziario (vedi anche l'equivalente in
    test_documenti_service_scadenziario.py::_FakeSupabase)."""

    def _handler(params):
        user_id = params["p_user_id"]
        ristorante_ids = set(params["p_ristorante_ids"])
        agg = {}
        for row in fatture_rows:
            if row.get("user_id") != user_id or row.get("ristorante_id") not in ristorante_ids:
                continue
            if row.get("deleted_at") or not str(row.get("file_origine") or "").strip():
                continue
            fo = str(row["file_origine"]).strip()
            rid = row["ristorante_id"]
            key = (fo, rid)
            if key not in agg or (row.get("created_at") or "") < (agg[key].get("created_at") or ""):
                prev_totale = agg.get(key, {}).get("totale_documento", 0.0)
                agg[key] = {
                    "file_origine": fo,
                    "ristorante_id": rid,
                    "fornitore": row.get("fornitore") or "Sconosciuto",
                    "tipo_documento": row.get("tipo_documento") or "TD01",
                    "data_documento": row.get("data_documento"),
                    "created_at": row.get("created_at"),
                    "totale_documento": prev_totale,
                }
            agg[key]["totale_documento"] = round(agg[key]["totale_documento"] + float(row.get("totale_riga") or 0), 2)
        return list(agg.values())

    return _handler


def test_gruppo_scadenziario_include_sede_tecnica(monkeypatch):
    fatture_rows = [
        {"user_id": "u1", "ristorante_id": "pv1", "file_origine": "a.xml", "fornitore": "F1", "tipo_documento": "TD01", "totale_riga": 10.0, "data_documento": "2026-01-10", "created_at": "2026-01-10T00:00:00Z", "deleted_at": None},
        {"user_id": "u1", "ristorante_id": "tecnica", "file_origine": "b.xml", "fornitore": "F2", "tipo_documento": "TD01", "totale_riga": 20.0, "data_documento": "2026-01-11", "created_at": "2026-01-11T00:00:00Z", "deleted_at": None},
    ]
    sb = FakeClient(
        {
            "ristoranti": _sedi_offside(),
            "fatture": fatture_rows,
            "fatture_documenti": [],
            "users": [{"id": "u1", "nome_gruppo": "OFFSIDE"}],
        },
        rpc_handlers={"scadenziario_fatture_aggregate": _scadenziario_fatture_aggregate_handler(fatture_rows)},
    )
    _bind_gruppo(monkeypatch, sb, {"id": "u1"})

    res = gruppo.gruppo_scadenziario(authorization="Bearer x")

    assert len(res.sedi) == 3
    tecnica = next(s for s in res.sedi if s["is_sede_tecnica"])
    assert tecnica["id"] == "tecnica"
    file_to_rid = {d["file_origine"]: d["ristorante_id"] for d in res.documenti}
    assert file_to_rid["a.xml"] == "pv1"
    assert file_to_rid["b.xml"] == "tecnica"
    assert all("sede_nome" in d for d in res.documenti)


def test_gruppo_scadenziario_400_se_account_non_multisede(monkeypatch):
    sb = FakeClient({
        "ristoranti": [
            {"id": "pv1", "nome_ristorante": "SEDE UNICA", "user_id": "u1", "attivo": True, "sede_tecnica": False, "created_at": "2026-01-01"},
        ],
        "users": [{"id": "u1", "nome_gruppo": ""}],
    })
    _bind_gruppo(monkeypatch, sb, {"id": "u1"})

    with pytest.raises(HTTPException) as ei:
        gruppo.gruppo_scadenziario(authorization="Bearer x")
    assert ei.value.status_code == 400


class _CestinoQuery:
    """Fake minimale per get_fatture_cestino: supporta select/eq/in_/not_.is_/range."""

    def __init__(self, rows):
        self._rows = rows
        self._filters = {}
        self._in = None
        self._exclude_null = None
        self._range = None

    def select(self, *_a, **_k):
        return self

    def eq(self, f, v):
        self._filters[f] = v
        return self

    def in_(self, f, vals):
        self._in = (f, list(vals))
        return self

    @property
    def not_(self):
        return self

    def is_(self, f, val):
        if val == "null":
            self._exclude_null = f
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        out = self._matching()
        if self._range is not None:
            start, end = self._range
            out = out[start:end + 1]
        return _Result(out)

    def _matching(self):
        out = []
        for row in self._rows:
            if any(row.get(k) != v for k, v in self._filters.items()):
                continue
            if self._in is not None:
                f, vals = self._in
                if row.get(f) not in vals:
                    continue
            if self._exclude_null and row.get(self._exclude_null) is None:
                continue
            out.append(dict(row))
        return out


class _Result:
    def __init__(self, data):
        self.data = data


class _CestinoClient:
    def __init__(self, fatture_rows):
        self._fatture_rows = fatture_rows

    def table(self, name):
        assert name == "fatture"
        return _CestinoQuery(self._fatture_rows)


def test_gruppo_cestino_aggrega_tutte_le_sedi():
    # get_fatture_cestino e' decorata con @_make_cache -> sotto il mock streamlit
    # globale di conftest.py diventa un MagicMock inerte (vedi Fase 1, stesso
    # bypass usato in test_documenti_service_scadenziario.py).
    from tests.test_documenti_service_scadenziario import _get_fatture_cestino_unwrapped
    get_fatture_cestino = _get_fatture_cestino_unwrapped()

    fatture_rows = [
        {"user_id": "u1", "file_origine": "c.xml", "fornitore": "F3", "totale_riga": 7.0, "deleted_at": "2026-01-03T00:00:00Z", "data_documento": "2026-01-03", "ristorante_id": "pv2"},
        {"user_id": "u1", "file_origine": "d.xml", "fornitore": "F4", "totale_riga": 9.0, "deleted_at": "2026-01-04T00:00:00Z", "data_documento": "2026-01-04", "ristorante_id": "tecnica"},
        {"user_id": "u1", "file_origine": "e.xml", "fornitore": "F5", "totale_riga": 3.0, "deleted_at": None, "data_documento": "2026-01-05", "ristorante_id": "pv1"},
    ]
    sb = _CestinoClient(fatture_rows)
    sedi_nomi = {"pv1": "OFFSIDE San Giuliano", "pv2": "OFFSIDE Villaguardia", "tecnica": "Costi comuni di gruppo"}

    items = get_fatture_cestino("u1", ristorante_id=["pv1", "pv2", "tecnica"], supabase_client=sb, sedi_nomi=sedi_nomi)

    # e.xml non e' cestinato (deleted_at None): resta fuori.
    assert len(items) == 2
    file_to_sede = {c["file_origine"]: c["sede_nome"] for c in items}
    assert file_to_sede["d.xml"] == "Costi comuni di gruppo"
    assert file_to_sede["c.xml"] == "OFFSIDE Villaguardia"


def test_gruppo_cestino_endpoint_usa_resolve_gruppo_con_tecnica(monkeypatch):
    """L'endpoint /api/gruppo/cestino deve risolvere le sedi (incl. tecnica) e
    passarle a get_fatture_cestino: verifica il collegamento, non la logica di
    aggregazione (già coperta dal test sopra e da test_documenti_service_scadenziario)."""
    sb = FakeClient({
        "ristoranti": _sedi_offside(),
        "users": [{"id": "u1", "nome_gruppo": "OFFSIDE"}],
    })
    _bind_gruppo(monkeypatch, sb, {"id": "u1"})

    captured = {}

    def _fake_get_fatture_cestino(user_id, ristorante_id=None, supabase_client=None, sedi_nomi=None):
        captured["ristorante_id"] = ristorante_id
        captured["sedi_nomi"] = sedi_nomi
        return [{"file_origine": "x.xml", "ristorante_id": "tecnica", "sede_nome": "Costi comuni di gruppo"}]

    monkeypatch.setattr("services.db_service.get_fatture_cestino", _fake_get_fatture_cestino)

    res = gruppo.gruppo_cestino(authorization="Bearer x")

    assert res.count == 1
    assert set(captured["ristorante_id"]) == {"pv1", "pv2", "tecnica"}
    assert captured["sedi_nomi"]["tecnica"] == "Costi comuni di gruppo"


# ─── ownership check /api/scadenziario/pagata + /scadenza ──────────────────


def _bind_scadenziario(monkeypatch, sb, user_id):
    monkeypatch.setattr(scadenziario, "_resolve_user_from_token", lambda *a, **k: {"id": user_id})
    monkeypatch.setattr(scadenziario, "_get_supabase_client", lambda *a, **k: sb)


def test_pagata_senza_ristorante_id_comportamento_invariato(monkeypatch):
    sb = FakeClient({"ristoranti": _sedi_offside()})
    _bind_scadenziario(monkeypatch, sb, "u1")
    monkeypatch.setattr(scadenziario, "_resolve_ristorante_id", lambda *a, **k: "pv1")
    monkeypatch.setattr(
        "services.documenti_service.segna_fattura_pagata",
        lambda **kw: {"success": True, **kw},
    )

    res = scadenziario.segna_pagata_endpoint(
        scadenziario.PagataRequest(file_origini=["a.xml"], pagata=True),
        authorization="Bearer x",
    )
    assert res["ok"] is True
    assert res["dettaglio"][0]["ristorante_id"] == "pv1"


def test_pagata_con_ristorante_id_di_unaltra_sede_del_gruppo_ok(monkeypatch):
    """Il body porta ristorante_id della sede TECNICA (documento di gruppo): deve
    passare l'ownership check ed essere usato al posto della sede attiva."""
    sb = FakeClient({"ristoranti": _sedi_offside()})
    _bind_scadenziario(monkeypatch, sb, "u1")
    monkeypatch.setattr(scadenziario, "_resolve_ristorante_id", lambda *a, **k: "pv1")
    monkeypatch.setattr(
        "services.documenti_service.segna_fattura_pagata",
        lambda **kw: {"success": True, **kw},
    )

    res = scadenziario.segna_pagata_endpoint(
        scadenziario.PagataRequest(file_origini=["b.xml"], pagata=True, ristorante_id="tecnica"),
        authorization="Bearer x",
    )
    assert res["ok"] is True
    assert res["dettaglio"][0]["ristorante_id"] == "tecnica"


def test_pagata_con_ristorante_id_non_del_cliente_404(monkeypatch):
    """ristorante_id nel body che non appartiene all'account (cross-tenant): 404,
    niente scrittura."""
    sb = FakeClient({"ristoranti": _sedi_offside()})
    _bind_scadenziario(monkeypatch, sb, "u1")
    monkeypatch.setattr(scadenziario, "_resolve_ristorante_id", lambda *a, **k: "pv1")
    called = []
    monkeypatch.setattr(
        "services.documenti_service.segna_fattura_pagata",
        lambda **kw: called.append(kw) or {"success": True},
    )

    with pytest.raises(HTTPException) as ei:
        scadenziario.segna_pagata_endpoint(
            scadenziario.PagataRequest(file_origini=["x.xml"], pagata=True, ristorante_id="sede-di-un-altro"),
            authorization="Bearer x",
        )
    assert ei.value.status_code == 404
    assert not called


def test_scadenza_override_con_ristorante_id_ownership_ok(monkeypatch):
    sb = FakeClient({"ristoranti": _sedi_offside()})
    _bind_scadenziario(monkeypatch, sb, "u1")
    monkeypatch.setattr(scadenziario, "_resolve_ristorante_id", lambda *a, **k: "pv1")
    calls = []
    monkeypatch.setattr(
        "services.documenti_service.set_scadenza_override",
        lambda **kw: calls.append(kw) or {"ok": True},
    )

    res = scadenziario.set_scadenza_override_endpoint(
        scadenziario.ScadenzaOverrideRequest(
            file_origine="b.xml", scadenza_override="2026-08-01", ristorante_id="tecnica",
        ),
        authorization="Bearer x",
    )
    assert res["ok"] is True
    assert calls[0]["ristorante_id"] == "tecnica"


def test_scadenza_override_con_ristorante_id_non_del_cliente_404(monkeypatch):
    sb = FakeClient({"ristoranti": _sedi_offside()})
    _bind_scadenziario(monkeypatch, sb, "u1")
    monkeypatch.setattr(scadenziario, "_resolve_ristorante_id", lambda *a, **k: "pv1")
    called = []
    monkeypatch.setattr(
        "services.documenti_service.set_scadenza_override",
        lambda **kw: called.append(kw) or {"ok": True},
    )

    with pytest.raises(HTTPException) as ei:
        scadenziario.set_scadenza_override_endpoint(
            scadenziario.ScadenzaOverrideRequest(
                file_origine="b.xml", scadenza_override="2026-08-01", ristorante_id="non-mio",
            ),
            authorization="Bearer x",
        )
    assert ei.value.status_code == 404
    assert not called
