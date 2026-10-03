"""Invio degli XML al commercialista — la scheda admin del cliente (25/09/2026;
rifatta il 03/10/2026: lo attiva solo l'admin, il cliente non fa niente).

Una riga per P.IVA, perche' il commercialista segue la societa': OFFSIDE ha due
locali e una P.IVA, una riga; Sushiland tre locali e tre P.IVA, tre righe.
L'admin scrive l'email (o la PEC) del commercialista, sceglie ogni quanto, preme
Attiva: il collegamento a Invoicetronic si fa qui (il company_id si CERCA, mai
scritto a mano) e il primo invio lo crea il pianificatore notturno, dalle
fatture arrivate da oggi. Si registra chi ha attivato, quando e verso chi
(consenso_at, consenso_da, consenso_testo): su richiesta del cliente.

Da attivo si salva (email e frequenza nuove, o la ripresa dopo una
sospensione) senza spegnere: la partenza resta quella. Disattiva e poi Attiva
riparte invece da oggi, e il periodo spento non si manda. Resta il chiarimento
di un esito incerto (Brevo non ha confermato), l'unico caso che ferma la P.IVA finche' qualcuno non guarda i log.
Nessun endpoint spedisce: scrivono la configurazione, ed e' il DB (trigger e
vincoli delle migration 20260925113943 e 20261002194731) a rifiutare cio' che
non va.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services import invio_commercialista_service as svc
from services.routers.admin import _verify_admin
from utils.supabase_paging import fetch_all


def _fw():
    import services.fastapi_worker as fw
    return fw


def get_supabase_client(*args, **kwargs):
    return _fw().get_supabase_client(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


def _client_invoicetronic():
    from services.invoicetronic_client import ClientInvoicetronic
    return ClientInvoicetronic()


router = APIRouter(dependencies=[Depends(_verify_worker_key)])
logger = logging.getLogger("fastapi_worker")

BASE = "/api/admin/clienti/{cliente_id}/invio-commercialista"
_PIVA = re.compile(r"^[0-9]{11}$")
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
# La stessa regola del vincolo icc_email_chk: meglio dirlo qui con parole chiare.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# I vincoli della migration, per nome: (status, frase per l'admin).
_VINCOLI = {
    "icc_email_chk": (400, "Email non valida."),
    "icc_piva_unica": (409, "Per questa P.IVA esiste gia' una configurazione."),
    "icc_company_unica": (409, "Questa azienda Invoicetronic e' gia' collegata a un'altra configurazione."),
}


def _oggi() -> date:
    return svc.a_roma(svc.adesso_utc()).date()


def _rifiuto(exc: Exception) -> HTTPException:
    """Il DB ha detto no: la frase giusta per l'admin. I messaggi dei trigger sono
    gia' frasi in italiano senza dati personali; i vincoli si traducono per nome."""
    messaggio = str(getattr(exc, "message", "") or exc).strip()
    for nome, (status, frase) in _VINCOLI.items():
        if f'"{nome}"' in messaggio:
            return HTTPException(status_code=status, detail=frase)
    if getattr(exc, "code", None) in ("23514", "23505"):
        return HTTPException(status_code=400, detail=messaggio.splitlines()[0] if messaggio else "Richiesta rifiutata")
    raise exc


def _ids_validi(*ids: str) -> None:
    """Un id che non e' un UUID arriverebbe al DB come cast fallito (un 500)."""
    if not all(_ID.match(i or "") for i in ids):
        raise HTTPException(status_code=404, detail="Non trovato")


def _cliente(sb, cliente_id: str) -> None:
    _ids_validi(cliente_id)
    if not sb.table("users").select("id").eq("id", cliente_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")


def _pive_sdi(sb, cliente_id: str) -> Dict[str, List[str]]:
    """P.IVA del cliente con almeno una sede attiva che riceve via SDI, coi nomi
    delle sedi. Le altre non hanno fatture da inviare."""
    sedi = fetch_all(
        sb.table("ristoranti").select("id,nome_ristorante,partita_iva")
        .eq("user_id", cliente_id).eq("attivo", True).eq("sdi_attivo", True).order("id")
    )
    pive: Dict[str, List[str]] = {}
    for sede in sedi:
        piva = sede.get("partita_iva")
        if isinstance(piva, str) and _PIVA.match(piva):
            pive.setdefault(piva, []).append(str(sede.get("nome_ristorante") or "").strip())
    return {p: sorted(n for n in nomi if n) for p, nomi in sorted(pive.items())}


def _configurazioni(sb, cliente_id: str) -> Dict[str, Dict[str, Any]]:
    righe = fetch_all(sb.table(svc.CONFIG).select("*").eq("user_id", cliente_id).order("id"))
    return {r["piva"]: r for r in righe}


def _ultimo_invio(sb, config_id: str) -> Optional[Dict[str, Any]]:
    righe = (
        sb.table(svc.INVII).select("periodo_dal,periodo_al,n_file,conclusa_at")
        .eq("config_id", config_id).in_("tipo", ["primo", "ordinario"])
        .eq("stato", "inviato").order("conclusa_at", desc=True).limit(1).execute().data or []
    )
    return righe[0] if righe else None


def _da_chiarire(sb, config_id: str) -> Optional[Dict[str, Any]]:
    righe = (
        sb.table(svc.INVII).select("id,periodo_dal,periodo_al")
        .eq("config_id", config_id).eq("stato", "esito_incerto").limit(1).execute().data or []
    )
    return righe[0] if righe else None


def _stato(sb, cliente_id: str) -> Dict[str, Any]:
    adesso = svc.adesso_utc()
    pive = _pive_sdi(sb, cliente_id)
    configurazioni = _configurazioni(sb, cliente_id)
    voci = []
    # Anche una P.IVA che non riceve piu' via SDI ma ha una configurazione: va
    # vista, e va potuta spegnere.
    for piva in sorted(set(pive) | set(configurazioni)):
        config = configurazioni.get(piva)
        voce: Dict[str, Any] = {
            "piva": piva,
            "sedi": pive.get(piva, []),
            "sdi_attivo": piva in pive,
            "arrivate": svc.prima_fattura_arrivata(sb, piva) is not None,
            "config_id": None, "attivo": False, "sospesa_motivo": None,
            "email": None, "frequenza": "settimanale",
            "attivato_il": None, "attivato_da": None,
            "ultimo_invio": None, "prossimo_invio": None, "da_chiarire": None,
        }
        if config:
            voce.update({
                "config_id": config["id"],
                "attivo": bool(config.get("attivo")),
                "sospesa_motivo": (config.get("sospesa_motivo") or "sospesa") if config.get("sospesa_at") else None,
                "email": config.get("email_destinatario"),
                "frequenza": config.get("frequenza") or "settimanale",
                "attivato_il": config.get("consenso_at") if config.get("consenso_ricevuto") else None,
                "attivato_da": config.get("consenso_da") if config.get("consenso_ricevuto") else None,
                "ultimo_invio": _ultimo_invio(sb, config["id"]),
                "da_chiarire": _da_chiarire(sb, config["id"]),
            })
            if voce["attivo"] and not voce["sospesa_motivo"] and voce["sdi_attivo"]:
                prossimo = svc.prossimo_invio(
                    voce["frequenza"], svc.ultimo_giorno_inviato(sb, config["id"]),
                    svc._data(config.get("data_partenza")), adesso,
                )
                voce["prossimo_invio"] = prossimo.isoformat() if prossimo else None
        voci.append(voce)
    return {"interruttore": svc.invio_attivo(), "frequenze": svc.FREQUENZE, "pive": voci}


@router.get(BASE, tags=["Admin"])
def invio_commercialista_stato(cliente_id: str, admin_user: dict = Depends(_verify_admin)) -> Dict[str, Any]:
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    return _stato(sb, cliente_id)


def _collega(sb, cliente_id: str, piva: str) -> Dict[str, Any]:
    """Crea la configurazione (spenta) col company_id cercato su Invoicetronic."""
    from services.invoicetronic_client import ErroreInvoicetronic

    try:
        azienda = svc.cerca_azienda(sb, _client_invoicetronic(), piva)
    except ErroreInvoicetronic as exc:
        raise HTTPException(status_code=503, detail=f"Invoicetronic non risponde come dovrebbe: {exc}") from None
    except svc.AziendaNonTrovata:
        raise HTTPException(
            status_code=400,
            detail="Su Invoicetronic questa P.IVA non c'e' ancora: si potra' attivare dopo la prima fattura "
                   "arrivata sul codice destinatario di OneFlux.",
        ) from None
    except svc.AziendaIncoerente as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Invoicetronic risponde con l'azienda {exc.company_id}, ma le fatture gia' arrivate per "
                   f"questa P.IVA vengono da {exc.viste}: non si collega, va chiarito col supporto.",
        ) from None
    try:
        return sb.table(svc.CONFIG).insert({
            "user_id": cliente_id, "piva": piva,
            "invoicetronic_company_id": azienda["company_id"],
            "invoicetronic_nome": azienda["nome"],
        }).execute().data[0]
    except Exception as exc:
        raise _rifiuto(exc) from None


def _scrivi(sb, config_id: str, campi: Dict[str, Any]) -> None:
    try:
        sb.table(svc.CONFIG).update(campi).eq("id", config_id).execute()
    except Exception as exc:
        raise _rifiuto(exc) from None


class AttivaBody(BaseModel):
    piva: str
    email: str
    frequenza: Literal["settimanale", "quindicinale", "mensile"]


@router.post(BASE + "/attiva", tags=["Admin"])
def invio_commercialista_attiva(
    cliente_id: str, body: AttivaBody, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """Attiva (o cambia email e frequenza) per una P.IVA. In tre passi, perche' il
    trigger azzera consenso e attivazione quando cambia l'email: i dati, poi la
    registrazione per l'email appena scritta, poi l'accensione. Da spento si
    parte dalle fatture arrivate da oggi; da acceso la partenza non cambia."""
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="L'email del commercialista non sembra valida.")
    piva = body.piva.strip()
    if piva not in _pive_sdi(sb, cliente_id):
        raise HTTPException(status_code=400, detail="Questa P.IVA non riceve fatture tramite OneFlux (SDI).")
    config = _configurazioni(sb, cliente_id).get(piva) or _collega(sb, cliente_id, piva)

    oggi = _oggi()
    partenza = (svc._data(config.get("data_partenza")) or oggi) if config.get("attivo") else oggi
    admin = str(admin_user.get("email") or "admin").strip().lower()
    _scrivi(sb, config["id"], {"email_destinatario": email, "frequenza": body.frequenza,
                               "data_partenza": partenza.isoformat()})
    _scrivi(sb, config["id"], {
        "consenso_ricevuto": True,
        "consenso_data": oggi.isoformat(),
        "consenso_email": email,
        "consenso_at": svc.adesso_utc().isoformat(),
        "consenso_da": admin,
        "consenso_testo": svc.testo_attivazione(admin, email, body.frequenza, piva),
    })
    # Riattivare toglie anche una sospensione della guardia: il trigger rifa' il
    # controllo che la P.IVA sia solo di questo cliente, e se non lo e' rifiuta.
    _scrivi(sb, config["id"], {"attivo": True, "sospesa_at": None, "sospesa_motivo": None})
    logger.info("invio_commercialista: attivato per cliente %s (configurazione %s, %s, dal %s) | admin=%s",
                cliente_id[:8], str(config["id"])[:8], body.frequenza, partenza, admin)
    return _stato(sb, cliente_id)


class DisattivaBody(BaseModel):
    piva: str


@router.post(BASE + "/disattiva", tags=["Admin"])
def invio_commercialista_disattiva(
    cliente_id: str, body: DisattivaBody, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    config = _configurazioni(sb, cliente_id).get(body.piva.strip())
    if config is None:
        raise HTTPException(status_code=404, detail="Configurazione non trovata")
    _scrivi(sb, config["id"], {"attivo": False})
    logger.info("invio_commercialista: disattivato per cliente %s (configurazione %s) | admin=%s",
                cliente_id[:8], str(config["id"])[:8], admin_user.get("email"))
    return _stato(sb, cliente_id)


class ChiarisciBody(BaseModel):
    esito: Literal["arrivata", "non_arrivata"]


@router.post(BASE + "/invii/{invio_id}/chiarisci", tags=["Admin"])
def invio_commercialista_chiarisci(
    cliente_id: str, invio_id: str, body: ChiarisciBody, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """Un esito incerto si chiude guardando i log di Brevo. «Non arrivata» libera
    il periodo: il prossimo invio lo rispedisce."""
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    _ids_validi(invio_id)
    adesso = svc.adesso_utc().isoformat()
    if body.esito == "arrivata":
        campi = {"stato": "inviato", "motivo": "chiarito dall'admin: arrivata", "conclusa_at": adesso}
    else:
        campi = {"stato": "errore", "chiarito_non_partito_at": adesso,
                 "motivo": "chiarito dall'admin: non arrivata", "conclusa_at": adesso}
    try:
        righe = (
            sb.table(svc.INVII).update(campi)
            .eq("id", invio_id).eq("user_id", cliente_id).eq("stato", "esito_incerto").execute().data
        )
    except Exception as exc:
        raise _rifiuto(exc) from None
    if not righe:
        raise HTTPException(status_code=409, detail="Si chiarisce solo un invio dall'esito incerto di questo cliente.")
    logger.info("invio_commercialista: invio %s chiarito (%s) | admin=%s",
                invio_id[:8], body.esito, admin_user.get("email"))
    return _stato(sb, cliente_id)
