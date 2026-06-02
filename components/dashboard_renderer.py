"""Dashboard principale - Statistiche, KPI, categorizzazione AI e navigazione sezioni."""

import streamlit as st
import pandas as pd
import time
import logging
from datetime import datetime, timezone
import plotly.express as px
import plotly.graph_objects as go

from config.constants import (
    CATEGORIE_SPESE_GENERALI,
    MESI_ITA,
    TRUNCATE_DESC_LOG,
    TRUNCATE_DESC_QUERY,
    MAX_AI_CALLS_PER_DAY,
)

from utils.text_utils import normalizza_stringa
from utils.ui_helpers import render_pivot_mensile
from utils.ristorante_helper import add_ristorante_filter
from utils.validation import classify_special_row_vectorized

from services.ai_service import (
    carica_memoria_completa,
    invalida_cache_memoria,
    applica_correzioni_dizionario,
    applica_regole_categoria_forti,
    svuota_memoria_globale,
    set_global_memory_enabled,
    ottieni_categoria_prodotto,
    ottieni_hint_per_ai,
    aggiorna_streak_classificazione,
)
from services.worker_client import classifica_via_worker, classifica_via_worker_con_confidenza
from services.db_service import calcola_spesa_mensile_aggregata

from components.category_editor import render_category_editor
from utils.app_controllers import is_admin_or_impersonating as _is_admin_or_impersonating


logger = logging.getLogger("fci_app")


def mostra_statistiche(df_completo, supabase, uploaded_files=None):
    """Mostra grafici, filtri e tabella dati"""
    
    if df_completo is None or df_completo.empty:
        st.info("📭 Nessun dato disponibile. Carica le tue prime fatture!")
        return

    # Stili componenti condivisi (ai-banner, kpi-card, ecc.): common.css è già
    # iniettato dal chiamante (app.py / app_controllers) nello stesso run — niente doppia injection.

    # ===== 🔍 DEBUG CATEGORIZZAZIONE (SOLO ADMIN IMPERSONIFICATO) =====
    if st.session_state.get('impersonating', False):
        with st.expander("🔍 DEBUG: Verifica Categorie", expanded=False):
            st.markdown("**Statistiche DataFrame Completo:**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Righe Totali", len(df_completo))
            with col2:
                st.metric("Categorie NULL", df_completo['Categoria'].isna().sum())
            with col3:
                st.metric("Categorie Vuote", (df_completo['Categoria'] == '').sum())
            
            st.markdown("**Conteggio per Categoria:**")
            conteggio_cat = df_completo.groupby('Categoria', dropna=False).size().reset_index(name='Righe')
            conteggio_cat = conteggio_cat.sort_values('Righe', ascending=False)
            st.dataframe(conteggio_cat, hide_index=True, use_container_width=True)
            
            st.markdown("**Esempio 15 righe (verifica categoria):**")
            _sample_cols = ['FileOrigine', 'NumeroDocumento', 'Descrizione', 'Categoria', 'Fornitore', 'TotaleRiga']
            sample_df = df_completo[[c for c in _sample_cols if c in df_completo.columns]].head(15)
            st.dataframe(sample_df, hide_index=True, use_container_width=True)
            
            # Test query diretta Supabase
            if st.button("🔄 Ricarica da Supabase (bypass cache)", key="debug_reload"):
                invalida_cache_memoria()
                st.success("Cache invalidata. Dati ricaricati al prossimo accesso.")

        # ===== 🧠 MEMORIA GLOBALE AI (SOLO ADMIN IMPERSONIFICATO) =====
        with st.expander("🧠 Memoria Globale AI", expanded=False):
            st.markdown("Gestione memoria condivisa per test/diagnosi.")

            # Toggle sessione: disabilita uso memoria globale
            disabilita = st.checkbox(
                "Disabilita memoria globale (solo sessione)",
                value=st.session_state.get("disable_global_memory", False),
                help="Ignora 'prodotti_master' in questa sessione per testare la logica senza memorie pregresse.",
                key="chk_disable_global_memory"
            )
            st.session_state["disable_global_memory"] = disabilita
            # Applica al servizio
            set_global_memory_enabled(not disabilita)

            st.divider()
            st.markdown("""<strong>Azione definitiva:</strong> elimina tutte le voci in memoria globale (DB).""", unsafe_allow_html=True)
            conferma = st.checkbox("Confermo svuotamento totale della memoria globale", key="chk_confirm_clear")
            if st.button("🗑️ Svuota Memoria Globale AI (DB)", disabled=not conferma, key="btn_clear_global"):
                esito = svuota_memoria_globale(supabase)
                if esito:
                    st.success("Memoria globale svuotata con successo.")
                else:
                    st.error("Errore durante lo svuotamento della memoria globale.")
                st.rerun()
    # ===== FINE DEBUG =====
    
    # ===== FILTRA DICITURE DA DASHBOARD =====
    righe_prima = len(df_completo)
    
    special_meta = classify_special_row_vectorized(df_completo)

    mask_escludi = ~special_meta['include_in_dashboard'].fillna(False).astype(bool)

    # Fallback difensivo: su DataFrame minimali (test/migrazioni) il classificatore
    # puo' non avere abbastanza contesto; escludiamo comunque righe note/review.
    if 'needs_review' in df_completo.columns:
        mask_escludi = mask_escludi | df_completo['needs_review'].fillna(False).astype(bool)
    if 'Categoria' in df_completo.columns:
        categoria_norm = df_completo['Categoria'].fillna('').astype(str).str.upper().str.strip()
        mask_escludi = mask_escludi | categoria_norm.isin({'📝 NOTE E DICITURE', 'NOTE E DICITURE'})
    
    # Applica filtro (MANTIENI righe NON escluse)
    df_completo = df_completo[~mask_escludi].copy()
    
    righe_dopo = len(df_completo)
    if righe_prima > righe_dopo:
        logger.info(
            f"Escluse da dashboard: {righe_prima - righe_dopo} righe "
            f"(diciture + storni + righe da verificare)"
        )
    
    if df_completo.empty:
        st.info("📭 Nessun dato disponibile dopo i filtri.")
        return
    # ===== FINE FILTRO DICITURE =====

    def _render_spesa_tempo_sotto_tab(df_source: pd.DataFrame, dimensione: str, key_prefix: str):
        """Renderizza grafico trend spesa mensile sotto la tabella pivot del tab corrente."""
        if df_source is None or df_source.empty:
            return

        df_spesa = calcola_spesa_mensile_aggregata(df_source, dimensione)
        if df_spesa.empty:
            st.info(f"📭 Nessun dato disponibile per il grafico {dimensione.lower()}.")
            return

        st.markdown("<div style='margin-top: 1.9rem;'></div>", unsafe_allow_html=True)

        ranking_dimensioni = (
            df_spesa.groupby('dimensione', as_index=False)['spesa_totale']
            .sum()
            .sort_values('spesa_totale', ascending=False)
        )

        select_key = f"{key_prefix}_select"
        opzioni = sorted(
            ranking_dimensioni['dimensione'].astype(str).dropna().unique().tolist(),
            key=lambda valore: valore.casefold(),
        )

        if not opzioni:
            st.info(f"📭 Nessun valore {dimensione.lower()} disponibile.")
            return

        st.markdown(
            f"<h4 style='color:#1e40af; font-weight:700; margin-bottom:0.45rem;'>📊 Spesa nel Tempo per {dimensione}</h4>",
            unsafe_allow_html=True,
        )

        selected_value = st.session_state.get(select_key)
        selected_index = opzioni.index(selected_value) if selected_value in opzioni else 0
        col_filtro, _ = st.columns([1, 2])
        with col_filtro:
            scelta = st.selectbox(
                f"Seleziona {dimensione.lower()}",
                options=opzioni,
                index=selected_index,
                key=select_key,
            )

        serie_raw = df_spesa[df_spesa['dimensione'] == scelta].copy().sort_values('mese')
        if serie_raw.empty:
            st.info("📭 Nessun dato disponibile per la selezione corrente.")
            return

        valori_periodo = pd.to_numeric(serie_raw['spesa_totale'], errors='coerce').fillna(0.0)
        mesi_disponibili = int(serie_raw['mese'].dropna().nunique())
        totale_periodo = float(valori_periodo.sum())
        media_periodo = float(valori_periodo.mean())

        full_range = pd.date_range(serie_raw['mese'].min(), serie_raw['mese'].max(), freq='MS')
        serie = serie_raw.copy()
        serie = (
            serie.set_index('mese')
            .reindex(full_range)
            .rename_axis('mese')
            .reset_index()
        )
        serie['spesa_totale'] = pd.to_numeric(serie['spesa_totale'], errors='coerce').fillna(0.0)

        x_min = serie['mese'].min()
        x_max = serie['mese'].max()
        x_padding = pd.Timedelta(days=1)
        x_range = [x_min - x_padding, x_max + x_padding]

        n_punti = len(serie)
        x_axis_cfg = dict(
            tickformat='%m/%Y',
            tickmode='array',
            tickvals=serie['mese'].dropna().drop_duplicates().tolist(),
            tickangle=0,
            tickfont=dict(size=16, color='#1e293b', family='Arial', weight='bold'),
            showgrid=False,
            showline=False,
        )
        y_axis_cfg = dict(
            nticks=7,
            tickprefix='€',
            tickformat='.0f',
            tickfont=dict(size=16, color='#1e293b', family='Arial', weight='bold'),
            gridcolor='rgba(229,231,235,0.55)',
            gridwidth=1,
            zeroline=False,
            showline=False,
        )

        # --- Mini-legend chips (spesa + media) ---
        st.markdown(
            """
            <div style="display:flex; gap:20px; align-items:center; margin-bottom:0.5rem; flex-wrap:wrap; padding-left:4px;">
                <span style="display:inline-flex; align-items:center; gap:7px; font-size:0.80rem; color:#374151; font-weight:600; letter-spacing:0.01em;">
                    <svg width="22" height="4"><rect y="0" width="22" height="4" rx="2" fill="#2563eb"/></svg>
                    Spesa mensile
                </span>
                <span style="display:inline-flex; align-items:center; gap:7px; font-size:0.80rem; color:#374151; font-weight:600; letter-spacing:0.01em;">
                    <svg width="22" height="4"><line x1="0" y1="2" x2="22" y2="2" stroke="#dc2626" stroke-width="2.5" stroke-dasharray="5,3"/></svg>
                    Media periodo
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Grafico principale: spesa mensile + linea media
        fig = px.line(serie, x='mese', y='spesa_totale', markers=True, labels={'mese': '', 'spesa_totale': ''})
        fig.update_traces(
            line=dict(color='#2563eb', width=3.6, shape='spline'),
            marker=dict(size=10, color='#2563eb', line=dict(color='#ffffff', width=2)),
            hovertemplate='<b>%{x|%m/%Y}</b><br><b>€%{y:,.0f}</b><extra></extra>',
        )
        fig.add_scatter(
            x=serie['mese'].tolist(),
            y=[media_periodo] * len(serie),
            mode='lines',
            line=dict(color='#dc2626', width=2.5, dash='dash'),
            showlegend=False,
            hovertemplate=f'Media: €{media_periodo:,.0f}<extra></extra>',
        )
        fig.add_annotation(
            x=0.015, xref='paper', y=media_periodo, yref='y',
            text=f"<b>Media €{media_periodo:,.0f}</b>",
            showarrow=False, xanchor='left', yanchor='bottom', yshift=8,
            font=dict(color='#dc2626', size=13, family='Arial'),
            bgcolor='rgba(255,255,255,0.88)',
            bordercolor='#dc2626', borderwidth=1, borderpad=4,
        )
        fig.update_layout(
            height=400, hovermode='x unified', margin=dict(t=20, b=10, l=10, r=80),
            xaxis=x_axis_cfg, yaxis=y_axis_cfg,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='#ffffff',
            font=dict(size=13, color='#374151', family='Arial'), showlegend=False,
        )
        fig.update_xaxes(range=x_range)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        riepilogo_periodo = (
            f"📋 Mesi: {mesi_disponibili:,} | "
            f"💰 Totale periodo: € {totale_periodo:,.0f} | "
            f"📊 Media periodo: € {media_periodo:,.0f}"
        )
        st.markdown(
            f"""
            <div style="background-color: #E3F2FD; padding: 0.6rem 1rem; border-radius: 8px; border: 2px solid #2196F3; width: fit-content;">
                <p style="color: #1565C0; font-size: 0.95rem; font-weight: bold; margin: 0; white-space: nowrap;">
                    {riepilogo_periodo}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    # Recupera user_id da session_state (necessario per get_fatture_stats)
    try:
        user_id = st.session_state.user_data["id"]
    except (KeyError, TypeError):
        st.error("❌ Sessione invalida. Effettua il login.")
        st.stop()
    
    # Separa F&B da Spese Generali solo per categoria (NON escludere fornitori)
    # ⚡ PERFORMANCE: Calcola Data_DT UNA VOLTA su df_completo PRIMA di splittare
    if "Data_DT" not in df_completo.columns:
        df_completo["Data_DT"] = pd.to_datetime(df_completo["DataDocumento"], errors='coerce').dt.date
    
    mask_spese = df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
    df_spese_generali_completo = df_completo[mask_spese]
    
    # F&B: Escludi solo le categorie spese generali (NON i fornitori)
    df_food_completo = df_completo[~mask_spese]
    
    # ============================================
    # CATEGORIZZAZIONE AI
    # ============================================
    
    # Conta righe da classificare VELOCEMENTE dal DataFrame locale (ZERO query Supabase)
    # I dati sono già stati caricati da carica_e_prepara_dataframe() che è cached
    # Calcola maschera locale per sapere quali descrizioni processare (dal df_completo locale)
    maschera_ai = (
        df_completo['Categoria'].isna()
        | (df_completo['Categoria'] == 'Da Classificare')
        | (df_completo['Categoria'].astype(str).str.strip() == '')
        | (df_completo['Categoria'] == '')
    )
    
    # Conta dal DataFrame locale (istantaneo, nessuna query HTTP)
    righe_da_classificare = maschera_ai.sum()
    if 'Descrizione' in df_completo.columns:
        descrizioni_da_classificare = set(df_completo[maschera_ai]['Descrizione'].dropna().unique())
    else:
        descrizioni_da_classificare = set()
    
    # ============================================================
    # CATEGORIZZAZIONE AI (triggerata dal bottone nella sezione upload)
    # ============================================================
    if st.session_state.pop('trigger_ai_categorize', False):
        st.session_state.ai_categorization_in_progress = True
        try:
            # Sopprimi i messaggi dell'uploader nel rerun successivo
            st.session_state.suppress_upload_messages_once = True
            # ============================================================
            # VERIFICA FINALE (sicurezza)
            # ============================================================
            if righe_da_classificare == 0:
                st.warning("⚠️ Nessun prodotto da classificare")
            else:
                # ============================================================
                # CHIAMATA AI (SOLO DESCRIZIONI DA CLASSIFICARE)
                # ============================================================
                # 🔧 FIX: Query DIRETTA al DB per evitare problema filtri locali su df_completo
                try:
                    # Query tutte le descrizioni che hanno categoria NULL, "Da Classificare" o stringa vuota
                    _ristorante_id = st.session_state.get('ristorante_id')

                    # Loop paginato: utenti con >1000 fatture non classificate ricevono classificazione completa
                    tutti_dati = []
                    _offset_ai = 0
                    _page_ai = 1000
                    while True:
                        _q_all = (
                            supabase.table("fatture")
                            .select("id, descrizione, fornitore, prezzo_unitario, iva_percentuale")
                            .eq("user_id", user_id)
                            .or_("categoria.is.null,categoria.eq.,categoria.eq.Da Classificare")
                        )
                        if _ristorante_id:
                            _q_all = _q_all.eq("ristorante_id", _ristorante_id)
                        _resp_all = _q_all.range(_offset_ai, _offset_ai + _page_ai - 1).execute()
                        _batch = _resp_all.data or []
                        if not _batch:
                            break
                        tutti_dati.extend(_batch)
                        if len(_batch) < _page_ai:
                            break
                        _offset_ai += _page_ai
                    
                    descrizioni_da_classificare = list(set([row['descrizione'] for row in tutti_dati if row.get('descrizione')]))
                    fornitori_da_classificare = list(set([row['fornitore'] for row in tutti_dati if row.get('fornitore')]))

                    # Mapping per-descrizione: mantiene fornitore e IVA allineati con la descrizione
                    # (una stessa descrizione può venire da più righe; scegliamo l'ultima occorrenza non-nulla)
                    desc_to_fornitore: dict = {}
                    desc_to_iva: dict = {}
                    desc_to_row_ids: dict = {}
                    for _row in tutti_dati:
                        _d = _row.get('descrizione')
                        if not _d:
                            continue
                        _row_id = _row.get('id')
                        _forn = _row.get('fornitore') or ''
                        _iva = int(_row.get('iva_percentuale') or 0)
                        if _row_id is not None:
                            desc_to_row_ids.setdefault(_d, []).append(_row_id)
                        if _forn and _d not in desc_to_fornitore:
                            desc_to_fornitore[_d] = _forn
                        if _iva and _d not in desc_to_iva:
                            desc_to_iva[_d] = _iva
                    
                    # 🛡️ QUARANTENA: Identifica descrizioni che hanno ALMENO una riga €0
                    # Queste NON andranno in memoria globale (restano in attesa di review admin)
                    _descrizioni_con_prezzo_zero = set()
                    for row in tutti_dati:
                        desc = row.get('descrizione')
                        prezzo = row.get('prezzo_unitario', 0) or 0
                        if desc and float(prezzo) == 0:
                            _descrizioni_con_prezzo_zero.add(desc)
                    logger.info(f"🛡️ QUARANTENA: {len(_descrizioni_con_prezzo_zero)} descrizioni con righe €0 (escluse da memoria globale)")
                    
                    logger.info(
                        f"🔍 Query diretta DB: trovate {len(descrizioni_da_classificare)} descrizioni uniche da classificare"
                    )
                except Exception as e:
                    logger.error(f"Errore query diretta descrizioni: {e}")
                    # Fallback su df_completo se query fallisce
                    descrizioni_da_classificare = df_completo[maschera_ai]['Descrizione'].unique().tolist()
                    fornitori_da_classificare = df_completo[maschera_ai]['Fornitore'].unique().tolist()
                    # Fallback mapping per-descrizione da DataFrame
                    desc_to_fornitore = {}
                    desc_to_iva = {}
                    desc_to_row_ids = {}
                    if 'Fornitore' in df_completo.columns:
                        for _, _r in df_completo[maschera_ai].iterrows():
                            _d = _r.get('Descrizione')
                            if _d and _d not in desc_to_fornitore:
                                desc_to_fornitore[_d] = str(_r.get('Fornitore') or '')
                            if _d and _d not in desc_to_iva and 'IVAPercentuale' in df_completo.columns:
                                _iva = int(_r.get('IVAPercentuale') or 0)
                                if _iva:
                                    desc_to_iva[_d] = _iva
                    # Fallback quarantena: usa TotaleRiga dal DataFrame locale
                    _descrizioni_con_prezzo_zero = set()
                    if 'TotaleRiga' in df_completo.columns:
                        _mask_zero = maschera_ai & (df_completo['TotaleRiga'] == 0)
                        _descrizioni_con_prezzo_zero = set(df_completo[_mask_zero]['Descrizione'].dropna().unique())
                    logger.info(f"🛡️ QUARANTENA (fallback): {len(_descrizioni_con_prezzo_zero)} descrizioni €0")
            
            if descrizioni_da_classificare:
                    # 🧠 Placeholder per banner orizzontale
                    progress_placeholder = st.empty()
                    
                    # Mostra banner immediatamente con 0%
                    totale_da_classificare = len(descrizioni_da_classificare)
                    progress_placeholder.markdown(f"""
                    <div class="ai-banner">
                        <div class="brain-pulse-banner">🧠</div>
                        <div class="progress-percentage">0%</div>
                        <div class="progress-status">0 di {totale_da_classificare} prodotti</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # CSS per banner orizzontale con pulsazione cervelletto — ora in static/common.css
                    
                    # � PRE-STEP: Controlla memoria (admin > locale > globale) PRIMA di keyword/AI
                    # Invalida cache per avere dati aggiornati (altri utenti potrebbero aver categorizzato)
                    invalida_cache_memoria()
                    carica_memoria_completa(user_id)
                    
                    mappa_categorie = {}  # desc -> categoria
                    prodotti_elaborati = 0  # Contatore per banner
                    descrizioni_dopo_memoria = []  # Quelle NON risolte dalla memoria
                    desc_to_hint: dict = {}  # desc -> hint categoria (confidence 'media')
                    
                    # Resetta tracking Fonte per il nuovo run AI
                    st.session_state.righe_memoria_appena_categorizzate = []
                    st.session_state.righe_keyword_appena_categorizzate = []
                    st.session_state.righe_ai_appena_categorizzate = []
                    _tracking_memoria_set = set()
                    
                    for desc in descrizioni_da_classificare:
                        cat_memoria = ottieni_categoria_prodotto(desc, user_id)
                        if cat_memoria and cat_memoria != 'Da Classificare':
                            mappa_categorie[desc] = cat_memoria
                            prodotti_elaborati += 1
                            # Aggiorna banner in tempo reale
                            percentuale = (prodotti_elaborati / totale_da_classificare) * 100
                            if prodotti_elaborati % 5 == 0 or prodotti_elaborati == totale_da_classificare:
                                progress_placeholder.markdown(f"""
                            <div class="ai-banner">
                                <div class="brain-pulse-banner">🧠</div>
                                <div class="progress-percentage">{int(percentuale)}%</div>
                                <div class="progress-status">{prodotti_elaborati} di {totale_da_classificare} prodotti</div>
                            </div>
                            """, unsafe_allow_html=True)
                            # Traccia per colonna Fonte 📚
                            if desc not in _tracking_memoria_set:
                                _tracking_memoria_set.add(desc)
                                st.session_state.righe_memoria_appena_categorizzate.append(desc)
                            logger.info(f"📦 MEMORIA: '{desc[:TRUNCATE_DESC_LOG]}' → {cat_memoria}")
                        else:
                            # Controlla se c'è un hint da confidence 'media' in prodotti_master
                            hint = ottieni_hint_per_ai(desc, user_id)
                            if hint:
                                desc_to_hint[desc] = hint
                                logger.info(f"💡 HINT: '{desc[:TRUNCATE_DESC_LOG]}' → suggerisco '{hint}' all'AI")
                            descrizioni_dopo_memoria.append(desc)
                    
                    if prodotti_elaborati > 0:
                        logger.info(f"📦 PRE-STEP MEMORIA: {prodotti_elaborati} descrizioni risolte dalla memoria globale")
                    
                    # 🧠 STEP 1: Invia all'AI tutte le descrizioni non risolte dalla memoria
                    # Il dizionario interviene SOLO come fallback post-AI per i "Da Classificare" rimasti
                    descrizioni_per_ai = list(descrizioni_dopo_memoria)
                    chunk_size = 30
                    
                    if descrizioni_per_ai:
                        # 🔒 BUDGET GIORNALIERO AI: limita chiamate per sessione/giorno
                        _today = datetime.now(timezone.utc).date().isoformat()
                        if st.session_state.get('_ai_budget_date') != _today:
                            st.session_state['_ai_budget_date'] = _today
                            st.session_state['_ai_budget_calls'] = 0
                        
                        _ai_calls_today = st.session_state.get('_ai_budget_calls', 0)
                        _ai_chunks_needed = (len(descrizioni_per_ai) + chunk_size - 1) // chunk_size
                        if _ai_calls_today + _ai_chunks_needed >= MAX_AI_CALLS_PER_DAY:
                            _remaining = max(0, MAX_AI_CALLS_PER_DAY - _ai_calls_today)
                            st.warning(f"⚠️ Limite giornaliero AI raggiunto ({MAX_AI_CALLS_PER_DAY} chiamate/giorno). "
                                       f"Rimanenti: {_remaining}. Le descrizioni non classificate resteranno 'Da Classificare'.")
                            logger.warning(f"🔒 Budget AI giornaliero esaurito: {_ai_calls_today} chiamate, servirebbero {_ai_chunks_needed}")
                            descrizioni_per_ai = []  # svuota lista per saltare il loop AI
                        
                        _num_chunks = (len(descrizioni_per_ai) + chunk_size - 1) // chunk_size
                        for i in range(0, len(descrizioni_per_ai), chunk_size):
                            chunk = descrizioni_per_ai[i:i+chunk_size]
                            _chunk_num = i // chunk_size + 1
                            # ⏳ Mostra banner ATTESA prima della chiamata bloccante a OpenAI
                            _perc_attesa = int((prodotti_elaborati / totale_da_classificare) * 100)
                            progress_placeholder.markdown(f"""
                            <div class="ai-banner">
                                <div class="brain-pulse-banner">🧠</div>
                                <div class="progress-percentage">{_perc_attesa}%</div>
                                <div class="progress-status">{prodotti_elaborati} di {totale_da_classificare} prodotti</div>
                            </div>
                            """, unsafe_allow_html=True)
                            try:
                                cats, confs = classifica_via_worker_con_confidenza(
                                    chunk,
                                    fornitori=[desc_to_fornitore.get(d, '') for d in chunk],
                                    iva=[desc_to_iva.get(d, 0) for d in chunk],
                                    hint=[desc_to_hint.get(d) for d in chunk],
                                    user_id=user_id,
                                    ristorante_id=st.session_state.get('ristorante_id'),
                                )
                            except Exception as ai_exc:
                                logger.error(f"❌ classifica_via_worker fallita per chunk {_chunk_num}: {ai_exc}")
                                cats = ["Da Classificare"] * len(chunk)
                                confs = ["bassa"] * len(chunk)
                            st.session_state['_ai_budget_calls'] = st.session_state.get('_ai_budget_calls', 0) + 1
                            ai_batch_upsert = []
                            needs_review_row_ids = []  # righe Da Classificare o bassa confidence
                            for desc, cat, conf in zip(chunk, cats, confs):
                                cat, override_reason = applica_regole_categoria_forti(desc, cat)
                                if override_reason:
                                    conf = "alta"  # override sicurezza → alta
                                    logger.info(
                                        f"🧭 OVERRIDE SICUREZZA (AI): '{desc[:TRUNCATE_DESC_LOG]}' -> {cat} [{override_reason}]"
                                    )
                                mappa_categorie[desc] = cat
                                prodotti_elaborati += 1

                                # 🧠 Aggiorna banner dopo ogni prodotto (AI step: nessuna soglia)
                                percentuale = (prodotti_elaborati / totale_da_classificare) * 100
                                if prodotti_elaborati % 5 == 0 or prodotti_elaborati == totale_da_classificare:
                                    progress_placeholder.markdown(f"""
                                    <div class="ai-banner">
                                        <div class="brain-pulse-banner">🧠</div>
                                        <div class="progress-percentage">{int(percentuale)}%</div>
                                        <div class="progress-status">{prodotti_elaborati} di {totale_da_classificare} prodotti</div>
                                    </div>
                                    """, unsafe_allow_html=True)

                                # Raccoglie righe Da Classificare o bassa confidence per needs_review
                                _is_da_class = (cat == "Da Classificare")
                                _is_bassa = (conf == "bassa")
                                if _is_da_class or _is_bassa:
                                    _row_ids_for_review = desc_to_row_ids.get(desc) or []
                                    needs_review_row_ids.extend(_row_ids_for_review)
                                    if _is_da_class:
                                        logger.info(f"⏭️ Da Classificare (needs_review): '{desc[:TRUNCATE_DESC_LOG]}'")
                                    else:
                                        logger.info(f"⚠️ Confidence bassa (needs_review): '{desc[:TRUNCATE_DESC_LOG]}' → {cat}")

                                if cat and cat != "Da Classificare" and conf != "bassa":
                                    # 🛡️ QUARANTENA: Escludi descrizioni €0 dalla memoria locale automatica
                                    if desc not in _descrizioni_con_prezzo_zero:
                                        ai_batch_upsert.append({
                                            'user_id': user_id,
                                            'descrizione': desc,
                                            'categoria': cat,
                                            'volte_visto': 1,
                                            'classificato_da': 'AI (auto)',
                                            'updated_at': datetime.now(timezone.utc).isoformat(),
                                            'created_at': datetime.now(timezone.utc).isoformat(),
                                        })
                                    else:
                                        logger.info(f"🛡️ QUARANTENA AI: '{desc[:60]}' → {cat} (€0, escluso da memoria automatica)")
                            
                            # 💾 Batch upsert memoria LOCALE per AI (singola query per chunk)
                            if ai_batch_upsert:
                                try:
                                    _ai_result = supabase.table('prodotti_utente').upsert(
                                        ai_batch_upsert, on_conflict='user_id,descrizione'
                                    ).execute()
                                    _ai_saved = len(_ai_result.data) if _ai_result.data else 0
                                    logger.info(f"💾 BATCH AI LOCALE: {_ai_saved}/{len(ai_batch_upsert)} prodotti salvati in memoria utente")
                                except Exception as e:
                                    logger.error(f"Errore batch salvataggio memoria locale AI: {e}")

                            # ⚠️ Batch UPDATE needs_review=True per Da Classificare / bassa confidence
                            if needs_review_row_ids:
                                try:
                                    _nr_ids = list(set(needs_review_row_ids))
                                    supabase.table('fatture').update({'needs_review': True}).in_('id', _nr_ids).execute()
                                    logger.info(f"⚠️ NEEDS_REVIEW: {len(_nr_ids)} righe marcate per review manuale")
                                except Exception as e:
                                    logger.error(f"Errore batch update needs_review: {e}")
                        
                        # Invalida cache una sola volta dopo tutti i chunk
                        invalida_cache_memoria()


                    # Aggiorna categorie su Supabase
                    try:
                        user_id = st.session_state.user_data["id"]
                        
                        righe_aggiornate_totali = 0
                        descrizioni_non_trovate = []
                        descrizioni_aggiornate = []  # Per icone AI: solo quelle realmente aggiornate
                        
                        # normalizza_stringa già importata al top-level
                        
                        logger.info(f"🔄 INIZIO UPDATE: {len(mappa_categorie)} descrizioni da aggiornare")
                        
                        # DEBUG: Log prime 10 categorie dall'AI
                        logger.info("🧠 CATEGORIE RESTITUITE DALL'AI (prime 10)")
                        for i, (desc, cat) in enumerate(list(mappa_categorie.items())[:10]):
                            cat_display = f"'{cat}'" if cat else "VUOTA/NULL"
                            logger.info(f"   [{i+1}] '{desc[:TRUNCATE_DESC_LOG]}' → {cat_display}")
                        
                        # ⚡ OTTIMIZZAZIONE: Raggruppa descrizioni per categoria per batch UPDATE
                        # Invece di 1 query per descrizione (N+1), facciamo 1 query per categoria
                        cat_to_descs = {}  # {categoria: [descrizione, ...]}
                        cat_to_row_ids = {}  # {categoria: set(row_id, ...)}
                        da_classificare_row_ids = []  # righe con cat=Da Classificare da marcare needs_review
                        for desc, cat in mappa_categorie.items():
                            if not cat or cat.strip() == '':
                                logger.warning(f"⚠️ Categoria vuota/NULL per '{desc[:TRUNCATE_DESC_LOG]}', skip update")
                                continue
                            if cat == "Da Classificare":
                                # non aggiorniamo categoria, ma marchiamo needs_review
                                _dc_ids = desc_to_row_ids.get(desc) or []
                                da_classificare_row_ids.extend(_dc_ids)
                                logger.info(f"⏭️ Skip update categoria per '{desc[:TRUNCATE_DESC_LOG]}' → Da Classificare (needs_review=""True"" impostato)")
                                continue
                            cat_to_descs.setdefault(cat, []).append(desc)
                            row_ids = desc_to_row_ids.get(desc) or []
                            if row_ids:
                                cat_to_row_ids.setdefault(cat, set()).update(row_ids)
                            else:
                                logger.warning(f"⚠️ Nessun row_id disponibile per '{desc[:TRUNCATE_DESC_LOG]}', userò fallback esatto")
                        
                        logger.info(f"⚡ BATCH UPDATE: {len(cat_to_descs)} categorie distinte per {sum(len(v) for v in cat_to_descs.values())} descrizioni")
                        
                        # FASE 1: Batch UPDATE per categoria usando gli id riga letti dal DB
                        descs_non_matchate = {}  # {desc_orig: cat} - fallback individuale
                        
                        for cat, desc_list in cat_to_descs.items():
                            row_ids = sorted(cat_to_row_ids.get(cat, set()))

                            if not row_ids:
                                logger.info(f"ℹ️ Nessun row_id batch per {cat}, passo al fallback esatto per {len(desc_list)} descrizioni")
                                for desc_orig in desc_list:
                                    descs_non_matchate[desc_orig] = cat
                                continue
                            
                            # Batch UPDATE con tutte le righe note per questa categoria
                            try:
                                query_batch = supabase.table("fatture").update(
                                    {"categoria": cat}
                                ).eq("user_id", user_id).in_("id", row_ids)
                                query_batch = add_ristorante_filter(query_batch)
                                result_batch = query_batch.execute()
                                
                                matched_count = len(result_batch.data) if result_batch.data else 0
                                matched_ids = {row['id'] for row in result_batch.data} if result_batch.data else set()
                                
                                if matched_count > 0:
                                    logger.info(f"⚡ Batch {cat}: {matched_count} righe aggiornate")
                                
                                righe_aggiornate_totali += matched_count
                                
                                # Identifica descrizioni matchate per tracking
                                for desc_orig in desc_list:
                                    desc_row_ids = set(desc_to_row_ids.get(desc_orig) or [])
                                    if desc_row_ids and desc_row_ids.issubset(matched_ids):
                                        descrizioni_aggiornate.append(desc_orig)
                                    else:
                                        descs_non_matchate[desc_orig] = cat
                                
                            except Exception as batch_err:
                                logger.warning(f"⚠️ Batch UPDATE fallito per {cat}: {batch_err}, fallback individuale")
                                for desc_orig in desc_list:
                                    descs_non_matchate[desc_orig] = cat
                        
                        # FASE 2: Fallback individuale SOLO per descrizioni non matchate dal batch
                        # Conservativo: match esatti בלבד, mai ILIKE parziale per evitare update espansivi.
                        if descs_non_matchate:
                            logger.info(f"🔄 Fallback individuale per {len(descs_non_matchate)} descrizioni non matchate")
                        
                        for desc, cat in descs_non_matchate.items():
                            num_aggiornate = 0
                            row_ids = desc_to_row_ids.get(desc) or []

                            if row_ids:
                                try:
                                    query_update_ids = supabase.table("fatture").update(
                                        {"categoria": cat}
                                    ).eq("user_id", user_id).in_("id", row_ids)
                                    query_update_ids = add_ristorante_filter(query_update_ids)
                                    result_ids = query_update_ids.execute()
                                    num_aggiornate = len(result_ids.data) if result_ids.data else 0
                                    if num_aggiornate > 0:
                                        logger.info(f"✅ Match ID: '{desc[:TRUNCATE_DESC_LOG]}...' ({num_aggiornate} righe)")
                                except Exception as _e_ids:
                                    logger.debug(f"Fallback id per '{desc[:TRUNCATE_DESC_QUERY]}': {_e_ids}")
                            
                            # Tentativo con descrizione originale (non normalizzata)
                            if num_aggiornate == 0:
                                try:
                                    query_update2 = supabase.table("fatture").update(
                                        {"categoria": cat}
                                    ).eq("user_id", user_id).eq("descrizione", desc)
                                    query_update2 = add_ristorante_filter(query_update2)
                                    result2 = query_update2.execute()
                                    num_aggiornate = len(result2.data) if result2.data else 0
                                    if num_aggiornate > 0:
                                        logger.info(f"✅ Match desc originale: '{desc[:TRUNCATE_DESC_LOG]}...' ({num_aggiornate} righe)")
                                except Exception as _e_orig:
                                    logger.debug(f"Fallback desc originale per '{desc[:TRUNCATE_DESC_QUERY]}': {_e_orig}")
                            
                            # Tentativo con trim
                            if num_aggiornate == 0:
                                desc_trimmed = desc.strip()
                                if desc_trimmed != desc:
                                    try:
                                        query_update3 = supabase.table("fatture").update(
                                            {"categoria": cat}
                                        ).eq("user_id", user_id).eq("descrizione", desc_trimmed)
                                        query_update3 = add_ristorante_filter(query_update3)
                                        result3 = query_update3.execute()
                                        num_aggiornate = len(result3.data) if result3.data else 0
                                        if num_aggiornate > 0:
                                            logger.info(f"✅ Match trim: '{desc_trimmed[:TRUNCATE_DESC_LOG]}...' ({num_aggiornate} righe)")
                                    except Exception as _e_trim:
                                        logger.debug(f"Fallback trim per '{desc[:TRUNCATE_DESC_QUERY]}': {_e_trim}")
                            
                            # Tentativo ILIKE case-insensitive solo esatto, mai parziale
                            if num_aggiornate == 0 and len(desc.strip()) >= 3:
                                try:
                                    query_update4 = supabase.table("fatture").update(
                                        {"categoria": cat}
                                    ).eq("user_id", user_id).ilike("descrizione", desc.strip())
                                    query_update4 = add_ristorante_filter(query_update4)
                                    result4 = query_update4.execute()
                                    num_aggiornate = len(result4.data) if result4.data else 0
                                    if num_aggiornate > 0:
                                        logger.info(f"✅ Match ILIKE esatto: '{desc[:TRUNCATE_DESC_LOG]}...' ({num_aggiornate} righe)")
                                except Exception as ilike_err:
                                    logger.warning(f"Errore ILIKE update '{desc[:TRUNCATE_DESC_QUERY]}...': {ilike_err}")
                            
                            if num_aggiornate == 0:
                                descrizioni_non_trovate.append(desc)
                                logger.error(f"❌ NESSUN MATCH per: '{desc}' (cat: {cat})")
                            
                            righe_aggiornate_totali += num_aggiornate
                            if num_aggiornate > 0:
                                descrizioni_aggiornate.append(desc)
                                logger.info(f"✅ AGGIORNATO '{desc[:TRUNCATE_DESC_LOG]}...' → {cat} ({num_aggiornate} righe)")
                        
                        # 🔧 FALLBACK: Applica dizionario ai prodotti rimasti "Da Classificare"
                        try:
                            _all_check = []
                            _offset_chk = 0
                            _page_chk = 1000
                            while True:
                                _q_chk = (
                                    supabase.table("fatture")
                                    .select("descrizione, categoria")
                                    .eq("user_id", user_id)
                                    .or_("categoria.is.null,categoria.eq.,categoria.eq.Da Classificare")
                                )
                                _q_chk = add_ristorante_filter(_q_chk)
                                _r_chk = _q_chk.range(_offset_chk, _offset_chk + _page_chk - 1).execute()
                                _batch_chk = _r_chk.data or []
                                if not _batch_chk:
                                    break
                                _all_check.extend(_batch_chk)
                                if len(_batch_chk) < _page_chk:
                                    break
                                _offset_chk += _page_chk

                            if _all_check:
                                df_temp = pd.DataFrame(_all_check)
                                ancora_da_class = df_temp[
                                    (df_temp['categoria'].isna()) | (df_temp['categoria'] == 'Da Classificare')
                                ]['descrizione'].unique()
                                
                                if len(ancora_da_class) > 0:
                                    logger.info(f"🔧 FALLBACK: Tentando categorizzazione con dizionario per {len(ancora_da_class)} prodotti rimasti...")
                                    
                                    # ⚡ BATCH: Raggruppa per categoria prima di fare query
                                    _fb_cat_to_descs = {}  # {categoria: [desc1, desc2, ...]}
                                    for desc in ancora_da_class:
                                        # Prima prova regole forti (più precise), poi dizionario
                                        cat_forte = applica_regole_categoria_forti(desc)
                                        if cat_forte:
                                            _fb_cat_to_descs.setdefault(cat_forte, []).append(desc)
                                            continue
                                        cat_dizionario = applica_correzioni_dizionario(desc, "Da Classificare")
                                        if cat_dizionario and cat_dizionario != 'Da Classificare':
                                            _fb_cat_to_descs.setdefault(cat_dizionario, []).append(desc)
                                        else:
                                            logger.warning(f"⚠️ '{desc[:TRUNCATE_DESC_LOG]}...' rimane Da Classificare - richiede intervento manuale")
                                    
                                    ristorante_id = st.session_state.get('ristorante_id')
                                    for _fb_cat, _fb_descs in _fb_cat_to_descs.items():
                                        try:
                                            # Batch update: tutte le descrizioni con stessa categoria
                                            query_fallback = supabase.table('fatture').update(
                                                {'categoria': _fb_cat}
                                            ).eq('user_id', user_id).in_('descrizione', [d.strip() for d in _fb_descs])
                                            if ristorante_id:
                                                query_fallback = query_fallback.eq('ristorante_id', ristorante_id)
                                            righe_updated = query_fallback.execute()
                                            _fb_count = len(righe_updated.data) if righe_updated.data else 0
                                            righe_aggiornate_totali += _fb_count
                                            if _fb_count > 0:
                                                logger.info(f"✅ Fallback batch {_fb_cat}: {_fb_count} righe ({len(_fb_descs)} desc)")
                                        except Exception as fb_err:
                                            logger.warning(f"Errore fallback batch {_fb_cat}: {fb_err}")
                        except Exception as fb_err:
                            logger.warning(f"Errore fallback categorizzazione: {fb_err}")
                        
                        # ⚠️ Batch UPDATE needs_review=True per righe Da Classificare (da update-loop)
                        if da_classificare_row_ids:
                            try:
                                _dc_ids_unique = list(set(da_classificare_row_ids))
                                supabase.table('fatture').update({'needs_review': True}).in_('id', _dc_ids_unique).execute()
                                logger.info(f"⚠️ NEEDS_REVIEW (update-loop): {len(_dc_ids_unique)} righe Da Classificare marcate")
                            except Exception as _nr_err:
                                logger.error(f"Errore batch update needs_review (Da Classificare): {_nr_err}")

                        # ✅ Pulisci placeholder progress
                        progress_placeholder.empty()
                        
                        # 🧠 SALVA in session state le descrizioni categorizzate PER FONTE
                        # AI: solo quelle inviate all'AI (NON include keyword/dizionario)
                        # Keyword/Dizionario: già tracciate in righe_keyword_appena_categorizzate
                        descrizioni_solo_ai = [d for d in descrizioni_aggiornate if d in set(descrizioni_per_ai)] if descrizioni_aggiornate else list(set(descrizioni_per_ai) & set(mappa_categorie.keys()))
                        st.session_state.righe_ai_appena_categorizzate = descrizioni_solo_ai
                        logger.info(f"🧠 Fonte tracking: {len(descrizioni_solo_ai)} AI, {len(st.session_state.get('righe_keyword_appena_categorizzate', []))} keyword")

                        # 📈 STREAK: Aggiorna contatore per ogni descrizione classificata dal GPT
                        for _desc_ai in descrizioni_solo_ai:
                            _cat_ai = mappa_categorie.get(_desc_ai)
                            if _cat_ai:
                                aggiorna_streak_classificazione(_desc_ai, _cat_ai, supabase)

                        # DEBUG: Log per admin
                        logger.info(f"📊 RISULTATO FINALE: {righe_aggiornate_totali} righe aggiornate, {len(descrizioni_non_trovate)} non trovate")
                        
                        # 📊 Messaggio SEMPLICE - conteggio righe aggiornate vs descrizioni processate
                        num_descrizioni = len(mappa_categorie)
                        
                        if righe_aggiornate_totali > 0:
                            st.success(f"✅ {righe_aggiornate_totali} righe aggiornate ({num_descrizioni} prodotti distinti)")
                        else:
                            st.error(f"❌ Nessuna riga aggiornata! Controlla i log del terminale per i dettagli.")
                        
                        # Avviso se ci sono descrizioni non trovate
                        if descrizioni_non_trovate:
                            st.warning(f"⚠️ {len(descrizioni_non_trovate)} descrizioni non trovate nel database")
                        
                        logger.info(f"🎉 CATEGORIZZAZIONE: {righe_aggiornate_totali} righe, {num_descrizioni} descrizioni")
                        
                        # 🔍 VERIFICA POST-UPDATE: Conferma che DB è stato aggiornato correttamente
                        try:
                            _ristorante_id_v = st.session_state.get('ristorante_id')
                            _count_q = (
                                supabase.table('fatture')
                                .select('id', count='exact')
                                .eq('user_id', user_id)
                                .or_('categoria.is.null,categoria.eq.Da Classificare,categoria.eq.')
                            )
                            if _ristorante_id_v:
                                _count_q = _count_q.eq('ristorante_id', _ristorante_id_v)
                            _count_resp = _count_q.execute()
                            null_count = _count_resp.count or 0
                            logger.info(f"🔍 POST-UPDATE VERIFICA: {null_count} righe ancora NULL/Da Classificare")
                            
                            if null_count > 0:
                                logger.warning(f"⚠️ ATTENZIONE: {null_count} righe non categorizzate dopo AI")
                            else:
                                logger.info(f"✅ VERIFICA OK: Tutte le righe categorizzate correttamente nel DB")
                        except Exception as e:
                            logger.error(f"❌ Errore verifica post-update: {e}")
                        
                        # Pulisci cache PRIMA del delay per garantire ricaricamento
                        invalida_cache_memoria()
                        
                        # ⭐ FIX CRITICO: Imposta flag per forzare reload completo al prossimo caricamento
                        st.session_state.force_reload = True
                        st.session_state.force_empty_until_upload = False  # Assicura che i dati vengano caricati
                        st.session_state.editor_refresh_counter = st.session_state.get('editor_refresh_counter', 0) + 1
                        logger.info("🔄 Flag force_reload impostato su True")

                        # ⚡ PERF: nessuna pausa — Supabase è sincrono e la cache è già stata pulita sopra.
                        # Rerun per ricaricare dati freschi dal database
                        st.rerun()
                        
                    except Exception as e:
                        logger.exception("Errore aggiornamento categorie AI su Supabase")
                        logger.error(f"Errore aggiornamento categorie: {e}")
                        st.error("❌ Errore durante l'aggiornamento delle categorie. Riprova.")
        finally:
            st.session_state.ai_categorization_in_progress = False
    
    # Rimuovi il flag automaticamente quando tutti i file sono stati rimossi (dopo aver cliccato la X)
    if not uploaded_files and st.session_state.get("force_empty_until_upload"):
        st.session_state.force_empty_until_upload = False
        st.stop()
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # ============================================
    # FILTRO DROPDOWN PERIODO
    # ============================================
    from utils.period_helper import PERIODO_OPTIONS, calcola_date_periodo, risolvi_periodo
    
    st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📅 Filtra per Periodo</h3>", unsafe_allow_html=True)
    
    date_periodo = calcola_date_periodo()
    oggi_date = date_periodo['oggi']
    inizio_anno = date_periodo['inizio_anno']
    
    # Default: Anno in Corso
    if 'periodo_dropdown' not in st.session_state:
        st.session_state.periodo_dropdown = "🗓️ Anno in Corso"
    
    # Layout: selectbox + info box sulla stessa riga.
    # In alcuni test con mock incompleti st.columns puo' restituire una lista vuota.
    _cols_periodo = st.columns([1, 4])
    if isinstance(_cols_periodo, (list, tuple)) and len(_cols_periodo) >= 2:
        col_periodo, col_info_periodo = _cols_periodo[0], _cols_periodo[1]
    else:
        col_periodo = st.container()
        col_info_periodo = st.container()
    
    with col_periodo:
        periodo_selezionato = st.selectbox(
            "Periodo",
            options=PERIODO_OPTIONS,
            label_visibility="collapsed",
            index=PERIODO_OPTIONS.index(st.session_state.periodo_dropdown) if st.session_state.periodo_dropdown in PERIODO_OPTIONS else 0,
            key="filtro_periodo_main"
        )

    if periodo_selezionato not in PERIODO_OPTIONS:
        periodo_selezionato = st.session_state.periodo_dropdown
    
    # Aggiorna session state
    st.session_state.periodo_dropdown = periodo_selezionato
    
    # Gestione logica periodo
    data_inizio_filtro, data_fine_filtro, label_periodo = risolvi_periodo(periodo_selezionato, date_periodo)
    _is_widget_mode = data_inizio_filtro is None  # True per Seleziona Mese e Periodo Personalizzato

    with col_info_periodo:
        if periodo_selezionato == "📆 Seleziona Mese":
            from utils.period_helper import get_mesi_disponibili_fatture, risolvi_mese_selezionato
            from services import get_supabase_client as _get_sb
            _sb_dash = _get_sb()
            _uid_dash = st.session_state.user_data.get('id') if st.session_state.get('user_data') else None
            _rid_dash = st.session_state.get('ristorante_id')
            _mesi_dash = get_mesi_disponibili_fatture(_uid_dash, _rid_dash, _sb_dash)
            _mesi_labels_dash = [x[2] for x in _mesi_dash]
            if not _mesi_labels_dash:
                _mesi_labels_dash = [oggi_date.replace(day=1).strftime("%B %Y")]
            _col_mese_dash, _col_empty_dash = st.columns([1.2, 1.8])
            with _col_mese_dash:
                _mese_sel_dash = st.selectbox(
                    "Mese",
                    options=_mesi_labels_dash,
                    index=len(_mesi_labels_dash) - 1,
                    key="dash_mese_sel",
                    label_visibility="collapsed",
                )
            data_inizio_filtro, data_fine_filtro = risolvi_mese_selezionato(_mese_sel_dash, _mesi_dash)
            label_periodo = _mese_sel_dash
        elif _is_widget_mode:
            if 'data_inizio_filtro' not in st.session_state:
                st.session_state.data_inizio_filtro = inizio_anno
            if 'data_fine_filtro' not in st.session_state:
                st.session_state.data_fine_filtro = oggi_date
            _col_range, _col_empty = st.columns([1.2, 1.8])
            with _col_range:
                _range = st.date_input(
                    "Periodo",
                    value=(st.session_state.data_inizio_filtro, st.session_state.data_fine_filtro),
                    min_value=inizio_anno,
                    format="DD/MM/YYYY",
                    key="data_range_custom",
                    label_visibility="collapsed",
                )
            if isinstance(_range, (list, tuple)) and len(_range) == 2:
                data_inizio_custom, data_fine_custom = _range[0], _range[1]
                if data_inizio_custom > data_fine_custom:
                    st.error("⚠️ La data iniziale deve essere precedente alla data finale.")
                    data_inizio_filtro = st.session_state.data_inizio_filtro
                    data_fine_filtro = st.session_state.data_fine_filtro
                else:
                    st.session_state.data_inizio_filtro = data_inizio_custom
                    st.session_state.data_fine_filtro = data_fine_custom
                    data_inizio_filtro = data_inizio_custom
                    data_fine_filtro = data_fine_custom
            else:
                data_inizio_filtro = st.session_state.data_inizio_filtro
                data_fine_filtro = st.session_state.data_fine_filtro
            label_periodo = f"{data_inizio_filtro.strftime('%d/%m/%Y')} → {data_fine_filtro.strftime('%d/%m/%Y')}"

    # APPLICA FILTRO AI DATI
    # ⚡ Data_DT già calcolata prima dello split - le viste la ereditano automaticamente
    mask = (df_food_completo["Data_DT"] >= data_inizio_filtro) & (df_food_completo["Data_DT"] <= data_fine_filtro)
    df_food = df_food_completo[mask]
    
    mask_spese = (df_spese_generali_completo["Data_DT"] >= data_inizio_filtro) & (df_spese_generali_completo["Data_DT"] <= data_fine_filtro)
    df_spese_generali = df_spese_generali_completo[mask_spese]
    
    # Calcola giorni nel periodo
    giorni = (data_fine_filtro - data_inizio_filtro).days + 1
    
    # Stats globali: conta fatture PRIMA del filtro temporale (nel DF già pulito)
    num_fatture_totali_df = df_completo['FileOrigine'].nunique() if not df_completo.empty else 0
    num_righe_totali_df = len(df_completo)
    
    # Filtra df_completo per periodo (Data_DT già calcolata sopra)
    mask_completo = (df_completo["Data_DT"] >= data_inizio_filtro) & (df_completo["Data_DT"] <= data_fine_filtro)
    df_completo_filtrato = df_completo[mask_completo]
    num_doc_filtrati = df_completo_filtrato['FileOrigine'].nunique()
    
    # ⭐ FIX: allinea "Righe Totali" al periodo filtrato (come le card di spesa)
    num_righe_filtrate_periodo = len(df_completo_filtrato)
    
    # Mostra info periodo nel box accanto al selettore (solo per periodi preimpostati)
    info_testo = f"🗓️ {label_periodo} ({giorni} giorni) | 🍽️ Righe F&B: {len(df_food):,} | 📊 Righe Totali: {num_righe_filtrate_periodo:,} | 📄 Fatture: {num_doc_filtrati} di {num_fatture_totali_df}"
    if not _is_widget_mode:
        with col_info_periodo:
            st.markdown(f"""
            <div style="margin-top: 0; background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%); 
                        padding: 10px 16px; 
                        border-radius: 8px; 
                        border: 1px solid #93c5fd;
                        font-size: clamp(0.78rem, 1.8vw, 0.88rem);
                        font-weight: 500;
                        line-height: 1.5;
                        word-wrap: break-word;">
                {info_testo}
            </div>
            """, unsafe_allow_html=True)
    
    if df_food.empty and df_spese_generali.empty:
        st.warning("⚠️ Nessuna fattura nel periodo selezionato")
        st.stop()

    # Calcola variabili per i KPI
    # Regola KPI: somma sempre TotaleRiga (unico campo realmente per-riga e
    # filtrabile per categoria). TotaleImponibile è header replicato su tutte
    # le righe della fattura: sommarlo causerebbe inflazione N× (una volta per
    # riga) e renderebbe il filtro "tipo prodotto" non reattivo.
    def _sum_imponibile_fallback(df_source: pd.DataFrame) -> float:
        if df_source is None or df_source.empty:
            return 0.0
        totale_riga = pd.to_numeric(df_source.get('TotaleRiga'), errors='coerce').fillna(0.0)
        return float(totale_riga.sum())

    spesa_fb = _sum_imponibile_fallback(df_food)
    spesa_generale = _sum_imponibile_fallback(df_spese_generali)
    num_fornitori = df_food['Fornitore'].nunique()
    num_fatture_spese = df_spese_generali['FileOrigine'].nunique() if not df_spese_generali.empty else 0
    num_fornitori_spese = df_spese_generali['Fornitore'].nunique() if not df_spese_generali.empty else 0
    
    # Layout 6 colonne per i KPI - una card per metrica
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    # Calcola spesa totale
    spesa_totale = spesa_fb + spesa_generale
    
    # Calcola spesa media mensile (usa il PERIODO FILTRATO, non il dataset intero)
    # Conta i mesi UNICI nel periodo filtrato (data_inizio_filtro → data_fine_filtro)
    dates_filtered = df_completo_filtrato['Data_DT'].dropna()
    mesi_periodo = len({(d.year, d.month) for d in dates_filtered}) if not dates_filtered.empty else 0
    spesa_media = spesa_totale / mesi_periodo if mesi_periodo > 0 else 0
    
    # CSS per KPI caricato da static/layout.css (kpi-card styles)

    def _fmt_kpi_main(val):
        segno = "-" if val < 0 else ""
        return f"{segno}€{abs(val):,.0f}".replace(",", ".")

    def _kpi_html(label, value):
        return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """

    with col1:
        st.markdown(_kpi_html("💰 Spesa Totale", _fmt_kpi_main(spesa_totale)), unsafe_allow_html=True)

    with col2:
        st.markdown(_kpi_html("🔥 Spesa F&B", _fmt_kpi_main(spesa_fb)), unsafe_allow_html=True)

    with col3:
        st.markdown(_kpi_html("🏪 Fornit. F&B", str(num_fornitori)), unsafe_allow_html=True)

    with col4:
        st.markdown(_kpi_html("🏢 Fornit. Sp.Gen.", str(num_fornitori_spese)), unsafe_allow_html=True)

    with col5:
        st.markdown(_kpi_html("🛒 Spesa Generale", _fmt_kpi_main(spesa_generale)), unsafe_allow_html=True)

    with col6:
        st.markdown(_kpi_html("📊 Media Mensile", _fmt_kpi_main(spesa_media)), unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    st.markdown("---")
    
    # 🎨 NAVIGAZIONE CON BOTTONI COLORATI (invece di tab)
    if 'sezione_attiva' not in st.session_state:
        st.session_state.sezione_attiva = "dettaglio"
    # Redirect da sezioni rimosse
    if st.session_state.sezione_attiva in ("spese", "centri", "alert"):
        st.session_state.sezione_attiva = "categorie"
    if 'is_loading' not in st.session_state:
        st.session_state.is_loading = False
    
    st.markdown("<h3 style='color:#1e40af; font-weight:700;'>📊 Naviga tra le Sezioni</h3>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📦 DETTAGLIO\nARTICOLI", key="btn_dettaglio", use_container_width=True, 
                     type="primary" if st.session_state.sezione_attiva == "dettaglio" else "secondary"):
            if st.session_state.sezione_attiva != "dettaglio":
                st.session_state.sezione_attiva = "dettaglio"
                st.session_state.is_loading = True
                # Cambio schermata: pulisci riepilogo upload persistente
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    with col2:
        if st.button("📈 CATEGORIE", key="btn_categorie", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "categorie" else "secondary"):
            if st.session_state.sezione_attiva != "categorie":
                st.session_state.sezione_attiva = "categorie"
                st.session_state.is_loading = True
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    with col3:
        if st.button("🚚 FORNITORI", key="btn_fornitori", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "fornitori" else "secondary"):
            if st.session_state.sezione_attiva != "fornitori":
                st.session_state.sezione_attiva = "fornitori"
                st.session_state.is_loading = True
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    # CSS per bottoni colorati personalizzati — spostato all'inizio della funzione
    
    # Resetta il flag is_loading dopo il rerun
    if st.session_state.is_loading:
        st.session_state.is_loading = False
    
    # ========================================================
    # SEZIONE 1: DETTAGLIO ARTICOLI
    # ========================================================
    if st.session_state.sezione_attiva == "dettaglio":
        render_category_editor(df_completo_filtrato, supabase)

    if st.session_state.sezione_attiva == "categorie":
        if df_completo_filtrato.empty:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")
        else:
            col_filtro_cat, _ = st.columns([2, 5])
            with col_filtro_cat:
                # Inizializza con valore di default se non ancora in session_state
                if "tipo_filtro_categorie" not in st.session_state:
                    st.session_state.tipo_filtro_categorie = "Tutti"
                
                tipo_filtro_cat = st.selectbox(
                    "📦 Tipo Prodotti:",
                    options=["Food & Beverage", "Spese Generali", "Tutti"],
                    key="tipo_filtro_categorie",
                    help="Filtra per tipologia di prodotto"
                )
            
            if tipo_filtro_cat == "Food & Beverage":
                df_cat_source = df_completo_filtrato[~df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
            elif tipo_filtro_cat == "Spese Generali":
                df_cat_source = df_completo_filtrato[df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
            else:
                df_cat_source = df_completo_filtrato.copy()
            
            if df_cat_source.empty:
                st.info(f"📊 Nessun dato per '{tipo_filtro_cat}' nel periodo selezionato")
            else:
                try:
                    render_pivot_mensile(df_cat_source, 'Categoria', MESI_ITA, 'categorie', 'Categorie')
                    _render_spesa_tempo_sotto_tab(df_cat_source, 'Categoria', 'af_trend_categorie')
                except Exception as e:
                    logger.error(f"Errore in render_pivot_mensile (categorie): {e}", exc_info=True)
                    st.error(f"❌ Errore nel rendering della tabella categorie: {str(e)}")

    # ========================================================
    # SEZIONE 4: FORNITORI
    # ========================================================
    if st.session_state.sezione_attiva == "fornitori":
        if df_completo_filtrato.empty:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")
        else:
            col_filtro_forn, _ = st.columns([2, 5])
            with col_filtro_forn:
                # Inizializza con valore di default se non ancora in session_state
                if "tipo_filtro_fornitori" not in st.session_state:
                    st.session_state.tipo_filtro_fornitori = "Tutti"
                
                tipo_filtro_forn = st.selectbox(
                    "📦 Tipo Prodotti:",
                    options=["Food & Beverage", "Spese Generali", "Tutti"],
                    key="tipo_filtro_fornitori",
                    help="Filtra per tipologia di prodotto"
                )
            
            if tipo_filtro_forn == "Food & Beverage":
                df_forn_source = df_completo_filtrato[~df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
            elif tipo_filtro_forn == "Spese Generali":
                df_forn_source = df_completo_filtrato[df_completo_filtrato['Categoria'].isin(CATEGORIE_SPESE_GENERALI)].copy()
            else:
                df_forn_source = df_completo_filtrato.copy()
            
            if df_forn_source.empty:
                st.info(f"📊 Nessun dato per '{tipo_filtro_forn}' nel periodo selezionato")
            else:
                try:
                    render_pivot_mensile(df_forn_source, 'Fornitore', MESI_ITA, 'fornitori', 'Fornitori')
                    _render_spesa_tempo_sotto_tab(df_forn_source, 'Fornitore', 'af_trend_fornitori')
                except Exception as e:
                    logger.error(f"Errore in render_pivot_mensile (fornitori): {e}", exc_info=True)
                    st.error(f"❌ Errore nel rendering della tabella fornitori: {str(e)}")




