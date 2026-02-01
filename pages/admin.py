"""
🔧 PANNELLO AMMINISTRAZIONE - ANALISI FATTURE AI
===============================================
Pannello admin con 3 TAB:
- Gestione Clienti (con impersonazione)
- Verifica Integrità Database (con dettaglio per cliente)
- Review Righe €0 (con memoria permanente)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import time
import logging
import extra_streamlit_components as stx
import plotly.express as px
import requests

# Importa funzioni categorie dinamiche da utils
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import corretto da utils (non da app.py per evitare esecuzione interfaccia)
from utils.formatters import carica_categorie_da_db
from utils.text_utils import estrai_nome_categoria, aggiungi_icona_categoria

# Importa costanti per filtri e admin
from config.constants import CATEGORIE_SPESE_GENERALI, ADMIN_EMAILS

# ============================================================
# SETUP
# ============================================================

# Import singleton Supabase e utilities
from services import get_supabase_client
from config.logger_setup import get_logger

# Setup logging (usa configurazione centralizzata)
logger = get_logger('admin')

# Setup pagina
st.set_page_config(
    page_title="Pannello Admin", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# ============================================================
# CONNESSIONE SUPABASE (usa singleton condiviso)
# ============================================================

# Ottieni client Supabase singleton
supabase = get_supabase_client()

# ============================================================
# RIPRISTINO SESSIONE DA COOKIE (come in app.py)
# ============================================================
try:
    # Inizializza logged_in se non esiste
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Ripristina sessione da cookie se non loggato
    if not st.session_state.logged_in:
        cookie_manager = stx.CookieManager(key="cookie_manager_admin")
        user_email_cookie = cookie_manager.get("user_email")
        
        if user_email_cookie:
            try:
                response = supabase.table("users").select("*").eq("email", user_email_cookie).eq("attivo", True).execute()
                if response and getattr(response, 'data', None) and len(response.data) > 0:
                    st.session_state.logged_in = True
                    st.session_state.user_data = response.data[0]
                    logger.info(f"✅ Sessione ripristinata da cookie per: {user_email_cookie}")
            except Exception as e:
                logger.error(f"Errore recupero utente da cookie: {e}")
except Exception as e:
    logger.error(f'Errore controllo cookie sessione: {e}')

# ============================================================
# CHECK AUTENTICAZIONE
# ============================================================

if not st.session_state.get('logged_in', False):
    st.error("⛔ Accesso negato. Effettua il login.")
    st.info("👉 Torna alla [pagina principale](/) per effettuare il login")
    st.stop()

user = st.session_state.get('user_data', {})

if user.get('email') not in ADMIN_EMAILS:
    st.error("⛔ Accesso riservato agli amministratori")
    st.stop()

# ============================================================
# HELPER FUNCTIONS
# ============================================================

# ============================================================
# FUNZIONI HELPER PER REVIEW CONFERME
# ============================================================

def conferma_prodotto_corretto(descrizione, categoria, admin_email):
    """
    Marca prodotto come confermato corretto.
    Viene rimosso dalla review ma salvato in history.
    
    Args:
        descrizione: Descrizione prodotto
        categoria: Categoria assegnata (corretta)
        admin_email: Email admin che conferma
        
    Returns:
        bool: True se successo
    """
    try:
        supabase.table('review_confirmed').insert({
            'descrizione': descrizione.strip(),
            'categoria_finale': categoria,
            'is_correct': True,
            'confirmed_by': admin_email,
            'confirmed_at': datetime.now().isoformat(),
            'note': 'Confermato corretto da admin'
        }).execute()
        
        logger.info(f"✅ Confermato: {descrizione[:50]} → {categoria}")
        return True
        
    except Exception as e:
        # Ignora errore se già esistente (duplicate key)
        if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
            logger.warning(f"Già confermato: {descrizione[:50]}")
            return True
        else:
            logger.error(f"Errore conferma: {e}")
            return False


def filtra_righe_confermate(df):
    """
    Rimuove dalla vista righe già confermate dall'admin.
    
    Args:
        df: DataFrame con colonna 'descrizione' o 'Descrizione'
        
    Returns:
        DataFrame filtrato
    """
    if df.empty:
        return df
    
    try:
        # Determina nome colonna (case-insensitive)
        col_desc = None
        for col in df.columns:
            if col.lower() == 'descrizione':
                col_desc = col
                break
        
        if not col_desc:
            logger.warning("Colonna 'descrizione' non trovata nel DataFrame")
            return df
        
        # Carica descrizioni confermate
        confirmed = supabase.table('review_confirmed')\
            .select('descrizione')\
            .execute()
        
        if confirmed.data and len(confirmed.data) > 0:
            desc_confermate = [r['descrizione'].strip() for r in confirmed.data]
            
            # Filtra fuori le confermate
            df_filtrato = df[~df[col_desc].str.strip().isin(desc_confermate)]
            
            num_filtrate = len(df) - len(df_filtrato)
            if num_filtrate > 0:
                logger.info(f"Filtrate {num_filtrate} righe già confermate")
            
            return df_filtrato
        else:
            return df
            
    except Exception as e:
        logger.error(f"Errore filtraggio confermate: {e}")
        return df  # In caso di errore, mostra tutto


def ignora_problema_temporaneo(row_id, descrizione, admin_email, giorni=30):
    """
    Ignora temporaneamente un problema (nasconde dalla review per N giorni).
    
    Args:
        row_id: ID riga fattura
        descrizione: Descrizione prodotto
        admin_email: Email admin
        giorni: Giorni di ignore (default 30)
        
    Returns:
        bool: True se successo
    """
    try:
        ignored_until = (datetime.now() + timedelta(days=giorni)).isoformat()
        
        supabase.table('review_ignored').insert({
            'row_id': row_id,
            'descrizione': descrizione,
            'ignored_by': admin_email,
            'ignored_at': datetime.now().isoformat(),
            'ignored_until': ignored_until
        }).execute()
        
        logger.info(f"🗑️ Ignorato per {giorni}gg: {descrizione[:50]}")
        return True
        
    except Exception as e:
        logger.error(f"Errore ignore: {e}")
        return False

# ============================================================
# ALTRE FUNZIONI HELPER
# ============================================================

def applica_bulk_categoria(lista_descrizioni, nuova_categoria, is_admin=True):
    """
    Applica categoria a lista di descrizioni in batch.
    
    Args:
        lista_descrizioni: Lista di descrizioni prodotto
        nuova_categoria: Categoria da applicare
        is_admin: Se True, modifica globalmente, altrimenti solo per utente
        
    Returns:
        dict: {'righe_memoria': int, 'righe_fatture': int, 'success': bool}
    """
    righe_memoria = 0
    righe_fatture = 0
    
    try:
        for descrizione in lista_descrizioni:
            try:
                if is_admin:
                    # Aggiorna memoria GLOBALE
                    result_memoria = supabase.table('prodotti_master')\
                        .update({'categoria': nuova_categoria})\
                        .eq('descrizione', descrizione)\
                        .execute()
                    righe_memoria += len(result_memoria.data) if result_memoria.data else 0
                    
                    # Aggiorna TUTTE le fatture
                    result_fatture = supabase.table('fatture')\
                        .update({'categoria': nuova_categoria})\
                        .eq('descrizione', descrizione)\
                        .execute()
                    righe_fatture += len(result_fatture.data) if result_fatture.data else 0
                else:
                    # Modifica solo per l'utente corrente
                    user_id = st.session_state.user_data.get('id')
                    result_fatture = supabase.table('fatture')\
                        .update({'categoria': nuova_categoria})\
                        .eq('descrizione', descrizione)\
                        .eq('user_id', user_id)\
                        .execute()
                    righe_fatture += len(result_fatture.data) if result_fatture.data else 0
                    
            except Exception as e:
                logger.error(f"Errore bulk update per '{descrizione}': {e}")
                continue
        
        logger.info(f"✅ Bulk update: {righe_memoria} memoria + {righe_fatture} fatture → {nuova_categoria}")
        return {'righe_memoria': righe_memoria, 'righe_fatture': righe_fatture, 'success': True}
        
    except Exception as e:
        logger.error(f"Errore bulk update: {e}")
        return {'righe_memoria': 0, 'righe_fatture': 0, 'success': False}

# ============================================================
# FUNZIONI DIAGNOSTICA DATABASE
# ============================================================

def analizza_integrita_database():
    """
    Analizza integrità database e rileva anomalie.
    
    Returns:
        tuple: (problemi dict, dettagli dict con DataFrame)
    """
    try:
        # Query dati completi
        response = supabase.table('fatture')\
            .select('*')\
            .execute()
        
        if not response.data:
            return {}, {}
        
        df = pd.DataFrame(response.data)
        
        # Verifica colonne necessarie
        required_cols = ['data_documento', 'prezzo_unitario', 'quantita', 'descrizione', 'totale_riga']
        for col in required_cols:
            if col not in df.columns:
                logger.warning(f"Colonna '{col}' mancante nel database")
                df[col] = None
        
        problemi = {
            'date_invalide': 0,
            'prezzi_anomali': 0,
            'quantita_anomale': 0,
            'descrizioni_vuote': 0,
            'totali_non_corrispondenti': 0,
            'fatture_duplicate': 0
        }
        
        # NUOVO: Store DataFrame dettagli per drill-down
        dettagli = {}
        
        # ============================================================
        # CHECK 1: Date invalide
        # ============================================================
        try:
            df['data_dt'] = pd.to_datetime(df['data_documento'], errors='coerce')
            df_date_invalide = df[df['data_dt'].isna()].copy()
            
            # Date nel futuro
            oggi = pd.Timestamp.now()
            df_date_future = df[df['data_dt'] > oggi].copy()
            
            # Unisci
            df_date_problema = pd.concat([df_date_invalide, df_date_future]).drop_duplicates()
            
            problemi['date_invalide'] = len(df_date_problema)
            dettagli['date_invalide'] = df_date_problema[['id', 'descrizione', 'fornitore', 'data_documento', 'file_origine']].head(100)
        except Exception as e:
            logger.warning(f"Errore check date: {e}")
            dettagli['date_invalide'] = pd.DataFrame()
        
        # ============================================================
        # CHECK 2: Prezzi anomali
        # ============================================================
        try:
            # Converti a numeric con coerce per gestire valori non numerici
            df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce')
            
            # Prezzi negativi o eccessivi (>1000€)
            df_prezzi_anomali = df[
                (df['prezzo_unitario'] < 0) | (df['prezzo_unitario'] > 1000)
            ].copy()
            
            problemi['prezzi_anomali'] = len(df_prezzi_anomali)
            dettagli['prezzi_anomali'] = df_prezzi_anomali[['id', 'descrizione', 'prezzo_unitario', 'fornitore', 'file_origine']].head(100)
        except Exception as e:
            logger.warning(f"Errore check prezzi: {e}")
            dettagli['prezzi_anomali'] = pd.DataFrame()
        
        # ============================================================
        # CHECK 3: Quantità anomale
        # ============================================================
        try:
            # Converti a numeric con coerce
            df['quantita'] = pd.to_numeric(df['quantita'], errors='coerce')
            
            # Quantità negative o eccessive (>1000)
            df_qta_anomale = df[
                (df['quantita'] < 0) | (df['quantita'] > 1000)
            ].copy()
            
            problemi['quantita_anomale'] = len(df_qta_anomale)
            dettagli['quantita_anomale'] = df_qta_anomale[['id', 'descrizione', 'quantita', 'fornitore', 'file_origine']].head(100)
        except Exception as e:
            logger.warning(f"Errore check quantità: {e}")
            dettagli['quantita_anomale'] = pd.DataFrame()
        
        # ============================================================
        # CHECK 4: Descrizioni vuote o troppo corte
        # ============================================================
        try:
            df['desc_len'] = df['descrizione'].fillna('').astype(str).str.len()
            df_desc_vuote = df[df['desc_len'] < 3].copy()
            
            problemi['descrizioni_vuote'] = len(df_desc_vuote)
            dettagli['descrizioni_vuote'] = df_desc_vuote[['id', 'descrizione', 'fornitore', 'file_origine']].head(100)
        except Exception as e:
            logger.warning(f"Errore check descrizioni: {e}")
            dettagli['descrizioni_vuote'] = pd.DataFrame()
        
        # ============================================================
        # CHECK 5: Fatture duplicate
        # ============================================================
        try:
            if all(col in df.columns for col in ['numero_fattura', 'fornitore', 'data_documento']):
                duplicates = df.duplicated(subset=['numero_fattura', 'fornitore', 'data_documento'], keep=False)
                df_duplicate = df[duplicates].copy()
                
                problemi['fatture_duplicate'] = len(df_duplicate)
                dettagli['fatture_duplicate'] = df_duplicate[['id', 'numero_fattura', 'fornitore', 'data_documento', 'file_origine']].head(100)
            else:
                dettagli['fatture_duplicate'] = pd.DataFrame()
        except Exception as e:
            logger.warning(f"Errore check duplicati: {e}")
            dettagli['fatture_duplicate'] = pd.DataFrame()
        
        # ============================================================
        # CHECK 6: Totali non corrispondenti
        # ============================================================
        try:
            df['totale_riga'] = pd.to_numeric(df['totale_riga'], errors='coerce')
            df['totale_calcolato'] = df['quantita'] * df['prezzo_unitario']
            df['diff'] = abs(df['totale_riga'] - df['totale_calcolato'])
            
            # Tolleranza 0.10€ per arrotondamenti
            df_totali_errati = df[df['diff'] > 0.10].copy()
            
            problemi['totali_non_corrispondenti'] = len(df_totali_errati)
            dettagli['totali_non_corrispondenti'] = df_totali_errati[['id', 'descrizione', 'totale_riga', 'totale_calcolato', 'diff', 'fornitore']].head(100)
        except Exception as e:
            logger.warning(f"Errore check totali: {e}")
            dettagli['totali_non_corrispondenti'] = pd.DataFrame()
        
        return problemi, dettagli
        
    except Exception as e:
        logger.error(f"Errore analisi integrità: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}, {}


def trova_fornitori_duplicati():
    """
    Trova fornitori con nomi simili (probabili duplicati).
    
    Returns:
        list: Gruppi di fornitori simili
    """
    try:
        response = supabase.table('fatture')\
            .select('fornitore')\
            .execute()
        
        if not response.data:
            return []
        
        fornitori = [r.get('fornitore', '') for r in response.data if r.get('fornitore')]
        fornitori = [f for f in fornitori if f and len(f) > 0]  # Filtra vuoti
        fornitori_unici = list(set(fornitori))
        
        if len(fornitori_unici) < 2:
            return []
        
        # Trova nomi simili
        from difflib import SequenceMatcher
        
        duplicati = []
        
        for i, forn1 in enumerate(fornitori_unici):
            for forn2 in fornitori_unici[i+1:]:
                try:
                    similarity = SequenceMatcher(None, forn1.lower(), forn2.lower()).ratio()
                    
                    # Se somiglianza >80% sono probabilmente duplicati
                    if similarity > 0.8:
                        duplicati.append({
                            'fornitore1': forn1,
                            'fornitore2': forn2,
                            'similarity': f"{similarity*100:.0f}%"
                        })
                except Exception as e:
                    logger.warning(f"Errore confronto fornitori '{forn1}' vs '{forn2}': {e}")
                    continue
        
        return duplicati
        
    except Exception as e:
        logger.error(f"Errore ricerca duplicati: {e}")
        return []


def statistiche_salute_sistema():
    """
    Calcola statistiche salute complessiva sistema.
    
    Returns:
        dict: Metriche sistema
    """
    try:
        # Query base con gestione errori
        try:
            righe_response = supabase.table('fatture').select('*', count='exact').execute()
            totale_righe = righe_response.count if righe_response else 0
            df_righe = pd.DataFrame(righe_response.data) if righe_response.data else pd.DataFrame()
        except Exception as e:
            logger.warning(f"Errore query fatture: {e}")
            totale_righe = 0
            df_righe = pd.DataFrame()
        
        try:
            clienti_response = supabase.table('users').select('*', count='exact').execute()
            totale_clienti = clienti_response.count if clienti_response else 0
        except Exception as e:
            logger.warning(f"Errore query users: {e}")
            totale_clienti = 0
        
        try:
            memoria_response = supabase.table('prodotti_master').select('*', count='exact').execute()
            totale_memoria = memoria_response.count if memoria_response else 0
        except Exception as e:
            logger.warning(f"Errore query memoria: {e}")
            totale_memoria = 0
            memoria_response = None
        
        stats = {
            'totale_clienti': totale_clienti,
            'totale_righe': totale_righe,
            'totale_memoria': totale_memoria,
            'righe_categorizzate': 0,
            'tasso_successo_ai': 0,
            'chiamate_api_risparmiate': 0
        }
        
        if not df_righe.empty and 'categoria' in df_righe.columns:
            # Righe categorizzate (non "Da Classificare")
            categorizzate = df_righe[df_righe['categoria'] != 'Da Classificare']
            stats['righe_categorizzate'] = len(categorizzate)
            
            # Tasso successo AI
            if len(df_righe) > 0:
                stats['tasso_successo_ai'] = (len(categorizzate) / len(df_righe)) * 100
        
        # Chiamate API risparmiate (memoria globale)
        if memoria_response and memoria_response.data:
            df_mem = pd.DataFrame(memoria_response.data)
            if 'volte_visto' in df_mem.columns:
                total_visto = pd.to_numeric(df_mem['volte_visto'], errors='coerce').fillna(0).sum()
                stats['chiamate_api_risparmiate'] = int(total_visto - len(df_mem))
        
        return stats
        
    except Exception as e:
        logger.error(f"Errore statistiche sistema: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'totale_clienti': 0,
            'totale_righe': 0,
            'totale_memoria': 0,
            'righe_categorizzate': 0,
            'tasso_successo_ai': 0,
            'chiamate_api_risparmiate': 0
        }


def clienti_con_piu_errori():
    """
    Trova top 10 clienti con più problemi.
    
    Returns:
        DataFrame: Clienti ordinati per numero errori
    """
    try:
        response = supabase.table('fatture')\
            .select('user_id, descrizione, categoria, prezzo_unitario')\
            .execute()
        
        if not response.data:
            return pd.DataFrame()
        
        df = pd.DataFrame(response.data)
        
        # Converti prezzo a numeric
        df['prezzo_unitario'] = pd.to_numeric(df['prezzo_unitario'], errors='coerce').fillna(0)
        
        # Conta problemi per cliente
        problemi_per_cliente = []
        
        for user_id in df['user_id'].unique():
            if not user_id:
                continue
                
            df_user = df[df['user_id'] == user_id]
            
            # Conta tipi problema
            prezzi_zero = int((df_user['prezzo_unitario'] == 0).sum())
            materiale_consumo = int((df_user['categoria'] == 'MATERIALE DI CONSUMO').sum())
            da_class = int((df_user['categoria'] == 'Da Classificare').sum())
            
            totale_problemi = prezzi_zero + materiale_consumo + da_class
            
            if totale_problemi > 0:
                problemi_per_cliente.append({
                    'user_id': user_id,
                    'prezzi_zero': prezzi_zero,
                    'materiale_consumo': materiale_consumo,
                    'da_classificare': da_class,
                    'totale': totale_problemi
                })
        
        if not problemi_per_cliente:
            return pd.DataFrame()
        
        df_problemi = pd.DataFrame(problemi_per_cliente)
        
        # Arricchisci con nome cliente
        try:
            clienti_response = supabase.table('users')\
                .select('id, nome_ristorante, email')\
                .execute()
            
            if clienti_response.data:
                df_clienti = pd.DataFrame(clienti_response.data)
                df_problemi = df_problemi.merge(
                    df_clienti,
                    left_on='user_id',
                    right_on='id',
                    how='left'
                )
                
                # Riempi nome mancante
                df_problemi['nome_ristorante'] = df_problemi['nome_ristorante'].fillna('Cliente Sconosciuto')
        except Exception as e:
            logger.warning(f"Errore join clienti: {e}")
            df_problemi['nome_ristorante'] = 'Cliente Sconosciuto'
        
        # Ordina per totale problemi
        df_problemi = df_problemi.sort_values('totale', ascending=False).head(10)
        
        return df_problemi
        
    except Exception as e:
        logger.error(f"Errore top clienti errori: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return pd.DataFrame()


def invalida_cache_memoria():
    """Invalida cache memoria globale."""
    st.cache_data.clear()
    logger.info("✅ Cache memoria invalidata")


# ============================================================
# HEADER
# ============================================================

st.title("👨‍💼 Pannello Amministrazione")
st.caption(f"Admin: {user.get('email')} | [🏠 Torna all'App](/) | [🔓 Cambia Password](/cambio_password)")
st.markdown("---")

# ============================================================
# TABS PRINCIPALI CON PERSISTENZA
# ============================================================

# Inizializza tab attivo in session_state (default = 0)
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

# Cache categorie in session_state (carica 1 sola volta)
if 'categorie_cached' not in st.session_state:
    st.session_state.categorie_cached = carica_categorie_da_db(supabase_client=supabase)
    logger.info(f"✅ Categorie caricate in cache: {len(st.session_state.categorie_cached)} categorie")

# Usa radio buttons nascosti per mantenere tab attivo
tab_names = ["📊 Gestione Clienti", "💰 Review Righe €0", "🧠 Memoria Globale AI", "📊 Upload Events", "💳 Costi AI"]
selected_tab = st.radio(
    "Seleziona Tab",
    range(len(tab_names)),
    format_func=lambda x: tab_names[x],
    key="tab_selector",
    horizontal=True,
    label_visibility="collapsed"
)

# Aggiorna tab attivo se cambiato dall'utente
if selected_tab != st.session_state.active_tab:
    st.session_state.active_tab = selected_tab

st.markdown("---")

# Mostra solo il contenuto del tab selezionato
tab1 = (st.session_state.active_tab == 0)
tab2 = (st.session_state.active_tab == 1)
tab3 = (st.session_state.active_tab == 2)
tab4 = (st.session_state.active_tab == 3)
tab5 = (st.session_state.active_tab == 4)

# ============================================================
# FUNZIONI DIAGNOSTICA TECNICA (legacy removed)
# ============================================================
# verifica_completezza_fatture() rimossa - ora si usa upload_events



# ============================================================
# FUNZIONI DIAGNOSTICHE VECCHIE RIMOSSE
# ============================================================
# Le funzioni trova_duplicati_reali(), valida_date_e_dati() e
# conta_problemi_per_cliente() sono state rimosse.
# 
# Ora si usa il sistema di logging upload_events che traccia
# solo problemi tecnici reali (FAILED, SAVED_PARTIAL).
# ============================================================


# ============================================================
# FUNZIONI AVANZATE PER TAB 2
# ============================================================

def calcola_score_salute(problemi, stats_sistema):
    """
    Calcola score salute database 0-100.
    
    Returns:
        int: score 0-100
    """
    try:
        totale_righe = stats_sistema.get('totale_righe', 1)
        if totale_righe == 0:
            return 100
        
        totale_problemi = sum(problemi.values())
        perc_problemi = (totale_problemi / totale_righe) * 100
        score = max(0, 100 - (perc_problemi * 2))
        
        return int(score)
    except Exception as e:
        logger.error(f"Errore calcolo_score_salute: {e}")
        return 0


def carica_trend_problemi(giorni=30):
    """Carica trend problemi ultimi N giorni."""
    try:
        data_limite = (datetime.now() - timedelta(days=giorni)).isoformat()
        
        response = supabase.table('fatture')\
            .select('created_at, prezzo_unitario, categoria')\
            .gte('created_at', data_limite)\
            .execute()
        
        if not response.data:
            return pd.DataFrame()
        
        df = pd.DataFrame(response.data)
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['data'] = df['created_at'].dt.date
        
        df_trend = df.groupby('data').agg({
            'prezzo_unitario': lambda x: (x == 0).sum(),
            'categoria': lambda x: (x == 'Da Classificare').sum()
        }).reset_index()
        
        df_trend.columns = ['data', 'prezzi_zero', 'da_classificare']
        df_trend['totale'] = df_trend['prezzi_zero'] + df_trend['da_classificare']
        
        return df_trend
    except Exception as e:
        logger.error(f"Errore carica trend: {e}")
        return pd.DataFrame()


def genera_csv_problemi(dettagli):
    """Genera CSV con tutti i problemi rilevati."""
    try:
        import io
        
        output = io.StringIO()
        all_problemi = []
        
        for tipo, df in dettagli.items():
            if not df.empty:
                df_copy = df.copy()
                df_copy['tipo_problema'] = tipo
                all_problemi.append(df_copy)
        
        if all_problemi:
            df_completo = pd.concat(all_problemi, ignore_index=True)
            df_completo.to_csv(output, index=False)
            return output.getvalue().encode('utf-8')
        else:
            return b"Nessun problema rilevato"
    except Exception as e:
        logger.error(f"Errore generazione CSV: {e}")
        return b"Errore generazione CSV"


def unisci_fornitori(fornitore_principale, fornitore_da_unire):
    """Unisce due fornitori duplicati."""
    try:
        result = supabase.table('fatture').update({
            'fornitore': fornitore_principale
        }).eq('fornitore', fornitore_da_unire).execute()
        
        num_updated = len(result.data) if result.data else 0
        logger.info(f"🔀 Uniti fornitori: '{fornitore_da_unire}' → '{fornitore_principale}' ({num_updated} righe)")
        
        return num_updated
    except Exception as e:
        logger.error(f"Errore unione fornitori: {e}")
        return 0


def ottieni_lista_clienti():
    """Ottiene lista clienti per filtro."""
    try:
        response = supabase.table('users')\
            .select('id, nome_ristorante')\
            .order('nome_ristorante')\
            .execute()
        
        if response.data:
            return [(r['id'], r.get('nome_ristorante', 'N/A')) for r in response.data]
        return []
    except Exception as e:
        logger.error(f"Errore ottieni_lista_clienti: {e}")
        return []


def fix_automatico_tutti_problemi(dettagli):
    """Applica tutte le correzioni automatiche possibili."""
    report = {
        'descrizioni_vuote': 0,
        'prezzi_negativi': 0,
        'totali_errati': 0
    }
    
    try:
        # 1. Elimina descrizioni vuote
        df_desc = dettagli.get('descrizioni_vuote', pd.DataFrame())
        if not df_desc.empty:
            for row_id in df_desc['id'].tolist():
                try:
                    supabase.table('fatture').delete().eq('id', row_id).execute()
                    report['descrizioni_vuote'] += 1
                except Exception as e:
                    logger.warning(f"Errore delete descrizione vuota {row_id}: {e}")
        
        # 2. Elimina prezzi negativi
        df_prezzi = dettagli.get('prezzi_anomali', pd.DataFrame())
        if not df_prezzi.empty and 'prezzo_unitario' in df_prezzi.columns:
            df_neg = df_prezzi[df_prezzi['prezzo_unitario'] < 0]
            for row_id in df_neg['id'].tolist():
                try:
                    supabase.table('fatture').delete().eq('id', row_id).execute()
                    report['prezzi_negativi'] += 1
                except Exception as e:
                    logger.warning(f"Errore delete prezzo negativo {row_id}: {e}")
        
        # 3. Ricalcola totali errati
        df_totali = dettagli.get('totali_non_corrispondenti', pd.DataFrame())
        if not df_totali.empty:
            for idx, row in df_totali.iterrows():
                try:
                    supabase.table('fatture').update({
                        'totale_riga': row['totale_calcolato']
                    }).eq('id', row['id']).execute()
                    report['totali_errati'] += 1
                except Exception as e:
                    logger.warning(f"Errore update totale {row['id']}: {e}")
        
        return report
    except Exception as e:
        logger.error(f"Errore fix automatico: {e}")
        return report


# ============================================================
# TAB 1: GESTIONE CLIENTI + IMPERSONAZIONE
# ============================================================

if tab1:
    st.markdown("### 📊 Gestione Clienti e Statistiche")
    st.caption("Visualizza statistiche clienti e accedi come utente impersonando account")
    
    # ============================================================
    # CREA NUOVO CLIENTE (solo admin) - GDPR COMPLIANT
    # ============================================================
    # L'admin NON imposta password. Il cliente la imposta via link email.
    # ============================================================
    st.markdown("### ➕ Crea Nuovo Cliente")
    
    with st.expander("➕ Crea Nuovo Cliente", expanded=False):
        # Import validatore P.IVA
        from utils.piva_validator import valida_formato_piva, normalizza_piva
        from services.auth_service import crea_cliente_con_token
        
        st.info("📧 **GDPR Compliant**: Il cliente riceverà un'email per impostare la propria password. L'admin non conosce mai le password dei clienti.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_email = st.text_input(
                "📧 Email cliente *", 
                key="new_email", 
                placeholder="cliente@esempio.com",
                help="Email per login cliente"
            )
            new_name = st.text_input(
                "🏪 Nome ristorante *", 
                key="new_name", 
                placeholder="Es: Ristorante Da Mario",
                help="Nome locale"
            )
        
        with col2:
            new_piva = st.text_input(
                "🏢 Partita IVA *", 
                key="new_piva", 
                placeholder="12345678901",
                max_chars=11,
                help="11 cifre numeriche"
            )
            new_ragione_sociale = st.text_input(
                "📄 Ragione Sociale", 
                key="new_ragione_sociale", 
                placeholder="Mario Rossi S.r.l. (opzionale)",
                help="Nome ufficiale azienda (opzionale)"
            )
        
        # Validazione real-time P.IVA
        if new_piva:
            piva_norm = normalizza_piva(new_piva)
            if len(piva_norm) == 11:
                valida, msg = valida_formato_piva(piva_norm)
                if valida:
                    st.success(f"✅ P.IVA valida: {piva_norm}")
                else:
                    st.error(msg)
            elif len(piva_norm) > 0:
                st.warning(f"⚠️ P.IVA incompleta: {len(piva_norm)}/11 cifre")
        
        st.markdown("---")
        
        if st.button("🆕 Crea Account e Invia Email", type="primary", use_container_width=True):
            # Validazione input
            errori_form = []
            
            if not new_email or '@' not in new_email:
                errori_form.append("❌ Email non valida")
            
            if not new_name:
                errori_form.append("❌ Nome ristorante obbligatorio")
            
            if not new_piva:
                errori_form.append("❌ P.IVA obbligatoria")
            else:
                piva_valida, piva_msg = valida_formato_piva(new_piva)
                if not piva_valida:
                    errori_form.append(piva_msg)
            
            if errori_form:
                for err in errori_form:
                    st.error(err)
            else:
                try:
                    # Crea cliente con token (senza password)
                    successo, messaggio, token = crea_cliente_con_token(
                        email=new_email,
                        nome_ristorante=new_name,
                        partita_iva=new_piva,
                        ragione_sociale=new_ragione_sociale,
                        supabase_client=supabase
                    )
                    
                    if not successo:
                        st.error(messaggio)
                    else:
                        # Invia email con link attivazione
                        email_inviata = False
                        try:
                            brevo_api_key = st.secrets["brevo"]["api_key"]
                            sender_email = st.secrets["brevo"]["sender_email"]
                            app_url = st.secrets.get("app", {}).get("url", "https://envoicescan-ai.streamlit.app")
                            
                            # Link con token per impostare password
                            link_attivazione = f"{app_url}?reset_token={token}"
                            
                            url_brevo = "https://api.brevo.com/v3/smtp/email"
                            
                            email_html = f"""
                            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                <h2 style="color: #2c5aa0;">🎉 Benvenuto in ANALISI FATTURE AI!</h2>
                                <p>Ciao <strong>{new_name}</strong>,</p>
                                <p>Il tuo account è stato creato con successo dal nostro team.</p>
                                
                                <p><strong>Per iniziare, imposta la tua password personale:</strong></p>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{link_attivazione}" 
                                       style="background-color: #0ea5e9; 
                                              color: white; 
                                              padding: 15px 30px; 
                                              text-decoration: none; 
                                              border-radius: 6px; 
                                              display: inline-block;
                                              font-weight: bold;">
                                        🔐 Imposta Password
                                    </a>
                                </div>
                                
                                <p style="color: #dc2626;">
                                    ⚠️ <strong>Importante:</strong> Questo link scade tra <strong>24 ore</strong> per sicurezza.
                                </p>
                                
                                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                                
                                <p><strong>📧 La tua email di accesso:</strong> {new_email}</p>
                                <p><strong>🏢 P.IVA registrata:</strong> {normalizza_piva(new_piva)}</p>
                                
                                <p>Dopo aver impostato la password, potrai:</p>
                                <ul>
                                    <li>✅ Caricare fatture XML automaticamente</li>
                                    <li>📊 Vedere dashboard analytics in tempo reale</li>
                                    <li>🔔 Ricevere alert su anomalie prezzi</li>
                                </ul>
                                
                                <p style="margin-top: 30px; color: #666; font-size: 14px;">
                                    <strong>Hai domande?</strong> Rispondi direttamente a questa email, ti risponderemo al più presto!
                                </p>
                                
                                <p style="color: #666; font-size: 14px;">
                                    ---<br>
                                    <strong>ANALISI FATTURE AI Team</strong><br>
                                    <a href="https://envoicescan-ai.streamlit.app">envoicescan-ai.streamlit.app</a><br>
                                    📧 Support: mattiadavolio90@gmail.com
                                </p>
                            </div>
                            """
                            
                            payload = {
                                "sender": {"email": sender_email, "name": "ANALISI FATTURE AI"},
                                "to": [{"email": new_email, "name": new_name}],
                                "replyTo": {"email": "mattiadavolio90@gmail.com", "name": "Mattia Davolio - Support"},
                                "bcc": [{"email": "mattiadavolio90@gmail.com"}],
                                "subject": f"🆕 Benvenuto {new_name} - Imposta la tua Password",
                                "htmlContent": email_html
                            }
                            
                            response = requests.post(
                                url_brevo, 
                                json=payload, 
                                headers={
                                    "api-key": brevo_api_key,
                                    "Content-Type": "application/json"
                                },
                                timeout=10
                            )
                            
                            if response.status_code == 201:
                                email_inviata = True
                                logger.info(f"✅ Email attivazione inviata a {new_email}")
                            else:
                                logger.warning(f"⚠️ Email non inviata: {response.status_code} - {response.text}")
                                
                        except Exception as e:
                            logger.error(f"❌ Errore invio email: {e}")
                        
                        # Mostra messaggio di successo
                        if email_inviata:
                            st.success(f"""
                            ✅ **Cliente creato con successo!**
                            
                            📧 Email inviata a: **{new_email}**
                            🔗 Link attivazione valido per: **24 ore**
                            🏢 P.IVA: **{normalizza_piva(new_piva)}**
                            
                            Il cliente riceverà un'email per impostare la propria password.
                            """)
                        else:
                            st.success(f"✅ Cliente {new_email} creato con successo!")
                            st.warning("⚠️ Errore invio email automatico.")
                            st.info(f"""
                            📋 **Comunica manualmente al cliente:**
                            
                            Link attivazione: `{link_attivazione}`
                            
                            Il link scade tra 24 ore.
                            """)
                        
                        logger.info(f"✅ Nuovo cliente creato da admin: {new_email} | P.IVA: {normalizza_piva(new_piva)} | Email: {email_inviata}")
                        time.sleep(2)
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Errore creazione cliente: {e}")
                    logger.exception(f"Errore creazione cliente {new_email}")
    
    st.markdown("---")
    
    try:
        # Query utenti (retrocompatibile: prova con partita_iva, fallback senza)
        try:
            query_users = supabase.table('users')\
                .select('id, email, nome_ristorante, attivo, created_at, partita_iva, ragione_sociale')\
                .order('email')\
                .execute()
            has_piva_column = True
        except Exception as col_err:
            # Fallback: colonne partita_iva non ancora migrate
            if '42703' in str(col_err) or 'does not exist' in str(col_err):
                query_users = supabase.table('users')\
                    .select('id, email, nome_ristorante, attivo, created_at')\
                    .order('email')\
                    .execute()
                has_piva_column = False
                st.warning("⚠️ Esegui migrazione 009 per abilitare P.IVA")
            else:
                raise col_err
        
        if not query_users.data:
            st.info("📭 Nessun cliente registrato")
        else:
            # Filtra admin dalla lista clienti
            clienti_non_admin = [u for u in query_users.data if u.get('email') not in ADMIN_EMAILS]
            
            if not clienti_non_admin:
                st.info("📭 Nessun cliente registrato (esclusi admin)")
            
            # Calcola statistiche per ogni cliente
            stats_clienti = []
            
            for user_data in clienti_non_admin:
                user_id = user_data['id']
                
                # Query fatture per questo utente (con conteggio esatto)
                query_fatture = supabase.table('fatture')\
                    .select('file_origine, id, created_at, data_documento, totale_riga, fornitore, categoria, needs_review', count='exact')\
                    .eq('user_id', user_id)\
                    .execute()
                
                num_fatture = 0
                num_righe = 0
                ultimo_caricamento = None
                totale_costi_complessivi = 0
                
                # DEBUG: contatori per analisi
                debug_info = {
                    'totale_raw': 0,
                    'escluse_note': 0,
                    'escluse_review': 0,
                    'escluse_date_invalide': 0,
                    'incluse_finale': 0,
                    'somma_totale_riga': 0.0,
                    'righe_con_date': []
                }
                
                if query_fatture.data:
                    # Conta file unici
                    file_unici = set([r['file_origine'] for r in query_fatture.data])
                    num_fatture = len(file_unici)
                    num_righe = query_fatture.count  # ✅ FIX: usa count reale invece di len()
                    
                    # Ultimo caricamento (converte tutto a timezone-aware)
                    date_caricate = []
                    for r in query_fatture.data:
                        dt = pd.to_datetime(r['created_at'])
                        # Converti a timezone-aware se naive
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        date_caricate.append(dt)
                    
                    if date_caricate:
                        ultimo_caricamento = max(date_caricate)
                    
                    # Calcola totale costi complessivi (ESCLUSE NOTE E DICITURE e needs_review)
                    for r in query_fatture.data:
                        debug_info['totale_raw'] += 1
                        
                        try:
                            categoria = str(r.get('categoria', '')).strip()
                            needs_review = r.get('needs_review', False)
                            data_documento = r.get('data_documento')
                            totale_riga = float(r.get('totale_riga', 0) or 0)
                            
                            # Escludi NOTE E DICITURE (righe a 0€)
                            if categoria == '📝 NOTE E DICITURE':
                                debug_info['escluse_note'] += 1
                                continue
                            
                            # Escludi righe in review (qualsiasi categoria)
                            if needs_review:
                                debug_info['escluse_review'] += 1
                                continue
                            
                            # Verifica data valida (come fa il client)
                            try:
                                data_dt = pd.to_datetime(data_documento, errors='coerce')
                                if pd.isna(data_dt):
                                    debug_info['escluse_date_invalide'] += 1
                                    continue
                            except (ValueError, TypeError):
                                debug_info['escluse_date_invalide'] += 1
                                continue
                            
                            debug_info['incluse_finale'] += 1
                            debug_info['somma_totale_riga'] += totale_riga
                            totale_costi_complessivi += totale_riga
                            
                            # Salva info data per analisi (solo prime 5)
                            if len(debug_info['righe_con_date']) < 5:
                                debug_info['righe_con_date'].append({
                                    'data': str(data_documento),
                                    'importo': totale_riga,
                                    'categoria': categoria
                                })
                        except Exception as e:
                            logger.warning(f"Errore calcolo costo riga {r.get('id')}: {e}")
                            continue
                
                stats_clienti.append({
                    'user_id': user_id,
                    'email': user_data['email'],
                    'ristorante': user_data.get('nome_ristorante', 'N/A'),
                    'attivo': user_data.get('attivo', True),
                    'partita_iva': user_data.get('partita_iva'),
                    'ragione_sociale': user_data.get('ragione_sociale'),
                    'num_fatture': num_fatture,
                    'num_righe': num_righe,
                    'ultimo_caricamento': ultimo_caricamento,
                    'totale_costi': totale_costi_complessivi,
                    'debug': debug_info
                })
            
            df_clienti = pd.DataFrame(stats_clienti)
            
            # ===== METRICHE GENERALI =====
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Totale Clienti", len(df_clienti))
            with col2:
                clienti_attivi = df_clienti[df_clienti['attivo'] == True].shape[0]
                st.metric("Clienti Attivi", clienti_attivi)
            with col3:
                totale_fatture = int(df_clienti['num_fatture'].sum())
                st.metric("Totale Fatture", totale_fatture)
            with col4:
                totale_righe = int(df_clienti['num_righe'].sum())
                st.metric("Totale Righe", totale_righe)
            with col5:
                totale_costi_globale = df_clienti['totale_costi'].sum()
                st.metric("Totale Costi", f"€{totale_costi_globale:,.2f}")
            
            st.markdown("---")
            st.markdown("#### 👥 Lista Clienti")
            
            # ===== FILTRI RICERCA =====
            st.markdown("##### 🔍 Filtri Ricerca")
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                cerca_email = st.text_input("📧 Cerca per email", "", key="filtro_email_admin")
            
            with col_f2:
                cerca_piva = st.text_input("🏢 Cerca per P.IVA", "", key="filtro_piva_admin")
            
            with col_f3:
                solo_mancanti = st.checkbox("🚨 Solo senza P.IVA", value=False, key="filtro_mancanti")
            
            # Applica filtri
            df_clienti_filtrato = df_clienti.copy()
            
            if cerca_email:
                df_clienti_filtrato = df_clienti_filtrato[
                    df_clienti_filtrato['email'].str.contains(cerca_email, case=False, na=False)
                ]
            
            if cerca_piva and has_piva_column:
                df_clienti_filtrato = df_clienti_filtrato[
                    df_clienti_filtrato['partita_iva'].astype(str).str.contains(cerca_piva, case=False, na=False)
                ]
            
            if solo_mancanti and has_piva_column:
                df_clienti_filtrato = df_clienti_filtrato[
                    df_clienti_filtrato['partita_iva'].isna() | (df_clienti_filtrato['partita_iva'] == '')
                ]
            
            # Metriche P.IVA (solo se colonna esiste)
            if has_piva_column:
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("📊 Filtrati", len(df_clienti_filtrato))
                with col_s2:
                    con_piva = df_clienti['partita_iva'].notna().sum()
                    st.metric("✅ Con P.IVA", con_piva)
                with col_s3:
                    senza_piva = df_clienti['partita_iva'].isna().sum()
                    st.metric("⚠️ Senza P.IVA", senza_piva)
            
            st.markdown("---")
            
            # Ordina per ultimo caricamento (più recenti prima)
            df_clienti_sorted = df_clienti_filtrato.sort_values('ultimo_caricamento', ascending=False, na_position='last')
            
            # ===== TABELLA CLIENTI CON IMPERSONAZIONE =====
            # Layout dinamico: con/senza colonna P.IVA in base a migrazione
            for idx, row in df_clienti_sorted.iterrows():
                if has_piva_column:
                    col1, col2, col_piva, col3, col4, col5, col6, col7 = st.columns([2.5, 1.8, 1.5, 0.8, 0.8, 1.3, 1.2, 1])
                else:
                    col1, col2, col3, col4, col5, col6, col7 = st.columns([2.5, 2, 1, 1, 1.5, 1.5, 1])
                    col_piva = None
                
                with col1:
                    status_icon = "🟢" if row['attivo'] else "🔴"
                    st.markdown(f"{status_icon} **{row['email']}**")
                
                with col2:
                    st.text(row['ristorante'])
                
                if col_piva:
                    with col_piva:
                        # P.IVA con badge
                        piva = row.get('partita_iva')
                        if piva:
                            st.caption(f"🏢 {piva}")
                        else:
                            st.caption("⚠️ P.IVA mancante")
                
                with col3:
                    st.caption(f"📄 {row['num_fatture']}")
                
                with col4:
                    st.caption(f"📊 {row['num_righe']}")
                
                with col5:
                    # Mostra totale costi complessivi formattato
                    costi_totali = row.get('totale_costi', 0)
                    if costi_totali > 0:
                        st.caption(f"💰 €{costi_totali:,.2f}")
                    else:
                        st.caption("💰 €0,00")
                
                with col6:
                    if pd.notna(row['ultimo_caricamento']):
                        now_aware = pd.Timestamp.now(tz=timezone.utc)
                        giorni_fa = (now_aware - row['ultimo_caricamento']).days
                        
                        if giorni_fa == 0:
                            st.caption("🟢 Oggi")
                        elif giorni_fa < 7:
                            st.caption(f"🟢 {giorni_fa}g fa")
                        elif giorni_fa < 30:
                            st.caption(f"🟡 {giorni_fa}g fa")
                        else:
                            st.caption(f"🔴 {giorni_fa}g fa")
                    else:
                        st.caption("⚪ Mai")
                
                with col7:
                    # ===== BOTTONI AZIONI =====
                    col_entra, col_menu = st.columns([1, 0.3])
                    
                    with col_entra:
                        # Bottone impersonazione
                        if st.button("👁️ Entra", key=f"impersona_{row['user_id']}", type="secondary", use_container_width=True):
                            # Salva admin originale
                            st.session_state.admin_original_user = st.session_state.user_data.copy()
                            st.session_state.impersonating = True
                            
                            # Imposta dati cliente
                            cliente_data = {
                                'id': row['user_id'],
                                'email': row['email'],
                                'nome_ristorante': row['ristorante'],
                                'attivo': row['attivo']
                            }
                            st.session_state.user_data = cliente_data
                            
                            # Disabilita flag admin per cliente impersonato
                            st.session_state.user_is_admin = False
                            
                            # Log
                            logger.info(f"🔀 IMPERSONAZIONE: admin={st.session_state.admin_original_user['email']} → cliente={row['email']}")
                            
                            # Redirect
                            st.success(f"✅ Accesso come: {row['email']}")
                            time.sleep(0.8)
                            st.switch_page("app.py")
                
                # DEBUG INFO (espandibile)
                if 'debug' in row:
                    debug = row['debug']
                    with st.expander(f"🔍 Debug {row['email']}", expanded=False):
                        col_d1, col_d2, col_d3, col_d4, col_d5 = st.columns(5)
                        with col_d1:
                            st.metric("Raw", debug['totale_raw'])
                        with col_d2:
                            st.metric("- Note", debug['escluse_note'])
                        with col_d3:
                            st.metric("- Review", debug['escluse_review'])
                        with col_d4:
                            st.metric("- Date Invalid", debug['escluse_date_invalide'])
                        with col_d5:
                            st.metric("✅ Finale", debug['incluse_finale'])
                        
                        st.divider()
                        col_t1, col_t2 = st.columns(2)
                        with col_t1:
                            st.info(f"💰 **Somma calcolata**: €{debug['somma_totale_riga']:,.2f}")
                        with col_t2:
                            st.info(f"💰 **Totale finale**: €{row['totale_costi']:,.2f}")
                        
                        if debug['righe_con_date']:
                            st.markdown("**Sample prime 5 righe incluse:**")
                            for riga in debug['righe_con_date']:
                                st.caption(f"📅 {riga['data']} | €{riga['importo']:.2f} | {riga['categoria']}")
                    
                    with col_menu:
                        # Menu azioni aggiuntive
                        with st.popover("⚙️", use_container_width=True):
                            st.markdown("**Azioni Cliente**")
                            
                            # AZIONE 1: Attiva/Disattiva
                            stato_attuale = row['attivo']
                            if stato_attuale:
                                if st.button("🔴 Disattiva Account", key=f"disattiva_{row['user_id']}", type="secondary", use_container_width=True):
                                    try:
                                        supabase.table('users')\
                                            .update({'attivo': False})\
                                            .eq('id', row['user_id'])\
                                            .execute()
                                        
                                        logger.info(f"🔴 Account disattivato: {row['email']}")
                                        st.success(f"Account {row['email']} disattivato")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore: {e}")
                            else:
                                if st.button("🟢 Attiva Account", key=f"attiva_{row['user_id']}", type="primary", use_container_width=True):
                                    try:
                                        supabase.table('users')\
                                            .update({'attivo': True})\
                                            .eq('id', row['user_id'])\
                                            .execute()
                                        
                                        logger.info(f"🟢 Account attivato: {row['email']}")
                                        st.success(f"Account {row['email']} attivato")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore: {e}")
                            
                            st.markdown("---")
                            
                            # AZIONE 2: Invia Email Reset Password (GDPR compliant)
                            st.markdown("**Reset Password**")
                            st.caption("Il cliente riceverà un'email per impostare la nuova password")
                            
                            if st.button("📧 Invia Email Reset", key=f"reset_{row['user_id']}", type="primary", use_container_width=True):
                                try:
                                    import uuid
                                    from datetime import datetime, timedelta
                                    
                                    # Genera token reset (1 ora validità)
                                    reset_token = str(uuid.uuid4())
                                    expires_at = datetime.now() + timedelta(hours=1)
                                    
                                    # Salva token nel database
                                    supabase.table('users')\
                                        .update({
                                            'reset_token': reset_token,
                                            'reset_token_expires_at': expires_at.isoformat()
                                        })\
                                        .eq('id', row['user_id'])\
                                        .execute()
                                    
                                    # Invia email con link reset
                                    from services.email_service import invia_email
                                    
                                    # Costruisci URL reset
                                    base_url = st.secrets.get("app", {}).get("base_url", "http://localhost:8501")
                                    reset_url = f"{base_url}/?reset_token={reset_token}"
                                    
                                    email_inviata = invia_email(
                                        destinatario=row['email'],
                                        oggetto="🔑 Reset Password - ANALISI FATTURE AI",
                                        corpo_html=f"""
                                        <h2>Reset Password Richiesto</h2>
                                        <p>Ciao,</p>
                                        <p>L'amministratore ha richiesto un reset della tua password.</p>
                                        <p>Clicca sul link per impostare una nuova password:</p>
                                        <p><a href="{reset_url}" style="background-color:#4CAF50;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;">Imposta Nuova Password</a></p>
                                        <p><small>Link valido per 1 ora: {reset_url}</small></p>
                                        <hr>
                                        <p><small>Se non hai richiesto questo reset, ignora questa email.</small></p>
                                        """
                                    )
                                    
                                    if email_inviata:
                                        logger.info(f"📧 Email reset password inviata a: {row['email']}")
                                        st.success(f"✅ Email inviata a {row['email']}")
                                    else:
                                        st.warning(f"⚠️ Token generato ma email non inviata. Link: {reset_url}")
                                    
                                    time.sleep(1.5)
                                    st.rerun()
                                except Exception as e:
                                    # Fallback se colonne reset_token non esistono
                                    if '42703' in str(e) or 'does not exist' in str(e):
                                        st.error("⚠️ Esegui migrazione 009 per abilitare reset password via email")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore invio email reset: {e}")
                            
                            st.markdown("---")
                            
                            # AZIONE 3: Elimina Account Completo (2 click)
                            st.markdown("**⚠️ Zona Pericolosa**")
                            
                            if st.button("🗑️ Elimina Account", key=f"elimina_btn_{row['user_id']}", type="secondary", use_container_width=True):
                                st.session_state[f"show_delete_dialog_{row['user_id']}"] = True
                            
                            # Dialog conferma (solo se attivato)
                            if st.session_state.get(f"show_delete_dialog_{row['user_id']}", False):
                                @st.dialog("⚠️ Conferma Eliminazione Account")
                                def show_delete_confirmation():
                                    # CONTROLLO SICUREZZA: Impedisci eliminazione dell'admin
                                    admin_email = st.session_state.user_data.get('email')
                                    if row['email'] == admin_email or row['email'] in ADMIN_EMAILS:
                                        st.error("🚫 **ERRORE**: Non puoi eliminare il tuo account admin o altri account admin!")
                                        st.info("Se vuoi rimuovere un amministratore, contatta il supporto tecnico.")
                                        if st.button("❌ Chiudi", use_container_width=True):
                                            st.session_state[f"show_delete_dialog_{row['user_id']}"] = False
                                            st.rerun()
                                        return
                                    
                                    st.warning(
                                        f"**Stai per eliminare definitivamente:**\n\n"
                                        f"👤 **{row['email']}** ({row['ristorante']})\n\n"
                                        f"📊 **Dati che verranno eliminati:**\n"
                                        f"- Account utente\n"
                                        f"- {row['num_fatture']} fatture\n"
                                        f"- {row['num_righe']} righe prodotto\n"
                                        f"- Log upload\n\n"
                                        f"✅ **Memoria globale preservata (default):**\n"
                                        f"- Categorizzazioni condivise\n"
                                        f"- Contributi alla memoria collettiva\n\n"
                                        f"⚠️ **Questa azione è IRREVERSIBILE**"
                                    )
                                    
                                    # Checkbox opzionale per eliminare memoria globale
                                    st.markdown("---")
                                    elimina_memoria = st.checkbox(
                                        "🗑️ Elimina anche contributi alla memoria globale",
                                        value=False,
                                        key=f"elimina_mem_{row['user_id']}",
                                        help="Se attivo, rimuove le categorizzazioni di questo cliente dal database condiviso (prodotti_master)"
                                    )
                                    
                                    if elimina_memoria:
                                        st.warning("⚠️ Verranno eliminati anche i contributi alla memoria AI condivisa")
                                    
                                    st.markdown("---")
                                    
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        if st.button("❌ Annulla", use_container_width=True):
                                            st.session_state[f"show_delete_dialog_{row['user_id']}"] = False
                                            st.rerun()
                                    
                                    with col2:
                                        if st.button("🗑️ Sì, elimina definitivamente", type="primary", use_container_width=True):
                                            try:
                                                with st.spinner(f"Eliminazione {row['email']}..."):
                                                    user_id_to_delete = row['user_id']
                                                    email_deleted = row['email']
                                                    
                                                    # Contatori eliminazioni
                                                    deleted = {
                                                        'fatture': 0,
                                                        'prodotti': 0,
                                                        'upload_events': 0,
                                                        'memoria_globale': 0
                                                    }
                                                    
                                                    # 1. Elimina fatture
                                                    try:
                                                        result_fatture = supabase.table('fatture')\
                                                            .delete()\
                                                            .eq('user_id', user_id_to_delete)\
                                                            .execute()
                                                        deleted['fatture'] = len(result_fatture.data) if result_fatture.data else 0
                                                    except Exception as e:
                                                        logger.warning(f"Errore eliminazione fatture: {e}")
                                                    
                                                    # 2. Elimina prodotti_utente (dati locali)
                                                    try:
                                                        result_prodotti = supabase.table('prodotti_utente')\
                                                            .delete()\
                                                            .eq('user_id', user_id_to_delete)\
                                                            .execute()
                                                        deleted['prodotti'] = len(result_prodotti.data) if result_prodotti.data else 0
                                                    except Exception as e:
                                                        logger.warning(f"Errore eliminazione prodotti: {e}")
                                                    
                                                    # 3. Elimina upload_events
                                                    try:
                                                        result_events = supabase.table('upload_events')\
                                                            .delete()\
                                                            .eq('user_id', user_id_to_delete)\
                                                            .execute()
                                                        deleted['upload_events'] = len(result_events.data) if result_events.data else 0
                                                    except Exception as e:
                                                        logger.warning(f"Errore eliminazione upload_events: {e}")
                                                    
                                                    # 4. Eliminazione CONDIZIONALE memoria globale
                                                    if elimina_memoria:
                                                        try:
                                                            result_master = supabase.table('prodotti_master')\
                                                                .delete()\
                                                                .eq('user_id', user_id_to_delete)\
                                                                .execute()
                                                            deleted['memoria_globale'] = len(result_master.data) if result_master.data else 0
                                                            logger.info(f"🗑️ Memoria globale eliminata: {deleted['memoria_globale']} record")
                                                        except Exception as e:
                                                            logger.warning(f"Errore eliminazione memoria globale: {e}")
                                                    
                                                    # 5. Elimina utente (con doppia verifica sicurezza)
                                                    # Verifica che user_id non sia None/vuoto
                                                    if not user_id_to_delete:
                                                        raise ValueError("user_id_to_delete è vuoto!")
                                                    
                                                    # Verifica che non sia l'admin
                                                    if email_deleted in ADMIN_EMAILS:
                                                        raise ValueError(f"Tentativo di eliminare admin: {email_deleted}")
                                                    
                                                    logger.warning(f"🗑️ Eliminazione utente: {email_deleted} (ID: {user_id_to_delete})")
                                                    
                                                    result_user = supabase.table('users')\
                                                        .delete()\
                                                        .eq('id', user_id_to_delete)\
                                                        .execute()
                                                    
                                                    # Verifica che l'eliminazione abbia funzionato
                                                    if not result_user.data:
                                                        logger.error(f"⚠️ Eliminazione utente fallita per ID: {user_id_to_delete}")
                                                    
                                                    # 6. Invalida cache
                                                    try:
                                                        invalida_cache_memoria()
                                                        st.cache_data.clear()
                                                    except Exception as e:
                                                        logger.warning(f"Errore invalidazione cache: {e}")
                                                    
                                                    # Log operazione
                                                    memoria_status = f"ELIMINATA ({deleted['memoria_globale']} record)" if elimina_memoria else "PRESERVATA"
                                                    logger.warning(
                                                        f"🗑️ ELIMINAZIONE ACCOUNT | "
                                                        f"Admin: {st.session_state.user_data['email']} | "
                                                        f"Cliente: {email_deleted} | "
                                                        f"Fatture: {deleted['fatture']} | "
                                                        f"Prodotti locali: {deleted['prodotti']} | "
                                                        f"Events: {deleted['upload_events']} | "
                                                        f"Memoria globale: {memoria_status}"
                                                    )
                                                    
                                                    st.success(f"✅ Account {email_deleted} eliminato")
                                                    
                                                    # Messaggio riepilogo con stato memoria
                                                    info_msg = (
                                                        f"📊 **Dati eliminati:**\n"
                                                        f"- Fatture: {deleted['fatture']}\n"
                                                        f"- Prodotti locali: {deleted['prodotti']}\n"
                                                        f"- Upload Events: {deleted['upload_events']}\n\n"
                                                    )
                                                    
                                                    if elimina_memoria:
                                                        info_msg += f"🗑️ Memoria globale: {deleted['memoria_globale']} contributi eliminati"
                                                    else:
                                                        info_msg += "✅ Memoria globale condivisa preservata"
                                                    
                                                    st.info(info_msg)
                                                    
                                                    # Reset dialog
                                                    st.session_state[f"show_delete_dialog_{row['user_id']}"] = False
                                                    time.sleep(2)
                                                    st.rerun()
                                                    
                                            except Exception as e:
                                                st.error(f"❌ Errore eliminazione: {e}")
                                                logger.exception(f"Errore critico eliminazione {row['email']}")
                                
                                show_delete_confirmation()
                
                st.markdown("---")
    
    except Exception as e:
        st.error(f"❌ Errore caricamento clienti: {e}")
        logger.exception("Errore gestione clienti")
        import traceback
        st.code(traceback.format_exc())
    
    # ════════════════════════════════════════════════════════════════════════════
    # SEZIONE: GESTIONE MULTI-RISTORANTE (STEP 2)
    # ════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("### 🏢 Gestione Multi-Ristorante")
    st.caption("Aggiungi o rimuovi ristoranti per cliente (ciascuno con P.IVA unica)")
    
    try:
        # Carica clienti
        query_users_mr = supabase.table('users')\
            .select('id, email, nome_ristorante')\
            .order('email')\
            .execute()
        
        if query_users_mr.data:
            # Dropdown selezione cliente
            cliente_emails = [u['email'] for u in query_users_mr.data]
            cliente_selezionato = st.selectbox(
                "👤 Seleziona Cliente",
                options=cliente_emails,
                key="select_cliente_multi_rist"
            )
            
            if cliente_selezionato:
                # Trova user selezionato
                user_sel = next((u for u in query_users_mr.data if u['email'] == cliente_selezionato), None)
                
                if user_sel:
                    # Carica ristoranti di questo utente
                    ristoranti_query = supabase.table('ristoranti')\
                        .select('*')\
                        .eq('user_id', user_sel['id'])\
                        .execute()
                    
                    ristoranti_list = ristoranti_query.data if ristoranti_query.data else []
                    num_ristoranti = len(ristoranti_list)
                    
                    col_info, col_azioni = st.columns([2, 3])
                    
                    with col_info:
                        st.metric("🏪 Ristoranti configurati", num_ristoranti)
                        st.caption(f"📧 {cliente_selezionato}")
                        
                        # Lista ristoranti attuali
                        if num_ristoranti > 0:
                            st.markdown("**Ristoranti attivi:**")
                            for idx, r in enumerate(ristoranti_list, 1):
                                status_icon = "✅" if r.get('attivo') else "🔴"
                                st.write(f"{idx}. {status_icon} **{r['nome_ristorante']}**")
                                st.caption(f"   📋 P.IVA: `{r['partita_iva']}` | {r.get('ragione_sociale', 'N/A')}")
                    
                    with col_azioni:
                        # AZIONE: Aggiungi Ristorante
                        with st.expander("➕ Aggiungi Nuovo Ristorante", expanded=False):
                            with st.form(f"form_nuovo_ristorante_{user_sel['id']}"):
                                st.markdown("**Nuovo Ristorante**")
                                
                                new_nome = st.text_input("Nome Ristorante *", placeholder="Es: Trattoria Mario 2")
                                new_piva_mr = st.text_input("P.IVA * (11 cifre)", placeholder="12345678901", max_chars=11)
                                new_ragione_mr = st.text_input("Ragione Sociale", placeholder="Opzionale")
                                
                                # Validazione real-time P.IVA
                                if new_piva_mr:
                                    from utils.piva_validator import valida_formato_piva, normalizza_piva
                                    piva_norm_mr = normalizza_piva(new_piva_mr)
                                    if len(piva_norm_mr) == 11:
                                        valida_mr, msg_mr = valida_formato_piva(piva_norm_mr)
                                        if valida_mr:
                                            st.success(f"✅ P.IVA valida: {piva_norm_mr}")
                                        else:
                                            st.error(msg_mr)
                                
                                if st.form_submit_button("✅ Crea Ristorante", type="primary", use_container_width=True):
                                    if not new_nome or not new_piva_mr:
                                        st.error("❌ Nome e P.IVA obbligatori")
                                    else:
                                        from utils.piva_validator import valida_formato_piva, normalizza_piva
                                        piva_norm_mr = normalizza_piva(new_piva_mr)
                                        valida_mr, msg_mr = valida_formato_piva(piva_norm_mr)
                                        
                                        if not valida_mr:
                                            st.error(msg_mr)
                                        else:
                                            try:
                                                # Verifica P.IVA non duplicata
                                                check_piva = supabase.table('ristoranti')\
                                                    .select('id')\
                                                    .eq('partita_iva', piva_norm_mr)\
                                                    .execute()
                                                
                                                if check_piva.data:
                                                    st.error(f"❌ P.IVA {piva_norm_mr} già registrata")
                                                else:
                                                    # Inserisci nuovo ristorante
                                                    supabase.table('ristoranti').insert({
                                                        'user_id': user_sel['id'],
                                                        'nome_ristorante': new_nome,
                                                        'partita_iva': piva_norm_mr,
                                                        'ragione_sociale': new_ragione_mr if new_ragione_mr else None,
                                                        'attivo': True
                                                    }).execute()
                                                    
                                                    logger.info(f"✅ Ristorante creato: {new_nome} (P.IVA: {piva_norm_mr}) per {cliente_selezionato}")
                                                    st.success(f"✅ Ristorante **{new_nome}** creato!")
                                                    time.sleep(1)
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"❌ Errore creazione: {e}")
                                                logger.exception(f"Errore creazione ristorante per {cliente_selezionato}")
                        
                        # AZIONE: Elimina Ristorante
                        if num_ristoranti > 0:
                            with st.expander("🗑️ Elimina Ristorante", expanded=False):
                                st.warning("⚠️ Eliminazione permanente")
                                
                                rist_da_eliminare = st.selectbox(
                                    "Ristorante da eliminare",
                                    options=ristoranti_list,
                                    format_func=lambda r: f"{r['nome_ristorante']} (P.IVA: {r['partita_iva']})",
                                    key=f"select_elimina_rist_{user_sel['id']}"
                                )
                                
                                if rist_da_eliminare:
                                    st.caption(f"⚠️ Verranno eliminate anche tutte le fatture associate")
                                    
                                    if st.button(f"🗑️ Elimina {rist_da_eliminare['nome_ristorante']}", 
                                                type="secondary", 
                                                key=f"btn_elimina_{rist_da_eliminare['id']}"):
                                        try:
                                            # Elimina ristorante (cascade elimina anche fatture via FK)
                                            supabase.table('ristoranti')\
                                                .delete()\
                                                .eq('id', rist_da_eliminare['id'])\
                                                .execute()
                                            
                                            logger.warning(f"🗑️ Ristorante eliminato: {rist_da_eliminare['nome_ristorante']} di {cliente_selezionato}")
                                            st.success("✅ Ristorante eliminato!")
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Errore eliminazione: {e}")
                                            logger.exception(f"Errore eliminazione ristorante {rist_da_eliminare['id']}")
        else:
            st.info("📭 Nessun cliente registrato")
    
    except Exception as e:
        st.error(f"❌ Errore gestione multi-ristorante: {e}")
        logger.exception("Errore sezione multi-ristorante")

# ============================================================
# TAB 2: REVIEW RIGHE €0 CON SISTEMA CONFERMA
# ============================================================

if tab2:
    st.markdown("## 📊 Review Righe Prezzo €0")
    st.caption("Verifica righe con prezzo €0 - potrebbero essere omaggi o diciture")
    
    # ============================================================
    # FILTRO PER CLIENTE
    # ============================================================
    st.markdown("### 👥 Seleziona Cliente")
    
    try:
        clienti_response = supabase.table('users')\
            .select('id, email, nome_ristorante')\
            .eq('attivo', True)\
            .order('nome_ristorante', desc=False)\
            .execute()
        
        clienti = clienti_response.data if clienti_response.data else []
        
        # Opzione "Tutti" all'inizio
        opzioni_clienti = [{'id': 'TUTTI', 'email': 'Tutti i clienti', 'nome_ristorante': 'Tutti'}] + clienti
        
        cliente_selezionato = st.selectbox(
            "Visualizza problemi di",
            opzioni_clienti,
            format_func=lambda x: f"🌐 {x['nome_ristorante']}" if x['id'] == 'TUTTI' else f"👤 {x['nome_ristorante']} ({x['email']})",
            key="filtro_cliente_review"
        )
        
        filtro_cliente_id = None if cliente_selezionato['id'] == 'TUTTI' else cliente_selezionato['id']
        
    except Exception as e:
        st.error(f"Errore caricamento clienti: {e}")
        filtro_cliente_id = None
    
    st.markdown("---")
    
    # ============================================================
    # CARICAMENTO RIGHE €0 CON FILTRO CLIENTE
    # ============================================================
    @st.cache_data(ttl=60, show_spinner=False)
    def carica_righe_zero_con_filtro(cliente_id=None):
        """
        Carica righe da validare: €0 OPPURE needs_review=true.
        Query singola ottimizzata con OR.
        
        Args:
            cliente_id: UUID cliente o None per tutti
            
        Returns:
            DataFrame con righe da validare
        """
        try:
            # Query singola con OR per entrambe le condizioni
            query = supabase.table('fatture')\
                .select('id, descrizione, categoria, fornitore, file_origine, data_documento, user_id, prezzo_unitario, needs_review, reviewed_at, reviewed_by')\
                .or_('prezzo_unitario.eq.0,needs_review.eq.true')
            
            # Applica filtro cliente se specificato
            if cliente_id:
                query = query.eq('user_id', cliente_id)
            
            response = query.execute()
            
            df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            # Log statistiche
            if not df.empty:
                n_zero = len(df[df['prezzo_unitario'] == 0]) if 'prezzo_unitario' in df.columns else 0
                n_review = len(df[df['needs_review'] == True]) if 'needs_review' in df.columns else 0
                logger.info(f"🔍 Righe da validare: {n_zero} €0 | {n_review} needs_review | {len(df)} totali (dedup)")
            
            return df
            
        except Exception as e:
            logger.error(f"Errore caricamento righe review: {e}")
            return pd.DataFrame()
    
    df_zero = carica_righe_zero_con_filtro(filtro_cliente_id)
    
    if df_zero.empty:
        st.success("✅ Nessuna riga da revisionare!")
        st.stop()
    
    # ============================================================
    # STATISTICHE
    # ============================================================
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Righe Totali €0", len(df_zero))
    
    with col2:
        # Calcola categorie sospette
        cat_sospette = df_zero[~df_zero['categoria'].isin(['NOTE E DICITURE', 'Da Classificare'])]
        st.metric("Prodotti Classificati", len(cat_sospette))
    
    with col3:
        # Info cliente selezionato
        if filtro_cliente_id:
            st.metric("Cliente", cliente_selezionato['nome_ristorante'][:20])
        else:
            st.metric("Cliente", "Tutti")
    
    st.markdown("---")
    
    # ============================================================
    # FILTRO PER CATEGORIA
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_cat, col_forn = st.columns(2)
    
    with col_cat:
        cat_uniche = ['Tutte'] + sorted(df_zero['categoria'].unique().tolist())
        filtro_categoria = st.selectbox(
            "Filtra per categoria",
            cat_uniche,
            key="filtro_cat_zero"
        )
    
    with col_forn:
        forn_unici = ['Tutti'] + sorted(df_zero['fornitore'].dropna().unique().tolist())
        filtro_fornitore = st.selectbox(
            "Filtra per fornitore",
            forn_unici,
            key="filtro_forn_zero"
        )
    
    # Applica filtri
    df_display = df_zero.copy()
    
    # Traccia filtri precedenti per reset pagina
    filtri_correnti = f"{filtro_categoria}_{filtro_fornitore}"
    if 'filtri_review_prev' not in st.session_state:
        st.session_state.filtri_review_prev = filtri_correnti
    elif st.session_state.filtri_review_prev != filtri_correnti:
        # Filtri cambiati: reset pagina
        st.session_state.pagina_review = 0
        st.session_state.filtri_review_prev = filtri_correnti
    
    if filtro_categoria != 'Tutte':
        df_display = df_display[df_display['categoria'] == filtro_categoria]
    
    if filtro_fornitore != 'Tutti':
        df_display = df_display[df_display['fornitore'] == filtro_fornitore]
    
    # ============================================================
    # RAGGRUPPA PER DESCRIZIONE (una riga = tutte le occorrenze)
    # ============================================================
    df_grouped = df_display.groupby('descrizione', as_index=False).agg({
        'id': 'first',  # Prendi primo ID (per chiave bottone)
        'categoria': 'first',  # Prima categoria trovata
        'fornitore': 'first',  # Primo fornitore
        'file_origine': lambda x: ', '.join(set(x.dropna().astype(str)))[:30]  # File unici (max 30 char)
    })
    
    # Aggiungi colonna occorrenze
    df_grouped['occorrenze'] = df_display.groupby('descrizione').size().values
    
    # ORDINA ALFABETICAMENTE per descrizione
    df_grouped = df_grouped.sort_values('descrizione').reset_index(drop=True)
    
    # ============================================================
    # PAGINAZIONE PER PERFORMANCE (25 righe = più veloce)
    # ============================================================
    RIGHE_PER_PAGINA = 25
    totale_righe = len(df_grouped)
    
    # Inizializza pagina corrente
    if 'pagina_review' not in st.session_state:
        st.session_state.pagina_review = 0
    
    num_pagine = (totale_righe + RIGHE_PER_PAGINA - 1) // RIGHE_PER_PAGINA
    
    col_info, col_pag = st.columns([2, 1])
    
    with col_info:
        st.info(f"📋 Mostrando {totale_righe} descrizioni uniche ({len(df_display)} righe totali)")
    
    with col_pag:
        if num_pagine > 1:
            pagina = st.number_input(
                f"Pag. (max {num_pagine})",
                min_value=1,
                max_value=num_pagine,
                value=st.session_state.pagina_review + 1,
                step=1,
                key="input_pagina_review",
                label_visibility="visible"
            )
            st.session_state.pagina_review = pagina - 1
    
    if df_grouped.empty:
        st.info("Nessuna riga con questi filtri")
        st.stop()
    
    # Applica paginazione
    inizio = st.session_state.pagina_review * RIGHE_PER_PAGINA
    fine = min(inizio + RIGHE_PER_PAGINA, totale_righe)
    df_pagina = df_grouped.iloc[inizio:fine]
    
    if num_pagine > 1:
        st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")
    
    # ============================================================
    # INIZIALIZZA MODIFICHE PENDENTI
    # ============================================================
    if 'modifiche_review' not in st.session_state:
        st.session_state.modifiche_review = {}
    
    st.markdown("---")
    
    # ============================================================
    # TABELLA CON 2 AZIONI PER DESCRIZIONE UNICA
    # ============================================================
    num_modifiche = len(st.session_state.modifiche_review)
    
    if num_modifiche > 0:
        st.markdown(f"### 📝 Righe da Revisionare | 🔸 **{num_modifiche} modifiche pendenti**")
    else:
        st.markdown("### 📝 Righe da Revisionare (raggruppate)")
    
    # HEADER
    col_desc, col_occur, col_cat, col_forn, col_azioni = st.columns([3, 0.7, 1.5, 1.5, 1.5])
    
    with col_desc:
        st.markdown("**Descrizione**")
    
    with col_occur:
        st.markdown("**N°**")
    
    with col_cat:
        st.markdown("**Categoria**")
    
    with col_forn:
        st.markdown("**Fornitore**")
    
    with col_azioni:
        st.markdown("**Azioni**")
    
    st.markdown("---")
    
    # RIGHE PAGINATE - Usa categorie da cache
    categorie = st.session_state.categorie_cached
    
    admin_email = user.get('email', 'admin')
    
    for idx, row in df_pagina.iterrows():
        row_id = row['id']
        descrizione = row['descrizione']
        categoria_corrente = row['categoria']
        fornitore = row.get('fornitore', 'N/A')
        occorrenze = row['occorrenze']
        
        col_desc, col_occur, col_cat, col_forn, col_azioni = st.columns([3, 0.7, 1.5, 1.5, 1.5])
        
        # DESCRIZIONE + Badge review
        with col_desc:
            # Accesso sicuro a needs_review dalla riga corrente
            needs_review_flag = row.get('needs_review', False) if 'needs_review' in df_pagina.columns else False
            review_badge = "🔍 " if needs_review_flag else ""
            desc_short = descrizione[:45] + "..." if len(descrizione) > 45 else descrizione
            st.markdown(f"`{review_badge}{desc_short}`")
        
        # OCCORRENZE
        with col_occur:
            st.markdown(f"`{occorrenze}×`")
        
        # CATEGORIA ATTUALE
        with col_cat:
            cat_short = categoria_corrente[:20] if categoria_corrente else "N/A"
            st.text(cat_short)
        
        # FORNITORE
        with col_forn:
            forn_short = fornitore[:15] if fornitore else "N/A"
            st.caption(forn_short)
        
        # AZIONI - Bottoni Ignora e Modifica
        with col_azioni:
            col_a1, col_a2 = st.columns(2)
            
            with col_a1:
                # Bottone IGNORA
                if st.button("❌", key=f"ignore_{idx}", help="Ignora definitivamente"):
                    try:
                        from datetime import datetime
                        result = supabase.table('fatture').update({
                            'categoria': '📝 NOTE E DICITURE',
                            'needs_review': False,
                            'reviewed_at': datetime.now().isoformat(),
                            'reviewed_by': 'admin'
                        }).eq('descrizione', descrizione).execute()
                        
                        st.success(f"❌ {len(result.data) if result.data else occorrenze} righe ignorate")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore: {e}")
            
            with col_a2:
                # Bottone MODIFICA (apre expander)
                if st.button("✏️", key=f"edit_{idx}", help="Modifica categoria"):
                    st.session_state[f"editing_{idx}"] = True
                    st.rerun()
        
        # EXPANDER PER MODIFICA CATEGORIA
        if st.session_state.get(f"editing_{idx}", False):
            with st.expander(f"🔧 Modifica: {descrizione[:30]}...", expanded=True):
                # Usa categorie standardizzate da constants.py + NOTE E DICITURE solo qui
                from config.constants import (
                    CATEGORIE_FOOD_BEVERAGE, 
                    CATEGORIE_MATERIALI, 
                    CATEGORIE_SPESE_OPERATIVE
                )
                
                # Combina e ordina categorie
                categorie_fb = sorted(CATEGORIE_FOOD_BEVERAGE + CATEGORIE_MATERIALI)
                categorie_spese = sorted(CATEGORIE_SPESE_OPERATIVE)
                
                # NOTE E DICITURE disponibile SOLO nel tab Review Righe €0
                categorie_review = ["NOTE E DICITURE"] + categorie_spese + categorie_fb
                
                nuova_categoria = st.selectbox(
                    "Nuova categoria:",
                    categorie_review,
                    key=f"newcat_{idx}"
                )
                
                col_confirm, col_cancel = st.columns(2)
                
                with col_confirm:
                    if st.button("✅ Conferma", key=f"confirm_{idx}"):
                        try:
                            from datetime import datetime
                            result = supabase.table('fatture').update({
                                'categoria': nuova_categoria,
                                'needs_review': False,
                                'reviewed_at': datetime.now().isoformat(),
                                'reviewed_by': 'admin'
                            }).eq('descrizione', descrizione).execute()
                            
                            st.success(f"✅ {len(result.data) if result.data else occorrenze} righe → {nuova_categoria}")
                            del st.session_state[f"editing_{idx}"]
                            st.cache_data.clear()
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")
                
                with col_cancel:
                    if st.button("🚫 Annulla", key=f"cancel_{idx}"):
                        del st.session_state[f"editing_{idx}"]
                        st.rerun()
        
        st.markdown("---")
    
    # ============================================================
    # BARRA AZIONI BATCH (se ci sono modifiche)
    # ============================================================
    if num_modifiche > 0:
        st.markdown("---")
        st.markdown("### 💾 Salvataggio Batch")
        
        # Info modifiche
        totale_righe_affected = sum(m['occorrenze'] for m in st.session_state.modifiche_review.values())
        st.info(f"📊 **{num_modifiche}** descrizioni modificate → **{totale_righe_affected}** righe totali")
        
        # Mostra preview modifiche
        with st.expander("🔍 Preview Modifiche", expanded=False):
            for desc, info in list(st.session_state.modifiche_review.items())[:10]:
                desc_short = desc[:50] + "..." if len(desc) > 50 else desc
                st.markdown(f"- `{desc_short}` ({info['occorrenze']}×): {info['categoria_originale']} → **{info['nuova_categoria']}**")
            if num_modifiche > 10:
                st.caption(f"... e altre {num_modifiche - 10} modifiche")
        
        # Bottoni azione - TAB 3 REVIEW
        col_save, col_cancel, col_export = st.columns([2, 1, 1.5])
        
        with col_save:
            if st.button(f"💾 Salva Tutte ({num_modifiche})", type="primary", use_container_width=True, key="save_review_batch"):
                with st.spinner(f"💾 Salvataggio {num_modifiche} modifiche in corso..."):
                    success_count = 0
                    total_rows = 0
                    
                    for descrizione, info in st.session_state.modifiche_review.items():
                        try:
                            result = supabase.table('fatture').update({
                                'categoria': info['nuova_categoria']
                            }).eq('descrizione', descrizione).execute()
                            
                            num_updated = len(result.data) if result.data else info['occorrenze']
                            success_count += 1
                            total_rows += num_updated
                            
                        except Exception as e:
                            logger.error(f"Errore salvataggio '{descrizione}': {e}")
                    
                    # Reset modifiche
                    st.session_state.modifiche_review = {}
                    st.cache_data.clear()
                    
                    st.success(f"✅ {success_count} modifiche salvate! {total_rows} righe aggiornate.")
                    time.sleep(1.5)
                    st.rerun()
        
        with col_cancel:
            if st.button("❌ Annulla Tutte", use_container_width=True, key="cancel_review_batch"):
                st.session_state.modifiche_review = {}
                st.rerun()
        
        with col_export:
            # Prepara CSV modifiche
            export_data = []
            for desc, info in st.session_state.modifiche_review.items():
                export_data.append({
                    'Descrizione': desc,
                    'Occorrenze': info['occorrenze'],
                    'Categoria Originale': info['categoria_originale'],
                    'Nuova Categoria': info['nuova_categoria']
                })
            df_export = pd.DataFrame(export_data)
            csv = df_export.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📄 Export CSV",
                data=csv,
                file_name=f"modifiche_review_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="export_review_csv"
            )

# ============================================================
# FOOTER
# ============================================================
# TAB 3: MEMORIA GLOBALE AI - TABELLA UNIFICATA
# ============================================================

def tab_memoria_globale_unificata():
    """
    TAB Memoria Globale - VERSIONE DEFINITIVA
    - Mostra TUTTE le righe filtrate (no limite)
    - Scroll nativo Streamlit
    - Checkbox master funzionante
    - Info semplice
    """
    st.markdown("## 🧠 Memoria Globale Prodotti")
    st.caption("Gestisci classificazioni condivise tra tutti i clienti")
    
    # Funzione helper per toggle massivo
    def toggle_all_rows(righe_ids, seleziona):
        """Seleziona o deseleziona tutte le righe della pagina"""
        if seleziona:
            st.session_state.righe_selezionate.update(righe_ids)
        else:
            st.session_state.righe_selezionate.difference_update(righe_ids)
    
    # ============================================================
    # IDENTIFICA RUOLO
    # ============================================================
    user = st.session_state.get('user_data', {})
    user_email = user.get('email', '')
    is_admin = user_email in ADMIN_EMAILS
    
    if is_admin:
        st.info("🔧 **MODALITÀ ADMIN**: Modifiche applicate GLOBALMENTE")
    else:
        st.info("👤 **MODALITÀ CLIENTE**: Personalizzazioni solo tue")
    
    # ============================================================
    # CARICAMENTO DATI
    # ============================================================
    @st.cache_data(ttl=60, show_spinner=False)
    def carica_memoria_completa():
        try:
            campo_verified_exists = False
            if is_admin:
                # Prova prima con verified, se fallisce usa query base (retrocompatibilità)
                try:
                    response = supabase.table('prodotti_master')\
                        .select('id, descrizione, categoria, volte_visto, created_at, verified')\
                        .order('volte_visto', desc=True)\
                        .execute()
                    campo_verified_exists = True
                except Exception:
                    # Campo verified non esiste ancora, usa query senza
                    response = supabase.table('prodotti_master')\
                        .select('id, descrizione, categoria, volte_visto, created_at')\
                        .order('volte_visto', desc=True)\
                        .execute()
            else:
                user_id = user.get('id')
                response = supabase.table('prodotti_utente')\
                    .select('id, descrizione, categoria, volte_visto, created_at')\
                    .eq('user_id', user_id)\
                    .order('volte_visto', desc=True)\
                    .execute()
            
            df = pd.DataFrame(response.data)
            # Aggiungi colonna verified se non esiste (solo per UI, non nel DB)
            if 'verified' not in df.columns:
                df['verified'] = False  # Default: da verificare
            return df, campo_verified_exists
        except Exception as e:
            logger.error(f"Errore caricamento memoria: {e}")
            return pd.DataFrame(), False
    
    df_memoria, campo_verified_exists = carica_memoria_completa()
    
    if df_memoria.empty:
        st.warning("📭 Memoria vuota. Inizia a caricare fatture per popolarla!")
        return
    
    # ⚠️ AVVISO MIGRATION NECESSARIA (solo admin)
    if is_admin and not campo_verified_exists:
        st.warning("""
        ⚠️ **Sistema Verifica Non Disponibile**: Il campo `verified` non esiste nel database.
        
        **Per abilitare la funzionalità di verifica prodotti:**
        1. Apri [Supabase Dashboard SQL Editor](https://supabase.com/dashboard)
        2. Copia ed esegui: `migrations/008_add_verified_to_prodotti_master.sql`
        3. Oppure esegui: `python run_migration_008.py`
        """)
    
    # ============================================================
    # METRICHE
    # ============================================================
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Prodotti Totali", len(df_memoria))
    
    with col2:
        totale_utilizzi = int(df_memoria['volte_visto'].sum())
        st.metric("Totale Utilizzi", totale_utilizzi)
    
    with col3:
        chiamate_risparmiate = totale_utilizzi - len(df_memoria)
        st.metric("Chiamate API Risparmiate", chiamate_risparmiate)
    
    with col4:
        if is_admin and campo_verified_exists:
            non_verificati = (~df_memoria['verified']).sum()
            st.metric("⚠️ Da Verificare", non_verificati)
    
    st.markdown("---")
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_search, col_cat, col_verified, col_reset = st.columns([3, 2, 2, 1])
    
    with col_search:
        # Inizializza session_state se non esiste
        if 'search_memoria' not in st.session_state:
            st.session_state.search_memoria = ""
        
        search_text = st.text_input(
            "🔍 Cerca descrizione",
            value=st.session_state.search_memoria,
            placeholder="es: POMODORO, OLIO, PASTA",
            key="search_memoria"
        )
    
    with col_cat:
        categorie = st.session_state.categorie_cached
        # Inizializza session_state se non esiste
        if 'filtro_cat' not in st.session_state:
            st.session_state.filtro_cat = "Tutte"
        
        filtro_cat = st.selectbox(
            "Filtra categoria",
            ["Tutte"] + categorie,
            key="filtro_cat"
        )
    
    with col_verified:
        # Filtro verified (SOLO per admin E se campo esiste)
        if is_admin and campo_verified_exists:
            if 'filtro_verified' not in st.session_state:
                st.session_state.filtro_verified = "Da Verificare"  # Default: mostra solo non verificate
            
            filtro_verified = st.selectbox(
                "Stato verifica",
                ["Da Verificare", "Già Verificate", "Tutte"],
                key="filtro_verified"
            )
        else:
            filtro_verified = "Tutte"
    
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset", key="reset_filtri"):
            st.session_state.search_memoria = ""
            st.session_state.filtro_cat = "Tutte"
            if is_admin:
                st.session_state.filtro_verified = "Da Verificare"
            st.rerun()
    
    # ============================================================
    # APPLICA FILTRI
    # ============================================================
    df_filtrato = df_memoria.copy()
    
    # Traccia filtri precedenti per reset pagina
    filtri_correnti = f"{search_text}_{filtro_cat}_{filtro_verified}"
    if 'filtri_memoria_prev' not in st.session_state:
        st.session_state.filtri_memoria_prev = filtri_correnti
    elif st.session_state.filtri_memoria_prev != filtri_correnti:
        # Filtri cambiati: reset pagina
        st.session_state.pagina_memoria = 0
        st.session_state.filtri_memoria_prev = filtri_correnti
    
    if search_text:
        df_filtrato = df_filtrato[
            df_filtrato['descrizione'].str.contains(search_text, case=False, na=False)
        ]
    
    if filtro_cat != "Tutte":
        cat_clean = estrai_nome_categoria(filtro_cat)
        df_filtrato = df_filtrato[df_filtrato['categoria'] == cat_clean]
    
    # FILTRO VERIFIED (solo admin e se campo esiste)
    if is_admin and campo_verified_exists and filtro_verified != "Tutte":
        if filtro_verified == "Da Verificare":
            df_filtrato = df_filtrato[df_filtrato['verified'] == False]
        elif filtro_verified == "Già Verificate":
            df_filtrato = df_filtrato[df_filtrato['verified'] == True]
    
    # ORDINA ALFABETICAMENTE per descrizione
    df_filtrato = df_filtrato.sort_values('descrizione').reset_index(drop=True)
    
    # ============================================================
    # INFO SEMPLICE + PAGINAZIONE
    # ============================================================
    
    # Paginazione per performance (25 righe = più veloce)
    RIGHE_PER_PAGINA = 25
    totale_righe = len(df_filtrato)
    
    # Inizializza pagina corrente
    if 'pagina_memoria' not in st.session_state:
        st.session_state.pagina_memoria = 0
    
    num_pagine = (totale_righe + RIGHE_PER_PAGINA - 1) // RIGHE_PER_PAGINA
    
    col_info, col_pag = st.columns([2, 1])
    
    with col_info:
        st.info(f"📊 Mostrando {totale_righe} prodotti")
    
    with col_pag:
        if num_pagine > 1:
            pagina = st.number_input(
                f"Pag. (max {num_pagine})",
                min_value=1,
                max_value=num_pagine,
                value=st.session_state.pagina_memoria + 1,
                step=1,
                key="input_pagina_memoria",
                label_visibility="visible"
            )
            st.session_state.pagina_memoria = pagina - 1
    
    if df_filtrato.empty:
        st.warning("⚠️ Nessun prodotto trovato con questi filtri")
        return
    
    # Applica paginazione
    inizio = st.session_state.pagina_memoria * RIGHE_PER_PAGINA
    fine = min(inizio + RIGHE_PER_PAGINA, totale_righe)
    df_pagina = df_filtrato.iloc[inizio:fine]
    
    if num_pagine > 1:
        st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")
    
    # ============================================================
    # INIZIALIZZA MODIFICHE PENDENTI E SELEZIONE
    # ============================================================
    if 'modifiche_memoria' not in st.session_state:
        st.session_state.modifiche_memoria = {}
    
    # Inizializza selezione righe per verifica (SOLO per admin)
    if 'righe_selezionate' not in st.session_state:
        st.session_state.righe_selezionate = set()
    
    # Contatore refresh per forzare ricreazione checkbox dopo selezione massiva
    if 'checkbox_refresh_counter' not in st.session_state:
        st.session_state.checkbox_refresh_counter = 0
    
    st.markdown("---")
    
    # ============================================================
    # TABELLA - TUTTE LE RIGHE FILTRATE
    # ============================================================
    num_modifiche = len(st.session_state.modifiche_memoria)
    
    if num_modifiche > 0:
        st.markdown(f"### 📋 Prodotti | 🔸 **{num_modifiche} modifiche pendenti**")
    else:
        st.markdown("### 📋 Prodotti")
    
    # HEADER TABELLA (con checkbox solo se admin, campo exists e filtro da verificare)
    mostra_checkbox = is_admin and campo_verified_exists and filtro_verified == "Da Verificare"
    
    if mostra_checkbox:
        # Bottoni per selezione massiva PRIMA della tabella
        st.markdown("#### Selezione Rapida")
        col_sel_all, col_desel_all = st.columns(2)
        
        with col_sel_all:
            righe_pagina_ids = set(df_pagina['id'].tolist())
            if st.button(f"☑️ Seleziona Tutte ({len(righe_pagina_ids)} righe)", use_container_width=True, key="btn_select_all"):
                st.session_state.righe_selezionate.update(righe_pagina_ids)
                st.session_state.checkbox_refresh_counter += 1  # Forza refresh checkbox
                st.rerun()
        
        with col_desel_all:
            if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_deselect_all"):
                st.session_state.righe_selezionate.difference_update(righe_pagina_ids)
                st.session_state.checkbox_refresh_counter += 1  # Forza refresh checkbox
                st.rerun()
        
        st.markdown("---")
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
    else:
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
    
    with col_desc:
        st.markdown("**Descrizione**")
    
    with col_cat:
        st.markdown("**Categoria**")
    
    with col_azioni:
        st.markdown("**Azioni**")
    
    st.markdown("---")
    
    # CICLO SOLO SULLE RIGHE DELLA PAGINA CORRENTE (per performance)
    # Usa categorie da cache
    categorie = st.session_state.categorie_cached
    
    for idx, row in df_pagina.iterrows():
        row_id = row['id']
        descrizione = row['descrizione']
        categoria_corrente = row['categoria']
        volte_visto = row['volte_visto']
        verified = row.get('verified', True)
        
        # Prepara colonne (con o senza checkbox)
        if mostra_checkbox:
            col_check, col_desc, col_cat, col_azioni = st.columns([0.5, 3.5, 2.5, 1])
        else:
            col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
        
        # Prepara colonne (con o senza checkbox)
        if mostra_checkbox:
            col_check, col_desc, col_cat, col_azioni = st.columns([0.5, 3.5, 2.5, 1])
        else:
            col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
        
        # CHECKBOX (solo se admin e mostra righe da verificare)
        if mostra_checkbox:
            with col_check:
                is_checked = row_id in st.session_state.righe_selezionate
                # Key dinamica con refresh counter per forzare ricreazione dopo selezione massiva
                checked = st.checkbox(
                    "sel",
                    value=is_checked,
                    key=f"chk_{row_id}_r{st.session_state.checkbox_refresh_counter}",
                    label_visibility="collapsed"
                )
                # Aggiorna stato in tempo reale
                if checked:
                    st.session_state.righe_selezionate.add(row_id)
                else:
                    st.session_state.righe_selezionate.discard(row_id)
        
        # DESCRIZIONE
        with col_desc:
            desc_short = descrizione[:50] + "..." if len(descrizione) > 50 else descrizione
            # Emoji stato verifica
            if not verified:
                st.markdown(f"⚠️ `{desc_short}`")
            else:
                st.markdown(f"✅ `{desc_short}`")
        
        # DROPDOWN CATEGORIA (modifica inline)
        with col_cat:
            # Controlla se c'è una modifica pendente
            if descrizione in st.session_state.modifiche_memoria:
                cat_default = st.session_state.modifiche_memoria[descrizione]['nuova_categoria']
            else:
                cat_default = categoria_corrente
            
            # Estrai nome categoria SENZA emoji
            cat_pulita = estrai_nome_categoria(cat_default)
            index_default = categorie.index(cat_pulita) if cat_pulita in categorie else 0
            
            nuova_cat = st.selectbox(
                "cat",
                categorie,
                index=index_default,
                key=f"cat_{row_id}",
                label_visibility="collapsed"
            )
            
            # Traccia modifica se diversa
            cat_clean = estrai_nome_categoria(nuova_cat)
            if cat_clean != categoria_corrente:
                st.session_state.modifiche_memoria[descrizione] = {
                    'nuova_categoria': cat_clean,
                    'occorrenze': volte_visto,
                    'categoria_originale': categoria_corrente,
                    'row_id': row_id  # Serve per auto-verificare quando salvi
                }
            elif descrizione in st.session_state.modifiche_memoria:
                # Ripristinata categoria originale, rimuovi da pendenti
                del st.session_state.modifiche_memoria[descrizione]
        
        # AZIONI - Badge modifica o info volte visto
        with col_azioni:
            # Mostra badge se c'è modifica pendente, altrimenti volte visto
            if descrizione in st.session_state.modifiche_memoria:
                st.markdown("🔸 **Mod**")
            else:
                st.caption(f"{volte_visto}×")
        
        st.markdown("---")
    
    # ============================================================
    # BARRA AZIONI UNIFICATA (Verifiche + Modifiche)
    # ============================================================
    # Ricalcola num_selezionate DOPO il ciclo (quando le checkbox hanno aggiornato lo stato)
    num_selezionate = len(st.session_state.righe_selezionate)
    
    # ✅ PULSANTE UNICO: Gestisce entrambe le operazioni (verifiche checkbox + modifiche categorie)
    if is_admin and campo_verified_exists and (num_selezionate > 0 or num_modifiche > 0):
        st.markdown("---")
        st.markdown("### 💾 Salvataggio e Conferma")
        
        # Info riassuntiva
        info_parts = []
        if num_modifiche > 0:
            totale_righe_affected = sum(m['occorrenze'] for m in st.session_state.modifiche_memoria.values())
            info_parts.append(f"**{num_modifiche}** modifiche categorie → **{totale_righe_affected}** righe")
        if num_selezionate > 0:
            info_parts.append(f"**{num_selezionate}** verifiche checkbox")
        
        st.info(f"📊 Azioni pendenti: " + " | ".join(info_parts))
        
        # Preview modifiche (se esistono)
        if num_modifiche > 0:
            with st.expander("🔍 Preview Modifiche Categorie", expanded=False):
                for desc, info in list(st.session_state.modifiche_memoria.items())[:10]:
                    desc_short = desc[:50] + "..." if len(desc) > 50 else desc
                    st.markdown(f"- `{desc_short}` ({info['occorrenze']}×): {info['categoria_originale']} → **{info['nuova_categoria']}**")
                if num_modifiche > 10:
                    st.caption(f"... e altre {num_modifiche - 10} modifiche")
        
        # Bottoni azione unificati
        col_save, col_cancel, col_export = st.columns([2, 1, 1.5])
        
        with col_save:
            # Label dinamica
            label_parts = []
            if num_modifiche > 0:
                label_parts.append(f"{num_modifiche} modifiche")
            if num_selezionate > 0:
                label_parts.append(f"{num_selezionate} verifiche")
            
            button_label = f"💾 Salva e Conferma ({' + '.join(label_parts)})"
            
            if st.button(button_label, type="primary", use_container_width=True, key="save_unified"):
                with st.spinner("💾 Salvataggio in corso..."):
                    success_messages = []
                    
                    try:
                        # STEP 1: Salva modifiche categorie (se esistono)
                        if num_modifiche > 0:
                            success_count = 0
                            total_rows = 0
                            
                            for descrizione, info in st.session_state.modifiche_memoria.items():
                                try:
                                    # Admin: aggiorna memoria globale + auto-verifica
                                    supabase.table('prodotti_master')\
                                        .update({
                                            'categoria': info['nuova_categoria'],
                                            'verified': True  # ✅ Auto-verifica: correzione manuale = già controllata
                                        })\
                                        .eq('descrizione', descrizione)\
                                        .execute()
                                    
                                    # Aggiorna anche fatture
                                    result = supabase.table('fatture')\
                                        .update({'categoria': info['nuova_categoria']})\
                                        .eq('descrizione', descrizione)\
                                        .execute()
                                    
                                    num_updated = len(result.data) if result.data else info['occorrenze']
                                    success_count += 1
                                    total_rows += num_updated
                                    
                                except Exception as e:
                                    logger.error(f"Errore salvataggio '{descrizione}': {e}")
                            
                            success_messages.append(f"✅ {success_count} modifiche salvate ({total_rows} righe aggiornate)")
                            
                            # Reset modifiche
                            st.session_state.modifiche_memoria = {}
                        
                        # STEP 2: Conferma verifiche checkbox (se esistono)
                        if num_selezionate > 0:
                            righe_ids = list(st.session_state.righe_selezionate)
                            
                            supabase.table('prodotti_master')\
                                .update({'verified': True})\
                                .in_('id', righe_ids)\
                                .execute()
                            
                            success_messages.append(f"✅ {num_selezionate} verifiche confermate")
                            
                            # Reset selezione
                            st.session_state.righe_selezionate = set()
                        
                        # Refresh cache
                        st.cache_data.clear()
                        
                        # Mostra success unificato
                        st.success("\n\n".join(success_messages))
                        time.sleep(1.5)
                        st.rerun()
                        
                    except Exception as e:
                        logger.error(f"Errore salvataggio unificato: {e}")
                        st.error(f"❌ Errore durante il salvataggio: {e}")
        
        with col_cancel:
            if st.button("❌ Annulla Tutte", use_container_width=True, key="cancel_unified"):
                st.session_state.modifiche_memoria = {}
                st.session_state.righe_selezionate = set()
                st.rerun()
        
        with col_export:
            # Export solo se ci sono modifiche
            if num_modifiche > 0:
                export_data = []
                for desc, info in st.session_state.modifiche_memoria.items():
                    export_data.append({
                        'Descrizione': desc,
                        'Occorrenze': info['occorrenze'],
                        'Categoria Originale': info['categoria_originale'],
                        'Nuova Categoria': info['nuova_categoria']
                    })
                df_export = pd.DataFrame(export_data)
                csv = df_export.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="📄 Export CSV",
                    data=csv,
                    file_name=f"modifiche_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="export_unified_csv"
                )

# Chiama la funzione unificata
if tab3:
    tab_memoria_globale_unificata()

# ============================================================
# TAB 4: UPLOAD EVENTS - VERIFICA DATABASE
# ============================================================

if tab4:
    st.markdown("## � Verifica Database - Problemi Tecnici")
    st.caption("Mostra solo eventi che richiedono assistenza (FAILED, SAVED_PARTIAL). I duplicati sono comportamento normale e non vengono loggati.")
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_email, col_periodo = st.columns(2)
    
    with col_email:
        # Carica lista clienti
        try:
            clienti_response = supabase.table('users')\
                .select('email, nome_ristorante')\
                .order('nome_ristorante')\
                .execute()
            
            if clienti_response.data:
                # Opzione "Tutti" all'inizio
                opzioni_clienti = ["Tutti i clienti"] + [
                    f"{c.get('nome_ristorante', 'N/A')} ({c['email']})" 
                    for c in clienti_response.data
                ]
                
                # Mappa per recuperare email dalla selezione
                email_map = {
                    f"{c.get('nome_ristorante', 'N/A')} ({c['email']})": c['email']
                    for c in clienti_response.data
                }
            else:
                opzioni_clienti = ["Tutti i clienti"]
                email_map = {}
        except Exception as e:
            logger.warning(f"Errore caricamento clienti per filtro: {e}")
            opzioni_clienti = ["Tutti i clienti"]
            email_map = {}
        
        # Selectbox clienti
        filtro_cliente_sel = st.selectbox(
            "👤 Seleziona Cliente",
            options=opzioni_clienti,
            key="filtro_cliente_upload_events"
        )
        
        # Estrai email dalla selezione
        if filtro_cliente_sel == "Tutti i clienti":
            filtro_email = None
        else:
            filtro_email = email_map.get(filtro_cliente_sel, None)
    
    with col_periodo:
        # Filtro periodo
        filtro_periodo = st.selectbox(
            "Periodo",
            ["Ultimi 7 giorni", "Ultimi 30 giorni", "Ultimi 90 giorni", "Ultimi 180 giorni", "Tutto"],
            key="filtro_periodo_upload_events"
        )
    
    # Opzione mostra verificati
    mostra_verificati = st.checkbox(
        "Mostra anche eventi già verificati",
        value=False,
        key="mostra_verificati_upload_events"
    )
    
    st.markdown("---")
    
    # ============================================================
    # QUERY EVENTI
    # ============================================================
    
    if st.button("🔍 Verifica Database", key="btn_verifica_db", type="primary"):
        with st.spinner("Caricamento eventi..."):
            try:
                # Costruisci query base
                query = supabase.table('upload_events').select('*')
                
                # Filtro email (exact match se selezionato un cliente)
                if filtro_email:
                    query = query.eq('user_email', filtro_email)
                
                # Filtro periodo
                if filtro_periodo == "Ultimi 7 giorni":
                    data_limite = (datetime.now() - timedelta(days=7)).isoformat()
                    query = query.gte('created_at', data_limite)
                elif filtro_periodo == "Ultimi 30 giorni":
                    data_limite = (datetime.now() - timedelta(days=30)).isoformat()
                    query = query.gte('created_at', data_limite)
                elif filtro_periodo == "Ultimi 90 giorni":
                    data_limite = (datetime.now() - timedelta(days=90)).isoformat()
                    query = query.gte('created_at', data_limite)
                elif filtro_periodo == "Ultimi 180 giorni":
                    data_limite = (datetime.now() - timedelta(days=180)).isoformat()
                    query = query.gte('created_at', data_limite)
                
                # Filtro ACK (mostra solo non verificati se opzione disattivata)
                if not mostra_verificati:
                    query = query.eq('ack', False)
                
                # Filtro status (solo problemi tecnici che richiedono assistenza)
                query = query.in_('status', ['FAILED', 'SAVED_PARTIAL'])
                
                # Ordina per data (più recenti prima)
                query = query.order('created_at', desc=True)
                
                # Esegui query
                response = query.execute()
                
                if not response.data:
                    st.success("✅ Nessun problema rilevato nel periodo selezionato")
                    st.info("Il sistema sta funzionando correttamente. Tutti gli upload sono andati a buon fine.")
                else:
                    df_events = pd.DataFrame(response.data)
                    
                    # ============================================================
                    # STATISTICHE
                    # ============================================================
                    st.markdown("---")
                    st.markdown("### 📊 Statistiche")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        eventi_failed = df_events[df_events['status'] == 'FAILED'].shape[0]
                        st.metric("❌ FAILED", eventi_failed)
                    
                    with col2:
                        eventi_partial = df_events[df_events['status'] == 'SAVED_PARTIAL'].shape[0]
                        st.metric("⚠️ SAVED_PARTIAL", eventi_partial)
                    
                    with col3:
                        if not mostra_verificati:
                            eventi_non_ack = df_events[df_events['ack'] == False].shape[0]
                            st.metric("🔔 Da Verificare", eventi_non_ack)
                        else:
                            st.metric("📋 Totale Mostrati", len(df_events))
                    
                    st.markdown("---")
                    
                    # ============================================================
                    # TABELLA EVENTI
                    # ============================================================
                    st.markdown("### 📋 Lista Eventi")
                    
                    # Prepara DataFrame per visualizzazione
                    df_display = df_events[[
                        'created_at', 'user_email', 'file_name', 'status',
                        'rows_parsed', 'rows_saved', 'error_stage', 'error_message', 'ack'
                    ]].copy()
                    
                    # Formatta data
                    df_display['created_at'] = pd.to_datetime(df_display['created_at']).dt.strftime('%Y-%m-%d %H:%M')
                    
                    # Tronca messaggio errore
                    if 'error_message' in df_display.columns:
                        df_display['error_message'] = df_display['error_message'].apply(
                            lambda x: (str(x)[:100] + "...") if x and len(str(x)) > 100 else x
                        )
                    
                    # Rinomina colonne per visualizzazione
                    df_display.columns = [
                        '📅 Data', '👤 Cliente', '📄 File', '🔖 Status',
                        '📊 Parse', '💾 Salvate', '⚠️ Fase', '💬 Messaggio', '✅ Verificato'
                    ]
                    
                    # Mostra tabella
                    st.dataframe(
                        df_display,
                        hide_index=True,
                        use_container_width=True,
                        height=400
                    )
                    
                    # ============================================================
                    # AZIONE: SEGNA COME VERIFICATI
                    # ============================================================
                    eventi_da_ack = df_events[df_events['ack'] == False]
                    
                    if not eventi_da_ack.empty:
                        st.markdown("---")
                        st.info(f"🔔 **{len(eventi_da_ack)} eventi** richiedono verifica")
                        
                        if st.button(
                            "✅ Segna Tutti Come Verificati",
                            type="secondary",
                            use_container_width=True,
                            key="ack_all_events"
                        ):
                            try:
                                admin_email = user.get('email', 'admin')
                                event_ids = eventi_da_ack['id'].tolist()
                                
                                # Update batch su Supabase
                                for event_id in event_ids:
                                    supabase.table('upload_events').update({
                                        'ack': True,
                                        'ack_at': datetime.now().isoformat(),
                                        'ack_by': admin_email
                                    }).eq('id', event_id).execute()
                                
                                st.success(f"✅ {len(event_ids)} eventi marcati come verificati!")
                                st.balloons()
                                time.sleep(1)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Errore: {e}")
            
            except Exception as e:
                st.error(f"❌ Errore durante la verifica: {str(e)}")
                with st.expander("🔍 Dettagli Tecnici"):
                    import traceback
                    st.code(traceback.format_exc())


# ============================================================
# TAB 5: COSTI AI PER CLIENTE
# ============================================================

if tab5:
    st.markdown("## 💳 Costi AI per Cliente")
    st.caption("Monitoraggio utilizzo e costi OpenAI per estrazione PDF e categorizzazione prodotti")
    
    try:
        # Carica dati costi AI usando funzione RPC
        response = supabase.rpc('get_ai_costs_summary').execute()
        
        if not response.data or len(response.data) == 0:
            st.info("📊 Nessun utilizzo AI registrato. I costi verranno tracciati automaticamente quando i clienti caricano PDF o immagini.")
        else:
            df_costs = pd.DataFrame(response.data)
            
            # ⚠️ BACKWARDS COMPATIBILITY: Aggiungi colonna se non esiste (pre-migrazione)
            if 'ai_categorization_count' not in df_costs.columns:
                st.warning("⚠️ **Migrazione database necessaria!** Esegui `migrations/014_add_ai_cost_tracking.sql` per abilitare tracking categorizzazioni.")
                df_costs['ai_categorization_count'] = 0
                df_costs['ai_avg_cost_per_operation'] = df_costs.get('ai_avg_cost_per_pdf', 0)
            
            # ============================================================
            # STATISTICHE GENERALI
            # ============================================================
            st.markdown("### 📊 Riepilogo Globale")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                totale_costi = df_costs['ai_cost_total'].sum()
                st.metric(
                    "💰 Totale Costi",
                    f"${totale_costi:.2f}",
                    help="Costo totale cumulativo di tutte le chiamate AI"
                )
            
            with col2:
                totale_pdf = df_costs['ai_pdf_count'].sum()
                st.metric(
                    "📄 PDF Processati",
                    f"{int(totale_pdf):,}",
                    help="Numero totale di PDF/immagini elaborati con Vision API"
                )
            
            with col3:
                totale_categorization = df_costs['ai_categorization_count'].sum()
                st.metric(
                    "🧠 Categorizzazioni",
                    f"{int(totale_categorization):,}",
                    help="Numero totale di categorizzazioni AI effettuate"
                )
            
            with col4:
                totale_operazioni = totale_pdf + totale_categorization
                costo_medio = totale_costi / totale_operazioni if totale_operazioni > 0 else 0
                st.metric(
                    "📊 Costo Medio",
                    f"${costo_medio:.4f}",
                    help="Costo medio per singola operazione AI"
                )
            
            with col5:
                clienti_attivi = len(df_costs[(df_costs['ai_pdf_count'] > 0) | (df_costs['ai_categorization_count'] > 0)])
                st.metric(
                    "👥 Clienti Attivi",
                    clienti_attivi,
                    help="Numero di clienti che hanno usato funzioni AI"
                )
            
            st.markdown("---")
            
            # ============================================================
            # TABELLA DETTAGLIO PER CLIENTE
            # ============================================================
            st.markdown("### 📋 Dettaglio per Cliente")
            
            # Prepara DataFrame per visualizzazione
            df_display = df_costs[(df_costs['ai_pdf_count'] > 0) | (df_costs['ai_categorization_count'] > 0)].copy()
            
            if len(df_display) > 0:
                df_display['Cliente'] = df_display['nome_ristorante']
                df_display['Ragione Sociale'] = df_display['ragione_sociale'].fillna('-')
                df_display['PDF'] = df_display['ai_pdf_count'].astype(int)
                df_display['Categorizzazioni'] = df_display['ai_categorization_count'].astype(int)
                df_display['Tot Operazioni'] = (df_display['ai_pdf_count'] + df_display['ai_categorization_count']).astype(int)
                df_display['Costo Totale'] = df_display['ai_cost_total'].apply(lambda x: f"${x:.4f}")
                df_display['Costo/Op'] = df_display['ai_avg_cost_per_operation'].apply(lambda x: f"${x:.4f}")
                df_display['Ultimo Uso'] = pd.to_datetime(df_display['ai_last_usage']).dt.strftime('%Y-%m-%d %H:%M')
                
                # Mostra tabella
                st.dataframe(
                    df_display[['Cliente', 'Ragione Sociale', 'PDF', 'Categorizzazioni', 'Tot Operazioni', 'Costo Totale', 'Costo/Op', 'Ultimo Uso']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # ============================================================
                # EXPORT CSV
                # ============================================================
                st.markdown("---")
                col_export, col_spacer = st.columns([2, 8])
                
                with col_export:
                    csv_data = df_display[['Cliente', 'Ragione Sociale', 'PDF', 'Categorizzazioni', 'Tot Operazioni', 'Costo Totale', 'Costo/Op', 'Ultimo Uso']].to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Esporta CSV",
                        data=csv_data,
                        file_name=f"costi_ai_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                # ============================================================
                # GRAFICO TOP CLIENTI
                # ============================================================
                st.markdown("---")
                st.markdown("### 📈 Top 10 Clienti per Costo")
                
                df_top = df_display.nlargest(10, 'ai_cost_total')
                
                fig = px.bar(
                    df_top,
                    x='Cliente',
                    y='ai_cost_total',
                    title='Costi AI per Cliente (Top 10)',
                    labels={'ai_cost_total': 'Costo ($)', 'Cliente': ''},
                    color='ai_cost_total',
                    color_continuous_scale='Blues'
                )
                
                fig.update_layout(
                    showlegend=False,
                    xaxis_tickangle=-45,
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # ============================================================
                # INFO E NOTE
                # ============================================================
                st.markdown("---")
                st.info("""
                **ℹ️ Note:**
                - I costi sono calcolati in base al modello **GPT-4o-mini** (sia Vision che Text)
                - **PDF Vision**: ~$0.02-0.04 per documento (dipende da complessità e numero prodotti)
                - **Categorizzazione**: ~$0.001-0.005 per batch (molto economico)
                - I file **XML sono gratuiti** (parsing locale, nessun costo AI)
                - Per ridurre i costi, incoraggia i clienti a usare XML quando possibile
                - La categorizzazione AI viene usata solo per prodotti "Da Classificare"
                """)
            else:
                st.warning("Nessun cliente ha ancora utilizzato funzioni AI")
    
    except Exception as e:
        st.error(f"❌ Errore caricamento dati: {str(e)}")
        logger.exception("Errore nel tab Costi AI")
        with st.expander("🔍 Dettagli Errore"):
            st.code(str(e))
