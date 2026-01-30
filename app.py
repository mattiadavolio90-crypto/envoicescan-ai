# Fix: Force re-deployment to resolve IndentationError on cloud
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
    # Dizionario correzioni
    DIZIONARIO_CORREZIONI,
    # Admin
    ADMIN_EMAILS
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

from utils.piva_validator import (
    valida_formato_piva,
    normalizza_piva
)

from utils.formatters import (
    converti_in_base64,
    safe_get,
    calcola_prezzo_standard_intelligente,
    carica_categorie_da_db,
    log_upload_event,
    crea_pivot_mensile,
    genera_box_recap
)

from utils.ristorante_helper import add_ristorante_filter, get_current_ristorante_id

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
    svuota_memoria_globale,
    set_global_memory_enabled,
    # Legacy functions
    carica_memoria_ai,
    salva_memoria_ai,
    aggiorna_memoria_ai
)

from services.auth_service import (
    verify_and_migrate_password,
    verifica_credenziali,
    invia_codice_reset,
    registra_logout_utente,
    verifica_sessione_valida,
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
    elimina_fattura_completa,
    elimina_tutte_fatture,
    audit_data_consistency,
    get_fatture_stats
)


# ============================================================
# 🔄 HOT RELOAD AUTOMATICO MODULI (Development Mode)
# ============================================================
import importlib
import sys

# Hot reload automatico per development
if st.secrets.get("environment", {}).get("mode", "production") != "production":
    # Lista tutti i moduli in services/
    services_modules = [
        'services.db_service',
        'services.invoice_service',
        'services.auth_service',
        'services.ai_service',
        'utils.text_utils',
        'utils.validation',
        'utils.formatters',
        'config.constants'
    ]
    
    for module_name in services_modules:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


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

# ============================================
# NASCONDI FOOTER BRANDING STREAMLIT
# ============================================
st.markdown("""
<style>
    /* Nascondi footer Streamlit - TUTTI I SELETTORI */
    footer,
    .stApp footer,
    div[role="contentinfo"],
    [data-testid="stFooter"] {
        visibility: hidden !important;
        display: none !important;
        height: 0 !important;
        overflow: hidden !important;
        position: absolute !important;
        bottom: -9999px !important;
    }
    
    /* Nascondi "Created by" e "Hosted with" */
    [data-testid="stStatusWidget"],
    .stStatusWidget {
        display: none !important;
    }
    
    /* Nascondi link profilo e branding */
    div[data-testid="stDecoration"],
    [data-testid="stToolbar"],
    .stDecoration {
        display: none !important;
    }
    
    /* Target specifico per footer icons */
    footer::after,
    footer::before {
        display: none !important;
    }
    
    /* Nascondi toolbar e header */
    header[data-testid="stHeader"],
    .stApp > header,
    div[data-testid="stToolbar"] {
        display: none !important;
    }
    
    /* Nascondi ViewerBadge (Made with Streamlit) */
    .viewerBadge_container__1QSob,
    .viewerBadge_link__1S137,
    .styles_viewerBadge__1yB5_,
    [class*="viewerBadge"],
    a[href*="streamlit.io"],
    a[target="_blank"][rel*="noopener"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }
    
    /* OVERLAY BIANCO per coprire footer se reinserito */
    body::after {
        content: "";
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: 100px;
        background: white;
        z-index: 999999;
        pointer-events: none;
    }
    
    /* ✂️ RIDUCI SPAZIO SUPERIORE APP (valori aumentati per evitare tagli) */
    .main > div {
        padding-top: 2rem !important;
    }
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 6rem !important;
    }
    
    /* ✅ ASSICURA VISIBILITÀ COMPLETA CONTENUTO */
    [data-testid="stVerticalBlock"] {
        overflow: visible !important;
    }
    [data-testid="column"] {
        overflow: visible !important;
        min-height: 120px !important;
        margin-bottom: 30px !important;
    }
</style>
""", unsafe_allow_html=True)

# JavaScript SUPER aggressivo per rimuovere elementi branding
st.markdown("""
<script>
(function() {
    function hideStreamlitBranding() {
        // Rimuovi TUTTI i footer
        document.querySelectorAll('footer').forEach(el => {
            el.style.display = 'none';
            el.style.visibility = 'hidden';
            el.style.height = '0';
            el.style.overflow = 'hidden';
            el.remove();
        });
        document.querySelectorAll('[role="contentinfo"]').forEach(el => el.remove());
        document.querySelectorAll('[data-testid="stFooter"]').forEach(el => el.remove());
        
        // Rimuovi decorazioni
        document.querySelectorAll('[data-testid="stDecoration"]').forEach(el => el.remove());
        document.querySelectorAll('[data-testid="stToolbar"]').forEach(el => el.remove());
        
        // Rimuovi header
        document.querySelectorAll('header[data-testid="stHeader"]').forEach(el => el.remove());
        
        // Rimuovi ViewerBadge (Made with Streamlit)
        document.querySelectorAll('[class*="viewerBadge"]').forEach(el => {
            el.style.display = 'none';
            el.remove();
        });
        document.querySelectorAll('a[href*="streamlit.io"]').forEach(el => {
            if (el.textContent.includes('Streamlit') || el.textContent.includes('Made with')) {
                el.remove();
            }
        });
        
        // Cerca e rimuovi qualsiasi elemento che contiene "Made with" o "Hosted"
        document.querySelectorAll('*').forEach(el => {
            const text = el.textContent || '';
            if (text.includes('Made with') || text.includes('Hosted with') || text.includes('Streamlit')) {
                if (el.tagName === 'A' || el.tagName === 'DIV' || el.tagName === 'SPAN') {
                    el.style.display = 'none';
                    el.remove();
                }
            }
        });
    }
    
    // Esegui subito
    hideStreamlitBranding();
    
    // Ripeti ogni 100ms (ancora più frequente)
    setInterval(hideStreamlitBranding, 100);
    
    // Observer per nuovi elementi
    const observer = new MutationObserver(hideStreamlitBranding);
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'data-testid']
    });
    
    // Esegui anche su DOMContentLoaded
    document.addEventListener('DOMContentLoaded', hideStreamlitBranding);
})();
</script>
""", unsafe_allow_html=True)

# Nascondi bottone "Manage app"
st.markdown("""
<style>
    /* Nascondi Manage App con tutti i selettori possibili */
    [data-testid="manage-app-button"],
    [data-testid="stDecoration"],
    button[kind="header"],
    button[aria-label*="Manage"],
    button[title*="Manage"],
    .stApp > header,
    header[data-testid="stHeader"],
    div[data-testid="stToolbar"],
    .stDeployButton,
    footer,
    #MainMenu {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        width: 0 !important;
    }
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


# ============================================================
# INIZIALIZZAZIONE SUPABASE CON CONNECTION POOLING
# ============================================================
@st.cache_resource
def get_supabase_client() -> Client:
    """✅ Singleton Supabase client con connection pooling.
    
    Riutilizza la stessa connessione per tutti gli utenti → performance 10x migliori.
    Cache persiste per tutta la sessione Streamlit (non viene ricreata ad ogni run).
    """
    try:
        supabase_url = st.secrets["supabase"]["url"]
        supabase_key = st.secrets["supabase"]["key"]
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        logger.exception("Connessione Supabase fallita")
        st.error(f"⛔ Errore connessione Supabase: {e}")
        st.stop()

# Inizializza client globale (singleton)
try:
    supabase: Client = get_supabase_client()
except Exception as e:
    logger.exception("Connessione Supabase fallita")
    st.error(f"⛔ Errore connessione Supabase: {e}")
    st.stop()


# DISABILITO RIPRISTINO SESSIONE DA COOKIE E CANCELLO COOKIE ESISTENTI
# I cookie causavano problemi con il logout - ora usiamo solo session_state
try:
    # Inizializza logged_in se non esiste
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Cancella eventuali cookie esistenti dal browser
    if 'cookies_cleared' not in st.session_state:
        try:
            from datetime import datetime, timedelta
            cookie_manager = stx.CookieManager(key="cookie_manager_cleanup")
            past_time = datetime.now() - timedelta(days=365)
            # Cancella cookie "user_email" se esiste
            cookie_manager.set("user_email", "", expires_at=past_time)
            cookie_manager.delete("user_email")
            st.session_state.cookies_cleared = True
            logger.info("Cookie esistenti cancellati al primo caricamento")
        except Exception:
            logger.exception('Errore pulizia cookie esistenti')
    
    # NON ripristinare MAI da cookie - sessione persa al refresh
except Exception:
    # Non fatale: se qualcosa va storto non blocchiamo l'app
    logger.exception('Errore controllo cookie sessione')


# ============================================
# GESTIONE LOGOUT FORZATO VIA QUERY PARAMS
# ============================================
# Se c'è il parametro logout=1, forza logout completo (funziona anche su Streamlit Cloud)
if st.query_params.get("logout") == "1":
    logger.warning("🚨 LOGOUT FORZATO via query params - pulizia totale sessione")
    # Pulizia sessione e reimpostazione flag (ORDINE CORRETTO)
    st.session_state.clear()  # Cancella tutto
    st.session_state.logged_in = False  # Reimposta dopo clear
    st.session_state.force_logout = True  # Flag che persiste
    # Rimuovi parametro logout dall'URL
    st.query_params.clear()
    st.rerun()


# ============================================================
# GESTIONE TOKEN RESET PASSWORD (NUOVO CLIENTE + RECUPERO PASSWORD)
# ============================================================
# Se c'è il parametro reset_token, mostra form impostazione password
if st.query_params.get("reset_token"):
    from services.auth_service import imposta_password_da_token, valida_password_compliance
    
    reset_token = st.query_params.get("reset_token")
    
    # Nascondi sidebar per pagina pulita
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("🔐 Imposta la tua Password")
    
    # Verifica token valido
    try:
        check_result = supabase.table('users')\
            .select('id, email, nome_ristorante, reset_expires, password_hash')\
            .eq('reset_code', reset_token)\
            .execute()
        
        if not check_result.data:
            st.error("❌ Link non valido o già utilizzato")
            st.info("💡 Se hai già impostato la password, vai al login. Altrimenti contatta il supporto per un nuovo link.")
            if st.button("🔑 Vai al Login"):
                st.query_params.clear()
                st.rerun()
            st.stop()
        
        user_data = check_result.data[0]
        
        # Check scadenza token
        from datetime import datetime, timezone as tz
        expires_str = user_data.get('reset_expires')
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                now_utc = datetime.now(tz.utc)
                
                if now_utc > expires:
                    st.error("⏰ Link scaduto (validità: 24 ore)")
                    st.info("💡 Contatta il supporto per ricevere un nuovo link di attivazione.")
                    st.stop()
            except Exception as e:
                logger.warning(f"Errore parsing data scadenza token: {e}")
        
        # Mostra info utente
        is_nuovo_cliente = user_data.get('password_hash') is None
        
        if is_nuovo_cliente:
            st.success(f"✅ Benvenuto, **{user_data.get('nome_ristorante')}**!")
            st.info(f"📧 Il tuo account: **{user_data.get('email')}**")
            st.markdown("Imposta una password sicura per accedere all'app.")
        else:
            st.info(f"📧 Reset password per: **{user_data.get('email')}**")
        
        # Form impostazione password
        with st.form("form_imposta_password"):
            nuova_password = st.text_input(
                "🔑 Nuova Password",
                type="password",
                help="Minimo 10 caratteri, con maiuscola, minuscola e numero"
            )
            
            conferma_password = st.text_input(
                "🔑 Conferma Password",
                type="password"
            )
            
            st.markdown("""
            **Requisiti password:**
            - ✅ Almeno 10 caratteri
            - ✅ Almeno 3 tra: maiuscola, minuscola, numero, simbolo
            - ❌ Non usare email o nome ristorante
            - ❌ Non usare password comuni
            """)
            
            submitted = st.form_submit_button("✅ Conferma Password", type="primary", use_container_width=True)
            
            if submitted:
                # Validazioni
                if not nuova_password or not conferma_password:
                    st.error("⚠️ Compila entrambi i campi password")
                elif nuova_password != conferma_password:
                    st.error("❌ Le password non coincidono")
                else:
                    # Valida compliance GDPR
                    errori = valida_password_compliance(
                        nuova_password,
                        user_data.get('email', ''),
                        user_data.get('nome_ristorante', '')
                    )
                    
                    if errori:
                        for err in errori:
                            st.error(err)
                    else:
                        # Imposta password
                        successo, messaggio, _ = imposta_password_da_token(
                            reset_token,
                            nuova_password,
                            supabase
                        )
                        
                        if successo:
                            st.success("""
                            🎉 **Password impostata con successo!**
                            
                            Ora puoi effettuare il login con la tua email e password.
                            """)
                            st.balloons()
                            
                            # Pulisci token da URL
                            import time
                            time.sleep(2)
                            st.query_params.clear()
                            st.rerun()
                        else:
                            st.error(messaggio)
    
    except Exception as e:
        st.error(f"❌ Errore durante verifica token: {e}")
        logger.exception("Errore verifica reset_token")
    
    st.stop()  # Non mostrare resto app


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


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_admin_or_impersonating() -> bool:
    """
    Helper per verificare se l'utente corrente è admin o in impersonificazione.
    Riduce codice duplicato in tutta l'app.
    
    Returns:
        bool: True se admin o impersonating, False altrimenti
    """
    return st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False)


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
        [data-testid="manage-app-button"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        footer { visibility: hidden !important; }
        
        /* ✂️ RIDUCI SPAZIO SUPERIORE LOGIN (valori aumentati) */
        .main > div {
            padding-top: 2rem !important;
        }
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 3rem !important;
        }
        </style>
        <script>
        setInterval(function() {
            var buttons = document.querySelectorAll('[data-testid="manage-app-button"]');
            buttons.forEach(function(btn) { btn.remove(); });
            
            var decorations = document.querySelectorAll('[data-testid="stDecoration"]');
            decorations.forEach(function(dec) { dec.remove(); });
            
            var headers = document.querySelectorAll('button[kind="header"]');
            headers.forEach(function(h) { h.remove(); });
        }, 200);
        </script>
    """, unsafe_allow_html=True)
    
    st.markdown("""
<h1 style="font-size: 52px; font-weight: 700; margin: 0; display: inline-block;">
    🧠 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi Fatture AI</span>
</h1>
""", unsafe_allow_html=True)
    st.markdown("### Accedi al Sistema")
    
    tab1, tab2 = st.tabs(["🔑 Login", "🔄 Recupera Password"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input("🔑 Password", type="password", placeholder="Password")
            
            # CSS per bottone blu chiaro e fix spazio verticale
            st.markdown("""
                <style>
                div[data-testid="stFormSubmitButton"] button {
                    background-color: #0ea5e9 !important;
                    color: white !important;
                    margin-bottom: 100px !important;
                }
                div[data-testid="stFormSubmitButton"] button:hover {
                    background-color: #0284c7 !important;
                }
                /* Fix altezza pagina per vedere tutto */
                .main .block-container {
                    max-height: none !important;
                    padding-bottom: 150px !important;
                }
                div[data-testid="stForm"] {
                    max-height: none !important;
                    height: auto !important;
                    padding-bottom: 50px !important;
                }
                section[data-testid="stSidebar"] ~ div {
                    max-height: none !important;
                    overflow-y: auto !important;
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
                            
                            # Salva P.IVA in session_state per validazione fatture
                            st.session_state.partita_iva = user.get('partita_iva')
                            st.session_state.created_at = user.get('created_at')
                            
                            # Verifica se è admin e imposta flag
                            if user.get('email') in ADMIN_EMAILS:
                                st.session_state.user_is_admin = True
                                logger.info(f"✅ Login ADMIN: {user.get('email')}")
                                st.success("✅ Accesso effettuato come ADMIN!")
                                time.sleep(0.5)
                                # Reindirizza direttamente al pannello admin
                                st.switch_page("pages/admin.py")
                            else:
                                st.session_state.user_is_admin = False
                                logger.info(f"✅ Login cliente: {user.get('email')} | P.IVA: {user.get('partita_iva', 'N/A')}")
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

# INIZIALIZZA logged_in se non esiste
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# VERIFICA FINALE: se force_logout è attivo, FORZA logged_in = False
if st.session_state.get('force_logout', False):
    logger.critical("⛔ force_logout attivo - forzando logged_in=False")
    st.session_state.logged_in = False
    st.session_state.user_data = None

# Se NON loggato, mostra login e STOP
if not st.session_state.get('logged_in', False):
    logger.info("👤 Utente non loggato - mostrando pagina login")
    mostra_pagina_login()
    st.stop()

# Se arrivi qui, sei loggato! Vai DIRETTO ALL'APP
user = st.session_state.user_data

# ULTIMA VERIFICA: se user_data è None o invalido, FORZA logout immediato
if not user or not user.get('email'):
    logger.critical("❌ user_data è None o mancante email - FORZA LOGOUT")
    st.session_state.logged_in = False
    st.session_state.user_data = None
    st.error("⚠️ Sessione invalida. Effettua nuovamente il login.")
    st.rerun()

if not user or not user.get('email'):
    logger.critical("⛔ user_data invalido - forzando logout")
    st.session_state.clear()  # Cancella tutto
    st.session_state.logged_in = False  # Reimposta dopo clear
    st.rerun()


# ============================================
# CARICAMENTO RISTORANTI (MULTI-RISTORANTE STEP 2)
# ============================================
# Carica ristoranti dell'utente (anche se admin sta impersonando)
if not st.session_state.get('user_is_admin', False):
    if 'ristoranti' not in st.session_state or 'ristorante_id' not in st.session_state:
        try:
            ristoranti = supabase.table('ristoranti')\
                .select('id, nome_ristorante, partita_iva, ragione_sociale')\
                .eq('user_id', user.get('id'))\
                .eq('attivo', True)\
                .execute()
            
            st.session_state.ristoranti = ristoranti.data if ristoranti.data else []
            
            logger.info(f"🔍 DEBUG: Caricati {len(st.session_state.ristoranti)} ristoranti per user_id={user.get('id')}")
            
            # Se ha ristoranti, imposta il primo come default
            if st.session_state.ristoranti:
                # Se non c'è un ristorante selezionato, usa il primo
                if 'ristorante_id' not in st.session_state:
                    st.session_state.ristorante_id = st.session_state.ristoranti[0]['id']
                    st.session_state.partita_iva = st.session_state.ristoranti[0]['partita_iva']
                    st.session_state.nome_ristorante = st.session_state.ristoranti[0]['nome_ristorante']
                    logger.info(f"🏢 Ristorante caricato: {st.session_state.nome_ristorante} (P.IVA: {st.session_state.partita_iva})")
            else:
                logger.warning(f"⚠️ Nessun ristorante trovato per user_id={user.get('id')} in tabella 'ristoranti'")
        except Exception as e:
            logger.exception(f"Errore caricamento ristoranti: {e}")
            # Fallback: usa dati utente
            st.session_state.ristoranti = []
            st.session_state.partita_iva = user.get('partita_iva')
            st.session_state.nome_ristorante = user.get('nome_ristorante')


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
                
                # Ripristina flag admin
                st.session_state.user_is_admin = True
                
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


# Struttura colonne: se admin mostra 4 colonne, altrimenti 3
if user.get('email') in ADMIN_EMAILS:
    col1, col2, col3, col4 = st.columns([6, 1.5, 1.5, 1])
else:
    col1, col2, col3 = st.columns([7, 2, 1])


with col1:
    st.markdown("""
<h1 style="font-size: 52px; font-weight: 700; margin: 0; margin-top: 20px; display: inline-block;">
    🧠 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi Fatture AI</span>
</h1>
""", unsafe_allow_html=True)
    
    # Recupera email e nome ristorante
    user_email = (user.get('email') or user.get('Email') or user.get('user_email') or 
                  st.session_state.user_data.get('email') if st.session_state.user_data else None or 
                  'Email non disponibile')
    
    nome_ristorante = (user.get('nome_ristorante') or user.get('restaurant_name') or 
                       user.get('nome') or user.get('name') or 'Ristorante')
    
    # Mostra nome ristorante ed email
    st.markdown(f"<p style='font-size: 14px; color: #666; margin-top: -10px;'>🏪 {nome_ristorante} | 📧 {user_email}</p>", 
                unsafe_allow_html=True)


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
            # Reset completo session_state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
            # Rerun per applicare
            st.rerun()
else:
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Cambio Password", use_container_width=True, key="change_pwd_btn"):
            st.switch_page("pages/cambio_password.py")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", type="primary", use_container_width=True, key="logout_btn_alt"):
            # Reset completo session_state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
            # Rerun per applicare
            st.rerun()


st.markdown("---")

# ============================================
# DROPDOWN MULTI-RISTORANTE
# ============================================
# Mostra dropdown per clienti NON admin con più ristoranti
if user.get('email') not in ADMIN_EMAILS:
    ristoranti = st.session_state.get('ristoranti', [])
    
    if len(ristoranti) > 1:
        st.markdown("### 🏢 Seleziona Ristorante da Gestire")
        
        # Trova indice ristorante corrente
        current_id = st.session_state.get('ristorante_id')
        current_idx = 0
        for idx, r in enumerate(ristoranti):
            if r['id'] == current_id:
                current_idx = idx
                break
        
        # Dropdown full-width
        ristorante_idx = st.selectbox(
            "🏪 Scegli quale ristorante vuoi gestire:",
            range(len(ristoranti)),
            index=current_idx,
            format_func=lambda i: f"{ristoranti[i]['nome_ristorante']} - P.IVA: {ristoranti[i]['partita_iva']}",
            key="dropdown_ristorante_main",
            help="Seleziona il ristorante per cui vuoi caricare e analizzare fatture"
        )
        
        # Aggiorna sessione se cambiato
        selected_ristorante = ristoranti[ristorante_idx]
        if st.session_state.get('ristorante_id') != selected_ristorante['id']:
            st.session_state.ristorante_id = selected_ristorante['id']
            st.session_state.partita_iva = selected_ristorante['partita_iva']
            st.session_state.nome_ristorante = selected_ristorante['nome_ristorante']
            
            # 🧹 Pulizia cache contesto ristorante precedente
            if 'files_processati_sessione' in st.session_state:
                st.session_state.files_processati_sessione = set()
            if 'files_con_errori' in st.session_state:
                st.session_state.files_con_errori = set()
            
            logger.info(f"🔄 Ristorante cambiato: {st.session_state.nome_ristorante} (P.IVA: {st.session_state.partita_iva})")
            st.rerun()
        
        # Info ristorante attivo - disposizione ORIZZONTALE con box azzurro standard
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.info(f"**✅ Ristorante Attivo**  \nSì")
        
        with col2:
            st.info(f"**📋 Nome**  \n{selected_ristorante['nome_ristorante']}")
        
        with col3:
            st.info(f"**🏢 P.IVA**  \n`{selected_ristorante['partita_iva']}`")
        
        with col4:
            st.info(f"**📄 Ragione Sociale**  \n{selected_ristorante.get('ragione_sociale', 'N/A')}")
        
        st.warning("⚠️ **IMPORTANTE:** Le fatture caricate devono corrispondere alla P.IVA del ristorante selezionato sopra! **Altrimenti verranno scartate**")
        st.markdown("---")
    
    elif len(ristoranti) == 1:
        # Singolo ristorante: mostra solo info compatta
        st.success(f"🏪 **Ristorante:** {ristoranti[0]['nome_ristorante']} | 📋 **P.IVA:** `{ristoranti[0]['partita_iva']}`")
        st.markdown("---")

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


# ============================================================
# TEST & AUDIT UTILITIES
# ============================================================

        return {"num_uniche": 0, "num_righe": 0, "success": False}


# ============================================================
# CACHING DATAFRAME OTTIMIZZATO
# ============================================================


@st.cache_data(ttl=600, max_entries=50)  # ✅ TTL 10 minuti: dati sempre freschi senza logout
# ============================================================
# CONVERSIONE FILE IN BASE64 PER VISION
# ============================================================


# ============================================================
# FUNZIONI CALCOLO ALERT PREZZI (SPOSTATE IN services/db_service.py)
# ============================================================

# ============================================================
# FUNZIONE PIVOT MENSILE
# ============================================================


@st.cache_data(ttl=600, show_spinner=False, max_entries=50)  # ✅ TTL 10 minuti
# ============================================================
# FUNZIONE RENDERING STATISTICHE
# ============================================================

def mostra_statistiche(df_completo):
    """Mostra grafici, filtri e tabella dati"""
    
    # ===== 🔍 DEBUG CATEGORIZZAZIONE (SOLO ADMIN/IMPERSONIFICATO) =====
    if is_admin_or_impersonating():
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
    
    # 🔒 VERIFICA ristorante_id presente (CRITICO per multi-tenancy)
    if not st.session_state.get('ristorante_id'):
        st.error("❌ Ristorante non selezionato. Contatta l'assistenza.")
        logger.critical(f"ristorante_id mancante per user_id={user_id}")
        st.stop()
    
    # Separa F&B da Spese Generali solo per categoria (NON escludere fornitori)
    mask_spese = df_completo['Categoria'].isin(CATEGORIE_SPESE_GENERALI)
    df_spese_generali_completo = df_completo[mask_spese].copy()
    
    # F&B: Escludi solo le categorie spese generali (NON i fornitori)
    df_food_completo = df_completo[~mask_spese].copy()
    
    # Spazio sotto il box arancione
    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)


    # ============================================
    # CATEGORIZZAZIONE AI
    # ============================================
    
    # Conta righe da classificare con QUERY DIRETTA al database (non df_completo che può essere filtrato)
    # user_id già recuperato sopra
    
    # Query 1: Conta righe con 'Da Classificare'
    ristorante_id = st.session_state.get('ristorante_id')
    query_da_class = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id).eq("categoria", "Da Classificare")
    if ristorante_id:
        query_da_class = query_da_class.eq("ristorante_id", ristorante_id)
    count_da_class = query_da_class.execute()
    righe_da_class = count_da_class.count if count_da_class.count else 0
    
    # Query 2: Conta righe con categoria NULL
    query_null = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id).is_("categoria", "null")
    if ristorante_id:
        query_null = query_null.eq("ristorante_id", ristorante_id)
    count_null = query_null.execute()
    righe_null = count_null.count if count_null.count else 0
    
    # TOTALE righe senza categoria valida nel database
    righe_da_classificare = righe_da_class + righe_null
    
    # Calcola maschera locale per sapere quali descrizioni processare (dal df_completo locale)
    maschera_ai = (
        df_completo['Categoria'].isna()
        | (df_completo['Categoria'] == 'Da Classificare')
        | (df_completo['Categoria'].astype(str).str.strip() == '')
        | (df_completo['Categoria'] == '')
    )
    
    # Debug: cerca specificamente COPPETTA SANGO
    if 'COPPETTA' in ' '.join(df_completo['Descrizione'].astype(str).str.upper().tolist()):
        coppetta_rows = df_completo[df_completo['Descrizione'].str.contains('COPPETTA', case=False, na=False)]
        if not coppetta_rows.empty:
            logger.info(f"🔍 DEBUG: Trovata COPPETTA in df_completo ({len(coppetta_rows)} righe)")
            for idx, row in coppetta_rows.iterrows():
                cat = row['Categoria']
                in_maschera = maschera_ai.loc[idx] if idx in maschera_ai.index else False
                logger.info(f"   - '{row['Descrizione']}' cat='{cat}' in_maschera={in_maschera}")
        else:
            pass
    
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
                    # Query tutte le descrizioni che hanno categoria NULL o "Da Classificare"
                    ristorante_id = st.session_state.get('ristorante_id')
                    query_null = supabase.table("fatture").select("descrizione, fornitore").eq("user_id", user_id).is_("categoria", "null")
                    query_da_class = supabase.table("fatture").select("descrizione, fornitore").eq("user_id", user_id).eq("categoria", "Da Classificare")
                    if ristorante_id:
                        query_null = query_null.eq("ristorante_id", ristorante_id)
                        query_da_class = query_da_class.eq("ristorante_id", ristorante_id)
                    resp_null = query_null.execute()
                    resp_da_class = query_da_class.execute()
                    
                    # Combina e rimuovi duplicati
                    dati_null = resp_null.data if resp_null.data else []
                    dati_da_class = resp_da_class.data if resp_da_class.data else []
                    tutti_dati = dati_null + dati_da_class
                    
                    descrizioni_da_classificare = list(set([row['descrizione'] for row in tutti_dati if row.get('descrizione')]))
                    fornitori_da_classificare = list(set([row['fornitore'] for row in tutti_dati if row.get('fornitore')]))
                    
                    logger.info(f"🔍 Query diretta DB: trovate {len(descrizioni_da_classificare)} descrizioni uniche da classificare")
                except Exception as e:
                    logger.error(f"Errore query diretta descrizioni: {e}")
                    # Fallback su df_completo se query fallisce
                    descrizioni_da_classificare = df_completo[maschera_ai]['Descrizione'].unique().tolist()
                    fornitori_da_classificare = df_completo[maschera_ai]['Fornitore'].unique().tolist()
                
                if descrizioni_da_classificare:
                    # 🧠 Placeholder per banner orizzontale
                    progress_placeholder = st.empty()
                    
                    # Mostra banner immediatamente con 0%
                    totale_da_classificare = len(descrizioni_da_classificare)
                    progress_placeholder.markdown(f"""
                    <div class="ai-banner">
                        <div class="brain-pulse-banner">🧠</div>
                        <div class="progress-percentage">0%</div>
                        <div class="progress-status">Avvio categorizzazione: 0 di {totale_da_classificare}</div>
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
                        font-size: 60px;
                        animation: pulse_brain 1.5s ease-in-out infinite;
                        line-height: 1;
                    }
                    
                    .progress-percentage {
                        font-family: monospace;
                        font-size: 32px;
                        font-weight: bold;
                        color: #FF69B4;
                        min-width: 80px;
                    }
                    
                    .progress-status {
                        color: #555;
                        font-size: 18px;
                        font-weight: 500;
                    }
                        font-weight: 500;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    # 📖 STEP 1: Prima prova con DIZIONARIO (più veloce, più preciso)
                    from services.ai_service import applica_correzioni_dizionario
                    
                    mappa_categorie = {}  # desc -> categoria
                    descrizioni_per_ai = []  # Solo quelle che dizionario non risolve
                    prodotti_elaborati = 0  # Contatore per banner
                    
                    for desc in descrizioni_da_classificare:
                        cat_dizionario = applica_correzioni_dizionario(desc, "Da Classificare")
                        if cat_dizionario and cat_dizionario != 'Da Classificare':
                            mappa_categorie[desc] = cat_dizionario
                            prodotti_elaborati += 1
                            
                            # Aggiorna banner in tempo reale durante dizionario
                            percentuale = (prodotti_elaborati / totale_da_classificare) * 100
                            progress_placeholder.markdown(f"""
                            <div class="ai-banner">
                                <div class="brain-pulse-banner">🧠</div>
                                <div class="progress-percentage">{int(percentuale)}%</div>
                                <div class="progress-status">Categorizzando: {prodotti_elaborati} di {totale_da_classificare}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # ⭐ NUOVO: Traccia righe keyword per colonna Fonte
                            if 'righe_keyword_appena_categorizzate' not in st.session_state:
                                st.session_state.righe_keyword_appena_categorizzate = []
                            if desc not in st.session_state.righe_keyword_appena_categorizzate:
                                st.session_state.righe_keyword_appena_categorizzate.append(desc)
                            logger.info(f"📖 DIZIONARIO: '{desc[:40]}' → {cat_dizionario}")
                        else:
                            descrizioni_per_ai.append(desc)
                    
                    # 🧠 STEP 2: Invia all'AI solo quelli che dizionario non ha risolto
                    chunk_size = 50
                    # prodotti_elaborati già inizializzato sopra e aggiornato durante STEP 1
                    
                    if descrizioni_per_ai:
                        for i in range(0, len(descrizioni_per_ai), chunk_size):
                            chunk = descrizioni_per_ai[i:i+chunk_size]
                            cats = classifica_con_ai(chunk, fornitori_da_classificare)
                            for desc, cat in zip(chunk, cats):
                                mappa_categorie[desc] = cat
                                # ✅ Memoria AI ora salvata automaticamente in salva_correzione_in_memoria_globale
                                prodotti_elaborati += 1
                            
                                # 🧠 Aggiorna banner orizzontale in tempo reale (REPLACE)
                                percentuale = (prodotti_elaborati / totale_da_classificare) * 100
                                progress_placeholder.markdown(f"""
                                <div class="ai-banner">
                                    <div class="brain-pulse-banner">🧠</div>
                                    <div class="progress-percentage">{int(percentuale)}%</div>
                                    <div class="progress-status">Categorizzando: {prodotti_elaborati} di {totale_da_classificare}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Salva anche in memoria GLOBALE su Supabase
                                try:
                                    supabase.table('prodotti_master').upsert({
                                        'descrizione': desc,
                                        'categoria': cat,
                                        'volte_visto': 1,
                                        'verified': False,  # ⚠️ Da verificare: classificazione automatica AI
                                        'classificato_da': 'AI'
                                    }, on_conflict='descrizione').execute()
                                    
                                    logger.info(f"💾 GLOBALE salvato: '{desc[:40]}...' → {cat}")
                                except Exception as e:
                                    logger.error(f"Errore salvataggio globale '{desc[:40]}...': {e}")
                            
                            # Invalida cache per forzare ricaricamento dopo ogni chunk
                            invalida_cache_memoria()


                    # Aggiorna categorie su Supabase
                    try:
                        user_id = st.session_state.user_data["id"]
                        
                        righe_aggiornate_totali = 0
                        descrizioni_non_trovate = []
                        descrizioni_aggiornate = []  # Per icone AI: solo quelle realmente aggiornate
                        
                        # Import normalizzazione
                        from utils.text_utils import normalizza_stringa
                        
                        logger.info(f"🔄 INIZIO UPDATE: {len(mappa_categorie)} descrizioni da aggiornare")
                        
                        # DEBUG: Log prime 5 categorie dall'AI per verificare che non siano vuote
                        print("\n" + "="*80)
                        print("🧠 CATEGORIE RESTITUITE DALL'AI (prime 10)")
                        print("="*80)
                        for i, (desc, cat) in enumerate(list(mappa_categorie.items())[:10]):
                            cat_display = f"'{cat}'" if cat else "VUOTA/NULL"
                            print(f"   [{i+1}] '{desc[:40]}' → {cat_display}")
                        print("="*80 + "\n")
                        
                        for desc, cat in mappa_categorie.items():
                            # Normalizza descrizione per matching consistente
                            desc_normalized = normalizza_stringa(desc)
                            
                            logger.info(f"🔍 Tentando update: '{desc[:50]}' → {cat}")
                            
                            # VALIDAZIONE: Assicurati che cat non sia vuota o None (MA ACCETTA "Da Classificare")
                            if not cat or cat.strip() == '':
                                logger.warning(f"⚠️ Categoria vuota/NULL per '{desc[:40]}', skip update")
                                continue
                            
                            # TENTATIVO 1: Match con descrizione normalizzata
                            query_update1 = supabase.table("fatture").update(
                                {"categoria": cat}
                            ).eq("user_id", user_id).eq("descrizione", desc_normalized)
                            query_update1 = add_ristorante_filter(query_update1)
                            result = query_update1.execute()
                            
                            num_aggiornate = len(result.data) if result.data else 0
                            if num_aggiornate > 0:
                                logger.info(f"✅ Match normalizzato: '{desc[:40]}...' ({num_aggiornate} righe)")
                            
                            # ⭐ RETRY se UPDATE non ha modificato nulla (possibile timeout/race condition)
                            if num_aggiornate == 0:
                                logger.warning(f"⚠️ UPDATE 0 righe per '{desc[:50]}...', retry...")
                                time.sleep(0.5)
                                query_retry = supabase.table("fatture").update(
                                    {"categoria": cat}
                                ).eq("user_id", user_id).eq("descrizione", desc_normalized)
                                query_retry = add_ristorante_filter(query_retry)
                                result = query_retry.execute()
                                num_aggiornate = len(result.data) if result.data else 0
                                if num_aggiornate > 0:
                                    logger.info(f"✅ Retry riuscito: {num_aggiornate} righe aggiornate")
                            
                            # TENTATIVO 2: Se non trovato, prova con descrizione originale
                            if num_aggiornate == 0:
                                query_update2 = supabase.table("fatture").update(
                                    {"categoria": cat}
                                ).eq("user_id", user_id).eq("descrizione", desc)
                                query_update2 = add_ristorante_filter(query_update2)
                                result2 = query_update2.execute()
                                
                                num_aggiornate = len(result2.data) if result2.data else 0
                                
                                if num_aggiornate > 0:
                                    logger.info(f"✅ Match con desc originale: '{desc[:40]}...' ({num_aggiornate} righe)")
                            
                            # TENTATIVO 3: Prova con trim
                            if num_aggiornate == 0:
                                desc_trimmed = desc.strip()
                                if desc_trimmed != desc:
                                    query_update3 = supabase.table("fatture").update(
                                        {"categoria": cat}
                                    ).eq("user_id", user_id).eq("descrizione", desc_trimmed)
                                    query_update3 = add_ristorante_filter(query_update3)
                                    result3 = query_update3.execute()
                                    
                                    num_aggiornate = len(result3.data) if result3.data else 0
                                    
                                    if num_aggiornate > 0:
                                        logger.info(f"✅ Match con trim: '{desc_trimmed[:40]}...' ({num_aggiornate} righe)")
                            
                            # TENTATIVO 4: Match case-insensitive parziale (ILIKE) controllato
                            if num_aggiornate == 0 and len(desc.strip()) >= 3:
                                try:
                                    # Prova prima con desc originale via ILIKE esatto
                                    query_update4 = supabase.table("fatture").update(
                                        {"categoria": cat}
                                    ).eq("user_id", user_id).ilike("descrizione", desc.strip())
                                    query_update4 = add_ristorante_filter(query_update4)
                                    result4 = query_update4.execute()
                                    num_aggiornate = len(result4.data) if result4.data else 0
                                    if num_aggiornate > 0:
                                        logger.info(f"✅ Match ILIKE esatto: '{desc[:40]}...' ({num_aggiornate} righe)")
                                    
                                    # Se ancora zero, prova con pattern parziale
                                    if num_aggiornate == 0 and len(desc.strip()) >= 5:
                                        query_update5 = supabase.table("fatture").update(
                                            {"categoria": cat}
                                        ).eq("user_id", user_id).ilike("descrizione", f"%{desc.strip()[:30]}%")
                                        query_update5 = add_ristorante_filter(query_update5)
                                        result5 = query_update5.execute()
                                        num_aggiornate = len(result5.data) if result5.data else 0
                                        if num_aggiornate > 0:
                                            logger.info(f"✅ Match ILIKE parziale: '{desc[:40]}...' ({num_aggiornate} righe)")
                                except Exception as ilike_err:
                                    logger.warning(f"Errore ILIKE update '{desc[:30]}...': {ilike_err}")
                            
                            # Se ancora non trovato, logga DETTAGLIATO
                            if num_aggiornate == 0:
                                descrizioni_non_trovate.append(desc)
                                logger.error(f"❌ NESSUN MATCH per: '{desc}' (cat: {cat})")
                                # Query diagnostica: cerca descrizioni simili
                                try:
                                    check_query = supabase.table("fatture").select("descrizione, categoria").eq("user_id", user_id).ilike("descrizione", f"%{desc[:20]}%").limit(10)
                                    check_query = add_ristorante_filter(check_query)
                                    check = check_query.execute()
                                    if check.data:
                                        logger.error(f"   Descrizioni simili trovate nel DB:")
                                        for row in check.data[:5]:
                                            logger.error(f"     - '{row['descrizione']}' (cat: {row.get('categoria', 'N/A')})")
                                    else:
                                        logger.error(f"   Nessuna descrizione simile trovata per '{desc[:30]}...'")
                                except Exception as diag_err:
                                    logger.error(f"   Errore query diagnostica: {diag_err}")
                            
                            righe_aggiornate_totali += num_aggiornate
                            
                            if num_aggiornate > 0:
                                descrizioni_aggiornate.append(desc)
                                logger.info(f"✅ AGGIORNATO '{desc[:40]}...' → {cat} ({num_aggiornate} righe)")
                        
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
                                    
                                    # Importa funzione dizionario
                                    from services.ai_service import applica_correzioni_dizionario
                                    
                                    for desc in ancora_da_class:
                                        # Tenta match con dizionario
                                        cat_dizionario = applica_correzioni_dizionario(desc, "Da Classificare")
                                        
                                        if cat_dizionario and cat_dizionario != 'Da Classificare':
                                            # Aggiorna con categoria da dizionario
                                            try:
                                                ristorante_id = st.session_state.get('ristorante_id')
                                                query_fallback = supabase.table('fatture').update(
                                                    {'categoria': cat_dizionario}
                                                ).eq('user_id', user_id).ilike('descrizione', f'%{desc.strip()}%')
                                                if ristorante_id:
                                                    query_fallback = query_fallback.eq('ristorante_id', ristorante_id)
                                                righe_updated = query_fallback.execute()
                                                righe_aggiornate_totali += len(righe_updated.data) if righe_updated.data else 0
                                                logger.info(f"✅ Fallback dizionario: '{desc[:40]}...' → {cat_dizionario}")
                                            except Exception as fb_err:
                                                logger.warning(f"Errore fallback: {fb_err}")
                                        else:
                                            # NON categorizzare - rimane "Da Classificare" per intervento manuale
                                            logger.warning(f"⚠️ '{desc[:40]}...' rimane Da Classificare - richiede intervento manuale")
                        except Exception as fb_err:
                            logger.warning(f"Errore fallback categorizzazione: {fb_err}")
                        
                        # ✅ Pulisci placeholder progress
                        progress_placeholder.empty()
                        
                        # 🧠 SALVA in session state le descrizioni categorizzate (AI + dizionario)
                        # Usa mappa_categorie che contiene TUTTE le descrizioni categorizzate
                        # Salva SOLO le descrizioni che hanno comportato un update
                        descrizioni_categorizzate = descrizioni_aggiornate if descrizioni_aggiornate else list(mappa_categorie.keys())
                        st.session_state.righe_ai_appena_categorizzate = descrizioni_categorizzate
                        
                        # DEBUG: Log per admin
                        logger.info(f"🧠 Salvate {len(descrizioni_categorizzate)} descrizioni in session_state")
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
                            ristorante_id = st.session_state.get('ristorante_id')
                            query_verifica = supabase.table('fatture').select('categoria').eq('user_id', user_id)
                            if ristorante_id:
                                query_verifica = query_verifica.eq('ristorante_id', ristorante_id)
                            verifica_response = query_verifica.execute()
                            if verifica_response.data:
                                null_count = sum(1 for row in verifica_response.data if not row.get('categoria') or row['categoria'] == 'Da Classificare')
                                logger.info(f"🔍 POST-UPDATE VERIFICA: {null_count} righe ancora NULL/Da Classificare su {len(verifica_response.data)} totali")
                                
                                if null_count > 0:
                                    logger.warning(f"⚠️ ATTENZIONE: {null_count} righe non categorizzate dopo AI")
                                else:
                                    logger.info(f"✅ VERIFICA OK: Tutte le righe categorizzate correttamente nel DB")
                        except Exception as e:
                            logger.error(f"❌ Errore verifica post-update: {e}")
                        
                        # Pulisci cache PRIMA del delay per garantire ricaricamento
                        st.cache_data.clear()
                        invalida_cache_memoria()
                        
                        # ⭐ FIX CRITICO: Imposta flag per forzare reload completo al prossimo caricamento
                        st.session_state.force_reload = True
                        st.session_state.force_empty_until_upload = False  # Assicura che i dati vengano caricati
                        logger.info("🔄 Flag force_reload impostato su True")
                        
                        # ⭐ FIX RACE CONDITION: Delay aumentato per garantire propagazione modifiche su Supabase CDN globale
                        with st.spinner("⏳ Sincronizzazione database in corso..."):
                            time.sleep(4)
                        
                        # Rerun per ricaricare dati freschi dal database
                        st.rerun()
                        
                    except Exception as e:
                        logger.exception("Errore aggiornamento categorie AI su Supabase")
                        st.error(f"❌ Errore aggiornamento categorie: {e}")
    
    # Rimuovi il flag automaticamente quando tutti i file sono stati rimossi (dopo aver cliccato la X)
    if not uploaded_files and st.session_state.get("force_empty_until_upload"):
        st.session_state.force_empty_until_upload = False
        st.stop()
    
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
            # Mostra SOLO i prodotti distinti (quello che vede nella tabella)
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
                <span style="color: #856404; font-weight: 600; font-size: 14px;">⚠️ CI SONO {righe_da_classificare} righe da categorizzare</span>
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
    
    elif periodo_selezionato == "⚙️ Periodo Personalizzato":
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
    
    else:
        # Default: Mese in Corso
        data_inizio_filtro = inizio_mese
        label_periodo = f"Mese in corso ({inizio_mese.strftime('%d/%m/%Y')} → {oggi_date.strftime('%d/%m/%Y')})"
    
    # APPLICA FILTRO AI DATI
    df_food_completo["Data_DT"] = pd.to_datetime(df_food_completo["DataDocumento"], errors='coerce').dt.date
    mask = (df_food_completo["Data_DT"] >= data_inizio_filtro) & (df_food_completo["Data_DT"] <= data_fine_filtro)
    df_food = df_food_completo[mask].copy()
    
    df_spese_generali_completo["Data_DT"] = pd.to_datetime(df_spese_generali_completo["DataDocumento"], errors='coerce').dt.date
    mask_spese = (df_spese_generali_completo["Data_DT"] >= data_inizio_filtro) & (df_spese_generali_completo["Data_DT"] <= data_fine_filtro)
    df_spese_generali = df_spese_generali_completo[mask_spese].copy()
    
    # Calcola giorni nel periodo
    giorni = (data_fine_filtro - data_inizio_filtro).days + 1
    
    # Stats globali: conta fatture PRIMA del filtro temporale (nel DF già pulito)
    num_fatture_totali_df = df_completo['FileOrigine'].nunique() if not df_completo.empty else 0
    num_righe_totali_df = len(df_completo)
    
    # Filtra df_completo per periodo (stesso filtro di df_food)
    df_completo["Data_DT"] = pd.to_datetime(df_completo["DataDocumento"], errors='coerce').dt.date
    mask_completo = (df_completo["Data_DT"] >= data_inizio_filtro) & (df_completo["Data_DT"] <= data_fine_filtro)
    df_completo_filtrato = df_completo[mask_completo]
    num_doc_filtrati = df_completo_filtrato['FileOrigine'].nunique()
    
    # Mostra info periodo con box ben visibile (stile simile ai box blu)
    info_testo = f"🗓️ {label_periodo} ({giorni} giorni) | 🍽️ Righe F&B: {len(df_food):,} | 📊 Righe Totali: {num_righe_totali_df:,} | 📄 Fatture: {num_doc_filtrati} di {num_fatture_totali_df}"
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                padding: 20px 25px; 
                border-radius: 12px; 
                border: 3px solid #f59e0b;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                margin-bottom: 20px;
                font-size: 15px;
                font-weight: 500;
                line-height: 1.8;
                transition: all 0.3s ease;">
        {info_testo}
    </div>
    """, unsafe_allow_html=True)
    
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
        <div style="background: #f8f9fa; border-left: 4px solid #43e97b;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">🏪 N. Fornitori Analizzati F&B</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">""" + str(num_fornitori) + """</h2>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #4facfe;
                    padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
                    height: 130px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 13px; margin: 0; color: #666; font-weight: 500;">🛒 Spesa Generale</p>
            <h2 style="font-size: 32px; margin: 8px 0 0 0; font-weight: bold; color: #1a1a1a;">€ """ + f"{spesa_generale:.2f}" + """</h2>
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
                # Cambio schermata: pulisci riepilogo upload persistente
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    with col2:
        if st.button("🚨 ALERT\nARTICOLI (F&B)", key="btn_alert", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "alert" else "secondary"):
            if st.session_state.sezione_attiva != "alert":
                st.session_state.sezione_attiva = "alert"
                st.session_state.is_loading = True
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    with col3:
        if st.button("📈 CATEGORIE\n(F&B)", key="btn_categorie", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "categorie" else "secondary"):
            if st.session_state.sezione_attiva != "categorie":
                st.session_state.sezione_attiva = "categorie"
                st.session_state.is_loading = True
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    with col4:
        if st.button("🚚 FORNITORI\n(F&B)", key="btn_fornitori", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "fornitori" else "secondary"):
            if st.session_state.sezione_attiva != "fornitori":
                st.session_state.sezione_attiva = "fornitori"
                st.session_state.is_loading = True
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
                st.rerun()
    
    with col5:
        if st.button("🏢 SPESE\nGENERALI", key="btn_spese", use_container_width=True,
                     type="primary" if st.session_state.sezione_attiva == "spese" else "secondary"):
            if st.session_state.sezione_attiva != "spese":
                st.session_state.sezione_attiva = "spese"
                st.session_state.is_loading = True
                if 'last_upload_summary' in st.session_state:
                    del st.session_state.last_upload_summary
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
        if ('df_completo_filtrato' not in locals()) or ('df_food' not in locals()) or ('df_spese_generali' not in locals()) or df_completo_filtrato.empty:
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
        
        # ⭐ NUOVO: COLONNA FONTE - Origine categorizzazione (UI-only, NON salvata in DB)
        if 'Descrizione' in df_editor.columns:
            # DIZIONARIO (📚)
            righe_diz = st.session_state.get('righe_keyword_appena_categorizzate', [])
            diz_set = set(str(d).strip() for d in righe_diz)
            
            # AI BATCH (🤖)
            righe_ai = st.session_state.get('righe_ai_appena_categorizzate', [])
            ai_set = set(str(d).strip() for d in righe_ai)
            
            # MANUALE (✋)
            righe_man = st.session_state.get('righe_modificate_manualmente', [])
            man_set = set(str(d).strip() for d in righe_man)
            
            # MEMORIA (🧠)
            righe_mem = st.session_state.get('righe_memoria_appena_categorizzate', [])
            mem_set = set(str(d).strip() for d in righe_mem)
            
            # Priorità: ✋ > 🤖 > 📚 > 🧠 > vuoto
            df_editor['Fonte'] = df_editor['Descrizione'].apply(
                lambda d: '✋' if str(d).strip() in man_set else
                          '🤖' if str(d).strip() in ai_set else
                          '📚' if str(d).strip() in diz_set else
                          '🧠' if str(d).strip() in mem_set else ''
            )
            logger.info(f"✅ Colonna Fonte: {len(man_set)} manuali, {len(ai_set)} AI, {len(diz_set)} dizionario, {len(mem_set)} memoria")
        
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
        
        # 🧠 AGGIUNGI ICONA AI alle righe appena categorizzate (solo sessione corrente)
        # TEMPORANEO: Icone AI 🧠 disabilitate - causavano mismatch dropdown
        # PROBLEMA: Aggiungere emoji trasforma "MATERIALE DI CONSUMO" in "MATERIALE DI CONSUMO 🧠"
        # Il dropdown ha opzioni ["MATERIALE DI CONSUMO", "PESCE", ...] senza emoji
        # Streamlit bug: se valore non è nelle options → cella bianca/vuota
        # LOG EVIDENZA: "⚠️ Categoria 'MATERIALE DI CONSUMO 🧠' non nelle opzioni! → 'Da Classificare'"
        # RISULTATO: 26/26 celle bianche dopo categorizzazione AI
        #
        # # ORA che le celle vuote sono state convertite in "Da Classificare", possiamo aggiungere l'icona
        # righe_ai = st.session_state.get('righe_ai_appena_categorizzate', [])
        # 
        # if righe_ai and 'Categoria' in df_editor.columns and 'Descrizione' in df_editor.columns:
        #     # Converti lista in set per lookup O(1)
        #     righe_ai_set = set(righe_ai)
        #     for idx, row in df_editor.iterrows():
        #         desc = str(row['Descrizione']).strip()
        #         cat = str(row['Categoria']).strip()
        #         # Aggiungi icona solo se: descrizione è in righe_ai E categoria è valida (non vuota e non "Da Classificare")
        #         if desc in righe_ai_set and cat and cat != 'Da Classificare':
        #             df_editor.at[idx, 'Categoria'] = f"{cat} 🧠"
        #             logger.debug(f"🧠 Icona aggiunta a: {desc[:30]}... → {cat} 🧠")
        
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

        num_righe = len(df_editor)
        
        # ============================================================
        # 📦 CHECKBOX RAGGRUPPAMENTO PRODOTTI
        # ============================================================
        vista_aggregata = st.checkbox(
            "📦 Raggruppa prodotti unici", 
            value=False,  # ← DEFAULT OFF per rollout sicuro
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
        
        # 🚫 RIMUOVI colonna LISTINO dalla visualizzazione
        if 'PrezzoStandard' in df_editor_paginato.columns:
            df_editor_paginato = df_editor_paginato.drop(columns=['PrezzoStandard'])
        elif 'Listino' in df_editor_paginato.columns:
            df_editor_paginato = df_editor_paginato.drop(columns=['Listino'])
        elif 'LISTINO' in df_editor_paginato.columns:
            df_editor_paginato = df_editor_paginato.drop(columns=['LISTINO'])

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
            "Fonte": st.column_config.TextColumn(
                "Fonte",
                help="📚=dizionario | 🤖=AI batch | ✋=modifica manuale | (vuoto)=storica",
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
        
        edited_df = st.data_editor(
            df_editor_paginato,
            column_config=column_config_dict,
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
            
            /* 🧠 COLORAZIONE ROSA per righe classificate da AI */
            [data-testid="stDataFrame"] [data-testid="stDataFrameCell"] {
                transition: background-color 0.3s ease;
            }
            /* Nota: Streamlit data_editor non supporta styling condizionale per riga basato su valore cella.
               La colorazione visiva principale sarà l'icona 🧠 nella colonna Stato. */
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
            <div style="background-color: #E3F2FD; padding: 15px 20px; border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 20px; width: fit-content;">
                <p style="color: #1565C0; font-size: 16px; font-weight: bold; margin: 0; white-space: nowrap;">
                    📋 N. Righe: {num_righe:,} | 💰 Totale: € {totale_tabella:.2f}
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        with col_ord:
            # Selettore ordinamento affiancato al box blu
            st.markdown('<p style="margin-top: 8px; font-size: 14px; font-weight: 500;">Seleziona ordinamento per export</p>', unsafe_allow_html=True)
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
                [data-testid="stDownloadButton"] button {
                    border: none !important;
                    outline: none !important;
                    box-shadow: none !important;
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
                    label="📊 EXCEL",
                    data=excel_buffer.getvalue(),
                    file_name=f"dettaglio_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_excel_dettaglio",
                    type="primary",
                    use_container_width=False
                )
            except Exception as e:
                st.error(f"Errore: {e}")
            
            st.markdown('</div>', unsafe_allow_html=True)


        if salva_modifiche:
            try:
                user_id = st.session_state.user_data["id"]
                user_email = st.session_state.user_data.get("email", "unknown")
                modifiche_effettuate = 0
                
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
                    
                    # 📦 AVVISO MODALITÀ AGGREGATA
                    if vista_aggregata:
                        st.warning("📦 **Modalità Raggruppata Attiva:** Le modifiche alle categorie verranno applicate a TUTTE le righe con la stessa descrizione nel database.")
                    
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
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"Errore conversione prezzo_standard: {e}")
                            
                            # ✋ TRACCIAMENTO MODIFICA MANUALE
                            # Se categoria cambiata dall'utente → salva in memoria
                            categoria_modificata = (vecchia_cat and vecchia_cat != nuova_cat) or \
                                                 (not vecchia_cat and nuova_cat != 'Da Classificare')
                            if categoria_modificata:
                                logger.info(f"✋ MANUALE: '{descrizione[:40]}' modificato da '{vecchia_cat or "vuoto"}' → {nuova_cat}")
                                
                                # ⭐ NUOVO: Traccia modifica manuale per colonna Fonte
                                if 'righe_modificate_manualmente' not in st.session_state:
                                    st.session_state.righe_modificate_manualmente = []
                                if descrizione not in st.session_state.righe_modificate_manualmente:
                                    st.session_state.righe_modificate_manualmente.append(descrizione)
                            
                            # 🔄 MODIFICA BATCH: Se categoria è cambiata, aggiorna TUTTE le righe con stessa descrizione
                            # In vista aggregata: SEMPRE batch update (1 riga vista = N righe DB)
                            # In vista normale: batch update solo se categoria diversa dalla precedente
                            esegui_batch_update = vista_aggregata or (vecchia_cat and vecchia_cat != nuova_cat)
                            
                            if esegui_batch_update:
                                if vista_aggregata:
                                    logger.info(f"📦 AGGREGATA - BATCH UPDATE: '{descrizione}' → {nuova_cat}")
                                else:
                                    logger.info(f"🔄 BATCH UPDATE: '{descrizione}' {vecchia_cat} → {nuova_cat}")
                                
                                # 🔍 DIAGNOSI: Log dettagliato descrizione per debug
                                from utils.text_utils import normalizza_stringa
                                desc_normalized = normalizza_stringa(descrizione)
                                logger.info(f"🔍 DEBUG UPDATE:")
                                logger.info(f"   📝 Descrizione raw (edited_df): '{descrizione}'")
                                logger.info(f"   🔧 Descrizione normalizzata: '{desc_normalized}'")
                                logger.info(f"   🏷️  Categoria nuova: '{nuova_cat}'")
                                logger.info(f"   📊 User ID: {user_id}")
                                
                                # Aggiorna tutte le righe con stessa descrizione (normalizzata)
                                ristorante_id = st.session_state.get('ristorante_id')
                                query_update_batch = supabase.table("fatture").update(update_data).eq(
                                    "user_id", user_id
                                ).eq(
                                    "descrizione", descrizione
                                )
                                if ristorante_id:
                                    query_update_batch = query_update_batch.eq("ristorante_id", ristorante_id)
                                result = query_update_batch.execute()
                                
                                righe_aggiornate = len(result.data) if result.data else 0
                                logger.info(f"✅ BATCH: {righe_aggiornate} righe aggiornate per '{descrizione[:40]}'")
                                
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
                                            ).ilike("descrizione", f"%{pattern_search}%").limit(5)
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
                                
                                # ✅ Salva correzione (memoria DB + cache, no file locale)
                                salva_correzione_in_memoria_globale(
                                    descrizione=descrizione,
                                    vecchia_categoria=vecchia_cat,
                                    nuova_categoria=nuova_cat,
                                    user_email=user_email
                                )
                                
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
                                result = query_update_single.execute()
                                
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
                    
                    # ⭐ NUOVO: Reset tracking fonte categorizzazione dopo salvataggio
                    st.session_state.pop('righe_ai_appena_categorizzate', None)
                    st.session_state.pop('righe_keyword_appena_categorizzate', None)
                    st.session_state.pop('righe_modificate_manualmente', None)
                    logger.info("🔄 Reset tracking fonte categorizzazione dopo salvataggio")
                    
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
        if ('df_completo_filtrato' not in locals()) or df_completo_filtrato.empty:
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
            
            # CALCOLA ALERT (SOLO F&B) - USA DATI FILTRATI PER PERIODO
            df_alert = calcola_alert(df_completo_filtrato, soglia_aumento, filtro_prodotto)
            
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
                    min-height: 130px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                ">
                    <div style="font-size: 14px; color: #666; font-weight: 500;">Sconti Applicati</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0;">{} righe</div>
                    <div style="font-size: 16px; color: #dc3545; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">-€{:.2f}</div>
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
                    min-height: 130px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                ">
                    <div style="font-size: 14px; color: #666; font-weight: 500;">Omaggi Ricevuti</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0;">{} righe</div>
                    <div style="font-size: 14px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Prodotti gratuiti</div>
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
                    min-height: 130px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                ">
                    <div style="font-size: 14px; color: #666; font-weight: 500;">Totale Risparmiato</div>
                    <div style="font-size: 24px; font-weight: bold; margin: 8px 0; color: #28a745;">€{:.2f}</div>
                    <div style="font-size: 12px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{}">{}</div>
                </div>
                """.format(totale_risparmiato if totale_risparmiato > 0 else 0, label_periodo, label_periodo), 
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
            col_left, col_right = st.columns([5, 1])
            
            with col_left:
                st.markdown(f"""
                <div style="background-color: #E3F2FD; padding: 15px 20px; border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 20px; width: fit-content;">
                    <p style="color: #1565C0; font-size: 16px; font-weight: bold; margin: 0; white-space: nowrap;">
                        📋 N. Righe: {num_righe_cat:,} | 💰 Totale: € {totale_cat:.2f}
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            with col_right:
                st.markdown('<div style="text-align: right;">', unsafe_allow_html=True)
                
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        border-radius: 6px !important;
                        border: none !important;
                        outline: none !important;
                        box-shadow: none !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_cat = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_cat, engine='openpyxl') as writer:
                    pivot_cat.to_excel(writer, index=False, sheet_name='Categorie')
                
                st.download_button(
                    label="📊 EXCEL",
                    data=excel_buffer_cat.getvalue(),
                    file_name=f"categorie_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_categorie",
                    type="primary",
                    use_container_width=False
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
            
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
            col_left, col_right = st.columns([5, 1])
            
            with col_left:
                st.markdown(f"""
                <div style="background-color: #E3F2FD; padding: 15px 20px; border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 20px; width: fit-content;">
                    <p style="color: #1565C0; font-size: 16px; font-weight: bold; margin: 0; white-space: nowrap;">
                        📋 N. Righe: {num_righe_forn:,} | 💰 Totale: € {totale_forn:.2f}
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            with col_right:
                st.markdown('<div style="text-align: right;">', unsafe_allow_html=True)
                
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        border-radius: 6px !important;
                        border: none !important;
                        outline: none !important;
                        box-shadow: none !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_forn = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_forn, engine='openpyxl') as writer:
                    pivot_forn.to_excel(writer, index=False, sheet_name='Fornitori')
                
                st.download_button(
                    label="📊 EXCEL",
                    data=excel_buffer_forn.getvalue(),
                    file_name=f"fornitori_mensile_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_fornitori",
                    type="primary",
                    use_container_width=False
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
            
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
            st.markdown("#### 📊 Spesa per Categoria mensile")
            
            # Aggiungi colonna Mese con formato italiano
            df_spese_con_mese = df_spese_generali.copy()
            df_spese_con_mese['Data_DT'] = pd.to_datetime(df_spese_con_mese['DataDocumento'], errors='coerce')
            
            mesi_ita = {
                1: 'GENNAIO', 2: 'FEBBRAIO', 3: 'MARZO', 4: 'APRILE',
                5: 'MAGGIO', 6: 'GIUGNO', 7: 'LUGLIO', 8: 'AGOSTO',
                9: 'SETTEMBRE', 10: 'OTTOBRE', 11: 'NOVEMBRE', 12: 'DICEMBRE'
            }
            
            df_spese_con_mese['Mese'] = df_spese_con_mese['Data_DT'].apply(
                lambda x: f"{mesi_ita[x.month]} {x.year}" if pd.notna(x) else ''
            )
            
            df_spese_con_mese['Mese_Ordine'] = df_spese_con_mese['Data_DT'].apply(
                lambda x: f"{x.year}-{x.month:02d}" if pd.notna(x) else ''
            )
            
            # Pivot: Categorie × Mesi
            pivot_cat = df_spese_con_mese.pivot_table(
                index='Categoria',
                columns='Mese',
                values='TotaleRiga',
                aggfunc='sum',
                fill_value=0
            )
            
            # Ordina colonne cronologicamente
            mese_ordine_map = df_spese_con_mese[['Mese', 'Mese_Ordine']].drop_duplicates()
            mese_ordine_map = mese_ordine_map[mese_ordine_map['Mese'] != '']
            mese_ordine_map = dict(zip(mese_ordine_map['Mese'], mese_ordine_map['Mese_Ordine']))
            
            cols_sorted = sorted(list(pivot_cat.columns), key=lambda x: mese_ordine_map.get(x, x))
            pivot_cat = pivot_cat[cols_sorted]
            
            # Aggiungi colonna TOTALE
            pivot_cat['TOTALE'] = pivot_cat.sum(axis=1)
            
            # Ordina per totale decrescente
            pivot_cat = pivot_cat.sort_values('TOTALE', ascending=False)
            
            # Formatta come €
            pivot_cat_display = pivot_cat.map(lambda x: f"€ {x:,.2f}")
            
            num_righe_spese_cat = len(pivot_cat_display)
            altezza_spese_cat = max(num_righe_spese_cat * 35 + 50, 200)
            st.dataframe(pivot_cat_display, use_container_width=True, height=altezza_spese_cat)
            
            # Box + Excel per Categorie
            totale_cat_spese = pivot_cat['TOTALE'].sum()
            col_left, col_right = st.columns([5, 1])
            
            with col_left:
                st.markdown(f"""
                <div style="background-color: #E3F2FD; padding: 15px 20px; border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 20px; width: fit-content;">
                    <p style="color: #1565C0; font-size: 16px; font-weight: bold; margin: 0; white-space: nowrap;">
                        📋 N. Righe: {num_righe_spese_cat:,} | 💰 Totale: € {totale_cat_spese:.2f}
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            with col_right:
                st.markdown('<div style="text-align: right;">', unsafe_allow_html=True)
                
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        border-radius: 6px !important;
                        border: none !important;
                        outline: none !important;
                        box-shadow: none !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_spese_cat = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_spese_cat, engine='openpyxl') as writer:
                    pivot_cat.to_excel(writer, sheet_name='Categorie_Spese')
                
                st.download_button(
                    label="📊 EXCEL",
                    data=excel_buffer_spese_cat.getvalue(),
                    file_name=f"spese_categorie_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_spese_categorie",
                    type="primary",
                    use_container_width=False
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            # ============================================
            # TABELLA 2: FORNITORI × MESI
            # ============================================
            st.markdown("#### 🏪 Spesa per Fornitore mensile")
            
            # Pivot: Fornitori × Mesi (usa stesso df con mesi formattati)
            pivot_forn = df_spese_con_mese.pivot_table(
                index='Fornitore',
                columns='Mese',
                values='TotaleRiga',
                aggfunc='sum',
                fill_value=0
            )
            
            # Ordina colonne cronologicamente (usa stesso mapping)
            cols_sorted_forn = sorted(list(pivot_forn.columns), key=lambda x: mese_ordine_map.get(x, x))
            pivot_forn = pivot_forn[cols_sorted_forn]
            
            # Aggiungi colonna TOTALE
            pivot_forn['TOTALE'] = pivot_forn.sum(axis=1)
            
            # Ordina per totale decrescente
            pivot_forn = pivot_forn.sort_values('TOTALE', ascending=False)
            
            # Formatta come €
            pivot_forn_display = pivot_forn.map(lambda x: f"€ {x:,.2f}")
            
            num_righe_spese_forn = len(pivot_forn_display)
            altezza_spese_forn = max(num_righe_spese_forn * 35 + 50, 200)
            st.dataframe(pivot_forn_display, use_container_width=True, height=altezza_spese_forn)
            
            # Box + Excel per Fornitori
            totale_forn_spese = pivot_forn['TOTALE'].sum()
            col_left, col_right = st.columns([5, 1])
            
            with col_left:
                st.markdown(f"""
                <div style="background-color: #E3F2FD; padding: 15px 20px; border-radius: 8px; border: 2px solid #2196F3; margin-bottom: 20px; width: fit-content;">
                    <p style="color: #1565C0; font-size: 16px; font-weight: bold; margin: 0; white-space: nowrap;">
                        📋 N. Righe: {num_righe_spese_forn:,} | 💰 Totale: € {totale_forn_spese:.2f}
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            with col_right:
                st.markdown('<div style="text-align: right;">', unsafe_allow_html=True)
                
                st.markdown("""
                    <style>
                    [data-testid="stDownloadButton"] button {
                        background-color: #28a745 !important;
                        color: white !important;
                        font-weight: 600 !important;
                        border-radius: 6px !important;
                        border: none !important;
                        outline: none !important;
                        box-shadow: none !important;
                    }
                    [data-testid="stDownloadButton"] button:hover {
                        background-color: #218838 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                excel_buffer_spese_forn = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_spese_forn, engine='openpyxl') as writer:
                    pivot_forn.to_excel(writer, sheet_name='Fornitori_Spese')
                
                st.download_button(
                    label="📊 EXCEL",
                    data=excel_buffer_spese_forn.getvalue(),
                    file_name=f"spese_fornitori_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_spese_fornitori",
                    type="primary",
                    use_container_width=False
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
            
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
try:
    user_id = st.session_state.user_data["id"]
except (KeyError, TypeError, AttributeError):
    logger.critical("❌ user_data corrotto o mancante campo 'id' - FORZA LOGOUT")
    st.session_state.logged_in = False
    st.error("⚠️ Sessione invalida. Effettua nuovamente il login.")
    st.rerun()


with st.spinner("⏳ Caricamento dati..."):
    df_cache = carica_e_prepara_dataframe(user_id)


# 🗂️ GESTIONE FATTURE - Eliminazione (prima del file uploader)
if not df_cache.empty:
    with st.expander("🗂️ Gestione Fatture Caricate (Elimina)", expanded=False):
        
        # ========================================
        # BOX STATISTICHE
        # ========================================
        try:
            stats_db = get_fatture_stats(user_id)
        except Exception as e:
            logger.error(f"Errore get_fatture_stats: {e}")
            st.error("❌ Errore caricamento statistiche")
            stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}
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
        # Solo admin e impersonificati vedono eliminazione massiva
        if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
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
                        st.cache_data.clear()  # Reset cache Streamlit (prima chiamata)
                        
                        # 🔥 RESET SESSION: Reinizializza set vuoti (non solo clear)
                        st.session_state.files_processati_sessione = set()
                        st.session_state.files_con_errori = set()
                        
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
                        except Exception as e:
                            logger.warning(f"⚠️ Errore clear cache_resource durante hard reset: {e}")
                        
                        progress.progress(80, text="Reset session state...")
                        
                        # HARD RESET: Rimuovi session state specifici (mantieni login)
                        keys_to_remove = [k for k in st.session_state.keys() 
                                         if k not in ['user_data', 'logged_in', 'check_conferma_svuota']]
                        for key in keys_to_remove:
                            st.session_state.pop(key, None)  # Sicuro: niente errore se non esiste
                        
                        # 🔥 ULTIMA PULIZIA CACHE: Doppia invalidazione per sicurezza
                        st.cache_data.clear()
                        invalida_cache_memoria()
                        
                        progress.progress(100, text="Completato!")
                        time.sleep(0.3)
                        
                        # Mostra risultato DENTRO lo spinner (indentazione corretta)
                        if result["success"]:
                            st.success(f"✅ **{result['fatture_eliminate']} fatture** eliminate! ({result['righe_eliminate']} prodotti)")
                            st.info("🧹 **Hard Reset completato**: Cache, JSON locali e session state puliti")
                            
                            # LOG AUDIT: Verifica immediata post-delete
                            try:
                                verify_query = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id)
                                verify_query = add_ristorante_filter(verify_query)
                                verify = verify_query.execute()
                                num_residue = len(verify.data) if verify.data else 0
                                if num_residue == 0:
                                    logger.info(f"✅ DELETE VERIFIED: 0 righe rimaste per user_id={user_id}")
                                    st.success(f"✅ Verifica: Database pulito (0 righe)")
                                else:
                                    logger.error(f"⚠️ DELETE INCOMPLETE: {num_residue} righe ancora presenti per user_id={user_id}")
                                    st.error(f"⚠️ Attenzione: {num_residue} righe ancora presenti (possibile problema RLS)")
                            except Exception as e:
                                logger.exception("Errore verifica post-delete")
                            
                            # Reset checkbox
                            if 'check_conferma_svuota' in st.session_state:
                                del st.session_state.check_conferma_svuota
                            
                            # 🔥 FLAG HIDE UPLOADER: Nascondi uploader dopo eliminazione totale
                            st.session_state.hide_uploader = True
                            st.session_state.files_processati_sessione = set()
                            st.cache_data.clear()
                            st.success("✅ Eliminato tutto!")
                            st.rerun()
                        else:
                            st.error(f"❌ Errore: {result['error']}")
            
            st.markdown("---")
        
        # ========== ELIMINA SINGOLA FATTURA ==========
        st.markdown("### 🗑️ Elimina Fattura Singola")
        
        # Usa fatture_summary già creato sopra
        if len(fatture_summary) > 0:
            # Crea opzioni dropdown con dict per passare tutti i dati
            fatture_options = []
            for idx, row in fatture_summary.iterrows():
                fatture_options.append({
                    'File': row['File'],
                    'Fornitore': row['Fornitore'],
                    'NumProdotti': int(row['NumProdotti']),
                    'Totale': row['Totale'],
                    'Data': row['Data']
                })
            
            fattura_selezionata = st.selectbox(
                "Seleziona fattura da eliminare:",
                options=fatture_options,
                format_func=lambda x: f"📄 {x['File']} - {x['Fornitore']} (📅 {x['Data']}, 📦 {x['NumProdotti']} prodotti, 💰 €{x['Totale']:.2f})",
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



# === GESTIONE VISIBILITÀ UPLOADER ===
if st.session_state.get("hide_uploader", False):
    st.warning("⚠️ Hai eliminato tutte le fatture.")
    if st.button("🔄 Ricarica Pagina", key="refresh_page_btn"):
        st.session_state.hide_uploader = False
        st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
        st.components.v1.html(
            """
            <script>
            window.parent.location.reload();
            </script>
            """,
            height=0
        )
    uploaded_files = None  # Fix NameError: uploaded_files sempre definito
else:
    # ============================================================
    # CHECK LIMITE RIGHE GLOBALE (STEP 1 - Performance)
    # ============================================================
    # Configurazione limiti
    MAX_RIGHE_GLOBALE = 100000  # 100k righe per sicurezza
    MAX_RIGHE_BATCH = 500        # Max righe per batch upload
    BATCH_FILE_SIZE = 20         # Max 20 file per batch
    
    # Recupera user_id da session state (già definito sopra ma riusato qui per chiarezza)
    try:
        user_id = st.session_state.user_data["id"]
    except (KeyError, TypeError):
        st.error("❌ Sessione non valida. Effettua il login.")
        logger.critical("user_data mancante in sezione upload")
        st.stop()
    
    try:
        stats_db = get_fatture_stats(user_id)
        righe_totali = stats_db['num_righe']
    except Exception as e:
        logger.error(f"Errore stats durante controllo limite: {e}")
        righe_totali = 0
    
    # Controllo prima elaborazione
    if righe_totali >= MAX_RIGHE_GLOBALE:
        st.error(f"⚠️ Limite database raggiunto ({righe_totali:,} righe). Elimina vecchie fatture.")
        st.warning("Usa 'Gestione Fatture Caricate' sopra per eliminare")
        st.stop()  # Blocca file_uploader
    
    # Warning se vicino al limite (80%)
    elif righe_totali >= MAX_RIGHE_GLOBALE * 0.8:
        percentuale = (righe_totali / MAX_RIGHE_GLOBALE * 100)
        st.warning(f"⚠️ Database quasi pieno: {righe_totali:,}/{MAX_RIGHE_GLOBALE:,} righe ({percentuale:.0f}%)")
    
    uploaded_files = st.file_uploader(
        "Carica file XML, PDF o Immagini",
        accept_multiple_files=True,
        type=['xml', 'pdf', 'jpg', 'jpeg', 'png'],
        label_visibility="collapsed",
        key=f"file_uploader_{st.session_state.get('uploader_key', 0)}"  # Chiave dinamica per reset
    )
    
    # 🧠 RESET ICONE AI al nuovo caricamento (solo session_state, niente DB)
    if uploaded_files and len(uploaded_files) > 0:
        current_upload_ids = [f.name for f in uploaded_files]
        ultimo_upload = st.session_state.get('ultimo_upload_ids', [])
        
        # Rilevamento nuovo caricamento (file diversi)
        if current_upload_ids != ultimo_upload:
            # Reset solo session_state (no query DB costosa)
            if 'righe_ai_appena_categorizzate' in st.session_state:
                st.session_state.righe_ai_appena_categorizzate = []
            logger.info("🧹 Reset icone AI - nuovo caricamento rilevato")
            st.session_state.ultimo_upload_ids = current_upload_ids
            # Pulisce riepilogo ultimo upload all'inizio di un nuovo caricamento
            if 'last_upload_summary' in st.session_state:
                del st.session_state.last_upload_summary

    # ============================================================
    # INIZIALIZZAZIONE SET ERRORI (prevenzione loop)
    # ============================================================
    if 'files_con_errori' not in st.session_state:
        st.session_state.files_con_errori = set()

    # Bottone Reset Upload (solo admin)
    if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
        if st.button("🔄 Reset upload (pulisci cache sessione)", key="reset_upload_cache"):
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
            st.session_state.files_errori_report = {}
            # 🔥 Rimuovi flag force_empty per sbloccare caricamento
            if 'force_empty_until_upload' in st.session_state:
                del st.session_state.force_empty_until_upload
            st.success("✅ Cache pulita! Puoi ricaricare i file.")
            st.rerun()


if 'files_processati_sessione' not in st.session_state:
    st.session_state.files_processati_sessione = set()

if 'files_con_errori' not in st.session_state:
    st.session_state.files_con_errori = set()

if 'files_errori_report' not in st.session_state:
    st.session_state.files_errori_report = {}  # Dizionario persistente per mostrare report anche dopo rerun


# ============================================================
# AUTO-PULIZIA: Se non ci sono file caricati ma ci sono errori nel report,
# significa che l'utente ha rimosso i file → pulisci automaticamente
# ============================================================
if not uploaded_files and len(st.session_state.files_errori_report) > 0:
    logger.info("🧹 Auto-pulizia errori dopo rimozione file")
    st.session_state.files_con_errori = set()
    st.session_state.files_errori_report = {}
    st.rerun()  # Forza refresh per mostrare pagina pulita


# 🔥 GESTIONE FILE CARICATI
if uploaded_files:
    # 🚫 BLOCCO POST-DELETE: Se c'è flag force_empty, ignora file caricati
    if st.session_state.get('force_empty_until_upload', False):
        st.warning("⚠️ **Hai appena eliminato tutte le fatture.** Clicca su 'Reset upload' prima di caricare nuovi file.")
        st.info("💡 Usa il pulsante '🔄 Reset upload' sopra per sbloccare il caricamento.")
        st.stop()  # Blocca esecuzione per evitare ricaricamento automatico
    
    # QUERY FILE GIÀ CARICATI SU SUPABASE (con filtro userid obbligatorio)
    # ⚠️ IMPORTANTE: Query fresca senza cache per evitare dati stale dopo eliminazione
    # 🚀 OTTIMIZZAZIONE: Usa RPC function per ottenere solo file unici (evita 6000+ righe)
    try:
        # ✅ Usa user_id globale definito alla linea 3373 (no ridefinizione)
        ristorante_id = st.session_state.get('ristorante_id')
        
        # Tentativo 1: Usa RPC function se disponibile (query aggregata SQL lato server)
        try:
            # Prova a chiamare funzione RPC che restituisce file_origine DISTINCT
            rpc_params = {'p_user_id': user_id}
            if ristorante_id:
                rpc_params['p_ristorante_id'] = ristorante_id
            response_rpc = supabase.rpc('get_distinct_files', rpc_params).execute()
            file_su_supabase = {row["file_origine"] for row in response_rpc.data if row.get("file_origine") and row["file_origine"].strip()}
                
        except Exception as rpc_error:
            # Fallback: Query normale ma ottimizzata CON PAGINAZIONE
            logger.warning(f"RPC function non disponibile, uso query normale con paginazione: {rpc_error}")
            
            # ⚠️ CRITICO: Supabase restituisce di default solo 1000 righe!
            # Dobbiamo paginare per ottenere TUTTI i file
            file_su_supabase = set()
            page = 0
            page_size = 1000
            
            while True:
                offset = page * page_size
                ristorante_id = st.session_state.get('ristorante_id')
                query_files = (
                    supabase.table("fatture")
                    .select("file_origine", count="exact")
                    .eq("user_id", user_id)
                )
                if ristorante_id:
                    query_files = query_files.eq("ristorante_id", ristorante_id)
                response = query_files.range(offset, offset + page_size - 1).execute()
                
                if not response.data:
                    break
                    
                # Estrai file_origine da questa pagina
                for row in response.data:
                    if row.get("file_origine") and row["file_origine"].strip():
                        file_su_supabase.add(row["file_origine"])
                
                # Se questa pagina ha meno di page_size record, abbiamo finito
                if len(response.data) < page_size:
                    break
                    
                page += 1
        
        # 🔍 VERIFICA COERENZA: Se DB è vuoto ma session ha file, è un errore -> reset
        if len(file_su_supabase) == 0 and len(st.session_state.files_processati_sessione) > 0:
            logger.warning(f"⚠️ INCOERENZA RILEVATA: DB vuoto ma session ha {len(st.session_state.files_processati_sessione)} file -> RESET")
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
        
    except Exception as e:
        logger.exception(f"Errore caricamento file da DB per user_id={st.session_state.user_data.get('id')}")
        st.error(f"Errore caricamento file da DB: {e}")
        file_su_supabase = set()


    tutti_file_processati = st.session_state.files_processati_sessione | file_su_supabase
    
    # Calcola nomi caricati e duplicati in modo robusto
    uploaded_names = [f.name for f in uploaded_files]
    uploaded_unique = set(uploaded_names)
    duplicate_count = max(0, len(uploaded_names) - len(uploaded_unique))

    # Ricostruisci liste coerenti con i nomi unici
    visti = set()
    file_unici = []
    for file in uploaded_files:
        if file.name not in visti:
            file_unici.append(file)
            visti.add(file.name)
    
    # ============================================================
    # FIX: DEDUPLICAZIONE CORRETTA (solo contro DB reale)
    # ============================================================
    file_nuovi = []
    file_gia_processati = []
    
    # � OTTIMIZZAZIONE: Skip file appena caricati usando session_state
    just_uploaded = st.session_state.get('just_uploaded_files', set())
    
    for file in file_unici:
        filename = file.name
        
        # Conta come già presente se appena caricato o già nel DB
        if filename in just_uploaded or filename in file_su_supabase:
            file_gia_processati.append(filename)
        # Protezione: Salta file che hanno già dato errore in questa sessione
        elif filename in st.session_state.get('files_con_errori', set()):
            continue
        else:
            file_nuovi.append(file)
    
    # Messaggio SOLO per ADMIN (interfaccia pulita per clienti)
    is_admin = st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False)
    
    # ============================================================
    # 🔥 FIX: Conserva info file appena caricati per messaggi corretti
    # ============================================================
    # Salva riferimento a just_uploaded PRIMA di pulirlo
    erano_just_uploaded = just_uploaded.copy() if just_uploaded else set()
    
    # NON pulire il flag subito - mantienilo per il ciclo di controllo messaggi
    # Verrà azzerato DOPO che abbiamo verificato i messaggi
    
    if is_admin:
        if file_nuovi:
            st.info(f"✅ **{len(file_nuovi)} nuove fatture** da elaborare")
    
    # ============================================================
    # GESTIONE MESSAGGI: Mostra TUTTI i messaggi rilevanti
    # (anche se ci sono file_nuovi, mostra comunque duplicati/già presenti)
    # Sopprimi se arriviamo da AVVIA AI (flag one-shot)
    # ============================================================
    if st.session_state.get('suppress_upload_messages_once', False):
        # Pulisci il flag per usare solo una volta
        st.session_state.suppress_upload_messages_once = False
    else:
        # Se NESSUN file nuovo E erano just_uploaded → silenzio (post-rerun di file già elaborati)
        if not file_nuovi and len(erano_just_uploaded) > 0:
            logger.info(f"⏭️ Skip messaggi: {len(erano_just_uploaded)} file erano just_uploaded")
        # Se ci sono file_gia_processati (indipendentemente da file_nuovi)
        # 🔇 RIMOSSO: Non mostrare messaggio "X fatture già presenti nel database"
        elif file_gia_processati and duplicate_count == 0:
            # Tutte le fatture (non elaborate) erano già nel database
            # (messaggio rimosso su richiesta utente - assolutamente non desiderato)
            pass
        # Se ci sono solo duplicati nell'upload stesso
        elif duplicate_count and not file_gia_processati:
            num = duplicate_count
            sing_plur = "fattura duplicata" if num == 1 else "fatture duplicate"
            st.warning(f"⚠️ {num} {sing_plur} nell'upload - carica file diversi")
        # Se ci sono ENTRAMBI duplicati e già presenti
        elif file_gia_processati and duplicate_count:
            # RIMOSSO: Non mostrare mai il messaggio "X fatture già presenti o duplicate"
            # (messaggio rimosso su richiesta utente - non lo vuole vedere MAI)
            pass
    
    # ✅ Pulizia flag just_uploaded dopo aver mostrato/non mostrato i messaggi
    if erano_just_uploaded:
        st.session_state.just_uploaded_files = set()
    
    # ============================================================
    # ELABORAZIONE FILE NUOVI (solo se ci sono)
    # ============================================================
    
    # Riepilogo base per questa selezione (aggiornato dopo l'elaborazione)
    upload_summary = {
        'totale_selezionati': len(uploaded_names),
        'gia_presenti': len({n for n in uploaded_unique if (n in file_su_supabase or n in erano_just_uploaded)}),
        'duplicati_upload': duplicate_count,
        'nuovi_da_elaborare': len(file_nuovi),
        'caricate_successo': 0,
        'errori': 0
    }

    if file_nuovi:
        # Crea placeholder per loading AI
        upload_placeholder = st.empty()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Mostra animazione AI
            mostra_loading_ai(upload_placeholder, f"Analisi AI di {len(file_nuovi)} Fatture")
            
            # Contatori per statistiche DETTAGLIATE (GLOBALI - fuori batch)
            file_processati = 0
            righe_totali = 0
            salvati_supabase = 0
            salvati_json = 0
            errori = []
            file_ok = []
            file_errore = {}  # {nome_file: messaggio_errore}
            
            total_files = len(file_nuovi)
            
            # ============================================================
            # BATCH PROCESSING - 20 file alla volta (evita memoria piena)
            # ============================================================
            BATCH_SIZE = BATCH_FILE_SIZE  # Usa costante definita sopra (20)
            
            # Loop batch invisibile
            for batch_start in range(0, total_files, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_files)
                batch_corrente = file_nuovi[batch_start:batch_end]
                
                # Elabora file nel batch corrente
                for idx_in_batch, file in enumerate(batch_corrente):
                    idx_globale = batch_start + idx_in_batch + 1
                    nome_file = file.name.lower()
                    
                    # Protezione loop: salta file già elaborati o con errori
                    if file.name in st.session_state.files_processati_sessione:
                        continue
                    
                    # 🔥 FIX BUG #3: Se file è in errori, skippa senza aggiungere a file_errore
                    # (errore già presente in files_errori_report, evita duplicati)
                    if file.name in st.session_state.get('files_con_errori', set()):
                        continue
                    
                    # Aggiorna progress GLOBALE
                    progress = idx_globale / total_files
                    progress_bar.progress(progress)
                    status_text.text(f"📄 Elaborazione {idx_globale}/{total_files}: {file.name[:40]}...")
                    
                    # Routing automatico per tipo file con TRY/EXCEPT ROBUSTO
                    try:
                        if nome_file.endswith('.xml'):
                            items = estrai_dati_da_xml(file)
                            
                            # ============================================================
                            # VALIDAZIONE P.IVA CESSIONARIO (Anti-abuso)
                            # ═══════════════════════════════════════════════════════════════
                            # VALIDAZIONE P.IVA MULTI-RISTORANTE (STEP 2)
                            # ═══════════════════════════════════════════════════════════════
                            # ⚠️ SKIP per admin e impersonazione (possono caricare qualsiasi fattura)
                            is_admin = st.session_state.get('user_is_admin', False)
                            is_impersonating = st.session_state.get('impersonating', False)
                            
                            if not is_admin and not is_impersonating:
                                # Estrai P.IVA dal cessionario (dalla prima riga - items è lista di dict)
                                piva_cessionario = None
                                if isinstance(items, list) and len(items) > 0:
                                    piva_cessionario = items[0].get('piva_cessionario')
                                elif isinstance(items, dict):
                                    piva_cessionario = items.get('piva_cessionario')
                                
                                # P.IVA ristorante ATTUALMENTE SELEZIONATO (multi-ristorante aware)
                                piva_attiva = st.session_state.get('partita_iva')
                                nome_ristorante_attivo = st.session_state.get('nome_ristorante', 'N/A')
                                
                                logger.info(f"🔍 Validazione P.IVA Multi-Ristorante - Attiva: {piva_attiva}, Fattura: {piva_cessionario}")
                                
                                # 🚫 CASO 1: Nessun ristorante/P.IVA configurato → BLOCCO TOTALE
                                if not piva_attiva:
                                    logger.warning(
                                        f"⚠️ UPLOAD BLOCCATO - User {st.session_state.get('user_data', {}).get('email')} "
                                        f"non ha ristorante/P.IVA attivo"
                                    )
                                    raise ValueError(
                                        f"🚫 NESSUN RISTORANTE ATTIVO\n\n"
                                        f"Il tuo account non ha ristoranti configurati o nessuna P.IVA registrata.\n"
                                        f"Contatta l'assistenza per completare la registrazione.\n\n"
                                        f"📧 supporto@envoicescan-ai.com"
                                    )
                                
                                # ✅ CASO 2: P.IVA presente → VALIDAZIONE STRICT MULTI-RISTORANTE
                                elif piva_attiva and piva_cessionario:
                                    piva_cessionario_norm = normalizza_piva(piva_cessionario)
                                    piva_attiva_norm = normalizza_piva(piva_attiva)
                                    
                                    if piva_cessionario_norm != piva_attiva_norm:
                                        # 🚫 BLOCCO: P.IVA non corrisponde al ristorante selezionato
                                        
                                        # Conta ristoranti disponibili
                                        num_ristoranti = len(st.session_state.get('ristoranti', []))
                                        
                                        msg_help = ""
                                        if num_ristoranti > 1:
                                            msg_help = f"\n\n💡 **Hai {num_ristoranti} ristoranti configurati.**\n   Seleziona il ristorante corretto dal menu laterale."
                                        else:
                                            msg_help = "\n\n📞 Hai più locali? Contatta supporto@envoicescan-ai.com"
                                        
                                        logger.warning(
                                            f"⚠️ UPLOAD BLOCCATO - User {st.session_state.get('user_data', {}).get('email')} "
                                            f"ha tentato upload con P.IVA {piva_cessionario} (ristorante attivo: {piva_attiva})"
                                        )
                                        raise ValueError(
                                            f"🚫 FATTURA NON VALIDA\n\n"
                                            f"**Fattura P.IVA:** `{piva_cessionario}`\n"
                                            f"**Ristorante attivo:** {nome_ristorante_attivo}\n"
                                            f"**P.IVA attiva:** `{piva_attiva}`\n"
                                            f"{msg_help}"
                                        )
                                    else:
                                        # ✅ P.IVA match: log successo
                                        logger.info(f"✅ Validazione OK: P.IVA {piva_attiva_norm} match per {nome_ristorante_attivo}")
                            
                            else:
                                # Admin/Impersonazione: log per debug (bypass validazione)
                                piva_cessionario = None
                                if isinstance(items, list) and len(items) > 0:
                                    piva_cessionario = items[0].get('piva_cessionario')
                                logger.debug(f"👨‍💼 Admin upload - P.IVA fattura: {piva_cessionario} (validazione bypassata)")
                            
                            
                        elif nome_file.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                            items = estrai_dati_da_scontrino_vision(file)
                        else:
                            raise ValueError("Formato non supportato")
                        
                        # Validazione risultato parsing
                        if items is None:
                            raise ValueError("Parsing ritornato None")
                        if len(items) == 0:
                            raise ValueError("Nessuna riga estratta - DataFrame vuoto")
                        
                        # Salva in memoria se trovati dati (SILENZIOSO)
                        result = salva_fattura_processata(file.name, items, silent=True)
                        
                        if result["success"]:
                            file_processati += 1
                            righe_totali += result["righe"]
                            if result["location"] == "supabase":
                                salvati_supabase += 1
                            elif result["location"] == "json":
                                salvati_json += 1
                            
                            # Rimuovi flag force empty: ci sono nuovi dati
                            if 'force_empty_until_upload' in st.session_state:
                                del st.session_state.force_empty_until_upload
                            
                            # Traccia successo
                            file_ok.append(file.name)
                            st.session_state.files_processati_sessione.add(file.name)
                            
                            # 🔥 FIX BUG #1: Rimuovi da files_con_errori se presente (file ora ha successo)
                            st.session_state.files_con_errori.discard(file.name)
                        else:
                            raise ValueError(f"Errore salvataggio: {result.get('error', 'Sconosciuto')}")
                    
                    except Exception as e:
                        # TRACCIA ERRORE DETTAGLIATO (silenzioso - solo log)
                        error_msg = str(e)[:150]
                        logger.exception(f"❌ Errore elaborazione {file.name}")
                        file_errore[file.name] = error_msg
                        errori.append(f"{file.name}: {error_msg}")
                        
                        # NON mostrare errore qui (evita duplicati) - verrà mostrato nel report finale
                        
                        # ============================================================
                        # 🔥 FIX BUG #2: NON aggiungere a files_processati_sessione
                        # altrimenti il file viene skippato per sempre e non può riprovare
                        # ============================================================
                        # st.session_state.files_processati_sessione.add(file.name)  # ❌ RIMOSSO
                        
                        # Inizializza set errori se non esiste
                        if 'files_con_errori' not in st.session_state:
                            st.session_state.files_con_errori = set()
                        
                        st.session_state.files_con_errori.add(file.name)
                        
                        # Salva anche in report persistente (per mostrarlo dopo download)
                        st.session_state.files_errori_report[file.name] = error_msg
                        
                        # Log upload event FAILED
                        try:
                            user_id = st.session_state.user_data.get("id")
                            user_email = st.session_state.user_data.get("email", "unknown")
                            error_stage = "PARSING" if file.name.endswith('.xml') else "VISION"
                            
                            log_upload_event(
                                user_id=user_id,
                                user_email=user_email,
                                file_name=file.name,
                                status="FAILED",
                                rows_parsed=0,
                                rows_saved=0,
                                error_stage=error_stage,
                                error_message=error_msg,
                                details={"exception_type": type(e).__name__}
                            )
                        except Exception as log_error:
                            logger.error(f"Errore logging failed event: {log_error}")
                        
                        # CONTINUA con il prossimo file invece di crashare
                        continue
                
                # ============================================================
                # PAUSA TRA BATCH (rate limit OpenAI + liberazione memoria)
                # ============================================================
                if batch_end < total_files:
                    time.sleep(2)  # 2 secondi tra batch per evitare rate limit
        
        except Exception as critical_error:
            # ERRORE CRITICO: ferma tutto ma mostra report
            logger.exception(f"❌ ERRORE CRITICO durante elaborazione batch")
            st.error(f"⚠️ ERRORE CRITICO: {str(critical_error)[:200]}")
        
        finally:
            # ============================================================
            # PULIZIA GARANTITA: rimuove loading anche in caso di crash
            # ============================================================
            upload_placeholder.empty()
            progress_bar.empty()
            status_text.empty()
        
        # ============================================
        # REPORT FINALE PULITO E PROFESSIONALE
        # ============================================
        
        # Usa il report persistente da session_state (rimane anche dopo rerun del download)
        if len(file_errore) > 0:
            # Aggiorna il report persistente con nuovi errori
            st.session_state.files_errori_report.update(file_errore)
        
        # Mostra report se ci sono errori persistenti
        if len(st.session_state.files_errori_report) > 0:
            # CI SONO ERRORI - Report compatto e immediato
            
            num_errori = len(st.session_state.files_errori_report)
            
            # Messaggio principale compatto
            st.error(f"❌ {num_errori} fattura{'e' if num_errori > 1 else ''} SCARTATA{'E' if num_errori > 1 else ''}")
            
            # Expander errori - PER TUTTI
            with st.expander("📋 Dettaglio Errori", expanded=True):
                for nome_file, errore in st.session_state.files_errori_report.items():
                    st.warning(f"**{nome_file}**")
                    st.caption(f"{errore[:200]}")
                
                st.markdown("")
                
                # Istruzioni per il cliente
                st.info("💡 **Clicca su 'Scarica Log e Azzera' e poi invia il file all'assistenza per risolvere il problema**")
                
                # Due bottoni: Scarica Log + Azzera Errori
                col_download, col_clear = st.columns([2, 1])
                
                with col_download:
                    error_log = "\n".join([f"{nome}: {err}" for nome, err in st.session_state.files_errori_report.items()])
                    st.download_button(
                        label="📥 Scarica Log",
                        data=error_log,
                        file_name=f"errori_upload_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        type="primary"
                    )
                
                with col_clear:
                    if st.button("✖️ Azzera", use_container_width=True, type="secondary"):
                        st.session_state.files_errori_report = {}
                        st.session_state.files_con_errori = set()  # 🔥 FIX: Pulisci ANCHE il set errori
                        logger.info("✅ Report errori azzerato manualmente")
                        st.rerun()
            
            # Separatore visivo prima del resto della pagina
            st.markdown("---")
        
        else:
            # TUTTO OK - Messaggio pulito per clienti, dettagliato per admin
            if is_admin:
                # Admin: Report dettagliato (in aggiunta al successo mostrato sopra)
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📄 File", file_processati)
                with col2:
                    st.metric("📊 Righe Totali", righe_totali)
                with col3:
                    location_text = "Supabase" if salvati_supabase > 0 else "JSON"
                    st.metric("💾 Storage", location_text)
            else:
                # Cliente: Messaggio già mostrato sopra prima del rerun
                # Mostra avviso per duplicati NELL'UPLOAD STESSO se ci sono
                if duplicate_count > 0:
                    sing_plur_dup = "fattura" if duplicate_count == 1 else "fatture"
                    sing_plur_ign = "ignorata" if duplicate_count == 1 else "ignorate"
                    st.warning(f"⚠️ {duplicate_count} {sing_plur_dup} duplicata nell'upload, {sing_plur_ign}")
            
            # Invalidazione cache e reset stati
            if file_processati > 0:
                # ✅ MOSTRA SUCCESSO PRIMA DEL RERUN per evitare che venga perso
                if file_processati == 1:
                    st.success(f"✅ 1 fattura caricata con successo!")
                else:
                    st.success(f"✅ {file_processati} fatture caricate con successo!")
                st.cache_data.clear()
                
                # Reset icone AI: nuove fatture = nuova sessione
                if 'righe_ai_appena_categorizzate' in st.session_state:
                    st.session_state.righe_ai_appena_categorizzate = []
                
                # Marca file come appena caricati per evitare falsi "già presenti" nel prossimo rerun
                st.session_state.just_uploaded_files = set([f.name for f in file_nuovi])

                # Aggiorna riepilogo e persistilo per la sessione
                upload_summary['caricate_successo'] = file_processati
                upload_summary['errori'] = len(st.session_state.files_errori_report)
                st.session_state.last_upload_summary = upload_summary
                
                # Breve pausa per mostrare il messaggio
                import time
                time.sleep(0.5)
                
                # Ricarica pagina con dati freschi
                st.rerun()
            else:
                # Nessuna fattura caricata con successo: salva comunque riepilogo
                upload_summary['caricate_successo'] = 0
                upload_summary['errori'] = len(st.session_state.files_errori_report)
                st.session_state.last_upload_summary = upload_summary

    else:
        # Nessun file nuovo: persistiamo comunque un riepilogo accurato
        st.session_state.last_upload_summary = upload_summary


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
    
    loading_placeholder.empty()
    
    # Mostra dashboard direttamente senza messaggi
    if not df_completo.empty:
        mostra_statistiche(df_completo)
    else:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


except Exception as e:
    loading_placeholder.empty()
    st.error(f"❌ Errore durante il caricamento: {e}")
    logger.exception("Errore caricamento dashboard")
