"""Test di GET /api/admin/riparto/incoerenze e GET /api/gruppo/costi-comuni
(services/routers/riparto.py). Entrambi sola lettura, 0 test prima di questo
file (audit ONEFLUX §2, 8/8/2026, residuo dopo la copertura di riparto_da_fattura).

riparto_incoerenze: diagnostica per il workflow riparto_coerenza_check.yml,
aggrega v_riparto_incoerenze per account distinguendo 'orfano' (costo sparito
dal MOL) da 'riparto_senza_documento' (costo fantasma ancora contato) — le due
classi non sono mai sommabili in un unico numero, solo il totale conta le righe.

gruppo_costi_comuni: lista costi di gruppo del mese con quote per sede, gatato
da _require_catena (>=2 sedi attive, altrimenti 400).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.riparto as riparto


# ─── riparto_incoerenze ────────────────────────────────────────────────────

class _QueryIncoerenze:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self

    def execute(self):
        if self._t == "v_riparto_incoerenze":
            return SimpleNamespace(data=self._c.righe)
        return SimpleNamespace(data=[])


class _FakeSBIncoerenze:
    def __init__(self, righe):
        self.righe = righe

    def table(self, name):
        return _QueryIncoerenze(self, name)


def _patch_incoerenze(righe):
    sb = _FakeSBIncoerenze(righe)
    return sb, patch.object(riparto, "_get_supabase_client", MagicMock(return_value=sb))


def test_incoerenze_vuoto():
    sb, p = _patch_incoerenze([])
    with p:
        out = riparto.riparto_incoerenze()
    assert out == {"totale": 0, "account": []}


def test_incoerenze_bucket_orfano_e_senza_documento():
    righe = [
        {
            "user_id": "user-1", "tipo_incoerenza": "orfano",
            "file_origine": "IT123_a.xml", "riparto_id": None,
            "fornitore": "Fornitore A", "importo": 100.0, "data_documento": "2026-06-01",
        },
        {
            "user_id": "user-1", "tipo_incoerenza": "riparto_senza_documento",
            "file_origine": None, "riparto_id": "riparto-9",
            "fornitore": "Fornitore B", "importo": 250.5, "data_documento": "2026-06-10",
        },
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()

    assert out["totale"] == 2
    assert len(out["account"]) == 1
    acc = out["account"][0]
    assert acc["user_id"] == "user-1"
    assert len(acc["orfani"]) == 1
    assert acc["orfani"][0]["fornitore"] == "Fornitore A"
    assert acc["orfani"][0]["importo"] == 100.0
    assert len(acc["riparti_senza_documento"]) == 1
    assert acc["riparti_senza_documento"][0]["riparto_id"] == "riparto-9"


def test_incoerenze_multi_account_non_mischiati():
    righe = [
        {"user_id": "user-1", "tipo_incoerenza": "orfano", "file_origine": "a.xml",
         "riparto_id": None, "fornitore": "F1", "importo": 10.0, "data_documento": "2026-06-01"},
        {"user_id": "user-2", "tipo_incoerenza": "orfano", "file_origine": "b.xml",
         "riparto_id": None, "fornitore": "F2", "importo": 20.0, "data_documento": "2026-06-02"},
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()

    assert out["totale"] == 2
    uids = {acc["user_id"] for acc in out["account"]}
    assert uids == {"user-1", "user-2"}
    for acc in out["account"]:
        assert len(acc["orfani"]) == 1
        assert len(acc["riparti_senza_documento"]) == 0


def test_incoerenze_importo_none_non_solleva():
    righe = [
        {"user_id": "user-1", "tipo_incoerenza": "orfano", "file_origine": "a.xml",
         "riparto_id": None, "fornitore": "F1", "importo": None, "data_documento": None},
    ]
    sb, p = _patch_incoerenze(righe)
    with p:
        out = riparto.riparto_incoerenze()
    assert out["account"][0]["orfani"][0]["importo"] is None


# ─── gruppo_costi_comuni ────────────────────────────────────────────────────

_SEDI_2 = [
    {"id": "sede-a", "nome_ristorante": "Locale A"},
    {"id": "sede-b", "nome_ristorante": "Locale B"},
]

_SEDE_1 = [{"id": "sede-a", "nome_ristorante": "Locale A"}]


class _QueryCostiComuni:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def order(self, *a, **k): return self

    def execute(self):
        if self._t == "riparto_costi_catena":
            return SimpleNamespace(data=self._c.costi)
        if self._t == "riparto_costi_catena_quote":
            return SimpleNamespace(data=self._c.quote)
        return SimpleNamespace(data=[])


class _FakeSBCostiComuni:
    def __init__(self, costi, quote):
        self.costi = costi
        self.quote = quote

    def table(self, name):
        return _QueryCostiComuni(self, name)


def _patch_costi_comuni(costi, quote, sedi=_SEDI_2):
    sb = _FakeSBCostiComuni(costi, quote)
    p = patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _carica_sedi_attive=MagicMock(return_value=sedi),
    )
    return sb, p


def test_costi_comuni_richiede_almeno_2_sedi():
    sb, p = _patch_costi_comuni([], [], sedi=_SEDE_1)
    with p, pytest.raises(HTTPException) as exc:
        riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert exc.value.status_code == 400


def test_costi_comuni_nessun_costo_ritorna_vuoto_senza_interrogare_quote():
    sb, p = _patch_costi_comuni([], [])
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")
    assert out == {"anno": 2026, "mese": 6, "costi": [], "totale": 0.0}


def test_costi_comuni_happy_path_mappa_sede_e_totale():
    costi = [
        {"id": "c1", "origine": "manuale", "file_origine": None, "fornitore": "FASTWEB",
         "descrizione": "Internet", "importo_totale": 100.0, "tipo": "generale", "regola": "equa"},
        {"id": "c2", "origine": "manuale", "file_origine": None, "fornitore": "ENEL",
         "descrizione": "Energia", "importo_totale": 200.5, "tipo": "generale", "regola": "equa"},
    ]
    quote = [
        {"riparto_id": "c1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 50.0},
        {"riparto_id": "c1", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 50.0},
        {"riparto_id": "c2", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 100.25},
        {"riparto_id": "c2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 100.25},
    ]
    sb, p = _patch_costi_comuni(costi, quote)
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")

    assert out["anno"] == 2026 and out["mese"] == 6
    assert out["totale"] == 300.5
    assert len(out["costi"]) == 2
    c1 = next(c for c in out["costi"] if c["id"] == "c1")
    assert len(c1["quote"]) == 2
    sedi_nomi = {q["sede"] for q in c1["quote"]}
    assert sedi_nomi == {"Locale A", "Locale B"}


def test_costi_comuni_costo_senza_quote_ritorna_lista_vuota():
    costi = [
        {"id": "c1", "origine": "manuale", "file_origine": None, "fornitore": "FASTWEB",
         "descrizione": "Internet", "importo_totale": 100.0, "tipo": "generale", "regola": "equa"},
    ]
    sb, p = _patch_costi_comuni(costi, [])
    with p:
        out = riparto.gruppo_costi_comuni(anno=2026, mese=6, authorization="Bearer x")

    assert out["costi"][0]["quote"] == []
    assert out["totale"] == 100.0
