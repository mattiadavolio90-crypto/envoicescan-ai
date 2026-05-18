"""
Modulo ui_helpers per OH YEAH! Hub.

Funzioni condivise per:
- Caricamento CSS/JS da file statici
- Rendering pivot table mensile (Categorie / Fornitori)
"""

import os
import io
import html as _html_mod
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
            return f"€ {float(value):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _render_styled_pivot_html(
    df: pd.DataFrame,
    index_col: str,
    total_row_label: str,
    sezione_key: str,
    altezza: int = 500,
) -> None:
    """
    Renderizza la pivot mensile come tabella HTML con gli stessi colori/stili
    del st.dataframe+Styler (usato per Categorie), senza passare per il grid
    React — evita l'errore #185 su dataset grandi come Fornitori.
    """
    cols = list(df.columns)

    def _fmt(col_name: str, value) -> str:
        if pd.isna(value) or str(value).strip() == '':
            return ''
        if col_name == index_col:
            return _html_mod.escape(str(value))
        if col_name.endswith(' %'):
            try:
                return f"{float(value):.1f}%"
            except (TypeError, ValueError):
                return _html_mod.escape(str(value))
        try:
            return f"€ {float(value):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return _html_mod.escape(str(value))

    def _td_cls(col_name: str) -> str:
        if col_name in ('TOTALE', 'TOTALE %'):
            return 'ohh-col-tot'
        if col_name == 'MEDIA':
            return 'ohh-col-med'
        return ''

    header = ''.join(f'<th>{_html_mod.escape(str(c))}</th>' for c in cols)
    rows_html = ''
    for _, row in df.iterrows():
        is_sum = str(row.get(index_col, '')).strip() == total_row_label
        tr_cls = ' class="ohh-row-sum"' if is_sum else ''
        cells = ''
        for col in cols:
            tc = _td_cls(col)
            tc_attr = f' class="{tc}"' if tc else ''
            cells += f'<td{tc_attr}>{_fmt(col, row[col])}</td>'
        rows_html += f'<tr{tr_cls}>{cells}</tr>'

    uid = sezione_key
    css = f"""
<style>
.ohh-pv-wrap-{uid}{{overflow-y:auto;overflow-x:auto;height:{altezza}px;border:1px solid #dbe4f0;
    border-radius:10px;background:#fff;margin-bottom:.75rem;}}
.ohh-pv-wrap-{uid} table{{width:100%;border-collapse:collapse;font-size:.86rem;
    font-family:"Source Sans Pro",sans-serif;}}
.ohh-pv-wrap-{uid} thead th{{position:sticky;top:0;z-index:2;background:#f7f9fc;
    color:#334155;padding:.55rem .65rem;border-bottom:2px solid #dbe4f0;
    text-align:right;white-space:nowrap;font-weight:700;}}
.ohh-pv-wrap-{uid} thead th:first-child{{text-align:left;}}
.ohh-pv-wrap-{uid} tbody td{{padding:.48rem .65rem;border-top:1px solid #eef2f7;
    white-space:nowrap;text-align:right;vertical-align:middle;}}
.ohh-pv-wrap-{uid} tbody td:first-child{{text-align:left;}}
.ohh-pv-wrap-{uid} tbody tr:nth-child(even){{background:#fbfdff;}}
.ohh-pv-wrap-{uid} td.ohh-col-tot{{background-color:#E3F2FD!important;
    color:#1565C0;font-weight:700;}}
.ohh-pv-wrap-{uid} td.ohh-col-med{{background-color:#FFF3CD!important;
    color:#856404;font-weight:700;}}
.ohh-pv-wrap-{uid} tr.ohh-row-sum td{{background-color:#F2F8FF!important;
    color:#0B3B91;font-weight:700;}}
.ohh-pv-wrap-{uid} tr.ohh-row-sum td:first-child{{background-color:#DCEEFF!important;
    color:#0B3B91;font-weight:900;}}
.ohh-pv-wrap-{uid} tr.ohh-row-sum td.ohh-col-tot{{background-color:#DBECFF!important;
    color:#0B3B91;font-weight:800;}}
.ohh-pv-wrap-{uid} tr.ohh-row-sum td.ohh-col-med{{background-color:#FFF1C9!important;
    color:#7A4E00;font-weight:800;}}
</style>"""

    table = (
        f'<div class="ohh-pv-wrap-{uid}">'
        f'<table><thead><tr>{header}</tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>'
    )
    st.markdown(css + table, unsafe_allow_html=True)


def _render_styled_pivot_html(
    df: pd.DataFrame,
    index_col: str,
    total_row_label: str,
    sezione_key: str,
    altezza: int = 500,
) -> None:
    """
    Renderizza la pivot mensile come tabella HTML con gli stessi colori/stili
    del st.dataframe+Styler (usato per Categorie), senza passare per il grid
    React — evita l'errore #185 su dataset grandi come Fornitori.
    """
    cols = list(df.columns)

    def _fmt(col_name: str, value) -> str:
        if pd.isna(value) or str(value).strip() == '':
            return ''
        if col_name == index_col:
            return _html_mod.escape(str(value))
        if col_name.endswith(' %'):
            try:
                return f"{float(value):.1f}%"
            except (TypeError, ValueError):
                return _html_mod.escape(str(value))
        try:
            return f"€\u00a0{float(value):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return _html_mod.escape(str(value))

    def _td_cls(col_name: str) -> str:
        if col_name in ('TOTALE', 'TOTALE %'):
            return 'ohh-col-tot'
        if col_name == 'MEDIA':
            return 'ohh-col-med'
        return ''

    header = ''.join(f'<th>{_html_mod.escape(str(c))}</th>' for c in cols)
    rows_html = ''
    for _, row in df.iterrows():
        is_sum = str(row.get(index_col, '')).strip() == total_row_label
        tr_cls = ' class="ohh-row-sum"' if is_sum else ''
        cells = ''
        for col in cols:
            tc = _td_cls(col)
            tc_attr = f' class="{tc}"' if tc else ''
            cells += f'<td{tc_attr}>{_fmt(col, row[col])}</td>'
        rows_html += f'<tr{tr_cls}>{cells}</tr>'

    uid = sezione_key
    css = (
        f'<style>'
        f'.ohh-pv-wrap-{uid}{{overflow:auto;max-height:{altezza}px;border:1px solid #dbe4f0;'
        f'border-radius:10px;background:#fff;margin-bottom:.75rem;}}'
        f'.ohh-pv-wrap-{uid} table{{width:100%;border-collapse:collapse;font-size:.86rem;'
        f'font-family:"Source Sans Pro",sans-serif;}}'
        f'.ohh-pv-wrap-{uid} thead th{{position:sticky;top:0;z-index:2;background:#f7f9fc;'
        f'color:#334155;padding:.55rem .65rem;border-bottom:2px solid #dbe4f0;'
        f'text-align:right;white-space:nowrap;font-weight:700;}}'
        f'.ohh-pv-wrap-{uid} thead th:first-child{{text-align:left;}}'
        f'.ohh-pv-wrap-{uid} tbody td{{padding:.48rem .65rem;border-top:1px solid #eef2f7;'
        f'white-space:nowrap;text-align:right;vertical-align:middle;}}'
        f'.ohh-pv-wrap-{uid} tbody td:first-child{{text-align:left;}}'
        f'.ohh-pv-wrap-{uid} tbody tr:nth-child(even){{background:#fbfdff;}}'
        f'.ohh-pv-wrap-{uid} td.ohh-col-tot{{background-color:#E3F2FD!important;'
        f'color:#1565C0;font-weight:700;}}'
        f'.ohh-pv-wrap-{uid} td.ohh-col-med{{background-color:#FFF3CD!important;'
        f'color:#856404;font-weight:700;}}'
        f'.ohh-pv-wrap-{uid} tr.ohh-row-sum td{{background-color:#F2F8FF!important;'
        f'color:#0B3B91;font-weight:700;border-top:3px solid #1D4ED8;'
        f'border-bottom:2px solid #1D4ED8;}}'
        f'.ohh-pv-wrap-{uid} tr.ohh-row-sum td:first-child{{background-color:#DCEEFF!important;'
        f'color:#0B3B91;font-weight:900;}}'
        f'.ohh-pv-wrap-{uid} tr.ohh-row-sum td.ohh-col-tot{{background-color:#DBECFF!important;'
        f'color:#0B3B91;font-weight:800;}}'
        f'.ohh-pv-wrap-{uid} tr.ohh-row-sum td.ohh-col-med{{background-color:#FFF1C9!important;'
        f'color:#7A4E00;font-weight:800;}}'
        f'</style>'
    )
    table = (
        f'<div class="ohh-pv-wrap-{uid}">'
        f'<table><thead><tr>{header}</tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>'
    )
    st.markdown(css + table, unsafe_allow_html=True)


def _render_static_table(df: pd.DataFrame, key: str):
    table_html = df.to_html(index=False, escape=True, classes=f"ohh-static-table ohh-static-table-{key}")
    html = (
        f"<style>"
        f".ohh-static-wrap-{key}{{overflow-x:auto;border:1px solid #dbe4f0;border-radius:10px;background:#ffffff;margin-bottom:1rem;}}"
        f".ohh-static-table-{key}{{width:100%;border-collapse:collapse;font-size:0.92rem;}}"
        f".ohh-static-table-{key} thead th{{position:sticky;top:0;background:#f7f9fc;color:#334155;padding:0.7rem 0.75rem;border-bottom:1px solid #dbe4f0;text-align:left;white-space:nowrap;font-weight:700;}}"
        f".ohh-static-table-{key} tbody td{{padding:0.65rem 0.75rem;border-top:1px solid #eef2f7;white-space:nowrap;}}"
        f".ohh-static-table-{key} tbody tr:nth-child(even){{background:#fbfdff;}}"
        f"</style>"
        f"<div class=\"ohh-static-wrap-{key}\">{table_html}</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _format_euro_migliaia(value):
    if pd.isna(value):
        return ''
    try:
        return f"€ {float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _format_percentuale(value):
    if pd.isna(value):
        return ''
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


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

    # Riga riepilogo finale: totale per ogni mese e totale complessivo.
    total_row_label = '∑ TOTALE MESE'
    total_row = {index_col: total_row_label}
    for col in cols_sorted:
        col_total_value = float(col_totals.get(col, 0.0) or 0.0)
        total_row[col] = round(col_total_value, 2)
        total_row[f'{col} %'] = 100.0 if col_total_value > 0 else 0.0
    total_row['TOTALE'] = round(float(grand_total or 0.0), 2)
    total_row['TOTALE %'] = 100.0 if (grand_total and grand_total > 0) else 0.0
    total_row['MEDIA'] = round(float((grand_total / num_mesi) if num_mesi > 0 else 0.0), 2)
    pivot_display = pd.concat([pivot_display, pd.DataFrame([total_row])], ignore_index=True)

    if not pivot_display.empty:
        st.markdown(
            (
                f"<h4 style='margin:0 0 0.45rem 0; color:#1e3a5f; "
                f"font-weight:800;'>📋 Tabella {sheet_name}</h4>"
            ),
            unsafe_allow_html=True,
        )

        def _evidenzia_colonne_riepilogo(_row):
            styles = []
            is_total_row = str(_row.get(index_col, '')).strip() == total_row_label
            for _col in pivot_display.columns:
                if is_total_row:
                    if _col == index_col:
                        styles.append('background-color: #DCEEFF; color: #0B3B91; font-weight: 900; border-top: 3px solid #1D4ED8; border-bottom: 2px solid #1D4ED8;')
                    elif _col == 'TOTALE':
                        styles.append('background-color: #DBECFF; color: #0B3B91; font-weight: 800; border-top: 3px solid #1D4ED8; border-bottom: 2px solid #1D4ED8;')
                    elif _col == 'MEDIA':
                        styles.append('background-color: #FFF1C9; color: #7A4E00; font-weight: 800; border-top: 3px solid #1D4ED8; border-bottom: 2px solid #1D4ED8;')
                    else:
                        styles.append('background-color: #F2F8FF; color: #0B3B91; font-weight: 700; border-top: 3px solid #1D4ED8; border-bottom: 2px solid #1D4ED8;')
                elif _col == 'TOTALE':
                    styles.append('background-color: #E3F2FD; color: #1565C0; font-weight: 700;')
                elif _col == 'MEDIA':
                    styles.append('background-color: #FFF3CD; color: #856404; font-weight: 700;')
                else:
                    styles.append('')
            return styles

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
                # FIX React #185: ProgressColumn + Styler causa "Maximum update depth exceeded"
                # su Streamlit 1.54 (Glide Data Grid bug). Usare NumberColumn senza format;
                # la formattazione '12.3%' è gestita dallo Styler sotto.
                pivot_column_config[col] = st.column_config.NumberColumn(col, width='small')
            else:
                # Nessun format= per evitare il bug sprintf con '€ %,.0f':
                # la formattazione visiva è gestita dallo Styler via _format_euro_migliaia.
                pivot_column_config[col] = st.column_config.NumberColumn(col, width='small')

        # Fornitori: usa tabella HTML stilizzata per evitare errore React #185
        # (Glide Data Grid va in loop con Styler su dataset grandi).
        # Categorie: usa st.dataframe con Styler (dataset più piccolo, funziona).
        # Usa sempre la tabella HTML stilizzata (stile uniforme per Fornitori e Categorie,
        # evita anche il bug React #185 su Glide Data Grid con Styler).
        _render_styled_pivot_html(pivot_display, index_col, total_row_label, sezione_key, altezza_dinamica)

        totale = pivot['TOTALE'].sum()
        media = totale / num_mesi if num_mesi > 0 else 0
        riepilogo_text = f"📋 N. Righe: {num_righe:,} | 💰 Totale: € {totale:,.0f} | 📊 Media mensile: € {media:,.0f}"

        # Export Excel
        excel_buffer = io.BytesIO()
        excel_export = pivot.reset_index().copy()
        total_export_row = {index_col: total_row_label}
        for col in cols_sorted:
            total_export_row[col] = round(float(col_totals.get(col, 0.0) or 0.0), 2)
        total_export_row['TOTALE'] = round(float(grand_total or 0.0), 2)
        total_export_row['MEDIA'] = round(float((grand_total / num_mesi) if num_mesi > 0 else 0.0), 2)
        excel_export = pd.concat([excel_export, pd.DataFrame([total_export_row])], ignore_index=True)
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            excel_export.to_excel(writer, index=False, sheet_name=sheet_name)

        col_info, col_excel = st.columns([9.5, 0.5], vertical_alignment='top')
        with col_info:
            st.markdown(f"""
            <div style="background-color: #E3F2FD; padding: 0.5rem 0.8rem; border-radius: 8px; border: 2px solid #2196F3; display: inline-block; width: fit-content;">
                <p style="color: #1565C0; font-size: 0.88rem; font-weight: bold; margin: 0; white-space: nowrap;">
                    {riepilogo_text}
                </p>
            </div>
            """, unsafe_allow_html=True)
        with col_excel:
            st.download_button(
                label="XLS",
                data=excel_buffer.getvalue(),
                file_name=f"{sezione_key}_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"btn_excel_{sezione_key}",
                use_container_width=False,
            )
    else:
        st.info("📊 Nessun dato da visualizzare per il periodo selezionato")
