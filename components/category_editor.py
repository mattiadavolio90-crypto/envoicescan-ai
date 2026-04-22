"""Sezione Dettaglio Articoli - Data editor per la modifica delle categorie."""

import streamlit as st
import pandas as pd
import io
import time
import logging
from collections import defaultdict

from config.constants import CATEGORIE_SPESE_GENERALI, TRUNCATE_DESC_LOG, TRUNCATE_DESC_QUERY
from utils.text_utils import normalizza_stringa, estrai_nome_categoria, escape_ilike as _escape_ilike
from utils.formatters import calcola_prezzo_standard_intelligente, carica_categorie_da_db, get_nome_base_file
from utils.ristorante_helper import add_ristorante_filter
from utils.ui_helpers import load_css
from services.ai_service import invalida_cache_memoria, salva_correzione_in_memoria_globale, salva_correzione_in_memoria_locale


logger = logging.getLogger("fci_app")

# ─── Emoji per categoria merceologica (statico, no query DB) ─────────────────
# Usato per la colonna CatIcon nel dettaglio articoli.
CATEGORIA_ICONS: dict[str, str] = {
    # Food
    "CARNE":                   "🥩",
    "PESCE":                   "🐠",
    "LATTICINI":               "🧀",
    "SALUMI":                  "🥓",
    "UOVA":                    "🥚",
    "SCATOLAME E CONSERVE":    "🥫",
    "OLIO E CONDIMENTI":       "🫙",
    "SECCO":                   "🌾",
    "VERDURE":                 "🥦",
    "FRUTTA":                  "🍓",
    "SALSE E CREME":           "🥣",
    "PRODOTTI DA FORNO":       "🍞",
    "SPEZIE E AROMI":          "🌿",
    "PASTICCERIA":             "🍰",
    "GELATI":                  "🍦",
    "SUSHI VARIE":             "🍣",
    "SHOP":                    "🛍️",
    # Bevande
    "ACQUA":                   "💧",
    "BEVANDE":                 "🥤",
    "CAFFE E THE":             "☕",
    "BIRRE":                   "🍺",
    "VINI":                    "🍷",
    "DISTILLATI":              "🥃",
    "AMARI/LIQUORI":           "🍸",
    "VARIE BAR":               "🍹",
    # Materiali
    "MATERIALE DI CONSUMO":    "📦",
    # Spese operative
    "SERVIZI E CONSULENZE":    "📋",
    "UTENZE E LOCALI":         "🔌",
    "MANUTENZIONE E ATTREZZATURE": "🔧",
    # Fallback
    "Da Classificare":         "❓",
}


def _compute_novita_badge(created_at_value, login_reference_value) -> str:
    """Restituisce il badge Novità se la fattura è arrivata dopo l'ultimo login utile."""
    created_ts = pd.to_datetime(created_at_value, utc=True, errors='coerce')
    login_ts = pd.to_datetime(login_reference_value, utc=True, errors='coerce')
    if pd.isna(created_ts) or pd.isna(login_ts):
        return ''
    return '🆕 Nuova' if created_ts > login_ts else ''


def _resolve_novita_badge(file_origine_value, created_at_value, login_reference_value, recent_file_origini=None) -> str:
    """Mostra il badge sui file recenti (manuali o Invoicetronic) anche se cambia l'estensione/nome base."""
    recent_files = set()
    for fname in (recent_file_origini or set()):
        fname_str = str(fname).strip()
        if not fname_str:
            continue
        recent_files.add(fname_str)
        recent_files.add(get_nome_base_file(fname_str))

    current_file = str(file_origine_value or '').strip()
    current_candidates = {current_file}
    if current_file:
        current_candidates.add(get_nome_base_file(current_file))

    if recent_files:
        return '🆕 Nuova' if recent_files.intersection(current_candidates) else ''

    return _compute_novita_badge(created_at_value, login_reference_value)


def _sort_detail_rows(df_source: pd.DataFrame) -> pd.DataFrame:
    """Ordina la vista per arrivo più recente, con fallback su data documento."""
    if df_source is None or df_source.empty:
        return df_source.copy() if isinstance(df_source, pd.DataFrame) else pd.DataFrame()

    df_sorted = df_source.copy()
    sort_cols = []
    ascending = []

    if 'CreatedAt' in df_sorted.columns:
        df_sorted['_sort_created_at'] = pd.to_datetime(df_sorted['CreatedAt'], utc=True, errors='coerce')
        sort_cols.append('_sort_created_at')
        ascending.append(False)

    if 'DataDocumento' in df_sorted.columns:
        df_sorted['_sort_data_documento'] = pd.to_datetime(df_sorted['DataDocumento'], errors='coerce')
        sort_cols.append('_sort_data_documento')
        ascending.append(False)

    if sort_cols:
        df_sorted = df_sorted.sort_values(by=sort_cols, ascending=ascending, na_position='last')

    drop_cols = [c for c in ['_sort_created_at', '_sort_data_documento'] if c in df_sorted.columns]
    if drop_cols:
        df_sorted = df_sorted.drop(columns=drop_cols)

    return df_sorted.reset_index(drop=True)


def _render_spese_generali_fallback_editor(df_editor_paginato: pd.DataFrame, categorie_disponibili: list[str], editor_key: str) -> pd.DataFrame:
    """Editor stabile senza data_editor per aggirare React #185 su Streamlit 1.54."""
    edited_df = df_editor_paginato.copy().reset_index(drop=True)

    preview_cols = [
        col for col in ['DataDocumento', 'Descrizione', 'Fornitore', 'Quantita', 'TotaleRiga', 'Categoria']
        if col in edited_df.columns
    ]
    preview_df = edited_df[preview_cols].copy()
    if 'TotaleRiga' in preview_df.columns:
        preview_df['TotaleRiga'] = preview_df['TotaleRiga'].apply(lambda value: f"€ {float(value):,.2f}" if pd.notna(value) else '')
    if 'Quantita' in preview_df.columns:
        preview_df['Quantita'] = preview_df['Quantita'].apply(lambda value: f"{float(value):,.2f}" if pd.notna(value) else '')
    table_html = preview_df.to_html(index=False, escape=True, classes="ohh-detail-stable-table")
    st.markdown(
        """
<style>
.ohh-detail-stable-wrap {
    overflow-x: auto;
    border: 1px solid #dbe4f0;
    border-radius: 10px;
    background: #ffffff;
    margin-bottom: 1rem;
}
.ohh-detail-stable-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
}
.ohh-detail-stable-table thead th {
    background: #f7f9fc;
    color: #334155;
    padding: 0.7rem 0.75rem;
    border-bottom: 1px solid #dbe4f0;
    text-align: left;
    white-space: nowrap;
}
.ohh-detail-stable-table tbody td {
    padding: 0.65rem 0.75rem;
    border-top: 1px solid #eef2f7;
    white-space: nowrap;
}
</style>
""",
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="ohh-detail-stable-wrap">{table_html}</div>', unsafe_allow_html=True)
    st.caption("Modalità stabile: modifica categoria tramite selettori sotto la tabella.")

    for idx in edited_df.index:
        descrizione = str(edited_df.at[idx, 'Descrizione']) if 'Descrizione' in edited_df.columns else f'Riga {idx + 1}'
        fornitore = str(edited_df.at[idx, 'Fornitore']) if 'Fornitore' in edited_df.columns else ''
        label = f"{idx + 1}. {descrizione[:80]}"
        if fornitore:
            label = f"{label} | {fornitore[:40]}"

        current_value = str(edited_df.at[idx, 'Categoria']).strip() if 'Categoria' in edited_df.columns else 'Da Classificare'
        if current_value not in categorie_disponibili:
            current_value = 'Da Classificare'
        edited_df.at[idx, 'Categoria'] = st.selectbox(
            label,
            options=categorie_disponibili,
            index=categorie_disponibili.index(current_value),
            key=f"{editor_key}_fallback_categoria_{idx}",
        )

    return edited_df


def render_category_editor(df_completo_filtrato, supabase):
    """Renderizza la sezione Dettaglio Articoli con data editor e logica di salvataggio."""
    # Placeholder se dataset mancanti/vuoti
    if df_completo_filtrato is None or df_completo_filtrato.empty:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")
        st.stop()

    
    # 📦 SEZIONE DETTAGLIO ARTICOLI
    
    # ===== FILTRO TIPO PRODOTTI =====
    with st.container(key="category_editor_top_filters"):
        col_tipo, col_search_type, col_search, col_save = st.columns(
            [2, 2, 3, 2],
            vertical_alignment="bottom"
        )

        with col_tipo:
            tipo_filtro = st.selectbox(
                "📦 Tipo Prodotti:",
                options=["Food & Beverage", "Spese Generali", "Tutti"],
                key="tipo_filtro_prodotti"
            )

        with col_search_type:
            search_type = st.selectbox(
                "🔍 Cerca per:",
                options=["Prodotto", "Categoria", "Fornitore"],
                key="search_type"
            )

        with col_search:
            if search_type == "Prodotto":
                search_term = st.text_input(
                    "🔍 Cerca nella descrizione:",
                    placeholder="Es: pollo, salmone, caffè...",
                    key="search_prodotto_text"
                )
            elif search_type == "Categoria":
                # Lista categorie disponibili filtrate per tipo_filtro
                if tipo_filtro == "Food & Beverage":
                    _df_opt = df_completo_filtrato[~df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)]
                elif tipo_filtro == "Spese Generali":
                    _df_opt = df_completo_filtrato[df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)]
                else:
                    _df_opt = df_completo_filtrato
                _cat_opts = ["— Tutte le categorie —"] + sorted(_df_opt['Categoria'].dropna().unique().tolist())
                _cat_sel = st.selectbox("🔍 Cerca per categoria:", options=_cat_opts, key="search_prodotto_cat")
                search_term = "" if _cat_sel == "— Tutte le categorie —" else _cat_sel
            else:  # Fornitore
                # Lista fornitori disponibili filtrati per tipo_filtro
                if tipo_filtro == "Food & Beverage":
                    _df_opt = df_completo_filtrato[~df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)]
                elif tipo_filtro == "Spese Generali":
                    _df_opt = df_completo_filtrato[df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)]
                else:
                    _df_opt = df_completo_filtrato
                _forn_opts = ["— Tutti i fornitori —"] + sorted(_df_opt['Fornitore'].dropna().unique().tolist())
                _forn_sel = st.selectbox("🔍 Cerca per fornitore:", options=_forn_opts, key="search_prodotto_forn")
                search_term = "" if _forn_sel == "— Tutti i fornitori —" else _forn_sel

        with col_save:
            salva_modifiche = st.button(
                "💾 Salva Modifiche Categorie",
                type="primary",
                use_container_width=True,
                key="salva_btn"
            )
    
    # ✅ FILTRO DINAMICO IN BASE ALLA SELEZIONE - USA DATI FILTRATI PER PERIODO
    # NOTA: Filtriamo SOLO per categoria, NON per fornitore!
    # - MATERIALE DI CONSUMO rientra ora nelle Spese Generali
    # - Le Spese Generali sono 4 categorie logiche
    if tipo_filtro == "Food & Beverage":
        # F&B = tutto ciò che NON appartiene a Spese Generali
        df_base = df_completo_filtrato[
            ~df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
        ].copy()
    elif tipo_filtro == "Spese Generali":
        # Solo le categorie spese generali definite in constants.py
        df_base = df_completo_filtrato[
            df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
        ].copy()
    else:  # "Tutti"
        # Tutti i prodotti senza filtri
        df_base = df_completo_filtrato.copy()
    
    # Applica struttura colonne nell'ordine corretto (allineato con vista aggregata)
    # Ordine: File, NumeroRiga, Data, Descrizione, Categoria, Fornitore, Quantita, Totale, Prezzo, UM, IVA
    cols_base = ['FileOrigine', 'NumeroRiga', 'DataDocumento', 'Descrizione', 'Categoria', 
                'Fornitore', 'Quantita', 'TotaleRiga', 'PrezzoUnitario', 'UnitaMisura', 'IVAPercentuale']
    
    # Aggiungi prezzo_standard se esiste nel database
    if 'PrezzoStandard' in df_base.columns:
        cols_base.append('PrezzoStandard')
    if 'CreatedAt' in df_base.columns:
        cols_base.append('CreatedAt')
    
    df_editor = df_base[cols_base].copy()
    
    # ⭐ COLONNA NOVITÀ - badge UI basato su CreatedAt rispetto all'ultimo login utile
    _user_data = st.session_state.get('user_data', {}) or {}
    _current_access_key = '_current_access_started_at'
    if _current_access_key not in st.session_state:
        st.session_state[_current_access_key] = _user_data.get('login_at') or pd.Timestamp.utcnow().isoformat()

    _novita_reference = (
        _user_data.get('last_login_precedente')
        or st.session_state.get('last_login_precedente')
        or st.session_state.get(_current_access_key)
    )

    _recent_file_origini = set()
    _recent_file_origini.update(
        str(fname).strip()
        for fname in (st.session_state.get('auto_received_file_origini') or set())
        if str(fname).strip()
    )
    _recent_file_origini.update(
        str(fname).strip()
        for fname in ((st.session_state.get('last_upload_notification_context') or {}).get('successful_files') or [])
        if str(fname).strip()
    )
    _recent_file_origini.update(
        str(fname).strip()
        for fname in (st.session_state.get('just_uploaded_files') or set())
        if str(fname).strip()
    )

    if 'CreatedAt' in df_editor.columns:
        if 'FileOrigine' in df_editor.columns:
            df_editor['Novità'] = df_editor.apply(
                lambda row: _resolve_novita_badge(
                    row.get('FileOrigine'),
                    row.get('CreatedAt'),
                    _novita_reference,
                    _recent_file_origini,
                ),
                axis=1,
            )
        else:
            df_editor['Novità'] = df_editor['CreatedAt'].apply(
                lambda value: _compute_novita_badge(value, _novita_reference)
            )
    else:
        df_editor['Novità'] = ''
    
    # 🧪 TEST AGGREGAZIONE (diagnostico - zero impatto UI)
    if 'Descrizione' in df_editor.columns:
        df_test_agg = df_editor.groupby('Descrizione').agg({
            'Categoria': 'first',
            'Quantita': 'sum',
            'TotaleRiga': 'sum'
        })
        logger.info(f"📊 TEST Aggregazione: {len(df_editor)} righe → {len(df_test_agg)} prodotti unici")
    
    # 🔧 CONVERTI pd.NA/vuoti in "Da Classificare" PRIMA di aggiungere icona AI
    # (Così la condizione per l'icona può trovare categorie valide)
    # SelectboxColumn ora include "Da Classificare" come opzione valida
    # L'AI li categorizza correttamente quando si usa "AVVIA AI PER CATEGORIZZARE"
    if 'Categoria' in df_editor.columns:
        # Converti pd.NA, None, stringhe vuote in "Da Classificare"
        # NON toccare "SECCO" perché è una categoria valida (pasta, riso, farina)
        
        vuote_prima = df_editor['Categoria'].apply(lambda x: pd.isna(x) or x is None or str(x).strip() == '').sum()
        
        df_editor['Categoria'] = df_editor['Categoria'].apply(
            lambda x: 'Da Classificare' if pd.isna(x) or x is None or str(x).strip() == '' else x
        )
        
        da_class_dopo = (df_editor['Categoria'] == 'Da Classificare').sum()
        
        if vuote_prima > 0 or da_class_dopo > 0:
            logger.info(f"📋 CATEGORIA: {vuote_prima} vuote → {da_class_dopo} 'Da Classificare'")
    
    # NOTE: Icone AI 🧠 disabilitate (causavano mismatch dropdown Streamlit)
    
    # Inizializza colonna prezzo_standard se non esiste
    if 'PrezzoStandard' not in df_editor.columns:
        df_editor['PrezzoStandard'] = None


    if search_term:
        if search_type == "Prodotto":
            mask = df_editor['Descrizione'].str.upper().str.contains(search_term.upper(), na=False, regex=False)
            _n = mask.sum(); st.info(f"🔍 {'Trovata' if _n == 1 else 'Trovate'} {_n} {'riga' if _n == 1 else 'righe'} con '{search_term}' nella descrizione")
        elif search_type == "Categoria":
            mask = df_editor['Categoria'].str.upper().str.contains(search_term.upper(), na=False, regex=False)
            _n = mask.sum(); st.info(f"🔍 {'Trovata' if _n == 1 else 'Trovate'} {_n} {'riga' if _n == 1 else 'righe'} nella categoria '{search_term}'")
        else:
            mask = df_editor['Fornitore'].str.upper().str.contains(search_term.upper(), na=False, regex=False)
            _n = mask.sum(); st.info(f"🔍 {'Trovata' if _n == 1 else 'Trovate'} {_n} {'riga' if _n == 1 else 'righe'} del fornitore '{search_term}'")
        
        df_editor = df_editor[mask]
    
    # ===== CALCOLO INTELLIGENTE PREZZO STANDARDIZZATO (VETTORIZZATO) =====
    
    # Calcola prezzo_standard solo dove manca (evita loop Python row-by-row)
    mask_mancante = (
        df_editor['PrezzoStandard'].isna() 
        | (df_editor['PrezzoStandard'] <= 0)
    )
    if mask_mancante.any():
        idx_mancanti = df_editor.index[mask_mancante]
        prezzi_calcolati = df_editor.loc[idx_mancanti].apply(
            lambda row: calcola_prezzo_standard_intelligente(
                descrizione=row.get('Descrizione'),
                um=row.get('UnitaMisura'),
                prezzo_unitario=row.get('PrezzoUnitario')
            ), axis=1
        )
        # Applica solo dove il calcolo ha prodotto un risultato
        validi = prezzi_calcolati.dropna()
        if not validi.empty:
            df_editor.loc[validi.index, 'PrezzoStandard'] = validi
    
    # ===== FINE CALCOLO =====

    # Ordinamento default: fatture/righe arrivate più recentemente in alto
    df_editor = _sort_detail_rows(df_editor)

    num_righe = len(df_editor)
    
    # Avviso salvataggio modifiche (dopo filtri)
    st.markdown("""
<div style='padding: 8px 14px; font-size: 0.88rem; color: #9a3412; font-weight: 500; text-align: left; margin-bottom: 12px;'>
    ⚠️ <strong>ATTENZIONE:</strong> Se hai modificato dati nella tabella, <strong>clicca SALVA</strong> prima di cambiare filtro, altrimenti le modifiche andranno perse!
</div>
""", unsafe_allow_html=True)
    
    # ============================================================
    # 📦 TOGGLE VISTA / FILTRO NOVITÀ
    # ============================================================
    with st.container(key="category_editor_toggle_row"):
        col_flag_group, col_flag_new, _ = st.columns(
            [2.6, 2.4, 5.0],
            vertical_alignment="center"
        )
        with col_flag_group:
            vista_aggregata = st.checkbox(
                "📦 Raggruppa prodotti unici",
                value=True,
                key="checkbox_raggruppa_prodotti"
            )
        with col_flag_new:
            filtra_nuovi = st.checkbox(
                "🆕 Filtra nuovi inserimenti",
                value=False,
                key="checkbox_filtra_nuovi_inserimenti"
            )

    if filtra_nuovi and 'Novità' in df_editor.columns:
        df_editor = df_editor[df_editor['Novità'] == '🆕 Nuova'].copy()

    df_editor_paginato = df_editor.copy()  # fallback sicuro (sovrascritto sotto se vista_aggregata)

    if vista_aggregata:
        # Prepara dizionario aggregazione (colonne sempre presenti)
        agg_dict = {
            'Categoria': 'first',
            'Fornitore': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],
            'Quantita': 'sum',
            'TotaleRiga': 'sum',
            'PrezzoUnitario': 'mean',
            'DataDocumento': 'max',
            'FileOrigine': 'nunique',
            'UnitaMisura': 'first',
            'IVAPercentuale': 'first'
        }
        
        # ✅ Aggiungi colonne opzionali solo se presenti
        if 'Novità' in df_editor.columns:
            agg_dict['Novità'] = 'first'
        if 'CreatedAt' in df_editor.columns:
            agg_dict['CreatedAt'] = 'max'
        if 'PrezzoStandard' in df_editor.columns:
            agg_dict['PrezzoStandard'] = 'mean'
        
        # Esegui aggregazione con conteggio righe
        df_editor_agg = df_editor.groupby('Descrizione', as_index=False).agg(agg_dict)
        
        # Aggiungi colonna N.Righe (numero righe aggregate per ogni prodotto)
        num_righe_per_prodotto = df_editor.groupby('Descrizione').size()
        df_editor_agg['NumRighe'] = df_editor_agg['Descrizione'].map(num_righe_per_prodotto)
        
        # Rinomina FileOrigine → NumFatture
        if 'FileOrigine' in df_editor_agg.columns:
            df_editor_agg.rename(columns={'FileOrigine': 'NumFatture'}, inplace=True)
        
        # Riordina colonne per allinearle con vista normale
        # Ordine: NumFatture, NumRighe, Data, Descrizione, Novità, Categoria, Fornitore, Quantita, Totale, Prezzo, UM, IVA
        cols_order = ['NumFatture', 'NumRighe', 'DataDocumento', 'Descrizione', 'Novità', 'Categoria', 
                     'Fornitore', 'Quantita', 'TotaleRiga', 'PrezzoUnitario', 'UnitaMisura', 'IVAPercentuale']
        
        # Aggiungi PrezzoStandard se presente
        if 'PrezzoStandard' in df_editor_agg.columns:
            cols_order.append('PrezzoStandard')
        
        # Mantieni solo le colonne effettivamente presenti nel dataframe
        cols_final = [c for c in cols_order if c in df_editor_agg.columns]
        df_editor_agg = df_editor_agg[cols_final]
        
        # Usa vista aggregata
        df_editor_paginato = _sort_detail_rows(df_editor_agg)
    else:
        df_editor_paginato = _sort_detail_rows(df_editor.copy())
    
    # Calcola prodotti unici (descrizioni distinte)
    num_prodotti_unici = df_editor['Descrizione'].nunique()
    
    st.markdown(f"""
    <div style="background-color: #E8F5E9; padding: 12px 15px; border-radius: 8px; border-left: 4px solid #4CAF50; margin-bottom: 15px;">
        <p style="margin: 0; font-size: clamp(0.85rem, 1.2vw, 0.95rem); color: #2E7D32; font-weight: 500; line-height: 1.4; overflow-wrap: anywhere;">
            📄 <strong>Totale: {num_righe:,} {'riga' if num_righe == 1 else 'righe'}</strong> • 🏷️ <strong>{num_prodotti_unici:,} prodotti unici</strong>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Altezza dinamica per tabella (massimo 800px con scroll)
    altezza_dinamica = min(max(len(df_editor_paginato) * 35 + 50, 400), 800)

    # ===== CARICA CATEGORIE DINAMICHE =====
    categorie_disponibili = carica_categorie_da_db(supabase_client=supabase)
    
    # Rimuovi TUTTI i valori non validi (None, vuoti, solo spazi)
    categorie_disponibili = [
        cat for cat in categorie_disponibili 
        if cat is not None and str(cat).strip() != '' and cat != 'Da Classificare'
    ]
    
    # 🚫 RIMUOVI "NOTE E DICITURE" - Categoria riservata SOLO per Admin Panel (Review Righe Zero)
    categorie_disponibili = [
        cat for cat in categorie_disponibili 
        if 'NOTE E DICITURE' not in cat.upper() and 'DICITURE' not in cat.upper()
    ]
    
    # Rimuovi duplicati mantenendo l'ordine
    categorie_temp = []
    for cat in categorie_disponibili:
        if cat not in categorie_temp:
            categorie_temp.append(cat)
    categorie_disponibili = categorie_temp
    
    # 🔄 MIGRAZIONE NOMI: Uniforma vecchio nome 'CONSERVE' al nuovo 'SCATOLAME E CONSERVE'
    categorie_disponibili = [
        ('SCATOLAME E CONSERVE' if str(cat).strip().upper() == 'CONSERVE' else cat)
        for cat in categorie_disponibili
    ]
    # 🔄 MIGRAZIONE NOMI: Uniforma vecchio nome 'CAFFÈ' / 'CAFFÈ E THE' al nuovo 'CAFFE E THE'
    categorie_disponibili = [
        ('CAFFE E THE' if str(cat).strip().upper() in ['CAFFÈ', 'CAFFE', 'CAFFÈ E THE'] else cat)
        for cat in categorie_disponibili
    ]
    
    # ✅ ORDINE ALFABETICO: Prima F&B, poi Spese Generali
    # Separa categorie F&B da spese generali (usa la costante importata)
    categorie_fb = [cat for cat in categorie_disponibili if cat not in CATEGORIE_SPESE_GENERALI]
    categorie_spese = [cat for cat in categorie_disponibili if cat in CATEGORIE_SPESE_GENERALI]
    
    # Ordina alfabeticamente entrambe le liste
    categorie_fb.sort()
    categorie_spese.sort()
    
    # Combina: prima F&B, poi spese generali
    categorie_disponibili = categorie_fb + categorie_spese
    
    # ✅ Aggiungi "Da Classificare" come prima opzione (per prodotti non ancora categorizzati)
    categorie_disponibili = ["Da Classificare"] + categorie_disponibili
    
    logger.info(f"📋 Categorie disponibili: {len(categorie_disponibili)} (1 placeholder + {len(categorie_fb)} F&B + {len(categorie_spese)} spese)")
    
    # 🔧 FIX CELLE BIANCHE ULTRA-AGGRESSIVO (Streamlit bug workaround)
    # Se una cella ha un valore NON nelle opzioni, Streamlit la mostra VUOTA
    # FORZA che ogni categoria nel DataFrame sia nelle opzioni disponibili
    categorie_valide_set = set(categorie_disponibili)
    
    def valida_categoria(cat):
        """Assicura che categoria sia nelle opzioni disponibili o 'Da Classificare' se vuota"""
        if pd.isna(cat) or cat is None or str(cat).strip() == '':
            return 'Da Classificare'  # Mostra testo invece di cella vuota
        cat_str = str(cat).strip()
        if cat_str == 'Da Classificare':
            return 'Da Classificare'  # Mantieni esplicito
        if cat_str not in categorie_valide_set:
            logger.warning(f"⚠️ Categoria '{cat_str}' non nelle opzioni! → 'Da Classificare'")
            return 'Da Classificare'  # Categoria non valida = da classificare
        return cat_str
    
    # Applica validazione a TUTTE le categorie
    df_editor['Categoria'] = df_editor['Categoria'].apply(valida_categoria)
    
    # FIX: applica la stessa validazione anche a df_editor_paginato (già assegnato sopra come copia)
    if 'Categoria' in df_editor_paginato.columns:
        df_editor_paginato['Categoria'] = (
            df_editor_paginato['Categoria'].apply(valida_categoria)
        )
    
    # Log finale validazione
    vuote_count = df_editor['Categoria'].isna().sum()
    if vuote_count > 0:
        logger.warning(f"⚠️ VALIDAZIONE: {vuote_count} celle vuote (non categorizzate)")
    
    # ✅ Le categorie vengono normalizzate automaticamente al caricamento
    # Migrazione vecchi nomi → nuovi nomi avviene in carica_e_prepara_dataframe()
    
    # 🚫 RIMUOVI colonne LISTINO dalla visualizzazione
    cols_to_drop = [c for c in ['PrezzoStandard', 'Listino', 'LISTINO', 'CreatedAt'] if c in df_editor_paginato.columns]
    if cols_to_drop:
        df_editor_paginato = df_editor_paginato.drop(columns=cols_to_drop)

    # ── Colonna CatIcon: emoji categoria per riga (read-only, statica) ────────
    # Non usa SelectboxColumn → nessun rischio blank-cell.
    for _target_df in [df_editor, df_editor_paginato]:
        if 'Categoria' in _target_df.columns:
            _target_df['CatIcon'] = _target_df['Categoria'].apply(
                lambda c: CATEGORIA_ICONS.get(str(c).strip(), '🏷️')
            )

    # Riordina: metti CatIcon subito prima di Categoria nel df da visualizzare
    if 'CatIcon' in df_editor_paginato.columns and 'Categoria' in df_editor_paginato.columns:
        _cols = list(df_editor_paginato.columns)
        _cols.remove('CatIcon')
        _cols.insert(_cols.index('Categoria'), 'CatIcon')
        df_editor_paginato = df_editor_paginato[_cols]

    # Configurazione colonne (ordine allineato tra vista normale e aggregata)
    # Niente tooltip hover sui titoli: devono restare facili da cliccare per l'ordinamento.
    column_config_dict = {
        "FileOrigine": st.column_config.TextColumn("📄 File", disabled=True),
        "NumeroRiga": st.column_config.NumberColumn("🔢 N.Riga", disabled=True, width="small"),
        "DataDocumento": st.column_config.TextColumn("🗓️ Data", disabled=True),
        "Descrizione": st.column_config.TextColumn("📝 Descrizione", disabled=True),
        "CatIcon": st.column_config.TextColumn(
            "🏷️",
            disabled=True,
            width="small",
        ),
        "Categoria": st.column_config.SelectboxColumn(
            "Categoria",
            width="medium",
            options=categorie_disponibili,
            required=True
        ),
        "Fornitore": st.column_config.TextColumn("🏭 Fornitore", disabled=True),
        "Quantita": st.column_config.NumberColumn("📦 Q.tà", disabled=True),
        "TotaleRiga": st.column_config.NumberColumn("💶 Totale (€)", format="€ %.2f", disabled=True),
        "PrezzoUnitario": st.column_config.NumberColumn("💰 Prezzo Unit.", format="€ %.2f", disabled=True),
        "UnitaMisura": st.column_config.TextColumn("📏 U.M.", disabled=True, width="small"),
        "IVAPercentuale": st.column_config.NumberColumn(
            "🧾 IVA %",
            format="%.0f%%",
            disabled=True,
            width="small"
        ),
        "Novità": st.column_config.TextColumn(
            "🆕 Novità",
            disabled=True,
            width="small"
        )
    }
    
    # ============================================================
    # CONFIGURAZIONE COLONNE PER VISTA AGGREGATA
    # ============================================================
    if vista_aggregata:
        # Colonna NumFatture (solo in aggregata)
        if 'NumFatture' in df_editor_paginato.columns:
            column_config_dict["NumFatture"] = st.column_config.NumberColumn(
                "📄 N.Fatt",
                disabled=True,
                width="small"
            )
        
        # Colonna NumRighe (solo in aggregata)
        if 'NumRighe' in df_editor_paginato.columns:
            column_config_dict["NumRighe"] = st.column_config.NumberColumn(
                "📊 N.Righe",
                disabled=True,
                width="small"
            )
        
        # Adatta etichette colonne esistenti
        column_config_dict["Quantita"] = st.column_config.NumberColumn(
            "📦 Q.tà TOT",
            disabled=True
        )
        
        column_config_dict["PrezzoUnitario"] = st.column_config.NumberColumn(
            "💰 Prezzo MEDIO",
            format="€ %.2f",
            disabled=True
        )
        
        column_config_dict["TotaleRiga"] = st.column_config.NumberColumn(
            "💶 € TOTALE",
            format="€ %.2f",
            disabled=True
        )
    
    # ⭐ Key dinamica: cambia dopo ogni salvataggio per forzare refresh widget
    # (evita che Streamlit cache il vecchio stato del data editor)
    # FIX: include anche tipo_filtro nella key per evitare React #185 quando
    # si cambia filtro (edited_rows dal vecchio DF vengono riapplicati al nuovo
    # DF più corto causando "Maximum update depth exceeded").
    _editor_version = st.session_state.get('editor_refresh_counter', 0)
    _filtro_slug = (tipo_filtro or "tutti").lower().replace(" ", "_").replace("&", "and")
    _editor_key = f"editor_dati_v{_editor_version}_{_filtro_slug}"
    use_stable_fallback_editor = tipo_filtro == "Spese Generali"

    if use_stable_fallback_editor:
        st.warning("⚠️ Modalità editor stabile attiva per evitare un bug React di Streamlit su questo filtro.")
        edited_df = _render_spese_generali_fallback_editor(
            df_editor_paginato=df_editor_paginato,
            categorie_disponibili=categorie_disponibili,
            editor_key=_editor_key,
        )
    else:
        edited_df = st.data_editor(
            df_editor_paginato,
            column_config=column_config_dict,
            hide_index=True,
            use_container_width=True,
            height=altezza_dinamica,
            key=_editor_key
        )
    
    if not use_stable_fallback_editor:
        st.markdown("""
            <style>
            [data-testid="stDataFrame"] [data-testid="stDataFrameCell"] {
                transition: background-color 0.3s ease;
            }
            
            /* 🔍 BADGE PIÙ LEGGIBILE nella colonna Novità */
            /* Approccio 1: Targetta tutte le celle dell'ultima colonna */
            div[data-testid="stDataFrame"] div[role="gridcell"]:nth-last-child(1),
            div[data-testid="stDataFrame"] div[role="gridcell"]:nth-last-child(2):has(:only-child) {
                font-size: clamp(1.1rem, 1vw + 0.8rem, 1.625rem) !important;
                text-align: center !important;
                line-height: 1.5 !important;
            }
            /* Approccio 2: Aumenta font per colonne con width="small" (Fonte e U.M.) */
            div[data-testid="stDataFrame"] [data-baseweb="cell"]:has(span:only-child) {
                font-size: clamp(1rem, 0.9vw + 0.8rem, 1.5rem) !important;
            }
            /* Approccio 3: Centra e ingrandisci celle contenenti solo emoji singole */
            div[data-testid="stDataFrame"] div[role="gridcell"] > div:only-child {
                font-size: inherit;
            }
            </style>
        """, unsafe_allow_html=True)
    
    totale_tabella = edited_df['TotaleRiga'].sum()
    num_righe = len(edited_df)
    
    # 🔍 CHECK VALIDAZIONE: Verifica che NON ci siano celle bianche nella colonna Categoria
    if 'Categoria' in edited_df.columns:
        celle_bianche = edited_df['Categoria'].apply(
            lambda x: x is None or pd.isna(x) or str(x).strip() == '' or str(x).strip().lower() == 'nan'
        ).sum()
        
        if celle_bianche > 0:
            logger.warning(f"⚠️ CHECK FALLITO: {celle_bianche} celle bianche trovate nella colonna Categoria!")
            # Forza conversione a "Da Classificare" se ancora bianche
            edited_df['Categoria'] = edited_df['Categoria'].apply(
                lambda x: 'Da Classificare' if (x is None or pd.isna(x) or str(x).strip() == '' or str(x).strip().lower() == 'nan') else x
            )
            st.warning(f"⚠️ {celle_bianche} celle vuote convertite a 'Da Classificare'")
        else:
            logger.info("✅ CHECK OK: Nessuna cella bianca nella colonna Categoria")

    pending_category_changes = []
    if not use_stable_fallback_editor:
        _editor_state = st.session_state.get(_editor_key, {})
        _edited_rows = _editor_state.get('edited_rows', {}) if isinstance(_editor_state, dict) else {}

        for raw_idx, row_changes in _edited_rows.items():
            if not isinstance(row_changes, dict) or 'Categoria' not in row_changes:
                continue

            try:
                row_idx = int(raw_idx)
            except (TypeError, ValueError):
                row_idx = raw_idx

            if row_idx not in edited_df.index or row_idx not in df_editor_paginato.index:
                continue

            nuova_cat = estrai_nome_categoria(edited_df.at[row_idx, 'Categoria'])
            vecchia_cat = estrai_nome_categoria(df_editor_paginato.at[row_idx, 'Categoria'])
            vecchia_cat = vecchia_cat or 'Da Classificare'

            if nuova_cat == vecchia_cat:
                continue

            pending_category_changes.append({
                'index': row_idx,
                'descrizione': edited_df.at[row_idx, 'Descrizione'],
                'file_origine': edited_df.at[row_idx, 'FileOrigine'] if 'FileOrigine' in edited_df.columns else None,
                'numero_riga': edited_df.at[row_idx, 'NumeroRiga'] if 'NumeroRiga' in edited_df.columns else None,
                'vecchia_cat': vecchia_cat,
                'nuova_cat': nuova_cat,
            })

    if not pending_category_changes and 'Categoria' in edited_df.columns and 'Categoria' in df_editor_paginato.columns:
        idx_comuni = edited_df.index.intersection(df_editor_paginato.index)
        for row_idx in idx_comuni:
            nuova_cat = estrai_nome_categoria(edited_df.at[row_idx, 'Categoria'])
            vecchia_cat = estrai_nome_categoria(df_editor_paginato.at[row_idx, 'Categoria'])
            vecchia_cat = vecchia_cat or 'Da Classificare'

            if nuova_cat == vecchia_cat:
                continue

            pending_category_changes.append({
                'index': row_idx,
                'descrizione': edited_df.at[row_idx, 'Descrizione'],
                'file_origine': edited_df.at[row_idx, 'FileOrigine'] if 'FileOrigine' in edited_df.columns else None,
                'numero_riga': edited_df.at[row_idx, 'NumeroRiga'] if 'NumeroRiga' in edited_df.columns else None,
                'vecchia_cat': vecchia_cat,
                'nuova_cat': nuova_cat,
            })

    if pending_category_changes:
        logger.info(f"📝 Modifiche categoria pendenti rilevate: {len(pending_category_changes)}")
    
    # Box riepilogo + selettore ordinamento + bottone Excel su una riga
    col_box, col_ord, col_btn = st.columns([5, 2, 1])
    
    with col_box:
        # Box blu con statistiche
        st.markdown(f"""
        <div style="background-color: #E3F2FD; padding: clamp(0.75rem, 2vw, 1rem) clamp(1rem, 2.5vw, 1.25rem); border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 1.25rem; width: fit-content;">
            <p style="color: #1565C0; font-size: clamp(0.875rem, 2vw, 1rem); font-weight: bold; margin: 0; white-space: normal; word-wrap: break-word; line-height: 1.4;">
                📋 N. Righe: {num_righe:,} | 💰 Totale: € {totale_tabella:.2f}
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_ord:
        # Selettore ordinamento affiancato al box blu
        st.markdown('<p style="margin-top: 0.5rem; font-size: clamp(0.75rem, 1.8vw, 0.875rem); font-weight: 500;">Seleziona ordinamento per export</p>', unsafe_allow_html=True)
        ordina_per = st.selectbox(
            "ord",
            options=["DataDocumento", "Categoria", "Fornitore", "Descrizione", "TotaleRiga"],
            index=0,
            key="select_ordina_export",
            label_visibility="collapsed"
        )

    with col_btn:
        # Allinea il pulsante a destra e stile pulito
        st.markdown('<div style="text-align: right;">', unsafe_allow_html=True)
        st.markdown("""
            <style>
            div.st-key-btn_excel_dettaglio .stDownloadButton button {
                background-color: #22c55e !important;
                color: white !important;
                border: none !important;
                border-radius: 8px !important;
                font-weight: 600 !important;
                outline: none !important;
                box-shadow: none !important;
            }
            div.st-key-btn_excel_dettaglio .stDownloadButton button:hover {
                background-color: #16a34a !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # Prepara Excel - USA TUTTI I DATI con ordinamento selezionato
        try:
            # ✅ ESPORTA DATI IN BASE ALLA VISUALIZZAZIONE
            # Vista aggregata: esporta righe aggregate (quelle visualizzate)
            # Vista normale: esporta tutte righe con modifiche applicate
            if vista_aggregata:
                # Esporta vista aggregata (già contiene somme/medie corrette)
                df_export = df_editor_paginato.copy()
                
                # Applica modifiche categorie fatte dall'utente
                if not edited_df.empty and 'Categoria' in edited_df.columns:
                    for idx in edited_df.index:
                        if idx in df_export.index:
                            df_export.at[idx, 'Categoria'] = edited_df.at[idx, 'Categoria']
            else:
                # Vista normale: esporta tutti i dati originali
                df_export = df_editor.copy()
                
                # Applica modifiche categorie fatte dall'utente nella pagina corrente
                if not edited_df.empty and 'Categoria' in edited_df.columns:
                    for idx in edited_df.index:
                        if idx in df_export.index:
                            df_export.at[idx, 'Categoria'] = edited_df.at[idx, 'Categoria']
            
            # ✅ APPLICA ORDINAMENTO SELEZIONATO
            if ordina_per and ordina_per in df_export.columns:
                # Ordina in modo decrescente per data e totale, crescente per gli altri
                if ordina_per in ['DataDocumento', 'TotaleRiga']:
                    df_export = df_export.sort_values(by=ordina_per, ascending=False)
                else:
                    df_export = df_export.sort_values(by=ordina_per, ascending=True)
            
            # Rimuovi colonna PrezzoStandard se presente
            if 'PrezzoStandard' in df_export.columns:
                df_export = df_export.drop(columns=['PrezzoStandard'])
            
            # Rimuovi colonna Novità e CreatedAt (segnali solo UI, non utili in Excel)
            if 'Novità' in df_export.columns:
                df_export = df_export.drop(columns=['Novità'])
            if 'CreatedAt' in df_export.columns:
                df_export = df_export.drop(columns=['CreatedAt'])
            
            # Rimuovi colonna CatIcon (solo decorativa nella UI)
            if 'CatIcon' in df_export.columns:
                df_export = df_export.drop(columns=['CatIcon'])
            
            # Rimuovi timezone da colonne datetime (openpyxl non supporta tz-aware)
            for col in df_export.select_dtypes(include=['datetimetz', 'datetime64[ns, UTC]']).columns:
                df_export[col] = df_export[col].dt.tz_localize(None)
            # Gestisci anche colonne object con date tz-aware
            if 'DataDocumento' in df_export.columns:
                try:
                    df_export['DataDocumento'] = pd.to_datetime(df_export['DataDocumento'], errors='coerce').dt.tz_localize(None)
                except TypeError:
                    df_export['DataDocumento'] = pd.to_datetime(df_export['DataDocumento'], errors='coerce').dt.tz_convert(None)
            
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Articoli')
            
            st.download_button(
                label="Excel",
                data=excel_buffer.getvalue(),
                file_name=f"dettaglio_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_excel_dettaglio",
                type="primary",
                use_container_width=False
            )
        except Exception as e:
            logger.exception(f"Errore esportazione Excel: {e}")
            st.error("❌ Errore nell'esportazione. Riprova.")
        
        st.markdown('</div>', unsafe_allow_html=True)


    if salva_modifiche:
        try:
            user_id = st.session_state.user_data["id"]
            user_email = st.session_state.user_data.get("email", "unknown")
            modifiche_effettuate = 0
            categorie_modificate_count = 0  # Conta prodotti unici modificati (non righe DB)
            skip_da_classificare_count = 0  # Conta righe "Da Classificare" saltate
            
            logger.info(f"💾 INIZIO SALVATAGGIO: user_id={user_id}, modifiche_pendenti={len(pending_category_changes)}, vista_aggregata={vista_aggregata}")
            st.toast("Salvataggio in corso...", icon="💾")
            
            # ⚠️ NOTA PAGINAZIONE: Il salvataggio riguarda SOLO le modifiche della pagina corrente
            righe_salvate = len(pending_category_changes)
            righe_totali_tabella = num_righe
            if 0 < righe_salvate < righe_totali_tabella:
                st.info(f"💾 Stai salvando {righe_salvate} {'modifica' if righe_salvate == 1 else 'modifiche'} della pagina corrente. Verifica altre pagine per modifiche aggiuntive.")
            
            # ========================================
            # ✅ CHECK: Quale tabella stiamo modificando?
            # ========================================
            colonne_df = edited_df.columns.tolist()
            
            # Check flessibile per Editor Fatture (supporta nomi alternativi + vista aggregata)
            ha_file = any(col in colonne_df for col in ['File', 'FileOrigine', 'NumFatture'])  # ← NumFatture per vista aggregata
            ha_numero_riga = any(col in colonne_df for col in ['NumeroRiga', 'Numero Riga', 'Riga', '#'])
            ha_fornitore = 'Fornitore' in colonne_df
            ha_descrizione = 'Descrizione' in colonne_df
            ha_categoria = 'Categoria' in colonne_df
            
            # Se ha colonne tipiche editor fatture (almeno File + Categoria + Descrizione)
            if (ha_file or (ha_numero_riga and ha_categoria and ha_descrizione and ha_fornitore)):
                logger.info("🔄 Rilevato: EDITOR FATTURE CLIENTE - Salvataggio modifiche...")
                if not pending_category_changes:
                    st.toast("⚠️ Nessuna modifica rilevata.")
                else:
                    changes_by_description = {}
                    conflict_map = defaultdict(set)

                    for change in pending_category_changes:
                        descrizione = str(change['descrizione'])
                        conflict_map[descrizione].add(change['nuova_cat'])
                        changes_by_description[descrizione] = change

                    conflicting_descriptions = [desc for desc, cats in conflict_map.items() if len(cats) > 1]
                    if conflicting_descriptions:
                        logger.warning(f"⚠️ Conflitto categorie per {len(conflicting_descriptions)} descrizioni duplicate nella sessione")

                    unique_changes = list(changes_by_description.values())
                    is_real_admin = st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False)

                    for change in unique_changes:
                        descrizione = change['descrizione']
                        nuova_cat = change['nuova_cat']
                        vecchia_cat = change['vecchia_cat']

                        if nuova_cat == "Da Classificare":
                            logger.debug(f"⏭️ SKIP: Categoria 'Da Classificare' non salvata per {descrizione[:TRUNCATE_DESC_QUERY]}")
                            skip_da_classificare_count += 1
                            continue

                        if nuova_cat not in categorie_valide_set:
                            logger.warning("Categoria non valida scartata al save: '%s'", nuova_cat)
                            skip_da_classificare_count += 1
                            continue

                        categorie_modificate_count += 1
                        logger.info(f"✋ MANUALE: '{descrizione[:TRUNCATE_DESC_LOG]}' modificato da '{vecchia_cat}' → {nuova_cat}")

                        if 'righe_modificate_manualmente' not in st.session_state:
                            st.session_state.righe_modificate_manualmente = []
                        if descrizione not in st.session_state.righe_modificate_manualmente:
                            st.session_state.righe_modificate_manualmente.append(descrizione)

                        if is_real_admin:
                            salva_correzione_in_memoria_globale(
                                descrizione=descrizione,
                                vecchia_categoria=vecchia_cat,
                                nuova_categoria=nuova_cat,
                                user_email=user_email,
                                is_admin=True
                            )
                        else:
                            successo = salva_correzione_in_memoria_locale(
                                descrizione=descrizione,
                                nuova_categoria=nuova_cat,
                                user_id=user_id,
                                user_email=user_email,
                                vecchia_categoria=vecchia_cat
                            )
                            if not successo:
                                logger.error(f"❌ CLIENTE: Errore salvataggio locale '{descrizione[:TRUNCATE_DESC_LOG]}'")

                    batch_groups = defaultdict(list)
                    for change in unique_changes:
                        if change['nuova_cat'] == 'Da Classificare':
                            continue
                        if change['nuova_cat'] not in categorie_valide_set:
                            continue  # già loggato nel loop precedente
                        batch_groups[change['nuova_cat']].append(change)

                    for nuova_cat, group_changes in batch_groups.items():
                        descrizioni = sorted({str(change['descrizione']) for change in group_changes if str(change['descrizione']).strip()})
                        if not descrizioni:
                            continue

                        logger.info(f"🚀 BATCH SAVE: categoria={nuova_cat}, descrizioni={len(descrizioni)}")

                        for start in range(0, len(descrizioni), 100):
                            chunk_descrizioni = descrizioni[start:start + 100]
                            query_batch = supabase.table("fatture").update({"categoria": nuova_cat}).eq(
                                "user_id", user_id
                            ).in_(
                                "descrizione", chunk_descrizioni
                            )
                            query_batch = add_ristorante_filter(query_batch)
                            result_batch = query_batch.execute()

                            updated_rows = result_batch.data or []
                            modifiche_effettuate += len(updated_rows)
                            updated_descs = {row.get('descrizione') for row in updated_rows if row.get('descrizione')}

                            unmatched_changes = [
                                change for change in group_changes
                                if str(change['descrizione']) in chunk_descrizioni and str(change['descrizione']) not in updated_descs
                            ]

                            for change in unmatched_changes:
                                descrizione = change['descrizione']
                                f_name = change['file_origine']
                                riga_idx = change['numero_riga']
                                righe_aggiornate = 0

                                if descrizione and str(descrizione).strip() != str(descrizione):
                                    query_update_trim = supabase.table("fatture").update({"categoria": nuova_cat}).eq(
                                        "user_id", user_id
                                    ).eq(
                                        "descrizione", str(descrizione).strip()
                                    )
                                    query_update_trim = add_ristorante_filter(query_update_trim)
                                    result_trim = query_update_trim.execute()
                                    if result_trim is not None and result_trim.data:
                                        righe_aggiornate = len(result_trim.data)

                                if righe_aggiornate == 0 and descrizione and str(descrizione).strip():
                                    query_update_ilike = supabase.table("fatture").update({"categoria": nuova_cat}).eq(
                                        "user_id", user_id
                                    ).ilike(
                                        "descrizione", str(descrizione).strip()
                                    )
                                    query_update_ilike = add_ristorante_filter(query_update_ilike)
                                    result_ilike = query_update_ilike.execute()
                                    if result_ilike is not None and result_ilike.data:
                                        righe_aggiornate = len(result_ilike.data)

                                if righe_aggiornate == 0 and f_name and riga_idx is not None:
                                    ristorante_id = st.session_state.get('ristorante_id')
                                    query_update_fallback = supabase.table("fatture").update({"categoria": nuova_cat}).eq(
                                        "user_id", user_id
                                    ).eq(
                                        "file_origine", f_name
                                    ).eq(
                                        "numero_riga", riga_idx
                                    )
                                    if ristorante_id:
                                        query_update_fallback = query_update_fallback.eq("ristorante_id", ristorante_id)
                                    result_fallback = query_update_fallback.execute()
                                    if result_fallback is not None and result_fallback.data:
                                        righe_aggiornate = len(result_fallback.data)

                                if righe_aggiornate == 0:
                                    logger.error(f"❌ UPDATE FALLITO: 0 righe aggiornate per '{descrizione}'")
                                    try:
                                        parole = str(descrizione).split()[:3]
                                        if parole:
                                            pattern_search = "%".join(parole)
                                            check_query = supabase.table("fatture").select("descrizione, categoria").eq(
                                                "user_id", user_id
                                            ).ilike("descrizione", f"%{_escape_ilike(pattern_search)}%").limit(5)
                                            check_query = add_ristorante_filter(check_query)
                                            check = check_query.execute()
                                            for i, row in enumerate(check.data or [], 1):
                                                logger.info(f"   [{i}] DB: '{row.get('descrizione', 'N/A')}' → cat: '{row.get('categoria', 'N/A')}'")
                                    except Exception as diag_err:
                                        logger.error(f"   ❌ Errore query diagnostica: {diag_err}")

                                modifiche_effettuate += righe_aggiornate
            
            # ⚠️ Se ha 'ID' ma NON colonne fatture → Memoria Globale (admin.py TAB 4)
            elif 'ID' in colonne_df and not ha_file and not ha_fornitore:
                st.warning("⚠️ Questa è una tabella Memoria Globale!")
                st.error("❌ Usa il bottone 'Salva Modifiche' nella sezione dedicata sotto la tabella.")
                st.info("💡 Questo bottone è solo per modifiche alle fatture, non per la memoria globale.")
            
            else:
                # Tipo di modifica non riconosciuto
                st.error("❌ Tipo di modifica non riconosciuto")
                st.info(f"📋 Colonne trovate: {colonne_df}")
                logger.warning(f"Tentativo salvataggio su tabella non riconosciuta. Colonne: {colonne_df}")


            if modifiche_effettuate > 0:
                # Conta quanti prodotti saranno rimossi dalla vista (categorie spese generali)
                prodotti_spostati = edited_df[edited_df['Categoria'].apply(
                    lambda cat: estrai_nome_categoria(cat) in CATEGORIE_SPESE_GENERALI
                )].shape[0]
                
                if prodotti_spostati > 0:
                    st.toast(f"✅ {categorie_modificate_count} categorie modificate! {prodotti_spostati} prodotti spostati in Spese Generali.")
                else:
                    st.toast(f"✅ {categorie_modificate_count} categorie modificate! L'AI imparerà da questo.")
                
                invalida_cache_memoria()
                # Invalida anche la cache Fonte (prodotti_master) per forzare rilettura
                st.session_state.pop('_fonte_pm_cache', None)
                st.session_state.force_reload = True  # ← Forza ricaricamento completo
                
                # ⭐ Incrementa counter per forzare refresh del data_editor
                # (altrimenti Streamlit usa il widget state cached con Fonte vuota)
                st.session_state.editor_refresh_counter = st.session_state.get('editor_refresh_counter', 0) + 1
                
                # ⭐ Le icone Fonte vengono MANTENUTE dopo il salvataggio
                # per continuare a mostrare l'origine della categorizzazione.
                # Si resettano solo quando viene caricata una nuova fattura (linea ~4282).
                logger.info(f"✅ Fonte tracking mantenuto: {len(st.session_state.get('righe_ai_appena_categorizzate', []))} AI, {len(st.session_state.get('righe_keyword_appena_categorizzate', []))} keyword, {len(st.session_state.get('righe_modificate_manualmente', []))} manuali")
                
                st.rerun()
            elif (ha_file or ha_numero_riga) and ha_categoria and ha_descrizione:
                # Solo se era davvero l'editor fatture
                if categorie_modificate_count > 0:
                    st.error("❌ Modifiche manuali rilevate ma nessuna riga aggiornata su database.")
                    st.info("💡 Possibile mismatch sulla descrizione tra tabella e DB. Ho aggiunto fallback robusti: riprova il salvataggio.")
                elif skip_da_classificare_count > 0:
                    st.toast(f"⚠️ {skip_da_classificare_count} prodotti 'Da Classificare' saltati. Assegna una categoria prima di salvare.")
                else:
                    st.toast("⚠️ Nessuna modifica rilevata.")


        except Exception as e:
            logger.exception("Errore durante il salvataggio modifiche categorie")
            logger.error(f"Errore durante il salvataggio: {e}")
            st.error("❌ Errore durante il salvataggio. Riprova.")
