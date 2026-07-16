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

from config.logger_setup import get_logger

logger = get_logger("router_gruppo")


def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


def _chat_limite_pool_gruppo(*args, **kwargs):
    return _fw()._chat_limite_pool_gruppo(*args, **kwargs)


def _chat_domande_oggi(*args, **kwargs):
    return _fw()._chat_domande_oggi(*args, **kwargs)


router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# OVERVIEW — KPI gruppo + salute media + ranking per margine%
# ═══════════════════════════════════════════════════════════════════════════

class GruppoKpi(BaseModel):
    fatturato: float            # Σ fatturato LORDO (iva10+iva22+altri) — come la Home PV
    margine_medio_perc: float   # margine % aggregato del gruppo (Σmol / Σnetto)
    spesa_fornitori: float      # Σ costi_fb_totali del periodo (food cost in €)
    mol: float                  # Σ mol del periodo (totale gruppo, valore assoluto)
    food_cost_pct: Optional[float]  # Σ costi_fb_totali / Σ lordo — come food cost % della Home PV
    costo_personale: float      # Σ (costo_dipendenti + costo_personale_extra)
    spese_generali: float       # Σ (costi_spese_auto + altri_costi_spese)
    # Cascata dati (decisione 19/06): "nessuno" = nessun PV ha fatturato/F&B ->
    # non mostrare numeri; "food" = ci sono F&B ma manca personale/spese in qualche
    # PV -> food cost e 1° margine si', MOL no (sarebbe gonfiato); "completo" = tutti
    # i PV hanno fatturato + F&B + personale -> MOL affidabile.
    livello_dati: str = "completo"
    # Quanti PV hanno ancora dati base da completare (per la nota nella card).
    pv_da_completare: int = 0


class MolMensile(BaseModel):
    mese: int
    mol: float                  # Σ mol del mese su tutti i PV (per sparkline andamento)


class SalutePV(BaseModel):
    ristorante_id: str
    nome: str
    indice: int                 # 0-100, stessa formula della salute PV
    colore: str                 # "verde" | "giallo" | "rosso"


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
    # Fatture di gruppo ancora da collocare (a nome della società, non attribuite a
    # un locale). Fuori dalla narrativa perché l'AZIONE non è uguale ovunque: sul
    # desktop c'è la coda subito sotto il briefing → l'imperativo "assegnale/dividile"
    # è azionabile; sul mobile la coda non esiste → il testo rimanda al computer.
    # Il conteggio è strutturato così ogni client sceglie il proprio wording.
    n_fatture_da_collocare: int = 0


class GruppoOverviewResponse(BaseModel):
    nome_gruppo: str
    num_pv: int
    periodo_label: str
    briefing: GruppoBriefing
    kpi: GruppoKpi
    mol_mensile: List[MolMensile]   # serie MOL per mese (sparkline andamento gruppo)
    mol_mensile_anno: int
    salute_indice: int          # media semplice degli indici di salute dei PV
    salute_colore: str          # "verde" | "giallo" | "rosso"
    salute_pv: List[SalutePV]   # dettaglio per-PV (voci della card salute gruppo)
    ranking: List[RankingPV]


def _overrides_mese_sede(sb, ristorante_id: str, anno: int) -> Dict[int, Dict[str, float]]:
    """Override ricavi 'modalità mensile' di UNA sede per l'anno, riindicizzati {mese: {...}}.

    Riusa _load_mensile_overrides del worker (stessa fonte del PV: ricavi_modalita_mensile)
    così catena e pagina Margini leggono gli stessi ricavi. Best-effort: se la lettura
    fallisce si torna {} e i ricavi ricadono sullo snapshot (comportamento storico).
    """
    try:
        raw = _fw()._load_mensile_overrides(sb, ristorante_id, [int(anno)])
    except Exception:
        return {}
    return {int(m): v for (a, m), v in (raw or {}).items() if int(a) == int(anno)}


def _aggrega_sedi_mensili(
    ids: List[str],
    righe_mm: List[Dict[str, Any]],
    costi_auto: Dict[str, tuple],
    overrides: Dict[str, Dict[int, Dict[str, float]]],
    mesi: List[int],
    per_mese: bool = False,
) -> Dict[str, Any]:
    """Aggrega per sede il conto economico dei mesi richiesti, con la STESSA formula
    della pagina Margini del PV (_aggrega_mensili_margini in fastapi_worker).

    È il punto unico di verità della catena: gruppo_overview e gruppo_margini_coperti
    la condividono, così non possono più divergere fra loro né dal PV (ogni copia
    della formula è un bug che aspetta di nascere — è già successo).

    Due asimmetrie col PV, corrette qui perché causavano MOL diversi tra le viste:
      • si itera sui MESI DI CALENDARIO, non sulle righe margini_mensili esistenti:
        una sede con fatture ma senza riga del mese (ricavi non ancora inseriti) ha
        comunque i suoi costi nel MOL, come sul PV;
      • i ricavi dei mesi in modalità mensile vengono dagli OVERRIDE
        (ricavi_modalita_mensile), che vincono sullo snapshot fatturato_netto.

    `overrides` è {ristorante_id: {mese: {iva10, iva22, altri, coperti}}} (per sede:
    ogni PV ha la sua modalità mensile). `costi_auto` è {ristorante_id: (dict_fb
    {mese:€}, dict_spese {mese:€})}.
    Con per_mese=True aggiunge le serie _mol_per_mese/_netto_per_mese (sparkline).
    """
    per_sede_mese: Dict[tuple, Dict[str, Any]] = {}
    for r in (righe_mm or []):
        rid = str(r.get("ristorante_id"))
        try:
            m = int(r.get("mese"))
        except (TypeError, ValueError):
            continue
        per_sede_mese[(rid, m)] = r

    out: Dict[str, Any] = {
        rid: {"netto": 0.0, "lordo": 0.0, "mol": 0.0, "fb": 0.0,
              "spese": 0.0, "pers": 0.0, "cop": 0.0, "cop_fb": 0.0}
        for rid in ids
    }
    mol_per_mese: Dict[int, float] = {}
    netto_per_mese: Dict[int, float] = {}

    for rid in ids:
        fb_auto_m, spese_auto_m = costi_auto.get(rid, ({}, {}))
        ov_sede = overrides.get(rid) or {}
        a = out[rid]
        for m in mesi:
            r = per_sede_mese.get((rid, m), {})
            # Ricavi: override del mese se in modalità mensile, altrimenti snapshot.
            # Scorporo IVA identico al PV (iva10/1.10 + iva22/1.22 + altri).
            ov = ov_sede.get(m)
            if ov:
                iva10 = float(ov.get("iva10") or 0)
                iva22 = float(ov.get("iva22") or 0)
                altri = float(ov.get("altri") or 0)
            else:
                iva10 = float(r.get("fatturato_iva10") or 0)
                iva22 = float(r.get("fatturato_iva22") or 0)
                altri = float(r.get("altri_ricavi_noiva") or 0)
            lordo = iva10 + iva22 + altri
            netto = (iva10 / 1.10) + (iva22 / 1.22) + altri

            fb_tot = (
                float(fb_auto_m.get(m, 0.0))
                + float(r.get("altri_costi_fb") or 0)
                + float(r.get("quote_riparto_fb") or 0)
            )
            sp_tot = (
                float(spese_auto_m.get(m, 0.0))
                + float(r.get("altri_costi_spese") or 0)
                + float(r.get("quote_riparto_spese") or 0)
            )
            pers = (
                float(r.get("costo_dipendenti") or 0)
                + float(r.get("costo_personale_extra") or 0)
            )
            mol_v = (netto - fb_tot) - sp_tot - pers

            a["netto"] += netto
            a["lordo"] += lordo
            a["fb"] += fb_tot
            a["spese"] += sp_tot
            a["pers"] += pers
            a["mol"] += mol_v

            # Coperti: override del mese se presente (stessa fonte dei ricavi),
            # altrimenti il valore su margini_mensili.
            cop_mese = 0.0
            if ov and ov.get("coperti") is not None:
                cop_mese = float(ov["coperti"] or 0)
            else:
                cop_mese = float(r.get("coperti") or 0)
            a["cop"] += cop_mese
            # €MP/coperto: contano solo i mesi con costo F&B, altrimenti i mesi con
            # coperti ma fatture non ancora arrivate diluirebbero la media (come PV).
            if fb_tot > 0:
                a["cop_fb"] += cop_mese

            if per_mese:
                mol_per_mese[m] = mol_per_mese.get(m, 0.0) + mol_v
                netto_per_mese[m] = netto_per_mese.get(m, 0.0) + netto

    if per_mese:
        out["_mol_per_mese"] = mol_per_mese
        out["_netto_per_mese"] = netto_per_mese
    return out


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
    salute_pv: Optional[List["SalutePV"]] = None,
    incompleti_ids: Optional[set] = None,
    n_fatture_da_collocare: int = 0,
) -> "GruppoBriefing":
    """Narrativa di gruppo DETERMINISTICA (no AI): si fonda sugli STESSI dati di
    overview + segnali → coerente per costruzione, tono sobrio.

    Completezza misurata per PRESENZA di dati (decisione 19/06): una sede è
    affidabile per il confronto margini solo se ha fatturato + fatture costo (F&B) +
    costo personale. Senza, il margine è FINTO: non la usiamo per dire "va
    meglio/peggio" e la contiamo tra quelle da completare. Mai "tutto sotto
    controllo" se la salute è rossa o ci sono sedi incomplete. Fallback alla salute
    per-PV (<50) se incompleti_ids non è disponibile."""
    incompleti_ids = incompleti_ids or set()
    salute_by_id = {s.ristorante_id: s.indice for s in (salute_pv or [])}

    def _affidabile(r: "RankingPV") -> bool:
        if r.dati_incompleti or r.margine_perc is None:
            return False
        if incompleti_ids:
            return r.ristorante_id not in incompleti_ids
        ix = salute_by_id.get(r.ristorante_id)
        return ix is None or ix >= 50

    completi = [r for r in ranking if _affidabile(r)]
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
            frasi.append(f"Margine attorno al {best.margine_perc:.0f}% sui punti vendita con dati completi.")
    elif len(completi) == 1:
        frasi.append(f"{completi[0].nome} è al {completi[0].margine_perc:.0f}% di margine.")

    # Sedi con dati da completare: per PRESENZA di dati (costi mancanti). Fallback
    # alla salute (<50) o, in ultima istanza, al solo fatturato.
    if incompleti_ids:
        n_incompleti = len(incompleti_ids)
    elif salute_by_id:
        n_incompleti = sum(1 for ix in salute_by_id.values() if ix < 50)
    else:
        n_incompleti = sum(1 for r in ranking if r.dati_incompleti)
    if n_incompleti:
        frasi.append(
            f"{n_incompleti} "
            + ("punto vendita ha" if n_incompleti == 1 else "punti vendita hanno")
            + " i dati di costo ancora da completare: lì il margine non è reale."
        )

    # Azione concreta del giorno: fatture di gruppo da collocare (arrivano a nome
    # della società, l'app non le ha attribuite a un locale). NON entra nella
    # narrativa condivisa (l'imperativo "assegnale/dividile" non è azionabile su
    # mobile, dove la coda non esiste): resta nel campo strutturato
    # n_fatture_da_collocare e ogni client sceglie il wording e il CTA giusti.

    # "Tutto sotto controllo" SOLO se non manca davvero nulla: niente segnali,
    # salute non rossa, nessuna sede incompleta, niente fatture in sospeso. Mai dire
    # che va tutto bene mentre la salute è bassa (la contraddizione segnalata da Mattia).
    tutto_ok = (
        n_segnali == 0 and salute_colore != "rosso"
        and n_incompleti == 0 and n_fatture_da_collocare == 0
    )
    if tutto_ok:
        frasi.append("Nessuna segnalazione aperta: tutto in ordine.")

    if salute_colore == "rosso":
        frasi.append(
            f"La salute del gruppo è bassa ({salute_indice}): "
            "conviene completare i dati prima di leggere i margini."
        )

    narrativa = " ".join(frasi) if frasi else "Ecco la sintesi della catena."
    return GruppoBriefing(
        saluto=_saluto_ora(),
        narrativa=narrativa,
        severity_max=sev_max,
        n_fatture_da_collocare=n_fatture_da_collocare,
    )


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


def _salute_componenti_raw(sb, ids: List[str]) -> List[Dict[str, Any]]:
    """Righe grezze della RPC gruppo_salute_componenti (n_fatture, n_needs_review,
    netto, personale per PV). Fonte UNICA condivisa da _salute_indici_batch e
    _completezza_dati_pv: cosi' l'overview chiama la RPC una sola volta. Mese
    precedente + finestra 30gg, come /api/home/salute."""
    from datetime import datetime as _dt, timedelta as _td
    if not ids:
        return []
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()
    inizio_dt = _dt.combine(oggi - _td(days=29), _dt.min.time())
    if oggi.month == 1:
        mc_anno, mc_mese = oggi.year - 1, 12
    else:
        mc_anno, mc_mese = oggi.year, oggi.month - 1
    try:
        res = sb.rpc("gruppo_salute_componenti", {
            "p_ristorante_ids": ids,
            "p_inizio": inizio_dt.isoformat(),
            "p_anno": mc_anno,
            "p_mese": mc_mese,
        }).execute()
        return res.data or []
    except Exception:
        return []


def _salute_indici_batch(
    sb, ids: List[str], rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Indice di salute (0-100) per OGNI sede, stessa formula 4-voci di
    /api/home/salute (fatture recenti, fatturato, costo personale, % classificate).
    `rows` opzionale per riusare una RPC gia' fatta (overview)."""
    out: Dict[str, int] = {rid: 0 for rid in ids}
    if not ids:
        return out
    if rows is None:
        rows = _salute_componenti_raw(sb, ids)
    for r in rows:
        rid = str(r.get("ristorante_id"))
        if rid not in out:
            continue
        n_fatture = int(r.get("n_fatture") or 0)
        n_needs = int(r.get("n_needs_review") or 0)
        netto = float(r.get("netto") or 0)
        personale = float(r.get("personale") or 0)
        fatture_ok = n_fatture > 0
        pct_classificate = round((n_fatture - n_needs) / n_fatture * 100) if n_fatture > 0 else 0
        score = (
            (100 if fatture_ok else 0)
            + (100 if netto > 0 else 0)
            + (100 if personale > 0 else 0)
            + (pct_classificate if fatture_ok else 0)
        ) / 4
        out[rid] = round(score)
    return out


def _periodo_anno_corrente() -> tuple[int, str]:
    """Periodo di default della overview: anno corrente, etichetta leggibile."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()
    return oggi.year, f"Anno {oggi.year}"


def _anno_mese_corrente() -> tuple[int, int]:
    """(anno, mese) correnti in fuso Europe/Rome. Serve a NON sommare i mesi
    futuri: margini_mensili può contenere righe di mesi non ancora trascorsi
    (proiezioni/seed di test) che gonfierebbero i totali anno-su-anno."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()
    return oggi.year, oggi.month


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
        .select("id, nome_ristorante")
        .eq("user_id", user_id)
        .eq("attivo", True)
        .eq("sede_tecnica", False)   # la sede-contenitore "Costi comuni" non è un PV del gruppo
        .order("created_at")
        .execute()
    )
    sedi = sedi_resp.data or []
    if len(sedi) < 2:
        raise HTTPException(status_code=400, detail="Account non multi-sede: nessun gruppo da mostrare.")

    # nome_gruppo è un'etichetta a livello account: vive su users, non su ristoranti.
    # La sessione non porta sempre questo campo, quindi lo rileggiamo qui.
    nome_gruppo = str(user.get("nome_gruppo") or "").strip()
    if not nome_gruppo:
        try:
            ug = (
                sb.table("users")
                .select("nome_gruppo")
                .eq("id", user_id)
                .single()
                .execute()
            )
            nome_gruppo = str((ug.data or {}).get("nome_gruppo") or "").strip()
        except Exception:
            nome_gruppo = ""
    if not nome_gruppo:
        nome_gruppo = "Gruppo"

    rid_to_nome = {str(s["id"]): (s.get("nome_ristorante") or "Sede") for s in sedi}
    ids = list(rid_to_nome.keys())
    return sb, user_id, sedi, nome_gruppo, rid_to_nome, ids


_MESI_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def _periodo_da_query(data_da: Optional[str], data_a: Optional[str]) -> tuple[str, str, str]:
    """Normalizza il periodo: default = anno corrente. Ritorna (da_iso, a_iso, label).

    Etichetta leggibile: anno intero → "Anno YYYY"; mese di calendario intero →
    "Giugno 2026"; altro range → "da → a"."""
    anno, label = _periodo_anno_corrente()
    da = data_da or f"{anno}-01-01"
    a = data_a or f"{anno}-12-31"
    if data_da or data_a:
        label = f"{da} → {a}"
        try:
            from datetime import date as _date
            d0, d1 = _date.fromisoformat(da), _date.fromisoformat(a)
            ultimo = (_date(d0.year + (d0.month == 12), (d0.month % 12) + 1, 1)
                      - _date.resolution)
            if d0.day == 1 and d0.year == d1.year and d0.month == d1.month and d1 == ultimo:
                label = f"{_MESI_IT[d0.month - 1].capitalize()} {d0.year}"
            elif d0 == _date(d0.year, 1, 1) and d1 == _date(d0.year, 12, 31):
                label = f"Anno {d0.year}"
        except Exception:
            pass
    return da, a, label


@router.get(
    "/api/gruppo/overview",
    tags=["Catena"],
    summary="Vista gruppo: KPI + salute media + ranking PV per margine%",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_overview(authorization: Optional[str] = Header(None)) -> GruppoOverviewResponse:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)

    anno, mese_corr = _anno_mese_corrente()
    periodo_label = f"Anno {anno}"

    # Righe margini_mensili dell'anno FINO AL MESE CORRENTE per le sedi del gruppo
    # (niente mesi futuri: sarebbero proiezioni/seed che gonfiano i totali). Da qui
    # prendiamo ricavi, costi MANUALI (altri_costi_*/personale) e quote riparto —
    # tutti valori già 1-riga-per-sede×mese, nessun loop sulle righe fattura.
    # I costi AUTOMATICI (food/spese da fatture) NON si leggono più dallo snapshot
    # costi_fb_totali/mol (a 0 finché nessuno salva la pagina Margini della sede):
    # si ricalcolano LIVE come la pagina Margini del PV, così Sintesi e PV combaciano.
    mm_resp = (
        sb.table("margini_mensili")
        .select(
            "ristorante_id,mese,fatturato_netto,fatturato_iva10,fatturato_iva22,"
            "altri_ricavi_noiva,altri_costi_fb,altri_costi_spese,"
            "quote_riparto_fb,quote_riparto_spese,"
            "costo_dipendenti,costo_personale_extra"
        )
        .in_("ristorante_id", ids)
        .eq("anno", anno)
        .lte("mese", mese_corr)
        .execute()
    )

    # Costi automatici F&B/spese LIVE per (sede, mese) su tutto il gruppo in UNA RPC
    # SQL (esclude 'Da Classificare' e le fatture ripartite → anti-doppio-conteggio,
    # identico alla pagina Margini). Fallback per-sede interno alla funzione.
    from services.margine_service import calcola_costi_automatici_gruppo_sql
    costi_auto_gruppo = calcola_costi_automatici_gruppo_sql(user_id, ids, anno)

    # Ricavi in modalità mensile: vincono sullo snapshot, come sul PV. Per sede,
    # perché ogni PV ha la sua modalità (una lettura per sede su una tabella piccola,
    # 1 riga per mese: niente loop sulle righe fattura).
    overrides_gruppo = {rid: _overrides_mese_sede(sb, rid, anno) for rid in ids}

    mesi_periodo = list(range(1, mese_corr + 1))
    agg = _aggrega_sedi_mensili(
        ids=ids,
        righe_mm=(mm_resp.data or []),
        costi_auto=costi_auto_gruppo,
        overrides=overrides_gruppo,
        mesi=mesi_periodo,
        per_mese=True,
    )
    mol_per_mese: Dict[int, float] = agg.pop("_mol_per_mese", {})
    netto_per_mese: Dict[int, float] = agg.pop("_netto_per_mese", {})

    tot_netto = sum(a["netto"] for a in agg.values())
    tot_lordo = sum(a["lordo"] for a in agg.values())
    tot_mol = sum(a["mol"] for a in agg.values())
    tot_fb = sum(a["fb"] for a in agg.values())
    tot_spese = sum(a["spese"] for a in agg.values())
    tot_pers = sum(a["pers"] for a in agg.values())
    margine_medio = round(tot_mol / tot_netto * 100, 1) if tot_netto > 0 else 0.0
    # Food cost %: come la Home PV → costi F&B sul fatturato LORDO.
    food_cost_pct = round(tot_fb / tot_lordo * 100, 1) if tot_lordo > 0 else None

    # Cascata dati del gruppo (decisione 19/06): senza i costi di alcuni PV il MOL
    # aggregato e' falso. Stesso criterio del PV (presenza dati, non % salute):
    #  - nessun fatturato/F&B nel gruppo -> "nessuno" (niente numeri, completa i PV);
    #  - F&B presenti ma qualche PV senza personale -> "food" (food cost/1° margine
    #    si', MOL no: sarebbe gonfiato);
    #  - tutti i PV con fatturato + F&B + personale -> "completo" (MOL affidabile).
    # RPC salute componenti UNA volta sola: la condividono completezza e indici.
    salute_rows = _salute_componenti_raw(sb, ids)
    try:
        completezza = _completezza_dati_pv(sb, ids, rows=salute_rows)
    except Exception:
        completezza = {}
    incompleti_ids = set(completezza.keys())
    pv_da_completare = len(completezza)
    if tot_lordo <= 0 or tot_fb <= 0:
        livello_dati = "nessuno"
    elif pv_da_completare > 0:
        livello_dati = "food"
    else:
        livello_dati = "completo"

    kpi = GruppoKpi(
        fatturato=round(tot_lordo, 2),
        margine_medio_perc=margine_medio,
        spesa_fornitori=round(tot_fb, 2),
        mol=round(tot_mol, 2),
        food_cost_pct=food_cost_pct,
        costo_personale=round(tot_pers, 2),
        spese_generali=round(tot_spese, 2),
        livello_dati=livello_dati,
        pv_da_completare=pv_da_completare,
    )

    # Serie MOL mensile del gruppo (solo mesi con ricavi → la sparkline non mostra
    # i mesi futuri vuoti a zero). Σmol per mese su tutti i PV.
    mol_mensile = [
        MolMensile(mese=m, mol=round(mol_per_mese.get(m, 0.0), 2))
        for m in sorted(mol_per_mese.keys())
        if netto_per_mese.get(m, 0.0) > 0
    ]

    # Ranking per margine%; PV senza ricavi = dati incompleti, in coda.
    ranking: List[RankingPV] = []
    for rid in ids:
        a = agg[rid]
        # Incompleto = nessun ricavo OPPURE mancano i costi (food/personale): stesso
        # criterio del briefing, così il ranking non mostra "0% rosso" per le sedi
        # che semplicemente non hanno ancora caricato i costi.
        incompleti = a["netto"] <= 0 or rid in incompleti_ids
        mol_perc = None if incompleti else round(a["mol"] / a["netto"] * 100, 1)
        ranking.append(RankingPV(
            ristorante_id=rid,
            nome=rid_to_nome[rid],
            margine_perc=mol_perc,
            fatturato=round(a["lordo"], 2),
            colore=_colore_margine(mol_perc),
            dati_incompleti=incompleti,
        ))
    # Completi prima (margine% desc), incompleti in coda (per nome).
    ranking.sort(key=lambda x: (x.dati_incompleti, -(x.margine_perc or 0), x.nome))

    # Salute del gruppo = MEDIA SEMPLICE degli indici di salute dei PV. Esponiamo
    # anche il dettaglio per-PV (le "voci" della card salute gruppo).
    def _colore_salute(ix: int) -> str:
        if ix >= 80:
            return "verde"
        if ix >= 50:
            return "giallo"
        return "rosso"

    indici_map = _salute_indici_batch(sb, ids, rows=salute_rows)
    indici = list(indici_map.values())
    salute_indice = round(sum(indici) / len(indici)) if indici else 0
    salute_colore = _colore_salute(salute_indice)
    # Dettaglio per-PV, dal più debole (serve attenzione) al più sano.
    salute_pv = [
        SalutePV(
            ristorante_id=rid,
            nome=rid_to_nome[rid],
            indice=indici_map[rid],
            colore=_colore_salute(indici_map[rid]),
        )
        for rid in ids
    ]
    salute_pv.sort(key=lambda x: x.indice)

    # Briefing: legge il conteggio segnali dalla cache di OGGI (read-only, niente
    # ricalcolo qui → overview resta leggera; i segnali si calcolano alla loro
    # chiamata). Se la cache manca, il briefing parla solo di margini/salute.
    n_segnali, sev_max = _conta_segnali_cache(sb, user_id)
    # Fatture di gruppo ancora in coda 'da_assegnare' (COUNT leggero, no full-load):
    # entrano nel briefing come azione concreta del giorno.
    n_da_collocare = 0
    try:
        cnt = (
            sb.table("fatture_queue")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("status", "da_assegnare")
            .execute()
        )
        n_da_collocare = int(cnt.count or 0)
    except Exception:
        n_da_collocare = 0
    briefing = _build_briefing(
        nome_gruppo, ranking, salute_indice, salute_colore, n_segnali, sev_max,
        salute_pv=salute_pv, incompleti_ids=incompleti_ids,
        n_fatture_da_collocare=n_da_collocare,
    )

    return GruppoOverviewResponse(
        nome_gruppo=nome_gruppo,
        num_pv=len(sedi),
        periodo_label=periodo_label,
        briefing=briefing,
        kpi=kpi,
        mol_mensile=mol_mensile,
        mol_mensile_anno=anno,
        salute_indice=salute_indice,
        salute_colore=salute_colore,
        salute_pv=salute_pv,
        ranking=ranking,
    )


# ═══════════════════════════════════════════════════════════════════════════
# FINESTRA "SPESA PER PV" — pivot righe=dimensione × colonne=PV
# ═══════════════════════════════════════════════════════════════════════════

class SpesaPivotRow(BaseModel):
    dim_val: str                    # categoria o fornitore
    emoji: Optional[str] = None     # icona categoria (None per fornitore)
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

    # Icone categoria dal catalogo (solo dimensione=categoria): 1 query, non per riga.
    emoji_map: Dict[str, str] = {}
    if dimensione == "categoria":
        try:
            cat_rows = (sb.table("categorie").select("nome,icona").execute()).data or []
            emoji_map = {
                (c.get("nome") or "").strip(): (c.get("icona") or "").strip()
                for c in cat_rows
                if (c.get("icona") or "").strip()
            }
        except Exception:
            emoji_map = {}

    grand_total = sum(totali_pv.values())
    rows: List[SpesaPivotRow] = []
    for dim_val, per_pv in agg.items():
        tot = sum(per_pv.values())
        rows.append(SpesaPivotRow(
            dim_val=dim_val,
            emoji=emoji_map.get(dim_val.strip()) or None,
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
    n_incompleti: int = 0               # sedi senza dati completi (margine gruppo parziale)


@router.get(
    "/api/gruppo/margini-coperti",
    tags=["Catena"],
    summary="Finestra Margini e Coperti per PV (da margini_mensili, anno corrente)",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_margini_coperti(
    mese: Optional[int] = None,
    authorization: Optional[str] = Header(None),
) -> MarginiCopertiResponse:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    anno, mese_corr = _anno_mese_corrente()
    mese_sel = mese if (mese and 1 <= mese <= 12) else None
    periodo_label = (
        f"{_MESI_IT[mese_sel - 1].capitalize()} {anno}" if mese_sel else f"Anno {anno}"
    )

    # margini_mensili: ricavi + costi MANUALI + quote riparto + coperti (già
    # pre-aggregata, 1 riga per sede×mese). Mese specifico se richiesto, altrimenti
    # l'anno FINO AL MESE CORRENTE (no mesi futuri, vedi gruppo_overview).
    q = (
        sb.table("margini_mensili")
        .select(
            "ristorante_id,mese,fatturato_netto,fatturato_iva10,fatturato_iva22,"
            "altri_ricavi_noiva,altri_costi_fb,altri_costi_spese,"
            "quote_riparto_fb,quote_riparto_spese,"
            "costo_dipendenti,costo_personale_extra,coperti"
        )
        .in_("ristorante_id", ids)
        .eq("anno", anno)
    )
    q = q.eq("mese", mese_sel) if mese_sel else q.lte("mese", mese_corr)
    mm_resp = q.execute()

    # Costi automatici F&B/spese LIVE per (sede, mese), come gruppo_overview e la
    # pagina Margini del PV: MOL e €MP/coperto non dipendono più dallo snapshot
    # costi_fb_totali/mol (a 0 finché nessuno salva la pagina Margini della sede).
    from services.margine_service import calcola_costi_automatici_gruppo_sql
    costi_auto_gruppo = calcola_costi_automatici_gruppo_sql(user_id, ids, anno)

    # Ricavi/coperti in modalità mensile: stessa fonte del PV (vedi gruppo_overview).
    overrides_gruppo = {rid: _overrides_mese_sede(sb, rid, anno) for rid in ids}

    # Un PV è "incompleto" se gli mancano i dati base (fatturato/fatture costo/
    # personale): stesso criterio del briefing/overview. Senza, mostrerebbe 0% in
    # rosso (sembra in perdita) invece di "dati incompleti".
    try:
        incompleti_set = set(_completezza_dati_pv(sb, ids).keys())
    except Exception:
        incompleti_set = set()

    # Stessa formula di gruppo_overview e del PV (helper condiviso: una sola copia).
    mesi_periodo = [mese_sel] if mese_sel else list(range(1, mese_corr + 1))
    agg = _aggrega_sedi_mensili(
        ids=ids,
        righe_mm=(mm_resp.data or []),
        costi_auto=costi_auto_gruppo,
        overrides=overrides_gruppo,
        mesi=mesi_periodo,
    )

    def _riga(rid: str, nome: str, a: Dict[str, float], incompleti: bool) -> MarginiCopertiPV:
        netto = a["netto"]
        cop = int(round(a["cop"]))
        cop_fb = int(round(a["cop_fb"]))  # coperti dei soli mesi con costo F&B
        # Tutto su base NETTA, coerente con la pagina Margini/Coperti del PV: così
        # fatturato, margine % e scontrino medio quadrano tra loro (scontrino =
        # fatturato/coperti). Il LORDO (IVA inclusa) resta nei "conti del gruppo".
        return MarginiCopertiPV(
            ristorante_id=rid,
            nome=nome,
            margine_perc=None if incompleti else round(a["mol"] / netto * 100, 1),
            fatturato=round(netto, 2),
            coperti=cop,
            scontrino_medio=round(netto / cop, 2) if cop > 0 else None,
            mp_per_coperto=round(a["fb"] / cop_fb, 2) if (cop_fb > 0 and a["fb"] > 0) else None,
            dati_incompleti=incompleti,
        )

    righe = [
        _riga(rid, rid_to_nome[rid], agg[rid], agg[rid]["netto"] <= 0 or rid in incompleti_set)
        for rid in ids
    ]
    righe.sort(key=lambda x: (x.dati_incompleti, -(x.margine_perc or 0), x.nome))

    tot = {
        "netto": sum(a["netto"] for a in agg.values()),
        "lordo": sum(a["lordo"] for a in agg.values()),
        "mol": sum(a["mol"] for a in agg.values()),
        "fb": sum(a["fb"] for a in agg.values()),
        "cop": sum(a["cop"] for a in agg.values()),
        "cop_fb": sum(a["cop_fb"] for a in agg.values()),
    }
    gruppo = _riga("", f"Gruppo {nome_gruppo}", tot, tot["netto"] <= 0)

    return MarginiCopertiResponse(
        nome_gruppo=nome_gruppo,
        periodo_label=periodo_label,
        righe=righe,
        gruppo=gruppo,
        n_incompleti=sum(1 for r in righe if r.dati_incompleti),
    )


# ═══════════════════════════════════════════════════════════════════════════
# FINESTRA "SPRECO PER CATEGORIA" — €MP/coperto per categoria, CONFRONTO PV
# ═══════════════════════════════════════════════════════════════════════════
# Stessa analisi del PV singolo (coperti-tab → "Costo materia prima per coperto ·
# per categoria"), ma PIVOTATA per confronto tra punti vendita: righe = categoria,
# colonne = PV. Cella = costo F&B della categoria ÷ coperti, sui SOLI mesi con
# costo (stesso metodo di margini-coperti: i mesi con coperti ma fatture non
# ancora arrivate non diluiscono la media). SHOP escluso (merce da rivendita).


class SprecoCategoriaCella(BaseModel):
    ristorante_id: str
    valore: Optional[float] = None      # €MP/coperto della categoria per quel PV


class SprecoCategoriaRiga(BaseModel):
    categoria: str
    per_pv: List[SprecoCategoriaCella]  # un valore per ogni PV (stesso ordine di pv)
    media_gruppo: Optional[float] = None  # costo totale ÷ coperti totali (pesata)


class SprecoCategoriePV(BaseModel):
    ristorante_id: str
    nome: str
    dati_incompleti: bool


class SprecoCategorieResponse(BaseModel):
    nome_gruppo: str
    periodo_label: str
    pv: List[SprecoCategoriePV]          # intestazioni colonne (i punti vendita)
    righe: List[SprecoCategoriaRiga]     # ordinate per media gruppo decrescente


# SHOP fuori: è merce da rivendita, non materia prima di cucina (come nel PV).
_SPRECO_CAT_ESCLUSE = {"SHOP"}


@router.get(
    "/api/gruppo/spreco-categorie",
    tags=["Catena"],
    summary="Finestra Spreco per categoria (€MP/coperto per PV), anno corrente",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_spreco_categorie(
    mese: Optional[int] = None,
    authorization: Optional[str] = Header(None),
) -> SprecoCategorieResponse:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    anno, mese_corr = _anno_mese_corrente()
    mese_sel = mese if (mese and 1 <= mese <= 12) else None
    periodo_label = (
        f"{_MESI_IT[mese_sel - 1].capitalize()} {anno}" if mese_sel else f"Anno {anno}"
    )
    fw = _fw()

    # Periodo: mese singolo o anno fino al mese corrente (no mesi futuri, come
    # margini-coperti). Le date servono all'aggregatore fatture per categoria.
    if mese_sel:
        mesi_target = [(anno, mese_sel)]
    else:
        mesi_target = [(anno, m) for m in range(1, mese_corr + 1)]
    data_da = f"{mesi_target[0][0]}-{mesi_target[0][1]:02d}-01"
    ult_y, ult_m = mesi_target[-1]
    ult_giorno = 31 if ult_m in (1, 3, 5, 7, 8, 10, 12) else (29 if ult_m == 2 else 30)
    data_a = f"{ult_y}-{ult_m:02d}-{ult_giorno:02d}"

    try:
        incompleti_set = set(_completezza_dati_pv(sb, ids).keys())
    except Exception:
        incompleti_set = set()

    # Coperti per (rid, anno, mese): margini_mensili + override mensile (stessa
    # fonte del PV). Una sola lettura per tutti i PV.
    mm_resp = (
        sb.table("margini_mensili")
        .select("ristorante_id,anno,mese,coperti")
        .in_("ristorante_id", ids)
        .eq("anno", anno)
        .execute()
    )
    cop_map: Dict[tuple, int] = {}
    for r in (mm_resp.data or []):
        if r.get("coperti") is None:
            continue
        cop_map[(str(r["ristorante_id"]), int(r["anno"]), int(r["mese"]))] = int(r["coperti"])
    for rid in ids:
        try:
            ov = fw._load_mensile_overrides(sb, rid, [anno])
        except Exception:
            ov = {}
        for (y, m), o in ov.items():
            if o.get("coperti") is not None:
                cop_map[(rid, y, m)] = o["coperti"]

    # Costo F&B per (anno, mese, categoria) per ogni PV. Riuso l'aggregatore del
    # worker, una chiamata per PV (i PV sono pochi: niente N+1 di rilievo).
    # acc[(categoria, rid)] = {"costo": Σ costo (mesi con costo), "cop": Σ coperti}
    acc: Dict[tuple, Dict[str, float]] = {}
    categorie_viste: set = set()
    for rid in ids:
        try:
            cat_map = fw._load_fatture_fb_per_categoria_e_mese(sb, rid, data_da, data_a)
        except Exception as exc:
            logger.warning("spreco-categorie: aggregazione fatture fallita (%s): %s", rid, exc)
            cat_map = {}
        for (y, m, cat) in list(cat_map.keys()):
            if cat in _SPRECO_CAT_ESCLUSE:
                continue
            if (y, m) not in mesi_target:
                continue
            costo = float(cat_map.get((y, m, cat), 0.0))
            cop = cop_map.get((rid, y, m), 0)
            if costo <= 0 or cop <= 0:
                continue
            categorie_viste.add(cat)
            a = acc.setdefault((cat, rid), {"costo": 0.0, "cop": 0.0})
            a["costo"] += costo
            a["cop"] += cop

    pv = [
        SprecoCategoriePV(
            ristorante_id=rid,
            nome=rid_to_nome[rid],
            dati_incompleti=(rid in incompleti_set),
        )
        for rid in ids
    ]

    righe: List[SprecoCategoriaRiga] = []
    for cat in sorted(categorie_viste):
        celle: List[SprecoCategoriaCella] = []
        tot_costo = 0.0
        tot_cop = 0.0
        for rid in ids:
            a = acc.get((cat, rid))
            if a and a["cop"] > 0 and a["costo"] > 0:
                celle.append(SprecoCategoriaCella(
                    ristorante_id=rid, valore=round(a["costo"] / a["cop"], 2),
                ))
                tot_costo += a["costo"]
                tot_cop += a["cop"]
            else:
                celle.append(SprecoCategoriaCella(ristorante_id=rid, valore=None))
        media = round(tot_costo / tot_cop, 2) if (tot_cop > 0 and tot_costo > 0) else None
        righe.append(SprecoCategoriaRiga(categoria=cat, per_pv=celle, media_gruppo=media))

    righe.sort(key=lambda r: (r.media_gruppo if r.media_gruppo is not None else -1), reverse=True)

    return SprecoCategorieResponse(
        nome_gruppo=nome_gruppo,
        periodo_label=periodo_label,
        pv=pv,
        righe=righe,
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
    tipo: str                       # "dati_mancanti" | "margine_calo" | "prezzi_sopra" | "ricavi_mancanti"
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


# Catalogo dei segnali di catena (per la config "Configura assistente catena").
_SEGNALI_CATALOGO = [
    {"key": "dati_mancanti", "label": "Dati mancanti nei PV",
     "descrizione": "Avvisa quando a un PV mancano fatturato, fatture costo o costo personale: senza, i confronti di margine sono falsi."},
    {"key": "margine_calo", "label": "Margine in calo",
     "descrizione": "Avvisa quando il margine di un PV scende sotto la media dei mesi precedenti."},
    {"key": "prezzi_sopra", "label": "Prezzi sopra la media catena",
     "descrizione": "Avvisa quando un PV paga una categoria più della media del gruppo."},
    {"key": "ricavi_mancanti", "label": "Ricavi mancanti",
     "descrizione": "Avvisa quando un PV non ha ricavi registrati nel mese in corso."},
]
_SEGNALI_KEYS = {s["key"] for s in _SEGNALI_CATALOGO}


def _gruppo_chat_disabilitata(sb, user_id: str) -> bool:
    """True se la chat di catena è spenta dal «Configura assistente» (toggle a
    livello account, indipendente dal pool). Default False (accesa)."""
    try:
        r = (
            sb.table("gruppo_assistant_config")
            .select("chat_disabilitata")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if r.data:
            return bool(r.data[0].get("chat_disabilitata"))
    except Exception:
        pass
    return False


def _get_gruppo_config(sb, user_id: str) -> tuple:
    """(segnali_disattivati:set, pv_esclusi:set) dalla config assistente catena.
    Default (nessuna riga) = tutto attivo, nessun PV escluso."""
    try:
        r = (
            sb.table("gruppo_assistant_config")
            .select("segnali_disattivati,pv_esclusi")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if r.data:
            row = r.data[0]
            return (
                set(row.get("segnali_disattivati") or []),
                set(str(x) for x in (row.get("pv_esclusi") or [])),
            )
    except Exception:
        pass
    return set(), set()


def _elenco_it(voci: List[str]) -> str:
    """Unisce le voci in italiano: 'a', 'a e b', 'a, b e c'."""
    if not voci:
        return ""
    if len(voci) == 1:
        return voci[0]
    return ", ".join(voci[:-1]) + " e " + voci[-1]


def _completezza_dati_pv(
    sb, ids: List[str], rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, List[str]]:
    """Per ogni PV, la lista dei dati BASE mancanti (vuota = completo).

    Criterio deciso (presenza dati, non % salute): un PV è affidabile per i confronti
    di margine/MOL solo se ha fatturato + fatture costo (F&B) + costo personale del
    mese. Riusa la RPC gruppo_salute_componenti (netto/personale/n_fatture). `rows`
    opzionale per riusare una RPC gia' fatta (overview). Best-effort."""
    out: Dict[str, List[str]] = {}
    if not ids:
        return out
    if rows is None:
        rows = _salute_componenti_raw(sb, ids)
    by_id = {str(r.get("ristorante_id")): r for r in (rows or [])}
    for rid in ids:
        r = by_id.get(rid) or {}
        manca: List[str] = []
        if float(r.get("netto") or 0) <= 0:
            manca.append("il fatturato")
        if int(r.get("n_fatture") or 0) <= 0:
            manca.append("le fatture costo")
        if float(r.get("personale") or 0) <= 0:
            manca.append("il costo del personale")
        if manca:
            out[rid] = manca
    return out


def _calcola_segnali(
    sb,
    ids: List[str],
    rid_to_nome: Dict[str, str],
    segnali_off: Optional[set] = None,
    pv_esclusi: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Calcola i 3 segnali di analisi della catena. Tutto SQL aggregato / letture
    su tabelle pre-aggregate — niente full-load righe fattura.

    Config assistente catena: `pv_esclusi` toglie i PV da OGNI segnale (anche dalla
    media catena dei prezzi); `segnali_off` disattiva interi tipi di segnale."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        oggi = _dt.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = _dt.now().date()

    segnali: List[Dict[str, Any]] = []

    segnali_off = segnali_off or set()
    if pv_esclusi:
        ids = [r for r in ids if r not in pv_esclusi]

    # ── Segnale 0: dati mancanti per PV (la catena INDIRIZZA, non spiega) ──
    # Completezza per PRESENZA di dati (non % salute): un PV è affidabile solo se ha
    # fatturato + fatture costo (F&B) + costo personale del mese. Senza, margine e
    # MOL del PV (e del gruppo) sono falsi: lo si dice PRIMA di ogni confronto, e si
    # manda l'utente nel PV a sistemare (il dettaglio del cosa fare è nella Home PV).
    # Riusa la RPC della salute (stesse componenti netto/personale/n_fatture).
    if "dati_mancanti" not in segnali_off:
        try:
            comp = _completezza_dati_pv(sb, ids)
            for rid in ids:
                manca = comp.get(rid)
                if manca:
                    segnali.append({
                        "tipo": "dati_mancanti",
                        "severity": "warning",
                        "ristorante_id": rid,
                        "pv_nome": rid_to_nome[rid],
                        "testo": "Mancano " + _elenco_it(manca) + " — vai a completare nel punto vendita",
                        "cta_page": "/dashboard",
                    })
        except Exception:
            pass

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
    # Un PV ha "ricavi" se ne ha registrato in QUALSIASI modo del mese: giornalieri
    # (import gestionale) O mensili (margini_mensili / override modalità mensile).
    # Controllare solo i giornalieri darebbe falsi positivi ai clienti in modalità
    # mensile. 3 query AGGREGATE (no loop per-PV).
    if "ricavi_mancanti" not in segnali_off:
        primo_mese = oggi.replace(day=1).isoformat()
        con_ricavi: set = set()
        try:
            rg = (
                sb.table("ricavi_giornalieri").select("ristorante_id")
                .in_("ristorante_id", ids).gte("data", primo_mese).lte("data", oggi.isoformat())
                .execute()
            )
            con_ricavi |= {str(r.get("ristorante_id")) for r in (rg.data or [])}
        except Exception:
            pass
        try:
            mmc = (
                sb.table("margini_mensili").select("ristorante_id,fatturato_netto")
                .in_("ristorante_id", ids).eq("anno", oggi.year).eq("mese", oggi.month)
                .execute()
            )
            con_ricavi |= {str(r.get("ristorante_id")) for r in (mmc.data or []) if float(r.get("fatturato_netto") or 0) > 0}
        except Exception:
            pass
        try:
            rmm = (
                sb.table("ricavi_modalita_mensile").select("ristorante_id")
                .in_("ristorante_id", ids).eq("anno", oggi.year).eq("mese", oggi.month)
                .execute()
            )
            con_ricavi |= {str(r.get("ristorante_id")) for r in (rmm.data or [])}
        except Exception:
            pass
        for rid in ids:
            if rid not in con_ricavi:
                segnali.append({
                    "tipo": "ricavi_mancanti",
                    "severity": "warning",
                    "ristorante_id": rid,
                    "pv_nome": rid_to_nome[rid],
                    "testo": "Nessun ricavo registrato questo mese",
                    "cta_page": "/margini",
                })

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

    # Tipi di segnale disattivati dalla config: fuori.
    if segnali_off:
        segnali = [s for s in segnali if s["tipo"] not in segnali_off]

    # Ordine: i DATI MANCANTI per primi (senza, il resto è falso), poi per gravità,
    # poi per nome PV. La catena indirizza: prima "vai a completare", poi i confronti.
    sev_rank = {"error": 0, "warning": 1, "info": 2}
    tipo_rank = {"dati_mancanti": 0}
    segnali.sort(key=lambda s: (
        tipo_rank.get(s["tipo"], 1),
        sev_rank.get(s["severity"], 9),
        s["pv_nome"],
    ))
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

    seg_off, pv_excl = _get_gruppo_config(sb, user_id)
    segnali = _calcola_segnali(sb, ids, rid_to_nome, seg_off, pv_excl)
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
# CONFIGURA ASSISTENTE CATENA — quali segnali attivi, su quali PV (per account)
# ═══════════════════════════════════════════════════════════════════════════

class GruppoAssistantSegnale(BaseModel):
    key: str
    label: str
    descrizione: str
    enabled: bool


class GruppoAssistantPV(BaseModel):
    ristorante_id: str
    nome: str
    incluso: bool


class GruppoAssistantConfigResponse(BaseModel):
    nome_gruppo: str
    chat_enabled: bool
    segnali: List[GruppoAssistantSegnale]
    pv: List[GruppoAssistantPV]


class GruppoAssistantConfigSave(BaseModel):
    nome_gruppo: Optional[str] = None
    chat_enabled: Optional[bool] = None
    segnali_disattivati: List[str] = []
    pv_esclusi: List[str] = []


@router.get(
    "/api/gruppo/assistant-config",
    tags=["Catena"],
    summary="Config assistente catena: segnali attivi + PV inclusi",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_assistant_config_get(authorization: Optional[str] = Header(None)) -> GruppoAssistantConfigResponse:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    seg_off, pv_excl = _get_gruppo_config(sb, user_id)
    return GruppoAssistantConfigResponse(
        nome_gruppo=nome_gruppo,
        chat_enabled=not _gruppo_chat_disabilitata(sb, user_id),
        segnali=[
            GruppoAssistantSegnale(
                key=s["key"], label=s["label"], descrizione=s["descrizione"],
                enabled=s["key"] not in seg_off,
            )
            for s in _SEGNALI_CATALOGO
        ],
        pv=[
            GruppoAssistantPV(ristorante_id=rid, nome=rid_to_nome[rid], incluso=rid not in pv_excl)
            for rid in ids
        ],
    )


@router.post(
    "/api/gruppo/assistant-config",
    tags=["Catena"],
    summary="Salva config assistente catena (ricalcola i segnali di oggi)",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_assistant_config_save(
    body: GruppoAssistantConfigSave, authorization: Optional[str] = Header(None)
):
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    id_set = set(ids)
    seg_off = sorted({k for k in body.segnali_disattivati if k in _SEGNALI_KEYS})
    pv_excl = sorted({p for p in body.pv_esclusi if p in id_set})

    # nome_gruppo è l'etichetta del gruppo (saluto "Buongiorno, X" + testata): vive
    # su users. La aggiorniamo solo se è stata passata una stringa non vuota.
    if body.nome_gruppo is not None:
        nuovo = body.nome_gruppo.strip()[:60]
        if nuovo and nuovo != nome_gruppo:
            try:
                sb.table("users").update({"nome_gruppo": nuovo}).eq("id", user_id).execute()
            except Exception:
                pass

    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc).isoformat()
    payload = {
        "user_id": user_id,
        "segnali_disattivati": seg_off,
        "pv_esclusi": pv_excl,
        "updated_at": now,
    }
    # chat_enabled è opzionale: lo scriviamo solo se passato, così non azzeriamo il
    # toggle quando si salvano solo segnali/PV (upsert aggiorna solo le colonne date).
    if body.chat_enabled is not None:
        payload["chat_disabilitata"] = not body.chat_enabled
    sb.table("gruppo_assistant_config").upsert(payload, on_conflict="user_id").execute()
    # La config cambia i segnali: butto lo snapshot in cache così alla prossima
    # lettura si ricalcolano con le nuove regole (niente attesa fino a domani).
    try:
        sb.table("gruppo_segnali_state").delete().eq("user_id", user_id).execute()
    except Exception:
        pass
    return {"ok": True}


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
def gruppo_tag_descrizioni(q: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Descrizioni distinte su tutti i PV del gruppo (per costruire il tag).

    `q` = ricerca testo lato DB su TUTTE le sedi: senza, restituisce le prime 500
    per spesa (lista iniziale); con testo, filtra fra tutte le descrizioni (così
    anche i prodotti meno costosi oltre le prime 500 sono trovabili)."""
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    q_clean = (q or "").strip() or None
    res = sb.rpc("gruppo_tag_descrizioni", {
        "p_ristorante_ids": ids, "p_q": q_clean, "p_limit": 500,
    }).execute()
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
    incidenza_pct: float                # % della spesa PV sul totale gruppo
    prezzo_medio: Optional[float]       # spesa/quantità del PV (None se quantità 0)


class TagFornitore(BaseModel):
    nome: str
    spesa: float
    incidenza_pct: float
    n_righe: int


class TagTrendPunto(BaseModel):
    anno: int
    mese: int
    spesa: float


class GruppoTagAnalisiResponse(BaseModel):
    tag_id: int
    nome: str
    emoji: Optional[str] = None
    periodo_label: str
    spesa_totale: float
    quantita_totale: float
    prezzo_medio: Optional[float]       # spesa/quantità di gruppo
    n_fornitori: int                    # fornitori distinti sul gruppo
    per_pv: List[TagAnalisiPV]
    fornitori: List[TagFornitore]
    trend: List[TagTrendPunto]


@router.get("/api/gruppo/tag/{tag_id}/analisi", tags=["Catena"], dependencies=[Depends(_verify_worker_key)])
def gruppo_tag_analisi(
    tag_id: int,
    mese: Optional[int] = None,
    authorization: Optional[str] = Header(None),
) -> GruppoTagAnalisiResponse:
    """Analisi ricca del tag di catena, tutto via RPC SQL (no full-load):
    per-PV (spesa, quantità, prezzo medio, incidenza, fornitori), classifica
    fornitori del gruppo e trend mensile. `mese` opzionale per il periodo."""
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    tag_row = (
        sb.table("gruppo_tags").select("id,nome,emoji").eq("id", int(tag_id)).eq("user_id", user_id).limit(1).execute()
    ).data or []
    if not tag_row:
        raise HTTPException(status_code=404, detail="Tag di catena non trovato")
    nome = tag_row[0].get("nome") or "Tag"
    emoji = tag_row[0].get("emoji")

    keys = [
        r["descrizione_key"]
        for r in (
            sb.table("gruppo_tag_prodotti").select("descrizione_key")
            .eq("tag_id", int(tag_id)).eq("user_id", user_id).execute()
        ).data or []
    ]

    # Periodo: mese specifico o anno corrente fino a oggi (coerente con le altre
    # finestre catena, niente mesi futuri).
    import calendar as _cal
    anno, mese_corr = _anno_mese_corrente()
    mese_sel = mese if (mese and 1 <= mese <= 12) else None
    if mese_sel:
        da = f"{anno}-{mese_sel:02d}-01"
        a = f"{anno}-{mese_sel:02d}-{_cal.monthrange(anno, mese_sel)[1]:02d}"
        periodo_label = f"{_MESI_IT[mese_sel - 1].capitalize()} {anno}"
    else:
        da = f"{anno}-01-01"
        a = f"{anno}-{mese_corr:02d}-{_cal.monthrange(anno, mese_corr)[1]:02d}"
        periodo_label = f"Anno {anno}"

    per_pv: List[TagAnalisiPV] = []
    fornitori: List[TagFornitore] = []
    trend: List[TagTrendPunto] = []
    if keys:
        params = {
            "p_ristorante_ids": ids, "p_descrizione_keys": keys,
            "p_data_da": da, "p_data_a": a,
        }
        res = sb.rpc("gruppo_tag_analisi", params).execute()
        by_rid = {str(r.get("ristorante_id")): r for r in (res.data or [])}
        tot = sum(float(r.get("spesa") or 0) for r in (res.data or []))
        for rid in ids:
            r = by_rid.get(rid)
            spesa = float(r.get("spesa") or 0) if r else 0.0
            qta = float(r.get("quantita") or 0) if r else 0.0
            per_pv.append(TagAnalisiPV(
                ristorante_id=rid,
                nome=rid_to_nome[rid],
                spesa=round(spesa, 2),
                quantita=round(qta, 2),
                n_righe=int(r.get("n_righe") or 0) if r else 0,
                n_fornitori=int(r.get("n_fornitori") or 0) if r else 0,
                incidenza_pct=round(spesa / tot * 100, 1) if tot > 0 else 0.0,
                prezzo_medio=round(spesa / qta, 2) if qta > 0 else None,
            ))
        per_pv.sort(key=lambda x: -x.spesa)

        f_res = sb.rpc("gruppo_tag_fornitori", params).execute()
        tot_f = sum(float(r.get("spesa") or 0) for r in (f_res.data or []))
        for r in (f_res.data or []):
            sp = float(r.get("spesa") or 0)
            fornitori.append(TagFornitore(
                nome=r.get("fornitore") or "—",
                spesa=round(sp, 2),
                incidenza_pct=round(sp / tot_f * 100, 1) if tot_f > 0 else 0.0,
                n_righe=int(r.get("n_righe") or 0),
            ))

        t_res = sb.rpc("gruppo_tag_trend", params).execute()
        trend = [
            TagTrendPunto(
                anno=int(r.get("anno")), mese=int(r.get("mese")),
                spesa=round(float(r.get("spesa") or 0), 2),
            )
            for r in (t_res.data or []) if r.get("mese") is not None
        ]

    spesa_totale = round(sum(p.spesa for p in per_pv), 2)
    quantita_totale = round(sum(p.quantita for p in per_pv), 2)
    return GruppoTagAnalisiResponse(
        tag_id=int(tag_id),
        nome=nome,
        emoji=emoji,
        periodo_label=periodo_label,
        spesa_totale=spesa_totale,
        quantita_totale=quantita_totale,
        prezzo_medio=round(spesa_totale / quantita_totale, 2) if quantita_totale > 0 else None,
        n_fornitori=len(fornitori),
        per_pv=per_pv,
        fornitori=fornitori,
        trend=trend,
    )


# ═══════════════════════════════════════════════════════════════════════════
# CHAT CATENA — config del pool AI (limite gruppo + domande oggi)
# ═══════════════════════════════════════════════════════════════════════════

class GruppoChatConfig(BaseModel):
    enabled: bool                 # pool > 0 (almeno una sede non-free)
    limite_giorno: int            # SOMMA dei limiti effettivi delle sedi
    domande_oggi: int             # richieste chat dell'account già fatte oggi


@router.get(
    "/api/gruppo/chat-config",
    tags=["Catena"],
    summary="Config chat catena: pool AI unico (limite gruppo + domande oggi)",
    dependencies=[Depends(_verify_worker_key)],
)
def gruppo_chat_config(authorization: Optional[str] = Header(None)) -> GruppoChatConfig:
    sb, user_id, sedi, nome_gruppo, rid_to_nome, ids = _resolve_gruppo(authorization)
    user = _resolve_user_from_token(authorization)
    limite = _chat_limite_pool_gruppo(user, sb)
    # Domande oggi a livello account: conteggio per user_id (ristorante_id=None) →
    # tutte le righe chat dell'account (catena + ogni PV), coerente col pool unico.
    domande = _chat_domande_oggi(None, user_id, sb)
    return GruppoChatConfig(
        enabled=limite > 0 and not _gruppo_chat_disabilitata(sb, user_id),
        limite_giorno=limite,
        domande_oggi=domande,
    )
