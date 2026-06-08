"""Router dominio SCADENZIARIO — pagamenti, scadenze, regole fornitore, notifiche.

Estratto da fastapi_worker.py. Include anche /api/ricavi/notifica-mancante, che
era fisicamente in questa sezione (path e tag invariati). Gli helper condivisi
sono importati dal worker.
"""
from typing import Dict, List, Optional

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


def _oggi_rome(*args, **kwargs):
    return _fw()._oggi_rome(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)

router = APIRouter()


class PagataRequest(BaseModel):
    file_origini: List[str]
    pagata: bool = True


class ScadenzaOverrideRequest(BaseModel):
    file_origine: str
    scadenza_override: Optional[str] = None


class FornitoreRegolaRequest(BaseModel):
    piva_fornitore: str
    modalita: str
    note: Optional[str] = None


@router.get("/api/scadenziario", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def get_scadenziario(authorization: Optional[str] = Header(None)):
    from services.documenti_service import get_documenti_scadenziario
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    documenti = get_documenti_scadenziario(str(user["id"]), ristorante_id)
    return {"documenti": documenti}


@router.get("/api/scadenziario/calendario", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def get_scadenziario_calendario(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
):
    from services.documenti_service import get_documenti_scadenziario
    import calendar as _cal
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    docs = get_documenti_scadenziario(str(user["id"]), ristorante_id)
    _, last_day = _cal.monthrange(anno, mese)
    agg: Dict[int, float] = {}
    for doc in docs:
        if doc.get("pagata"):
            continue
        scad = doc.get("scadenza_effettiva")
        if not scad:
            continue
        try:
            import pandas as _pd
            dt = _pd.to_datetime(scad, errors="coerce")
            if _pd.isna(dt):
                continue
            if dt.year == anno and dt.month == mese:
                day = int(dt.day)
                agg[day] = agg.get(day, 0.0) + float(doc.get("totale_documento") or 0)
        except Exception:
            continue

    return {
        "anno": anno,
        "mese": mese,
        "giorni": [
            {"giorno": g, "totale": round(agg.get(g, 0.0), 2)}
            for g in range(1, last_day + 1)
        ],
        "totale_mese": round(sum(agg.values()), 2),
    }


@router.post("/api/scadenziario/pagata", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def segna_pagata_endpoint(body: PagataRequest, authorization: Optional[str] = Header(None)):
    from services.documenti_service import segna_fattura_pagata
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    results = []
    for fo in body.file_origini:
        r = segna_fattura_pagata(
            file_origine=fo,
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
            pagata=body.pagata,
        )
        results.append({"file_origine": fo, **r})

    ok_count = sum(1 for r in results if r.get("success"))
    return {"ok": ok_count == len(results), "aggiornate": ok_count, "dettaglio": results}


@router.post("/api/scadenziario/scadenza", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def set_scadenza_override_endpoint(
    body: ScadenzaOverrideRequest, authorization: Optional[str] = Header(None)
):
    from services.documenti_service import set_scadenza_override
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    file_origine = str(body.file_origine or "").strip()
    if not file_origine:
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    result = set_scadenza_override(
        file_origine=file_origine,
        user_id=str(user["id"]),
        ristorante_id=ristorante_id,
        scadenza_override=body.scadenza_override or None,
    )

    if not result.get("ok"):
        status = 404 if "trovato" in str(result.get("error", "")).lower() else 400
        raise HTTPException(status_code=status, detail=result.get("error"))

    return result


@router.get("/api/scadenziario/anteprima", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def get_anteprima_fattura(file_origine: str, authorization: Optional[str] = Header(None)):
    """Righe di una fattura specifica per anteprima nello scadenziario."""
    from services.db_service import filter_active as _fa
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if not file_origine or not str(file_origine).strip():
        raise HTTPException(status_code=400, detail="file_origine obbligatorio")

    resp = (
        _fa(
            sb.table("fatture")
            .select("numero_riga,descrizione,quantita,unita_misura,prezzo_unitario,iva_percentuale,totale_riga,categoria")
            .eq("user_id", str(user["id"]))
            .eq("ristorante_id", ristorante_id)
            .eq("file_origine", str(file_origine).strip())
        )
        .order("numero_riga", desc=False)
        .execute()
    )

    return {"righe": resp.data or [], "file_origine": file_origine, "count": len(resp.data or [])}


@router.get("/api/scadenziario/fornitori", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def get_fornitori_scadenziario(authorization: Optional[str] = Header(None)):
    """
    Restituisce lista fornitori unici per lo scadenziario.

    Fonte primaria: fatture (sempre popolata) → nomi distinti.
    Fonte secondaria: fatture_documenti → piva_fornitore (se disponibile).
    Risultato: lista {fornitore, piva_fornitore | null} ordinata per nome.
    """
    from services.db_service import filter_active as _fa
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    uid = str(user["id"])

    # Step 1: nomi distinti da fatture (fonte primaria garantita)
    nomi_fatture: set = set()
    page_size = 1000
    offset = 0
    while True:
        r = (
            _fa(
                sb.table("fatture")
                .select("fornitore")
                .eq("user_id", uid)
                .eq("ristorante_id", ristorante_id)
            )
            .range(offset, offset + page_size - 1)
            .execute()
        )
        for row in (r.data or []):
            nome = str(row.get("fornitore") or "").strip()
            if nome:
                nomi_fatture.add(nome)
        if len(r.data or []) < page_size:
            break
        offset += page_size

    # Step 2: mappa nome → piva da fatture_documenti (opzionale)
    nome_to_piva: Dict[str, str] = {}
    try:
        r2 = (
            sb.table("fatture_documenti")
            .select("fornitore,piva_fornitore")
            .eq("user_id", uid)
            .eq("ristorante_id", ristorante_id)
            .not_.is_("piva_fornitore", "null")
            .execute()
        )
        for row in (r2.data or []):
            nome = str(row.get("fornitore") or "").strip()
            piva = str(row.get("piva_fornitore") or "").strip()
            if nome and piva and nome not in nome_to_piva:
                nome_to_piva[nome] = piva
    except Exception:
        pass

    fornitori = sorted(
        [
            {
                "fornitore": nome,
                "piva_fornitore": nome_to_piva.get(nome),
            }
            for nome in nomi_fatture
        ],
        key=lambda x: x["fornitore"].casefold(),
    )
    return {"fornitori": fornitori}


@router.get("/api/scadenziario/regole", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def get_regole_pagamento(authorization: Optional[str] = Header(None)):
    from services.documenti_service import get_fornitori_pagamenti_config
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    regole = get_fornitori_pagamenti_config(str(user["id"]), ristorante_id)
    return {"regole": regole}


@router.post("/api/scadenziario/regole", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def upsert_regola_pagamento(
    body: FornitoreRegolaRequest, authorization: Optional[str] = Header(None)
):
    from services.documenti_service import upsert_fornitori_pagamenti_config
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    valid_modalita = {"rid", "30gg", "60gg", "90gg", "30gg_fm", "60gg_fm", "90gg_fm"}
    modalita = str(body.modalita or "").strip().lower()
    if modalita not in valid_modalita:
        raise HTTPException(
            status_code=400,
            detail=f"Modalità non valida. Consentite: {', '.join(sorted(valid_modalita))}",
        )

    try:
        result = upsert_fornitori_pagamenti_config(
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
            piva_fornitore=body.piva_fornitore,
            modalita=modalita,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Errore salvataggio"))

    return result


@router.delete(
    "/api/scadenziario/regole/{regola_id}", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)]
)
def delete_regola_pagamento(regola_id: str, authorization: Optional[str] = Header(None)):
    from services.documenti_service import delete_fornitori_pagamenti_config
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        result = delete_fornitori_pagamenti_config(
            user_id=str(user["id"]),
            ristorante_id=ristorante_id,
            regola_id=regola_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="Regola non trovata")

    return result


@router.post("/api/scadenziario/notifica", tags=["Scadenziario"], dependencies=[Depends(_verify_worker_key)])
def genera_notifica_scadenze(authorization: Optional[str] = Header(None)):
    """Genera/aggiorna notifica aggregata scadenze nella inbox (upsert idempotente)."""
    from services.documenti_service import get_documenti_scadenziario
    import pandas as _pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    docs = get_documenti_scadenziario(str(user["id"]), ristorante_id)
    today = _oggi_rome()

    scadute, settimana = [], []
    for doc in docs:
        if doc.get("pagata"):
            continue
        scad = doc.get("scadenza_effettiva")
        if not scad:
            continue
        try:
            dt = _pd.to_datetime(scad, errors="coerce")
            if _pd.isna(dt):
                continue
            delta = (dt.date() - today).days
            if delta < 0:
                scadute.append(doc)
            elif delta <= 7:
                settimana.append(doc)
        except Exception:
            continue

    if not scadute and not settimana:
        return {"ok": True, "notifica": None}

    tot_sc = sum(d.get("totale_documento", 0) or 0 for d in scadute)
    tot_sw = sum(d.get("totale_documento", 0) or 0 for d in settimana)

    parts = []
    if scadute:
        parts.append(f"{len(scadute)} scadut{'a' if len(scadute) == 1 else 'e'} (€{tot_sc:,.0f})")
    if settimana:
        parts.append(f"{len(settimana)} in scadenza questa settimana (€{tot_sw:,.0f})")

    record = {
        "user_id": str(user["id"]),
        "ristorante_id": ristorante_id,
        "topic_key": "scadenze_aggregate",
        "source_type": "scadenziario",
        "severity": "error" if scadute else "warning",
        "title": "Fatture in scadenza",
        "body": " • ".join(parts),
        "action_page": "/scadenziario",
        "dismissed_at": None,
    }

    try:
        sb.table("notification_inbox").upsert(
            record, on_conflict="user_id,ristorante_id,topic_key"
        ).execute()
    except Exception as e:
        logger.warning("Errore upsert notifica scadenze: %s", e)
        return {"ok": False, "error": str(e)}

    return {"ok": True, "notifica": record}


@router.post("/api/ricavi/notifica-mancante", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def genera_notifica_incasso_mancante(authorization: Optional[str] = Header(None)):
    """Promemoria in-app: se manca l'incasso di IERI, mette/aggiorna un avviso
    nella inbox (badge campanella). Se l'incasso di ieri c'e', dismette l'avviso.

    Usa il servizio ufficiale notification_inbox_service (RPC idempotente,
    dedupe_key + refresh_on_conflict gestiti dalla factory) — NON l'upsert diretto.
    Topic 'incasso_mancante': source_type 'operativa', bucket giornaliero (ieri
    cambia ogni giorno), severity 'warning' (non critico, e' un'app di analisi).

    Trigger: chiamato all'apertura della sezione mobile (come scadenze sul tab
    Scadenziario), non da cron. Raffinamento futuro possibile ("non disturbare nei
    giorni di chiusura") ma richiederebbe una semantica di chiusura su diario_eventi
    che oggi non esiste: non la inventiamo qui."""
    from datetime import timedelta as _td
    from services.notification_inbox_service import (
        build_notification_record,
        upsert_inbox_notifications,
        dismiss_inbox_topics,
    )

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    ieri = (_oggi_rome() - _td(days=1)).isoformat()

    # Nota: il rispetto del toggle "Incasso di ieri mancante" e' centralizzato in
    # get_notifiche (filtro unico per tutti i topic, su campanella + avvisi). Qui
    # non serve ricontrollarlo: generare l'avviso anche se spento e' innocuo
    # perche' viene filtrato in lettura, ed evitiamo due logiche sovrapposte.

    # C'e' gia' una riga ricavi per ieri (manuale, xls o email)?
    resp = (
        sb.table("ricavi_giornalieri")
        .select("data")
        .eq("ristorante_id", ristorante_id)
        .eq("data", ieri)
        .limit(1)
        .execute()
    )
    presente = bool(resp.data)

    if presente:
        # Incasso gia' inserito: spegni l'avviso (soft-delete del topic, se attivo).
        dismiss_inbox_topics(str(user["id"]), ristorante_id, ["incasso_mancante"], sb)
        return {"ok": True, "notifica": None}

    record = build_notification_record(
        user_id=str(user["id"]),
        ristorante_id=ristorante_id,
        topic_key="incasso_mancante",
        source_type="operativa",
        severity="warning",
        title="Manca l'incasso di ieri",
        body="Inseriscilo dalla sezione Agenda → Incassi per tenere i margini aggiornati.",
        action_page="Agenda",
    )
    inserted = upsert_inbox_notifications([record], sb)
    return {"ok": True, "inserted": inserted}
