"""Test guardia: /api/dashboard/stats usa la RPC aggregata (perf) e ricade sul
full-load Python solo se la RPC fallisce.

Perché conta: l'endpoint prima scaricava TUTTE le righe fattura (LAND: 6.315) e
aggregava in Python a ogni apertura Home. Ora chiama dashboard_stats_aggregata
(GROUP BY lato DB). Questi test bloccano due regressioni:
  - la risposta RPC viene mappata fedelmente su DashboardStats (KPI, mensile, top);
  - se la RPC lancia, NON si rompe: si ricade sul percorso storico.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


_AGG = {
    "kpi": {
        "fatture_uniche": 553,
        "righe_totali": 6315,
        "spesa_totale": 888131.83,
        "spesa_mese_corrente": 0,
        "spesa_mese_precedente": 1234.5,
        "prima_fattura": "2026-01-01",
        "ultima_fattura": "2026-04-30",
    },
    "spesa_mensile": [
        {"mese": "2026-01", "spesa": 200000.0},
        {"mese": "2026-02", "spesa": 220000.0},
    ],
    "top_fornitori": [
        {"nome": "ADC S.R.L", "spesa": 172796.39, "righe": 400},
        {"nome": "H.D. ITALIA S.R.L", "spesa": 105925.35, "righe": 300},
    ],
    "top_categorie": [
        {"nome": "PESCE", "spesa": 90000.0, "righe": 120},
    ],
}


def _fake_sb(rpc_data=None, rpc_raises=False):
    sb = MagicMock()
    if rpc_raises:
        sb.rpc.side_effect = RuntimeError("rpc down")
    else:
        sb.rpc.return_value.execute.return_value = SimpleNamespace(data=rpc_data)
    return sb


def test_dashboard_stats_usa_rpc_e_mappa_i_campi():
    fw._DASHBOARD_STATS_CACHE.clear()
    sb = _fake_sb(rpc_data=_AGG)
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": "u1"}), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value="r1"):
        out = fw.dashboard_stats(authorization="Bearer t")

    assert out.kpi.fatture_uniche == 553
    assert out.kpi.righe_totali == 6315
    assert out.kpi.spesa_totale == 888131.83
    assert out.kpi.ultima_fattura == "2026-04-30"
    assert [p.mese for p in out.spesa_mensile] == ["2026-01", "2026-02"]
    assert out.top_fornitori[0].nome == "ADC S.R.L"
    assert out.top_fornitori[0].righe == 400
    assert out.top_categorie[0].nome == "PESCE"
    # La RPC deve essere stata chiamata col nome giusto e NON deve essere partito
    # il full-load (table('fatture') non interrogata sul path veloce).
    sb.rpc.assert_called_once()
    assert sb.rpc.call_args[0][0] == "dashboard_stats_aggregata"


def test_dashboard_stats_fallback_se_rpc_lancia():
    """Se la RPC lancia, l'endpoint deve ricadere sul full-load senza errori."""
    fw._DASHBOARD_STATS_CACHE.clear()
    sb = _fake_sb(rpc_raises=True)

    # Sul fallback parte table('fatture').select()...range().execute(): mockiamo
    # una risposta vuota -> stats a zero, ma SENZA eccezione (è ciò che testiamo).
    _empty = SimpleNamespace(data=[])
    sb.table.return_value.select.return_value.eq.return_value.is_.return_value.eq.return_value.range.return_value.execute.return_value = _empty
    sb.table.return_value.select.return_value.eq.return_value.is_.return_value.range.return_value.execute.return_value = _empty

    with patch.object(fw, "_resolve_user_from_token", return_value={"id": "u1"}), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=None):
        out = fw.dashboard_stats(authorization="Bearer t")

    # Non deve sollevare: ritorna stats vuote dal percorso Python.
    assert out.kpi.righe_totali == 0
    assert out.kpi.spesa_totale == 0
