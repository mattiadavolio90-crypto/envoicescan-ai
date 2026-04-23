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
    carica_sconti_e_omaggi,
    get_custom_tags,
)

# Logger
logger = get_logger('controllo_prezzi')

# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Controllo Prezzi - OH YEAH! Hub",
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

# CSS globale per bottoni Excel verdi
st.markdown("""
<style>
div.st-key-cp_download_excel_alert .stDownloadButton button,
div.st-key-cp_download_excel_sconti .stDownloadButton button,
div.st-key-cp_download_excel_omaggi .stDownloadButton button,
div.st-key-cp_download_excel_nc .stDownloadButton button {
    background-color: #22c55e !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
div.st-key-cp_download_excel_alert .stDownloadButton button:hover,
div.st-key-cp_download_excel_sconti .stDownloadButton button:hover,
div.st-key-cp_download_excel_omaggi .stDownloadButton button:hover,
div.st-key-cp_download_excel_nc .stDownloadButton button:hover {
    background-color: #16a34a !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================
# FILTRO PERIODO
# ============================================
from utils.period_helper import PERIODO_OPTIONS, calcola_date_periodo, risolvi_periodo

date_periodo = calcola_date_periodo()
oggi_date = date_periodo['oggi']
inizio_anno = date_periodo['inizio_anno']

if 'cp_periodo_dropdown' not in st.session_state:
    st.session_state.cp_periodo_dropdown = "🗓️ Anno in Corso"

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

if data_inizio_filtro is None:
    # Periodo Personalizzato
    st.markdown("##### Seleziona Range Date")
    col_da, col_a = st.columns(2)

    if 'cp_data_inizio' not in st.session_state:
        st.session_state.cp_data_inizio = inizio_anno
    if 'cp_data_fine' not in st.session_state:
        st.session_state.cp_data_fine = oggi_date

    with col_da:
        data_inizio_custom = st.date_input(
            "📅 Da",
            value=st.session_state.cp_data_inizio,
            min_value=inizio_anno,
            key="cp_data_da_custom"
        )

    with col_a:
        data_fine_custom = st.date_input(
            "📅 A",
            value=st.session_state.cp_data_fine,
            min_value=inizio_anno,
            key="cp_data_a_custom"
        )

    if data_inizio_custom > data_fine_custom:
        st.error("⚠️ La data iniziale deve essere precedente alla data finale!")
        data_inizio_filtro = st.session_state.cp_data_inizio
        data_fine_filtro = st.session_state.cp_data_fine
    else:
        st.session_state.cp_data_inizio = data_inizio_custom
        st.session_state.cp_data_fine = data_fine_custom
        data_inizio_filtro = data_inizio_custom
        data_fine_filtro = data_fine_custom

    label_periodo = f"{data_inizio_filtro.strftime('%d/%m/%Y')} → {data_fine_filtro.strftime('%d/%m/%Y')}"

with col_info_periodo:
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

# ============================================
# CARICAMENTO DATI
# ============================================
with st.spinner("Caricamento dati fatture..."):
    df_all = carica_e_prepara_dataframe(user_id, ristorante_id=current_ristorante)
    custom_tags = get_custom_tags(user_id, current_ristorante)

if df_all.empty:
    st.info("📊 Nessuna fattura disponibile. Carica le fatture dalla pagina Analisi Fatture AI.")
    st.stop()

# Filtro periodo
df_all['Data_DT'] = pd.to_datetime(df_all['DataDocumento'], errors='coerce')
mask_periodo = (
    (df_all['Data_DT'].dt.date >= data_inizio_filtro) &
    (df_all['Data_DT'].dt.date <= data_fine_filtro)
)
df_filtrato = df_all[mask_periodo].copy()

if df_filtrato.empty:
    st.warning(f"📊 Nessun dato disponibile per il periodo: {label_periodo}")
    st.stop()

st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

# ============================================
# NAVIGAZIONE TAB
# ============================================
if 'cp_tab_attivo' not in st.session_state:
    st.session_state.cp_tab_attivo = "variazioni"

col_t1, col_t2, col_t3 = st.columns(3)

with col_t1:
    if st.button("📈 VARIAZIONI\nPREZZO", key="cp_btn_variazioni", use_container_width=True,
                 type="primary" if st.session_state.cp_tab_attivo == "variazioni" else "secondary"):
        if st.session_state.cp_tab_attivo != "variazioni":
            st.session_state.cp_tab_attivo = "variazioni"
            st.rerun()

with col_t2:
    if st.button("🎁 SCONTI E\nOMAGGI", key="cp_btn_sconti", use_container_width=True,
                 type="primary" if st.session_state.cp_tab_attivo == "sconti" else "secondary"):
        if st.session_state.cp_tab_attivo != "sconti":
            st.session_state.cp_tab_attivo = "sconti"
            st.rerun()

with col_t3:
    if st.button("📋 NOTE DI\nCREDITO", key="cp_btn_nc", use_container_width=True,
                 type="primary" if st.session_state.cp_tab_attivo == "nc" else "secondary"):
        if st.session_state.cp_tab_attivo != "nc":
            st.session_state.cp_tab_attivo = "nc"
            st.rerun()

# CSS bottoni tab e download (caricati da file statico condiviso)
from utils.ui_helpers import load_css
load_css('common.css')

st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

# ================================================================
# TAB 1: VARIAZIONI PREZZO
# ================================================================
if st.session_state.cp_tab_attivo == "variazioni":

    # ── Riga filtro: Soglia + Badge conteggio ──
    col_soglia, col_badge = st.columns([1, 3])

    with col_soglia:
        soglia_aumento = st.number_input(
            "Soglia %",
            min_value=0,
            max_value=100,
            value=5,
            step=1,
            key="cp_soglia_alert",
            help="Mostra solo variazioni con valore assoluto ≥ X%"
        )

    # Calcola alert (solo F&B, storico completo)
    df_alert_source = df_all
    df_alert = calcola_alert(df_alert_source, soglia_aumento)

    with col_badge:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if not df_alert.empty:
            st.info(f"⚠️ **{len(df_alert)} Variazioni Rilevate** (soglia ≥ {soglia_aumento}%) - Solo prodotti Food & Beverage")
        else:
            st.markdown(
                f"<p style='margin:0; color:#0B3A82; font-weight:700;'>✅ Nessuna variazione rilevata con soglia ≥ {soglia_aumento}%</p>",
                unsafe_allow_html=True,
            )

    if not df_alert.empty:

        # ── TABELLA ──
        st.caption("📖 **Storico**: ultimi 5 prezzi incluso l'ultimo | **Trend**: andamento recente | **Imp. €/mese**: stima peso economico del rincaro o ribasso | ⏰ Confronto su tutto lo storico, indipendente dal filtro periodo")

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
        df_display = df_display[['Prodotto', 'Categoria', 'Fornitore', 'Storico', 'Media', 'Ultimo', 'Trend', 'Aumento_Perc', 'Impatto_Stimato', 'Data', 'N_Fattura']]
        df_display.columns = ['Prodotto', 'Cat.', 'Fornitore', 'Storico (ultimi 5)', 'Media storico', 'Ultimo', 'Trend', 'Var. %', 'Imp. €/mese', 'Data ultima', 'N.Fattura']

        num_righe_alert = len(df_display)
        altezza_alert = min(max(num_righe_alert * 35 + 50, 220), 520)

        st.dataframe(
            df_display,
            width='stretch',
            height=altezza_alert,
            hide_index=True
        )

        # Export Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_alert.to_excel(writer, sheet_name='Variazioni Prezzo', index=False)

        col_spacer, col_btn = st.columns([11, 1])
        with col_btn:
            st.download_button(
                label="Excel",
                data=excel_buffer.getvalue(),
                file_name=f"variazioni_prezzo_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cp_download_excel_alert",
                type="primary",
                use_container_width=True
            )

        # ── KPI CARDS (dimensione fissa, colori dinamici, nessun decimale) ──
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

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
            impatto_label = f"+€{abs(impatto_netto):,}/mese"
        elif impatto_netto < 0:
            colore_impatto = "#16a34a"
            impatto_label = f"-€{abs(impatto_netto):,}/mese"
        else:
            colore_impatto = "#1e40af"
            impatto_label = "€0/mese"

        st.markdown(f"""
        <style>
        .cp-kpi-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 1.5rem;
        }}
        .cp-kpi-card {{
            flex: 1 1 0;
            min-width: 0;
            background: linear-gradient(135deg, rgba(248,249,250,0.95), rgba(233,236,239,0.95));
            padding: clamp(0.75rem, 2vw, 1.25rem);
            border-radius: 12px;
            border: 1px solid rgba(206,212,218,0.5);
            box-shadow: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.05);
            text-align: center;
            box-sizing: border-box;
            aspect-ratio: auto;
        }}
        .cp-kpi-card .kpi-label {{
            color: #2563eb;
            font-size: clamp(0.7rem, 1.6vw, 0.85rem);
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .cp-kpi-card .kpi-value {{
            font-size: clamp(1.2rem, 3vw, 1.8rem);
            font-weight: 700;
            line-height: 1.2;
        }}
        </style>
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

        st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)

    # ── GRAFICO: Storico prezzo acquisto (sempre visibile) ──
    st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📈 Storico prezzo acquisto</h3>", unsafe_allow_html=True)
    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

    # Toggle: solo prodotti con alert o tutti
    st.markdown("<p style='font-size:1.15rem; font-weight:700; color:#1e40af; margin-bottom:0.25rem;'>Prodotti da visualizzare</p>", unsafe_allow_html=True)

    _has_alerts = not df_alert.empty
    _scope_options = ["Solo con alert", "Tutti i prodotti"] if _has_alerts else ["Tutti i prodotti"]
    if st.session_state.get('cp_scope_grafico') not in _scope_options:
        st.session_state.cp_scope_grafico = _scope_options[0]

    scope_grafico = st.radio(
        "Prodotti da visualizzare",
        label_visibility="collapsed",
        options=_scope_options,
        index=0,
        horizontal=True,
        key="cp_scope_grafico",
    )
    st.markdown("<div style='margin-top: 0.75rem;'></div>", unsafe_allow_html=True)

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

    st.markdown("<p style='font-size:1.15rem; font-weight:700; color:#1e40af; margin-bottom:0.25rem;'>Seleziona prodotto</p>", unsafe_allow_html=True)

    if not prodotti_grafico:
        st.info("📭 Nessun prodotto disponibile per il grafico.")
    else:
        if scope_grafico == "Tutti i prodotti":
            filtro_prodotto_grafico = st.text_input(
                "Cerca prodotto",
                value=st.session_state.get("cp_filtro_prodotto_grafico", ""),
                key="cp_filtro_prodotto_grafico",
                placeholder="Scrivi qui per filtrare l'elenco prodotti",
                label_visibility="collapsed",
            )
            filtro_norm = filtro_prodotto_grafico.strip().lower()
        else:
            filtro_norm = ""

        if filtro_norm:
            prodotti_filtrati = [
                prodotto for prodotto in prodotti_grafico
                if filtro_norm in prodotto.lower()
            ]
        else:
            prodotti_filtrati = prodotti_grafico

        if not prodotti_filtrati:
            st.info("🔎 Nessun prodotto trovato con questo filtro. Prova a scrivere meno caratteri o una parola diversa.")
            st.stop()

        if scope_grafico == "Tutti i prodotti":
            st.caption(f"{len(prodotti_filtrati)} prodotti disponibili")

        selected_prodotto = st.session_state.get("cp_prodotto_grafico")
        selected_index = prodotti_filtrati.index(selected_prodotto) if selected_prodotto in prodotti_filtrati else 0

        prodotto_grafico = st.selectbox(
            "Seleziona prodotto",
            options=prodotti_filtrati,
            index=selected_index,
            key="cp_prodotto_grafico",
            label_visibility="collapsed"
        )
        st.markdown("<div style='margin-top: 0.75rem;'></div>", unsafe_allow_html=True)

        # Filtro temporale
        PERIODI = {"Ultimi 30 giorni": 30, "Ultimi 90 giorni": 90, "Ultimi 180 giorni": 180, "Tutto": 0}
        st.markdown("<p style='font-size:1.15rem; font-weight:700; color:#1e40af; margin-bottom:0.25rem;'>Seleziona periodo</p>", unsafe_allow_html=True)
        periodo_sel = st.selectbox(
            "Seleziona periodo",
            options=list(PERIODI.keys()),
            index=len(PERIODI) - 1,
            key="cp_periodo_grafico",
            label_visibility="collapsed"
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

            fig_prezzo = px.line(
                df_trend,
                x='Data_DT',
                y='Var_Perc',
                markers=True,
                title=f"Variazione % prezzo — {prodotto_grafico}",
                labels={'Data_DT': '', 'Var_Perc': 'Variazione %'},
                custom_data=['PrezzoUnitario', 'VarPercLabel'],
            )
            fig_prezzo.update_traces(
                line=dict(color='#2563eb', width=2),
                marker=dict(size=8, color='#1d4ed8'),
            )

            fig_prezzo.update_traces(
                hovertemplate="<b>Prezzo acquisto</b>: €%{customdata[0]:.2f}<br><b>Variazione vs media</b>: %{customdata[1]}<extra></extra>"
            )
            fig_prezzo.add_hline(
                y=0,
                line_dash='dash',
                line_color='#dc2626',
                annotation_text=f"Prezzo medio di acquisto €{prezzo_medio:.2f}",
                annotation_position='top left',
                annotation_font=dict(color='#dc2626', size=16, family='Arial Black'),
            )
            fig_prezzo.update_layout(
                height=420,
                hovermode='closest',
                xaxis=dict(
                    tickformat='%d/%m/%Y',
                    tickfont=dict(size=16, color='#1e40af', family='Arial Black')
                ),
                yaxis=dict(
                    tickfont=dict(size=16, color='#1e40af', family='Arial Black')
                ),
                title=dict(font=dict(size=18, color='#111111', family='Arial Black')),
                font=dict(size=16, color='#1e40af', family='Arial'),
                yaxis_title_font=dict(size=18, color='#1e40af', family='Arial Black'),
                xaxis_title_font=dict(size=18, color='#1e40af', family='Arial Black'),
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

    st.markdown(
        "<p style='color:#1e40af; font-size:0.95rem; font-weight:600; margin-bottom:0.8rem;'>📖 <b>Sconti</b>: totale sconti ricevuti | <b>Omaggi</b>: valore stimato dall'ultimo prezzo d'acquisto × quantità se disponibile | <b>Totale</b>: somma sconti + omaggi | Solo F&amp;B</p>",
        unsafe_allow_html=True,
    )

    # Carica dati
    with st.spinner("Caricamento sconti e omaggi..."):
        dati_sconti = carica_sconti_e_omaggi(user_id, data_inizio_filtro, data_fine_filtro, ristorante_id=get_current_ristorante_id())

    df_sconti = dati_sconti['sconti']
    df_omaggi = dati_sconti['omaggi']
    totale_risparmiato = dati_sconti['totale_risparmiato']

    # ============================================================
    # KPI SCONTI E OMAGGI - Stile identico alla pagina principale
    # ============================================================
    st.markdown("""
    <style>
    .kpi-card-cp {
        background: linear-gradient(135deg, rgba(248, 249, 250, 0.95), rgba(233, 236, 239, 0.95));
        padding: clamp(0.75rem, 2vw, 1.25rem);
        border-radius: 12px;
        border: 1px solid rgba(206, 212, 218, 0.5);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.05);
        backdrop-filter: blur(10px);
        text-align: center;
        min-height: 100px;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .kpi-card-cp .kpi-label {
        color: #2563eb;
        font-weight: 600;
        font-size: clamp(0.7rem, 1.6vw, 0.85rem);
        margin-bottom: 6px;
        line-height: 1.3;
    }
    .kpi-card-cp .kpi-value {
        color: #1e40af;
        font-size: clamp(1.3rem, 3.5vw, 1.75rem);
        font-weight: 700;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    </style>
    """, unsafe_allow_html=True)

    col_metric1, col_metric2, col_metric3 = st.columns(3)

    importo_sconti = df_sconti['importo_sconto'].sum() if not df_sconti.empty else 0.0
    valore_omaggi = dati_sconti.get('totale_omaggi', totale_risparmiato - importo_sconti)
    _omaggi_ha_storico = valore_omaggi is not None and not (isinstance(valore_omaggi, float) and valore_omaggi == 0.0 and not df_omaggi.empty)

    with col_metric1:
        st.markdown(f"""
        <div class="kpi-card-cp">
            <div class="kpi-label">💸 Sconti Applicati</div>
            <div class="kpi-value">€{importo_sconti:,.2f}</div>
            <div style="font-size: clamp(0.65rem, 1.4vw, 0.75rem); color: #6b7280; margin-top: 4px;">{len(df_sconti)} prodotti scontati</div>
        </div>
        """, unsafe_allow_html=True)

    with col_metric2:
        _omaggi_display = f"€{valore_omaggi:,.2f}" if _omaggi_ha_storico else "N/D"
        _omaggi_sub = f"{len(df_omaggi)} prodotti omaggio" if _omaggi_ha_storico else f"{len(df_omaggi)} omaggi — nessuno storico prezzi"
        st.markdown(f"""
        <div class="kpi-card-cp">
            <div class="kpi-label">🎁 Omaggi Ricevuti</div>
            <div class="kpi-value">{_omaggi_display}</div>
            <div style="font-size: clamp(0.65rem, 1.4vw, 0.75rem); color: #6b7280; margin-top: 4px;">{_omaggi_sub}</div>
        </div>
        """, unsafe_allow_html=True)

    with col_metric3:
        st.markdown(f"""
        <div class="kpi-card-cp">
            <div class="kpi-label">✅ Totale Risparmiato</div>
            <div class="kpi-value">€{totale_risparmiato:,.2f}</div>
            <div style="font-size: clamp(0.65rem, 1.4vw, 0.75rem); color: #6b7280; margin-top: 4px;">{label_periodo}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================================================
    # TABELLA SCONTI
    # ============================================================
    if not df_sconti.empty:
        with st.expander("💸 Dettaglio Sconti Applicati", expanded=True):
            st.markdown(f"**{len(df_sconti)} sconti** ricevuti dai fornitori")
            st.caption("Solo prodotti Food & Beverage - Escluse spese generali")

            df_sconti_view = df_sconti[[
                'descrizione',
                'categoria',
                'fornitore',
                'importo_sconto',
                'data_documento',
                'file_origine'
            ]].copy()

            df_sconti_view = df_sconti_view.reset_index(drop=True)

            df_sconti_view.columns = [
                'Prodotto',
                'Categoria',
                'Fornitore',
                'Sconto',
                'Data',
                'Fattura'
            ]

            num_righe_sconti = len(df_sconti_view)
            altezza_sconti = min(max(num_righe_sconti * 35 + 50, 200), 500)

            st.dataframe(
                df_sconti_view,
                hide_index=True,
                width='stretch',
                height=altezza_sconti,
                column_config={
                    'Prodotto': st.column_config.TextColumn('Prodotto', width="large"),
                    'Categoria': st.column_config.TextColumn('Categoria', width="medium"),
                    'Fornitore': st.column_config.TextColumn('Fornitore', width="medium"),
                    'Sconto': st.column_config.NumberColumn('Sconto', format="€%.2f", help="Importo sconto ricevuto"),
                    'Data': st.column_config.DateColumn('Data', format="DD/MM/YYYY"),
                    'Fattura': st.column_config.TextColumn('Fattura', width="medium")
                }
            )

            # Export Excel sconti
            excel_sconti = io.BytesIO()
            with pd.ExcelWriter(excel_sconti, engine='openpyxl') as writer:
                df_sconti_view.to_excel(writer, sheet_name='Sconti', index=False)

            col_spacer, col_btn = st.columns([11, 1])
            with col_btn:
                st.download_button(
                    label="Excel",
                    data=excel_sconti.getvalue(),
                    file_name=f"sconti_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="cp_download_excel_sconti",
                    type="primary",
                    use_container_width=True
                )

    else:
        st.info(f"📊 Nessuno sconto applicato nel periodo {label_periodo.lower()}")

    # ============================================================
    # TABELLA OMAGGI
    # ============================================================
    st.markdown("<div style='margin-top: 1.2rem;'></div>", unsafe_allow_html=True)
    if not df_omaggi.empty:
        with st.expander(f"🎁 Dettaglio Omaggi ({len(df_omaggi)})", expanded=False):
            st.markdown(f"**{len(df_omaggi)} omaggi** ricevuti dai fornitori")
            st.caption("Solo prodotti Food & Beverage - Escluse spese generali")

            cols_omaggi = ['descrizione', 'fornitore', 'quantita', 'data_documento', 'file_origine']
            col_names = ['Prodotto', 'Fornitore', 'Quantità', 'Data', 'Fattura']
            has_prezzo_storico = 'ultimo_prezzo' in df_omaggi.columns
            if has_prezzo_storico:
                cols_omaggi.extend(['ultimo_prezzo', 'valore_stimato'])
                col_names.extend(['Ultimo Prezzo', 'Valore Stimato'])

            df_omaggi_view = df_omaggi[[c for c in cols_omaggi if c in df_omaggi.columns]].copy()
            df_omaggi_view = df_omaggi_view.reset_index(drop=True)
            df_omaggi_view.columns = col_names[:len(df_omaggi_view.columns)]

            num_righe_omaggi = len(df_omaggi_view)
            altezza_omaggi = min(max(num_righe_omaggi * 35 + 50, 200), 500)

            col_cfg = {
                'Data': st.column_config.DateColumn('Data', format="DD/MM/YYYY"),
            }
            if has_prezzo_storico:
                col_cfg['Ultimo Prezzo'] = st.column_config.NumberColumn(
                    'Ultimo Prezzo', format="€%.2f",
                    help="Ultimo prezzo d'acquisto prima dell'omaggio (stesso fornitore)"
                )
                col_cfg['Valore Stimato'] = st.column_config.NumberColumn(
                    'Valore Stimato', format="€%.2f",
                    help="Valore stimato: ultimo prezzo × quantità"
                )

            st.dataframe(
                df_omaggi_view,
                hide_index=True,
                width='stretch',
                height=altezza_omaggi,
                column_config=col_cfg
            )

            st.info("ℹ️ Ultimo Prezzo = ultimo acquisto disponibile dello stesso prodotto prima dell'omaggio, preferibilmente dallo stesso fornitore.")

            # Export Excel omaggi
            excel_omaggi = io.BytesIO()
            with pd.ExcelWriter(excel_omaggi, engine='openpyxl') as writer:
                df_omaggi_view.to_excel(writer, sheet_name='Omaggi', index=False)

            col_spacer, col_btn = st.columns([11, 1])
            with col_btn:
                st.download_button(
                    label="Excel",
                    data=excel_omaggi.getvalue(),
                    file_name=f"omaggi_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="cp_download_excel_omaggi",
                    type="primary",
                    use_container_width=True
                )

    if df_sconti.empty and df_omaggi.empty:
        st.info(f"📊 Nessuno sconto o omaggio ricevuto nel periodo {label_periodo.lower()}")


# ================================================================
# TAB 3: NOTE DI CREDITO
# ================================================================
elif st.session_state.cp_tab_attivo == "nc":

    # Filtra note di credito: TD04 oppure importi negativi (per dati pre-migrazione)
    # NOTA: TipoDocumento ha default 'TD01' nel caricamento, quindi per fatture
    # pre-migrazione il campo esiste ma vale 'TD01'. Serve combinare entrambi i criteri.
    # NC = documenti TD04 oppure INTERO documento con totale negativo (non singole righe sconto)
    mask_td04 = (df_filtrato['TipoDocumento'] == 'TD04') if 'TipoDocumento' in df_filtrato.columns else pd.Series(False, index=df_filtrato.index)
    # Per documenti non-TD04, consideriamo NC solo se il totale del documento è negativo
    _totale_per_doc = df_filtrato.groupby('FileOrigine')['TotaleRiga'].transform('sum')
    mask_doc_negativo = (_totale_per_doc < 0) & ~mask_td04
    mask_nc = mask_td04 | mask_doc_negativo
    
    df_nc = df_filtrato[mask_nc].copy()

    st.caption("📖 **Note di Credito**: documenti TD04 o fatture con totale complessivo negativo. Le singole righe sconto all'interno di fatture normali sono mostrate nel tab Sconti e Omaggi.")

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
            cols_display = ['FileOrigine', 'DataDocumento', 'Fornitore', 'Descrizione', 'Categoria',
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
                width='stretch',
                height=altezza_nc,
                column_config={
                    'Data': st.column_config.DateColumn('Data', format="DD/MM/YYYY"),
                    'Q.tà': st.column_config.NumberColumn('Q.tà', format="%.2f"),
                    'Prezzo Unit.': st.column_config.NumberColumn('Prezzo Unit.', format="€%.2f"),
                    'Credito': st.column_config.NumberColumn('Credito', format="€%.2f", help="Importo nota di credito (valore assoluto)")
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
                st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
                st.download_button(
                    label="Excel",
                    data=excel_nc.getvalue(),
                    file_name=f"note_credito_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="cp_download_excel_nc",
                    type="primary",
                    use_container_width=True
                )
        else:
            st.info("📊 Nessun risultato con i filtri applicati")

    else:
        st.info(f"📊 Nessuna nota di credito nel periodo {label_periodo.lower()}")
