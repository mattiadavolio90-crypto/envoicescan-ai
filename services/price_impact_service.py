"""Alert prezzi per IMPATTO €/mese — motore live della Home (Step 4).

Logica decisa da Mattia (doc Punto 1 §2):
- Non conta la % di aumento da sola, conta l'IMPATTO = quanto pesa sui costi ×
  quanto e' aumentato. Salmone (pesa tanto, +5%) batte aglio (pesa niente, +100%).
- SOLO Food & Beverage (le spese generali sono canoni fissi: niente da fare).
- "Solo se conta davvero": soglia automatica = frazione della spesa food del
  periodo, cosi' si adatta alla taglia del ristorante. Zero numero fisso.
- Monitora ANCHE i custom TAG del cliente (li ha creati lui, ci tiene di piu').

Questo service e' PURO/orchestratore: riusa calcola_alert (gia' food&beverage +
impatto € pronti) e tag_analytics (gia' trend prezzi del tag). Nessuna dipendenza
da Streamlit. Il backend calcola, la Home racconta.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from config.logger_setup import get_logger
from config.constants import CATEGORIE_SPESE_GENERALI
from services.db_service import carica_e_prepara_dataframe, calcola_alert, get_custom_tags

logger = get_logger("price_impact")

# Finestra storica: serve abbastanza passato per avere >=2 acquisti per prodotto.
_FINESTRA_GIORNI = 90

# Soglia di aumento % minima per considerare un prodotto candidato. Bassa di
# proposito: il filtro VERO e' l'impatto €, non la percentuale.
_SOGLIA_PERC_CANDIDATO = 3.0

# Rilevanza automatica: un aumento conta solo se il suo impatto €/mese supera
# questa frazione della spesa food del periodo. Si adatta alla taglia.
_FRAZIONE_SPESA_FOOD = 0.005   # 0,5%

# Numero massimo di alert mostrati in Home ("solo i 2-3 col maggior impatto").
_MAX_ALERT = 3


def _spesa_food_periodo(df: pd.DataFrame) -> float:
    """Spesa totale Food & Beverage nel DataFrame (esclude spese generali)."""
    if df.empty or "Categoria" not in df.columns or "TotaleRiga" not in df.columns:
        return 0.0
    df_fb = df[~df["Categoria"].isin(CATEGORIE_SPESE_GENERALI)]
    tot = pd.to_numeric(df_fb["TotaleRiga"], errors="coerce").fillna(0.0).sum()
    return float(tot)


def _filtra_finestra(df: pd.DataFrame, giorni: int) -> pd.DataFrame:
    """Restringe il DataFrame agli ultimi `giorni` (per DataDocumento)."""
    if df.empty or "DataDocumento" not in df.columns:
        return df
    soglia = pd.Timestamp.now().normalize() - pd.Timedelta(days=giorni)
    out = df.copy()
    out["_data_dt"] = pd.to_datetime(out["DataDocumento"], errors="coerce")
    out = out[out["_data_dt"].notna() & (out["_data_dt"] >= soglia)]
    return out.drop(columns=["_data_dt"], errors="ignore")


def _alert_prodotti(df: pd.DataFrame, soglia_impatto: float) -> List[Dict[str, Any]]:
    """Aumenti su PRODOTTI food&beverage che superano la soglia d'impatto."""
    df_alert = calcola_alert(df, soglia_minima=_SOGLIA_PERC_CANDIDATO)
    if df_alert.empty:
        return []

    # Solo aumenti reali (non ribassi) con impatto stimato rilevante.
    df_alert = df_alert[
        (df_alert["Aumento_Perc"] > 0)
        & (pd.to_numeric(df_alert["Impatto_Stimato"], errors="coerce").fillna(0) >= soglia_impatto)
    ]
    if df_alert.empty:
        return []

    df_alert = df_alert.sort_values("Impatto_Stimato", ascending=False)
    out: List[Dict[str, Any]] = []
    for _, r in df_alert.iterrows():
        out.append({
            "tipo": "prodotto",
            "nome": str(r["Prodotto"]),
            "fornitore": str(r.get("Fornitore") or ""),
            "aumento_pct": round(float(r["Aumento_Perc"]), 1),
            "impatto_mese": round(float(r["Impatto_Stimato"]), 0),
        })
    return out


def _alert_tag(
    user_id: str,
    ristorante_id: str,
    df_periodo: pd.DataFrame,
    soglia_impatto: float,
) -> List[Dict[str, Any]]:
    """Aumenti sui custom TAG del cliente, stessa logica impatto €/mese.

    Usa il prezzo medio ponderato del tag (tag_analytics) e confronta la prima
    meta' del periodo con la seconda per stimare la variazione; l'impatto e'
    delta_prezzo × quantita' del tag nel periodo, riportato al mese.
    """
    try:
        tags = get_custom_tags(user_id, ristorante_id) or []
    except Exception as exc:
        logger.warning("price_impact: lettura tag fallita: %s", exc)
        return []
    if not tags:
        return []

    from services.tag_analytics_service import analizza_tag

    oggi = date.today()
    meta = oggi - timedelta(days=_FINESTRA_GIORNI // 2)
    inizio = oggi - timedelta(days=_FINESTRA_GIORNI)

    out: List[Dict[str, Any]] = []
    for tag in tags:
        tag_id = tag.get("id")
        nome = str(tag.get("nome") or tag.get("name") or "").strip()
        if tag_id is None or not nome:
            continue
        try:
            recente = analizza_tag(user_id, ristorante_id, int(tag_id), meta, oggi)
            precedente = analizza_tag(user_id, ristorante_id, int(tag_id), inizio, meta)
        except Exception as exc:
            logger.warning("price_impact: analisi tag %s fallita: %s", tag_id, exc)
            continue

        if recente.get("vuoto") or precedente.get("vuoto"):
            continue
        p_new = (recente.get("trend") or {}).get("prezzo_medio_periodo") or 0.0
        p_old = (precedente.get("trend") or {}).get("prezzo_medio_periodo") or 0.0
        if p_old <= 0 or p_new <= p_old:
            continue

        aumento_pct = (p_new - p_old) / p_old * 100.0
        # Impatto: delta prezzo × quantita' normalizzata acquistata di recente,
        # riportata al mese (la finestra recente e' ~mezza finestra = ~45gg).
        kpi = recente.get("kpi") or {}
        qta = float(kpi.get("quantita_norm_totale") or 0.0)
        if qta <= 0:
            continue
        delta_prezzo = p_new - p_old
        giorni_recenti = max(1, (_FINESTRA_GIORNI // 2))
        impatto_mese = delta_prezzo * qta * (30.0 / giorni_recenti)

        if impatto_mese < soglia_impatto:
            continue
        out.append({
            "tipo": "tag",
            "nome": nome,
            "fornitore": "",
            "aumento_pct": round(aumento_pct, 1),
            "impatto_mese": round(impatto_mese, 0),
        })
    return out


def calcola_alert_prezzi_impatto(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Dict[str, Any]:
    """Motore live alert prezzi per impatto €/mese (prodotti + tag).

    Returns un dict serializzabile:
        {
          "count": int,                 # quanti alert rilevanti
          "alerts": [ {tipo,nome,fornitore,aumento_pct,impatto_mese}, ... ],
          "top": {...} | None,          # l'alert col maggior impatto
        }
    """
    vuoto = {"count": 0, "alerts": [], "top": None}

    try:
        # force_refresh=False: la Home apre questo motore ad ogni caricamento; con
        # force_refresh=True si ricaricavano e rielaboravano TUTTE le righe ogni
        # volta (25s su clienti con migliaia di fatture -> timeout briefing). La
        # cache 120s e' adeguata: gli alert prezzi non richiedono freschezza al secondo.
        df = carica_e_prepara_dataframe(
            user_id, ristorante_id=ristorante_id,
            supabase_client=supabase_client, force_refresh=False,
        )
    except Exception as exc:
        logger.warning("price_impact: caricamento fatture fallito: %s", exc)
        return vuoto
    if df is None or df.empty:
        return vuoto

    df_periodo = _filtra_finestra(df, _FINESTRA_GIORNI)
    if df_periodo.empty:
        return vuoto

    spesa_food = _spesa_food_periodo(df_periodo)
    soglia_impatto = max(0.0, spesa_food * _FRAZIONE_SPESA_FOOD)

    prodotti = _alert_prodotti(df_periodo, soglia_impatto)
    tag = _alert_tag(user_id, ristorante_id, df_periodo, soglia_impatto)

    # Unisci e ordina per impatto €/mese decrescente; tieni i top.
    tutti = sorted(prodotti + tag, key=lambda a: a["impatto_mese"], reverse=True)
    tutti = tutti[:_MAX_ALERT]

    return {
        "count": len(tutti),
        "alerts": tutti,
        "top": tutti[0] if tutti else None,
    }
