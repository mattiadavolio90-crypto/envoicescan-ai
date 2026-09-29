"""La «Conferma» delle cifre dettate all'assistente (fase 3, M4).

Il modello non scrive mai: propone una card (incasso di un giorno, personale di
un mese, fatturato di un mese) e la scrittura parte solo da qui, quando il
cliente preme Conferma. Per questo l'endpoint non si fida di niente di cio' che
arriva: la sede della proposta si riverifica (dell'account, attiva, non tecnica,
fra quelle del sotto-utente, con la pagina Margini), i valori si rivalidano, e
se il valore registrato non e' piu' quello mostrato sulla card (un'email di
cassa arrivata nel frattempo, un form in un'altra scheda) si risponde 409 invece
di sovrascrivere.

La sede e' quella della proposta, non quella attiva della sessione: le cache
della sede attiva divergono qualche secondo fra i processi, e la card dice gia'
su quale locale si scrive.

Diversamente dai form (`/api/ricavi/giornalieri`, `/api/margini/cella`) qui si
scrive solo cio' che e' stato dettato: `coperti` e gli altri campi restano, e il
totale mensile non si spegne mai (su un mese tenuto a totale l'incasso di un
giorno non si registra).
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config.logger_setup import get_logger
from services import sotto_utenti_service as _su

logger = get_logger("router_assistente")


def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _oggi() -> date:
    return _fw()._oggi_rome()


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


router = APIRouter(dependencies=[Depends(_verify_worker_key)])


# Tetti: tre-cinque volte il massimo registrato sul live il 29/9/2026 (incasso di
# un giorno 36.461 €, fatturato di un mese 88.606 €, personale di un mese
# 60.000 €). Non sono un limite di business: fermano uno zero di troppo prima che
# finisca nel MOL; la card mostra comunque la cifra al cliente.
TETTO_INCASSO_GIORNO = 100_000.0
TETTO_FATTURATO_MESE = 500_000.0
TETTO_PERSONALE_MESE = 300_000.0
GIORNI_INDIETRO_INCASSO = 60
MESI_INDIETRO = 12  # il mese corrente e i 12 prima

CAMPI_INCASSO = ("fatturato_iva10", "altri_ricavi_noiva", "fatturato_iva22")
PAGINA_RICHIESTA = "margini"
_TOLLERANZA = 0.005


class RegistraRequest(BaseModel):
    tipo: Literal["incasso_giorno", "personale_mese", "fatturato_mese"]
    ristorante_id: str
    data: Optional[str] = None
    anno: Optional[int] = None
    mese: Optional[int] = None
    fatturato_iva10: float = 0.0
    altri_ricavi_noiva: float = 0.0
    fatturato_iva22: float = 0.0
    costo_dipendenti: Optional[float] = None
    # Il valore mostrato sulla card come «risulta …»; None = nessun valore.
    precedente: Optional[Dict[str, float]] = None


class RegistraResponse(BaseModel):
    ok: bool
    tipo: str
    ristorante_id: str
    valori: Dict[str, Any]


# ─── Validazioni pure ─────────────────────────────────────────────────────────
def _importo(nome: str, valore: Any) -> float:
    try:
        v = float(valore)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Importo non valido: {nome}")
    if not math.isfinite(v) or v < 0:
        raise HTTPException(status_code=400, detail=f"Importo non valido: {nome}")
    return round(v, 2)


def valida_importi_incasso(body: RegistraRequest, tetto: float) -> Dict[str, float]:
    valori = {c: _importo(c, getattr(body, c)) for c in CAMPI_INCASSO}
    totale = sum(valori.values())
    if totale <= 0:
        raise HTTPException(status_code=400, detail="L'importo deve essere maggiore di zero")
    if totale > tetto:
        raise HTTPException(status_code=400, detail="Importo fuori scala: controlla la cifra")
    return valori


def valida_personale(body: RegistraRequest) -> float:
    v = _importo("costo_dipendenti", body.costo_dipendenti)
    if v <= 0:
        raise HTTPException(status_code=400, detail="L'importo deve essere maggiore di zero")
    if v > TETTO_PERSONALE_MESE:
        raise HTTPException(status_code=400, detail="Importo fuori scala: controlla la cifra")
    return v


def valida_giorno(testo: Optional[str], oggi: date) -> date:
    try:
        giorno = date.fromisoformat(str(testo or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida")
    if giorno > oggi:
        raise HTTPException(status_code=400, detail="Non si registra un incasso nel futuro")
    if giorno < oggi - timedelta(days=GIORNI_INDIETRO_INCASSO):
        raise HTTPException(status_code=400, detail="Data troppo lontana: usa Movimenti")
    return giorno


def valida_mese(anno: Optional[int], mese: Optional[int], oggi: date) -> Tuple[int, int]:
    if not isinstance(anno, int) or not isinstance(mese, int) or not 1 <= mese <= 12:
        raise HTTPException(status_code=400, detail="Mese non valido")
    indice = anno * 12 + (mese - 1)
    corrente = oggi.year * 12 + (oggi.month - 1)
    if indice > corrente:
        raise HTTPException(status_code=400, detail="Non si registra un mese nel futuro")
    if indice < corrente - MESI_INDIETRO:
        raise HTTPException(status_code=400, detail="Mese troppo lontano: usa Margini")
    return anno, mese


def _uguali(precedente: Optional[Dict[str, float]], attuale: Optional[Dict[str, float]]) -> bool:
    if precedente is None or attuale is None:
        return precedente is None and attuale is None
    if set(precedente) != set(attuale):
        return False
    try:
        return all(abs(float(precedente[k]) - float(attuale[k])) < _TOLLERANZA for k in attuale)
    except (TypeError, ValueError):
        return False


def _conflitto(motivo: str, attuale: Optional[Dict[str, float]] = None) -> HTTPException:
    return HTTPException(status_code=409, detail={"motivo": motivo, "attuale": attuale})


# ─── Letture ──────────────────────────────────────────────────────────────────
# Le usera' anche lo strumento di proposta (step 2): la card mostra come
# «risulta …» esattamente cio' che qui si confronta. None = niente da mostrare
# (riga assente o tutta a zero), e con None la card dice «nessun valore».
# Il primo elemento e' l'id della riga da aggiornare, anche quando e' a zero.
def _num(v: Any) -> float:
    return round(float(v or 0), 2)


def sede_scrivibile(user: Dict[str, Any], sb, ristorante_id: str) -> str:
    """La sede della proposta, verificata. 404 se non e' un punto vendita attivo
    dell'account (anche per un id malformato: niente 500 dal cast), 403 se chi
    agisce e' un sotto-utente senza quella sede."""
    try:
        rid = str(uuid.UUID(str(ristorante_id)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Sede non trovata")
    trovata = (
        sb.table("ristoranti")
        .select("id")
        .eq("id", rid)
        .eq("user_id", str(user["id"]))
        .eq("attivo", True)
        .eq("sede_tecnica", False)
        .limit(1)
        .execute()
    )
    if not trovata.data:
        raise HTTPException(status_code=404, detail="Sede non trovata")
    _su.verifica_sede_consentita(user, rid)
    return rid


def leggi_incasso_giorno(sb, rid: str, giorno: date) -> Tuple[Optional[str], Optional[Dict[str, float]]]:
    resp = (
        sb.table("ricavi_giornalieri")
        .select("id, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva")
        .eq("ristorante_id", rid)
        .eq("data", giorno.isoformat())
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None, None
    riga = resp.data[0]
    valori = {c: _num(riga.get(c)) for c in CAMPI_INCASSO}
    return str(riga["id"]), (valori if sum(valori.values()) > 0 else None)


def leggi_mese_a_totale(sb, rid: str, anno: int, mese: int) -> Tuple[Optional[str], Optional[Dict[str, float]]]:
    """(id della riga di modalita', importi se il mese e' tenuto a totale)."""
    resp = (
        sb.table("ricavi_modalita_mensile")
        .select("id, modalita, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva")
        .eq("ristorante_id", rid)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None, None
    riga = resp.data[0]
    if riga.get("modalita") != "mensile":
        return str(riga["id"]), None
    return str(riga["id"]), {c: _num(riga.get(c)) for c in CAMPI_INCASSO}


def mese_ha_giorni(sb, rid: str, anno: int, mese: int) -> bool:
    primo = date(anno, mese, 1)
    dopo = date(anno + (mese == 12), mese % 12 + 1, 1)
    resp = (
        sb.table("ricavi_giornalieri")
        .select("id")
        .eq("ristorante_id", rid)
        .gte("data", primo.isoformat())
        .lt("data", dopo.isoformat())
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def leggi_personale(sb, rid: str, anno: int, mese: int) -> Tuple[Optional[str], Optional[Dict[str, float]]]:
    resp = (
        sb.table("margini_mensili")
        .select("id, costo_dipendenti")
        .eq("ristorante_id", rid)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None, None
    # La riga del mese nasce col trigger dei ricavi e `costo_dipendenti` ha
    # default 0: zero vuol dire «non registrato», come per l'avviso del briefing.
    valore = _num(resp.data[0].get("costo_dipendenti"))
    return str(resp.data[0]["id"]), ({"costo_dipendenti": valore} if valore > 0 else None)


# ─── Scritture ────────────────────────────────────────────────────────────────
def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inserisci_o_409(sb, tabella: str, riga: Dict[str, Any], rileggi) -> None:
    """Insert quando la card diceva «nessun valore». Se nel frattempo la riga e'
    nata (vincolo unico), 409 col valore nuovo: non un 500, non una sovrascrittura."""
    try:
        sb.table(tabella).insert(riga).execute()
    except Exception as exc:
        _, attuale = rileggi()
        if attuale is not None:
            raise _conflitto("valore_cambiato", attuale)
        logger.error("assistente/registra: insert %s fallito: %s", tabella, exc)
        raise HTTPException(status_code=500, detail="Registrazione non riuscita")


def _registra_incasso(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    giorno = valida_giorno(body.data, _oggi())
    valori = valida_importi_incasso(body, TETTO_INCASSO_GIORNO)
    _, a_totale = leggi_mese_a_totale(sb, rid, giorno.year, giorno.month)
    if a_totale is not None:
        raise _conflitto("mese_a_totale")
    riga_id, attuale = leggi_incasso_giorno(sb, rid, giorno)
    if not _uguali(body.precedente, attuale):
        raise _conflitto("valore_cambiato", attuale)
    if riga_id:
        sb.table("ricavi_giornalieri").update(
            {**valori, "source": "manuale", "updated_at": _adesso()}
        ).eq("id", riga_id).eq("ristorante_id", rid).execute()
    else:
        _inserisci_o_409(
            sb, "ricavi_giornalieri",
            {"user_id": str(user["id"]), "ristorante_id": rid, "data": giorno.isoformat(),
             **valori, "source": "manuale"},
            lambda: leggi_incasso_giorno(sb, rid, giorno),
        )
    return {"data": giorno.isoformat(), **valori}


def _registra_fatturato_mese(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    anno, mese = valida_mese(body.anno, body.mese, _oggi())
    valori = valida_importi_incasso(body, TETTO_FATTURATO_MESE)
    riga_id, attuale = leggi_mese_a_totale(sb, rid, anno, mese)
    if attuale is None and mese_ha_giorni(sb, rid, anno, mese):
        raise _conflitto("mese_con_giorni")
    if not _uguali(body.precedente, attuale):
        raise _conflitto("valore_cambiato", attuale)
    if riga_id:
        sb.table("ricavi_modalita_mensile").update(
            {**valori, "modalita": "mensile", "updated_at": _adesso()}
        ).eq("id", riga_id).eq("ristorante_id", rid).execute()
    else:
        _inserisci_o_409(
            sb, "ricavi_modalita_mensile",
            {"ristorante_id": rid, "anno": anno, "mese": mese, "modalita": "mensile", **valori},
            lambda: leggi_mese_a_totale(sb, rid, anno, mese),
        )
    return {"anno": anno, "mese": mese, **valori}


def _registra_personale(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    anno, mese = valida_mese(body.anno, body.mese, _oggi())
    valore = valida_personale(body)
    riga_id, attuale = leggi_personale(sb, rid, anno, mese)
    if not _uguali(body.precedente, attuale):
        raise _conflitto("valore_cambiato", attuale)
    if riga_id:
        sb.table("margini_mensili").update(
            {"costo_dipendenti": valore, "updated_at": _adesso()}
        ).eq("id", riga_id).eq("ristorante_id", rid).execute()
    else:
        _inserisci_o_409(
            sb, "margini_mensili",
            {"user_id": str(user["id"]), "ristorante_id": rid, "anno": anno, "mese": mese,
             "costo_dipendenti": valore},
            lambda: leggi_personale(sb, rid, anno, mese),
        )
    return {"anno": anno, "mese": mese, "costo_dipendenti": valore}


_REGISTRA = {
    "incasso_giorno": _registra_incasso,
    "fatturato_mese": _registra_fatturato_mese,
    "personale_mese": _registra_personale,
}


def _invalida(user_id: str, rid: str, sb) -> None:
    """Come gli endpoint dei form, piu' la campanella (`_LIVE_SEGNALI_CACHE`),
    che i form non toccano: dopo una conferma il «manca l'incasso» deve sparire."""
    try:
        _fw()._invalidate_home_kpi_cache(rid)
    except Exception as exc:
        logger.warning("assistente/registra: invalidazione KPI fallita: %s", exc)
    try:
        from services.daily_briefing_service import invalidate_today_briefing
        invalidate_today_briefing(user_id, rid, sb)
    except Exception as exc:
        logger.warning("assistente/registra: invalidazione briefing fallita: %s", exc)
    try:
        _fw()._LIVE_SEGNALI_CACHE.pop(rid, None)
    except Exception as exc:
        logger.warning("assistente/registra: invalidazione segnali fallita: %s", exc)


@router.post("/api/assistente/registra", response_model=RegistraResponse, tags=["Assistente"],
             dependencies=[Depends(_verify_worker_key)])
def assistente_registra(body: RegistraRequest, authorization: Optional[str] = Header(None)):
    user = _resolve_user_from_token(authorization)
    if not _su.ha_pagina(user, PAGINA_RICHIESTA):
        raise HTTPException(status_code=403, detail="Pagina non consentita per questo utente")
    sb = _get_supabase_client()
    rid = sede_scrivibile(user, sb, body.ristorante_id)
    valori = _REGISTRA[body.tipo](sb, user, rid, body)
    _invalida(str(user["id"]), rid, sb)
    logger.info("assistente/registra: %s registrato su sede %s (utente %s)", body.tipo, rid, user["id"])
    return RegistraResponse(ok=True, tipo=body.tipo, ristorante_id=rid, valori=valori)
