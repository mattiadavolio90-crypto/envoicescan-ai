"""Router dominio FATTURE — analisi, KPI, articoli aggregati, pivot, trend, batch.

Estratto da fastapi_worker.py. La data-access layer righe fatture (costanti
CATEGORIE_*, _build_fatture_base_query, _fetch_fatture_rows e la cache
_invalidate_fatture_rows_cache) resta nel worker perche' _invalidate_fatture_rows_cache
e' usata anche dalla route upload (worker) e _load_num_documento_map e' condivisa
con il router prezzi: tutto importato da qui. Path/gate/response invariati.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). __getattr__ risolve i
# simboli condivisi al primo accesso a runtime (incluse costanti come
# CATEGORIE_NOTE_WORKER, usate solo dentro le funzioni); _verify_worker_key resta
# esplicito perche' usato in Depends() a import-time (firma identica per FastAPI).
def __getattr__(name: str):
    import services.fastapi_worker as _fw
    return getattr(_fw, name)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    import services.fastapi_worker as _fw
    return _fw._verify_worker_key(x_worker_key)

router = APIRouter()


# ─── Modelli pydantic ──────────────────────────────────────────────────────

class RigaFattura(BaseModel):
    id: int
    file_origine: str
    numero_riga: int
    data_documento: Optional[str]
    fornitore: str
    descrizione: str
    quantita: Optional[float]
    unita_misura: Optional[str]
    prezzo_unitario: Optional[float]
    totale_riga: Optional[float]
    categoria: Optional[str]
    needs_review: Optional[bool]
    tipo_documento: Optional[str]
    data_competenza: Optional[str]
    piva_cedente: Optional[str]
    created_at: Optional[str] = None
    numero_documento: Optional[str] = None


class ArticoloAggregato(BaseModel):
    descrizione: str
    categoria: Optional[str]
    fornitore_principale: str
    altri_fornitori: List[str]
    ultimo_acquisto: Optional[str]
    quantita_totale: float
    unita_misura: Optional[str]
    prezzo_unit_medio: Optional[float]
    prezzo_unit_trend_pct: Optional[float]  # % rispetto al periodo precedente
    totale_speso: float
    num_acquisti: int
    righe_ids: List[int]  # per batch operations
    needs_review: bool
    is_nuovo: bool  # arrivato dopo l'ultimo accesso utente


class ArticoliResponse(BaseModel):
    articoli: List[ArticoloAggregato]
    total: int


class KpiResponse(BaseModel):
    totale: float
    num_righe: int
    num_prodotti: int
    media_mensile: float
    delta_totale_pct: Optional[float]
    delta_righe_pct: Optional[float]
    delta_prodotti_pct: Optional[float]
    delta_media_pct: Optional[float]
    confronto_label: str = "periodo prec."


class MesiDisponibiliResponse(BaseModel):
    mesi: List[Dict[str, Any]]  # [{year, month, label, count}, ...]


class PivotRow(BaseModel):
    dimensione: str
    periodi: Dict[str, float]  # chiave: YYYY-MM o YYYY-Qn o YYYY
    totale: float
    media: float
    incidenza_pct: float  # % sul grand total
    sparkline: List[float]  # ultimi N periodi per mini-grafico


class PivotResponse(BaseModel):
    rows: List[PivotRow]
    periodi: List[str]
    periodi_labels: List[str]
    granularita: str  # "mese" | "trimestre" | "anno"
    totali_periodo: Dict[str, float]
    grand_total: float


class TrendPunto(BaseModel):
    periodo: str
    label: str
    valore: float


class TrendSerie(BaseModel):
    valore: str
    punti: List[TrendPunto]
    media: float
    totale: float


class TrendResponse(BaseModel):
    serie: List[TrendSerie]
    periodi: List[str]
    periodi_labels: List[str]


class CategoriaBatchRequest(BaseModel):
    descrizione: str
    nuova_categoria: str
    riga_ids: Optional[List[int]] = None  # se fornito, aggiorna solo questi id


_MESI_LABEL_IT = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
                  "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def _period_key(date_str: str, granularita: str) -> str:
    """Restituisce chiave periodo per granularita selezionata."""
    if not date_str or len(date_str) < 10:
        return ""
    y = date_str[:4]
    m = int(date_str[5:7])
    if granularita == "anno":
        return y
    if granularita == "trimestre":
        q = (m - 1) // 3 + 1
        return f"{y}-Q{q}"
    return f"{y}-{m:02d}"  # mese


def _period_label(key: str, granularita: str) -> str:
    if not key:
        return ""
    if granularita == "anno":
        return key
    if granularita == "trimestre":
        return key.replace("-Q", " T")  # "2026 T1"
    # mese
    y, m = key.split("-")
    return f"{_MESI_LABEL_IT[int(m)]} {y[2:]}"


def _scegli_granularita(periodi_set: set) -> str:
    """Sceglie granularita automatica basata sul numero di mesi nel periodo."""
    n = len(periodi_set)
    if n <= 12:
        return "mese"
    if n <= 36:
        return "trimestre"
    return "anno"


def _compute_periodo_precedente(data_da: Optional[str], data_a: Optional[str]) -> tuple:
    """Calcola il periodo precedente di stessa durata."""
    from datetime import date, timedelta
    if not data_da or not data_a:
        return None, None
    try:
        d_da = date.fromisoformat(data_da)
        d_a = date.fromisoformat(data_a)
        durata = (d_a - d_da).days + 1
        prev_a = d_da - timedelta(days=1)
        prev_da = prev_a - timedelta(days=durata - 1)
        return prev_da.isoformat(), prev_a.isoformat()
    except Exception:
        return None, None


# ─── Endpoint: lista mesi disponibili ──────────────────────────────────────

@router.get("/api/fatture/mesi-disponibili", response_model=MesiDisponibiliResponse, dependencies=[Depends(_verify_worker_key)])
def get_mesi_disponibili(
    authorization: Optional[str] = Header(None),
) -> MesiDisponibiliResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    res = (
        supabase_client.table("fatture")
        .select("data_documento")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .not_.is_("data_documento", "null")
        .execute()
    )
    rows = res.data or []
    counts: Dict[str, int] = {}
    for r in rows:
        d = r.get("data_documento")
        if d and len(d) >= 7:
            counts[d[:7]] = counts.get(d[:7], 0) + 1

    mesi = []
    for ym in sorted(counts.keys(), reverse=True):
        y, m = ym.split("-")
        mesi.append({
            "year": int(y),
            "month": int(m),
            "label": f"{_MESI_LABEL_IT[int(m)]} {y}",
            "count": counts[ym],
        })
    return MesiDisponibiliResponse(mesi=mesi)


# ─── Endpoint: KPI con delta vs periodo precedente ─────────────────────────

@router.get("/api/fatture/kpi", response_model=KpiResponse, dependencies=[Depends(_verify_worker_key)])
def get_fatture_kpi(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> KpiResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()

    def _calc(rows):
        rows_valid = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) > 0]
        totale = sum(float(r["totale_riga"]) for r in rows_valid)
        num_righe = len(rows_valid)
        prodotti = {r.get("descrizione", "").strip().lower() for r in rows_valid if r.get("descrizione")}
        mesi = {(r.get("data_documento") or "")[:7] for r in rows_valid if r.get("data_documento")}
        num_mesi = max(len(mesi), 1)
        media = totale / num_mesi
        return totale, num_righe, len(prodotti), media

    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    tot, nr, np, med = _calc(rows)

    from datetime import date as _date, timedelta as _timedelta

    delta_tot = delta_nr = delta_np = delta_med = None
    confronto_label = "periodo prec."
    use_media_anno = False

    # Per periodi brevi (≤ 31 giorni) confronta vs media mensile dell'anno in corso
    if data_da and data_a:
        try:
            d_da = _date.fromisoformat(data_da)
            d_a = _date.fromisoformat(data_a)
            durata = (d_a - d_da).days + 1
            if durata <= 31:
                anno_inizio = _date(d_da.year, 1, 1)
                giorno_prima = d_da - _timedelta(days=1)
                if giorno_prima >= anno_inizio:
                    prev_da = anno_inizio.isoformat()
                    prev_a = giorno_prima.isoformat()
                    use_media_anno = True
                    confronto_label = "media anno in corso"
                else:
                    prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
            else:
                prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
        except Exception:
            prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
    else:
        prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)

    if prev_da and prev_a:
        prev_rows = _fetch_fatture_rows(supabase_client, ristorante_id, prev_da, prev_a, tipo_prodotti)
        ptot, pnr, pnp, pmed = _calc(prev_rows)

        def _delta(curr, prev_val):
            if prev_val == 0:
                return None
            return round((curr - prev_val) / prev_val * 100, 1)

        if use_media_anno:
            # pmed = media mensile del periodo baseline (gen→giorno prima)
            prev_mesi_set = {(r.get("data_documento") or "")[:7] for r in prev_rows if r.get("data_documento")}
            num_prev_mesi = max(len(prev_mesi_set), 1)
            pmed_righe = pnr / num_prev_mesi
            pmed_prod = pnp / num_prev_mesi
            delta_tot = _delta(tot, pmed)
            delta_nr = _delta(nr, pmed_righe)
            delta_np = _delta(np, pmed_prod)
            delta_med = _delta(med, pmed)
        else:
            delta_tot = _delta(tot, ptot)
            delta_nr = _delta(nr, pnr)
            delta_np = _delta(np, pnp)
            delta_med = _delta(med, pmed)

    return KpiResponse(
        totale=round(tot, 2),
        num_righe=nr,
        num_prodotti=np,
        media_mensile=round(med, 2),
        delta_totale_pct=delta_tot,
        delta_righe_pct=delta_nr,
        delta_prodotti_pct=delta_np,
        delta_media_pct=delta_med,
        confronto_label=confronto_label,
    )


# ─── Endpoint: articoli aggregati (vista default tab Articoli) ─────────────

@router.get("/api/fatture/articoli-aggregati", response_model=ArticoliResponse, dependencies=[Depends(_verify_worker_key)])
def get_articoli_aggregati(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    categoria: Optional[str] = None,
    fornitore: Optional[str] = None,
    search: Optional[str] = None,
    solo_nuovi: bool = False,
    solo_da_verificare: bool = False,
    authorization: Optional[str] = Header(None),
) -> ArticoliResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()

    # cutoff "Nuovo": usa nuovi_da dal ristorante (impostato all'inizio di ogni sessione upload).
    # Fallback a 24h se nuovi_da non è ancora impostato (primo avvio).
    from datetime import datetime, timedelta, timezone
    ristorante_row = supabase_client.table("ristoranti").select("nuovi_da").eq("id", ristorante_id).single().execute()
    nuovi_da_raw = (ristorante_row.data or {}).get("nuovi_da")
    if nuovi_da_raw:
        cutoff_nuovo = nuovi_da_raw
    else:
        cutoff_nuovo = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    rows = _fetch_fatture_rows(
        supabase_client, ristorante_id, data_da, data_a, tipo_prodotti, search
    )
    if categoria:
        rows = [r for r in rows if r.get("categoria") == categoria]
    if fornitore:
        rows = [r for r in rows if r.get("fornitore") == fornitore]
    if solo_da_verificare:
        rows = [r for r in rows if r.get("needs_review")]

    # Aggrega per descrizione normalizzata
    from collections import defaultdict
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        desc = (r.get("descrizione") or "").strip()
        if not desc:
            continue
        groups[desc].append(r)

    # Periodo precedente per trend prezzo
    prev_da, prev_a = _compute_periodo_precedente(data_da, data_a)
    prev_prices: Dict[str, float] = {}
    if prev_da and prev_a:
        prev_rows = _fetch_fatture_rows(
            supabase_client, ristorante_id, prev_da, prev_a, tipo_prodotti
        )
        prev_groups: Dict[str, List[float]] = defaultdict(list)
        for pr in prev_rows:
            desc = (pr.get("descrizione") or "").strip()
            pu = pr.get("prezzo_unitario")
            if desc and pu is not None and float(pu) > 0:
                prev_groups[desc].append(float(pu))
        for desc, prices in prev_groups.items():
            if prices:
                prev_prices[desc] = sum(prices) / len(prices)

    articoli: List[ArticoloAggregato] = []
    for desc, items in groups.items():
        # fornitori
        forn_counts: Dict[str, int] = defaultdict(int)
        for it in items:
            f = (it.get("fornitore") or "").strip()
            if f:
                forn_counts[f] += 1
        forn_sorted = sorted(forn_counts.items(), key=lambda x: -x[1])
        forn_principale = forn_sorted[0][0] if forn_sorted else ""
        altri_forn = [f for f, _ in forn_sorted[1:]]

        # categoria piu frequente
        cat_counts: Dict[str, int] = defaultdict(int)
        for it in items:
            c = it.get("categoria")
            if c:
                cat_counts[c] += 1
        categoria_principale = max(cat_counts.items(), key=lambda x: x[1])[0] if cat_counts else None

        # date e quantita
        date_list = [it.get("data_documento") for it in items if it.get("data_documento")]
        ultimo_acq = max(date_list) if date_list else None
        qta_totale = sum(float(it.get("quantita") or 0) for it in items)
        um = next((it.get("unita_misura") for it in items if it.get("unita_misura")), None)
        prezzi = [float(it["prezzo_unitario"]) for it in items if it.get("prezzo_unitario") and float(it["prezzo_unitario"]) > 0]
        prezzo_medio = sum(prezzi) / len(prezzi) if prezzi else None
        totale_speso = sum(float(it.get("totale_riga") or 0) for it in items)
        num_acq = len(items)

        # trend prezzo vs periodo precedente
        trend_pct = None
        if prezzo_medio is not None and desc in prev_prices and prev_prices[desc] > 0:
            trend_pct = round((prezzo_medio - prev_prices[desc]) / prev_prices[desc] * 100, 1)

        # needs_review se almeno una riga
        nr = any(it.get("needs_review") for it in items)

        # is_nuovo: created_at di almeno una riga nelle ultime 24h
        is_nuovo = False
        for it in items:
            ca = it.get("created_at")
            if ca and ca >= cutoff_nuovo:
                is_nuovo = True
                break

        if solo_nuovi and not is_nuovo:
            continue

        articoli.append(ArticoloAggregato(
            descrizione=desc,
            categoria=categoria_principale,
            fornitore_principale=forn_principale,
            altri_fornitori=altri_forn,
            ultimo_acquisto=ultimo_acq,
            quantita_totale=round(qta_totale, 2),
            unita_misura=um,
            prezzo_unit_medio=round(prezzo_medio, 2) if prezzo_medio else None,
            prezzo_unit_trend_pct=trend_pct,
            totale_speso=round(totale_speso, 2),
            num_acquisti=num_acq,
            righe_ids=[int(it["id"]) for it in items if it.get("id")],
            needs_review=nr,
            is_nuovo=is_nuovo,
        ))

    # Ordina per totale_speso desc (i piu impattanti in alto)
    articoli.sort(key=lambda a: -a.totale_speso)
    return ArticoliResponse(articoli=articoli, total=len(articoli))


# ─── Endpoint: righe singole (per espansione articolo) ─────────────────────

@router.get("/api/fatture/righe-articolo", response_model=List[RigaFattura], dependencies=[Depends(_verify_worker_key)])
def get_righe_articolo(
    descrizione: str,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> List[RigaFattura]:
    user = _resolve_user_from_token(authorization)
    supabase_client = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    q = _build_fatture_base_query(supabase_client, ristorante_id).eq("descrizione", descrizione)
    if data_da:
        q = q.gte("data_documento", data_da)
    if data_a:
        q = q.lte("data_documento", data_a)
    q = q.order("data_documento", desc=True)
    res = q.execute()
    num_map = _load_num_documento_map(supabase_client, ristorante_id)
    result = []
    for r in (res.data or []):
        fields = {k: v for k, v in r.items() if k in RigaFattura.model_fields}
        fields["numero_documento"] = num_map.get(r.get("file_origine", ""), "") or None
        result.append(RigaFattura(**fields))
    return result


# ─── Endpoint: pivot estesa (mese/trimestre/anno auto) ─────────────────────

@router.get("/api/fatture/pivot", response_model=PivotResponse, dependencies=[Depends(_verify_worker_key)])
def get_fatture_pivot(
    dimensione: str = "categoria",  # "categoria" | "fornitore"
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> PivotResponse:
    if dimensione not in ("categoria", "fornitore"):
        raise HTTPException(status_code=400, detail="dimensione deve essere 'categoria' o 'fornitore'")

    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    rows = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) > 0]

    # Determina granularita dai mesi presenti
    mesi_presenti = {(r.get("data_documento") or "")[:7] for r in rows if r.get("data_documento")}
    mesi_presenti.discard("")
    granularita = _scegli_granularita(mesi_presenti)

    col = "categoria" if dimensione == "categoria" else "fornitore"
    from collections import defaultdict
    agg: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    periodi_set: set = set()
    for r in rows:
        d = r.get("data_documento")
        if not d:
            continue
        key = _period_key(d, granularita)
        if not key:
            continue
        dim_val = (r.get(col) or "N/D")
        agg[dim_val][key] += float(r.get("totale_riga") or 0)
        periodi_set.add(key)

    periodi = sorted(periodi_set)
    periodi_labels = [_period_label(p, granularita) for p in periodi]

    grand_total = sum(sum(d.values()) for d in agg.values())
    totali_periodo: Dict[str, float] = {p: 0.0 for p in periodi}
    for d in agg.values():
        for k, v in d.items():
            totali_periodo[k] = totali_periodo.get(k, 0) + v

    # sparkline: ultimi min(12, len(periodi)) periodi
    spark_n = min(12, len(periodi))
    spark_periodi = periodi[-spark_n:] if spark_n > 0 else []

    pivot_rows: List[PivotRow] = []
    for dim_val, periodi_dict in agg.items():
        tot = sum(periodi_dict.values())
        media = tot / len(periodi) if periodi else 0
        inc = (tot / grand_total * 100) if grand_total > 0 else 0
        spark = [round(periodi_dict.get(p, 0), 2) for p in spark_periodi]
        pivot_rows.append(PivotRow(
            dimensione=dim_val,
            periodi={k: round(v, 2) for k, v in periodi_dict.items()},
            totale=round(tot, 2),
            media=round(media, 2),
            incidenza_pct=round(inc, 1),
            sparkline=spark,
        ))
    pivot_rows.sort(key=lambda x: -x.totale)

    return PivotResponse(
        rows=pivot_rows,
        periodi=periodi,
        periodi_labels=periodi_labels,
        granularita=granularita,
        totali_periodo={k: round(v, 2) for k, v in totali_periodo.items()},
        grand_total=round(grand_total, 2),
    )


# ─── Endpoint: trend temporale (grafico multi-select) ──────────────────────

@router.get("/api/fatture/trend", response_model=TrendResponse, dependencies=[Depends(_verify_worker_key)])
def get_fatture_trend(
    dimensione: str = "categoria",
    valori: Optional[str] = None,  # CSV: "CARNE,PESCE,..." o "Marini,Demare"
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> TrendResponse:
    if dimensione not in ("categoria", "fornitore"):
        raise HTTPException(status_code=400, detail="dimensione invalida")

    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    rows = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) > 0]

    mesi_presenti = {(r.get("data_documento") or "")[:7] for r in rows if r.get("data_documento")}
    mesi_presenti.discard("")
    granularita = _scegli_granularita(mesi_presenti)
    periodi = sorted(mesi_presenti) if granularita == "mese" else sorted({_period_key(r.get("data_documento", ""), granularita) for r in rows if r.get("data_documento")})
    periodi_labels = [_period_label(p, granularita) for p in periodi]

    col = "categoria" if dimensione == "categoria" else "fornitore"
    selected = [v.strip() for v in (valori or "").split(",") if v.strip()] if valori else []
    if not selected:
        # top 3 di default
        from collections import defaultdict
        tots = defaultdict(float)
        for r in rows:
            tots[(r.get(col) or "N/D")] += float(r.get("totale_riga") or 0)
        selected = [k for k, _ in sorted(tots.items(), key=lambda x: -x[1])[:3]]

    serie: List[TrendSerie] = []
    for val in selected:
        from collections import defaultdict
        per_periodo = defaultdict(float)
        for r in rows:
            if (r.get(col) or "N/D") != val:
                continue
            d = r.get("data_documento")
            if not d:
                continue
            key = _period_key(d, granularita)
            if key:
                per_periodo[key] += float(r.get("totale_riga") or 0)
        punti = [TrendPunto(periodo=p, label=_period_label(p, granularita), valore=round(per_periodo.get(p, 0), 2)) for p in periodi]
        tot = sum(per_periodo.values())
        media = tot / len(periodi) if periodi else 0
        serie.append(TrendSerie(valore=val, punti=punti, media=round(media, 2), totale=round(tot, 2)))

    return TrendResponse(serie=serie, periodi=periodi, periodi_labels=periodi_labels)


# ─── Endpoint: fornitori distinti del ristorante ───────────────────────────

@router.get("/api/fatture/fornitori", dependencies=[Depends(_verify_worker_key)])
def get_fornitori_disponibili(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    supabase_client = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    rows: List[Dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            supabase_client.table("fatture")
            .select("fornitore")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        if offset >= 50000:
            break
    fornitori = sorted({(r.get("fornitore") or "").strip() for r in rows if r.get("fornitore")}, key=lambda s: s.casefold())
    return {"fornitori": fornitori}


# ─── Endpoint: categorie disponibili ───────────────────────────────────────

@router.get("/api/fatture/categorie", dependencies=[Depends(_verify_worker_key)])
def get_categorie_disponibili(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    # Categorie usate dal ristorante
    res = (
        supabase_client.table("fatture")
        .select("categoria")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    rows = res.data or []
    categorie_usate = sorted({
        r["categoria"] for r in rows
        if r.get("categoria") and r["categoria"] not in CATEGORIE_NOTE_WORKER
    })

    # Categorie canoniche (lista master) — facciamo query semplice
    try:
        res_master = supabase_client.table("categorie").select("nome").execute()
        canoniche = sorted({c["nome"] for c in (res_master.data or []) if c.get("nome") and "DICITURE" not in c["nome"].upper()})
    except Exception:
        canoniche = []

    # Unione
    tutte = sorted(set(categorie_usate) | set(canoniche))
    return {"categorie": tutte, "usate": categorie_usate}


# ─── Endpoint: batch update categoria (stessa descrizione) + memoria AI ────

@router.post("/api/fatture/categoria-batch", dependencies=[Depends(_verify_worker_key)])
def categoria_batch(
    body: CategoriaBatchRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    user_id = user.get("id")
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id or not user_id:
        raise HTTPException(status_code=400, detail="Utente o ristorante mancante")

    nuova_cat = body.nuova_categoria.strip()
    if not nuova_cat or nuova_cat in ("Da Clasificare", "Da Classificare"):
        raise HTTPException(status_code=400, detail="Categoria non valida")

    descrizione = body.descrizione.strip()
    if not descrizione:
        raise HTTPException(status_code=400, detail="Descrizione mancante")

    supabase_client = _get_supabase_client()
    # Aggiorna tutte le righe con stessa descrizione del ristorante
    update_q = (
        supabase_client.table("fatture")
        .update({"categoria": nuova_cat, "needs_review": False})
        .eq("ristorante_id", ristorante_id)
        .eq("descrizione", descrizione)
        .is_("deleted_at", "null")
    )
    res_update = update_q.execute()
    righe_aggiornate = len(res_update.data or [])
    if righe_aggiornate:
        _invalidate_fatture_rows_cache(ristorante_id)

    # Salva memoria AI locale (prodotti_utente)
    try:
        existing = (
            supabase_client.table("prodotti_utente")
            .select("id")
            .eq("user_id", user_id)
            .eq("descrizione", descrizione)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase_client.table("prodotti_utente").update({
                "categoria": nuova_cat,
                "classificato_da": "User",
                "updated_at": "now()",
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase_client.table("prodotti_utente").insert({
                "user_id": user_id,
                "descrizione": descrizione,
                "categoria": nuova_cat,
                "classificato_da": "User",
                "volte_visto": 1,
            }).execute()
    except Exception as e:
        logger.warning(f"Memoria AI non salvata per '{descrizione}': {e}")

    return {"ok": True, "righe_aggiornate": righe_aggiornate, "descrizione": descrizione, "nuova_categoria": nuova_cat}


# ─── Endpoint: lista righe paginata (compat con vecchio /api/fatture) ──────

class FattureListResponse(BaseModel):
    righe: List[RigaFattura]
    total: int
    page: int
    page_size: int


@router.get("/api/fatture", response_model=FattureListResponse, dependencies=[Depends(_verify_worker_key)])
def get_fatture(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    fornitore: Optional[str] = None,
    categoria: Optional[str] = None,
    needs_review: Optional[bool] = None,
    tipo_prodotti: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    authorization: Optional[str] = Header(None),
) -> FattureListResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()
    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti, search)
    if fornitore:
        rows = [r for r in rows if fornitore.lower() in (r.get("fornitore") or "").lower()]
    if categoria:
        rows = [r for r in rows if r.get("categoria") == categoria]
    if needs_review is not None:
        rows = [r for r in rows if bool(r.get("needs_review")) == bool(needs_review)]

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    righe = [RigaFattura(**{k: v for k, v in r.items() if k in RigaFattura.model_fields}) for r in page_rows]
    return FattureListResponse(righe=righe, total=total, page=page, page_size=page_size)


# ─── Endpoint legacy compat: PATCH categoria singola riga ──────────────────

class AggiornaCategoriaRequest(BaseModel):
    categoria: str


@router.patch("/api/fatture/{riga_id}/categoria", dependencies=[Depends(_verify_worker_key)])
def aggiorna_categoria_riga(
    riga_id: int,
    body: AggiornaCategoriaRequest,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    categoria = body.categoria.strip()
    if not categoria or categoria in ("Da Clasificare", "Da Classificare"):
        raise HTTPException(status_code=400, detail="Categoria non valida")

    supabase_client = _get_supabase_client()
    check = (
        supabase_client.table("fatture")
        .select("id")
        .eq("id", riga_id)
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Riga non trovata")

    supabase_client.table("fatture").update(
        {"categoria": categoria, "needs_review": False}
    ).eq("id", riga_id).execute()
    return {"ok": True, "id": riga_id, "categoria": categoria}
