"""Router dominio MARGINI — conto economico, centri di costo, analisi avanzata, KPI hub.

Estratto da fastapi_worker.py. Gli aggregatori condivisi del conto economico
(costanti _CENTRI_*, _CATEGORIE_*, e gli helper _load_*/_calcola_costi_*/_aggrega_*)
restano nel worker e sono importati qui: sono il cuore dati lato margini e
restano co-locati con le costanti che usano. _calc_netto vive nel router ricavi
(condiviso) ed e' importato da li'. _ore_turno e' condiviso con il workspace
(Personale) e resta nel worker. Path/gate/response invariati.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint. Le costanti _CENTRI_*/_CATEGORIE_* (dict/set, usate
# come valori) vengono ribindate localmente all'inizio delle funzioni che le usano,
# via _consts(). _verify_worker_key resta esplicito perche' usato in Depends() a
# import-time (firma identica per l'iniezione FastAPI).
def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _resolve_ristorante_id(*args, **kwargs):
    return _fw()._resolve_ristorante_id(*args, **kwargs)


def _ore_turno(*args, **kwargs):
    return _fw()._ore_turno(*args, **kwargs)


def _load_fatture_fb_for_period(*args, **kwargs):
    return _fw()._load_fatture_fb_for_period(*args, **kwargs)


def _load_fatture_fb_per_categoria_e_mese(*args, **kwargs):
    return _fw()._load_fatture_fb_per_categoria_e_mese(*args, **kwargs)


def _load_mensile_overrides(*args, **kwargs):
    return _fw()._load_mensile_overrides(*args, **kwargs)


def _calcola_costi_auto_per_periodo(*args, **kwargs):
    return _fw()._calcola_costi_auto_per_periodo(*args, **kwargs)


def _aggrega_mensili_margini(*args, **kwargs):
    return _fw()._aggrega_mensili_margini(*args, **kwargs)


def _invalidate_home_kpi_cache(*args, **kwargs):
    return _fw()._invalidate_home_kpi_cache(*args, **kwargs)


def _consts():
    """Le costanti dominio margini (dict/set) dal worker, risolte al primo uso."""
    fw = _fw()
    return (
        fw._CATEGORIE_FB_M,
        fw._CATEGORIE_SPESE_M,
        fw._CAT_TO_CENTRO,
        fw._CENTRI_CON_FATTURATO,
        fw._CENTRI_DI_PRODUZIONE,
    )


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)
from services.routers.ricavi import _calc_netto

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# MARGINALITÀ
# ═══════════════════════════════════════════════════════════════════════════

class MarginiMeseData(BaseModel):
    mese: int
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    altri_costi_fb: float = 0.0
    altri_costi_spese: float = 0.0
    costo_dipendenti: float = 0.0
    costo_personale_extra: float = 0.0
    costi_fb_auto: float = 0.0
    costi_spese_auto: float = 0.0
    # Quote dei costi di gruppo ripartiti su questa sede nel mese. Popolate SOLO
    # dal motore riparto (riparto_quote_mensili), sola lettura per l'utente: si
    # sommano ai costi F&B / spese nel MOL ma non sono editabili qui.
    quote_riparto_fb: float = 0.0
    quote_riparto_spese: float = 0.0


class MarginiAnnoResponse(BaseModel):
    anno: int
    mesi: List[MarginiMeseData]


class SalvaMarginiRequest(BaseModel):
    anno: int
    mesi: List[MarginiMeseData]


class FatturatoCentriData(BaseModel):
    anno: int
    mese: int
    fatturato_food: float = 0.0
    fatturato_beverage: float = 0.0
    fatturato_alcolici: float = 0.0
    fatturato_dolci: float = 0.0


class CentroCostoItem(BaseModel):
    centro: str
    categorie: List[str]
    costo_totale: float
    fatturato: float = 0.0
    margine: float = 0.0
    incidenza_su_fatt: float = 0.0
    incidenza_su_fb: float = 0.0


class AnalisiCentriResponse(BaseModel):
    centri: List[CentroCostoItem]
    totale_costi_fb: float
    fatturato_netto_periodo: float
    primo_margine: float
    primo_margine_pct: float
    mesi_con_dati: List[int]


@router.get("/api/margini", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_margini(
    anno: Optional[int] = None,
    authorization: Optional[str] = Header(None),
) -> MarginiAnnoResponse:
    from datetime import datetime as _dt
    if anno is None:
        anno = _dt.now().year
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    resp = (
        sb.table("margini_mensili")
        .select("mese,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,altri_costi_fb,altri_costi_spese,costo_dipendenti,costo_personale_extra,quote_riparto_fb,quote_riparto_spese")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .execute()
    )
    saved = {int(r["mese"]): r for r in (resp.data or [])}

    # Costi auto food/spese per mese: aggregazione SQL via RPC costi_automatici_mensili
    # invece del full-load di tutte le righe fattura dell'anno + groupby pandas (era il
    # collo di bottiglia su clienti con molte fatture). La RPC replica esattamente la
    # logica storica — COALESCE(data_competenza, data_documento), stessi filtri, stesso
    # split food/spese — e ricade automaticamente su pandas se fallisce.
    from services.margine_service import calcola_costi_automatici_per_anno_sql
    costi_fb_auto, costi_spese_auto = calcola_costi_automatici_per_anno_sql(
        user_id, ristorante_id, int(anno)
    )

    mesi = []
    for m in range(1, 13):
        s = saved.get(m, {})
        mesi.append(MarginiMeseData(
            mese=m,
            fatturato_iva10=float(s.get("fatturato_iva10") or 0),
            fatturato_iva22=float(s.get("fatturato_iva22") or 0),
            altri_ricavi_noiva=float(s.get("altri_ricavi_noiva") or 0),
            altri_costi_fb=float(s.get("altri_costi_fb") or 0),
            altri_costi_spese=float(s.get("altri_costi_spese") or 0),
            costo_dipendenti=float(s.get("costo_dipendenti") or 0),
            costo_personale_extra=float(s.get("costo_personale_extra") or 0),
            costi_fb_auto=float(costi_fb_auto.get(m, 0)),
            costi_spese_auto=float(costi_spese_auto.get(m, 0)),
            quote_riparto_fb=float(s.get("quote_riparto_fb") or 0),
            quote_riparto_spese=float(s.get("quote_riparto_spese") or 0),
        ))

    return MarginiAnnoResponse(anno=anno, mesi=mesi)


@router.post("/api/margini", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def save_margini(
    body: SalvaMarginiRequest,
    authorization: Optional[str] = Header(None),
):
    from datetime import datetime as _dt, timezone as _tz
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        ex_resp = (
            sb.table("margini_mensili")
            .select("mese,fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci,quote_riparto_fb,quote_riparto_spese")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", body.anno)
            .execute()
        )
        existing_centri = {int(r["mese"]): r for r in (ex_resp.data or [])}
    except Exception:
        existing_centri = {}

    now_iso = _dt.now(_tz.utc).isoformat()
    records = []
    for m in body.mesi:
        if not 1 <= m.mese <= 12:
            continue
        ec = existing_centri.get(m.mese, {})
        # Quote riparto: mai dal body (l'utente non le edita qui), sempre dal DB.
        # Vanno nel MOL come addendo ai costi auto/manuali E ri-scritte invariate
        # nel record, altrimenti il bulk-upsert postgrest le azzererebbe.
        q_fb = float(ec.get("quote_riparto_fb") or 0)
        q_spese = float(ec.get("quote_riparto_spese") or 0)
        fatt_netto = (m.fatturato_iva10 / 1.10) + (m.fatturato_iva22 / 1.22) + m.altri_ricavi_noiva
        costi_fb_tot = m.costi_fb_auto + m.altri_costi_fb + q_fb
        costi_spese_tot = m.costi_spese_auto + m.altri_costi_spese + q_spese
        costi_pers = m.costo_dipendenti + m.costo_personale_extra
        primo_margine = fatt_netto - costi_fb_tot
        mol = primo_margine - costi_spese_tot - costi_pers
        fn = fatt_netto if fatt_netto > 0 else 1.0
        records.append({
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "anno": body.anno,
            "mese": m.mese,
            "fatturato_iva10": m.fatturato_iva10,
            "fatturato_iva22": m.fatturato_iva22,
            "altri_ricavi_noiva": m.altri_ricavi_noiva,
            "altri_costi_fb": m.altri_costi_fb,
            "altri_costi_spese": m.altri_costi_spese,
            "costo_dipendenti": m.costo_dipendenti,
            "costo_personale_extra": m.costo_personale_extra,
            "costi_fb_auto": m.costi_fb_auto,
            "costi_spese_auto": m.costi_spese_auto,
            "quote_riparto_fb": q_fb,
            "quote_riparto_spese": q_spese,
            "fatturato_netto": round(fatt_netto, 2),
            "costi_fb_totali": round(costi_fb_tot, 2),
            "primo_margine": round(primo_margine, 2),
            "mol": round(mol, 2),
            "food_cost_perc": round(costi_fb_tot / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "spese_perc": round(costi_spese_tot / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "personale_perc": round(costi_pers / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "mol_perc": round(mol / fn * 100, 2) if fatt_netto > 0 else 0.0,
            "fatturato_food": float(ec.get("fatturato_food") or 0),
            "fatturato_beverage": float(ec.get("fatturato_beverage") or 0),
            "fatturato_alcolici": float(ec.get("fatturato_alcolici") or 0),
            "fatturato_dolci": float(ec.get("fatturato_dolci") or 0),
            "updated_at": now_iso,
        })

    sb.table("margini_mensili").upsert(records, on_conflict="ristorante_id,anno,mese").execute()
    # Il briefing Home racconta i dati mensili (fatturato/costi): cambiandoli va
    # invalidato lo snapshot di oggi cosi' la prossima Home rigenera (best-effort).
    from services.daily_briefing_service import invalidate_today_briefing
    invalidate_today_briefing(user_id, ristorante_id, sb)
    # Stessi dati alimentano la card "I tuoi conti" (cache KPI, TTL 2 min): senza
    # questo il MOL restava stantio dopo l'inserimento. Invalidazione esplicita.
    _invalidate_home_kpi_cache(ristorante_id)
    return {"ok": True, "saved": len(records)}


@router.get("/api/margini/fatturato-centri", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_fatturato_centri(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
) -> FatturatoCentriData:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        resp = (
            sb.table("margini_mensili")
            .select("fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", anno)
            .eq("mese", mese)
            .execute()
        )
        row = (resp.data or [{}])[0]
    except Exception:
        row = {}

    return FatturatoCentriData(
        anno=anno, mese=mese,
        fatturato_food=float(row.get("fatturato_food") or 0),
        fatturato_beverage=float(row.get("fatturato_beverage") or 0),
        fatturato_alcolici=float(row.get("fatturato_alcolici") or 0),
        fatturato_dolci=float(row.get("fatturato_dolci") or 0),
    )


@router.post("/api/margini/fatturato-centri", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def save_fatturato_centri(
    body: FatturatoCentriData,
    authorization: Optional[str] = Header(None),
):
    from datetime import datetime as _dt, timezone as _tz
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    sb.table("margini_mensili").upsert({
        "user_id": user_id,
        "ristorante_id": ristorante_id,
        "anno": body.anno,
        "mese": body.mese,
        "fatturato_food": body.fatturato_food,
        "fatturato_beverage": body.fatturato_beverage,
        "fatturato_alcolici": body.fatturato_alcolici,
        "fatturato_dolci": body.fatturato_dolci,
        "updated_at": _dt.now(_tz.utc).isoformat(),
    }, on_conflict="ristorante_id,anno,mese").execute()
    from services.daily_briefing_service import invalidate_today_briefing
    invalidate_today_briefing(user_id, ristorante_id, sb)
    _invalidate_home_kpi_cache(ristorante_id)
    return {"ok": True}


class FatturatoCentriGiornoItem(BaseModel):
    data: str
    food: float = 0.0
    beverage: float = 0.0
    alcolici: float = 0.0
    dolci: float = 0.0
    shop: float = 0.0


@router.get("/api/margini/fatturato-centri-giorni", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_fatturato_centri_giorni(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
) -> List[FatturatoCentriGiornoItem]:
    """Fatturato giornaliero stimato per centro.

    Non esiste uno split per singolo giorno: la ripartizione è mensile (% per
    centro su margini_mensili). Il valore giornaliero per centro è derivato
    distribuendo la quota mensile del centro sul fatturato netto di ogni giorno.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    from calendar import monthrange
    mese_str = f"{mese:02d}"
    last_day = monthrange(anno, mese)[1]
    data_da = f"{anno}-{mese_str}-01"
    data_a = f"{anno}-{mese_str}-{last_day:02d}"

    # Ricavi giornalieri → netto per giorno
    ric_resp = (
        sb.table("ricavi_giornalieri")
        .select("data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
        .eq("ristorante_id", ristorante_id)
        .gte("data", data_da)
        .lte("data", data_a)
        .order("data", desc=False)
        .execute()
    )
    netto_per_giorno: Dict[str, float] = {}
    for r in (ric_resp.data or []):
        netto_per_giorno[str(r.get("data"))] = _calc_netto(
            float(r.get("fatturato_iva10") or 0),
            float(r.get("fatturato_iva22") or 0),
            float(r.get("altri_ricavi_noiva") or 0),
        )
    netto_mese = sum(netto_per_giorno.values())
    if netto_mese <= 0:
        return []

    # Quote mensili per centro (euro) → frazione sul netto del mese
    mc_resp = (
        sb.table("margini_mensili")
        .select("fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    mc = (mc_resp.data or [{}])[0]
    frazioni = {
        "food": float(mc.get("fatturato_food") or 0) / netto_mese,
        "beverage": float(mc.get("fatturato_beverage") or 0) / netto_mese,
        "alcolici": float(mc.get("fatturato_alcolici") or 0) / netto_mese,
        "dolci": float(mc.get("fatturato_dolci") or 0) / netto_mese,
    }

    items: List[FatturatoCentriGiornoItem] = []
    for data_iso, netto_g in sorted(netto_per_giorno.items()):
        items.append(FatturatoCentriGiornoItem(
            data=data_iso,
            food=round(netto_g * frazioni["food"], 2),
            beverage=round(netto_g * frazioni["beverage"], 2),
            alcolici=round(netto_g * frazioni["alcolici"], 2),
            dolci=round(netto_g * frazioni["dolci"], 2),
            shop=0.0,
        ))
    return items


@router.get("/api/margini/analisi-centri", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_analisi_centri(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> AnalisiCentriResponse:
    from datetime import date as _date
    _, _, _, _CENTRI_CON_FATTURATO, _CENTRI_DI_PRODUZIONE = _consts()
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    costi_per_cat = _load_fatture_fb_for_period(sb, ristorante_id, data_da, data_a)

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)
    margini_resp = (
        sb.table("margini_mensili")
        .select("anno,mese,fatturato_netto,fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
        .eq("ristorante_id", ristorante_id)
        .gte("anno", d_da.year)
        .lte("anno", d_a.year)
        .execute()
    )

    fatturato_netto_periodo = 0.0
    fatturato_per_centro: Dict[str, float] = {c: 0.0 for c in _CENTRI_CON_FATTURATO}
    mesi_con_dati: List[int] = []

    for r in (margini_resp.data or []):
        anno_r, mese_r = int(r.get("anno", 0)), int(r.get("mese", 0))
        if not (1 <= mese_r <= 12):
            continue
        row_d = _date(anno_r, mese_r, 1)
        if not (_date(d_da.year, d_da.month, 1) <= row_d <= _date(d_a.year, d_a.month, 1)):
            continue
        fatt = float(r.get("fatturato_netto") or 0)
        fatturato_netto_periodo += fatt
        if fatt > 0:
            mesi_con_dati.append(mese_r)
        for c in _CENTRI_CON_FATTURATO:
            fatturato_per_centro[c] += float(r.get(f"fatturato_{c.lower()}") or 0)

    totale_costi_fb = sum(costi_per_cat.values())
    centri_out = []
    for centro, cats in _CENTRI_DI_PRODUZIONE.items():
        costo = sum(costi_per_cat.get(cat, 0) for cat in cats)
        fatt_c = fatturato_per_centro.get(centro, 0.0)
        margine = fatt_c - costo
        centri_out.append(CentroCostoItem(
            centro=centro,
            categorie=cats,
            costo_totale=round(costo, 2),
            fatturato=round(fatt_c, 2),
            margine=round(margine, 2),
            incidenza_su_fatt=round(costo / fatt_c * 100, 2) if fatt_c > 0 else 0.0,
            incidenza_su_fb=round(costo / totale_costi_fb * 100, 2) if totale_costi_fb > 0 else 0.0,
        ))

    primo_margine = fatturato_netto_periodo - totale_costi_fb
    return AnalisiCentriResponse(
        centri=centri_out,
        totale_costi_fb=round(totale_costi_fb, 2),
        fatturato_netto_periodo=round(fatturato_netto_periodo, 2),
        primo_margine=round(primo_margine, 2),
        primo_margine_pct=round(primo_margine / fatturato_netto_periodo * 100, 2) if fatturato_netto_periodo > 0 else 0.0,
        mesi_con_dati=sorted(set(mesi_con_dati)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# ANALISI AVANZATA CENTRI — drill-down categorie + andamento mensile + commenti
# ═══════════════════════════════════════════════════════════════════════════

_ICONE_CENTRI = {"FOOD": "🍖", "BEVERAGE": "☕", "ALCOLICI": "🍷", "DOLCI": "🍰", "SHOP": "🛒"}


class CategoriaDetail(BaseModel):
    categoria: str
    costo: float
    pct_su_centro: float


class CentroDetailItem(BaseModel):
    centro: str
    icona: str
    categorie_def: List[str]
    categorie_dettaglio: List[CategoriaDetail]
    costo_totale: float
    fatturato: float
    margine: float
    margine_pct: float
    incidenza_su_fatt: float
    incidenza_su_fb: float
    has_fatturato: bool


class AndamentoMese(BaseModel):
    anno: int
    mese: int
    label: str
    food: float
    beverage: float
    alcolici: float
    dolci: float
    shop: float


class CommentoKpi(BaseModel):
    kpi_nome: str
    percentuale: str
    commento: str
    emoji: str
    colore: str


class AnalisiAvanzataResponse(BaseModel):
    centri: List[CentroDetailItem]
    andamento_mensile: List[AndamentoMese]
    commenti: List[CommentoKpi]
    totale_costi_fb: float
    fatturato_netto_periodo: float
    fatturato_per_centro_totale: float
    primo_margine: float
    primo_margine_pct: float
    fatturato_split_attivo: bool
    mesi_con_dati: List[int]


@router.get("/api/margini/analisi-avanzata", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_analisi_avanzata(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> AnalisiAvanzataResponse:
    from datetime import date as _date
    _, _, _CAT_TO_CENTRO, _CENTRI_CON_FATTURATO, _CENTRI_DI_PRODUZIONE = _consts()
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)

    # Lista (anno, mese) target
    mesi_target = []
    y, m = d_da.year, d_da.month
    while (y, m) <= (d_a.year, d_a.month):
        mesi_target.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    # Costi mensili per categoria
    costi_map = _load_fatture_fb_per_categoria_e_mese(sb, ristorante_id, data_da, data_a)

    # Aggregato per categoria periodo
    costi_per_cat: Dict[str, float] = {}
    for (_a, _m, cat), tot in costi_map.items():
        costi_per_cat[cat] = costi_per_cat.get(cat, 0) + tot

    # Carica margini_mensili per ricavi e split centri
    annos = sorted({y for y, _ in mesi_target})
    margini_resp = (
        sb.table("margini_mensili")
        .select("anno,mese,fatturato_netto,fatturato_food,fatturato_beverage,fatturato_alcolici,fatturato_dolci")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )

    mensile_overrides = _load_mensile_overrides(sb, ristorante_id, annos)

    fatturato_netto_periodo = 0.0
    fatturato_per_centro: Dict[str, float] = {c: 0.0 for c in _CENTRI_CON_FATTURATO}
    mesi_con_dati: List[int] = []
    split_attivo = False

    mesi_target_set = {(y, m) for y, m in mesi_target}
    margini_map = {}
    for r in (margini_resp.data or []):
        anno_r = int(r.get("anno", 0))
        mese_r = int(r.get("mese", 0))
        if (anno_r, mese_r) in mesi_target_set:
            margini_map[(anno_r, mese_r)] = r
            ov = mensile_overrides.get((anno_r, mese_r))
            fatt = _calc_netto(ov["iva10"], ov["iva22"], ov["altri"]) if ov else float(r.get("fatturato_netto") or 0)
            fatturato_netto_periodo += fatt
            if fatt > 0:
                mesi_con_dati.append(mese_r)
            for c in _CENTRI_CON_FATTURATO:
                v = float(r.get(f"fatturato_{c.lower()}") or 0)
                fatturato_per_centro[c] += v
                if v > 0:
                    split_attivo = True

    fatturato_per_centro_tot = sum(fatturato_per_centro.values())
    totale_costi_fb = sum(costi_per_cat.values())

    # Costruisci CentroDetailItem
    centri_out: List[CentroDetailItem] = []
    for centro, cats in _CENTRI_DI_PRODUZIONE.items():
        costo = sum(costi_per_cat.get(cat, 0) for cat in cats)
        fatt_c = fatturato_per_centro.get(centro, 0.0)
        has_fatt = centro in _CENTRI_CON_FATTURATO and split_attivo and fatt_c > 0
        margine = fatt_c - costo if has_fatt else 0.0
        margine_pct = (margine / fatt_c * 100) if fatt_c > 0 else 0.0
        incidenza = (costo / fatt_c * 100) if fatt_c > 0 else 0.0
        # Per centri senza fatt proprio: % su fatturato totale split
        if not has_fatt and fatturato_per_centro_tot > 0:
            incidenza = (costo / fatturato_per_centro_tot * 100)

        # Categorie con dettaglio
        cat_details = []
        for cat in cats:
            c_cost = costi_per_cat.get(cat, 0)
            if c_cost > 0:
                cat_details.append(CategoriaDetail(
                    categoria=cat,
                    costo=round(c_cost, 2),
                    pct_su_centro=round(c_cost / costo * 100, 2) if costo > 0 else 0.0,
                ))
        cat_details.sort(key=lambda x: x.costo, reverse=True)

        centri_out.append(CentroDetailItem(
            centro=centro,
            icona=_ICONE_CENTRI.get(centro, "📁"),
            categorie_def=cats,
            categorie_dettaglio=cat_details,
            costo_totale=round(costo, 2),
            fatturato=round(fatt_c, 2),
            margine=round(margine, 2),
            margine_pct=round(margine_pct, 2),
            incidenza_su_fatt=round(incidenza, 2),
            incidenza_su_fb=round(costo / totale_costi_fb * 100, 2) if totale_costi_fb > 0 else 0.0,
            has_fatturato=has_fatt,
        ))

    primo_margine = fatturato_netto_periodo - totale_costi_fb
    primo_margine_pct = (primo_margine / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0

    # Andamento mensile per centro
    andamento: List[AndamentoMese] = []
    MESI_NOMI_BR = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    for (yy, mm) in mesi_target:
        costi_centri = {c: 0.0 for c in _CENTRI_DI_PRODUZIONE.keys()}
        for (a2, m2, cat), tot in costi_map.items():
            if a2 == yy and m2 == mm:
                centro_n = _CAT_TO_CENTRO.get(cat)
                if centro_n:
                    costi_centri[centro_n] += tot
        andamento.append(AndamentoMese(
            anno=yy, mese=mm, label=f"{MESI_NOMI_BR[mm-1]} {yy}",
            food=round(costi_centri.get("FOOD", 0), 2),
            beverage=round(costi_centri.get("BEVERAGE", 0), 2),
            alcolici=round(costi_centri.get("ALCOLICI", 0), 2),
            dolci=round(costi_centri.get("DOLCI", 0), 2),
            shop=round(costi_centri.get("SHOP", 0), 2),
        ))

    # Commenti automatici per centro
    commenti: List[CommentoKpi] = []
    for c in centri_out:
        if not c.has_fatturato or c.costo_totale == 0:
            continue
        fc = c.incidenza_su_fatt
        emoji, testo = _valuta_soglia_margine(fc, "food_cost", crescente=True)
        commenti.append(CommentoKpi(
            kpi_nome=f"{c.icona} {c.centro} — Incidenza costi",
            percentuale=f"{fc:.1f}%",
            commento=testo,
            emoji=emoji,
            colore=_COLORI_EMOJI.get(emoji, "#6b7280"),
        ))

    # Centro più performante / meno performante
    centri_con_fatt = [c for c in centri_out if c.has_fatturato and c.fatturato > 0]
    if centri_con_fatt:
        best = max(centri_con_fatt, key=lambda x: x.margine_pct)
        worst = min(centri_con_fatt, key=lambda x: x.margine_pct)
        if best.centro != worst.centro:
            commenti.append(CommentoKpi(
                kpi_nome=f"{best.icona} Centro più performante",
                percentuale=f"{best.margine_pct:.1f}%",
                commento=f"{best.centro} ha il margine % più alto del periodo",
                emoji="🟢",
                colore=_COLORI_EMOJI["🟢"],
            ))
            commenti.append(CommentoKpi(
                kpi_nome=f"{worst.icona} Centro più critico",
                percentuale=f"{worst.margine_pct:.1f}%",
                commento=f"{worst.centro} ha il margine % più basso — verificare costi e prezzi",
                emoji="🔴",
                colore=_COLORI_EMOJI["🔴"],
            ))

    return AnalisiAvanzataResponse(
        centri=centri_out,
        andamento_mensile=andamento,
        commenti=commenti,
        totale_costi_fb=round(totale_costi_fb, 2),
        fatturato_netto_periodo=round(fatturato_netto_periodo, 2),
        fatturato_per_centro_totale=round(fatturato_per_centro_tot, 2),
        primo_margine=round(primo_margine, 2),
        primo_margine_pct=round(primo_margine_pct, 2),
        fatturato_split_attivo=split_attivo,
        mesi_con_dati=sorted(set(mesi_con_dati)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# MARGINI — analisi completa per periodo + cell update + commenti
# ═══════════════════════════════════════════════════════════════════════════

_KPI_SOGLIE_MARGINI = {
    "food_cost": [
        (28, "🟢", "Food cost eccellente — ottimo controllo acquisti e sprechi"),
        (33, "🟡", "Food cost nella norma per il settore ristorazione"),
        (38, "🟠", "Food cost sopra la media — valutare ottimizzazione acquisti o menù"),
        (100, "🔴", "Food cost critico — necessaria revisione fornitori, porzioni e sprechi"),
    ],
    "spese_generali": [
        (15, "🟢", "Spese generali contenute — gestione efficiente"),
        (22, "🟡", "Spese generali nella norma"),
        (28, "🟠", "Spese generali elevate — verificare utenze e contratti"),
        (100, "🔴", "Spese generali fuori controllo — necessaria rinegoziazione"),
    ],
    "personale": [
        (24, "🟢", "Costo del lavoro contenuto — buona efficienza del personale"),
        (30, "🟡", "Costo del lavoro nella norma per il settore"),
        (35, "🟠", "Costo del lavoro elevato — verificare turni, produttività e coperti"),
        (100, "🔴", "Costo del lavoro critico — incidenza troppo alta sul fatturato"),
    ],
    "primo_margine": [
        (55, "🔴", "1° Margine molto basso — costi F&B troppo alti rispetto al fatturato"),
        (62, "🟠", "1° Margine sotto la media — margine di miglioramento sui costi"),
        (70, "🟡", "1° Margine nella norma per il settore"),
        (200, "🟢", "1° Margine eccellente — ottima marginalità sui prodotti"),
    ],
    "mol": [
        (5, "🔴", "MOL critico — l'attività non genera margine sufficiente"),
        (12, "🟠", "MOL basso — necessario contenere costi o incrementare ricavi"),
        (20, "🟡", "MOL nella norma — margine operativo adeguato"),
        (200, "🟢", "MOL eccellente — ottima redditività operativa"),
    ],
}

_COLORI_EMOJI = {"🟢": "#16a34a", "🟡": "#ca8a04", "🟠": "#ea580c", "🔴": "#dc2626", "ℹ️": "#2563eb"}

_CELL_FIELDS_EDITABILI = {
    "altri_costi_fb", "altri_costi_spese", "costo_dipendenti", "costo_personale_extra",
}


def _valuta_soglia_margine(valore: float, key: str, crescente: bool = True) -> tuple:
    soglie = _KPI_SOGLIE_MARGINI.get(key, [])
    if not soglie:
        return ("ℹ️", "")
    for soglia, emoji, testo in soglie:
        if valore <= soglia:
            return (emoji, testo)
    return (soglie[-1][1], soglie[-1][2])


class MarginiCellaRequest(BaseModel):
    anno: int = Field(..., ge=2000, le=2100)
    mese: int = Field(..., ge=1, le=12)
    field: str
    value: float


class MarginiCellaResponse(BaseModel):
    anno: int
    mese: int
    field: str
    value: float


class MesiPivot(BaseModel):
    anno: int
    mese: int
    label: str
    fatturato_iva10: float
    fatturato_iva22: float
    altri_ricavi_noiva: float
    fatturato_netto: float
    costi_fb_auto: float
    altri_costi_fb: float
    costi_fb_totali: float
    primo_margine: float
    costi_spese_auto: float
    altri_costi_spese: float
    costi_spese_totali: float
    costo_dipendenti: float
    costo_personale_extra: float
    costi_personale: float
    mol: float


class MarginiAnalisiResponse(BaseModel):
    mesi: List[MesiPivot]
    totali: MesiPivot
    fatt_medio_mensile: float
    food_cost_perc: float
    primo_margine_perc: float
    spese_gen_perc: float
    personale_perc: float
    mol_perc: float
    num_mesi_attivi: int
    commenti: List[CommentoKpi]


@router.post("/api/margini/cella", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def update_margini_cella(
    body: MarginiCellaRequest,
    authorization: Optional[str] = Header(None),
) -> MarginiCellaResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if body.field not in _CELL_FIELDS_EDITABILI:
        raise HTTPException(status_code=400, detail=f"Field non editable: {body.field}")

    val = max(0.0, float(body.value))

    # Upsert preservando altri campi: prima leggi riga esistente, poi update
    existing = (
        sb.table("margini_mensili")
        .select("*")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", body.anno)
        .eq("mese", body.mese)
        .limit(1)
        .execute()
    )

    if existing.data:
        sb.table("margini_mensili").update({
            body.field: val,
            "updated_at": "now()",
        }).eq("ristorante_id", ristorante_id).eq("anno", body.anno).eq("mese", body.mese).execute()
    else:
        new_row = {
            "user_id": user["id"],
            "ristorante_id": ristorante_id,
            "anno": body.anno,
            "mese": body.mese,
            body.field: val,
        }
        sb.table("margini_mensili").insert(new_row).execute()

    return MarginiCellaResponse(anno=body.anno, mese=body.mese, field=body.field, value=val)


@router.get("/api/margini/costo-personale-turni", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_costo_personale_da_turni(
    anno: int = Query(..., ge=2000, le=2100),
    mese: int = Query(..., ge=1, le=12),
    authorization: Optional[str] = Header(None),
):
    """Calcola il costo del personale del mese dai turni (tab Personale).
    Restituisce lo split in EURO coerente con margini_mensili:
      - costo_dipendenti       = Σ((ore_turno − ore_extra) × costo_orario)
      - costo_personale_extra  = Σ(ore_extra × costo_orario)
    I turni senza costo_orario impostato non contribuiscono (vengono contati a parte)."""
    from calendar import monthrange
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    last_day = monthrange(anno, mese)[1]
    data_da = f"{anno}-{mese:02d}-01"
    data_a = f"{anno}-{mese:02d}-{last_day:02d}"

    turni = (
        sb.table("turni_personale").select("*")
        .eq("ristorante_id", ristorante_id)
        .gte("data_turno", data_da).lte("data_turno", data_a)
        .execute()
    ).data or []

    costo_dipendenti = 0.0
    costo_personale_extra = 0.0
    ore_totali = 0.0
    ore_extra_tot = 0.0
    n_turni = len(turni)
    n_senza_costo = 0
    for t in turni:
        ore = _ore_turno(t)                     # totale: orari + extra (giorn.) o ore_dichiarate (mensile)
        extra = float(t.get("ore_extra") or 0)
        extra = min(extra, ore)                  # difensivo: extra non può eccedere il totale
        ore_totali += ore
        ore_extra_tot += extra
        if t.get("mensile"):
            # Riga mensile (busta paga): costo reale da lordo, non da tariffa.
            # L'esclusivita' giornaliero/mensile per dipendente/mese garantisce
            # che non si sommi mai al ramo giornaliero.
            lordo = float(t.get("lordo_mensile") or 0)
            imp_ext = float(t.get("importo_extra") or 0)
            costo_personale_extra += imp_ext
            costo_dipendenti += max(0.0, lordo - imp_ext)
            continue
        co = t.get("costo_orario")
        if co is None:
            n_senza_costo += 1
            continue
        co = float(co)
        # Le ore extra usano costo_orario_extra se impostato, altrimenti il costo standard.
        co_ext = t.get("costo_orario_extra")
        co_ext = float(co_ext) if co_ext is not None else co
        costo_personale_extra += extra * co_ext
        costo_dipendenti += (ore - extra) * co

    return {
        "anno": anno,
        "mese": mese,
        "costo_dipendenti": round(costo_dipendenti, 2),
        "costo_personale_extra": round(costo_personale_extra, 2),
        "ore_totali": round(ore_totali, 2),
        "ore_extra": round(ore_extra_tot, 2),
        "n_turni": n_turni,
        "n_senza_costo": n_senza_costo,
    }


@router.get("/api/margini/costo-spese-extra", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_costo_spese_da_voci(
    anno: int = Query(..., ge=2000, le=2100),
    mese: int = Query(..., ge=1, le=12),
    authorization: Optional[str] = Header(None),
):
    """Aggrega le voci di spesa extra (tab Spese) del mese, separate per tipo,
    coerenti con le celle editabili di margini_mensili:
      - totale_fb        -> altri_costi_fb
      - totale_generale  -> altri_costi_spese"""
    from calendar import monthrange
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    last_day = monthrange(anno, mese)[1]
    data_da = f"{anno}-{mese:02d}-01"
    data_a = f"{anno}-{mese:02d}-{last_day:02d}"

    voci = (
        sb.table("spese_extra").select("tipo,importo")
        .eq("ristorante_id", ristorante_id)
        .gte("data_spesa", data_da).lte("data_spesa", data_a)
        .execute()
    ).data or []

    totale_fb = 0.0
    totale_generale = 0.0
    n_fb = 0
    n_generale = 0
    for v in voci:
        importo = float(v.get("importo") or 0)
        if v.get("tipo") == "fb":
            totale_fb += importo
            n_fb += 1
        elif v.get("tipo") == "generale":
            totale_generale += importo
            n_generale += 1

    return {
        "anno": anno,
        "mese": mese,
        "totale_fb": round(totale_fb, 2),
        "totale_generale": round(totale_generale, 2),
        "n_voci_fb": n_fb,
        "n_voci_generale": n_generale,
    }


@router.get("/api/margini/analisi", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_margini_analisi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> MarginiAnalisiResponse:
    from datetime import date as _date
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)

    # Costruisci lista (anno, mese) in range
    mesi_target = []
    y, m = d_da.year, d_da.month
    while (y, m) <= (d_a.year, d_a.month):
        mesi_target.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    # Carica margini_mensili (manuali + ricavi sincronizzati)
    annos = sorted({y for y, _ in mesi_target})
    margini_resp = (
        sb.table("margini_mensili")
        .select("*")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    margini_map = {(int(r["anno"]), int(r["mese"])): r for r in (margini_resp.data or [])}
    mensile_overrides = _load_mensile_overrides(sb, ristorante_id, annos)

    # Costi auto F&B/Spese di tutti i mesi in UNA passata (era N+1: 1 scansione
    # fatture per mese -> 12 round-trip per un anno).
    costi_auto_map = _calcola_costi_auto_per_periodo(sb, ristorante_id, mesi_target)

    mesi_pivot: List[MesiPivot] = []
    for (y, m) in mesi_target:
        r = margini_map.get((y, m), {})
        fb_auto, spese_auto = costi_auto_map.get((y, m), (0.0, 0.0))

        ov = mensile_overrides.get((y, m))
        iva10 = ov["iva10"] if ov else float(r.get("fatturato_iva10") or 0)
        iva22 = ov["iva22"] if ov else float(r.get("fatturato_iva22") or 0)
        altri = ov["altri"] if ov else float(r.get("altri_ricavi_noiva") or 0)
        netto = (iva10 / 1.10) + (iva22 / 1.22) + altri

        altri_fb = float(r.get("altri_costi_fb") or 0)
        altri_sp = float(r.get("altri_costi_spese") or 0)
        cd = float(r.get("costo_dipendenti") or 0)
        cpe = float(r.get("costo_personale_extra") or 0)
        # Quote dei costi di gruppo ripartiti su questa sede (modalità catena):
        # vanno sommate ai costi F&B/spese come già fa GET /api/margini, altrimenti
        # tabella-analisi e KPI mostrerebbero un MOL diverso dal conto economico.
        q_fb = float(r.get("quote_riparto_fb") or 0)
        q_spese = float(r.get("quote_riparto_spese") or 0)

        fb_tot = fb_auto + altri_fb + q_fb
        sp_tot = spese_auto + altri_sp + q_spese
        pers = cd + cpe
        pm = netto - fb_tot
        mol_v = pm - sp_tot - pers

        MESI_NOMI_BR = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
        mesi_pivot.append(MesiPivot(
            anno=y, mese=m, label=f"{MESI_NOMI_BR[m-1]} {y}",
            fatturato_iva10=round(iva10, 2),
            fatturato_iva22=round(iva22, 2),
            altri_ricavi_noiva=round(altri, 2),
            fatturato_netto=round(netto, 2),
            costi_fb_auto=fb_auto,
            altri_costi_fb=round(altri_fb, 2),
            costi_fb_totali=round(fb_tot, 2),
            primo_margine=round(pm, 2),
            costi_spese_auto=spese_auto,
            altri_costi_spese=round(altri_sp, 2),
            costi_spese_totali=round(sp_tot, 2),
            costo_dipendenti=round(cd, 2),
            costo_personale_extra=round(cpe, 2),
            costi_personale=round(pers, 2),
            mol=round(mol_v, 2),
        ))

    # Totali periodo
    tot_iva10 = sum(p.fatturato_iva10 for p in mesi_pivot)
    tot_iva22 = sum(p.fatturato_iva22 for p in mesi_pivot)
    tot_altri = sum(p.altri_ricavi_noiva for p in mesi_pivot)
    tot_netto = sum(p.fatturato_netto for p in mesi_pivot)
    tot_fb_auto = sum(p.costi_fb_auto for p in mesi_pivot)
    tot_altri_fb = sum(p.altri_costi_fb for p in mesi_pivot)
    tot_fb_totali = sum(p.costi_fb_totali for p in mesi_pivot)
    tot_pm = sum(p.primo_margine for p in mesi_pivot)
    tot_spese_auto = sum(p.costi_spese_auto for p in mesi_pivot)
    tot_altri_spese = sum(p.altri_costi_spese for p in mesi_pivot)
    tot_spese_totali = sum(p.costi_spese_totali for p in mesi_pivot)
    tot_cd = sum(p.costo_dipendenti for p in mesi_pivot)
    tot_cpe = sum(p.costo_personale_extra for p in mesi_pivot)
    tot_pers = sum(p.costi_personale for p in mesi_pivot)
    tot_mol = sum(p.mol for p in mesi_pivot)

    totali = MesiPivot(
        anno=0, mese=0, label="Totale periodo",
        fatturato_iva10=round(tot_iva10, 2), fatturato_iva22=round(tot_iva22, 2),
        altri_ricavi_noiva=round(tot_altri, 2), fatturato_netto=round(tot_netto, 2),
        costi_fb_auto=round(tot_fb_auto, 2), altri_costi_fb=round(tot_altri_fb, 2),
        costi_fb_totali=round(tot_fb_totali, 2), primo_margine=round(tot_pm, 2),
        costi_spese_auto=round(tot_spese_auto, 2), altri_costi_spese=round(tot_altri_spese, 2),
        costi_spese_totali=round(tot_spese_totali, 2),
        costo_dipendenti=round(tot_cd, 2), costo_personale_extra=round(tot_cpe, 2),
        costi_personale=round(tot_pers, 2), mol=round(tot_mol, 2),
    )

    # KPI medie sui mesi attivi (fatturato > 0)
    mesi_attivi = [p for p in mesi_pivot if p.fatturato_netto > 0]
    n_attivi = len(mesi_attivi)

    if n_attivi > 0:
        fatt_medio = sum(p.fatturato_netto for p in mesi_attivi) / n_attivi
        fc_perc = (tot_fb_totali / tot_netto * 100) if tot_netto > 0 else 0.0
        pm_perc = (tot_pm / tot_netto * 100) if tot_netto > 0 else 0.0
        sg_perc = (tot_spese_totali / tot_netto * 100) if tot_netto > 0 else 0.0
        pers_perc = (tot_pers / tot_netto * 100) if tot_netto > 0 else 0.0
        mol_perc = (tot_mol / tot_netto * 100) if tot_netto > 0 else 0.0
    else:
        fatt_medio = 0.0
        fc_perc = pm_perc = sg_perc = pers_perc = mol_perc = 0.0

    # Commenti automatici
    commenti: List[CommentoKpi] = []
    if n_attivi > 0:
        for key, val, crescente, nome in [
            ("food_cost", fc_perc, True, "Food Cost"),
            ("primo_margine", pm_perc, False, "1° Margine"),
            ("spese_generali", sg_perc, True, "Spese Generali"),
            ("personale", pers_perc, True, "Costo del Lavoro"),
            ("mol", mol_perc, False, "MOL"),
        ]:
            emoji, testo = _valuta_soglia_margine(val, key, crescente)
            commenti.append(CommentoKpi(
                kpi_nome=nome,
                percentuale=f"{val:.1f}%",
                commento=testo,
                emoji=emoji,
                colore=_COLORI_EMOJI.get(emoji, "#6b7280"),
            ))

    return MarginiAnalisiResponse(
        mesi=mesi_pivot,
        totali=totali,
        fatt_medio_mensile=round(fatt_medio, 2),
        food_cost_perc=round(fc_perc, 2),
        primo_margine_perc=round(pm_perc, 2),
        spese_gen_perc=round(sg_perc, 2),
        personale_perc=round(pers_perc, 2),
        mol_perc=round(mol_perc, 2),
        num_mesi_attivi=n_attivi,
        commenti=commenti,
    )


# ═══════════════════════════════════════════════════════════════════════════
# KPI condivisi (hub Ricavi e Margini) — 6 metriche + delta vs periodo prec.
# ═══════════════════════════════════════════════════════════════════════════

class MarginiKpiResponse(BaseModel):
    fatturato_lordo: float
    fatturato_netto: float
    costi_fb: float
    primo_margine: float
    spese_generali: float
    costo_personale: float
    mol: float
    food_cost_perc: float
    primo_margine_perc: float
    spese_perc: float
    personale_perc: float
    mol_perc: float
    delta_lordo_pct: Optional[float] = None
    delta_fb_pct: Optional[float] = None
    delta_margine_pct: Optional[float] = None
    delta_spese_pct: Optional[float] = None
    delta_personale_pct: Optional[float] = None
    delta_mol_pct: Optional[float] = None
    confronto_label: str
    spark_lordo: List[float] = []
    spark_fb: List[float] = []
    spark_margine: List[float] = []
    spark_spese: List[float] = []
    spark_personale: List[float] = []
    spark_mol: List[float] = []


@router.get("/api/margini/kpi", tags=["Marginalità"], dependencies=[Depends(_verify_worker_key)])
def get_margini_kpi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> MarginiKpiResponse:
    from datetime import date as _date, timedelta as _timedelta
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    d_da = _date.fromisoformat(data_da)
    d_a = _date.fromisoformat(data_a)
    cur = _aggrega_mensili_margini(sb, ristorante_id, d_da, d_a)

    netto = cur["netto"]
    return MarginiKpiResponse(
        fatturato_lordo=round(cur["lordo"], 2),
        fatturato_netto=round(cur["netto"], 2),
        costi_fb=round(cur["fb"], 2),
        primo_margine=round(cur["pm"], 2),
        spese_generali=round(cur["spese"], 2),
        costo_personale=round(cur["pers"], 2),
        mol=round(cur["mol"], 2),
        food_cost_perc=round(cur["fb"] / netto * 100, 1) if netto > 0 else 0.0,
        primo_margine_perc=round(cur["pm"] / netto * 100, 1) if netto > 0 else 0.0,
        spese_perc=round(cur["spese"] / netto * 100, 1) if netto > 0 else 0.0,
        personale_perc=round(cur["pers"] / netto * 100, 1) if netto > 0 else 0.0,
        mol_perc=round(cur["mol"] / netto * 100, 1) if netto > 0 else 0.0,
        confronto_label="",
        spark_lordo=cur["spark_lordo"],
        spark_fb=cur["spark_fb"],
        spark_margine=cur["spark_margine"],
        spark_spese=cur["spark_spese"],
        spark_personale=cur["spark_personale"],
        spark_mol=cur["spark_mol"],
    )
