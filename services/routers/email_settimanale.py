"""Email settimanale dell'assistente — gli ingressi HTTP (fase 7a).

La logica sta in services/email_settimanale_service.py. Qui solo:
- il lavoro del lunedi', chiamato dal cron di GitHub Actions
  (.github/workflows/email_settimanale.yml);
- la disiscrizione con il token firmato, chiamata dalla pagina pubblica
  /disiscrizione e dal List-Unsubscribe dei client di posta (via Next.js, che
  aggiunge la chiave del worker: questo router, come tutti, e' dietro
  `_verify_worker_key`).
L'anteprima per l'admin sta in routers/admin.py, dietro `_verify_admin`.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services import email_settimanale_service as svc


def _fw():
    import services.fastapi_worker as fw
    return fw


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


router = APIRouter(dependencies=[Depends(_verify_worker_key)])


@router.post("/api/interno/email-settimanale", tags=["Email"],
             dependencies=[Depends(_verify_worker_key)])
def email_settimanale_esegui(
    dry_run: bool = True,
    solo_user_id: Optional[str] = None,
    forza: bool = False,
) -> Dict[str, Any]:
    """Il lavoro del lunedi'. Senza `forza` lavora solo se a Roma e' lunedi'
    fra le 7 e le 9:59: il cron gira due volte (05:35 e 06:35 UTC) e almeno una
    cade nella finestra, qualunque sia l'ora legale. `dry_run` e' vero di
    default: per spedire servono `dry_run=false` E `EMAIL_SETTIMANALE_ATTIVA=1`."""
    adesso = svc.adesso_roma()
    if not forza and not svc.e_ora_di_invio(adesso):
        return {"eseguito": False, "motivo": "fuori orario", "adesso_roma": adesso.isoformat()}
    resoconto = svc.esegui(
        _get_supabase_client(), adesso=adesso, dry_run=dry_run, solo_user_id=solo_user_id,
    )
    return {"eseguito": True, **resoconto}


class DisiscrizioneBody(BaseModel):
    u: str
    t: str


@router.post("/api/email/disiscrizione", tags=["Email"],
             dependencies=[Depends(_verify_worker_key)])
def email_disiscrizione(body: DisiscrizioneBody) -> Dict[str, Any]:
    """Spegne l'email settimanale per l'utente del token. Nessun login: il
    token firmato e' la prova. Risposta identica per token sbagliato e utente
    inesistente, per non dire quali id esistono."""
    if not svc.disiscrivi(_get_supabase_client(), body.u.strip(), body.t.strip()):
        raise HTTPException(status_code=400, detail="Link non valido")
    return {"ok": True}
