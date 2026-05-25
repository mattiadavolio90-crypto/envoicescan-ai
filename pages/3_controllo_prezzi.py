"""
Controllo Prezzi - Variazioni, Sconti, Omaggi e Note di Credito
Pagina dedicata al monitoraggio prezzi e documenti finanziari.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import io

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

from config.logger_setup import get_logger
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ristorante_helper import get_current_ristorante_id
from services.db_service import (
    carica_e_prepara_dataframe,
    calcola_alert,
    _calcola_alert_cached,
    carica_sconti_e_omaggi,
    _carica_sconti_e_omaggi_cached,
    get_custom_tags,
    get_price_alert_threshold,
    set_price_alert_threshold,
)
from utils.validation import SPECIAL_ROW_STORNO, classify_special_row, classify_special_row_vectorized

# Logger
logger = get_logger('controllo_prezzi')


def _fmt_int_migliaia(valore) -> str:
    """Formato intero italiano: no decimali, separatore migliaia con punto."""
    try:
        return f"{int(round(float(valore))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"

# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Controllo Prezzi - ONEFLUX",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# NASCONDI SIDEBAR SE NON LOGGATO
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()

# ============================================
# AUTENTICAZIONE RICHIESTA
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")
    st.stop()

# Admin puro: accesso consentito anche fuori dal pannello admin

user = st.session_state.user_data
user_id = user["id"]
current_ristorante = get_current_ristorante_id()

if not current_ristorante:
    st.error("⚠️ Nessun ristorante selezionato. Torna alla Dashboard per selezionarne uno.")
    st.stop()

# ============================================
# CONTROLLO PAGINA ABILITATA (legge sempre dal DB per riflettere modifiche admin)
# ============================================
from utils.page_setup import check_page_enabled
check_page_enabled('controllo_prezzi', user_id)

# ============================================
# SIDEBAR CONDIVISA
# ============================================
render_sidebar(user)

# ============================================
# HEADER PAGINA
# ============================================
render_oh_yeah_header()

st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
    🔍 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Controllo Prezzi</span>
</h2>
""", unsafe_allow_html=True)

st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)

# ============================================
# FILTRO PERIODO
# ============================================
from utils.period_helper import PERIODO_OPTIONS, calcola_date_periodo, risolvi_periodo

date_periodo = calcola_date_periodo()
oggi_date = date_periodo['oggi']
inizio_anno = date_periodo['inizio_anno']

if 'cp_periodo_dropdown' not in st.session_state:
    st.session_state.cp_periodo_dropdown = "🗓️ Anno in Corso"

if 'cp_data_inizio' not in st.session_state:
    st.session_state.cp_data_inizio = inizio_anno
if 'cp_data_fine' not in st.session_state:
    st.session_state.cp_data_fine = oggi_date

# ============================================
# CARICAMENTO DATI
# ============================================
with st.spinner("Caricamento dati fatture..."):
    df_all = carica_e_prepara_dataframe(user_id, ristorante_id=current_ristorante)
    custom_tags = get_custom_tags(user_id, current_ristorante)

if df_all.empty:
    st.info("📊 Nessuna fattura disponibile. Carica le fatture dalla pagina Analisi Fatture.")
    st.stop()

special_meta = classify_special_row_vectorized(df_all)
df_all['_special_bucket'] = special_meta['bucket']
df_all['_include_in_price_average'] = special_meta['include_in_price_average'].fillna(False).astype(bool)

st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

# ============================================
# NAVIGAZIONE TAB
# ============================================
if 'cp_tab_attivo' not in st.session_state:
    st.session_state.cp_tab_attivo = "variazioni"

def _set_cp_tab(tab: str) -> None:
    """on_click callback: aggiorna il tab PRIMA che Streamlit ri-renderizzi i bottoni.
    Evita il flash 'secondary → primary' che si vedeva con il pattern if st.button(...)."""
    st.session_state.cp_tab_attivo = tab


col_t1, col_t2, col_t3 = st.columns(3)

with col_t1:
    st.button("📈 VARIAZIONI\nPREZZO", key="cp_btn_variazioni", use_container_width=True,
              type="primary" if st.session_state.cp_tab_attivo == "variazioni" else "secondary",
              on_click=_set_cp_tab, args=("variazioni",))

with col_t2:
    st.button("🎁 SCONTI E\nOMAGGI", key="cp_btn_sconti", use_container_width=True,
              type="primary" if st.session_state.cp_tab_attivo == "sconti" else "secondary",
              on_click=_set_cp_tab, args=("sconti",))

with col_t3:
    st.button("📋 NOTE DI\nCREDITO", key="cp_btn_nc", use_container_width=True,
              type="primary" if st.session_state.cp_tab_attivo == "nc" else "secondary",
              on_click=_set_cp_tab, args=("nc",))

st.markdown("<div style='margin-top: 0.3rem;'></div>", unsafe_allow_html=True)
st.markdown(
    "<div style='margin-top: 0.45rem; margin-bottom: 0.35rem; color:#1e3a8a; font-weight:700; font-size:0.95rem;'>Seleziona periodo:</div>",
    unsafe_allow_html=True,
)

col_periodo, col_info_periodo = st.columns([1, 3])

with col_periodo:
    periodo_selezionato = st.selectbox(
        "Periodo",
        options=PERIODO_OPTIONS,
        label_visibility="collapsed",
        index=PERIODO_OPTIONS.index(st.session_state.cp_periodo_dropdown) if st.session_state.cp_periodo_dropdown in PERIODO_OPTIONS else 0,
        key="cp_filtro_periodo"
    )

st.session_state.cp_periodo_dropdown = periodo_selezionato

# Gestione logica periodo
data_inizio_filtro, data_fine_filtro, label_periodo = risolvi_periodo(periodo_selezionato, date_periodo)

with col_info_periodo:
    if periodo_selezionato == "📆 Seleziona Mese":
        from utils.period_helper import get_mesi_disponibili_fatture, risolvi_mese_selezionato
        from services import get_supabase_client as _get_sb_cp
        _sb_cp = _get_sb_cp()
        _mesi_cp = get_mesi_disponibili_fatture(user_id, current_ristorante, _sb_cp)
        _mesi_labels_cp = [x[2] for x in _mesi_cp]
        if not _mesi_labels_cp:
            _mesi_labels_cp = [oggi_date.replace(day=1).strftime("%B %Y")]
        _col_mese_cp, _col_empty_cp = st.columns([1.2, 1.8])
        with _col_mese_cp:
            _mese_sel_cp = st.selectbox(
                "Mese",
                options=_mesi_labels_cp,
                index=len(_mesi_labels_cp) - 1,
                key="cp_mese_sel",
                label_visibility="collapsed",
            )
        data_inizio_filtro, data_fine_filtro = risolvi_mese_selezionato(_mese_sel_cp, _mesi_cp)
        label_periodo = _mese_sel_cp
    elif data_inizio_filtro is None:
        # Periodo Personalizzato: range picker inline
        _col_range, _col_empty = st.columns([1.2, 1.8])
        with _col_range:
            _range = st.date_input(
                "Periodo",
                value=(st.session_state.cp_data_inizio, st.session_state.cp_data_fine),
                min_value=inizio_anno,
                format="DD/MM/YYYY",
                key="cp_data_range_custom",
                label_visibility="collapsed",
            )
        if isinstance(_range, (list, tuple)) and len(_range) == 2:
            data_inizio_custom, data_fine_custom = _range[0], _range[1]
            if data_inizio_custom > data_fine_custom:
                st.error("⚠️ La data iniziale deve essere precedente alla data finale.")
                data_inizio_filtro = st.session_state.cp_data_inizio
                data_fine_filtro = st.session_state.cp_data_fine
            else:
                st.session_state.cp_data_inizio = data_inizio_custom
                st.session_state.cp_data_fine = data_fine_custom
                data_inizio_filtro = data_inizio_custom
                data_fine_filtro = data_fine_custom
        else:
            data_inizio_filtro = st.session_state.cp_data_inizio
            data_fine_filtro = st.session_state.cp_data_fine
        label_periodo = f"{data_inizio_filtro.strftime('%d/%m/%Y')} → {data_fine_filtro.strftime('%d/%m/%Y')}"
    else:
        st.markdown(f"""
        <div style="display: inline-block; width: fit-content; background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
                    padding: 10px 16px;
                    border-radius: 8px;
                    border: 1px solid #93c5fd;
                    color: #1e3a8a;
                    font-size: clamp(0.78rem, 1.8vw, 0.88rem);
                    font-weight: 500;
                    line-height: 1.5;
                    margin-top: 0px;">
            📊 {label_periodo}
        </div>
        """, unsafe_allow_html=True)

# Filtro periodo (dopo risoluzione input periodo)
df_all['Data_DT'] = pd.to_datetime(df_all['DataDocumento'], errors='coerce')
mask_periodo = (
    (df_all['Data_DT'].dt.date >= data_inizio_filtro) &
    (df_all['Data_DT'].dt.date <= data_fine_filtro)
)
df_filtrato = df_all[mask_periodo].copy()

_prezzo_periodo = pd.to_numeric(df_filtrato.get('PrezzoUnitario'), errors='coerce').fillna(0.0)
df_filtrato_variazioni = df_filtrato[
    df_filtrato['_include_in_price_average']
    & (_prezzo_periodo > 0)
].copy()

if df_filtrato.empty:
    st.warning(f"📊 Nessun dato disponibile per il periodo: {label_periodo}")
    st.stop()

# CSS bottoni tab e download (caricati da file statico condiviso)
from utils.ui_helpers import load_all_css
load_all_css()

st.markdown("<div style='margin-top: 0.25rem;'></div>", unsafe_allow_html=True)

# ================================================================
# TAB 1: VARIAZIONI PREZZO
# ================================================================
if st.session_state.cp_tab_attivo == "variazioni":

    st.markdown(
        """
        <style>
        div.st-key-cp_btn_salva_soglia_alert .stButton button {
            background: linear-gradient(135deg, #0ea5e9, #2563eb) !important;
            color: #ffffff !important;
            border: none !important;
            font-weight: 700 !important;
        }
        div.st-key-cp_btn_salva_soglia_alert .stButton button:hover {
            background: linear-gradient(135deg, #0284c7, #1d4ed8) !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Inizializza soglia da DB una sola volta per utente in sessione.
    _cp_threshold_user_key = f"cp_threshold_loaded_user:{user_id}"
    if not st.session_state.get(_cp_threshold_user_key):
        st.session_state.cp_soglia_alert = float(get_price_alert_threshold(user_id))
        st.session_state[_cp_threshold_user_key] = True

    # ── Riga filtro: Soglia + Salva + testo guida ──
    col_soglia, col_salva, col_help = st.columns([0.9, 0.5, 5.4], vertical_alignment="bottom")

    with col_soglia:
        st.markdown("<div style='font-size:0.92rem; font-weight:500; color:#374151; margin-bottom:0.25rem;'>Soglia %</div>", unsafe_allow_html=True)
        soglia_aumento = st.number_input(
            "Soglia %",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            key="cp_soglia_alert",
            help="Mostra solo variazioni con valore assoluto ≥ X%",
            label_visibility="collapsed",
        )

    with col_salva:
        st.markdown("<div style='height: 1.65rem;'></div>", unsafe_allow_html=True)
        if st.button("SALVA", key="cp_btn_salva_soglia_alert", use_container_width=True):
            saved = set_price_alert_threshold(user_id, soglia_aumento)
            if saved:
                st.toast(f"Soglia alert salvata: {soglia_aumento:.1f}%", icon="✅")
            else:
                st.toast("Impossibile salvare la soglia alert. Riprova.", icon="⚠️")

    with col_help:
        st.markdown("<div style='height: 1.58rem;'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='margin-top: 0; color:#1e3a8a; font-weight:600; line-height:1.2; white-space: nowrap;'>"
            "🚨 Imposta la soglia minima di variazione prezzo che attiva le notifiche alert in Tab Notifiche."
            "</div>",
            unsafe_allow_html=True,
        )

    # Calcola alert (solo F&B, periodo selezionato)
    df_alert_source = df_filtrato_variazioni
    df_alert = _calcola_alert_cached(df_alert_source, soglia_aumento)

    # Messaggio se nessuna variazione
    if df_alert.empty:
        st.markdown(
            "<p style='margin:0; color:#0B3A82; font-weight:700;'>✅ Nessuna variazione rilevata</p>",
            unsafe_allow_html=True,
        )

    if not df_alert.empty:

        # ── KPI CARDS ──
        df_metric = df_alert.copy()
        df_metric['Aumento_Perc'] = pd.to_numeric(df_metric['Aumento_Perc'], errors='coerce').fillna(0.0)
        df_metric['Impatto_Stimato'] = pd.to_numeric(df_metric['Impatto_Stimato'], errors='coerce').fillna(0.0)

        scostamento_medio = int(round(float(df_metric['Aumento_Perc'].mean()))) if not df_metric.empty else 0
        impatto_netto = int(round(float(df_metric['Impatto_Stimato'].sum())))
        fornitori_coinvolti = int(df_metric['Fornitore'].nunique())

        if scostamento_medio > 0:
            colore_scostamento = "#dc2626"
            scostamento_label = f"+{scostamento_medio}%"
        elif scostamento_medio < 0:
            colore_scostamento = "#16a34a"
            scostamento_label = f"{scostamento_medio}%"
        else:
            colore_scostamento = "#1e40af"
            scostamento_label = "0%"

        if impatto_netto > 0:
            colore_impatto = "#dc2626"
            impatto_label = f"+€{_fmt_int_migliaia(abs(impatto_netto))}/mese"
        elif impatto_netto < 0:
            colore_impatto = "#16a34a"
            impatto_label = f"-€{_fmt_int_migliaia(abs(impatto_netto))}/mese"
        else:
            colore_impatto = "#1e40af"
            impatto_label = "€0/mese"

        st.markdown(f"""
        <div class="cp-kpi-row">
            <div class="cp-kpi-card">
                <div class="kpi-label">⚠️ Alert attivi</div>
                <div class="kpi-value" style="color: #1e40af;">{len(df_metric)}</div>
            </div>
            <div class="cp-kpi-card">
                <div class="kpi-label">📈 Scostamento medio</div>
                <div class="kpi-value" style="color: {colore_scostamento};">{scostamento_label}</div>
            </div>
            <div class="cp-kpi-card">
                <div class="kpi-label">💰 Impatto stimato</div>
                <div class="kpi-value" style="color: {colore_impatto};">{impatto_label}</div>
            </div>
            <div class="cp-kpi-card">
                <div class="kpi-label">🏪 Fornitori coinvolti</div>
                <div class="kpi-value" style="color: #1e40af;">{fornitori_coinvolti}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── TABELLA ──
        df_display = df_alert.copy()
        df_display['Data'] = pd.to_datetime(df_display['Data']).dt.strftime('%d/%m/%y')
        df_display['Media'] = df_display['Media'].apply(lambda x: f"€{x:.2f}")
        df_display['Ultimo'] = df_display['Ultimo'].apply(lambda x: f"€{x:.2f}")
        df_display['Trend'] = df_display['Trend'].fillna('↕️')

        def formatta_variazione(perc):
            if pd.isna(perc):
                return 'N/A'
            if perc > 0:
                return f"🔴 +{perc:.1f}%"
            if perc < 0:
                return f"🟢 {perc:.1f}%"
            return f"{perc:.1f}%"

        def formatta_impatto(valore):
            if pd.isna(valore):
                return '-'
            if valore > 0:
                return f"🔴 €{valore:.0f}"
            if valore < 0:
                return f"🟢 €{valore:.0f}"
            return '€0'

        df_display['Aumento_Perc'] = df_display['Aumento_Perc'].apply(formatta_variazione)
        df_display['Impatto_Stimato'] = df_display['Impatto_Stimato'].apply(formatta_impatto)

        df_display = df_display.reset_index(drop=True)
        df_display = df_display[['Prodotto', 'Categoria', 'Fornitore', 'Storico', 'Media', 'Ultimo', 'Trend', 'Aumento_Perc', 'Impatto_Stimato', 'Data', 'N_Fattura', 'NumeroDocumento']]
        df_display.columns = ['Prodotto', 'Cat.', 'Fornitore', 'Storico (ultimi 5)', 'Media storico', 'Ultimo', 'Trend', 'Var. %', 'Imp. €/mese', 'Data ultima', 'Fattura', 'N° Fattura']

        num_righe_alert = len(df_display)
        altezza_alert = min(max(num_righe_alert * 35 + 50, 220), 520)

        st.dataframe(
            df_display,
            use_container_width=True,
            height=altezza_alert,
            hide_index=True
        )

        # Export Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_alert.to_excel(writer, sheet_name='Variazioni Prezzo', index=False)

        _col_badge_v, _col_xls_v = st.columns([9, 0.7])
        with _col_badge_v:
            st.markdown(
                f"""
            <div style="display:inline-block; width:fit-content; background:linear-gradient(135deg,#dbeafe,#eff6ff);
                        border:1px solid #93c5fd; color:#1e40af; border-radius:8px; padding:10px 14px;
                        font-weight:700; margin-top:8px; margin-bottom:4px;">
                ⚠️ {len(df_alert)} Variazioni Rilevate
            </div>
            """,
                unsafe_allow_html=True,
            )
        with _col_xls_v:
            # cp_download_excel_alert button CSS ora in common.css
            st.download_button(
                label="XLS",
                data=excel_buffer.getvalue(),
                file_name=f"variazioni_prezzo_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cp_download_excel_alert",
                use_container_width=False,
            )

        st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)

    # ── GRAFICO: Storico prezzo acquisto (sempre visibile) ──
    st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📈 Storico prezzo acquisto</h3>", unsafe_allow_html=True)
    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

    _has_alerts = not df_alert.empty
    _scope_options = ["Solo con alert", "Tutti i prodotti"] if _has_alerts else ["Tutti i prodotti"]
    if st.session_state.get('cp_scope_grafico') not in _scope_options:
        st.session_state['cp_scope_grafico'] = _scope_options[0]

    PERIODI = {"Ultimi 30 giorni": 30, "Ultimi 90 giorni": 90, "Ultimi 180 giorni": 180, "Tutto": 0}

    # 3 filtri in linea
    _col_scope, _col_prodotto, _col_periodo = st.columns(3)
    with _col_scope:
        scope_grafico = st.selectbox(
            "Prodotti da visualizzare",
            options=_scope_options,
            key="cp_scope_grafico",
        )

    if scope_grafico == "Solo con alert" and _has_alerts:
        prodotti_grafico = []
        for valore in df_alert['Prodotto'].dropna().astype(str).tolist():
            label = valore.replace(" ⚠️ >6m", "").strip()
            if label and label not in prodotti_grafico:
                prodotti_grafico.append(label)
    else:
        prodotti_grafico = sorted(
            df_alert_source['Descrizione'].dropna().astype(str).str.strip().unique().tolist()
        )

    if not prodotti_grafico:
        st.info("📭 Nessun prodotto disponibile per il grafico.")
    else:
        selected_prodotto = st.session_state.get("cp_prodotto_grafico")
        selected_index = prodotti_grafico.index(selected_prodotto) if selected_prodotto in prodotti_grafico else 0

        with _col_prodotto:
            prodotto_grafico = st.selectbox(
                "Seleziona prodotto",
                options=prodotti_grafico,
                index=selected_index,
                key="cp_prodotto_grafico",
            )

        with _col_periodo:
            periodo_sel = st.selectbox(
                "Seleziona periodo",
                options=list(PERIODI.keys()),
                index=len(PERIODI) - 1,
                key="cp_periodo_grafico",
            )

        df_trend = df_alert_source.copy()
        df_trend['Data_DT'] = pd.to_datetime(df_trend['DataDocumento'], errors='coerce')
        df_trend['PrezzoUnitario'] = pd.to_numeric(df_trend['PrezzoUnitario'], errors='coerce')
        df_trend['TotaleRiga'] = pd.to_numeric(df_trend.get('TotaleRiga'), errors='coerce')
        df_trend['Quantita'] = pd.to_numeric(df_trend.get('Quantita'), errors='coerce')

        # B1: match esatto (con fallback startswith per nomi troncati)
        filtro_chart = prodotto_grafico.strip().upper()
        df_trend['_desc_norm'] = df_trend['Descrizione'].astype(str).str.strip().str.upper()
        _mask_prodotto = df_trend['_desc_norm'] == filtro_chart
        if _mask_prodotto.sum() == 0:
            _mask_prodotto = df_trend['_desc_norm'].str.startswith(filtro_chart, na=False)
        df_trend = df_trend[
            _mask_prodotto
            & df_trend['Data_DT'].notna()
            & df_trend['PrezzoUnitario'].notna()
            & (df_trend['PrezzoUnitario'] > 0)
        ].copy()

        # Prezzo medio calcolato su tutto lo storico del prodotto PRIMA del filtro periodo
        df_trend = df_trend.sort_values(['Data_DT', 'FileOrigine', 'Descrizione'])
        prezzo_medio = float(df_trend['PrezzoUnitario'].mean()) if not df_trend.empty else 0.0

        # Applica filtro temporale
        giorni_periodo = PERIODI[periodo_sel]
        if giorni_periodo > 0:
            data_limite = pd.Timestamp.now() - pd.Timedelta(days=giorni_periodo)
            df_trend = df_trend[df_trend['Data_DT'] >= data_limite]

        if not df_trend.empty and prezzo_medio > 0:
            df_trend['Var_Perc'] = ((df_trend['PrezzoUnitario'] - prezzo_medio) / prezzo_medio) * 100
            df_trend['VarPercLabel'] = df_trend['Var_Perc'].apply(lambda x: f"{x:+.1f}%")

            n_punti_cp = len(df_trend)

            if n_punti_cp > 20:
                x_axis_cp = dict(
                    tickformat='%d/%m/%y',
                    nticks=12,
                    tickangle=45,
                    tickfont=dict(size=13, color='#6b7280', family='Arial'),
                    showgrid=False,
                    linecolor='#e5e7eb',
                )
            elif n_punti_cp > 10:
                x_axis_cp = dict(
                    tickformat='%d/%m/%y',
                    tickmode='array',
                    tickvals=df_trend['Data_DT'].dropna().drop_duplicates().tolist(),
                    tickangle=40,
                    tickfont=dict(size=13, color='#6b7280', family='Arial'),
                    showgrid=False,
                    linecolor='#e5e7eb',
                )
            else:
                x_axis_cp = dict(
                    tickformat='%d/%m/%Y',
                    tickmode='array',
                    tickvals=df_trend['Data_DT'].dropna().drop_duplicates().tolist(),
                    tickangle=0,
                    tickfont=dict(size=14, color='#6b7280', family='Arial'),
                    showgrid=False,
                    linecolor='#e5e7eb',
                )

            y_axis_cp = dict(
                nticks=7,
                ticksuffix='%',
                tickformat='.1f',
                tickfont=dict(size=14, color='#6b7280', family='Arial'),
                gridcolor='rgba(229,231,235,0.7)',
                gridwidth=1,
                zeroline=False,
            )

            fig_prezzo = px.line(
                df_trend,
                x='Data_DT',
                y='Var_Perc',
                markers=True,
                labels={'Data_DT': '', 'Var_Perc': ''},
                custom_data=['PrezzoUnitario', 'VarPercLabel'],
            )
            fig_prezzo.update_traces(
                line=dict(color='#2563eb', width=2.5, shape='spline'),
                marker=dict(size=7, color='#2563eb', line=dict(color='#ffffff', width=1.5)),
                hovertemplate='<b>%{x|%d/%m/%Y}</b><br>Variazione: <b>%{customdata[1]}</b><br>Prezzo: €%{customdata[0]:.2f}<extra></extra>',
            )
            fig_prezzo.add_scatter(
                x=df_trend['Data_DT'].tolist(),
                y=[0] * len(df_trend),
                mode='lines',
                line=dict(color='#dc2626', width=1.5, dash='dash'),
                showlegend=False,
                hovertemplate='Baseline var. 0%<extra></extra>',
            )
            fig_prezzo.add_annotation(
                x=1.0, xref='paper', y=0, yref='y',
                text=f"<b>Media €{prezzo_medio:.2f}</b>",
                showarrow=False, xanchor='right', yanchor='bottom', yshift=5,
                font=dict(color='#dc2626', size=13, family='Arial'),
                bgcolor='rgba(255,255,255,0.85)',
            )
            fig_prezzo.update_layout(
                height=380,
                hovermode='x unified',
                plot_bgcolor='#f9fafb',
                paper_bgcolor='#ffffff',
                margin=dict(t=20, b=10, l=10, r=80),
                xaxis=x_axis_cp,
                yaxis=y_axis_cp,
                font=dict(size=13, color='#374151', family='Arial'),
                showlegend=False,
            )
            st.plotly_chart(
                fig_prezzo,
                use_container_width=True,
                config={'displayModeBar': False}
            )
        else:
            st.info("📭 Nessun dato disponibile per disegnare lo storico di questo prodotto.")

# ================================================================
# TAB 2: SCONTI E OMAGGI
# ================================================================
elif st.session_state.cp_tab_attivo == "sconti":

    # Carica dati
    with st.spinner("Caricamento sconti e omaggi..."):
        dati_sconti = _carica_sconti_e_omaggi_cached(
            user_id,
            get_current_ristorante_id(),
            data_inizio_filtro.isoformat(),
            data_fine_filtro.isoformat(),
        )

    df_sconti = dati_sconti['sconti']
    df_omaggi = dati_sconti['omaggi']
    totale_risparmiato = dati_sconti['totale_risparmiato']

    # KPI SCONTI E OMAGGI — stesso componente/stile usato nelle pagine analisi (st.metric)
    col_metric1, col_metric2, col_metric3 = st.columns(3)

    _n_sconti = len(df_sconti)
    _n_omaggi = len(df_omaggi)
    _n_voci_tot = _n_sconti + _n_omaggi

    _fornitori_sconti = set(df_sconti['fornitore'].dropna().astype(str).str.strip()) if not df_sconti.empty and 'fornitore' in df_sconti.columns else set()
    _fornitori_omaggi = set(df_omaggi['fornitore'].dropna().astype(str).str.strip()) if not df_omaggi.empty and 'fornitore' in df_omaggi.columns else set()
    _fornitori_coinvolti = len({f for f in (_fornitori_sconti | _fornitori_omaggi) if f})

    with col_metric1:
        _totale_display = _fmt_int_migliaia(totale_risparmiato)
        st.metric("💸 Sconti + Omaggi", f"€{_totale_display}")
        st.caption(f"Sconti: {_n_sconti} | Omaggi: {_n_omaggi}")

    with col_metric2:
        st.metric("🧾 Voci Totali", f"{_n_voci_tot}")
        st.caption(label_periodo)

    with col_metric3:
        st.metric("🏢 N. Fornitori Coinvolti", f"{_fornitori_coinvolti}")
        st.caption("Sconti e omaggi")

    st.markdown("<br>", unsafe_allow_html=True)

    _righe_unificate = []

    if not df_sconti.empty:
        for _, _r in df_sconti.iterrows():
            _righe_unificate.append({
                'Tipo': '💸 Sconto',
                'Prodotto': _r.get('descrizione'),
                'Categoria': _r.get('categoria'),
                'Fornitore': _r.get('fornitore'),
                'Quantità': None,
                'Valore': _r.get('importo_sconto'),
                'Data': _r.get('data_documento'),
                'Fattura': _r.get('file_origine'),
                'N° Fattura': _r.get('numero_documento'),
            })

    if not df_omaggi.empty:
        for _, _r in df_omaggi.iterrows():
            _val_omaggio = _r.get('valore_stimato')
            _righe_unificate.append({
                'Tipo': '🎁 Omaggio',
                'Prodotto': _r.get('descrizione'),
                'Categoria': _r.get('categoria'),
                'Fornitore': _r.get('fornitore'),
                'Quantità': _r.get('quantita'),
                'Valore': _val_omaggio if pd.notna(pd.to_numeric(_val_omaggio, errors='coerce')) else 0.0,
                'Data': _r.get('data_documento'),
                'Fattura': _r.get('file_origine'),
                'N° Fattura': _r.get('numero_documento'),
            })

    if _righe_unificate:
        df_unificato = pd.DataFrame(_righe_unificate)
        df_unificato['Data'] = pd.to_datetime(df_unificato['Data'], errors='coerce')
        df_unificato['Valore'] = pd.to_numeric(df_unificato['Valore'], errors='coerce').fillna(0.0)
        df_unificato = df_unificato.sort_values(['Data', 'Fornitore', 'Prodotto'], ascending=[False, True, True], na_position='last')

        num_righe_unificate = len(df_unificato)
        altezza_unificata = min(max(num_righe_unificate * 35 + 50, 240), 560)

        st.dataframe(
            df_unificato,
            hide_index=True,
            use_container_width=True,
            height=altezza_unificata,
            column_config={
                'Tipo': st.column_config.TextColumn('Tipo', width='small'),
                'Prodotto': st.column_config.TextColumn('Prodotto', width='large'),
                'Categoria': st.column_config.TextColumn('Categoria', width='medium'),
                'Fornitore': st.column_config.TextColumn('Fornitore', width='medium'),
                'Quantità': st.column_config.NumberColumn('Quantità', format='%.2f'),
                'Valore': st.column_config.NumberColumn('Valore (€)', format='€%.2f'),
                'Data': st.column_config.DateColumn('Data', format='DD/MM/YYYY'),
                'Fattura': st.column_config.TextColumn('Fattura', width='medium'),
                'N° Fattura': st.column_config.TextColumn('N° Fattura', width='small'),
            }
        )

        excel_unificato = io.BytesIO()
        with pd.ExcelWriter(excel_unificato, engine='openpyxl') as writer:
            df_unificato.to_excel(writer, sheet_name='Sconti_Omaggi', index=False)

        _col_xls_pad, _col_xls_btn = st.columns([10, 1])
        with _col_xls_btn:
            st.download_button(
                label="XLS",
                data=excel_unificato.getvalue(),
                file_name=f"sconti_omaggi_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cp_download_excel_sconti_omaggi_unificato",
                use_container_width=True,
            )
    else:
        st.info(f"📊 Nessuno sconto o omaggio ricevuto nel periodo {label_periodo.lower()}")


# ================================================================
# TAB 3: NOTE DI CREDITO
# ================================================================
elif st.session_state.cp_tab_attivo == "nc":

    df_nc = df_filtrato[df_filtrato['_special_bucket'] == SPECIAL_ROW_STORNO].copy()

    # ============================================================
    # FILTRI NOTE DI CREDITO
    # ============================================================
    if not df_nc.empty:
        col_search_nc, col_fornitore_nc = st.columns([3, 2])

        with col_search_nc:
            search_nc = st.text_input(
                "🔍 Cerca nella descrizione",
                "",
                placeholder="Digita per filtrare...",
                key="cp_search_nc"
            )

        with col_fornitore_nc:
            # Normalizza case per evitare duplicati (es. "METRO" e "Metro")
            fornitori_norm = df_nc['Fornitore'].dropna().str.strip().str.title()
            fornitori_nc = ["Tutti"] + sorted(fornitori_norm.unique().tolist())
            filtro_fornitore_nc = st.selectbox(
                "🏭 Fornitore",
                options=fornitori_nc,
                key="cp_filtro_fornitore_nc"
            )

        # Applica filtri
        df_nc_view = df_nc.copy()

        if search_nc:
            df_nc_view = df_nc_view[df_nc_view['Descrizione'].str.contains(search_nc, case=False, na=False, regex=False)]

        if filtro_fornitore_nc != "Tutti":
            df_nc_view = df_nc_view[df_nc_view['Fornitore'].str.strip().str.title() == filtro_fornitore_nc]

        # ============================================================
        # TABELLA NOTE DI CREDITO
        # ============================================================
        if not df_nc_view.empty:

            # Prepara colonne per display
            cols_display = ['FileOrigine', 'NumeroDocumento', 'DataDocumento', 'Fornitore', 'Descrizione', 'Categoria',
                           'Quantita', 'PrezzoUnitario', 'TotaleRiga']
            
            df_nc_display = df_nc_view[[c for c in cols_display if c in df_nc_view.columns]].copy()
            
            # Mostra importi in valore assoluto per chiarezza (sono crediti, non costi)
            if 'PrezzoUnitario' in df_nc_display.columns:
                df_nc_display['PrezzoUnitario'] = df_nc_display['PrezzoUnitario'].abs()
            if 'TotaleRiga' in df_nc_display.columns:
                df_nc_display['TotaleRiga'] = df_nc_display['TotaleRiga'].abs()

            df_nc_display = df_nc_display.reset_index(drop=True)

            # Rinomina colonne
            rename_map = {
                'FileOrigine': 'Documento',
                'NumeroDocumento': 'N° Fattura',
                'DataDocumento': 'Data',
                'Fornitore': 'Fornitore',
                'Descrizione': 'Descrizione',
                'Categoria': 'Categoria',
                'Quantita': 'Q.tà',
                'PrezzoUnitario': 'Prezzo Unit.',
                'TotaleRiga': 'Credito'
            }
            df_nc_display.rename(columns={k: v for k, v in rename_map.items() if k in df_nc_display.columns}, inplace=True)

            num_righe_nc_view = len(df_nc_display)
            altezza_nc = min(max(num_righe_nc_view * 35 + 50, 200), 500)

            st.dataframe(
                df_nc_display,
                hide_index=True,
                use_container_width=True,
                height=altezza_nc,
                column_config={
                    'Data': st.column_config.DateColumn('Data', format="DD/MM/YYYY"),
                    'Q.tà': st.column_config.NumberColumn('Q.tà', format="%.2f"),
                    'Prezzo Unit.': st.column_config.NumberColumn('Prezzo Unit.', format="€%.2f"),
                    'Credito': st.column_config.NumberColumn('Credito', format="€%.2f", help="Importo nota di credito (valore assoluto)"),
                    'N° Fattura': st.column_config.TextColumn('N° Fattura', width="small"),
                }
            )

            # Box riepilogativo blu (usa dati FILTRATI per coerenza con tabella)
            totale_nc_view = df_nc_view['TotaleRiga'].sum()
            num_doc_nc_view = df_nc_view['FileOrigine'].nunique()
            num_righe_nc_view_box = len(df_nc_view)

            # Export Excel note di credito
            excel_nc = io.BytesIO()
            with pd.ExcelWriter(excel_nc, engine='openpyxl') as writer:
                df_nc_display.to_excel(writer, sheet_name='Note di Credito', index=False)

            col_riep_nc, col_btn_nc = st.columns([11, 1])
            with col_riep_nc:
                st.markdown("""
                <div style="display:inline-block; background-color:#E3F2FD; padding:10px 16px; border-radius:8px;
                            border:2px solid #2196F3; margin-top:8px; box-sizing:border-box; width:auto; max-width:100%;">
                    <span style="color:#1565C0; font-weight:700; font-size:clamp(0.88rem, 2vw, 1rem); white-space:nowrap; line-height:1.35;">
                        📋 N. Documenti: {} &nbsp;|&nbsp; N. Righe: {} &nbsp;|&nbsp; 💰 Totale Note di Credito: €{:.2f}
                    </span>
                </div>
                """.format(num_doc_nc_view, num_righe_nc_view_box, abs(totale_nc_view)),
                unsafe_allow_html=True)
            with col_btn_nc:
                st.markdown("<div style='margin-top: 4px;'></div>", unsafe_allow_html=True)
                st.download_button(
                    label="XLS",
                    data=excel_nc.getvalue(),
                    file_name=f"note_credito_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="cp_download_excel_nc",
                    use_container_width=False,
                )
        else:
            st.info("📊 Nessun risultato con i filtri applicati")

    else:
        st.info(f"📊 Nessuna nota di credito nel periodo {label_periodo.lower()}")
