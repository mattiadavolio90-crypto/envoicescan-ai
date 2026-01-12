"""
🔧 PANNELLO AMMINISTRAZIONE - CHECK FORNITORI AI
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

# Importa funzioni categorie dinamiche da app.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
try:
    from app import carica_categorie_da_db, estrai_nome_categoria, aggiungi_icona_categoria
except ImportError:
    # Fallback se import fallisce
    def carica_categorie_da_db():
        return ["❓ Da Classificare", "🍖 CARNE", "🐟 PESCE"]
    def estrai_nome_categoria(cat):
        return cat.split(' ', 1)[1] if ' ' in cat else cat
    def aggiungi_icona_categoria(cat):
        return cat

# ============================================================
# SETUP
# ============================================================

# Setup logging
logger = logging.getLogger('fci.admin')

# Setup pagina
st.set_page_config(
    page_title="Pannello Admin", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# ============================================================
# CONNESSIONE SUPABASE CON CONNECTION POOLING
# ============================================================
from supabase import create_client, Client

# Leggi credenziali Supabase
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

# Connection pooling: client riutilizzato tra richieste
@st.cache_resource
def get_supabase_client():
    """Singleton Supabase client con connection pooling."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = get_supabase_client()

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
ADMIN_EMAILS = ["mattiadavolio90@gmail.com"]

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
            no_food = int((df_user['categoria'] == 'NO FOOD').sum())
            da_class = int((df_user['categoria'] == 'Da Classificare').sum())
            
            totale_problemi = prezzi_zero + no_food + da_class
            
            if totale_problemi > 0:
                problemi_per_cliente.append({
                    'user_id': user_id,
                    'prezzi_zero': prezzi_zero,
                    'no_food': no_food,
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
st.caption(f"Admin: {user.get('email')}")
st.markdown("---")

# ============================================================
# TABS PRINCIPALI CON PERSISTENZA
# ============================================================

# Inizializza tab attivo in session_state (default = 0)
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

# Cache categorie in session_state (carica 1 sola volta)
if 'categorie_cached' not in st.session_state:
    st.session_state.categorie_cached = carica_categorie_da_db()
    logger.info(f"✅ Categorie caricate in cache: {len(st.session_state.categorie_cached)} categorie")

# Usa radio buttons nascosti per mantenere tab attivo
tab_names = ["📊 Gestione Clienti", "� Review Righe €0", "🧠 Memoria Globale AI", "📊 Upload Events"]
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
    st.caption("Visualizza statistiche clienti e accedi come utente per debug/supporto")
    
    # ============================================================
    # CREA NUOVO CLIENTE (solo admin)
    # ============================================================
    st.markdown("### ➕ Crea Nuovo Cliente")
    
    with st.expander("➕ Crea Nuovo Cliente", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            new_email = st.text_input("📧 Email cliente", key="new_email", placeholder="cliente@esempio.com")
            new_name = st.text_input("🏪 Nome ristorante", key="new_name", placeholder="Es: Ristorante Da Mario")
        
        with col2:
            new_password = st.text_input("🔑 Password temporanea (min 8 caratteri)", type="password", key="new_pwd", placeholder="Password sicura")
            confirm_password = st.text_input("🔑 Conferma password", type="password", key="confirm_pwd", placeholder="Ripeti password")
        
        st.markdown("---")
        
        if st.button("🆕 Crea Account Cliente", type="primary", use_container_width=True):
            # Validazione input
            if not new_email or not new_name or not new_password or not confirm_password:
                st.error("⚠️ Compila tutti i campi")
            elif new_password != confirm_password:
                st.error("❌ Le password non coincidono")
            elif len(new_password) < 8:
                st.error("❌ Password troppo corta (minimo 8 caratteri)")
            elif '@' not in new_email:
                st.error("❌ Email non valida")
            else:
                try:
                    # Verifica se email già esiste
                    check_existing = supabase.table('users').select('id').eq('email', new_email).execute()
                    
                    if check_existing.data:
                        st.error(f"❌ Email {new_email} già registrata")
                    else:
                        # Hash password con Argon2
                        from services.auth_service import hash_password
                        password_hash = hash_password(new_password)
                        
                        # Inserisci nuovo utente
                        nuovo_utente = {
                            'email': new_email,
                            'nome_ristorante': new_name,
                            'password': password_hash,
                            'attivo': True,
                            'created_at': datetime.now(timezone.utc).isoformat()
                        }
                        
                        result = supabase.table('users').insert(nuovo_utente).execute()
                        
                        if result.data:
                            # ===== INVIO EMAIL AUTOMATICO BREVO =====
                            email_inviata = False
                            try:
                                brevo_api_key = st.secrets["brevo"]["api_key"]
                                sender_email = st.secrets["brevo"]["sender_email"]
                                app_url = st.secrets.get("app", {}).get("url", "https://checkfornitori.streamlit.app")
                                
                                url_brevo = "https://api.brevo.com/v3/smtp/email"
                                
                                email_html = f"""
                                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                    <h2 style="color: #0ea5e9;">🧠 Benvenuto in Check Fornitori AI</h2>
                                    <p>Il tuo account è stato creato con successo!</p>
                                    
                                    <div style="background: #f1f5f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                                        <p><strong>📧 Email:</strong> {new_email}</p>
                                        <p><strong>🔑 Password:</strong> <code style="background: #e2e8f0; padding: 4px 8px; border-radius: 4px;">{new_password}</code></p>
                                    </div>
                                    
                                    <p style="margin: 25px 0;">
                                        <a href="{app_url}" style="display: inline-block; background: #0ea5e9; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                            🚀 Accedi all'App
                                        </a>
                                    </p>
                                    
                                    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                                    <p style="color: #94a3b8; font-size: 12px;">
                                        Questa email è stata generata automaticamente. Se non hai richiesto la creazione di questo account, contatta l'amministratore.
                                    </p>
                                </div>
                                """
                                
                                payload = {
                                    "sender": {"email": sender_email, "name": "Check Fornitori AI"},
                                    "to": [{"email": new_email, "name": new_name}],
                                    "cc": [{"email": "mattiadavolio90@gmail.com"}],
                                    "subject": "🆕 Benvenuto - Credenziali Accesso Check Fornitori AI",
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
                                    logger.info(f"✅ Email credenziali inviata a {new_email}")
                                else:
                                    logger.warning(f"⚠️ Email non inviata: {response.status_code} - {response.text}")
                                    
                            except Exception as e:
                                logger.error(f"❌ Errore invio email: {e}")
                            
                            # Mostra messaggio di successo
                            if email_inviata:
                                st.success(f"✅ Cliente {new_email} creato con successo!")
                                st.info(f"📧 Email con credenziali inviata automaticamente a: **{new_email}**")
                            else:
                                st.success(f"✅ Cliente {new_email} creato con successo!")
                                st.warning(f"⚠️ Errore invio email automatico. Comunica manualmente le credenziali:")
                                st.info(f"📧 Email: {new_email}\n🔑 Password temporanea: {new_password}")
                            
                            logger.info(f"✅ Nuovo cliente creato da admin: {new_email} | Email inviata: {email_inviata}")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Errore durante la creazione dell'account")
                            
                except Exception as e:
                    st.error(f"❌ Errore creazione cliente: {e}")
                    logger.exception(f"Errore creazione cliente {new_email}")
    
    st.markdown("---")
    
    try:
        # Query utenti
        query_users = supabase.table('users')\
            .select('id, email, nome_ristorante, attivo, created_at')\
            .order('email')\
            .execute()
        
        if not query_users.data:
            st.info("📭 Nessun cliente registrato")
        else:
            # Calcola statistiche per ogni cliente
            stats_clienti = []
            
            for user_data in query_users.data:
                user_id = user_data['id']
                
                # Query fatture per questo utente (con conteggio esatto)
                query_fatture = supabase.table('fatture')\
                    .select('file_origine, id, created_at', count='exact')\
                    .eq('user_id', user_id)\
                    .execute()
                
                num_fatture = 0
                num_righe = 0
                ultimo_caricamento = None
                
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
                
                stats_clienti.append({
                    'user_id': user_id,
                    'email': user_data['email'],
                    'ristorante': user_data.get('nome_ristorante', 'N/A'),
                    'attivo': user_data.get('attivo', True),
                    'num_fatture': num_fatture,
                    'num_righe': num_righe,
                    'ultimo_caricamento': ultimo_caricamento
                })
            
            df_clienti = pd.DataFrame(stats_clienti)
            
            # ===== METRICHE GENERALI =====
            col1, col2, col3, col4 = st.columns(4)
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
            
            st.markdown("---")
            st.markdown("#### 👥 Lista Clienti")
            
            # Ordina per ultimo caricamento (più recenti prima)
            df_clienti_sorted = df_clienti.sort_values('ultimo_caricamento', ascending=False, na_position='last')
            
            # ===== TABELLA CLIENTI CON IMPERSONAZIONE =====
            for idx, row in df_clienti_sorted.iterrows():
                col1, col2, col3, col4, col5, col6 = st.columns([2.5, 2, 1, 1, 1.5, 1])
                
                with col1:
                    status_icon = "🟢" if row['attivo'] else "🔴"
                    st.markdown(f"{status_icon} **{row['email']}**")
                
                with col2:
                    st.text(row['ristorante'])
                
                with col3:
                    st.caption(f"📄 {row['num_fatture']}")
                
                with col4:
                    st.caption(f"📊 {row['num_righe']}")
                
                with col5:
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
                
                with col6:
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
                            
                            # Log
                            logger.info(f"🔀 IMPERSONAZIONE: admin={st.session_state.admin_original_user['email']} → cliente={row['email']}")
                            
                            # Redirect
                            st.success(f"✅ Accesso come: {row['email']}")
                            time.sleep(0.8)
                            st.switch_page("app.py")
                    
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
                            
                            # AZIONE 2: Reset Password
                            st.markdown("**Reset Password**")
                            nuova_password = st.text_input(
                                "Nuova password",
                                type="password",
                                key=f"pwd_{row['user_id']}",
                                placeholder="Min 6 caratteri"
                            )
                            
                            if st.button("🔑 Cambia Password", key=f"reset_{row['user_id']}", type="primary", use_container_width=True, disabled=len(nuova_password)<6):
                                try:
                                    import hashlib
                                    password_hash = hashlib.sha256(nuova_password.encode()).hexdigest()
                                    
                                    supabase.table('users')\
                                        .update({'password': password_hash})\
                                        .eq('id', row['user_id'])\
                                        .execute()
                                    
                                    logger.info(f"🔑 Password resettata per: {row['email']}")
                                    st.success(f"Password aggiornata per {row['email']}")
                                    time.sleep(1.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                            
                            if len(nuova_password) > 0 and len(nuova_password) < 6:
                                st.caption("⚠️ Password troppo corta")
                            
                            st.markdown("---")
                            
                            # AZIONE 3: Elimina Account Completo (2 click)
                            st.markdown("**⚠️ Zona Pericolosa**")
                            
                            if st.button("🗑️ Elimina Account", key=f"elimina_btn_{row['user_id']}", type="secondary", use_container_width=True):
                                st.session_state[f"show_delete_dialog_{row['user_id']}"] = True
                            
                            # Dialog conferma (solo se attivato)
                            if st.session_state.get(f"show_delete_dialog_{row['user_id']}", False):
                                @st.dialog("⚠️ Conferma Eliminazione Account")
                                def show_delete_confirmation():
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
                                                    
                                                    # 5. Elimina utente
                                                    supabase.table('users')\
                                                        .delete()\
                                                        .eq('id', user_id_to_delete)\
                                                        .execute()
                                                    
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
        Carica righe €0, con filtro cliente opzionale.
        
        Args:
            cliente_id: UUID cliente o None per tutti
            
        Returns:
            DataFrame con righe €0
        """
        try:
            query = supabase.table('fatture')\
                .select('id, descrizione, categoria, fornitore, file_origine, data_documento, user_id')\
                .eq('prezzo_unitario', 0)
            
            # Applica filtro cliente se specificato
            if cliente_id:
                query = query.eq('user_id', cliente_id)
            
            response = query.execute()
            
            df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            return df
            
        except Exception as e:
            logger.error(f"Errore caricamento righe €0: {e}")
            return pd.DataFrame()
    
    df_zero = carica_righe_zero_con_filtro(filtro_cliente_id)
    
    if df_zero.empty:
        st.success("✅ Nessuna riga con prezzo €0 da revisionare!")
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
        
        # DESCRIZIONE
        with col_desc:
            desc_short = descrizione[:45] + "..." if len(descrizione) > 45 else descrizione
            st.markdown(f"`{desc_short}`")
        
        # OCCORRENZE
        with col_occur:
            st.markdown(f"`{occorrenze}×`")
        
        # CATEGORIA (dropdown modificabile)
        with col_cat:
            # Controlla se c'è una modifica pendente
            if descrizione in st.session_state.modifiche_review:
                cat_default = st.session_state.modifiche_review[descrizione]['nuova_categoria']
            else:
                cat_default = categoria_corrente
            
            # Estrai nome categoria SENZA emoji
            cat_pulita = estrai_nome_categoria(cat_default)
            index_default = categorie.index(cat_pulita) if cat_pulita in categorie else 0
            
            nuova_cat = st.selectbox(
                "cat",
                categorie,
                index=index_default,
                key=f"cat_review_{row_id}",
                label_visibility="collapsed"
            )
            
            # Traccia modifica se diversa
            cat_clean = estrai_nome_categoria(nuova_cat)
            if cat_clean != categoria_corrente:
                st.session_state.modifiche_review[descrizione] = {
                    'nuova_categoria': cat_clean,
                    'occorrenze': occorrenze,
                    'categoria_originale': categoria_corrente
                }
            elif descrizione in st.session_state.modifiche_review:
                # Ripristinata categoria originale, rimuovi da pendenti
                del st.session_state.modifiche_review[descrizione]
        
        # FORNITORE
        with col_forn:
            forn_short = fornitore[:15] if fornitore else "N/A"
            st.caption(forn_short)
        
        # AZIONI - Badge modifica o bottone ignora
        with col_azioni:
            col_a1, col_a2 = st.columns(2)
            
            with col_a1:
                # Mostra badge se c'è modifica pendente
                if descrizione in st.session_state.modifiche_review:
                    st.markdown("🔸 **Mod**")
                else:
                    st.caption("-")
            
            # AZIONE: Ignora (marca TUTTE come NOTE E DICITURE)
            with col_a2:
                if st.button("🗑️", key=f"ignore_{row_id}", help=f"Ignora {occorrenze} righe"):
                    try:
                        # Marca TUTTE LE RIGHE CON STESSA DESCRIZIONE
                        result = supabase.table('fatture').update({
                            'categoria': 'NOTE E DICITURE'
                        }).eq('descrizione', descrizione).execute()
                        
                        num_updated = len(result.data) if result.data else occorrenze
                        
                        # Rimuovi da modifiche pendenti se presente
                        if descrizione in st.session_state.modifiche_review:
                            del st.session_state.modifiche_review[descrizione]
                        
                        st.success(f"✅ {num_updated} righe ignorate")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Errore: {e}")
        
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
    - NO checkbox master
    - Info semplice
    """
    st.markdown("## 🧠 Memoria Globale Prodotti")
    st.caption("Gestisci classificazioni condivise tra tutti i clienti")
    
    # ============================================================
    # IDENTIFICA RUOLO
    # ============================================================
    ADMIN_EMAILS = ['mattiadavolio90@gmail.com']
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
            if is_admin:
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
            return df
        except Exception as e:
            logger.error(f"Errore caricamento memoria: {e}")
            return pd.DataFrame()
    
    df_memoria = carica_memoria_completa()
    
    if df_memoria.empty:
        st.warning("📭 Memoria vuota. Inizia a caricare fatture per popolarla!")
        return
    
    # ============================================================
    # METRICHE
    # ============================================================
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Prodotti Totali", len(df_memoria))
    
    with col2:
        totale_utilizzi = int(df_memoria['volte_visto'].sum())
        st.metric("Totale Utilizzi", totale_utilizzi)
    
    with col3:
        chiamate_risparmiate = totale_utilizzi - len(df_memoria)
        st.metric("Chiamate API Risparmiate", chiamate_risparmiate)
    
    st.markdown("---")
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_search, col_cat, col_reset = st.columns([3, 2, 1])
    
    with col_search:
        search_text = st.text_input(
            "🔍 Cerca descrizione",
            placeholder="es: POMODORO, OLIO, PASTA",
            key="search_memoria"
        )
    
    with col_cat:
        categorie = st.session_state.categorie_cached
        filtro_cat = st.selectbox(
            "Filtra categoria",
            ["Tutte"] + categorie,
            key="filtro_cat"
        )
    
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset", key="reset_filtri"):
            st.session_state.search_memoria = ""
            st.session_state.filtro_cat = "Tutte"
            st.rerun()
    
    # ============================================================
    # APPLICA FILTRI
    # ============================================================
    df_filtrato = df_memoria.copy()
    
    # Traccia filtri precedenti per reset pagina
    filtri_correnti = f"{search_text}_{filtro_cat}"
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
    # INIZIALIZZA MODIFICHE PENDENTI
    # ============================================================
    if 'modifiche_memoria' not in st.session_state:
        st.session_state.modifiche_memoria = {}
    
    st.markdown("---")
    
    # ============================================================
    # TABELLA - TUTTE LE RIGHE FILTRATE
    # ============================================================
    num_modifiche = len(st.session_state.modifiche_memoria)
    
    if num_modifiche > 0:
        st.markdown(f"### 📋 Prodotti | 🔸 **{num_modifiche} modifiche pendenti**")
    else:
        st.markdown("### 📋 Prodotti")
    
    # HEADER TABELLA
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
        
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
        
        # DESCRIZIONE
        with col_desc:
            desc_short = descrizione[:50] + "..." if len(descrizione) > 50 else descrizione
            st.markdown(f"`{desc_short}`")
        
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
                    'categoria_originale': categoria_corrente
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
    # BARRA AZIONI BATCH (se ci sono modifiche)
    # ============================================================
    if num_modifiche > 0:
        st.markdown("---")
        st.markdown("### 💾 Salvataggio Batch")
        
        # Info modifiche
        totale_righe_affected = sum(m['occorrenze'] for m in st.session_state.modifiche_memoria.values())
        st.info(f"📊 **{num_modifiche}** descrizioni modificate → **{totale_righe_affected}** righe totali")
        
        # Mostra preview modifiche
        with st.expander("🔍 Preview Modifiche", expanded=False):
            for desc, info in list(st.session_state.modifiche_memoria.items())[:10]:
                desc_short = desc[:50] + "..." if len(desc) > 50 else desc
                st.markdown(f"- `{desc_short}` ({info['occorrenze']}×): {info['categoria_originale']} → **{info['nuova_categoria']}**")
            if num_modifiche > 10:
                st.caption(f"... e altre {num_modifiche - 10} modifiche")
        
        # Bottoni azione - TAB 4 MEMORIA
        col_save, col_cancel, col_export = st.columns([2, 1, 1.5])
        
        with col_save:
            if st.button(f"💾 Salva Tutte ({num_modifiche})", type="primary", use_container_width=True, key="save_memoria_batch"):
                with st.spinner(f"💾 Salvataggio {num_modifiche} modifiche in corso..."):
                    success_count = 0
                    total_rows = 0
                    
                    for descrizione, info in st.session_state.modifiche_memoria.items():
                        try:
                            # AGGIORNA TUTTE LE RIGHE CON STESSA DESCRIZIONE
                            if is_admin:
                                # Admin: aggiorna memoria globale
                                supabase.table('prodotti_master')\
                                    .update({'categoria': info['nuova_categoria']})\
                                    .eq('descrizione', descrizione)\
                                    .execute()
                                
                                # Aggiorna anche fatture
                                result = supabase.table('fatture')\
                                    .update({'categoria': info['nuova_categoria']})\
                                    .eq('descrizione', descrizione)\
                                    .execute()
                            else:
                                # Cliente: aggiorna solo sue fatture
                                user_id = user.get('id')
                                result = supabase.table('fatture')\
                                    .update({'categoria': info['nuova_categoria']})\
                                    .eq('descrizione', descrizione)\
                                    .eq('user_id', user_id)\
                                    .execute()
                            
                            num_updated = len(result.data) if result.data else info['occorrenze']
                            success_count += 1
                            total_rows += num_updated
                            
                        except Exception as e:
                            logger.error(f"Errore salvataggio '{descrizione}': {e}")
                    
                    # Reset modifiche
                    st.session_state.modifiche_memoria = {}
                    st.cache_data.clear()
                    
                    st.success(f"✅ {success_count} modifiche salvate! {total_rows} righe aggiornate.")
                    time.sleep(1.5)
                    st.rerun()
        
        with col_cancel:
            if st.button("❌ Annulla Tutte", use_container_width=True, key="cancel_memoria_batch"):
                st.session_state.modifiche_memoria = {}
                st.rerun()
        
        with col_export:
            # Prepara CSV modifiche
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
                file_name=f"modifiche_memoria_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="export_memoria_csv"
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
