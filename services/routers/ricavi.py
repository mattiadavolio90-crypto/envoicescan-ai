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


class RicaviBatchUpsertRequest(BaseModel):
    items: List[RicavoUpsertRequest]
    source: str = "manuale"
    source_meta: Optional[Dict[str, Any]] = None


class RicaviBatchUpsertResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []


class RicaviImportXlsResponse(BaseModel):
    parsed_rows: int
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []
    preview: List[RicavoGiornalieroItem] = []


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
        .select("id,data,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva,source")
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
            rows_to_upsert.append({
                "user_id": user["id"],
                "ristorante_id": ristorante_id,
                "data": d,
                "fatturato_iva10": iva10,
                "fatturato_iva22": iva22,
                "altri_ricavi_noiva": altri,
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

    if gestionale_version == "passbi_v1":
        items, errors, parsed_rows = _parse_passbi_v1(raw_df, ristorante_id, sb)
    else:
        items, errors, parsed_rows = _parse_generico(raw_df)

    if not items:
        return RicaviImportXlsResponse(parsed_rows=parsed_rows, inserted=0, updated=0,
                                       skipped=parsed_rows, errors=errors or ["Nessuna riga valida"])

    batch_req = RicaviBatchUpsertRequest(
        items=items,
        source="xls",
        source_meta={"filename": file.filename or "", "gestionale": gestionale_version},
    )
    batch_res = await asyncio.to_thread(upsert_ricavi_batch, batch_req, authorization=authorization)

    preview = [RicavoGiornalieroItem(
        data=it.data,
        fatturato_iva10=it.fatturato_iva10,
        fatturato_iva22=it.fatturato_iva22,
        altri_ricavi_noiva=it.altri_ricavi_noiva,
        source="xls",
    ) for it in items[:10]]

    return RicaviImportXlsResponse(
        parsed_rows=parsed_rows,
        inserted=batch_res.inserted,
        updated=batch_res.updated,
        skipped=batch_res.skipped + (parsed_rows - len(items)),
        errors=errors + batch_res.errors,
        preview=preview,
    )


# ─── Parser gestionale (condivisi con worker/email_queue_processor.py) ─────────
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

    def _to_float(v) -> float:
        if v is None:
            return 0.0
        import pandas as pd
        if isinstance(v, float) and pd.isna(v):
            return 0.0
        try:
            return max(0.0, float(str(v).replace(",", ".")))
        except Exception:
            return 0.0

    # Aggrega per (ristorante_id, data) → {iva10, iva22, altri}
    aggregato: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {"iva10": 0.0, "iva22": 0.0, "altri": 0.0})
    warnings_ragione: set = set()
    errors: List[str] = []

    for i, row in data_rows.iterrows():
        vals = row.tolist()

        # Scarta footer (data vuota + importo non vuoto)
        raw_data_val = vals[idx_data] if idx_data < len(vals) else None
        data_iso = _parse_date(raw_data_val)
        if data_iso is None:
            continue

        importo = _to_float(vals[idx_importo] if idx_importo < len(vals) else None)
        if importo <= 0:
            continue

        # Risolvi ristorante
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

        tipo_doc = str(vals[idx_tipo]).strip().lower() if idx_tipo is not None and idx_tipo < len(vals) else ""
        raw_iva = vals[idx_iva] if idx_iva is not None and idx_iva < len(vals) else None
        iva_str = "" if raw_iva is None or (isinstance(raw_iva, float) and pd.isna(raw_iva)) else str(raw_iva).strip()

        key = (target_ristorante, data_iso)

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
            else:
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
        # Salva lordi; il calcolo netto avviene in lettura con scorporo
        items.append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=round(buckets["iva10"], 4),
            fatturato_iva22=round(buckets["iva22"], 4),
            altri_ricavi_noiva=round(buckets["altri"], 4),
        ))

    if giorni_altri_ristoranti:
        errors.append(
            f"{giorni_altri_ristoranti} giorni di altri ristoranti (mappati via ragione sociale) "
            f"ignorati: importa il file dal ristorante corrispondente."
        )

    return items, errors, parsed_rows


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

        items.append(RicavoUpsertRequest(
            data=data_iso,
            fatturato_iva10=iva10,
            fatturato_iva22=iva22,
            altri_ricavi_noiva=altri,
        ))

    return items, errors, len(df)


# ── Modalità ricavi mensili ──────────────────────────────────────────────────
class RicaviModalitaResponse(BaseModel):
    anno: int
    mese: int
    modalita: str  # "giornaliero" | "mensile"
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0


class RicaviModalitaUpsertRequest(BaseModel):
    anno: int
    mese: int
    modalita: str = "giornaliero"
    fatturato_iva10: float = 0.0
    fatturato_iva22: float = 0.0
    altri_ricavi_noiva: float = 0.0


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

    resp = (
        sb.table("ricavi_modalita_mensile")
        .select("anno,mese,modalita,fatturato_iva10,fatturato_iva22,altri_ricavi_noiva")
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
        )
    return RicaviModalitaResponse(anno=anno, mese=mese, modalita="giornaliero")


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
    )
