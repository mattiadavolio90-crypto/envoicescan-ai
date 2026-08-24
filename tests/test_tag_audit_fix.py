"""Guardie per i fix dell'audit §3b sulla feature Tag (24/8/2026).

Ogni test difende un difetto misurato sul DB live, non un caso teorico:
i numeri nei docstring sono quelli osservati sui clienti reali.
"""
from datetime import date

import pandas as pd
import pytest

import services.tag_analytics_service as tas
from services.tag_analytics_service import _compute_fornitori, _compute_kpi, _prepare_tag_dataframe


def _df(rows):
    return pd.DataFrame(rows)


# ─── Fix #4: unita' miste (KG + PZ) non si sommano ────────────────────────────

def test_kpi_unita_miste_usa_solo_unita_dominante():
    """Caso SCAMONE WAGYU reale: 252,97 PZ per 11.007 EUR + 9,74 KG per 92 EUR.

    Pre-fix: (11007.73+92.49)/(252.97+9.74) = 42.25 EUR su un'unita' inesistente.
    Post-fix: 11007.73/252.97 = 43.51 EUR/pz, il prezzo vero del prodotto.
    """
    df = _df([
        {"QuantitaNorm": 9.74, "UnitaNorm": "KG", "TotaleRigaNum": 92.49,
         "Fornitore": "A", "FileOrigine": "f1"},
        {"QuantitaNorm": 252.97, "UnitaNorm": "PZ", "TotaleRigaNum": 11007.73,
         "Fornitore": "B", "FileOrigine": "f2"},
    ])
    kpi = _compute_kpi(df)

    assert kpi["unita_dominante"] == "PZ"
    assert round(kpi["prezzo_medio_ponderato"], 2) == 43.51
    assert kpi["prezzo_label"].endswith("€/pz")
    # la spesa resta completa: si esclude dal PREZZO, non dal totale
    assert kpi["spesa_totale"] == 11100.22
    assert kpi["spesa_esclusa_mix"] == 92.49


def test_kpi_unita_omogenea_non_esclude_nulla():
    df = _df([
        {"QuantitaNorm": 10.0, "UnitaNorm": "KG", "TotaleRigaNum": 20.0,
         "Fornitore": "A", "FileOrigine": "f1"},
        {"QuantitaNorm": 5.0, "UnitaNorm": "KG", "TotaleRigaNum": 15.0,
         "Fornitore": "B", "FileOrigine": "f2"},
    ])
    kpi = _compute_kpi(df)

    assert kpi["unita_dominante"] is None
    assert kpi["spesa_esclusa_mix"] == 0.0
    assert round(kpi["prezzo_medio_ponderato"], 4) == round(35.0 / 15.0, 4)
    assert kpi["prezzo_label"].endswith("€/KG")


def test_kpi_dominante_scelta_per_spesa_non_per_quantita():
    """La dominante e' l'unita' che pesa di piu' in EUR, non in numero di unita'.

    Qui i PZ sono 1000 contro 10 KG, ma valgono 50 EUR contro 900: il prezzo
    che interessa al cliente e' quello al KG.
    """
    df = _df([
        {"QuantitaNorm": 10.0, "UnitaNorm": "KG", "TotaleRigaNum": 900.0,
         "Fornitore": "A", "FileOrigine": "f1"},
        {"QuantitaNorm": 1000.0, "UnitaNorm": "PZ", "TotaleRigaNum": 50.0,
         "Fornitore": "B", "FileOrigine": "f2"},
    ])
    kpi = _compute_kpi(df)

    assert kpi["unita_dominante"] == "KG"
    assert round(kpi["prezzo_medio_ponderato"], 2) == 90.0
    assert kpi["spesa_esclusa_mix"] == 50.0


# ─── Fix spesa: le note di credito vanno scalate ──────────────────────────────

def test_nota_credito_entra_nella_spesa_ma_non_nel_prezzo():
    """Misurato sul DB: -1.652 EUR di resi non venivano scalati dalla spesa tag."""
    df_src = _df([
        {"FileOrigine": "f1", "DataDocumento": "2026-03-01", "Fornitore": "A",
         "Descrizione": "Salmone", "Quantita": 10, "UnitaMisura": "KG",
         "PrezzoUnitario": 10.0, "TotaleRiga": 100.0},
        {"FileOrigine": "f2", "DataDocumento": "2026-03-05", "Fornitore": "A",
         "Descrizione": "Salmone", "Quantita": 1, "UnitaMisura": "KG",
         "PrezzoUnitario": -10.0, "TotaleRiga": -10.0},
    ])
    assoc = {"SALMONE": {"descrizione": "Salmone", "fattore_kg": None}}
    df_tag = _prepare_tag_dataframe(df_src, assoc)

    assert df_tag["PrezzoValido"].tolist() == [True, False]

    kpi = _compute_kpi(df_tag)
    assert kpi["spesa_totale"] == 90.0                    # 100 - 10, il reso e' scalato
    assert kpi["quantita_norm_totale"] == 10.0            # il reso non gonfia la quantita'
    assert round(kpi["prezzo_medio_ponderato"], 2) == 10.0  # prezzo vero, non 9.0


# ─── Fix #5: riferimento ponderato, non media di medie ────────────────────────

def test_prezzo_medio_tag_e_ponderato_sui_volumi():
    """Sbilanciamento misurato sul DB: fino a 93:1 fra fornitori dello stesso tag.

    Media di medie: (1.0 + 10.0)/2 = 5.5 -> il fornitore da 100 acquisti
    risultava "-82%" rispetto a un riferimento che non rappresenta la spesa.
    Ponderato: 1100/1100 = 1.0009..., vicino al prezzo realmente pagato.
    """
    df = _df([
        {"QuantitaNorm": 1000.0, "UnitaNorm": "KG", "TotaleRigaNum": 1000.0,
         "PrezzoUnitario": 1.0, "Quantita": 1000.0, "Fornitore": "GROSSO",
         "FileOrigine": "f1"},
        {"QuantitaNorm": 10.0, "UnitaNorm": "KG", "TotaleRigaNum": 100.0,
         "PrezzoUnitario": 10.0, "Quantita": 10.0, "Fornitore": "PICCOLO",
         "FileOrigine": "f2"},
    ])
    agg = _compute_fornitori(df)["aggregati"]

    # riferimento = spesa/quantita totali = 1100/1010 ~ 1.089, non 5.5
    assert round(agg["prezzo_medio_tag"], 3) == round(1100.0 / 1010.0, 3)
    assert agg["prezzo_medio_tag"] < 2.0

    per_forn = {f["fornitore"]: f for f in _compute_fornitori(df)["fornitori"]}
    # il fornitore che copre il 91% della spesa e' vicino al riferimento
    assert abs(per_forn["GROSSO"]["delta_pct"]) < 15
    # quello marginale e caro resta segnalato come molto sopra
    assert per_forn["PICCOLO"]["delta_pct"] > 500


def test_incidenza_spesa_zero_non_esplode():
    """Pre-fix: spesa_tot = max(somma, 0.0001) produceva incidenze astronomiche."""
    df = _df([
        {"QuantitaNorm": 1.0, "UnitaNorm": "KG", "TotaleRigaNum": 0.0,
         "PrezzoUnitario": 0.0, "Quantita": 1.0, "Fornitore": "A", "FileOrigine": "f1"},
    ])
    res = _compute_fornitori(df)
    for f in res["fornitori"]:
        assert f["incidenza_spesa"] == 0.0


# ─── Fix #4 esteso al trend: alimenta gli alert prezzi della Home ─────────────

def test_trend_con_unita_miste_usa_solo_la_dominante():
    """prezzo_medio_periodo guida price_impact_service (alert prezzi Home).

    Senza questa guardia il KPI sarebbe corretto e il trend no: due prezzi
    diversi per lo stesso tag nella stessa risposta, e l'alert calcolato su
    quello sbagliato.
    """
    from services.tag_analytics_service import _compute_trend

    df = _df([
        # giorno 1: 10 KG a 9 EUR/kg -> 90
        {"Data_DT": pd.Timestamp("2026-03-01"), "UnitaNorm": "KG", "QuantitaNorm": 10.0,
         "Quantita": 10.0, "PrezzoUnitario": 9.0, "TotaleRigaNum": 90.0},
        # giorno 2: 10 KG a 11 EUR/kg -> 110
        {"Data_DT": pd.Timestamp("2026-03-02"), "UnitaNorm": "KG", "QuantitaNorm": 10.0,
         "Quantita": 10.0, "PrezzoUnitario": 11.0, "TotaleRigaNum": 110.0},
        # stesso giorno 2: 500 PZ da pochi centesimi, spesa marginale
        {"Data_DT": pd.Timestamp("2026-03-02"), "UnitaNorm": "PZ", "QuantitaNorm": 500.0,
         "Quantita": 500.0, "PrezzoUnitario": 0.02, "TotaleRigaNum": 10.0},
    ])
    trend = _compute_trend(df)

    prezzi = sorted(p["prezzo"] for p in trend["punti"])
    # I PZ non devono schiacciare il prezzo al kg del giorno 2:
    # senza il fix sarebbe (110+10)/(10+500) = 0.235 invece di 11.0
    assert prezzi == [9.0, 11.0]
    assert trend["prezzo_medio_periodo"] == 10.0
