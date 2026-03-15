"""Sezione Dettaglio Articoli - Data editor per la modifica delle categorie."""

import streamlit as st
import pandas as pd
import io
import time
import logging

from config.constants import CATEGORIE_SPESE_GENERALI, TRUNCATE_DESC_LOG, TRUNCATE_DESC_QUERY
from utils.text_utils import normalizza_stringa, estrai_nome_categoria, escape_ilike as _escape_ilike
from utils.formatters import calcola_prezzo_standard_intelligente, carica_categorie_da_db
from utils.ristorante_helper import add_ristorante_filter
from utils.ui_helpers import load_css
from services.ai_service import invalida_cache_memoria, salva_correzione_in_memoria_globale, salva_correzione_in_memoria_locale


logger = logging.getLogger("fci_app")


def render_category_editor(df_completo_filtrato, supabase):
    """Renderizza la sezione Dettaglio Articoli con data editor e logica di salvataggio."""
    # Placeholder se dataset mancanti/vuoti
    if df_completo_filtrato is None or df_completo_filtrato.empty:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")
        st.stop()

    
    # 📦 SEZIONE DETTAGLIO ARTICOLI
    
    # ===== FILTRO TIPO PRODOTTI =====
    col_tipo, col_search_type, col_search, col_save = st.columns([2, 2, 3, 2])
    
    with col_tipo:
        tipo_filtro = st.selectbox(
            "📦 Tipo Prodotti:",
            options=["Food & Beverage", "Spese Generali", "Tutti"],
            key="tipo_filtro_prodotti",
            help="Filtra per tipologia di prodotto"
        )

    with col_search_type:
        search_type = st.selectbox(
            "🔍 Cerca per:",
            options=["Prodotto", "Categoria", "Fornitore"],
            key="search_type"
        )


    with col_search:
        if search_type == "Prodotto":
            placeholder_text = "Es: pollo, salmone, caffè..."
            label_text = "🔍 Cerca nella descrizione:"
        elif search_type == "Categoria":
            placeholder_text = "Es: CARNE, PESCE, CAFFÈ..."
            label_text = "🔍 Cerca per categoria:"
        else:
            placeholder_text = "Es: EKAF, PREGIS..."
            label_text = "🔍 Cerca per fornitore:"
        
        search_term = st.text_input(
            label_text,
            placeholder=placeholder_text,
            key="search_prodotto"
        )


    with col_save:
        st.markdown("<br>", unsafe_allow_html=True)
        salva_modifiche = st.button(
            "💾 Salva Modifiche Categorie",
            type="primary",
            use_container_width=True,
            key="salva_btn"
        )
    
    # ✅ FILTRO DINAMICO IN BASE ALLA SELEZIONE - USA DATI FILTRATI PER PERIODO
    # NOTA: Filtriamo SOLO per categoria, NON per fornitore!
    # - MATERIALE DI CONSUMO (ex NO FOOD) è F&B (pellicole, guanti, detersivi)
    # - SPESE GENERALI sono solo 3 categorie: UTENZE, SERVIZI, MANUTENZIONE
    if tipo_filtro == "Food & Beverage":
        # F&B + MATERIALE DI CONSUMO = tutto tranne Spese Generali
        df_base = df_completo_filtrato[
            ~df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
        ].copy()
    elif tipo_filtro == "Spese Generali":
        # Solo le 3 categorie spese generali
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
    
    df_editor = df_base[cols_base].copy()
    
    # ⭐ COLONNA FONTE - Origine categorizzazione (UI-only, NON salvata in DB)
    # 3 stati: 📚 Memoria Globale | 🧠 AI Batch | ✋ Modifica Manuale
    if 'Descrizione' in df_editor.columns:
        # MEMORIA GLOBALE 📚 (dizionario + memoria prodotti già visti)
        righe_diz = st.session_state.get('righe_keyword_appena_categorizzate', [])
        righe_mem = st.session_state.get('righe_memoria_appena_categorizzate', [])
        globale_set = set(str(d).strip() for d in righe_diz) | set(str(d).strip() for d in righe_mem)
        
        # AI BATCH 🧠 (solo AI pura, escludi keyword/dizionario)
        righe_ai = st.session_state.get('righe_ai_appena_categorizzate', [])
        ai_set = set(str(d).strip() for d in righe_ai) - globale_set  # Rimuovi overlap con keyword
        
        # MODIFICA MANUALE ✋
        righe_man = st.session_state.get('righe_modificate_manualmente', [])
        man_set = set(str(d).strip() for d in righe_man)
        
        # Priorità: ✋ > 🧠 > 📚 > vuoto
        df_editor['Fonte'] = df_editor['Descrizione'].apply(
            lambda d: ' ✋ ' if str(d).strip() in man_set else
                      ' 🧠 ' if str(d).strip() in ai_set else
                      ' 📚 ' if str(d).strip() in globale_set else ''
        )
        logger.info(f"✅ Colonna Fonte: {len(man_set)} manuali, {len(ai_set)} AI, {len(globale_set)} memoria globale")
    
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
            st.info(f"🔍 Trovate {mask.sum()} righe con '{search_term}' nella descrizione")
        elif search_type == "Categoria":
            mask = df_editor['Categoria'].str.upper().str.contains(search_term.upper(), na=False, regex=False)
            st.info(f"🔍 Trovate {mask.sum()} righe nella categoria '{search_term}'")
        else:
            mask = df_editor['Fornitore'].str.upper().str.contains(search_term.upper(), na=False, regex=False)
            st.info(f"🔍 Trovate {mask.sum()} righe del fornitore '{search_term}'")
        
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

    num_righe = len(df_editor)
    
    # Avviso salvataggio modifiche (dopo filtri)
    st.markdown("""
<div style='padding: 8px 14px; font-size: 0.88rem; color: #9a3412; font-weight: 500; text-align: left; margin-bottom: 12px;'>
    ⚠️ <strong>ATTENZIONE:</strong> Se hai modificato dati nella tabella, <strong>clicca SALVA</strong> prima di cambiare filtro, altrimenti le modifiche andranno perse!
</div>
""", unsafe_allow_html=True)
    
    # ============================================================
    # 📦 CHECKBOX RAGGRUPPAMENTO PRODOTTI
    # ============================================================
    vista_aggregata = st.checkbox(
        "📦 Raggruppa prodotti unici", 
        value=True,  # ← DEFAULT ON
        help="Mostra 1 riga per prodotto con totali sommati (Q.tà, €, Prezzo medio)",
        key="checkbox_raggruppa_prodotti"
    )

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
        if 'Fonte' in df_editor.columns:
            agg_dict['Fonte'] = 'first'
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
        # Ordine: NumFatture, NumRighe, Data, Descrizione, Categoria, Fornitore, Quantita, Totale, Prezzo, UM, IVA, Fonte
        cols_order = ['NumFatture', 'NumRighe', 'DataDocumento', 'Descrizione', 'Categoria', 
                     'Fornitore', 'Quantita', 'TotaleRiga', 'PrezzoUnitario', 'UnitaMisura', 'IVAPercentuale']
        
        # Aggiungi Fonte se presente
        if 'Fonte' in df_editor_agg.columns:
            cols_order.append('Fonte')
        
        # Aggiungi PrezzoStandard se presente
        if 'PrezzoStandard' in df_editor_agg.columns:
            cols_order.append('PrezzoStandard')
        
        # Mantieni solo le colonne effettivamente presenti nel dataframe
        cols_final = [c for c in cols_order if c in df_editor_agg.columns]
        df_editor_agg = df_editor_agg[cols_final]
        
        # Usa vista aggregata
        df_editor_paginato = df_editor_agg
    else:
        df_editor_paginato = df_editor.copy()
    
    # Calcola prodotti unici (descrizioni distinte)
    num_prodotti_unici = df_editor['Descrizione'].nunique()
    
    st.markdown(f"""
    <div style="background-color: #E8F5E9; padding: 12px 15px; border-radius: 8px; border-left: 4px solid #4CAF50; margin-bottom: 15px;">
        <p style="margin: 0; font-size: 14px; color: #2E7D32; font-weight: 500;">
            📄 <strong>Totale: {num_righe:,} righe</strong> • 🏷️ <strong>{num_prodotti_unici:,} prodotti unici</strong>
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
    # 🔄 MIGRAZIONE NOMI: Uniforma vecchio nome 'CAFFÈ' al nuovo 'CAFFE E THE'
    categorie_disponibili = [
        ('CAFFE E THE' if str(cat).strip().upper() in ['CAFFÈ', 'CAFFE'] else cat)
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
    
    # Log finale validazione
    vuote_count = df_editor['Categoria'].isna().sum()
    if vuote_count > 0:
        logger.warning(f"⚠️ VALIDAZIONE: {vuote_count} celle vuote (non categorizzate)")
    
    # ✅ Le categorie vengono normalizzate automaticamente al caricamento
    # Migrazione vecchi nomi → nuovi nomi avviene in carica_e_prepara_dataframe()
    
    # 🚫 RIMUOVI colonne LISTINO dalla visualizzazione
    cols_to_drop = [c for c in ['PrezzoStandard', 'Listino', 'LISTINO'] if c in df_editor_paginato.columns]
    if cols_to_drop:
        df_editor_paginato = df_editor_paginato.drop(columns=cols_to_drop)

    # Configurazione colonne (ordine allineato tra vista normale e aggregata)
    column_config_dict = {
        "FileOrigine": st.column_config.TextColumn("File", disabled=True),
        "NumeroRiga": st.column_config.NumberColumn("N.Riga", disabled=True, width="small"),
        "DataDocumento": st.column_config.TextColumn("Data", disabled=True),
        "Descrizione": st.column_config.TextColumn("Descrizione", disabled=True),
        "Categoria": st.column_config.SelectboxColumn(
            "Categoria",
            help="Seleziona la categoria corretta (le celle 'Da Classificare' devono essere categorizzate)",
            width="medium",
            options=categorie_disponibili,
            required=True
        ),
        "Fornitore": st.column_config.TextColumn("Fornitore", disabled=True),
        "Quantita": st.column_config.NumberColumn("Q.tà", disabled=True),
        "TotaleRiga": st.column_config.NumberColumn("Totale (€)", format="€ %.2f", disabled=True),
        "PrezzoUnitario": st.column_config.NumberColumn("Prezzo Unit.", format="€ %.2f", disabled=True),
        "UnitaMisura": st.column_config.TextColumn("U.M.", disabled=True, width="small"),
        # ⭐ NUOVO: Colonna Fonte (dopo IVA)
        "IVAPercentuale": st.column_config.NumberColumn(
            "IVA %",
            format="%.0f%%",
            disabled=True,
            width="small"
        ),
        "Fonte": st.column_config.TextColumn(
            "Fonte",
            help="📚 Memoria Globale | 🧠 AI Batch | ✋ Modifica Manuale",
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
                "N.Fatt", 
                help="Numero fatture con questo prodotto",
                disabled=True,
                width="small"
            )
        
        # Colonna NumRighe (solo in aggregata)
        if 'NumRighe' in df_editor_paginato.columns:
            column_config_dict["NumRighe"] = st.column_config.NumberColumn(
                "N.Righe", 
                help="Numero righe fattura aggregate per questo prodotto",
                disabled=True,
                width="small"
            )
        
        # Adatta etichette colonne esistenti
        column_config_dict["Quantita"] = st.column_config.NumberColumn(
            "Q.tà TOT",  # ← Sottolinea che è somma
            help="Quantità totale da tutte le fatture",
            disabled=True
        )
        
        column_config_dict["PrezzoUnitario"] = st.column_config.NumberColumn(
            "Prezzo MEDIO",  # ← Chiarisce che è media
            format="€ %.2f",
            disabled=True
        )
        
        column_config_dict["TotaleRiga"] = st.column_config.NumberColumn(
            "€ TOTALE",  # ← Enfatizza somma
            format="€ %.2f",
            disabled=True
        )
    
    # ⭐ Key dinamica: cambia dopo ogni salvataggio per forzare refresh widget
    # (evita che Streamlit cache il vecchio stato della colonna Fonte)
    _editor_version = st.session_state.get('editor_refresh_counter', 0)
    edited_df = st.data_editor(
        df_editor_paginato,
        column_config=column_config_dict,
        hide_index=True,
        width='stretch',
        height=altezza_dinamica,
        key=f"editor_dati_v{_editor_version}"
    )
    
    st.markdown("""
        <style>
        /* 🧠 COLORAZIONE ROSA per righe classificate da AI */
        [data-testid="stDataFrame"] [data-testid="stDataFrameCell"] {
            transition: background-color 0.3s ease;
        }
        /* Nota: Streamlit data_editor non supporta styling condizionale per riga basato su valore cella.
           La colorazione visiva principale sarà l'icona 🧠 nella colonna Stato. */
        
        /* 🔍 EMOJI PIÙ GRANDI nella colonna Fonte (ultima colonna) */
        /* Approccio 1: Targetta tutte le celle dell'ultima colonna */
        div[data-testid="stDataFrame"] div[role="gridcell"]:nth-last-child(1),
        div[data-testid="stDataFrame"] div[role="gridcell"]:nth-last-child(2):has(:only-child) {
            font-size: 26px !important;
            text-align: center !important;
            line-height: 1.5 !important;
        }
        /* Approccio 2: Aumenta font per colonne con width="small" (Fonte e U.M.) */
        div[data-testid="stDataFrame"] [data-baseweb="cell"]:has(span:only-child) {
            font-size: 24px !important;
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
            logger.error(f"Errore esportazione Excel: {e}")
            st.error("❌ Errore nell'esportazione. Riprova.")
        
        st.markdown('</div>', unsafe_allow_html=True)


    if salva_modifiche:
        try:
            user_id = st.session_state.user_data["id"]
            user_email = st.session_state.user_data.get("email", "unknown")
            modifiche_effettuate = 0
            categorie_modificate_count = 0  # Conta prodotti unici modificati (non righe DB)
            skip_da_classificare_count = 0  # Conta righe "Da Classificare" saltate
            
            logger.info(f"💾 INIZIO SALVATAGGIO: user_id={user_id}, righe_edited={len(edited_df)}, vista_aggregata={vista_aggregata}")
            st.toast("💾 Salvataggio in corso...", icon="💾")
            
            # ⚠️ NOTA PAGINAZIONE: Il salvataggio riguarda SOLO le righe della pagina corrente
            righe_salvate = len(edited_df)
            righe_totali_tabella = num_righe
            if righe_salvate < righe_totali_tabella:
                st.info(f"💾 Stai salvando {righe_salvate} righe della pagina corrente. Verifica altre pagine per modifiche aggiuntive.")
            
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
            if (ha_file or ha_numero_riga) and ha_categoria and ha_descrizione and ha_fornitore:
                logger.info("🔄 Rilevato: EDITOR FATTURE CLIENTE - Salvataggio modifiche...")
                
                for index, row in edited_df.iterrows():
                    try:
                        # Recupera valori con nomi alternativi
                        f_name = row.get('File') or row.get('FileOrigine')
                        riga_idx = row.get('NumeroRiga') or row.get('Numero Riga') or row.get('Riga') or (index + 1)
                        nuova_cat_raw = row['Categoria']
                        descrizione = row['Descrizione']
                        
                        # ✅ ESTRAI SOLO NOME CATEGORIA (rimuovi emoji se presente)
                        nuova_cat = estrai_nome_categoria(nuova_cat_raw)
                        
                        # ⛔ SKIP se categoria è "Da Classificare" (non salvare categorie placeholder)
                        if nuova_cat == "Da Classificare":
                            logger.debug(f"⏭️ SKIP: Categoria 'Da Classificare' non salvata per {descrizione[:TRUNCATE_DESC_QUERY]}")
                            skip_da_classificare_count += 1
                            continue
                        
                        # Recupera categoria originale per tracciare correzione
                        # ⚠️ In vista aggregata, df_editor ha indici diversi da edited_df
                        # Usa df_editor_paginato (stessi indici di edited_df) per il confronto
                        if vista_aggregata:
                            vecchia_cat_raw = df_editor_paginato.loc[index, 'Categoria'] if index in df_editor_paginato.index else None
                        else:
                            vecchia_cat_raw = df_editor.loc[index, 'Categoria'] if index in df_editor.index else None
                        vecchia_cat = estrai_nome_categoria(vecchia_cat_raw) if vecchia_cat_raw else None
                        
                        # Prepara dati da aggiornare
                        update_data = {
                            "categoria": nuova_cat
                        }
                        
                        # Aggiungi prezzo_standard solo se presente e valido
                        prezzo_std = row.get('PrezzoStandard')
                        if prezzo_std is not None and pd.notna(prezzo_std):
                            try:
                                update_data["prezzo_standard"] = float(prezzo_std)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Errore conversione prezzo_standard: {e}")
                        
                        # ✋ TRACCIAMENTO MODIFICA MANUALE
                        # Se categoria cambiata dall'utente → salva in memoria
                        categoria_modificata = (vecchia_cat and vecchia_cat != nuova_cat) or \
                                             (not vecchia_cat and nuova_cat != 'Da Classificare')
                        
                        if categoria_modificata:
                            categorie_modificate_count += 1
                            logger.info(f"✋ MANUALE: '{descrizione[:TRUNCATE_DESC_LOG]}' modificato da '{vecchia_cat or "vuoto"}' → {nuova_cat}")
                            
                            # ⭐ NUOVO: Traccia modifica manuale per colonna Fonte
                            if 'righe_modificate_manualmente' not in st.session_state:
                                st.session_state.righe_modificate_manualmente = []
                            if descrizione not in st.session_state.righe_modificate_manualmente:
                                st.session_state.righe_modificate_manualmente.append(descrizione)
                            
                            # ✅ SALVA IN MEMORIA: LOCALE per clienti, GLOBALE solo per admin veri
                            is_real_admin = st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False)
                            
                            if is_real_admin:
                                # Admin vero (non impersonificato) → modifica GLOBALE per tutti
                                salva_correzione_in_memoria_globale(
                                    descrizione=descrizione,
                                    vecchia_categoria=vecchia_cat,
                                    nuova_categoria=nuova_cat,
                                    user_email=user_email,
                                    is_admin=True
                                )
                                logger.info(f"🔧 ADMIN: Modifica GLOBALE per tutti i clienti")
                            else:
                                # Cliente (o admin impersonificato) → modifica LOCALE solo per lui
                                successo = salva_correzione_in_memoria_locale(
                                    descrizione=descrizione,
                                    nuova_categoria=nuova_cat,
                                    user_id=user_id,
                                    user_email=user_email
                                )
                                
                                if successo:
                                    logger.info(f"✅ CLIENTE: Salvato locale '{descrizione[:TRUNCATE_DESC_LOG]}' → {nuova_cat}")
                                else:
                                    logger.error(f"❌ CLIENTE: Errore salvataggio locale '{descrizione[:TRUNCATE_DESC_LOG]}'")
                        
                        # 🔄 MODIFICA BATCH: Se categoria è cambiata, aggiorna TUTTE le righe con stessa descrizione
                        # In vista aggregata: SEMPRE batch update (1 riga vista = N righe DB)
                        # In vista normale: batch update solo se categoria diversa dalla precedente
                        esegui_batch_update = vista_aggregata or (vecchia_cat and vecchia_cat != nuova_cat)
                        
                        # ⚡ PERFORMANCE: Se non c'è modifica, SKIP (evita query DB inutili)
                        if not esegui_batch_update and not categoria_modificata:
                            continue
                        
                        if esegui_batch_update:
                            if vista_aggregata:
                                logger.info(f"📦 AGGREGATA - BATCH UPDATE: '{descrizione}' → {nuova_cat}")
                            else:
                                logger.info(f"🔄 BATCH UPDATE: '{descrizione}' {vecchia_cat} → {nuova_cat}")
                            
                            # 🔍 DIAGNOSI: Log dettagliato descrizione per debug
                            desc_normalized = normalizza_stringa(descrizione)
                            logger.debug(f"🔍 DEBUG UPDATE: '{descrizione}' → '{desc_normalized}' → {nuova_cat} (user={user_id})")
                            
                            # Aggiorna tutte le righe con stessa descrizione per TUTTI i ristoranti del cliente
                            query_update_batch = supabase.table("fatture").update(update_data).eq(
                                "user_id", user_id
                            ).eq(
                                "descrizione", descrizione
                            )
                            result = query_update_batch.select("id").execute()
                            
                            # supabase-py v2: senza .select() result.data è sempre []
                            righe_aggiornate = len(result.data) if result.data else 1  # assume 1 se nessun errore
                            logger.info(f"✅ BATCH: {righe_aggiornate} righe aggiornate per '{descrizione[:TRUNCATE_DESC_LOG]}'")
                            
                            # 🔍 DIAGNOSI: Se UPDATE fallisce (0 righe), cerca descrizioni simili nel DB
                            if righe_aggiornate == 0:
                                logger.error(f"❌ UPDATE FALLITO: 0 righe aggiornate per '{descrizione}'")
                                logger.info(f"🔍 Cerco descrizioni simili nel database...")
                                
                                try:
                                    # Query diagnostica: cerca per pattern parziale
                                    parole = descrizione.split()[:3]  # Prime 3 parole
                                    if parole:
                                        pattern_search = "%".join(parole)
                                        check_query = supabase.table("fatture").select("descrizione, categoria").eq(
                                            "user_id", user_id
                                        ).ilike("descrizione", f"%{_escape_ilike(pattern_search)}%").limit(5)
                                        check_query = add_ristorante_filter(check_query)
                                        check = check_query.execute()
                                        
                                        if check.data:
                                            logger.info(f"📋 Trovate {len(check.data)} descrizioni simili nel DB:")
                                            for i, row in enumerate(check.data, 1):
                                                db_desc = row.get('descrizione', 'N/A')
                                                db_cat = row.get('categoria', 'N/A')
                                                logger.info(f"   [{i}] DB: '{db_desc}' → cat: '{db_cat}'")
                                                
                                                # Confronto carattere per carattere
                                                if db_desc != descrizione:
                                                    logger.info(f"   ⚠️ DIFFERENZA TROVATA:")
                                                    logger.info(f"      edited_df: '{descrizione}' (len={len(descrizione)})")
                                                    logger.info(f"      database:  '{db_desc}' (len={len(db_desc)})")
                                        else:
                                            logger.info(f"   ❌ Nessuna descrizione simile trovata per pattern '{pattern_search}'")
                                except Exception as diag_err:
                                    logger.error(f"   ❌ Errore query diagnostica: {diag_err}")
                            
                            modifiche_effettuate += righe_aggiornate
                            
                        else:
                            # Aggiorna solo questa riga specifica (nessun cambio categoria)
                            ristorante_id = st.session_state.get('ristorante_id')
                            query_update_single = supabase.table("fatture").update(update_data).eq(
                                "user_id", user_id
                            ).eq(
                                "file_origine", f_name
                            ).eq(
                                "numero_riga", riga_idx
                            ).eq(
                                "descrizione", descrizione
                            )
                            if ristorante_id:
                                query_update_single = query_update_single.eq("ristorante_id", ristorante_id)
                            result = query_update_single.select("id").execute()
                            
                            # supabase-py v2: senza .select() result.data è sempre []
                            modifiche_effettuate += 1  # assume successo se nessun errore
                            
                    except Exception as e_single:
                        logger.exception(f"Errore aggiornamento singola riga {f_name}:{riga_idx}")
                        continue
            
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


            if modifiche_effettuate > 0 or categorie_modificate_count > 0:
                # Conta quanti prodotti saranno rimossi dalla vista (categorie spese generali)
                prodotti_spostati = edited_df[edited_df['Categoria'].apply(
                    lambda cat: estrai_nome_categoria(cat) in CATEGORIE_SPESE_GENERALI
                )].shape[0]
                
                if prodotti_spostati > 0:
                    st.toast(f"✅ {categorie_modificate_count} categorie modificate! {prodotti_spostati} prodotti spostati in Spese Generali.")
                else:
                    st.toast(f"✅ {categorie_modificate_count} categorie modificate! L'AI imparerà da questo.")
                
                time.sleep(0.5)
                st.cache_data.clear()
                invalida_cache_memoria()
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
                if skip_da_classificare_count > 0:
                    st.toast(f"⚠️ {skip_da_classificare_count} prodotti 'Da Classificare' saltati. Assegna una categoria prima di salvare.")
                else:
                    st.toast("⚠️ Nessuna modifica rilevata.")


        except Exception as e:
            logger.exception("Errore durante il salvataggio modifiche categorie")
            logger.error(f"Errore durante il salvataggio: {e}")
            st.error("❌ Errore durante il salvataggio. Riprova.")
