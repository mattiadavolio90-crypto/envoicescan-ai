"""La «Conferma» delle cifre dettate all'assistente (fase 3, M4).

Il modello non scrive mai: propone una card (incasso di un giorno, personale di
un mese, fatturato di un mese, una spesa extra) e la scrittura parte solo da qui, quando il
cliente preme Conferma. Per questo l'endpoint non si fida di niente di cio' che
arriva: la sede della proposta si riverifica (dell'account, attiva, non tecnica,
fra quelle del sotto-utente, con la pagina del tipo: Margini, o Agenda per la
spesa), i valori si rivalidano, e
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
from typing import Any, Dict, Literal, NamedTuple, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config.constants import (
    CATEGORIE_FOOD_BEVERAGE,
    CATEGORIE_SPESE_GENERALI,
    SETTORE_RETAIL,
)
from config.logger_setup import get_logger
from services import sotto_utenti_service as _su
from services.routers.workspace import _tipo_da_categoria, _valida_categoria_spesa

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
# Spesa extra: la piu' alta sul live il 4/10/2026 era 1.306 €.
TETTO_SPESA = 50_000.0
# Le categorie di una spesa extra, nell'ordine del form dell'Agenda.
CATEGORIE_SPESA = tuple(CATEGORIE_FOOD_BEVERAGE) + tuple(CATEGORIE_SPESE_GENERALI)
DESCRIZIONE_MAX = 200
GIORNI_INDIETRO_INCASSO = 60
MESI_INDIETRO = 12  # il mese corrente e i 12 prima

CAMPI_INCASSO = ("fatturato_iva10", "altri_ricavi_noiva", "fatturato_iva22")
# Le tre voci del personale di Margini (fase C): lordo, ore extra, chiamata.
CAMPI_PERSONALE = ("costo_dipendenti", "costo_personale_extra", "costo_personale_chiamata")
# La spesa extra si scrive dall'Agenda (`/api/workspace/spese`): chi non la vede
# non la registra nemmeno dalla chat.
PAGINA_PER_TIPO = {
    "incasso_giorno": "margini",
    "personale_mese": "margini",
    "fatturato_mese": "margini",
    "spesa_extra": "agenda",
}
_TOLLERANZA = 0.005


TipoRegistra = Literal["incasso_giorno", "personale_mese", "fatturato_mese", "spesa_extra"]


class RegistraRequest(BaseModel):
    tipo: TipoRegistra
    ristorante_id: str
    data: Optional[str] = None
    anno: Optional[int] = None
    mese: Optional[int] = None
    fatturato_iva10: float = 0.0
    altri_ricavi_noiva: float = 0.0
    fatturato_iva22: float = 0.0
    # Personale: le voci dettate; None = non dettata, resta com'e'.
    costo_dipendenti: Optional[float] = None
    costo_personale_extra: Optional[float] = None
    costo_personale_chiamata: Optional[float] = None
    # Il valore mostrato sulla card come «risulta …»; None = nessun valore.
    precedente: Optional[Dict[str, float]] = None
    # Spesa extra: `importo` com'e' stato pagato, IVA compresa (Mattia, 5/10: una
    # spesa senza fattura non scarica l'IVA, che e' costo). `id_proposta` diventa
    # l'id della riga: una Conferma ripetuta non scrive una seconda spesa.
    categoria: Optional[str] = None
    descrizione: Optional[str] = None
    importo: Optional[float] = None
    id_proposta: Optional[str] = None


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


def valida_personale(body: RegistraRequest) -> Dict[str, float]:
    """Le voci dettate, le sole che si scrivono. Uno zero vale «non detta»: un
    modello che passa 0 per la voce che il cliente non ha nominato non deve
    cancellarla (azzerare una voce si fa dal modulo di Margini)."""
    valori = {c: _importo(c, getattr(body, c)) for c in CAMPI_PERSONALE if getattr(body, c) is not None}
    dettato = {c: v for c, v in valori.items() if v > 0}
    if not dettato:
        raise HTTPException(status_code=400, detail="L'importo deve essere maggiore di zero")
    if sum(dettato.values()) > TETTO_PERSONALE_MESE:
        raise HTTPException(status_code=400, detail="Importo fuori scala: controlla la cifra")
    return dettato


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


def valida_giorno_spesa(testo: Optional[str], oggi: date) -> date:
    try:
        giorno = date.fromisoformat(str(testo or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida")
    if giorno > oggi:
        raise HTTPException(status_code=400, detail="Non si registra una spesa nel futuro")
    indice = oggi.year * 12 + (oggi.month - 1) - MESI_INDIETRO
    if giorno < date(indice // 12, indice % 12 + 1, 1):
        raise HTTPException(status_code=400, detail="Data troppo lontana: usa l'Agenda")
    return giorno


def valida_spesa(body: RegistraRequest, oggi: date) -> Dict[str, Any]:
    """La riga di `spese_extra` che la Conferma inserisce, con le regole del form
    dell'Agenda (`ws_spese_crea`): categoria ammessa e tipo derivato da lei,
    descrizione obbligatoria, importo salvato com'e' stato pagato."""
    giorno = valida_giorno_spesa(body.data, oggi)
    categoria = _valida_categoria_spesa(body.categoria or "")
    descrizione = (body.descrizione or "").strip()
    if not descrizione:
        raise HTTPException(status_code=400, detail="Manca la descrizione della spesa")
    if len(descrizione) > DESCRIZIONE_MAX:
        raise HTTPException(status_code=400, detail="Descrizione troppo lunga")
    detto = _importo("importo", body.importo)
    if detto <= 0:
        raise HTTPException(status_code=400, detail="L'importo deve essere maggiore di zero")
    if detto > TETTO_SPESA:
        raise HTTPException(status_code=400, detail="Importo fuori scala: controlla la cifra")
    try:
        id_riga = str(uuid.UUID(str(body.id_proposta)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Proposta non valida")
    return {"id": id_riga, "data_spesa": giorno.isoformat(), "tipo": _tipo_da_categoria(categoria),
            "categoria": categoria, "descrizione": descrizione, "importo": detto}


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
# «risulta …» esattamente `attuale`, cioe' cio' che qui si confronta. None =
# niente da mostrare (riga assente o importi tutti a zero), e la card dice
# «nessun valore». `grezzo` sono i valori letti cosi' come stanno nel DB: l'update
# li rimette come condizione, e se nel frattempo sono cambiati non scrive.
class Letto(NamedTuple):
    id: Optional[str]
    attuale: Optional[Dict[str, float]]
    grezzo: Dict[str, Any]
    fonte: Optional[str] = None
    info: Optional[Dict[str, float]] = None


def _num(v: Any) -> float:
    return round(float(v or 0), 2)


def _importi_o_none(riga: Dict[str, Any]) -> Optional[Dict[str, float]]:
    valori = {c: _num(riga.get(c)) for c in CAMPI_INCASSO}
    return valori if sum(valori.values()) > 0 else None


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


def leggi_incasso_giorno(sb, rid: str, giorno: date) -> Letto:
    resp = (
        sb.table("ricavi_giornalieri")
        .select("id, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva")
        .eq("ristorante_id", rid)
        .eq("data", giorno.isoformat())
        .limit(1)
        .execute()
    )
    if not resp.data:
        return Letto(None, None, {})
    riga = resp.data[0]
    return Letto(str(riga["id"]), _importi_o_none(riga), {c: riga.get(c) for c in CAMPI_INCASSO})


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


def leggi_fatturato_mese(sb, rid: str, anno: int, mese: int) -> Letto:
    """Il fatturato del mese dalle sue tre fonti, nell'ordine in cui le legge la
    pagina Margini (`_merge_override_mensile`):
    - `mensile`: il totale in `ricavi_modalita_mensile` (vince su tutto);
    - `giorni`: gli incassi giornalieri (il trigger li somma in `margini_mensili`);
    - `margini`: il fatturato scritto a mano in `margini_mensili` senza giorni
      (`POST /api/margini`; TIME CAFE e CASATI 14 al 29/9).
    `id` e `grezzo` sono della riga di `ricavi_modalita_mensile`, l'unica che si
    scrive: la card mostra comunque cio' che il cliente vede in Margini.
    """
    resp = (
        sb.table("ricavi_modalita_mensile")
        .select("id, modalita, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva")
        .eq("ristorante_id", rid)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    riga = resp.data[0] if resp.data else None
    if riga is None:
        mod_id, grezzo = None, {}
    else:
        mod_id, grezzo = str(riga["id"]), {"modalita": riga.get("modalita")}
    if riga is not None and riga.get("modalita") == "mensile":
        grezzo.update({c: riga.get(c) for c in CAMPI_INCASSO})
        return Letto(mod_id, _importi_o_none(riga), grezzo, fonte="mensile")
    if mese_ha_giorni(sb, rid, anno, mese):
        return Letto(mod_id, None, grezzo, fonte="giorni")
    mm = (
        sb.table("margini_mensili")
        .select("fatturato_iva10, fatturato_iva22, altri_ricavi_noiva")
        .eq("ristorante_id", rid)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    a_mano = _importi_o_none(mm.data[0]) if mm.data else None
    return Letto(mod_id, a_mano, grezzo, fonte="margini" if a_mano else None)


def leggi_personale(sb, rid: str, anno: int, mese: int,
                    campi: Tuple[str, ...] = ("costo_dipendenti",)) -> Letto:
    """`attuale` e `grezzo` sulle sole voci dettate (`campi`): l'update si
    condiziona a quelle, e una voce non dettata cambiata nel frattempo non e' un
    conflitto. `info` porta tutte e tre le voci, per il «restano» della card."""
    resp = (
        sb.table("margini_mensili")
        .select("id, costo_dipendenti, costo_personale_extra, costo_personale_chiamata")
        .eq("ristorante_id", rid)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return Letto(None, None, {})
    riga = resp.data[0]
    # La riga del mese nasce col trigger dei ricavi e le voci hanno default 0:
    # zero vuol dire «non registrato», come per l'avviso del briefing.
    valori = {c: _num(riga.get(c)) for c in campi}
    return Letto(
        str(riga["id"]),
        valori if sum(valori.values()) > 0 else None,
        {c: riga.get(c) for c in campi},
        info={c: _num(riga.get(c)) for c in CAMPI_PERSONALE},
    )


# ─── Scritture ────────────────────────────────────────────────────────────────
def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gia_registrato(rileggi, dettato: Dict[str, float]) -> Letto:
    """Dopo una scrittura non andata a buon fine: se il DB ha gia' il dettato (la
    risposta di una scrittura riuscita si e' persa, o qualcuno ha scritto la stessa
    cifra) e' un successo, non un conflitto del cliente con se stesso."""
    letto = rileggi()
    if letto.attuale is not None and _uguali(dettato, {k: letto.attuale.get(k) for k in dettato}):
        return letto
    raise _conflitto("valore_cambiato", letto.attuale) if letto.id else HTTPException(
        status_code=500, detail="Registrazione non riuscita"
    )


def _inserisci(sb, tabella: str, riga: Dict[str, Any], dettato: Dict[str, float], rileggi) -> None:
    """Insert quando la card diceva «nessun valore». Se nel frattempo la riga e'
    nata (vincolo unico), 409 col valore nuovo: non un 500, non una sovrascrittura."""
    try:
        sb.table(tabella).insert(riga).execute()
    except Exception as exc:
        logger.warning("assistente/registra: insert %s non riuscito: %s", tabella, exc)
        _gia_registrato(rileggi, dettato)


def _aggiorna(sb, tabella: str, letto: Letto, rid: str, payload: Dict[str, Any],
              dettato: Dict[str, float], rileggi) -> None:
    """Update condizionato ai valori letti: se fra la lettura e la scrittura e'
    arrivata un'email di cassa o un'altra conferma, nessuna riga combacia e si
    risponde 409 invece di far vincere l'ultima scrittura."""
    q = sb.table(tabella).update(payload).eq("id", letto.id).eq("ristorante_id", rid)
    for col, val in letto.grezzo.items():
        q = q.is_(col, "null") if val is None else q.eq(col, val)
    if not q.execute().data:
        _gia_registrato(rileggi, dettato)


def _registra_incasso(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    giorno = valida_giorno(body.data, _oggi())
    valori = valida_importi_incasso(body, TETTO_INCASSO_GIORNO)
    # Un giorno su un mese tenuto a totale (override, o fatturato scritto a mano
    # senza giorni) spegnerebbe il totale: il trigger rifa' il mese coi soli giorni.
    if leggi_fatturato_mese(sb, rid, giorno.year, giorno.month).fonte in ("mensile", "margini"):
        raise _conflitto("mese_a_totale")
    letto = leggi_incasso_giorno(sb, rid, giorno)
    if not _uguali(body.precedente, letto.attuale):
        raise _conflitto("valore_cambiato", letto.attuale)
    rileggi = lambda: leggi_incasso_giorno(sb, rid, giorno)  # noqa: E731
    if letto.id:
        _aggiorna(sb, "ricavi_giornalieri", letto, rid,
                  {**valori, "source": "manuale", "updated_at": _adesso()}, valori, rileggi)
    else:
        _inserisci(sb, "ricavi_giornalieri",
                   {"user_id": str(user["id"]), "ristorante_id": rid, "data": giorno.isoformat(),
                    **valori, "source": "manuale"}, valori, rileggi)
    return {"data": giorno.isoformat(), **valori}


def _registra_fatturato_mese(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    anno, mese = valida_mese(body.anno, body.mese, _oggi())
    valori = valida_importi_incasso(body, TETTO_FATTURATO_MESE)
    letto = leggi_fatturato_mese(sb, rid, anno, mese)
    if letto.fonte == "giorni":
        raise _conflitto("mese_con_giorni")
    if not _uguali(body.precedente, letto.attuale):
        raise _conflitto("valore_cambiato", letto.attuale)
    rileggi = lambda: leggi_fatturato_mese(sb, rid, anno, mese)  # noqa: E731
    if letto.id:
        _aggiorna(sb, "ricavi_modalita_mensile", letto, rid,
                  {**valori, "modalita": "mensile", "updated_at": _adesso()}, valori, rileggi)
    else:
        _inserisci(sb, "ricavi_modalita_mensile",
                   {"ristorante_id": rid, "anno": anno, "mese": mese, "modalita": "mensile", **valori},
                   valori, rileggi)
    return {"anno": anno, "mese": mese, **valori}


# Il client dichiara sempre le tre voci (None = non dettata). Il JavaScript di
# prima della fase D2, in una scheda aperta da prima del deploy, manda il solo
# lordo: scriverebbe quello, e la sua card direbbe che le ore extra dettate
# «restano». Meglio un «ricarica» che una voce persa in silenzio.
_RICARICA = "Ricarica la pagina e dettami di nuovo il personale"


def _registra_personale(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    if not set(CAMPI_PERSONALE) <= body.model_fields_set:
        raise HTTPException(status_code=400, detail=_RICARICA)
    anno, mese = valida_mese(body.anno, body.mese, _oggi())
    dettato = valida_personale(body)
    campi = tuple(dettato)
    letto = leggi_personale(sb, rid, anno, mese, campi)
    if not _uguali(body.precedente, letto.attuale):
        raise _conflitto("valore_cambiato", letto.attuale)
    rileggi = lambda: leggi_personale(sb, rid, anno, mese, campi)  # noqa: E731
    if letto.id:
        _aggiorna(sb, "margini_mensili", letto, rid,
                  {**dettato, "updated_at": _adesso()}, dettato, rileggi)
    else:
        _inserisci(sb, "margini_mensili",
                   {"user_id": str(user["id"]), "ristorante_id": rid, "anno": anno, "mese": mese,
                    **dettato}, dettato, rileggi)
    return {"anno": anno, "mese": mese, **dettato}


def _registra_spesa(sb, user, rid: str, body: RegistraRequest) -> Dict[str, Any]:
    """Una spesa si aggiunge, non sostituisce niente: non c'e' un «risulta …» da
    confrontare. Il doppione lo evita l'id della proposta: se l'insert fallisce
    perche' la riga c'e' gia' (Conferma ripetuta, risposta persa) e' la stessa
    spesa, ed e' un successo."""
    riga = valida_spesa(body, _oggi())
    try:
        sb.table("spese_extra").insert(
            {**riga, "ristorante_id": rid, "user_id": str(user["id"])}
        ).execute()
    except Exception as exc:
        logger.warning("assistente/registra: insert spese_extra non riuscito: %s", exc)
        gia = (
            sb.table("spese_extra")
            .select("id, importo")
            .eq("id", riga["id"])
            .eq("ristorante_id", rid)
            .limit(1)
            .execute()
        )
        if not gia.data or abs(_num(gia.data[0].get("importo")) - riga["importo"]) >= _TOLLERANZA:
            raise HTTPException(status_code=500, detail="Registrazione non riuscita")
    return {k: riga[k] for k in ("data_spesa", "tipo", "categoria", "descrizione", "importo")}


_REGISTRA = {
    "incasso_giorno": _registra_incasso,
    "fatturato_mese": _registra_fatturato_mese,
    "personale_mese": _registra_personale,
    "spesa_extra": _registra_spesa,
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
    if not _su.ha_pagina(user, PAGINA_PER_TIPO[body.tipo]):
        raise HTTPException(status_code=403, detail="Pagina non consentita per questo utente")
    sb = _get_supabase_client()
    rid = sede_scrivibile(user, sb, body.ristorante_id)
    valori = _REGISTRA[body.tipo](sb, user, rid, body)
    _invalida(str(user["id"]), rid, sb)
    logger.info("assistente/registra: %s registrato su sede %s (utente %s)", body.tipo, rid, user["id"])
    return RegistraResponse(ok=True, tipo=body.tipo, ristorante_id=rid, valori=valori)


# ─── Le proposte (step 2): cosa prepara lo strumento della chat ───────────────
# Il modello chiama `proponi_*` con le cifre dettate; qui si validano con le
# stesse regole della Conferma e si legge il valore attuale con le stesse letture,
# cosi' la card non propone mai cio' che la Conferma rifiuterebbe. Niente si
# scrive: la proposta torna al cliente nella risposta della chat.
STRUMENTI_PROPOSTA = ("proponi_incasso", "proponi_personale", "proponi_fatturato_mese", "proponi_spesa")
MAX_PROPOSTE = 3

_MESI = ("", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
         "agosto", "settembre", "ottobre", "novembre", "dicembre")


class PropostaCifra(BaseModel):
    """Una card con Conferma. I campi sono il corpo di POST /api/assistente/registra
    (il frontend lo rimanda cosi' com'e'); `sede_nome`, `restano` e `doppione`
    servono solo a scrivere la card. `restano`: le voci del personale
    gia' registrate e non dettate."""
    tipo: TipoRegistra
    ristorante_id: str
    sede_nome: Optional[str] = None
    data: Optional[str] = None
    anno: Optional[int] = None
    mese: Optional[int] = None
    fatturato_iva10: float = 0.0
    altri_ricavi_noiva: float = 0.0
    fatturato_iva22: float = 0.0
    costo_dipendenti: Optional[float] = None
    precedente: Optional[Dict[str, float]] = None
    costo_personale_extra: Optional[float] = None
    costo_personale_chiamata: Optional[float] = None
    restano: Optional[Dict[str, float]] = None
    categoria: Optional[str] = None
    descrizione: Optional[str] = None
    importo: Optional[float] = None
    id_proposta: Optional[str] = None
    doppione: bool = False


def chiave_proposta(p: PropostaCifra) -> Tuple[str, Any]:
    """Due proposte sulla stessa cifra nella stessa risposta: vale l'ultima. Due
    spese diverse nello stesso giorno sono due card."""
    if p.tipo == "spesa_extra":
        return (p.tipo, (p.data, p.categoria, (p.descrizione or "").lower(), p.importo))
    return (p.tipo, p.data if p.tipo == "incasso_giorno" else (p.anno, p.mese))


def _numero(args: Dict[str, Any], nome: str) -> Optional[float]:
    v = args.get(nome)
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _intero(args: Dict[str, Any], nome: str) -> Optional[int]:
    v = _numero(args, nome)
    return int(v) if v is not None and math.isfinite(v) and v == int(v) else None


_PRONTA = (
    "Sotto la tua risposta il cliente vede una card con il pulsante Conferma: la cifra "
    "si registra SOLO quando la preme. Non dire che e' registrata. Riepiloga in una "
    "riga cosa stai per registrare e digli di premere Conferma."
)


def proponi(nome: str, args: Dict[str, Any], *, user: Dict[str, Any], sb,
            ristorante_id: Optional[str], sede_nome: Optional[str],
            settore: Optional[str] = None) -> Tuple[Optional[PropostaCifra], Dict[str, Any]]:
    """(proposta o None, cio' che legge il modello)."""
    # La pagina Margini non si ricontrolla qui: senza, lo strumento non e' offerto
    # e chat_ai rifiuta cio' che non ha offerto. La sede si': la sede attiva di una
    # sessione puo' essere stata spenta, e una card che la Conferma rifiuterebbe
    # e' una promessa falsa.
    try:
        rid = sede_scrivibile(user, sb, ristorante_id or "")
        oggi = _oggi()
        if nome == "proponi_incasso":
            return _proponi_incasso(args, sb, rid, sede_nome, oggi, settore)
        if nome == "proponi_fatturato_mese":
            return _proponi_fatturato_mese(args, sb, rid, sede_nome, oggi, settore)
        if nome == "proponi_personale":
            return _proponi_personale(args, sb, rid, sede_nome, oggi)
        if nome == "proponi_spesa":
            return _proponi_spesa(args, sb, rid, sede_nome, oggi)
        return None, {"errore": f"strumento sconosciuto: {nome}"}
    except HTTPException as exc:
        motivo = exc.detail if isinstance(exc.detail, str) else "richiesta non valida"
        return None, {"errore": motivo}
    except Exception as exc:
        # Una lettura fallita non fa cadere la chat (la domanda e' gia' contata).
        logger.warning("proposta %s non preparata: %s", nome, exc)
        return None, {"errore": "non sono riuscito a leggere i dati: la cifra non e' pronta, "
                                "di' al cliente di riprovare fra poco"}


def _importi_dettati(args: Dict[str, Any], settore: Optional[str]) -> Tuple[Optional[Dict[str, float]], Dict[str, Any]]:
    """(importi, None) oppure (None, cio' che legge il modello). Gli incassi hanno
    solo 10%, 22% e senza IVA (Mattia, 5/10/2026)."""
    # «2.340» come stringa diventerebbe 2,34: il punto delle migliaia non si indovina.
    if any(isinstance(args.get(k), str) for k in ("iva10", "senza_iva", "iva22")):
        return None, _IMPORTO_IN_TESTO
    iva10, senza_iva = _numero(args, "iva10"), _numero(args, "senza_iva")
    if iva10 is None or senza_iva is None:
        return None, _chiedi_divisione(settore)
    return {"fatturato_iva10": iva10, "altri_ricavi_noiva": senza_iva,
            "fatturato_iva22": _numero(args, "iva22") or 0.0}, {}


_IMPORTO_IN_TESTO = {
    "errore": "importo passato come testo",
    "cosa_fare": "Ripeti la chiamata con gli importi come numeri: 2340, non \"2.340\".",
}


def _chiedi_divisione(settore: Optional[str]) -> Dict[str, str]:
    if settore == SETTORE_RETAIL:
        come = "quanto e' al 22%, quanto al 10% e quanto senza IVA"
    else:
        come = "quanto e' al 10% e quanto senza IVA (il 22% solo se lo dice lui)"
    return {"errore": "divisione IVA mancante",
            "cosa_fare": f"Chiedi al cliente {come}. Non dividere tu il totale."}


def _gia_cosi(attuale: Optional[Dict[str, float]], dettato: Dict[str, float]) -> bool:
    return attuale is not None and _uguali(dettato, {k: attuale.get(k) for k in dettato})


def _proponi_incasso(args, sb, rid, sede_nome, oggi, settore):
    importi, errore = _importi_dettati(args, settore)
    if importi is None:
        return None, errore
    giorno = valida_giorno(args.get("data"), oggi)
    corpo = RegistraRequest(tipo="incasso_giorno", ristorante_id=rid, data=giorno.isoformat(), **importi)
    valori = valida_importi_incasso(corpo, TETTO_INCASSO_GIORNO)
    if leggi_fatturato_mese(sb, rid, giorno.year, giorno.month).fonte in ("mensile", "margini"):
        return None, {"errore": (f"{_MESI[giorno.month]} {giorno.year} e' tenuto come totale del mese: "
                                 "non si registra il singolo giorno. Se il cliente vuole, puo' "
                                 "dettarti il nuovo totale del mese.")}
    attuale = leggi_incasso_giorno(sb, rid, giorno).attuale
    if _gia_cosi(attuale, valori):
        return None, {"gia_registrato": True, "valore_attuale": attuale}
    proposta = PropostaCifra(tipo="incasso_giorno", ristorante_id=rid, sede_nome=sede_nome,
                             data=giorno.isoformat(), precedente=attuale, **valori)
    return proposta, {"proposta_pronta": True, "giorno": giorno.isoformat(), **valori,
                      "valore_attuale": attuale or "nessun valore", "istruzione": _PRONTA}


def _proponi_fatturato_mese(args, sb, rid, sede_nome, oggi, settore):
    importi, errore = _importi_dettati(args, settore)
    if importi is None:
        return None, errore
    anno, mese = valida_mese(_intero(args, "anno"), _intero(args, "mese"), oggi)
    corpo = RegistraRequest(tipo="fatturato_mese", ristorante_id=rid, anno=anno, mese=mese, **importi)
    valori = valida_importi_incasso(corpo, TETTO_FATTURATO_MESE)
    letto = leggi_fatturato_mese(sb, rid, anno, mese)
    if letto.fonte == "giorni":
        return None, {"errore": (f"{_MESI[mese]} {anno} ha gia' incassi giorno per giorno: il fatturato "
                                 "del mese e' la loro somma. Si puo' registrare l'incasso di un "
                                 "giorno, non il totale del mese.")}
    if _gia_cosi(letto.attuale, valori):
        return None, {"gia_registrato": True, "valore_attuale": letto.attuale}
    proposta = PropostaCifra(tipo="fatturato_mese", ristorante_id=rid, sede_nome=sede_nome,
                             anno=anno, mese=mese, precedente=letto.attuale, **valori)
    return proposta, {"proposta_pronta": True, "mese": f"{_MESI[mese]} {anno}", **valori,
                      "valore_attuale": letto.attuale or "nessun valore", "istruzione": _PRONTA}


# Gli argomenti dello strumento → le voci di Margini. Il modello legge i nomi
# dello strumento, non quelli delle colonne.
VOCI_PERSONALE = {"importo": "costo_dipendenti", "ore_extra": "costo_personale_extra",
                  "chiamata": "costo_personale_chiamata"}
_NOME_VOCE = {"costo_dipendenti": "lordo", "costo_personale_extra": "ore_extra",
              "costo_personale_chiamata": "chiamata"}


def _voci_in_chiaro(valori: Optional[Dict[str, float]]) -> Any:
    return {_NOME_VOCE[c]: v for c, v in valori.items()} if valori else "nessun valore"


def _proponi_personale(args, sb, rid, sede_nome, oggi):
    if any(isinstance(args.get(a), str) for a in VOCI_PERSONALE):
        return None, _IMPORTO_IN_TESTO
    anno, mese = valida_mese(_intero(args, "anno"), _intero(args, "mese"), oggi)
    corpo = RegistraRequest(tipo="personale_mese", ristorante_id=rid, anno=anno, mese=mese,
                            **{col: _numero(args, a) for a, col in VOCI_PERSONALE.items()})
    dettato = valida_personale(corpo)
    letto = leggi_personale(sb, rid, anno, mese, tuple(dettato))
    if _gia_cosi(letto.attuale, dettato):
        return None, {"gia_registrato": True, "valore_attuale": _voci_in_chiaro(letto.attuale)}
    restano = {c: v for c, v in (letto.info or {}).items() if c not in dettato and v > 0} or None
    proposta = PropostaCifra(tipo="personale_mese", ristorante_id=rid, sede_nome=sede_nome,
                             anno=anno, mese=mese, precedente=letto.attuale, restano=restano, **dettato)
    al_modello = {"proposta_pronta": True, "mese": f"{_MESI[mese]} {anno}",
                  "si_registra": _voci_in_chiaro(dettato),
                  "valore_attuale": _voci_in_chiaro(letto.attuale), "istruzione": _PRONTA}
    if restano:
        al_modello["restano_gia_registrate"] = _voci_in_chiaro(restano)
    return proposta, al_modello


_PRONTA_SPESA = (
    _PRONTA + " Digli anche che la spesa va nelle Spese dell'Agenda e che nel MOL entra "
    "quando in Margini preme «Recupera dal tab Spese»."
)


def _proponi_spesa(args, sb, rid, sede_nome, oggi):
    if isinstance(args.get("importo"), str):
        return None, _IMPORTO_IN_TESTO
    corpo = RegistraRequest(
        tipo="spesa_extra", ristorante_id=rid, data=args.get("data"),
        categoria=str(args.get("categoria") or "").strip().upper(),
        descrizione=args.get("descrizione"), importo=_numero(args, "importo"),
        id_proposta=str(uuid.uuid4()),
    )
    riga = valida_spesa(corpo, oggi)
    simili = (
        sb.table("spese_extra")
        .select("id")
        .eq("ristorante_id", rid)
        .eq("data_spesa", riga["data_spesa"])
        .eq("categoria", riga["categoria"])
        .eq("importo", riga["importo"])
        .limit(1)
        .execute()
    )
    doppione = bool(simili.data)
    proposta = PropostaCifra(
        tipo="spesa_extra", ristorante_id=rid, sede_nome=sede_nome, data=riga["data_spesa"],
        categoria=riga["categoria"], descrizione=riga["descrizione"], importo=corpo.importo,
        id_proposta=riga["id"], doppione=doppione,
    )
    al_modello = {"proposta_pronta": True, "giorno": riga["data_spesa"], "descrizione": riga["descrizione"],
                  "categoria": riga["categoria"], "si_registra": riga["importo"],
                  "istruzione": _PRONTA_SPESA}
    if doppione:
        al_modello["attenzione"] = ("c'e' gia' una spesa uguale in questo giorno: confermando se ne "
                                    "aggiunge un'altra. Diglielo.")
    return proposta, al_modello
