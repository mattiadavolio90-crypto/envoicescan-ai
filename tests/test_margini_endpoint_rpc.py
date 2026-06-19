"""Test guardia: l'endpoint GET /api/margini usa la RPC costi_automatici_mensili
(via calcola_costi_automatici_per_anno_sql) invece del full-load di tutte le righe
fattura dell'anno + groupby pandas.

Contesto (audit 19/06, finding Performance): get_margini scaricava paginando TUTTE
le righe fattura dell'anno e aggregava in pandas — il collo di bottiglia su clienti
con molte fatture. La RPC SQL fa la stessa aggregazione lato DB ed e' gia' verificata
numericamente identica (test_margine_service). Questi test verificano il WIRING:
che l'endpoint chiami l'helper SQL e mappi correttamente i costi auto per mese nella
risposta, fondendoli con i valori salvati in margini_mensili.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.routers.margini as margini


def _saved_query_mock(saved_rows):
    """Mock della query su margini_mensili (select/eq/eq/execute)."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.execute.return_value = SimpleNamespace(data=saved_rows or [])
    client = MagicMock()
    client.table.return_value = q
    return client


def _patch(saved_rows, costi_fb, costi_spese):
    client = _saved_query_mock(saved_rows)
    return patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ), patch(
        "services.margine_service.calcola_costi_automatici_per_anno_sql",
        MagicMock(return_value=(costi_fb, costi_spese)),
    )


def test_get_margini_usa_rpc_per_costi_auto():
    """I costi auto della risposta vengono dalla RPC, non dal full-load fatture."""
    p_router, p_rpc = _patch(
        saved_rows=[],
        costi_fb={3: 1200.0, 7: 800.0},
        costi_spese={3: 150.0},
    )
    with p_router, p_rpc as mock_rpc:
        resp = margini.get_margini(anno=2026, authorization="Bearer x")

    mock_rpc.assert_called_once_with("user-1", "rist-1", 2026)
    per_mese = {m.mese: m for m in resp.mesi}
    assert per_mese[3].costi_fb_auto == 1200.0
    assert per_mese[3].costi_spese_auto == 150.0
    assert per_mese[7].costi_fb_auto == 800.0
    # Un mese senza righe nella RPC resta a zero
    assert per_mese[1].costi_fb_auto == 0.0
    assert per_mese[1].costi_spese_auto == 0.0


def test_get_margini_fonde_salvato_e_auto():
    """I valori salvati (margini_mensili) e i costi auto (RPC) convivono nello stesso mese."""
    p_router, p_rpc = _patch(
        saved_rows=[{"mese": 3, "fatturato_iva10": 5000.0, "costo_dipendenti": 2000.0}],
        costi_fb={3: 1200.0},
        costi_spese={},
    )
    with p_router, p_rpc:
        resp = margini.get_margini(anno=2026, authorization="Bearer x")

    marzo = next(m for m in resp.mesi if m.mese == 3)
    assert marzo.fatturato_iva10 == 5000.0
    assert marzo.costo_dipendenti == 2000.0
    assert marzo.costi_fb_auto == 1200.0


def test_get_margini_dodici_mesi_sempre_presenti():
    """La risposta ha sempre 12 mesi anche senza dati."""
    p_router, p_rpc = _patch(saved_rows=[], costi_fb={}, costi_spese={})
    with p_router, p_rpc:
        resp = margini.get_margini(anno=2026, authorization="Bearer x")
    assert [m.mese for m in resp.mesi] == list(range(1, 13))
