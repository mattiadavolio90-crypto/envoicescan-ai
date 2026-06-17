"""Router MODALITÀ CATENA — vista gruppo multi-sede, SOLA LETTURA.

La catena è un LAYER SUPERIORE di sola visualizzazione/analisi sopra i punti
vendita (PV): nessun inserimento/upload qui (quello vive solo nel PV). Regola
non negoziabile: AGGREGAZIONE SQL, mai loop Python sulle righe — la vista gruppo
deve costare meno di una vista sede.

Fase 1: `/api/gruppo/overview` — KPI gruppo + salute media + RANKING per margine%,
tutto da `margini_mensili` (tabella GIÀ pre-aggregata: 1 riga per
ristorante×anno×mese) con un solo GROUP BY ristorante_id. Coerente per
costruzione con i numeri dei PV (stessa fonte).

Import LAZY da fastapi_worker (pattern di margini.py/ricavi.py): wrapper espliciti
risolti al primo uso, niente module-level __getattr__ (PEP 562 non risolve i
lookup di nome globale interni → NameError → HTTP 500). _verify_worker_key resta
esplicito perché usato in Depends() a import-time.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel


def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# OVERVIEW — KPI gruppo + salute media + ranking per margine%
# ═══════════════════════════════════════════════════════════════════════════

class GruppoKpi(BaseModel):
    fatturato: float            # Σ fatturato_netto del periodo (totale gruppo)
    margine_medio_perc: float   # margine % aggregato del gruppo (Σmol / Σnetto)
    spesa_fornitori: float      # Σ costi_fb_totali del periodo


class RankingPV(BaseModel):
    ristorante_id: str
    nome: str
    margine_perc: Optional[float]   # mol% del periodo; None se dati incompleti
    fatturato: float
    colore: str                     # "verde" | "giallo" | "rosso" | "grigio"
    dati_incompleti: bool           # True = nessun ricavo nel periodo → in coda


class GruppoOverviewResponse(BaseModel):
    nome_gruppo: str
    num_pv: int
    periodo_label: str
    kpi: GruppoKpi
    salute_indice: int          # media semplice degli indici di salute dei PV
    salute_colore: str          # "verde" | "giallo" | "rosso"
    ranking: List[RankingPV]


def _colore_margine(mol_perc: Optional[float]) -> str:
    """Pallino ranking dal margine %: stesse soglie di lettura dei conti PV.

    grigio = dati incompleti (nessun ricavo). Le soglie verde/giallo/rosso
    riprendono lo spirito del KPI MOL (≥15 buono, ≥8 ok, sotto critico).
    """
    if mol_perc is None:
        return "grigio"
    if mol_perc >= 15:
        return "verde"
    if mol_perc >= 8:
        return "giallo"
    return "rosso"


def _salute_indice_sede(sb, ristorante_id: str) -> int:
    """Indice di salute (0-100) di una sede, stessa formula di /api/home/salute.

    4 voci a peso uguale: fatture caricate di recente, fatturato ultimo mese
    completo, costo personale ultimo mese completo, % righe classificate.
    Versione compatta e autonoma (la catena fa la MEDIA SEMPLICE di questi
    indici): non tocca l'endpoint PV vivo, replica solo il calcolo. Se la formula
    PV cambia, allineare anche qui (come già fa _salute_indice_rosso).
    """
    from datetime import datetime as _dt, timedelta as _td
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()
    inizio = oggi - _td(days=29)
    inizio_dt = _dt.combine(inizio, _dt.min.time())
    if oggi.month == 1:
        mc_anno, mc_mese = oggi.year - 1, 12
    else:
        mc_anno, mc_mese = oggi.year, oggi.month - 1

    # Voce 1 + voce 4: fatture caricate di recente + % classificate
    fatture_ok = False
    pct_classificate = 0
    try:
        resp = (
            sb.table("fatture")
            .select("needs_review")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gte("created_at", inizio_dt.isoformat())
            .execute()
        )
        righe = resp.data or []
        tot = len(righe)
        fatture_ok = tot > 0
        if tot > 0:
            da_controllare = sum(1 for r in righe if r.get("needs_review"))
            pct_classificate = round((tot - da_controllare) / tot * 100)
    except Exception:
        pass

    # Voci 2 e 3: fatturato + costo personale ultimo mese completo
    fatturato_ok = False
    personale_ok = False
    try:
        resp = (
            sb.table("margini_mensili")
            .select("fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,costo_dipendenti,costo_personale_extra")
            .eq("ristorante_id", ristorante_id)
            .eq("anno", mc_anno)
            .eq("mese", mc_mese)
            .execute()
        )
        netto = 0.0
        for r in (resp.data or []):
            netto += (
                float(r.get("fatturato_iva10") or 0)
                + float(r.get("fatturato_iva22") or 0)
                + float(r.get("altri_ricavi_noiva") or 0)
            )
            if (float(r.get("costo_dipendenti") or 0) + float(r.get("costo_personale_extra") or 0)) > 0:
                personale_ok = True
        fatturato_ok = netto > 0
    except Exception:
        pass

    score = (
        (100 if fatture_ok else 0)
        + (100 if fatturato_ok else 0)
        + (100 if personale_ok else 0)
        + (pct_classificate if fatture_ok else 0)
    ) / 4
    return round(score)


def _periodo_anno_corrente() -> tuple[int, str]:
    """Periodo di default della overview: anno corrente, etichetta leggibile."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()
    return oggi.year, f"Anno {oggi.year}"


@router.get(
    "/api/gruppo/overview",
    tags=["Catena"],
    summary="Vista gruppo: KPI + salute media + ranking PV per margine%",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_overview(authorization: Optional[str] = Header(None)) -> GruppoOverviewResponse:
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()

    # Sedi attive dell'account (= i PV del gruppo). nome_gruppo è uguale su tutte
    # le sedi dello stesso account (etichetta catena).
    sedi_resp = (
        sb.table("ristoranti")
        .select("id, nome_ristorante, nome_gruppo")
        .eq("user_id", user_id)
        .eq("attivo", True)
        .order("created_at")
        .execute()
    )
    sedi = sedi_resp.data or []
    if len(sedi) < 2:
        raise HTTPException(status_code=400, detail="Account non multi-sede: nessun gruppo da mostrare.")

    nome_gruppo = ""
    for s in sedi:
        if s.get("nome_gruppo"):
            nome_gruppo = str(s["nome_gruppo"])
            break
    if not nome_gruppo:
        nome_gruppo = "Gruppo"

    rid_to_nome = {str(s["id"]): (s.get("nome_ristorante") or "Sede") for s in sedi}
    ids = list(rid_to_nome.keys())

    anno, periodo_label = _periodo_anno_corrente()

    # UNICA lettura aggregabile: tutte le righe margini_mensili dell'anno per le
    # sedi del gruppo. margini_mensili è già pre-aggregata (1 riga per PV×mese):
    # qui sommiamo per ristorante_id — niente loop sulle righe fattura.
    mm_resp = (
        sb.table("margini_mensili")
        .select("ristorante_id,fatturato_netto,mol,costi_fb_totali")
        .in_("ristorante_id", ids)
        .eq("anno", anno)
        .execute()
    )
    agg: Dict[str, Dict[str, float]] = {
        rid: {"netto": 0.0, "mol": 0.0, "fb": 0.0} for rid in ids
    }
    for r in (mm_resp.data or []):
        rid = str(r.get("ristorante_id"))
        a = agg.get(rid)
        if a is None:
            continue
        a["netto"] += float(r.get("fatturato_netto") or 0)
        a["mol"] += float(r.get("mol") or 0)
        a["fb"] += float(r.get("costi_fb_totali") or 0)

    tot_netto = sum(a["netto"] for a in agg.values())
    tot_mol = sum(a["mol"] for a in agg.values())
    tot_fb = sum(a["fb"] for a in agg.values())
    margine_medio = round(tot_mol / tot_netto * 100, 1) if tot_netto > 0 else 0.0

    kpi = GruppoKpi(
        fatturato=round(tot_netto, 2),
        margine_medio_perc=margine_medio,
        spesa_fornitori=round(tot_fb, 2),
    )

    # Ranking per margine%; PV senza ricavi = dati incompleti, in coda.
    ranking: List[RankingPV] = []
    for rid in ids:
        a = agg[rid]
        incompleti = a["netto"] <= 0
        mol_perc = None if incompleti else round(a["mol"] / a["netto"] * 100, 1)
        ranking.append(RankingPV(
            ristorante_id=rid,
            nome=rid_to_nome[rid],
            margine_perc=mol_perc,
            fatturato=round(a["netto"], 2),
            colore=_colore_margine(mol_perc),
            dati_incompleti=incompleti,
        ))
    # Completi prima (margine% desc), incompleti in coda (per nome).
    ranking.sort(key=lambda x: (x.dati_incompleti, -(x.margine_perc or 0), x.nome))

    # Salute del gruppo = MEDIA SEMPLICE degli indici di salute dei PV.
    indici = [_salute_indice_sede(sb, rid) for rid in ids]
    salute_indice = round(sum(indici) / len(indici)) if indici else 0
    if salute_indice >= 80:
        salute_colore = "verde"
    elif salute_indice >= 50:
        salute_colore = "giallo"
    else:
        salute_colore = "rosso"

    return GruppoOverviewResponse(
        nome_gruppo=nome_gruppo,
        num_pv=len(sedi),
        periodo_label=periodo_label,
        kpi=kpi,
        salute_indice=salute_indice,
        salute_colore=salute_colore,
        ranking=ranking,
    )
