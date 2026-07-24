"""Router dominio RICAVI — giornalieri, batch, import XLS (Passbi/generico), modalità.

Estratto da fastapi_worker.py. Include i parser gestionale
(_detect_gestionale_version, _parse_passbi_v1, _parse_generico): erano nel worker
e importati da worker/email_queue_processor.py — ora quel modulo li importa da qui.

ATTENZIONE al ciclo ricavi <-> fastapi_worker: questo modulo e' l'UNICO router
importato anche FUORI dal contesto FastAPI (dal worker, per i parser). fastapi_worker
importa `from services.routers.ricavi import router` in coda al file; se importassimo
fastapi_worker AL TOP qui, il worker (che carica ricavi.py per primo) esploderebbe con
"partially initialized module" e il ciclo email non processerebbe mai la coda ricavi.
Per questo i simboli di fastapi_worker sotto sono risolti LAZY (helper `_fw()`).
Path/gate/response invariati.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from config.logger_setup import get_logger

logger = get_logger("router_ricavi")

# NB: import LAZY di fastapi_worker per evitare il ciclo
# ricavi -> fastapi_worker -> ricavi. Il worker (worker/email_queue_processor.py)
# importa da questo modulo SOLO i parser (_detect_gestionale_version, _parse_*),
# fuori dal contesto FastAPI: importare fastapi_worker al top esplodeva con
# "partially initialized module" e il ciclo email non processava mai la coda.
# I 4 simboli sotto servono solo agli endpoint HTTP, risolti al primo uso quando
# fastapi_worker e' gia' caricato.
def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _resolve_ristorante_id(*args, **kwargs):
    return _fw()._resolve_ristorante_id(*args, **kwargs)


# Usato in Depends(...) nei decorator (valutato a import-time): non puo' essere
# lazy come gli altri. La firma DEVE restare identica all'originale (x_worker_key
# via Header) perche' FastAPI inietta il valore leggendo la signature; delega poi
# al verificatore reale di fastapi_worker, risolto al primo uso.
def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)


router = APIRouter()


class RicavoGiornalieroItem(BaseModel):
    id: Optional[str] = None
    data: str  # YYYY-MM-DD
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    coperti: Optional[int] = None  # None = non pervenuto, distinto da 0 reale
    source: str = "manuale"


class RicaviGiornalieriResponse(BaseModel):
    items: List[RicavoGiornalieroItem]
    totale_iva10: float
    totale_iva22: float
    totale_altri: float
    totale_netto: float
    giorni_con_dati: int


class RicavoUpsertRequest(BaseModel):
    data: str
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    coperti: Optional[int] = None


class RicaviBatchUpsertRequest(BaseModel):
    items: List[RicavoUpsertRequest]
    source: str = "manuale"
    source_meta: Optional[Dict[str, Any]] = None


class RicaviBatchUpsertResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []


class RicaviImportSedeDettaglio(BaseModel):
    ristorante_id: str
    nome: Optional[str] = None
    giorni: int = 0
    coperti_giorni: int = 0


class RicaviImportXlsResponse(BaseModel):
    parsed_rows: int
    inserted: int
    updated: int
    skipped: int
    coperti_giorni: int = 0   # giorni importati con coperti valorizzati
    errors: List[str] = []
    preview: List[RicavoGiornalieroItem] = []
    # Catene: ripartizione per sede (multi-ristorante via ragione sociale).
    dettaglio_sedi: List[RicaviImportSedeDettaglio] = []


def _calc_netto(iva10: float, iva22: float, altri: float) -> float:
    return round((iva10 / 1.10) + (iva22 / 1.22) + altri, 2)


@router.get("/api/ricavi/giornalieri", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def get_ricavi_giornalieri(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> RicaviGiornalieriResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    resp = (
        sb.table("ricavi_giornalieri")
        .select("id,data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti,source")
        .eq("ristorante_id", ristorante_id)
        .gte("data", data_da)
        .lte("data", data_a)
        .order("data", desc=False)
        .execute()
    )
    rows = resp.data or []

    items = [
        RicavoGiornalieroItem(
            id=str(r.get("id")),
            data=str(r.get("data")),
            fatturato_iva10=float(r.get("fatturato_iva10") or 0),
            fatturato_iva22=float(r.get("fatturato_iva22") or 0),
            altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
            coperti=(int(r["coperti"]) if r.get("coperti") is not None else None),
            source=str(r.get("source") or "manuale"),
        )
        for r in rows
    ]

    tot10 = sum(x.fatturato_iva10 for x in items)
    tot22 = sum(x.fatturato_iva22 for x in items)
    tot_altri = sum(x.altri_ricavi_noiva for x in items)

    return RicaviGiornalieriResponse(
        items=items,
        totale_iva10=round(tot10, 2),
        totale_iva22=round(tot22, 2),
        totale_altri=round(tot_altri, 2),
        totale_netto=_calc_netto(tot10, tot22, tot_altri),
        giorni_con_dati=len(items),
    )


@router.post("/api/ricavi/giornalieri", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def upsert_ricavo_giornaliero(
    body: RicavoUpsertRequest,
    authorization: Optional[str] = Header(None),
) -> RicavoGiornalieroItem:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    payload = {
        "user_id": user["id"],
        "ristorante_id": ristorante_id,
        "data": body.data,
        "fatturato_iva10": max(0.0, float(body.fatturato_iva10)),
        "fatturato_iva22": max(0.0, float(body.fatturato_iva22)),
        "altri_ricavi_noiva": max(0.0, float(body.altri_ricavi_noiva)),
        "coperti": (max(0, int(body.coperti)) if body.coperti is not None else None),
        "source": "manuale",
    }

    resp = (
        sb.table("ricavi_giornalieri")
        .upsert(payload, on_conflict="ristorante_id,data")
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Salvataggio fallito")

    r = resp.data[0]
    return RicavoGiornalieroItem(
        id=str(r.get("id")),
        data=str(r.get("data")),
        fatturato_iva10=float(r.get("fatturato_iva10") or 0),
        fatturato_iva22=float(r.get("fatturato_iva22") or 0),
        altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
        coperti=(int(r["coperti"]) if r.get("coperti") is not None else None),
        source=str(r.get("source") or "manuale"),
    )


@router.delete("/api/ricavi/giornalieri", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def delete_ricavo_giornaliero(
    data: str,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    sb.table("ricavi_giornalieri").delete()\
      .eq("ristorante_id", ristorante_id)\
      .eq("data", data).execute()
    return {"deleted": True, "data": data}


@router.post("/api/ricavi/batch", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def upsert_ricavi_batch(
    body: RicaviBatchUpsertRequest,
    authorization: Optional[str] = Header(None),
) -> RicaviBatchUpsertResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    inserted = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    source = body.source if body.source in ("manuale", "xls", "email") else "manuale"

    # Pre-check esistenti per contare inserted vs updated
    if body.items:
        dates = [it.data for it in body.items]
        existing = (
            sb.table("ricavi_giornalieri")
            .select("data")
            .eq("ristorante_id", ristorante_id)
            .in_("data", dates)
            .execute()
        )
        existing_set = {str(r["data"]) for r in (existing.data or [])}
    else:
        existing_set = set()

    rows_to_upsert = []
    for it in body.items:
        try:
            d = it.data
            if not d:
                skipped += 1
                continue
            iva10 = max(0.0, float(it.fatturato_iva10 or 0))
            iva22 = max(0.0, float(it.fatturato_iva22 or 0))
            altri = max(0.0, float(it.altri_ricavi_noiva or 0))
            if iva10 + iva22 + altri <= 0:
                skipped += 1
                continue
            coperti = (max(0, int(it.coperti)) if it.coperti is not None else None)
            rows_to_upsert.append({
                "user_id": user["id"],
                "ristorante_id": ristorante_id,
                "data": d,
                "fatturato_iva10": iva10,
                "fatturato_iva22": iva22,
                "altri_ricavi_noiva": altri,
                "coperti": coperti,
                "source": source,
                "source_meta": body.source_meta or None,
            })
        except Exception as e:
            errors.append(f"riga {it.data}: {e}")

    if rows_to_upsert:
        try:
            resp = (
                sb.table("ricavi_giornalieri")
                .upsert(rows_to_upsert, on_conflict="ristorante_id,data")
                .execute()
            )
            for row in (resp.data or []):
                if str(row.get("data")) in existing_set:
                    updated += 1
                else:
                    inserted += 1
        except Exception as e:
            errors.append(f"upsert: {e}")

    # Nuovi ricavi -> lo snapshot briefing di oggi e' stantio (l'apertura
    # positiva "ieri sono entrati €X" dipende da questi dati). Lo invalidiamo
    # cosi' al prossimo load si rigenera. Best-effort: non blocca l'upsert.
    if inserted or updated:
        try:
            from services.daily_briefing_service import invalidate_today_briefing
            invalidate_today_briefing(str(user["id"]), str(ristorante_id), sb)
        except Exception as exc:
            logger.warning("upsert_ricavi_batch: invalidate briefing fallita: %s", exc)

    return RicaviBatchUpsertResponse(
        inserted=inserted, updated=updated, skipped=skipped, errors=errors,
    )


@router.post("/api/ricavi/import-xls", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
async def import_ricavi_xls(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
) -> RicaviImportXlsResponse:
    """Importa ricavi giornalieri da XLS/XLSX.

    Riconosce automaticamente il formato del gestionale:
      - Passbi v1: colonne Data|Ragione sociale|Tipo documento|Codice (IVA)|Importo
      - Generico: colonne data|iva10|iva22|altri (formato precedente)
    """
    import io as _io
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    content = await file.read()
    filename = (file.filename or "ricavi.xlsx").lower()

    try:
        if filename.endswith(".csv"):
            raw_df = pd.read_csv(_io.BytesIO(content), sep=None, engine="python", header=None)
        else:
            raw_df = pd.read_excel(_io.BytesIO(content), engine="openpyxl", header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File non leggibile: {e}")

    if raw_df.empty:
        return RicaviImportXlsResponse(parsed_rows=0, inserted=0, updated=0, skipped=0,
                                       errors=["File vuoto"])

    # ── Riconoscimento versione gestionale ───────────────────────────────────
    gestionale_version = _detect_gestionale_version(raw_df)
    source_meta = {"filename": file.filename or "", "gestionale": gestionale_version}

    if gestionale_version == "passbi_v1":
        # Multi-sede: un file di catena alimenta tutti i locali dell'account in un
        # colpo solo (smistamento via ragione sociale). Le righe senza ragione
        # sociale mappata ricadono sul ristorante del token (fallback).
        per_ristorante, errors, parsed_rows = _parse_passbi_v1_multisede(
            raw_df, ristorante_id, user["id"], sb
        )
    else:
        # Generico: niente colonna ragione sociale → tutto sul ristorante del token.
        items, errors, parsed_rows = _parse_generico(raw_df)
        per_ristorante = {ristorante_id: items} if items else {}

    total_items = sum(len(v) for v in per_ristorante.values())
    if not per_ristorante:
        return RicaviImportXlsResponse(parsed_rows=parsed_rows, inserted=0, updated=0,
                                       skipped=parsed_rows, errors=errors or ["Nessuna riga valida"])

    # Nomi sedi per il dettaglio (1 query). Best-effort: il dettaglio è informativo.
    nomi_sedi: Dict[str, str] = {}
    try:
        rids = list(per_ristorante.keys())
        nome_resp = sb.table("ristoranti").select("id,nome_ristorante").in_("id", rids).execute()
        nomi_sedi = {str(r["id"]): r.get("nome_ristorante") for r in (nome_resp.data or [])}
    except Exception:
        pass

    inserted = 0
    updated = 0
    upsert_errors: List[str] = []
    dettaglio_sedi: List[RicaviImportSedeDettaglio] = []
    for rid, items in per_ristorante.items():
        ins, upd, errs = await asyncio.to_thread(
            _upsert_ricavi_ristorante, sb, rid, user["id"], items, source_meta, nomi_sedi.get(rid)
        )
        inserted += ins
        updated += upd
        upsert_errors.extend(errs)
        dettaglio_sedi.append(RicaviImportSedeDettaglio(
            ristorante_id=rid,
            nome=nomi_sedi.get(rid),
            giorni=len(items),
            coperti_giorni=sum(1 for it in items if it.coperti is not None),
        ))
    dettaglio_sedi.sort(key=lambda d: (d.nome or d.ristorante_id))

    # Preview: prime 10 righe della prima sede (informativa).
    first_items = next(iter(per_ristorante.values()), [])
    preview = [RicavoGiornalieroItem(
        data=it.data,
        fatturato_iva10=it.fatturato_iva10,
        fatturato_iva22=it.fatturato_iva22,
        altri_ricavi_noiva=it.altri_ricavi_noiva,
        coperti=it.coperti,
        source="xls",
    ) for it in first_items[:10]]

    coperti_giorni = sum(
        1 for items in per_ristorante.values() for it in items if it.coperti is not None
    )

    return RicaviImportXlsResponse(
        parsed_rows=parsed_rows,
        inserted=inserted,
        updated=updated,
        skipped=max(0, parsed_rows - total_items),
        coperti_giorni=coperti_giorni,
        errors=errors + upsert_errors,
        preview=preview,
        dettaglio_sedi=dettaglio_sedi,
    )


# ─── Parser gestionale (condivisi con worker/email_queue_processor.py) ─────────
def _to_float_it(v) -> float:
    """Converte un importo it-IT (es. "2.450,00") in float, clampato a >= 0.

    Prima ogni parser Passbi (qui e in worker/email_queue_processor.py) faceva
    solo .replace(",", ".") : su un importo con separatore delle migliaia
    ("2.450,00" -> "2.450.00") float() solleva, l'except silenzioso ritorna 0.0
    e la riga/giorno viene scartata a valle (if importo <= 0: continue). Bug
    live su qualsiasi giorno con incasso >= 1000 € (footer reali verificati:
    367.159,76 / 9.869.784,247 — sempre in questo formato).
    Regola: se c'e' una virgola e' il separatore decimale -> i punti prima sono
    migliaia e vanno rimossi; se non c'e' virgola il valore e' gia' un numero
    semplice (es. "12.5") e non va toccato.
    """
    if v is None:
        return 0.0
    import pandas as pd
    if isinstance(v, float) and pd.isna(v):
        return 0.0
    s = str(v).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return max(0.0, float(s))
    except Exception:
        return 0.0


def _detect_gestionale_version(raw_df) -> str:
    """Identifica il formato del file dal contenuto della prima riga."""
    import pandas as pd
    first_row_vals = [str(v).strip().lower() for v in raw_df.iloc[0].tolist() if pd.notna(v)]
    # Passbi v1: prima cella contiene "oneflux export" oppure le colonne header
    # tipiche sono data/ragione sociale/tipo documento
    combined = " ".join(first_row_vals)
    if "oneflux export" in combined:
        return "passbi_v1"
    # Controlla anche la riga header (riga 3 in Passbi v1)
    if len(raw_df) >= 4:
        header_row = [str(v).strip().lower() for v in raw_df.iloc[3].tolist() if str(v).strip()]
        header_combined = " ".join(header_row)
        if "ragione sociale" in header_combined or "tipo documento" in header_combined:
            return "passbi_v1"
    return "generico"


def _parse_passbi_v1(raw_df, ristorante_id: str, sb) -> tuple:
    """
    Parser per Passbi v1.
    Struttura: righe 0-2 header/metadati, riga 3 colonne, righe 4..N dati, ultima riga footer.
    Colonne: Data | Ragione sociale | Tipo documento | Codice (IVA) | Importo
    Regole mapping:
      - tipo_doc 'proforma' o vuoto, oppure IVA vuota → altri_ricavi_noiva (importo = netto già)
      - tipo_doc 'fattura'/'scontrino' + IVA 10 → fatturato_iva10 (lordo, scorporare)
      - tipo_doc 'fattura'/'scontrino' + IVA 22 → fatturato_iva22 (lordo, scorporare)
    """
    import pandas as pd
    from datetime import date, datetime as _dt
    from collections import defaultdict

    # Trova la riga header: non basta "data" in una cella (le righe di metadati
    # tipo "Data generazione" / "Dati export" la contengono). Cerchiamo la riga
    # che contiene PIU' intestazioni attese contemporaneamente, con almeno 2 match.
    _HEADER_TOKENS = ("data", "importo", "totale", "tipo documento", "ragione sociale", "azienda", "codice")
    header_idx = None
    best_score = 0
    for i, row in raw_df.iterrows():
        vals = [str(v).strip().lower() for v in row.tolist()]
        joined = " | ".join(vals)
        # "data" deve comparire come intestazione di colonna, non come parte di frase
        has_data_col = any(v == "data" or v.startswith("data ") or v.endswith(" data") for v in vals)
        score = sum(1 for tok in _HEADER_TOKENS if tok in joined)
        if has_data_col and score >= 2 and score > best_score:
            best_score = score
            header_idx = i
    if header_idx is None:
        # Fallback prudente: riga 3 e' la posizione standard dell'header Passbi v1
        if len(raw_df) > 3:
            header_idx = 3
        else:
            return [], ["Header colonne non trovato nel file Passbi"], len(raw_df)

    headers = [str(v).strip() for v in raw_df.iloc[header_idx].tolist()]
    data_rows = raw_df.iloc[header_idx + 1:].reset_index(drop=True)
    parsed_rows = len(data_rows)

    # Mappa colonne per nome (tollerante a newline e varianti)
    def _find_col(names: list) -> Optional[int]:
        for i, h in enumerate(headers):
            norm = h.lower().replace("\n", " ").replace("  ", " ").strip()
            for n in names:
                if n in norm:
                    return i
        return None

    idx_data = _find_col(["data"])
    idx_ragione = _find_col(["ragione sociale", "azienda"])
    idx_tipo = _find_col(["tipo documento", "testata", "tipo_documento"])
    idx_iva = _find_col(["codice", "iva"])
    idx_importo = _find_col(["importo", "totale"])
    idx_coperti = _find_col(["coperti"])  # colonna opzionale (Passbi v1 con coperti)

    if idx_data is None or idx_importo is None:
        return [], ["Colonne Data o Importo non trovate nel file Passbi"], parsed_rows

    # Carica mapping ragione_sociale → ristorante_id
    mapping_resp = sb.table("ricavi_ragione_sociale_map").select("ragione_sociale_norm,ristorante_id").execute()
    ragione_map: Dict[str, str] = {
        str(r["ragione_sociale_norm"]).strip().lower(): str(r["ristorante_id"])
        for r in (mapping_resp.data or [])
    }

    def _parse_date(v) -> Optional[str]:
        from datetime import date as _date, datetime as _dt2
        if isinstance(v, (_date, _dt)):
            d = v.date() if isinstance(v, _dt) else v
            return d.isoformat()
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return _dt.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    _to_float = _to_float_it

    # Aggrega per (ristorante_id, data) → {iva10, iva22, altri, coperti}.
    # I coperti Passbi sono frazionari PER RIGA (ripartizione proporzionale): si
    # accumulano come float e si arrotondano a intero solo sull'aggregato del
    # giorno (somma di tutti i tipi documento). 'coperti_seen' distingue "nessuna
    # riga aveva la colonna" (→ None) da "somma 0" reale.
    aggregato: Dict[tuple, Dict[str, float]] = defaultdict(
        lambda: {"iva10": 0.0, "iva22": 0.0, "altri": 0.0, "coperti": 0.0}
    )
    coperti_seen: set = set()
    warnings_ragione: set = set()
    errors: List[str] = []

    for i, row in data_rows.iterrows():
        vals = row.tolist()

        # Scarta footer (data vuota + importo non vuoto)
        raw_data_val = vals[idx_data] if idx_data < len(vals) else None
        data_iso = _parse_date(raw_data_val)
        if data_iso is None:
            continue

        # Risolvi ristorante PRIMA del check importo: una riga con importo 0/negativo
        # (proforma annullata, nota di credito) puo' comunque avere coperti valorizzati
        # per quel giorno — se il continue scattasse qui sotto prima di leggere i
        # coperti, quel valore andrebbe perso anche se altre righe dello stesso
        # giorno hanno importo positivo (bug reale confermato su file SushiLand).
        raw_ragione = str(vals[idx_ragione]).strip() if idx_ragione is not None and idx_ragione < len(vals) else ""
        import pandas as pd
        if not raw_ragione or raw_ragione.lower() in ("nan", "none"):
            target_ristorante = ristorante_id
        else:
            norm_ragione = raw_ragione.lower().strip()
            target_ristorante = ragione_map.get(norm_ragione)
            if target_ristorante is None:
                warnings_ragione.add(raw_ragione)
                target_ristorante = ristorante_id  # fallback: usa ristorante corrente

        key = (target_ristorante, data_iso)

        # Coperti: somma su tutti i tipi documento del giorno (frazionari per riga),
        # letti indipendentemente dall'importo della riga.
        if idx_coperti is not None and idx_coperti < len(vals):
            cop_val = vals[idx_coperti]
            if not (cop_val is None or (isinstance(cop_val, float) and pd.isna(cop_val))):
                try:
                    aggregato[key]["coperti"] += float(str(cop_val).replace(",", "."))
                    coperti_seen.add(key)
                except (ValueError, TypeError):
                    pass

        importo = _to_float(vals[idx_importo] if idx_importo < len(vals) else None)
        if importo <= 0:
            continue

        tipo_doc = str(vals[idx_tipo]).strip().lower() if idx_tipo is not None and idx_tipo < len(vals) else ""
        raw_iva = vals[idx_iva] if idx_iva is not None and idx_iva < len(vals) else None
        iva_str = "" if raw_iva is None or (isinstance(raw_iva, float) and pd.isna(raw_iva)) else str(raw_iva).strip()

        # Applica regole mapping
        if tipo_doc in ("proforma", "") or iva_str == "":
            aggregato[key]["altri"] += importo
        else:
            try:
                iva_val = int(float(iva_str))
            except (ValueError, TypeError):
                aggregato[key]["altri"] += importo
                continue
            if iva_val == 10:
                aggregato[key]["iva10"] += importo
            elif iva_val == 22:
                aggregato[key]["iva22"] += importo
            elif iva_val > 0:
                # Aliquote reali diverse da 10/22 (es. 4%, 5%) non hanno una colonna
                # dedicata in ricavi_giornalieri: finiscono in "altri", MA quel campo
                # e' trattato ovunque a valle (calcolo netto/MOL) come gia' netto,
                # senza scorporo. Un importo lordo con IVA 4/5 sommato li' gonfiava
                # il netto della differenza IVA. Scorporiamo qui, prima di sommarlo.
                aggregato[key]["altri"] += importo / (1 + iva_val / 100)
            else:
                # iva_val == 0 (o negativo, non atteso): nessuna IVA, importo gia' netto.
                aggregato[key]["altri"] += importo

    if warnings_ragione:
        errors.append(f"Ragioni sociali non mappate (usato ristorante corrente): {', '.join(sorted(warnings_ragione))}")

    # L'import salva solo sul ristorante corrente. Le righe mappate ad altri
    # ristoranti vengono ignorate (il batch upsert non sa scrivere su ristoranti
    # diversi da quello del token): l'utente importa il file dal ristorante giusto.
    items: List[RicavoUpsertRequest] = []
    giorni_altri_ristoranti = 0
    for (rid, data_iso), buckets in aggregato.items():
        if buckets["iva10"] + buckets["iva22"] + buckets["altri"] <= 0:
            continue
        if rid != ristorante_id:
            giorni_altri_ristoranti += 1
            continue
        # Salva lordi; il calcolo netto avviene in lettura con scorporo.
        # Coperti: intero solo sull'aggregato; None se il giorno non aveva la colonna.
        coperti_giorno = round(buckets["coperti"]) if (rid, data_iso) in coperti_seen else None
        items.append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=round(buckets["iva10"], 4),
            fatturato_iva22=round(buckets["iva22"], 4),
            altri_ricavi_noiva=round(buckets["altri"], 4),
            coperti=coperti_giorno,
        ))

    if giorni_altri_ristoranti:
        errors.append(
            f"{giorni_altri_ristoranti} giorni di altri ristoranti (mappati via ragione sociale) "
            f"ignorati: importa il file dal ristorante corrispondente."
        )

    return items, errors, parsed_rows


def _parse_passbi_v1_multisede(raw_df, fallback_ristorante_id: str, user_id, sb) -> tuple:
    """Parser Passbi v1 per import manuale di CATENE multi-sede.

    A differenza di _parse_passbi_v1 (che collassa tutto sul ristorante del token),
    smista ogni riga sul ristorante corretto via ragione sociale — così un singolo
    file di una catena alimenta tutti i locali in un colpo solo. Stessa logica del
    parser email (_parse_passbi_email), riusata qui per la UI.

    Sicurezza: ogni ristorante_id di destinazione DEVE appartenere allo stesso
    user_id dell'account che importa. Righe mappate a ristoranti di altri utenti
    vengono scartate (difesa contro un mapping errato che scriverebbe dati altrui).

    Ritorna (per_ristorante: dict[rid -> list[RicavoUpsertRequest]], errors, parsed_rows).
    """
    import pandas as pd
    from datetime import date as _date, datetime as _dt
    from collections import defaultdict

    _HEADER_TOKENS = ("data", "importo", "totale", "tipo documento", "ragione sociale", "azienda", "codice")
    header_idx = None
    best_score = 0
    for i, row in raw_df.iterrows():
        vals = [str(v).strip().lower() for v in row.tolist()]
        joined = " | ".join(vals)
        has_data_col = any(v == "data" or v.startswith("data ") or v.endswith(" data") for v in vals)
        score = sum(1 for tok in _HEADER_TOKENS if tok in joined)
        if has_data_col and score >= 2 and score > best_score:
            best_score = score
            header_idx = i
    if header_idx is None:
        if len(raw_df) > 3:
            header_idx = 3
        else:
            return {}, ["Header colonne non trovato nel file Passbi"], len(raw_df)

    headers = [str(v).strip() for v in raw_df.iloc[header_idx].tolist()]
    data_rows = raw_df.iloc[header_idx + 1:].reset_index(drop=True)
    parsed_rows = len(data_rows)

    def _find_col(names: list) -> Optional[int]:
        for i, h in enumerate(headers):
            norm = h.lower().replace("\n", " ").replace("  ", " ").strip()
            for n in names:
                if n in norm:
                    return i
        return None

    idx_data = _find_col(["data"])
    idx_ragione = _find_col(["ragione sociale", "azienda"])
    idx_tipo = _find_col(["tipo documento", "testata", "tipo_documento"])
    idx_iva = _find_col(["codice", "iva"])
    idx_importo = _find_col(["importo", "totale"])
    idx_coperti = _find_col(["coperti"])

    if idx_data is None or idx_importo is None:
        return {}, ["Colonne Data o Importo non trovate nel file Passbi"], parsed_rows

    # Mapping ragione_sociale → ristorante_id, filtrato sui ristoranti di QUESTO
    # account. Il filtro su ristoranti.user_id è la barriera di sicurezza: una
    # ragione sociale che punta a un ristorante di un altro utente non entra.
    try:
        owned = sb.table("ristoranti").select("id").eq("user_id", user_id).execute()
        owned_ids = {str(r["id"]) for r in (owned.data or [])}
    except Exception as exc:
        return {}, [f"Lookup ristoranti utente fallito: {exc}"], parsed_rows
    if not owned_ids:
        return {}, [f"Utente {user_id} non ha ristoranti: import scartato"], parsed_rows

    ragione_map: Dict[str, str] = {}
    try:
        mp = sb.table("ricavi_ragione_sociale_map").select("ragione_sociale_norm,ristorante_id").execute()
        for r in (mp.data or []):
            rid = str(r["ristorante_id"])
            if rid in owned_ids:
                ragione_map[str(r["ragione_sociale_norm"]).strip().lower()] = rid
    except Exception as exc:
        return {}, [f"Lookup mapping ragione sociale fallito: {exc}"], parsed_rows

    def _parse_date(v) -> Optional[str]:
        if isinstance(v, (_date, _dt)):
            d = v.date() if isinstance(v, _dt) else v
            return d.isoformat()
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return _dt.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    _to_float = _to_float_it

    aggregato: Dict[tuple, Dict[str, float]] = defaultdict(
        lambda: {"iva10": 0.0, "iva22": 0.0, "altri": 0.0, "coperti": 0.0}
    )
    coperti_seen: set = set()
    unmapped: set = set()
    foreign: set = set()
    errors: List[str] = []

    for _, row in data_rows.iterrows():
        vals = row.tolist()

        data_iso = _parse_date(vals[idx_data] if idx_data < len(vals) else None)
        if data_iso is None:
            continue

        # Risolvi ristorante + guardia ownership PRIMA del check importo: una riga
        # con importo 0/negativo puo' comunque avere coperti valorizzati per quel
        # giorno — se il continue scattasse prima di leggerli, si perderebbero anche
        # se altre righe dello stesso giorno hanno importo positivo (bug reale
        # confermato su file SushiLand). L'ownership resta invariata: deve girare
        # PRIMA di scrivere in aggregato[key], indipendentemente dall'importo.
        raw_ragione = ""
        if idx_ragione is not None and idx_ragione < len(vals):
            raw_ragione = str(vals[idx_ragione]).strip()

        if not raw_ragione or raw_ragione.lower() in ("nan", "none"):
            target = fallback_ristorante_id
        else:
            target = ragione_map.get(raw_ragione.lower().strip())
            if target is None:
                unmapped.add(raw_ragione)
                target = fallback_ristorante_id

        if target not in owned_ids:
            foreign.add(str(target))
            continue

        key = (target, data_iso)

        if idx_coperti is not None and idx_coperti < len(vals):
            cop_val = vals[idx_coperti]
            if not (cop_val is None or (isinstance(cop_val, float) and pd.isna(cop_val))):
                try:
                    aggregato[key]["coperti"] += float(str(cop_val).replace(",", "."))
                    coperti_seen.add(key)
                except (ValueError, TypeError):
                    pass

        importo = _to_float(vals[idx_importo] if idx_importo < len(vals) else None)
        if importo <= 0:
            continue

        tipo_doc = ""
        if idx_tipo is not None and idx_tipo < len(vals):
            tipo_doc = str(vals[idx_tipo]).strip().lower()
        raw_iva = vals[idx_iva] if (idx_iva is not None and idx_iva < len(vals)) else None
        iva_str = "" if raw_iva is None or (isinstance(raw_iva, float) and pd.isna(raw_iva)) else str(raw_iva).strip()

        if tipo_doc in ("proforma", "") or iva_str == "":
            aggregato[key]["altri"] += importo
        else:
            try:
                iva_val = int(float(iva_str))
            except (ValueError, TypeError):
                aggregato[key]["altri"] += importo
                continue
            if iva_val == 10:
                aggregato[key]["iva10"] += importo
            elif iva_val == 22:
                aggregato[key]["iva22"] += importo
            elif iva_val > 0:
                # Aliquote reali diverse da 10/22 (es. 4%, 5%): niente colonna
                # dedicata, finiscono in "altri" che a valle e' sempre trattato
                # come gia' netto (nessuno scorporo) — un lordo qui gonfiava il
                # netto/MOL della differenza IVA. Scorporiamo prima di sommare.
                aggregato[key]["altri"] += importo / (1 + iva_val / 100)
            else:
                aggregato[key]["altri"] += importo

    if unmapped:
        errors.append(f"Ragioni sociali non mappate (usato ristorante corrente): {', '.join(sorted(unmapped))}")
    if foreign:
        errors.append(f"{len(foreign)} ristoranti di altri utenti ignorati (sicurezza ownership)")

    per_ristorante: Dict[str, List[RicavoUpsertRequest]] = defaultdict(list)
    for (rid, data_iso), b in aggregato.items():
        if b["iva10"] + b["iva22"] + b["altri"] <= 0:
            continue
        coperti_giorno = round(b["coperti"]) if (rid, data_iso) in coperti_seen else None
        per_ristorante[rid].append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=round(b["iva10"], 4),
            fatturato_iva22=round(b["iva22"], 4),
            altri_ricavi_noiva=round(b["altri"], 4),
            coperti=coperti_giorno,
        ))

    return dict(per_ristorante), errors, parsed_rows


def _upsert_ricavi_ristorante(sb, ristorante_id: str, user_id, items, source_meta, nome_ristorante: Optional[str] = None) -> tuple:
    """Upsert dei ricavi di UN ristorante con user_id/ristorante_id espliciti.

    Usato dall'import manuale multi-sede (la UI può scrivere su sedi diverse da
    quella del token, purché appartengano allo stesso account: la verifica avviene
    a monte in _parse_passbi_v1_multisede). Ritorna (inserted, updated, errors).

    nome_ristorante e' opzionale (solo per messaggi errore leggibili): se
    fallisce l'upsert di una sede su piu', il cliente vedeva un UUID crittico
    invece del nome del locale nella risposta import-xls.
    """
    _sede_label = nome_ristorante or ristorante_id
    inserted = 0
    updated = 0
    errors: List[str] = []
    if not items:
        return 0, 0, errors

    dates = [it.data for it in items if it.data]
    existing_set: set = set()
    if dates:
        try:
            existing = (
                sb.table("ricavi_giornalieri")
                .select("data")
                .eq("ristorante_id", ristorante_id)
                .in_("data", dates)
                .execute()
            )
            existing_set = {str(r["data"]) for r in (existing.data or [])}
        except Exception as exc:
            errors.append(f"pre-check {_sede_label}: {exc}")

    rows_to_upsert = []
    for it in items:
        if not it.data:
            continue
        iva10 = max(0.0, float(it.fatturato_iva10 or 0))
        iva22 = max(0.0, float(it.fatturato_iva22 or 0))
        altri = max(0.0, float(it.altri_ricavi_noiva or 0))
        if iva10 + iva22 + altri <= 0:
            continue
        coperti = (max(0, int(it.coperti)) if it.coperti is not None else None)
        rows_to_upsert.append({
            "user_id": user_id,
            "ristorante_id": ristorante_id,
            "data": it.data,
            "fatturato_iva10": iva10,
            "fatturato_iva22": iva22,
            "altri_ricavi_noiva": altri,
            "coperti": coperti,
            "source": "xls",
            "source_meta": source_meta or None,
        })

    if rows_to_upsert:
        try:
            resp = (
                sb.table("ricavi_giornalieri")
                .upsert(rows_to_upsert, on_conflict="ristorante_id,data")
                .execute()
            )
            for row in (resp.data or []):
                if str(row.get("data")) in existing_set:
                    updated += 1
                else:
                    inserted += 1
        except Exception as exc:
            errors.append(f"upsert {_sede_label}: {exc}")

    if inserted or updated:
        try:
            from services.daily_briefing_service import invalidate_today_briefing
            invalidate_today_briefing(str(user_id), str(ristorante_id), sb)
        except Exception as exc:
            logger.warning("_upsert_ricavi_ristorante: invalidate briefing fallita: %s", exc)

    return inserted, updated, errors


def _parse_generico(raw_df) -> tuple:
    """Parser generico per file con colonne data|iva10|iva22|altri (formato precedente)."""
    import pandas as pd
    from datetime import date, datetime as _dt

    df = raw_df.copy()
    # Prova a usare prima riga come header se sembra tale
    first_row = [str(v).strip().lower() for v in df.iloc[0].tolist()]
    if any(v in ("data", "date", "giorno") for v in first_row):
        df.columns = first_row
        df = df.iloc[1:].reset_index(drop=True)
    else:
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    col_data = next((c for c in df.columns if c in ("data", "date", "giorno", "data_documento")), None)
    col_iva10 = next((c for c in df.columns if c in ("iva10", "iva_10", "fatturato_iva10")), None)
    col_iva22 = next((c for c in df.columns if c in ("iva22", "iva_22", "fatturato_iva22")), None)
    col_altri = next((c for c in df.columns if c in ("altri", "altri_ricavi", "altri_ricavi_noiva", "noiva")), None)
    col_coperti = next((c for c in df.columns if c in ("coperti", "coperti_ristorante", "covers")), None)

    if not col_data:
        return [], ["Colonna 'data' non trovata"], len(df)

    items: List[RicavoUpsertRequest] = []
    errors: List[str] = []

    def _f(v) -> float:
        try:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return 0.0
            return max(0.0, float(str(v).replace(",", ".")))
        except Exception:
            return 0.0

    for idx, row in df.iterrows():
        raw_data = row.get(col_data)
        try:
            if isinstance(raw_data, (_dt,)):
                data_iso = raw_data.date().isoformat()
            elif hasattr(raw_data, "isoformat"):
                data_iso = raw_data.isoformat()
            else:
                s = str(raw_data).strip()
                if not s or s.lower() in ("nan", "none", ""):
                    continue
                parsed = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
                    try:
                        parsed = _dt.strptime(s, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    errors.append(f"riga {idx + 2}: data non riconosciuta '{s}'")
                    continue
                data_iso = parsed.isoformat()
        except Exception as e:
            errors.append(f"riga {idx + 2}: {e}")
            continue

        iva10 = _f(row.get(col_iva10)) if col_iva10 else 0.0
        iva22 = _f(row.get(col_iva22)) if col_iva22 else 0.0
        altri = _f(row.get(col_altri)) if col_altri else 0.0

        if iva10 + iva22 + altri <= 0:
            continue

        coperti = None
        if col_coperti:
            cop_raw = row.get(col_coperti)
            if not (cop_raw is None or (isinstance(cop_raw, float) and pd.isna(cop_raw))):
                try:
                    coperti = max(0, round(float(str(cop_raw).replace(",", "."))))
                except (ValueError, TypeError):
                    coperti = None

        items.append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=iva10,
            fatturato_iva22=iva22,
            altri_ricavi_noiva=altri,
            coperti=coperti,
        ))

    return items, errors, len(df)


# ── Analisi COPERTI ───────────────────────────────────────────────────────────
# Endpoint dedicato che alimenta il tab "Coperti" in un'unica fetch (come
# /api/margini/analisi per Marginalità). Calcolo tutto lato worker: tab = solo
# mensili; il dettaglio giornaliero (grafico + giorno top/fiacco + media per
# giorno-settimana) si calcola dai giornalieri ma è esposto qui per il widget.
_MESI_SHORT = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
               "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


class CopertiMese(BaseModel):
    anno: int
    mese: int
    label: str
    coperti: Optional[int] = None
    ricavi_netto: float = 0.0
    ricavi_lordo: float = 0.0
    scontrino_medio_netto: Optional[float] = None
    scontrino_medio_lordo: Optional[float] = None
    costo_fb: float = 0.0
    # Costo materia prima per coperto (efficienza): None se mancano coperti/costi
    costo_fb_per_coperto: Optional[float] = None


class CopertiGiorno(BaseModel):
    data: str            # YYYY-MM-DD
    coperti: int
    ricavi_netto: float
    ricavi_lordo: float


class CopertiKpi(BaseModel):
    coperti_totali: Optional[int] = None
    coperti_medi_giorno: Optional[float] = None
    scontrino_medio_netto: Optional[float] = None
    scontrino_medio_lordo: Optional[float] = None
    giorno_top: Optional[CopertiGiorno] = None
    giorno_min: Optional[CopertiGiorno] = None
    media_per_dow: List[Optional[float]] = []   # lun..dom (7 valori), None = no dati
    delta_coperti_pct: Optional[float] = None   # vs periodo precedente di pari durata
    confronto_label: str = "periodo prec."
    # ── Efficienza materia prima (analisi spreco per scostamento) ──
    costo_fb_per_coperto: Optional[float] = None      # media periodo
    costo_fb_per_coperto_delta_pct: Optional[float] = None  # trend: ultimo vs primo mese
    efficienza_commento: Optional[str] = None         # lettura sintetica del trend


class CopertiAnalisiResponse(BaseModel):
    mesi: List[CopertiMese]
    totale_coperti: Optional[int] = None
    totale_ricavi_netto: float = 0.0
    totale_ricavi_lordo: float = 0.0
    giorni: List[CopertiGiorno]                 # solo giorni con coperti > 0
    ha_dati_giornalieri: bool = False
    kpi: CopertiKpi


def _scontrino(ricavi: float, coperti: Optional[int]) -> Optional[float]:
    if not coperti or coperti <= 0 or ricavi <= 0:
        return None
    return round(ricavi / coperti, 2)


def _somma_coperti_periodo(sb, fw, ristorante_id: str, d_da, d_a) -> int:
    """Somma coperti nel periodo [d_da, d_a] dalla STESSA fonte del tab:
    margini_mensili (aggregato del trigger) con override mensile per i mesi in
    modalità 'mensile'. Coerente col calcolo del periodo corrente."""
    mesi: List[tuple] = []
    yy, mm = d_da.year, d_da.month
    while (yy, mm) <= (d_a.year, d_a.month):
        mesi.append((yy, mm))
        mm += 1
        if mm > 12:
            yy += 1
            mm = 1
    annos = sorted({y for y, _ in mesi}) or [d_da.year]
    resp = (
        sb.table("margini_mensili")
        .select("anno,mese,coperti")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    cop = {(int(r["anno"]), int(r["mese"])): (int(r["coperti"]) if r.get("coperti") is not None else None)
           for r in (resp.data or [])}
    overrides = fw._load_mensile_overrides(sb, ristorante_id, annos)
    for (y, m), ov in overrides.items():
        if ov.get("coperti") is not None:
            cop[(y, m)] = ov["coperti"]
    return sum((cop.get((y, m)) or 0) for (y, m) in mesi)


@router.get("/api/ricavi/coperti-analisi", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def get_coperti_analisi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> CopertiAnalisiResponse:
    from datetime import date as _date, datetime as _dt, timedelta as _td

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        d_da = _dt.strptime(data_da, "%Y-%m-%d").date()
        d_a = _dt.strptime(data_a, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date non valide (YYYY-MM-DD)")

    fw = _fw()

    # ── Mensile: stesso percorso del fatturato (margini_mensili + override) ──
    mesi_target: List[tuple] = []
    yy, mm = d_da.year, d_da.month
    while (yy, mm) <= (d_a.year, d_a.month):
        mesi_target.append((yy, mm))
        mm += 1
        if mm > 12:
            yy += 1
            mm = 1
    annos = sorted({y for y, _ in mesi_target}) or [d_da.year]

    margini_resp = (
        sb.table("margini_mensili")
        .select("anno,mese,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    margini_map = {(int(r["anno"]), int(r["mese"])): r for r in (margini_resp.data or [])}
    overrides = fw._load_mensile_overrides(sb, ristorante_id, annos)

    # Costi F&B per mese, STESSA fonte del tab Marginalità (riuso, niente N+1):
    # garantisce che "costo F&B/coperto" sia coerente con "Costi F&B (Fatture)".
    try:
        costi_fb_map = fw._calcola_costi_auto_per_periodo(sb, ristorante_id, mesi_target)
    except Exception as exc:
        logger.warning("coperti-analisi: costi F&B non calcolati: %s", exc)
        costi_fb_map = {}

    mesi_out: List[CopertiMese] = []
    tot_coperti = 0
    tot_coperti_seen = False
    tot_netto = 0.0
    tot_lordo = 0.0
    tot_fb = 0.0
    for (y, m) in mesi_target:
        r = margini_map.get((y, m), {})
        ov = overrides.get((y, m))
        if ov:
            iva10, iva22, altri = ov["iva10"], ov["iva22"], ov["altri"]
            coperti = ov.get("coperti")
        else:
            iva10 = float(r.get("fatturato_iva10") or 0)
            iva22 = float(r.get("fatturato_iva22") or 0)
            altri = float(r.get("altri_ricavi_noiva") or 0)
            coperti = (int(r["coperti"]) if r.get("coperti") is not None else None)
        lordo = iva10 + iva22 + altri
        netto = round((iva10 / 1.10) + (iva22 / 1.22) + altri, 2)
        fb = float((costi_fb_map.get((y, m)) or (0.0, 0.0))[0])
        # Mostra solo mesi con qualche dato (ricavi o coperti)
        if lordo <= 0 and not coperti:
            continue
        # Costo materia prima per coperto: solo se ho sia coperti che costo F&B.
        cfb_per_cop = (round(fb / coperti, 2) if (coperti and coperti > 0 and fb > 0) else None)
        mesi_out.append(CopertiMese(
            anno=y, mese=m, label=f"{_MESI_SHORT[m]} {y}",
            coperti=coperti,
            ricavi_netto=netto,
            ricavi_lordo=round(lordo, 2),
            scontrino_medio_netto=_scontrino(netto, coperti),
            scontrino_medio_lordo=_scontrino(lordo, coperti),
            costo_fb=round(fb, 2),
            costo_fb_per_coperto=cfb_per_cop,
        ))
        tot_netto += netto
        tot_lordo += lordo
        tot_fb += fb
        if coperti is not None:
            tot_coperti += coperti
            tot_coperti_seen = True

    # ── Giornaliero: per widget dettaglio (giorno top/fiacco, media per dow) ──
    gio_resp = (
        sb.table("ricavi_giornalieri")
        .select("data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti")
        .eq("ristorante_id", ristorante_id)
        .gte("data", data_da)
        .lte("data", data_a)
        .order("data", desc=False)
        .execute()
    )
    giorni_out: List[CopertiGiorno] = []
    dow_acc: List[List[int]] = [[] for _ in range(7)]  # lun..dom
    for gr in (gio_resp.data or []):
        cop = gr.get("coperti")
        if cop is None or int(cop) <= 0:
            continue
        cop = int(cop)
        i10 = float(gr.get("fatturato_iva10") or 0)
        i22 = float(gr.get("fatturato_iva22") or 0)
        alt = float(gr.get("altri_ricavi_noiva") or 0)
        lordo = i10 + i22 + alt
        netto = round((i10 / 1.10) + (i22 / 1.22) + alt, 2)
        ds = str(gr.get("data"))
        giorni_out.append(CopertiGiorno(
            data=ds, coperti=cop, ricavi_netto=netto, ricavi_lordo=round(lordo, 2),
        ))
        try:
            dow = _dt.strptime(ds, "%Y-%m-%d").date().weekday()  # 0=lun
            dow_acc[dow].append(cop)
        except ValueError:
            pass

    media_per_dow: List[Optional[float]] = [
        (round(sum(v) / len(v), 1) if v else None) for v in dow_acc
    ]
    giorno_top = max(giorni_out, key=lambda g: g.coperti, default=None)
    giorno_min = min(giorni_out, key=lambda g: g.coperti, default=None)

    coperti_medi_giorno = (
        round(sum(g.coperti for g in giorni_out) / len(giorni_out), 1)
        if giorni_out else None
    )

    # ── Delta coperti vs periodo precedente di pari durata ──
    # Confronto coerente: i coperti del periodo precedente arrivano dalla STESSA
    # fonte di quelli correnti (margini_mensili + override mensile), non solo dai
    # giornalieri — altrimenti un mese in modalità mensile sbilancerebbe il delta.
    delta_pct: Optional[float] = None
    if tot_coperti_seen and tot_coperti > 0:
        durata = (d_a - d_da).days + 1
        prev_a = d_da - _td(days=1)
        prev_da = prev_a - _td(days=durata - 1)
        try:
            prev_cop = _somma_coperti_periodo(sb, fw, ristorante_id, prev_da, prev_a)
            if prev_cop and prev_cop > 0:
                delta_pct = round((tot_coperti - prev_cop) / prev_cop * 100, 1)
        except Exception:
            delta_pct = None

    # ── Efficienza materia prima: costo F&B/coperto medio + trend ──
    # Lo "spreco" non si misura direttamente: emerge come scostamento. Se il
    # costo materia prima per coperto SALE mentre lo scontrino medio resta fermo,
    # stai spendendo di più per servire le stesse persone → spreco/porzioni/cali.
    #
    # IMPORTANTE: la media si calcola SOLO sui mesi che hanno SIA costo F&B SIA
    # coperti. I mesi recenti hanno spesso coperti ma fatture non ancora arrivate
    # (costo F&B = 0): includerli abbasserebbe falsamente il costo/coperto.
    fb_validi = sum(m.costo_fb for m in mesi_out if m.costo_fb_per_coperto is not None)
    cop_validi = sum((m.coperti or 0) for m in mesi_out if m.costo_fb_per_coperto is not None)
    cfb_per_coperto = (
        round(fb_validi / cop_validi, 2) if (cop_validi > 0 and fb_validi > 0) else None
    )
    cfb_delta_pct: Optional[float] = None
    efficienza_commento: Optional[str] = None
    mesi_cfb = [m for m in mesi_out if m.costo_fb_per_coperto is not None]
    if len(mesi_cfb) >= 2:
        primo = mesi_cfb[0].costo_fb_per_coperto or 0
        ultimo = mesi_cfb[-1].costo_fb_per_coperto or 0
        if primo > 0:
            cfb_delta_pct = round((ultimo - primo) / primo * 100, 1)
            # Confronto con il trend dello scontrino medio: se il costo/coperto
            # cresce più di quanto cresca lo speso a testa → campanello spreco.
            sm_primo = mesi_cfb[0].scontrino_medio_netto or 0
            sm_ultimo = mesi_cfb[-1].scontrino_medio_netto or 0
            sm_delta = ((sm_ultimo - sm_primo) / sm_primo * 100) if sm_primo > 0 else 0
            if cfb_delta_pct >= 8 and cfb_delta_pct - sm_delta >= 5:
                efficienza_commento = (
                    f"Il costo materia prima per coperto è salito del {cfb_delta_pct:.0f}% "
                    f"più dello scontrino medio: verifica porzioni, sprechi o prezzi fornitori."
                )
            elif cfb_delta_pct <= -8:
                efficienza_commento = (
                    f"Buon segnale: il costo materia prima per coperto è sceso del {abs(cfb_delta_pct):.0f}% — "
                    f"acquisti più efficienti."
                )
            else:
                efficienza_commento = "Costo materia prima per coperto stabile nel periodo."

    kpi = CopertiKpi(
        coperti_totali=(tot_coperti if tot_coperti_seen else None),
        coperti_medi_giorno=coperti_medi_giorno,
        scontrino_medio_netto=_scontrino(tot_netto, tot_coperti if tot_coperti_seen else None),
        scontrino_medio_lordo=_scontrino(tot_lordo, tot_coperti if tot_coperti_seen else None),
        giorno_top=giorno_top,
        giorno_min=giorno_min,
        media_per_dow=media_per_dow,
        delta_coperti_pct=delta_pct,
        costo_fb_per_coperto=cfb_per_coperto,
        costo_fb_per_coperto_delta_pct=cfb_delta_pct,
        efficienza_commento=efficienza_commento,
    )

    return CopertiAnalisiResponse(
        mesi=mesi_out,
        totale_coperti=(tot_coperti if tot_coperti_seen else None),
        totale_ricavi_netto=round(tot_netto, 2),
        totale_ricavi_lordo=round(tot_lordo, 2),
        giorni=giorni_out,
        ha_dati_giornalieri=len(giorni_out) > 0,
        kpi=kpi,
    )


# ── Costo materia prima per coperto, PER CATEGORIA (dialog approfondimento) ────
# Tabella categoria × mese: costo F&B della categoria nel mese ÷ coperti del mese.
# Solo categorie materia prima reali; SHOP escluso (merce da rivendita, non spreco
# di cucina). Spese generali già fuori (la helper aggrega solo le F&B).
_SHOP_ESCLUSO = {"SHOP"}


class CategoriaCopertoMese(BaseModel):
    anno: int
    mese: int
    label: str
    valore: Optional[float] = None   # €/coperto, None se mese senza coperti/costi


class CategoriaCopertoRiga(BaseModel):
    categoria: str
    per_mese: List[CategoriaCopertoMese]
    media: Optional[float] = None    # costo totale ÷ coperti totali (pesata)


class CopertiCategorieResponse(BaseModel):
    mesi_label: List[str]            # intestazioni colonne (mesi con coperti)
    righe: List[CategoriaCopertoRiga]  # ordinate per media decrescente


@router.get("/api/ricavi/coperti-categorie", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def get_coperti_categorie(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> CopertiCategorieResponse:
    from datetime import datetime as _dt

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    try:
        d_da = _dt.strptime(data_da, "%Y-%m-%d").date()
        d_a = _dt.strptime(data_a, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date non valide (YYYY-MM-DD)")

    fw = _fw()

    # Coperti per mese (stessa fonte del tab): margini_mensili + override mensile.
    mesi_target: List[tuple] = []
    yy, mm = d_da.year, d_da.month
    while (yy, mm) <= (d_a.year, d_a.month):
        mesi_target.append((yy, mm))
        mm += 1
        if mm > 12:
            yy += 1
            mm = 1
    annos = sorted({y for y, _ in mesi_target}) or [d_da.year]

    margini_resp = (
        sb.table("margini_mensili")
        .select("anno,mese,coperti")
        .eq("ristorante_id", ristorante_id)
        .in_("anno", annos)
        .execute()
    )
    cop_map = {
        (int(r["anno"]), int(r["mese"])): (int(r["coperti"]) if r.get("coperti") is not None else None)
        for r in (margini_resp.data or [])
    }
    overrides = fw._load_mensile_overrides(sb, ristorante_id, annos)
    for (y, m), ov in overrides.items():
        if ov.get("coperti") is not None:
            cop_map[(y, m)] = ov["coperti"]

    # Solo i mesi che hanno coperti > 0 (senza coperti il costo/coperto non esiste).
    mesi_con_coperti = [(y, m) for (y, m) in mesi_target if (cop_map.get((y, m)) or 0) > 0]
    if not mesi_con_coperti:
        return CopertiCategorieResponse(mesi_label=[], righe=[])

    # Costo F&B per (anno, mese, categoria). Riuso l'aggregatore del worker.
    try:
        cat_map = fw._load_fatture_fb_per_categoria_e_mese(
            sb, ristorante_id, data_da, data_a,
        )
    except Exception as exc:
        logger.warning("coperti-categorie: aggregazione fatture fallita: %s", exc)
        cat_map = {}

    # Categorie presenti, SHOP escluso.
    categorie = sorted({
        cat for (_, _, cat) in cat_map.keys() if cat not in _SHOP_ESCLUSO
    })

    mesi_label = [f"{_MESI_SHORT[m]} {y}" for (y, m) in mesi_con_coperti]
    righe: List[CategoriaCopertoRiga] = []
    for cat in categorie:
        per_mese: List[CategoriaCopertoMese] = []
        tot_costo = 0.0
        tot_cop = 0
        for (y, m) in mesi_con_coperti:
            cop = cop_map.get((y, m)) or 0
            costo = float(cat_map.get((y, m, cat), 0.0))
            valore = (round(costo / cop, 2) if (cop > 0 and costo > 0) else None)
            per_mese.append(CategoriaCopertoMese(
                anno=y, mese=m, label=f"{_MESI_SHORT[m]} {y}", valore=valore,
            ))
            if costo > 0:
                tot_costo += costo
                tot_cop += cop
        media = (round(tot_costo / tot_cop, 2) if (tot_cop > 0 and tot_costo > 0) else None)
        # Salta categorie senza alcun dato nel periodo
        if media is None and all(pm.valore is None for pm in per_mese):
            continue
        righe.append(CategoriaCopertoRiga(categoria=cat, per_mese=per_mese, media=media))

    # Ordina per media decrescente (la categoria che pesa di più in cima).
    righe.sort(key=lambda r: (r.media if r.media is not None else -1), reverse=True)

    return CopertiCategorieResponse(mesi_label=mesi_label, righe=righe)


# ── Modalità ricavi mensili ──────────────────────────────────────────────────
class RicaviModalitaResponse(BaseModel):
    anno: int
    mese: int
    modalita: str  # "giornaliero" | "mensile"
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    coperti: Optional[int] = None
    # Valori aggregati già presenti in margini_mensili per questo mese, se ci sono.
    # Servono al dialog per precompilare la vista mensile quando i ricavi sono
    # stati caricati direttamente come totali mensili (non da giornalieri né da
    # un override in ricavi_modalita_mensile). Sola informazione, non un override.
    margini_iva10: float = 0.0
    margini_iva22: float = 0.0
    margini_altri: float = 0.0
    margini_coperti: Optional[int] = None


class RicaviModalitaUpsertRequest(BaseModel):
    anno: int
    mese: int
    modalita: str = "giornaliero"
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0
    coperti: Optional[int] = None


@router.get("/api/ricavi/modalita", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def get_ricavi_modalita(
    anno: int,
    mese: int,
    authorization: Optional[str] = Header(None),
) -> RicaviModalitaResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    mm = (
        sb.table("margini_mensili")
        .select("fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    mm_row = mm.data[0] if mm.data else {}
    margini_iva10 = float(mm_row.get("fatturato_iva10") or 0)
    margini_iva22 = float(mm_row.get("fatturato_iva22") or 0)
    margini_altri = float(mm_row.get("altri_ricavi_noiva") or 0)
    margini_coperti = int(mm_row["coperti"]) if mm_row.get("coperti") is not None else None

    resp = (
        sb.table("ricavi_modalita_mensile")
        .select("anno,mese,modalita,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,coperti")
        .eq("ristorante_id", ristorante_id)
        .eq("anno", anno)
        .eq("mese", mese)
        .limit(1)
        .execute()
    )
    if resp.data:
        r = resp.data[0]
        return RicaviModalitaResponse(
            anno=r["anno"], mese=r["mese"],
            modalita=str(r.get("modalita") or "giornaliero"),
            fatturato_iva10=float(r.get("fatturato_iva10") or 0),
            fatturato_iva22=float(r.get("fatturato_iva22") or 0),
            altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
            coperti=(int(r["coperti"]) if r.get("coperti") is not None else None),
            margini_iva10=margini_iva10, margini_iva22=margini_iva22,
            margini_altri=margini_altri, margini_coperti=margini_coperti,
        )
    return RicaviModalitaResponse(
        anno=anno, mese=mese, modalita="giornaliero",
        margini_iva10=margini_iva10, margini_iva22=margini_iva22,
        margini_altri=margini_altri, margini_coperti=margini_coperti,
    )


@router.post("/api/ricavi/modalita", tags=["Ricavi"], dependencies=[Depends(_verify_worker_key)])
def upsert_ricavi_modalita(
    body: RicaviModalitaUpsertRequest,
    authorization: Optional[str] = Header(None),
) -> RicaviModalitaResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    if body.modalita not in ("giornaliero", "mensile"):
        raise HTTPException(status_code=400, detail="modalita deve essere 'giornaliero' o 'mensile'")
    if not 1 <= body.mese <= 12:
        raise HTTPException(status_code=400, detail="mese deve essere tra 1 e 12")

    payload = {
        "ristorante_id": ristorante_id,
        "anno": body.anno,
        "mese": body.mese,
        "modalita": body.modalita,
        "fatturato_iva10": max(0.0, float(body.fatturato_iva10)),
        "fatturato_iva22": max(0.0, float(body.fatturato_iva22)),
        "altri_ricavi_noiva": max(0.0, float(body.altri_ricavi_noiva)),
        "coperti": (max(0, int(body.coperti)) if body.coperti is not None else None),
    }

    resp = (
        sb.table("ricavi_modalita_mensile")
        .upsert(payload, on_conflict="ristorante_id,anno,mese")
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Salvataggio modalità fallito")

    r = resp.data[0]
    return RicaviModalitaResponse(
        anno=r["anno"], mese=r["mese"],
        modalita=str(r.get("modalita") or "giornaliero"),
        fatturato_iva10=float(r.get("fatturato_iva10") or 0),
        fatturato_iva22=float(r.get("fatturato_iva22") or 0),
        altri_ricavi_noiva=float(r.get("altri_ricavi_noiva") or 0),
        coperti=(int(r["coperti"]) if r.get("coperti") is not None else None),
    )
