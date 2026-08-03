"""Router dominio WORKSPACE — foodcost (ricette/ingredienti), inventario, diario,
personale (turni, regole ricorrenti), spese extra.

Estratto da fastapi_worker.py. Gli helper condivisi (_verify_worker_key,
_resolve_user_from_token, _get_supabase_client, _get_ristorante_id_for_user,
_oggi_rome, _ore_turno, logger) restano nel worker e sono importati da qui.
_ore_turno in particolare e' condiviso col router margini, quindi NON viene
spostato. Logica copiata identica. Path/gate/response invariati.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI (workspace.X) e mai i lookup di nome globale bare dentro le funzioni di
# questo modulo -> quegli usi davano NameError -> HTTP 500 su ogni endpoint.
# _verify_worker_key resta esplicito perche' usato in Depends() a import-time
# (firma identica per l'iniezione FastAPI).
def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _get_ristorante_id_for_user(*args, **kwargs):
    return _fw()._get_ristorante_id_for_user(*args, **kwargs)


def _oggi_rome(*args, **kwargs):
    return _fw()._oggi_rome(*args, **kwargs)


def _ore_turno(*args, **kwargs):
    return _fw()._ore_turno(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# WORKSPACE / FOODCOST
# ═══════════════════════════════════════════════════════════════════════════

class NuovaRicettaBody(BaseModel):
    nome: str
    categoria: str
    prezzo_vendita_ivainc: Optional[float] = None
    righe: list[dict]  # lista ingredienti con quantita/um/tipo/prezzi


class CalcolaRigheBody(BaseModel):
    righe: list[dict]


class NuovoIngredienteManualeBody(BaseModel):
    nome: str
    prezzo_per_um: float
    um: str


class AggiornaIngredienteManualeBody(BaseModel):
    nome: Optional[str] = None
    prezzo_per_um: Optional[float] = None
    um: Optional[str] = None


@router.get("/api/workspace/foodcost/ingredienti", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_ingredienti(authorization: Optional[str] = Header(None)):
    """Lista unificata: articoli da fatture + ingredienti manuali + semilavorati."""
    from services.foodcost_service import get_articoli_da_fatture

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    articoli = get_articoli_da_fatture(sb, user_id, ristorante_id)

    manuali_resp = (
        sb.table("ingredienti_workspace")
        .select("id,nome,prezzo_per_um,um")
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .order("nome")
        .execute()
    )
    manuali = manuali_resp.data or []

    semi_resp = (
        sb.table("ricette")
        .select("id,nome,foodcost_totale")
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .eq("categoria", "SEMILAVORATI")
        .execute()
    )
    semilavorati = semi_resp.data or []

    return {
        "articoli": [{"tipo": "articolo", **a} for a in articoli],
        "manuali": [
            {
                "tipo": "manuale",
                "id": m["id"],
                "nome": m["nome"],
                "prezzo_unitario": float(m["prezzo_per_um"]),
                "um": m["um"],
            }
            for m in manuali
        ],
        "semilavorati": [
            {
                "tipo": "semilavorato",
                "id": s["id"],
                "nome": s["nome"],
                "foodcost_ricetta": float(s["foodcost_totale"] or 0),
            }
            for s in semilavorati
        ],
    }


@router.get("/api/workspace/foodcost/ricette", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_ricette(authorization: Optional[str] = Header(None)):
    """Lista ricette con KPI calcolati (margine, incidenza%) + alert prezzo ingredienti."""
    from services.foodcost_service import arricchisci_ricetta, get_articoli_da_fatture

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    resp = (
        sb.table("ricette")
        .select("id,nome,categoria,foodcost_totale,prezzo_vendita_ivainc,ordine_visualizzazione,ingredienti")
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .order("ordine_visualizzazione")
        .execute()
    )

    # Mappa prezzo corrente articoli (da fatture) per alert prezzo aumentato
    try:
        prezzo_corrente = {a["nome"]: a["prezzo_unitario"] for a in get_articoli_da_fatture(sb, user_id, ristorante_id)}
    except Exception:
        prezzo_corrente = {}

    ricette = []
    for r in (resp.data or []):
        arr = arricchisci_ricetta(r)
        # Alert prezzo: confronta prezzo articolo salvato vs prezzo corrente fattura (soglia +5%)
        ings_raw = arr.pop("ingredienti", None) or "[]"
        if isinstance(ings_raw, str):
            try:
                ings_raw = json.loads(ings_raw)
            except Exception:
                ings_raw = []
        aumentati = []
        for riga in ings_raw:
            if riga.get("tipo") != "articolo" or riga.get("prezzo_override") is not None:
                continue
            stored = float(riga.get("prezzo_unitario") or 0)
            cur = prezzo_corrente.get(riga.get("nome"))
            if stored > 0 and cur and cur > stored * 1.05:
                aumentati.append(riga.get("nome"))
        arr["alert_prezzo"] = len(aumentati) > 0
        arr["ingredienti_aumentati"] = aumentati
        ricette.append(arr)

    # KPI globali
    con_prezzo = [r for r in ricette if r["margine"] is not None]
    kpi = {
        "totale": len(ricette),
        "costo_medio": round(sum(r["foodcost_totale"] for r in ricette) / len(ricette), 2) if ricette else 0,
        "margine_medio": round(sum(r["margine"] for r in con_prezzo) / len(con_prezzo), 2) if con_prezzo else None,
        "incidenza_media": round(sum(r["incidenza_pct"] for r in con_prezzo) / len(con_prezzo), 1) if con_prezzo else None,
    }

    # Aggregati per categoria
    from collections import defaultdict
    cat_map: dict = defaultdict(lambda: {"n": 0, "fc": 0.0, "margini": [], "incidenze": []})
    for r in ricette:
        c = cat_map[r["categoria"]]
        c["n"] += 1
        c["fc"] += float(r["foodcost_totale"] or 0)
        if r["margine"] is not None:
            c["margini"].append(r["margine"])
        if r["incidenza_pct"] is not None:
            c["incidenze"].append(r["incidenza_pct"])

    categorie = []
    for cat, d in sorted(cat_map.items()):
        categorie.append({
            "categoria": cat,
            "n_ricette": d["n"],
            "fc_totale": round(d["fc"], 2),
            "fc_medio": round(d["fc"] / d["n"], 2),
            "margine_medio": round(sum(d["margini"]) / len(d["margini"]), 2) if d["margini"] else None,
            "incidenza_media": round(sum(d["incidenze"]) / len(d["incidenze"]), 1) if d["incidenze"] else None,
        })

    return {"ricette": ricette, "kpi": kpi, "categorie": categorie}


@router.get("/api/workspace/foodcost/ricette/{ricetta_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_ricetta_detail(ricetta_id: str, authorization: Optional[str] = Header(None)):
    """Ricetta completa con righe ingrediente."""
    from services.foodcost_service import arricchisci_ricetta

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)

    resp = (
        sb.table("ricette")
        .select("id,nome,categoria,foodcost_totale,prezzo_vendita_ivainc,ingredienti,ordine_visualizzazione")
        .eq("id", ricetta_id)
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    r = resp.data[0]
    ingredienti = r.get("ingredienti") or "[]"
    if isinstance(ingredienti, str):
        try:
            ingredienti = json.loads(ingredienti)
        except Exception:
            ingredienti = []

    return {**arricchisci_ricetta(r), "righe": ingredienti}


@router.post("/api/workspace/foodcost/calcola", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_calcola(body: CalcolaRigheBody, authorization: Optional[str] = Header(None)):
    """Ricalcola foodcost righe senza salvare (usato dall'editor live)."""
    from services.foodcost_service import calcola_ricetta, calcola_costo_riga, IVA_RISTORAZIONE

    _resolve_user_from_token(authorization)

    costi = []
    for r in body.righe:
        try:
            c = calcola_costo_riga(
                tipo=r.get("tipo", "articolo"),
                prezzo_unitario=float(r.get("prezzo_unitario", 0) or 0),
                um_db=r.get("um_db", "KG"),
                quantita=float(r.get("quantita", 0) or 0),
                um_richiesta=r.get("um", "KG"),
                grammatura_confezione=r.get("grammatura_confezione"),
                grammatura_um=r.get("grammatura_um"),
                prezzo_override=r.get("prezzo_override"),
                foodcost_ricetta=r.get("foodcost_ricetta"),
            )
        except Exception:
            c = 0.0
        costi.append(round(c, 4))

    fc_totale = round(sum(costi), 4)
    return {"costi_righe": costi, "foodcost_totale": fc_totale}


@router.post("/api/workspace/foodcost/ricette", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_crea_ricetta(body: NuovaRicettaBody, authorization: Optional[str] = Header(None)):
    """Crea nuova ricetta. Il foodcost_totale è calcolato dal server."""
    from services.foodcost_service import calcola_ricetta, CATEGORIE_RICETTE

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if body.categoria not in CATEGORIE_RICETTE:
        raise HTTPException(status_code=422, detail=f"Categoria non valida: {body.categoria}")

    fc_totale = calcola_ricetta(body.righe)

    try:
        next_ordine_resp = sb.rpc("get_next_ordine_ricetta", {"p_user_id": user_id, "p_ristorante_id": ristorante_id}).execute()
        next_ordine = next_ordine_resp.data if next_ordine_resp.data else 1
    except Exception:
        q = sb.table("ricette").select("ordine_visualizzazione").eq("user_id", user_id).eq("ristorante_id", ristorante_id).order("ordine_visualizzazione", desc=True).limit(1).execute()
        next_ordine = (q.data[0]["ordine_visualizzazione"] + 1) if q.data else 1

    payload = {
        "user_id": user_id,
        "ristorante_id": ristorante_id,
        "nome": body.nome.strip(),
        "categoria": body.categoria,
        "ingredienti": json.dumps(body.righe),
        "foodcost_totale": fc_totale,
        "prezzo_vendita_ivainc": round(body.prezzo_vendita_ivainc, 2) if body.prezzo_vendita_ivainc else None,
        "ordine_visualizzazione": next_ordine,
    }
    resp = sb.table("ricette").insert(payload).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Errore salvataggio ricetta")
    return {"ok": True, "id": resp.data[0]["id"], "foodcost_totale": fc_totale}


@router.patch("/api/workspace/foodcost/ricette/{ricetta_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_aggiorna_ricetta(ricetta_id: str, body: NuovaRicettaBody, authorization: Optional[str] = Header(None)):
    """Aggiorna ricetta esistente. Il foodcost_totale è ricalcolato dal server."""
    from services.foodcost_service import calcola_ricetta, CATEGORIE_RICETTE

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)

    if body.categoria not in CATEGORIE_RICETTE:
        raise HTTPException(status_code=422, detail=f"Categoria non valida: {body.categoria}")

    fc_totale = calcola_ricetta(body.righe)
    payload = {
        "nome": body.nome.strip(),
        "categoria": body.categoria,
        "ingredienti": json.dumps(body.righe),
        "foodcost_totale": fc_totale,
        "prezzo_vendita_ivainc": round(body.prezzo_vendita_ivainc, 2) if body.prezzo_vendita_ivainc else None,
    }
    sb.table("ricette").update(payload).eq("id", ricetta_id).eq("user_id", user_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True, "foodcost_totale": fc_totale}


@router.delete("/api/workspace/foodcost/ricette/{ricetta_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_elimina_ricetta(ricetta_id: str, authorization: Optional[str] = Header(None)):
    """Elimina ricetta."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    sb.table("ricette").delete().eq("id", ricetta_id).eq("user_id", user_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


class RiordinaBody(BaseModel):
    ordine: list[str]  # lista di id ricetta nel nuovo ordine


@router.post("/api/workspace/foodcost/ricette/riordina", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_riordina_ricette(body: RiordinaBody, authorization: Optional[str] = Header(None)):
    """Aggiorna ordine_visualizzazione delle ricette secondo la lista di id ricevuta."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    for idx, rid in enumerate(body.ordine):
        sb.table("ricette").update({"ordine_visualizzazione": idx + 1}).eq("id", rid).eq("user_id", user_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


@router.get("/api/workspace/foodcost/ingredienti-manuali", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_ingredienti_manuali(authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    resp = sb.table("ingredienti_workspace").select("id,nome,prezzo_per_um,um").eq("user_id", user_id).eq("ristorante_id", ristorante_id).order("nome").execute()
    return {"ingredienti": resp.data or []}


@router.post("/api/workspace/foodcost/ingredienti-manuali", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_crea_ingrediente_manuale(body: NuovoIngredienteManualeBody, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    try:
        resp = sb.table("ingredienti_workspace").insert({
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "nome": body.nome.strip(),
            "prezzo_per_um": body.prezzo_per_um,
            "um": body.um.upper(),
        }).execute()
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Ingrediente già esistente")
        raise HTTPException(status_code=500, detail="Errore salvataggio")
    return {"ok": True, "id": resp.data[0]["id"]}


@router.patch("/api/workspace/foodcost/ingredienti-manuali/{ing_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_aggiorna_ingrediente_manuale(ing_id: str, body: AggiornaIngredienteManualeBody, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if "um" in payload:
        payload["um"] = payload["um"].upper()
    sb.table("ingredienti_workspace").update(payload).eq("id", ing_id).eq("user_id", user_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


@router.delete("/api/workspace/foodcost/ingredienti-manuali/{ing_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_elimina_ingrediente_manuale(ing_id: str, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    sb.table("ingredienti_workspace").delete().eq("id", ing_id).eq("user_id", user_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


# ─── Workspace: Inventario ──────────────────────────────────────────────────

class NuovaVoceInventarioBody(BaseModel):
    data_inventario: str
    nome: str
    categoria: str = ""
    quantita: float = 0
    um: str = "KG"
    prezzo_unitario: float = 0
    note: Optional[str] = None


class AggiornaVoceInventarioBody(BaseModel):
    nome: Optional[str] = None
    categoria: Optional[str] = None
    quantita: Optional[float] = None
    um: Optional[str] = None
    prezzo_unitario: Optional[float] = None
    note: Optional[str] = None


class CopiaSnapshotInventarioBody(BaseModel):
    data_source: str
    data_target: str


class VoceInventarioBatchItem(BaseModel):
    nome: str
    categoria: str = ""
    quantita: float = 0
    um: str = "KG"
    prezzo_unitario: float = 0
    note: Optional[str] = None


class NuoveVociInventarioBody(BaseModel):
    data_inventario: str
    voci: list[VoceInventarioBatchItem]


@router.get("/api/workspace/inventario/articoli", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_articoli(authorization: Optional[str] = Header(None)):
    """Articoli dalle fatture con categoria, per ricerca nell'inventario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    from config.constants import CATEGORIE_SPESE_GENERALI
    all_rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        resp = (
            sb.table("fatture")
            .select("descrizione,prezzo_unitario,unita_misura,categoria,data_documento")
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .not_.in_("categoria", CATEGORIE_SPESE_GENERALI)
            .order("data_documento", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    articoli_map: dict[str, dict] = {}
    for row in all_rows:
        desc = (row.get("descrizione") or "").strip()
        if not desc or desc in articoli_map:
            continue
        articoli_map[desc] = {
            "nome": desc,
            "categoria": row.get("categoria") or "",
            "prezzo_unitario": float(row.get("prezzo_unitario") or 0),
            "um": (row.get("unita_misura") or "PZ").upper(),
        }
    return {"articoli": list(articoli_map.values())}


@router.get("/api/workspace/inventario/snapshot-dates", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_snapshot_dates(authorization: Optional[str] = Header(None)):
    """Lista delle date con snapshot inventario salvati."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    resp = (
        sb.table("inventario_voci")
        .select("data_inventario,valore_totale")
        .eq("ristorante_id", ristorante_id)
        .order("data_inventario", desc=True)
        .execute()
    )
    from collections import defaultdict as _dd2
    snapshot_map: dict = _dd2(lambda: {"n_articoli": 0, "valore_totale": 0.0})
    for r in (resp.data or []):
        d = r["data_inventario"]
        snapshot_map[d]["n_articoli"] += 1
        snapshot_map[d]["valore_totale"] += float(r["valore_totale"] or 0)
    snapshots = [
        {
            "data_inventario": d,
            "n_articoli": s["n_articoli"],
            "valore_totale": round(s["valore_totale"], 2),
        }
        for d, s in sorted(snapshot_map.items(), reverse=True)
    ]
    return {"snapshots": snapshots}


@router.post("/api/workspace/inventario/copia-snapshot", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_copia_snapshot(body: CopiaSnapshotInventarioBody, authorization: Optional[str] = Header(None)):
    """Copia articoli da uno snapshot precedente alla data target (quantità = 0)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    resp = (
        sb.table("inventario_voci")
        .select("nome,categoria,um,prezzo_unitario")
        .eq("ristorante_id", ristorante_id)
        .eq("data_inventario", body.data_source)
        .execute()
    )
    source = resp.data or []
    if not source:
        raise HTTPException(status_code=404, detail="Snapshot sorgente non trovato")
    rows = [
        {
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "data_inventario": body.data_target,
            "nome": r["nome"],
            "categoria": r["categoria"],
            "quantita": 0,
            "um": r["um"],
            "prezzo_unitario": r["prezzo_unitario"],
        }
        for r in source
    ]
    sb.table("inventario_voci").insert(rows).execute()
    return {"ok": True, "n_articoli": len(rows)}


@router.get("/api/workspace/inventario", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_list(
    data: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """Lista voci inventario per una data specifica, con KPI e stats per categoria."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not data:
        data = _oggi_rome().isoformat()
    resp = (
        sb.table("inventario_voci")
        .select("id,data_inventario,nome,categoria,quantita,um,prezzo_unitario,valore_totale,note")
        .eq("ristorante_id", ristorante_id)
        .eq("data_inventario", data)
        .order("categoria")
        .order("nome")
        .execute()
    )
    voci = resp.data or []
    valore_totale = sum(float(v["valore_totale"] or 0) for v in voci)
    categorie_set = set(v["categoria"] for v in voci if v["categoria"])
    from collections import defaultdict as _dd3
    cat_map: dict = _dd3(lambda: {"n_articoli": 0, "valore_totale": 0.0})
    for v in voci:
        cat = v["categoria"] or "—"
        cat_map[cat]["n_articoli"] += 1
        cat_map[cat]["valore_totale"] += float(v["valore_totale"] or 0)
    categorie = [
        {
            "categoria": c,
            "n_articoli": s["n_articoli"],
            "valore_totale": round(s["valore_totale"], 2),
            "pct_totale": round(s["valore_totale"] / valore_totale * 100, 1) if valore_totale else 0,
        }
        for c, s in sorted(cat_map.items())
    ]
    return {
        "voci": voci,
        "kpi": {
            "n_articoli": len(voci),
            "n_categorie": len(categorie_set),
            "valore_totale": round(valore_totale, 2),
        },
        "categorie": categorie,
    }


@router.post("/api/workspace/inventario", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_crea(body: NuovaVoceInventarioBody, authorization: Optional[str] = Header(None)):
    """Aggiunge una voce all'inventario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    resp = sb.table("inventario_voci").insert({
        "user_id": user_id,
        "ristorante_id": ristorante_id,
        "data_inventario": body.data_inventario,
        "nome": body.nome.strip(),
        "categoria": body.categoria.strip(),
        "quantita": body.quantita,
        "um": body.um.upper(),
        "prezzo_unitario": body.prezzo_unitario,
        "note": body.note,
    }).execute()
    return {"ok": True, "id": resp.data[0]["id"]}


@router.post("/api/workspace/inventario/batch", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_crea_batch(body: NuoveVociInventarioBody, authorization: Optional[str] = Header(None)):
    """Aggiunge più voci all'inventario in un'unica operazione."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    rows = [
        {
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "data_inventario": body.data_inventario,
            "nome": v.nome.strip(),
            "categoria": v.categoria.strip(),
            "quantita": v.quantita,
            "um": v.um.upper(),
            "prezzo_unitario": v.prezzo_unitario,
            "note": v.note,
        }
        for v in body.voci
        if v.nome.strip()
    ]
    if not rows:
        raise HTTPException(status_code=400, detail="Nessuna voce valida da inserire")
    sb.table("inventario_voci").insert(rows).execute()
    return {"ok": True, "n_articoli": len(rows)}


@router.patch("/api/workspace/inventario/{voce_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_aggiorna(voce_id: str, body: AggiornaVoceInventarioBody, authorization: Optional[str] = Header(None)):
    """Aggiorna una voce inventario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if "um" in payload:
        payload["um"] = payload["um"].upper()
    sb.table("inventario_voci").update(payload).eq("id", voce_id).eq("user_id", user_id).execute()
    return {"ok": True}


@router.delete("/api/workspace/inventario/{voce_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_elimina(voce_id: str, authorization: Optional[str] = Header(None)):
    """Elimina una voce inventario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    sb.table("inventario_voci").delete().eq("id", voce_id).eq("user_id", user_id).execute()
    return {"ok": True}


@router.delete("/api/workspace/inventario", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_inventario_elimina_data(data: str = Query(..., description="Data inventario YYYY-MM-DD"), authorization: Optional[str] = Header(None)):
    """Elimina tutte le voci inventario per una data."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    resp = sb.table("inventario_voci").delete().eq("user_id", user_id).eq("data_inventario", data).execute()
    n = len(resp.data) if resp.data else 0
    return {"ok": True, "n_eliminate": n}


# ─── Workspace: Diario ──────────────────────────────────────────────────────

class NuovoEventoDiarioBody(BaseModel):
    data_evento: str  # YYYY-MM-DD
    titolo: str
    descrizione: Optional[str] = None
    ora_inizio: Optional[str] = None  # HH:MM
    ora_fine: Optional[str] = None
    colore: str = "sky"


class AggiornaEventoDiarioBody(BaseModel):
    data_evento: Optional[str] = None
    titolo: Optional[str] = None
    descrizione: Optional[str] = None
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    colore: Optional[str] = None


@router.get("/api/workspace/diario", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_diario_list(
    mese: Optional[str] = Query(None, description="YYYY-MM — filtra per mese"),
    authorization: Optional[str] = Header(None),
):
    """Lista eventi diario per il ristorante, opzionalmente filtrati per mese."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    q = sb.table("diario_eventi").select("*").eq("ristorante_id", ristorante_id)
    if mese:
        anno, mo = mese.split("-")
        import calendar
        ultimo_giorno = calendar.monthrange(int(anno), int(mo))[1]
        q = q.gte("data_evento", f"{mese}-01").lte("data_evento", f"{mese}-{ultimo_giorno:02d}")
    q = q.order("data_evento").order("ora_inizio", nullsfirst=True)
    resp = q.execute()
    return {"eventi": resp.data or []}


@router.post("/api/workspace/diario", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_diario_crea(body: NuovoEventoDiarioBody, authorization: Optional[str] = Header(None)):
    """Crea un nuovo evento nel diario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    payload: dict = {
        "ristorante_id": ristorante_id,
        "user_id": user_id,
        "data_evento": body.data_evento,
        "titolo": body.titolo.strip(),
        "colore": body.colore,
    }
    if body.descrizione is not None:
        payload["descrizione"] = body.descrizione
    if body.ora_inizio:
        payload["ora_inizio"] = body.ora_inizio
    if body.ora_fine:
        payload["ora_fine"] = body.ora_fine
    resp = sb.table("diario_eventi").insert(payload).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/workspace/diario/{evento_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_diario_aggiorna(evento_id: str, body: AggiornaEventoDiarioBody, authorization: Optional[str] = Header(None)):
    """Aggiorna un evento diario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    raw = body.model_dump(exclude_unset=True)
    # titolo/data_evento/colore: solo se valorizzati; orario/descrizione: azzerabili (null = reset)
    updates = {k: v for k, v in raw.items() if k in ("titolo", "data_evento", "colore") and v is not None}
    for campo in ("ora_inizio", "ora_fine", "descrizione"):
        if campo in raw:
            updates[campo] = raw[campo]
    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    resp = sb.table("diario_eventi").update(updates).eq("id", evento_id).eq("ristorante_id", ristorante_id).execute()
    return resp.data[0] if resp.data else {}


@router.delete("/api/workspace/diario/{evento_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_diario_elimina(evento_id: str, authorization: Optional[str] = Header(None)):
    """Elimina un evento diario."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    sb.table("diario_eventi").delete().eq("id", evento_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


# ─── Workspace: Dipendenti (anagrafica) ─────────────────────────────────────

class NuovoDipendenteBody(BaseModel):
    nome: str
    costo_orario_default: Optional[float] = None


class AggiornaDipendenteBody(BaseModel):
    nome: Optional[str] = None
    costo_orario_default: Optional[float] = None


def _dipendente_attivo_omonimo(sb, ristorante_id: str, nome_norm: str, escludi_id: Optional[str] = None):
    """Cerca un dipendente ATTIVO con lo stesso nome normalizzato (case/spazi
    insensitive). Usato per la guardia 409 su crea/rinomina/riattiva."""
    q = (
        sb.table("dipendenti").select("id,nome")
        .eq("ristorante_id", ristorante_id)
        .eq("attivo", True)
        .ilike("nome", nome_norm)
    )
    if escludi_id:
        q = q.neq("id", escludi_id)
    r = q.execute()
    return (r.data or [None])[0]


def _dipendente_disattivato_omonimo(sb, ristorante_id: str, nome_norm: str):
    """Cerca un dipendente DISATTIVATO con lo stesso nome normalizzato.
    Usato per suggerire la riattivazione invece di duplicare silenziosamente."""
    r = (
        sb.table("dipendenti").select("id,nome")
        .eq("ristorante_id", ristorante_id)
        .eq("attivo", False)
        .ilike("nome", nome_norm)
        .execute()
    )
    return (r.data or [None])[0]


@router.get("/api/workspace/dipendenti", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_list(
    attivo: Optional[bool] = Query(True, description="True = solo attivi (default), False = solo disattivati, None = tutti"),
    authorization: Optional[str] = Header(None),
):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    q = sb.table("dipendenti").select("*").eq("ristorante_id", ristorante_id)
    if attivo is not None:
        q = q.eq("attivo", attivo)
    resp = q.order("nome").execute()
    return {"dipendenti": resp.data or []}


@router.post("/api/workspace/dipendenti", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_crea(body: NuovoDipendenteBody, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    nome_norm = body.nome.strip()
    if not nome_norm:
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio")

    if _dipendente_attivo_omonimo(sb, ristorante_id, nome_norm):
        raise HTTPException(status_code=409, detail=f"{nome_norm} è già un dipendente attivo")
    disattivato = _dipendente_disattivato_omonimo(sb, ristorante_id, nome_norm)
    if disattivato:
        raise HTTPException(
            status_code=409,
            detail=f"{disattivato['nome']} esiste già ma è disattivato. Riattivalo invece di crearne un altro.",
        )

    payload: dict = {"ristorante_id": ristorante_id, "nome": nome_norm}
    if body.costo_orario_default is not None:
        payload["costo_orario_default"] = body.costo_orario_default
    resp = sb.table("dipendenti").insert(payload).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/workspace/dipendenti/{dipendente_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_aggiorna(dipendente_id: str, body: AggiornaDipendenteBody, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    raw = body.model_dump(exclude_unset=True)
    updates: dict = {}
    if "nome" in raw and raw["nome"] is not None:
        nome_norm = raw["nome"].strip()
        if not nome_norm:
            raise HTTPException(status_code=400, detail="Il nome è obbligatorio")
        if _dipendente_attivo_omonimo(sb, ristorante_id, nome_norm, escludi_id=dipendente_id):
            raise HTTPException(status_code=409, detail=f"{nome_norm} è già un altro dipendente attivo")
        updates["nome"] = nome_norm
    if "costo_orario_default" in raw:  # azzerabile
        updates["costo_orario_default"] = raw["costo_orario_default"]
    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    resp = (
        sb.table("dipendenti").update(updates)
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return resp.data[0]


@router.patch("/api/workspace/dipendenti/{dipendente_id}/disattiva", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_disattiva(dipendente_id: str, authorization: Optional[str] = Header(None)):
    """Soft-delete: nessuna guardia bloccante, i turni storici restano intatti
    (dipendente_id resta valido via FK RESTRICT)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    resp = (
        sb.table("dipendenti").update({"attivo": False})
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return resp.data[0]


@router.patch("/api/workspace/dipendenti/{dipendente_id}/riattiva", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_riattiva(dipendente_id: str, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    corrente = (
        sb.table("dipendenti").select("nome")
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .limit(1).execute()
    )
    if not corrente.data:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    nome_norm = corrente.data[0]["nome"].strip()
    conflitto = _dipendente_attivo_omonimo(sb, ristorante_id, nome_norm, escludi_id=dipendente_id)
    if conflitto:
        raise HTTPException(
            status_code=409,
            detail=f"Esiste già un altro dipendente attivo di nome {conflitto['nome']}",
        )
    resp = (
        sb.table("dipendenti").update({"attivo": True})
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .execute()
    )
    return resp.data[0] if resp.data else {}


@router.delete("/api/workspace/dipendenti/{dipendente_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_elimina(dipendente_id: str, authorization: Optional[str] = Header(None)):
    """Cancellazione definitiva, consentita SOLO se il dipendente non ha nessun
    turno registrato (creato per errore, mai usato). Con turni a carico si
    rifiuta e si rimanda alla disattivazione: cancellare cambierebbe
    retroattivamente il costo del personale di mesi già chiusi."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    corrente = (
        sb.table("dipendenti").select("id,nome")
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .limit(1).execute()
    )
    if not corrente.data:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    turni = (
        sb.table("turni_personale").select("id")
        .eq("ristorante_id", ristorante_id).eq("dipendente_id", dipendente_id)
        .limit(1).execute()
    ).data or []
    if turni:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{corrente.data[0]['nome']} ha turni registrati e non può essere eliminato: "
                "disattivalo, così lo storico dei costi resta intatto."
            ),
        )

    sb.table("dipendenti").delete().eq("id", dipendente_id).eq("ristorante_id", ristorante_id).execute()
    return {"eliminato": True, "nome": corrente.data[0]["nome"]}


@router.post("/api/workspace/dipendenti/{dipendente_id}/merge-in/{target_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_dipendenti_merge(dipendente_id: str, target_id: str, authorization: Optional[str] = Header(None)):
    """Sposta tutti i turni da dipendente_id a target_id, poi disattiva
    l'origine. Mai cancella turni. Utile per unire doppioni creati per errore
    (es. stesso dipendente inserito due volte con grafie diverse)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    if dipendente_id == target_id:
        raise HTTPException(status_code=400, detail="Origine e destinazione coincidono")
    target = (
        sb.table("dipendenti").select("id")
        .eq("id", target_id).eq("ristorante_id", ristorante_id)
        .limit(1).execute()
    )
    if not target.data:
        raise HTTPException(status_code=404, detail="Dipendente di destinazione non trovato")
    sb.table("turni_personale").update({"dipendente_id": target_id}) \
        .eq("ristorante_id", ristorante_id).eq("dipendente_id", dipendente_id).execute()
    resp = (
        sb.table("dipendenti").update({"attivo": False})
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .execute()
    )
    return resp.data[0] if resp.data else {}


# ─── Workspace: Personale ───────────────────────────────────────────────────

class NuovoTurnoBody(BaseModel):
    dipendente_id: str
    data_turno: str  # YYYY-MM-DD
    ora_inizio: str  # HH:MM
    ora_fine: str    # HH:MM
    ora_inizio2: Optional[str] = None  # secondo slot (spezzato)
    ora_fine2: Optional[str] = None
    ore_extra: Optional[float] = None          # quota straordinario (di cui)
    costo_orario: Optional[float] = None       # EUR/h ore standard
    costo_orario_extra: Optional[float] = None # EUR/h ore extra (se diverso)
    note: Optional[str] = None


class AggiornaTurnoBody(BaseModel):
    dipendente_id: Optional[str] = None
    data_turno: Optional[str] = None
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    ora_inizio2: Optional[str] = None
    ora_fine2: Optional[str] = None
    ore_extra: Optional[float] = None
    costo_orario: Optional[float] = None
    costo_orario_extra: Optional[float] = None
    note: Optional[str] = None


class CopiaSettimanaBody(BaseModel):
    da: str          # lunedì settimana destinazione YYYY-MM-DD
    a: str           # domenica settimana destinazione YYYY-MM-DD


class CopiaMeseBody(BaseModel):
    mese: str                 # YYYY-MM, mese DESTINAZIONE
    dipendente_ids: List[str]  # sottoinsieme selezionato in UI, non vuoto


_TIPI_GIORNO = {"turno", "riposo", "ferie", "malattia"}
_TIPI_GIORNO_CON_IMPORTO = {"ferie", "malattia"}


class StatoGiornoBody(BaseModel):
    tipo_giorno: str
    importo_a_carico: Optional[float] = None


class StatoGiornoIntervalloBody(BaseModel):
    dipendente_id: str
    data_da: str   # YYYY-MM-DD
    data_a: str    # YYYY-MM-DD
    tipo_giorno: str
    importo_a_carico: Optional[float] = None
    # Giorni espliciti da colpire dentro [data_da, data_a]. Serve alla selezione
    # multipla del dialog, che può essere non contigua (es. solo i lunedì): senza
    # questa lista il ciclo riempirebbe anche i giorni in mezzo, non scelti.
    giorni: Optional[List[str]] = None


class TurnoMensileBody(BaseModel):
    """Inserimento aggregato mensile da busta paga: i totali del mese per un
    dipendente, senza spezzare in turni giornalieri."""
    dipendente_id: str
    mese: str                              # YYYY-MM
    ore_totali: float                      # monte ore del mese
    lordo: float                           # importo lordo del mese (EUR)
    ore_extra: Optional[float] = None       # ore di straordinario incluse nel mese
    importo_extra: Optional[float] = None   # importo straordinario del mese (EUR)
    note: Optional[str] = None


class AggiornaTurnoMensileBody(BaseModel):
    ore_totali: Optional[float] = None
    lordo: Optional[float] = None
    ore_extra: Optional[float] = None
    importo_extra: Optional[float] = None
    note: Optional[str] = None


@router.get("/api/workspace/personale", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_list(
    da: Optional[str] = Query(None, description="Data inizio YYYY-MM-DD"),
    a: Optional[str] = Query(None, description="Data fine YYYY-MM-DD"),
    mensile: Optional[bool] = Query(None, description="True = solo righe mensili, False = solo giornaliere, None = tutte"),
    authorization: Optional[str] = Header(None),
):
    """Lista turni + nomi distinti + monte ore per persona nel periodo.

    Il filtro `mensile` seleziona le righe: True solo aggregati da busta paga,
    False solo turni giornalieri, None entrambi. La regola di dominio resta che
    lo STESSO dipendente nello STESSO mese non usi entrambi i metodi (le ore si
    conterebbero due volte) — vedi guardia in POST; dipendenti diversi possono
    invece usare metodi diversi e convivere nella stessa risposta."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    q = sb.table("turni_personale").select("*").eq("ristorante_id", ristorante_id)
    if da:
        q = q.gte("data_turno", da)
    if a:
        q = q.lte("data_turno", a)
    if mensile is not None:
        q = q.eq("mensile", mensile)
    q = q.order("data_turno").order("ora_inizio")
    resp = q.execute()
    turni = resp.data or []

    # Anagrafica dipendenti del ristorante: usata per tradurre dipendente_id
    # nel nome corrente (chiave esposta nei dizionari aggregati sotto — il
    # frontend continua a ragionare per nome, l'id resta interno).
    dipendenti_resp = sb.table("dipendenti").select("id,nome").eq("ristorante_id", ristorante_id).execute()
    nome_per_id = {d["id"]: d["nome"] for d in (dipendenti_resp.data or [])}

    def _nome(dip_id: str) -> str:
        return nome_per_id.get(dip_id, dip_id)

    monte_ore: dict = {}
    ore_standard_per_persona: dict = {}
    ore_extra_per_persona: dict = {}
    costo_standard_per_persona: dict = {}
    costo_extra_per_persona: dict = {}
    costo_assenze_per_persona: dict = {}

    for t in turni:
        nome = _nome(t["dipendente_id"])

        if t.get("tipo_giorno", "turno") != "turno":
            imp = float(t.get("importo_a_carico") or 0)
            if imp:
                costo_assenze_per_persona[nome] = round(costo_assenze_per_persona.get(nome, 0) + imp, 2)
            continue

        ore_tot = _ore_turno(t)
        monte_ore[nome] = round(monte_ore.get(nome, 0) + ore_tot, 2)

        extra = float(t.get("ore_extra") or 0)
        std = round(ore_tot - extra, 2)

        ore_standard_per_persona[nome] = round(ore_standard_per_persona.get(nome, 0) + std, 2)
        if extra:
            ore_extra_per_persona[nome] = round(ore_extra_per_persona.get(nome, 0) + extra, 2)

        if t.get("mensile"):
            # Riga mensile: il costo e' il dato reale dalla busta paga, non
            # ricalcolato da tariffa. lordo_mensile = totale del mese (incl.
            # quota extra); importo_extra = quota straordinario.
            lordo = float(t.get("lordo_mensile") or 0)
            imp_ext = float(t.get("importo_extra") or 0)
            costo_std = round(max(0.0, lordo - imp_ext), 2)
            costo_standard_per_persona[nome] = round(
                costo_standard_per_persona.get(nome, 0) + costo_std, 2
            )
            if imp_ext:
                costo_extra_per_persona[nome] = round(
                    costo_extra_per_persona.get(nome, 0) + imp_ext, 2
                )
            continue

        co_std = t.get("costo_orario")
        co_ext = t.get("costo_orario_extra")
        # Se costo_orario_extra non impostato, usa costo_orario anche per le extra
        co_ext_eff = float(co_ext) if co_ext is not None else (float(co_std) if co_std is not None else None)
        if co_std is not None:
            costo_standard_per_persona[nome] = round(
                costo_standard_per_persona.get(nome, 0) + std * float(co_std), 2
            )
        if co_ext_eff is not None and extra:
            costo_extra_per_persona[nome] = round(
                costo_extra_per_persona.get(nome, 0) + extra * co_ext_eff, 2
            )

    ore_standard_totale = round(sum(ore_standard_per_persona.values()), 2)
    ore_extra_totale = round(sum(ore_extra_per_persona.values()), 2)
    costo_standard_totale = round(sum(costo_standard_per_persona.values()), 2)
    costo_extra_totale = round(sum(costo_extra_per_persona.values()), 2)
    costo_totale = round(costo_standard_totale + costo_extra_totale, 2)

    # Dipendenti attivi + ultimi costi noti (per prefill nel dialog). Il prefill
    # usa dipendenti.costo_orario_default se impostato, altrimenti l'ultimo
    # costo_orario/costo_orario_extra usato in un turno per quel dipendente.
    q_storico = (
        sb.table("turni_personale")
        .select("dipendente_id,costo_orario,costo_orario_extra,data_turno")
        .eq("ristorante_id", ristorante_id)
        .order("data_turno", desc=True)
        .execute()
    )
    costi_noti_per_id: dict = {}
    for r in (q_storico.data or []):
        dip_id = r.get("dipendente_id")
        if not dip_id or dip_id in costi_noti_per_id:
            continue
        entry: dict = {}
        if r.get("costo_orario") is not None:
            entry["std"] = float(r["costo_orario"])
        if r.get("costo_orario_extra") is not None:
            entry["ext"] = float(r["costo_orario_extra"])
        if entry:
            costi_noti_per_id[dip_id] = entry

    dipendenti_attivi = (
        sb.table("dipendenti").select("id,nome,costo_orario_default")
        .eq("ristorante_id", ristorante_id).eq("attivo", True)
        .order("nome").execute()
    ).data or []
    nomi_distinti = [d["nome"] for d in dipendenti_attivi]
    costi_noti: dict = {}
    for d in dipendenti_attivi:
        entry = dict(costi_noti_per_id.get(d["id"], {}))
        if "std" not in entry and d.get("costo_orario_default") is not None:
            entry["std"] = float(d["costo_orario_default"])
        if entry:
            costi_noti[d["nome"]] = entry

    return {
        "turni": turni,
        "monte_ore": monte_ore,
        "ore_standard_per_persona": ore_standard_per_persona,
        "ore_extra_per_persona": ore_extra_per_persona,
        "costo_standard_per_persona": costo_standard_per_persona,
        "costo_extra_per_persona": costo_extra_per_persona,
        "costo_assenze_per_persona": costo_assenze_per_persona,
        # legacy — mantenuto per compatibilità con eventuali consumer
        "extra_per_persona": ore_extra_per_persona,
        "costo_per_persona": {
            n: round(costo_standard_per_persona.get(n, 0) + costo_extra_per_persona.get(n, 0), 2)
            for n in nomi_distinti
        },
        "ore_standard_totale": ore_standard_totale,
        "ore_extra_totale": ore_extra_totale,
        "costo_standard_totale": costo_standard_totale,
        "costo_extra_totale": costo_extra_totale,
        "extra_totale": ore_extra_totale,
        "costo_totale": costo_totale,
        "nomi": nomi_distinti,
        "costi_noti": costi_noti,
        "dipendenti": dipendenti_attivi,
    }


@router.get("/api/workspace/personale/export-mensile", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_export_mensile(
    mese: str = Query(..., description="Mese YYYY-MM"),
    authorization: Optional[str] = Header(None),
):
    """Export Excel (.xlsx) dei turni del mese: foglio Turni (griglia
    dipendenti×giorni) + foglio Riepilogo (ore/costi per dipendente).

    Riusa la stessa aggregazione di ws_personale_list per garanzia di
    coerenza numerica export↔UI — nessun ricalcolo parallelo."""
    import re
    from fastapi.responses import Response
    from services.personale_export_service import export_excel_personale_mensile

    # Validazione stretta (piu' di _mese_bounds, che accetta anche '2026-7' o
    # '99999-01'): qui il valore finisce nel titolo del foglio e nel filename
    # scaricato, quindi un formato imperfetto produce un file malformato senza
    # errore visibile invece di un 400 esplicito.
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mese):
        raise HTTPException(status_code=400, detail="Mese non valido (atteso YYYY-MM)")

    primo, ultimo = _mese_bounds(mese)

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    # mensile=None: servono ENTRAMBI i metodi. Il foglio Turni salta comunque le
    # righe da busta paga (non hanno un giorno da mettere in cella), ma il foglio
    # Riepilogo deve includerne ore e lordo, altrimenti chi è pagato a busta paga
    # sparisce dall'export e il totale costi è più basso del vero — muto.
    dati = ws_personale_list(da=primo, a=ultimo, mensile=None, authorization=authorization)

    # ws_personale_list filtra i dipendenti su attivo=True per il prefill del
    # dialog: chi e' stato disattivato durante il mese esportato ha comunque
    # turni/costi nei dizionari aggregati e va incluso, altrimenti sparisce
    # sia dalla griglia sia dal totale del Riepilogo (silenziosamente).
    dipendenti_export = list(dati["dipendenti"])
    id_gia_inclusi = {d["id"] for d in dipendenti_export}
    id_da_turni = {t["dipendente_id"] for t in dati["turni"] if t.get("dipendente_id")}
    id_mancanti = id_da_turni - id_gia_inclusi
    if id_mancanti:
        extra = sb.table("dipendenti").select("id,nome").in_("id", list(id_mancanti)).execute()
        dipendenti_export.extend(extra.data or [])

    rist = sb.table("ristoranti").select("nome_ristorante").eq("id", ristorante_id).single().execute()
    nome_ristorante = (rist.data or {}).get("nome_ristorante") or "Ristorante"

    xlsx_bytes = export_excel_personale_mensile(
        turni=dati["turni"],
        dipendenti=dipendenti_export,
        mese=mese,
        nome_ristorante=nome_ristorante,
        ore_standard_per_persona=dati["ore_standard_per_persona"],
        ore_extra_per_persona=dati["ore_extra_per_persona"],
        costo_standard_per_persona=dati["costo_standard_per_persona"],
        costo_extra_per_persona=dati["costo_extra_per_persona"],
        costo_assenze_per_persona=dati["costo_assenze_per_persona"],
    )

    filename = f"personale_mensile_{mese.replace('-', '')}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _mese_bounds(mese: str) -> tuple[str, str]:
    """('YYYY-MM') -> (primo giorno, ultimo giorno) come ISO date."""
    import calendar
    try:
        anno, mo = mese.split("-")
        ultimo = calendar.monthrange(int(anno), int(mo))[1]
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Mese non valido (atteso YYYY-MM)")
    return f"{mese}-01", f"{mese}-{ultimo:02d}"


def _esiste_riga_mese(sb, ristorante_id: str, dipendente_id: str, mese: str, mensile: bool) -> bool:
    """True se per dipendente+mese esiste almeno una riga del tipo richiesto
    (mensile=True -> riga mensile; mensile=False -> turni giornalieri)."""
    primo, ultimo = _mese_bounds(mese)
    r = (
        sb.table("turni_personale").select("id")
        .eq("ristorante_id", ristorante_id)
        .eq("dipendente_id", dipendente_id)
        .eq("mensile", mensile)
        .gte("data_turno", primo).lte("data_turno", ultimo)
        .limit(1)
        .execute()
    )
    return bool(r.data)


def _esiste_turno_lavorato_mese(sb, ristorante_id: str, dipendente_id: str, mese: str) -> bool:
    """True se nel mese esiste almeno un turno EFFETTIVAMENTE lavorato
    (tipo_giorno='turno') per il dipendente. A differenza di _esiste_riga_mese,
    ignora le righe di stato (riposo/ferie/malattia): marcare un'assenza per un
    dipendente mensile non deve essere bloccato dall'esclusivita' giornaliero/
    mensile, solo un turno lavorato lo e'."""
    primo, ultimo = _mese_bounds(mese)
    r = (
        sb.table("turni_personale").select("id")
        .eq("ristorante_id", ristorante_id)
        .eq("dipendente_id", dipendente_id)
        .eq("mensile", False)
        .eq("tipo_giorno", "turno")
        .gte("data_turno", primo).lte("data_turno", ultimo)
        .limit(1)
        .execute()
    )
    return bool(r.data)


def _dipendente_esiste(sb, ristorante_id: str, dipendente_id: str) -> bool:
    r = (
        sb.table("dipendenti").select("id")
        .eq("id", dipendente_id).eq("ristorante_id", ristorante_id)
        .limit(1).execute()
    )
    return bool(r.data)


@router.post("/api/workspace/personale", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_crea(body: NuovoTurnoBody, authorization: Optional[str] = Header(None)):
    """Aggiunge un turno giornaliero (supporta secondo slot per spezzato).

    Esclusivita': rifiutato se il dipendente ha gia' una riga MENSILE in quel
    mese (giornaliero e mensile non coesistono per dipendente/mese)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    if not _dipendente_esiste(sb, ristorante_id, body.dipendente_id):
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    mese = body.data_turno[:7]
    if _esiste_riga_mese(sb, ristorante_id, body.dipendente_id, mese, mensile=True):
        raise HTTPException(
            status_code=409,
            detail=f"Questo dipendente ha già un inserimento mensile per {mese}. Elimina la riga mensile per inserire turni giornalieri.",
        )
    payload: dict = {
        "ristorante_id": ristorante_id,
        "user_id": user_id,
        "dipendente_id": body.dipendente_id,
        "data_turno": body.data_turno,
        "ora_inizio": body.ora_inizio,
        "ora_fine": body.ora_fine,
    }
    if body.ora_inizio2:
        payload["ora_inizio2"] = body.ora_inizio2
    if body.ora_fine2:
        payload["ora_fine2"] = body.ora_fine2
    if body.ore_extra is not None:
        payload["ore_extra"] = body.ore_extra
    if body.costo_orario is not None:
        payload["costo_orario"] = body.costo_orario
    if body.costo_orario_extra is not None:
        payload["costo_orario_extra"] = body.costo_orario_extra
    if body.note:
        payload["note"] = body.note
    resp = sb.table("turni_personale").insert(payload).execute()
    return resp.data[0] if resp.data else {}


@router.post("/api/workspace/personale/copia-settimana", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_copia_settimana(body: CopiaSettimanaBody, authorization: Optional[str] = Header(None)):
    """Copia i turni della settimana precedente sulla settimana [da, a].
    Salta i giorni della settimana destinazione che hanno già turni (no duplicati)."""
    from datetime import datetime as _dt, timedelta as _td
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        dest_da = _dt.strptime(body.da, "%Y-%m-%d").date()
        dest_a = _dt.strptime(body.a, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date non valide")

    src_da = (dest_da - _td(days=7)).isoformat()
    src_a = (dest_a - _td(days=7)).isoformat()

    sorgente = (
        sb.table("turni_personale").select("*")
        .eq("ristorante_id", ristorante_id)
        .eq("mensile", False)
        .gte("data_turno", src_da).lte("data_turno", src_a)
        .execute()
    ).data or []
    if not sorgente:
        return {"ok": True, "n_copiati": 0, "n_saltati": 0, "messaggio": "Nessun turno nella settimana precedente"}

    esistenti = (
        sb.table("turni_personale").select("dipendente_id, data_turno")
        .eq("ristorante_id", ristorante_id)
        .gte("data_turno", body.da).lte("data_turno", body.a)
        .execute()
    ).data or []
    giorni_pieni = {(r["dipendente_id"], r["data_turno"]) for r in esistenti}

    nuovi = []
    n_saltati = 0
    for t in sorgente:
        nuova_data = (_dt.strptime(t["data_turno"], "%Y-%m-%d").date() + _td(days=7)).isoformat()
        if (t["dipendente_id"], nuova_data) in giorni_pieni:
            n_saltati += 1
            continue
        riga = {
            "ristorante_id": ristorante_id,
            "user_id": user_id,
            "dipendente_id": t["dipendente_id"],
            "data_turno": nuova_data,
            "ora_inizio": t["ora_inizio"],
            "ora_fine": t["ora_fine"],
        }
        for campo in ("ora_inizio2", "ora_fine2", "ore_extra", "costo_orario", "costo_orario_extra", "note"):
            if t.get(campo) is not None:
                riga[campo] = t[campo]
        nuovi.append(riga)

    if nuovi:
        sb.table("turni_personale").insert(nuovi).execute()
    return {"ok": True, "n_copiati": len(nuovi), "n_saltati": n_saltati}


@router.post("/api/workspace/personale/copia-mese", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_copia_mese(body: CopiaMeseBody, authorization: Optional[str] = Header(None)):
    """Copia turni e assenze del mese precedente sul mese [body.mese], allineando
    per giorno della settimana (lunedì->lunedì...domenica->domenica) anziché per
    numero del giorno. Se il mese sorgente ha più occorrenze di un giorno della
    settimana di quello destinazione, l'eccesso mappa sull'ultima occorrenza
    disponibile in destinazione (clamp). Salta i giorni già occupati in
    destinazione (no duplicati), stesso meccanismo di copia-settimana."""
    from datetime import datetime as _dt, date as _date

    if not body.dipendente_ids:
        raise HTTPException(status_code=400, detail="Nessun dipendente selezionato")

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    dest_da, dest_a = _mese_bounds(body.mese)
    anno, mo = (int(x) for x in body.mese.split("-"))
    prev_anno, prev_mo = (anno - 1, 12) if mo == 1 else (anno, mo - 1)
    mese_sorgente = f"{prev_anno:04d}-{prev_mo:02d}"
    src_da, src_a = _mese_bounds(mese_sorgente)

    sorgente = (
        sb.table("turni_personale").select("*")
        .eq("ristorante_id", ristorante_id)
        .eq("mensile", False)
        .in_("dipendente_id", body.dipendente_ids)
        .gte("data_turno", src_da).lte("data_turno", src_a)
        .execute()
    ).data or []
    if not sorgente:
        return {"ok": True, "n_copiati": 0, "n_saltati": 0, "messaggio": "Nessun turno nel mese precedente"}

    # Occorrenze del mese destinazione per giorno della settimana, in ordine crescente.
    giorni_dest_per_weekday: dict[int, list[str]] = {i: [] for i in range(7)}
    d = _dt.strptime(dest_da, "%Y-%m-%d").date()
    fine_dest = _dt.strptime(dest_a, "%Y-%m-%d").date()
    while d <= fine_dest:
        giorni_dest_per_weekday[d.weekday()].append(d.isoformat())
        d = _date.fromordinal(d.toordinal() + 1)

    esistenti = (
        sb.table("turni_personale").select("dipendente_id, data_turno")
        .eq("ristorante_id", ristorante_id)
        .gte("data_turno", dest_da).lte("data_turno", dest_a)
        .execute()
    ).data or []
    giorni_pieni = {(r["dipendente_id"], r["data_turno"]) for r in esistenti}

    # Indice di occorrenza per (dipendente, weekday), calcolato processando le
    # righe sorgente in ordine di data crescente cosi' la i-esima occorrenza
    # sorgente si allinea alla i-esima occorrenza destinazione.
    sorgente_ordinata = sorted(sorgente, key=lambda t: t["data_turno"])
    contatore: dict[tuple[str, int], int] = {}

    nuovi = []
    n_saltati = 0
    for t in sorgente_ordinata:
        data_src = _dt.strptime(t["data_turno"], "%Y-%m-%d").date()
        weekday = data_src.weekday()
        chiave = (t["dipendente_id"], weekday)
        idx = contatore.get(chiave, 0)
        contatore[chiave] = idx + 1

        occorrenze_dest = giorni_dest_per_weekday[weekday]
        if not occorrenze_dest:
            n_saltati += 1
            continue
        idx_clampato = min(idx, len(occorrenze_dest) - 1)
        nuova_data = occorrenze_dest[idx_clampato]

        if (t["dipendente_id"], nuova_data) in giorni_pieni:
            n_saltati += 1
            continue
        giorni_pieni.add((t["dipendente_id"], nuova_data))

        riga = {
            "ristorante_id": ristorante_id,
            "user_id": user_id,
            "dipendente_id": t["dipendente_id"],
            "data_turno": nuova_data,
        }
        tipo_giorno = t.get("tipo_giorno") or "turno"
        if tipo_giorno != "turno":
            riga["tipo_giorno"] = tipo_giorno
            if t.get("importo_a_carico") is not None:
                riga["importo_a_carico"] = t["importo_a_carico"]
            if t.get("note"):
                riga["note"] = t["note"]
        else:
            riga["ora_inizio"] = t["ora_inizio"]
            riga["ora_fine"] = t["ora_fine"]
            for campo in ("ora_inizio2", "ora_fine2", "ore_extra", "costo_orario", "costo_orario_extra", "note"):
                if t.get(campo) is not None:
                    riga[campo] = t[campo]
        nuovi.append(riga)

    if nuovi:
        sb.table("turni_personale").insert(nuovi).execute()
    return {"ok": True, "n_copiati": len(nuovi), "n_saltati": n_saltati}


@router.post("/api/workspace/personale/mensile", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_crea_mensile(body: TurnoMensileBody, authorization: Optional[str] = Header(None)):
    """Inserisce i totali mensili di un dipendente (da busta paga) come singola
    riga mensile. Esclusiva: rifiutato se esistono turni giornalieri per quel
    dipendente in quel mese, o se la riga mensile esiste gia'."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if not _dipendente_esiste(sb, ristorante_id, body.dipendente_id):
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    if body.ore_totali < 0 or body.lordo < 0:
        raise HTTPException(status_code=400, detail="Ore e lordo non possono essere negativi")
    if body.ore_totali <= 0 and body.lordo <= 0:
        raise HTTPException(status_code=400, detail="Inserisci almeno le ore o il lordo del mese")
    ore_ext = float(body.ore_extra or 0)
    if ore_ext < 0 or ore_ext > body.ore_totali + 0.01:
        raise HTTPException(status_code=400, detail="Le ore extra non possono superare le ore totali")
    imp_ext = float(body.importo_extra or 0)
    if imp_ext < 0 or imp_ext > body.lordo + 0.01:
        raise HTTPException(status_code=400, detail="L'importo extra non può superare il lordo")

    primo, _ = _mese_bounds(body.mese)
    if _esiste_riga_mese(sb, ristorante_id, body.dipendente_id, body.mese, mensile=False):
        raise HTTPException(
            status_code=409,
            detail=f"Questo dipendente ha già turni giornalieri per {body.mese}. Eliminali per usare l'inserimento mensile.",
        )
    if _esiste_riga_mese(sb, ristorante_id, body.dipendente_id, body.mese, mensile=True):
        raise HTTPException(
            status_code=409,
            detail=f"Questo dipendente ha già un inserimento mensile per {body.mese}.",
        )

    payload: dict = {
        "ristorante_id": ristorante_id,
        "user_id": user_id,
        "dipendente_id": body.dipendente_id,
        "data_turno": primo,
        "ora_inizio": "00:00",
        "ora_fine": "00:00",
        "mensile": True,
        "ore_dichiarate": round(float(body.ore_totali), 2),
        "lordo_mensile": round(float(body.lordo), 2),
        "ore_extra": round(ore_ext, 2) if ore_ext else None,
        "importo_extra": round(imp_ext, 2) if imp_ext else None,
        "note": body.note or None,
    }
    resp = sb.table("turni_personale").insert(payload).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/workspace/personale/mensile/{turno_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_aggiorna_mensile(turno_id: str, body: AggiornaTurnoMensileBody, authorization: Optional[str] = Header(None)):
    """Aggiorna i totali di una riga mensile esistente."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    raw = body.model_dump(exclude_unset=True)
    updates: dict = {}
    if "ore_totali" in raw and raw["ore_totali"] is not None:
        if raw["ore_totali"] < 0:
            raise HTTPException(status_code=400, detail="Ore non valide")
        updates["ore_dichiarate"] = round(float(raw["ore_totali"]), 2)
    if "lordo" in raw and raw["lordo"] is not None:
        if raw["lordo"] < 0:
            raise HTTPException(status_code=400, detail="Lordo non valido")
        updates["lordo_mensile"] = round(float(raw["lordo"]), 2)
    if "ore_extra" in raw:  # azzerabile
        updates["ore_extra"] = round(float(raw["ore_extra"]), 2) if raw["ore_extra"] else None
    if "importo_extra" in raw:  # azzerabile
        updates["importo_extra"] = round(float(raw["importo_extra"]), 2) if raw["importo_extra"] else None
    if "note" in raw:  # azzerabile
        updates["note"] = raw["note"] or None
    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    resp = (
        sb.table("turni_personale").update(updates)
        .eq("id", turno_id).eq("ristorante_id", ristorante_id).eq("mensile", True)
        .execute()
    )
    return resp.data[0] if resp.data else {}


@router.patch("/api/workspace/personale/{turno_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_aggiorna(turno_id: str, body: AggiornaTurnoBody, authorization: Optional[str] = Header(None)):
    """Aggiorna un turno (i campi ora_inizio2/ora_fine2 possono essere azzerati passando null)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    raw = body.model_dump()
    azzerabili = ("ora_inizio2", "ora_fine2", "ore_extra", "costo_orario", "costo_orario_extra")
    # Campi standard: includi solo se non None
    updates = {k: v for k, v in raw.items() if k not in azzerabili and v is not None}
    # Slot2 / extra / costo: includi sempre se esplicitamente nel body (anche None = reset)
    for campo in azzerabili:
        if campo in raw:
            updates[campo] = raw[campo]
    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    # .eq("mensile", False): questo PATCH gestisce solo turni giornalieri, non puo'
    # corrompere una riga mensile (che ha il suo endpoint /mensile/{id}).
    resp = (
        sb.table("turni_personale").update(updates)
        .eq("id", turno_id).eq("ristorante_id", ristorante_id).eq("mensile", False)
        .execute()
    )
    return resp.data[0] if resp.data else {}


@router.delete("/api/workspace/personale/{turno_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_elimina(turno_id: str, authorization: Optional[str] = Header(None)):
    """Elimina un turno o una riga mensile (per id, ristorante)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    sb.table("turni_personale").delete().eq("id", turno_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


def _valida_stato_giorno(tipo_giorno: str, importo_a_carico: Optional[float]) -> None:
    if tipo_giorno not in _TIPI_GIORNO:
        raise HTTPException(status_code=400, detail="tipo_giorno non valido (turno | riposo | ferie | malattia)")
    if importo_a_carico is not None and tipo_giorno not in _TIPI_GIORNO_CON_IMPORTO:
        raise HTTPException(status_code=400, detail="importo_a_carico consentito solo per ferie o malattia")
    if importo_a_carico is not None and importo_a_carico < 0:
        raise HTTPException(status_code=400, detail="importo_a_carico non può essere negativo")


@router.patch("/api/workspace/personale/{turno_id}/stato-giorno", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_stato_giorno(turno_id: str, body: StatoGiornoBody, authorization: Optional[str] = Header(None)):
    """Cambia lo stato esplicito di una riga giornaliera (turno/riposo/ferie/malattia).

    Il ritorno a 'turno' passa da qui: azzera importo_a_carico (non ammesso
    per tipo_giorno='turno'), gli orari restano quelli già in riga (il PATCH
    generico gestisce l'editing di ora_inizio/ora_fine)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _valida_stato_giorno(body.tipo_giorno, body.importo_a_carico)
    updates: dict = {"tipo_giorno": body.tipo_giorno}
    updates["importo_a_carico"] = (
        round(float(body.importo_a_carico), 2) if body.importo_a_carico is not None else None
    )
    resp = (
        sb.table("turni_personale").update(updates)
        .eq("id", turno_id).eq("ristorante_id", ristorante_id).eq("mensile", False)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Turno non trovato")
    return resp.data[0]


@router.post("/api/workspace/personale/stato-giorno-intervallo", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_stato_giorno_intervallo(body: StatoGiornoIntervalloBody, authorization: Optional[str] = Header(None)):
    """Applica uno stato-giorno (riposo/ferie/malattia/turno) a ogni giorno di
    [data_da, data_a] per un dipendente. Crea la riga se manca, aggiorna se
    esiste già come riga di stato; MAI sovrascrive silenziosamente un giorno
    con un turno effettivamente lavorato (tipo_giorno='turno') — quel giorno
    viene saltato ed elencato in n_saltati_turno_esistente."""
    from datetime import datetime as _dt, timedelta as _td

    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    if not _dipendente_esiste(sb, ristorante_id, body.dipendente_id):
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    _valida_stato_giorno(body.tipo_giorno, body.importo_a_carico)

    try:
        data_da = _dt.strptime(body.data_da, "%Y-%m-%d").date()
        data_a = _dt.strptime(body.data_a, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date non valide")
    if data_a < data_da:
        raise HTTPException(status_code=400, detail="data_a precedente a data_da")
    if (data_a - data_da).days > 366:
        raise HTTPException(status_code=400, detail="Intervallo troppo ampio (max 366 giorni)")

    esistenti = (
        sb.table("turni_personale").select("id,data_turno,tipo_giorno")
        .eq("ristorante_id", ristorante_id)
        .eq("dipendente_id", body.dipendente_id)
        .eq("mensile", False)
        .gte("data_turno", body.data_da).lte("data_turno", body.data_a)
        .execute()
    ).data or []
    per_giorno = {r["data_turno"]: r for r in esistenti}

    importo = round(float(body.importo_a_carico), 2) if body.importo_a_carico is not None else None
    n_creati = 0
    n_aggiornati = 0
    saltati: list = []

    # Senza `giorni` vale tutto l'intervallo (comportamento storico); con
    # `giorni` si colpiscono solo quelli scelti, scartando i fuori-range.
    if body.giorni is not None:
        giorni_target = sorted({
            g for g in body.giorni
            if isinstance(g, str) and body.data_da <= g <= body.data_a
        })
        if not giorni_target:
            raise HTTPException(status_code=400, detail="Nessun giorno valido nell'intervallo")
    else:
        giorni_target = []
        giorno = data_da
        while giorno <= data_a:
            giorni_target.append(giorno.isoformat())
            giorno += _td(days=1)

    for data_iso in giorni_target:
        riga = per_giorno.get(data_iso)
        if riga is None:
            sb.table("turni_personale").insert({
                "ristorante_id": ristorante_id,
                "user_id": user_id,
                "dipendente_id": body.dipendente_id,
                "data_turno": data_iso,
                "ora_inizio": "00:00",
                "ora_fine": "00:00",
                "tipo_giorno": body.tipo_giorno,
                "importo_a_carico": importo,
            }).execute()
            n_creati += 1
        elif riga.get("tipo_giorno", "turno") == "turno":
            saltati.append(data_iso)
        else:
            sb.table("turni_personale").update({
                "tipo_giorno": body.tipo_giorno,
                "importo_a_carico": importo,
            }).eq("id", riga["id"]).execute()
            n_aggiornati += 1

    return {
        "n_creati": n_creati,
        "n_aggiornati": n_aggiornati,
        "n_saltati_turno_esistente": saltati,
    }


# ─── Workspace: Regole turni ricorrenti ─────────────────────────────────────
# Template settimanale per dipendente (Fase 3a: CRUD; Fase 3b: generazione).

_TIPI_GIORNO_REGOLA = {"turno", "riposo"}


class NuovaRegolaTurnoBody(BaseModel):
    dipendente_id: str
    giorno_settimana: int   # 0=lunedì ... 6=domenica
    tipo_giorno: str        # 'turno' | 'riposo'
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    ora_inizio2: Optional[str] = None
    ora_fine2: Optional[str] = None
    costo_orario: Optional[float] = None


class AggiornaRegolaTurnoBody(BaseModel):
    giorno_settimana: Optional[int] = None
    tipo_giorno: Optional[str] = None
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    ora_inizio2: Optional[str] = None
    ora_fine2: Optional[str] = None
    costo_orario: Optional[float] = None
    attiva: Optional[bool] = None


def _valida_regola_turno(tipo_giorno: str, ora_inizio: Optional[str], ora_fine: Optional[str],
                          ora_inizio2: Optional[str], ora_fine2: Optional[str]) -> None:
    if tipo_giorno not in _TIPI_GIORNO_REGOLA:
        raise HTTPException(status_code=400, detail="tipo_giorno non valido (turno | riposo)")
    if tipo_giorno == "turno":
        if not ora_inizio or not ora_fine:
            raise HTTPException(status_code=400, detail="ora_inizio e ora_fine sono obbligatori per tipo_giorno='turno'")
    else:
        if ora_inizio or ora_fine or ora_inizio2 or ora_fine2:
            raise HTTPException(status_code=400, detail="tipo_giorno='riposo' non ammette orari")


@router.get("/api/workspace/regole-turni", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_regole_turni_list(
    dipendente_id: Optional[str] = Query(None),
    attiva: Optional[bool] = Query(None, description="True = solo attive, False = solo disattivate, None = tutte"),
    authorization: Optional[str] = Header(None),
):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    q = sb.table("regole_turni_ricorrenti").select("*").eq("ristorante_id", ristorante_id)
    if dipendente_id:
        q = q.eq("dipendente_id", dipendente_id)
    if attiva is not None:
        q = q.eq("attiva", attiva)
    resp = q.order("giorno_settimana").execute()
    return {"regole": resp.data or []}


@router.post("/api/workspace/regole-turni", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_regole_turni_crea(body: NuovaRegolaTurnoBody, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    if not _dipendente_esiste(sb, ristorante_id, body.dipendente_id):
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    if not (0 <= body.giorno_settimana <= 6):
        raise HTTPException(status_code=400, detail="giorno_settimana deve essere tra 0 (lunedì) e 6 (domenica)")
    _valida_regola_turno(body.tipo_giorno, body.ora_inizio, body.ora_fine, body.ora_inizio2, body.ora_fine2)

    payload: dict = {
        "ristorante_id": ristorante_id,
        "dipendente_id": body.dipendente_id,
        "giorno_settimana": body.giorno_settimana,
        "tipo_giorno": body.tipo_giorno,
        "ora_inizio": body.ora_inizio,
        "ora_fine": body.ora_fine,
        "ora_inizio2": body.ora_inizio2,
        "ora_fine2": body.ora_fine2,
    }
    if body.costo_orario is not None:
        payload["costo_orario"] = round(float(body.costo_orario), 2)
    resp = sb.table("regole_turni_ricorrenti").insert(payload).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/workspace/regole-turni/{regola_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_regole_turni_aggiorna(regola_id: str, body: AggiornaRegolaTurnoBody, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    esistente = (
        sb.table("regole_turni_ricorrenti").select("*")
        .eq("id", regola_id).eq("ristorante_id", ristorante_id)
        .limit(1).execute()
    )
    if not esistente.data:
        raise HTTPException(status_code=404, detail="Regola non trovata")
    corrente = esistente.data[0]

    raw = body.model_dump(exclude_unset=True)
    updates: dict = {}

    if "giorno_settimana" in raw and raw["giorno_settimana"] is not None:
        if not (0 <= raw["giorno_settimana"] <= 6):
            raise HTTPException(status_code=400, detail="giorno_settimana deve essere tra 0 (lunedì) e 6 (domenica)")
        updates["giorno_settimana"] = raw["giorno_settimana"]
    if "costo_orario" in raw:  # azzerabile
        updates["costo_orario"] = round(float(raw["costo_orario"]), 2) if raw["costo_orario"] is not None else None
    if "attiva" in raw and raw["attiva"] is not None:
        updates["attiva"] = raw["attiva"]

    # tipo_giorno e orari si validano insieme: merge su corrente + updates
    # espliciti, cosi' un PATCH parziale non puo' lasciare la riga incoerente
    # (es. cambiare solo ora_inizio senza toccare tipo_giorno='riposo').
    tocca_orari_o_tipo = any(c in raw for c in ("tipo_giorno", "ora_inizio", "ora_fine", "ora_inizio2", "ora_fine2"))
    if tocca_orari_o_tipo:
        tipo_giorno = raw.get("tipo_giorno", corrente["tipo_giorno"])
        ora_inizio = raw["ora_inizio"] if "ora_inizio" in raw else corrente["ora_inizio"]
        ora_fine = raw["ora_fine"] if "ora_fine" in raw else corrente["ora_fine"]
        ora_inizio2 = raw["ora_inizio2"] if "ora_inizio2" in raw else corrente["ora_inizio2"]
        ora_fine2 = raw["ora_fine2"] if "ora_fine2" in raw else corrente["ora_fine2"]
        if tipo_giorno == "riposo":
            ora_inizio = ora_fine = ora_inizio2 = ora_fine2 = None
        _valida_regola_turno(tipo_giorno, ora_inizio, ora_fine, ora_inizio2, ora_fine2)
        updates["tipo_giorno"] = tipo_giorno
        updates["ora_inizio"] = ora_inizio
        updates["ora_fine"] = ora_fine
        updates["ora_inizio2"] = ora_inizio2
        updates["ora_fine2"] = ora_fine2

    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    resp = (
        sb.table("regole_turni_ricorrenti").update(updates)
        .eq("id", regola_id).eq("ristorante_id", ristorante_id)
        .execute()
    )
    return resp.data[0] if resp.data else {}


@router.delete("/api/workspace/regole-turni/{regola_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_regole_turni_elimina(regola_id: str, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    sb.table("regole_turni_ricorrenti").delete().eq("id", regola_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


class GeneraTurniDaRegoleBody(BaseModel):
    data_da: str   # YYYY-MM-DD
    data_a: str    # YYYY-MM-DD
    dipendente_id: Optional[str] = None  # None = tutti i dipendenti con regole attive


@router.post("/api/workspace/regole-turni/genera", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_regole_turni_genera(body: GeneraTurniDaRegoleBody, authorization: Optional[str] = Header(None)):
    """Genera righe turni_personale nell'intervallo [data_da, data_a] applicando
    le regole ricorrenti attive per giorno_settimana. Le regole tipo_giorno='riposo'
    non generano righe (un riposo e' assenza di turno, non un turno vuoto).
    Salta (dipendente_id, data_turno) che hanno gia' un turno — stessa chiave
    composita del fix copia-settimana, per non riprodurre lo stesso bug qui."""
    from datetime import datetime as _dt, timedelta as _td
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        data_da = _dt.strptime(body.data_da, "%Y-%m-%d").date()
        data_a = _dt.strptime(body.data_a, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date non valide")
    if data_a < data_da:
        raise HTTPException(status_code=400, detail="data_a deve essere successiva o uguale a data_da")
    if (data_a - data_da).days > 92:
        raise HTTPException(status_code=400, detail="Intervallo troppo ampio (max 92 giorni)")

    if body.dipendente_id and not _dipendente_esiste(sb, ristorante_id, body.dipendente_id):
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    q = (
        sb.table("regole_turni_ricorrenti").select("*")
        .eq("ristorante_id", ristorante_id)
        .eq("attiva", True)
        .eq("tipo_giorno", "turno")
    )
    if body.dipendente_id:
        q = q.eq("dipendente_id", body.dipendente_id)
    regole = q.execute().data or []
    if not regole:
        return {"ok": True, "n_creati": 0, "n_saltati": 0, "messaggio": "Nessuna regola attiva di tipo turno"}

    regole_per_giorno: dict = {}
    for r in regole:
        regole_per_giorno.setdefault(r["giorno_settimana"], []).append(r)

    esistenti = (
        sb.table("turni_personale").select("dipendente_id, data_turno")
        .eq("ristorante_id", ristorante_id)
        .gte("data_turno", body.data_da).lte("data_turno", body.data_a)
        .execute()
    ).data or []
    giorni_pieni = {(r["dipendente_id"], r["data_turno"]) for r in esistenti}

    nuovi = []
    n_saltati = 0
    giorno = data_da
    while giorno <= data_a:
        for r in regole_per_giorno.get(giorno.weekday(), []):
            data_turno = giorno.isoformat()
            if (r["dipendente_id"], data_turno) in giorni_pieni:
                n_saltati += 1
                continue
            riga = {
                "ristorante_id": ristorante_id,
                "user_id": user_id,
                "dipendente_id": r["dipendente_id"],
                "data_turno": data_turno,
                "ora_inizio": r["ora_inizio"],
                "ora_fine": r["ora_fine"],
            }
            if r.get("ora_inizio2"):
                riga["ora_inizio2"] = r["ora_inizio2"]
            if r.get("ora_fine2"):
                riga["ora_fine2"] = r["ora_fine2"]
            if r.get("costo_orario") is not None:
                riga["costo_orario"] = r["costo_orario"]
            nuovi.append(riga)
            giorni_pieni.add((r["dipendente_id"], data_turno))
        giorno += _td(days=1)

    if nuovi:
        sb.table("turni_personale").insert(nuovi).execute()
    return {"ok": True, "n_creati": len(nuovi), "n_saltati": n_saltati}


# ─── Workspace: Spese extra (F&B / Generali) ────────────────────────────────

_TIPI_SPESA = {"fb", "generale"}


class NuovaSpesaBody(BaseModel):
    data_spesa: str   # YYYY-MM-DD
    tipo: str         # 'fb' | 'generale'
    importo: float
    descrizione: str
    note: Optional[str] = None


class AggiornaSpesaBody(BaseModel):
    data_spesa: Optional[str] = None
    tipo: Optional[str] = None
    importo: Optional[float] = None
    descrizione: Optional[str] = None
    note: Optional[str] = None


@router.get("/api/workspace/spese", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_spese_list(
    da: Optional[str] = Query(None, description="Data inizio YYYY-MM-DD"),
    a: Optional[str] = Query(None, description="Data fine YYYY-MM-DD"),
    authorization: Optional[str] = Header(None),
):
    """Lista voci di spesa extra nel periodo + totali per tipo."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    q = sb.table("spese_extra").select("*").eq("ristorante_id", ristorante_id)
    if da:
        q = q.gte("data_spesa", da)
    if a:
        q = q.lte("data_spesa", a)
    q = q.order("data_spesa", desc=True).order("created_at", desc=True)
    voci = q.execute().data or []
    tot_fb = round(sum(float(v.get("importo") or 0) for v in voci if v.get("tipo") == "fb"), 2)
    tot_generale = round(sum(float(v.get("importo") or 0) for v in voci if v.get("tipo") == "generale"), 2)
    return {
        "voci": voci,
        "totale_fb": tot_fb,
        "totale_generale": tot_generale,
        "totale": round(tot_fb + tot_generale, 2),
    }


@router.post("/api/workspace/spese", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_spese_crea(body: NuovaSpesaBody, authorization: Optional[str] = Header(None)):
    """Crea una nuova voce di spesa extra."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    if body.tipo not in _TIPI_SPESA:
        raise HTTPException(status_code=400, detail="Tipo spesa non valido (fb | generale)")
    if not body.descrizione.strip():
        raise HTTPException(status_code=400, detail="La descrizione è obbligatoria")
    if body.importo < 0:
        raise HTTPException(status_code=400, detail="L'importo non può essere negativo")
    payload: dict = {
        "ristorante_id": ristorante_id,
        "user_id": user_id,
        "data_spesa": body.data_spesa,
        "tipo": body.tipo,
        "importo": round(float(body.importo), 2),
        "descrizione": body.descrizione.strip(),
    }
    if body.note is not None:
        payload["note"] = body.note
    resp = sb.table("spese_extra").insert(payload).execute()
    return resp.data[0] if resp.data else {}


@router.patch("/api/workspace/spese/{spesa_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_spese_aggiorna(spesa_id: str, body: AggiornaSpesaBody, authorization: Optional[str] = Header(None)):
    """Aggiorna una voce di spesa extra (note azzerabile passando null)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    raw = body.model_dump(exclude_unset=True)
    if "tipo" in raw and raw["tipo"] not in _TIPI_SPESA:
        raise HTTPException(status_code=400, detail="Tipo spesa non valido (fb | generale)")
    updates: dict = {}
    for campo in ("data_spesa", "tipo", "descrizione"):
        if campo in raw and raw[campo] is not None:
            v = raw[campo]
            updates[campo] = v.strip() if campo == "descrizione" else v
    if "importo" in raw and raw["importo"] is not None:
        if float(raw["importo"]) < 0:
            raise HTTPException(status_code=400, detail="L'importo non può essere negativo")
        updates["importo"] = round(float(raw["importo"]), 2)
    if "note" in raw:  # azzerabile
        updates["note"] = raw["note"]
    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    resp = sb.table("spese_extra").update(updates).eq("id", spesa_id).eq("ristorante_id", ristorante_id).execute()
    return resp.data[0] if resp.data else {}


@router.delete("/api/workspace/spese/{spesa_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_spese_elimina(spesa_id: str, authorization: Optional[str] = Header(None)):
    """Elimina una voce di spesa extra."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    sb.table("spese_extra").delete().eq("id", spesa_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}
