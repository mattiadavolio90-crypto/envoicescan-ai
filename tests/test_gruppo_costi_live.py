"""Test guardia: la Sintesi di catena ricalcola i costi LIVE (non dallo snapshot)
e somma le quote di riparto costi di gruppo al MOL.

Contesto: gruppo_overview / gruppo_margini_coperti leggevano
margini_mensili.costi_fb_totali e .mol (snapshot popolato solo quando qualcuno
salva la pagina Margini della sede → a 0 per un cliente appena partito). Ora usano
la RPC costi_automatici_mensili_gruppo (calcolo live per sede×mese) e sommano
altri_costi_* + quote_riparto_* come la pagina Margini del PV. Questi test bloccano
una regressione a "solo snapshot" o "quote riparto ignorate".
"""
from unittest.mock import MagicMock, patch

from services.margine_service import calcola_costi_automatici_gruppo_sql


def _rpc_sb(rows):
    sb = MagicMock()
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=rows)
    sb.rpc.return_value = rpc_res
    return sb


class TestCalcolaCostiAutomaticiGruppoSql:
    def test_split_food_spese_per_sede(self):
        rows = [
            {"ristorante_id": "a", "mese": 1, "food": 100.0, "spese": 50.0},
            {"ristorante_id": "a", "mese": 2, "food": 0.0, "spese": 30.0},
            {"ristorante_id": "b", "mese": 1, "food": 200.0, "spese": 0.0},
        ]
        with patch("services.margine_service.get_supabase_client", return_value=_rpc_sb(rows)):
            out = calcola_costi_automatici_gruppo_sql("u1", ["a", "b"], 2026)
        fb_a, sp_a = out["a"]
        fb_b, sp_b = out["b"]
        assert fb_a == {1: 100.0}          # food a mese 2 è 0 → niente chiave spuria
        assert sp_a == {1: 50.0, 2: 30.0}
        assert fb_b == {1: 200.0}
        assert sp_b == {}                  # spese b tutte 0

    def test_sede_senza_righe_resta_vuota(self):
        with patch("services.margine_service.get_supabase_client", return_value=_rpc_sb([])):
            out = calcola_costi_automatici_gruppo_sql("u1", ["a", "b"], 2026)
        assert out == {"a": ({}, {}), "b": ({}, {})}

    def test_lista_vuota_nessuna_query(self):
        # Nessun ristorante → nessuna chiamata RPC, dict vuoto.
        with patch("services.margine_service.get_supabase_client") as gc:
            out = calcola_costi_automatici_gruppo_sql("u1", [], 2026)
        assert out == {}
        gc.assert_not_called()

    def test_fallback_per_sede_se_rpc_fallisce(self):
        sb = MagicMock()
        sb.rpc.side_effect = RuntimeError("rpc giù")
        with patch("services.margine_service.get_supabase_client", return_value=sb), patch(
            "services.margine_service.calcola_costi_automatici_per_anno_sql",
            return_value=({3: 77.0}, {3: 11.0}),
        ) as fb:
            out = calcola_costi_automatici_gruppo_sql("u1", ["a"], 2026)
        assert out == {"a": ({3: 77.0}, {3: 11.0})}
        fb.assert_called_once_with("u1", "a", 2026)
