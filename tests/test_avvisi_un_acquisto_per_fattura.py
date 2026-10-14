"""Negli avvisi prezzi (Home, chat, notifiche, briefing) un acquisto e' una fattura.

`calcola_alert` confrontava le ultime due RIGHE: con lo stesso prodotto su piu'
righe della stessa fattura l'avviso nasceva dentro la fattura (ORTOFRUTTA 2,88
-> 3,83 nella 39/FA, screenshot di Mattia del 14/10/2026) o nascondeva la
variazione vera rispetto alla fattura prima. Misurato sul live: su 3.656 serie
del 2026, in 822 ultimo e penultimo stavano nella stessa fattura. Ora la regola
e' quella dell'Osservatorio (`una_riga_per_documento`).
"""
import pandas as pd
import pytest

from services.db_service import calcola_alert
from services.routers.prezzi import _calcola_variazioni_prezzi_sync


def _avvisi(righe, soglia=5.0):
    df = pd.DataFrame([
        {"Categoria": "VERDURE", "Fornitore": "GIANOLI", "UnitaMisura": "PZ", **r} for r in righe
    ])
    return calcola_alert(df, soglia)


def test_due_prezzi_nella_stessa_fattura_non_sono_un_avviso():
    out = _avvisi([
        {"Descrizione": "ORTOFRUTTA", "DataDocumento": "2026-04-04", "PrezzoUnitario": 10.0, "Quantita": 1, "FileOrigine": "39.xml"},
        {"Descrizione": "ORTOFRUTTA", "DataDocumento": "2026-04-04", "PrezzoUnitario": 12.0, "Quantita": 1, "FileOrigine": "39.xml"},
    ])
    assert out.empty, "un avviso nato dentro una sola fattura"


def test_la_variazione_e_fra_la_fattura_prima_e_l_ultima_ponderata():
    out = _avvisi([
        {"Descrizione": "ORTOFRUTTA", "DataDocumento": "2026-03-04", "PrezzoUnitario": 2.50, "Quantita": 2, "FileOrigine": "38.xml"},
        {"Descrizione": "ORTOFRUTTA", "DataDocumento": "2026-04-04", "PrezzoUnitario": 2.88, "Quantita": 2, "FileOrigine": "39.xml"},
        {"Descrizione": "ORTOFRUTTA", "DataDocumento": "2026-04-04", "PrezzoUnitario": 3.83, "Quantita": 4, "FileOrigine": "39.xml"},
        {"Descrizione": "ORTOFRUTTA", "DataDocumento": "2026-04-04", "PrezzoUnitario": 2.88, "Quantita": 2, "FileOrigine": "39.xml"},
    ])
    assert len(out) == 1
    ponderato = (2.88 * 2 + 3.83 * 4 + 2.88 * 2) / 8
    assert out.loc[0, "Ultimo"] == pytest.approx(ponderato)
    assert out.loc[0, "Aumento_Perc"] == pytest.approx((ponderato - 2.50) / 2.50 * 100)
    assert out.loc[0, "N_Fattura"] == "39.xml"


def test_avviso_e_osservatorio_confrontano_le_stesse_fatture():
    """Stesse righe nelle due forme (colonne del caricamento degli avvisi e del
    PV): stesso ultimo, stesso penultimo, stessa fattura."""
    righe = [
        ("MOZZARELLA", "2026-03-01", 6.00, 2, "a.xml", "PZ"),
        ("MOZZARELLA", "2026-03-20", 6.10, 1, "b.xml", "PZ"),
        ("MOZZARELLA", "2026-03-20", 6.90, 3, "b.xml", "PZ"),
        ("MOZZARELLA", "2026-04-02", 7.00, 1, "D.xml", "PZ"),
        ("MOZZARELLA", "2026-04-02", 5.00, 1, "c.xml", "PZ"),
    ]
    avv = calcola_alert(pd.DataFrame([
        {"Descrizione": d, "Fornitore": "ADC", "Categoria": "LATTICINI", "DataDocumento": g,
         "PrezzoUnitario": p, "Quantita": q, "FileOrigine": f, "UnitaMisura": u}
        for d, g, p, q, f, u in righe
    ]), 0.0)
    pv = _calcola_variazioni_prezzi_sync([
        {"descrizione": d, "fornitore": "ADC", "categoria": "LATTICINI", "data_documento": g,
         "prezzo_unitario": p, "quantita": q, "file_origine": f, "unita_misura": u, "tipo_documento": "TD01"}
        for d, g, p, q, f, u in righe
    ], 0.0)
    assert len(avv) == len(pv) == 1
    assert avv.loc[0, "N_Fattura"] == pv[0]["n_fattura"] == "c.xml", "spareggio sul nome del file: «D» < «c»"
    assert avv.loc[0, "Ultimo"] == pytest.approx(pv[0]["ultimo"])
    assert avv.loc[0, "Ultimo"] - avv.loc[0, "Delta_Euro"] == pytest.approx(pv[0]["penultimo"])


def test_unita_diverse_nella_stessa_fattura_restano_due_acquisti():
    out = _avvisi([
        {"Descrizione": "ANATRA", "DataDocumento": "2026-04-01", "PrezzoUnitario": 5.00, "Quantita": 16, "FileOrigine": "1.xml"},
        {"Descrizione": "ANATRA", "DataDocumento": "2026-05-01", "PrezzoUnitario": 5.50, "Quantita": 16, "FileOrigine": "2.xml"},
        {"Descrizione": "ANATRA", "DataDocumento": "2026-05-01", "PrezzoUnitario": 84.0, "Quantita": 1, "FileOrigine": "2.xml", "UnitaMisura": "CT"},
    ], 0.0)
    # CT prima di PZ nello spareggio: l'ultimo e' la 2 in PZ, il penultimo il CT
    # (salto di 10 volte: nessun avviso, come «Confezione diversa?»).
    assert out.empty


def test_un_omaggio_nella_stessa_fattura_non_abbassa_il_prezzo():
    """Le righe a prezzo zero (omaggi) restano fuori PRIMA della fusione: dentro,
    con il loro peso, abbasserebbero il prezzo pagato (5,50 -> 4,89)."""
    out = _avvisi([
        {"Descrizione": "LATTE", "DataDocumento": "2026-04-01", "PrezzoUnitario": 5.00, "Quantita": 16, "FileOrigine": "1.xml"},
        {"Descrizione": "LATTE", "DataDocumento": "2026-05-01", "PrezzoUnitario": 5.50, "Quantita": 16, "FileOrigine": "2.xml"},
        {"Descrizione": "LATTE", "DataDocumento": "2026-05-01", "PrezzoUnitario": 0.00, "Quantita": 2, "FileOrigine": "2.xml"},
    ])
    assert out.loc[0, "Ultimo"] == pytest.approx(5.50)
