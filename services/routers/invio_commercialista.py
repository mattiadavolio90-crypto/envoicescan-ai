"""Invio degli XML al commercialista — l'area admin (fase D del piano, 25/09/2026).

Dalla scheda cliente l'admin:
  - collega una P.IVA del cliente a Invoicetronic: il company_id si CERCA
    (`GET /company/IT<piva>`), si confronta con quello delle fatture gia'
    arrivate e si salva solo se coincide con quello che l'admin ha visto;
  - scrive email del commercialista, frequenza, data di partenza, e registra il
    consenso (vale per l'email di quel momento);
  - lancia la prova a vuoto, l'invio (il primo o, dopo, quello del periodo
    maturato) e i reinvii;
  - chiarisce gli esiti incerti e annulla una richiesta non ancora presa.

Nessun endpoint spedisce: scrivono una riga `richiesto` nel registro, che
l'esecutore del queue-worker prende entro un minuto. E' il DB (trigger e vincoli
della migration 20260925113943) a rifiutare cio' che non e' autorizzato: qui i
suoi rifiuti diventano frasi per l'admin.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Literal, Optional, Set

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
DUE_ANNI = (
    "Invoicetronic conserva le fatture ricevute per 2 anni. Per periodi precedenti "
    "usa il Cassetto fiscale dell'Agenzia delle Entrate."
)
# I vincoli della migration, per nome: (status, frase per l'admin).
_VINCOLI = {
    "icc_attivabile_chk": (400, "Per attivare servono l'email del commercialista, il consenso per quell'email, "
                                "la data di partenza e il collegamento a Invoicetronic."),
    "icc_email_chk": (400, "Email non valida."),
    "icc_frequenza_chk": (400, "Frequenza non valida."),
    "ici_mai_oggi_chk": (400, "Il periodo deve finire al piu' tardi ieri."),
    "ici_due_anni_chk": (400, DUE_ANNI),
    "ici_periodo_chk": (400, "La data di inizio viene dopo quella di fine."),
    "icc_piva_unica": (409, "Per questa P.IVA esiste gia' una configurazione."),
    "icc_company_unica": (409, "Questa azienda Invoicetronic e' gia' collegata a un'altra configurazione."),
    "ici_uno_in_volo": (409, "C'e' gia' un invio in corso o da chiarire per questo cliente: aspetta che finisca."),
    "ici_un_solo_primo": (409, "Il primo invio e' gia' stato fatto."),
    "ici_inizio_unico": (409, "Quel periodo e' gia' stato inviato o e' in corso."),
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
    codice = getattr(exc, "code", None)
    if codice == "23P01":
        return HTTPException(status_code=409, detail="Il periodo si sovrappone a un invio gia' fatto o in corso.")
    if codice in ("23514", "23505"):
        return HTTPException(status_code=400, detail=messaggio.splitlines()[0] if messaggio else "Richiesta rifiutata")
    raise exc


def _cliente(sb, cliente_id: str) -> None:
    if not sb.table("users").select("id").eq("id", cliente_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail="Cliente non trovato")


def _configurazione(sb, cliente_id: str, config_id: str) -> Dict[str, Any]:
    righe = (
        sb.table(svc.CONFIG).select("*")
        .eq("id", config_id).eq("user_id", cliente_id).limit(1).execute().data
    )
    if not righe:
        raise HTTPException(status_code=404, detail="Configurazione non trovata")
    return righe[0]


def _piva_del_cliente(sb, cliente_id: str) -> List[str]:
    sedi = fetch_all(sb.table("ristoranti").select("id,partita_iva").eq("user_id", cliente_id).order("id"))
    registrate = fetch_all(sb.table("piva_ristoranti").select("id,piva").eq("user_id", cliente_id).order("id"))
    tutte = {r.get("partita_iva") for r in sedi} | {r.get("piva") for r in registrate}
    return sorted(p for p in tutte if isinstance(p, str) and _PIVA.match(p))


def _company_gia_viste(sb, piva: str) -> Set[int]:
    """I company_id che il webhook ha gia' scritto per questa P.IVA."""
    righe = fetch_all(
        sb.table("fatture_queue").select("id,payload_meta")
        .eq("source", "invoicetronic").eq("piva_raw", piva).order("id")
    )
    viste = set()
    for riga in righe:
        valore = (riga.get("payload_meta") or {}).get("invoicetronic_company_id")
        if isinstance(valore, int) and not isinstance(valore, bool):
            viste.add(valore)
    return viste


def _trova_azienda(sb, cliente_id: str, piva: str) -> Dict[str, Any]:
    from services.invoicetronic_client import ErroreInvoicetronic

    if not _PIVA.match(piva or "") or piva not in _piva_del_cliente(sb, cliente_id):
        raise HTTPException(status_code=400, detail="La P.IVA non e' di una sede di questo cliente")
    try:
        azienda = _client_invoicetronic().azienda_per_piva(piva)
    except ErroreInvoicetronic as exc:
        raise HTTPException(status_code=503, detail=f"Invoicetronic non risponde come dovrebbe: {exc}") from None
    if azienda is None:
        raise HTTPException(
            status_code=404,
            detail="Su Invoicetronic questa P.IVA non c'e' ancora: l'azienda nasce all'arrivo della prima "
                   "fattura sul codice destinatario di OneFlux.",
        )
    viste = _company_gia_viste(sb, piva)
    if viste and viste != {azienda["id"]}:
        raise HTTPException(
            status_code=409,
            detail=f"Invoicetronic risponde con l'azienda {azienda['id']}, ma le fatture gia' arrivate per "
                   f"questa P.IVA vengono da {sorted(viste)}: non si collega, va chiarito col supporto.",
        )
    return {"company_id": azienda["id"], "nome": azienda.get("name"), "vat": azienda.get("vat"),
            "gia_viste": sorted(viste)}


# ── Letture ─────────────────────────────────────────────────────────────────

_COLONNE_INVII = (
    "id,tipo,stato,periodo_dal,periodo_al,richiesto_da,n_file,byte_totali,destinatario,motivo,"
    "creata_at,iniziata_at,conclusa_at,email_tentata_at,brevo_http_status,link_scade_il,"
    "file_rimossi_at,chiarito_non_partito_at"
)


@router.get(BASE, tags=["Admin"])
def invio_commercialista_stato(cliente_id: str, admin_user: dict = Depends(_verify_admin)) -> Dict[str, Any]:
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    oggi = _oggi()
    configurazioni = fetch_all(sb.table(svc.CONFIG).select("*").eq("user_id", cliente_id).order("creata_at"))
    risultato = []
    for config in configurazioni:
        invii = (
            sb.table(svc.INVII).select(_COLONNE_INVII)
            .eq("config_id", config["id"]).order("creata_at", desc=True).limit(20).execute().data or []
        )
        ultimo = svc.ultimo_giorno_inviato(sb, config["id"])
        risultato.append({
            **config,
            "sede_sdi_attiva": svc.sede_sdi_attiva(sb, cliente_id, config["piva"]),
            "ultimo_giorno_inviato": ultimo.isoformat() if ultimo else None,
            "invii": invii,
        })
    collegate = {c["piva"] for c in configurazioni}
    return {
        "oggi": oggi.isoformat(),
        "limite_due_anni": svc.limite_due_anni(oggi).isoformat(),
        "piva_disponibili": [p for p in _piva_del_cliente(sb, cliente_id) if p not in collegate],
        "configurazioni": risultato,
    }


@router.get(BASE + "/azienda", tags=["Admin"])
def invio_commercialista_cerca_azienda(
    cliente_id: str, piva: str, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    return _trova_azienda(sb, cliente_id, piva.strip())


# ── Configurazione ──────────────────────────────────────────────────────────

class CollegaBody(BaseModel):
    piva: str
    company_id: int


@router.post(BASE, tags=["Admin"])
def invio_commercialista_collega(
    cliente_id: str, body: CollegaBody, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """Crea la configurazione (spenta). Il company_id lo decide Invoicetronic,
    non il body: il body dice solo quale azienda l'admin ha visto e confermato."""
    sb = get_supabase_client()
    _cliente(sb, cliente_id)
    azienda = _trova_azienda(sb, cliente_id, body.piva.strip())
    if azienda["company_id"] != body.company_id:
        raise HTTPException(status_code=409, detail="Invoicetronic ora risponde con un'altra azienda: ricarica e ricontrolla.")
    try:
        righe = sb.table(svc.CONFIG).insert({
            "user_id": cliente_id,
            "piva": body.piva.strip(),
            "invoicetronic_company_id": azienda["company_id"],
            "invoicetronic_nome": azienda["nome"],
        }).execute().data
    except HTTPException:
        raise
    except Exception as exc:
        raise _rifiuto(exc) from None
    logger.info("invio_commercialista: collegata P.IVA per cliente %s | admin=%s",
                    cliente_id, admin_user.get("email"))
    return righe[0]


class ModificaBody(BaseModel):
    email_destinatario: Optional[str] = None
    frequenza: Optional[Literal["settimanale", "quindicinale", "mensile"]] = None
    data_partenza: Optional[date] = None
    consenso_data: Optional[date] = None
    revoca_consenso: bool = False
    attivo: Optional[bool] = None
    riprendi: bool = False


@router.patch(BASE + "/{config_id}", tags=["Admin"])
def invio_commercialista_modifica(
    cliente_id: str, config_id: str, body: ModificaBody, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """In tre passi, perche' il trigger azzera consenso e attivazione quando
    cambia l'email: prima i dati, poi il consenso (per l'email appena scritta),
    poi accensione o ripresa."""
    sb = get_supabase_client()
    config = _configurazione(sb, cliente_id, config_id)
    oggi = _oggi()

    dati: Dict[str, Any] = {}
    if body.email_destinatario is not None:
        email = body.email_destinatario.strip().lower()
        dati["email_destinatario"] = email or None
    if body.frequenza is not None:
        dati["frequenza"] = body.frequenza
    if body.data_partenza is not None:
        if body.data_partenza < svc.limite_due_anni(oggi):
            raise HTTPException(status_code=400, detail=DUE_ANNI)
        if body.data_partenza >= oggi:
            raise HTTPException(status_code=400, detail="La data di partenza deve essere passata.")
        dati["data_partenza"] = body.data_partenza.isoformat()
    if body.revoca_consenso:
        dati.update({"consenso_ricevuto": False, "consenso_data": None, "consenso_email": None, "attivo": False})

    passi: List[Dict[str, Any]] = [dati] if dati else []
    if body.consenso_data is not None:
        if body.consenso_data > oggi:
            raise HTTPException(status_code=400, detail="Il consenso non puo' avere una data futura.")
        email = dati.get("email_destinatario", config.get("email_destinatario"))
        if not email:
            raise HTTPException(status_code=400, detail="Prima scrivi l'email del commercialista: il consenso vale per quell'email.")
        passi.append({"consenso_ricevuto": True, "consenso_data": body.consenso_data.isoformat(), "consenso_email": email})
    finale: Dict[str, Any] = {}
    if body.attivo is not None:
        finale["attivo"] = body.attivo
    if body.riprendi:
        finale.update({"sospesa_at": None, "sospesa_motivo": None})
    if finale:
        passi.append(finale)
    if not passi:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")

    for passo in passi:
        try:
            sb.table(svc.CONFIG).update(passo).eq("id", config_id).eq("user_id", cliente_id).execute()
        except Exception as exc:
            raise _rifiuto(exc) from None
    logger.info("invio_commercialista: configurazione %s aggiornata (%s) | admin=%s",
                    config_id[:8], sorted(k for p in passi for k in p), admin_user.get("email"))
    return _configurazione(sb, cliente_id, config_id)


# ── Invii ───────────────────────────────────────────────────────────────────

class InvioBody(BaseModel):
    tipo: Literal["prova", "invia_ora", "reinvio"]
    dal: Optional[date] = None
    al: Optional[date] = None


@router.post(BASE + "/{config_id}/invii", tags=["Admin"])
def invio_commercialista_richiedi(
    cliente_id: str, config_id: str, body: InvioBody, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """Scrive la richiesta. «Invia ora» e' il primo invio (dalla data di partenza)
    finche' non ce n'e' uno riuscito, poi il periodo maturato dall'ultimo."""
    sb = get_supabase_client()
    config = _configurazione(sb, cliente_id, config_id)
    if config.get("invoicetronic_company_id") is None:
        raise HTTPException(status_code=400, detail="Prima collega la P.IVA a Invoicetronic.")
    oggi = _oggi()
    ieri, limite = oggi - timedelta(days=1), svc.limite_due_anni(oggi)

    if body.tipo == "invia_ora":
        ultimo = svc.ultimo_giorno_inviato(sb, config_id)
        if ultimo is None:
            if not config.get("data_partenza"):
                raise HTTPException(status_code=400, detail="Manca la data di partenza.")
            tipo, dal = "primo", max(date.fromisoformat(str(config["data_partenza"])[:10]), limite)
        else:
            tipo, dal = "ordinario", max(ultimo + timedelta(days=1), limite)
        al = ieri
        if dal > al:
            raise HTTPException(status_code=400, detail="Niente da inviare: fino a ieri e' gia' stato tutto inviato.")
    else:
        # Fine entro ieri, inizio entro 2 anni, inizio prima della fine: li
        # controllano i vincoli del registro, e _rifiuto li dice con queste parole.
        if body.dal is None or body.al is None:
            raise HTTPException(status_code=400, detail="Indica il periodo (dal, al).")
        tipo, dal, al = body.tipo, body.dal, body.al

    if tipo != "prova" and not svc.sede_sdi_attiva(sb, cliente_id, config["piva"]):
        raise HTTPException(status_code=400, detail="Sospesa: nessuna sede di questa P.IVA ha la ricezione SDI attiva.")
    try:
        righe = sb.table(svc.INVII).insert({
            "config_id": config_id,
            "user_id": cliente_id,
            "piva": config["piva"],
            "invoicetronic_company_id": config["invoicetronic_company_id"],
            "destinatario": config.get("email_destinatario"),
            "tipo": tipo,
            "periodo_dal": dal.isoformat(),
            "periodo_al": al.isoformat(),
            "stato": "richiesto",
            "richiesto_da": "admin",
        }).execute().data
    except Exception as exc:
        raise _rifiuto(exc) from None
    logger.info("invio_commercialista: richiesto %s %s..%s per configurazione %s | admin=%s",
                    tipo, dal, al, config_id[:8], admin_user.get("email"))
    return righe[0]


def _invio(sb, cliente_id: str, config_id: str, invio_id: str) -> None:
    _configurazione(sb, cliente_id, config_id)
    righe = (
        sb.table(svc.INVII).select("id")
        .eq("id", invio_id).eq("config_id", config_id).limit(1).execute().data
    )
    if not righe:
        raise HTTPException(status_code=404, detail="Invio non trovato")


class ChiarisciBody(BaseModel):
    esito: Literal["arrivata", "non_arrivata"]


@router.post(BASE + "/{config_id}/invii/{invio_id}/chiarisci", tags=["Admin"])
def invio_commercialista_chiarisci(
    cliente_id: str, config_id: str, invio_id: str, body: ChiarisciBody,
    admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    """Un esito incerto si chiude guardando i log di Brevo. «Non arrivata» libera
    il periodo: il prossimo invio lo rispedisce."""
    sb = get_supabase_client()
    _invio(sb, cliente_id, config_id, invio_id)
    adesso = svc.adesso_utc().isoformat()
    if body.esito == "arrivata":
        campi = {"stato": "inviato", "motivo": "chiarito dall'admin: arrivata", "conclusa_at": adesso}
    else:
        campi = {"stato": "errore", "chiarito_non_partito_at": adesso,
                 "motivo": "chiarito dall'admin: non arrivata", "conclusa_at": adesso}
    try:
        righe = (
            sb.table(svc.INVII).update(campi)
            .eq("id", invio_id).eq("stato", "esito_incerto").execute().data
        )
    except Exception as exc:
        raise _rifiuto(exc) from None
    if not righe:
        raise HTTPException(status_code=409, detail="Si chiarisce solo un invio dall'esito incerto.")
    logger.info("invio_commercialista: invio %s chiarito (%s) | admin=%s",
                    invio_id[:8], body.esito, admin_user.get("email"))
    return righe[0]


@router.post(BASE + "/{config_id}/invii/{invio_id}/annulla", tags=["Admin"])
def invio_commercialista_annulla(
    cliente_id: str, config_id: str, invio_id: str, admin_user: dict = Depends(_verify_admin),
) -> Dict[str, Any]:
    sb = get_supabase_client()
    _invio(sb, cliente_id, config_id, invio_id)
    righe = (
        sb.table(svc.INVII)
        .update({"stato": "errore", "motivo": "annullato dall'admin", "conclusa_at": svc.adesso_utc().isoformat()})
        .eq("id", invio_id).eq("stato", "richiesto").execute().data
    )
    if not righe:
        raise HTTPException(status_code=409, detail="Si annulla solo una richiesta che l'esecutore non ha ancora preso.")
    return righe[0]
