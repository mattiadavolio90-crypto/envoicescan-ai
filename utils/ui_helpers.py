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


def _format_pivot_value(col_name: str, value):
    if pd.isna(value):
        return ''
    if col_name.endswith(' %') or col_name == 'TOTALE %':
        return f"{float(value):.1f}%"
    if col_name == 'MEDIA' or col_name == 'TOTALE' or col_name not in ('Categoria', 'Fornitore'):
        try:
            return f"€ {float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _render_static_table(df: pd.DataFrame, key: str):
    table_html = df.to_html(index=False, escape=True, classes=f"ohh-static-table ohh-static-table-{key}")
    html = (
        f"<style>"
        f".ohh-static-wrap-{key}{{overflow-x:auto;border:1px solid #dbe4f0;border-radius:10px;background:#ffffff;margin-bottom:1rem;}}"
        f".ohh-static-table-{key}{{width:100%;border-collapse:collapse;font-size:0.92rem;}}"
        f".ohh-static-table-{key} thead th{{position:sticky;top:0;background:#f7f9fc;color:#334155;padding:0.7rem 0.75rem;border-bottom:1px solid #dbe4f0;text-align:left;white-space:nowrap;}}"
        f".ohh-static-table-{key} tbody td{{padding:0.65rem 0.75rem;border-top:1px solid #eef2f7;white-space:nowrap;}}"
        f".ohh-static-table-{key} tbody tr:nth-child(even){{background:#fbfdff;}}"
        f"</style>"
        f"<div class=\"ohh-static-wrap-{key}\">{table_html}</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


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
    
    # Normalizza i tipi per evitare payload non serializzabili lato frontend.
    df_prep = df_source.copy()
    df_prep['Data_DT'] = pd.to_datetime(df_prep['Data_DT'], errors='coerce')
    df_prep['TotaleRiga'] = pd.to_numeric(df_prep['TotaleRiga'], errors='coerce')
    df_prep[index_col] = df_prep[index_col].astype(str).str.strip()
    df_prep.loc[df_prep[index_col].str.lower().isin({'', 'nan', 'none'}), index_col] = ''

    # Filtra righe con Data_DT o TotaleRiga nulli, e con index_col nullo/vuoto.
    righe_input = len(df_prep)
    df_prep = df_prep[
        df_prep['Data_DT'].notna()
        & df_prep['TotaleRiga'].notna()
        & (df_prep[index_col] != '')
    ].copy()
    righe_scartate = righe_input - len(df_prep)
    if righe_scartate > 0:
        logger.info(
            "[pivot:%s] Scartate %s righe non valide su %s",
            sezione_key,
            righe_scartate,
            righe_input,
        )
    if df_prep.empty:
        st.info("📭 Nessun dato valido dopo validazione delle colonne.")
        return

    # Formato mese per visualizzazione (solo nome, es. GENNAIO)
    df_prep['Mese'] = df_prep['Data_DT'].apply(
        lambda x: mesi_ita[x.month] if pd.notna(x) else ''
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

        mostra_pct = st.checkbox(
            "📊 Visualizza incidenze %",
            key=f"mostra_incidenze_pct_{sezione_key}"
        )

        # Droppa colonne % se checkbox OFF e resetta index
        if not mostra_pct:
            pct_cols = [c for c in pivot_display.columns if c.endswith(' %')]
            pivot_display = pivot_display.drop(columns=pct_cols)

        # Ordine colonne: TOTALE e MEDIA sempre come ultime due (utile anche per stile CSS)
        if mostra_pct:
            ordered_cols = [index_col]
            for col in cols_sorted:
                ordered_cols.append(col)
                pct_name = f'{col} %'
                if pct_name in pivot_display.columns:
                    ordered_cols.append(pct_name)
            if 'TOTALE %' in pivot_display.columns:
                ordered_cols.append('TOTALE %')
            if 'TOTALE' in pivot_display.columns:
                ordered_cols.append('TOTALE')
            if 'MEDIA' in pivot_display.columns:
                ordered_cols.append('MEDIA')
            pivot_display = pivot_display[[c for c in ordered_cols if c in pivot_display.columns]]

        pivot_display = pivot_display.reset_index(drop=True)

        # Sanitizzazione finale anti-React/Arrow: solo numerici finiti nelle colonne valore.
        for col in pivot_display.columns:
            if col == index_col:
                pivot_display[col] = pivot_display[col].astype(str).fillna('')
                continue
            col_numeric = pd.to_numeric(pivot_display[col], errors='coerce')
            col_numeric = col_numeric.replace([float('inf'), float('-inf')], 0).fillna(0.0)
            if col.endswith(' %'):
                pivot_display[col] = col_numeric.clip(lower=0, upper=100).round(1).astype(float)
            else:
                pivot_display[col] = col_numeric.round(2).astype(float)

        num_righe = len(pivot_display)
        altezza_dinamica = min(max(num_righe * 35 + 50, 320), 760)

        pivot_column_config = {
            index_col: st.column_config.TextColumn(index_col, width='medium')
        }
        for col in pivot_display.columns:
            if col == index_col:
                continue
            if col.endswith(' %'):
                pivot_column_config[col] = st.column_config.NumberColumn(col, format='%.1f%%', width='small')
            else:
                pivot_column_config[col] = st.column_config.NumberColumn(col, format='€ %.2f', width='small')

        try:
            st.dataframe(
                pivot_display,
                column_config=pivot_column_config,
                hide_index=True,
                use_container_width=True,
                height=altezza_dinamica,
            )
        except Exception as grid_error:
            logger.exception("[pivot:%s] Fallback tabella statica per errore grid: %s", sezione_key, grid_error)
            st.warning("⚠️ Visualizzazione semplificata attivata per questa tabella.")
            fallback_df = pivot_display.copy()
            for col in fallback_df.columns:
                fallback_df[col] = fallback_df[col].apply(lambda value: _format_pivot_value(col, value))
            _render_static_table(fallback_df, key=f"{sezione_key}_fallback")

        totale = pivot['TOTALE'].sum()
        media = totale / num_mesi if num_mesi > 0 else 0
        riepilogo_text = f"📋 N. Righe: {num_righe:,} | 💰 Totale: € {totale:,.0f} | 📊 Media mensile: € {media:,.0f}"

        # Export Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            pivot.reset_index().to_excel(writer, index=False, sheet_name=sheet_name)

        col_info, col_excel = st.columns([9, 1])
        with col_info:
            st.markdown(f"""
            <div style="background-color: #E3F2FD; padding: 0.6rem 1rem; border-radius: 8px; border: 2px solid #2196F3; width: fit-content;">
                <p style="color: #1565C0; font-size: 0.95rem; font-weight: bold; margin: 0; white-space: nowrap;">
                    {riepilogo_text}
                </p>
            </div>
            """, unsafe_allow_html=True)
        with col_excel:
            st.download_button(
                label="Excel",
                data=excel_buffer.getvalue(),
                file_name=f"{sezione_key}_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"btn_excel_{sezione_key}",
                use_container_width=True,
            )
    else:
        st.info("📊 Nessun dato da visualizzare per il periodo selezionato")
