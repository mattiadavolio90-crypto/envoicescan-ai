"""Il food cost si calcola SEMPRE sul fatturato NETTO, in ogni pagina.

Fino al 4/9/2026 c'erano due definizioni convivevanti:
  - pagina Margini + margine_service (soglie e notifiche) -> NETTO
  - Home (card KPI) + Catena                              -> LORDO

Sullo stesso mese le due davano numeri diversi di 2-4 punti. Il guaio non era
estetico: le soglie di KPI_SOGLIE (38% food cost) sono tarate sul netto, quindi
il denominatore lordo giudicava con un metro piu' generoso e l'allarme NON
scattava quando avrebbe dovuto. Misurato a DB il 4/9 sui costi veri da fatture:
5 mesi su 5 sedi diverse (OVERTIME 6/2026, LAND 4+5/2026, SUSHILAND SAN GIULIANO
5/2026, SUSHILAND VILLA GUARDIA 5/2026) stavano SOTTO il 38 col lordo e SOPRA
col netto.

Questi test valgono come presidio solo perche' confrontano il valore atteso
calcolato sul netto con quello che uscirebbe dal lordo, e i due sono distinti:
rimettere il denominatore lordo li fa fallire. Provati per mutazione.
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw
import services.routers.gruppo as G


def _row(iva10=0, iva22=0, altri=0, altri_fb=0, altri_spese=0,
         q_fb=0, q_spese=0, dipendenti=0, extra=0):
    return {
        "fatturato_iva10": iva10,
        "fatturato_iva22": iva22,
        "altri_ricavi_noiva": altri,
        "altri_costi_fb": altri_fb,
        "altri_costi_spese": altri_spese,
        "quote_riparto_fb": q_fb,
        "quote_riparto_spese": q_spese,
        "costo_dipendenti": dipendenti,
        "costo_personale_extra": extra,
    }


class TestHomeKpiFoodCostSuNetto:
    """services.fastapi_worker._kpi_periodo — la card KPI della Home."""

    def test_denominatore_e_il_netto_non_il_lordo(self):
        # 11.000 al 10% -> netto 10.000; lordo 11.000. F&B 4.000.
        kpi = fw._kpi_periodo({6: _row(iva10=11_000)}, {6: 4_000}, {}, 6)

        assert kpi["food_cost_pct"] == 40.0, "4.000/10.000 netto = 40,0%"
        # Col vecchio divisore sarebbe 36,4: il test distingue le due formule.
        assert kpi["food_cost_pct"] != 36.4

    def test_la_soglia_38_scatta_col_netto_e_non_col_lordo(self):
        """Il caso reale misurato: sotto soglia col lordo, sopra col netto."""
        kpi = fw._kpi_periodo({5: _row(iva10=11_000)}, {5: 4_100}, {}, 5)

        assert kpi["food_cost_pct"] >= 38, "41,0% sul netto: l'allarme deve scattare"
        assert round(4_100 / 11_000 * 100, 1) < 38, "col lordo restava 37,3: muto"

    def test_iva22_e_altri_ricavi_scorporati_come_nel_mol(self):
        """Il netto del food cost e' lo stesso denominatore del MOL."""
        kpi = fw._kpi_periodo(
            {3: _row(iva10=1_100, iva22=1_220, altri=500)}, {3: 1_000}, {}, 3
        )

        netto = 1_100 / 1.10 + 1_220 / 1.22 + 500  # = 2.500
        assert kpi["food_cost_pct"] == round(1_000 / netto * 100, 1) == 40.0

    def test_le_quote_riparto_entrano_nel_numeratore(self):
        """Su una sede di catena i costi di gruppo ripartiti sono costo F&B."""
        kpi = fw._kpi_periodo(
            {7: _row(iva10=11_000, q_fb=1_000)}, {7: 3_000}, {}, 7
        )

        assert kpi["food_cost_pct"] == 40.0, "(3.000+1.000)/10.000 netto"

    def test_senza_ricavi_resta_none_non_zero(self):
        """Nessun ricavo: il food cost non esiste, non e' 0% (che sarebbe ottimo)."""
        kpi = fw._kpi_periodo({9: _row(iva10=0)}, {9: 500}, {}, 9)

        assert kpi["food_cost_pct"] is None


class TestCatenaFoodCostSuNetto:
    """services.routers.gruppo.gruppo_overview — il KPI della pagina Catena.

    Il calcolo vive dentro l'endpoint, quindi il test CHIAMA l'endpoint isolando
    auth/DB. Una versione precedente ricalcolava la formula dentro il test:
    sopravviveva al mutante (il denominatore lordo rimesso in gruppo.py non la
    faceva fallire) e quindi non era un presidio.
    """

    @staticmethod
    def _overview(righe, costi_auto):
        sb = MagicMock()
        q = MagicMock()
        for m in ("select", "in_", "eq", "lte", "order", "limit"):
            getattr(q, m).return_value = q
        q.execute.return_value = MagicMock(data=righe)
        sb.table.return_value = q
        rpc_res = MagicMock()
        rpc_res.execute.return_value = MagicMock(data=[])
        sb.rpc.return_value = rpc_res

        with patch.object(G, "_resolve_gruppo",
                          return_value=(sb, "u1", [{"id": "a"}], "Gruppo",
                                        {"a": "PV a"}, ["a"])), \
             patch.object(G, "_anno_mese_corrente", return_value=(2026, 6)), \
             patch.object(G, "_completezza_dati_pv", return_value={}), \
             patch.object(G, "_overrides_mese_sede", return_value={}), \
             patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                   return_value=costi_auto), \
             patch.object(G, "_calcola_segnali", return_value=[]):
            return G.gruppo_overview(authorization="Bearer t")

    def test_denominatore_e_il_netto_non_il_lordo(self):
        # 11.000 al 10% -> netto 10.000, lordo 11.000. F&B 4.000 dalle fatture.
        righe = [{"ristorante_id": "a", "mese": 6, "fatturato_iva10": 11_000,
                  "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
                  "altri_costi_fb": 0, "altri_costi_spese": 0,
                  "quote_riparto_fb": 0, "quote_riparto_spese": 0,
                  "costo_dipendenti": 0, "costo_personale_extra": 0}]
        resp = self._overview(righe, {"a": ({6: 4_000.0}, {})})

        assert resp.kpi.food_cost_pct == 40.0, "4.000/10.000 netto"
        assert resp.kpi.food_cost_pct != 36.4, "36,4 e' il vecchio valore sul lordo"

    def test_stessa_base_del_margine_medio(self):
        """Le due percentuali della stessa card poggiano sullo stesso netto."""
        righe = [{"ristorante_id": "a", "mese": 6, "fatturato_iva10": 11_000,
                  "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
                  "altri_costi_fb": 0, "altri_costi_spese": 0,
                  "quote_riparto_fb": 0, "quote_riparto_spese": 0,
                  "costo_dipendenti": 1_000, "costo_personale_extra": 0}]
        resp = self._overview(righe, {"a": ({6: 4_000.0}, {})})

        # netto 10.000; fb 4.000; pers 1.000 -> mol 5.000 -> 50,0%
        assert resp.kpi.food_cost_pct == 40.0
        assert resp.kpi.margine_medio_perc == 50.0


class TestCoerenzaFraLePagine:
    """L'invariante che ha motivato il cambio: stesso mese, stesso numero."""

    def test_home_e_margini_danno_lo_stesso_food_cost(self):
        iva10, fb = 11_000, 4_000
        kpi = fw._kpi_periodo({6: _row(iva10=iva10)}, {6: fb}, {}, 6)

        # Formula della pagina Margini (routers/margini.py): fb / netto * 100.
        netto_margini = iva10 / 1.10
        food_cost_margini = round(fb / netto_margini * 100, 1)

        assert kpi["food_cost_pct"] == food_cost_margini
