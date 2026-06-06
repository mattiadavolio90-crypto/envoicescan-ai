"""Router dominio WORKSPACE — foodcost (ricette/ingredienti), inventario, diario,
personale (turni), spese extra.

Estratto da fastapi_worker.py. Gli helper condivisi (_verify_worker_key,
_resolve_user_from_token, _get_supabase_client, _get_ristorante_id_for_user,
_oggi_rome, _ore_turno, logger) restano nel worker e sono importati da qui.
_ore_turno in particolare e' condiviso col router margini, quindi NON viene
spostato. Le tabelle ricette/ingredienti usano la colonna `userid` (non user_id),
logica copiata identica. Path/gate/response invariati.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from services.fastapi_worker import (
    _verify_worker_key,
    _resolve_user_from_token,
    _get_supabase_client,
    _get_ristorante_id_for_user,
    _oggi_rome,
    _ore_turno,
    logger,
)

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
        .eq("userid", user_id)
        .eq("ristorante_id", ristorante_id)
        .order("nome")
        .execute()
    )
    manuali = manuali_resp.data or []

    semi_resp = (
        sb.table("ricette")
        .select("id,nome,foodcost_totale")
        .eq("userid", user_id)
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
        .eq("userid", user_id)
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

    resp = (
        sb.table("ricette")
        .select("id,nome,categoria,foodcost_totale,prezzo_vendita_ivainc,ingredienti,ordine_visualizzazione")
        .eq("id", ricetta_id)
        .eq("userid", user_id)
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
        next_ordine_resp = sb.rpc("get_next_ordine_ricetta", {"p_userid": user_id, "p_ristorante_id": ristorante_id}).execute()
        next_ordine = next_ordine_resp.data if next_ordine_resp.data else 1
    except Exception:
        q = sb.table("ricette").select("ordine_visualizzazione").eq("userid", user_id).eq("ristorante_id", ristorante_id).order("ordine_visualizzazione", desc=True).limit(1).execute()
        next_ordine = (q.data[0]["ordine_visualizzazione"] + 1) if q.data else 1

    payload = {
        "userid": user_id,
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
    sb.table("ricette").update(payload).eq("id", ricetta_id).eq("userid", user_id).execute()
    return {"ok": True, "foodcost_totale": fc_totale}


@router.delete("/api/workspace/foodcost/ricette/{ricetta_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_elimina_ricetta(ricetta_id: str, authorization: Optional[str] = Header(None)):
    """Elimina ricetta."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    sb.table("ricette").delete().eq("id", ricetta_id).eq("userid", user_id).execute()
    return {"ok": True}


class RiordinaBody(BaseModel):
    ordine: list[str]  # lista di id ricetta nel nuovo ordine


@router.post("/api/workspace/foodcost/ricette/riordina", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_riordina_ricette(body: RiordinaBody, authorization: Optional[str] = Header(None)):
    """Aggiorna ordine_visualizzazione delle ricette secondo la lista di id ricevuta."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    for idx, rid in enumerate(body.ordine):
        sb.table("ricette").update({"ordine_visualizzazione": idx + 1}).eq("id", rid).eq("userid", user_id).execute()
    return {"ok": True}


@router.get("/api/workspace/foodcost/ingredienti-manuali", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_ingredienti_manuali(authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    resp = sb.table("ingredienti_workspace").select("id,nome,prezzo_per_um,um").eq("userid", user_id).eq("ristorante_id", ristorante_id).order("nome").execute()
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
            "userid": user_id,
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
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if "um" in payload:
        payload["um"] = payload["um"].upper()
    sb.table("ingredienti_workspace").update(payload).eq("id", ing_id).eq("userid", user_id).execute()
    return {"ok": True}


@router.delete("/api/workspace/foodcost/ingredienti-manuali/{ing_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_elimina_ingrediente_manuale(ing_id: str, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    sb.table("ingredienti_workspace").delete().eq("id", ing_id).eq("userid", user_id).execute()
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


# ─── Workspace: Personale ───────────────────────────────────────────────────

class NuovoTurnoBody(BaseModel):
    nome: str
    data_turno: str  # YYYY-MM-DD
    ora_inizio: str  # HH:MM
    ora_fine: str    # HH:MM
    ora_inizio2: Optional[str] = None  # secondo slot (spezzato)
    ora_fine2: Optional[str] = None
    ore_extra: Optional[float] = None     # quota straordinario (di cui)
    costo_orario: Optional[float] = None  # EUR/h
    note: Optional[str] = None


class AggiornaTurnoBody(BaseModel):
    nome: Optional[str] = None
    data_turno: Optional[str] = None
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    ora_inizio2: Optional[str] = None
    ora_fine2: Optional[str] = None
    ore_extra: Optional[float] = None
    costo_orario: Optional[float] = None
    note: Optional[str] = None


class CopiaSettimanaBody(BaseModel):
    da: str          # lunedì settimana destinazione YYYY-MM-DD
    a: str           # domenica settimana destinazione YYYY-MM-DD


@router.get("/api/workspace/personale", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_list(
    da: Optional[str] = Query(None, description="Data inizio YYYY-MM-DD"),
    a: Optional[str] = Query(None, description="Data fine YYYY-MM-DD"),
    authorization: Optional[str] = Header(None),
):
    """Lista turni + nomi distinti + monte ore per persona nel periodo."""
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
    q = q.order("data_turno").order("ora_inizio")
    resp = q.execute()
    turni = resp.data or []

    monte_ore: dict = {}
    extra_per_persona: dict = {}
    costo_per_persona: dict = {}
    for t in turni:
        nome = t["nome"]
        ore = _ore_turno(t)
        monte_ore[nome] = round(monte_ore.get(nome, 0) + ore, 2)
        extra = float(t.get("ore_extra") or 0)
        if extra:
            extra_per_persona[nome] = round(extra_per_persona.get(nome, 0) + extra, 2)
        co = t.get("costo_orario")
        if co is not None:
            costo_per_persona[nome] = round(costo_per_persona.get(nome, 0) + ore * float(co), 2)

    extra_totale = round(sum(extra_per_persona.values()), 2)
    costo_totale = round(sum(costo_per_persona.values()), 2)

    # Nomi distinti + ultimo costo orario noto per persona (per prefill nel dialog)
    q_storico = (
        sb.table("turni_personale")
        .select("nome,costo_orario,data_turno")
        .eq("ristorante_id", ristorante_id)
        .order("data_turno", desc=True)
        .execute()
    )
    nomi_set = set()
    costi_noti: dict = {}
    for r in (q_storico.data or []):
        nome = r.get("nome")
        if not nome:
            continue
        nomi_set.add(nome)
        if nome not in costi_noti and r.get("costo_orario") is not None:
            costi_noti[nome] = float(r["costo_orario"])
    nomi_distinti = sorted(nomi_set)

    return {
        "turni": turni,
        "monte_ore": monte_ore,
        "extra_per_persona": extra_per_persona,
        "costo_per_persona": costo_per_persona,
        "extra_totale": extra_totale,
        "costo_totale": costo_totale,
        "nomi": nomi_distinti,
        "costi_noti": costi_noti,
    }


@router.post("/api/workspace/personale", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_crea(body: NuovoTurnoBody, authorization: Optional[str] = Header(None)):
    """Aggiunge un turno (supporta secondo slot per spezzato)."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    payload: dict = {
        "ristorante_id": ristorante_id,
        "user_id": user_id,
        "nome": body.nome.strip(),
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
        .gte("data_turno", src_da).lte("data_turno", src_a)
        .execute()
    ).data or []
    if not sorgente:
        return {"ok": True, "n_copiati": 0, "n_saltati": 0, "messaggio": "Nessun turno nella settimana precedente"}

    esistenti = (
        sb.table("turni_personale").select("data_turno")
        .eq("ristorante_id", ristorante_id)
        .gte("data_turno", body.da).lte("data_turno", body.a)
        .execute()
    ).data or []
    giorni_pieni = {r["data_turno"] for r in esistenti}

    nuovi = []
    n_saltati = 0
    for t in sorgente:
        nuova_data = (_dt.strptime(t["data_turno"], "%Y-%m-%d").date() + _td(days=7)).isoformat()
        if nuova_data in giorni_pieni:
            n_saltati += 1
            continue
        riga = {
            "ristorante_id": ristorante_id,
            "user_id": user_id,
            "nome": t["nome"],
            "data_turno": nuova_data,
            "ora_inizio": t["ora_inizio"],
            "ora_fine": t["ora_fine"],
        }
        for campo in ("ora_inizio2", "ora_fine2", "ore_extra", "costo_orario", "note"):
            if t.get(campo) is not None:
                riga[campo] = t[campo]
        nuovi.append(riga)

    if nuovi:
        sb.table("turni_personale").insert(nuovi).execute()
    return {"ok": True, "n_copiati": len(nuovi), "n_saltati": n_saltati}


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
    azzerabili = ("ora_inizio2", "ora_fine2", "ore_extra", "costo_orario")
    # Campi standard: includi solo se non None
    updates = {k: v for k, v in raw.items() if k not in azzerabili and v is not None}
    # Slot2 / extra / costo: includi sempre se esplicitamente nel body (anche None = reset)
    for campo in azzerabili:
        if campo in raw:
            updates[campo] = raw[campo]
    if not updates:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    resp = sb.table("turni_personale").update(updates).eq("id", turno_id).eq("ristorante_id", ristorante_id).execute()
    return resp.data[0] if resp.data else {}


@router.delete("/api/workspace/personale/{turno_id}", tags=["Workspace"], dependencies=[Depends(_verify_worker_key)])
def ws_personale_elimina(turno_id: str, authorization: Optional[str] = Header(None)):
    """Elimina un turno."""
    user = _resolve_user_from_token(authorization)
    user_id = str(user["id"])
    sb = _get_supabase_client()
    ristorante_id = _get_ristorante_id_for_user(user_id, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    sb.table("turni_personale").delete().eq("id", turno_id).eq("ristorante_id", ristorante_id).execute()
    return {"ok": True}


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
