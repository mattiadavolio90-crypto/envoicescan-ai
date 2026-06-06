"""
Test per la feature Spese Extra (F&B / Generali).

Copre la logica di aggregazione lato worker:
- get_costo_spese_da_voci: somma le voci del mese separate per tipo (alimenta margini_mensili)
- ws_spese_list: totali per tipo nel periodo
- ws_spese_crea: validazione tipo/descrizione/importo

Le dipendenze su Supabase e auth sono mockate, come per gli altri test del modulo.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.fastapi_worker as worker
import services.routers.margini as margini
import services.routers.workspace as workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query_mock(execute_data=None):
    """Mock chain del client Supabase Python (select/eq/gte/lte/order/execute)."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.gte.return_value = q
    q.lte.return_value = q
    q.order.return_value = q
    q.insert.return_value = q
    q.execute.return_value = SimpleNamespace(data=execute_data or [])
    return q


def _patch_common(voci):
    """Patcha auth + supabase + risoluzione ristorante sul router workspace
    (dove ora vivono ws_spese_*); il client restituisce `voci`."""
    client = MagicMock()
    client.table.return_value = _query_mock(voci)
    return patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _get_ristorante_id_for_user=MagicMock(return_value="rist-1"),
    )


def _patch_margini(voci):
    """Come _patch_common ma sul modulo router margini (dove vive get_costo_spese_da_voci)."""
    client = MagicMock()
    client.table.return_value = _query_mock(voci)
    return patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    )


# ---------------------------------------------------------------------------
# get_costo_spese_da_voci — aggregatore per margini
# ---------------------------------------------------------------------------

class TestCostoSpeseDaVoci:

    def test_aggrega_per_tipo(self):
        voci = [
            {"tipo": "fb", "importo": 100.0},
            {"tipo": "fb", "importo": 50.5},
            {"tipo": "generale", "importo": 30.0},
        ]
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 150.5
        assert res["totale_generale"] == 30.0
        assert res["n_voci_fb"] == 2
        assert res["n_voci_generale"] == 1

    def test_nessuna_voce(self):
        with _patch_margini([]):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 0.0
        assert res["totale_generale"] == 0.0
        assert res["n_voci_fb"] == 0
        assert res["n_voci_generale"] == 0

    def test_importo_none_non_rompe(self):
        voci = [
            {"tipo": "fb", "importo": None},
            {"tipo": "generale", "importo": 20.0},
        ]
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 0.0
        assert res["totale_generale"] == 20.0

    def test_tipo_sconosciuto_ignorato(self):
        voci = [
            {"tipo": "fb", "importo": 10.0},
            {"tipo": "altro", "importo": 999.0},  # non deve confluire da nessuna parte
        ]
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 10.0
        assert res["totale_generale"] == 0.0


# ---------------------------------------------------------------------------
# ws_spese_list — totali per periodo
# ---------------------------------------------------------------------------

class TestSpeseList:

    def test_totali_per_tipo(self):
        voci = [
            {"id": "1", "tipo": "fb", "importo": 40.0},
            {"id": "2", "tipo": "generale", "importo": 60.0},
            {"id": "3", "tipo": "generale", "importo": 15.0},
        ]
        with _patch_common(voci):
            res = workspace.ws_spese_list(da="2026-06-01", a="2026-06-30", authorization="Bearer x")
        assert res["totale_fb"] == 40.0
        assert res["totale_generale"] == 75.0
        assert res["totale"] == 115.0
        assert len(res["voci"]) == 3


# ---------------------------------------------------------------------------
# ws_spese_crea — validazione
# ---------------------------------------------------------------------------

class TestSpeseCrea:

    def test_tipo_non_valido(self):
        body = workspace.NuovaSpesaBody(data_spesa="2026-06-10", tipo="xxx", importo=10.0, descrizione="Test")
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_descrizione_vuota(self):
        body = workspace.NuovaSpesaBody(data_spesa="2026-06-10", tipo="fb", importo=10.0, descrizione="   ")
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_importo_negativo(self):
        body = workspace.NuovaSpesaBody(data_spesa="2026-06-10", tipo="fb", importo=-5.0, descrizione="Test")
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_creazione_valida(self):
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="fb", importo=12.345, descrizione="  Pesce  ", note=None
        )
        client = MagicMock()
        inserted = {"id": "new", "tipo": "fb", "importo": 12.35, "descrizione": "Pesce"}
        q = _query_mock([inserted])
        client.table.return_value = q
        with patch.multiple(
            workspace,
            _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
            _get_supabase_client=MagicMock(return_value=client),
            _get_ristorante_id_for_user=MagicMock(return_value="rist-1"),
        ):
            res = workspace.ws_spese_crea(body=body, authorization="Bearer x")
        # Verifica che l'importo sia stato arrotondato a 2 decimali e descrizione strippata nel payload
        args, kwargs = q.insert.call_args
        payload = args[0]
        assert payload["importo"] == 12.35
        assert payload["descrizione"] == "Pesce"
        assert payload["tipo"] == "fb"
        assert res == inserted
