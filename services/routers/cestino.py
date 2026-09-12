"""Router dominio CESTINO — soft-delete fatture, ripristino, svuota, hard-delete.

Estratto da fastapi_worker.py (sezioni "CESTINO FATTURE" e "FATTURE — soft delete").
Path, gate e response invariati.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint. _verify_worker_key resta esplicito perche' usato in
# Depends() a import-time (firma identica per l'iniezione FastAPI).
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


class CestinoRipristinaRequest(BaseModel):
    file_origine: str


class CestinoEliminaRequest(BaseModel):
    file_origine: str


class FatturaEliminaRequest(BaseModel):
    file_origine: str
    ristorante_id: Optional[str] = None


class FatturaOscuraRequest(BaseModel):
    file_origine: str
    oscurata: bool
    ristorante_id: Optional[str] = None


def _resolve_ristorante_scrivibile(user, sb, ristorante_id_body: Optional[str]) -> str:
    """Risolve la sede su cui scrivere: sede ATTIVA se il body non la specifica,
    altrimenti la sede indicata PREVIO controllo di appartenenza all'account
    (stesso pattern di scadenziario.py — necessario in modalità catena, dove la
    sede del documento può differire dalla sede attiva dell'utente loggato)."""
    rid_body = str(ristorante_id_body or "").strip()
    if not rid_body:
        ristorante_id = _resolve_ristorante_id(user, sb)
        if not ristorante_id:
            raise HTTPException(status_code=400, detail="Nessun ristorante associato")
        return ristorante_id
    owns = (
        sb.table("ristoranti")
        .select("id")
        .eq("id", rid_body)
        .eq("user_id", str(user["id"]))
        .limit(1)
        .execute()
    )
    if not owns.data:
        raise HTTPException(status_code=404, detail="Sede non trovata")
    return rid_body


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
    ristorante_id = _resolve_ristorante_scrivibile(user, sb, body.ristorante_id)
    user_id = str(user["id"])

    file_origine = str(body.file_origine or "").strip()
    if not file_origine:
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    try:
        # Cerca la fattura per user_id + file_origine + ristorante_id (sede ATTIVA),
        # SENZA filtro deleted_at nel check (problemi di compatibilità con is_() in
        # alcuni contesti FastAPI). deleted_at viene controllato manualmente sul
        # record trovato.
        # Il filtro su ristorante_id è essenziale per gli account multi-sede con
        # stessa P.IVA: lo stesso file_origine può esistere su più sedi e senza il
        # vincolo di sede si rischierebbe di cestinare la fattura della sede sbagliata.
        check = (
            sb.table("fatture")
            .select("id, ristorante_id, deleted_at")
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .eq("ristorante_id", ristorante_id)
            .limit(1)
            .execute()
        )
        if not check.data:
            logger.warning(
                f"elimina_fattura_soft: record non trovato — file={file_origine!r} "
                f"user={user_id} ristorante={ristorante_id}"
            )
            raise HTTPException(status_code=404, detail="not_found")

        row = check.data[0]
        if row.get("deleted_at"):
            raise HTTPException(status_code=409, detail="already_in_trash")

        # Soft delete su tutte le righe attive della fattura, vincolato alla sede attiva.
        upd = (
            sb.table("fatture")
            .update({"deleted_at": "now()"})
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .execute()
        )

        righe = len(upd.data or [])
        if righe == 0:
            # Tra il check e l'update il record è già finito nel cestino (race).
            raise HTTPException(status_code=409, detail="already_in_trash")

        logger.info(f"Fattura spostata nel cestino: {file_origine} | user={user_id} | ristorante={ristorante_id} | righe={righe}")

        # Chiude il buco delete→riparto: se questo documento aveva generato un riparto
        # costi-catena e non resta piu' alcuna riga viva nell'account, rimuovilo e
        # ri-aggrega le quote mensili (altrimenti il costo resta fantasma nel MOL).
        from services.db_service import _pulisci_riparto_orfano, clear_fatture_cache
        _pulisci_riparto_orfano(sb, user_id, file_origine)

        # Questo endpoint scrive su `fatture` senza passare da db_service, quindi
        # l'invalidazione va ripetuta qui: senza, la lista fatture e il cestino
        # restano fermi fino al TTL (60-120s) dopo lo spostamento nel cestino.
        clear_fatture_cache()

        return {"success": True, "righe_eliminate": righe}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Errore soft-delete fattura {file_origine}")
        raise HTTPException(status_code=500, detail="Errore durante l'eliminazione della fattura.")


@router.post("/api/fatture/oscura", tags=["Fatture"], dependencies=[Depends(_verify_worker_key)])
def oscura_fattura(
    body: FatturaOscuraRequest, authorization: Optional[str] = Header(None)
):
    """Esclude una fattura da TUTTI i conteggi (o la rimette dentro), lasciandola
    visibile e consultabile in Gestione Fatture.

    Non e' il cestino: il cestino la fa sparire e dopo 30 giorni la cancella. Qui
    la fattura resta in elenco, marcata, e un click la riporta nei conti.

    Vive in questo router e non in uno nuovo perche' e' la terza azione sullo
    stesso oggetto (cestina / ripristina / escludi) e riusa
    `_resolve_ristorante_scrivibile`: un router dedicato duplicherebbe i wrapper
    lazy senza aggiungere niente.
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_scrivibile(user, sb, body.ristorante_id)
    user_id = str(user["id"])

    file_origine = str(body.file_origine or "").strip()
    if not file_origine:
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    try:
        # Stesso check di elimina_fattura_soft: senza filtro deleted_at nella
        # query (problemi di compatibilita' con is_() in alcuni contesti FastAPI),
        # controllato a mano sul record. Il vincolo di sede e' essenziale per i
        # multi-sede con stessa P.IVA: lo stesso file_origine puo' esistere su
        # piu' sedi.
        check = (
            sb.table("fatture")
            .select("id, deleted_at, oscurata")
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .eq("ristorante_id", ristorante_id)
            .limit(1)
            .execute()
        )
        if not check.data:
            raise HTTPException(status_code=404, detail="not_found")

        row = check.data[0]
        if row.get("deleted_at"):
            # Due stati di esclusione sovrapposti aprirebbero la domanda "cosa
            # succede se la ripristino dal cestino?" senza una risposta scritta.
            raise HTTPException(status_code=409, detail="already_in_trash")

        # Una fattura di struttura gia' ripartita sul gruppo NON puo' essere
        # esclusa qui. Escluderla non toglierebbe il costo dai punti vendita: le
        # quote sono proiettate da `riparto_service`, che senza righe reali cade
        # sul ramo SINTETICO e proietta lo stesso -- "oscurata alla fonte, viva a
        # valle", peggio che non averla esclusa perche' il cliente crede di
        # averlo fatto. Si rimuove prima il riparto.
        if body.oscurata:
            rip = (
                sb.table("riparto_costi_catena")
                .select("id")
                .eq("user_id", user_id)
                .eq("file_origine", file_origine)
                .limit(1)
                .execute()
            )
            if rip.data:
                raise HTTPException(status_code=409, detail="ripartita_su_gruppo")

        if bool(row.get("oscurata")) == bool(body.oscurata):
            # Idempotente, a differenza del cestino: qui non c'e' una race da
            # proteggere e un doppio click non deve diventare un errore a video.
            return {"success": True, "righe": 0, "oscurata": bool(body.oscurata)}

        upd = (
            sb.table("fatture")
            .update({
                "oscurata": bool(body.oscurata),
                "oscurata_at": "now()" if body.oscurata else None,
            })
            .eq("user_id", user_id)
            .eq("file_origine", file_origine)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .execute()
        )
        righe = len(upd.data or [])

        logger.info(
            "Fattura %s dai conti: %s | user=%s | ristorante=%s | righe=%d",
            "esclusa" if body.oscurata else "rimessa", file_origine, user_id,
            ristorante_id, righe,
        )

        # DUE invalidazioni, non una. `clear_fatture_cache` copre le cache di
        # db_service (stats, margini); `_invalidate_fatture_rows_cache` copre il
        # funnel Analisi Fatture, la cache di PREZZI e lo snapshot Home del
        # giorno. elimina_fattura_soft chiama solo la prima: e' un buco che qui
        # non va replicato, perche' escludere una fattura cambia proprio i numeri
        # serviti da quelle tre.
        from services.db_service import clear_fatture_cache
        clear_fatture_cache()
        try:
            _fw()._invalidate_fatture_rows_cache(ristorante_id)
        except Exception as exc:  # pragma: no cover - non deve bloccare la scrittura
            logger.warning("invalidazione cache righe fallita: %s", exc)

        return {"success": True, "righe": righe, "oscurata": bool(body.oscurata)}

    except HTTPException:
        raise
    except Exception:
        logger.exception("Errore esclusione dai conti per %s", file_origine)
        raise HTTPException(status_code=500, detail="Errore durante l'operazione.")
