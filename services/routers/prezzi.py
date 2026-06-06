"""Router dominio PREZZI — variazioni, sconti, omaggi, note di credito, storico.

Estratto da fastapi_worker.py. _load_num_documento_map resta nel worker (usato
anche dalla sezione FATTURE) ed e' importato da qui. Path/gate/response invariati.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services.fastapi_worker import (
    _verify_worker_key,
    _resolve_user_from_token,
    _get_supabase_client,
    _resolve_ristorante_id,
    _load_num_documento_map,
)

router = APIRouter()

_CATEGORIE_SPESE_PREZZI = [
    "SERVIZI E CONSULENZE", "UTENZE E LOCALI",
    "MANUTENZIONE E ATTREZZATURE", "MATERIALE DI CONSUMO",
]
_PRICE_ALERT_DEFAULT = 5.0


class VariazionePrezzo(BaseModel):
    prodotto: str
    categoria: str
    fornitore: str
    storico: str
    media: float
    penultimo: float
    ultimo: float
    aumento_perc: float
    data: str
    n_fattura: str
    trend: str
    impatto_stimato: float
    delta_euro: float


class VariazioniResponse(BaseModel):
    variazioni: List[VariazionePrezzo]
    scostamento_medio: float
    impatto_netto: float
    fornitori_coinvolti: int
    soglia: float


class ScontoOmaggioItem(BaseModel):
    tipo: str
    descrizione: str
    categoria: str
    fornitore: str
    quantita: Optional[float]
    valore: float
    data: str
    numero_documento: str
    fattura: str


class ScontiOmaggiResponse(BaseModel):
    items: List[ScontoOmaggioItem]
    totale_risparmiato: float
    n_sconti: int
    n_omaggi: int


class NotaCreditoItem(BaseModel):
    documento: str
    data: str
    fornitore: str
    descrizione: str
    categoria: str
    quantita: Optional[float]
    credito: float
    numero_documento: str


class NoteCreditoResponse(BaseModel):
    note: List[NotaCreditoItem]
    totale_credito: float
    n_documenti: int


class StoricoPrezzoPoint(BaseModel):
    data: str
    prezzo_unitario: float


class StoricoPrezzoResponse(BaseModel):
    prodotto: str
    fornitore: str
    punti: List[StoricoPrezzoPoint]
    prezzo_medio: float


class SogliaAlertRequest(BaseModel):
    soglia: float


class SogliaAlertResponse(BaseModel):
    soglia: float


def _calcola_variazioni_prezzi_sync(rows: list, soglia: float) -> list:
    import pandas as pd

    if not rows:
        return []

    df = pd.DataFrame(rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce').fillna(1.0)

    df = df[~df['categoria'].isin(_CATEGORIE_SPESE_PREZZI)].copy()
    df = df[df['prezzo_unitario'] > 0].copy()

    if df.empty:
        return []

    df['_desc_key'] = df['descrizione'].astype(str).str.strip().str.upper()
    df['_forn_key'] = df['fornitore'].astype(str).str.strip().str.upper()

    alert_list = []

    for (_dk, _fk), group in df.groupby(['_desc_key', '_forn_key']):
        group = group.sort_values('data_documento')
        acquisti = group[group['prezzo_unitario'] > 0].copy()

        if len(acquisti) < 2:
            continue

        ultimo = acquisti.iloc[-1]
        penultimo = acquisti.iloc[-2]
        prezzo_ult = float(ultimo['prezzo_unitario'])
        prezzo_pen = float(penultimo['prezzo_unitario'])
        delta = prezzo_ult - prezzo_pen
        var_pct = (delta / prezzo_pen) * 100

        if abs(var_pct) < soglia:
            continue

        nota = ""
        try:
            d_pen = pd.to_datetime(penultimo['data_documento'], utc=True)
            d_ult = pd.to_datetime(ultimo['data_documento'], utc=True)
            if (d_ult - d_pen).days > 180:
                nota = " ⚠️ >6m"
        except Exception:
            pass

        storico = " → ".join(f"€{p:.2f}" for p in acquisti.tail(5)['prezzo_unitario'])
        media = float(acquisti['prezzo_unitario'].mean())

        prezzi_rec = pd.to_numeric(acquisti['prezzo_unitario'].tail(4), errors='coerce').dropna().tolist()
        var_rec = [
            prezzi_rec[i] - prezzi_rec[i - 1]
            for i in range(1, len(prezzi_rec))
            if abs(prezzi_rec[i] - prezzi_rec[i - 1]) > 0.0001
        ]
        if len(var_rec) >= 3 and all(v > 0 for v in var_rec[-3:]):
            trend = "⬆⬆"
        elif len(var_rec) >= 3 and all(v < 0 for v in var_rec[-3:]):
            trend = "⬇⬇"
        elif var_rec and any(v > 0 for v in var_rec) and any(v < 0 for v in var_rec):
            trend = "↕"
        elif delta > 0:
            trend = "⬆"
        elif delta < 0:
            trend = "⬇"
        else:
            trend = "↕"

        qta_all = pd.to_numeric(acquisti['quantita'], errors='coerce').dropna()
        qta_ref = float(qta_all.mean()) if not qta_all.empty else 1.0

        date_all = pd.to_datetime(acquisti['data_documento'], errors='coerce').dropna().sort_values()
        freq = 1.0
        if len(date_all) >= 2:
            n_mesi = max(1.0, (date_all.iloc[-1] - date_all.iloc[0]).days / 30.0)
            freq = len(date_all) / n_mesi

        alert_list.append({
            'prodotto': (str(group['descrizione'].mode()[0]) + nota)[:60],
            'categoria': str(ultimo.get('categoria', ''))[:25],
            'fornitore': str(group['fornitore'].mode()[0])[:30],
            'storico': storico,
            'media': round(media, 4),
            'penultimo': round(prezzo_pen, 4),
            'ultimo': round(prezzo_ult, 4),
            'aumento_perc': round(var_pct, 2),
            'data': str(ultimo.get('data_documento', '')),
            'n_fattura': str(ultimo.get('file_origine', '')),
            'trend': trend,
            'impatto_stimato': round(float(delta * qta_ref * freq), 2),
            'delta_euro': round(delta, 4),
        })

    alert_list.sort(key=lambda x: x['aumento_perc'], reverse=True)
    return alert_list


def _load_fatture_for_prezzi(
    sb, ristorante_id: str, data_da: str, data_a: str,
    extra_cols: str = "",
) -> list:
    cols = (
        "descrizione,categoria,fornitore,prezzo_unitario,quantita,"
        "totale_riga,data_documento,file_origine,tipo_documento"
        + (f",{extra_cols}" if extra_cols else "")
    )
    all_rows: list = []
    page = 0
    page_size = 1000
    while True:
        resp = (
            sb.table("fatture")
            .select(cols)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gte("data_documento", data_da)
            .lte("data_documento", data_a)
            .order("data_documento", desc=False)
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        page += 1
    return all_rows


def _load_nc_file_origini(sb, ristorante_id: str, data_da: str, data_a: str) -> set:
    """Set di file_origine che sono vere note di credito (segno_compensazione=-1).
    Usato per distinguere sconti su fattura normale (→ Sconti tab) da NC reali.
    """
    resp = (
        sb.table("fatture_documenti")
        .select("file_origine")
        .eq("ristorante_id", ristorante_id)
        .eq("segno_compensazione", -1)
        .is_("deleted_at", "null")
        .gte("data_documento", data_da)
        .lte("data_documento", data_a)
        .execute()
    )
    return {r["file_origine"] for r in (resp.data or [])}


@router.get("/api/prezzi/soglia-alert", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_soglia_alert(
    authorization: Optional[str] = Header(None),
) -> SogliaAlertResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    resp = sb.table("users").select("price_alert_threshold").eq("id", user["id"]).limit(1).execute()
    val = _PRICE_ALERT_DEFAULT
    if resp.data:
        raw = resp.data[0].get("price_alert_threshold")
        if raw is not None:
            try:
                val = max(0.0, min(50.0, float(raw)))
            except (TypeError, ValueError):
                pass
    return SogliaAlertResponse(soglia=val)


@router.post("/api/prezzi/soglia-alert", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def set_soglia_alert(
    body: SogliaAlertRequest,
    authorization: Optional[str] = Header(None),
) -> SogliaAlertResponse:
    user = _resolve_user_from_token(authorization)
    val = max(0.0, min(50.0, float(body.soglia)))
    sb = _get_supabase_client()
    sb.table("users").update({"price_alert_threshold": val}).eq("id", user["id"]).execute()
    return SogliaAlertResponse(soglia=val)


@router.get("/api/prezzi/variazioni", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_variazioni_prezzi(
    data_da: str,
    data_a: str,
    soglia: float = _PRICE_ALERT_DEFAULT,
    authorization: Optional[str] = Header(None),
) -> VariazioniResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    variazioni = _calcola_variazioni_prezzi_sync(all_rows, soglia)

    scostamento_medio = 0.0
    impatto_netto = 0.0
    fornitori: set = set()
    if variazioni:
        pct_vals = [v['aumento_perc'] for v in variazioni]
        scostamento_medio = round(sum(pct_vals) / len(pct_vals), 2)
        impatto_netto = round(sum(v['impatto_stimato'] for v in variazioni), 2)
        fornitori = {v['fornitore'] for v in variazioni}

    return VariazioniResponse(
        variazioni=[VariazionePrezzo(**v) for v in variazioni],
        scostamento_medio=scostamento_medio,
        impatto_netto=impatto_netto,
        fornitori_coinvolti=len(fornitori),
        soglia=soglia,
    )


@router.get("/api/prezzi/sconti-omaggi", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_sconti_omaggi(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> ScontiOmaggiResponse:
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    if not all_rows:
        return ScontiOmaggiResponse(items=[], totale_risparmiato=0.0, n_sconti=0, n_omaggi=0)

    num_map = _load_num_documento_map(sb, ristorante_id)

    df = pd.DataFrame(all_rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['totale_riga'] = pd.to_numeric(df['totale_riga'], errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce').fillna(1.0)
    df = df[~df['categoria'].isin(_CATEGORIE_SPESE_PREZZI)].copy()

    mask_sconto = (df['prezzo_unitario'] < -1e-9) | (df['totale_riga'] < -1e-9)
    mask_omaggio = (
        ~mask_sconto
        & (df['totale_riga'].abs() < 1e-9)
        & (df['prezzo_unitario'].abs() < 1e-9)
        & (df['descrizione'].astype(str).str.strip().str.len() > 3)
        & (~df['categoria'].astype(str).str.contains("NOTE E DICITURE", na=False))
    )

    df_sconti = df[mask_sconto].copy()
    df_omaggi = df[mask_omaggio].copy()

    items = []
    for _, r in df_sconti.iterrows():
        fo = str(r.get('file_origine', ''))
        items.append(ScontoOmaggioItem(
            tipo="sconto",
            descrizione=str(r.get('descrizione', '')),
            categoria=str(r.get('categoria', '')),
            fornitore=str(r.get('fornitore', '')),
            quantita=float(r['quantita']) if pd.notna(r['quantita']) else None,
            valore=round(abs(float(r['totale_riga'])), 2),
            data=str(r.get('data_documento', '')),
            numero_documento=num_map.get(fo, ''),
            fattura=fo,
        ))
    for _, r in df_omaggi.iterrows():
        fo = str(r.get('file_origine', ''))
        items.append(ScontoOmaggioItem(
            tipo="omaggio",
            descrizione=str(r.get('descrizione', '')),
            categoria=str(r.get('categoria', '')),
            fornitore=str(r.get('fornitore', '')),
            quantita=float(r['quantita']) if pd.notna(r['quantita']) else None,
            valore=0.0,
            data=str(r.get('data_documento', '')),
            numero_documento=num_map.get(fo, ''),
            fattura=fo,
        ))

    items.sort(key=lambda x: x.data, reverse=True)
    totale = round(sum(abs(float(r['totale_riga'])) for _, r in df_sconti.iterrows()), 2)

    return ScontiOmaggiResponse(
        items=items,
        totale_risparmiato=totale,
        n_sconti=len(df_sconti),
        n_omaggi=len(df_omaggi),
    )


@router.get("/api/prezzi/note-credito", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_note_credito(
    data_da: str,
    data_a: str,
    authorization: Optional[str] = Header(None),
) -> NoteCreditoResponse:
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    if not all_rows:
        return NoteCreditoResponse(note=[], totale_credito=0.0, n_documenti=0)

    num_map = _load_num_documento_map(sb, ristorante_id)
    # NC reali identificate via segno_compensazione=-1 in fatture_documenti.
    # Evita doppio conteggio con tab Sconti: righe negative su fatture normali
    # finivano sia in Sconti sia qui. Ora mask_totale_neg è limitata ai file NC.
    nc_files = _load_nc_file_origini(sb, ristorante_id, data_da, data_a)

    df = pd.DataFrame(all_rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['totale_riga'] = pd.to_numeric(df['totale_riga'], errors='coerce').fillna(0.0)
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce').fillna(1.0)

    mask_tipo_nc = df['tipo_documento'].astype(str).str.upper().str.contains("NC|NOTA DI CREDITO|CREDIT", na=False)
    mask_totale_neg = (df['totale_riga'] < -0.01) & (df['file_origine'].isin(nc_files))
    df_nc = df[mask_tipo_nc | mask_totale_neg].copy()

    if df_nc.empty:
        return NoteCreditoResponse(note=[], totale_credito=0.0, n_documenti=0)

    note = []
    for _, r in df_nc.iterrows():
        fo = str(r.get('file_origine', ''))
        note.append(NotaCreditoItem(
            documento=fo,
            data=str(r.get('data_documento', '')),
            fornitore=str(r.get('fornitore', '')),
            descrizione=str(r.get('descrizione', '')),
            categoria=str(r.get('categoria', '')),
            quantita=float(r['quantita']) if pd.notna(r['quantita']) else None,
            credito=round(abs(float(r['totale_riga'])), 2),
            numero_documento=num_map.get(fo, ''),
        ))

    note.sort(key=lambda x: x.data, reverse=True)
    n_docs = df_nc['file_origine'].nunique()
    totale = round(df_nc['totale_riga'].abs().sum(), 2)

    return NoteCreditoResponse(note=note, totale_credito=totale, n_documenti=n_docs)


@router.get("/api/prezzi/storico-prodotto", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_storico_prodotto(
    prodotto: str,
    fornitore: str = "",
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    authorization: Optional[str] = Header(None),
) -> StoricoPrezzoResponse:
    import pandas as pd

    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    # Pulisce il nome prodotto dai suffissi UI prima di usarlo nei filtri DB
    prod_upper = prodotto.strip().upper()
    for suffix in [" ⚠️ >6M", " ⚠ >6M"]:
        if prod_upper.endswith(suffix):
            prod_upper = prod_upper[:-len(suffix)].strip()
    # Prefisso per ilike (primi 40 chars, sicuro per Supabase)
    prod_prefix = prod_upper[:40]

    all_rows: list = []
    page = 0
    page_size = 1000
    while True:
        q = (
            sb.table("fatture")
            .select("descrizione,fornitore,prezzo_unitario,data_documento")
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .gt("prezzo_unitario", 0)
            .ilike("descrizione", f"{prod_prefix}%")
            .order("data_documento", desc=False)
            .range(page * page_size, (page + 1) * page_size - 1)
        )
        if data_da:
            q = q.gte("data_documento", data_da)
        if data_a:
            q = q.lte("data_documento", data_a)
        if fornitore:
            q = q.eq("fornitore", fornitore.strip())
        resp = q.execute()
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        page += 1

    if not all_rows:
        return StoricoPrezzoResponse(prodotto=prodotto, fornitore=fornitore, punti=[], prezzo_medio=0.0)

    df = pd.DataFrame(all_rows)
    df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0.0)
    df['_desc'] = df['descrizione'].astype(str).str.strip().str.upper()
    df['_forn'] = df['fornitore'].astype(str).str.strip().str.upper()

    # Corrispondenza esatta prima, fallback su startswith
    mask = df['_desc'] == prod_upper
    if mask.sum() == 0:
        mask = df['_desc'].str.startswith(prod_upper[:30], na=False)

    if fornitore:
        mask = mask & (df['_forn'] == fornitore.strip().upper())

    df = df[mask & (df['prezzo_unitario'] > 0)].copy()

    if df.empty:
        return StoricoPrezzoResponse(prodotto=prodotto, fornitore=fornitore, punti=[], prezzo_medio=0.0)

    prezzo_medio = round(float(df['prezzo_unitario'].mean()), 4)
    punti = [
        StoricoPrezzoPoint(
            data=str(r['data_documento']),
            prezzo_unitario=round(float(r['prezzo_unitario']), 4),
        )
        for _, r in df.iterrows()
    ]

    return StoricoPrezzoResponse(
        prodotto=prodotto,
        fornitore=fornitore,
        punti=punti,
        prezzo_medio=prezzo_medio,
    )
