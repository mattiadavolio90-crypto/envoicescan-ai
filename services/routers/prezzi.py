"""Router dominio PREZZI — variazioni, sconti, omaggi, note di credito, storico.

Estratto da fastapi_worker.py. _load_num_documento_map resta nel worker (usato
anche dalla sezione FATTURE) ed e' importato da qui. Path/gate/response invariati.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# Import LAZY da fastapi_worker per evitare il ciclo router<->fastapi_worker
# (fastapi_worker importa questo router in coda al file). I simboli condivisi sono
# WRAPPER espliciti risolti al primo uso (pattern di ricavi.py): un module-level
# __getattr__ NON basta, perche' PEP 562 risolve solo gli accessi-attributo
# ESTERNI e mai i lookup di nome globale bare dentro le funzioni -> NameError ->
# HTTP 500 su ogni endpoint. _verify_worker_key resta esplicito perche' usato in
# Depends() a import-time (firma identica per l'iniezione FastAPI).
def _fw():
    import services.fastapi_worker as fw
    return fw


def _resolve_user_from_token(*args, **kwargs):
    return _fw()._resolve_user_from_token(*args, **kwargs)


def _get_supabase_client(*args, **kwargs):
    return _fw()._get_supabase_client(*args, **kwargs)


def _resolve_ristorante_id(*args, **kwargs):
    return _fw()._resolve_ristorante_id(*args, **kwargs)


def _load_num_documento_map(*args, **kwargs):
    return _fw()._load_num_documento_map(*args, **kwargs)


def _verify_worker_key(x_worker_key: Optional[str] = Header(None)) -> None:
    return _fw()._verify_worker_key(x_worker_key)

router = APIRouter()

_CATEGORIE_SPESE_PREZZI = [
    "SERVIZI E CONSULENZE", "UTENZE E LOCALI",
    "MANUTENZIONE E ATTREZZATURE", "MATERIALE DI CONSUMO",
]
_PRICE_ALERT_DEFAULT = 5.0

# Il worker salva le note di credito con tipo_documento='TD04'. Il vecchio
# pattern "NC|NOTA DI CREDITO|CREDIT" NON includeva TD04: va sempre usato
# questo regex per riconoscere una NC dalla colonna tipo_documento.
_NC_TIPO_REGEX = r"TD04|NOTA DI CREDITO|NOTA CREDITO|\bNC\b|CREDIT"


def _mask_nota_credito(df):
    """Serie booleana: True dove la riga appartiene a una nota di credito.
    Basato su tipo_documento (TD04 incluso). Robusto a colonna assente."""
    import pandas as pd
    if 'tipo_documento' not in df.columns:
        return pd.Series(False, index=df.index)
    return df['tipo_documento'].astype(str).str.upper().str.contains(
        _NC_TIPO_REGEX, na=False, regex=True
    )

# Suffissi UI aggiunti al nome prodotto nelle variazioni (es. " ⚠️ >6m"): vanno
# rimossi prima di usarlo come chiave preferiti, altrimenti la stella non
# combacerebbe con la riga al ricaricamento.
_SUFFISSI_UI_PRODOTTO = (" ⚠️ >6M", " ⚠ >6M")


def _pulisci_desc_key(descrizione: str) -> str:
    """Chiave normalizzata della descrizione: UPPER+TRIM senza suffissi UI.

    Allineata al raggruppamento delle variazioni (_calcola_variazioni_prezzi_sync
    usa str.strip().str.upper() su 'descrizione') e alla pulizia gia' fatta in
    get_storico_prodotto. Unica fonte di verita' per la chiave preferiti.
    """
    s = str(descrizione).strip().upper()
    for suffix in _SUFFISSI_UI_PRODOTTO:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
            break
    return s


def _pulisci_forn_key(fornitore: str) -> str:
    """Chiave normalizzata del fornitore: UPPER+TRIM."""
    return str(fornitore).strip().upper()


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
    preferito: bool = False


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
    fattura: str = ""
    numero_documento: str = ""
    quantita: Optional[float] = None
    totale_riga: Optional[float] = None


class StoricoPrezzoResponse(BaseModel):
    prodotto: str
    fornitore: str
    punti: List[StoricoPrezzoPoint]
    prezzo_medio: float


class ScoreSottometrica(BaseModel):
    """Una delle metriche che compongono lo stato fornitore.

    `punteggio` (0-100) resta come dato interno per ordinamento/sintesi, ma la UI
    mostra `stato`: la lettura è per asse (stabile/da monitorare/instabile/non
    valutabile), non un voto numerico, così non si presta a contestazioni.
    """
    chiave: str          # stabilita | coerenza | impatto | documentale
    label: str
    punteggio: float     # 0-100, uso interno (sintesi/ordinamento)
    stato: str           # stabile | da_monitorare | instabile | non_valutabile
    spiegazione: str     # frase breve leggibile dall'utente
    disponibile: bool    # False = dato troppo debole per pesare → non_valutabile


class ScoreSegnale(BaseModel):
    """Segnale osservato sulla relazione (positivo o di attenzione)."""
    tipo: str            # rincaro | sconto_perso | oscillazione | nota_credito | stabilita
    tono: str            # attenzione | positivo | neutro
    testo: str


class BozzaTrattativa(BaseModel):
    """Bozza testuale copiabile, UNICA. Solo testo, nessun invio: il cliente la
    copia e la usa dove preferisce (mail, messaggio, telefonata).

    `attiva=False` quando non c'è nulla da negoziare (fornitore affidabile):
    la UI non mostra il box. `motivo` spiega in una riga perché è vuota."""
    attiva: bool = True
    testo: str = ""
    motivo: str = ""


class ScoreFornitore(BaseModel):
    fornitore: str
    score: Optional[float]          # 0-100, None se dati insufficienti
    stato: str                      # affidabile | da_monitorare | instabile | provvisorio | dati_insufficienti
    affidabilita_dato: str          # alta | media | bassa
    frase_sintesi: str
    sottometriche: List[ScoreSottometrica]
    segnali: List[ScoreSegnale]
    bozza: BozzaTrattativa
    # contesto del campione, mostrato come "limiti del dato"
    n_fatture: int
    n_prodotti: int
    mesi_coperti: int
    periodo: str                    # es. "mar–giu 2026"
    spesa_periodo: float
    impatto_rincari: float          # € stimato/mese dei rincari (>=0)


class ScoreFornitoriResponse(BaseModel):
    fornitori: List[ScoreFornitore]
    periodo: str
    n_fornitori_valutati: int       # con score numerico
    n_fornitori_insufficienti: int


class SogliaAlertRequest(BaseModel):
    soglia: float


class SogliaAlertResponse(BaseModel):
    soglia: float


class PreferitoItem(BaseModel):
    descrizione_key: str
    fornitore_key: str


class PreferitiResponse(BaseModel):
    preferiti: List[PreferitoItem]


class PreferitoRequest(BaseModel):
    prodotto: str
    fornitore: str = ""


def _carica_preferiti_keys(sb, ristorante_id: str) -> set:
    """Set di chiavi '{descrizione_key}|{fornitore_key}' dei preferiti del ristorante."""
    try:
        resp = (
            sb.table("prezzi_preferiti")
            .select("descrizione_key,fornitore_key")
            .eq("ristorante_id", ristorante_id)
            .execute()
        )
    except Exception:
        return set()
    return {
        f"{r.get('descrizione_key', '')}|{r.get('fornitore_key', '')}"
        for r in (resp.data or [])
    }


def _calcola_variazioni_prezzi_sync(rows: list, soglia: float, preferiti_keys: set | None = None) -> list:
    import pandas as pd

    if not rows:
        return []

    preferiti_keys = preferiti_keys or set()

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

        desc_piena = str(group['descrizione'].mode()[0])
        forn_piena = str(group['fornitore'].mode()[0])
        pref_key = f"{_pulisci_desc_key(desc_piena)}|{_pulisci_forn_key(forn_piena)}"
        is_preferito = pref_key in preferiti_keys

        qta_all = pd.to_numeric(acquisti['quantita'], errors='coerce').dropna()
        qta_ref = float(qta_all.mean()) if not qta_all.empty else 1.0

        date_all = pd.to_datetime(acquisti['data_documento'], errors='coerce').dropna().sort_values()
        freq = 1.0
        if len(date_all) >= 2:
            n_mesi = max(1.0, (date_all.iloc[-1] - date_all.iloc[0]).days / 30.0)
            freq = len(date_all) / n_mesi

        alert_list.append({
            'prodotto': (desc_piena + nota)[:60],
            'categoria': str(ultimo.get('categoria', ''))[:25],
            'fornitore': forn_piena[:30],
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
            'preferito': is_preferito,
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
    """DEPRECATO (9/6/2026): la soglia alert si imposta dal configuratore
    assistente (POST /api/home/config). La pagina Prezzi non scrive piu' qui — usa
    GET /api/prezzi/soglia-alert solo come valore iniziale del filtro vista.
    Endpoint mantenuto per compatibilita'; nessun frontend lo chiama piu'."""
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
    preferiti_keys = _carica_preferiti_keys(sb, ristorante_id)
    variazioni = _calcola_variazioni_prezzi_sync(all_rows, soglia, preferiti_keys)

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


@router.get("/api/prezzi/preferiti", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_preferiti(
    authorization: Optional[str] = Header(None),
) -> PreferitiResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")
    resp = (
        sb.table("prezzi_preferiti")
        .select("descrizione_key,fornitore_key")
        .eq("ristorante_id", ristorante_id)
        .execute()
    )
    items = [
        PreferitoItem(
            descrizione_key=str(r.get("descrizione_key", "")),
            fornitore_key=str(r.get("fornitore_key", "")),
        )
        for r in (resp.data or [])
    ]
    return PreferitiResponse(preferiti=items)


@router.post("/api/prezzi/preferiti", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def add_preferito(
    body: PreferitoRequest,
    authorization: Optional[str] = Header(None),
) -> PreferitiResponse:
    """Aggiunge un preferito (idempotente). Chiave = coppia normalizzata."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    desc_key = _pulisci_desc_key(body.prodotto)
    forn_key = _pulisci_forn_key(body.fornitore)
    if not desc_key:
        raise HTTPException(status_code=400, detail="Prodotto mancante")

    sb.table("prezzi_preferiti").upsert(
        {
            "ristorante_id": ristorante_id,
            "user_id": str(user["id"]),
            "descrizione_key": desc_key,
            "fornitore_key": forn_key,
        },
        on_conflict="ristorante_id,descrizione_key,fornitore_key",
    ).execute()
    return get_preferiti(authorization)


@router.delete("/api/prezzi/preferiti", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def remove_preferito(
    prodotto: str,
    fornitore: str = "",
    authorization: Optional[str] = Header(None),
) -> PreferitiResponse:
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    desc_key = _pulisci_desc_key(prodotto)
    forn_key = _pulisci_forn_key(fornitore)
    (
        sb.table("prezzi_preferiti")
        .delete()
        .eq("ristorante_id", ristorante_id)
        .eq("descrizione_key", desc_key)
        .eq("fornitore_key", forn_key)
        .execute()
    )
    return get_preferiti(authorization)


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

    # Le righe negative di una NOTA DI CREDITO (TD04) sono resi di merce, NON
    # sconti commerciali: vanno nel tab Note di Credito, non qui. Escluderle
    # toglie il doppio conteggio e il "Risparmiato" gonfiato.
    nc_mask = _mask_nota_credito(df)
    mask_sconto = (~nc_mask) & ((df['prezzo_unitario'] < -1e-9) | (df['totale_riga'] < -1e-9))
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

    mask_tipo_nc = _mask_nota_credito(df)
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
            .select("descrizione,fornitore,prezzo_unitario,data_documento,file_origine,quantita,totale_riga")
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
    df['quantita'] = pd.to_numeric(df.get('quantita', pd.Series(dtype=float)), errors='coerce')
    df['totale_riga'] = pd.to_numeric(df.get('totale_riga', pd.Series(dtype=float)), errors='coerce')
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
    num_map = _load_num_documento_map(sb, ristorante_id)
    punti = [
        StoricoPrezzoPoint(
            data=str(r['data_documento']),
            prezzo_unitario=round(float(r['prezzo_unitario']), 4),
            fattura=str(r.get('file_origine', '') or ''),
            numero_documento=num_map.get(str(r.get('file_origine', '') or ''), ''),
            quantita=round(float(r['quantita']), 3) if pd.notna(r['quantita']) else None,
            totale_riga=round(float(r['totale_riga']), 2) if pd.notna(r['totale_riga']) else None,
        )
        for _, r in df.iterrows()
    ]

    return StoricoPrezzoResponse(
        prodotto=prodotto,
        fornitore=fornitore,
        punti=punti,
        prezzo_medio=prezzo_medio,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCORE FORNITORI — lettura interna (cliente↔fornitore), nessun benchmark esterno
#
# Lo score (0-100) NON è un giudizio sul listino né un confronto col mercato: è
# una misura di quanto la RELAZIONE con quel fornitore è stata stabile, coerente
# e leggibile nel tempo, SOLO sui dati di questo ristorante. Tutto deterministico:
# nessuna AI, nessun numero inventato. Le bozze trattativa sono template riempiti
# con valori già calcolati qui.
#
# Pesi delle 4 metriche (la 5ª — affidabilità campione — è un moltiplicatore di
# confidenza, non un punteggio). Sommano a 100.
_SCORE_PESI = {
    "stabilita": 30.0,
    "coerenza": 20.0,
    "impatto": 35.0,
    "documentale": 15.0,
}

# Guardrail anti-rumore: sotto queste soglie il dato è troppo debole.
_SCORE_MIN_FATTURE = 3        # meno di 3 documenti → nessun giudizio
_SCORE_MIN_PRODOTTI_TREND = 1  # serve almeno 1 prodotto con storico per stabilità
_SCORE_MESI_FRESCHEZZA = 6   # ultimo acquisto oltre N mesi fa → dato vecchio
_MESI_IT_ABBR = ["", "gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]


def _stato_metrica(punteggio: float, disponibile: bool = True) -> str:
    """Mappa il punteggio interno (0-100) nello stato per asse mostrato in UI.
    `disponibile=False` → 'non_valutabile' (dato troppo debole, niente giudizio)."""
    if not disponibile:
        return "non_valutabile"
    if punteggio >= 75:
        return "stabile"
    if punteggio >= 55:
        return "da_monitorare"
    return "instabile"


def _periodo_label(date_min, date_max) -> str:
    """'mar–giu 2026' oppure 'mar 2025 – giu 2026' se a cavallo d'anno."""
    if date_min is None or date_max is None:
        return ""
    m1, y1 = date_min.month, date_min.year
    m2, y2 = date_max.month, date_max.year
    if y1 == y2:
        if m1 == m2:
            return f"{_MESI_IT_ABBR[m1]} {y1}"
        return f"{_MESI_IT_ABBR[m1]}–{_MESI_IT_ABBR[m2]} {y1}"
    return f"{_MESI_IT_ABBR[m1]} {y1} – {_MESI_IT_ABBR[m2]} {y2}"


def _bozza_trattativa(
    fornitore: str,
    periodo: str,
    prodotti_top: list,        # [(nome, var_pct, impatto)], i piu' impattanti in rincaro
    impatto_mese: float,       # € stimato/mese dei rincari
    sconti_persi: list,        # [nome prodotto] su cui lo sconto e' sparito
    stato: str = "",           # stato sintetico fornitore: se "affidabile" → bozza vuota
) -> BozzaTrattativa:
    """Genera UNA bozza testuale (stile lettera/email) da dati già calcolati.

    Testo unico che il cliente copia e usa come preferisce: NON è un invio, NON è
    legato a un canale. Tono prudente e collaborativo, mai accusatorio, mai
    confronti col mercato.

    Se non c'è nulla da negoziare — fornitore affidabile, oppure nessun rincaro e
    nessuno sconto perso — la bozza è VUOTA (attiva=False): non ha senso proporre
    una trattativa quando la relazione è in ordine."""

    nomi_prod = [p[0] for p in prodotti_top[:3]]
    elenco = ", ".join(n.title() for n in nomi_prod) if nomi_prod else ""
    forn_t = fornitore.title()
    ha_rincari = impatto_mese > 0 and bool(nomi_prod)
    ha_sconti_persi = bool(sconti_persi)

    # Niente da negoziare → nessuna bozza. Evita di spingere una trattativa
    # quando il fornitore è affidabile o non emerge alcun segnale concreto.
    if stato == "affidabile" or (not ha_rincari and not ha_sconti_persi):
        motivo = (
            "Relazione in ordine: non emergono motivi per una trattativa."
            if stato == "affidabile"
            else "Nessun rincaro o cambio di condizioni da portare al fornitore."
        )
        return BozzaTrattativa(attiva=False, testo="", motivo=motivo)

    # Frammento condiviso che cita SOLO dati osservati internamente.
    if ha_rincari:
        oggetto = (
            "alcune variazioni di prezzo su prodotti che acquisto con continuità"
            + (f" (in particolare {elenco})" if elenco else "")
        )
    elif ha_sconti_persi:
        oggetto = "alcune condizioni commerciali che sembrano essere cambiate"
    else:
        oggetto = "le condizioni della nostra fornitura"

    periodo_frase = f" nel periodo {periodo}" if periodo else " negli ultimi mesi"

    righe = [
        f"Gentile {forn_t},",
        "",
        f"analizzando i miei acquisti{periodo_frase} ho notato {oggetto}.",
    ]
    if ha_rincari:
        # L'apertura cita già i prodotti (in `oggetto`): qui aggiungiamo l'angolo
        # dell'impatto, senza rielencarli, per non essere ripetitivi.
        righe.append(
            "Si tratta di aumenti che incidono in modo sensibile sui costi che "
            "sostengo con regolarità."
        )
    if ha_sconti_persi:
        persi = ", ".join(n.title() for n in sconti_persi[:3])
        righe.append(
            f"Mi sembra inoltre che alcune condizioni agevolate di cui beneficiavo "
            f"(ad esempio su {persi}) non siano più presenti."
        )
    righe += [
        "",
        "Tengo molto alla continuità del nostro rapporto e vorrei capire se "
        "possiamo rivedere insieme alcune condizioni per i prossimi ordini, "
        "trovando un assetto sostenibile per entrambi.",
        "Resto a disposizione per sentirci quando preferite.",
        "",
        "Cordiali saluti",
    ]
    testo = "\n".join(righe)

    return BozzaTrattativa(testo=testo)


def _calcola_score_fornitori(
    rows: list,
    variazioni: list,
    nc_per_fornitore: dict,
    oggi=None,
) -> list:
    """Calcola lo score (0-100) per ogni fornitore dai dati interni del cliente.

    rows: righe fattura grezze (output _load_fatture_for_prezzi).
    variazioni: output _calcola_variazioni_prezzi_sync (già con impatto_stimato).
    nc_per_fornitore: {fornitore_upper: totale_credito_nc} nel periodo.
    """
    import pandas as pd

    if not rows:
        return []

    oggi = oggi or pd.Timestamp.now(tz="UTC")

    df = pd.DataFrame(rows)
    df["prezzo_unitario"] = pd.to_numeric(df["prezzo_unitario"], errors="coerce").fillna(0.0)
    df["totale_riga"] = pd.to_numeric(df.get("totale_riga", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    df["_forn"] = df["fornitore"].astype(str).str.strip()
    df["_forn_key"] = df["_forn"].str.upper()
    df["_data"] = pd.to_datetime(df["data_documento"], errors="coerce", utc=True)
    # Spese pure (utenze, servizi…) non sono "fornitura": le escludiamo dallo score
    df = df[~df["categoria"].isin(_CATEGORIE_SPESE_PREZZI)].copy()

    # Variazioni raggruppate per fornitore (chiave UPPER, gemella di _forn_key)
    var_per_forn: dict = {}
    for v in variazioni:
        k = _pulisci_forn_key(v["fornitore"])
        var_per_forn.setdefault(k, []).append(v)

    risultati = []

    for forn_key, g in df.groupby("_forn_key"):
        if not forn_key:
            continue
        nome = str(g["_forn"].mode()[0]) if not g["_forn"].mode().empty else str(forn_key)

        date_valide = g["_data"].dropna().sort_values()
        n_fatture = int(g["file_origine"].nunique()) if "file_origine" in g else len(g)
        # Spesa reale del fornitore nel periodo (solo righe positive)
        spesa = float(g.loc[g["totale_riga"] > 0, "totale_riga"].sum())
        n_prodotti = int(g["descrizione"].astype(str).str.strip().str.upper().nunique())

        mesi_coperti = 0
        date_min = date_max = None
        if not date_valide.empty:
            date_min = date_valide.iloc[0]
            date_max = date_valide.iloc[-1]
            mesi_coperti = max(1, (date_max.year - date_min.year) * 12 + (date_max.month - date_min.month) + 1)

        periodo = _periodo_label(date_min, date_max)
        vars_f = var_per_forn.get(forn_key, [])

        # ── Affidabilità del campione (metrica E) ─────────────────────────────
        # Decide se possiamo sbilanciarci. Meglio "dati insufficienti" che rumore.
        mesi_da_ultimo = 99
        if date_max is not None:
            mesi_da_ultimo = (oggi - date_max).days / 30.0

        troppo_poche = n_fatture < _SCORE_MIN_FATTURE
        troppo_breve = mesi_coperti < 2
        troppo_vecchio = mesi_da_ultimo > _SCORE_MESI_FRESCHEZZA

        # Confidenza: 1.0 piena, scende con campione corto/povero
        if troppo_poche or (troppo_breve and n_fatture < 4):
            affidabilita = "bassa"
        elif n_fatture < 5 or mesi_coperti < 3 or n_prodotti < 2:
            affidabilita = "media"
        else:
            affidabilita = "alta"

        impatto_rincari = round(sum(v["impatto_stimato"] for v in vars_f if v["impatto_stimato"] > 0), 2)
        nc_tot = float(nc_per_fornitore.get(forn_key, 0.0))

        # Prodotti più impattanti in rincaro (per segnali + bozza)
        prodotti_rincaro = sorted(
            [
                (str(v["prodotto"]), float(v["aumento_perc"]), float(v["impatto_stimato"]))
                for v in vars_f
                if v["aumento_perc"] > 0
            ],
            key=lambda x: x[2],
            reverse=True,
        )

        # Caso DATI INSUFFICIENTI: nessuno score numerico, nessun giudizio.
        if troppo_poche or (troppo_breve and not vars_f):
            motivo = (
                "Poche fatture nel periodo" if troppo_poche
                else "Storico troppo breve per un giudizio affidabile"
            )
            risultati.append(ScoreFornitore(
                fornitore=nome,
                score=None,
                stato="dati_insufficienti",
                affidabilita_dato="bassa",
                frase_sintesi=f"{motivo}: il sistema non si sbilancia.",
                sottometriche=[],
                segnali=[],
                bozza=_bozza_trattativa(nome, periodo, prodotti_rincaro, impatto_rincari, []),
                n_fatture=n_fatture,
                n_prodotti=n_prodotti,
                mesi_coperti=mesi_coperti,
                periodo=periodo,
                spesa_periodo=round(spesa, 2),
                impatto_rincari=impatto_rincari,
            ))
            continue

        sottometriche: list = []

        # ── A. Stabilità prezzi (peso 30) ────────────────────────────────────
        # Volatilità = media degli |Δ%| sui prodotti che hanno avuto variazione.
        # Nessuna variazione rilevata = massima stabilità.
        if vars_f:
            abs_var = [abs(float(v["aumento_perc"])) for v in vars_f]
            volat = sum(abs_var) / len(abs_var)
            n_oscillanti = sum(1 for v in vars_f if "↕" in str(v.get("trend", "")))
            # 0% volatilità → 100; ~25% medio → ~0. Penalità extra per oscillazioni.
            punteggio_stab = max(0.0, 100.0 - volat * 4.0 - n_oscillanti * 5.0)
            if volat < 3:
                spieg_stab = "Prezzi molto stabili nel periodo osservato."
            elif volat < 8:
                spieg_stab = f"Variazioni contenute (media {volat:.0f}% sui prodotti mossi)."
            else:
                spieg_stab = f"Prezzi piuttosto mobili (media {volat:.0f}% sui prodotti mossi)."
        else:
            punteggio_stab = 92.0  # nessuna variazione sopra soglia = stabile
            spieg_stab = "Nessuna variazione di prezzo rilevante nel periodo."
        sottometriche.append(ScoreSottometrica(
            chiave="stabilita", label="Stabilità prezzi",
            punteggio=round(punteggio_stab, 1), stato=_stato_metrica(punteggio_stab),
            spiegazione=spieg_stab, disponibile=True,
        ))

        # ── B. Coerenza commerciale (peso 20) ────────────────────────────────
        # Confronta presenza di sconti/omaggi prima vs seconda metà del periodo.
        # PRUDENTE per scelta: si sbilancia SOLO sui due casi chiari (sconti
        # spariti / sconti continui) e con almeno 3 mesi di storico. In tutti gli
        # altri casi — periodo corto, nessuna agevolazione, segnale ambiguo —
        # resta "non valutabile" e NON pesa come colpa né come merito.
        mask_sconto = (g["prezzo_unitario"] < -1e-9) | (g["totale_riga"] < -1e-9)
        mask_omaggio = (g["totale_riga"].abs() < 1e-9) & (g["prezzo_unitario"].abs() < 1e-9) & (
            g["descrizione"].astype(str).str.strip().str.len() > 3
        )
        sconti_persi: list = []
        coerenza_disp = False
        punteggio_coer = 75.0  # neutro: usato solo come fallback, non valutabile
        spieg_coer = "Nessuno sconto o omaggio ricorrente da valutare nel periodo."

        ha_agevolazioni = bool((mask_sconto | mask_omaggio).any())
        if (
            date_min is not None and date_max is not None
            and ha_agevolazioni and mesi_coperti >= 3
        ):
            meta = date_min + (date_max - date_min) / 2
            agev = g[mask_sconto | mask_omaggio]
            prima = agev[agev["_data"] <= meta]
            dopo = agev[agev["_data"] > meta]
            if len(prima) > 0 and len(dopo) == 0:
                # Caso chiaro: c'erano, non ci sono più → valutabile, segnale.
                punteggio_coer = 45.0
                spieg_coer = "Condizioni agevolate presenti all'inizio ma non più di recente."
                sconti_persi = (
                    prima["descrizione"].astype(str).str.strip().dropna().unique().tolist()[:5]
                )
                coerenza_disp = True
            elif len(dopo) > 0 and len(prima) > 0:
                # Caso chiaro: presenti su tutto il periodo → continuità.
                punteggio_coer = 85.0
                spieg_coer = "Sconti o omaggi presenti con una certa continuità."
                coerenza_disp = True
            else:
                # Ambiguo (solo nella seconda metà, o pochi episodi): non ci
                # sbilanciamo.
                spieg_coer = "Condizioni agevolate osservate solo di recente: presto per leggere una tendenza."
        elif ha_agevolazioni and mesi_coperti < 3:
            spieg_coer = "Storico troppo breve per valutare la continuità delle condizioni."

        sottometriche.append(ScoreSottometrica(
            chiave="coerenza", label="Coerenza commerciale",
            punteggio=round(punteggio_coer, 1), stato=_stato_metrica(punteggio_coer, coerenza_disp),
            spiegazione=spieg_coer, disponibile=coerenza_disp,
        ))

        # ── C. Impatto economico (peso 35) ───────────────────────────────────
        # Rincari pesati per impatto € reale (già in impatto_stimato), rapportati
        # alla spesa MENSILE con quel fornitore. Un aumento marginale conta poco,
        # uno che pesa davvero abbassa lo score.
        spesa_mensile = spesa / max(1, mesi_coperti)
        if spesa_mensile > 0:
            incidenza = impatto_rincari / spesa_mensile  # quota della spesa erosa/mese
            punteggio_imp = max(0.0, 100.0 - min(1.0, incidenza) * 100.0)
            if impatto_rincari <= 0:
                spieg_imp = "Nessun rincaro con impatto economico nel periodo."
            elif incidenza < 0.03:
                spieg_imp = f"Rincari dall'impatto marginale (~€{impatto_rincari:,.0f}/mese).".replace(",", ".")
            else:
                spieg_imp = f"I rincari incidono per ~{incidenza*100:.0f}% sulla spesa mensile con questo fornitore.".replace(",", ".")
        else:
            punteggio_imp = 70.0
            spieg_imp = "Spesa nel periodo troppo bassa per stimare l'impatto."
        sottometriche.append(ScoreSottometrica(
            chiave="impatto", label="Impatto economico",
            punteggio=round(punteggio_imp, 1), stato=_stato_metrica(punteggio_imp, spesa_mensile > 0),
            spiegazione=spieg_imp, disponibile=spesa_mensile > 0,
        ))

        # ── D. Regolarità documentale (peso 15) ──────────────────────────────
        # Le note di credito NON sono di per sé negative: spesso sono storni
        # corretti. Penalizziamo solo se il volume NC è anomalo rispetto alla
        # spesa. Metrica volutamente prudente.
        if nc_tot <= 0:
            punteggio_doc = 90.0
            spieg_doc = "Nessuna nota di credito o storno nel periodo."
        else:
            quota_nc = nc_tot / spesa if spesa > 0 else 0
            if quota_nc < 0.05:
                punteggio_doc = 82.0
                spieg_doc = "Qualche nota di credito, su volumi fisiologici."
            elif quota_nc < 0.15:
                punteggio_doc = 65.0
                spieg_doc = f"Note di credito non trascurabili (~{quota_nc*100:.0f}% della spesa) — da interpretare."
            else:
                punteggio_doc = 50.0
                spieg_doc = f"Volume di note di credito elevato (~{quota_nc*100:.0f}% della spesa): vale un controllo."
        sottometriche.append(ScoreSottometrica(
            chiave="documentale", label="Regolarità documentale",
            punteggio=round(punteggio_doc, 1), stato=_stato_metrica(punteggio_doc),
            spiegazione=spieg_doc, disponibile=True,
        ))

        # ── Sintesi complessiva: media pesata SOLO sugli assi valutabili ──────
        # Gli assi 'non_valutabile' (es. coerenza su dato debole) non pesano: non
        # devono spingere la sintesi né in bene né in male. `score` resta come
        # ordinamento interno; la UI mostra lo stato sintetico, non il numero.
        metriche_valide = [m for m in sottometriche if m.disponibile]
        peso_tot = sum(_SCORE_PESI[m.chiave] for m in metriche_valide)
        if peso_tot > 0:
            score_raw = sum(_SCORE_PESI[m.chiave] * m.punteggio for m in metriche_valide) / peso_tot
        else:
            score_raw = 70.0
        score = round(score_raw, 0)

        # Confidenza bassa/dato vecchio → niente etichetta forte: "provvisorio".
        if affidabilita == "bassa" or troppo_vecchio:
            stato = "provvisorio"
        elif score >= 75:
            stato = "affidabile"
        elif score >= 55:
            stato = "da_monitorare"
        else:
            stato = "instabile"

        # Coerenza sintesi↔assi: tolto il numero, una sintesi "affidabile" con un
        # asse chiaramente "instabile" sotto apparirebbe contraddittoria. Quindi
        # un asse instabile non può convivere con la sintesi più alta: si scende
        # almeno a "da monitorare". Non alziamo mai: la sintesi non è più ottimista
        # dei suoi assi, solo più prudente.
        stati_assi = {m.stato for m in sottometriche if m.disponibile}
        declassato_per_asse = stato == "affidabile" and "instabile" in stati_assi
        if declassato_per_asse:
            stato = "da_monitorare"

        # ── Segnali osservati ────────────────────────────────────────────────
        segnali: list = []
        for nome_p, var_pct, imp in prodotti_rincaro[:3]:
            imp_s = f" (~€{imp:,.0f}/mese)".replace(",", ".") if imp > 0 else ""
            segnali.append(ScoreSegnale(
                tipo="rincaro", tono="attenzione",
                testo=f"Aumento del {var_pct:.0f}% su {nome_p.title()}{imp_s}.",
            ))
        for nome_s in sconti_persi[:2]:
            segnali.append(ScoreSegnale(
                tipo="sconto_perso", tono="attenzione",
                testo=f"Sconto/condizione non più presente su {str(nome_s).title()}.",
            ))
        n_oscill = sum(1 for v in vars_f if "↕" in str(v.get("trend", "")))
        if n_oscill >= 2:
            segnali.append(ScoreSegnale(
                tipo="oscillazione", tono="attenzione",
                testo=f"Prezzi altalenanti su {n_oscill} prodotti.",
            ))
        if nc_tot > 0:
            segnali.append(ScoreSegnale(
                tipo="nota_credito", tono="neutro",
                testo=f"Note di credito per €{nc_tot:,.0f} nel periodo — da interpretare, non per forza un problema.".replace(",", "."),
            ))
        if not segnali and punteggio_stab >= 85:
            segnali.append(ScoreSegnale(
                tipo="stabilita", tono="positivo",
                testo="Relazione stabile: nessun segnale di attenzione nel periodo.",
            ))

        # ── Frase di sintesi ─────────────────────────────────────────────────
        if stato == "affidabile":
            frase = "Fornitore stabile e coerente nel periodo osservato."
        elif stato == "da_monitorare":
            frase = (
                "C'è un'area che merita attenzione, anche se nel complesso la relazione regge."
                if declassato_per_asse
                else "Relazione complessivamente solida, con qualche segnale da tenere d'occhio."
            )
        elif stato == "provvisorio":
            frase = "Lettura provvisoria: lo storico disponibile è ancora limitato."
        else:
            frase = "Diversi segnali di instabilità: vale la pena un confronto."

        risultati.append(ScoreFornitore(
            fornitore=nome,
            score=score,
            stato=stato,
            affidabilita_dato=affidabilita,
            frase_sintesi=frase,
            sottometriche=sottometriche,
            segnali=segnali,
            bozza=_bozza_trattativa(nome, periodo, prodotti_rincaro, impatto_rincari, sconti_persi, stato),
            n_fatture=n_fatture,
            n_prodotti=n_prodotti,
            mesi_coperti=mesi_coperti,
            periodo=periodo,
            spesa_periodo=round(spesa, 2),
            impatto_rincari=impatto_rincari,
        ))

    # Ordine: prima quelli valutati per score crescente (più instabili in alto,
    # sono quelli su cui agire), poi i "dati insufficienti" in coda.
    def _sort_key(s: ScoreFornitore):
        if s.score is None:
            return (1, 0.0, s.fornitore)
        return (0, s.score, s.fornitore)

    risultati.sort(key=_sort_key)
    return risultati


def _nc_credito_per_fornitore(sb, ristorante_id: str, data_da: str, data_a: str, rows: list | None = None) -> dict:
    """{fornitore_upper: totale_credito_nc} riusando la stessa logica del tab NC.

    `rows` (opzionale) = righe già caricate dal chiamante: se fornite NON si
    rilegge la tabella fatture (evita una seconda scansione paginata per request).
    """
    import pandas as pd

    if rows is None:
        rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    if not rows:
        return {}
    nc_files = _load_nc_file_origini(sb, ristorante_id, data_da, data_a)
    df = pd.DataFrame(rows)
    df["totale_riga"] = pd.to_numeric(df["totale_riga"], errors="coerce").fillna(0.0)
    mask_tipo_nc = _mask_nota_credito(df)
    mask_totale_neg = (df["totale_riga"] < -0.01) & (df["file_origine"].isin(nc_files))
    df_nc = df[mask_tipo_nc | mask_totale_neg].copy()
    if df_nc.empty:
        return {}
    df_nc["_forn_key"] = df_nc["fornitore"].astype(str).str.strip().str.upper()
    grouped = df_nc.groupby("_forn_key")["totale_riga"].apply(lambda s: float(s.abs().sum()))
    return grouped.to_dict()


@router.get("/api/prezzi/score-fornitori", tags=["Prezzi"], dependencies=[Depends(_verify_worker_key)])
def get_score_fornitori(
    data_da: str,
    data_a: str,
    soglia: float = _PRICE_ALERT_DEFAULT,
    authorization: Optional[str] = Header(None),
) -> ScoreFornitoriResponse:
    """Score interno (0-100) per fornitore, sola lettura cliente↔fornitore.

    Riusa gli stessi dati di variazioni/sconti/NC: nessuna nuova tabella, nessun
    benchmark esterno. Soglia = stessa soglia variazioni (default avvisi)."""
    user = _resolve_user_from_token(authorization)
    sb = _get_supabase_client()
    ristorante_id = _resolve_ristorante_id(user, sb)
    if not ristorante_id:
        raise HTTPException(status_code=400, detail="Nessun ristorante associato")

    all_rows = _load_fatture_for_prezzi(sb, ristorante_id, data_da, data_a)
    if not all_rows:
        return ScoreFornitoriResponse(
            fornitori=[], periodo="", n_fornitori_valutati=0, n_fornitori_insufficienti=0,
        )

    variazioni = _calcola_variazioni_prezzi_sync(all_rows, soglia)
    nc_map = _nc_credito_per_fornitore(sb, ristorante_id, data_da, data_a, rows=all_rows)
    fornitori = _calcola_score_fornitori(all_rows, variazioni, nc_map)

    n_val = sum(1 for f in fornitori if f.score is not None)
    n_insuf = len(fornitori) - n_val
    periodo = next((f.periodo for f in fornitori if f.periodo), "")

    return ScoreFornitoriResponse(
        fornitori=fornitori,
        periodo=periodo,
        n_fornitori_valutati=n_val,
        n_fornitori_insufficienti=n_insuf,
    )
