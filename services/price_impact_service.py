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

# Quota di spesa food coperta dai prodotti "che pesano" (Pareto). Un prodotto e'
# eleggibile agli alert solo se rientra nella fascia che cumula questa quota
# della spesa: adattivo alla frammentazione del cliente (vedi _prodotti_pareto).
_PARETO_QUOTA = 0.80

# Soglia % di default se il cliente non ne ha salvata una in pagina Prezzi
# (allineata a _PRICE_ALERT_DEFAULT del router prezzi).
_SOGLIA_PERC_DEFAULT = 5.0

# Numero massimo di alert mostrati in Home ("solo i 2-3 col maggior impatto").
_MAX_ALERT = 3


def _filtra_finestra(df: pd.DataFrame, giorni: int) -> pd.DataFrame:
    """Restringe il DataFrame agli ultimi `giorni` (per DataDocumento)."""
    if df.empty or "DataDocumento" not in df.columns:
        return df
    soglia = pd.Timestamp.now().normalize() - pd.Timedelta(days=giorni)
    out = df.copy()
    out["_data_dt"] = pd.to_datetime(out["DataDocumento"], errors="coerce")
    out = out[out["_data_dt"].notna() & (out["_data_dt"] >= soglia)]
    return out.drop(columns=["_data_dt"], errors="ignore")


def _pareto_key(nome: str) -> str:
    """Chiave normalizzata per confrontare prodotti tra Pareto e calcola_alert.

    `calcola_alert` espone il prodotto come `(Descrizione.mode + nota)[:50]`
    (vedi db_service): puo' avere case originale, suffisso ` ⚠️ >6m` ed essere
    troncato a 50 char. Il df grezzo ha invece la `Descrizione` piena. Per far
    combaciare i due lati confronto su una chiave comune: upper+strip, suffisso
    rimosso, troncata agli stessi 50 char. Cosi' il filtro peso non fallisce in
    modo silenzioso su nomi lunghi o stagionali.
    """
    s = str(nome).strip().upper()
    if s.endswith("⚠️ >6M"):
        s = s[: -len("⚠️ >6M")].strip()
    return s[:50]


def _prodotti_pareto(df: pd.DataFrame, quota: float = _PARETO_QUOTA) -> set:
    """Prodotti che cumulano la `quota` (es. 80%) della spesa food del periodo.

    Pareto adattivo alla frammentazione del cliente: invece di una soglia di
    peso fissa (es. "almeno il 3%", che taglia tutto sui clienti con centinaia
    di prodotti e niente su quelli con pochi), tiene eleggibili SOLO i prodotti
    che insieme fanno la quota dominante della spesa. Su un cliente concentrato
    sono pochi pilastri; su uno frammentato sono di piu'. La soglia "peso" si
    adatta da sola. Cosi' i marginali (limoni, accessori) restano fuori dagli
    alert prezzi a prescindere da quanto rincarino in percentuale.

    Raggruppa per `Descrizione` (la colonna che il df grezzo ha davvero: la
    `Prodotto` nasce solo dentro calcola_alert). Restituisce chiavi normalizzate
    via `_pareto_key`, le stesse usate poi da `_alert_prodotti` per il match.
    """
    if df.empty or "Descrizione" not in df.columns or "TotaleRiga" not in df.columns:
        return set()
    df_fb = df[~df["Categoria"].isin(CATEGORIE_SPESE_GENERALI)] if "Categoria" in df.columns else df
    spesa = (
        df_fb.assign(
            _t=pd.to_numeric(df_fb["TotaleRiga"], errors="coerce").fillna(0.0),
            _k=df_fb["Descrizione"].map(_pareto_key),
        )
        .groupby("_k")["_t"].sum()
        .sort_values(ascending=False)
    )
    spesa = spesa[spesa > 0]
    totale = float(spesa.sum())
    if totale <= 0:
        return set()
    cumulata = spesa.cumsum() / totale
    # Tieni tutti i prodotti fino a coprire la quota (incluso quello che la
    # supera, cosi' la fascia copre almeno `quota`).
    eleggibili = cumulata[cumulata.shift(fill_value=0.0) < quota]
    return set(str(p) for p in eleggibili.index)


def _pref_match_key(descrizione: str, fornitore: str) -> str:
    """Chiave per confrontare un prodotto con i preferiti del ristorante.

    I preferiti (tabella prezzi_preferiti) salvano descrizione UPPER+TRIM senza
    suffissi UI e fornitore UPPER+TRIM. Qui il `Prodotto` di calcola_alert e' gia'
    troncato/normalizzato come _pareto_key (upper, suffisso rimosso, [:50]):
    applico lo stesso [:50] sul lato preferito cosi' i due lati combaciano anche
    su nomi lunghi. Include il fornitore: la stella e' per coppia (prodotto, forn).
    """
    d = _pareto_key(descrizione)  # upper+strip, suffisso rimosso, [:50]
    f = str(fornitore).strip().upper()
    return f"{d}|{f}"


def _alert_prodotti(
    df: pd.DataFrame,
    soglia_perc_cliente: float,
    prodotti_pareto: set,
    preferiti_keys: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Aumenti su PRODOTTI food&beverage rilevanti per il cliente.

    Un prodotto entra solo se: 1) e' aumentato di almeno la soglia % che il
    cliente ha impostato in pagina Prezzi (price_alert_threshold), 2) ha impatto
    €/mese positivo, 3) supera il filtro di rilevanza.

    Filtro di rilevanza (punto 3):
    - Default (preferiti_keys=None): fascia Pareto della spesa food — i prodotti
      che pesano davvero. I marginali tipo limoni restano fuori anche se rincarano.
    - Modalita' "solo preferiti" (preferiti_keys passato): SOLO i prodotti che il
      cliente ha messo a preferito (stella in pagina Prezzi). Se la lista e' vuota,
      nessun prodotto entra (restano solo i tag, gestiti altrove). Decisione Mattia.
    """
    df_alert = calcola_alert(df, soglia_minima=_SOGLIA_PERC_CANDIDATO)
    if df_alert.empty:
        return []

    impatto = pd.to_numeric(df_alert["Impatto_Stimato"], errors="coerce").fillna(0)
    base = (df_alert["Aumento_Perc"] >= soglia_perc_cliente) & (impatto > 0)

    if preferiti_keys is not None:
        # Modalita' solo preferiti: filtra sulla coppia (prodotto, fornitore).
        match = df_alert.apply(
            lambda r: _pref_match_key(r["Prodotto"], r.get("Fornitore") or "") in preferiti_keys,
            axis=1,
        )
        df_alert = df_alert[base & match]
    else:
        chiave_pareto = df_alert["Prodotto"].map(_pareto_key)
        df_alert = df_alert[base & chiave_pareto.isin(prodotti_pareto)]
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
    df_completo: pd.DataFrame,
    soglia_perc_cliente: float,
) -> List[Dict[str, Any]]:
    """Aumenti sui custom TAG del cliente — il SUO focus, quindi prioritari.

    A differenza dei prodotti, i tag NON hanno filtro di peso (Pareto): se il
    cliente ha creato un tag, ci tiene per definizione, quindi basta che superi
    la sua soglia % (price_alert_threshold) e abbia un rincaro reale. Decisione
    Mattia: "i tag dovrebbero sempre rientrare, e' un'informazione su cui ha
    focus la sua attenzione".

    Usa il prezzo medio ponderato del tag (tag_analytics) e confronta la prima
    meta' del periodo con la seconda per stimare la variazione; l'impatto e'
    delta_prezzo × quantita' del tag nel periodo, riportato al mese.

    ``df_completo`` (NON filtrato per periodo) viene passato a ``analizza_tag``
    che filtra lui per le sue finestre: cosi' il DataFrame si carica UNA volta
    sola per tutti i tag, invece di una ricarica completa da Supabase per ognuna
    delle 2×N chiamate (era il collo di bottiglia ~17s del briefing Home).
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

    from services.db_service import get_custom_tag_prodotti_bulk

    # Tutte le associazioni dei tag in UNA query (IN su tag_id), invece di una
    # get_custom_tag_prodotti per tag × due finestre: su clienti con piu' tag era
    # il collo di bottiglia dell'alert prezzi (N query sequenziali da ~0.5s).
    tag_ids = [int(t["id"]) for t in tags if t.get("id") is not None]
    assoc_per_tag = get_custom_tag_prodotti_bulk(tag_ids, user_id)

    out: List[Dict[str, Any]] = []
    for tag in tags:
        tag_id = tag.get("id")
        nome = str(tag.get("nome") or tag.get("name") or "").strip()
        if tag_id is None or not nome:
            continue
        assoc_tag = assoc_per_tag.get(int(tag_id)) or []
        if not assoc_tag:
            continue
        try:
            recente = analizza_tag(user_id, ristorante_id, int(tag_id), meta, oggi, df_precaricato=df_completo, associazioni_precaricate=assoc_tag)
            precedente = analizza_tag(user_id, ristorante_id, int(tag_id), inizio, meta, df_precaricato=df_completo, associazioni_precaricate=assoc_tag)
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
        # Filtro UNICO sui tag: la soglia % che il cliente ha scelto. Niente peso
        # Pareto (il tag e' gia' il suo focus). Sotto la sua soglia non e' un
        # rincaro che gli interessa, sopra si'.
        if aumento_pct < soglia_perc_cliente:
            continue
        # Impatto: delta prezzo × quantita' normalizzata acquistata di recente,
        # riportata al mese (la finestra recente e' ~mezza finestra = ~45gg).
        kpi = recente.get("kpi") or {}
        qta = float(kpi.get("quantita_norm_totale") or 0.0)
        if qta <= 0:
            continue
        delta_prezzo = p_new - p_old
        giorni_recenti = max(1, (_FINESTRA_GIORNI // 2))
        impatto_mese = delta_prezzo * qta * (30.0 / giorni_recenti)
        out.append({
            "tipo": "tag",
            "nome": nome,
            "fornitore": "",
            "aumento_pct": round(aumento_pct, 1),
            "impatto_mese": round(impatto_mese, 0),
        })
    return out


def _leggi_soglia_perc_cliente(user_id: str, supabase_client=None) -> float:
    """Soglia % alert prezzi salvata dal cliente (users.price_alert_threshold).

    E' la stessa che imposta in pagina Prezzi. Clamp [0,50] come il router.
    Fallback a _SOGLIA_PERC_DEFAULT se assente o illeggibile.
    """
    try:
        sb = supabase_client
        if sb is None:
            from services import get_supabase_client
            sb = get_supabase_client()
        resp = (
            sb.table("users").select("price_alert_threshold")
            .eq("id", user_id).limit(1).execute()
        )
        if resp.data:
            raw = resp.data[0].get("price_alert_threshold")
            if raw is not None:
                return max(0.0, min(50.0, float(raw)))
    except Exception as exc:
        logger.warning("price_impact: lettura soglia cliente fallita: %s", exc)
    return _SOGLIA_PERC_DEFAULT


def _leggi_solo_preferiti(ristorante_id: str, supabase_client=None) -> bool:
    """Flag 'avvisi prezzi solo preferiti' da assistant_preferences. Default False."""
    try:
        sb = supabase_client
        if sb is None:
            from services import get_supabase_client
            sb = get_supabase_client()
        resp = (
            sb.table("assistant_preferences").select("alert_prezzi_solo_preferiti")
            .eq("ristorante_id", ristorante_id).limit(1).execute()
        )
        if resp.data:
            return bool(resp.data[0].get("alert_prezzi_solo_preferiti"))
    except Exception as exc:
        logger.warning("price_impact: lettura flag solo_preferiti fallita: %s", exc)
    return False


def _carica_preferiti_keys(ristorante_id: str, supabase_client=None) -> set:
    """Set di chiavi '{desc[:50]}|{forn}' dei prodotti preferiti del ristorante.

    Allineato a _pref_match_key: descrizione troncata a 50 (come _pareto_key) e
    fornitore upper. La tabella prezzi_preferiti gia' salva chiavi UPPER+TRIM.
    """
    try:
        sb = supabase_client
        if sb is None:
            from services import get_supabase_client
            sb = get_supabase_client()
        resp = (
            sb.table("prezzi_preferiti").select("descrizione_key,fornitore_key")
            .eq("ristorante_id", ristorante_id).execute()
        )
    except Exception as exc:
        logger.warning("price_impact: lettura preferiti fallita: %s", exc)
        return set()
    out: set = set()
    for r in (resp.data or []):
        d = str(r.get("descrizione_key", "")).strip().upper()[:50]
        f = str(r.get("fornitore_key", "")).strip().upper()
        out.add(f"{d}|{f}")
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
        # Carica SOLO la finestra che il motore usa davvero (prodotti + tag lavorano
        # entro _FINESTRA_GIORNI). Margine extra per i confronti ai bordi delle
        # sotto-finestre di analizza_tag. Evita il full-load di tutta la storia
        # (migliaia di righe -> 5s+ su clienti grossi, sforava il budget briefing).
        df = carica_e_prepara_dataframe(
            user_id, ristorante_id=ristorante_id,
            supabase_client=supabase_client, force_refresh=False,
            solo_ultimi_giorni=_FINESTRA_GIORNI + 10,
        )
    except Exception as exc:
        logger.warning("price_impact: caricamento fatture fallito: %s", exc)
        return vuoto
    if df is None or df.empty:
        return vuoto

    df_periodo = _filtra_finestra(df, _FINESTRA_GIORNI)
    if df_periodo.empty:
        return vuoto

    # Soglia % scelta dal cliente in pagina Prezzi (price_alert_threshold). E' il
    # "di quanto deve aumentare un prezzo perche' mi interessi" deciso da lui:
    # riusarla evita soglie magiche nostre e rispetta la sua sensibilita'.
    soglia_perc = _leggi_soglia_perc_cliente(user_id, supabase_client)

    # Modalita' filtro prodotti: "solo preferiti" (scelta del cliente nel
    # configuratore) oppure Pareto automatico (default AI-first). In modalita'
    # preferiti, se non ce ne sono, _alert_prodotti restituisce vuoto e restano
    # solo i tag (decisione Mattia: niente fallback al Pareto).
    if _leggi_solo_preferiti(ristorante_id, supabase_client):
        preferiti_keys = _carica_preferiti_keys(ristorante_id, supabase_client)
        prodotti = _alert_prodotti(df_periodo, soglia_perc, set(), preferiti_keys=preferiti_keys)
    else:
        # Fascia Pareto dei prodotti che pesano davvero sulla spesa food: i
        # marginali (limoni & co.) restano fuori anche se rincarano molto.
        prodotti_pareto = _prodotti_pareto(df_periodo)
        prodotti = _alert_prodotti(df_periodo, soglia_perc, prodotti_pareto)

    tag = _alert_tag(user_id, ristorante_id, df, soglia_perc)

    # Unisci e ordina per impatto €/mese decrescente; tieni i top.
    tutti = sorted(prodotti + tag, key=lambda a: a["impatto_mese"], reverse=True)
    tutti = tutti[:_MAX_ALERT]

    return {
        "count": len(tutti),
        "alerts": tutti,
        "top": tutti[0] if tutti else None,
    }
