"""
Helper centralizzato per calcolo date periodo.
Evita duplicazione della logica mese/trimestre/semestre/anno in ogni pagina.
"""
from datetime import date
import calendar as _calendar


_MESI_ITA = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
]

# Opzioni dropdown condivise
PERIODO_OPTIONS = [
    "📅 Mese in Corso",
    "📊 Trimestre in Corso",
    "📈 Semestre in Corso",
    "🗓️ Anno in Corso",
    "📆 Seleziona Mese",
    "⚙️ Periodo Personalizzato"
]


def calcola_date_periodo():
    """
    Calcola le date di inizio per ogni periodo standard.
    
    Returns:
        dict con chiavi: oggi, inizio_mese, inizio_trimestre, inizio_semestre, inizio_anno
    """
    oggi = date.today()
    mese_trim = ((oggi.month - 1) // 3) * 3 + 1
    mese_sem = 1 if oggi.month <= 6 else 7
    
    return {
        'oggi': oggi,
        'inizio_mese': oggi.replace(day=1),
        'inizio_trimestre': oggi.replace(month=mese_trim, day=1),
        'inizio_semestre': oggi.replace(month=mese_sem, day=1),
        'inizio_anno': oggi.replace(month=1, day=1),
    }


def risolvi_periodo(periodo_selezionato: str, date_periodo: dict) -> tuple:
    """
    Dato il periodo selezionato e le date calcolate, restituisce (data_inizio, data_fine, label).
    
    Per "Periodo Personalizzato" restituisce (None, oggi, None) — il chiamante gestisce i date_input.
    """
    oggi = date_periodo['oggi']
    
    if periodo_selezionato == "📅 Mese in Corso":
        d = date_periodo['inizio_mese']
        return d, oggi, f"Mese in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📊 Trimestre in Corso":
        d = date_periodo['inizio_trimestre']
        return d, oggi, f"Trimestre in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📈 Semestre in Corso":
        d = date_periodo['inizio_semestre']
        return d, oggi, f"Semestre in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "🗓️ Anno in Corso":
        d = date_periodo['inizio_anno']
        return d, oggi, f"Anno in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📆 Seleziona Mese":
        return None, oggi, None

    else:  # Periodo Personalizzato
        return None, oggi, None


try:
    import streamlit as _st_mesi

    @_st_mesi.cache_data(ttl=300, show_spinner=False)
    def _get_mesi_disponibili_cached(user_id: str, ristorante_id: str) -> list:
        """Versione cached (TTL 300s) di get_mesi_disponibili_fatture."""
        from datetime import datetime as _dt_inner
        from datetime import date as _date_inner
        oggi_inner = _date_inner.today()
        prima_data_inner = None
        try:
            from services import get_supabase_client as _sb_fn
            sb_inner = _sb_fn()
            resp = (
                sb_inner.table('fatture')
                .select('data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .is_('deleted_at', 'null')
                .not_.is_('data_documento', 'null')
                .order('data_documento', desc=False)
                .limit(1)
                .execute()
            )
            if resp.data and resp.data[0].get('data_documento'):
                prima_data_inner = _dt_inner.fromisoformat(resp.data[0]['data_documento'][:10]).date()
        except Exception:
            pass
        if prima_data_inner is None:
            prima_data_inner = oggi_inner.replace(day=1)
        mesi_inner = []
        anno, mese = prima_data_inner.year, prima_data_inner.month
        anno_end, mese_end = oggi_inner.year, oggi_inner.month
        while (anno, mese) <= (anno_end, mese_end):
            label = f"{_MESI_ITA[mese - 1]} {anno}"
            mesi_inner.append((anno, mese, label))
            mese += 1
            if mese > 12:
                mese = 1
                anno += 1
        return mesi_inner
except Exception:
    _get_mesi_disponibili_cached = None  # type: ignore[assignment]


def get_mesi_disponibili_fatture(user_id: str, ristorante_id: str, supabase_client=None) -> list:
    """
    Restituisce una lista di (anno, mese, label) per tutti i mesi dalla prima fattura
    del ristorante fino al mese corrente incluso.
    Se non ci sono fatture o la query fallisce, parte dal mese corrente.
    Cached 300s per ridurre round-trip Supabase su ogni render.
    """
    # Usa versione cached quando Streamlit è disponibile (ignora supabase_client: non hashable)
    if _get_mesi_disponibili_cached is not None and user_id and ristorante_id:
        return _get_mesi_disponibili_cached(str(user_id), str(ristorante_id))

    # Fallback senza cache (worker/test/non-Streamlit context)
    oggi = date.today()
    prima_data = None

    if supabase_client and user_id and ristorante_id:
        try:
            resp = (
                supabase_client.table('fatture')
                .select('data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .is_('deleted_at', 'null')
                .not_.is_('data_documento', 'null')
                .order('data_documento', desc=False)
                .limit(1)
                .execute()
            )
            if resp.data and resp.data[0].get('data_documento'):
                from datetime import datetime as _dt
                prima_data = _dt.fromisoformat(resp.data[0]['data_documento'][:10]).date()
        except Exception:
            pass

    if prima_data is None:
        prima_data = oggi.replace(day=1)

    mesi = []
    anno, mese = prima_data.year, prima_data.month
    anno_end, mese_end = oggi.year, oggi.month

    while (anno, mese) <= (anno_end, mese_end):
        label = f"{_MESI_ITA[mese - 1]} {anno}"
        mesi.append((anno, mese, label))
        mese += 1
        if mese > 12:
            mese = 1
            anno += 1

    return mesi


def risolvi_mese_selezionato(mese_label: str, mesi_list: list) -> tuple:
    """
    Dato il label di un mese (es. "Febbraio 2026") e la lista restituita da
    get_mesi_disponibili_fatture, ritorna (data_inizio, data_fine) del mese solare.
    """
    for anno, mese, label in mesi_list:
        if label == mese_label:
            primo = date(anno, mese, 1)
            ultimo = date(anno, mese, _calendar.monthrange(anno, mese)[1])
            return primo, ultimo
    # fallback: mese corrente
    oggi = date.today()
    primo = oggi.replace(day=1)
    ultimo = date(oggi.year, oggi.month, _calendar.monthrange(oggi.year, oggi.month)[1])
    return primo, ultimo
