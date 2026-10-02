"""Invio degli XML al commercialista — lo attiva il cliente dalle Impostazioni
(02/10/2026).

Il cliente scrive l'email del commercialista, sceglie ogni quanto, spunta
«Autorizzo» e preme Attiva: quell'atto E' il consenso, e si salva con la sua
prova (quando, chi, il testo esatto). Il collegamento a Invoicetronic lo fa il
sistema dalla P.IVA. Il primo invio lo crea il pianificatore notturno: nessun
admin lo lancia.

Solo il titolare: le rotte sono in ROTTE_VIETATE (services/permessi_rotte.py), e
qui lo si ricontrolla. Nessun endpoint spedisce: scrivono la configurazione, ed
e' il DB (trigger e vincoli delle migration 20260925113943 e 20261002194731) a
rifiutare cio' che non va.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services import invio_commercialista_service as svc
from services import sotto_utenti_service as _su
from utils.supabase_paging import fetch_all


def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def get_supabase_client(*args, **kwargs):
    return _fw().get_supabase_client(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


def _client_invoicetronic():
    from services.invoicetronic_client import ClientInvoicetronic
    return ClientInvoicetronic()


def _avvisa_admin(testo: str) -> None:
    from services.telegram_service import invia_messaggio
    invia_messaggio(testo)


router = APIRouter(dependencies=[Depends(_verify_worker_key)])
logger = logging.getLogger("fastapi_worker")

BASE = "/api/account/invio-commercialista"
_PIVA = re.compile(r"^[0-9]{11}$")
# La stessa regola del vincolo icc_email_chk: meglio dirlo qui con parole chiare.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NON_DISPONIBILE = "L'invio al commercialista non è ancora disponibile."
SOLO_TITOLARE = "L'invio al commercialista lo può attivare solo il titolare dell'account."


def _solo_titolare(user: Dict[str, Any]) -> Dict[str, Any]:
    if _su.e_sotto_utente(user):
        raise HTTPException(status_code=403, detail=SOLO_TITOLARE)
    return user


def _oggi() -> date:
    return svc.a_roma(svc.adesso_utc()).date()


def _pive_sdi(sb, user_id: str) -> Dict[str, List[str]]:
    """P.IVA del cliente con almeno una sede attiva che riceve via SDI E almeno
    una fattura gia' arrivata da Invoicetronic, coi nomi delle sedi. Solo
    queste (Mattia, 02/10): il flag da solo non basta, quattro sedi l'hanno
    acceso dal 23/06 senza aver mai ricevuto niente."""
    sedi = fetch_all(
        sb.table("ristoranti").select("id,nome_ristorante,partita_iva")
        .eq("user_id", user_id).eq("attivo", True).eq("sdi_attivo", True).order("id")
    )
    pive: Dict[str, List[str]] = {}
    for sede in sedi:
        piva = sede.get("partita_iva")
        if isinstance(piva, str) and _PIVA.match(piva):
            pive.setdefault(piva, []).append(str(sede.get("nome_ristorante") or "").strip())
    return {
        p: sorted(n for n in nomi if n) for p, nomi in sorted(pive.items())
        if svc.prima_fattura_arrivata(sb, p) is not None
    }


def _configurazione(sb, user_id: str, piva: str) -> Optional[Dict[str, Any]]:
    righe = sb.table(svc.CONFIG).select("*").eq("piva", piva).limit(1).execute().data or []
    if not righe:
        return None
    if str(righe[0]["user_id"]) != user_id:
        # La P.IVA e' configurata su un altro account: il DB non lo permette per
        # una configurazione attiva, ma una spenta puo' restare. Non si tocca.
        raise HTTPException(status_code=409, detail="Non riusciamo ad attivare l'invio per questa P.IVA: "
                                                    "scrivi all'assistenza.")
    return righe[0]


def _ultimo_invio(sb, config_id: str) -> Optional[Dict[str, Any]]:
    righe = (
        sb.table(svc.INVII).select("periodo_dal,periodo_al,n_file,conclusa_at")
        .eq("config_id", config_id).in_("tipo", ["primo", "ordinario", "reinvio"])
        .eq("stato", "inviato").order("conclusa_at", desc=True).limit(1).execute().data or []
    )
    return righe[0] if righe else None


def _stato(sb, user_id: str) -> Dict[str, Any]:
    oggi = _oggi()
    adesso = svc.adesso_utc()
    pive = _pive_sdi(sb, user_id)
    orfani = svc.storico_orfano(sb, list(pive))
    voci = []
    for piva, sedi in pive.items():
        config = _configurazione(sb, user_id, piva)
        ultimo = svc.ultimo_giorno_inviato(sb, config["id"]) if config else None
        orfano = orfani.get(piva)
        recupero = svc.recupero_dal(
            ultimo, svc.prima_fattura_arrivata(sb, piva),
            date.fromisoformat(orfano) if orfano else None, oggi,
        )
        voce: Dict[str, Any] = {
            "piva": piva,
            "sedi": sedi,
            "attivo": bool(config and config.get("attivo")),
            "sospeso": bool(config and config.get("sospesa_at")),
            "email": (config or {}).get("email_destinatario"),
            "frequenza": (config or {}).get("frequenza") or "settimanale",
            "attivato_il": (config or {}).get("consenso_at") if config and config.get("consenso_ricevuto") else None,
            "recupero_dal": recupero.isoformat() if recupero else None,
            "ultimo_invio": _ultimo_invio(sb, config["id"]) if config else None,
            "prossimo_invio": None,
        }
        if voce["attivo"] and not voce["sospeso"]:
            partenza = svc._data(config.get("data_partenza"))
            prossimo = svc.prossimo_invio(config["frequenza"], ultimo, partenza, adesso)
            voce["prossimo_invio"] = prossimo.isoformat() if prossimo else None
        voci.append(voce)
    return {
        "disponibile": svc.invio_attivo(),
        "oggi": oggi.isoformat(),
        "frequenze": svc.FREQUENZE,
        "testo_autorizzazione": svc.TESTO_AUTORIZZAZIONE,
        "pive": voci,
    }


@router.get(BASE, tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def invio_commercialista_cliente_stato(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    user = _solo_titolare(_resolve_user_from_token(authorization))
    return _stato(get_supabase_client(), str(user["id"]))


class AttivaBody(BaseModel):
    piva: str
    email: str
    frequenza: Literal["settimanale", "quindicinale", "mensile"]
    autorizzo: bool
    includi_precedenti: bool = False


def _scrivi(sb, config_id: str, campi: Dict[str, Any]) -> None:
    try:
        sb.table(svc.CONFIG).update(campi).eq("id", config_id).execute()
    except Exception as exc:
        logger.warning("invio_commercialista cliente: configurazione %s non aggiornata (%s)",
                       config_id[:8], getattr(exc, "code", type(exc).__name__))
        raise HTTPException(status_code=400, detail="Non siamo riusciti a salvare: controlla l'email e riprova.") from None


def _collega(sb, user_id: str, piva: str) -> Dict[str, Any]:
    """Crea la configurazione (spenta) col company_id cercato su Invoicetronic."""
    from services.invoicetronic_client import ErroreInvoicetronic

    try:
        azienda = svc.cerca_azienda(sb, _client_invoicetronic(), piva)
    except ErroreInvoicetronic:
        raise HTTPException(status_code=503, detail="Non riusciamo a completare l'attivazione adesso: "
                                                    "riprova tra qualche minuto.") from None
    except svc.AziendaNonTrovata:
        raise HTTPException(status_code=400, detail="Per questa P.IVA non è ancora arrivata nessuna fattura "
                                                    "tramite OneFlux: potrai attivare l'invio dopo la prima.") from None
    except svc.AziendaIncoerente as exc:
        _avvisa_admin(f"⚠️ Invio al commercialista: il cliente {user_id[:8]} ha provato ad attivarlo, ma "
                      f"Invoicetronic risponde con l'azienda {exc.company_id} e le fatture arrivate vengono "
                      f"da {exc.viste}. Va chiarito col supporto.")
        raise HTTPException(status_code=409, detail="Non riusciamo ad attivare l'invio per questa P.IVA: "
                                                    "ti contatteremo noi.") from None
    try:
        righe = sb.table(svc.CONFIG).insert({
            "user_id": user_id, "piva": piva,
            "invoicetronic_company_id": azienda["company_id"],
            "invoicetronic_nome": azienda["nome"],
        }).execute().data
    except Exception as exc:
        logger.warning("invio_commercialista cliente: collegamento non creato per %s (%s)",
                       user_id[:8], getattr(exc, "code", type(exc).__name__))
        raise HTTPException(status_code=409, detail="Non riusciamo ad attivare l'invio per questa P.IVA: "
                                                    "scrivi all'assistenza.") from None
    return righe[0]


@router.post(BASE, tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def invio_commercialista_cliente_attiva(
    body: AttivaBody, authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Attiva (o modifica) l'invio per una P.IVA. In tre passi, perche' il trigger
    azzera consenso e attivazione quando cambia l'email: prima i dati, poi il
    consenso per l'email appena scritta, poi l'accensione."""
    user = _solo_titolare(_resolve_user_from_token(authorization))
    user_id = str(user["id"])
    if not svc.invio_attivo():
        raise HTTPException(status_code=409, detail=NON_DISPONIBILE)
    if not body.autorizzo:
        raise HTTPException(status_code=400, detail="Per attivare l'invio serve la tua autorizzazione.")
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="L'email del commercialista non sembra valida.")
    sb = get_supabase_client()
    piva = body.piva.strip()
    if piva not in _pive_sdi(sb, user_id):
        raise HTTPException(status_code=400, detail="Questa P.IVA non riceve fatture tramite OneFlux.")

    config = _configurazione(sb, user_id, piva)
    if config is None:
        config = _collega(sb, user_id, piva)
    if config.get("sospesa_at"):
        raise HTTPException(status_code=409, detail="L'invio è in verifica da parte di OneFlux: ti contatteremo noi.")

    oggi = _oggi()
    if config.get("attivo"):
        # Gia' attivo: si cambiano email o frequenza, non da quando si parte.
        partenza = svc._data(config.get("data_partenza")) or oggi
    else:
        partenza = oggi
        if body.includi_precedenti:
            orfano = svc.storico_orfano(sb, [piva]).get(piva)
            partenza = svc.recupero_dal(
                svc.ultimo_giorno_inviato(sb, config["id"]), svc.prima_fattura_arrivata(sb, piva),
                date.fromisoformat(orfano) if orfano else None, oggi,
            ) or oggi

    _scrivi(sb, config["id"], {"email_destinatario": email, "frequenza": body.frequenza,
                               "data_partenza": partenza.isoformat()})
    _scrivi(sb, config["id"], {
        "consenso_ricevuto": True,
        "consenso_data": oggi.isoformat(),
        "consenso_email": email,
        "consenso_at": svc.adesso_utc().isoformat(),
        "consenso_da": str(user.get("email") or "").strip().lower() or user_id,
        "consenso_testo": svc.testo_autorizzazione(email, body.frequenza, piva),
    })
    _scrivi(sb, config["id"], {"attivo": True})
    logger.info("invio_commercialista: attivato dal cliente %s (configurazione %s, %s, dal %s)",
                user_id[:8], str(config["id"])[:8], body.frequenza, partenza)
    if not config.get("attivo"):
        _avvisa_admin(f"ℹ️ Invio al commercialista attivato dal cliente {user_id[:8]} "
                      f"(configurazione {str(config['id'])[:8]}, {body.frequenza}, fatture dal {partenza:%d/%m/%Y}).")
    return _stato(sb, user_id)


class DisattivaBody(BaseModel):
    piva: str


@router.post(BASE + "/disattiva", tags=["Account"], dependencies=[Depends(_verify_worker_key)])
def invio_commercialista_cliente_disattiva(
    body: DisattivaBody, authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _solo_titolare(_resolve_user_from_token(authorization))
    user_id = str(user["id"])
    sb = get_supabase_client()
    config = _configurazione(sb, user_id, body.piva.strip())
    if config is None:
        raise HTTPException(status_code=404, detail="Invio non trovato")
    _scrivi(sb, config["id"], {"attivo": False})
    logger.info("invio_commercialista: disattivato dal cliente %s (configurazione %s)",
                user_id[:8], str(config["id"])[:8])
    return _stato(sb, user_id)
