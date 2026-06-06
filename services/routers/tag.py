"""Router dominio TAG — custom tag prodotto, associazioni, analisi, suggerimenti.

Estratto da fastapi_worker.py. Path, gate (_verify_worker_key) e response
identici all'originale. Gli helper condivisi sono importati dal worker.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services.fastapi_worker import (
    _verify_worker_key,
    _resolve_user_from_token,
    _get_supabase_client,
    _resolve_ristorante_id,
)

router = APIRouter()


# ─── Modelli ──────────────────────────────────────────────────────────────────
class TagCreateRequest(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class TagUpdateRequest(BaseModel):
    nome: str
    emoji: Optional[str] = None
    colore: Optional[str] = None


class AssociazioneItem(BaseModel):
    descrizione: str
    descrizione_key: Optional[str] = None
    fattore_kg: Optional[float] = None


class AggiungiAssociazioniRequest(BaseModel):
    descrizioni: list[AssociazioneItem]


class AcceptSuggestionRequest(BaseModel):
    suggestion_type: Optional[str] = None  # "new_tag" | "extend_tag"
    tag_name: Optional[str] = None
    tag_id: Optional[int] = None


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
    from services.db_service import get_custom_tags
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    return {"tags": get_custom_tags(str(user["id"]), ristorante_id)}


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


@router.delete("/api/tag/prodotti/{assoc_id}", tags=["Tag"], dependencies=[Depends(_verify_worker_key)])
def remove_tag_prodotto(assoc_id: int, authorization: Optional[str] = Header(None)):
    from services.db_service import rimuovi_associazione
    user = _resolve_user_from_token(authorization)
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
    if refresh:
        run_tag_suggestion_pipeline(user_id=str(user["id"]), ristorante_id=ristorante_id)
    suggestions = list_pending_tag_suggestions(user_id=str(user["id"]), ristorante_id=ristorante_id)
    return {"suggestions": suggestions}


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
        )
    elif s_type == "extend_tag":
        result = accept_suggestion_extend_tag(
            suggestion_id=int(sid),
            tag_id=body.tag_id,
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
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
