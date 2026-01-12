import extra_streamlit_components as stx
import tempfile
import shutil
import streamlit as st
import pandas as pd
import xmltodict
import os
import json
from openai import OpenAI
import plotly.express as px
import plotly.graph_objects as go
import io
import time
import re
import base64
import fitz  # PyMuPDF - conversione PDF senza dipendenze esterne
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError

# Import costanti e regex da modulo separato
from config.constants import (
    # Regex precompilate
    REGEX_UNITA_MISURA,
    REGEX_NUMERI_UNITA,
    REGEX_SOSTITUZIONI,
    REGEX_PUNTEGGIATURA,
    REGEX_ARTICOLI,
    REGEX_LETTERE_MINIME,
    REGEX_PATTERN_BOLLA,
    REGEX_KG_NUMERO,
    REGEX_GR_NUMERO,
    REGEX_ML_NUMERO,
    REGEX_CL_NUMERO,
    REGEX_LT_NUMERO,
    REGEX_PZ_NUMERO,
    REGEX_X_NUMERO,
    REGEX_PARENTESI_NUMERO,
    REGEX_NUMERO_KG,
    REGEX_NUMERO_LT,
    REGEX_NUMERO_GR,
    REGEX_PUNTEGGIATURA_FINALE,
    # Colori
    COLORI_PLOTLY,
    # Categorie
    CATEGORIE_FOOD_BEVERAGE,
    CATEGORIE_MATERIALI,
    CATEGORIE_SPESE_OPERATIVE,
    TUTTE_LE_CATEGORIE,
    CATEGORIE_FOOD,
    CATEGORIE_SPESE_GENERALI,
    # Fornitori NO FOOD (unificati)
    FORNITORI_NO_FOOD_KEYWORDS,
    # Dizionario correzioni
    DIZIONARIO_CORREZIONI
)

# Import utilities da moduli separati
from utils.text_utils import (
    normalizza_descrizione,
    get_descrizione_normalizzata_e_originale,
    normalizza_stringa,
    estrai_nome_categoria,
    estrai_fornitore_xml,
    aggiungi_icona_categoria
)

from utils.validation import (
    is_dicitura_sicura,
    verifica_integrita_fattura,
    is_prezzo_valido
)

from utils.formatters import (
    converti_in_base64,
    safe_get,
    calcola_prezzo_standard_intelligente,
    carica_categorie_da_db,
    log_upload_event
)

# Import services
from services.ai_service import (
    carica_memoria_completa,
    invalida_cache_memoria,
    ottieni_categoria_prodotto,
    categorizza_con_memoria,
    applica_correzioni_dizionario,
    salva_correzione_in_memoria_globale,
    classifica_con_ai,
    mostra_loading_ai,
    # Legacy functions
    carica_memoria_ai,
    salva_memoria_ai,
    aggiorna_memoria_ai
)

from services.auth_service import (
    verify_and_migrate_password,
    verifica_credenziali,
    invia_codice_reset,
)

from services.invoice_service import (
    estrai_dati_da_xml,
    estrai_dati_da_scontrino_vision,
    salva_fattura_processata,
)

from services.db_service import (
    carica_e_prepara_dataframe,
    ricalcola_prezzi_con_sconti,
    calcola_alert,
    carica_sconti_e_omaggi,
)



# ============================================================
# 🔍 ANALISI FATTURE AI - VERSIONE 3.2 FINAL COMPLETA
# ============================================================
# CHANGELOG V3.2 FINAL:
# ✅ BUGFIX CRITICO: safe_get con keep_list per DettaglioLinee
# ✅ Ripristinato (F&B) nelle etichette Tab
# ✅ Rimossi KPI ridondanti Tab Spese Generali
# ✅ Grafici identici originale (no etichette sotto)
# ✅ Ottimizzazioni Gemini complete
# ✅ CODICE COMPLETO 1800+ RIGHE
# ✅ PDF con PyMuPDF (no Poppler richiesto)
# ============================================================



# ============================================
# FUNZIONE CALCOLO PREZZO STANDARDIZZATO
# ============================================

st.set_page_config(
    page_title="Analisi Fatture AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# Nascondi bottone "Manage app"
st.markdown("""
<style>
    [data-testid="manage-app-button"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}
</style>
""", unsafe_allow_html=True)


# Elimina completamente sidebar in tutta l'app
st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        display: none !important;
    }
    section[data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)


# Nasconde il menu principale (tre puntini) e l'header per utenti finali
st.markdown(
    """
    <style>
      #MainMenu { visibility: hidden !important; }
      header[role="banner"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# CSS addizionale per nascondere bottoni/elementi con attributi che contengono Deploy/Share
st.markdown(
        """
        <style>
            button[title*="Deploy" i], a[title*="Deploy" i], [aria-label*="Deploy" i], [data-testid*="deploy" i] { display: none !important; }
            button[title*="Share" i], a[title*="Share" i], [aria-label*="Share" i], [data-testid*="share" i] { display: none !important; }
            /* italiano */
            button[title*="Condividi" i], a[title*="Condividi" i], [aria-label*="Condividi" i] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
)


# Rimuove dinamicamente eventuale bottone "Deploy"/"Share" in ambienti Streamlit Cloud
st.markdown(
        """
        <script>
            (function(){
                const keywords = ['deploy','share','deploy app','share app','condividi','pubblica'];
                function hideCandidates(){
                    try{
                        // scan common elements
                        const candidates = Array.from(document.querySelectorAll('button, a, div, span'));
                        candidates.forEach(el=>{
                            try{
                                const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                                const title = (el.title || '').toLowerCase();
                                const aria = (el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('data-testid') || '')) || '';
                                const attrs = (aria || '').toLowerCase();
                                const combined = [text, title, attrs].join(' ');
                                for(const k of keywords){
                                    if(k && combined.indexOf(k) !== -1){
                                        el.style.display = 'none';
                                        // also try to hide parent nodes to remove wrappers
                                        if(el.parentElement) el.parentElement.style.display = 'none';
                                        break;
                                    }
                                }
                            }catch(e){}
                        });
                    }catch(e){}
                }
                // initial run + repeated attempts (Streamlit may inject later)
                hideCandidates();
                const interval = setInterval(hideCandidates, 800);
                // observe DOM mutations as well
                const obs = new MutationObserver(hideCandidates);
                obs.observe(document.body, {childList:true, subtree:true});
                // stop interval after some time to avoid perf issues
                setTimeout(()=>{ clearInterval(interval); }, 20000);
            })();
        </script>
        """,
        unsafe_allow_html=True,
)


# ============================================================
# 🔒 SISTEMA AUTENTICAZIONE CON RECUPERO PASSWORD
# ============================================================

# Import mantenuti per compatibilità con altre parti del codice
import hashlib
from supabase import create_client, Client
from datetime import datetime, timedelta
import logging
import sys


# Logger con fallback cloud-compatible
logger = logging.getLogger('fci_app')
if not logger.handlers:
    try:
        # Prova filesystem locale (sviluppo)
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler('debug.log', maxBytes=5_000_000, backupCount=5, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.info("✅ Logging su file locale attivo")
    except (OSError, PermissionError) as e:
        # Fallback: stdout per cloud read-only
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info("✅ Logging su stdout attivo (cloud mode)")


# Inizializza Supabase
try:
    supabase_url = st.secrets["supabase"]["url"]
    supabase_key = st.secrets["supabase"]["key"]
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    logger.exception("Connessione Supabase fallita")
    st.error(f"⛔ Errore connessione Supabase: {e}")
    st.stop()


# RIPRISTINO SESSIONE DA COOKIE (dopo inizializzazione Supabase)
try:
    # Inizializza logged_in se non esiste
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Inizializza logout_in_progress se non esiste
    if 'logout_in_progress' not in st.session_state:
        st.session_state.logout_in_progress = False
    
    # Ripristina sessione da cookie SOLO se:
    # 1. NON è già loggato
    # 2. NON sta facendo logout
    if not st.session_state.logged_in and not st.session_state.logout_in_progress:
        cookie_manager = stx.CookieManager(key="cookie_manager_init")
        user_email_cookie = cookie_manager.get("user_email")
        logger.debug(f"Cookie recuperato all'avvio: {user_email_cookie}")
        if user_email_cookie:
            try:
                response = supabase.table("users").select("*").eq("email", user_email_cookie).eq("attivo", True).execute()
                if response and getattr(response, 'data', None):
                    st.session_state.logged_in = True
                    st.session_state.user_data = response.data[0]
                    logger.debug(f"Sessione ripristinata per: {user_email_cookie}")
            except Exception:
                logger.exception('Errore recupero utente da cookie')
    
    # Reset del flag logout dopo il primo rerun
    if st.session_state.logout_in_progress:
        st.session_state.logout_in_progress = False
except Exception:
    # Non fatale: se qualcosa va storto non blocchiamo l'app
    logger.exception('Errore controllo cookie sessione')


# ============================================================
# FUNZIONI AUTENTICAZIONE (SPOSTATA IN services/auth_service.py)
# ============================================================



def verifica_codice_reset(email, code, new_password):
    """Verifica codice e aggiorna password"""
    try:
        resp = supabase.table('users').select('*').eq('email', email).limit(1).execute()
        user = resp.data[0] if resp.data else None
        
        valid = False
        
        if user:
            stored_code = user.get('reset_code')
            if stored_code == code:
                valid = True
        
        if not valid:
            codes = st.session_state.get('reset_codes', {})
            entry = codes.get(email)
            if entry and entry.get('code') == code:
                valid = True
        
        if not valid:
            return None, "Codice errato o scaduto"
        
        new_hash = ph.hash(new_password)
        supabase.table('users').update({
            'password_hash': new_hash,
            'reset_code': None,
            'reset_expires': None
        }).eq('email', email).execute()
        
        if 'reset_codes' in st.session_state and email in st.session_state.reset_codes:
            del st.session_state.reset_codes[email]
        
        resp = supabase.table('users').select('*').eq('email', email).execute()
        return resp.data[0] if resp.data else None, None
        
    except Exception as e:
        logger.exception("Errore reset password")
        return None, str(e)


def mostra_pagina_login():
    """Form login con recupero password - ESTETICA STREAMLIT PULITA"""
    # Elimina completamente sidebar e pulsante
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            min-width: 0 !important;
        }
        section[data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        button[kind="header"] {
            display: none !important;
        }
        .css-1d391kg {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("## 🧠 Analisi Fatture AI")
    st.markdown("### Accedi al Sistema")
    
    tab1, tab2 = st.tabs(["🔑 Login", "🔄 Recupera Password"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input("🔑 Password", type="password", placeholder="Password")
            
            # CSS per bottone blu chiaro
            st.markdown("""
                <style>
                div[data-testid="stFormSubmitButton"] button {
                    background-color: #0ea5e9 !important;
                    color: white !important;
                }
                div[data-testid="stFormSubmitButton"] button:hover {
                    background-color: #0284c7 !important;
                }
                </style>
            """, unsafe_allow_html=True)
            
            submit = st.form_submit_button("🚀 Accedi", use_container_width=True)
            
            if submit:
                if not email or not password:
                    st.error("⚠️ Compila tutti i campi!")
                else:
                    with st.spinner("Verifica credenziali..."):
                        user, errore = verifica_credenziali(email, password)
                        
                        if user:
                            st.session_state.logged_in = True
                            st.session_state.user_data = user


                            # SALVA COOKIE PER MANTENERE SESSIONE
                            cookie_manager = stx.CookieManager(key="cookie_manager_login")
                            try:
                                # Impostiamo expires_at come oggetto datetime (expectation di CookieManager)
                                expires_at = datetime.now() + timedelta(days=7)
                                res = cookie_manager.set("user_email", user['email'], expires_at=expires_at)
                                logger.debug(f"Cookie set result: {res}")
                                # Leggiamo immediatamente il cookie per verifica
                                read_back = cookie_manager.get("user_email")
                                logger.debug(f"Cookie letto dopo set: {read_back}")
                            except Exception:
                                logger.exception('Impossibile impostare cookie')


                            st.success("✅ Accesso effettuato!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {errore}")
    
    with tab2:
        st.markdown("#### Reset Password via Email")
        
        reset_email = st.text_input("📧 Email per reset", placeholder="tua@email.com", key="reset_email")
        
        if st.button("📨 Invia Codice", use_container_width=True):
            if not reset_email:
                st.warning("⚠️ Inserisci un'email")
            else:
                success, msg = invia_codice_reset(reset_email)
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.info(f"ℹ️ {msg}")
        
        st.markdown("---")
        
        code_input = st.text_input("🔢 Codice ricevuto", placeholder="Inserisci il codice", key="code_input")
        new_pwd = st.text_input("🔑 Nuova password (min 8 caratteri)", type="password", key="new_pwd")
        confirm_pwd = st.text_input("🔑 Conferma password", type="password", key="confirm_pwd")
        
        if st.button("✅ Conferma Reset", use_container_width=True, type="primary"):
            if not reset_email or not code_input or not new_pwd or not confirm_pwd:
                st.warning("⚠️ Compila tutti i campi")
            elif new_pwd != confirm_pwd:
                st.error("❌ Le password non coincidono")
            elif len(new_pwd) < 8:
                st.error("❌ Password troppo corta (min 8 caratteri)")
            else:
                user, errore = verifica_codice_reset(reset_email, code_input, new_pwd)
                
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user_data = user
                    st.success("✅ Password aggiornata! Accesso automatico...")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error(f"❌ {errore}")


# ============================================================
# CHECK LOGIN ALL'AVVIO
# ============================================================


# logged_in già inizializzato nella sezione RIPRISTINO SESSIONE DA COOKIE


if not st.session_state.logged_in:
    mostra_pagina_login()
    st.stop()


# Se arrivi qui, sei loggato! Vai DIRETTO ALL'APP
user = st.session_state.user_data


# ============================================
# BANNER IMPERSONAZIONE (solo per admin che impersonano)
# ============================================

if st.session_state.get('impersonating', False):
    # Banner visibile quando l'admin sta impersonando un cliente
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f59e0b 0%, #dc2626 100%); 
                padding: 15px; 
                border-radius: 10px; 
                margin-bottom: 20px; 
                text-align: center;
                border: 3px solid #dc2626;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
        <h3 style="color: white; margin: 0;">
            ⚠️ MODALITÀ IMPERSONAZIONE
        </h3>
        <p style="color: #fef3c7; margin: 10px 0 0 0; font-size: 16px;">
            Stai visualizzando l'account di: <strong>{user.get('nome_ristorante', 'Cliente')}</strong> ({user.get('email')})
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Bottone "Torna Admin" in colonna separata
    col_back_admin, col_spacer = st.columns([2, 8])
    with col_back_admin:
        if st.button("🔙 Torna Admin", type="primary", use_container_width=True, key="back_to_admin_btn"):
            # Ripristina dati admin originali
            if 'admin_original_user' in st.session_state:
                st.session_state.user_data = st.session_state.admin_original_user.copy()
                del st.session_state.admin_original_user
                st.session_state.impersonating = False
                
                # Log uscita impersonazione
                logger.info(f"FINE IMPERSONAZIONE: Ritorno a admin {st.session_state.user_data.get('email')}")
                
                # Redirect al pannello admin
                st.switch_page("pages/admin.py")
            else:
                st.error("⚠️ Errore: dati admin originali non trovati")
                st.session_state.impersonating = False
                st.rerun()
    
    st.markdown("---")


# ============================================
# HEADER CON LOGOUT, LINK ADMIN E CAMBIO PASSWORD
# ============================================


# Lista admin (deve coincidere con quella in pages/admin.py)
ADMIN_EMAILS = ["mattiadavolio90@gmail.com"]


# Struttura colonne: se admin mostra 4 colonne, altrimenti 3
if user.get('email') in ADMIN_EMAILS:
    col1, col2, col3, col4 = st.columns([6, 1.5, 1.5, 1])
else:
    col1, col2, col3 = st.columns([7, 2, 1])


with col1:
    st.markdown("""
<h1 style="font-size: 52px; font-weight: 700; margin: 0; display: inline-block;">
    🧠 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi Fatture AI</span>
</h1>
""", unsafe_allow_html=True)
    st.caption(f"👤 {user.get('nome_ristorante', 'Utente')} | 📧 {user.get('email')}")


# Pulsanti diversi per admin e clienti
if user.get('email') in ADMIN_EMAILS:
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔧 Pannello Admin", use_container_width=True, key="admin_panel_btn"):
            st.switch_page("pages/admin.py")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Password", use_container_width=True, key="change_pwd_btn"):
            st.switch_page("pages/cambio_password.py")
    
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", type="primary", use_container_width=True, key="logout_btn"):
            # Imposta flag per evitare auto-login dal cookie
            st.session_state.logout_in_progress = True
            
            # Cancella il cookie per evitare auto-login al prossimo refresh
            try:
                cookie_manager = stx.CookieManager(key="cookie_manager_logout")
                cookie_manager.delete("user_email")
            except Exception:
                logger.exception('Errore cancellazione cookie al logout')
            
            st.session_state.logged_in = False
            st.session_state.user_data = None
            st.rerun()
else:
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Cambio Password", use_container_width=True, key="change_pwd_btn"):
            st.switch_page("pages/cambio_password.py")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", type="primary", use_container_width=True, key="logout_btn_alt"):
            # Imposta flag per evitare auto-login dal cookie
            st.session_state.logout_in_progress = True
            
            # Cancella il cookie per evitare auto-login al prossimo refresh
            try:
                cookie_manager = stx.CookieManager(key="cookie_manager_logout2")
                cookie_manager.delete("user_email")
            except Exception:
                logger.exception('Errore cancellazione cookie al logout')
            
            st.session_state.logged_in = False
            st.session_state.user_data = None
            st.rerun()


st.markdown("---")

# ============================================================
# PROSEGUE CODICE NORMALE APP
# ============================================================
# ============================================================
# FILE DI MEMORIA
# ============================================================
# MEMORIA_FILE rimosso - usa solo Supabase
MEMORIA_AI_FILE = "memoria_ai_correzioni.json"
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    logger.exception("API Key OpenAI non trovata o accesso a st.secrets fallito")
    st.error("⛔ ERRORE: API Key non trovata!")
    st.stop()



client = OpenAI(api_key=api_key)


# ============================================
# 🔥 USA STESSA CONNESSIONE SUPABASE GIÀ INIZIALIZZATA
# ============================================
# Non serve ricreare la connessione, usiamo quella già creata sopra!
# La variabile 'supabase' è già disponibile globalmente


# ============================================================
# CARICAMENTO CATEGORIE DINAMICHE DA DATABASE
# ============================================================

# ============================================================
# FUNZIONI MEMORIA AI (SPOSTATA IN services/ai_service.py)
# ============================================================


# ============================================================
# FUNZIONI DATABASE (SPOSTATE IN services/db_service.py)
# ============================================================

# ============================================================
# FUNZIONI MEMORIA PRINCIPALE
# ============================================================



# Funzioni carica_memoria() e salva_memoria() RIMOSSE
# Usa solo Supabase come unica fonte dati


# ============================================================
# FUNZIONI GESTIONE FATTURE (SPOSTATA IN services/invoice_service.py)
# ============================================================

# ============================================================
# ELIMINAZIONE FATTURE
# ============================================================


def elimina_fattura_completa(file_origine, user_id):
    """
    Elimina una fattura completa (tutti i prodotti) dal database.
    
    Args:
        file_origine: Nome del file XML della fattura
        user_id: ID utente (per controllo sicurezza)
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int}
    """
    try:
        # Verifica che l'utente sia autenticato
        if not user_id:
            return {"success": False, "error": "not_authenticated", "righe_eliminate": 0}
        
        # Prima conta quante righe verranno eliminate
        count_response = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("file_origine", file_origine).execute()
        num_righe = len(count_response.data) if count_response.data else 0
        
        if num_righe == 0:
            return {"success": False, "error": "not_found", "righe_eliminate": 0}
        
        # Elimina dal database (con controllo user_id per sicurezza)
        response = supabase.table("fatture").delete().eq("user_id", user_id).eq("file_origine", file_origine).execute()
        
        # Log operazione
        logger.info(f"❌ Fattura eliminata: {file_origine} ({num_righe} righe) da user {user_id}")
        
        # Invalida cache per ricaricare dati
        st.cache_data.clear()
        invalida_cache_memoria()
        
        return {"success": True, "error": None, "righe_eliminate": num_righe}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione fattura {file_origine} per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0}


def elimina_tutte_fatture(user_id):
    """
    Elimina TUTTE le fatture dell'utente dal database.
    
    Args:
        user_id: ID utente (per controllo sicurezza)
    
    Returns:
        dict: {"success": bool, "error": str, "righe_eliminate": int, "fatture_eliminate": int}
    """
    try:
        # Verifica che l'utente sia autenticato
        if not user_id:
            return {"success": False, "error": "not_authenticated", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Prima conta quante righe e fatture verranno eliminate
        count_response = supabase.table("fatture").select("id, file_origine", count="exact").eq("user_id", user_id).execute()
        num_righe = count_response.count if count_response.count else 0
        num_fatture = len(set([r['file_origine'] for r in count_response.data])) if count_response.data else 0
        
        print(f"🔍 PRIMA DELETE: user_id={user_id} ha {num_fatture} fatture ({num_righe} righe)")
        logger.info(f"🔍 PRIMA DELETE: user_id={user_id} ha {num_fatture} fatture ({num_righe} righe)")
        
        if num_righe == 0:
            return {"success": False, "error": "no_data", "righe_eliminate": 0, "fatture_eliminate": 0}
        
        # Elimina TUTTO per questo user_id
        response = supabase.table("fatture").delete().eq("user_id", user_id).execute()
        
        # 🔍 LOG DETTAGLIATO NUOVO
        print(f"🗑️ DELETE executed for user_id={user_id}")
        print(f"📊 DELETE result: {response}")
        logger.info(f"🗑️ DELETE executed for user_id={user_id}")
        logger.info(f"📊 DELETE result: {response}")
        
        # Verifica post-delete (conferma eliminazione)
        verify_response = supabase.table("fatture").select("id, file_origine, data_documento").eq("user_id", user_id).execute()
        num_rimaste = len(verify_response.data) if verify_response.data else 0
        
        print(f"✅ Righe rimaste dopo DELETE: {num_rimaste}")
        logger.info(f"✅ Righe rimaste dopo DELETE: {num_rimaste}")
        
        if num_rimaste > 0:
            print(f"⚠️ ATTENZIONE: DELETE NON COMPLETA!")
            print(f"📋 Prime 5 righe rimaste: {verify_response.data[:5]}")
            
            # Analizza QUALI righe sono sopravvissute
            fornitori_rimasti = set([r.get('file_origine', 'N/A') for r in verify_response.data])
            print(f"📊 File rimasti: {list(fornitori_rimasti)[:10]}")
            
            # Verifica se hanno lo stesso user_id
            user_ids_rimasti = set([r.get('user_id', 'N/A') for r in verify_response.data]) if 'user_id' in verify_response.data[0] else {'N/A'}
            print(f"🆔 User IDs delle righe rimaste: {user_ids_rimasti}")
            print(f"🆔 User ID attuale richiesto: {user_id}")
            
            if user_id not in user_ids_rimasti and 'N/A' not in user_ids_rimasti:
                print(f"🚨 PROBLEMA RLS: Le righe rimaste hanno user_id DIVERSO!")
            
            logger.error(f"⚠️ DELETE PARZIALE: {num_rimaste} righe ancora presenti per user {user_id}")
            logger.error(f"📋 Prime 5 righe rimaste: {verify_response.data[:5]}")
        else:
            print(f"✅ DELETE VERIFIED: Database completamente pulito")
            logger.info(f"✅ DELETE COMPLETA: 0 righe rimaste per user {user_id}")
        
        # Log operazione
        logger.warning(f"⚠️ ELIMINAZIONE MASSIVA: {num_fatture} fatture ({num_righe} righe) da user {user_id}")
        
        # Invalida cache per ricaricare dati
        st.cache_data.clear()
        invalida_cache_memoria()
        
        return {"success": True, "error": None, "righe_eliminate": num_righe, "fatture_eliminate": num_fatture}
        
    except Exception as e:
        logger.exception(f"Errore eliminazione massiva per user {user_id}")
        return {"success": False, "error": str(e), "righe_eliminate": 0, "fatture_eliminate": 0}

# ============================================================
# TEST & AUDIT UTILITIES
# ============================================================


def audit_data_consistency(user_id: str, context: str = "unknown") -> dict:
    """
    🔍 Verifica coerenza dati tra DB, Cache e UI
    
    Args:
        user_id: ID utente da verificare
        context: Contesto della chiamata (es. "post-delete", "post-upload")
    
    Returns:
        dict con dettagli verifica:
        - db_count: righe su Supabase
        - db_files: file unici su Supabase
        - cache_count: righe in cache
        - cache_files: file unici in cache
        - consistent: bool (True se DB = Cache)
    """
    result = {
        "context": context,
        "user_id": user_id,
        "db_count": 0,
        "db_files": 0,
        "cache_count": 0,
        "cache_files": 0,
        "consistent": False,
        "error": None
    }
    
    try:
        # 1. Query diretta DB (bypass cache)
        db_response = supabase.table("fatture").select("file_origine", count="exact").eq("user_id", user_id).execute()
        result["db_count"] = db_response.count if db_response.count else 0
        result["db_files"] = len(set([r['file_origine'] for r in db_response.data])) if db_response.data else 0
        
        # 2. Query cache (potrebbe essere stale)
        df_cached = carica_e_prepara_dataframe(user_id)
        result["cache_count"] = len(df_cached)
        result["cache_files"] = df_cached['FileOrigine'].nunique() if not df_cached.empty else 0
        
        # 3. Verifica coerenza
        result["consistent"] = (result["db_count"] == result["cache_count"])
        
        # 4. Log audit
        if result["consistent"]:
            logger.info(f"✅ AUDIT OK [{context}]: DB={result['db_count']} Cache={result['cache_count']} (user={user_id})")
        else:
            logger.warning(f"⚠️ AUDIT FAIL [{context}]: DB={result['db_count']} ≠ Cache={result['cache_count']} (user={user_id})")
        
        return result
        
    except Exception as e:
        logger.exception(f"Errore audit per user {user_id}")
        result["error"] = str(e)
        return result


def get_fatture_stats(user_id: str) -> dict:
    """
    📊 Ottiene statistiche fatture SOLO da Supabase.
    Fonte unica di verità per tutti i conteggi UI.
    
    Args:
        user_id: ID utente per filtro multi-tenancy
    
    Returns:
        dict con:
        - num_uniche: Numero fatture uniche (FileOrigine distinti)
        - num_righe: Numero totale righe/prodotti
        - success: bool (True se query riuscita)
    
    GARANZIE:
    - Legge SOLO da Supabase (nessun cache/sessione)
    - Coerente con Gestione Fatture
    - Usato per tutti i conteggi pubblici
    """
    try:
        response = supabase.table("fatture") \
            .select("file_origine", count='exact') \
            .eq("user_id", user_id) \
            .execute()
        
        if not response.data:
            return {"num_uniche": 0, "num_righe": 0, "success": True}
        
        # Conta file unici e righe totali
        file_unici_set = set([r["file_origine"] for r in response.data])
        
        return {
            "num_uniche": len(file_unici_set),
            "num_righe": response.count,  # ✅ FIX: usa count reale invece di len()
            "success": True
        }
    except Exception as e:
        logger.error(f"Errore get_fatture_stats per user {user_id}: {e}")
        return {"num_uniche": 0, "num_righe": 0, "success": False}


# ============================================================
# CACHING DATAFRAME OTTIMIZZATO
# ============================================================


@st.cache_data(ttl=None, max_entries=50)  # ← NESSUN TTL: invalidazione SOLO manuale con clear()
# ============================================================
# CONVERSIONE FILE IN BASE64 PER VISION
# ============================================================


# ============================================================
# FUNZIONI CALCOLO ALERT PREZZI (SPOSTATE IN services/db_service.py)
# ============================================================

# ============================================================
# FUNZIONE PIVOT MENSILE
# ============================================================


@st.cache_data(ttl=None, show_spinner=False, max_entries=50)
def crea_pivot_mensile(df, index_col):
    if df.empty:
        return pd.DataFrame()
    
    df_temp = df.copy()
    df_temp['Data_DT'] = pd.to_datetime(df_temp['DataDocumento'], errors='coerce')


    # Controlla date invalide
    date_invalide = df_temp['Data_DT'].isna().sum()
    if date_invalide > 0:
        st.warning(
            f"⚠️ ATTENZIONE: {date_invalide} fatture hanno date non valide e non appariranno nei grafici temporali."
        )
        
        fatture_problema = df_temp[df_temp['Data_DT'].isna()][['Fornitore', 'Numero_Fattura', 'Data_Documento']].head(5)
        if not fatture_problema.empty:
            with st.expander("📋 Mostra fatture con date problematiche"):
                st.dataframe(fatture_problema)


    # Mesi in italiano maiuscolo
    mesi_ita = {
        1: 'GENNAIO', 2: 'FEBBRAIO', 3: 'MARZO', 4: 'APRILE',
        5: 'MAGGIO', 6: 'GIUGNO', 7: 'LUGLIO', 8: 'AGOSTO',
        9: 'SETTEMBRE', 10: 'OTTOBRE', 11: 'NOVEMBRE', 12: 'DICEMBRE'
    }
    df_temp['Mese'] = df_temp['Data_DT'].apply(
        lambda x: f"{mesi_ita[x.month]} {x.year}" if pd.notna(x) else ''
    )


    pivot = df_temp.pivot_table(
        index=index_col,
        columns='Mese',
        values='TotaleRiga',
        aggfunc='sum',
        fill_value=0
    )


    cols_sorted = sorted(list(pivot.columns))
    pivot = pivot[cols_sorted]
    pivot['TOTALE ANNO'] = pivot.sum(axis=1)
    pivot = pivot.reset_index()
    pivot = pivot.sort_values('TOTALE ANNO', ascending=False)


    return pivot


def genera_box_recap(num_righe, totale):
    return f"""
    <div style="background-color: #E3F2FD; padding: 17px 20px; border-radius: 8px; border: 2px solid #2196F3; display: inline-block; width: auto;">
        <p style="color: #1565C0; font-size: 18px; font-weight: bold; margin: 0; line-height: 1; white-space: nowrap;">
            📋 N. Righe Elaborate: {num_righe:,} | 💰 Totale: € {totale:.2f}
        </p>
    </div>
    """

# ============================================================
# FUNZIONE RENDERING STATISTICHE
# ============================================================



def mostra_statistiche(df_completo):
    """Mostra grafici, filtri e tabella dati"""
    
    # ===== 🔍 DEBUG CATEGORIZZAZIONE (SOLO ADMIN/IMPERSONIFICATO) =====
    if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
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
            
            st.markdown("**Sample 15 righe (verifica categoria):**")
            sample_df = df_completo[['FileOrigine', 'Descrizione', 'Categoria', 'Fornitore', 'TotaleRiga']].head(15)
            st.dataframe(sample_df, hide_index=True, use_container_width=True)
            
            # Test query diretta Supabase
            if st.button("🔄 Ricarica da Supabase (bypass cache)", key="debug_reload"):
                st.cache_data.clear()
                st.rerun()
    # ===== FINE DEBUG =====
    
    # ===== FILTRA DICITURE DA TUTTA L'ANALISI =====
    righe_prima = len(df_completo)
    na_prima = df_completo['Categoria'].isna().sum()
    logger.info(f"🔍 PRE-FILTRO DICITURE: {righe_prima} righe totali, {na_prima} con categoria NA")
    
    # 🔧 FIX: Usa fillna per mantenere righe con categoria NA/NULL (non sono diciture!)
    df_completo = df_completo[df_completo['Categoria'].fillna('') != '📝 NOTE E DICITURE'].copy()
    righe_dopo = len(df_completo)
    na_dopo = df_completo['Categoria'].isna().sum()
    logger.info(f"🔍 POST-FILTRO DICITURE: {righe_dopo} righe totali, {na_dopo} con categoria NA")
    
    if righe_prima > righe_dopo:
        logger.info(f"Diciture escluse dall'analisi: {righe_prima - righe_dopo} righe")
    
    if df_completo.empty:
        st.info("📭 Nessun dato disponibile dopo i filtri.")
        return
    # ===== FINE FILTRO DICITURE =====
    
    # Recupera user_id da session_state (necessario per get_fatture_stats)
    user_id = st.session_state.user_data["id"]
    
    # Crea pattern per esclusione fornitori NO FOOD (usa costante importata)
    pattern_no_food = '|'.join(FORNITORI_NO_FOOD_KEYWORDS)
    mask_fornitori_no_food = df_completo['Fornitore'].str.upper().str.contains(pattern_no_food, na=False, regex=True)
    
    mask_spese = df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
    df_spese_generali_completo = df_completo[mask_spese].copy()
    
    # F&B: Escludi spese generali E fornitori sicuramente NO FOOD
    df_food_completo = df_completo[(~mask_spese) & (~mask_fornitori_no_food)].copy()
    
    # Spazio sotto il box arancione
    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)


    # ============================================
    # CATEGORIZZAZIONE AI
    # ============================================
    
    # Conta righe da classificare PRIMA del bottone
    maschera_ai = (
        df_completo['Categoria'].isna()
        | (df_completo['Categoria'] == 'Da Classificare')
    )
    righe_da_classificare = maschera_ai.sum()
    
    # ============================================================
    # LAYOUT: BOTTONE + TESTO INFORMATIVO
    # ============================================================
    col_btn, col_info = st.columns([1, 2])
    
    with col_btn:
        # Bottone categorizzazione AI (disabilitato se nulla da classificare)
        if st.button(
            "🧠 Avvia AI per Categorizzare", 
            use_container_width=True, 
            type="secondary",  # ← GRIGIO
            key="btn_ai_categorizza",
            disabled=(righe_da_classificare == 0)
        ):
            # ============================================================
            # VERIFICA FINALE (sicurezza)
            # ============================================================
            if righe_da_classificare == 0:
                st.warning("⚠️ Nessun prodotto da classificare")
                st.stop()
            
            # ============================================================
            # CHIAMATA AI (SOLO DESCRIZIONI DA CLASSIFICARE)
            # ============================================================
            with st.spinner(f"L'AI sta analizzando i tuoi prodotti..."):
                descrizioni_da_classificare = df_completo[maschera_ai]['Descrizione'].unique().tolist()
                fornitori_da_classificare = df_completo[maschera_ai]['Fornitore'].unique().tolist()

                if descrizioni_da_classificare:
                    with st.spinner(f"🧠 Classificazione AI in corso... ({len(descrizioni_da_classificare)} prodotti)"):
                        mappa_categorie = {}
                        chunk_size = 50
                        for i in range(0, len(descrizioni_da_classificare), chunk_size):
                            chunk = descrizioni_da_classificare[i:i+chunk_size]
                            cats = classifica_con_ai(chunk, fornitori_da_classificare)
                            for desc, cat in zip(chunk, cats):
                                mappa_categorie[desc] = cat
                                aggiorna_memoria_ai(desc, cat)
                                
                                # Salva anche in memoria GLOBALE su Supabase
                                try:
                                    from datetime import datetime
                                    supabase.table('prodotti_master').upsert({
                                        'descrizione': desc,
                                        'categoria': cat,
                                        'volte_visto': 1,
                                        'classificato_da': 'AI',
                                        'updated_at': datetime.now().isoformat()
                                    }, on_conflict='descrizione').execute()
                                    
                                    # Invalida cache per forzare ricaricamento
                                    invalida_cache_memoria()
                                    
                                    logger.info(f"💾 GLOBALE salvato: '{desc[:40]}...' → {cat}")
                                except Exception as e:
                                    logger.error(f"Errore salvataggio globale '{desc[:40]}...': {e}")


                    # Aggiorna categorie su Supabase
                    try:
                        user_id = st.session_state.user_data["id"]
                        
                        for desc, cat in mappa_categorie.items():
                            # Aggiorna tutte le righe con questa descrizione
                            supabase.table("fatture").update(
                                {"categoria": cat}
                            ).eq("user_id", user_id).eq("descrizione", desc).execute()
                        
                        st.toast(f"✅ Categorizzati {len(descrizioni_da_classificare)} prodotti su Supabase!")
                        logger.info(f"🔄 CATEGORIZZAZIONE AI: Aggiornate {len(descrizioni_da_classificare)} descrizioni")
                        
                        # Pulisci cache PRIMA del delay per garantire ricaricamento
                        st.cache_data.clear()
                        invalida_cache_memoria()
                        
                        # Delay per garantire propagazione modifiche su Supabase
                        time.sleep(2)
                        
                        # Rerun per ricaricare dati freschi
                        st.rerun()
                        
                    except Exception as e:
                        logger.exception("Errore aggiornamento categorie AI su Supabase")
                        st.error(f"❌ Errore aggiornamento categorie: {e}")
    
    with col_info:
        # ============================================================
        # BOX INFO CON ALTEZZA FISSA = ALTEZZA BOTTONE (38px)
        # ============================================================
        if righe_da_classificare == 0:
            st.markdown("""
            <div style="
                background-color: #d4edda;
                border-left: 4px solid #28a745;
                padding: 0px 15px;
                border-radius: 4px;
                height: 38px;
                display: flex;
                align-items: center;
                margin-top: 0px;
            ">
                <span style="color: #155724; font-weight: 600; font-size: 14px;">✅ NON CI SONO prodotti da categorizzare</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="
                background-color: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 0px 15px;
                border-radius: 4px;
                height: 38px;
                display: flex;
                align-items: center;
                margin-top: 0px;
            ">
                <span style="color: #856404; font-weight: 600; font-size: 14px;">⚠️ CI SONO {righe_da_classificare} prodotti da categorizzare</span>
            </div>
            """, unsafe_allow_html=True)
    
    # ============================================
    # FILTRO DROPDOWN PERIODO
    # ============================================
    st.subheader("📅 Filtra per Periodo")
    
    # Calcola date dinamiche per i filtri
    oggi = pd.Timestamp.now()
    oggi_date = oggi.date()
    inizio_mese = oggi.replace(day=1).date()
    inizio_trimestre = oggi.replace(month=((oggi.month-1)//3)*3+1, day=1).date()
    inizio_semestre = oggi.replace(month=1 if oggi.month <= 6 else 7, day=1).date()
    inizio_anno = oggi.replace(month=1, day=1).date()
    
    # Opzioni filtro periodo
    periodo_options = [
        "📅 Mese in Corso",
        "📊 Trimestre in Corso",
        "📈 Semestre in Corso",
        "🗓️ Anno in Corso",
        "📋 Anno Scorso",
        "⚙️ Periodo Personalizzato"
    ]
    
    # Default: Mese in Corso
    if 'periodo_dropdown' not in st.session_state:
        st.session_state.periodo_dropdown = " Mese in Corso"
    
    # Selectbox
    periodo_selezionato = st.selectbox(
        "",
        options=periodo_options,
        index=periodo_options.index(st.session_state.periodo_dropdown) if st.session_state.periodo_dropdown in periodo_options else 0,
        key="filtro_periodo_main"
    )
    
    # Aggiorna session state
    st.session_state.periodo_dropdown = periodo_selezionato
    
    # Gestione logica periodo
    data_inizio_filtro = None
    data_fine_filtro = oggi_date
    
    if periodo_selezionato == " Mese in Corso":
        data_inizio_filtro = inizio_mese
        label_periodo = f"Mese in corso ({inizio_mese.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == " Trimestre in Corso":
        data_inizio_filtro = inizio_trimestre
        label_periodo = f"Trimestre in corso ({inizio_trimestre.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == " Semestre in Corso":
        data_inizio_filtro = inizio_semestre
        label_periodo = f"Semestre in corso ({inizio_semestre.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == " Anno in Corso":
        data_inizio_filtro = inizio_anno
        label_periodo = f"Anno in corso ({inizio_anno.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📋 Anno Scorso":
        inizio_anno_scorso = (oggi.replace(year=oggi.year - 1, month=1, day=1)).date()
        fine_anno_scorso = (oggi.replace(year=oggi.year - 1, month=12, day=31)).date()
        data_inizio_filtro = inizio_anno_scorso
        data_fine_filtro = fine_anno_scorso
        label_periodo = f"Anno scorso ({inizio_anno_scorso.strftime('%d/%m/%Y')} → {fine_anno_scorso.strftime('%d/%m/%Y')})"
    
    else:  # Periodo Personalizzato
        st.markdown("##### Seleziona Range Date")
        col_da, col_a = st.columns(2)
        
        # Inizializza date personalizzate se non esistono
        if 'data_inizio_filtro' not in st.session_state:
            st.session_state.data_inizio_filtro = inizio_anno
        if 'data_fine_filtro' not in st.session_state:
            st.session_state.data_fine_filtro = oggi_date
        
        with col_da:
            data_inizio_custom = st.date_input(
                "📅 Da", 
                value=st.session_state.data_inizio_filtro, 
                key="data_da_custom"
            )
        
        with col_a:
            data_fine_custom = st.date_input(
                "📅 A", 
                value=st.session_state.data_fine_filtro, 
                key="data_a_custom"
            )
        
        # Valida date
        if data_inizio_custom > data_fine_custom:
            st.error("⚠️ La data iniziale deve essere precedente alla data finale!")
            data_inizio_filtro = st.session_state.data_inizio_filtro
            data_fine_filtro = st.session_state.data_fine_filtro
        else:
            # Salva le date valide
            st.session_state.data_inizio_filtro = data_inizio_custom
            st.session_state.data_fine_filtro = data_fine_custom
            data_inizio_filtro = data_inizio_custom
            data_fine_filtro = data_fine_custom
        
        label_periodo = f"{data_inizio_filtro.strftime('%d/%m/%Y')} → {data_fine_filtro.strftime('%d/%m/%Y')}"
    
    # Fallback se data_inizio_filtro è None (non dovrebbe mai accadere)
    if data_inizio_filtro is None:
        data_inizio_filtro = inizio_mese
        label_periodo = "Periodo non valido"
    
    # APPLICA FILTRO AI DATI
    df_food_completo["Data_DT"] = pd.to_datetime(df_food_completo["DataDocumento"], errors='coerce').dt.date
    mask = (df_food_completo["Data_DT"] >= data_inizio_filtro) & (df_food_completo["Data_DT"] <= data_fine_filtro)
    df_food = df_food_completo[mask].copy()
    
    df_spese_generali_completo["Data_DT"] = pd.to_datetime(df_spese_generali_completo["DataDocumento"], errors='coerce').dt.date
    mask_spese = (df_spese_generali_completo["Data_DT"] >= data_inizio_filtro) & (df_spese_generali_completo["Data_DT"] <= data_fine_filtro)
    df_spese_generali = df_spese_generali_completo[mask_spese].copy()
    
    # Calcola giorni nel periodo
    giorni = (data_fine_filtro - data_inizio_filtro).days + 1
    
    # Stats globali
    stats_totali = get_fatture_stats(user_id)
    df_completo_filtrato = df_completo[df_completo['DataDocumento'].isin(df_food['DataDocumento'])]
    num_doc_filtrati = df_completo_filtrato['FileOrigine'].nunique()
    
    # Mostra info periodo
    st.info(f"🔍 **{label_periodo}** ({giorni} giorni) | Righe F&B: **{len(df_food):,}** | Righe Totali: {stats_totali['num_righe']:,} | Fatture: {num_doc_filtrati} di {stats_totali['num_uniche']}")
    
    if df_food.empty and df_spese_generali.empty:
        st.warning("⚠️ Nessuna fattura nel periodo selezionato")
        st.stop()
    
    st.markdown("---")

    # CSS per stilizzare le metrics con colori diversi per ogni card
    st.markdown("""
    <style>
        [data-testid="stMetricValue"] {
            font-size: 36px;
            font-weight: bold;
            color: white !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 15px;
            font-weight: 600;
            color: rgba(255,255,255,0.9) !important;
        }
        div[data-testid="metric-container"] {
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
            color: white;
            min-height: 120px;
        }
        /* Colori diversi per ogni colonna */
        div[data-testid="column"]:nth-child(1) div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        div[data-testid="column"]:nth-child(2) div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        div[data-testid="column"]:nth-child(3) div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        div[data-testid="column"]:nth-child(4) div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        }
        div[data-testid="column"]:nth-child(5) div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }
        /* Nascondi il delta sotto variazione */
        div[data-testid="column"]:nth-child(5) [data-testid="stMetricDelta"] {
            display: none;
        }
    </style>
    """, unsafe_allow_html=True)

    # Calcola variabili per i KPI
    spesa_fb = df_food['TotaleRiga'].sum()
    spesa_generale = df_spese_generali['TotaleRiga'].sum()
    num_fornitori = df_food['Fornitore'].nunique()
    
    # Layout 5 colonne per i KPI - Stile minimal
    col1, col2, col3, col4, col5 = st.columns(5)

    # Calcola spesa totale
    spesa_totale = spesa_fb + spesa_generale

    with col1:
        st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #667eea;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">💰 Spesa Totale (F&B + Spese Generali)</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">€ """ + f"{spesa_totale:.2f}" + """</h2>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #f093fb;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">🔥 Spesa F&B</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">€ """ + f"{spesa_fb:.2f}" + """</h2>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #4facfe;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">🛒 Spesa Generale</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">€ """ + f"{spesa_generale:.2f}" + """</h2>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #43e97b;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">🏪 N. Fornitori Analizzati</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">""" + str(num_fornitori) + """</h2>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        # Calcola spesa media mensile
        mesi_periodo = len(pd.to_datetime(df_completo['DataDocumento']).dt.to_period('M').unique())
        spesa_media = spesa_totale / mesi_periodo if mesi_periodo > 0 else 0
        
        st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #fa709a;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">📊 Spesa Media Mensile (F&B + Spese Generali)</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">€ """ + f"{spesa_media:.2f}" + """</h2>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    # 🎨 NAVIGAZIONE CON BOTTONI COLORATI (invece di tab)
    if 'sezione_attiva' not in st.session_state:
        st.session_state.sezione_attiva = "dettaglio"
    if 'is_loading' not in st.session_state:
        st.session_state.is_loading = False
    
    st.markdown("### 📊 Naviga tra le Sezioni")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if st.button("📦 DETTAGLIO\nARTICOLI", key="btn_dettaglio", use_container_width=True, 
                     type="primary" if st.session_state.sezione_attiva == "dettaglio" else "secondary"):
            if st.session_state.sezione_attiva != "dettaglio":
                st.session_state.sezione_attiva = "dettaglio"
                st.session_state.is_loading = True
                st.rerun()
    
    with col2:
        if st.button("🚨 ALERT\nARTICOLI (F&B)", key="btn_alert", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "alert" else "secondary"):
            if st.session_state.sezione_attiva != "alert":
                st.session_state.sezione_attiva = "alert"
                st.session_state.is_loading = True
                st.rerun()
    
    with col3:
        if st.button("📈 CATEGORIE\n(F&B)", key="btn_categorie", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "categorie" else "secondary"):
            if st.session_state.sezione_attiva != "categorie":
                st.session_state.sezione_attiva = "categorie"
                st.session_state.is_loading = True
                st.rerun()
    
    with col4:
        if st.button("🚚 FORNITORI\n(F&B)", key="btn_fornitori", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "fornitori" else "secondary"):
            if st.session_state.sezione_attiva != "fornitori":
                st.session_state.sezione_attiva = "fornitori"
                st.session_state.is_loading = True
                st.rerun()
    
    with col5:
        if st.button("🏢 SPESE\nGENERALI", key="btn_spese", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "spese" else "secondary"):
            if st.session_state.sezione_attiva != "spese":
                st.session_state.sezione_attiva = "spese"
                st.session_state.is_loading = True
                st.rerun()
    
    # CSS per bottoni colorati personalizzati
    st.markdown("""
        <style>
        div[data-testid="column"] button[kind="secondary"] {
            background-color: #f0f2f6 !important;
            color: #31333F !important;
            border: 2px solid #e0e0e0 !important;
        }
        div[data-testid="column"] button[kind="secondary"]:hover {
            background-color: #e0e5eb !important;
            border-color: #0ea5e9 !important;
        }
        div[data-testid="column"] button[kind="primary"] {
            background-color: #0ea5e9 !important;
            color: white !important;
            border: 2px solid #0284c7 !important;
            font-weight: bold !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Resetta il flag is_loading dopo il rerun
    if st.session_state.is_loading:
        st.session_state.is_loading = False
    
    # ========================================================
    # SEZIONE 1: DETTAGLIO ARTICOLI
    # ========================================================
    if st.session_state.sezione_attiva == "dettaglio":
        # Placeholder se dataset mancanti/vuoti
        if ('df_completo' not in locals()) or ('df_food' not in locals()) or ('df_spese_generali' not in locals()) or df_completo.empty:
            st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


        
        # 📦 SEZIONE DETTAGLIO ARTICOLI
        
        # Avviso salvataggio modifiche
        st.warning("⚠️ ATTENZIONE: Se hai modificato dati nella tabella, **clicca SALVA** prima di cambiare filtro, altrimenti le modifiche andranno perse!")
        
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
                key="salva_btn",
                help="Salva le modifiche manuali che hai fatto nella tabella (es. cambi categoria da 'SECCO' a 'VERDURE')"
            )
        
        # ✅ FILTRO DINAMICO IN BASE ALLA SELEZIONE
        if tipo_filtro == "Food & Beverage":
            # Solo F&B + NO FOOD, escludi spese generali
            df_base = df_completo[
                (~df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)) &
                (~df_completo['Fornitore'].str.upper().str.contains('|'.join(FORNITORI_NO_FOOD_KEYWORDS), na=False))
            ].copy()
        elif tipo_filtro == "Spese Generali":
            # Solo spese generali
            df_base = df_completo[
                df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
            ].copy()
        else:  # "Tutti"
            # Tutti i prodotti, escludi solo fornitori non-food
            df_base = df_completo[
                ~df_completo['Fornitore'].str.upper().str.contains('|'.join(FORNITORI_NO_FOOD_KEYWORDS), na=False)
            ].copy()
        
        # Applica struttura colonne nell'ordine corretto
        cols_base = ['FileOrigine', 'DataDocumento', 'Fornitore', 'Descrizione',
                    'Quantita', 'UnitaMisura', 'PrezzoUnitario', 'IVAPercentuale', 'TotaleRiga', 'Categoria']
        
        # Aggiungi prezzo_standard se esiste nel database
        if 'PrezzoStandard' in df_base.columns:
            cols_base.append('PrezzoStandard')
        
        df_editor = df_base[cols_base].copy()
        
        # 🔧 CONVERTI pd.NA/vuoti in "Da Classificare" (placeholder visibile per celle non categorizzate)
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
                print(f"📋 DEBUG CATEGORIA: {vuote_prima} vuote → {da_class_dopo} 'Da Classificare'")
        
        # Inizializza colonna prezzo_standard se non esiste
        if 'PrezzoStandard' not in df_editor.columns:
            df_editor['PrezzoStandard'] = None


        if search_term:
            if search_type == "Prodotto":
                mask = df_editor['Descrizione'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe con '{search_term}' nella descrizione")
            elif search_type == "Categoria":
                mask = df_editor['Categoria'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe nella categoria '{search_term}'")
            else:
                mask = df_editor['Fornitore'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe del fornitore '{search_term}'")
            
            df_editor = df_editor[mask]
        
        # ===== CALCOLO INTELLIGENTE PREZZO STANDARDIZZATO =====
        
        # Calcola prezzo_standard per ogni riga F&B
        for idx in df_editor.index:
            row = df_editor.loc[idx]
            
            # SKIP se già presente (manuale)
            prezzo_attuale = row.get('PrezzoStandard')
            if prezzo_attuale is not None and pd.notna(prezzo_attuale) and prezzo_attuale > 0:
                continue
            
            # Calcola intelligentemente
            prezzo_std = calcola_prezzo_standard_intelligente(
                descrizione=row.get('Descrizione'),
                um=row.get('UnitaMisura'),
                prezzo_unitario=row.get('PrezzoUnitario')
            )
            
            if prezzo_std is not None:
                df_editor.at[idx, 'PrezzoStandard'] = prezzo_std
        
        # ===== FINE CALCOLO =====
        
        st.info("""
🤖 **Calcolo Automatico Prezzo di Listino**  
L'app estrae automaticamente dalla descrizione e calcola il prezzo di Listino.  
✏️ Se il calcolo non è disponibile, puoi modificarlo manualmente nella colonna Listino.
        """)


        num_righe = len(df_editor)
        altezza_dinamica = min(max(num_righe * 35 + 50, 200), 500)

        # ===== CARICA CATEGORIE DINAMICHE =====
        categorie_disponibili = carica_categorie_da_db()
        
        # Rimuovi TUTTI i valori non validi (None, vuoti, solo spazi)
        categorie_disponibili = [
            cat for cat in categorie_disponibili 
            if cat is not None and str(cat).strip() != ''
        ]
        
        # Rimuovi duplicati mantenendo l'ordine
        categorie_temp = []
        for cat in categorie_disponibili:
            if cat not in categorie_temp:
                categorie_temp.append(cat)
        categorie_disponibili = categorie_temp
        
        # ⭐ AGGIUNGI "Da Classificare" come prima opzione (per celle non ancora categorizzate)
        # NON ordinare! carica_categorie_da_db() restituisce già l'ordine corretto:
        # 1. NOTE E DICITURE
        # 2. Spese generali (NO FOOD, MANUTENZIONE, ecc.)
        # 3. Prodotti alfabetici
        categorie_disponibili = ['Da Classificare'] + categorie_disponibili
        
        # ✅ "Da Classificare" è ora un'opzione valida - le celle non categorizzate la mostrano chiaramente
        
        # � FIX CELLE BIANCHE ULTRA-AGGRESSIVO (Streamlit bug workaround)
        # Se una cella ha un valore NON nelle opzioni, Streamlit la mostra VUOTA
        # FORZA che ogni categoria nel DataFrame sia nelle opzioni disponibili
        categorie_valide_set = set(categorie_disponibili)
        
        def valida_categoria(cat):
            """Assicura che categoria sia nelle opzioni disponibili"""
            if pd.isna(cat) or cat is None or str(cat).strip() == '':
                return 'Da Classificare'
            cat_str = str(cat).strip()
            if cat_str not in categorie_valide_set:
                logger.warning(f"⚠️ Categoria '{cat_str}' non nelle opzioni! → 'Da Classificare'")
                return 'Da Classificare'
            return cat_str
        
        # Applica validazione a TUTTE le categorie
        df_editor['Categoria'] = df_editor['Categoria'].apply(valida_categoria)
        
        # Log finale per debug
        invalid_count = (df_editor['Categoria'] == 'Da Classificare').sum()
        logger.info(f"📋 VALIDAZIONE: {invalid_count} celle con 'Da Classificare' (valide: {len(df_editor) - invalid_count})")
        print(f"📋 DEBUG: {invalid_count} 'Da Classificare', {len(df_editor) - invalid_count} categorizzate")
        
        # �🔒 FILTRA "NOTE E DICITURE" per utenti NON admin
        # Solo admin e impersonificati possono usare questa categoria
        is_admin_or_impersonating = (
            st.session_state.get('user_is_admin', False) or 
            st.session_state.get('impersonating', False)
        )
        
        if not is_admin_or_impersonating:
            # Rimuovi "NOTE E DICITURE" dalla lista disponibile per clienti
            categorie_disponibili = [
                cat for cat in categorie_disponibili 
                if 'NOTE E DICITURE' not in cat.upper() and 'DICITURE' not in cat.upper()
            ]
            logger.info("🔒 Categoria 'NOTE E DICITURE' nascosta per utente non-admin")
        
        # ⚡ ASSICURA che "Da Classificare" sia SEMPRE presente (anche dopo filtri)
        if 'Da Classificare' not in categorie_disponibili:
            categorie_disponibili = ['Da Classificare'] + categorie_disponibili
            logger.info("⚡ 'Da Classificare' ri-aggiunto dopo filtri")
        
        # ✅ Le categorie vengono normalizzate automaticamente al caricamento
        # Migrazione vecchi nomi → nuovi nomi avviene in carica_e_prepara_dataframe()

        edited_df = st.data_editor(
            df_editor,
            column_config={
                "DataDocumento": st.column_config.TextColumn("Data", disabled=True),
                "Categoria": st.column_config.SelectboxColumn(
                    "Categoria",
                    help="Seleziona la categoria corretta (le celle 'Da Classificare' devono essere categorizzate)",
                    width="medium",
                    options=categorie_disponibili,
                    required=False
                ),
                "TotaleRiga": st.column_config.NumberColumn("Totale (€)", format="€ %.2f", disabled=True),
                "PrezzoUnitario": st.column_config.NumberColumn("Prezzo Unit.", format="€ %.2f", disabled=True),
                "Descrizione": st.column_config.TextColumn("Descrizione", disabled=True),
                "Fornitore": st.column_config.TextColumn("Fornitore", disabled=True),
                "FileOrigine": st.column_config.TextColumn("File", disabled=True),
                "Quantita": st.column_config.NumberColumn("Q.tà", disabled=True),
                "UnitaMisura": st.column_config.TextColumn("U.M.", disabled=True, width="small"),
                "PrezzoStandard": st.column_config.NumberColumn(
                    "LISTINO",
                    help="Prezzo di listino standardizzato - calcolato automaticamente per confronti. Puoi modificarlo manualmente.",
                    format="€%.2f",
                    min_value=0.01,
                    max_value=10000,
                    step=0.01,
                    width="small"
                )
            },
            hide_index=True,
            use_container_width=True,
            height=altezza_dinamica,
            key="editor_dati"
        )
        
        st.markdown("""
            <style>
            [data-testid="stDownloadButton"] {
                margin-top: 10px !important;
            }
            [data-testid="stDownloadButton"] button {
                background-color: #28a745 !important;
                color: white !important;
                font-weight: 600 !important;
                font-size: 13px !important;
                border-radius: 6px !important;
                border: none !important;
                width: 140px !important;
                height: 38px !important;
                padding: 0 !important;
            }
            [data-testid="stDownloadButton"] button:hover {
                background-color: #218838 !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        totale_tabella = edited_df['TotaleRiga'].sum()
        num_righe = len(edited_df)
        
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown(genera_box_recap(num_righe, totale_tabella), unsafe_allow_html=True)
        
        with col_right:
            df_export = edited_df.copy()
            
            # 🧼 STEP 1: NORMALIZZA Unità di Misura (PRIMA di tutto)
            um_mapping = {
                # PESO
                'KG': 'KG', 'KG.': 'KG', 'Kg': 'KG', 'kg': 'KG',
                'KILOGRAMMI': 'KG', 'Kilogrammi': 'KG', 'kilogrammi': 'KG',
                'GR': 'GR', 'Gr': 'GR', 'gr': 'GR', 'GRAMMI': 'GR', 'Grammi': 'GR',
                # LITRI
                'LT': 'LT', 'Lt': 'LT', 'lt': 'LT', 'LT.': 'LT',
                'LITRI': 'LT', 'Litri': 'LT', 'litri': 'LT', 'LITRO': 'LT',
                'L': 'LT', 'l': 'LT',
                'ML': 'ML', 'ml': 'ML', 'MILLILITRI': 'ML',
                # PEZZI/NUMERO
                'PZ': 'PZ', 'Pz': 'PZ', 'pz': 'PZ',
                'NR': 'PZ', 'Nr': 'PZ', 'nr': 'PZ', 'NR.': 'PZ',
                'NUMERO': 'PZ', 'Numero': 'PZ', 'numero': 'PZ',
                'PEZZI': 'PZ', 'Pezzi': 'PZ', 'pezzi': 'PZ', 'PEZZO': 'PZ',
                # CONFEZIONI
                'CT': 'CT', 'Ct': 'CT', 'ct': 'CT', 'CARTONE': 'CT',
                # FUSTI
                'FS': 'FS', 'Fs': 'FS', 'fs': 'FS', 'FUSTO': 'FS',
            }
            
            if 'UnitaMisura' in df_export.columns:
                # Rimuovi spazi e normalizza
                df_export['UnitaMisura'] = df_export['UnitaMisura'].astype(str).str.strip()
                df_export['UnitaMisura'] = df_export['UnitaMisura'].map(lambda x: um_mapping.get(x, x))
            
            # 🧼 STEP 2: FILTRA righe informative (DDT, CASSA, BOLLO)
            righe_prima = len(df_export)
            df_export = df_export[
                (~df_export['Descrizione'].str.contains('DDT|DIT|BOLLO|CASSA', na=False, case=False)) &
                (df_export['TotaleRiga'] != 0)
            ]
            righe_dopo = len(df_export)
            righe_filtrate = righe_prima - righe_dopo
            
            if righe_filtrate > 0:
                logger.info(f"✅ Export: filtrate {righe_filtrate} righe informative (DDT/CASSA/BOLLO)")
            
            # 🧼 STEP 3: RICALCOLA Prezzo Standard (DOPO normalizzazione U.M.)
            if 'PrezzoStandard' in df_export.columns:
                df_export['PrezzoStandard'] = df_export.apply(
                    lambda row: calcola_prezzo_standard_intelligente(
                        row['Descrizione'],
                        row['UnitaMisura'],
                        row['PrezzoUnitario']
                    ),
                    axis=1
                )
                # Arrotonda a 4 decimali
                df_export['PrezzoStandard'] = df_export['PrezzoStandard'].round(4)
            
            # 🔧 FIX: Reset index prima di rinominare colonne (evita errore "Columns must be same length")
            df_export = df_export.reset_index(drop=True)
            
            # Prepara nomi colonne per export
            col_names = ['File', 'Data', 'Fornitore', 'Descrizione',
                        'Quantità', 'U.M.', 'Prezzo Unit.', 'IVA %', 'Totale (€)', 'Categoria']
            
            # Aggiungi prezzo_standard se presente
            if 'PrezzoStandard' in df_export.columns:
                col_names.append('LISTINO')
            
            # ✅ VERIFICA: Numero colonne deve corrispondere
            if len(df_export.columns) == len(col_names):
                df_export.columns = col_names
            else:
                logger.warning(f"⚠️ Mismatch colonne: DataFrame ha {len(df_export.columns)}, col_names ha {len(col_names)}")
                # Fallback sicuro: usa solo le colonne esistenti
                df_export.columns = col_names[:len(df_export.columns)]

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Articoli')
            
            st.download_button(
                label="📊 Excel",
                data=excel_buffer.getvalue(),
                file_name=f"dettaglio_articoli_FB_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_excel",
                type="primary",
                use_container_width=True,
                help="Scarica dettaglio articoli Food & Beverage"
            )


        if salva_modifiche:
            try:
                user_id = st.session_state.user_data["id"]
                user_email = st.session_state.user_data.get("email", "unknown")
                modifiche_effettuate = 0
                
                # ========================================
                # ✅ CHECK: Quale tabella stiamo modificando?
                # ========================================
                colonne_df = edited_df.columns.tolist()
                
                # Check flessibile per Editor Fatture (supporta nomi alternativi)
                ha_file = any(col in colonne_df for col in ['File', 'FileOrigine'])
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
                                logger.info(f"⏭️ SKIP: Categoria 'Da Classificare' non salvata per {descrizione[:30]}")
                                continue
                            
                            # Recupera categoria originale per tracciare correzione
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
                                except (ValueError, TypeError):
                                    pass
                            
                            # 🔄 MODIFICA BATCH: Se categoria è cambiata, aggiorna TUTTE le righe con stessa descrizione
                            if vecchia_cat and vecchia_cat != nuova_cat:
                                logger.info(f"🔄 BATCH UPDATE: '{descrizione}' {vecchia_cat} → {nuova_cat}")
                                
                                # Aggiorna tutte le righe con stessa descrizione (normalizzata)
                                result = supabase.table("fatture").update(update_data).eq(
                                    "user_id", user_id
                                ).eq(
                                    "descrizione", descrizione
                                ).execute()
                                
                                righe_aggiornate = len(result.data) if result.data else 0
                                logger.info(f"✅ BATCH: {righe_aggiornate} righe aggiornate per '{descrizione[:40]}'")
                                
                                # Aggiorna memoria AI
                                aggiorna_memoria_ai(descrizione, nuova_cat)
                                
                                # Salva correzione in memoria globale
                                salva_correzione_in_memoria_globale(
                                    descrizione=descrizione,
                                    vecchia_categoria=vecchia_cat,
                                    nuova_categoria=nuova_cat,
                                    user_email=user_email
                                )
                                
                                modifiche_effettuate += righe_aggiornate
                                
                            else:
                                # Aggiorna solo questa riga specifica (nessun cambio categoria)
                                result = supabase.table("fatture").update(update_data).eq(
                                    "user_id", user_id
                                ).eq(
                                    "file_origine", f_name
                                ).eq(
                                    "numero_riga", riga_idx
                                ).eq(
                                    "descrizione", descrizione
                                ).execute()
                                
                                if result.data:
                                    modifiche_effettuate += 1
                                
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


                if modifiche_effettuate > 0:
                    # Conta quanti prodotti saranno rimossi dalla vista (categorie spese generali)
                    prodotti_spostati = edited_df[edited_df['Categoria'].apply(
                        lambda cat: estrai_nome_categoria(cat) in CATEGORIE_SPESE_GENERALI
                    )].shape[0]
                    
                    if prodotti_spostati > 0:
                        st.toast(f"✅ Salvate {modifiche_effettuate} modifiche! {prodotti_spostati} prodotti spostati in Spese Generali.")
                    else:
                        st.toast(f"✅ Salvate {modifiche_effettuate} modifiche su Supabase! L'AI imparerà da questo.")
                    
                    time.sleep(1.5)
                    st.cache_data.clear()
                    invalida_cache_memoria()
                    st.session_state.force_reload = True  # ← Forza ricaricamento completo
                    st.rerun()
                elif (ha_file or ha_numero_riga) and ha_categoria and ha_descrizione:
                    # Solo se era davvero l'editor fatture
                    st.toast("⚠️ Nessuna modifica rilevata.")


            except Exception as e:
                logger.exception("Errore durante il salvataggio modifiche categorie")
                st.error(f"❌ Errore durante il salvataggio: {e}")
    
    # ========================================================
    # SEZIONE 2: ALERT AUMENTI PREZZI - VERSIONE SEMPLIFICATA
    # ========================================================
    if st.session_state.sezione_attiva == "alert":
        
        # Verifica dataset
        if ('df_completo' not in locals()) or df_completo.empty:
            st.warning("📊 Carica delle fatture per vedere gli alert.")
        else:
            
            # FILTRI
            col_search, col_soglia = st.columns([3, 1])
            
            with col_search:
                filtro_prodotto = st.text_input(
                    "🔍 Cerca Prodotto", 
                    "", 
                    placeholder="Digita per filtrare per nome prodotto...",
                    key="filtro_alert_prodotto"
                )
            
            with col_soglia:
                soglia_aumento = st.number_input(
                    "Soglia Aumento Minimo %", 
                    min_value=0, 
                    max_value=100, 
                    value=5,
                    step=1,
                    key="soglia_alert",
                    help="Mostra solo aumenti ≥ +X%"
                )
            
            # CALCOLA ALERT (SOLO F&B)
            df_alert = calcola_alert(df_completo, soglia_aumento, filtro_prodotto)
            
            # BADGE CONTEGGIO
            if not df_alert.empty:
                st.info(f"⚠️ **{len(df_alert)} Aumenti Rilevati** (soglia ≥ +{soglia_aumento}%) - Solo prodotti Food & Beverage")
                
                # Prepara colonne display
                df_display = df_alert.copy()
                df_display['Data'] = pd.to_datetime(df_display['Data']).dt.strftime('%d/%m/%y')
                df_display['Prezzo_Prec'] = df_display['Prezzo_Prec'].apply(lambda x: f"€{x:.2f}")
                df_display['Prezzo_Nuovo'] = df_display['Prezzo_Nuovo'].apply(lambda x: f"€{x:.2f}")
                
                # PALLINI COLORATI: 🔴 Aumento / 🟢 Diminuzione
                def formatta_variazione(perc):
                    if perc > 0:
                        return f"🔴 +{perc:.1f}%"
                    elif perc < 0:
                        return f"🟢 {perc:.1f}%"
                    else:
                        return f"{perc:.1f}%"
                
                df_display['Aumento_Perc'] = df_display['Aumento_Perc'].apply(formatta_variazione)
                
                # 🔧 FIX: Reset index prima di rinominare
                df_display = df_display.reset_index(drop=True)
                
                # Rinomina colonne per display (NO EMOJI)
                df_display.columns = ['Prodotto', 'Cat.', 'Fornitore', 'Data', 'Prec.', 'Nuovo', 'Variazione', 'N.Fattura']
                
                # ============================================================
                # ALTEZZA SCROLLABILE (min 200px, max 500px)
                # ============================================================
                num_righe_alert = len(df_display)
                altezza_alert = min(max(num_righe_alert * 35 + 50, 200), 500)
                
                # Mostra tabella SCROLLABILE
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    height=altezza_alert,  # MAX 500px con scroll
                    hide_index=True
                )
                
                # CSS per bottone Excel
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                # EXPORT EXCEL
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_alert.to_excel(writer, sheet_name='Alert Aumenti', index=False)
                
                col_spacer, col_btn = st.columns([4, 2])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer.getvalue(),
                        file_name=f"alert_aumenti_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_alert",
                        type="primary",
                        use_container_width=False
                    )
            else:
                st.success(f"✅ Nessun aumento rilevato con soglia ≥ +{soglia_aumento}%. Tutto sotto controllo!")
            
            st.markdown("---")
            
            # ============================================================
            # NUOVA SEZIONE: SCONTI E OMAGGI
            # ============================================================
            st.markdown("### 🎁 Sconti e Omaggi Ricevuti")
            
            # Caption dinamica con periodo (usa label_periodo già calcolato sopra)
            st.caption(f"{label_periodo} - Solo prodotti Food & Beverage")
            
            # Carica dati CON PERIODO DINAMICO
            with st.spinner("Caricamento sconti e omaggi..."):
                dati_sconti = carica_sconti_e_omaggi(user_id, data_inizio_filtro, data_fine_filtro)
            
            df_sconti = dati_sconti['sconti']
            df_omaggi = dati_sconti['omaggi']
            totale_risparmiato = dati_sconti['totale_risparmiato']
            
            # ============================================================
            # METRICHE COMPATTE (STESSA ALTEZZA - HTML) - NO EMOJI
            # ============================================================
            col_metric1, col_metric2, col_metric3 = st.columns(3)
            
            with col_metric1:
                st.markdown("""
                <div style="
                    background-color: #fff5f0;
                    border-left: 4px solid #dc3545;
                    padding: 15px;
                    border-radius: 5px;
                    height: 110px;
                ">
                    <div style="font-size: 14px; color: #666;">Sconti Applicati</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0;">{} righe</div>
                    <div style="font-size: 16px; color: #dc3545;">-€{:.2f}</div>
                </div>
                """.format(len(df_sconti), totale_risparmiato if totale_risparmiato > 0 else 0), 
                unsafe_allow_html=True)
            
            with col_metric2:
                st.markdown("""
                <div style="
                    background-color: #f0f8ff;
                    border-left: 4px solid #0d6efd;
                    padding: 15px;
                    border-radius: 5px;
                    height: 110px;
                ">
                    <div style="font-size: 14px; color: #666;">Omaggi Ricevuti</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0;">{} righe</div>
                    <div style="font-size: 16px; color: #999;">Prodotti gratuiti</div>
                </div>
                """.format(len(df_omaggi)), 
                unsafe_allow_html=True)
            
            with col_metric3:
                st.markdown("""
                <div style="
                    background-color: #f0fff0;
                    border-left: 4px solid #28a745;
                    padding: 15px;
                    border-radius: 5px;
                    height: 110px;
                ">
                    <div style="font-size: 14px; color: #666;">Totale Risparmiato</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0; color: #28a745;">€{:.2f}</div>
                    <div style="font-size: 16px; color: #999;">{}</div>
                </div>
                """.format(totale_risparmiato if totale_risparmiato > 0 else 0, label_periodo), 
                unsafe_allow_html=True)
            
            # ============================================================
            # SPACING EXTRA (3 righe vuote)
            # ============================================================
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            
            # ============================================================
            # TABELLA SCONTI COMPLETA (SOLO F&B)
            # ============================================================
            if not df_sconti.empty:
                with st.expander("💸 Dettaglio Sconti Applicati", expanded=True):
                    st.markdown(f"**{len(df_sconti)} sconti** ricevuti dai fornitori")
                    st.caption("Solo prodotti Food & Beverage - Escluse spese generali")
                    
                    # Prepara dati completi (come tabella alert sopra)
                    df_sconti_view = df_sconti[[
                        'descrizione',
                        'categoria',
                        'fornitore',
                        'importo_sconto',
                        'data_documento',
                        'file_origine'
                    ]].copy()
                    
                    # 🔧 FIX: Reset index prima di rinominare
                    df_sconti_view = df_sconti_view.reset_index(drop=True)
                    
                    df_sconti_view.columns = [
                        'Prodotto',
                        'Categoria',
                        'Fornitore',
                        'Sconto',
                        'Data',
                        'Fattura'
                    ]
                    
                    # Altezza dinamica scrollabile
                    num_righe_sconti = len(df_sconti_view)
                    altezza_sconti = min(max(num_righe_sconti * 35 + 50, 200), 500)
                    
                    st.dataframe(
                        df_sconti_view,
                        hide_index=True,
                        use_container_width=True,
                        height=altezza_sconti,
                        column_config={
                            'Prodotto': st.column_config.TextColumn(
                                'Prodotto',
                                width="large"
                            ),
                            'Categoria': st.column_config.TextColumn(
                                'Categoria',
                                width="medium"
                            ),
                            'Fornitore': st.column_config.TextColumn(
                                'Fornitore',
                                width="medium"
                            ),
                            'Sconto': st.column_config.NumberColumn(
                                'Sconto',
                                format="€%.2f",
                                help="Importo sconto ricevuto"
                            ),
                            'Data': st.column_config.DateColumn(
                                'Data',
                                format="DD/MM/YYYY"
                            ),
                            'Fattura': st.column_config.TextColumn(
                                'Fattura',
                                width="medium"
                            )
                        }
                    )
            
            else:
                st.info(f"📊 Nessuno sconto applicato nel periodo {label_periodo.lower()}")
            
            # ============================================================
            # TABELLA OMAGGI
            # ============================================================
            if not df_omaggi.empty:
                with st.expander(f"🎁 Dettaglio Omaggi ({len(df_omaggi)})", expanded=False):
                    st.markdown(f"**{len(df_omaggi)} omaggi** ricevuti dai fornitori")
                    st.caption("Solo prodotti Food & Beverage - Escluse spese generali")
                    
                    df_omaggi_view = df_omaggi[[
                        'descrizione',
                        'fornitore',
                        'quantita',
                        'data_documento',
                        'file_origine'
                    ]].copy()
                    
                    # 🔧 FIX: Reset index prima di rinominare
                    df_omaggi_view = df_omaggi_view.reset_index(drop=True)
                    
                    df_omaggi_view.columns = [
                        'Prodotto',
                        'Fornitore',
                        'Quantità',
                        'Data',
                        'Fattura'
                    ]
                    
                    # Altezza dinamica scrollabile
                    num_righe_omaggi = len(df_omaggi_view)
                    altezza_omaggi = min(max(num_righe_omaggi * 35 + 50, 200), 500)
                    
                    st.dataframe(
                        df_omaggi_view,
                        hide_index=True,
                        use_container_width=True,
                        height=altezza_omaggi,
                        column_config={
                            'Data': st.column_config.DateColumn(
                                'Data',
                                format="DD/MM/YYYY"
                            )
                        }
                    )
                    
                    st.info("ℹ️ Gli omaggi sono prodotti con prezzo €0 (escluse diciture e note)")
            
            # ============================================================
            # INFO SE NESSUN DATO + DEBUG
            # ============================================================
            if df_sconti.empty and df_omaggi.empty:
                st.info(f"📊 Nessuno sconto o omaggio ricevuto nel periodo {label_periodo.lower()}")
                
                # Mostra statistiche utili per debug (solo admin/impersonificato)
                if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
                    with st.expander("🔍 Info Debug", expanded=False):
                        try:
                            # Ricarica dati per debug con stesso periodo
                            if hasattr(data_inizio_filtro, 'isoformat'):
                                data_inizio_str = data_inizio_filtro.isoformat()
                            else:
                                data_inizio_str = str(data_inizio_filtro)
                            
                            debug_response = supabase.table('fatture')\
                                .select('id, descrizione, categoria, prezzo_unitario')\
                                .eq('user_id', user_id)\
                                .gte('data_documento', data_limite)\
                                .execute()
                            
                            if debug_response.data:
                                df_debug = pd.DataFrame(debug_response.data)
                                st.write(f"📄 Righe totali caricate: {len(df_debug)}")
                                st.write(f"💸 Righe con prezzo <0: {len(df_debug[df_debug['prezzo_unitario'] < 0])}")
                                st.write(f"🎁 Righe con prezzo =0: {len(df_debug[df_debug['prezzo_unitario'] == 0])}")
                                
                                # Mostra categorie presenti
                                st.write("🏷️ Categorie presenti:", sorted(df_debug['categoria'].unique().tolist()))
                                
                                # Mostra sample prezzi negativi
                                if len(df_debug[df_debug['prezzo_unitario'] < 0]) > 0:
                                    st.markdown("**Sample prezzi negativi:**")
                                    st.dataframe(
                                        df_debug[df_debug['prezzo_unitario'] < 0][['descrizione', 'categoria', 'prezzo_unitario']].head(5),
                                        hide_index=True
                                    )
                            else:
                                st.warning("⚠️ Nessun dato nel periodo")
                        except Exception as e:
                            st.error(f"❌ Errore debug: {e}")
                
# ========================================================
    # ========================================================
    # SEZIONE 3: CATEGORIE
    # ========================================================
    if st.session_state.sezione_attiva == "categorie":
        # Placeholder se dataset mancanti/vuoti
        if ('df_food' not in locals()) or df_food.empty:
            st.info("📊 Nessun dato disponibile per i fornitori.")
        
        pivot_cat = crea_pivot_mensile(df_food, "Categoria")
        
        if not pivot_cat.empty:
            num_righe_cat = len(pivot_cat)
            altezza_cat = max(num_righe_cat * 35 + 50, 200)
            
            st.dataframe(
                pivot_cat,
                hide_index=True,
                use_container_width=True,
                height=altezza_cat,
                column_config={
                    "TOTALE ANNO": st.column_config.NumberColumn(format="€ %.2f")
                }
            )
            
            totale_cat = pivot_cat['TOTALE ANNO'].sum()
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.markdown(genera_box_recap(num_righe_cat, totale_cat), unsafe_allow_html=True)
            
            with col_right:
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_cat = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_cat, engine='openpyxl') as writer:
                    pivot_cat.to_excel(writer, index=False, sheet_name='Categorie')
                
                col_spacer, col_btn = st.columns([4, 2])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer_cat.getvalue(),
                        file_name=f"categorie_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_categorie",
                        type="primary",
                        use_container_width=False
                    )
            
            # GRAFICO SPESA PER CATEGORIA
            st.markdown("---")
            st.subheader("📊 Spesa per Categoria")
            spesa_cat = (
                df_food.groupby("Categoria")["TotaleRiga"]
                  .sum()
                  .reset_index()
                  .sort_values("TotaleRiga", ascending=False)
            )

            fig1 = px.bar(
                spesa_cat,
                x="Categoria",
                y="TotaleRiga",
                text="TotaleRiga",
                color="Categoria",
                color_discrete_sequence=COLORI_PLOTLY,
            )

            fig1.update_traces(
                texttemplate="€ %{text:.2f}",
                textposition="outside",
                textfont_size=18,
                hovertemplate="<b>%{x}</b><br>Spesa: € %{y:.2f}<extra></extra>",
            )

            fig1.update_layout(
                font=dict(size=20),
                xaxis_title="Categoria",
                yaxis_title="Spesa (€)",
                yaxis_title_font=dict(size=24, color="#333"),
                xaxis=dict(tickfont=dict(size=1), showticklabels=False),
                yaxis=dict(tickfont=dict(size=18)),
                showlegend=False,
                height=600,
                hoverlabel=dict(bgcolor="white", font_size=16, font_family="Arial"),
            )

            st.plotly_chart(
                fig1,
                use_container_width=True,
                key="grafico_categorie_tab",
                config={"displayModeBar": False},
            )
        else:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")

    # ======================================================
    # ========================================================
    # SEZIONE 4: FORNITORI
    # ========================================================
    if st.session_state.sezione_attiva == "fornitori":
        # Placeholder se dataset mancanti/vuoti
        if ('df_food' not in locals()) or df_food.empty:
            st.info("📊 Nessun dato disponibile per i fornitori.")
        
        pivot_forn = crea_pivot_mensile(df_food, "Fornitore")
        
        if not pivot_forn.empty:
            num_righe_forn = len(pivot_forn)
            altezza_forn = max(num_righe_forn * 35 + 50, 200)
            
            st.dataframe(
                pivot_forn,
                hide_index=True,
                use_container_width=True,
                height=altezza_forn,
                column_config={
                    "TOTALE ANNO": st.column_config.NumberColumn(format="€ %.2f")
                }
            )
            
            totale_forn = pivot_forn['TOTALE ANNO'].sum()
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.markdown(genera_box_recap(num_righe_forn, totale_forn), unsafe_allow_html=True)
            
            with col_right:
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_forn = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_forn, engine='openpyxl') as writer:
                    pivot_forn.to_excel(writer, index=False, sheet_name='Fornitori')
                
                col_spacer, col_btn = st.columns([4, 2])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer_forn.getvalue(),
                        file_name=f"fornitori_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_fornitori",
                        type="primary",
                        use_container_width=False
                    )
            
            # GRAFICO SPESA PER FORNITORE
            st.markdown("---")
            st.subheader("🏪 Spesa per Fornitore")
            spesa_forn = (
                df_food.groupby("Fornitore")["TotaleRiga"]
                  .sum()
                  .reset_index()
                  .sort_values("TotaleRiga", ascending=False)
            )

            fig2 = px.bar(
                spesa_forn,
                x="Fornitore",
                y="TotaleRiga",
                text="TotaleRiga",
                color="Fornitore",
                color_discrete_sequence=COLORI_PLOTLY,
            )

            fig2.update_traces(
                texttemplate="€ %{text:.2f}",
                textposition="outside",
                textfont_size=18,
                hovertemplate="<b>%{x}</b><br>Spesa: € %{y:.2f}<extra></extra>",
            )

            fig2.update_layout(
                font=dict(size=20),
                xaxis_title="Fornitore",
                yaxis_title="Spesa (€)",
                yaxis_title_font=dict(size=24, color="#333"),
                xaxis=dict(tickfont=dict(size=1), showticklabels=False),
                yaxis=dict(tickfont=dict(size=18)),
                showlegend=False,
                height=600,
                hoverlabel=dict(bgcolor="white", font_size=16, font_family="Arial"),
            )

            st.plotly_chart(
                fig2,
                use_container_width=True,
                key="grafico_fornitori_tab",
                config={"displayModeBar": False},
            )
        else:
            st.warning("⚠️ Nessun dato disponibile per il periodo selezionato")


    # ========================================================
    # ========================================================
    # SEZIONE 5: SPESE GENERALI
    # ========================================================
    if st.session_state.sezione_attiva == "spese":
        if df_spese_generali.empty:
            st.info("📊 Nessuna spesa generale nel periodo selezionato")
        else:
            # ============================================
            # TABELLA 1: CATEGORIE × MESI
            # ============================================
            st.markdown("#### 📊 Spesa per Categoria per Mese")
            
            # Aggiungi colonna Mese
            df_spese_con_mese = df_spese_generali.copy()
            df_spese_con_mese['Mese'] = pd.to_datetime(df_spese_con_mese['DataDocumento']).dt.to_period('M').astype(str)
            
            # Pivot: Categorie × Mesi
            pivot_cat = df_spese_con_mese.pivot_table(
                index='Categoria',
                columns='Mese',
                values='TotaleRiga',
                aggfunc='sum',
                fill_value=0
            )
            
            # Aggiungi colonna TOTALE
            pivot_cat['TOTALE'] = pivot_cat.sum(axis=1)
            
            # Ordina per totale decrescente
            pivot_cat = pivot_cat.sort_values('TOTALE', ascending=False)
            
            # Formatta come €
            pivot_cat_display = pivot_cat.map(lambda x: f"€ {x:,.2f}")
            
            num_righe_spese_cat = len(pivot_cat_display)
            altezza_spese_cat = max(num_righe_spese_cat * 35 + 50, 200)
            st.dataframe(pivot_cat_display, use_container_width=True, height=altezza_spese_cat)
            
            st.markdown("---")
            
            # ============================================
            # TABELLA 2: FORNITORI × MESI
            # ============================================
            st.markdown("#### 🏪 Spesa per Fornitore per Mese")
            
            # Pivot: Fornitori × Mesi
            pivot_forn = df_spese_con_mese.pivot_table(
                index='Fornitore',
                columns='Mese',
                values='TotaleRiga',
                aggfunc='sum',
                fill_value=0
            )
            
            # Aggiungi colonna TOTALE
            pivot_forn['TOTALE'] = pivot_forn.sum(axis=1)
            
            # Ordina per totale decrescente
            pivot_forn = pivot_forn.sort_values('TOTALE', ascending=False)
            
            # Formatta come €
            pivot_forn_display = pivot_forn.map(lambda x: f"€ {x:,.2f}")
            
            num_righe_spese_forn = len(pivot_forn_display)
            altezza_spese_forn = max(num_righe_spese_forn * 35 + 50, 200)
            st.dataframe(pivot_forn_display, use_container_width=True, height=altezza_spese_forn)
            
            st.markdown("---")
            
            # ============================================
            # GRAFICI SPESE GENERALI AFFIANCATI
            # ============================================
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("📊 Spesa per Categoria")
                # Prepara dati per grafico (usa colonna TOTALE)
                spesa_cat_grafico = pivot_cat.reset_index()
                spesa_cat_grafico = spesa_cat_grafico[['Categoria', 'TOTALE']].sort_values('TOTALE', ascending=False)
                
                fig_categoria_generale = px.bar(
                    spesa_cat_grafico,
                    x='Categoria',
                    y='TOTALE',
                    text='TOTALE',
                    color='Categoria',
                    color_discrete_sequence=COLORI_PLOTLY,
                )
                
                fig_categoria_generale.update_traces(
                    texttemplate='€ %{text:.2f}',
                    textposition='outside',
                    textfont_size=18,
                    hovertemplate='<b>%{x}</b><br>Spesa: € %{y:.2f}<extra></extra>',
                )
                
                fig_categoria_generale.update_layout(
                    font=dict(size=20),
                    xaxis_title='Categoria',
                    yaxis_title='Spesa (€)',
                    yaxis_title_font=dict(size=24, color='#333'),
                    xaxis=dict(tickfont=dict(size=1), showticklabels=False),
                    yaxis=dict(tickfont=dict(size=18)),
                    showlegend=False,
                    height=600,
                    hoverlabel=dict(bgcolor='white', font_size=16, font_family='Arial'),
                )
                
                st.plotly_chart(
                    fig_categoria_generale,
                    use_container_width=True,
                    key='grafico_categorie_spese_generali',
                    config={'displayModeBar': False},
                )
            
            with col_chart2:
                st.subheader("🏪 Spesa per Fornitore")
                # Prepara dati per grafico (usa colonna TOTALE)
                spesa_forn_grafico = pivot_forn.reset_index()
                spesa_forn_grafico = spesa_forn_grafico[['Fornitore', 'TOTALE']].sort_values('TOTALE', ascending=False)
                
                fig_fornitore_generale = px.bar(
                    spesa_forn_grafico,
                    x='Fornitore',
                    y='TOTALE',
                    text='TOTALE',
                    color='Fornitore',
                    color_discrete_sequence=COLORI_PLOTLY,
                )
                
                fig_fornitore_generale.update_traces(
                    texttemplate='€ %{text:.2f}',
                    textposition='outside',
                    textfont_size=18,
                    hovertemplate='<b>%{x}</b><br>Spesa: € %{y:.2f}<extra></extra>',
                )
                
                fig_fornitore_generale.update_layout(
                    font=dict(size=20),
                    xaxis_title='Fornitore',
                    yaxis_title='Spesa (€)',
                    yaxis_title_font=dict(size=24, color='#333'),
                    xaxis=dict(tickfont=dict(size=1), showticklabels=False),
                    yaxis=dict(tickfont=dict(size=18)),
                    showlegend=False,
                    height=600,
                    hoverlabel=dict(bgcolor='white', font_size=16, font_family='Arial'),
                )
                
                st.plotly_chart(
                    fig_fornitore_generale,
                    use_container_width=True,
                    key='grafico_fornitori_spese_generali',
                    config={'displayModeBar': False},
                )
            
            st.markdown("---")
            
            # ============================================
            # BOX RIEPILOGATIVO + EXCEL EXPORT
            # ============================================
            totale_spese_generali = df_spese_generali['TotaleRiga'].sum()
            num_righe_spese = len(df_spese_generali)
            
            col_recap, col_excel = st.columns([3, 1])
            
            with col_recap:
                st.markdown(genera_box_recap(num_righe_spese, totale_spese_generali), unsafe_allow_html=True)
            
            with col_excel:
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] {
                        margin-top: 10px !important;
                    }
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        font-size: 13px !important;
                        border-radius: 6px !important;
                        border: none !important;
                        width: 140px !important;
                        height: 38px !important;
                        padding: 0 !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                # Prepara Excel con entrambe le tabelle
                excel_buffer_spese = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_spese, engine='openpyxl') as writer:
                    pivot_cat.to_excel(writer, sheet_name='Per Categoria')
                    pivot_forn.to_excel(writer, sheet_name='Per Fornitore')
                
                col_spacer, col_btn = st.columns([3, 3])
                with col_btn:
                    st.download_button(
                        label="📊 Excel",
                        data=excel_buffer_spese.getvalue(),
                        file_name=f"spese_generali_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_spese",
                        type="primary",
                        use_container_width=False
                    )

# ============================================================
# STILI CSS (COMPLETI)
# ============================================================



st.markdown("""
    <style>
    [data-testid="stTab"] {
        font-size: 20px !important;
        font-weight: bold !important;
        text-transform: uppercase !important;
        padding: 15px 30px !important;
    }
    
    [data-testid="stFileUploader"] > div > div:not(:first-child) { display: none !important; }
    [data-testid="stFileUploader"] ul { display: none !important; }
    [data-testid="stFileUploader"] button[kind="icon"] { display: none !important; }
    [data-testid="stFileUploader"] small { display: none !important; }
    [data-testid="stFileUploader"] svg { display: none !important; }
    [data-testid="stFileUploader"] section > div > span { display: none !important; }
    [data-testid="stFileUploader"] section > div:last-child { display: none !important; }
    
    [data-testid="stFileUploader"] { margin: 20px 0; }
    [data-testid="stFileUploader"] > div { width: 100%; max-width: 700px; }
    [data-testid="stFileUploader"] section {
        padding: 50px 80px !important;
        border: 5px dashed #4CAF50 !important;
        border-radius: 25px !important;
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%) !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 6px 12px rgba(0,0,0,0.1) !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #2E7D32 !important;
        background: linear-gradient(135deg, #c8e6c9 0%, #a5d6a7 100%) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 20px rgba(0,0,0,0.15) !important;
    }
    [data-testid="stFileUploader"] label {
        font-size: 32px !important;
        font-weight: bold !important;
        color: #1b5e20 !important;
        letter-spacing: 1px !important;
        text-transform: uppercase !important;
    }
    [data-testid="stFileUploader"] button {
        padding: 15px 40px !important;
        font-size: 18px !important;
        font-weight: bold !important;
        background-color: #4CAF50 !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploader"] button:hover {
        background-color: #45a049 !important;
        transform: scale(1.05) !important;
    }
    
    .file-status-table {
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        background-color: #fafafa;
    }
    .file-status-table table { width: 100%; border-collapse: collapse; }
    .file-status-table th {
        background-color: #f0f0f0;
        padding: 15px 10px !important;
        text-align: left;
        position: sticky;
        top: 0;
        z-index: 10;
        font-size: 18px !important;
        font-weight: bold !important;
    }
    .file-status-table td {
        padding: 12px 10px !important;
        border-bottom: 1px solid #eee;
        font-size: 16px !important;
    }
    
    [data-testid="stMetricValue"] > div { font-size: 48px !important; font-weight: bold !important; }
    [data-testid="stMetricLabel"] > div { font-size: 22px !important; font-weight: 600 !important; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #f0f4f8 0%, #e1e8ed 100%) !important;
        border: 4px solid #cbd5e0 !important;
        border-radius: 20px !important;
        padding: 30px 20px !important;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15) !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-8px) !important;
        box-shadow: 0 12px 24px rgba(0,0,0,0.2) !important;
    }
    
    [data-testid="column"]:nth-child(1) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%) !important;
        border-color: #2196f3 !important;
    }
    [data-testid="column"]:nth-child(1) [data-testid="stMetricValue"] { color: #1565c0 !important; }
    [data-testid="column"]:nth-child(1) [data-testid="stMetricLabel"] { color: #1976d2 !important; }
    [data-testid="column"]:nth-child(2) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%) !important;
        border-color: #4caf50 !important;
    }
    [data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] { color: #2e7d32 !important; }
    [data-testid="column"]:nth-child(2) [data-testid="stMetricLabel"] { color: #388e3c !important; }
    [data-testid="column"]:nth-child(3) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%) !important;
        border-color: #ff9800 !important;
    }
    [data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] { color: #e65100 !important; }
    [data-testid="column"]:nth-child(3) [data-testid="stMetricLabel"] { color: #f57c00 !important; }
    [data-testid="column"]:nth-child(4) [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%) !important;
        border-color: #f44336 !important;
    }
    [data-testid="column"]:nth-child(4) [data-testid="stMetricValue"] { color: #c62828 !important; }
    [data-testid="column"]:nth-child(4) [data-testid="stMetricLabel"] { color: #d32f2f !important; }
            
    #MainMenu { visibility: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)


# ============================================================
# INTERFACCIA PRINCIPALE CON CACHING OTTIMIZZATO
# ============================================================


if 'timestamp_ultimo_caricamento' not in st.session_state:
    st.session_state.timestamp_ultimo_caricamento = time.time()


# 🔒 IMPORTANTE: user_id per cache isolata (multi-tenancy)
user_id = st.session_state.user_data["id"]


with st.spinner("⏳ Caricamento dati..."):
    df_cache = carica_e_prepara_dataframe(user_id)


# 🗂️ GESTIONE FATTURE - Eliminazione (prima del file uploader)
if not df_cache.empty:
    with st.expander("🗂️ Gestione Fatture Caricate (Elimina)", expanded=False):
        
        # ========================================
        # BOX STATISTICHE
        # ========================================
        stats_db = get_fatture_stats(user_id)
        st.markdown(f"""
<div style="
    background: linear-gradient(135deg, rgba(255, 140, 0, 0.15) 0%, rgba(255, 165, 0, 0.20) 100%);
    padding: 14px 22px;
    border-radius: 10px;
    border-left: 5px solid rgba(255, 107, 0, 0.6);
    box-shadow: 0 3px 6px rgba(255, 140, 0, 0.15);
    margin: 0 0 20px 0;
    display: inline-block;
    min-width: 400px;
    backdrop-filter: blur(10px);
">
    <span style="color: #FF6B00; font-size: 1.05em; font-weight: 700;">
        📊 Fatture: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_uniche"]:,}</strong> | 
        📋 Righe Totali: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_righe"]:,}</strong>
    </span>
</div>
""", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("**Fatture nel tuo account:**")
        
        # Raggruppa per file origine per creare summary
        fatture_summary = df_cache.groupby('FileOrigine').agg({
            'Fornitore': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],
            'TotaleRiga': 'sum',
            'NumeroRiga': 'count',
            'DataDocumento': 'first'
        }).reset_index()
        
        # 🔧 FIX: Reset index prima di rinominare (già fatto ma assicuriamo drop=True)
        fatture_summary = fatture_summary.reset_index(drop=True)
        
        fatture_summary.columns = ['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data']
        fatture_summary = fatture_summary.sort_values('Data', ascending=False)
        
        # 🔍 DEBUG TOOL: Rimosso - Usa Upload Events in Admin Panel per diagnostica
        
        # 🗑️ PULSANTE SVUOTA TUTTO CON CONFERMA INLINE
        st.markdown("### 🗑️ Eliminazione Massiva")
        
        col_check, col_btn = st.columns([3, 1])
        
        with col_check:
            conferma_check = st.checkbox(
                "⚠️ **Confermo di voler eliminare TUTTE le fatture**",
                key="check_conferma_svuota",
                help="Questa azione è irreversibile"
            )
        
        with col_btn:
            if st.button(
                "🗑️ ELIMINA TUTTO", 
                type="primary" if conferma_check else "secondary",
                disabled=not conferma_check,
                use_container_width=True,
                key="btn_svuota_definitivo"
            ):
                with st.spinner("🗑️ Eliminazione in corso..."):
                    # Progress bar per UX
                    progress = st.progress(0)
                    progress.progress(20, text="Eliminazione da Supabase...")
                    
                    result = elimina_tutte_fatture(user_id)
                    
                    # 🔥 INVALIDAZIONE CACHE: Forza reload dati dopo eliminazione
                    invalida_cache_memoria()  # Reset memoria AI
                    st.cache_data.clear()  # Reset cache Streamlit
                    
                    # 🔥 RESET SESSION: Pulisci lista file processati
                    if 'files_processati_sessione' in st.session_state:
                        st.session_state.files_processati_sessione.clear()
                    if 'files_con_errori' in st.session_state:
                        st.session_state.files_con_errori.clear()
                    
                    progress.progress(40, text="Pulizia file JSON locali...")
                    
                    # HARD RESET: Elimina file JSON obsoleti
                    json_files = ['fattureprocessate.json', 'fatture.json', 'data.json']
                    for json_file in json_files:
                        if os.path.exists(json_file):
                            try:
                                os.remove(json_file)
                                logger.info(f"🗑️ Rimosso file JSON obsoleto: {json_file}")
                            except Exception as e:
                                logger.warning(f"⚠️ Impossibile rimuovere {json_file}: {e}")
                    
                    progress.progress(60, text="Pulizia cache Streamlit...")
                    
                    # HARD RESET: Pulisci TUTTE le cache
                    st.cache_data.clear()
                    try:
                        st.cache_resource.clear()
                    except:
                        pass
                    
                    progress.progress(80, text="Reset session state...")
                    
                    # HARD RESET: Rimuovi session state specifici (mantieni login)
                    keys_to_remove = [k for k in st.session_state.keys() 
                                     if k not in ['user_data', 'logged_in', 'check_conferma_svuota']]
                    for key in keys_to_remove:
                        try:
                            del st.session_state[key]
                        except:
                            pass
                    
                    progress.progress(100, text="Completato!")
                    time.sleep(0.3)
                    
                    # Mostra risultato DENTRO lo spinner (indentazione corretta)
                    if result["success"]:
                        st.success(f"✅ **{result['fatture_eliminate']} fatture** eliminate! ({result['righe_eliminate']} prodotti)")
                        st.info("🧹 **Hard Reset completato**: Cache, JSON locali e session state puliti")
                        
                        # LOG AUDIT: Verifica immediata post-delete
                        try:
                            verify = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id).execute()
                            num_residue = len(verify.data) if verify.data else 0
                            if num_residue == 0:
                                logger.info(f"✅ DELETE VERIFIED: 0 righe rimaste per user_id={user_id}")
                                st.success(f"✅ Verifica: Database pulito (0 righe)")
                            else:
                                logger.error(f"⚠️ DELETE INCOMPLETE: {num_residue} righe ancora presenti per user_id={user_id}")
                                st.error(f"⚠️ Attenzione: {num_residue} righe ancora presenti (possibile problema RLS)")
                        except Exception as e:
                            logger.exception("Errore verifica post-delete")
                        
                        # Reset checkbox prima del rerun
                        if 'check_conferma_svuota' in st.session_state:
                            del st.session_state.check_conferma_svuota
                        
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(f"❌ Errore: {result['error']}")
        
        st.markdown("---")
        
        # ========== ELIMINA SINGOLA FATTURA ==========
        st.markdown("### 🗑️ Elimina Fattura Singola")
        st.caption("Seleziona una fattura specifica per eliminarla usando il menu a tendina.")
        
        # Usa fatture_summary già creato sopra
        if len(fatture_summary) > 0:
            # Crea opzioni dropdown con dict per passare tutti i dati
            fatture_options = []
            for idx, row in fatture_summary.iterrows():
                fatture_options.append({
                    'File': row['File'],
                    'Fornitore': row['Fornitore'],
                    'NumProdotti': int(row['NumProdotti']),
                    'Totale': row['Totale']
                })
            
            fattura_selezionata = st.selectbox(
                "Seleziona fattura da eliminare:",
                options=fatture_options,
                format_func=lambda x: f"📄 {x['File']} - {x['Fornitore']} (📦 {x['NumProdotti']} prodotti, 💰 €{x['Totale']:.2f})",
                key="select_fattura_elimina"
            )
            
            col_btn, col_spacer = st.columns([1, 3])
            with col_btn:
                if st.button("🗑️ Elimina Fattura", type="secondary", use_container_width=True):
                    with st.spinner(f"🗑️ Eliminazione in corso..."):
                        result = elimina_fattura_completa(fattura_selezionata['File'], user_id)
                        
                        # 🔥 INVALIDAZIONE CACHE: Forza reload dati dopo eliminazione
                        invalida_cache_memoria()  # Reset memoria AI
                        st.cache_data.clear()  # Reset cache Streamlit
                        
                        # 🔥 RESET SESSION: Rimuovi file eliminato dalla lista processati
                        if 'files_processati_sessione' in st.session_state:
                            st.session_state.files_processati_sessione.discard(fattura_selezionata['File'])
                        
                        if result["success"]:
                            st.success(f"✅ Fattura **{fattura_selezionata['File']}** eliminata! ({result['righe_eliminate']} prodotti)")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Errore: {result['error']}")
        else:
            st.info("🔭 Nessuna fattura da eliminare.")
        
        st.caption("⚠️ L'eliminazione è immediata e irreversibile")


# File uploader sempre visibile (solo Supabase, no JSON)
uploaded_files = st.file_uploader(
    "Carica file XML, PDF o Immagini", 
    accept_multiple_files=True, 
    type=['xml', 'pdf', 'jpg', 'jpeg', 'png'], 
    label_visibility="collapsed"
)


if 'files_processati_sessione' not in st.session_state:
    st.session_state.files_processati_sessione = set()

if 'files_con_errori' not in st.session_state:
    st.session_state.files_con_errori = {}


# 🔥 GESTIONE FILE CARICATI
if uploaded_files:
    # File già processati: solo da Supabase + sessione
    try:
        user_id = st.session_state.user_data["id"]
        response = supabase.table("fatture").select("file_origine", count="exact").eq("user_id", user_id).execute()
        file_su_supabase = set([row["file_origine"] for row in response.data])
    except Exception as e:
        logger.exception(f"Errore lettura file già processati da Supabase per user_id={st.session_state.user_data.get('id')}")
        file_su_supabase = set()


    tutti_file_processati = st.session_state.files_processati_sessione | file_su_supabase
    
    file_unici = []
    duplicati_interni = []
    visti = set()
    
    for file in uploaded_files:
        if file.name not in visti:
            file_unici.append(file)
            visti.add(file.name)
        else:
            duplicati_interni.append(file.name)
    
    file_nuovi = []
    file_gia_processati = []
    
    for file in file_unici:
        if file.name in tutti_file_processati:
            file_gia_processati.append(file)
        else:
            file_nuovi.append(file)
    
    # Messaggio semplice di conferma upload (senza lista ridondante)
    if file_nuovi:
        st.info(f"✅ **{len(file_nuovi)} nuove fatture** da elaborare")
    if file_gia_processati:
        st.info(f"♻️ **{len(file_gia_processati)} fatture** già in memoria (ignorate)")
        # NOTA: I duplicati NON vengono loggati (comportamento corretto, non problema)
        
    if duplicati_interni:
        st.warning(f"⚠️ **{len(duplicati_interni)} duplicati** nell'upload (ignorati)")
    
    if file_nuovi:
        # Crea placeholder per loading AI
        upload_placeholder = st.empty()
        
        try:
            # Mostra animazione AI
            mostra_loading_ai(upload_placeholder, f"Analisi AI di {len(file_nuovi)} Fatture")
            
            # Contatori per statistiche
            file_processati = 0
            righe_totali = 0
            salvati_supabase = 0
            salvati_json = 0
            errori = []
            
            # Elabora tutti i file
            for idx, file in enumerate(file_nuovi, 1):
                nome_file = file.name.lower()
                
                # Routing automatico per tipo file (SILENZIOSO)
                try:
                    if nome_file.endswith('.xml'):
                        items = estrai_dati_da_xml(file)
                    elif nome_file.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                        items = estrai_dati_da_scontrino_vision(file)
                    else:
                        errori.append(f"{file.name}: Formato non supportato")
                        # CRITICO: Aggiungi a processati per evitare loop
                        st.session_state.files_processati_sessione.add(file.name)
                        continue
                    
                    # Salva in memoria se trovati dati (SILENZIOSO)
                    if items:
                        result = salva_fattura_processata(file.name, items, silent=True)
                        
                        if result["success"]:
                            file_processati += 1
                            righe_totali += result["righe"]
                            if result["location"] == "supabase":
                                salvati_supabase += 1
                            elif result["location"] == "json":
                                salvati_json += 1
                            
                            # Aggiungi a processati
                            st.session_state.files_processati_sessione.add(file.name)
                        else:
                            errori.append(f"{file.name}: Errore salvataggio")
                            # CRITICO: Aggiungi a processati anche se salvataggio fallito
                            st.session_state.files_processati_sessione.add(file.name)
                    else:
                        # Nessun dato estratto - controlla se c'è errore specifico
                        if file.name in st.session_state.files_con_errori:
                            errore_dettaglio = st.session_state.files_con_errori[file.name]
                            errori.append(f"{file.name}: {errore_dettaglio}")
                        else:
                            errori.append(f"{file.name}: Nessun dato estratto")
                        
                        # CRITICO: Aggiungi a processati per evitare loop infinito
                        st.session_state.files_processati_sessione.add(file.name)
                
                except Exception as e:
                    logger.exception(f"Errore elaborazione {file.name}")
                    errori.append(f"{file.name}: {str(e)[:50]}")
                    
                    # ============================================================
                    # LOG UPLOAD EVENT - FAILED (parsing/vision error)
                    # ============================================================
                    try:
                        user_id = st.session_state.user_data.get("id")
                        user_email = st.session_state.user_data.get("email", "unknown")
                        
                        # Determina error_stage in base al tipo di file
                        error_stage = "PARSING" if file.name.endswith('.xml') else "VISION"
                        
                        log_upload_event(
                            user_id=user_id,
                            user_email=user_email,
                            file_name=file.name,
                            status="FAILED",
                            rows_parsed=0,
                            rows_saved=0,
                            error_stage=error_stage,
                            error_message=str(e)[:500],
                            details={"exception_type": type(e).__name__}
                        )
                    except Exception as log_error:
                        logger.error(f"Errore logging failed event: {log_error}")
                    # ============================================================
                    
                    # CRITICO: Aggiungi a processati per evitare loop infinito
                    st.session_state.files_processati_sessione.add(file.name)
            
            # Rimuovi loading SEMPRE
            upload_placeholder.empty()
            
            # MESSAGGIO FINALE RIASSUNTIVO
            if file_processati > 0:
                # Messaggio di successo
                location_text = ""
                if salvati_supabase > 0 and salvati_json == 0:
                    location_text = " su **Supabase Cloud** ☁️"
                elif salvati_json > 0 and salvati_supabase == 0:
                    location_text = " su **JSON locale** 💾"
                elif salvati_supabase > 0 and salvati_json > 0:
                    location_text = f" (☁️ {salvati_supabase} su Supabase, 💾 {salvati_json} su JSON)"
                
                st.success(f"✅ **Caricate {file_processati} fatture con successo!** ({righe_totali} righe elaborate){location_text}")
            
            # Mostra errori se presenti (SOLO ERRORI CRITICI)
            if errori:
                with st.expander(f"⚠️ {len(errori)} file con problemi", expanded=False):
                    for errore in errori:
                        st.warning(errore)
            
            # Piccola pausa per vedere il messaggio di successo
            if file_processati > 0:
                time.sleep(0.3)
                
                # 🔍 AUDIT: Verifica coerenza post-upload
                audit_result = audit_data_consistency(user_id, context="post-upload")
                if not audit_result["consistent"]:
                    st.warning(f"⚠️ Audit: DB ha {audit_result['db_count']} righe ma cache ne mostra {audit_result['cache_count']}")
            
            # Ricarica cache e aggiorna automaticamente
            st.cache_data.clear()
            st.rerun()
        
        except Exception as e:
            # CRITICO: rimuovi loading anche in caso di errore
            upload_placeholder.empty()
            st.error(f"❌ Errore durante l'elaborazione: {e}")
            logger.exception("Errore upload fatture")


# 🔥 CARICA E MOSTRA STATISTICHE SEMPRE (da Supabase)
# 🔒 IMPORTANTE: user_id per cache isolata (multi-tenancy)


# Crea placeholder per loading
loading_placeholder = st.empty()


try:
    # Mostra animazione AI durante caricamento
    mostra_loading_ai(loading_placeholder, "Caricamento Dashboard AI")
    
    # Carica dati (con force_refresh se richiesto dopo categorizzazione AI)
    user_id = st.session_state.user_data["id"]
    force_refresh = st.session_state.get('force_reload', False)
    if force_refresh:
        st.session_state.force_reload = False  # Reset flag
        logger.info("🔄 FORCE RELOAD attivato dopo categorizzazione AI")
    df_completo = carica_e_prepara_dataframe(user_id, force_refresh=force_refresh)
    
    # Logging shape e verifica dati (solo console)
    logger.debug(f"DataFrame shape = {df_completo.shape}")
    logger.debug(f"DataFrame empty = {df_completo.empty}")
    if not df_completo.empty:
        logger.debug(f"Colonne = {df_completo.columns.tolist()}")
        logger.debug(f"Prime 3 righe:\n{df_completo.head(3)}")
    
    # Rimuovi loading SEMPRE prima di mostrare contenuto
    loading_placeholder.empty()
    
    # Mostra dashboard direttamente senza messaggi
    if not df_completo.empty:
        mostra_statistiche(df_completo)
    else:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


except Exception as e:
    # CRITICO: rimuovi loading anche in caso di errore
    loading_placeholder.empty()
    st.error(f"❌ Errore durante il caricamento: {e}")
    logger.exception("Errore caricamento dashboard")
