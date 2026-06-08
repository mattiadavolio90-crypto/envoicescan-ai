"""Router dominio ACCOUNT — profilo, piano, contatori, cambio password, preferenze.

Estratto da fastapi_worker.py. Path, gate e response invariati.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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

_PIANO_LIMITI: Dict[str, int] = {
    "free": 50,
    "base": 50,
    "plus": 100,
    "pro": 200,
}


@router.get("/api/account/me", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_me(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dati account estesi: profilo, piano, contatori utilizzo."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    # Dati utente freschi dal DB (piano, price_alert_threshold, created_at)
    user_row = (
        sb.table("users")
        .select("id, email, nome_ristorante, ragione_sociale, partita_iva, piano, "
                "price_alert_threshold, tema, created_at, last_login")
        .eq("id", user_id)
        .single()
        .execute()
    )
    row = user_row.data or {}

    piano_raw = (row.get("piano") or "base").lower().strip()
    limite_fatture = _PIANO_LIMITI.get(piano_raw, 50)

    # Contatore fatture del mese corrente (documenti unici, non righe)
    now = datetime.now(timezone.utc)
    mese_inizio = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    ristorante_id = _resolve_ristorante_id(user, sb)
    fatture_mese = 0
    if ristorante_id:
        try:
            # Conta file_origine distinti nel mese corrente
            fd_resp = (
                sb.table("fatture_documenti")
                .select("file_origine")
                .eq("ristorante_id", ristorante_id)
                .gte("data_documento", mese_inizio[:10])
                .execute()
            )
            file_origini = {r["file_origine"] for r in (fd_resp.data or [])}
            fatture_mese = len(file_origini)
        except Exception:
            pass

    # Contatore domande Chat AI di oggi (per il rate limit visibile al cliente)
    chat_oggi = _chat_domande_oggi(ristorante_id, user_id, sb)

    return {
        "email": row.get("email", user.get("email", "")),
        "nome_ristorante": row.get("nome_ristorante", user.get("nome_ristorante", "")),
        "ragione_sociale": row.get("ragione_sociale"),
        "partita_iva": row.get("partita_iva"),
        "piano": piano_raw,
        "limite_fatture_mese": limite_fatture,
        "fatture_usate_mese": fatture_mese,
        "chat_usate_oggi": chat_oggi,
        "chat_limite_giorno": _chat_limite_per_piano(piano_raw),
        "price_alert_threshold": row.get("price_alert_threshold"),
        "tema": (row.get("tema") or "dark"),
        "membro_dal": row.get("created_at"),
        "ultimo_accesso": row.get("last_login"),
        "is_admin": _is_admin_email(row.get("email")),
    }


class CambioPasswordBody(BaseModel):
    password_attuale: str
    nuova_password: str


@router.post("/api/account/cambia-password", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_cambia_password(
    body: CambioPasswordBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Cambia password con verifica dell'attuale."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    # Carica hash attuale
    row = (
        sb.table("users")
        .select("id, password_hash, email")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    from services.auth_service import verify_and_migrate_password, ph
    if not verify_and_migrate_password(row.data, body.password_attuale):
        raise HTTPException(status_code=400, detail="La password attuale non è corretta")

    if len(body.nuova_password) < 8:
        raise HTTPException(status_code=400, detail="La nuova password deve essere di almeno 8 caratteri")

    new_hash = ph.hash(body.nuova_password)
    sb.table("users").update({
        "password_hash": new_hash,
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", user_id).execute()

    return {"ok": True}


class PreferenzeBody(BaseModel):
    tema: str


@router.post("/api/account/preferenze", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def account_preferenze(
    body: PreferenzeBody,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Salva le preferenze di aspetto del cliente (tema). Segue l'account."""
    user = _resolve_user_from_token(authorization)
    tema = (body.tema or "").strip().lower()
    if tema not in ("dark", "light"):
        raise HTTPException(status_code=400, detail="Tema non valido")
    sb = _get_supabase_client()
    sb.table("users").update({"tema": tema}).eq("id", str(user["id"])).execute()
    return {"ok": True, "tema": tema}
