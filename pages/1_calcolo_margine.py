"""
Calcolo Margine - Calcolo MOL (Margine Operativo Lordo)
Pagina dedicata al calcolo del margine operativo mensile del ristorante.
Tabella unica trasposta: voci come righe, mesi come colonne.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
import io
import html as _html

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

from config.logger_setup import get_logger
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ristorante_helper import get_current_ristorante_id
from services import get_supabase_client
from services.margine_service import (
    calcola_costi_automatici_per_anno,
    carica_margini_anno,
    salva_margini_anno,
    calcola_risultati,
    calcola_kpi_anno,
    genera_commenti_kpi,
    export_excel_margini,
    build_transposed_df,
    carica_costi_per_categoria,
    salva_fatturato_centri,
    carica_fatturato_centri_periodo,
    carica_fatturato_centri_mese,
    MESI_NOMI,
)

# Logger
logger = get_logger('calcolo_margine')

# ============================================
# CONFIGURAZIONE PAGINA
# ============================================
st.set_page_config(
    page_title="Calcolo Marginalità - OH YEAH! Hub",
    page_icon="💰",
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
check_page_enabled('calcolo_margine', user_id)

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
    💰 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Calcolo Marginalità</span>
</h2>
""", unsafe_allow_html=True)

st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)

# CSS globale per bottoni Excel verdi
st.markdown("""
<style>
div.st-key-aa_download_centri .stDownloadButton button,
div.st-key-cm_download_excel_centri .stDownloadButton button,
div.st-key-margine_download .stDownloadButton button {
    background-color: #22c55e !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
div.st-key-aa_download_centri .stDownloadButton button:hover,
div.st-key-cm_download_excel_centri .stDownloadButton button:hover,
div.st-key-margine_download .stDownloadButton button:hover {
    background-color: #16a34a !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================
# TABS: Calcolo Marginalità + Analisi Avanzate
# ============================================
if 'margine_tab' not in st.session_state:
    st.session_state.margine_tab = "calcolo"

col_tab1, col_tab2, col_tab3 = st.columns(3)
with col_tab1:
    if st.button("📊 CALCOLO\nRICAVI-COSTI-MARGINI", key="btn_tab_calcolo", use_container_width=True,
                 type="primary" if st.session_state.margine_tab == "calcolo" else "secondary"):
        if st.session_state.margine_tab != "calcolo":
            st.session_state.margine_tab = "calcolo"
            st.rerun()
with col_tab2:
    if st.button("🏭 CENTRI DI\nCOSTO", key="btn_tab_centri", use_container_width=True,
                 type="primary" if st.session_state.margine_tab == "centri" else "secondary"):
        if st.session_state.margine_tab != "centri":
            st.session_state.margine_tab = "centri"
            st.rerun()
with col_tab3:
    if st.button("🔬 ANALISI\nAVANZATE", key="btn_tab_analisi", use_container_width=True,
                 type="primary" if st.session_state.margine_tab == "analisi" else "secondary"):
        if st.session_state.margine_tab != "analisi":
            st.session_state.margine_tab = "analisi"
            st.rerun()

# CSS per bottoni tab - caricato da file statico condiviso
from utils.ui_helpers import load_css
load_css('common.css')
st.markdown("""
    <style>
    /* Override specifico: altezza bottoni più compatta per questa pagina */
    div[data-testid="column"] button {
        padding: 0.5rem 0.25rem !important;
        min-height: 3rem !important;
        height: auto !important;
    }
    </style>
""", unsafe_allow_html=True)

if st.session_state.margine_tab == "analisi":

    from config.constants import CENTRI_DI_PRODUZIONE, CATEGORIE_FOOD

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # ============================================
    # FILTRO TEMPORALE (stile identico ad Analisi Fatture)
    # ============================================
    from utils.period_helper import PERIODO_OPTIONS, calcola_date_periodo, risolvi_periodo
    
    date_periodo = calcola_date_periodo()
    oggi_date_aa = date_periodo['oggi']
    inizio_anno_aa = date_periodo['inizio_anno']

    if 'aa_periodo_dropdown' not in st.session_state:
        st.session_state.aa_periodo_dropdown = "🗓️ Anno in Corso"

    col_periodo_aa, col_info_aa = st.columns([1.5, 4.5])

    with col_periodo_aa:
        st.markdown('<p style="color:#1e40af;font-weight:600;font-size:0.9rem;margin:0 0 4px 0;">📅 Filtra per Periodo</p>', unsafe_allow_html=True)
        periodo_sel_aa = st.selectbox(
            "📅 Filtra per Periodo",
            options=PERIODO_OPTIONS,
            label_visibility="collapsed",
            index=PERIODO_OPTIONS.index(st.session_state.aa_periodo_dropdown) if st.session_state.aa_periodo_dropdown in PERIODO_OPTIONS else 3,
            key="aa_filtro_periodo"
        )

    st.session_state.aa_periodo_dropdown = periodo_sel_aa

    # Logica date
    data_inizio_aa, data_fine_aa, label_periodo = risolvi_periodo(periodo_sel_aa, date_periodo)
    anno_aa = oggi_date_aa.year  # default

    if data_inizio_aa is None:
        # Periodo Personalizzato
        st.markdown("##### Seleziona Range Date")
        col_da_aa, col_a_aa = st.columns(2)

        if 'aa_data_inizio' not in st.session_state:
            st.session_state.aa_data_inizio = inizio_anno_aa
        if 'aa_data_fine' not in st.session_state:
            st.session_state.aa_data_fine = oggi_date_aa

        with col_da_aa:
            data_inizio_custom_aa = st.date_input(
                "📅 Da",
                value=st.session_state.aa_data_inizio,
                min_value=inizio_anno_aa,
                key="aa_data_da_custom"
            )
        with col_a_aa:
            data_fine_custom_aa = st.date_input(
                "📅 A",
                value=st.session_state.aa_data_fine,
                min_value=inizio_anno_aa,
                key="aa_data_a_custom"
            )

        if data_inizio_custom_aa > data_fine_custom_aa:
            st.error("⚠️ La data iniziale deve essere precedente alla data finale!")
            data_inizio_aa = st.session_state.aa_data_inizio
            data_fine_aa = st.session_state.aa_data_fine
        else:
            st.session_state.aa_data_inizio = data_inizio_custom_aa
            st.session_state.aa_data_fine = data_fine_custom_aa
            data_inizio_aa = data_inizio_custom_aa
            data_fine_aa = data_fine_custom_aa

        anno_aa = data_inizio_aa.year
        label_periodo = f"{data_inizio_aa.strftime('%d/%m/%Y')} → {data_fine_aa.strftime('%d/%m/%Y')}"

    # Info periodo
    giorni_aa = (data_fine_aa - data_inizio_aa).days + 1
    with col_info_aa:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display: inline-block; width: fit-content; background: linear-gradient(135deg, #fef9c3 0%, #fefce8 100%);
                    padding: 10px 16px;
                    border-radius: 8px;
                    border: 1px solid #fde047;
                    font-size: clamp(0.78rem, 1.8vw, 0.88rem);
                    font-weight: 500;
                    line-height: 1.5;">
            🗓️ {label_periodo} ({giorni_aa} giorni)
        </div>
        """, unsafe_allow_html=True)

    # Converti date in stringhe per le query
    date_from_str = data_inizio_aa.strftime('%Y-%m-%d')
    date_to_str = data_fine_aa.strftime('%Y-%m-%d')

    # ============================================
    # CARICA DATI
    # ============================================
    # 1) Fatturato netto dai margini salvati — somma tutti gli anni/mesi nel range
    #    Per semplicità: iteriamo anno per anno
    if data_inizio_aa is None:
        st.warning("Seleziona un periodo valido.")
        st.stop()
    fatturato_netto_periodo = 0.0
    _mesi_con_fatt_aa = 0  # mesi con fatturato > 0 (usato per medie accurate)
    anno_start = data_inizio_aa.year
    anno_end = data_fine_aa.year
    for a in range(anno_start, anno_end + 1):
        dati_margini_a = carica_margini_anno(user_id, current_ristorante, a)
        m_from = data_inizio_aa.month if a == anno_start else 1
        m_to = data_fine_aa.month if a == anno_end else 12
        for m_num in range(m_from, m_to + 1):
            dati_m = dati_margini_a.get(m_num, {})
            fatt10 = float(dati_m.get('fatturato_iva10', 0.0) or 0.0)
            fatt22 = float(dati_m.get('fatturato_iva22', 0.0) or 0.0)
            altri_r = float(dati_m.get('altri_ricavi_noiva', 0.0) or 0.0)
            fatt_m = (fatt10 / 1.10) + (fatt22 / 1.22) + altri_r
            fatturato_netto_periodo += fatt_m
            if fatt_m > 0:
                _mesi_con_fatt_aa += 1

    # 2) Costi per categoria dalle fatture
    df_costi_cat = carica_costi_per_categoria(
        user_id, current_ristorante, date_from_str, date_to_str
    )

    # ============================================
    # MAPPATURA CATEGORIE → CENTRI
    # ============================================
    cat_to_centro = {}
    for centro_nome, cats in CENTRI_DI_PRODUZIONE.items():
        for cat in cats:
            cat_to_centro[cat] = centro_nome

    if df_costi_cat.empty:
        st.info("📊 Nessun dato fatture F&B disponibile per il periodo selezionato. Carica le fatture nella pagina Analisi Fatture.")
        st.stop()
    else:
        df_costi_cat['centro'] = df_costi_cat['categoria'].map(cat_to_centro).fillna('Altro')
        _non_mappate_aa = df_costi_cat[df_costi_cat['centro'] == 'Altro']['categoria'].unique().tolist()
        if _non_mappate_aa:
            logger.warning(f"⚠️ Categorie F&B non mappate a nessun centro (escluse dall'analisi avanzate): {_non_mappate_aa}")
        df_costi_cat = df_costi_cat[df_costi_cat['centro'] != 'Altro']

        totale_costi_fb = df_costi_cat['totale'].sum()

        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        st.markdown('<h3 style="color:#1e40af;font-weight:700;">🏭 Incidenza Centri di Costo sul Fatturato</h3>', unsafe_allow_html=True)
        st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)

        # ============================================
        # SUDDIVISIONE FATTURATO PER CENTRO
        # ============================================
        _centri_con_fatturato = ["FOOD", "BAR", "ALCOLICI", "DOLCI"]
        _MESI_COMPLETI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                          "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]

        # Icone centri (unica mappa, usata anche nell'expander split)
        icone_centri = {
            "FOOD": "🍖", "BAR": "☕", "ALCOLICI": "🍷",
            "DOLCI": "🍰", "MATERIALE DI CONSUMO": "📦", "SHOP": "🛒"
        }
        _icone = icone_centri  # alias per retrocompatibilità

        # Carica dati dal DB aggregati per il periodo selezionato
        fatturato_per_centro_db = carica_fatturato_centri_periodo(
            user_id, current_ristorante, data_inizio_aa, data_fine_aa
        )
        fatturato_split_attivo = len(fatturato_per_centro_db) > 0
        fatturato_per_centro = fatturato_per_centro_db if fatturato_split_attivo else {}
        fatturato_totale_split = sum(fatturato_per_centro.values()) if fatturato_per_centro else 0.0

        # Expander per inserimento/modifica — sfondo azzurro
        st.markdown("""
        <style>
        div.st-key-expander_fatturato_centri div[data-testid="stExpander"] > details > summary {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%) !important;
            border-radius: 8px !important;
            padding: clamp(0.625rem, 1.5vw, 1rem) clamp(0.75rem, 2vw, 1rem) !important;
            color: #1e40af !important;
            font-weight: 600 !important;
        }
        div.st-key-expander_fatturato_centri div[data-testid="stExpander"] > details[open] > div {
            background: #ffffff !important;
            border-radius: 0 0 8px 8px !important;
            padding: 12px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        with st.container(key="expander_fatturato_centri"):
          with st.expander("📌 Fatturato per Centro di Produzione", expanded=True):
            st.markdown("""
            <div style='color: #1e3a5f; font-size: 0.875rem; line-height: 1.6; margin-bottom: 12px;'>
            Ripartisci il Fatturato Netto tra i centri di produzione <strong>mese per mese</strong>.
            I dati vengono salvati e recuperati automaticamente in base al periodo selezionato nel filtro in alto.
            Questa analisi mostra i centri F&amp;B; le <strong>Spese Generali</strong>, incluso <strong>Materiale di Consumo</strong>, restano fuori da questa ripartizione.
            </div>
            """, unsafe_allow_html=True)

            # --- Selettore mese ---
            # Mesi disponibili nel range data_inizio_aa → data_fine_aa
            _mesi_options = []
            for a in range(data_inizio_aa.year, data_fine_aa.year + 1):
                m_from = data_inizio_aa.month if a == data_inizio_aa.year else 1
                m_to = data_fine_aa.month if a == data_fine_aa.year else 12
                for m in range(m_from, m_to + 1):
                    _mesi_options.append((a, m, f"{_MESI_COMPLETI[m-1]} {a}"))

            col_mese_sel, col_fatt_netto = st.columns([1.5, 4.5])
            with col_mese_sel:
                idx_default = 0
                mese_label_sel = st.selectbox(
                    "📅 Mese",
                    options=[x[2] for x in _mesi_options],
                    index=idx_default,
                    key="aa_split_mese_sel"
                )
            # Trova anno/mese selezionato
            _sel_idx = [x[2] for x in _mesi_options].index(mese_label_sel)
            _anno_sel_split = _mesi_options[_sel_idx][0]
            _mese_sel_split = _mesi_options[_sel_idx][1]

            # Carica dal DB il mese specifico
            _dati_mese_db = carica_fatturato_centri_mese(
                user_id, current_ristorante, _anno_sel_split, _mese_sel_split
            )

            # Fatturato netto del mese selezionato (dal tab calcolo)
            _dati_margini_mese = carica_margini_anno(user_id, current_ristorante, _anno_sel_split)
            _dati_m = _dati_margini_mese.get(_mese_sel_split, {})
            _fatt10 = float(_dati_m.get('fatturato_iva10', 0) or 0)
            _fatt22 = float(_dati_m.get('fatturato_iva22', 0) or 0)
            _altri_r = float(_dati_m.get('altri_ricavi_noiva', 0) or 0)
            _fatt_netto_mese = (_fatt10 / 1.10) + (_fatt22 / 1.22) + _altri_r

            with col_fatt_netto:
                if _fatt_netto_mese > 0:
                    st.markdown(f"""
                    <div style="display:inline-block; background:#fef9c3; padding:6px 14px; border-radius:6px; border:1px solid #fde047; font-size:0.88rem; font-weight:500; margin-top:28px;">
                        💰 Fatturato Netto di {mese_label_sel}: <strong>€ {_fatt_netto_mese:,.0f}</strong>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                    st.warning(f"⚠️ Nessun fatturato inserito per {mese_label_sel} nel tab Calcolo Ricavi-Costi-Margini.")

            # --- Modalità inserimento ---
            if "aa_split_mode_radio" not in st.session_state:
                st.session_state["aa_split_mode_radio"] = "€ Valore Assoluto"

            modo_split = st.radio(
                "Modalità di inserimento",
                ["% Percentuale", "€ Valore Assoluto"],
                horizontal=True,
                key="aa_split_mode_radio"
            )

            # Se ci sono dati DB, calcola i valori display
            _defaults_euro = {c: _dati_mese_db.get(c, 0.0) for c in _centri_con_fatturato}
            _defaults_pct = {}
            if _fatt_netto_mese > 0:
                _defaults_pct = {c: v / _fatt_netto_mese * 100.0 for c, v in _defaults_euro.items()}
            else:
                _defaults_pct = {c: 0.0 for c in _centri_con_fatturato}

            # --- Input per centro ---
            cols_split = st.columns(len(_centri_con_fatturato))
            _valori_inseriti = {}

            for i, centro in enumerate(_centri_con_fatturato):
                with cols_split[i]:
                    if modo_split == "€ Valore Assoluto":
                        _valori_inseriti[centro] = st.number_input(
                            f"{_icone.get(centro, '')} {centro}",
                            min_value=0.0,
                            step=1000.0,
                            format="%.2f",
                            key=f"aa_split_{centro}",
                            value=_defaults_euro.get(centro, 0.0)
                        )
                    else:
                        _valori_inseriti[centro] = st.number_input(
                            f"{_icone.get(centro, '')} {centro} (%)",
                            min_value=0.0,
                            max_value=100.0,
                            step=1.0,
                            format="%.1f",
                            key=f"aa_split_{centro}",
                            value=min(_defaults_pct.get(centro, 0.0), 100.0)
                        )

            # --- Validazione ---
            totale_inserito = sum(_valori_inseriti.values())
            if modo_split == "€ Valore Assoluto":
                obiettivo = _fatt_netto_mese
                label_tot = f"€ {totale_inserito:,.0f} / € {obiettivo:,.0f}"
                is_valid = abs(totale_inserito - obiettivo) < 1.0
            else:
                obiettivo = 100.0
                label_tot = f"{totale_inserito:.1f}% / 100.0%"
                is_valid = abs(totale_inserito - 100.0) < 0.1

            if totale_inserito > 0:
                color_tot = "#16a34a" if is_valid else "#dc2626"
                st.markdown(f'<p style="font-weight:600;color:{color_tot};font-size:0.95rem;">Totale: {label_tot} {"✅" if is_valid else "❌ Il totale non corrisponde"}</p>', unsafe_allow_html=True)

            # --- Bottoni ---
            col_btn_split, col_btn_reset, _col_split_empty = st.columns([1, 1, 4])
            with col_btn_split:
                if st.button("💾 Salva mese", use_container_width=True, key="aa_applica_split",
                             disabled=not (is_valid and totale_inserito > 0)):
                    if modo_split == "% Percentuale":
                        _euro_da_salvare = {c: _fatt_netto_mese * v / 100.0 for c, v in _valori_inseriti.items()}
                    else:
                        _euro_da_salvare = _valori_inseriti.copy()
                    ok = salva_fatturato_centri(user_id, current_ristorante, _anno_sel_split, _mese_sel_split, _euro_da_salvare)
                    if ok:
                        st.success(f"✅ Fatturato centri salvato per {mese_label_sel}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ Errore nel salvataggio")
            with col_btn_reset:
                if st.button("🗑️ Azzera mese", use_container_width=True, key="aa_reset_split"):
                    salva_fatturato_centri(user_id, current_ristorante, _anno_sel_split, _mese_sel_split,
                                           {c: 0.0 for c in _centri_con_fatturato})
                    st.rerun()

            # Mostra riepilogo mesi già compilati nel periodo
            if fatturato_split_attivo:
                st.markdown("---")
                st.markdown("**📋 Riepilogo mesi compilati nel periodo:**")
                _recap_rows = []
                for a in range(data_inizio_aa.year, data_fine_aa.year + 1):
                    m_from = data_inizio_aa.month if a == data_inizio_aa.year else 1
                    m_to = data_fine_aa.month if a == data_fine_aa.year else 12
                    for m in range(m_from, m_to + 1):
                        _d = carica_fatturato_centri_mese(user_id, current_ristorante, a, m)
                        if _d:
                            tot_m = sum(_d.values())
                            if tot_m > 0:
                                _recap_rows.append({
                                    "Mese": f"{_MESI_COMPLETI[m-1]} {a}",
                                    **{f"{_icone.get(c,'')} {c}": f"€ {_d.get(c,0):,.0f}" for c in _centri_con_fatturato},
                                    "Totale": f"€ {tot_m:,.0f}"
                                })
                if _recap_rows:
                    st.dataframe(pd.DataFrame(_recap_rows), hide_index=True, use_container_width=True)

        # Aggregazione per centro
        df_centri_agg = df_costi_cat.groupby('centro')['totale'].sum().reset_index()
        df_centri_agg.columns = ['Centro', 'Spesa']

        # Calcola percentuali
        # Se split attivo: % su fatturato specifico del centro
        # Eventuali centri senza fatturato diretto (es. SHOP): costo distribuito proporzionalmente
        _no_fatturato = {"SHOP"}
        if fatturato_split_attivo and fatturato_totale_split > 0:
            def _calc_pct_fatt(row):
                centro = row['Centro']
                spesa = row['Spesa']
                if centro in _no_fatturato:
                    # Costo senza fatturato proprio → % su fatturato totale
                    return (spesa / fatturato_totale_split * 100) if fatturato_totale_split > 0 else 0.0
                fatt_centro = fatturato_per_centro.get(centro, 0.0)
                return (spesa / fatt_centro * 100) if fatt_centro > 0 else 0.0
            df_centri_agg['pct_fatt'] = df_centri_agg.apply(_calc_pct_fatt, axis=1)
        else:
            df_centri_agg['pct_fatt'] = (
                (df_centri_agg['Spesa'] / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0
            )
        df_centri_agg['pct_fb'] = (
            (df_centri_agg['Spesa'] / totale_costi_fb * 100) if totale_costi_fb > 0 else 0.0
        )

        # Ordine centri fisso
        ordine_centri_fisso = list(CENTRI_DI_PRODUZIONE.keys())
        df_centri_agg['_sort'] = df_centri_agg['Centro'].apply(
            lambda x: ordine_centri_fisso.index(x) if x in ordine_centri_fisso else 99
        )
        df_centri_agg = df_centri_agg.sort_values('_sort').drop(columns=['_sort'])

        # ========================================================
        # TABELLA ESPANDIBILE: CENTRI + CATEGORIE INTEGRATE
        # ========================================================

        def _bar_html(pct, color="#f97316", width_factor=1.2):
            """Genera barra percentuale inline HTML."""
            w = min(pct, 100) * width_factor
            return f'<span style="display:inline-block;width:{w:.0f}px;height:10px;background:{color};border-radius:4px;margin-right:6px;vertical-align:middle;"></span>{pct:.1f}%'

        # 1° Margine (Fatturato Netto - Costi F&B) per la colonna Margine %
        primo_margine = fatturato_netto_periodo - totale_costi_fb

        # Separa eventuali centri senza fatturato diretto dalla tabella principale
        _centri_no_fatt = {"SHOP"}
        df_centri_main = df_centri_agg[~df_centri_agg['Centro'].isin(_centri_no_fatt)]
        df_centri_extra = df_centri_agg[df_centri_agg['Centro'].isin(_centri_no_fatt)]
        spesa_extra_tot = df_centri_extra['Spesa'].sum() if not df_centri_extra.empty else 0.0

        # Colonne: Centro | Fatturato | Costi | % Costi su Fatt. | Margine | Margine % | % su Costi F&B Tot
        _grid_cols = "20% 13% 12% 13% 13% 11% 18%"

        st.markdown(f"""
        <style>
        .aa-grid {{ width:100%; font-family:'Source Sans Pro',sans-serif; font-size:0.88rem; }}
        .aa-row {{ display:grid; grid-template-columns:{_grid_cols}; border-bottom:1px solid #e2e8f0; }}
        .aa-row > div {{ padding:10px 14px; }}
        .aa-row > div:not(:first-child) {{ text-align:right; font-variant-numeric:tabular-nums; }}
        .aa-header {{ background:#f0f2f6; font-weight:700; color:#1e3a5f; font-size:0.85rem; border-bottom:2px solid #cbd5e1; }}
        .aa-details {{ border:none; margin:0; padding:0; }}
        .aa-details summary {{ list-style:none; cursor:pointer; }}
        .aa-details summary::-webkit-details-marker {{ display:none; }}
        .aa-details summary::marker {{ display:none; content:""; }}
        .aa-details summary .aa-row {{ background:#fff; transition:background .15s; }}
        .aa-details summary .aa-row:hover {{ background:#eff6ff; }}
        .aa-details summary .aa-row > div:first-child {{ font-weight:700; color:#1e40af; font-size:0.9rem; }}
        .aa-details summary .aa-row > div {{ font-weight:600; }}
        .aa-details[open] summary .aa-row {{ background:#eff6ff; border-left:3px solid #0ea5e9; }}
        .aa-cat .aa-row {{ background:#f8fafc; }}
        .aa-cat .aa-row > div {{ font-size:0.83rem; color:#475569; padding:7px 14px; }}
        .aa-cat .aa-row > div:first-child {{ padding-left:40px; }}
        .aa-totale {{ background:#e0f2fe; border-top:2px solid #0ea5e9; }}
        .aa-totale > div {{ font-weight:700; color:#0c4a6e; }}
        .aa-arrow {{ display:inline-block; transition:transform .2s; margin-right:6px; font-size:0.7rem; }}
        .aa-details[open] .aa-arrow {{ transform:rotate(90deg); }}
        .aa-margine-pos {{ color:#16a34a; font-weight:700; }}
        .aa-margine-neg {{ color:#dc2626; font-weight:700; }}
        </style>
        """, unsafe_allow_html=True)

        def _margine_html(margine):
            cls = "aa-margine-pos" if margine >= 0 else "aa-margine-neg"
            segno = "+" if margine >= 0 else ""
            return f'<span class="{cls}">{segno}€ {margine:,.0f}</span>'

        def _margine_pct_html(pct):
            if pct >= 0:
                return f'<span style="color:#16a34a;font-weight:600;">{pct:.1f}%</span>'
            return f'<span style="color:#dc2626;font-weight:600;">{pct:.1f}%</span>'

        # HTML con CSS Grid
        h = []
        h.append('<div class="aa-grid">')
        # Header — ordine: Centro | Fatturato | Costi | % Costi su Fatt. | Margine | Margine % | % su Costi F&B Tot
        h.append('<div class="aa-row aa-header"><div>Centro / Categoria</div><div>Fatturato (€)</div><div>Costi (€)</div><div>% Costi su Fatt.</div><div>Margine (€)</div><div>Margine (%)</div><div>% su Costi F&amp;B Tot</div></div>')

        # Solo centri con fatturato (FOOD, BAR, ALCOLICI, DOLCI)
        for _, row_c in df_centri_main.iterrows():
            centro_nome = row_c['Centro']
            spesa_c = row_c['Spesa']
            pct_fatt_c = row_c['pct_fatt']
            pct_fb_c = row_c['pct_fb']
            icona = icone_centri.get(centro_nome, "📁")

            # Categorie di questo centro
            df_centro_cats = df_costi_cat[df_costi_cat['centro'] == centro_nome]
            df_cat_agg = df_centro_cats.groupby('categoria')['totale'].sum().reset_index()
            df_cat_agg.columns = ['Categoria', 'Spesa']
            df_cat_agg = df_cat_agg.sort_values('Spesa', ascending=False)

            # Fatturato e Margine centro
            _fatt_c = fatturato_per_centro.get(centro_nome, 0.0)
            _margine_c = _fatt_c - spesa_c
            _margine_pct_c = (_margine_c / _fatt_c * 100) if _fatt_c > 0 else 0.0

            h.append('<details class="aa-details">')
            h.append('<summary>')
            # Centro | Fatturato | Costi | % Costi su Fatt. | Margine | Margine % | % su Costi F&B Tot
            h.append(f'<div class="aa-row"><div><span class="aa-arrow">▶</span>{icona}  {centro_nome}</div>')
            if fatturato_split_attivo and _fatt_c > 0:
                h.append(f'<div>€ {_fatt_c:,.0f}</div>')
            else:
                h.append(f'<div style="color:#94a3b8;">—</div>')
            h.append(f'<div>€ {spesa_c:,.0f}</div>')
            h.append(f'<div>{_bar_html(pct_fatt_c, "#0ea5e9")}</div>')
            if fatturato_split_attivo and _fatt_c > 0:
                h.append(f'<div>{_margine_html(_margine_c)}</div>')
                h.append(f'<div>{_margine_pct_html(_margine_pct_c)}</div>')
            else:
                h.append(f'<div style="color:#94a3b8;">—</div>')
                h.append(f'<div style="color:#94a3b8;">—</div>')
            h.append(f'<div>{_bar_html(pct_fb_c, "#f97316")}</div></div>')
            h.append('</summary>')

            # Righe categorie
            _fatt_denom_centro = fatturato_per_centro.get(centro_nome, 0.0) if fatturato_split_attivo else fatturato_netto_periodo
            for _, row_cat in df_cat_agg.iterrows():
                cat_nome = row_cat['Categoria']
                cat_nome_safe = _html.escape(str(cat_nome))
                spesa_cat = row_cat['Spesa']
                pct_cat_fatt = (spesa_cat / _fatt_denom_centro * 100) if _fatt_denom_centro > 0 else 0.0
                pct_cat_centro = (spesa_cat / spesa_c * 100) if spesa_c > 0 else 0.0
                h.append(f'<div class="aa-cat"><div class="aa-row"><div>↳ {cat_nome_safe}</div>')
                h.append(f'<div style="color:#94a3b8;">—</div>')
                h.append(f'<div>€ {spesa_cat:,.0f}</div>')
                h.append(f'<div>{_bar_html(pct_cat_fatt, "#94a3b8")}</div>')
                h.append(f'<div style="color:#94a3b8;">—</div>')
                h.append(f'<div style="color:#94a3b8;">—</div>')
                h.append(f'<div>{_bar_html(pct_cat_centro, "#94a3b8")}</div></div></div>')

            h.append('</details>')

        # Riga TOTALE
        tot_pct_fatt = (totale_costi_fb / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0
        h.append(f'<div class="aa-row aa-totale"><div>TOTALE (1° Margine)</div>')
        h.append(f'<div>€ {fatturato_netto_periodo:,.0f}</div>')
        h.append(f'<div>€ {totale_costi_fb:,.0f}</div>')
        h.append(f'<div>{_bar_html(tot_pct_fatt, "#0ea5e9")}</div>')
        h.append(f'<div>{_margine_html(primo_margine)}</div>')
        _tot_margine_perc = (primo_margine / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0
        h.append(f'<div style="font-weight:700;">{_tot_margine_perc:.1f}%</div>')
        h.append(f'<div>100.0%</div></div>')

        h.append('</div>')

        st.markdown(''.join(h), unsafe_allow_html=True)

        # ========================================================
        # SEZIONE COSTI SENZA FATTURATO DIRETTO — expander con totale e suddivisione
        # ========================================================
        if spesa_extra_tot > 0:
            st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)
            with st.expander(f"🛍️ Costi senza fatturato diretto — Totale: € {spesa_extra_tot:,.0f}", expanded=False):
                st.markdown(f"""
                <p style="font-size:0.85rem;color:#475569;margin-bottom:10px;">
                    Costo distribuito proporzionalmente {'al fatturato' if fatturato_split_attivo and fatturato_totale_split > 0 else 'ai costi'} dei centri F&amp;B.
                </p>
                """, unsafe_allow_html=True)

                # Calcola distribuzione proporzionale
                _mc_rows = []
                _centri_fatt_list = ["FOOD", "BAR", "ALCOLICI", "DOLCI"]
                if fatturato_split_attivo and fatturato_totale_split > 0:
                    for c in _centri_fatt_list:
                        f_c = fatturato_per_centro.get(c, 0.0)
                        if f_c > 0:
                            quota = spesa_extra_tot * f_c / fatturato_totale_split
                            pct = f_c / fatturato_totale_split * 100
                            _mc_rows.append({"Centro": f"{icone_centri.get(c, '')} {c}", "Quota Fatturato": f"{pct:.1f}%", "Costo Attribuito": f"€ {quota:,.0f}"})
                else:
                    _centri_presenti = [c for c in _centri_fatt_list if c in df_centri_main['Centro'].values]
                    _spese_centri = {row['Centro']: row['Spesa'] for _, row in df_centri_main.iterrows()}
                    _tot_spese_centri = sum(_spese_centri.values())
                    for c in _centri_presenti:
                        sp_c = _spese_centri.get(c, 0.0)
                        pct = (sp_c / _tot_spese_centri * 100) if _tot_spese_centri > 0 else 0.0
                        quota = spesa_extra_tot * sp_c / _tot_spese_centri if _tot_spese_centri > 0 else 0.0
                        _mc_rows.append({"Centro": f"{icone_centri.get(c, '')} {c}", "Quota (prop. costi)": f"{pct:.1f}%", "Costo Attribuito": f"€ {quota:,.0f}"})

                if _mc_rows:
                    st.dataframe(pd.DataFrame(_mc_rows), hide_index=True, use_container_width=False)

        # Excel export - a destra, sotto le tabelle, prima dei KPI
        _col_excel_spacer, _col_excel_btn = st.columns([5, 1])
        with _col_excel_btn:
            excel_buf_c = io.BytesIO()
            with pd.ExcelWriter(excel_buf_c, engine='openpyxl') as writer:
                df_export_centri = df_centri_agg.copy()
                df_export_centri.loc[len(df_export_centri)] = {
                    'Centro': 'TOTALE F&B', 'Spesa': totale_costi_fb,
                    'pct_fatt': tot_pct_fatt, 'pct_fb': 100.0
                }
                df_export_centri.columns = ['Centro', 'Spesa (€)', '% su Fatturato', '% su Costi F&B']
                df_export_centri.to_excel(writer, index=False, sheet_name='Centri Riepilogo')
                for centro_n in ordine_centri_fisso:
                    df_c = df_costi_cat[df_costi_cat['centro'] == centro_n]
                    if df_c.empty:
                        continue
                    df_c_agg_exp = df_c.groupby('categoria')['totale'].sum().reset_index()
                    df_c_agg_exp.columns = ['Categoria', 'Spesa (€)']
                    df_c_agg_exp = df_c_agg_exp.sort_values('Spesa (€)', ascending=False)
                    sheet_name = centro_n[:31]
                    df_c_agg_exp.to_excel(writer, index=False, sheet_name=sheet_name)
            excel_buf_c.seek(0)
            st.download_button(
                label="Excel",
                data=excel_buf_c.getvalue(),
                file_name=f"analisi_centri_categorie_{anno_aa}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="aa_download_centri",
                type="primary",
                use_container_width=False,
            )

        # ============================================
        # KPI PERIODO - ANALISI CENTRI
        # ============================================
        st.markdown('<h3 style="color:#1e40af;font-weight:700;">📊 Riepilogo KPI - Media valori per periodo</h3>', unsafe_allow_html=True)

        # Numero mesi con fatturato > 0 (esclude mesi futuri o senza dati inseriti)
        _num_mesi_attivi_aa = _mesi_con_fatt_aa if _mesi_con_fatt_aa > 0 else 1

        # Medie mensili calcolate solo sui mesi con dati effettivi
        _fatt_medio_aa = fatturato_netto_periodo / _num_mesi_attivi_aa
        _costi_fb_medi_aa = totale_costi_fb / _num_mesi_attivi_aa
        _fc_perc_aa = (totale_costi_fb / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0
        _margine_medio_aa = primo_margine / _num_mesi_attivi_aa
        _margine_perc_aa = (primo_margine / fatturato_netto_periodo * 100) if fatturato_netto_periodo > 0 else 0.0

        if fatturato_netto_periodo > 0 or totale_costi_fb > 0:

            def _fmt_kpi_aa(val):
                segno = "-" if val < 0 else ""
                return f"{segno}€{abs(val):,.0f}".replace(",", ".")

            # CSS per KPI con sfondo grigio argentato traslucido e bordo (stile tab 1)
            st.markdown("""
            <style>
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
            div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
                color: #f97316 !important;
                font-weight: 600 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            # KPI Cards — 5 colonne, stile identico al tab 1
            col_kpi_aa1, col_kpi_aa2, col_kpi_aa3, col_kpi_aa4, col_kpi_aa5 = st.columns(5)

            with col_kpi_aa1:
                st.metric("📈 Fatturato Medio Mensile", _fmt_kpi_aa(_fatt_medio_aa), delta=" ", delta_color="off")

            with col_kpi_aa2:
                st.metric("💰 Costi F&B Medi Mensili", _fmt_kpi_aa(_costi_fb_medi_aa), delta=" ", delta_color="off")

            with col_kpi_aa3:
                st.metric("🍔 Food Cost Medio", f"{_fc_perc_aa:.1f}%", delta=" ", delta_color="off")

            with col_kpi_aa4:
                st.metric("💵 Margine Medio Mensile", _fmt_kpi_aa(_margine_medio_aa), delta=" ", delta_color="off")

            with col_kpi_aa5:
                st.metric("📊 Margine % Medio", f"{_margine_perc_aa:.1f}%", delta=" ", delta_color="off")

            # ============================================
            # ANALISI KPI PER CENTRO
            # ============================================
            _colori_kpi = {'🟢': '#16a34a', '🟡': '#ca8a04', '🟠': '#ea580c', '🔴': '#dc2626', 'ℹ️': '#2563eb'}
            _centri_analisi = _centri_con_fatturato
            _icone_kpi = icone_centri

            _commenti_centri = []

            # Food Cost per centro
            for _c_nome in _centri_analisi:
                _row = df_centri_main[df_centri_main['Centro'] == _c_nome]
                if _row.empty:
                    continue
                _spesa_c = float(_row['Spesa'].values[0])
                if _spesa_c == 0:
                    continue
                _fc_c = float(_row['pct_fatt'].values[0])

                # Soglie food cost
                if _fc_c <= 28:
                    _em, _txt = '🟢', 'Incidenza eccellente — ottimo controllo costi'
                elif _fc_c <= 33:
                    _em, _txt = '🟡', 'Incidenza nella norma per il settore'
                elif _fc_c <= 38:
                    _em, _txt = '🟠', 'Incidenza sopra la media — valutare ottimizzazione'
                else:
                    _em, _txt = '🔴', 'Incidenza critica — necessaria revisione costi'

                _commenti_centri.append({
                    'kpi_nome': f'{_icone_kpi.get(_c_nome, "")} {_c_nome} — % Costi su Fatturato',
                    'percentuale': f'{_fc_c:.1f}%',
                    'commento': _txt,
                    'emoji': _em,
                    'colore': _colori_kpi.get(_em, '#6b7280')
                })

            # Centro più performante (margine % più alto)
            _best_centro = None
            _best_marg_perc = -999
            _worst_centro = None
            _worst_marg_perc = 999
            for _c_nome in _centri_analisi:
                _row = df_centri_main[df_centri_main['Centro'] == _c_nome]
                if _row.empty:
                    continue
                _spesa_c = float(_row['Spesa'].values[0])
                _fc_c = float(_row['pct_fatt'].values[0])
                if _spesa_c == 0 and _fc_c == 0:
                    continue
                _marg_perc_c = 100.0 - _fc_c
                if _marg_perc_c > _best_marg_perc:
                    _best_marg_perc = _marg_perc_c
                    _best_centro = _c_nome
                if _marg_perc_c < _worst_marg_perc:
                    _worst_marg_perc = _marg_perc_c
                    _worst_centro = _c_nome

            if _best_centro:
                _commenti_centri.append({
                    'kpi_nome': f'{_icone_kpi.get(_best_centro, "")} Centro più performante',
                    'percentuale': f'{_best_marg_perc:.1f}%',
                    'commento': f'{_best_centro} ha il margine % più alto del periodo',
                    'emoji': '🟢',
                    'colore': _colori_kpi['🟢']
                })
            if _worst_centro and _worst_centro != _best_centro:
                _commenti_centri.append({
                    'kpi_nome': f'{_icone_kpi.get(_worst_centro, "")} Centro più critico',
                    'percentuale': f'{_worst_marg_perc:.1f}%',
                    'commento': f'{_worst_centro} ha il margine % più basso — verificare costi e prezzi',
                    'emoji': '🔴',
                    'colore': _colori_kpi['🔴']
                })

            # Distribuzione anomala: centro con peso costi >> peso fatturato
            if fatturato_split_attivo and fatturato_totale_split > 0:
                for _c_nome in _centri_analisi:
                    _fatt_c = fatturato_per_centro.get(_c_nome, 0.0)
                    _row = df_centri_main[df_centri_main['Centro'] == _c_nome]
                    if _row.empty or _fatt_c == 0:
                        continue
                    _spesa_c = float(_row['Spesa'].values[0])
                    _peso_fatt = (_fatt_c / fatturato_totale_split * 100)
                    _peso_costi = (_spesa_c / totale_costi_fb * 100) if totale_costi_fb > 0 else 0.0
                    _diff = _peso_costi - _peso_fatt
                    if _diff > 10:  # costi pesano >10pp in più del fatturato
                        _commenti_centri.append({
                            'kpi_nome': f'{_icone_kpi.get(_c_nome, "")} {_c_nome} — Squilibrio costi/fatturato',
                            'percentuale': f'+{_diff:.0f}pp',
                            'commento': f'Genera il {_peso_fatt:.0f}% del fatturato ma concentra il {_peso_costi:.0f}% dei costi F&B',
                            'emoji': '🟠',
                            'colore': _colori_kpi['🟠']
                        })

            # Food Cost complessivo
            if _fc_perc_aa <= 28:
                _em_fc, _txt_fc = '🟢', 'Food cost eccellente — ottimo controllo acquisti e sprechi'
            elif _fc_perc_aa <= 33:
                _em_fc, _txt_fc = '🟡', 'Food cost nella norma per il settore ristorazione'
            elif _fc_perc_aa <= 38:
                _em_fc, _txt_fc = '🟠', 'Food cost sopra la media — valutare ottimizzazione acquisti o menù'
            else:
                _em_fc, _txt_fc = '🔴', 'Food cost critico — necessaria revisione fornitori, porzioni e sprechi'
            _commenti_centri.append({
                'kpi_nome': '🍔 Food Cost Complessivo',
                'percentuale': f'{_fc_perc_aa:.1f}%',
                'commento': _txt_fc,
                'emoji': _em_fc,
                'colore': _colori_kpi.get(_em_fc, '#6b7280')
            })

            # 1° Margine complessivo
            if _margine_perc_aa <= 55:
                _em_pm, _txt_pm = '🔴', '1° Margine molto basso — costi F&B troppo alti rispetto al fatturato'
            elif _margine_perc_aa <= 62:
                _em_pm, _txt_pm = '🟠', '1° Margine sotto la media — margine di miglioramento sui costi'
            elif _margine_perc_aa <= 70:
                _em_pm, _txt_pm = '🟡', '1° Margine nella norma per il settore'
            else:
                _em_pm, _txt_pm = '🟢', '1° Margine eccellente — ottima marginalità sui prodotti'
            _commenti_centri.append({
                'kpi_nome': '💵 1° Margine Complessivo',
                'percentuale': f'{_margine_perc_aa:.1f}%',
                'commento': _txt_pm,
                'emoji': _em_pm,
                'colore': _colori_kpi.get(_em_pm, '#6b7280')
            })

            if _commenti_centri:
                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                st.markdown('<h4 style="color:#1e40af;font-weight:700;">💬 Analisi KPI</h4>', unsafe_allow_html=True)
                for c in _commenti_centri:
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

        else:
            st.info("📊 Nessun dato disponibile per il calcolo dei KPI del periodo.")

# ============================================
# TAB: CENTRI DI PRODUZIONE (F&B)
# ============================================
if st.session_state.margine_tab == "centri":

    from config.constants import CENTRI_DI_PRODUZIONE, CATEGORIE_SPESE_GENERALI, MESI_ITA
    from services.db_service import carica_e_prepara_dataframe

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # ============================================
    # FILTRO TEMPORALE
    # ============================================
    oggi_cp = pd.Timestamp.now()
    oggi_date_cp = oggi_cp.date()
    inizio_mese_cp = oggi_cp.replace(day=1).date()
    inizio_trimestre_cp = oggi_cp.replace(month=((oggi_cp.month-1)//3)*3+1, day=1).date()
    inizio_semestre_cp = oggi_cp.replace(month=1 if oggi_cp.month <= 6 else 7, day=1).date()
    inizio_anno_cp = oggi_cp.replace(month=1, day=1).date()

    periodo_options_cp = [
        "📅 Mese in Corso",
        "📊 Trimestre in Corso",
        "📈 Semestre in Corso",
        "🗓️ Anno in Corso",
        "⚙️ Periodo Personalizzato"
    ]

    if 'cm_centri_periodo_dropdown' not in st.session_state:
        st.session_state.cm_centri_periodo_dropdown = "🗓️ Anno in Corso"

    col_periodo_cp, col_info_cp = st.columns([1, 3])

    with col_periodo_cp:
        periodo_sel_cp = st.selectbox(
            "Periodo",
            options=periodo_options_cp,
            label_visibility="collapsed",
            index=periodo_options_cp.index(st.session_state.cm_centri_periodo_dropdown) if st.session_state.cm_centri_periodo_dropdown in periodo_options_cp else 3,
            key="cm_centri_filtro_periodo"
        )

    st.session_state.cm_centri_periodo_dropdown = periodo_sel_cp

    data_inizio_cp = None
    data_fine_cp = oggi_date_cp

    if periodo_sel_cp == "📅 Mese in Corso":
        data_inizio_cp = inizio_mese_cp
    elif periodo_sel_cp == "📊 Trimestre in Corso":
        data_inizio_cp = inizio_trimestre_cp
    elif periodo_sel_cp == "📈 Semestre in Corso":
        data_inizio_cp = inizio_semestre_cp
    elif periodo_sel_cp == "🗓️ Anno in Corso":
        data_inizio_cp = inizio_anno_cp
    elif periodo_sel_cp == "⚙️ Periodo Personalizzato":
        st.markdown("##### Seleziona Range Date")
        col_da_cp, col_a_cp = st.columns(2)
        if 'cp_centri_data_inizio' not in st.session_state:
            st.session_state.cp_centri_data_inizio = inizio_anno_cp
        if 'cp_centri_data_fine' not in st.session_state:
            st.session_state.cp_centri_data_fine = oggi_date_cp
        with col_da_cp:
            data_inizio_custom_cp = st.date_input("📅 Da", value=st.session_state.cp_centri_data_inizio, min_value=inizio_anno_cp, key="cp_centri_data_da")
        with col_a_cp:
            data_fine_custom_cp = st.date_input("📅 A", value=st.session_state.cp_centri_data_fine, min_value=inizio_anno_cp, key="cp_centri_data_a")
        if data_inizio_custom_cp > data_fine_custom_cp:
            st.error("⚠️ La data iniziale deve essere precedente alla data finale!")
            data_inizio_cp = st.session_state.cp_centri_data_inizio
            data_fine_cp = st.session_state.cp_centri_data_fine
        else:
            st.session_state.cp_centri_data_inizio = data_inizio_custom_cp
            st.session_state.cp_centri_data_fine = data_fine_custom_cp
            data_inizio_cp = data_inizio_custom_cp
            data_fine_cp = data_fine_custom_cp

    if data_inizio_cp is None:
        data_inizio_cp = inizio_anno_cp

    giorni_cp = (data_fine_cp - data_inizio_cp).days + 1
    with col_info_cp:
        st.markdown(f"""
        <div style="display: inline-block; width: fit-content; background: linear-gradient(135deg, #fef9c3 0%, #fefce8 100%);
                    padding: 10px 16px;
                    border-radius: 8px;
                    border: 1px solid #fde047;
                    font-size: clamp(0.78rem, 1.8vw, 0.88rem);
                    font-weight: 500;
                    line-height: 1.5;
                    margin-top: 0px;
                    vertical-align: middle;">
            📆 {data_inizio_cp.strftime('%d/%m/%Y')} → {data_fine_cp.strftime('%d/%m/%Y')} ({giorni_cp} giorni)
        </div>
        """, unsafe_allow_html=True)

    # ============================================
    # CARICA DATI E FILTRA
    # ============================================
    df_full = carica_e_prepara_dataframe(user_id, ristorante_id=current_ristorante)

    if df_full is None or df_full.empty:
        st.warning("⚠️ Nessun dato disponibile.")
    else:
        # Crea colonna Data_DT se mancante
        if 'Data_DT' not in df_full.columns and 'DataDocumento' in df_full.columns:
            df_full['Data_DT'] = pd.to_datetime(df_full['DataDocumento'], errors='coerce')

        # Filtra per periodo
        if 'Data_DT' in df_full.columns:
            df_filtrato_cp = df_full[
                (df_full['Data_DT'].dt.date >= data_inizio_cp) &
                (df_full['Data_DT'].dt.date <= data_fine_cp)
            ].copy()
        else:
            df_filtrato_cp = df_full.copy()

        # Filtra solo F&B (escludi spese generali)
        df_food_cp = df_filtrato_cp[~df_filtrato_cp['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()

        if df_food_cp.empty:
            st.warning("⚠️ Nessun dato F&B disponibile per il periodo selezionato")
        else:
            # Mappa categorie → centri di produzione
            cat_to_centro = {}
            for centro, cats in CENTRI_DI_PRODUZIONE.items():
                for cat in cats:
                    cat_to_centro[cat] = centro

            df_centri = df_food_cp.copy()
            df_centri['Centro'] = df_centri['Categoria'].map(cat_to_centro).fillna('Da Classificare')
            _non_mappate_cp = df_centri[df_centri['Centro'] == 'Da Classificare']['Categoria'].unique().tolist()
            if _non_mappate_cp:
                logger.warning(f"⚠️ Categorie F&B non mappate a nessun centro (escluse dal tab Centri): {_non_mappate_cp}")

            # Filtra solo i centri definiti (escludi "Da Classificare")
            centri_validi = list(CENTRI_DI_PRODUZIONE.keys())
            df_centri = df_centri[df_centri['Centro'].isin(centri_validi)]

            if df_centri.empty:
                st.info("📊 Nessun dato mappato ai centri di produzione per il periodo selezionato")
            else:
                df_centri['mese_nome'] = df_centri['Data_DT'].apply(
                    lambda x: f"{MESI_ITA[x.month]} {x.year}" if pd.notna(x) else ''
                )
                df_centri['mese_sort'] = df_centri['Data_DT'].apply(
                    lambda x: f"{x.year}-{x.month:02d}" if pd.notna(x) else ''
                )

                # Pivot: Centro × Mesi
                pivot = df_centri.pivot_table(
                    index='Centro',
                    columns='mese_nome',
                    values='TotaleRiga',
                    aggfunc='sum',
                    fill_value=0
                )

                # Ordine mesi cronologico — includi TUTTI i mesi del periodo (mesi senza dati appaiono come 0)
                mesi_ord = []
                for _a_cp in range(data_inizio_cp.year, data_fine_cp.year + 1):
                    _m_from_cp = data_inizio_cp.month if _a_cp == data_inizio_cp.year else 1
                    _m_to_cp = data_fine_cp.month if _a_cp == data_fine_cp.year else 12
                    for _m_cp in range(_m_from_cp, _m_to_cp + 1):
                        mesi_ord.append(f"{MESI_ITA[_m_cp]} {_a_cp}")
                pivot = pivot.reindex(columns=mesi_ord, fill_value=0)

                # Ordine centri fisso
                ordine_centri = [c for c in centri_validi if c in pivot.index]
                pivot = pivot.reindex(ordine_centri)

                # TOTALE e MEDIA
                pivot['TOTALE'] = pivot.sum(axis=1)
                pivot['MEDIA'] = pivot.drop(columns=['TOTALE']).replace(0, pd.NA).mean(axis=1)

                # Report
                st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                st.markdown("### 🏭 Spesa per Centro di Costo mensile")

                # Costruisci display DataFrame
                mesi_cols = [c for c in pivot.columns if c not in ['TOTALE', 'MEDIA']]

                # ========================================================
                # CENTRI ESPANDIBILI CON CATEGORIE
                # ========================================================
                icone_centri_cp = {
                    "FOOD": "🍖", "BAR": "☕", "ALCOLICI": "🍷",
                    "DOLCI": "🍰", "MATERIALE DI CONSUMO": "📦", "SHOP": "🛒"
                }

                # Flag per mostrare/nascondere colonne %
                mostra_pct_centri = st.checkbox("📊 Visualizza incidenze %", value=False, key="cm_mostra_incidenze_pct_centri")

                grand_total_centri = pivot['TOTALE'].sum()

                for centro_nome in ordine_centri:
                    spesa_tot = pivot.loc[centro_nome, 'TOTALE']
                    media_c = pivot.loc[centro_nome, 'MEDIA']
                    pct_incid = (spesa_tot / grand_total_centri * 100) if grand_total_centri > 0 else 0.0
                    icona = icone_centri_cp.get(centro_nome, "📁")

                    with st.expander(f"{icona} **{centro_nome}** — Totale: € {spesa_tot:,.0f} | Media: € {media_c:,.0f} | Incid.: {pct_incid:.1f}%", expanded=False):
                        # Categorie di questo centro
                        cats_centro = CENTRI_DI_PRODUZIONE.get(centro_nome, [])
                        df_cats = df_centri[df_centri['Centro'] == centro_nome].copy()

                        if df_cats.empty:
                            st.info("Nessun dato per questo centro")
                            continue

                        # Pivot per categoria
                        pivot_cat = df_cats.pivot_table(
                            index='Categoria',
                            columns='mese_nome',
                            values='TotaleRiga',
                            aggfunc='sum',
                            fill_value=0
                        )
                        pivot_cat = pivot_cat.reindex(columns=[m for m in mesi_ord if m in pivot_cat.columns])

                        pivot_cat['TOTALE'] = pivot_cat.sum(axis=1)
                        pivot_cat['MEDIA'] = pivot_cat.drop(columns=['TOTALE']).replace(0, pd.NA).mean(axis=1)
                        pivot_cat = pivot_cat.sort_values('TOTALE', ascending=False)

                        # Build display dataframe
                        cat_display = pd.DataFrame()
                        cat_display['Categoria'] = pivot_cat.index

                        cat_mesi_cols = [c for c in pivot_cat.columns if c not in ['TOTALE', 'MEDIA']]
                        for col in cat_mesi_cols:
                            cat_display[col] = pivot_cat[col].apply(lambda x: x if x > 0 else None).values
                            if mostra_pct_centri:
                                col_tot = pivot_cat[col].sum()
                                cat_display[f'{col} %'] = (pivot_cat[col] / col_tot * 100).round(1).values if col_tot > 0 else 0.0

                        cat_display['TOTALE'] = pivot_cat['TOTALE'].values
                        if mostra_pct_centri:
                            tot_centro = pivot_cat['TOTALE'].sum()
                            cat_display['TOTALE %'] = (pivot_cat['TOTALE'] / tot_centro * 100).round(1).values if tot_centro > 0 else 0.0
                        cat_display['MEDIA'] = pivot_cat['MEDIA'].values

                        # Column config
                        cc = {'Categoria': st.column_config.TextColumn('Categoria', width='medium')}
                        for col in cat_mesi_cols:
                            cc[col] = st.column_config.NumberColumn(col, format="€ %.0f")
                            if mostra_pct_centri:
                                cc[f'{col} %'] = st.column_config.ProgressColumn('%', format="%.1f%%", min_value=0, max_value=100, width='small')
                        cc['TOTALE'] = st.column_config.NumberColumn('TOTALE', format="€ %.0f")
                        if mostra_pct_centri:
                            cc['TOTALE %'] = st.column_config.ProgressColumn('Incid. %', format="%.1f%%", min_value=0, max_value=100, width='small')
                        cc['MEDIA'] = st.column_config.NumberColumn('MEDIA', format="€ %.0f")

                        alt = max(len(cat_display) * 35 + 50, 120)
                        st.dataframe(cat_display, hide_index=True, use_container_width=True, height=alt, column_config=cc)

                    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

                # Riepilogo
                tot_centri = pivot['TOTALE'].sum()
                n_centri = len(pivot)
                media_centri = tot_centri / max(len(mesi_cols), 1)
                excel_data_centri = io.BytesIO()
                with pd.ExcelWriter(excel_data_centri, engine='openpyxl') as writer:
                    pivot.to_excel(writer, sheet_name='Centri Produzione')
                excel_data_centri.seek(0)

                _col_centri_left, _col_centri_right = st.columns([5, 1])
                with _col_centri_left:
                    st.markdown(f"""
                    <div style="background-color: #E3F2FD; padding: clamp(0.75rem, 1.5vw, 0.9rem) clamp(0.9rem, 2vw, 1.25rem); border-radius: 8px; border: 2px solid #2196F3; margin-top: 8px; width: min(100%, fit-content); max-width: 100%; box-sizing: border-box;">
                        <span style="color: #1565C0; font-weight: bold; font-size: clamp(0.85rem, 2vw, 1rem); white-space: normal; overflow-wrap: anywhere; line-height: 1.4;">
                            📊 N. Centri: {n_centri} | 💰 Totale: € {tot_centri:,.0f} | 📊 Media mensile: € {media_centri:,.0f}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

                with _col_centri_right:
                    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
                    st.download_button(
                        label="Excel",
                        data=excel_data_centri,
                        file_name=f"centri_produzione_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="cm_download_excel_centri",
                        type="primary",
                        use_container_width=False,
                    )

if st.session_state.margine_tab == "calcolo":

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # Anno fisso: anno corrente
    anno_corrente = datetime.now().year
    anno = anno_corrente

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

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style="padding: 10px 14px; margin-bottom: 8px;">
        <span style="color: #1e40af; font-weight: 600; font-size: 1rem;">💡 Inserimento rapido - Seleziona metrica, mese o Tutti i mesi, inserisci l'importo e clicca Applica.</span>
    </div>
    """, unsafe_allow_html=True)

    _OPZIONI_RAPIDA = {
        "Ricavi IVA 10%": ("Fatt_IVA10", 100.0),
        "Ricavi IVA 22%": ("Fatt_IVA22", 100.0),
        "Altri ricavi (no iva)": ("Altri_Ricavi_NoIVA", 100.0),
        "Altri Costi F&B": ("Altri_FB", 50.0),
        "Altre Spese Generali": ("Altri_Spese", 50.0),
        "Costo personale Lordo": ("Costo_Dipendenti", 100.0),
    }
    _OPZIONI_TEMPORALI = ["Tutti i mesi"] + MESI_NOMI

    col_sel, col_tempo, col_imp, col_btn, col_empty = st.columns([1.4, 1.1, 1.2, 0.95, 2.35])
    with col_sel:
        voce_selezionata = st.selectbox(
            "Voce da compilare",
            options=list(_OPZIONI_RAPIDA.keys()),
            key="margine_compilazione_rapida_voce",
            label_visibility="collapsed"
        )
    with col_tempo:
        periodo_selezionato = st.selectbox(
            "Periodo",
            options=_OPZIONI_TEMPORALI,
            key="margine_compilazione_rapida_periodo",
            label_visibility="collapsed"
        )
    with col_imp:
        _colonna_target, _step_rapida = _OPZIONI_RAPIDA[voce_selezionata]
        importo_rapido = st.number_input(
            "Importo",
            min_value=0.0,
            step=_step_rapida,
            format="%.2f",
            key="margine_compilazione_rapida_importo",
            label_visibility="collapsed"
        )
    with col_btn:
        if st.button("📋 Applica", use_container_width=True, key="margine_applica_rapido"):
            df_input_apply = df_input.copy()
            mesi_target = range(1, 13) if periodo_selezionato == "Tutti i mesi" else [MESI_NOMI.index(periodo_selezionato) + 1]
            for mese_num in mesi_target:
                df_input_apply.loc[df_input_apply['MeseNum'] == mese_num, _colonna_target] = float(importo_rapido)

            df_risultati_apply = calcola_risultati(df_input_apply)
            with st.spinner("Salvataggio in corso..."):
                success = salva_margini_anno(
                    user_id, current_ristorante, anno, df_input_apply, df_risultati_apply
                )
            if success:
                st.success("✅ Valore applicato e salvato")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Errore durante il salvataggio. Riprova.")

    # ============================================
    # TABELLA UNICA TRASPOSTA - INPUT + RISULTATI
    # ============================================
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<h3 style="color:#1e40af;font-weight:700;">📊 Tabella Annuale ricavi-costi-margini</h3>', unsafe_allow_html=True)

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
    <li>I <strong>mesi</strong> compaiono in tabella solo quando sono stati popolati da <strong>fatture</strong> o da <strong>valori manuali salvati</strong></li>
    <li>I dati sono salvati per <strong>ristorante</strong> e <strong>anno</strong> — ogni ristorante ha i propri margini</li>
    </ul>
    </div>
    </details>
    """, unsafe_allow_html=True)

    # Build transposed display from df_input
    df_display = build_transposed_df(df_input)

    voce_display_map = {
        'Fatt. IVA 10%': 'Ricavi | IVA 10%',
        'Fatt. IVA 22%': 'Ricavi | IVA 22%',
        'Altri ricavi (no iva)': 'Ricavi | Altri ricavi',
        '= Fatturato Netto': 'Totale | Fatturato Netto',
        'Costi F&B (da Fatture)': 'Costi F&B | da fatture',
        'Altri Costi F&B': 'Costi F&B | altri costi',
        '= Costi F&B Totali': 'Totale | Costi F&B',
        '= 1° Margine': 'Margine | 1° Margine',
        'Spese Gen. (da Fatture)': 'Spese Gen. | da fatture',
        'Altre Spese Generali': 'Spese Gen. | altre spese',
        'Costo personale Lordo': 'Personale | costo lordo',
        '= 2° Margine (MOL)': 'Margine | 2° Margine (MOL)',
    }
    df_display['Voce'] = df_display['Voce'].map(lambda v: voce_display_map.get(v, v))

    euro_cols_all = [c for c in df_display.columns if c.endswith(' €')]
    pct_cols_all = [c for c in df_display.columns if c.endswith(' %')]

    # ============================================
    # NASCONDI TUTTI I MESI COMPLETAMENTE VUOTI
    # Il mese riappare automaticamente quando almeno un campo viene popolato
    # da fatture o da un inserimento già salvato.
    # ============================================
    _COLONNE_DATI = ['Fatt_IVA10', 'Fatt_IVA22', 'Altri_Ricavi_NoIVA',
                     'Costi_FB_Auto', 'Altri_FB', 'Costi_Spese_Auto',
                     'Altri_Spese', 'Costo_Dipendenti']
    mesi_nascosti = []
    for _m_idx, _mese_nome in enumerate(MESI_NOMI, start=1):
        _riga = df_input[df_input['MeseNum'] == _m_idx]
        if _riga.empty:
            mesi_nascosti.append(_mese_nome)
            continue

        _valori = [float(_riga.iloc[0][c]) for c in _COLONNE_DATI if c in _riga.columns]
        if not any(abs(v) > 0.0001 for v in _valori):
            mesi_nascosti.append(_mese_nome)

    # Rimuovi colonne dei mesi completamente vuoti dalla vista
    if mesi_nascosti:
        _cols_hide = [f'{m} €' for m in mesi_nascosti] + [f'{m} %' for m in mesi_nascosti]
        df_display = df_display.drop(columns=[c for c in _cols_hide if c in df_display.columns])
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # Mesi visibili dopo i filtri
    mesi_visibili = [m for m in MESI_NOMI if m not in mesi_nascosti]

    # Legenda colori sezioni
    st.markdown("""
    <div style="display:flex; flex-wrap:wrap; gap:8px; margin: 4px 0 10px 0;">
        <span style="color:#1d4ed8; border:1px solid #bfdbfe; border-radius:999px; padding:4px 12px; font-size:0.78rem; font-weight:600;">Ricavi</span>
        <span style="color:#c2410c; border:1px solid #fed7aa; border-radius:999px; padding:4px 12px; font-size:0.78rem; font-weight:600;">Costi F&B</span>
        <span style="color:#6d28d9; border:1px solid #ddd6fe; border-radius:999px; padding:4px 12px; font-size:0.78rem; font-weight:600;">Spese Generali</span>
        <span style="color:#be185d; border:1px solid #fbcfe8; border-radius:999px; padding:4px 12px; font-size:0.78rem; font-weight:600;">Personale</span>
        <span style="color:#166534; border:1px solid #bbf7d0; border-radius:999px; padding:4px 12px; font-size:0.78rem; font-weight:600;">Totali & Margini</span>
    </div>
    """, unsafe_allow_html=True)
    row_colors = {
        'Ricavi | IVA 10%': '#1d4ed8',
        'Ricavi | IVA 22%': '#1d4ed8',
        'Ricavi | Altri ricavi': '#1d4ed8',
        'Totale | Fatturato Netto': '#1e40af',
        'Costi F&B | da fatture': '#c2410c',
        'Costi F&B | altri costi': '#c2410c',
        'Totale | Costi F&B': '#9a3412',
        'Margine | 1° Margine': '#166534',
        'Spese Gen. | da fatture': '#6d28d9',
        'Spese Gen. | altre spese': '#6d28d9',
        'Personale | costo lordo': '#be185d',
        'Margine | 2° Margine (MOL)': '#15803d',
    }
    bold_rows = {
        'Totale | Fatturato Netto',
        'Totale | Costi F&B',
        'Margine | 1° Margine',
        'Margine | 2° Margine (MOL)',
    }
    metric_bg_colors = {
        'Totale | Fatturato Netto': 'rgba(30, 64, 175, 0.10)',
        'Totale | Costi F&B': 'rgba(154, 52, 18, 0.10)',
        'Margine | 1° Margine': 'rgba(22, 101, 52, 0.10)',
        'Margine | 2° Margine (MOL)': 'rgba(21, 128, 61, 0.10)',
    }
    pct_total_rows = {
        'Costi F&B | da fatture',
        'Costi F&B | altri costi',
        'Totale | Costi F&B',
        'Margine | 1° Margine',
        'Spese Gen. | da fatture',
        'Spese Gen. | altre spese',
        'Personale | costo lordo',
        'Margine | 2° Margine (MOL)',
    }

    df_input_current = df_input.copy()
    df_display_render = df_display.copy()
    euro_cols_visibili = [f'{mese} €' for mese in mesi_visibili if f'{mese} €' in df_display_render.columns]
    pct_cols_visibili = [f'{mese} %' for mese in mesi_visibili if f'{mese} %' in df_display_render.columns]

    totale_netto_mesi_visibili = 0.0
    _mask_netto = df_display_render['Voce'] == 'Totale | Fatturato Netto'
    if _mask_netto.any() and euro_cols_visibili:
        totale_netto_mesi_visibili = float(df_display_render.loc[_mask_netto, euro_cols_visibili].fillna(0.0).sum(axis=1).iloc[0])

    if euro_cols_visibili:
        df_display_render['Totale €'] = df_display_render[euro_cols_visibili].fillna(0.0).sum(axis=1)
    else:
        df_display_render['Totale €'] = 0.0

    def _compute_total_pct(row):
        if row['Voce'] not in pct_total_rows or totale_netto_mesi_visibili <= 0:
            return None
        return round((float(row['Totale €']) / totale_netto_mesi_visibili) * 100, 1)

    df_display_render['Totale %'] = df_display_render.apply(_compute_total_pct, axis=1)

    for col in euro_cols_all:
        if col in df_display_render.columns:
            df_display_render[col] = df_display_render[col].map(
                    lambda value: '' if pd.isna(value) or abs(float(value)) < 0.5 else f'€ {float(value):.0f}'
            )
    for col in pct_cols_all:
        if col in df_display_render.columns:
            df_display_render[col] = df_display_render[col].map(
                lambda value: '' if pd.isna(value) or abs(float(value)) < 0.05 else f'{float(value):.1f}%'
            )
    df_display_render['Totale €'] = df_display_render['Totale €'].map(
            lambda value: '' if pd.isna(value) or abs(float(value)) < 0.5 else f'€ {float(value):.0f}'
    )
    df_display_render['Totale %'] = df_display_render['Totale %'].map(
        lambda value: '' if pd.isna(value) or abs(float(value)) < 0.05 else f'{float(value):.1f}%'
    )

    def _style_rows(row):
        row_label = row.iloc[0]
        color = row_colors.get(row_label, '#334155')
        weight = '800' if row_label in bold_rows else '500'
        size = '1.08rem' if row_label in bold_rows else '0.92rem'
        styles = [f'color: {color}; font-weight: {weight} !important; font-size: {size} !important;'] * len(row)
        if row_label in metric_bg_colors:
            row_bg = metric_bg_colors[row_label]
            styles = [style + f' background-color: {row_bg}; box-shadow: inset 0 0 0 9999px {row_bg};' for style in styles]
            styles[0] = styles[0] + f' border-left: 4px solid {row_colors[row_label]};'
        return styles

    separator_styles = []
    for index in range(len(mesi_visibili)):
        col_position = 3 + (index * 2)
        separator_styles.append({
            'selector': f'thead th:nth-child({col_position}), tbody td:nth-child({col_position})',
            'props': [('border-right', '3px solid #94a3b8')]
        })
    separator_styles.extend([
        {'selector': 'thead th:nth-child(1), tbody td:nth-child(1)', 'props': [('border-right', '3px solid #94a3b8')]},
        {'selector': 'thead th:nth-last-child(2), tbody td:nth-last-child(2)', 'props': [('border-left', '3px solid #64748b')]},
        {'selector': 'thead th:last-child, tbody td:last-child', 'props': [('border-right', '3px solid #64748b')]},
    ])

    table_styles = [
        {'selector': 'table', 'props': [('width', '100%'), ('border-collapse', 'separate'), ('border-spacing', '0'), ('font-size', '0.92rem'), ('table-layout', 'auto')]},
        {'selector': 'thead th', 'props': [('color', '#111827'), ('font-weight', '800'), ('padding', '11px 12px'), ('border-bottom', '2px solid #94a3b8'), ('text-align', 'right'), ('background', '#eef2f7'), ('border-top', '1px solid #d7dde6')]},
        {'selector': 'thead th:first-child', 'props': [('text-align', 'left'), ('width', '280px'), ('border-top-left-radius', '10px')]},
        {'selector': 'thead th:last-child', 'props': [('border-top-right-radius', '10px')]},
        {'selector': 'tbody td', 'props': [('padding', '10px 12px'), ('border-bottom', '1px solid #d3dde8'), ('text-align', 'right'), ('background', 'transparent')]},
        {'selector': 'tbody td:first-child', 'props': [('text-align', 'left'), ('white-space', 'nowrap'), ('font-weight', '600'), ('padding-right', '16px')]},
        {'selector': 'tbody tr:hover td', 'props': [('background', '#fafcff')]},
        {'selector': 'tbody tr:last-child td', 'props': [('border-bottom', 'none')]},
    ] + separator_styles
    styled_table = (
        df_display_render.rename(columns={'Voce': '📊 Metriche'}).style
        .hide(axis='index')
        .apply(_style_rows, axis=1)
        .set_table_styles(table_styles)
    )
    st.markdown(
        f"<div style='overflow-x:auto; padding-bottom:4px;'>{styled_table.to_html()}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

    # ============================================
    # CALCOLA RISULTATI PER KPI + EXPORT
    # ============================================
    df_risultati = calcola_risultati(df_input_current)

    # ============================================
    # KPI CARDS RIEPILOGO ANNO
    # ============================================
    st.markdown("---")
    st.markdown('<h3 style="color:#1e3a5f;font-weight:700;">📊 Riepilogo KPI - Media valori per periodo</h3>', unsafe_allow_html=True)

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

    col_periodo_kpi, col_info_kpi = st.columns([1.5, 4.5])

    with col_periodo_kpi:
        st.markdown('<p style="color:#1e40af;font-weight:600;font-size:0.9rem;margin:0 0 4px 0;">📅 Periodo di riferimento KPI</p>', unsafe_allow_html=True)
        periodo_sel = st.selectbox(
            "📅 Periodo di riferimento KPI",
            options=list(periodi_kpi.keys()),
            index=0,
            key="kpi_periodo_select",
            label_visibility="collapsed"
        )

    mesi_filtro = periodi_kpi[periodo_sel]
    with col_info_kpi:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display: inline-block; width: fit-content; background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
                    padding: 10px 16px;
                    border-radius: 8px;
                    border: 1px solid #93c5fd;
                    color: #1e3a8a;
                    font-size: clamp(0.78rem, 1.8vw, 0.88rem);
                    font-weight: 500;
                    line-height: 1.5;">
            📊 {periodo_sel} ({len(mesi_filtro)} mesi)
        </div>
        """, unsafe_allow_html=True)

    kpi = calcola_kpi_anno(df_risultati, mesi_filtro=mesi_filtro)
    num_mesi = kpi['num_mesi']
    df_kpi_mesi = df_risultati[
        (df_risultati['MeseNum'] != 99) &
        (df_risultati['Fatt_Netto'] > 0) &
        (df_risultati['MeseNum'].isin(mesi_filtro))
    ]

    if num_mesi > 0:
        mol_medio = kpi['mol_medio']
        fatt_medio = kpi['fatt_medio']
        fatt_totale = round(df_kpi_mesi['Fatt_Netto'].sum(), 2) if not df_kpi_mesi.empty else 0.0
        fc_perc = kpi['fc_medio']
        mol_perc = kpi['mol_perc_medio']
        primo_marg = kpi['primo_margine_medio']
        primo_marg_perc = kpi['primo_margine_perc_media']
        costi_fb = kpi['costi_fb_medi']
        spese_gen = kpi['spese_gen_medie']
        spese_perc = kpi['spese_gen_perc_media']
        personale_medio = kpi['personale_medio']
        personale_perc = kpi['personale_perc_media']

        def _fmt_kpi(val):
            segno = "-" if val < 0 else ""
            return f"{segno}€{abs(val):,.0f}".replace(",", ".")
    
        # CSS per KPI con card custom uniformi
        st.markdown("""
        <style>
        .margine-kpi-grid {
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 12px;
            margin: 10px 0 4px 0;
        }
        .margine-kpi-card {
            background: linear-gradient(135deg, rgba(248, 249, 250, 0.95), rgba(233, 236, 239, 0.95));
            padding: clamp(1rem, 2.5vw, 1.25rem);
            border-radius: 12px;
            border: 1px solid rgba(206, 212, 218, 0.5);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.05);
            backdrop-filter: blur(10px);
            min-height: 122px;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .margine-kpi-label {
            color: #2563eb;
            font-weight: 600;
            font-size: clamp(0.74rem, 1.7vw, 0.86rem);
            line-height: 1.25;
            min-height: 2.4em;
        }
        .margine-kpi-value {
            color: #1e40af;
            font-size: clamp(1.18rem, 3.2vw, 1.62rem);
            font-weight: 700;
            line-height: 1.15;
            margin-top: 8px;
        }
        .margine-kpi-sub {
            color: #f97316;
            font-weight: 600;
            font-size: 0.82rem;
            margin-top: 8px;
            min-height: 1.3em;
        }
        @media (max-width: 1400px) {
            .margine-kpi-grid {
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }
        }
        @media (max-width: 900px) {
            .margine-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """, unsafe_allow_html=True)

        def _kpi_card_html(label: str, value: str, sub: str) -> str:
            return (
                "<div class='margine-kpi-card'>"
                f"<div class='margine-kpi-label'>{_html.escape(label)}</div>"
                f"<div class='margine-kpi-value'>{_html.escape(value)}</div>"
                f"<div class='margine-kpi-sub'>{_html.escape(sub)}</div>"
                "</div>"
            )

        kpi_cards_html = ''.join([
            _kpi_card_html('📈 Fatturato Totale', _fmt_kpi(fatt_totale), f'{num_mesi} mesi attivi nel periodo'),
            _kpi_card_html('📊 Fatturato Medio', _fmt_kpi(fatt_medio), 'media dei mesi attivi'),
            _kpi_card_html('🍔 Food Cost', _fmt_kpi(costi_fb), f'incidenza {fc_perc:.1f}%'),
            _kpi_card_html('💵 1° Margine', _fmt_kpi(primo_marg), f'incidenza {primo_marg_perc:.1f}%'),
            _kpi_card_html('💼 Spese Generali', _fmt_kpi(spese_gen), f'incidenza {spese_perc:.1f}%'),
            _kpi_card_html('👥 Costo del Lavoro', _fmt_kpi(personale_medio), f'incidenza {personale_perc:.1f}%'),
            _kpi_card_html('💰 2° Margine (MOL)', _fmt_kpi(mol_medio), f'incidenza {mol_perc:.1f}%'),
        ])
        st.markdown(f"<div class='margine-kpi-grid'>{kpi_cards_html}</div>", unsafe_allow_html=True)
    
        # ============================================
        # COMMENTI AUTOMATICI KPI
        # ============================================
        commenti = genera_commenti_kpi(kpi, df_risultati, mesi_filtro=mesi_filtro)
    
        if commenti:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            st.markdown('<h4 style="color:#1e3a5f;font-weight:700;">💬 Analisi KPI</h4>', unsafe_allow_html=True)
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
            'fatt_totale': fatt_totale,
            'fatt_medio': fatt_medio,
            'costi_fb': costi_fb,
            'fc_perc': fc_perc,
            'primo_marg': primo_marg,
            'primo_marg_perc': primo_marg_perc,
            'spese_gen': spese_gen,
            'spese_perc': spese_perc,
            'personale': personale_medio,
            'personale_perc': personale_perc,
            'mol_medio': mol_medio,
            'mol_perc': mol_perc
        }
        excel_data = export_excel_margini(df_risultati, anno, nome_rist, kpi_data)
        _col_excel_empty_t1, col_excel_t1 = st.columns([5, 1])
        with col_excel_t1:
            st.download_button(
                "Excel",
                data=excel_data,
                file_name=f"Margini_{anno}_{nome_rist.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="margine_download",
                use_container_width=False,
            )


