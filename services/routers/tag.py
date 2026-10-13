"""Router dominio TAG — custom tag prodotto, associazioni, analisi, suggerimenti.

Estratto da fastapi_worker.py. Path, gate (_verify_worker_key) e response
identici all'originale. Gli helper condivisi sono importati dal worker.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file; importarlo qui al top
# rompe l'import del router fuori dal contesto FastAPI). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint.
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


# Usato in Depends(...) nei decorator (valutato a import-time): firma identica
# all'originale perche' FastAPI inietta il valore leggendo la signature.
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


# ─── Modelli ──────────────────────────────────────────────────────────────────
class TagCreateRequest(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class TagUpdateRequest(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class TagPatchRequest(BaseModel):
    nome: Optional[str] = None
    emoji: Optional[str] = None
    colore: Optional[str] = None
    cartella_id: Optional[int] = None
    preferito: Optional[bool] = None


class CartellaRequest(BaseModel):
    nome: str


class RiordinaCartelleRequest(BaseModel):
    ids: list[int]


class AssociazioneItem(BaseModel):
    descrizione: str
    descrizione_key: Optional[str] = None
    fattore_kg: Optional[float] = None


class AggiungiAssociazioniRequest(BaseModel):
    descrizioni: list[AssociazioneItem]


class ModificaProdottiRequest(BaseModel):
    aggiungi: list[AssociazioneItem] = []
    togli: list[str] = []


class AcceptSuggestionRequest(BaseModel):
    suggestion_type: Optional[str] = None  # "new_tag" | "extend_tag"
    tag_name: Optional[str] = None
    tag_id: Optional[int] = None
    # Chiavi dei prodotti che il cliente ha lasciato spuntati nel dialog. Se assente
    # (chiamate vecchie) si ricade su selected_by_default, che è sempre True: senza
    # questo campo la deselezione lato UI non arrivava mai al backend.
    descrizioni_key: Optional[list[str]] = None
    # Un tag accettato da un suggerimento nasceva sempre senza emoji (`emoji=None`
    # cablato nel service): il selettore esisteva solo nella creazione manuale,
    # quindi l'unico rimedio era riaprire il tag e modificarlo a mano.
    emoji: Optional[str] = None


class SnoozeSuggestionRequest(BaseModel):
    days: int = 30


# ─── Helper di dominio ────────────────────────────────────────────────────────
def _assert_tag_ownership(sb, tag_id: int, user_id: str, ristorante_id: str) -> None:
    """Verifica che il tag appartenga all'utente/ristorante; alza 404 altrimenti."""
    resp = (
        sb.table("custom_tags")
        .select("id")
        .eq("id", int(tag_id))
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .limit(1)
        .execute()
    )
    if not (resp.data or []):
        raise HTTPException(status_code=404, detail="Tag non trovato")


def _parse_date_param(value: str, name: str):
    from datetime import datetime as _dt
    try:
        return _dt.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Parametro {name} non valido (atteso YYYY-MM-DD)")


# ─── Route ────────────────────────────────────────────────────────────────────
@router.get("/api/tag", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def list_tags(authorization: Optional[str] = Header(None)):
    from services.tag_organizza_service import lista_cartelle, lista_tag_organizzati
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    try:
        return {
            "tags": lista_tag_organizzati(str(user["id"]), ristorante_id),
            "cartelle": lista_cartelle(str(user["id"]), ristorante_id),
        }
    except Exception as e:
        logger.error(f"list_tags ristorante_id={ristorante_id}: {e}")
        raise HTTPException(status_code=502, detail="Impossibile caricare i tag: riprova")


def _organizza_http(funzione, *args):
    from services.tag_organizza_service import Conflitto, NonTrovato, ScritturaParziale
    try:
        return funzione(*args)
    except NonTrovato as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Conflitto as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ScritturaParziale as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/tag/cartelle", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def create_cartella(body: CartellaRequest, authorization: Optional[str] = Header(None)):
    from services.tag_organizza_service import crea_cartella
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    return {"cartella": _organizza_http(crea_cartella, str(user["id"]), ristorante_id, body.nome)}


@router.put("/api/tag/cartelle/ordine", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def riordina_cartelle_endpoint(body: RiordinaCartelleRequest, authorization: Optional[str] = Header(None)):
    from services.tag_organizza_service import riordina_cartelle
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _organizza_http(riordina_cartelle, str(user["id"]), ristorante_id, body.ids)
    return {"ok": True}


@router.put("/api/tag/cartelle/{cartella_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def rinomina_cartella_endpoint(
    cartella_id: int, body: CartellaRequest, authorization: Optional[str] = Header(None)
):
    from services.tag_organizza_service import rinomina_cartella
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    cartella = _organizza_http(
        rinomina_cartella, int(cartella_id), str(user["id"]), ristorante_id, body.nome
    )
    return {"cartella": cartella}


@router.delete("/api/tag/cartelle/{cartella_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def elimina_cartella_endpoint(cartella_id: int, authorization: Optional[str] = Header(None)):
    from services.tag_organizza_service import elimina_cartella
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _organizza_http(elimina_cartella, int(cartella_id), str(user["id"]), ristorante_id)
    return {"ok": True}


@router.post("/api/tag", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def create_tag(body: TagCreateRequest, authorization: Optional[str] = Header(None)):
    from services.db_service import crea_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome tag obbligatorio")
    tag = crea_tag(str(user["id"]), ristorante_id, nome, body.emoji, body.colore)
    return {"tag": tag}


@router.put("/api/tag/{tag_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def update_tag(tag_id: int, body: TagUpdateRequest, authorization: Optional[str] = Header(None)):
    from services.db_service import aggiorna_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome tag obbligatorio")
    tag = aggiorna_tag(int(tag_id), str(user["id"]), nome, body.emoji, body.colore)
    return {"tag": tag}


@router.patch("/api/tag/{tag_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def patch_tag(tag_id: int, body: TagPatchRequest, authorization: Optional[str] = Header(None)):
    from services.tag_organizza_service import aggiorna_tag_parziale
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    campi = {k: getattr(body, k) for k in body.model_fields_set}
    tag = _organizza_http(aggiorna_tag_parziale, int(tag_id), str(user["id"]), ristorante_id, campi)
    return {"tag": tag}


@router.delete("/api/tag/{tag_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def delete_tag(tag_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import elimina_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    elimina_tag(int(tag_id), str(user["id"]))
    return {"ok": True}


@router.get("/api/tag/descrizioni", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def list_descrizioni_distinte(authorization: Optional[str] = Header(None)):
    from services.db_service import get_descrizioni_distinte
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    return {"descrizioni": get_descrizioni_distinte(str(user["id"]), ristorante_id)}


@router.get("/api/tag/{tag_id}/prodotti", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def list_tag_prodotti(tag_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import get_custom_tag_prodotti
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    return {"prodotti": get_custom_tag_prodotti(int(tag_id), str(user["id"]))}


@router.post("/api/tag/{tag_id}/prodotti", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def add_tag_prodotti(
    tag_id: int, body: AggiungiAssociazioniRequest, authorization: Optional[str] = Header(None)
):
    from services.db_service import aggiungi_associazioni
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    descrizioni = [
        {
            "descrizione": i.descrizione,
            "descrizione_key": i.descrizione_key,
            "fattore_kg": i.fattore_kg,
        }
        for i in body.descrizioni
    ]
    try:
        created = aggiungi_associazioni(int(tag_id), descrizioni, user_id=str(user["id"]))
    except PermissionError:
        raise HTTPException(status_code=404, detail="Tag non trovato")
    return {"associazioni": created, "aggiunte": len(created)}


@router.patch("/api/tag/{tag_id}/prodotti", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def modifica_tag_prodotti(
    tag_id: int, body: ModificaProdottiRequest, authorization: Optional[str] = Header(None)
):
    from services.tag_organizza_service import RimozioniNonRiuscite, applica_modifiche_prodotti
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    aggiungi = [
        {
            "descrizione": i.descrizione,
            "descrizione_key": i.descrizione_key,
            "fattore_kg": i.fattore_kg,
        }
        for i in body.aggiungi
    ]
    try:
        return applica_modifiche_prodotti(
            int(tag_id), str(user["id"]), ristorante_id, aggiungi, body.togli
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=404, detail="Tag non trovato")
    except RimozioniNonRiuscite as e:
        logger.error(f"modifica_tag_prodotti tag_id={tag_id}: rimozioni non riuscite ({e})")
        raise HTTPException(
            status_code=502,
            detail="I prodotti aggiunti sono salvati, ma non e' stato possibile toglierne alcuni: riprova",
        )


@router.delete("/api/tag/prodotti/{assoc_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def remove_tag_prodotto(assoc_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import rimuovi_associazione
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    # rimuovi_associazione filtra solo user_id: su un account multi-sede un id di
    # un'altra sede sarebbe cancellabile. Qui si verifica la sede PRIMA, come
    # fanno gli altri endpoint via _assert_tag_ownership.
    owned = (
        sb.table("custom_tag_prodotti")
        .select("id")
        .eq("id", int(assoc_id))
        .eq("user_id", str(user["id"]))
        .eq("ristorante_id", ristorante_id)
        .limit(1)
        .execute()
    )
    if not (owned.data or []):
        raise HTTPException(status_code=404, detail="Associazione non trovata")
    rimuovi_associazione(int(assoc_id), str(user["id"]))
    return {"ok": True}


@router.get("/api/tag/{tag_id}/analisi", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def analizza_tag_endpoint(
    tag_id: int,
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
):
    from services.tag_analytics_service import analizza_tag
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    d_da = _parse_date_param(data_da, "data_da")
    d_a = _parse_date_param(data_a, "data_a")
    return analizza_tag(str(user["id"]), ristorante_id, int(tag_id), d_da, d_a)


@router.get("/api/tag/{tag_id}/orfani", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def tag_orfani_endpoint(tag_id: int, authorization: Optional[str] = Header(None)):
    from services.tag_analytics_service import compute_orfani
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    _assert_tag_ownership(sb, tag_id, str(user["id"]), ristorante_id)
    orfani = compute_orfani(str(user["id"]), ristorante_id, int(tag_id))
    return {"orfani": orfani, "count": len(orfani)}


@router.get("/api/tag/suggestions", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def list_tag_suggestions(
    refresh: bool = False, authorization: Optional[str] = Header(None)
):
    from services.tag_suggestion_service import (
        list_pending_tag_suggestions,
        run_tag_suggestion_pipeline,
    )
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    refresh_ok = None
    if refresh:
        # La pipeline degrada a {'success': False} senza sollevare: ignorare il
        # ritorno faceva rispondere 200 con la lista VECCHIA, indistinguibile da
        # "nessun suggerimento nuovo". Il client deve poter dire che il motore
        # non ha girato.
        esito = run_tag_suggestion_pipeline(
            user_id=str(user["id"]), ristorante_id=ristorante_id
        ) or {}
        refresh_ok = bool(esito.get("success"))
    suggestions = list_pending_tag_suggestions(user_id=str(user["id"]), ristorante_id=ristorante_id)
    out = {"suggestions": suggestions}
    if refresh:
        out["refresh_ok"] = refresh_ok
    return out


@router.post(
    "/api/tag/suggestions/{sid}/accept", tags=["Tag"], dependencies=[Depends(_verify_worker_key)]
)
def accept_tag_suggestion(
    sid: int,
    body: AcceptSuggestionRequest,
    authorization: Optional[str] = Header(None),
):
    from services.tag_suggestion_service import (
        accept_suggestion_create_tag,
        accept_suggestion_extend_tag,
    )
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    s_type = (body.suggestion_type or "").strip()
    if not s_type:
        row = (
            sb.table("custom_tag_suggestions")
            .select("suggestion_type")
            .eq("id", int(sid))
            .eq("user_id", str(user["id"]))
            .eq("ristorante_id", ristorante_id)
            .limit(1)
            .execute()
        )
        if not (row.data or []):
            raise HTTPException(status_code=404, detail="Suggerimento non trovato")
        s_type = str(row.data[0].get("suggestion_type") or "")

    if s_type == "new_tag":
        result = accept_suggestion_create_tag(
            suggestion_id=int(sid),
            tag_name=body.tag_name,
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
            descrizioni_key=body.descrizioni_key,
            emoji=body.emoji,
        )
    elif s_type == "extend_tag":
        result = accept_suggestion_extend_tag(
            suggestion_id=int(sid),
            tag_id=body.tag_id,
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
            descrizioni_key=body.descrizioni_key,
        )
    else:
        raise HTTPException(status_code=400, detail="suggestion_type non valido")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Operazione non riuscita"))
    return result


@router.post(
    "/api/tag/suggestions/{sid}/snooze", tags=["Tag"], dependencies=[Depends(_verify_worker_key)]
)
def snooze_tag_suggestion_endpoint(
    sid: int,
    body: SnoozeSuggestionRequest,
    authorization: Optional[str] = Header(None),
):
    from services.tag_suggestion_service import snooze_tag_suggestion
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    snooze_tag_suggestion(
        int(sid), user_id=str(user["id"]), ristorante_id=ristorante_id, days=int(body.days)
    )
    return {"ok": True}


@router.post(
    "/api/tag/suggestions/{sid}/dismiss", tags=["Tag"], dependencies=[Depends(_verify_worker_key)]
)
def dismiss_tag_suggestion_endpoint(sid: int, authorization: Optional[str] = Header(None)):
    from services.tag_suggestion_service import dismiss_tag_suggestion
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    dismiss_tag_suggestion(int(sid), user_id=str(user["id"]), ristorante_id=ristorante_id)
    return {"ok": True}
