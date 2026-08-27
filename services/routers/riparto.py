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

from utils.validation import normalizza_categoria_richiesta, importo_riga_per_guardrail
from utils.supabase_paging import fetch_all
from config.constants import CATEGORIE_FOOD_BEVERAGE, CATEGORIA_NON_CLASSIFICATA as _CATEGORIA_NON_CLASSIFICATA

# Chiave interna per le quote con categoria NULL (esplosione per-categoria mai
# riuscita: la fattura d'origine non ha righe vive). NON è una categoria di dominio e
# non deve finire in dettaglio_categorie né essere scritta a DB: serve solo a non
# perdere l'importo nell'aggregato. Le parentesi la rendono non collidibile con una
# categoria reale, che è sempre una stringa in maiuscolo senza punteggiatura.
_SENZA_CATEGORIA = "(senza categoria)"
from services.riparto_service import SENTINELLA_RIPARTO_MANUALE as _SENTINELLA_RIPARTO_MANUALE
from services.riparto_service import (
    DESCR_QUOTA_SINTETICA_GENERICA as _DESCR_QUOTA_GENERICA,
    DESCR_QUOTA_SINTETICA_PREFIX as _DESCR_QUOTA_PREFIX,
)
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


def _quote_equa(importo: float, sedi_ids: List[str], categoria: Optional[str] = None) -> List[Dict[str, Any]]:
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
        quota: Dict[str, Any] = {"ristorante_id": rid, "quota_perc": p, "quota_importo": q}
        if categoria:
            quota["categoria"] = categoria
        quote.append(quota)
    return quote


def _quote_percentuali(importo: float, percentuali: Dict[str, float], sedi_ok: set, categoria: Optional[str] = None) -> List[Dict[str, Any]]:
    """Quote da percentuali esplicite {ristorante_id: %}. Somma % deve fare ~100.
    L'ultima quota pareggia l'importo (evita derive di arrotondamento).
    sedi_ok: id delle sedi attive del chiamante — ogni chiave fuori da questo
    insieme viene rifiutata (altrimenti si scrive nel MOL di un altro account)."""
    items = [(rid, float(p or 0)) for rid, p in percentuali.items() if float(p or 0) > 0]
    ignote = {rid for rid, _ in items} - sedi_ok
    if ignote:
        raise HTTPException(status_code=400, detail="Sede non appartenente all'account")
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
        quota: Dict[str, Any] = {"ristorante_id": rid, "quota_perc": round(p, 3), "quota_importo": q}
        if categoria:
            quota["categoria"] = categoria
        quote.append(quota)
    return quote


def _post_scrittura_riparto(sb, user_id: str, anno: int, mese: int) -> bool:
    """Dopo ogni scrittura riparto: ricalcola le quote mensili (motore SQL) e
    invalida briefing + cache righe delle sedi coinvolte. Best-effort: un errore
    qui non deve far fallire l'operazione principale.

    Ritorna True se il ricalcolo quote è andato a buon fine, False altrimenti.

    Perché non solleva più: viene chiamata DOPO che la scrittura è già a segno. Un
    500 qui diceva al cliente "non è cambiato niente" mentre la categoria era già
    salvata — e senza exception handler globale sul worker quel 500 tornava con un
    corpo non-JSON, che lato Next diventava un fuorviante "Worker unreachable".
    Il chiamante propaga l'esito nella risposta e l'UI avvisa che resta da
    ricalcolare, invece di dichiarare fallito tutto.
    """
    ricalcolo_ok = True
    try:
        sb.rpc("riparto_quote_mensili", {"p_user_id": user_id, "p_anno": anno, "p_mese": mese}).execute()
    except Exception as exc:
        ricalcolo_ok = False
        logger.error("riparto_quote_mensili fallita user=%s %d-%d: %s", user_id, anno, mese, exc)
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
    return ricalcolo_ok


def _correggi_categoria_costo_manuale(
    sb, user_id: str, riparto_id: str, nuova_cat: str
) -> Dict[str, Any]:
    """Correzione categoria su un costo di gruppo MANUALE (senza fattura).

    Non passa da esplodi_quote_per_categoria: quella deriva i pesi dalle righe reali
    della fattura, che qui non esistono. Un costo manuale ha un solo importo e una
    sola categoria, quindi si riscrive `categoria` su tutte le sue quote e si riallinea
    `tipo` (F&B/spese), altrimenti header e quote divergono e il badge mente.
    """
    rip_resp = (
        sb.table("riparto_costi_catena")
        .select("id, anno, mese, origine, regola, importo_totale")
        .eq("user_id", user_id)
        .eq("id", riparto_id)
        .limit(1)
        .execute()
    ).data or []
    if not rip_resp:
        raise HTTPException(status_code=404, detail="Nessun costo di gruppo per questo documento")
    riparto = rip_resp[0]

    # Regola di dominio #2: NOTE E DICITURE solo a importo zero. Un costo di gruppo è
    # per definizione un importo positivo (vedi riparto_manuale).
    if nuova_cat == "📝 NOTE E DICITURE":
        raise HTTPException(
            status_code=422,
            detail="NOTE E DICITURE non applicabile: il costo di gruppo ha importo diverso da zero.",
        )

    tipo = "fb" if nuova_cat in CATEGORIE_FOOD_BEVERAGE else "generale"

    # Le quote vanno CONSOLIDATE per sede, non riscritte in blocco. Dall'esplosione
    # per-categoria (24/7) una sede può avere N quote (una per categoria): un
    # UPDATE che le porta tutte a `nuova_cat` le renderebbe duplicati sulla stessa
    # terna e violerebbe uq_riparto_quota_sede_categoria (riparto_id, ristorante_id,
    # categoria) — APIError non gestito, che il worker restituiva come 500 opaco.
    # Qui le N righe della sede diventano UNA: importi sommati (il totale di sede
    # non cambia) e quota_perc invariata, perché è la % della sede, non della
    # categoria. Riscrittura via RPC transazionale: un DELETE+INSERT a mano
    # lascerebbe il riparto senza quote se il secondo statement fallisse.
    quote = (
        sb.table("riparto_costi_catena_quote")
        .select("ristorante_id, quota_perc, quota_importo")
        .eq("riparto_id", riparto_id)
        .execute()
    ).data or []

    consolidate: Dict[str, Dict[str, Any]] = {}
    for q in quote:
        rid = str(q["ristorante_id"])
        voce = consolidate.setdefault(
            rid,
            {
                "ristorante_id": rid,
                "quota_perc": float(q.get("quota_perc") or 0),
                "quota_importo": 0.0,
                "categoria": nuova_cat,
            },
        )
        voce["quota_importo"] += float(q.get("quota_importo") or 0)

    if consolidate:
        for voce in consolidate.values():
            voce["quota_importo"] = round(voce["quota_importo"], 2)
        sb.rpc(
            "sostituisci_quote_riparto",
            {
                "p_riparto_id": riparto_id,
                "p_user_id": user_id,
                "p_tipo": tipo,
                "p_regola": riparto.get("regola") or "equa",
                "p_importo_totale": float(riparto.get("importo_totale") or 0),
                "p_quote": list(consolidate.values()),
            },
        ).execute()
    else:
        # Nessuna quota (riparto degenere): resta solo il riallineamento del padre,
        # altrimenti header e quote direbbero cose diverse.
        sb.table("riparto_costi_catena") \
            .update({"tipo": tipo}).eq("id", riparto_id).eq("user_id", user_id).execute()

    ricalcolo_ok = _post_scrittura_riparto(sb, user_id, int(riparto["anno"]), int(riparto["mese"]))

    sedi = _carica_sedi_attive(user_id, sb)
    return {
        "ok": True,
        "righe_aggiornate": 0,
        "categoria": nuova_cat,
        "ricalcolo_quote_ok": ricalcolo_ok,
        "sedi_impattate": [s.get("nome_ristorante") for s in sedi if s.get("nome_ristorante")],
    }


def _crea_riparto_con_quote(
    sb, user_id: str, origine: str, file_origine: Optional[str], fornitore: Optional[str],
    descrizione: str, importo_totale: float, tipo: str, anno: int, mese: int,
    regola: str, quote: List[Dict[str, Any]],
) -> str:
    """Crea il riparto padre + le sue quote in una sola transazione DB (RPC
    crea_riparto_con_quote, migration 20260805143000): se l'insert delle quote
    fallisse dopo quello del padre, senza transazione resterebbe un riparto
    "orfano" invisibile al motore MOL ma con le righe già marcate ripartite —
    il costo sparirebbe dal MOL in silenzio (stessa classe dell'incidente
    FASTWEB del 22/7)."""
    res = sb.rpc("crea_riparto_con_quote", {
        "p_user_id": user_id, "p_origine": origine, "p_file_origine": file_origine,
        "p_fornitore": fornitore, "p_descrizione": descrizione,
        "p_importo_totale": importo_totale, "p_tipo": tipo, "p_anno": anno, "p_mese": mese,
        "p_regola": regola, "p_quote": quote,
    }).execute()
    riparto_id = res.data
    if not riparto_id:
        raise HTTPException(status_code=500, detail="Creazione riparto fallita")
    return riparto_id


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
    categoria: str
    anno: int
    mese: int
    regola: str = "equa"
    percentuali: Optional[Dict[str, float]] = None


class RipartoModificaBody(BaseModel):
    tipo: Optional[str] = None
    regola: Optional[str] = None
    percentuali: Optional[Dict[str, float]] = None
    importo_totale: Optional[float] = None       # solo per voci manuali


class RipartoRigaCategoriaBody(BaseModel):
    file_origine: str
    descrizione: str
    nuova_categoria: str


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

    # Somma con segno: per una nota di credito (TD04) il parser ha già invertito le
    # righe, quindi `importo` è NEGATIVO ed è giusto che lo resti — la NC va ripartita
    # come rimborso, non come costo, e si netta nel mese come nel mono-sede. Nessun
    # guard `<= 0` qui, e dal 27/8/2026 nemmeno il CHECK DB che lo rifiutava
    # (20260827214500_riparto_consenti_note_credito.sql).
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
        quote = _quote_percentuali(importo, body.percentuali or {}, {str(s["id"]) for s in sedi})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    # Crea il riparto + quote (transazionale: vedi _crea_riparto_con_quote).
    riparto_id = _crea_riparto_con_quote(
        sb, user_id, "fattura", fo, fornitore,
        body.descrizione.strip() or "Costo di gruppo",
        importo, body.tipo, anno, mese, body.regola, quote,
    )

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
        # `importo_totale` dei metadati di coda è `ImportoTotaleDocumento` (IVA inclusa):
        # qui le righe non sono ancora atterrate, quindi il netto imponibile non è noto.
        # È un valore PROVVISORIO: all'atterraggio sulla sede tecnica il worker chiama
        # `esplodi_quote_per_categoria`, che riporta `importo_totale` e le quote al netto
        # reale (`sum(totale_riga)`). `/api/riparto/da-fattura` invece usa già il netto.
        importo = round(float(meta.get("importo_totale") or 0), 2)
    except (TypeError, ValueError):
        importo = 0.0
    # Il guard resta `<= 0` e NON va cambiato per le note di credito: qui
    # `ImportoTotaleDocumento` è positivo anche per una TD04 (il segno lo mette il
    # parser sulle righe, che non sono ancora atterrate). Un importo <= 0 a questo
    # punto significa davvero "metadato mancante", non "nota di credito". Il segno
    # corretto arriva dopo, da esplodi_quote_per_categoria.
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo fattura non disponibile nei metadati: impossibile ripartire dalla coda")
    _data = str(meta.get("data_fattura") or "").strip()
    if len(_data) < 7:
        raise HTTPException(status_code=400, detail="Data fattura non disponibile nei metadati: impossibile determinare il mese di competenza")
    anno, mese = int(_data[0:4]), int(_data[5:7])
    fornitore = meta.get("piva_cedente") or None

    if body.regola == "percentuali":
        quote = _quote_percentuali(importo, body.percentuali or {}, {str(s["id"]) for s in sedi})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    # 0) Guard di coerenza: il record di coda è già stato verificato ownership+stato
    # sopra (da_assegnare), quindi il documento esiste ancora nella coda. Se però nel
    # frattempo una riga con questo file_origine fosse già atterrata E fosse già stata
    # cestinata (race: doppio invio, o riparto duplicato su un documento già smaltito),
    # non creare un riparto senza alcun documento vivo dietro (classe di bug Amazon
    # 20-23/7: riparto nato dopo che le righe erano già soft-deleted). Verifica
    # apposta: deve vedere ANCHE le righe cestinate, per distinguere "mai atterrato"
    # (guard non applicabile, comportamento invariato) da "atterrato e poi cestinato"
    # (409). Stesso pattern delle verify post-eliminazione in db_service.py.
    from services.riparto_service import verifica_documento_vivo
    query_verify_esistenza = (
        sb.table("fatture").select("id", count="exact")
        .eq("user_id", user_id).eq("file_origine", fo).limit(1).execute()
    )
    n_atterrate = query_verify_esistenza.count if query_verify_esistenza.count is not None else (len(query_verify_esistenza.data) if query_verify_esistenza.data else 0)
    if n_atterrate > 0 and verifica_documento_vivo(sb, user_id, fo) == 0:
        raise HTTPException(status_code=409, detail="Documento già cestinato: impossibile ripartire dalla coda")

    # 1) Registra subito il riparto + quote (UX istantanea, transazionale).
    riparto_id = _crea_riparto_con_quote(
        sb, user_id, "fattura", fo, fornitore,
        body.descrizione.strip() or "Costo di gruppo",
        importo, body.tipo, anno, mese, body.regola, quote,
    )

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
    """Voce di costo di gruppo senza fattura (es. utenze sede centrale, canone gestionale)."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    sedi = _require_catena(user_id, sb)
    try:
        categoria = normalizza_categoria_richiesta(body.categoria)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if categoria == "📝 NOTE E DICITURE":
        # Regola di dominio #2: NOTE E DICITURE solo per importo zero — un costo di
        # gruppo è per definizione un importo positivo, quindi qui non è ammessa.
        raise HTTPException(status_code=422, detail="NOTE E DICITURE non è una categoria valida per un costo di gruppo")
    tipo = "fb" if categoria in CATEGORIE_FOOD_BEVERAGE else "generale"
    if not 1 <= body.mese <= 12:
        raise HTTPException(status_code=400, detail="mese non valido")
    importo = round(float(body.importo_totale or 0), 2)
    if importo <= 0:
        raise HTTPException(status_code=400, detail="importo non valido")

    if body.regola == "percentuali":
        quote = _quote_percentuali(importo, body.percentuali or {}, {str(s["id"]) for s in sedi}, categoria)
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi], categoria)

    riparto_id = _crea_riparto_con_quote(
        sb, user_id, "manuale", None, None,
        body.descrizione.strip() or "Costo di gruppo",
        importo, tipo, body.anno, body.mese, body.regola, quote,
    )

    _post_scrittura_riparto(sb, user_id, body.anno, body.mese)
    return {"ok": True, "riparto_id": riparto_id, "quote": quote}


# ATTENZIONE ALL'ORDINE: questa rotta LETTERALE deve stare prima di
# PATCH /api/riparto/{riparto_id}. FastAPI risolve le rotte nell'ordine di
# dichiarazione, non per specificita': con la parametrica davanti, ogni
# PATCH /api/riparto/riga-categoria finiva in riparto_modifica con
# riparto_id="riga-categoria", e Postgres rispondeva
# `invalid input syntax for type uuid` (22P02). Non spostarla piu' in basso.
@router.patch("/api/riparto/riga-categoria", dependencies=[Depends(_verify_worker_key)])
def riparto_riga_categoria(
    body: RipartoRigaCategoriaBody, authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Corregge la categoria di una riga appartenente a un costo ripartito sul gruppo.

    Perché serve un endpoint dedicato invece di /api/fatture/categoria-batch: le righe
    di una fattura di struttura vivono sulla SEDE TECNICA ("Costi comuni di gruppo"),
    non sul punto vendita. categoria-batch filtra per ristorante_id del PV → match su 0
    righe, e il cliente vedeva un falso successo. La sede tecnica non è selezionabile
    (account.py: non ci si può posizionare sulla sede-contenitore), quindi senza questa
    rotta la categoria di una riga ripartita non era correggibile da nessuna UI.

    Dopo la scrittura le quote vanno RI-ESPLOSE (forza=True): i pesi delle categorie
    sono cambiati e le quote porterebbero ancora quella vecchia, instradando l'importo
    nel secchio MOL sbagliato (F&B vs spese).
    """
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    user_id = str(user["id"])
    _require_catena(user_id, sb)

    try:
        nuova_cat = normalizza_categoria_richiesta(body.nuova_categoria)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    file_origine = (body.file_origine or "").strip()
    descrizione = (body.descrizione or "").strip()
    if not file_origine or not descrizione:
        raise HTTPException(status_code=400, detail="file_origine e descrizione sono obbligatori")

    # Un costo di gruppo MANUALE non ha file_origine (è NULL in tabella): le righe
    # sintetiche proiettate ricevono il sentinella "riparto:<uuid>"
    # (riparto_service._proietta_quote). Cercarlo per file_origine darebbe sempre 404,
    # e non esistono righe reali in `fatture` da aggiornare: qui la categoria vive solo
    # sulle quote, che riscriviamo direttamente.
    if file_origine.startswith(_SENTINELLA_RIPARTO_MANUALE):
        riparto_id = file_origine[len(_SENTINELLA_RIPARTO_MANUALE):]
        return _correggi_categoria_costo_manuale(sb, user_id, riparto_id, nuova_cat)

    rip_resp = (
        sb.table("riparto_costi_catena")
        .select("id, anno, mese")
        .eq("user_id", user_id)
        .eq("file_origine", file_origine)
        .limit(1)
        .execute()
    ).data or []
    if not rip_resp:
        raise HTTPException(status_code=404, detail="Nessun costo di gruppo per questo documento")
    riparto = rip_resp[0]

    righe = fetch_all(
        sb.table("fatture")
        .select("id, totale_riga, prezzo_unitario")
        .eq("user_id", user_id)
        .eq("file_origine", file_origine)
        .eq("descrizione", descrizione)
        .is_("deleted_at", "null")
    )
    if not righe:
        # Riga SINTETICA di quota (_proietta_riparto: nessuna riga reale per quella
        # categoria, storico purgato o quota legacy): la sua descrizione è generata,
        # non esiste in `fatture`, quindi il lookup sopra non può trovarla. Non è un
        # errore del cliente: la categoria di quelle righe vive solo sulle quote,
        # esattamente come per un costo manuale — stessa scrittura, stessa funzione.
        if descrizione.startswith(_DESCR_QUOTA_PREFIX) or descrizione == _DESCR_QUOTA_GENERICA:
            return _correggi_categoria_costo_manuale(sb, user_id, str(riparto["id"]), nuova_cat)
        raise HTTPException(status_code=404, detail="Riga non trovata nel documento di gruppo")

    # Guardrail dominio #2: "📝 NOTE E DICITURE" solo su righe a importo zero.
    target_ids = [r["id"] for r in righe]
    if nuova_cat == "📝 NOTE E DICITURE":
        target_ids = [r["id"] for r in righe if importo_riga_per_guardrail(r) == 0]
        if not target_ids:
            raise HTTPException(
                status_code=422,
                detail="NOTE E DICITURE non applicabile: la riga ha importo diverso da zero.",
            )

    res = (
        sb.table("fatture")
        .update({"categoria": nuova_cat, "needs_review": False})
        .in_("id", target_ids)
        .execute()
    )
    righe_aggiornate = len(res.data or [])

    # Le quote portano ancora la categoria vecchia: ricalcolarle sui pesi aggiornati.
    try:
        from services.riparto_service import esplodi_quote_per_categoria
        esplodi_quote_per_categoria(sb, user_id, str(riparto["id"]), file_origine, forza=True)
    except Exception as exc:
        logger.warning(
            "ri-esplosione post-correzione categoria fallita riparto=%s: %s", riparto["id"], exc
        )

    ricalcolo_ok = _post_scrittura_riparto(sb, user_id, int(riparto["anno"]), int(riparto["mese"]))

    sedi = _carica_sedi_attive(user_id, sb)
    return {
        "ok": True,
        "categoria": nuova_cat,
        "righe_aggiornate": righe_aggiornate,
        "ricalcolo_quote_ok": ricalcolo_ok,
        "sedi_impattate": [s.get("nome_ristorante") for s in sedi],
    }


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
        quote = _quote_percentuali(importo, body.percentuali or {}, {str(s["id"]) for s in sedi})
    else:
        quote = _quote_equa(importo, [str(s["id"]) for s in sedi])

    # Aggiorna padre + rimpiazza le quote in una transazione (RPC
    # sostituisci_quote_riparto, migration 20260805220000): se l'insert delle
    # nuove quote fallisse dopo il delete delle vecchie, senza transazione il
    # riparto resterebbe senza quote — "orfano" invisibile al motore MOL
    # (stessa classe dell'incidente FASTWEB del 22/7), qui sul lato modifica
    # invece che creazione. Le quote scritte sono sempre monolitiche
    # (categoria=None): se il riparto era per-categoria va ri-esploso subito
    # dopo, altrimenti la RPC mensile instrada tutto l'importo in un solo
    # secchio F&B/spese invece che per categoria (regressione sul MOL).
    sb.rpc("sostituisci_quote_riparto", {
        "p_riparto_id": riparto_id, "p_user_id": user_id,
        "p_tipo": tipo, "p_regola": regola, "p_importo_totale": importo,
        "p_quote": quote,
    }).execute()
    if rip["origine"] == "fattura" and rip.get("file_origine"):
        try:
            from services.riparto_service import esplodi_quote_per_categoria
            esplodi_quote_per_categoria(sb, user_id, riparto_id, rip["file_origine"])
        except Exception as exc:
            logger.warning("esplosione quote per categoria fallita (resta legacy) riparto=%s: %s", riparto_id, exc)

    _post_scrittura_riparto(sb, user_id, int(rip["anno"]), int(rip["mese"]))
    return {"ok": True, "quote": quote}


@router.delete("/api/riparto/{riparto_id}", dependencies=[Depends(_verify_worker_key)])
def riparto_elimina(riparto_id: str, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Elimina un riparto. Se da fattura → smarca le righe (il costo torna intero
    sulla sede intestataria). Le quote spariscono via ON DELETE CASCADE.

    Unico endpoint di scrittura del router che NON chiama _require_catena — per
    scelta, non dimenticanza (audit §1, 5/8/2026): se una catena scende sotto 2
    sedi, gli altri endpoint di scrittura si bloccano con 400 e i riparti
    esistenti diventano non modificabili/non duplicabili, ma devono restare
    eliminabili (altrimenti l'utente non avrebbe più modo di ripulirli).
    L'ownership resta comunque garantita dal doppio .eq("id").eq("user_id")."""
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
            .eq("user_id", user_id).eq("file_origine", rip["file_origine"]) \
            .is_("deleted_at", "null").execute()

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

    # `categoria` inclusa: senza, un riparto per-categoria duplicato ricadrebbe nel
    # modello legacy monolitico (stessa classe del fix HIGH su riparto_modifica).
    quote = (
        sb.table("riparto_costi_catena_quote").select("ristorante_id, quota_perc, quota_importo, categoria")
        .eq("riparto_id", riparto_id).execute()
    ).data or []
    if not quote:
        raise HTTPException(status_code=400, detail="Riparto senza quote: nulla da duplicare")

    # Mese successivo (con rollover anno).
    anno, mese = int(rip["anno"]), int(rip["mese"])
    if mese == 12:
        anno_n, mese_n = anno + 1, 1
    else:
        anno_n, mese_n = anno, mese + 1

    nuovo_id = _crea_riparto_con_quote(
        sb, user_id, "manuale", None, None,
        rip["descrizione"], float(rip["importo_totale"]), rip["tipo"], anno_n, mese_n, rip["regola"],
        quote,
    )

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


@router.get("/api/admin/riparto/incoerenze", dependencies=[Depends(_verify_worker_key)])
def riparto_incoerenze() -> Dict[str, Any]:
    """Diagnostica sola lettura (Voce 7, 27/7): incoerenze fra fatture di gruppo e
    riparto_costi_catena, per account. Legge v_riparto_incoerenze (migration
    20260727230000). Due classi possibili, mai sommabili in un unico numero perché
    hanno impatto opposto sul MOL:

    NOTA (audit §1, 5/8/2026): nonostante il prefisso /api/admin/*, questo è
    l'unico endpoint del router gatato da _verify_worker_key (chiave macchina)
    invece che da _verify_admin (identità admin) — voluto: il consumatore
    dichiarato è il workflow GitHub Actions riparto_coerenza_check.yml (codice
    macchina, non un admin che naviga /admin), e ritorna dati aggregati di TUTTI
    gli account senza filtro per chiamante. Se in futuro si volesse esporlo alla
    pagina /admin, va aggiunto _verify_admin — il gate attuale non basterebbe.

      - orfano: fattura viva marcata ripartita_su_gruppo ma senza riparto → costo
        sparito dal MOL (buco).
      - riparto_senza_documento: riparto senza più righe vive dietro → costo fantasma
        ancora contato dal MOL (materializzato in margini_mensili).
      - riparto_senza_quote: header senza alcuna quota → il costo non arriva a nessuna
        sede (né MOL né Analisi Fatture). Caso AUTOSTRADE luglio 2026.
      - riparto_segno_incoerente: header di segno opposto al netto reale delle righe →
        nota di credito (TD04) ripartita come costo: il gruppo la paga invece di
        riceverla. Le ultime due aggiunte da 20260827214500.

    Usato dal workflow GitHub Actions riparto_coerenza_check.yml (alert Telegram
    quando il totale è > 0) e disponibile per ispezione manuale. Non corregge nulla:
    la correzione resta un passo esplicito separato."""
    sb = _get_supabase_client()
    righe = sb.table("v_riparto_incoerenze").select("*").execute().data or []

    # Una chiave per tipo_incoerenza. Mai un `else` catch-all: un tipo nuovo aggiunto
    # alla view finirebbe silenziosamente nel secchio sbagliato e l'alert direbbe una
    # cosa per un'altra.
    _SECCHI = {
        "orfano": "orfani",
        "riparto_senza_documento": "riparti_senza_documento",
        "riparto_senza_quote": "riparti_senza_quote",
        "riparto_segno_incoerente": "riparti_segno_incoerente",
    }

    per_account: Dict[str, Dict[str, Any]] = {}
    for r in righe:
        uid = str(r["user_id"])
        acc = per_account.setdefault(
            uid, {"user_id": uid, **{k: [] for k in _SECCHI.values()}, "altro": []}
        )
        voce = {
            "file_origine": r.get("file_origine"),
            "riparto_id": r.get("riparto_id"),
            "fornitore": r.get("fornitore"),
            "importo": float(r["importo"]) if r.get("importo") is not None else None,
            "data_documento": r.get("data_documento"),
        }
        tipo = r.get("tipo_incoerenza")
        secchio = _SECCHI.get(tipo)
        if secchio:
            acc[secchio].append(voce)
        else:
            acc["altro"].append({**voce, "tipo_incoerenza": tipo})

    return {
        "totale": len(righe),
        "account": list(per_account.values()),
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
        # Stessa forma della risposta piena: un consumatore non deve dedurre l'assenza
        # dei campi dal fatto che il mese è vuoto.
        return {
            "anno": anno, "mese": mese, "costi": [], "totale": 0.0,
            "da_classificare_importo": 0.0, "da_classificare_costi": 0,
            "da_classificare_non_correggibili": 0,
        }

    ids = [c["id"] for c in costi]
    quote = (
        sb.table("riparto_costi_catena_quote")
        .select("riparto_id, ristorante_id, quota_perc, quota_importo, categoria")
        .in_("riparto_id", ids)
        .execute()
    ).data or []

    # Dal 24/7 le quote sono per (sede × categoria): una fattura mista ne genera
    # n_sedi × n_categorie. Elencarle piatte mostrava la stessa sede ripetuta 9 volte
    # con la sua percentuale replicata (nove "50%" che sommano 450%). Qui si aggrega:
    # l'IMPORTO si somma, la PERCENTUALE è quella della sede e si prende una volta sola.
    # Il dettaglio per categoria resta disponibile a parte, per chi vuole aprirlo.
    agg_sede: Dict[str, Dict[str, Dict[str, float]]] = {}
    agg_cat: Dict[str, Dict[str, float]] = {}
    for q in quote:
        rip_id = q["riparto_id"]
        rid = str(q["ristorante_id"])
        importo = float(q["quota_importo"] or 0)
        sede = agg_sede.setdefault(rip_id, {}).setdefault(
            rid, {"perc": 0.0, "importo": 0.0}
        )
        sede["perc"] = max(sede["perc"], float(q["quota_perc"] or 0))
        sede["importo"] += importo
        # Una quota senza categoria NON si scarta: il suo importo entra comunque nel
        # MOL (con categoria NULL non si passa da _riparto_categoria_is_fb, vale il
        # `tipo` dell'header), quindi scartarla qui la rendeva invisibile proprio al
        # conteggio che deve segnalarla. Va sotto una chiave sentinella, tenuta fuori
        # da dettaglio_categorie che elenca categorie reali.
        cat = (q.get("categoria") or "").strip() or _SENZA_CATEGORIA
        per_cat = agg_cat.setdefault(rip_id, {})
        per_cat[cat] = per_cat.get(cat, 0.0) + importo

    quote_by_rip: Dict[str, List[Dict[str, Any]]] = {}
    for rip_id, sedi_agg in agg_sede.items():
        quote_by_rip[rip_id] = [
            {
                "ristorante_id": rid,
                "sede": nomi.get(rid, "—"),
                "quota_perc": round(v["perc"], 3),
                "quota_importo": round(v["importo"], 2),
            }
            for rid, v in sedi_agg.items()
        ]

    # La sentinella resta fuori: dettaglio_categorie è un elenco di categorie reali,
    # e mostrarne una inventata la farebbe sembrare una classificazione avvenuta.
    dettaglio_by_rip: Dict[str, List[Dict[str, Any]]] = {
        rip_id: sorted(
            (
                {"categoria": c, "importo": round(i, 2)}
                for c, i in per_cat.items()
                if c != _SENZA_CATEGORIA
            ),
            key=lambda d: d["importo"],
            reverse=True,
        )
        for rip_id, per_cat in agg_cat.items()
    }

    # Righe reali dei documenti di gruppo (vivono sulla sede tecnica): alimentano il
    # dropdown di correzione categoria dentro la finestra Costi di gruppo.
    file_origini = [c["file_origine"] for c in costi if c.get("file_origine")]
    righe_by_file: Dict[str, List[Dict[str, Any]]] = {}
    if file_origini:
        # fetch_all e non .execute(): PostgREST tronca a 1000 righe in silenzio, e con
        # più documenti di gruppo nel mese le righe oltre la millesima sparirebbero dal
        # dropdown di correzione (stessa classe di bug già pagata su "Da Classificare").
        righe = fetch_all(
            sb.table("fatture")
            .select("id, file_origine, descrizione, categoria, totale_riga, needs_review")
            .eq("user_id", user_id)
            .in_("file_origine", file_origini)
            .is_("deleted_at", "null")
        )
        for r in righe:
            righe_by_file.setdefault(r["file_origine"], []).append({
                "id": r["id"],
                "descrizione": r.get("descrizione"),
                "categoria": r.get("categoria"),
                "totale_riga": float(r.get("totale_riga") or 0),
                "needs_review": bool(r.get("needs_review")),
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
            "dettaglio_categorie": dettaglio_by_rip.get(c["id"], []),
            "righe": righe_by_file.get(c.get("file_origine") or "", []),
        })

    # Quote non classificate: a differenza delle righe fattura normali (escluse dal
    # MOL), una quota "Da Classificare" ENTRA nel secchio spese — è l'unico posto in
    # cui quel costo esiste, la riga d'origine è già esclusa come ripartita_su_gruppo.
    # L'asimmetria è voluta (vedi 20260724220000_riparto_quote_per_categoria.sql), ma
    # va resa visibile: finché non si classifica, il costo pesa sul secchio sbagliato.
    #
    # Si contano DUE stati, non uno: "Da Classificare" (l'AI non ha saputo decidere) e
    # categoria NULL (l'esplosione per-categoria non è mai avvenuta, perché la fattura
    # d'origine non ha righe vive). Per chi legge sono lo stesso problema — "questo
    # costo non ha una categoria" — e distinguerli in UI significherebbe spiegare un
    # dettaglio interno. Il secondo però è più insidioso: non passa nemmeno da
    # _riparto_categoria_is_fb, finisce nel secchio del `tipo` dell'header senza che
    # nulla lo dichiari.
    _NON_CLASSIFICATE = (_CATEGORIA_NON_CLASSIFICATA, _SENZA_CATEGORIA)

    def _quota_non_classificata(per_cat: Dict[str, float]) -> float:
        return sum(per_cat.get(k, 0.0) for k in _NON_CLASSIFICATE)

    da_classificare = round(
        sum(_quota_non_classificata(per_cat) for per_cat in agg_cat.values()), 2
    )
    n_costi_da_classificare = sum(
        1 for per_cat in agg_cat.values() if _quota_non_classificata(per_cat)
    )

    # Quanti fra questi NON sono sistemabili dal dropdown: le quote si correggono
    # agendo sulle righe del documento, quindi un costo che non ne ha (o che non ha
    # proprio un file d'origine) lascia l'utente senza alcuna azione possibile. Il
    # frontend cambia il testo dell'avviso invece di dare un'istruzione ineseguibile.
    n_costi_non_correggibili = sum(
        1
        for c in out
        if _quota_non_classificata(agg_cat.get(c["id"], {})) and not c["righe"]
    )

    return {
        "anno": anno,
        "mese": mese,
        "costi": out,
        "totale": round(tot, 2),
        "da_classificare_importo": da_classificare,
        "da_classificare_costi": n_costi_da_classificare,
        "da_classificare_non_correggibili": n_costi_non_correggibili,
    }
