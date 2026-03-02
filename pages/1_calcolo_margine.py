"""
Calcolo Margine - Calcolo MOL (Margine Operativo Lordo)
Pagina dedicata al calcolo del margine operativo mensile del ristorante.
Tabella unica trasposta: voci come righe, mesi come colonne.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time

from config.logger_setup import get_logger
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ristorante_helper import get_current_ristorante_id
from services.margine_service import (
    calcola_costi_automatici_per_anno,
    carica_margini_anno,
    salva_margini_anno,
    calcola_risultati,
    calcola_kpi_anno,
    genera_commenti_kpi,
    export_excel_margini,
    build_transposed_df,
    extract_input_from_transposed,
    MESI_NOMI,
)

# Logger
logger = get_logger('calcolo_margine')

# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Calcolo Marginalità - OH YEAH!",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# NASCONDI SIDEBAR SE NON LOGGATO
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.markdown("""
        <style>
        [data-testid="stSidebar"],
        section[data-testid="stSidebar"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

# ============================================
# AUTENTICAZIONE RICHIESTA
# ============================================
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")

user = st.session_state.user_data
user_id = user["id"]
current_ristorante = get_current_ristorante_id()

if not current_ristorante:
    st.error("⚠️ Nessun ristorante selezionato. Torna alla Dashboard per selezionarne uno.")
    st.stop()

# ============================================
# CONTROLLO PAGINA ABILITATA
# ============================================
_pagine_raw = user.get('pagine_abilitate')
if isinstance(_pagine_raw, str):
    import json as _json
    try:
        _pagine_raw = _json.loads(_pagine_raw)
    except Exception:
        _pagine_raw = None
pagine_abilitate = _pagine_raw or {'marginalita': True, 'workspace': True}
if not pagine_abilitate.get('marginalita', True):
    st.warning("⚠️ Questa pagina non è abilitata per il tuo account. Contatta l'amministratore.")
    st.stop()

# ============================================
# SIDEBAR CONDIVISA
# ============================================
render_sidebar(user)

# ============================================
# HEADER PAGINA
# ============================================
render_oh_yeah_header()

st.markdown("""
<h2 style="font-size: clamp(1.5rem, 4vw, 2.2rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
    💰 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Calcolo Marginalità</span>
</h2>
""", unsafe_allow_html=True)

# ============================================
# TABS: Calcolo Marginalità + Analisi Avanzate
# ============================================
if 'margine_tab' not in st.session_state:
    st.session_state.margine_tab = "calcolo"

col_tab1, col_tab2 = st.columns(2)
with col_tab1:
    if st.button("📊 CALCOLO\nMARGINALITÀ", key="btn_tab_calcolo", use_container_width=True,
                 type="primary" if st.session_state.margine_tab == "calcolo" else "secondary"):
        if st.session_state.margine_tab != "calcolo":
            st.session_state.margine_tab = "calcolo"
            st.rerun()
with col_tab2:
    if st.button("🔬 ANALISI\nAVANZATE", key="btn_tab_analisi", use_container_width=True,
                 type="primary" if st.session_state.margine_tab == "analisi" else "secondary"):
        if st.session_state.margine_tab != "analisi":
            st.session_state.margine_tab = "analisi"
            st.rerun()

# CSS per bottoni tab - stile identico a Analisi Fatture
st.markdown("""
    <style>
    /* Globale: primary button azzurro */
    button[kind="primary"] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        font-weight: bold !important;
    }
    button[kind="primary"]:hover {
        background-color: #0284c7 !important;
        border-color: #0369a1 !important;
    }
    button[kind="primary"]:disabled,
    button[kind="primary"][disabled] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        opacity: 0.5 !important;
    }
    div[data-testid="column"] button[kind="primary"] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        font-weight: bold !important;
    }
    div[data-testid="column"] button[kind="primary"]:hover {
        background-color: #0284c7 !important;
        border-color: #0369a1 !important;
    }
    div[data-testid="column"] button[kind="secondary"] {
        background-color: #f0f2f6 !important;
        color: #31333F !important;
        border: 2px solid #e0e0e0 !important;
    }
    div[data-testid="column"] button[kind="secondary"]:hover {
        background-color: #e0e5eb !important;
        border-color: #0ea5e9 !important;
    }
    div[data-testid="column"] button p {
        font-size: clamp(0.7rem, 1.8vw, 0.95rem) !important;
        line-height: 1.3 !important;
        word-wrap: break-word !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
    }
    div[data-testid="column"] button {
        padding: 0.5rem 0.25rem !important;
        min-height: 3rem !important;
    }
    </style>
""", unsafe_allow_html=True)

if st.session_state.margine_tab == "analisi":
    st.info("🚧 Sezione in costruzione — contenuti in arrivo.")

if st.session_state.margine_tab == "calcolo":

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # ============================================
    # SELETTORE ANNO + BOTTONE AGGIORNA
    # ============================================
    anno_corrente = datetime.now().year
    # Range: da 2026 (primo anno clienti) fino a anno_corrente + 2
    anni_disponibili = list(range(2026, anno_corrente + 3))

    col_anno, col_refresh = st.columns([3, 1])

    with col_anno:
        # Imposta indice default sull'anno corrente
        default_idx = anni_disponibili.index(anno_corrente) if anno_corrente in anni_disponibili else 0
        anno = st.selectbox(
            "📅 Anno di riferimento",
            options=anni_disponibili,
            index=default_idx,
            key="margine_anno_select"
        )

    with col_refresh:
        st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Aggiorna", use_container_width=True, key="margine_refresh",
                     help="Ricalcola costi automatici dalle fatture"):
            # Invalida SOLO la cache di questa funzione, non tutta la cache app
            calcola_costi_automatici_per_anno.clear()
            st.rerun()

    # ============================================
    # CARICA DATI
    # ============================================
    dati_salvati = carica_margini_anno(user_id, current_ristorante, anno)
    costi_fb_mensili, costi_spese_mensili = calcola_costi_automatici_per_anno(
        user_id, current_ristorante, anno
    )

    # ============================================
    # PREPARA DATAFRAME INPUT (12 mesi SEMPRE)
    # ============================================
    # Chiave sessione per dati di lavoro non salvati (unica per ristorante/anno)
    work_key = f"margine_work_{current_ristorante}_{anno}"

    if work_key in st.session_state:
        # Dati di lavoro non salvati presenti → usali come base
        df_input = st.session_state[work_key].copy()
        # Safety: aggiungi colonna Altri_Ricavi_NoIVA se mancante (sessione pre-aggiornamento)
        if 'Altri_Ricavi_NoIVA' not in df_input.columns:
            df_input['Altri_Ricavi_NoIVA'] = 0.0
        # Aggiorna SEMPRE le colonne auto (possono cambiare se caricate nuove fatture)
        for i in range(12):
            mese_num = i + 1
            df_input.at[i, 'Costi_FB_Auto'] = float(costi_fb_mensili.get(mese_num, 0.0))
            df_input.at[i, 'Costi_Spese_Auto'] = float(costi_spese_mensili.get(mese_num, 0.0))
    else:
        # Prima apertura o dopo salvataggio → carica da DB
        data_input = []
        for mese_num in range(1, 13):
            dati_mese = dati_salvati.get(mese_num, {})
            data_input.append({
                'Mese': MESI_NOMI[mese_num - 1],
                'MeseNum': mese_num,
                'Fatt_IVA10': float(dati_mese.get('fatturato_iva10', 0.0) or 0.0),
                'Fatt_IVA22': float(dati_mese.get('fatturato_iva22', 0.0) or 0.0),
                'Altri_Ricavi_NoIVA': float(dati_mese.get('altri_ricavi_noiva', 0.0) or 0.0),
                'Costi_FB_Auto': float(costi_fb_mensili.get(mese_num, 0.0)),
                'Altri_FB': float(dati_mese.get('altri_costi_fb', 0.0) or 0.0),
                'Costi_Spese_Auto': float(costi_spese_mensili.get(mese_num, 0.0)),
                'Altri_Spese': float(dati_mese.get('altri_costi_spese', 0.0) or 0.0),
                'Costo_Dipendenti': float(dati_mese.get('costo_dipendenti', 0.0) or 0.0),
            })
        df_input = pd.DataFrame(data_input)

    # ============================================
    # COMPILAZIONE RAPIDA: Applica valori a tutti i mesi
    # ============================================
    # Applica costo dipendenti se richiesto
    if 'costo_dip_da_applicare' in st.session_state:
        val = st.session_state.costo_dip_da_applicare
        for i in range(12):
            df_input.at[i, 'Costo_Dipendenti'] = val
        del st.session_state.costo_dip_da_applicare
        st.session_state[work_key] = df_input.copy()
        if 'margine_data_editor' in st.session_state:
            del st.session_state['margine_data_editor']

    # Applica altri costi F&B se richiesto
    if 'altri_fb_da_applicare' in st.session_state:
        val = st.session_state.altri_fb_da_applicare
        for i in range(12):
            df_input.at[i, 'Altri_FB'] = val
        del st.session_state.altri_fb_da_applicare
        st.session_state[work_key] = df_input.copy()
        if 'margine_data_editor' in st.session_state:
            del st.session_state['margine_data_editor']

    # Applica altre spese se richiesto
    if 'altre_spese_da_applicare' in st.session_state:
        val = st.session_state.altre_spese_da_applicare
        for i in range(12):
            df_input.at[i, 'Altri_Spese'] = val
        del st.session_state.altre_spese_da_applicare
        st.session_state[work_key] = df_input.copy()
        if 'margine_data_editor' in st.session_state:
            del st.session_state['margine_data_editor']

    # Applica altri ricavi se richiesto
    if 'altri_ricavi_da_applicare' in st.session_state:
        val = st.session_state.altri_ricavi_da_applicare
        for i in range(12):
            df_input.at[i, 'Altri_Ricavi_NoIVA'] = val
        del st.session_state.altri_ricavi_da_applicare
        st.session_state[work_key] = df_input.copy()
        if 'margine_data_editor' in st.session_state:
            del st.session_state['margine_data_editor']

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style="padding: 10px 14px; margin-bottom: 8px;">
        <span style="color: #1e40af; font-weight: 600; font-size: 1rem;">💡 Compilazione Rapida - Applica lo stesso valore a tutti i 12 mesi. Puoi inserire per tutti i mesi un importo fisso per il costo del personale e per i costi F&B e spese generali Extra (non presenti nelle fatture caricate).</span>
    </div>
    """, unsafe_allow_html=True)

    # Quattro colonne per quattro input (tutti sulla stessa riga)
    col_ricavi, col_dip, col_fb, col_spese = st.columns(4)

    with col_ricavi:
        altri_ricavi_standard = st.number_input(
            "💰 Altri ricavi (no iva)",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            key="margine_altri_ricavi_input"
        )
        if st.button("📋 Applica a tutti", use_container_width=True, key="margine_applica_ricavi"):
            st.session_state.altri_ricavi_da_applicare = altri_ricavi_standard
            st.rerun()

    with col_dip:
        costo_dip_standard = st.number_input(
            "💶 Costo personale Lordo",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            key="margine_costo_dip_input"
        )
        if st.button("📋 Applica a tutti", use_container_width=True, key="margine_applica_dip"):
            st.session_state.costo_dip_da_applicare = costo_dip_standard
            st.rerun()

    with col_fb:
        altri_fb_standard = st.number_input(
            "🍔 Altri Costi F&B",
            min_value=0.0,
            step=50.0,
            format="%.2f",
            key="margine_altri_fb_input"
        )
        if st.button("📋 Applica a tutti", use_container_width=True, key="margine_applica_fb"):
            st.session_state.altri_fb_da_applicare = altri_fb_standard
            st.rerun()

    with col_spese:
        altre_spese_standard = st.number_input(
            "📄 Altre Spese Generali",
            min_value=0.0,
            step=50.0,
            format="%.2f",
            key="margine_altre_spese_input"
        )
        if st.button("📋 Applica a tutti", use_container_width=True, key="margine_applica_spese"):
            st.session_state.altre_spese_da_applicare = altre_spese_standard
            st.rerun()

    # ============================================
    # TABELLA UNICA TRASPOSTA - INPUT + RISULTATI
    # ============================================
    st.markdown("---")
    st.markdown("### 📊 Tabella Annuale ricavi-costi-margini")

    st.markdown("""
    <details style='background: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px; margin-bottom: 16px;'>
    <summary style='background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); border-radius: 8px;
        padding: 10px 14px; color: #1e40af; font-weight: 600; cursor: pointer; font-size: 0.95rem;'>
        📌 Apri per visualizzare la Legenda
    </summary>
    <div style='padding: 10px 18px; color: #1e3a5f; font-size: 0.875rem; line-height: 1.6;'>
    <ul style='margin: 4px 0; padding-left: 20px;'>
    <li>I <strong>Costi F&B</strong> e le <strong>Spese Generali</strong> contrassegnati <em>(Fatture)</em> sono calcolati automaticamente dalle fatture caricate</li>
    <li>Le righe con <strong>=</strong> sono calcolate automaticamente e si aggiornano in tempo reale</li>
    <li>Il <strong>Fatturato</strong> si riferisce all'incasso IVA inclusa: viene scorporata l'IVA per ottenere il <em>Fatturato Netto</em></li>
    <li>Se non inserisci fatturato, il <strong>MOL sarà negativo</strong> (somma dei soli costi)</li>
    <li>I dati sono salvati per <strong>ristorante</strong> e <strong>anno</strong> — ogni ristorante ha i propri margini</li>
    </ul>
    </div>
    </details>
    """, unsafe_allow_html=True)

    # Build transposed display from df_input
    df_display = build_transposed_df(df_input)

    # Column config for data_editor - 25 columns total
    column_config = {
        'Voce': st.column_config.TextColumn(
            '📋 Voce', disabled=True, width='medium'
        ),
    }

    # Add € (NumberColumn) and % (ProgressColumn with colored bar) for each month
    for mese in MESI_NOMI:
        column_config[f'{mese} €'] = st.column_config.NumberColumn(
            f'{mese} €', format="%.2f",
        )
        column_config[f'{mese} %'] = st.column_config.ProgressColumn(
            f'{mese} %', format="%.1f%%",
            min_value=0, max_value=100, width='small'
        )

    # Disabled columns: Voce + all % columns (text, readonly)
    disabled_cols = ['Voce']
    for mese in MESI_NOMI:
        disabled_cols.append(f'{mese} %')

    edited_display = st.data_editor(
        df_display,
        column_config=column_config,
        disabled=disabled_cols,
        hide_index=True,
        use_container_width=True,
        height=520,
        key="margine_data_editor"
    )

    # CSS per cambiare colore barre di progresso e numeri da rosso ad arancione
    st.markdown("""
    <style>
    /* Barre percentuale nella tabella - arancione - selettori multipli per coverage completo */
    [data-testid="stDataFrame"] [data-baseweb="progress-bar"] {
        --progress-bar-color: #f97316 !important;
    }
    [data-testid="stDataFrame"] [data-baseweb="progress-bar"] > div {
        background-color: #f97316 !important;
    }
    [data-testid="stDataFrame"] [data-baseweb="progress-bar"] > div > div {
        background-color: #f97316 !important;
    }
    [data-testid="stDataFrame"] [data-baseweb="progress-bar"] [class*="ProgressBar"] {
        background-color: #f97316 !important;
    }
    [data-testid="stDataFrame"] div[role="progressbar"] {
        background-color: #f97316 !important;
    }
    [data-testid="stDataFrame"] div[role="progressbar"] > div {
        background-color: #f97316 !important;
    }
    [data-testid="stDataFrame"] div[role="progressbar"] > div > div {
        background-color: #f97316 !important;
    }
    /* Testo percentuale - arancione */
    [data-testid="stDataFrame"] [data-baseweb="progress-bar"] span {
        color: #f97316 !important;
        font-weight: 600 !important;
    }
    /* Streamlit data_editor progress column specifico */
    [data-testid="column"] [data-baseweb="progress-bar"] > div {
        background-color: #f97316 !important;
    }
    /* Fallback generico per progress bar */
    .stDataFrame [data-baseweb="progress-bar"] > div,
    .stDataFrame [role="progressbar"] > div {
        background-color: #f97316 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ============================================
    # EXTRACT INPUT & DETECT CHANGES
    # ============================================
    df_input_new = extract_input_from_transposed(
        edited_display, costi_fb_mensili, costi_spese_mensili
    )

    rerun_flag_key = f"{work_key}_rerun_done"
    df_changed = False

    if work_key in st.session_state and not st.session_state.get(rerun_flag_key, False):
        editable_cols = ['Fatt_IVA10', 'Fatt_IVA22', 'Altri_Ricavi_NoIVA', 'Altri_FB', 'Altri_Spese', 'Costo_Dipendenti']
        for col in editable_cols:
            if not df_input[col].round(2).equals(df_input_new[col].round(2)):
                df_changed = True
                break
    elif work_key not in st.session_state:
        # Prima apertura: salva stato iniziale
        st.session_state[work_key] = df_input_new.copy()

    if df_changed:
        st.session_state[work_key] = df_input_new.copy()
        st.session_state[rerun_flag_key] = True
        st.rerun()

    # Reset flag
    if rerun_flag_key in st.session_state:
        del st.session_state[rerun_flag_key]

    # Usa i valori più aggiornati per i calcoli
    df_input_current = df_input_new

    # ============================================
    # CALCOLA RISULTATI PER KPI + EXPORT
    # ============================================
    df_risultati = calcola_risultati(df_input_current)

    # ============================================
    # BOTTONI SALVA + EXPORT
    # ============================================

    # CSS per bottoni personalizzati
    st.markdown("""
    <style>
    /* Bottone Salva Dati - azzurro, compatto (solo area principale, non sidebar) */
    .main .stButton button[kind="primary"] {
        background-color: #0ea5e9 !important;
        color: white !important;
        border: 2px solid #0284c7 !important;
        font-weight: 600 !important;
        max-width: 200px !important;
    }
    .main .stButton button[kind="primary"]:hover {
        background-color: #0284c7 !important;
    }
    /* Download Button - verde */
    [data-testid="stDownloadButton"] button {
        background-color: #28a745 !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        max-width: 250px !important;
    }
    [data-testid="stDownloadButton"] button:hover {
        background-color: #218838 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <p style="font-size: 0.78rem; color: #1e3a5f; margin-bottom: 6px;">
        💡 Dopo aver inserito i dati, salva per registrare le modifiche prima di cambiare pagina.
    </p>
    """, unsafe_allow_html=True)

    if st.button("💾 Salva Dati", type="primary", key="margine_salva"):
        with st.spinner("Salvataggio in corso..."):
            success = salva_margini_anno(
                user_id, current_ristorante, anno, df_input_current, df_risultati
            )
        if success:
            st.success("✅ Dati margini salvati correttamente!")
            if work_key in st.session_state:
                del st.session_state[work_key]
            if 'margine_data_editor' in st.session_state:
                del st.session_state['margine_data_editor']
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ Errore durante il salvataggio. Riprova.")

    # ============================================
    # KPI CARDS RIEPILOGO ANNO
    # ============================================
    st.markdown("---")
    st.markdown("### 📊 Riepilogo KPI - Media valori per periodo")

    # ============================================
    # FILTRO TEMPORALE KPI
    # ============================================
    periodi_kpi = {
        "Anno intero": list(range(1, 13)),
        "Q1 (Gen-Mar)": [1, 2, 3],
        "Q2 (Apr-Giu)": [4, 5, 6],
        "Q3 (Lug-Set)": [7, 8, 9],
        "Q4 (Ott-Dic)": [10, 11, 12],
        "H1 (Gen-Giu)": list(range(1, 7)),
        "H2 (Lug-Dic)": list(range(7, 13)),
    }

    periodo_sel = st.selectbox(
        "📅 Periodo di riferimento KPI",
        options=list(periodi_kpi.keys()),
        index=0,
        key="kpi_periodo_select"
    )
    mesi_filtro = periodi_kpi[periodo_sel]
    kpi = calcola_kpi_anno(df_risultati, mesi_filtro=mesi_filtro)
    num_mesi = kpi['num_mesi']

    if num_mesi > 0:
        mol_medio = kpi['mol_medio']
        fatt_medio = kpi['fatt_medio']
        fc_perc = kpi['fc_medio']
        mol_perc = kpi['mol_perc_medio']
        primo_marg = kpi['primo_margine_medio']
        primo_marg_perc = kpi['primo_margine_perc_media']
        costi_fb = kpi['costi_fb_medi']
        spese_gen = kpi['spese_gen_medie']
        spese_perc = kpi['spese_gen_perc_media']

        def _fmt_kpi(val):
            segno = "-" if val < 0 else ""
            return f"{segno}€{abs(val):,.0f}".replace(",", ".")
    
        # CSS per KPI con sfondo grigio argentato traslucido e bordo
        st.markdown("""
        <style>
        /* Altezza uniforme tra tutte le card KPI al variare dello zoom */
        [data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div[data-testid="column"] {
            display: flex !important;
            flex-direction: column !important;
            align-items: stretch !important;
        }
        [data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div[data-testid="column"] > div {
            flex: 1 !important;
            display: flex !important;
            flex-direction: column !important;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(248, 249, 250, 0.95), rgba(233, 236, 239, 0.95));
            padding: clamp(1rem, 2.5vw, 1.25rem);
            border-radius: 12px;
            border: 1px solid rgba(206, 212, 218, 0.5);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.05);
            backdrop-filter: blur(10px);
            height: 100%;
            min-height: 100px;
            box-sizing: border-box;
            justify-content: center;
        }
        div[data-testid="stMetric"] label {
            color: #2563eb !important;
            font-weight: 600 !important;
            font-size: clamp(0.75rem, 1.8vw, 0.875rem) !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #1e40af !important;
            font-size: clamp(1.25rem, 3.5vw, 1.75rem) !important;
            font-weight: 700 !important;
        }
        /* Delta incidenza in arancione */
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            color: #f97316 !important;
            font-weight: 600 !important;
        }
        </style>
        """, unsafe_allow_html=True)
    
        # KPI Cards
        col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
    
        with col_kpi1:
            st.metric("📈 Fatturato Medio Mensile", _fmt_kpi(fatt_medio), delta=" ", delta_color="off")
    
        with col_kpi2:
            st.metric("🍔 Food Cost", _fmt_kpi(costi_fb), delta=f"incidenza {fc_perc:.1f}%", delta_color="off")
    
        with col_kpi3:
            st.metric("💵 1° Margine", _fmt_kpi(primo_marg), delta=f"incidenza {primo_marg_perc:.1f}%", delta_color="off")
    
        with col_kpi4:
            st.metric("💼 Spese Generali", _fmt_kpi(spese_gen), delta=f"incidenza {spese_perc:.1f}%", delta_color="off")
    
        with col_kpi5:
            st.metric("💰 2° Margine (MOL)", _fmt_kpi(mol_medio), delta=f"incidenza {mol_perc:.1f}%", delta_color="off")
    
        # ============================================
        # COMMENTI AUTOMATICI KPI
        # ============================================
        commenti = genera_commenti_kpi(kpi, df_risultati, mesi_filtro=mesi_filtro)
    
        if commenti:
            st.markdown("#### 💬 Analisi KPI")
            for c in commenti:
                st.markdown(f"""
                <div style='display: flex; align-items: center; gap: 12px; padding: 10px 16px; margin: 5px 0;
                            border-left: 4px solid {c['colore']};
                            background: linear-gradient(135deg, rgba(248,249,250,0.95), rgba(240,242,245,0.95));
                            border-radius: 6px;'>
                    <span style='font-size: clamp(1.1rem, 3vw, 1.4rem); font-weight: 800; color: {c['colore']}; min-width: 70px;'>
                        {c['emoji']} {c['percentuale']}
                    </span>
                    <span style='font-size: clamp(0.8rem, 1.8vw, 0.9rem); color: #374151;'>
                        <strong>{c['kpi_nome']}</strong>: {c['commento']}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
    
        # Download Excel sotto i KPI
        nome_rist = st.session_state.get("nome_ristorante", "Ristorante")
        kpi_data = {
            'periodo': periodo_sel,
            'num_mesi': num_mesi,
            'fatt_medio': fatt_medio,
            'costi_fb': costi_fb,
            'fc_perc': fc_perc,
            'primo_marg': primo_marg,
            'primo_marg_perc': primo_marg_perc,
            'spese_gen': spese_gen,
            'spese_perc': spese_perc,
            'mol_medio': mol_medio,
            'mol_perc': mol_perc
        }
        excel_data = export_excel_margini(df_risultati, anno, nome_rist, kpi_data)
        st.download_button(
            "Scarica Excel",
            data=excel_data,
            file_name=f"Margini_{anno}_{nome_rist.replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="margine_download"
        )


