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
    margini = {3: _row(altri=8000, q_fb=2000)}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=3)
    assert kpi["food_cost_pct"] == round(2000 / 8000 * 100, 1)
