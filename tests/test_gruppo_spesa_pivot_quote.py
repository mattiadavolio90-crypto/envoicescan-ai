"""Test GET /api/gruppo/spesa-pivot: le quote dei costi di gruppo devono entrare
nelle colonne dei PV.

Bug: la RPC gruppo_spesa_pivot aggrega solo le fatture POSSEDUTE dai PV
(p_ristorante_ids esclude la sede tecnica per costruzione, via _resolve_gruppo).
Le fatture di struttura (Fastweb, Wind, Telepass...) vivono sulla sede tecnica
"Costi comuni di gruppo": prima del fix non comparivano in nessuna colonna né
nel grand_total. Decisione di prodotto (Mattia, 04/08): le quote entrano DENTRO
le colonne dei PV, stesso criterio del tab Calcolo — non una colonna separata.
"""
from unittest.mock import MagicMock, patch

import services.routers.gruppo as gruppo_router


def _rpc_sb(rpc_rows):
    sb = MagicMock()
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=rpc_rows)
    sb.rpc.return_value = rpc_res
    sb.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])
    return sb


def _call(rpc_rows, quote_per_pv, dimensione="categoria"):
    sb = _rpc_sb(rpc_rows)
    resolve = (sb, "u1", [], "Gruppo Test", {"pv-a": "OFFSIDE", "pv-b": "OVERTIME"}, ["pv-a", "pv-b"])

    def fake_quote(_sb, rid, _da, _a):
        return quote_per_pv.get(rid, [])

    with patch.object(gruppo_router, "_resolve_gruppo", return_value=resolve), \
         patch.object(gruppo_router, "_periodo_da_query", return_value=("2026-07-01", "2026-07-31", "Luglio 2026")), \
         patch.object(gruppo_router, "_righe_quote_gruppo", side_effect=fake_quote):
        return gruppo_router.gruppo_spesa_pivot(dimensione=dimensione, authorization="Bearer tok")


def test_quota_di_gruppo_entra_nella_colonna_del_pv():
    rpc_rows = [{"ristorante_id": "pv-a", "dim_val": "CARNE", "totale": 1000.0}]
    quote = {"pv-a": [{"categoria": "UTENZE E LOCALI", "totale_riga": 144.06}]}

    out = _call(rpc_rows, quote)

    assert out.totali_pv["pv-a"] == 1000.0 + 144.06
    assert out.grand_total == 1000.0 + 144.06
    riga_utenze = next(r for r in out.rows if r.dim_val == "UTENZE E LOCALI")
    assert riga_utenze.per_pv["pv-a"] == 144.06
    assert riga_utenze.per_pv["pv-b"] == 0.0


def test_pv_senza_quote_comportamento_invariato():
    rpc_rows = [{"ristorante_id": "pv-a", "dim_val": "CARNE", "totale": 1000.0}]
    out = _call(rpc_rows, quote_per_pv={})
    assert out.totali_pv["pv-a"] == 1000.0
    assert out.grand_total == 1000.0


def test_dimensione_fornitore_usa_il_fornitore_della_quota():
    rpc_rows = []
    quote = {"pv-a": [{"fornitore": "FASTWEB S.P.A", "totale_riga": 362.0}]}
    out = _call(rpc_rows, quote, dimensione="fornitore")
    riga = next(r for r in out.rows if r.dim_val == "FASTWEB S.P.A")
    assert riga.per_pv["pv-a"] == 362.0
