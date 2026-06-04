"""Analisi per custom tag — funzioni pure riutilizzabili (Streamlit + Next.js).

Porta la logica di analisi che prima viveva dentro la pagina Streamlit
`pages/4_analisi_personalizzata.py` (KPI, normalizzazione quantità, trend
prezzi, confronto fornitori, associazioni orfane) in un service riutilizzabile
dal FastAPI worker. Nessuna dipendenza da Streamlit o plotly: solo pandas.

Convenzione di output: il service ritorna SOLO numeri. I commenti KPI
(testo/emoji/colore) restano lato frontend — "il backend calcola, la UI racconta".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from config.constants import ORPHAN_CHECK_DAYS
from services.db_service import (
    _normalize_custom_tag_key,
    carica_e_prepara_dataframe,
    get_custom_tag_prodotti,
)


def _conversione_quantita_normalizzata(
    row: pd.Series, fattore_kg: Optional[float]
) -> tuple[Optional[float], Optional[str]]:
    quantita = row.get("Quantita")
    unita_misura = str(row.get("UnitaMisura") or "").strip().upper()

    if pd.isna(quantita):
        return None, None

    try:
        quantita = float(quantita)
    except (TypeError, ValueError):
        return None, None

    if fattore_kg:
        return quantita * float(fattore_kg), "normalizzata"

    if unita_misura == "KG":
        return quantita, "KG"
    if unita_misura == "GR":
        return quantita / 1000, "KG"
    if unita_misura == "LT":
        return quantita, "LT"
    if unita_misura == "ML":
        return quantita / 1000, "LT"
    if unita_misura == "CL":
        return quantita / 100, "LT"

    # Fallback per unità a pezzo/confezione (PZ, NR, CF, BT, SC, ecc.)
    if quantita > 0:
        return quantita, "PZ"

    return None, None


def _build_associazioni_map(associazioni_tag: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        assoc["descrizione_key"]: {
            "descrizione": assoc.get("descrizione"),
            "fattore_kg": assoc.get("fattore_kg"),
        }
        for assoc in associazioni_tag
        if assoc.get("descrizione_key")
    }


def _prepare_tag_dataframe(
    df_source: pd.DataFrame, associazioni_map: Dict[str, Dict[str, Any]]
) -> pd.DataFrame:
    if df_source.empty or not associazioni_map:
        return pd.DataFrame()

    df_tag = df_source.copy()
    df_tag["Data_DT"] = pd.to_datetime(df_tag["DataDocumento"], errors="coerce")
    df_tag["DescrizioneKey"] = df_tag["Descrizione"].apply(_normalize_custom_tag_key)
    df_tag = df_tag[df_tag["DescrizioneKey"].isin(set(associazioni_map.keys()))].copy()

    if df_tag.empty:
        return df_tag

    df_tag["FattoreKg"] = df_tag["DescrizioneKey"].map(
        lambda key: associazioni_map.get(key, {}).get("fattore_kg")
    )
    conversioni = df_tag.apply(
        lambda row: _conversione_quantita_normalizzata(row, row.get("FattoreKg")),
        axis=1,
        result_type="expand",
    )
    df_tag["QuantitaNorm"] = conversioni[0]
    df_tag["UnitaNorm"] = conversioni[1]
    df_tag["TotaleRigaNum"] = pd.to_numeric(df_tag["TotaleRiga"], errors="coerce").fillna(0.0)
    df_tag["PrezzoUnitarioNum"] = pd.to_numeric(df_tag["PrezzoUnitario"], errors="coerce")
    # Escludi righe con prezzo non positivo (sconti, rettifiche negative)
    df_tag = df_tag[df_tag["PrezzoUnitarioNum"] > 0].copy()
    return df_tag


def _filter_periodo(df_source: pd.DataFrame, data_inizio, data_fine) -> pd.DataFrame:
    if df_source.empty:
        return df_source
    mask = (
        (df_source["Data_DT"].dt.date >= data_inizio)
        & (df_source["Data_DT"].dt.date <= data_fine)
    )
    return df_source[mask].copy()


def _compute_kpi(df_tag_periodo: pd.DataFrame) -> Dict[str, Any]:
    df_convertibili = df_tag_periodo[df_tag_periodo["QuantitaNorm"].notna()].copy()
    spesa_totale = float(df_tag_periodo["TotaleRigaNum"].sum())
    quantita_norm_totale = (
        float(df_convertibili["QuantitaNorm"].sum()) if not df_convertibili.empty else 0.0
    )
    prezzo_medio_ponderato = (
        float(df_convertibili["TotaleRigaNum"].sum()) / quantita_norm_totale
        if quantita_norm_totale > 0
        else None
    )
    num_fornitori = int(df_tag_periodo["Fornitore"].nunique())
    num_fatture = int(df_tag_periodo["FileOrigine"].nunique())

    unita_norm_set = set(df_convertibili["UnitaNorm"].dropna().unique().tolist())
    if "KG" in unita_norm_set and "LT" not in unita_norm_set and "PZ" not in unita_norm_set:
        quantita_label = "⚖️ Quantità Totale KG"
        prezzo_label = "💶 Prezzo Medio €/KG"
    elif "LT" in unita_norm_set and "KG" not in unita_norm_set and "PZ" not in unita_norm_set:
        quantita_label = "🧴 Quantità Totale LT"
        prezzo_label = "💶 Prezzo Medio €/LT"
    elif unita_norm_set == {"PZ"} or (
        "PZ" in unita_norm_set and "KG" not in unita_norm_set and "LT" not in unita_norm_set
    ):
        quantita_label = "📦 Quantità Totale (pz)"
        prezzo_label = "💶 Prezzo Medio €/pz"
    else:
        quantita_label = "⚖️ Quantità Normalizzata"
        prezzo_label = "💶 Prezzo Medio €/unità norm."

    return {
        "spesa_totale": round(spesa_totale, 2),
        "quantita_norm_totale": round(quantita_norm_totale, 3),
        "prezzo_medio_ponderato": round(prezzo_medio_ponderato, 4)
        if prezzo_medio_ponderato is not None
        else None,
        "num_fornitori": num_fornitori,
        "num_fatture": num_fatture,
        "quantita_label": quantita_label,
        "prezzo_label": prezzo_label,
    }


def _compute_trend(df_tag_periodo: pd.DataFrame) -> Dict[str, Any]:
    df_trend = df_tag_periodo.copy()
    df_trend["Data_DT"] = pd.to_datetime(df_trend["Data_DT"], errors="coerce")
    df_trend["PrezzoUnitario"] = pd.to_numeric(df_trend["PrezzoUnitario"], errors="coerce")
    df_trend["TotaleRigaNum"] = pd.to_numeric(df_trend.get("TotaleRigaNum"), errors="coerce")
    df_trend["QuantitaNorm"] = pd.to_numeric(df_trend.get("QuantitaNorm"), errors="coerce")
    df_trend["Quantita"] = pd.to_numeric(df_trend.get("Quantita"), errors="coerce")
    df_trend = df_trend[df_trend["Data_DT"].notna() & df_trend["PrezzoUnitario"].notna()].copy()

    if df_trend.empty:
        return {"punti": [], "prezzo_medio_periodo": 0.0}

    usa_quantita_norm = (
        df_trend["QuantitaNorm"].notna().any()
        and float(df_trend["QuantitaNorm"].fillna(0).sum()) > 0
    )
    qty_col = "QuantitaNorm" if usa_quantita_norm else "Quantita"

    df_linea = df_trend.groupby("Data_DT", as_index=False).agg(
        TotaleSpesa=("TotaleRigaNum", "sum"),
        QuantitaTotale=(qty_col, "sum"),
    )
    df_linea["PrezzoTag"] = df_linea.apply(
        lambda r: (r["TotaleSpesa"] / r["QuantitaTotale"])
        if pd.notna(r["TotaleSpesa"])
        and pd.notna(r["QuantitaTotale"])
        and float(r["QuantitaTotale"]) > 0
        else None,
        axis=1,
    )
    df_linea = df_linea[df_linea["PrezzoTag"].notna()].sort_values("Data_DT")

    if df_linea.empty:
        return {"punti": [], "prezzo_medio_periodo": 0.0}

    prezzo_medio_periodo = float(df_linea["PrezzoTag"].mean())
    punti = []
    for _, r in df_linea.iterrows():
        prezzo = float(r["PrezzoTag"])
        var_perc = (
            ((prezzo - prezzo_medio_periodo) / prezzo_medio_periodo) * 100
            if prezzo_medio_periodo > 0
            else 0.0
        )
        data_dt = r["Data_DT"]
        punti.append(
            {
                "data": data_dt.date().isoformat() if pd.notna(data_dt) else None,
                "prezzo": round(prezzo, 4),
                "var_perc": round(var_perc, 2),
            }
        )

    return {"punti": punti, "prezzo_medio_periodo": round(prezzo_medio_periodo, 4)}


def _compute_fornitori(df_tag_periodo: pd.DataFrame) -> Dict[str, Any]:
    df_forn = df_tag_periodo.copy()
    df_forn["Fornitore"] = (
        df_forn["Fornitore"].fillna("Fornitore sconosciuto").astype(str).str.strip()
    )
    df_forn["TotaleRigaNum"] = pd.to_numeric(df_forn["TotaleRigaNum"], errors="coerce")
    df_forn["PrezzoUnitario"] = pd.to_numeric(df_forn["PrezzoUnitario"], errors="coerce")
    df_forn["Quantita"] = pd.to_numeric(df_forn.get("Quantita"), errors="coerce")
    df_forn["QuantitaNorm"] = pd.to_numeric(df_forn.get("QuantitaNorm"), errors="coerce")

    usa_quantita_norm = (
        df_forn["QuantitaNorm"].notna().any()
        and float(df_forn["QuantitaNorm"].fillna(0).sum()) > 0
    )

    if usa_quantita_norm:
        df_fornitori = df_forn.groupby("Fornitore", as_index=False).agg(
            SpesaTotale=("TotaleRigaNum", "sum"),
            QuantitaTotale=("QuantitaNorm", "sum"),
            NumAcquisti=("FileOrigine", "count"),
        )
        df_fornitori["PrezzoMedio"] = df_fornitori.apply(
            lambda row: row["SpesaTotale"] / row["QuantitaTotale"]
            if row["QuantitaTotale"] and row["QuantitaTotale"] > 0
            else None,
            axis=1,
        )
        quantita_label = "Q.tà norm."
    else:
        df_fornitori = df_forn.groupby("Fornitore", as_index=False).agg(
            SpesaTotale=("TotaleRigaNum", "sum"),
            QuantitaTotale=("Quantita", "sum"),
            NumAcquisti=("FileOrigine", "count"),
            PrezzoMedio=("PrezzoUnitario", "mean"),
        )
        quantita_label = "Q.tà"

    df_fornitori = df_fornitori[df_fornitori["SpesaTotale"].notna()].copy()
    if df_fornitori.empty:
        return {"fornitori": [], "aggregati": None}

    spesa_tot = max(float(df_fornitori["SpesaTotale"].sum()), 0.0001)
    df_fornitori["IncidenzaSpesa"] = df_fornitori["SpesaTotale"] / spesa_tot * 100

    prezzo_medio_tag = (
        float(df_fornitori["PrezzoMedio"].dropna().mean())
        if not df_fornitori["PrezzoMedio"].dropna().empty
        else None
    )
    if prezzo_medio_tag:
        df_fornitori["DeltaPct"] = ((df_fornitori["PrezzoMedio"] / prezzo_medio_tag) - 1) * 100
    else:
        df_fornitori["DeltaPct"] = 0.0

    df_fornitori = df_fornitori.sort_values(
        ["PrezzoMedio", "SpesaTotale"], ascending=[True, False]
    ).reset_index(drop=True)

    best = df_fornitori.iloc[0]
    worst = df_fornitori.iloc[-1]
    best_pm = best["PrezzoMedio"]
    worst_pm = worst["PrezzoMedio"]
    gap_pct = (
        ((float(worst_pm) / float(best_pm)) - 1) * 100
        if pd.notna(best_pm) and pd.notna(worst_pm) and float(best_pm) > 0
        else 0.0
    )

    fornitori = []
    for _, r in df_fornitori.iterrows():
        fornitori.append(
            {
                "fornitore": str(r["Fornitore"]),
                "spesa_totale": round(float(r["SpesaTotale"]), 2),
                "quantita_totale": round(float(r["QuantitaTotale"]), 2)
                if pd.notna(r["QuantitaTotale"])
                else 0.0,
                "num_acquisti": int(r["NumAcquisti"]),
                "prezzo_medio": round(float(r["PrezzoMedio"]), 4)
                if pd.notna(r["PrezzoMedio"])
                else None,
                "delta_pct": round(float(r["DeltaPct"]), 2) if pd.notna(r["DeltaPct"]) else 0.0,
                "incidenza_spesa": round(float(r["IncidenzaSpesa"]), 2),
            }
        )

    aggregati = {
        "num_fornitori": len(df_fornitori),
        "concentrazione_top": round(float(df_fornitori["IncidenzaSpesa"].max()), 2),
        "gap_pct": round(float(gap_pct), 2),
        "prezzo_medio_tag": round(prezzo_medio_tag, 4) if prezzo_medio_tag else None,
        "best_fornitore": str(best["Fornitore"]),
        "best_delta_pct": round(float(best["DeltaPct"]), 2) if pd.notna(best["DeltaPct"]) else 0.0,
        "worst_fornitore": str(worst["Fornitore"]),
        "worst_delta_pct": round(float(worst["DeltaPct"]), 2)
        if pd.notna(worst["DeltaPct"])
        else 0.0,
        "quantita_label": quantita_label,
    }

    return {"fornitori": fornitori, "aggregati": aggregati}


def analizza_tag(
    user_id: str,
    ristorante_id: str,
    tag_id: int,
    data_da,
    data_a,
    df_precaricato: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Analisi completa di un tag nel periodo richiesto.

    Args:
        user_id, ristorante_id: scope multi-tenant.
        tag_id: id del custom tag.
        data_da, data_a: ``datetime.date`` (estremi inclusi).
        df_precaricato: DataFrame fatture gia' caricato dal chiamante. Quando
            piu' chiamate condividono lo stesso scope (es. alert prezzi che
            analizza tutti i tag), il chiamante carica UNA volta e lo passa qui,
            evitando una ricarica completa da Supabase per ogni invocazione.

    Returns:
        dict con chiavi ``kpi``, ``trend``, ``fornitori``, ``vuoto``.
        ``vuoto=True`` quando non ci sono righe nel periodo.
    """
    empty_result = {"kpi": None, "trend": {"punti": [], "prezzo_medio_periodo": 0.0},
                    "fornitori": {"fornitori": [], "aggregati": None}, "vuoto": True}

    associazioni = get_custom_tag_prodotti(int(tag_id), user_id)
    if not associazioni:
        return empty_result

    associazioni_map = _build_associazioni_map(associazioni)
    # force_refresh=False: la cache 120s e' adeguata (l'analisi tag non richiede
    # freschezza al secondo) ed evita di ricaricare TUTTE le righe ad ogni chiamata.
    df_all = (
        df_precaricato
        if df_precaricato is not None
        else carica_e_prepara_dataframe(user_id, ristorante_id=ristorante_id, force_refresh=False)
    )
    if df_all is None or df_all.empty:
        return empty_result

    df_tag = _prepare_tag_dataframe(df_all, associazioni_map)
    if df_tag.empty:
        return empty_result

    df_tag_periodo = _filter_periodo(df_tag, data_da, data_a)
    if df_tag_periodo.empty:
        return empty_result

    return {
        "kpi": _compute_kpi(df_tag_periodo),
        "trend": _compute_trend(df_tag_periodo),
        "fornitori": _compute_fornitori(df_tag_periodo),
        "vuoto": False,
    }


def compute_orfani(user_id: str, ristorante_id: str, tag_id: int) -> List[Dict[str, Any]]:
    """Associazioni del tag senza acquisti negli ultimi ``ORPHAN_CHECK_DAYS`` giorni."""
    associazioni = get_custom_tag_prodotti(int(tag_id), user_id)
    if not associazioni:
        return []

    df_all = carica_e_prepara_dataframe(user_id, ristorante_id=ristorante_id, force_refresh=False)
    if df_all is None or df_all.empty:
        return []

    soglia = pd.Timestamp.now().normalize() - pd.Timedelta(days=ORPHAN_CHECK_DAYS)
    df_recenti = df_all.copy()
    df_recenti["Data_DT"] = pd.to_datetime(df_recenti["DataDocumento"], errors="coerce")
    df_recenti = df_recenti[df_recenti["Data_DT"] >= soglia].copy()
    df_recenti["DescrizioneKey"] = df_recenti["Descrizione"].apply(_normalize_custom_tag_key)

    chiavi_recenti = set(df_recenti["DescrizioneKey"].dropna().unique().tolist())
    orfani = []
    for assoc in associazioni:
        descrizione_key = assoc.get("descrizione_key")
        if descrizione_key and descrizione_key not in chiavi_recenti:
            orfani.append(assoc)
    return orfani
