"""Dashboard principale - Statistiche, KPI, categorizzazione AI e navigazione sezioni."""

import streamlit as st
import pandas as pd
import time
import logging
from datetime import datetime, timezone

from config.constants import (
    CATEGORIE_SPESE_GENERALI,
    MESI_ITA,
    TRUNCATE_DESC_LOG,
    TRUNCATE_DESC_QUERY,
    UI_DELAY_MEDIUM,
    MAX_AI_CALLS_PER_DAY,
)

from utils.text_utils import normalizza_stringa, estrai_nome_categoria, escape_ilike as _escape_ilike
from utils.ui_helpers import load_css, render_pivot_mensile
from utils.ristorante_helper import add_ristorante_filter

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
from services.worker_client import classifica_via_worker

from components.category_editor import render_category_editor
from utils.app_controllers import is_admin_or_impersonating as _is_admin_or_impersonating


logger = logging.getLogger("fci_app")


def mostra_statistiche(df_completo, supabase, uploaded_files=None):
    """Mostra grafici, filtri e tabella dati"""
    
    if df_completo is None or df_completo.empty:
        st.info("📭 Nessun dato disponibile. Carica le tue prime fatture!")
        return
    
    # ===== 🔍 DEBUG CATEGORIZZAZIONE (SOLO ADMIN/IMPERSONIFICATO) =====
    if _is_admin_or_impersonating():
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
            st.dataframe(conteggio_cat, hide_index=True, width='stretch')
            
            st.markdown("**Esempio 15 righe (verifica categoria):**")
            sample_df = df_completo[['FileOrigine', 'Descrizione', 'Categoria', 'Fornitore', 'TotaleRiga']].head(15)
            st.dataframe(sample_df, hide_index=True, width='stretch')
            
            # Test query diretta Supabase
            if st.button("🔄 Ricarica da Supabase (bypass cache)", key="debug_reload"):
                invalida_cache_memoria()
                st.success("Cache invalidata. Dati ricaricati al prossimo accesso.")

        # ===== 🧠 MEMORIA GLOBALE AI (SOLO ADMIN) =====
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
    
    # ===== FILTRA DICITURE E RIGHE IN REVIEW DA DASHBOARD =====
    # Le righe needs_review=True vanno SOLO in Admin Panel
    righe_prima = len(df_completo)
    
    # Costruisci maschera esclusione
    mask_escludi = pd.Series([False] * len(df_completo), index=df_completo.index)
    
    # 1. Escludi TUTTE le NOTE E DICITURE (validate o meno)
    mask_note = df_completo['Categoria'].fillna('') == '📝 NOTE E DICITURE'
    mask_escludi = mask_escludi | mask_note
    
    # 2. Escludi righe in review (qualsiasi categoria)
    if 'needs_review' in df_completo.columns:
        mask_review = df_completo['needs_review'].fillna(False) == True
        mask_escludi = mask_escludi | mask_review
    
    # Applica filtro (MANTIENI righe NON escluse)
    df_completo = df_completo[~mask_escludi].copy()
    
    righe_dopo = len(df_completo)
    if righe_prima > righe_dopo:
        logger.info(f"Escluse da dashboard: {righe_prima - righe_dopo} righe (NOTE + review)")
    
    if df_completo.empty:
        st.info("📭 Nessun dato disponibile dopo i filtri.")
        return
    # ===== FINE FILTRO DICITURE E REVIEW =====
    
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
    descrizioni_da_classificare = set(df_completo[maschera_ai]['Descrizione'].dropna().unique())
    
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

                    # Query 1: NULL + stringa vuota collassate
                    _q_nullempty = (
                        supabase.table("fatture")
                        .select("descrizione, fornitore, prezzo_unitario, iva_percentuale")
                        .eq("user_id", user_id)
                        .or_("categoria.is.null,categoria.eq.")
                    )
                    if _ristorante_id:
                        _q_nullempty = _q_nullempty.eq("ristorante_id", _ristorante_id)
                    _resp_nullempty = _q_nullempty.execute()

                    # Query 2: Da Classificare
                    _q_daclass = (
                        supabase.table("fatture")
                        .select("descrizione, fornitore, prezzo_unitario, iva_percentuale")
                        .eq("user_id", user_id)
                        .eq("categoria", "Da Classificare")
                    )
                    if _ristorante_id:
                        _q_daclass = _q_daclass.eq("ristorante_id", _ristorante_id)
                    _resp_daclass = _q_daclass.execute()

                    _dati_nullempty = _resp_nullempty.data or []
                    _dati_daclass   = _resp_daclass.data or []
                    tutti_dati = _dati_nullempty + _dati_daclass
                    
                    descrizioni_da_classificare = list(set([row['descrizione'] for row in tutti_dati if row.get('descrizione')]))
                    fornitori_da_classificare = list(set([row['fornitore'] for row in tutti_dati if row.get('fornitore')]))

                    # Mapping per-descrizione: mantiene fornitore e IVA allineati con la descrizione
                    # (una stessa descrizione può venire da più righe; scegliamo l'ultima occorrenza non-nulla)
                    desc_to_fornitore: dict = {}
                    desc_to_iva: dict = {}
                    for _row in tutti_dati:
                        _d = _row.get('descrizione')
                        if not _d:
                            continue
                        _forn = _row.get('fornitore') or ''
                        _iva = int(_row.get('iva_percentuale') or 0)
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
                    
                    logger.info(f"🔍 Query diretta DB: trovate {len(descrizioni_da_classificare)} descrizioni uniche da classificare (NullEmpty: {len(_dati_nullempty)}, DaClass: {len(_dati_daclass)})")
                except Exception as e:
                    logger.error(f"Errore query diretta descrizioni: {e}")
                    # Fallback su df_completo se query fallisce
                    descrizioni_da_classificare = df_completo[maschera_ai]['Descrizione'].unique().tolist()
                    fornitori_da_classificare = df_completo[maschera_ai]['Fornitore'].unique().tolist()
                    # Fallback mapping per-descrizione da DataFrame
                    desc_to_fornitore = {}
                    desc_to_iva = {}
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
                    
                    # CSS per banner orizzontale con pulsazione cervelletto
                    st.markdown("""
                    <style>
                    @keyframes pulse_brain {
                        0% { transform: scale(1); opacity: 1; }
                        50% { transform: scale(1.15); opacity: 0.9; }
                        100% { transform: scale(1); opacity: 1; }
                    }
                    
                    .ai-banner {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 25px;
                        padding: 20px;
                        background: linear-gradient(135deg, #FFE5F4 0%, #FFF0F8 100%);
                        border: 2px solid #FFB6E1;
                        border-radius: 12px;
                        box-shadow: 0 4px 8px rgba(255, 182, 225, 0.3);
                    }
                    
                    .brain-pulse-banner {
                        font-size: clamp(2.5rem, 6vw, 3.75rem);
                        animation: pulse_brain 1.5s ease-in-out infinite;
                        line-height: 1;
                    }
                    
                    .progress-percentage {
                        font-family: monospace;
                        font-size: clamp(1.5rem, 4vw, 2rem);
                        font-weight: bold;
                        color: #FF69B4;
                        min-width: 5rem;
                    }
                    
                    .progress-status {
                        color: #555;
                        font-size: clamp(0.875rem, 2.5vw, 1.125rem);
                        font-weight: 500;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
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
                    chunk_size = 50
                    
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
                            cats = classifica_via_worker(
                                chunk,
                                fornitori=[desc_to_fornitore.get(d, '') for d in chunk],
                                iva=[desc_to_iva.get(d, 0) for d in chunk],
                                hint=[desc_to_hint.get(d) for d in chunk],
                                user_id=user_id,
                            )
                            st.session_state['_ai_budget_calls'] = st.session_state.get('_ai_budget_calls', 0) + 1
                            ai_batch_upsert = []
                            for desc, cat in zip(chunk, cats):
                                cat, override_reason = applica_regole_categoria_forti(desc, cat)
                                if override_reason:
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
                                
                                if cat and cat != "Da Classificare":
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
                        cat_to_descs = {}  # {categoria: [(desc_orig, desc_normalized), ...]}
                        for desc, cat in mappa_categorie.items():
                            if not cat or cat.strip() == '':
                                logger.warning(f"⚠️ Categoria vuota/NULL per '{desc[:TRUNCATE_DESC_LOG]}', skip update")
                                continue
                            if cat == "Da Classificare":
                                logger.info(f"⏭️ Skip update per '{desc[:TRUNCATE_DESC_LOG]}' → già Da Classificare")
                                continue
                            cat_to_descs.setdefault(cat, []).append((desc, normalizza_stringa(desc)))
                        
                        logger.info(f"⚡ BATCH UPDATE: {len(cat_to_descs)} categorie distinte per {sum(len(v) for v in cat_to_descs.values())} descrizioni")
                        
                        # FASE 1: Batch UPDATE per categoria con descrizioni normalizzate (.in_())
                        descs_non_matchate = {}  # {desc_orig: cat} - fallback individuale
                        
                        for cat, desc_pairs in cat_to_descs.items():
                            normalized_list = [dn for _, dn in desc_pairs]
                            original_list = [do for do, _ in desc_pairs]
                            
                            # Batch UPDATE con tutte le descrizioni normalizzate per questa categoria
                            try:
                                query_batch = supabase.table("fatture").update(
                                    {"categoria": cat}
                                ).eq("user_id", user_id).in_("descrizione", normalized_list)
                                query_batch = add_ristorante_filter(query_batch)
                                result_batch = query_batch.execute()
                                
                                matched_count = len(result_batch.data) if result_batch.data else 0
                                matched_descs = {row['descrizione'] for row in result_batch.data} if result_batch.data else set()
                                
                                if matched_count > 0:
                                    logger.info(f"⚡ Batch {cat}: {matched_count} righe aggiornate")
                                
                                righe_aggiornate_totali += matched_count
                                
                                # Identifica descrizioni matchate per tracking
                                for desc_orig, desc_norm in desc_pairs:
                                    if desc_norm in matched_descs:
                                        descrizioni_aggiornate.append(desc_orig)
                                    else:
                                        descs_non_matchate[desc_orig] = cat
                                
                            except Exception as batch_err:
                                logger.warning(f"⚠️ Batch UPDATE fallito per {cat}: {batch_err}, fallback individuale")
                                for desc_orig, _ in desc_pairs:
                                    descs_non_matchate[desc_orig] = cat
                        
                        # FASE 2: Fallback individuale SOLO per descrizioni non matchate dal batch
                        if descs_non_matchate:
                            logger.info(f"🔄 Fallback individuale per {len(descs_non_matchate)} descrizioni non matchate")
                        
                        for desc, cat in descs_non_matchate.items():
                            num_aggiornate = 0
                            
                            # Tentativo con descrizione originale (non normalizzata)
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
                            
                            # Tentativo ILIKE case-insensitive
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
                                    
                                    if num_aggiornate == 0 and len(desc.strip()) >= 5:
                                        query_update5 = supabase.table("fatture").update(
                                            {"categoria": cat}
                                        ).eq("user_id", user_id).ilike("descrizione", f"%{_escape_ilike(desc.strip()[:TRUNCATE_DESC_QUERY])}%")
                                        query_update5 = add_ristorante_filter(query_update5)
                                        result5 = query_update5.execute()
                                        num_aggiornate = len(result5.data) if result5.data else 0
                                        if num_aggiornate > 0:
                                            logger.info(f"✅ Match ILIKE parziale: '{desc[:TRUNCATE_DESC_LOG]}...' ({num_aggiornate} righe)")
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
                            query_check = supabase.table("fatture").select("descrizione, categoria").eq("user_id", user_id)
                            query_check = add_ristorante_filter(query_check)
                            df_check = query_check.execute()
                            if df_check.data:
                                df_temp = pd.DataFrame(df_check.data)
                                ancora_da_class = df_temp[(df_temp['categoria'].isna()) | (df_temp['categoria'] == 'Da Classificare')]['descrizione'].unique()
                                
                                if len(ancora_da_class) > 0:
                                    logger.info(f"🔧 FALLBACK: Tentando categorizzazione con dizionario per {len(ancora_da_class)} prodotti rimasti...")
                                    
                                    # ⚡ BATCH: Raggruppa per categoria prima di fare query
                                    _fb_cat_to_descs = {}  # {categoria: [desc1, desc2, ...]}
                                    for desc in ancora_da_class:
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
                        
                        # ⭐ FIX: Pausa minima per propagazione (Supabase è sincrono, la cache è già pulita)
                        time.sleep(UI_DELAY_MEDIUM)
                        
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
    
    st.markdown('<h3 style="color:#1e3a5f;font-weight:700;">📅 Filtra per Periodo</h3>', unsafe_allow_html=True)
    
    date_periodo = calcola_date_periodo()
    oggi_date = date_periodo['oggi']
    inizio_anno = date_periodo['inizio_anno']
    
    # Default: Anno in Corso
    if 'periodo_dropdown' not in st.session_state:
        st.session_state.periodo_dropdown = "🗓️ Anno in Corso"
    
    # Layout: selectbox + info box sulla stessa riga
    col_periodo, col_info_periodo = st.columns([1, 4])
    
    with col_periodo:
        periodo_selezionato = st.selectbox(
            "Periodo",
            options=PERIODO_OPTIONS,
            label_visibility="collapsed",
            index=PERIODO_OPTIONS.index(st.session_state.periodo_dropdown) if st.session_state.periodo_dropdown in PERIODO_OPTIONS else 0,
            key="filtro_periodo_main"
        )
    
    # Aggiorna session state
    st.session_state.periodo_dropdown = periodo_selezionato
    
    # Gestione logica periodo
    data_inizio_filtro, data_fine_filtro, label_periodo = risolvi_periodo(periodo_selezionato, date_periodo)
    
    if data_inizio_filtro is None:
        # Periodo Personalizzato
        st.markdown("##### Seleziona Range Date")
        col_da, col_a = st.columns(2)
        
        if 'data_inizio_filtro' not in st.session_state:
            st.session_state.data_inizio_filtro = inizio_anno
        if 'data_fine_filtro' not in st.session_state:
            st.session_state.data_fine_filtro = oggi_date
        
        with col_da:
            data_inizio_custom = st.date_input(
                "📅 Da", 
                value=st.session_state.data_inizio_filtro,
                min_value=inizio_anno,
                max_value=st.session_state.get('data_fine_filtro', oggi_date),
                key="data_da_custom"
            )
        
        with col_a:
            data_fine_custom = st.date_input(
                "📅 A", 
                value=st.session_state.data_fine_filtro,
                min_value=inizio_anno,
                max_value=datetime.now(timezone.utc).date(),
                key="data_a_custom"
            )
        
        if data_inizio_custom > data_fine_custom:
            st.error("⚠️ La data iniziale deve essere precedente alla data finale!")
            data_inizio_filtro = st.session_state.data_inizio_filtro
            data_fine_filtro = st.session_state.data_fine_filtro
        else:
            st.session_state.data_inizio_filtro = data_inizio_custom
            st.session_state.data_fine_filtro = data_fine_custom
            data_inizio_filtro = data_inizio_custom
            data_fine_filtro = data_fine_custom
        
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
    
    # Mostra info periodo nel box accanto al selettore
    info_testo = f"🗓️ {label_periodo} ({giorni} giorni) | 🍽️ Righe F&B: {len(df_food):,} | 📊 Righe Totali: {num_righe_totali_df:,} | 📄 Fatture: {num_doc_filtrati} di {num_fatture_totali_df}"
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
    spesa_fb = df_food['TotaleRiga'].sum()
    spesa_generale = df_spese_generali['TotaleRiga'].sum()
    num_fornitori = df_food['Fornitore'].nunique()
    num_fatture_spese = df_spese_generali['FileOrigine'].nunique() if not df_spese_generali.empty else 0
    num_fornitori_spese = df_spese_generali['Fornitore'].nunique() if not df_spese_generali.empty else 0
    
    # Layout 6 colonne per i KPI - una card per metrica
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    # Calcola spesa totale
    spesa_totale = spesa_fb + spesa_generale
    
    # Calcola spesa media mensile (usa Data_DT già calcolata, evita re-parsing)
    dates_valid = df_completo['Data_DT'].dropna()
    mesi_periodo = len({(d.year, d.month) for d in dates_valid}) if not dates_valid.empty else 0
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
    
    st.markdown('<h3 style="color:#1e3a5f;font-weight:700;">📊 Naviga tra le Sezioni</h3>', unsafe_allow_html=True)
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
    
    # CSS per bottoni colorati personalizzati
    load_css('common.css')
    
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
                render_pivot_mensile(df_cat_source, 'Categoria', MESI_ITA, 'categorie', 'Categorie')

    # ========================================================
    # SEZIONE 4: FORNITORI
    # ========================================================
    if st.session_state.sezione_attiva == "fornitori":
        if df_completo_filtrato.empty:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")
        else:
            col_filtro_forn, _ = st.columns([2, 5])
            with col_filtro_forn:
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
                render_pivot_mensile(df_forn_source, 'Fornitore', MESI_ITA, 'fornitori', 'Fornitori')




