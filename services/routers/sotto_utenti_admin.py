"""Sotto-utenti dalla scheda cliente del pannello Admin (Fase 2 del piano).

Solo l'admin crea, modifica ed elimina i sotto-utenti di un cliente; il cliente
non li vede e non li gestisce. Le regole sono le stesse dello script
(`sotto_utenti_service.valida_permessi`): pagine che il titolare ha, sedi
attive del suo account, Catena solo con tutte le sedi. Le ricontrolla anche la
sessione a ogni richiesta (sovrapponi), questo e' il freno all'ingresso.

Un sotto-utente nasce SENZA password: riceve via email lo stesso link di
attivazione dei clienti (24 ore) e la sceglie lui. L'admin non la conosce mai.
Finche' non la sceglie e' «in attesa»: il login lo rifiuta perche' il suo hash
non e' argon2.

Schema: supabase/migrations/20260928215000_sotto_utenti.sql.
"""
from __future__ import annotations

import html as _html
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from services import sotto_utenti_service as su_svc
from services.routers.admin import _verify_admin

logger = logging.getLogger("fastapi_worker")


def _fw():
    import services.fastapi_worker as fw
    return fw


def get_supabase_client(*args, **kwargs):
    return _fw().get_supabase_client(*args, **kwargs)


def _admin_emails_set(*args, **kwargs):
    return _fw()._admin_emails_set(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


router = APIRouter(dependencies=[Depends(_verify_worker_key)])

BASE = "/api/admin/clienti/{cliente_id}/sotto-utenti"
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COLONNE = "id, email, nome, attivo, pagine, password_hash, last_login, created_at, reset_expires"
VALIDITA_LINK = timedelta(hours=24)


class NuovoSottoUtenteBody(BaseModel):
    email: str = Field(..., max_length=254)
    nome: Optional[str] = Field(None, max_length=100)
    pagine: List[str] = Field(default_factory=list, max_length=20)
    sedi: List[str] = Field(default_factory=list, max_length=200)


class ModificaSottoUtenteBody(BaseModel):
    nome: Optional[str] = Field(None, max_length=100)
    pagine: Optional[List[str]] = Field(None, max_length=20)
    sedi: Optional[List[str]] = Field(None, max_length=200)
    attivo: Optional[bool] = None


def _id_valido(valore: str, cosa: str) -> str:
    if not _ID.match(valore or ""):
        raise HTTPException(status_code=404, detail=f"{cosa} non trovato")
    return valore


def _cliente(sb, cliente_id: str) -> Dict[str, Any]:
    _id_valido(cliente_id, "Cliente")
    r = (
        sb.table("users").select("id, email, nome_ristorante, pagine_abilitate")
        .eq("id", cliente_id).limit(1).execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    return r.data[0]


def _sotto_utente(sb, cliente_id: str, sotto_utente_id: str) -> Dict[str, Any]:
    _id_valido(sotto_utente_id, "Sotto-utente")
    r = (
        sb.table("sotto_utenti").select(_COLONNE)
        .eq("id", sotto_utente_id).eq("titolare_id", cliente_id).limit(1).execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Sotto-utente non trovato")
    return r.data[0]


def _sedi_di(sb, sotto_utente_id: str) -> List[str]:
    r = (
        sb.table("sotto_utenti_sedi").select("ristorante_id")
        .eq("sotto_utente_id", sotto_utente_id).execute()
    )
    return [str(x["ristorante_id"]) for x in (r.data or [])]


def _pubblico(riga: Dict[str, Any], sedi: List[str]) -> Dict[str, Any]:
    """Mai hash, token o scadenza del token verso il pannello."""
    pagine = riga.get("pagine") if isinstance(riga.get("pagine"), dict) else {}
    return {
        "id": str(riga["id"]),
        "email": riga.get("email"),
        "nome": riga.get("nome"),
        "stato": su_svc.stato(riga),
        "pagine": sorted(p for p, v in pagine.items() if v is True),
        "sedi": sedi,
        "last_login": riga.get("last_login"),
        "created_at": riga.get("created_at"),
    }


def _valida(sb, cliente: Dict[str, Any], pagine: List[str], sedi: List[str]):
    sedi_account = su_svc.sedi_operative(sb, cliente["id"])
    # Solo id: dal pannello arrivano le caselle spuntate, mai nomi o "tutte".
    per_id = {str(s["id"]) for s in sedi_account}
    errori: List[str] = [f"sede non trovata fra quelle attive del cliente: {s!r}" for s in sedi if s not in per_id]
    dict_pagine, ids, errori_permessi = su_svc.valida_permessi(
        pagine, [s for s in sedi if s in per_id], sedi_account, cliente.get("pagine_abilitate"),
    )
    errori += [e for e in errori_permessi if not (errori and e == "serve almeno una sede")]
    if errori:
        raise HTTPException(status_code=400, detail="; ".join(errori))
    return dict_pagine, ids


def _link(token: str, primo_accesso: bool) -> str:
    base = f"https://app.oneflux.it/reset-password?token={token}"
    return base + "&onboarding=1" if primo_accesso else base


def _invia_email(email: str, nome: Optional[str], nome_account: str, link: str, primo_accesso: bool) -> bool:
    from services.email_service import brevo_send, email_template

    nome_safe = _html.escape(nome or email)
    account_safe = _html.escape(nome_account or "il tuo locale")
    email_safe = _html.escape(email)
    if primo_accesso:
        frase = f"Ti è stato creato un accesso a ONEFLUX per <strong style=\"color:#f1f5f9;\">{account_safe}</strong>. Scegli una password per entrare."
        oggetto = f"Il tuo accesso a ONEFLUX — {nome_account or 'ONEFLUX'}"
        cta = "Scegli la password"
    else:
        frase = f"Ecco il link per scegliere una nuova password del tuo accesso a ONEFLUX per <strong style=\"color:#f1f5f9;\">{account_safe}</strong>."
        oggetto = "Nuova password ONEFLUX"
        cta = "Scegli la nuova password"
    corpo = f"""
      Ciao <strong style="color:#f1f5f9;">{nome_safe}</strong>,<br><br>
      {frase}<br><br>
      <span style="color:#94a3b8;font-size:13px;">Email di accesso: <strong style="color:#cbd5e1;">{email_safe}</strong></span>
    """
    html_body = email_template(
        titolo="Il tuo accesso a ONEFLUX",
        corpo_html=corpo,
        cta_label=cta,
        cta_link=link,
        nota="⚠️ Il link scade tra 24 ore.",
    )
    return brevo_send(email, nome_safe, oggetto, html_body, contesto="sotto_utente")


def _nuovo_token() -> Dict[str, str]:
    return {
        "reset_code": secrets.token_urlsafe(32),
        "reset_expires": (datetime.now(timezone.utc) + VALIDITA_LINK).isoformat(),
    }


@router.get(BASE, tags=["Admin"])
def admin_elenco_sotto_utenti(cliente_id: str, admin_user: dict = Depends(_verify_admin)):
    """Sotto-utenti del cliente, con le sedi e le pagine che si possono assegnare."""
    sb = get_supabase_client()
    cliente = _cliente(sb, cliente_id)
    righe = (
        sb.table("sotto_utenti").select(_COLONNE)
        .eq("titolare_id", cliente_id).order("created_at").execute()
    ).data or []
    del_titolare = su_svc._pagine_account_del_titolare(cliente.get("pagine_abilitate"))
    pagine_assegnabili = sorted(
        p for p in su_svc.PAGINE_SOTTO_UTENTE
        if p not in su_svc.PAGINE_ACCOUNT or del_titolare is None or p in del_titolare
    )
    return {
        "sotto_utenti": [_pubblico(r, _sedi_di(sb, str(r["id"]))) for r in righe],
        "sedi": [{"id": str(s["id"]), "nome": s.get("nome_ristorante")} for s in su_svc.sedi_operative(sb, cliente_id)],
        "pagine_assegnabili": pagine_assegnabili,
    }


@router.post(BASE, tags=["Admin"])
def admin_crea_sotto_utente(cliente_id: str, body: NuovoSottoUtenteBody, admin_user: dict = Depends(_verify_admin)):
    """Crea un sotto-utente senza password e gli manda il link di attivazione (24 ore)."""
    sb = get_supabase_client()
    cliente = _cliente(sb, cliente_id)
    email = (body.email or "").strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Email non valida")
    if email in _admin_emails_set():
        raise HTTPException(status_code=403, detail="Non puoi usare un'email amministrativa per un sotto-utente")
    if sb.table("users").select("id").eq("email", email).limit(1).execute().data:
        raise HTTPException(status_code=409, detail=f"{email} è già l'email di un account cliente")
    if sb.table("sotto_utenti").select("id").eq("email", email).limit(1).execute().data:
        raise HTTPException(status_code=409, detail=f"{email} è già l'email di un sotto-utente")
    pagine, ids = _valida(sb, cliente, body.pagine, body.sedi)

    token = _nuovo_token()
    try:
        riga = sb.table("sotto_utenti").insert({
            "titolare_id": cliente_id,
            "email": email,
            # Non argon2: il login lo rifiuta finche' la password non la sceglie lui.
            "password_hash": "!attivazione:" + secrets.token_hex(16),
            "nome": (body.nome or "").strip() or None,
            "attivo": True,
            "pagine": pagine,
            **token,
        }).execute().data[0]
    except Exception as exc:
        if "unique" in str(exc).lower() or "23505" in str(exc):
            raise HTTPException(status_code=409, detail=f"{email} è già in uso")
        raise
    try:
        sb.table("sotto_utenti_sedi").insert(
            [{"sotto_utente_id": riga["id"], "ristorante_id": i} for i in ids]
        ).execute()
    except Exception:
        # Senza sedi non entrerebbe comunque, e la sua email resterebbe presa.
        sb.table("sotto_utenti").delete().eq("id", riga["id"]).execute()
        raise

    link = _link(token["reset_code"], primo_accesso=True)
    inviata = _invia_email(email, riga.get("nome"), cliente.get("nome_ristorante") or "", link, True)
    logger.info("Admin crea sotto-utente %s per cliente %s | admin=%s | email_inviata=%s",
                email, cliente_id, admin_user.get("email"), inviata)
    return {
        "ok": True,
        "sotto_utente": _pubblico(riga, ids),
        "email_inviata": inviata,
        # Il link in chiaro solo se l'email non e' partita (stesso criterio dei clienti).
        "link_attivazione": None if inviata else link,
    }


@router.patch(BASE + "/{sotto_utente_id}", tags=["Admin"])
def admin_modifica_sotto_utente(
    cliente_id: str, sotto_utente_id: str, body: ModificaSottoUtenteBody,
    admin_user: dict = Depends(_verify_admin),
):
    """Cambia nome, pagine, sedi o stato. Disattivare chiude subito le sue sessioni."""
    sb = get_supabase_client()
    cliente = _cliente(sb, cliente_id)
    riga = _sotto_utente(sb, cliente_id, sotto_utente_id)
    sedi_ora = _sedi_di(sb, sotto_utente_id)

    update: Dict[str, Any] = {}
    nuove_sedi: Optional[List[str]] = None
    if body.pagine is not None or body.sedi is not None:
        pagine_ora = [p for p, v in (riga.get("pagine") or {}).items() if v is True]
        pagine, ids = _valida(
            sb, cliente,
            body.pagine if body.pagine is not None else pagine_ora,
            body.sedi if body.sedi is not None else sedi_ora,
        )
        update["pagine"] = pagine
        nuove_sedi = ids
    if body.nome is not None:
        update["nome"] = body.nome.strip() or None
    if body.attivo is not None:
        update["attivo"] = body.attivo

    # Ordine: si tolgono le sedi, si cambiano pagine e stato, si aggiungono le
    # sedi. A meta' strada vede le pagine nuove solo su sedi che resteranno sue.
    via = [s for s in sedi_ora if s not in nuove_sedi] if nuove_sedi is not None else []
    nuove = [s for s in nuove_sedi if s not in sedi_ora] if nuove_sedi is not None else []
    if via:
        sb.table("sotto_utenti_sedi").delete().eq("sotto_utente_id", sotto_utente_id).in_("ristorante_id", via).execute()
    if update:
        sb.table("sotto_utenti").update(update).eq("id", sotto_utente_id).eq("titolare_id", cliente_id).execute()
    if nuove:
        sb.table("sotto_utenti_sedi").insert(
            [{"sotto_utente_id": sotto_utente_id, "ristorante_id": s} for s in nuove]
        ).execute()
    revocate = 0
    if body.attivo is False:
        from services.session_service import revoca_sessioni_sotto_utente
        revocate = revoca_sessioni_sotto_utente(sotto_utente_id, sb)

    logger.info("Admin modifica sotto-utente %s (cliente %s) campi=%s | admin=%s",
                sotto_utente_id, cliente_id, sorted(update) + (["sedi"] if nuove_sedi is not None else []),
                admin_user.get("email"))
    aggiornato = _sotto_utente(sb, cliente_id, sotto_utente_id)
    return {"ok": True, "sotto_utente": _pubblico(aggiornato, _sedi_di(sb, sotto_utente_id)), "sessioni_chiuse": revocate}


@router.delete(BASE + "/{sotto_utente_id}", tags=["Admin"])
def admin_elimina_sotto_utente(cliente_id: str, sotto_utente_id: str, admin_user: dict = Depends(_verify_admin)):
    """Elimina il sotto-utente: le sue sessioni e le sedi assegnate se ne vanno con lui.

    I dati che ha inserito restano: sono del cliente, non suoi.
    """
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    riga = _sotto_utente(sb, cliente_id, sotto_utente_id)
    from services.session_service import revoca_sessioni_sotto_utente
    revoca_sessioni_sotto_utente(sotto_utente_id, sb)
    sb.table("sotto_utenti").delete().eq("id", sotto_utente_id).eq("titolare_id", cliente_id).execute()
    logger.info("Admin elimina sotto-utente %s (cliente %s) | admin=%s", riga.get("email"), cliente_id, admin_user.get("email"))
    return {"ok": True}


@router.post(BASE + "/{sotto_utente_id}/invia-link", tags=["Admin"])
def admin_invia_link_sotto_utente(cliente_id: str, sotto_utente_id: str, admin_user: dict = Depends(_verify_admin)):
    """Nuovo link (24 ore) per scegliere la password: attivazione se e' in attesa,
    nuova password se e' gia' attivo. Il link precedente smette di valere."""
    sb = get_supabase_client()
    cliente = _cliente(sb, cliente_id)
    riga = _sotto_utente(sb, cliente_id, sotto_utente_id)
    stato = su_svc.stato(riga)
    if stato == su_svc.STATO_DISATTIVATO:
        raise HTTPException(status_code=400, detail="Sotto-utente disattivato: riattivalo prima di mandargli il link")
    token = _nuovo_token()
    sb.table("sotto_utenti").update(token).eq("id", sotto_utente_id).eq("titolare_id", cliente_id).execute()
    primo = stato == su_svc.STATO_IN_ATTESA
    link = _link(token["reset_code"], primo_accesso=primo)
    inviata = _invia_email(riga["email"], riga.get("nome"), cliente.get("nome_ristorante") or "", link, primo)
    logger.info("Admin invia link sotto-utente %s (cliente %s) | admin=%s | email_inviata=%s",
                riga.get("email"), cliente_id, admin_user.get("email"), inviata)
    return {"ok": True, "email_inviata": inviata, "link_attivazione": None if inviata else link}
