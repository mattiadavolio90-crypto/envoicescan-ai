"""Unit test analytics tag (funzioni pure + analizza_tag con monkeypatch)."""

from datetime import date

import pandas as pd

import services.tag_analytics_service as tas
from services.tag_analytics_service import (
    _build_associazioni_map,
    _compute_fornitori,
    _compute_kpi,
    _compute_trend,
    _prepare_tag_dataframe,
    analizza_tag,
)


def _df_fatture() -> pd.DataFrame:
    """DataFrame fatture sintetico in formato carica_e_prepara_dataframe."""
    return pd.DataFrame(
        [
            # POMODORO PELATO — Fornitore A, KG
            {"FileOrigine": "f1", "DataDocumento": "2026-03-01", "Fornitore": "FORN A",
             "Descrizione": "Pomodoro Pelato", "Quantita": 10, "UnitaMisura": "KG",
             "PrezzoUnitario": 2.0, "TotaleRiga": 20.0, "Categoria": "ALIMENTARI"},
            # POMODORO PELATO — Fornitore B, KG (più caro)
            {"FileOrigine": "f2", "DataDocumento": "2026-03-15", "Fornitore": "FORN B",
             "Descrizione": "Pomodoro Pelato", "Quantita": 5, "UnitaMisura": "KG",
             "PrezzoUnitario": 3.0, "TotaleRiga": 15.0, "Categoria": "ALIMENTARI"},
            # Riga fuori tag — non deve entrare
            {"FileOrigine": "f3", "DataDocumento": "2026-03-10", "Fornitore": "FORN A",
             "Descrizione": "Mozzarella", "Quantita": 2, "UnitaMisura": "KG",
             "PrezzoUnitario": 8.0, "TotaleRiga": 16.0, "Categoria": "ALIMENTARI"},
            # Riga con prezzo non positivo (sconto) — deve essere esclusa
            {"FileOrigine": "f4", "DataDocumento": "2026-03-20", "Fornitore": "FORN A",
             "Descrizione": "Pomodoro Pelato", "Quantita": 1, "UnitaMisura": "KG",
             "PrezzoUnitario": -1.0, "TotaleRiga": -1.0, "Categoria": "ALIMENTARI"},
        ]
    )


def _associazioni():
    return [
        {"id": 1, "descrizione": "Pomodoro Pelato", "descrizione_key": "POMODORO PELATO", "fattore_kg": None},
    ]


def test_prepare_tag_dataframe_filters_by_assoc_and_positive_price():
    df = _df_fatture()
    assoc_map = _build_associazioni_map(_associazioni())
    out = _prepare_tag_dataframe(df, assoc_map)

    # Le 3 righe POMODORO PELATO (esclusa solo Mozzarella, fuori tag): lo sconto
    # NON viene piu' scartato, viene marcato PrezzoValido=False cosi' entra nella
    # spesa (i resi vanno scalati) ma resta fuori dai calcoli di prezzo.
    assert len(out) == 3
    assert set(out["Fornitore"]) == {"FORN A", "FORN B"}
    assert out["PrezzoValido"].tolist() == [True, True, False]
    assert (out.loc[out["PrezzoValido"], "PrezzoUnitarioNum"] > 0).all()


def test_compute_kpi_kg_labels_and_weighted_price():
    df = _df_fatture()
    assoc_map = _build_associazioni_map(_associazioni())
    df_tag = _prepare_tag_dataframe(df, assoc_map)
    kpi = _compute_kpi(df_tag)

    assert kpi["spesa_totale"] == 34.0  # 20 + 15 - 1 (il reso viene scalato)
    assert kpi["quantita_norm_totale"] == 15.0  # 10 + 5 KG, il reso non conta
    # prezzo medio ponderato = 35 / 15: calcolato sulle sole righe a prezzo valido
    assert round(kpi["prezzo_medio_ponderato"], 4) == round(35.0 / 15.0, 4)
    # unita' omogenea (solo KG): nessuna esclusione per mix
    assert kpi["unita_dominante"] is None
    assert kpi["spesa_esclusa_mix"] == 0.0
    assert kpi["num_fornitori"] == 2
    # 3 documenti: f1, f2 e la nota di credito f4 (che resta una fattura reale)
    assert kpi["num_fatture"] == 3
    assert "KG" in kpi["quantita_label"]


def test_compute_trend_points_and_variance():
    df = _df_fatture()
    assoc_map = _build_associazioni_map(_associazioni())
    df_tag = _prepare_tag_dataframe(df, assoc_map)
    trend = _compute_trend(df_tag)

    # Due date distinte → due punti
    assert len(trend["punti"]) == 2
    prezzi = sorted(p["prezzo"] for p in trend["punti"])
    assert prezzi == [2.0, 3.0]
    assert trend["prezzo_medio_periodo"] == 2.5
    # var % coerente col segno
    for p in trend["punti"]:
        if p["prezzo"] == 2.0:
            assert p["var_perc"] < 0
        if p["prezzo"] == 3.0:
            assert p["var_perc"] > 0


def test_compute_fornitori_ranking_and_aggregati():
    df = _df_fatture()
    assoc_map = _build_associazioni_map(_associazioni())
    df_tag = _prepare_tag_dataframe(df, assoc_map)
    res = _compute_fornitori(df_tag)

    assert len(res["fornitori"]) == 2
    # ordinati per prezzo medio crescente → FORN A (2.0) prima di FORN B (3.0)
    assert res["fornitori"][0]["fornitore"] == "FORN A"
    agg = res["aggregati"]
    assert agg["num_fornitori"] == 2
    assert agg["best_fornitore"] == "FORN A"
    assert agg["worst_fornitore"] == "FORN B"
    # gap = (3/2 - 1)*100 = 50%
    assert round(agg["gap_pct"], 1) == 50.0


def test_analizza_tag_end_to_end(monkeypatch):
    monkeypatch.setattr(tas, "get_custom_tag_prodotti", lambda tag_id, user_id: _associazioni())
    monkeypatch.setattr(
        tas, "carica_e_prepara_dataframe",
        lambda user_id, ristorante_id=None, force_refresh=False: _df_fatture(),
    )

    result = analizza_tag("u1", "r1", 1, date(2026, 1, 1), date(2026, 12, 31))

    assert result["vuoto"] is False
    assert result["kpi"]["spesa_totale"] == 34.0  # include il reso da -1.00
    assert len(result["trend"]["punti"]) == 2
    assert len(result["fornitori"]["fornitori"]) == 2


def test_analizza_tag_df_precaricato_non_ricarica(monkeypatch):
    """Con df_precaricato, analizza_tag NON deve chiamare carica_e_prepara_dataframe.

    Blinda il fix performance del briefing Home: l'alert prezzi carica il df UNA
    volta e lo passa a tutte le 2×N analisi tag, invece di ricaricare ogni volta.
    """
    monkeypatch.setattr(tas, "get_custom_tag_prodotti", lambda tag_id, user_id: _associazioni())

    chiamate = {"n": 0}

    def _spy(*args, **kwargs):
        chiamate["n"] += 1
        return _df_fatture()

    monkeypatch.setattr(tas, "carica_e_prepara_dataframe", _spy)

    result = analizza_tag(
        "u1", "r1", 1, date(2026, 1, 1), date(2026, 12, 31),
        df_precaricato=_df_fatture(),
    )

    assert result["vuoto"] is False
    assert chiamate["n"] == 0


def test_analizza_tag_empty_when_no_assoc(monkeypatch):
    monkeypatch.setattr(tas, "get_custom_tag_prodotti", lambda tag_id, user_id: [])
    result = analizza_tag("u1", "r1", 99, date(2026, 1, 1), date(2026, 12, 31))
    assert result["vuoto"] is True
    assert result["kpi"] is None


def test_analizza_tag_empty_when_period_excludes_all(monkeypatch):
    monkeypatch.setattr(tas, "get_custom_tag_prodotti", lambda tag_id, user_id: _associazioni())
    monkeypatch.setattr(
        tas, "carica_e_prepara_dataframe",
        lambda user_id, ristorante_id=None, force_refresh=False: _df_fatture(),
    )
    # Periodo che non contiene nessuna riga (tutte a marzo 2026)
    result = analizza_tag("u1", "r1", 1, date(2025, 1, 1), date(2025, 12, 31))
    assert result["vuoto"] is True
