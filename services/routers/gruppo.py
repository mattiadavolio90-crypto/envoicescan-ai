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


class GruppoBriefing(BaseModel):
    saluto: str                 # "Buongiorno / Buon pomeriggio / Buonasera"
    narrativa: str              # voce macro deterministica "chi va meglio/peggio"
    severity_max: str           # "info" | "warning" | "error" (dai segnali)


class GruppoOverviewResponse(BaseModel):
    nome_gruppo: str
    num_pv: int
    periodo_label: str
    briefing: GruppoBriefing
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


def _saluto_ora() -> str:
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        h = _dt.now(tz=ZoneInfo("Europe/Rome")).hour
    except Exception:
        h = _dt.now().hour
    if h < 13:
        return "Buongiorno"
    if h < 18:
        return "Buon pomeriggio"
    return "Buonasera"


def _build_briefing(
    nome_gruppo: str,
    ranking: List["RankingPV"],
    salute_indice: int,
    salute_colore: str,
    n_segnali: int,
    sev_max: str,
) -> "GruppoBriefing":
    """Narrativa di gruppo DETERMINISTICA (no AI): si fonda sugli STESSI dati di
    overview + segnali → coerente per costruzione, tono sobrio. Racconta chi va
    meglio/peggio (margine%) e quante cose ci sono da vedere."""
    completi = [r for r in ranking if not r.dati_incompleti and r.margine_perc is not None]
    frasi: List[str] = []

    if len(completi) >= 2:
        best = completi[0]   # ranking già ordinato per margine% desc
        worst = completi[-1]
        if best.ristorante_id != worst.ristorante_id:
            frasi.append(
                f"Va meglio {best.nome} ({best.margine_perc:.0f}% di margine), "
                f"più indietro {worst.nome} ({worst.margine_perc:.0f}%)."
            )
        else:
            frasi.append(f"Margine attorno al {best.margine_perc:.0f}% sui punti vendita con dati.")
    elif len(completi) == 1:
        frasi.append(f"{completi[0].nome} è al {completi[0].margine_perc:.0f}% di margine.")

    n_incompleti = sum(1 for r in ranking if r.dati_incompleti)
    if n_incompleti:
        frasi.append(
            f"{n_incompleti} "
            + ("punto vendita" if n_incompleti == 1 else "punti vendita")
            + " ancora senza dati completi nel periodo."
        )

    if n_segnali == 0:
        frasi.append("Nessuna segnalazione aperta: tutto sotto controllo.")
    else:
        frasi.append(
            f"{n_segnali} "
            + ("cosa da vedere" if n_segnali == 1 else "cose da vedere")
            + " più sotto."
        )

    if salute_colore == "rosso":
        frasi.append(f"La salute del gruppo è bassa ({salute_indice}): conviene completare i dati.")

    narrativa = " ".join(frasi) if frasi else "Ecco la sintesi della catena."
    return GruppoBriefing(saluto=_saluto_ora(), narrativa=narrativa, severity_max=sev_max)


def _conta_segnali_cache(sb, user_id: str) -> tuple[int, str]:
    """(n_segnali, severity_max) dallo snapshot segnali di OGGI in cache.

    Read-only: NON ricalcola (il calcolo avviene su /api/gruppo/segnali). Se la
    cache di oggi non c'è ancora, ritorna (0, "info") — il briefing si limita a
    margini/salute finché la card segnali non genera lo snapshot. Coerente con la
    regola "stessa fonte dati"."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        today = _dt.now(tz=ZoneInfo("Europe/Rome")).date().isoformat()
    except Exception:
        today = _dt.now().date().isoformat()
    try:
        resp = (
            sb.table("gruppo_segnali_state")
            .select("snapshot")
            .eq("user_id", user_id)
            .eq("generated_for_date", today)
            .limit(1)
            .execute()
        )
        if resp.data:
            segnali = (resp.data[0].get("snapshot") or {}).get("segnali") or []
            sev_rank = {"error": 2, "warning": 1, "info": 0}
            sev_max = "info"
            for s in segnali:
                if sev_rank.get(s.get("severity"), 0) > sev_rank.get(sev_max, 0):
                    sev_max = s.get("severity")
            return len(segnali), sev_max
    except Exception:
        pass
    return 0, "info"


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


def _resolve_gruppo(authorization: Optional[str]):
    """(sb, user_id, sedi, nome_gruppo, rid_to_nome, ids) per le viste catena.

    Sedi attive dell'account = i PV del gruppo. 400 se l'account non è multi-sede
    (la catena non ha senso con <2 sedi). Condiviso dai 3 endpoint catena così
    nome_gruppo e l'elenco PV restano coerenti fra loro.
    """
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()

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
    return sb, user_id, sedi, nome_gruppo, rid_to_nome, ids


def _periodo_da_query(data_da: Optional[str], data_a: Optional[str]) -> tuple[str, str, str]:
    """Normalizza il periodo: default = anno corrente. Ritorna (da_iso, a_iso, label)."""
    anno, label = _periodo_anno_corrente()
    da = data_da or f"{anno}-01-01"
    a = data_a or f"{anno}-12-31"
    if data_da or data_a:
        label = f"{da} → {a}"
    return da, a, label


@router.get(
    "/api/gruppo/overview",
    tags=["Catena"],
    summary="Vista gruppo: KPI + salute media + ranking PV per margine%",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_overview(authorization: Optional[str] = Header(None)) -> GruppoOverviewResponse:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)

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

    # Briefing: legge il conteggio segnali dalla cache di OGGI (read-only, niente
    # ricalcolo qui → overview resta leggera; i segnali si calcolano alla loro
    # chiamata). Se la cache manca, il briefing parla solo di margini/salute.
    n_segnali, sev_max = _conta_segnali_cache(sb, user_id)
    briefing = _build_briefing(nome_gruppo, ranking, salute_indice, salute_colore, n_segnali, sev_max)

    return GruppoOverviewResponse(
        nome_gruppo=nome_gruppo,
        num_pv=len(sedi),
        periodo_label=periodo_label,
        briefing=briefing,
        kpi=kpi,
        salute_indice=salute_indice,
        salute_colore=salute_colore,
        ranking=ranking,
    )


# ═══════════════════════════════════════════════════════════════════════════
# FINESTRA "SPESA PER PV" — pivot righe=dimensione × colonne=PV
# ═══════════════════════════════════════════════════════════════════════════

class SpesaPivotRow(BaseModel):
    dim_val: str                    # categoria o fornitore
    per_pv: Dict[str, float]        # ristorante_id -> spesa nel periodo
    totale: float                   # somma riga (tutti i PV)
    incidenza_pct: float            # % della riga sul grand total


class SpesaPivotResponse(BaseModel):
    nome_gruppo: str
    periodo_label: str
    dimensione: str                 # "categoria" | "fornitore"
    pv: List[Dict[str, str]]        # [{id, nome}] colonne nell'ordine sedi
    rows: List[SpesaPivotRow]
    totali_pv: Dict[str, float]     # ristorante_id -> totale colonna
    grand_total: float


@router.get(
    "/api/gruppo/spesa-pivot",
    tags=["Catena"],
    summary="Finestra Spesa per PV: pivot dimensione × punto vendita (SQL aggregata)",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_spesa_pivot(
    dimensione: str = "categoria",
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> SpesaPivotResponse:
    if dimensione not in ("categoria", "fornitore"):
        raise HTTPException(status_code=400, detail="dimensione deve essere 'categoria' o 'fornitore'")

    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    da, a, periodo_label = _periodo_da_query(data_da, data_a)

    # AGGREGAZIONE SQL (RPC gruppo_spesa_pivot): GROUP BY ristorante_id + dimensione.
    # NIENTE full-load delle righe fattura (regola non negoziabile della catena).
    res = sb.rpc("gruppo_spesa_pivot", {
        "p_ristorante_ids": ids,
        "p_dimensione": dimensione,
        "p_data_da": da,
        "p_data_a": a,
    }).execute()

    # Costruisce la pivot: righe = dim_val, colonne = PV.
    from collections import defaultdict
    agg: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    totali_pv: Dict[str, float] = {rid: 0.0 for rid in ids}
    for r in (res.data or []):
        rid = str(r.get("ristorante_id"))
        if rid not in totali_pv:
            continue
        dim_val = r.get("dim_val") or "N/D"
        val = float(r.get("totale") or 0)
        agg[dim_val][rid] += val
        totali_pv[rid] += val

    grand_total = sum(totali_pv.values())
    rows: List[SpesaPivotRow] = []
    for dim_val, per_pv in agg.items():
        tot = sum(per_pv.values())
        rows.append(SpesaPivotRow(
            dim_val=dim_val,
            per_pv={rid: round(per_pv.get(rid, 0.0), 2) for rid in ids},
            totale=round(tot, 2),
            incidenza_pct=round(tot / grand_total * 100, 1) if grand_total > 0 else 0.0,
        ))
    rows.sort(key=lambda x: -x.totale)

    return SpesaPivotResponse(
        nome_gruppo=nome_gruppo,
        periodo_label=periodo_label,
        dimensione=dimensione,
        pv=[{"id": rid, "nome": rid_to_nome[rid]} for rid in ids],
        rows=rows,
        totali_pv={rid: round(v, 2) for rid, v in totali_pv.items()},
        grand_total=round(grand_total, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════
# FINESTRA "MARGINI E COPERTI PER PV" — righe=PV × metriche
# ═══════════════════════════════════════════════════════════════════════════

class MarginiCopertiPV(BaseModel):
    ristorante_id: str
    nome: str
    margine_perc: Optional[float]       # alto = meglio
    fatturato: float                    # alto = meglio
    coperti: int                        # alto = meglio
    scontrino_medio: Optional[float]    # netto/coperti; alto = meglio
    mp_per_coperto: Optional[float]     # costi F&B/coperti; BASSO = meglio
    dati_incompleti: bool


class MarginiCopertiResponse(BaseModel):
    nome_gruppo: str
    periodo_label: str
    righe: List[MarginiCopertiPV]
    gruppo: MarginiCopertiPV             # riga totale gruppo (in fondo)


@router.get(
    "/api/gruppo/margini-coperti",
    tags=["Catena"],
    summary="Finestra Margini e Coperti per PV (da margini_mensili, anno corrente)",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_margini_coperti(
    authorization: Optional[str] = Header(None),
) -> MarginiCopertiResponse:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    anno, periodo_label = _periodo_anno_corrente()

    # margini_mensili è già pre-aggregata: una lettura, somma per ristorante_id.
    mm_resp = (
        sb.table("margini_mensili")
        .select("ristorante_id,fatturato_netto,mol,costi_fb_totali,coperti")
        .in_("ristorante_id", ids)
        .eq("anno", anno)
        .execute()
    )
    agg: Dict[str, Dict[str, float]] = {
        rid: {"netto": 0.0, "mol": 0.0, "fb": 0.0, "cop": 0.0} for rid in ids
    }
    for r in (mm_resp.data or []):
        rid = str(r.get("ristorante_id"))
        a = agg.get(rid)
        if a is None:
            continue
        a["netto"] += float(r.get("fatturato_netto") or 0)
        a["mol"] += float(r.get("mol") or 0)
        a["fb"] += float(r.get("costi_fb_totali") or 0)
        a["cop"] += float(r.get("coperti") or 0)

    def _riga(rid: str, nome: str, a: Dict[str, float]) -> MarginiCopertiPV:
        netto = a["netto"]
        cop = int(round(a["cop"]))
        incompleti = netto <= 0
        return MarginiCopertiPV(
            ristorante_id=rid,
            nome=nome,
            margine_perc=None if incompleti else round(a["mol"] / netto * 100, 1),
            fatturato=round(netto, 2),
            coperti=cop,
            scontrino_medio=round(netto / cop, 2) if cop > 0 else None,
            mp_per_coperto=round(a["fb"] / cop, 2) if cop > 0 else None,
            dati_incompleti=incompleti,
        )

    righe = [_riga(rid, rid_to_nome[rid], agg[rid]) for rid in ids]
    righe.sort(key=lambda x: (x.dati_incompleti, -(x.margine_perc or 0), x.nome))

    tot = {
        "netto": sum(a["netto"] for a in agg.values()),
        "mol": sum(a["mol"] for a in agg.values()),
        "fb": sum(a["fb"] for a in agg.values()),
        "cop": sum(a["cop"] for a in agg.values()),
    }
    gruppo = _riga("", f"Gruppo {nome_gruppo}", tot)

    return MarginiCopertiResponse(
        nome_gruppo=nome_gruppo,
        periodo_label=periodo_label,
        righe=righe,
        gruppo=gruppo,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SEGNALI — "Da vedere nella catena" (3 segnali di analisi, cache 1×/giorno)
# ═══════════════════════════════════════════════════════════════════════════
# Filosofia: ogni segnale parla SOLO con un numero che lo giustifica ("66%, era
# 71%"). Niente AI interpretativa, soglie nette. Deep link "Vedi PV →" = switch
# sede + naviga alla pagina del PV giusto. Calcolo 1×/giorno (cache su
# gruppo_segnali_state, per account), payload JSON piccolo.

# Soglie v1 confermate da Mattia.
_SOGLIA_MARGINE_CALO_PT = 3.0      # margine% mese < media 3 mesi − 3 punti
_SOGLIA_PREZZO_SOPRA = 1.10        # prezzo categoria PV > media catena × 1.10
_PREZZI_MIN_RIGHE = 5              # min righe per categoria/PV per essere affidabile
_PREZZI_MIN_PV = 2                 # serve almeno 2 PV con la categoria per la media


class Segnale(BaseModel):
    tipo: str                       # "margine_calo" | "prezzi_sopra" | "ricavi_mancanti"
    severity: str                   # "warning" | "error"
    ristorante_id: str
    pv_nome: str
    testo: str                      # messaggio con il numero che lo giustifica
    cta_page: str                   # pagina PV dove approfondire (deep link)


class SegnaliResponse(BaseModel):
    nome_gruppo: str
    generated_at: Optional[str]
    segnali: List[Segnale]


def _mesi_indietro(anno: int, mese: int, n: int) -> List[tuple]:
    """Lista degli n (anno, mese) PRECEDENTI a (anno, mese), dal più recente."""
    out = []
    y, m = anno, mese
    for _ in range(n):
        m -= 1
        if m < 1:
            m = 12
            y -= 1
        out.append((y, m))
    return out


def _calcola_segnali(sb, ids: List[str], rid_to_nome: Dict[str, str]) -> List[Dict[str, Any]]:
    """Calcola i 3 segnali di analisi della catena. Tutto SQL aggregato / letture
    su tabelle pre-aggregate — niente full-load righe fattura."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()

    segnali: List[Dict[str, Any]] = []

    # ── Segnale 1: margine in calo (per PV vs se stesso) ──
    # margini_mensili pre-aggregata: prendo gli ultimi 5 mesi possibili per ogni
    # PV, l'ultimo con dati = "corrente", media dei 3 precedenti con dati.
    anni = sorted({oggi.year, oggi.year - 1})
    mm = (
        sb.table("margini_mensili")
        .select("ristorante_id,anno,mese,mol_perc,fatturato_netto")
        .in_("ristorante_id", ids)
        .in_("anno", anni)
        .execute()
    )
    per_pv_mesi: Dict[str, Dict[tuple, float]] = {rid: {} for rid in ids}
    for r in (mm.data or []):
        rid = str(r.get("ristorante_id"))
        if rid not in per_pv_mesi:
            continue
        if float(r.get("fatturato_netto") or 0) <= 0:
            continue  # mese senza ricavi: mol% non significativo
        per_pv_mesi[rid][(int(r["anno"]), int(r["mese"]))] = float(r.get("mol_perc") or 0)

    for rid in ids:
        mesi_dati = per_pv_mesi[rid]
        if len(mesi_dati) < 2:
            continue
        ultimo = max(mesi_dati.keys())
        cur = mesi_dati[ultimo]
        prec = [mesi_dati[k] for k in _mesi_indietro(ultimo[0], ultimo[1], 3) if k in mesi_dati]
        if not prec:
            continue
        media_prec = sum(prec) / len(prec)
        if cur < media_prec - _SOGLIA_MARGINE_CALO_PT:
            segnali.append({
                "tipo": "margine_calo",
                "severity": "warning",
                "ristorante_id": rid,
                "pv_nome": rid_to_nome[rid],
                "testo": f"Margine al {cur:.0f}%, era {media_prec:.0f}% di media nei mesi precedenti",
                "cta_page": "/margini",
            })

    # ── Segnale 3: ricavi mancanti nel mese in corso (per PV) ──
    primo_mese = oggi.replace(day=1).isoformat()
    for rid in ids:
        try:
            rg = (
                sb.table("ricavi_giornalieri")
                .select("data", count="exact")
                .eq("ristorante_id", rid)
                .gte("data", primo_mese)
                .lte("data", oggi.isoformat())
                .execute()
            )
            if (rg.count or 0) == 0:
                segnali.append({
                    "tipo": "ricavi_mancanti",
                    "severity": "warning",
                    "ristorante_id": rid,
                    "pv_nome": rid_to_nome[rid],
                    "testo": "Nessun ricavo registrato questo mese",
                    "cta_page": "/margini",
                })
        except Exception:
            pass

    # ── Segnale 2: prezzi categoria sopra la media catena (PV vs media catena) ──
    # Finestra: ultimi ~90 giorni sull'effective date. RPC aggregata.
    from datetime import timedelta as _td
    da = (oggi - _td(days=90)).isoformat()
    a = oggi.isoformat()
    try:
        pr = sb.rpc("gruppo_prezzi_categoria", {
            "p_ristorante_ids": ids,
            "p_data_da": da,
            "p_data_a": a,
        }).execute()
        # raggruppa per categoria: {cat: {rid: (prezzo, n_righe)}}
        from collections import defaultdict
        per_cat: Dict[str, Dict[str, tuple]] = defaultdict(dict)
        for row in (pr.data or []):
            rid = str(row.get("ristorante_id"))
            if rid not in rid_to_nome:
                continue
            cat = row.get("categoria") or "N/D"
            prezzo = float(row.get("prezzo_medio") or 0)
            n = int(row.get("n_righe") or 0)
            if prezzo > 0:
                per_cat[cat][rid] = (prezzo, n)
        # per ogni categoria con ≥2 PV: media catena, poi PV sopra soglia
        # (solo il PV più sopra per categoria, per non inondare di segnali).
        for cat, pv_map in per_cat.items():
            affidabili = {rid: p for rid, (p, n) in pv_map.items() if n >= _PREZZI_MIN_RIGHE}
            if len(affidabili) < _PREZZI_MIN_PV:
                continue
            media_catena = sum(affidabili.values()) / len(affidabili)
            if media_catena <= 0:
                continue
            peggiore = max(affidabili.items(), key=lambda kv: kv[1])
            rid_p, prezzo_p = peggiore
            if prezzo_p > media_catena * _SOGLIA_PREZZO_SOPRA:
                scarto = (prezzo_p / media_catena - 1) * 100
                segnali.append({
                    "tipo": "prezzi_sopra",
                    "severity": "warning",
                    "ristorante_id": rid_p,
                    "pv_nome": rid_to_nome[rid_p],
                    "testo": f"{cat.title()}: prezzo medio +{scarto:.0f}% sulla media catena",
                    "cta_page": "/prezzi",
                })
    except Exception:
        pass

    # Ordine: errori prima, poi per nome PV. (tutti warning in v1, ma futuro-proof)
    sev_rank = {"error": 0, "warning": 1, "info": 2}
    segnali.sort(key=lambda s: (sev_rank.get(s["severity"], 9), s["pv_nome"]))
    return segnali


@router.get(
    "/api/gruppo/segnali",
    tags=["Catena"],
    summary="Segnali catena 'Da vedere' (cache 1×/giorno, 3 segnali di analisi)",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_segnali(
    force: bool = False,
    authorization: Optional[str] = Header(None),
) -> SegnaliResponse:
    from datetime import datetime as _dt, timezone as _tz
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()

    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    today_iso = oggi.isoformat()

    # Fast-path: snapshot di oggi già in cache (1×/giorno per account).
    if not force:
        try:
            cached = (
                sb.table("gruppo_segnali_state")
                .select("snapshot")
                .eq("user_id", user_id)
                .eq("generated_for_date", today_iso)
                .limit(1)
                .execute()
            )
            if cached.data:
                snap = cached.data[0].get("snapshot") or {}
                return SegnaliResponse(
                    nome_gruppo=nome_gruppo,
                    generated_at=snap.get("generated_at"),
                    segnali=[Segnale(**s) for s in (snap.get("segnali") or [])],
                )
        except Exception:
            pass

    segnali = _calcola_segnali(sb, ids, rid_to_nome)
    generated_at = _dt.now(_tz.utc).isoformat()

    # Salva lo snapshot di oggi (best-effort: un errore di scrittura non deve far
    # fallire la lettura dei segnali appena calcolati).
    try:
        sb.table("gruppo_segnali_state").upsert({
            "user_id": user_id,
            "generated_for_date": today_iso,
            "snapshot": {"segnali": segnali, "generated_at": generated_at},
            "updated_at": generated_at,
        }, on_conflict="user_id,generated_for_date").execute()
    except Exception:
        pass

    return SegnaliResponse(
        nome_gruppo=nome_gruppo,
        generated_at=generated_at,
        segnali=[Segnale(**s) for s in segnali],
    )


# ═══════════════════════════════════════════════════════════════════════════
# TAG DI CATENA — livello account, SCOLLEGATI dai tag di sede (custom_tags)
# ═══════════════════════════════════════════════════════════════════════════
# Un tag di catena = nome + lista di descrizioni prodotto (descrizione_key),
# definito una volta per il gruppo, applicato a TUTTI i PV. Analisi macro per PV
# via RPC SQL (no full-load). L'anagrafica prodotti è già account-wide, quindi le
# stesse descrizioni ricorrono fra i PV.

class GruppoTagCreate(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class GruppoTagAssocItem(BaseModel):
    descrizione: str
    fattore_kg: Optional[float] = None


class GruppoTagAssocRequest(BaseModel):
    descrizioni: List[GruppoTagAssocItem]


def _norm_key(*args, **kwargs):
    """Normalizzazione descrizione → chiave, IDENTICA ai tag di sede."""
    from services.db_service import _normalize_custom_tag_key
    return _normalize_custom_tag_key(*args, **kwargs)


def _assert_gruppo_tag(sb, tag_id: int, user_id: str) -> None:
    r = (
        sb.table("gruppo_tags").select("id")
        .eq("id", int(tag_id)).eq("user_id", user_id).limit(1).execute()
    )
    if not (r.data or []):
        raise HTTPException(status_code=404, detail="Tag di catena non trovato")


@router.get("/api/gruppo/tag", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_list(authorization: Optional[str] = Header(None)):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    tags = (
        sb.table("gruppo_tags").select("id,nome,emoji,colore")
        .eq("user_id", user_id).order("created_at").execute()
    ).data or []
    # conteggio associazioni per tag (una query)
    if tags:
        assoc = (
            sb.table("gruppo_tag_prodotti").select("tag_id")
            .eq("user_id", user_id).execute()
        ).data or []
        from collections import Counter
        cnt = Counter(int(a["tag_id"]) for a in assoc)
        for t in tags:
            t["n_prodotti"] = cnt.get(int(t["id"]), 0)
    return {"tags": tags}


@router.post("/api/gruppo/tag", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_create(body: GruppoTagCreate, authorization: Optional[str] = Header(None)):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome tag obbligatorio")
    row = sb.table("gruppo_tags").insert({
        "user_id": user_id, "nome": nome, "emoji": body.emoji, "colore": body.colore,
    }).execute()
    return {"tag": (row.data or [{}])[0]}


@router.delete("/api/gruppo/tag/{tag_id}", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_delete(tag_id: int, authorization: Optional[str] = Header(None)):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    _assert_gruppo_tag(sb, tag_id, user_id)
    sb.table("gruppo_tags").delete().eq("id", int(tag_id)).eq("user_id", user_id).execute()
    return {"ok": True}


@router.get("/api/gruppo/tag/descrizioni", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_descrizioni(authorization: Optional[str] = Header(None)):
    """Descrizioni distinte su tutti i PV del gruppo (per costruire il tag)."""
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    res = sb.rpc("gruppo_tag_descrizioni", {"p_ristorante_ids": ids, "p_limit": 500}).execute()
    out = [
        {
            "descrizione": r.get("descrizione"),
            "descrizione_key": r.get("descrizione_key"),
            "n": int(r.get("n") or 0),
            "spesa": round(float(r.get("spesa") or 0), 2),
        }
        for r in (res.data or [])
    ]
    return {"descrizioni": out}


@router.get("/api/gruppo/tag/{tag_id}/prodotti", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_prodotti_list(tag_id: int, authorization: Optional[str] = Header(None)):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    _assert_gruppo_tag(sb, tag_id, user_id)
    rows = (
        sb.table("gruppo_tag_prodotti").select("id,descrizione,descrizione_key,fattore_kg")
        .eq("tag_id", int(tag_id)).eq("user_id", user_id).order("descrizione").execute()
    ).data or []
    return {"prodotti": rows}


@router.post("/api/gruppo/tag/{tag_id}/prodotti", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_prodotti_add(
    tag_id: int, body: GruppoTagAssocRequest, authorization: Optional[str] = Header(None)
):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    _assert_gruppo_tag(sb, tag_id, user_id)
    records = []
    visti = set()
    for item in body.descrizioni:
        desc = (item.descrizione or "").strip()
        if not desc:
            continue
        key = _norm_key(desc)
        if not key or key in visti:
            continue
        visti.add(key)
        records.append({
            "tag_id": int(tag_id), "user_id": user_id,
            "descrizione": desc, "descrizione_key": key, "fattore_kg": item.fattore_kg,
        })
    if not records:
        return {"associazioni": [], "aggiunte": 0}
    # upsert per non duplicare (vincolo unico tag_id+descrizione_key)
    res = sb.table("gruppo_tag_prodotti").upsert(
        records, on_conflict="tag_id,descrizione_key"
    ).execute()
    return {"associazioni": res.data or [], "aggiunte": len(records)}


@router.delete("/api/gruppo/tag/prodotti/{assoc_id}", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_prodotti_remove(assoc_id: int, authorization: Optional[str] = Header(None)):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    sb.table("gruppo_tag_prodotti").delete().eq("id", int(assoc_id)).eq("user_id", user_id).execute()
    return {"ok": True}


class TagAnalisiPV(BaseModel):
    ristorante_id: str
    nome: str
    spesa: float
    quantita: float
    n_righe: int
    n_fornitori: int


class GruppoTagAnalisiResponse(BaseModel):
    tag_id: int
    nome: str
    periodo_label: str
    spesa_totale: float
    per_pv: List[TagAnalisiPV]


@router.get("/api/gruppo/tag/{tag_id}/analisi", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_analisi(
    tag_id: int,
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> GruppoTagAnalisiResponse:
    """Analisi macro PER PV del tag di catena: spesa/quantità/righe/fornitori per
    ogni punto vendita, via RPC SQL (no full-load)."""
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    tag_row = (
        sb.table("gruppo_tags").select("id,nome").eq("id", int(tag_id)).eq("user_id", user_id).limit(1).execute()
    ).data or []
    if not tag_row:
        raise HTTPException(status_code=404, detail="Tag di catena non trovato")
    nome = tag_row[0].get("nome") or "Tag"

    keys = [
        r["descrizione_key"]
        for r in (
            sb.table("gruppo_tag_prodotti").select("descrizione_key")
            .eq("tag_id", int(tag_id)).eq("user_id", user_id).execute()
        ).data or []
    ]
    da, a, periodo_label = _periodo_da_query(data_da, data_a)

    per_pv: List[TagAnalisiPV] = []
    if keys:
        res = sb.rpc("gruppo_tag_analisi", {
            "p_ristorante_ids": ids,
            "p_descrizione_keys": keys,
            "p_data_da": da,
            "p_data_a": a,
        }).execute()
        by_rid = {str(r.get("ristorante_id")): r for r in (res.data or [])}
        for rid in ids:
            r = by_rid.get(rid)
            per_pv.append(TagAnalisiPV(
                ristorante_id=rid,
                nome=rid_to_nome[rid],
                spesa=round(float(r.get("spesa") or 0), 2) if r else 0.0,
                quantita=round(float(r.get("quantita") or 0), 2) if r else 0.0,
                n_righe=int(r.get("n_righe") or 0) if r else 0,
                n_fornitori=int(r.get("n_fornitori") or 0) if r else 0,
            ))
        per_pv.sort(key=lambda x: -x.spesa)

    return GruppoTagAnalisiResponse(
        tag_id=int(tag_id),
        nome=nome,
        periodo_label=periodo_label,
        spesa_totale=round(sum(p.spesa for p in per_pv), 2),
        per_pv=per_pv,
    )
