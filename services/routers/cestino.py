"""Router dominio CESTINO — soft-delete fatture, ripristino, svuota, hard-delete.

Estratto da fastapi_worker.py (sezioni "CESTINO FATTURE" e "FATTURE — soft delete").
Path, gate e response invariati.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). __getattr__ risolve i
# simboli condivisi al primo accesso a runtime; _verify_worker_key resta esplicito
# perche' usato in Depends() a import-time (firma identica per l'iniezione FastAPI).
def __getattr__(name: str):
    import services.fastapi_worker as _fw
    return getattr(_fw, name)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    import services.fastapi_worker as _fw
    return _fw._verify_worker_key(x_worker_key)

router = APIRouter()


class CestinoRipristinaRequest(BaseModel):
    file_origine: str


class CestinoEliminaRequest(BaseModel):
    file_origine: str


class FatturaEliminaRequest(BaseModel):
    file_origine: str


@router.get("/api/cestino", tags=["Cestino"], dependencies=[Depends(_verify_worker_key)])
def get_cestino(authorization: Optional[str] = Header(None)):
    from services.db_service import get_fatture_cestino
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    items = get_fatture_cestino(str(user["id"]), ristorante_id=ristorante_id)
    return {"cestino": items, "count": len(items)}


@router.post("/api/cestino/ripristina", tags=["Cestino"], dependencies=[Depends(_verify_worker_key)])
def ripristina_dal_cestino(
    body: CestinoRipristinaRequest, authorization: Optional[str] = Header(None)
):
    from services.db_service import ripristina_fattura
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    file_origine = str(body.file_origine or "").strip()
    if not file_origine:
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    result = ripristina_fattura(file_origine, user_id=str(user["id"]), ristorante_id=ristorante_id)

    if not result.get("success"):
        err = result.get("error", "Errore")
        status = 404 if "not_found" in str(err) else 500
        raise HTTPException(status_code=status, detail=err)

    return result


@router.post("/api/cestino/elimina", tags=["Cestino"], dependencies=[Depends(_verify_worker_key)])
def elimina_definitivamente(
    body: CestinoEliminaRequest, authorization: Optional[str] = Header(None)
):
    """Elimina definitivamente una fattura già nel cestino (hard delete)."""
    from services.db_service import elimina_fattura_completa
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    file_origine = str(body.file_origine or "").strip()
    if not file_origine:
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    result = elimina_fattura_completa(
        file_origine,
        user_id=str(user["id"]),
        ristoranteid=ristorante_id,
        soft_delete=False,
    )

    if not result.get("success"):
        err = result.get("error", "Errore")
        status = 404 if "not_found" in str(err) else 500
        raise HTTPException(status_code=status, detail=err)

    return result


@router.post("/api/cestino/svuota", tags=["Cestino"], dependencies=[Depends(_verify_worker_key)])
def svuota_cestino_endpoint(authorization: Optional[str] = Header(None)):
    from services.db_service import svuota_cestino
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    result = svuota_cestino(str(user["id"]), ristorante_id=ristorante_id)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Errore"))

    return result


@router.post("/api/fatture/elimina", tags=["Fatture"], dependencies=[Depends(_verify_worker_key)])
def elimina_fattura_soft(
    body: FatturaEliminaRequest, authorization: Optional[str] = Header(None)
):
    """Soft-delete: sposta una fattura attiva nel cestino (deleted_at = now)."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    user_id = str(user["id"])

    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    file_origine = str(body.file_origine or "").strip()
    if not file_origine:
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    try:
        # Cerca la fattura per user_id + file_origine, SENZA filtro deleted_at nel check
        # (problemi di compatibilità con is_() in alcuni contesti FastAPI).
        # deleted_at viene controllato manualmente sul record trovato.
        check = (
            sb.table("fatture")
            .select("id, ristorante_id, deleted_at")
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .limit(1)
            .execute()
        )
        if not check.data:
            logger.warning(
                f"elimina_fattura_soft: record non trovato — file={file_origine!r} user={user_id}"
            )
            raise HTTPException(status_code=404, detail="not_found")

        row = check.data[0]
        if row.get("deleted_at"):
            raise HTTPException(status_code=409, detail="already_in_trash")

        # Usa il ristorante_id del record (non quello risolto dal token)
        actual_ristorante_id = row.get("ristorante_id") or ristorante_id

        # Soft delete su tutte le righe della fattura
        (
            sb.table("fatture")
            .update({"deleted_at": "now()"})
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .eq("ristorante_id", actual_ristorante_id)
            .is_("deleted_at", "null")
            .execute()
        )

        logger.info(f"Fattura spostata nel cestino: {file_origine} | user={user_id} | ristorante={actual_ristorante_id}")
        return {"success": True, "righe_eliminate": 1}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Errore soft-delete fattura {file_origine}")
        raise HTTPException(status_code=500, detail="Errore durante l'eliminazione della fattura.")
