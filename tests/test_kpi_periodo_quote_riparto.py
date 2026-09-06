"""Test _kpi_periodo (services.fastapi_worker): quote di riparto catena nel MOL.

Bug: su una sede di catena (OFFSIDE/OVERTIME) i costi di gruppo ripartiti sono
scritti in margini_mensili.quote_riparto_fb/spese, ma _kpi_periodo (Home KPI,
sparkline MOL, briefing "buona notizia", prompt chat AI) li ignorava. Il costo
automatico esclude gia' le fatture ripartita_su_gruppo (vivono sulla sede
tecnica): senza sommare le quote il costo di gruppo spariva da entrambi i lati
e il MOL risultava GONFIATO dell'intero importo della quota.

La barra KPI della pagina Margini (_aggrega_mensili_margini) sommava gia' le
quote correttamente: prima del fix Home e Margini mostravano MOL diversi per
lo stesso mese sulla stessa sede.
"""
import services.fastapi_worker as fw


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


def test_mol_include_le_quote_di_riparto():
    # Netto = 10000 (no IVA da scorporare), nessun costo auto, nessun personale.
    # Le uniche voci di costo sono le quote di gruppo.
    margini = {5: _row(altri=10000, q_fb=1000, q_spese=500)}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=5)
    assert kpi["mol"] == 10000 - 1000 - 500


def test_senza_quote_comportamento_invariato():
    # Sede mono (CASATI): quote_riparto_* assenti dal record -> nessun impatto.
    margini = {5: {
        "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 5000,
        "costo_dipendenti": 1000, "costo_personale_extra": 0,
    }}
    kpi = fw._kpi_periodo(margini, costi_fb={5: 500}, costi_spese={5: 300}, mese=5)
    assert kpi["mol"] == 5000 - 500 - 300 - 1000


def test_mol_home_coincide_con_formula_barra_kpi_margini():
    # Stessa identica somma di _aggrega_mensili_margini (fastapi_worker.py
    # ~7785-7786): fb_tot = costi_fb_auto + altri_costi_fb + quote_riparto_fb.
    # Home e pagina Margini devono dare lo stesso MOL sullo stesso mese/sede.
    margini = {7: _row(altri=20000, altri_fb=200, altri_spese=100, q_fb=144.06, q_spese=14086.78)}
    kpi = fw._kpi_periodo(margini, costi_fb={7: 6219.0}, costi_spese={7: 2770.0}, mese=7)

    fb_tot = 6219.0 + 200 + 144.06
    sp_tot = 2770.0 + 100 + 14086.78
    mol_atteso = 20000 - fb_tot - sp_tot
    assert round(kpi["mol"], 2) == round(mol_atteso, 2)


def test_food_cost_pct_include_la_quota():
    """La quota di riparto entra nel NUMERATORE del food cost.

    Usa `altri_ricavi_noiva`, dove netto e lordo coincidono: questo test NON
    presidia il denominatore (passerebbe con entrambe le formule). Quello lo fa
    tests/test_food_cost_sempre_su_netto.py, con IVA da scorporare.
    """
    margini = {3: _row(altri=8000, q_fb=2000)}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=3)
    assert kpi["food_cost_pct"] == round(2000 / 8000 * 100, 1)


def test_food_cost_pct_quota_con_iva_da_scorporare():
    """Stessa quota, ma su ricavi con IVA: qui il denominatore conta davvero."""
    margini = {3: _row(iva10=8800, q_fb=2000)}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=3)
    assert kpi["food_cost_pct"] == 25.0, "2.000 / 8.000 netto"
    assert kpi["food_cost_pct"] != 22.7, "22,7 sarebbe il vecchio calcolo sul lordo"


# ───────────────────────────────────────────────────────────────────────────
# /api/margini/kpi e /api/margini/analisi: la stessa pagina, due formule
# (audit 06/09)
#
# La formula del MOL e' scritta due volte — margini.py:1184 dentro
# get_margini_analisi, e fastapi_worker.py:8618 in _aggrega_mensili_margini,
# che alimenta get_margini_kpi. I due endpoint servono la STESSA schermata:
# KpiBar (page.tsx:72) sta sopra i tab ed e' sempre a video, CalcoloTab
# (calcolo-tab.tsx:158) sta sotto. Una divergenza fra le due copie mette due
# MOL diversi nella stessa pagina, e nessun test la vedeva.
#
# Fino al 06/09 le percentuali divergevano davvero: /kpi arrotondava a 1
# decimale e /analisi a 2 (33,8 contro 33,79). Non era solo estetica —
# food_cost_perc alimenta la soglia del trigger Consulenza
# (lib/trigger-servizi.ts:144), con un confronto stretto `fc > soglia`.
# ───────────────────────────────────────────────────────────────────────────
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.margini as margini


def _patch_due_endpoint(saved_rows, costi_auto):
    """Stessi dati per entrambi gli endpoint: se divergono, e' colpa loro."""
    q = MagicMock()
    for m in ("select", "eq", "in_", "gte", "lte"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=saved_rows or [])
    client = MagicMock()
    client.table.return_value = q
    return client


@pytest.mark.parametrize("iva10,iva22,fb_auto,dipendenti", [
    # Scelti perche' cadono male sull'arrotondamento: 2745/8123 = 33,79%
    (8935.30, 0.0, 2745.0, 1500.0),
    (11000.0, 12200.0, 7333.0, 2100.0),
    (5000.0, 0.0, 1.0, 0.0),
])
def test_kpi_e_analisi_danno_lo_stesso_mol_e_le_stesse_percentuali(
    iva10, iva22, fb_auto, dipendenti
):
    saved = [{
        "anno": 2026, "mese": 3,
        "fatturato_iva10": iva10, "fatturato_iva22": iva22,
        "altri_ricavi_noiva": 0.0,
        "altri_costi_fb": 0.0, "altri_costi_spese": 0.0,
        "quote_riparto_fb": 0.0, "quote_riparto_spese": 0.0,
        "costo_dipendenti": dipendenti, "costo_personale_extra": 0.0,
    }]
    client = _patch_due_endpoint(saved, (fb_auto, 0.0))

    common = dict(
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    )

    with patch.multiple(margini, **common), \
            patch.object(margini, "_calcola_costi_auto_per_periodo",
                         MagicMock(return_value={(2026, 3): (fb_auto, 0.0)})), \
            patch.object(margini, "_load_mensile_overrides", MagicMock(return_value={})):
        analisi = margini.get_margini_analisi("2026-03-01", "2026-03-31", authorization="Bearer x")

    # _aggrega_mensili_margini legge il DB da se': gli si passa lo stesso client
    # e gli stessi costi auto, cosi' l'unica variabile e' la formula.
    with patch.object(fw, "_calcola_costi_auto_per_mese", MagicMock(return_value=(fb_auto, 0.0))), \
            patch.object(fw, "_load_mensile_overrides", MagicMock(return_value={})):
        import datetime as _dt
        agg = fw._aggrega_mensili_margini(client, "rist-1", _dt.date(2026, 3, 1), _dt.date(2026, 3, 31))

    # L'ENDPOINT vero, non solo l'helper: un confronto agg-vs-analisi non vede
    # l'arrotondamento, che vive nella response di get_margini_kpi.
    with patch.multiple(margini, **common), \
            patch.object(margini, "_aggrega_mensili_margini", MagicMock(return_value=agg)):
        kpi = margini.get_margini_kpi("2026-03-01", "2026-03-31", authorization="Bearer x")

    netto = agg["netto"]
    assert netto > 0, "scenario mal costruito: senza netto le percentuali sono 0 per definizione"

    # Le COMPONENTI, non solo il MOL: due errori opposti quadrano il totale.
    assert round(agg["mol"], 2) == analisi.totali.mol
    assert round(agg["pm"], 2) == analisi.totali.primo_margine
    assert round(agg["fb"], 2) == analisi.totali.costi_fb_totali
    assert round(agg["pers"], 2) == analisi.totali.costi_personale

    # Le percentuali: stesso numero di decimali, o la stessa pagina mostra
    # 33,8 sopra e 33,79 sotto.
    assert kpi.food_cost_perc == analisi.food_cost_perc
    assert kpi.mol_perc == analisi.mol_perc
    assert kpi.personale_perc == analisi.personale_perc
    # `spese`: i due endpoint danno alla stessa metrica nomi di campo diversi.
    assert kpi.spese_perc == analisi.spese_gen_perc
    assert kpi.mol == analisi.totali.mol
