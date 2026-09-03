"""Router dominio FATTURE — analisi, KPI, articoli aggregati, pivot, trend, batch.

Estratto da fastapi_worker.py. La data-access layer righe fatture (costanti
CATEGORIE_*, _build_fatture_base_query, _fetch_fatture_rows e la cache
_invalidate_fatture_rows_cache) resta nel worker perche' _invalidate_fatture_rows_cache
e' usata anche dalla route upload (worker) e _load_num_documento_map e' condivisa
con il router prezzi: tutto importato da qui. Path/gate/response invariati.
"""
import re
from html import unescape
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config.constants import TUTTE_LE_CATEGORIE
# utils/ non importa services/: import diretto, nessun rischio di ciclo.
from utils.supabase_paging import fetch_all

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint. La costante CATEGORIE_NOTE_WORKER si legge via
# accessor lazy (_categorie_note_worker). _verify_worker_key resta esplicito
# perche' usato in Depends() a import-time (firma identica per FastAPI).
import logging
logger = logging.getLogger("fastapi_worker")


def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _resolve_ristorante_id(*args, **kwargs):
    return _fw()._resolve_ristorante_id(*args, **kwargs)


def _load_num_documento_map(*args, **kwargs):
    return _fw()._load_num_documento_map(*args, **kwargs)


def _build_fatture_base_query(*args, **kwargs):
    return _fw()._build_fatture_base_query(*args, **kwargs)


def _fetch_fatture_rows(*args, **kwargs):
    return _fw()._fetch_fatture_rows(*args, **kwargs)


def _invalidate_fatture_rows_cache(*args, **kwargs):
    return _fw()._invalidate_fatture_rows_cache(*args, **kwargs)


def _categorie_note_worker():
    return _fw().CATEGORIE_NOTE_WORKER


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)

# `dependencies` a livello di router: la guardia vale per TUTTI gli endpoint,
# compresi quelli che verranno. Non sostituisce i `Depends` gia' presenti nelle
# firme — misurato il 3/9/2026: FastAPI esegue prima quella del router e POI
# quella dell'endpoint, quindi le protezioni piu' strette (`_verify_admin`, che
# controlla la worker key E il token admin) restano intatte.
#
# Non e' una falla che si chiude: al 3/9 tutti i 216 endpoint erano gia'
# protetti uno per uno. E' la rete perche' il 217esimo non nasca aperto.
router = APIRouter(dependencies=[Depends(_verify_worker_key)])


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
    ripartita_su_gruppo: bool = False


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
    righe_ids: List[int]  # per batch operations (solo righe reali, id>0)
    needs_review: bool
    is_nuovo: bool  # arrivato dopo l'ultimo accesso utente
    ripartita_su_gruppo: bool = False  # ha almeno una riga di quota di gruppo proiettata
    solo_gruppo: bool = False          # TUTTE le righe sono quote di gruppo (nessuna riga propria)
    file_origine_gruppo: Optional[str] = None  # documento di struttura da correggere


class ArticoliResponse(BaseModel):
    articoli: List[ArticoloAggregato]
    total: int
    # Quanti degli articoli elencati sono ACQUISTI secondo la stessa definizione del
    # KPI "Prodotti diversi" (almeno una riga con importo != 0, fatture.py:310-313).
    # `total` include le righe a importo 0 (note, diciture, omaggi), che la tabella
    # deve elencare perche' vanno categorizzate: senza questo campo il client non
    # poteva riconciliare i due numeri e li mostrava divergenti senza spiegazione.
    # Non si ricava lato client dall'aggregato: un articolo con storni che si
    # annullano ha totale_speso 0 ma righe di acquisto vere (misurato: fino a 14
    # articoli per sede).
    total_con_acquisti: int = 0


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
    # Costruisce l'elenco dei mesi selezionabili: se tronca, al cliente
    # spariscono mesi dal filtro senza alcun errore visibile.
    rows = fetch_all(
        supabase_client.table("fatture_documenti")
        .select("data_documento")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .not_.is_("data_documento", "null")
    )
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
    solo_nuovi: bool = False,
    solo_da_verificare: bool = False,
    solo_ripartite: bool = False,
    authorization: Optional[str] = Header(None),
) -> KpiResponse:
    user = _resolve_user_from_token(authorization)
    ristorante_id = _resolve_ristorante_id(user, _get_supabase_client())
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    supabase_client = _get_supabase_client()

    # cutoff "Nuovo": stesso criterio di /articoli-aggregati (nuovi_da del ristorante,
    # fallback 24h). Quando solo_nuovi è attivo i KPI riflettono SOLO le righe caricate
    # nell'ultima sessione, coerentemente con la tabella articoli.
    cutoff_nuovo = None
    if solo_nuovi:
        from datetime import datetime, timedelta, timezone
        ristorante_row = supabase_client.table("ristoranti").select("nuovi_da").eq("id", ristorante_id).single().execute()
        nuovi_da_raw = (ristorante_row.data or {}).get("nuovi_da")
        cutoff_nuovo = nuovi_da_raw or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    def _calc(rows):
        # "Spesa totale" = spesa NETTA: le note di credito (righe negative) sono
        # storni reali e DEVONO ridurre la spesa, altrimenti il KPI gonfia il
        # costo e non coincide con la tabella Articoli (che somma tutto).
        # Conteggio righe/prodotti resta sulle righe con importo != 0 (le righe
        # a 0 sono note/diciture/omaggi, non acquisti).
        rows_nonzero = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) != 0]
        totale = sum(float(r["totale_riga"]) for r in rows_nonzero)
        num_righe = len(rows_nonzero)
        prodotti = {r.get("descrizione", "").strip().lower() for r in rows_nonzero if r.get("descrizione")}
        mesi = {(r.get("data_documento") or "")[:7] for r in rows_nonzero if r.get("data_documento")}
        num_mesi = max(len(mesi), 1)
        media = totale / num_mesi
        return totale, num_righe, len(prodotti), media

    rows = _fetch_fatture_rows(supabase_client, ristorante_id, data_da, data_a, tipo_prodotti)
    if cutoff_nuovo is not None:
        rows = [r for r in rows if (r.get("created_at") or "") >= cutoff_nuovo]
    # Stessi due filtri di /articoli-aggregati: la KpiBar sta sopra la tabella
    # Articoli e senza di essi restava sul periodo intero mentre la tabella si
    # restringeva ("Spesa totale 120.000" sopra righe che ne sommano 3.200).
    # Il periodo di confronto NON viene filtrato, coerentemente con solo_nuovi:
    # il delta resta "quanto pesa questa selezione sul periodo precedente intero".
    if solo_da_verificare:
        rows = [r for r in rows if r.get("needs_review")]
    # Come il client (articoli-tab.tsx:199): il filtro si applica solo se nel
    # dataset esistono davvero righe ripartite. Il chip che lo spegne e' nascosto
    # quando non ce ne sono, e un ?ripartite=1 rimasto nell'URL avrebbe azzerato i
    # KPI sopra una tabella piena — lo stesso difetto, di segno opposto.
    if solo_ripartite and any(r.get("ripartita_su_gruppo") for r in rows):
        rows = [r for r in rows if r.get("ripartita_su_gruppo")]
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
    solo_ripartite: bool = False,
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
    if solo_ripartite:
        rows = [r for r in rows if r.get("ripartita_su_gruppo")]
    # solo_nuovi: filtra le righe PRIMA dell'aggregazione, così totale_speso/quantita/
    # num_acquisti di ogni articolo riflettono SOLO le righe dell'ultima sessione di
    # upload (non lo storico del prodotto nel periodo).
    if solo_nuovi:
        rows = [r for r in rows if (r.get("created_at") or "") >= cutoff_nuovo]

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

        # ripartita_su_gruppo: l'articolo include almeno una riga di quota di gruppo
        # proiettata (id sintetico < 0). Serve al badge nel tab Articoli.
        righe_gruppo = [it for it in items if it.get("ripartita_su_gruppo")]
        ripartita = bool(righe_gruppo)
        # solo_gruppo distingue i due casi che prima collassavano: un articolo fatto di
        # sole quote va corretto SOLO sul documento di struttura, uno misto ha bisogno
        # di entrambe le scritture (righe proprie del PV + documento di struttura),
        # altrimenti la porzione di gruppo resta sulla categoria vecchia e pesa nel
        # secchio MOL sbagliato. file_origine_gruppo dice su quale documento agire ed è
        # valorizzato ogni volta che esiste una porzione di gruppo, misto compreso.
        solo_gruppo = ripartita and len(righe_gruppo) == len(items)
        file_origine_gruppo = next(
            (it.get("file_origine") for it in righe_gruppo if it.get("file_origine")),
            None,
        )

        # is_nuovo: created_at di almeno una riga >= cutoff (ultima sessione upload).
        # Con solo_nuovi=True le righe vecchie sono già state filtrate a monte, quindi
        # qui resta sempre True.
        is_nuovo = False
        for it in items:
            ca = it.get("created_at")
            if ca and ca >= cutoff_nuovo:
                is_nuovo = True
                break

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
            righe_ids=[int(it["id"]) for it in items if it.get("id") and int(it["id"]) > 0],
            needs_review=nr,
            is_nuovo=is_nuovo,
            ripartita_su_gruppo=ripartita,
            solo_gruppo=solo_gruppo,
            file_origine_gruppo=file_origine_gruppo,
        ))

    # Ordina per totale_speso desc (i piu impattanti in alto)
    articoli.sort(key=lambda a: -a.totale_speso)
    con_acquisti = sum(
        1 for desc, items in groups.items()
        if any(it.get("totale_riga") and float(it["totale_riga"]) != 0 for it in items)
    )
    return ArticoliResponse(
        articoli=articoli, total=len(articoli), total_con_acquisti=con_acquisti
    )


# ─── Endpoint: righe singole (per espansione articolo) ─────────────────────

@router.get("/api/fatture/righe-articolo", response_model=List[RigaFattura], dependencies=[Depends(_verify_worker_key)])
def get_righe_articolo(
    descrizione: str,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    tipo_prodotti: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> List[RigaFattura]:
    user = _resolve_user_from_token(authorization)
    supabase_client = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, supabase_client)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    # Passa dal funnel _fetch_fatture_rows così l'espansione di un articolo mostra
    # anche le eventuali righe di gruppo proiettate (PV di catena), coerente con
    # l'aggregato. Filtro sulla descrizione esatta come faceva la query diretta.
    # tipo_prodotti va propagato come in /articoli-aggregati: senza il filtro il
    # totale della riga padre (aggregato, filtrato) non era la somma delle righe
    # figlie mostrate (tutte). Misurate 8 descrizioni a cavallo F&B/spese-generali
    # per (sede, descrizione) — che e' lo scope reale di questo endpoint. Il "22"
    # di §25 raggruppava per sola descrizione su tutte le sedi insieme.
    rows = [
        r for r in _fetch_fatture_rows(
            supabase_client, ristorante_id, data_da, data_a, tipo_prodotti
        )
        if (r.get("descrizione") or "") == descrizione
    ]
    rows.sort(key=lambda r: (r.get("data_documento") or ""), reverse=True)
    num_map = _load_num_documento_map(supabase_client, ristorante_id)
    result = []
    for r in rows:
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
    # Le note di credito (righe negative) sono storni reali e DEVONO ridurre la
    # spesa del periodo/categoria, esattamente come il KPI "Spesa totale"
    # (_calc, sopra). Filtrarle qui faceva divergere la card dai grafici: il
    # totale sottraeva gli storni, le barre no. Restano escluse le righe a 0
    # (note/diciture/omaggi, non acquisti).
    rows = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) != 0]

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
    # Come sopra (Andamento): gli storni delle note di credito riducono la
    # spesa anche nella Ripartizione, o le fette non sommano al totale della card.
    rows = [r for r in rows if r.get("totale_riga") and float(r["totale_riga"]) != 0]

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
    # Categorie usate dal ristorante.
    # PostgREST tronca a max_rows (1000) le select senza .range(): senza questa
    # paginazione il filtro perdeva le categorie presenti solo oltre la millesima
    # riga — tra cui "Da Classificare", che deve restare visibile (CLAUDE.md §1).
    rows = fetch_all(
        supabase_client.table("fatture")
        .select("categoria")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
    )
    categorie_usate = sorted({
        r["categoria"] for r in rows
        if r.get("categoria") and r["categoria"] not in _categorie_note_worker()
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

def _salva_correzione_memoria(*args, **kwargs):
    """Wrapper esplicito (niente __getattr__, PEP 562 ha già rotto 9 router):
    import al momento della chiamata per non pagare ai_service a import-time."""
    from services.ai_service import salva_correzione_in_memoria_locale
    return salva_correzione_in_memoria_locale(*args, **kwargs)

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
    # Stesso whitelist della PATCH singola riga (aggiorna_categoria_riga): il
    # constraint DB rifiuta solo "Da Clasificare", una categoria inventata/refuso
    # passerebbe e sporcherebbe margini e report su TUTTE le righe della descrizione.
    # La variante senza emoji è normalizzata subito sotto.
    _categorie_ammesse = set(TUTTE_LE_CATEGORIE) | {"📝 NOTE E DICITURE", "NOTE E DICITURE"}
    if nuova_cat not in _categorie_ammesse:
        raise HTTPException(status_code=400, detail=f"Categoria '{nuova_cat}' non riconosciuta")
    if nuova_cat == "NOTE E DICITURE":
        nuova_cat = "📝 NOTE E DICITURE"

    descrizione = body.descrizione.strip()
    if not descrizione:
        raise HTTPException(status_code=400, detail="Descrizione mancante")

    supabase_client = _get_supabase_client()
    # Aggiorna le righe con stessa descrizione del ristorante; se riga_ids e'
    # fornito, restringe l'update a quelle righe (prima il campo era dichiarato
    # ma ignorato: l'update toccava sempre TUTTE le righe con quella descrizione).
    update_q = (
        supabase_client.table("fatture")
        .update({
            "categoria": nuova_cat,
            "needs_review": False,
            # Fase 2 — vedi il ramo NOTE piu' sotto: una correzione manuale e' la
            # fonte piu' attendibile che esista. Vale su ENTRAMBI i rami, o una
            # riga corretta a mano terrebbe la provenienza automatica sbagliata.
            "categoria_fonte": "correzione_cliente",
            "categoria_fiducia": "certa",
        })
        .eq("ristorante_id", ristorante_id)
        .eq("descrizione", descrizione)
        .is_("deleted_at", "null")
    )
    if body.riga_ids:
        update_q = update_q.in_("id", body.riga_ids)
    # Guardrail dominio #2: NOTE E DICITURE solo su importo zero (stesso pattern
    # di admin.py:967-976) — senza questo check il batch scrive la variante con
    # emoji anche su righe con importo diverso da zero, aggirando il constraint DB.
    if nuova_cat == "📝 NOTE E DICITURE":
        _sel_q = (
            supabase_client.table("fatture")
            .select("id,totale_riga,prezzo_unitario")
            .eq("ristorante_id", ristorante_id)
            .eq("descrizione", descrizione)
            .is_("deleted_at", "null")
        )
        if body.riga_ids:
            _sel_q = _sel_q.in_("id", body.riga_ids)
        _candidate_rows = (_sel_q.execute()).data or []
        def _imp(r):
            t = float(r.get("totale_riga") or 0)
            return t if t != 0 else float(r.get("prezzo_unitario") or 0)
        _target_ids = [r["id"] for r in _candidate_rows if _imp(r) == 0]
        if not _target_ids:
            raise HTTPException(status_code=422, detail="NOTE E DICITURE non applicabile: tutte le righe hanno importo diverso da zero.")
        update_q = (
            supabase_client.table("fatture")
            .update({
                "categoria": nuova_cat,
                "needs_review": False,
                # Fase 2 — una correzione del cliente e' la fonte piu' attendibile che
                # esista: un umano ha guardato quella riga. Senza questo, una riga
                # corretta a mano conserverebbe per sempre la provenienza automatica
                # che l'aveva sbagliata, e la Fase 4 potrebbe escluderla dai margini
                # proprio dopo che il cliente l'ha sistemata.
                "categoria_fonte": "correzione_cliente",
                "categoria_fiducia": "certa",
            })
            .eq("ristorante_id", ristorante_id)
            .in_("id", _target_ids)
            .is_("deleted_at", "null")
        )
    res_update = update_q.execute()
    righe_aggiornate = len(res_update.data or [])
    if righe_aggiornate:
        _invalidate_fatture_rows_cache(ristorante_id)

    # Salva memoria AI locale (prodotti_utente) SOLO se qualcosa è stato davvero
    # aggiornato: con 0 righe toccate (es. riga di gruppo, che vive sulla sede tecnica
    # e non matcha il ristorante_id del PV) si insegnava all'AI una classificazione a
    # fronte di una scrittura mai avvenuta, e il cliente vedeva un falso successo.
    if not righe_aggiornate:
        return {
            "ok": True, "righe_aggiornate": 0, "descrizione": descrizione,
            "nuova_categoria": nuova_cat, "memoria_aggiornata": False,
        }

    # Fase 5: la funzione canonica al posto della scrittura inline. Quella
    # inline scriveva la descrizione GREZZA (chiave diversa dalla memoria che
    # legge la normalizzata) e `classificato_da: "User"`, che i check
    # `_e_override_manuale` non riconoscevano: l'auto-save poteva sovrascrivere
    # la correzione. E se falliva, il cliente riceveva comunque `ok: True`.
    memoria_ok = _salva_correzione_memoria(
        descrizione=descrizione,
        nuova_categoria=nuova_cat,
        user_id=user_id,
        user_email=str(user.get("email") or ""),
        supabase_client=supabase_client,
    )

    return {
        "ok": True, "righe_aggiornate": righe_aggiornate, "descrizione": descrizione,
        "nuova_categoria": nuova_cat, "memoria_aggiornata": bool(memoria_ok),
    }


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
    # La categoria deve appartenere al set ufficiale: il constraint DB rifiuta solo
    # "Da Clasificare", ma una categoria inventata/refuso passerebbe e sporcherebbe
    # margini e report. La variante senza emoji è normalizzata subito sotto, così
    # il guardrail importo-zero (regola dominio #2) si applica a un solo valore.
    _categorie_ammesse = set(TUTTE_LE_CATEGORIE) | {"📝 NOTE E DICITURE", "NOTE E DICITURE"}
    if categoria not in _categorie_ammesse:
        raise HTTPException(status_code=400, detail=f"Categoria '{categoria}' non riconosciuta")
    if categoria == "NOTE E DICITURE":
        categoria = "📝 NOTE E DICITURE"

    supabase_client = _get_supabase_client()
    check = (
        supabase_client.table("fatture")
        .select("id, totale_riga, prezzo_unitario, descrizione")
        .eq("id", riga_id)
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Riga non trovata")

    # Guardrail dominio #2: NOTE E DICITURE solo su importo zero (stesso pattern
    # di admin.py:967-976) — qui non c'è propagazione multi-riga, ma senza questo
    # check il constraint DB si aggira comunque scrivendo la variante con emoji
    # su una riga con importo diverso da zero.
    if categoria == "📝 NOTE E DICITURE":
        row = check.data[0]
        t = float(row.get("totale_riga") or 0)
        importo = t if t != 0 else float(row.get("prezzo_unitario") or 0)
        if importo != 0:
            raise HTTPException(status_code=422, detail="NOTE E DICITURE non applicabile: la riga ha importo diverso da zero.")

    supabase_client.table("fatture").update({
        "categoria": categoria,
        "needs_review": False,
        # Fase 2 — quarto e ultimo percorso di correzione manuale. Tutti registrano
        # la stessa fonte: e' quello che rende la provenienza affidabile a valle.
        "categoria_fonte": "correzione_cliente",
        "categoria_fiducia": "certa",
    }).eq("id", riga_id).execute()
    _invalidate_fatture_rows_cache(ristorante_id)

    # Fase 5 (D5): questo percorso aggiornava la riga e basta — la correzione
    # non insegnava nulla, e la STESSA descrizione sulla fattura successiva
    # tornava sbagliata. Stessa funzione canonica degli altri due percorsi.
    memoria_ok = _salva_correzione_memoria(
        descrizione=str(check.data[0].get("descrizione") or ""),
        nuova_categoria=categoria,
        user_id=str(user.get("id") or ""),
        user_email=str(user.get("email") or ""),
        supabase_client=supabase_client,
    )
    return {"ok": True, "id": riga_id, "categoria": categoria, "memoria_aggiornata": bool(memoria_ok)}


# ─────────────────────────────────────────────────────────────────────────────
# DA ASSEGNARE — coda fatture multi-sede in attesa di scelta sede dal cliente
# ─────────────────────────────────────────────────────────────────────────────
# Quando il webhook Invoicetronic non riesce a smistare automaticamente una fattura
# fra le sedi di un cliente (indirizzo ambiguo), la mette in status='da_assegnare'.
# Qui il cliente la vede e sceglie la sede; la RPC assegna_fattura_a_sede() completa.

_RE_DENOMINAZIONE = re.compile(r"<Denominazione>(.*?)</Denominazione>", re.DOTALL)
_RE_NOME = re.compile(r"<Nome>(.*?)</Nome>", re.DOTALL)
_RE_COGNOME = re.compile(r"<Cognome>(.*?)</Cognome>", re.DOTALL)


def _denominazione_cedente(xml: Optional[str]) -> Optional[str]:
    """Ragione sociale del fornitore letta dall'XML ancora in coda.

    Né il webhook SDI né l'upload manuale salvano la denominazione in payload_meta:
    entrambi mettono solo `piva_cedente`. La coda mostrava quindi "Fornitore P.IVA
    02910260963", illeggibile per chi deve decidere a quale locale appartiene la
    fattura. Il nome però è nell'XML, che per gli item da_assegnare è ancora in
    tabella (viene azzerato solo a lavorazione finita) → lo leggiamo qui, senza
    dover ri-scaricare nulla e recuperando anche gli item già in coda.

    Si taglia l'XML su CessionarioCommittente e si cerca solo nella parte prima:
    Denominazione compare in entrambi i blocchi, e il primo è il CedentePrestatore.
    Ditte individuali: niente Denominazione ma Nome+Cognome.
    """
    if not xml:
        return None
    testa = xml.split("CessionarioCommittente", 1)[0]
    m = _RE_DENOMINAZIONE.search(testa)
    if m and m.group(1).strip():
        return unescape(m.group(1).strip())
    nome = _RE_NOME.search(testa)
    cognome = _RE_COGNOME.search(testa)
    parti = [p.group(1).strip() for p in (nome, cognome) if p and p.group(1).strip()]
    return unescape(" ".join(parti)) if parti else None


@router.get("/api/fatture/da-assegnare", dependencies=[Depends(_verify_worker_key)])
def fatture_da_assegnare(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Elenca le fatture in attesa di assegnazione sede per l'account chiamante.

    Non espone l'XML: solo i metadati non-PII salvati dal webhook in payload_meta
    (fornitore, numero, data, importo) + l'indirizzo del destinatario letto in
    fattura, che è ciò che serve al cliente per capire a quale sede appartiene.
    L'XML si legge (non si restituisce) per ricavarne la ragione sociale del
    fornitore, che in payload_meta non c'è.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    resp = (
        sb.table("fatture_queue")
        .select("id, piva_raw, payload_meta, created_at, xml_content")
        .eq("user_id", user_id)
        .eq("status", "da_assegnare")
        .order("created_at", desc=True)
        .execute()
    )
    righe = resp.data or []

    # Regole fornitore memorizzate ("fai sempre così"): una sola query per tutto il
    # lotto (no loop per-fattura). Serve a evidenziare in coda le fatture già pronte
    # da ripartire e offrire la conferma rapida ("Dividi come al solito"). La regola
    # PROPONE, non applica mai da sola: il cliente conferma comunque.
    regole_by_piva: Dict[str, Dict[str, Any]] = {}
    pive = {str(p) for r in righe if (p := (r.get("payload_meta") or {}).get("piva_cedente"))}
    if pive:
        try:
            regs = (
                sb.table("riparto_regole_fornitore")
                .select("fornitore, regola, tipo, percentuali")
                .eq("user_id", user_id)
                .eq("attiva", True)
                .in_("fornitore", list(pive))
                .execute()
            ).data or []
            regole_by_piva = {str(g["fornitore"]): g for g in regs}
        except Exception as exc:
            # La regola è un di più: se la lettura fallisce la coda resta pienamente
            # usabile con la ripartizione manuale, non si perde nessuna fattura.
            logger.warning("da-assegnare: lettura regole fornitore fallita user=%s: %s", user_id, exc)

    items = []
    for r in righe:
        meta = r.get("payload_meta") or {}
        try:
            fornitore_nome = _denominazione_cedente(r.get("xml_content"))
        except Exception:
            # Il nome è una comodità: se l'XML è malformato la coda resta usabile
            # con la sola P.IVA, non si perde la fattura.
            fornitore_nome = None
        piva = meta.get("piva_cedente")
        reg = regole_by_piva.get(str(piva)) if piva else None
        items.append({
            "queue_id": r["id"],
            "fornitore": piva,
            "fornitore_nome": fornitore_nome,
            "numero_fattura": meta.get("numero_fattura"),
            "data_fattura": meta.get("data_fattura"),
            "importo_totale": meta.get("importo_totale"),
            "indirizzo_destinatario": meta.get("indirizzo_destinatario"),
            "created_at": r.get("created_at"),
            "regola_fornitore": (
                {"regola": reg["regola"], "tipo": reg["tipo"], "percentuali": reg.get("percentuali")}
                if reg else None
            ),
        })
    return {"items": items, "count": len(items)}


class ScartaCodaBody(BaseModel):
    queue_id: int


@router.post("/api/fatture/scarta-da-coda", dependencies=[Depends(_verify_worker_key)])
def fatture_scarta_da_coda(
    body: ScartaCodaBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Toglie dalla coda una fattura che non va assegnata a nessun locale.

    Senza questo, dalla coda si esce SOLO assegnando o ripartendo — entrambe fanno
    entrare il documento nei costi. Un documento non pertinente (o un doppione
    arrivato con un altro nome file) restava in coda per sempre, gonfiando il
    contatore del briefing di gruppo.

    Lo scarto è definitivo per quel file: l'event_id resta in tabella, quindi un
    ri-upload dello stesso identico file NON lo rimette in coda (idempotenza su
    event_id). Il file sorgente resta sul computer del cliente: per recuperarlo si
    ricarica dopo averlo rinominato.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    res = sb.rpc(
        "scarta_fattura_da_coda",
        {"p_queue_id": body.queue_id, "p_user_id": user_id},
    ).execute()
    if not bool(res.data):
        # Non è del chiamante, non esiste, o è stata assegnata da un altro click
        # nel frattempo. Per la UI non è un errore: la riga sparisce comunque.
        return {"ok": False, "motivo": "gia_gestita"}
    return {"ok": True, "queue_id": body.queue_id}


class AssegnaSedeBody(BaseModel):
    queue_id: int
    ristorante_id: str


@router.post("/api/fatture/assegna-sede", dependencies=[Depends(_verify_worker_key)])
def fatture_assegna_sede(
    body: AssegnaSedeBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Assegna una fattura 'da_assegnare' a una sede del cliente e la rimette in coda.

    Verifica prima che il record di coda appartenga al chiamante (la RPC fa già il
    guard cross-tenant lato DB, ma controlliamo anche qui per restituire un 404
    pulito invece di un'eccezione SQL).
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    rid = (body.ristorante_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="ristorante_id mancante")

    owns = (
        sb.table("fatture_queue")
        .select("id")
        .eq("id", body.queue_id)
        .eq("user_id", user_id)
        .eq("status", "da_assegnare")
        .execute()
    )
    if not owns.data:
        raise HTTPException(status_code=404, detail="Fattura non trovata o già assegnata")

    res = sb.rpc(
        "assegna_fattura_a_sede",
        {"p_queue_id": body.queue_id, "p_ristorante_id": rid},
    ).execute()
    assegnata = bool(res.data)
    if not assegnata:
        # Race: assegnata da un altro click nel frattempo. Non è un errore per la UI.
        return {"ok": False, "motivo": "gia_assegnata"}
    return {"ok": True, "queue_id": body.queue_id, "ristorante_id": rid}


class SpostaSedeBody(BaseModel):
    file_origine: str
    ristorante_id: str


@router.post("/api/fatture/sposta-sede", dependencies=[Depends(_verify_worker_key)])
def fatture_sposta_sede(
    body: SpostaSedeBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Sposta una fattura GIÀ acquisita verso un'altra sede dello stesso cliente.

    Correzione a posteriori del routing multi-sede: se una fattura è finita nella
    sede sbagliata (es. indirizzo fornitore errato ma plausibile), il cliente la
    sposta dal dettaglio fattura (Scadenziario). La RPC sposta_fattura_a_sede fa il
    guard anti cross-tenant lato DB; qui controlliamo che la fattura appartenga al
    chiamante per restituire un 404 pulito invece di un'eccezione SQL.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    rid = (body.ristorante_id or "").strip()
    fo = (body.file_origine or "").strip()
    if not rid or not fo:
        raise HTTPException(status_code=400, detail="Parametri mancanti")

    owns = (
        sb.table("fatture")
        .select("id, ripartita_su_gruppo")
        .eq("file_origine", fo)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if not owns.data:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    # Guard: una fattura ripartita sul gruppo non si sposta (avrebbe quote su sedi
    # diverse dalla sede intestataria → stato incoerente). Prima si toglie il
    # riparto (DELETE /api/riparto/{id}), poi eventualmente si sposta.
    if bool(owns.data[0].get("ripartita_su_gruppo")):
        raise HTTPException(
            status_code=409,
            detail="Questa fattura è ripartita sul gruppo: rimuovi prima la ripartizione, poi potrai spostarla.",
        )

    try:
        res = sb.rpc(
            "sposta_fattura_a_sede",
            {"p_user_id": user_id, "p_file_origine": fo, "p_ristorante_id": rid},
        ).execute()
    except Exception as exc:
        msg = str(exc)
        # Collisione: lo stesso file esiste già nella sede destinazione (account
        # multi-sede con stessa P.IVA). La RPC blocca atomicamente: messaggio chiaro.
        if "collisione_file_in_sede_destinazione" in msg:
            logger.warning("sposta_fattura_a_sede collisione user=%s file=%s rid=%s", user_id, fo, rid)
            raise HTTPException(
                status_code=409,
                detail="Questa fattura esiste già nella sede di destinazione: spostamento bloccato per evitare duplicati.",
            )
        # Guard DB (sede non del cliente / non attiva): non esporre l'SQL grezzo.
        logger.warning("sposta_fattura_a_sede fallita user=%s: %s", user_id, exc)
        raise HTTPException(status_code=400, detail="Sede non valida")

    spostate = int(res.data or 0)
    # Lo spostamento cambia il ristorante_id delle righe: invalida tutta la cache
    # (azione rara, non hot-path) così sia la sede di origine che quella di
    # destinazione ricaricano dati freschi. La cache è chiavata per ristorante.
    _invalidate_fatture_rows_cache()
    return {"ok": spostate > 0, "righe_spostate": spostate, "ristorante_id": rid}
