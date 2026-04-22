"""
Modulo ui_helpers per OH YEAH! Hub.

Funzioni condivise per:
- Caricamento CSS/JS da file statici
- Rendering pivot table mensile (Categorie / Fornitori)
"""

import os
import io
import logging
import pandas as pd
import streamlit as st
from config.logger_setup import get_logger

logger = get_logger('ui_helpers')

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')


def load_css(filename: str):
    """Carica un file CSS dalla cartella static/ e lo inietta via st.markdown."""
    path = os.path.join(_STATIC_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        logger.error(f"File statico non trovato: {filename}")
        return


_HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"],
section[data-testid="stSidebar"] {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    min-width: 0 !important;
    opacity: 0 !important;
    transform: translateX(-100%) !important;
}
[data-testid="stSidebarNav"],
[data-testid="collapsedControl"] {
    display: none !important;
}
</style>
"""


def hide_sidebar_css():
    """Inietta CSS per nascondere completamente la sidebar."""
    st.markdown(_HIDE_SIDEBAR_CSS, unsafe_allow_html=True)


def load_js(filename: str):
    """Carica un file JS dalla cartella static/ e lo inietta via st.markdown."""
    path = os.path.join(_STATIC_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            st.markdown(f'<script>{f.read()}</script>', unsafe_allow_html=True)
    except FileNotFoundError:
        logger.error(f"File statico non trovato: {filename}")
        return


def render_pivot_mensile(
    df_source: pd.DataFrame,
    index_col: str,
    mesi_ita: dict,
    sezione_key: str,
    sheet_name: str,
):
    """
    Renderizza una pivot table mensile con incidenze %, totale, media, export Excel.
    
    Usata sia per Categorie che per Fornitori (stessa logica, colonna indice diversa).
    
    Args:
        df_source: DataFrame filtrato (già F&B / Spese Generali / Tutti)
        index_col: Nome colonna indice ('Categoria' o 'Fornitore')
        mesi_ita: Dict {1: 'GENNAIO', ...}
        sezione_key: Suffisso univoco per widget keys ('categorie' o 'fornitori')
        sheet_name: Nome del foglio Excel per export
    """
    # Validazione input
    if df_source is None or df_source.empty:
        st.warning("⚠️ Nessun dato disponibile per questa sezione.")
        return
    
    required_cols = {index_col, 'Data_DT', 'TotaleRiga'}
    missing_cols = required_cols - set(df_source.columns)
    if missing_cols:
        st.error(f"❌ Errore: colonne mancanti nel dataframe: {missing_cols}")
        return
    
    # Filtra righe con Data_DT o TotaleRiga nulli, e con index_col nullo
    df_prep = df_source[
        df_source['Data_DT'].notna()
        & df_source['TotaleRiga'].notna()
        & df_source[index_col].notna()
        & (df_source[index_col].astype(str).str.strip() != '')
    ].copy()
    if df_prep.empty:
        st.info("📭 Nessun dato valido dopo validazione delle colonne.")
        return

    # Formato mese per visualizzazione (GENNAIO 2025)
    df_prep['Mese'] = df_prep['Data_DT'].apply(
        lambda x: f"{mesi_ita[x.month]} {x.year}" if pd.notna(x) else ''
    )
    df_prep['Mese_Ordine'] = df_prep['Data_DT'].apply(
        lambda x: f"{x.year}-{x.month:02d}" if pd.notna(x) else ''
    )

    # Pivot
    pivot = df_prep.pivot_table(
        index=index_col,
        columns='Mese',
        values='TotaleRiga',
        aggfunc='sum',
        fill_value=0
    )

    # Ordina colonne cronologicamente
    mese_ordine_map = df_prep[['Mese', 'Mese_Ordine']].drop_duplicates()
    mese_ordine_map = mese_ordine_map[mese_ordine_map['Mese'] != '']
    mese_ordine_map = dict(zip(mese_ordine_map['Mese'], mese_ordine_map['Mese_Ordine']))
    cols_sorted = sorted(list(pivot.columns), key=lambda x: mese_ordine_map.get(x, x))
    pivot = pivot[cols_sorted]

    # Totale e Media
    pivot['TOTALE'] = pivot.sum(axis=1)
    num_mesi = len(cols_sorted)
    pivot['MEDIA'] = pivot['TOTALE'] / num_mesi if num_mesi > 0 else 0
    pivot = pivot.sort_values('TOTALE', ascending=False)

    # Percentuali di incidenza
    col_totals = {col: pivot[col].sum() for col in cols_sorted}
    grand_total = pivot['TOTALE'].sum()

    # Display DataFrame con colonne % interleaved
    # FIX React #185: NON usare None per zero → tiene dtype=float64 puro (Arrow-safe).
    # Nessun column_config con format → evita bug Glide Data Grid in Streamlit 1.54.
    pivot_display = pd.DataFrame()
    pivot_display[index_col] = pivot.index.astype(str)

    for col in cols_sorted:
        pivot_display[col] = pivot[col].astype(float).round(2).values
        ct = col_totals[col]
        if ct and ct > 0:
            pct_vals = (pivot[col] / ct * 100).round(1).clip(lower=0, upper=100).fillna(0).astype(float).values
        else:
            pct_vals = [0.0] * len(pivot)
        pivot_display[f'{col} %'] = pct_vals

    pivot_display['TOTALE'] = pivot['TOTALE'].astype(float).round(2).values
    if grand_total and grand_total > 0:
        pivot_display['TOTALE %'] = (pivot['TOTALE'] / grand_total * 100).round(1).clip(lower=0, upper=100).fillna(0).astype(float).values
    else:
        pivot_display['TOTALE %'] = [0.0] * len(pivot)
    pivot_display['MEDIA'] = pivot['MEDIA'].astype(float).round(2).values

    if not pivot_display.empty:
        # Inizializza session_state per il checkbox se necessario
        if f"mostra_incidenze_pct_{sezione_key}" not in st.session_state:
            st.session_state[f"mostra_incidenze_pct_{sezione_key}"] = False
        
        # NOTA: non passare 'value=' quando si usa 'key=' con session_state già inizializzato
        # (causa warning e potenziali rerun loop → React error #185)
        mostra_pct = st.checkbox(
            "📊 Visualizza incidenze %",
            key=f"mostra_incidenze_pct_{sezione_key}"
        )

        if not mostra_pct:
            pct_cols = [c for c in pivot_display.columns if c.endswith(' %')]
            pivot_display = pivot_display.drop(columns=pct_cols)

        num_righe = len(pivot_display)
        altezza = max(num_righe * 35 + 50, 200)

        # FIX DIAGNOSTICO React #185 (Streamlit 1.54 + Glide Data Grid):
        # Usa st.dataframe SENZA column_config. Formattazione numerica sacrificata
        # per stabilità: i valori sono float arrotondati a 2 decimali.
        st.dataframe(
            pivot_display,
            hide_index=True,
            use_container_width=True,
            height=altezza
        )

        totale = pivot['TOTALE'].sum()
        media = totale / num_mesi if num_mesi > 0 else 0
        col_left, col_right = st.columns([5, 1])

        with col_left:
            st.markdown(f"""
            <div style="display:inline-block; background-color: #E3F2FD; padding: clamp(0.75rem, 1.5vw, 0.95rem) clamp(0.9rem, 2vw, 1.25rem); border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 20px; width: fit-content; max-width: 100%; box-sizing: border-box;">
                <p style="color: #1565C0; font-size: clamp(0.85rem, 1.4vw, 1rem); font-weight: bold; margin: 0; white-space: normal; overflow-wrap: anywhere; line-height: 1.4;">
                    📋 N. Righe: {num_righe:,} | 💰 Totale: € {totale:,.0f} | 📊 Media mensile: € {media:,.0f}
                </p>
            </div>
            """, unsafe_allow_html=True)

        with col_right:
            st.markdown(f"""
            <style>
            div.st-key-download_excel_{sezione_key} .stDownloadButton button {{
                background-color: #22c55e !important;
                color: white !important;
                border: none !important;
                border-radius: 8px !important;
                font-weight: 600 !important;
            }}
            div.st-key-download_excel_{sezione_key} .stDownloadButton button:hover {{
                background-color: #16a34a !important;
            }}
            </style>
            """, unsafe_allow_html=True)

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                pivot.reset_index().to_excel(writer, index=False, sheet_name=sheet_name)

            with st.container(key=f"download_excel_{sezione_key}"):
                st.download_button(
                    label="Excel",
                    data=excel_buffer.getvalue(),
                    file_name=f"{sezione_key}_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"btn_excel_{sezione_key}",
                    use_container_width=False
                )
    else:
        st.info("📊 Nessun dato da visualizzare per il periodo selezionato")
