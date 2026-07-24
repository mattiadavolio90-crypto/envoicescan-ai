"""Router dominio RIPARTIZIONE COSTI DI GRUPPO (catene multi-sede).

Un costo di struttura intestato alla sede legale (commercialista, auto aziendale,
ecc.) viene diviso in quote fra i punti vendita, così il MOL di ogni sede è onesto.
Modello dati: migration 20260714130000_riparto_costi_catena.sql. Motore aggregazione:
RPC riparto_quote_mensili (20260714140000). Anti-doppio-conteggio: flag
fatture.ripartita_su_gruppo escluso dal costo automatico (20260714150000).

Principi (PIANO_RIPARTIZIONE_COSTI_CATENA.md 1/7):
  - La fattura resta sacra: non si spezzano/riscrivono le righe. Le quote vivono in
    tabelle separate a livello account.
  - Il motore MOL non cambia: le quote alimentano margini_mensili.quote_riparto_*.
  - Aggregazione SQL 1×/scrittura, mai loop Python.
  - Gating 2+ sedi: la ripartizione esiste solo per le catene.

Pattern import lazy identico a fatture.py (evita il ciclo router<->fastapi_worker).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import logging
logger = logging.getLogger("fastapi_worker")


def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _invalidate_fatture_rows_cache(*args, **kwargs):
    return _fw()._invalidate_fatture_rows_cache(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


router = APIRouter()


# ─── Helper condivisi ────────────────────────────────────────────────────────

def _carica_sedi_attive(user_id: str, sb) -> List[Dict[str, Any]]:
    """Sedi REALI attive dell'account (id, nome). Serve al gating 2+ sedi e al riparto
    equo. Esclude la sede tecnica "Costi comuni di gruppo" (sede_tecnica=TRUE): non è
    un locale reale, non deve contare nel gating né ricevere quote."""
    resp = (
        sb.table("ristoranti")
        .select("id, nome_ristorante")
        .eq("user_id", user_id)
        .eq("attivo", True)
        .eq("sede_tecnica", False)
        .execute()
    )
    return resp.data or []


def _quote_equa(importo: float, sedi_ids: List[str]) -> List[Dict[str, Any]]:
    """Divide importo in parti uguali fra le sedi. L'ultima assorbe l'arrotondamento
    così la somma delle quote pareggia SEMPRE l'importo totale (no centesimi persi)."""
    n = len(sedi_ids)
    if n == 0:
        return []
    perc = round(100.0 / n, 3)
    base = round(importo / n, 2)
    quote = []
    acc = 0.0
    for i, rid in enumerate(sedi_ids):
        if i < n - 1:
            q = base
            p = perc
        else:
            q = round(importo - acc, 2)      # l'ultima pareggia
            p = round(100.0 - perc * (n - 1), 3)
        acc += q
        quote.append({"ristorante_id": rid, "quota_perc": p, "quota_importo": q})
    return quote


def _quote_percentuali(importo: float, percentuali: Dict[str, float]) -> List[Dict[str, Any]]:
    """Quote da percentuali esplicite {ristorante_id: %}. Somma % deve fare ~100.
    L'ultima quota pareggia l'importo (evita derive di arrotondamento)."""
    items = [(rid, float(p or 0)) for rid, p in percentuali.items() if float(p or 0) > 0]
    if not items:
        return []
    tot_perc = sum(p for _, p in items)
    if abs(tot_perc - 100.0) > 0.5:
        raise HTTPException(status_code=400, detail=f"Le percentuali devono sommare 100 (attuale: {tot_perc:.1f})")
    quote = []
    acc = 0.0
    for i, (rid, p) in enumerate(items):
        if i < len(items) - 1:
            q = round(importo * p / 100.0, 2)
        else:
            q = round(importo - acc, 2)
        acc += q
        quote.append({"ristorante_id": rid, "quota_perc": round(p, 3), "quota_importo": q})
    return quote


def _post_scrittura_riparto(sb, user_id: str, anno: int, mese: int) -> None:
    """Dopo ogni scrittura riparto: ricalcola le quote mensili (motore SQL) e
    invalida briefing + cache righe delle sedi coinvolte. Best-effort: un errore
    di invalidazione non deve far fallire l'operazione principale."""
    try:
        sb.rpc("riparto_quote_mensili", {"p_user_id": user_id, "p_anno": anno, "p_mese": mese}).execute()
    except Exception as exc:
        logger.error("riparto_quote_mensili fallita user=%s %d-%d: %s", user_id, anno, mese, exc)
        raise HTTPException(status_code=500, detail="Ricalcolo quote fallito")
    # Il MOL delle sedi coinvolte è cambiato: invalida briefing di tutte le sedi
    # del cliente (semplice e sicuro; azione rara) + cache righe fatture.
    try:
        from services.daily_briefing_service import invalidate_today_briefing
        for s in _carica_sedi_attive(user_id, sb):
            invalidate_today_briefing(user_id, str(s["id"]), sb)
    except Exception as exc:
        logger.warning("invalidazione briefing post-riparto fallita (non bloccante): %s", exc)
    try:
        _invalidate_fatture_rows_cache()
    except Exception:
        pass


# ─── Modelli ─────────────────────────────────────────────────────────────────

class RipartoDaFatturaBody(BaseModel):
    file_origine: str
    descrizione: str
    tipo: str = "generale"            # 'generale' | 'fb'
    regola: str = "equa"             # 'equa' | 'percentuali'
    percentuali: Optional[Dict[str, float]] = None   # {ristorante_id: %} se regola='percentuali'
    salva_regola_fornitore: bool = False


class RipartoDaCodaBody(BaseModel):
    queue_id: int
    descrizione: str
    tipo: str = "generale"            # 'generale' | 'fb'
    regola: str = "equa"             # 'equa' | 'percentuali'
    percentuali: Optional[Dict[str, float]] = None
    salva_regola_fornitore: bool = False


class RipartoManualeBody(BaseModel):
    descrizione: str
    importo_totale: float
    tipo: str = "generale"
    anno: int
    mese: int
    regola: str = "equa"
    percentuali: Optional[Dict[str, float]] = None


class RipartoModificaBody(BaseModel):
    tipo: Optional[str] = None
    regola: Optional[str] = None
    percentuali: Optional[Dict[str, float]] = None
    importo_totale: Optional[float] = None       # solo per voci manuali


# ─── Gating 2+ sedi ──────────────────────────────────────────────────────────

def _require_catena(user_id: str, sb) -> List[Dict[str, Any]]:
    sedi = _carica_sedi_attive(user_id, sb)
    if len(sedi) < 2:
        raise HTTPException(status_code=400, detail="La ripartizione è disponibile solo per gli account con più sedi.")
    return sedi


# ─── Endpoint ────────────────────────────────────────────────────────────────

@router.post("/api/riparto/da-fattura", dependencies=[Depends(_verify_worker_key)])
def riparto_da_fattura(body: RipartoDaFatturaBody, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Ripartisce una fattura di struttura sul gruppo. Legge importo e periodo dalla
    fattura, calcola le quote (equa/percentuali), marca le righe ripartite ed esclude
    così il costo dalla porta automatica (rientra distribuito dalle quote)."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    sedi = _require_catena(user_id, sb)
    fo = (body.file_origine or "").strip()
    if not fo:
        raise HTTPException(status_code=400, detail="file_origine mancante")
    if body.tipo not in ("generale", "fb"):
        raise HTTPException(status_code=400, detail="tipo non valido")

    # Carica le righe della fattura (importo = somma totale_riga, periodo da data).
    righe = (
        sb.table("fatture")
        .select("id, totale_riga, data_documento, data_competenza, fornitore, piva_cedente, ripartita_su_gruppo")
        .eq("user_id", user_id)
        .eq("file_origine", fo)
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    if not righe:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if any(bool(r.get("ripartita_su_gruppo")) for r in righe):
        raise HTTPException(status_code=409, detail="Fattura già ripartita sul gruppo")

    importo = round(sum(float(r.get("totale_riga") or 0) for r in righe), 2)
    # Periodo di competenza: data_competenza se presente, altrimenti data_documento.
    _data = None
    for r in righe:
        _data = r.get("data_competenza") or r.get("data_documento")
        if _data:
            break
    if not _data:
        raise HTTPException(status_code=400, detail="Data fattura assente: impossibile determinare il mese di competenza")
    anno, mese = int(str(_data)[0:4]), int(str(_data)[5:7])
    fornitore = next((r.get("piva_cedente") or r.get("fornitore") for r in righe if (r.get("piva_cedente") or r.get("fornitore"))), None)

    if body.regola == "percentuali":
        quote = _quote_percentuali(importo, body.percentuali or {})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    # Crea il riparto + quote.
    ins = (
        sb.table("riparto_costi_catena")
        .insert({
            "user_id": user_id, "origine": "fattura", "file_origine": fo,
            "fornitore": fornitore, "descrizione": body.descrizione.strip() or "Costo di gruppo",
            "importo_totale": importo, "tipo": body.tipo, "anno": anno, "mese": mese,
            "regola": body.regola,
        })
        .execute()
    )
    if not ins.data:
        raise HTTPException(status_code=500, detail="Creazione riparto fallita")
    riparto_id = ins.data[0]["id"]
    sb.table("riparto_costi_catena_quote").insert(
        [{"riparto_id": riparto_id, **q} for q in quote]
    ).execute()

    # Esplodi le quote per categoria dalle righe reali della fattura (già in `fatture`):
    # ogni sede vede la sua porzione F&B e la sua porzione spese nel MOL. Se la fattura
    # non ha righe categorizzabili resta il modello legacy per-tipo (helper ritorna False).
    try:
        from services.riparto_service import esplodi_quote_per_categoria
        esplodi_quote_per_categoria(sb, user_id, riparto_id, fo)
    except Exception as exc:
        logger.warning("esplosione quote per categoria fallita (resta legacy) riparto=%s: %s", riparto_id, exc)

    # Marca le righe della fattura come ripartite (anti-doppio-conteggio).
    sb.table("fatture").update({"ripartita_su_gruppo": True}) \
        .eq("user_id", user_id).eq("file_origine", fo).is_("deleted_at", "null").execute()

    # Regola fornitore opzionale (propone la volta dopo, non applica).
    if body.salva_regola_fornitore and fornitore:
        sb.table("riparto_regole_fornitore").upsert({
            "user_id": user_id, "fornitore": str(fornitore), "regola": body.regola,
            "tipo": body.tipo, "percentuali": body.percentuali, "attiva": True,
        }, on_conflict="user_id,fornitore").execute()

    _post_scrittura_riparto(sb, user_id, anno, mese)
    return {"ok": True, "riparto_id": riparto_id, "importo": importo, "anno": anno, "mese": mese, "quote": quote}


@router.post("/api/riparto/da-coda", dependencies=[Depends(_verify_worker_key)])
def riparto_da_coda(body: RipartoDaCodaBody, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Ripartisce una fattura ambigua DIRETTAMENTE dalla coda 'da_assegnare', senza
    prima assegnarla a un locale reale. UX istantanea (decisione utente): registra
    subito il riparto dai metadati della coda (importo/fornitore/periodo/file_origine
    sono in payload_meta), poi chiama assegna_fattura_a_sede_tecnica → il worker atterra
    la fattura sulla sede tecnica "Costi comuni di gruppo" (mai un locale reale) e la
    auto-marca ripartita_su_gruppo. Nessun locale reale viene toccato."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    sedi = _require_catena(user_id, sb)
    if body.tipo not in ("generale", "fb"):
        raise HTTPException(status_code=400, detail="tipo non valido")

    # Record di coda del chiamante, ancora da_assegnare (guard ownership + stato).
    q = (
        sb.table("fatture_queue")
        .select("id, user_id, status, piva_raw, payload_meta")
        .eq("id", body.queue_id)
        .eq("user_id", user_id)
        .eq("status", "da_assegnare")
        .limit(1)
        .execute()
    ).data
    if not q:
        raise HTTPException(status_code=404, detail="Fattura non trovata in coda o già assegnata")
    meta = (q[0].get("payload_meta") or {})

    # Metadati necessari: importo, periodo, file_origine (già salvati dal webhook /
    # dall'upload ambiguo). Fallback prudente se qualcuno manca.
    fo = str(meta.get("nome_file") or "").strip()
    if not fo:
        raise HTTPException(status_code=400, detail="Metadati fattura incompleti (nome_file assente): impossibile ripartire dalla coda")
    try:
        importo = round(float(meta.get("importo_totale") or 0), 2)
    except (TypeError, ValueError):
        importo = 0.0
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo fattura non disponibile nei metadati: impossibile ripartire dalla coda")
    _data = str(meta.get("data_fattura") or "").strip()
    if len(_data) < 7:
        raise HTTPException(status_code=400, detail="Data fattura non disponibile nei metadati: impossibile determinare il mese di competenza")
    anno, mese = int(_data[0:4]), int(_data[5:7])
    fornitore = meta.get("piva_cedente") or None

    if body.regola == "percentuali":
        quote = _quote_percentuali(importo, body.percentuali or {})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    # 1) Registra subito il riparto + quote (UX istantanea).
    ins = (
        sb.table("riparto_costi_catena")
        .insert({
            "user_id": user_id, "origine": "fattura", "file_origine": fo,
            "fornitore": fornitore, "descrizione": body.descrizione.strip() or "Costo di gruppo",
            "importo_totale": importo, "tipo": body.tipo, "anno": anno, "mese": mese,
            "regola": body.regola,
        })
        .execute()
    )
    if not ins.data:
        raise HTTPException(status_code=500, detail="Creazione riparto fallita")
    riparto_id = ins.data[0]["id"]
    sb.table("riparto_costi_catena_quote").insert(
        [{"riparto_id": riparto_id, **qq} for qq in quote]
    ).execute()

    # 2) Marcatura idempotente per file_origine: colpisce 0 righe finché la fattura non
    # è atterrata (innocuo); il worker la marca comunque all'atterraggio (sede tecnica).
    sb.table("fatture").update({"ripartita_su_gruppo": True}) \
        .eq("user_id", user_id).eq("file_origine", fo).is_("deleted_at", "null").execute()

    # 3) Assegna alla sede tecnica → il worker processa la fattura in background.
    res = sb.rpc("assegna_fattura_a_sede_tecnica", {"p_queue_id": body.queue_id}).execute()
    sede_tecnica_id = res.data if res.data else None
    if not sede_tecnica_id:
        # Race: assegnata da un altro click. Il riparto resta valido (idempotente sul
        # file_origine); non è un errore per la UI.
        logger.warning("assegna_fattura_a_sede_tecnica no-op per queue_id=%s (race)", body.queue_id)

    # Regola fornitore opzionale (propone la volta dopo, non applica).
    if body.salva_regola_fornitore and fornitore:
        sb.table("riparto_regole_fornitore").upsert({
            "user_id": user_id, "fornitore": str(fornitore), "regola": body.regola,
            "tipo": body.tipo, "percentuali": body.percentuali, "attiva": True,
        }, on_conflict="user_id,fornitore").execute()

    _post_scrittura_riparto(sb, user_id, anno, mese)
    return {"ok": True, "riparto_id": riparto_id, "importo": importo, "anno": anno, "mese": mese, "quote": quote}


@router.post("/api/riparto/manuale", dependencies=[Depends(_verify_worker_key)])
def riparto_manuale(body: RipartoManualeBody, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Voce di costo di gruppo senza fattura (es. stipendi ufficio)."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    sedi = _require_catena(user_id, sb)
    if body.tipo not in ("generale", "fb"):
        raise HTTPException(status_code=400, detail="tipo non valido")
    if not 1 <= body.mese <= 12:
        raise HTTPException(status_code=400, detail="mese non valido")
    importo = round(float(body.importo_totale or 0), 2)
    if importo <= 0:
        raise HTTPException(status_code=400, detail="importo non valido")

    if body.regola == "percentuali":
        quote = _quote_percentuali(importo, body.percentuali or {})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    ins = (
        sb.table("riparto_costi_catena")
        .insert({
            "user_id": user_id, "origine": "manuale", "file_origine": None,
            "descrizione": body.descrizione.strip() or "Costo di gruppo",
            "importo_totale": importo, "tipo": body.tipo, "anno": body.anno, "mese": body.mese,
            "regola": body.regola,
        })
        .execute()
    )
    if not ins.data:
        raise HTTPException(status_code=500, detail="Creazione riparto fallita")
    riparto_id = ins.data[0]["id"]
    sb.table("riparto_costi_catena_quote").insert(
        [{"riparto_id": riparto_id, **q} for q in quote]
    ).execute()

    _post_scrittura_riparto(sb, user_id, body.anno, body.mese)
    return {"ok": True, "riparto_id": riparto_id, "quote": quote}


@router.patch("/api/riparto/{riparto_id}", dependencies=[Depends(_verify_worker_key)])
def riparto_modifica(riparto_id: str, body: RipartoModificaBody, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Modifica regola/percentuali/importo di un riparto → ricalcola le quote."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    sedi = _require_catena(user_id, sb)

    rip = (
        sb.table("riparto_costi_catena").select("*")
        .eq("id", riparto_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rip:
        raise HTTPException(status_code=404, detail="Riparto non trovato")
    rip = rip[0]

    tipo = body.tipo or rip["tipo"]
    regola = body.regola or rip["regola"]
    importo = round(float(body.importo_totale), 2) if body.importo_totale is not None else float(rip["importo_totale"])
    if rip["origine"] == "fattura" and body.importo_totale is not None:
        raise HTTPException(status_code=400, detail="L'importo di un riparto da fattura non è modificabile (deriva dal documento)")
    if tipo not in ("generale", "fb"):
        raise HTTPException(status_code=400, detail="tipo non valido")

    if regola == "percentuali":
        quote = _quote_percentuali(importo, body.percentuali or {})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    sb.table("riparto_costi_catena").update({
        "tipo": tipo, "regola": regola, "importo_totale": importo,
    }).eq("id", riparto_id).eq("user_id", user_id).execute()
    # Rimpiazza le quote (delete + insert).
    sb.table("riparto_costi_catena_quote").delete().eq("riparto_id", riparto_id).execute()
    sb.table("riparto_costi_catena_quote").insert(
        [{"riparto_id": riparto_id, **q} for q in quote]
    ).execute()

    _post_scrittura_riparto(sb, user_id, int(rip["anno"]), int(rip["mese"]))
    return {"ok": True, "quote": quote}


@router.delete("/api/riparto/{riparto_id}", dependencies=[Depends(_verify_worker_key)])
def riparto_elimina(riparto_id: str, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Elimina un riparto. Se da fattura → smarca le righe (il costo torna intero
    sulla sede intestataria). Le quote spariscono via ON DELETE CASCADE."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    rip = (
        sb.table("riparto_costi_catena").select("id, origine, file_origine, anno, mese")
        .eq("id", riparto_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rip:
        raise HTTPException(status_code=404, detail="Riparto non trovato")
    rip = rip[0]

    sb.table("riparto_costi_catena").delete().eq("id", riparto_id).eq("user_id", user_id).execute()
    if rip["origine"] == "fattura" and rip.get("file_origine"):
        sb.table("fatture").update({"ripartita_su_gruppo": False}) \
            .eq("user_id", user_id).eq("file_origine", rip["file_origine"]).execute()

    _post_scrittura_riparto(sb, user_id, int(rip["anno"]), int(rip["mese"]))
    return {"ok": True}


@router.post("/api/riparto/{riparto_id}/duplica", dependencies=[Depends(_verify_worker_key)])
def riparto_duplica(riparto_id: str, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Duplica una voce (di norma manuale, ricorrente) sul mese successivo."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    _require_catena(user_id, sb)

    rip = (
        sb.table("riparto_costi_catena").select("*")
        .eq("id", riparto_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rip:
        raise HTTPException(status_code=404, detail="Riparto non trovato")
    rip = rip[0]
    if rip["origine"] == "fattura":
        raise HTTPException(status_code=400, detail="Un riparto da fattura non si duplica (la fattura del mese dopo è un altro documento)")

    quote = (
        sb.table("riparto_costi_catena_quote").select("ristorante_id, quota_perc, quota_importo")
        .eq("riparto_id", riparto_id).execute()
    ).data or []

    # Mese successivo (con rollover anno).
    anno, mese = int(rip["anno"]), int(rip["mese"])
    if mese == 12:
        anno_n, mese_n = anno + 1, 1
    else:
        anno_n, mese_n = anno, mese + 1

    ins = (
        sb.table("riparto_costi_catena")
        .insert({
            "user_id": user_id, "origine": "manuale", "file_origine": None,
            "descrizione": rip["descrizione"], "importo_totale": rip["importo_totale"],
            "tipo": rip["tipo"], "anno": anno_n, "mese": mese_n, "regola": rip["regola"],
        })
        .execute()
    ).data
    if not ins:
        raise HTTPException(status_code=500, detail="Duplicazione fallita")
    nuovo_id = ins[0]["id"]
    if quote:
        sb.table("riparto_costi_catena_quote").insert(
            [{"riparto_id": nuovo_id, **q} for q in quote]
        ).execute()

    _post_scrittura_riparto(sb, user_id, anno_n, mese_n)
    return {"ok": True, "riparto_id": nuovo_id, "anno": anno_n, "mese": mese_n}


class _AnteprimaFileLike:
    """File-like minimale per estrai_dati_da_xml() (accetta UploadedFile/BytesIO con
    .name, .read()). Non tocca disco né rete: wrappa i bytes già in memoria."""

    def __init__(self, data: bytes, name: str):
        import io
        self.name = name
        self._buf = io.BytesIO(data)

    def read(self, *a):
        return self._buf.read(*a)

    def seek(self, *a):
        return self._buf.seek(*a)


def costruisci_anteprima_righe(righe_parsate) -> list:
    """Converte l'output di estrai_dati_da_xml() nella forma dell'anteprima coda
    (le stesse chiavi che l'endpoint /api/riparto/anteprima-coda ritorna e che il
    frontend legge). Fonte UNICA della forma: usata sia dall'ingestione (per salvare
    la cache all'ingresso, così l'anteprima non dipende dalla prima apertura) sia
    dall'endpoint stesso. Nessun I/O — puro rimappaggio di chiavi."""
    return [
        {
            "numero_riga": r.get("Numero_Riga"),
            "descrizione": r.get("Descrizione"),
            "quantita": r.get("Quantita"),
            "unita_misura": r.get("Unita_Misura"),
            "prezzo_unitario": r.get("Prezzo_Unitario"),
            "iva_percentuale": r.get("IVA_Percentuale"),
            "totale_riga": r.get("Totale_Riga"),
            "categoria": r.get("Categoria"),
        }
        for r in (righe_parsate or [])
    ]


@router.get("/api/riparto/anteprima-coda", dependencies=[Depends(_verify_worker_key)])
def riparto_anteprima_coda(queue_id: int, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Anteprima delle righe di una fattura ancora in coda 'da_assegnare' (non ancora
    collocata su un locale, quindi non presente in `fatture`).

    Fase 4 (23/07): anteprima PERSISTENTE. Al primo accesso parsa l'XML una volta e
    salva le righe in fatture_queue.anteprima_righe; le aperture successive leggono da
    lì → istantanee, nessun ri-parse a caldo, nessuna contesa sul container singolo
    (era la causa radice dell'intermittenza "documento non leggibile"). La cache è di
    sola visualizzazione, derivata dall'XML e rigenerabile: azzerando anteprima_righe
    il prossimo accesso la ricalcola.

    Riusa estrai_dati_da_xml() in SOLA LETTURA passando user_id=None: la funzione fa
    parsing/sconti/note di credito (puro calcolo, nessun I/O) + categorizza_con_memoria
    (memoria/regole/dizionario, NESSUNA chiamata AI) SENZA memoria personalizzata né
    scritture (carica_memoria_completa e flush_pending_local_saves sono entrambe
    condizionate a user_id essere valorizzato — con None restano no-op). La categoria
    mostrata è quindi una stima (dizionario/regole globali), non la classificazione
    definitiva che il documento riceverà una volta collocato su un locale."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])

    q = (
        sb.table("fatture_queue")
        .select("id, user_id, xml_content, xml_url, xml_purged_at, payload_meta, anteprima_righe")
        .eq("id", queue_id)
        .eq("user_id", user_id)
        .eq("status", "da_assegnare")
        .limit(1)
        .execute()
    ).data
    if not q:
        raise HTTPException(status_code=404, detail="Fattura non trovata in coda")
    row = q[0]

    # Cache: righe già parsate e salvate → risposta istantanea, nessun ri-parse.
    # Sopravvive anche alla purge di xml_content, quindi va tentata PRIMA. Da quando
    # l'anteprima è generata all'ingresso (accoda_upload_ambiguo con p_anteprima_righe),
    # questo ramo copre di fatto tutti i documenti nuovi.
    cache = row.get("anteprima_righe")
    if isinstance(cache, list):
        return {"disponibile": True, "righe": cache, "cache": True}

    xml_content = row.get("xml_content")

    # Fallback recupero: xml_content assente ma xml_url presente (canale SDI) → lo
    # riscarico al volo. Il canale manuale non ha xml_url: se anche l'xml_content è
    # sparito (purga storica pre-guardia), il contenuto NON è recuperabile lato server
    # e va detto onestamente ("perso"), non spacciato per "documento illeggibile".
    if not xml_content:
        xml_url = row.get("xml_url")
        if xml_url:
            try:
                from worker.queue_processor import _fetch_xml_from_url
                xml_content = _fetch_xml_from_url(xml_url)
            except Exception as exc:
                logger.warning("Anteprima coda: refetch xml_url fallito queue_id=%s: %s", queue_id, exc)
                xml_content = None
        if not xml_content:
            # Distinzione onesta per la UI: motivo="perso" quando il documento è stato
            # purgato e non è più ricostruibile (niente cache, niente XML, niente url);
            # la fattura resta comunque assegnabile su fornitore/data/importo (payload_meta).
            motivo = "perso" if row.get("xml_purged_at") else "assente"
            return {"righe": [], "disponibile": False, "motivo": motivo}

    from services.invoice_service import estrai_dati_da_xml
    nome_file = (row.get("payload_meta") or {}).get("nome_file") or f"queue_{queue_id}.xml"
    xml_bytes = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    file_like = _AnteprimaFileLike(xml_bytes, nome_file)

    try:
        righe = estrai_dati_da_xml(file_like, user_id=None) or []
    except Exception as exc:
        logger.warning("Anteprima coda: parsing fallito queue_id=%s: %s", queue_id, exc)
        return {"righe": [], "disponibile": False, "motivo": "illeggibile"}

    righe_out = costruisci_anteprima_righe(righe)

    # Persisti la cache per le aperture successive. Il salvataggio è un di più: se
    # fallisce, l'utente riceve comunque le righe appena parsate (verrà ricalcolata
    # al prossimo accesso). Un parsing riuscito ma vuoto ([]) viene salvato lo stesso:
    # è un esito legittimo e va cacheato per non ri-parsare a vuoto ogni volta.
    try:
        from datetime import datetime, timezone
        sb.table("fatture_queue").update(
            {"anteprima_righe": righe_out, "anteprima_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", queue_id).eq("user_id", user_id).execute()
    except Exception as exc:
        logger.warning("Anteprima coda: salvataggio cache fallito queue_id=%s: %s", queue_id, exc)

    return {"disponibile": True, "righe": righe_out, "cache": False}


@router.get("/api/riparto/regola-fornitore", dependencies=[Depends(_verify_worker_key)])
def riparto_regola_fornitore(fornitore: str, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Regola di ripartizione memorizzata per un fornitore ("fai sempre così").

    Sola lettura: NON applica nulla. Serve al dialog di riparto per PRE-COMPILARE il
    criterio (regola/tipo/percentuali) alla fattura successiva dello stesso fornitore;
    il cliente conferma sempre. Ritorna {regola: null} se non c'è una regola attiva."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    _require_catena(user_id, sb)
    piva = (fornitore or "").strip()
    if not piva:
        return {"regola": None}

    res = (
        sb.table("riparto_regole_fornitore")
        .select("regola, tipo, percentuali")
        .eq("user_id", user_id)
        .eq("fornitore", piva)
        .eq("attiva", True)
        .limit(1)
        .execute()
    ).data
    if not res:
        return {"regola": None}
    r = res[0]
    return {
        "regola": r.get("regola"),
        "tipo": r.get("tipo"),
        "percentuali": r.get("percentuali"),
    }


@router.get("/api/gruppo/costi-comuni", dependencies=[Depends(_verify_worker_key)])
def gruppo_costi_comuni(anno: int, mese: int, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Lista dei costi di gruppo del mese con le quote per sede (finestra catena).
    Sola lettura, aggregazione SQL. Gating 2+ sedi."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    sedi = _require_catena(user_id, sb)
    nomi = {str(s["id"]): s.get("nome_ristorante") for s in sedi}

    costi = (
        sb.table("riparto_costi_catena")
        .select("id, origine, file_origine, fornitore, descrizione, importo_totale, tipo, regola")
        .eq("user_id", user_id).eq("anno", anno).eq("mese", mese)
        .order("descrizione")
        .execute()
    ).data or []
    if not costi:
        return {"anno": anno, "mese": mese, "costi": [], "totale": 0.0}

    ids = [c["id"] for c in costi]
    quote = (
        sb.table("riparto_costi_catena_quote")
        .select("riparto_id, ristorante_id, quota_perc, quota_importo")
        .in_("riparto_id", ids)
        .execute()
    ).data or []
    quote_by_rip: Dict[str, List[Dict[str, Any]]] = {}
    for q in quote:
        quote_by_rip.setdefault(q["riparto_id"], []).append({
            "ristorante_id": q["ristorante_id"],
            "sede": nomi.get(str(q["ristorante_id"]), "—"),
            "quota_perc": float(q["quota_perc"]),
            "quota_importo": float(q["quota_importo"]),
        })

    out = []
    tot = 0.0
    for c in costi:
        tot += float(c["importo_totale"] or 0)
        out.append({
            "id": c["id"], "origine": c["origine"], "file_origine": c.get("file_origine"),
            "fornitore": c.get("fornitore"), "descrizione": c["descrizione"],
            "importo_totale": float(c["importo_totale"] or 0), "tipo": c["tipo"], "regola": c["regola"],
            "quote": quote_by_rip.get(c["id"], []),
        })
    return {"anno": anno, "mese": mese, "costi": out, "totale": round(tot, 2)}
