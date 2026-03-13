import streamlit as st
import pandas as pd
import os
import html as _html
import hmac as _hmac
from collections import defaultdict

import io
import time

# Import costanti da modulo separato
from config.constants import (
    CATEGORIE_SPESE_GENERALI,
    ADMIN_EMAILS,
    TRUNCATE_ERROR_DISPLAY,
    TRUNCATE_DESC_LOG,
    TRUNCATE_DESC_QUERY,
    UI_DELAY_SHORT,
    UI_DELAY_MEDIUM,
    UI_DELAY_LONG,
    UI_DELAY_QUICK,
    BATCH_RATE_LIMIT_DELAY,
    MAX_FILES_PER_UPLOAD,
    MAX_UPLOAD_TOTAL_MB,
    MAX_AI_CALLS_PER_DAY,
)

# Import utilities da moduli separati
from utils.text_utils import (
    normalizza_stringa,
    estrai_nome_categoria,
    escape_ilike as _escape_ilike
)

from utils.piva_validator import normalizza_piva

from utils.formatters import (
    calcola_prezzo_standard_intelligente,
    carica_categorie_da_db,
    log_upload_event,
    get_nome_base_file
)

from utils.ristorante_helper import add_ristorante_filter
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ui_helpers import load_css, load_js, render_pivot_mensile

# Import services
from services.ai_service import (
    carica_memoria_completa,
    invalida_cache_memoria,
    applica_correzioni_dizionario,
    salva_correzione_in_memoria_globale,
    salva_correzione_in_memoria_locale,
    classifica_con_ai,
    mostra_loading_ai,
    svuota_memoria_globale,
    set_global_memory_enabled,
    ottieni_categoria_prodotto
)

from services.auth_service import (
    verify_and_migrate_password,
    verifica_credenziali,
    invia_codice_reset,
    aggiorna_last_seen,
)

from services.invoice_service import (
    estrai_dati_da_xml,
    estrai_xml_da_p7m,
    estrai_dati_da_scontrino_vision,
    salva_fattura_processata,
)

from services.db_service import (
    carica_e_prepara_dataframe,
    ricalcola_prezzi_con_sconti,
    elimina_fattura_completa,
    elimina_tutte_fatture,
    get_fatture_stats
)


# ============================================================
# � OH YEAH! - VERSIONE 3.2 FINAL
# ============================================================


# ============================================
# FUNZIONE CALCOLO PREZZO STANDARDIZZATO
# ============================================

st.set_page_config(
    page_title="OH YEAH!",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# ============================================================
# GUARDIA ANTI-LOOP: Limita rerun consecutivi (safety net)
# ============================================================
_rerun_count = st.session_state.get('_rerun_guard', 0)
if _rerun_count > 8:
    import logging as _logging_guard
    _logging_guard.getLogger('fci_app').critical(f"🚨 RERUN LOOP DETECTED ({_rerun_count} consecutivi) - reset forzato")
    st.session_state._rerun_guard = 0
    st.session_state.force_reload = False
    st.error("⚠️ Rilevato loop di aggiornamento. La pagina è stata stabilizzata.")
    st.stop()
st.session_state._rerun_guard = _rerun_count + 1

# ============================================================
# SIDEBAR: NASCONDI SUBITO SE NON LOGGATO (anti-flash)
# ============================================================
if not st.session_state.get('logged_in', False):
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()

# CSS + JS branding (caricati da file statici)
load_css('branding.css')
load_css('layout.css')
load_js('branding.js')


# ============================================================
# 🔒 SISTEMA AUTENTICAZIONE CON RECUPERO PASSWORD
# ============================================================
from supabase import Client
from datetime import datetime, timedelta, timezone
import uuid as _uuid
import logging
import sys

# Logger con fallback cloud-compatible
logger = logging.getLogger('fci_app')
if not logger.handlers:
    try:
        # Prova filesystem locale (sviluppo)
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler('debug.log', maxBytes=50_000_000, backupCount=10, encoding='utf-8')
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
# Usa singleton centralizzato da services/__init__.py
from services import get_supabase_client

# Inizializza client globale (singleton)
try:
    supabase: Client = get_supabase_client()
except Exception as e:
    logger.exception("Connessione Supabase fallita")
    st.error("⛔ Servizio temporaneamente non disponibile. Riprova tra qualche minuto.")
    st.stop()


# Inizializza logged_in se non esiste
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Regole sessione
_SESSION_MAX_AGE_DAYS = 30
_SESSION_INACTIVITY_HOURS = 8
_LAST_SEEN_WRITE_THROTTLE_SECONDS = 300

# ============================================================
# COOKIE MANAGER - SESSIONE PERSISTENTE
# ============================================================
try:
    import extra_streamlit_components as stx
    _cookie_manager = stx.CookieManager(key="cookie_manager_app")
except Exception as _ce:
    _cookie_manager = None
    logger.warning(f"CookieManager non disponibile: {_ce}")

# ============================================
# IMPOSTA COOKIE IMPERSONAZIONE (richiesto da admin.py via session_state)
# ============================================
# admin.py imposta _set_impersonation_cookie prima di switch_page("app.py").
# Qui lo leggiamo e scriviamo il cookie browser, così sopravvive al F5.
if st.session_state.get('_set_impersonation_cookie') and _cookie_manager is not None:
    try:
        _cookie_manager.set(
            "impersonation_user_id",
            str(st.session_state['_set_impersonation_cookie']),
            expires_at=datetime.now() + timedelta(hours=12)
        )
    except Exception as _ice:
        logger.warning(f"Errore impostazione cookie impersonazione: {_ice}")
    del st.session_state['_set_impersonation_cookie']

# ============================================
# GESTIONE LOGOUT FORZATO VIA QUERY PARAMS
# ============================================
if st.query_params.get("logout") == "1":
    logger.warning("🚨 LOGOUT FORZATO via query params - pulizia sessione")
    # Token già invalidato da sidebar_helper, ma tenta anche qui come fallback
    try:
        _email_for_logout = st.session_state.get('user_data', {}).get('email')
        if _email_for_logout:
            supabase.table('users').update({
                'session_token': None,
                'session_token_created_at': None,
                'last_seen_at': None,
            }).eq('email', _email_for_logout).execute()
    except Exception:
        pass
    st.session_state.clear()
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.query_params.clear()
    st.rerun()

# Ripristina sessione da cookie solo se NON in stato di logout forzato
_force_logout_active = st.session_state.get('force_logout', False)

if not st.session_state.logged_in and not _force_logout_active and _cookie_manager is not None:
    try:
        _token_cookie = _cookie_manager.get("session_token")
        if _token_cookie:
            # Valida il token contro il DB - se è stato cancellato (logout), la query non trova nulla
            _resp_cookie = supabase.table("users").select("*").eq("session_token", _token_cookie).eq("attivo", True).execute()
            if _resp_cookie and _resp_cookie.data:
                _u = _resp_cookie.data[0]
                _now_utc = datetime.now(timezone.utc)

                # Verifica scadenza token sessione (30 giorni massimi)
                _token_created = _u.get('session_token_created_at')
                _token_expired = False
                if _token_created:
                    try:
                        _token_dt = datetime.fromisoformat(_token_created.replace('Z', '+00:00'))
                        if _token_dt.tzinfo is None:
                            _token_dt = _token_dt.replace(tzinfo=timezone.utc)
                        _token_expired = (_now_utc - _token_dt) > timedelta(days=_SESSION_MAX_AGE_DAYS)
                    except (ValueError, TypeError):
                        _token_expired = True
                else:
                    _token_expired = True

                # Verifica inattivita': se last_seen_at e' NULL usa fallback su session_token_created_at
                _last_seen_raw = _u.get('last_seen_at') or _token_created
                _inactive_expired = False
                if _last_seen_raw:
                    try:
                        _last_seen_dt = datetime.fromisoformat(_last_seen_raw.replace('Z', '+00:00'))
                        if _last_seen_dt.tzinfo is None:
                            _last_seen_dt = _last_seen_dt.replace(tzinfo=timezone.utc)
                        _inactive_expired = (_now_utc - _last_seen_dt) > timedelta(hours=_SESSION_INACTIVITY_HOURS)
                    except (ValueError, TypeError):
                        _inactive_expired = True
                else:
                    _inactive_expired = True

                if _token_expired or _inactive_expired:
                    # Token scaduto → invalida e richiedi login
                    supabase.table("users").update({
                        "session_token": None,
                        "session_token_created_at": None,
                        "last_seen_at": None,
                    }).eq("id", _u.get("id")).execute()
                    logger.info("🔒 Sessione scaduta (30gg o inattivita' 8h) - richiesto login")
                    st.session_state._cookie_checked = True
                else:
                    _u.pop('password_hash', None)  # Non esporre hash in session
                    st.session_state.logged_in = True
                    st.session_state.user_data = _u
                    st.session_state.partita_iva = _u.get('partita_iva')
                    st.session_state.created_at = _u.get('created_at')
                    if _u.get('email') in ADMIN_EMAILS:
                        st.session_state.user_is_admin = True
                    logger.info(f"✅ Sessione ripristinata da token per user_id={_u.get('id')}")
            else:
                # Token non valido (logout effettuato) → vai al login direttamente
                logger.info("🔒 Session token non valido o scaduto - richiesto login")
                st.session_state._cookie_checked = True
        elif not st.session_state.get('_cookie_checked', False):
            # Primo render: CookieManager non ha ancora letto i cookie, aspetta un ciclo
            st.session_state._cookie_checked = True
            st.markdown("""
                <div style='display:flex;align-items:center;justify-content:center;
                            height:80vh;flex-direction:column;gap:12px;'>
                    <div style='font-size:2rem;'>⏳</div>
                    <div style='color:#94a3b8;font-size:0.95rem;'>Caricamento sessione...</div>
                </div>
            """, unsafe_allow_html=True)
            st.stop()
        # else: nessun token e già controllato → login normale
    except Exception as _re:
        logger.warning(f"Errore ripristino sessione da cookie: {_re}")


# Aggiorna last_seen_at con throttling: massimo 1 scrittura ogni 5 minuti per sessione Streamlit
if st.session_state.get('logged_in', False):
    _active_user_id = st.session_state.get('user_data', {}).get('id')
    if _active_user_id:
        _now_utc = datetime.now(timezone.utc)
        _last_seen_write_raw = st.session_state.get('_last_seen_write_at')
        _should_write_last_seen = False

        if not _last_seen_write_raw:
            _should_write_last_seen = True
        else:
            try:
                _last_write_dt = datetime.fromisoformat(str(_last_seen_write_raw).replace('Z', '+00:00'))
                if _last_write_dt.tzinfo is None:
                    _last_write_dt = _last_write_dt.replace(tzinfo=timezone.utc)
                _should_write_last_seen = (_now_utc - _last_write_dt).total_seconds() >= _LAST_SEEN_WRITE_THROTTLE_SECONDS
            except (ValueError, TypeError):
                _should_write_last_seen = True

        if _should_write_last_seen:
            if aggiorna_last_seen(_active_user_id, supabase):
                st.session_state._last_seen_write_at = _now_utc.isoformat()


# ============================================================
# GESTIONE TOKEN RESET PASSWORD (NUOVO CLIENTE + RECUPERO PASSWORD)
# ============================================================
# Se c'è il parametro reset_token, mostra form impostazione password
if st.query_params.get("reset_token"):
    from services.auth_service import imposta_password_da_token, valida_password_compliance
    
    reset_token = st.query_params.get("reset_token")
    
    # Nascondi sidebar per pagina pulita
    hide_sidebar_css()
    
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
        expires_str = user_data.get('reset_expires')
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                now_utc = datetime.now(timezone.utc)
                
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
                            time.sleep(UI_DELAY_LONG)
                            st.query_params.clear()
                            st.rerun()
                        else:
                            st.error(messaggio)
    
    except Exception as e:
        st.error("❌ Errore durante la verifica del link. Riprova o contatta il supporto.")
        logger.exception("Errore verifica reset_token")
    
    st.stop()  # Non mostrare resto app


def verifica_codice_reset(email, code, new_password):
    """Verifica codice e aggiorna password con validazione compliance"""
    from argon2 import PasswordHasher
    from services.auth_service import valida_password_compliance
    ph = PasswordHasher()
    
    try:
        resp = supabase.table('users').select('id, email, nome_ristorante, reset_code, reset_expires').eq('email', email).limit(1).execute()
        user = resp.data[0] if resp.data else None
        
        valid = False
        
        if user:
            stored_code = user.get('reset_code') or ''
            if _hmac.compare_digest(str(stored_code), str(code)):
                # Verifica scadenza
                expires_str = user.get('reset_expires')
                if expires_str:
                    try:
                        expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                        if expires.tzinfo is None:
                            expires = expires.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) > expires:
                            return None, "Codice scaduto. Richiedi un nuovo reset."
                    except (ValueError, TypeError):
                        pass
                valid = True
        
        if not valid:
            codes = st.session_state.get('reset_codes', {})
            entry = codes.get(email)
            if entry and _hmac.compare_digest(str(entry.get('code', '')), str(code)):
                valid = True
        
        if not valid:
            return None, "Codice errato o scaduto"
        
        # Valida password compliance
        errori = valida_password_compliance(
            new_password,
            email,
            user.get('nome_ristorante', '')
        )
        if errori:
            return None, errori[0]
        
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
        return None, "Errore durante il reset. Riprova."


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
    # Elimina completamente sidebar e pulsante (CSS già applicato globalmente prima del login)
    # Solo CSS aggiuntivo per padding login
    st.markdown("""
        <style>
        /* ✂️ RIDUCI SPAZIO SUPERIORE LOGIN */
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 3rem !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    render_oh_yeah_header()
    
    st.markdown("""
<h2 style="font-size: clamp(2.2rem, 5.5vw, 3.2rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🔐 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Accedi al Sistema</span>
</h2>
""", unsafe_allow_html=True)
    
    # Nota legale senza sfondo
    st.markdown("""
<p style="font-size: clamp(0.7rem, 1.6vw, 0.82rem); color: #1e3a8a; margin: 0.75rem 0 1.25rem 0; line-height: 1.6;">
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</p>
""", unsafe_allow_html=True)
    
    # Tab navigazione stile bottoni (stesso stile dell'app)
    if 'login_tab_attivo' not in st.session_state:
        st.session_state.login_tab_attivo = "login"

    st.markdown("""
        <style>
        /* Bottone Accedi: azzurro, larghezza 200px */
        div[data-testid="stFormSubmitButton"] button {
            background-color: #0ea5e9 !important;
            color: white !important;
            width: 200px !important;
        }
        div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #0284c7 !important;
        }
        /* Fix altezza pagina */
        .main .block-container {
            max-height: none !important;
        }
        div[data-testid="stForm"] {
            max-height: none !important;
            height: auto !important;
        }
        section[data-testid="stSidebar"] ~ div {
            max-height: none !important;
            overflow-y: auto !important;
        }
        </style>
    """, unsafe_allow_html=True)
    col_lt1, col_lt2, _ = st.columns([1.2, 1.8, 5])
    with col_lt1:
        if st.button("🔑 LOGIN", key="lt_btn_login", use_container_width=True,
                     type="primary" if st.session_state.login_tab_attivo == "login" else "secondary"):
            if st.session_state.login_tab_attivo != "login":
                st.session_state.login_tab_attivo = "login"
                st.rerun()
    with col_lt2:
        if st.button("🔄 RECUPERA PASSWORD", key="lt_btn_reset", use_container_width=True,
                     type="primary" if st.session_state.login_tab_attivo == "reset" else "secondary"):
            if st.session_state.login_tab_attivo != "reset":
                st.session_state.login_tab_attivo = "reset"
                st.rerun()

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    if st.session_state.login_tab_attivo == "login":
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input("🔑 Password", type="password", placeholder="La tua password")
            
            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Accedi")
            
            if submit:
                if not email or not password:
                    st.error("⚠️ Compila tutti i campi!")
                else:
                    with st.spinner("Verifica credenziali..."):
                        user, errore = verifica_credenziali(email, password)
                        
                        if user:
                            user.pop('password_hash', None)  # Non esporre hash in session
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False  # ← Reset flag logout
                            
                            # Salva P.IVA in session_state per validazione fatture
                            st.session_state.partita_iva = user.get('partita_iva')
                            st.session_state.created_at = user.get('created_at')
                            
                            # 🍪 Genera e salva session_token nel DB + cookie (30 giorni)
                            if _cookie_manager is not None:
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _s_token = str(_uuid.uuid4())
                                    supabase.table('users').update({
                                        'session_token': _s_token,
                                        'session_token_created_at': _now_utc.isoformat(),
                                        'last_seen_at': _now_utc.isoformat(),
                                    }).eq('id', user.get('id')).execute()
                                    _cookie_manager.set("session_token", _s_token,
                                                        expires_at=datetime.now() + timedelta(days=30))
                                    st.session_state._last_seen_write_at = _now_utc.isoformat()
                                except Exception as _ce:
                                    logger.warning(f"Errore salvataggio session token: {_ce}")
                            
                            # Verifica se è admin e imposta flag
                            if user.get('email') in ADMIN_EMAILS:
                                st.session_state.user_is_admin = True
                                logger.info(f"✅ Login ADMIN: user_id={user.get('id')}")
                                st.success("✅ Accesso effettuato come ADMIN!")
                                time.sleep(UI_DELAY_SHORT)
                                # Reindirizza direttamente al pannello admin
                                st.switch_page("pages/admin.py")
                            else:
                                st.session_state.user_is_admin = False
                                logger.info(f"✅ Login cliente: user_id={user.get('id')}")
                                st.success("✅ Accesso effettuato!")
                                time.sleep(UI_DELAY_MEDIUM)
                                st.rerun()
                        else:
                            st.error(f"❌ {errore}")

    elif st.session_state.login_tab_attivo == "reset":
        st.markdown("#### Reset Password via Email")
        st.markdown("""
            <style>
            /* Bottoni reset: larghezza auto, Invia Codice azzurro */
            div.st-key-reset_btn_invia button {
                width: auto !important;
                min-width: unset !important;
                background-color: #0ea5e9 !important;
                color: white !important;
            }
            div.st-key-reset_btn_invia button:hover {
                background-color: #0284c7 !important;
            }
            div.st-key-reset_btn_conferma button {
                width: auto !important;
                min-width: unset !important;
            }
            </style>
        """, unsafe_allow_html=True)

        reset_email = st.text_input("📧 Email per reset", placeholder="tua@email.com", key="reset_email")

        with st.container(key="reset_btn_invia"):
            if st.button("📨 Invia Codice"):
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
        new_pwd = st.text_input("🔑 Nuova password (min 10 caratteri)", type="password", key="new_pwd")
        confirm_pwd = st.text_input("🔑 Conferma password", type="password", key="confirm_pwd")

        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        with st.container(key="reset_btn_conferma"):
            if st.button("✅ Conferma Reset", type="primary"):
                if not reset_email or not code_input or not new_pwd or not confirm_pwd:
                    st.warning("⚠️ Compila tutti i campi")
                elif new_pwd != confirm_pwd:
                    st.error("❌ Le password non coincidono")
                elif len(new_pwd) < 10:
                    st.error("❌ Password troppo corta (min 10 caratteri)")
                else:
                    user, errore = verifica_codice_reset(reset_email, code_input, new_pwd)
                    
                    if user:
                        user.pop('password_hash', None)  # Non esporre hash in session
                        st.session_state.logged_in = True
                        st.session_state.user_data = user
                        st.session_state.force_logout = False
                        if _cookie_manager is not None:
                            try:
                                _s_token = str(_uuid.uuid4())
                                supabase.table('users').update({'session_token': _s_token}).eq('id', user.get('id')).execute()
                                _cookie_manager.set("session_token", _s_token,
                                                    expires_at=datetime.now() + timedelta(days=30))
                            except Exception:
                                pass
                        st.success("✅ Password aggiornata! Accesso automatico...")
                        time.sleep(UI_DELAY_LONG)
                        st.rerun()
                    else:
                        st.error(f"❌ {errore}")


# ============================================================
# CHECK LOGIN ALL'AVVIO
# ============================================================
# (logged_in già inizializzato sopra — riga ~262)

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
    if _cookie_manager is not None:
        try:
            # Invalida token nel DB prima di pulire la sessione
            _email_emergency = st.session_state.get('user_data', {}).get('email') if st.session_state.get('user_data') else None
            if _email_emergency:
                supabase.table('users').update({'session_token': None}).eq('email', _email_emergency).execute()
        except Exception:
            pass
    st.session_state.clear()
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.rerun()


# ============================================
# VERIFICA E RIPRISTINO FLAG ADMIN
# ============================================
# Ripristina flag admin se l'utente è in ADMIN_EMAILS
# (necessario perché session_state viene perso al refresh della pagina)
if user.get('email') in ADMIN_EMAILS:
    if not st.session_state.get('user_is_admin', False):
        st.session_state.user_is_admin = True
        logger.info(f"✅ Flag admin ripristinato per user_id={user.get('id')}")
else:
    # Assicura che non-admin non abbiano il flag
    if st.session_state.get('user_is_admin', False):
        st.session_state.user_is_admin = False
        logger.warning(f"⚠️ Flag admin rimosso per utente non-admin: user_id={user.get('id')}")


# ============================================
# RIPRISTINO IMPERSONAZIONE DA COOKIE (dopo F5/refresh)
# ============================================
# Se l'admin è loggato ma non sta impersonando, controlla se c'era
# un'impersonazione attiva prima del refresh e ripristinala.
if (st.session_state.get('user_is_admin', False)
        and not st.session_state.get('impersonating', False)
        and _cookie_manager is not None):
    try:
        _imp_uid_cookie = _cookie_manager.get("impersonation_user_id")
        if _imp_uid_cookie:
            _imp_resp = supabase.table("users").select("*")\
                .eq("id", _imp_uid_cookie).eq("attivo", True).execute()
            if _imp_resp and _imp_resp.data:
                _imp_customer = _imp_resp.data[0]
                # Salva dati admin originali e passa a quelli del cliente
                st.session_state.admin_original_user = st.session_state.user_data.copy()
                st.session_state.user_data = {
                    'id': _imp_customer['id'],
                    'email': _imp_customer['email'],
                    'nome_ristorante': _imp_customer.get('nome_ristorante'),
                    'attivo': _imp_customer.get('attivo', True),
                    'pagine_abilitate': _imp_customer.get('pagine_abilitate'),
                }
                st.session_state.user_is_admin = False
                st.session_state.impersonating = True
                # Aggiorna variabile locale user per il resto della pagina
                user = st.session_state.user_data
                logger.info(f"✅ Impersonazione ripristinata da cookie dopo refresh: user_id={_imp_customer.get('id')}")
            else:
                # Cliente non trovato (disattivato o cancellato) → pulisci il cookie
                _cookie_manager.set("impersonation_user_id", "",
                                    expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                logger.warning(f"⚠️ Cliente impersonato non trovato (id={_imp_uid_cookie}) - cookie rimosso")
    except Exception as _imp_e:
        logger.warning(f"Errore ripristino impersonazione da cookie: {_imp_e}")


# ============================================
# CARICAMENTO RISTORANTI (MULTI-RISTORANTE STEP 2)
# ============================================
# Carica ristoranti dell'utente (oppure TUTTI i ristoranti se admin)
# ⚠️ SAFETY CHECK: Verifica che user sia definito (dovrebbe essere già controllato sopra)
if not user or not user.get('id'):
    logger.error("❌ ERRORE CRITICO: user non definito in caricamento ristoranti")
    st.session_state.logged_in = False
    st.rerun()

if 'ristoranti' not in st.session_state or not st.session_state.get('ristorante_id'):
    try:
        # Admin: carica TUTTI i ristoranti dal sistema
        if st.session_state.get('user_is_admin', False):
            ristoranti = supabase.table('ristoranti')\
                .select('id, nome_ristorante, partita_iva, ragione_sociale, user_id')\
                .eq('attivo', True)\
                .order('nome_ristorante')\
                .execute()
            
            logger.info(f"👨‍💼 ADMIN: Caricati {len(ristoranti.data) if ristoranti.data else 0} ristoranti (tutti i clienti)")
        else:
            # Utente normale: carica solo i propri ristoranti
            ristoranti = supabase.table('ristoranti')\
                .select('id, nome_ristorante, partita_iva, ragione_sociale')\
                .eq('user_id', user.get('id'))\
                .eq('attivo', True)\
                .execute()
            
            logger.info(f"🔍 DEBUG: Caricati {len(ristoranti.data) if ristoranti.data else 0} ristoranti per user_id={user.get('id')}")
        
        st.session_state.ristoranti = ristoranti.data if ristoranti.data else []
        
        # Se ha ristoranti, imposta il default
        if st.session_state.ristoranti:
            # Se non c'è un ristorante selezionato, usa l'ultimo usato (se ancora disponibile)
            if 'ristorante_id' not in st.session_state:
                ultimo_id = user.get('ultimo_ristorante_id')
                ristorante_default = None
                if ultimo_id:
                    ristorante_default = next(
                        (r for r in st.session_state.ristoranti if r['id'] == ultimo_id), None
                    )
                if ristorante_default is None:
                    ristorante_default = st.session_state.ristoranti[0]
                st.session_state.ristorante_id = ristorante_default['id']
                st.session_state.partita_iva = ristorante_default['partita_iva']
                st.session_state.nome_ristorante = ristorante_default['nome_ristorante']
                logger.info(f"🏢 Ristorante caricato: rist_id={ristorante_default['id']}{' [ultimo usato]' if ultimo_id and ristorante_default['id'] == ultimo_id else ' [primo in lista]'}")
        else:
            # ⚠️ UTENTE LEGACY: Nessun ristorante trovato
            if not st.session_state.get('user_is_admin', False):
                piva = user.get('partita_iva')
                nome = user.get('nome_ristorante')
                user_id = user.get('id')
                
                # Tenta creazione automatica ristorante se ha P.IVA
                if piva and user_id:
                    logger.warning(f"⚠️ Utente legacy {user_id} senza ristoranti - tentativo creazione automatica")
                    logger.warning(f"   Dati: nome='{nome}', piva='{piva}'")
                    try:
                        # Cerca ristorante con questa P.IVA DELLO STESSO UTENTE
                        check_existing = supabase.table('ristoranti')\
                            .select('id, user_id, nome_ristorante')\
                            .eq('partita_iva', piva)\
                            .eq('user_id', user_id)\
                            .execute()
                        
                        if check_existing.data and len(check_existing.data) > 0:
                            # È il suo ristorante, usalo
                            existing = check_existing.data[0]
                            st.session_state.ristoranti = [existing]
                            st.session_state.ristorante_id = existing['id']
                            st.session_state.partita_iva = piva
                            st.session_state.nome_ristorante = existing['nome_ristorante']
                            logger.info(f"✅ Ristorante esistente trovato e collegato: {existing['id']}")
                        else:
                            # Non esiste, crea nuovo
                            nome_rist = nome or f"Ristorante {piva}"
                            new_rist = supabase.table('ristoranti').insert({
                                'user_id': user_id,
                                'nome_ristorante': nome_rist,
                                'partita_iva': piva,
                                'ragione_sociale': user.get('ragione_sociale', ''),
                                'attivo': True
                            }).execute()
                            
                            if new_rist.data:
                                st.session_state.ristoranti = new_rist.data
                                st.session_state.ristorante_id = new_rist.data[0]['id']
                                st.session_state.partita_iva = piva
                                st.session_state.nome_ristorante = nome
                                logger.info(f"✅ Ristorante creato automaticamente: {new_rist.data[0]['id']}")
                                st.success("✅ Account configurato correttamente!")
                                st.rerun()  # Ricarica per applicare i cambiamenti
                            else:
                                logger.error(f"❌ Creazione ristorante fallita per utente {user_id} - response vuota")
                                st.warning("⚠️ Configurazione account incompleta. Alcune funzionalità potrebbero non essere disponibili.")
                    except Exception as create_err:
                        logger.error(f"❌ ERRORE DETTAGLIATO creazione ristorante: {str(create_err)}")
                        logger.error(f"   Tipo errore: {type(create_err).__name__}")
                        # Non bloccare con st.stop(), permetti accesso all'app
                        st.warning(f"⚠️ Problemi di configurazione rilevati: {str(create_err)[:100]}")
                else:
                    # Nessuna P.IVA o dati mancanti - permetti comunque l'accesso
                    logger.warning(f"⚠️ Utente {user_id} senza ristoranti e dati incompleti - accesso limitato")
                    st.warning("⚠️ Configurazione account incompleta. Contatta l'assistenza per configurare il tuo ristorante.")
            
            # FALLBACK vecchio codice per compatibilità
            # ⚠️ Solo se ristoranti NON è stato popolato dalle operazioni sopra
            if not st.session_state.get('user_is_admin', False) and not st.session_state.get('ristoranti'):
                piva = user.get('partita_iva')
                nome = user.get('nome_ristorante')
                
                logger.warning(f"⚠️ Utente {user.get('email')} senza ristoranti in tabella - fallback su dati users")
                
                # Imposta dati di fallback dalla tabella users
                st.session_state.partita_iva = piva
                st.session_state.nome_ristorante = nome
            elif st.session_state.get('user_is_admin', False) and not st.session_state.get('ristoranti'):
                # Admin senza ristoranti nel sistema
                logger.warning(f"⚠️ Admin senza ristoranti nel sistema")
    except Exception as e:
        logger.exception(f"Errore caricamento ristoranti: {e}")
        # Fallback: usa dati utente (solo per non-admin)
        if not st.session_state.get('user_is_admin', False):
            st.session_state.ristoranti = []
            st.session_state.partita_iva = user.get('partita_iva')
            st.session_state.nome_ristorante = user.get('nome_ristorante')


# ============================================
# ADMIN PURO: REDIRECT A PANNELLO ADMIN
# ============================================
# L'admin (non impersonificato) non accede alle pagine app, solo al pannello admin.
if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
    logger.info(f"👨‍💼 Admin user_id={user.get('id')} su app.py → redirect a pannello admin")
    st.switch_page("pages/admin.py")

# ============================================
# BANNER IMPERSONAZIONE (solo per admin che impersonano)
# ============================================

if st.session_state.get('impersonating', False):
    # Banner visibile quando l'admin sta impersonando un cliente
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f59e0b 0%, #dc2626 100%); 
                padding: clamp(0.75rem, 2vw, 1rem); 
                border-radius: 10px; 
                margin-bottom: 1.25rem; 
                text-align: center;
                border: 3px solid #dc2626;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
        <h3 style="color: white; margin: 0; font-size: clamp(1rem, 2.5vw, 1.25rem);">
            ⚠️ MODALITÀ IMPERSONAZIONE
        </h3>
        <p style="color: #fef3c7; margin: 0.625rem 0 0 0; font-size: clamp(0.875rem, 2vw, 1rem); word-wrap: break-word;">
            Stai visualizzando l'account di: <strong>{_html.escape(user.get('nome_ristorante', 'Cliente'))}</strong> ({_html.escape(user.get('email', ''))})
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
                
                # 🏢 RIPRISTINA RISTORANTI ADMIN (tutti i ristoranti del sistema)
                try:
                    ristoranti_admin = supabase.table('ristoranti')\
                        .select('id, nome_ristorante, partita_iva, ragione_sociale, user_id')\
                        .eq('attivo', True)\
                        .order('nome_ristorante')\
                        .execute()
                    
                    st.session_state.ristoranti = ristoranti_admin.data if ristoranti_admin.data else []
                    
                    # Rimuovi ristorante_id specifico (admin vede tutti i ristoranti)
                    if st.session_state.get('ristorante_id'):
                        del st.session_state.ristorante_id
                    if 'partita_iva' in st.session_state:
                        del st.session_state.partita_iva
                    if 'nome_ristorante' in st.session_state:
                        del st.session_state.nome_ristorante
                    
                    logger.info(f"🔙 ADMIN: Ripristinati {len(st.session_state.ristoranti)} ristoranti del sistema")
                except Exception as e:
                    logger.error(f"Errore ripristino ristoranti admin: {e}")
                
                # Log uscita impersonazione
                logger.info(f"FINE IMPERSONAZIONE: Ritorno a admin user_id={st.session_state.user_data.get('id')}")
                
                # Rimuovi cookie impersonazione (non deve più sopravvivere al refresh)
                if _cookie_manager is not None:
                    try:
                        _cookie_manager.set("impersonation_user_id", "",
                                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    except Exception:
                        pass
                
                # Redirect al pannello admin
                st.switch_page("pages/admin.py")
            else:
                st.error("⚠️ Errore: dati admin originali non trovati")
                st.session_state.impersonating = False
                if _cookie_manager is not None:
                    try:
                        _cookie_manager.set("impersonation_user_id", "",
                                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    except Exception:
                        pass
                st.rerun()
    
    st.markdown("---")


# ============================================
# SIDEBAR CON NAVIGAZIONE E INFO
# ============================================
render_sidebar(user)


# ============================================
# HEADER
# ============================================

render_oh_yeah_header()

st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🧠 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi Fatture AI</span>
</h2>
<div style='padding: 4px 14px 0; font-size: 0.88rem; color: #1e2a4a; font-weight: 500; margin-bottom: 1.5rem;'>
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</div>
""", unsafe_allow_html=True)

# Recupera email e nome ristorante intelligente
user_email = (user.get('email') or user.get('Email') or user.get('user_email') or 
              (st.session_state.user_data.get('email') if st.session_state.user_data else None) or 
              'Email non disponibile')

# 🎯 LOGICA INTELLIGENTE: Single vs Multi-Ristorante (usa dati già in sessione, zero query DB)
ristoranti_session = st.session_state.get('ristoranti', [])
num_ristoranti = len(ristoranti_session)

if num_ristoranti == 0:
    nome_ristorante = "Nessun Ristorante"
elif num_ristoranti == 1:
    nome_ristorante = ristoranti_session[0].get('nome_ristorante', 'Ristorante')
else:
    nome_ristorante = "Multi-Ristorante"

# Nota legale spostata nel header accanto al titolo

# ============================================
# DROPDOWN MULTI-RISTORANTE
# ============================================
# Mostra dropdown per clienti NON admin con più ristoranti
if user.get('email') not in ADMIN_EMAILS:
    ristoranti = st.session_state.get('ristoranti', [])
    
    if len(ristoranti) > 1:
        st.markdown('<h3 style="color:#1e3a5f;font-weight:700;">🏢 Seleziona Ristorante da Gestire</h3>', unsafe_allow_html=True)
        
        # Trova indice ristorante corrente
        current_id = st.session_state.get('ristorante_id')
        current_idx = 0
        for idx, r in enumerate(ristoranti):
            if r['id'] == current_id:
                current_idx = idx
                break
        
        # Dropdown ristorante
        ristorante_idx = st.selectbox(
            "🏪 Scegli ristorante:",
            range(len(ristoranti)),
            index=current_idx,
            format_func=lambda i: f"{ristoranti[i]['nome_ristorante']}",
            key="dropdown_ristorante_main",
            help="Seleziona il ristorante per cui vuoi caricare e analizzare fatture"
        )
        
        # Info ristorante sotto il dropdown, su tutta la larghezza
        rag_soc = _html.escape(ristoranti[ristorante_idx].get('ragione_sociale') or 'N/A')
        nome_r = _html.escape(ristoranti[ristorante_idx]['nome_ristorante'])
        piva_r = _html.escape(ristoranti[ristorante_idx]['partita_iva'])
        st.markdown(f"""
        <div style='padding: 8px 14px; font-size: 0.88rem; color: #1e3a5f; font-weight: 500;'>
            ✅ <strong>Attivo</strong> &nbsp;·&nbsp; 📋 {nome_r} &nbsp;·&nbsp; 🏢 IT{piva_r} &nbsp;·&nbsp; 📄 {rag_soc}
        </div>
        """, unsafe_allow_html=True)
        
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
            # 🧹 Pulizia chiavi stale da ristorante precedente
            for _stale_key in ['righe_ai_appena_categorizzate', 'righe_keyword_appena_categorizzate',
                               'righe_modificate_manualmente', 'force_reload', 'force_empty_until_upload',
                               'files_errori_report', 'last_upload_summary', 'ultimo_upload_ids',
                               'ingredienti_temp', 'ricetta_edit_mode', 'ricetta_edit_data']:
                st.session_state.pop(_stale_key, None)
            st.cache_data.clear()
            
            # 💾 Salva l'ultimo ristorante usato nel DB per ripristinarlo alla prossima sessione
            try:
                supabase.table('users').update(
                    {'ultimo_ristorante_id': selected_ristorante['id']}
                ).eq('id', user.get('id')).execute()
            except Exception as _e:
                logger.warning(f"Errore salvataggio ultimo_ristorante_id: {_e}")
            
            logger.info(f"🔄 Ristorante cambiato: rist_id={selected_ristorante['id']}")
            st.rerun()
        
        st.markdown("---")
    
    elif len(ristoranti) == 1:
        # Singolo ristorante: mostra solo info compatta
        st.success(f"🏪 **Ristorante:** {ristoranti[0]['nome_ristorante']} | 📋 **P.IVA:** `IT{ristoranti[0]['partita_iva']}`")
        st.markdown("---")

# ============================================================
# API KEY OPENAI
# ============================================================
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    logger.exception("API Key OpenAI non trovata o accesso a st.secrets fallito")
    st.error("⛔ Configurazione AI non disponibile. Contatta l'amministratore.")
    st.stop()


# ============================================================
# STATISTICHE E GRAFICI
# ============================================================

# Dizionario mesi italiani (usato in pivot mensili)
MESI_ITA = {
    1: 'GENNAIO', 2: 'FEBBRAIO', 3: 'MARZO', 4: 'APRILE',
    5: 'MAGGIO', 6: 'GIUGNO', 7: 'LUGLIO', 8: 'AGOSTO',
    9: 'SETTEMBRE', 10: 'OTTOBRE', 11: 'NOVEMBRE', 12: 'DICEMBRE'
}

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
            st.dataframe(conteggio_cat, hide_index=True, width='stretch')
            
            st.markdown("**Esempio 15 righe (verifica categoria):**")
            sample_df = df_completo[['FileOrigine', 'Descrizione', 'Categoria', 'Fornitore', 'TotaleRiga']].head(15)
            st.dataframe(sample_df, hide_index=True, width='stretch')
            
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
                ristorante_id = st.session_state.get('ristorante_id')
                query_null = supabase.table("fatture").select("descrizione, fornitore, prezzo_unitario").eq("user_id", user_id).is_("categoria", "null")
                query_da_class = supabase.table("fatture").select("descrizione, fornitore, prezzo_unitario").eq("user_id", user_id).eq("categoria", "Da Classificare")
                query_empty = supabase.table("fatture").select("descrizione, fornitore, prezzo_unitario").eq("user_id", user_id).eq("categoria", "")
                if ristorante_id:
                    query_null = query_null.eq("ristorante_id", ristorante_id)
                    query_da_class = query_da_class.eq("ristorante_id", ristorante_id)
                    query_empty = query_empty.eq("ristorante_id", ristorante_id)
                resp_null = query_null.execute()
                resp_da_class = query_da_class.execute()
                resp_empty = query_empty.execute()
                
                # Combina e rimuovi duplicati (NULL + "Da Classificare" + stringa vuota)
                dati_null = resp_null.data if resp_null.data else []
                dati_da_class = resp_da_class.data if resp_da_class.data else []
                dati_empty = resp_empty.data if resp_empty.data else []
                tutti_dati = dati_null + dati_da_class + dati_empty
                
                descrizioni_da_classificare = list(set([row['descrizione'] for row in tutti_dati if row.get('descrizione')]))
                fornitori_da_classificare = list(set([row['fornitore'] for row in tutti_dati if row.get('fornitore')]))
                
                # 🛡️ QUARANTENA: Identifica descrizioni che hanno ALMENO una riga €0
                # Queste NON andranno in memoria globale (restano in attesa di review admin)
                _descrizioni_con_prezzo_zero = set()
                for row in tutti_dati:
                    desc = row.get('descrizione')
                    prezzo = row.get('prezzo_unitario', 0) or 0
                    if desc and float(prezzo) == 0:
                        _descrizioni_con_prezzo_zero.add(desc)
                logger.info(f"🛡️ QUARANTENA: {len(_descrizioni_con_prezzo_zero)} descrizioni con righe €0 (escluse da memoria globale)")
                
                logger.info(f"🔍 Query diretta DB: trovate {len(descrizioni_da_classificare)} descrizioni uniche da classificare (NULL: {len(dati_null)}, DaClass: {len(dati_da_class)}, Vuote: {len(dati_empty)})")
            except Exception as e:
                logger.error(f"Errore query diretta descrizioni: {e}")
                # Fallback su df_completo se query fallisce
                descrizioni_da_classificare = df_completo[maschera_ai]['Descrizione'].unique().tolist()
                fornitori_da_classificare = df_completo[maschera_ai]['Fornitore'].unique().tolist()
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
                    st.cache_data.clear()
                    invalida_cache_memoria()
                    carica_memoria_completa(user_id)
                    
                    mappa_categorie = {}  # desc -> categoria
                    prodotti_elaborati = 0  # Contatore per banner
                    descrizioni_dopo_memoria = []  # Quelle NON risolte dalla memoria
                    
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
                            progress_placeholder.markdown(f"""
                            <div class="ai-banner">
                                <div class="brain-pulse-banner">🧠</div>
                                <div class="progress-percentage">{int(percentuale)}%</div>
                                <div class="progress-status">Memoria: {prodotti_elaborati} di {totale_da_classificare}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            # Traccia per colonna Fonte 📚
                            if desc not in _tracking_memoria_set:
                                _tracking_memoria_set.add(desc)
                                st.session_state.righe_memoria_appena_categorizzate.append(desc)
                            logger.info(f"📦 MEMORIA: '{desc[:TRUNCATE_DESC_LOG]}' → {cat_memoria}")
                        else:
                            descrizioni_dopo_memoria.append(desc)
                    
                    if prodotti_elaborati > 0:
                        logger.info(f"📦 PRE-STEP MEMORIA: {prodotti_elaborati} descrizioni risolte dalla memoria globale")
                    
                    # 📖 STEP 1: Dizionario keyword (più veloce, più preciso) sulle rimanenti
                    descrizioni_per_ai = []  # Solo quelle che dizionario non risolve
                    
                    # Tracking keyword (già resettato sopra, init set per O(1) lookup)
                    _tracking_keyword_set = set(st.session_state.righe_keyword_appena_categorizzate)
                    
                    for desc in descrizioni_dopo_memoria:
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
                            
                            # Traccia righe keyword per colonna Fonte
                            if desc not in _tracking_keyword_set:
                                _tracking_keyword_set.add(desc)
                                st.session_state.righe_keyword_appena_categorizzate.append(desc)
                            
                            logger.debug(f"📖 DIZIONARIO: '{desc[:TRUNCATE_DESC_LOG]}' → {cat_dizionario}")
                        else:
                            descrizioni_per_ai.append(desc)
                    
                    # 💾 Batch upsert memoria GLOBALE per keyword (singola query)
                    # 🛡️ QUARANTENA: Escludi descrizioni con righe €0 dalla memoria globale
                    keyword_upsert_data = [
                        {
                            'descrizione': desc,
                            'categoria': mappa_categorie[desc],
                            'confidence': 'media',
                            'verified': False,
                            'volte_visto': 1,
                            'classificato_da': 'keyword',
                            'created_at': datetime.now(timezone.utc).isoformat(),
                            'ultima_modifica': datetime.now(timezone.utc).isoformat()
                        }
                        for desc in _tracking_keyword_set if desc in mappa_categorie and desc not in _descrizioni_con_prezzo_zero
                    ]
                    _kw_quarantined = len([d for d in _tracking_keyword_set if d in mappa_categorie and d in _descrizioni_con_prezzo_zero])
                    if _kw_quarantined > 0:
                        logger.info(f"🛡️ QUARANTENA keyword: {_kw_quarantined} descrizioni €0 escluse da memoria globale")
                    if keyword_upsert_data:
                        try:
                            _kw_result = supabase.table('prodotti_master').upsert(
                                keyword_upsert_data, on_conflict='descrizione'
                            ).execute()
                            _kw_saved = len(_kw_result.data) if _kw_result.data else 0
                            logger.info(f"💾 BATCH keyword: {_kw_saved}/{len(keyword_upsert_data)} prodotti salvati in memoria globale")
                        except Exception as e:
                            logger.warning(f"Errore batch salvataggio memoria keyword: {e}")
                    
                    # 🧠 STEP 2: Invia all'AI solo quelli che dizionario non ha risolto
                    chunk_size = 50
                    # prodotti_elaborati già inizializzato sopra e aggiornato durante STEP 1
                    
                    if descrizioni_per_ai:
                        # 🔒 BUDGET GIORNALIERO AI: limita chiamate per sessione/giorno
                        from datetime import date as _date_cls
                        _today = _date_cls.today().isoformat()
                        if st.session_state.get('_ai_budget_date') != _today:
                            st.session_state['_ai_budget_date'] = _today
                            st.session_state['_ai_budget_calls'] = 0
                        
                        _ai_calls_today = st.session_state.get('_ai_budget_calls', 0)
                        _ai_chunks_needed = (len(descrizioni_per_ai) + chunk_size - 1) // chunk_size
                        if _ai_calls_today + _ai_chunks_needed > MAX_AI_CALLS_PER_DAY:
                            _remaining = max(0, MAX_AI_CALLS_PER_DAY - _ai_calls_today)
                            st.warning(f"⚠️ Limite giornaliero AI raggiunto ({MAX_AI_CALLS_PER_DAY} chiamate/giorno). "
                                       f"Rimanenti: {_remaining}. Le descrizioni non classificate resteranno 'Da Classificare'.")
                            logger.warning(f"🔒 Budget AI giornaliero esaurito: {_ai_calls_today} chiamate, servirebbero {_ai_chunks_needed}")
                            descrizioni_per_ai = []  # Skip AI classification
                        
                        for i in range(0, len(descrizioni_per_ai), chunk_size):
                            chunk = descrizioni_per_ai[i:i+chunk_size]
                            cats = classifica_con_ai(chunk, fornitori_da_classificare)
                            st.session_state['_ai_budget_calls'] = st.session_state.get('_ai_budget_calls', 0) + 1
                            ai_batch_upsert = []
                            for desc, cat in zip(chunk, cats):
                                mappa_categorie[desc] = cat
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
                                
                                if cat and cat != "Da Classificare":
                                    # 🛡️ QUARANTENA: Escludi descrizioni €0 dalla memoria globale
                                    if desc not in _descrizioni_con_prezzo_zero:
                                        ai_batch_upsert.append({
                                            'descrizione': desc,
                                            'categoria': cat,
                                            'volte_visto': 1,
                                            'verified': False,
                                            'classificato_da': 'AI'
                                        })
                                    else:
                                        logger.info(f"🛡️ QUARANTENA AI: '{desc[:60]}' → {cat} (€0, escluso da memoria globale)")
                            
                            # 💾 Batch upsert memoria GLOBALE per AI (singola query per chunk)
                            if ai_batch_upsert:
                                try:
                                    _ai_result = supabase.table('prodotti_master').upsert(
                                        ai_batch_upsert, on_conflict='descrizione'
                                    ).execute()
                                    _ai_saved = len(_ai_result.data) if _ai_result.data else 0
                                    logger.info(f"💾 BATCH AI: {_ai_saved}/{len(ai_batch_upsert)} prodotti salvati in memoria globale")
                                except Exception as e:
                                    logger.error(f"Errore batch salvataggio memoria AI: {e}")
                        
                        # Invalida cache una sola volta dopo tutti i chunk
                        st.cache_data.clear()
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
                key="data_da_custom"
            )
        
        with col_a:
            data_fine_custom = st.date_input(
                "📅 A", 
                value=st.session_state.data_fine_filtro,
                min_value=inizio_anno,
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
        # Placeholder se dataset mancanti/vuoti (guard difensivo, st.stop() sopra copre il caso normale)
        if ('df_completo_filtrato' not in locals()) or ('df_food' not in locals()) or ('df_spese_generali' not in locals()) or df_completo_filtrato.empty:
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
                mask = df_editor['Descrizione'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe con '{search_term}' nella descrizione")
            elif search_type == "Categoria":
                mask = df_editor['Categoria'].str.upper().str.contains(search_term.upper(), na=False)
                st.info(f"🔍 Trovate {mask.sum()} righe nella categoria '{search_term}'")
            else:
                mask = df_editor['Fornitore'].str.upper().str.contains(search_term.upper(), na=False)
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
    
    # ========================================================
    # SEZIONE 3: CATEGORIE
    # ========================================================
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

# ⚡ SINGLE DATA LOAD: Carica una sola volta, riusa per Gestione Fatture + Dashboard
force_refresh = st.session_state.get('force_reload', False)
if force_refresh:
    st.session_state.force_reload = False
    logger.info("🔄 FORCE RELOAD attivato dopo categorizzazione AI")

with st.spinner("⏳ Caricamento dati..."):
    df_cache = carica_e_prepara_dataframe(user_id, force_refresh=force_refresh)

# ✅ Render riuscito: reset contatore anti-loop
st.session_state._rerun_guard = 0


# 🗂️ GESTIONE FATTURE - Eliminazione (prima del file uploader)
if not df_cache.empty:
    st.markdown("""
    <style>
    /* Expander Gestione Fatture - sfondo arancione chiaro */
    div.st-key-expander_gestione_fatture [data-testid="stExpander"] details summary {
        background: linear-gradient(135deg, rgba(255, 237, 213, 0.95) 0%, rgba(254, 215, 170, 0.95) 100%) !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        color: #9a3412 !important;
        font-weight: 600 !important;
        border: 1px solid #fdba74 !important;
    }
    div.st-key-expander_gestione_fatture [data-testid="stExpander"] details {
        background: rgba(255, 247, 237, 0.9) !important;
        border: 1px solid #fdba74 !important;
        border-radius: 8px !important;
    }
    div.st-key-expander_gestione_fatture [data-testid="stExpander"] details[open] summary {
        border-bottom: 1px solid #fdba74 !important;
        border-radius: 8px 8px 0 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.container(key="expander_gestione_fatture"):
      with st.expander("🗂️ Apri per gestire le Fatture Caricate (Elimina)", expanded=False):
        
        # ========================================
        # BOX STATISTICHE
        # ========================================
        try:
            stats_db = get_fatture_stats(user_id, st.session_state.get('ristorante_id'))
        except Exception as e:
            logger.error(f"Errore get_fatture_stats: {e}")
            st.error("❌ Errore caricamento statistiche")
            stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}
        # Conta note di credito (TD04) dai file unici in df_cache
        num_note_credito = 0
        if 'TipoDocumento' in df_cache.columns and 'FileOrigine' in df_cache.columns:
            num_note_credito = df_cache[df_cache['TipoDocumento'].str.upper().str.strip() == 'TD04']['FileOrigine'].nunique()
        note_credito_html = f' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #FF5500;">{num_note_credito:,}</strong>' if num_note_credito > 0 else ' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #FF5500;">0</strong>'
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
        📊 Fatture: <strong style="font-size: 1.2em; color: #FF5500;">{stats_db["num_uniche"]:,}</strong>{note_credito_html} | 
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
        
        # 🗑️ PULSANTE SVUOTA TUTTO (solo admin/impersonificati - nessuna conferma richiesta)
        if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
            st.markdown("### 🗑️ Eliminazione Massiva")
            
            if st.button(
                "🗑️ ELIMINA TUTTO",
                type="primary",
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
                        
                        progress.progress(80, text="Ripristino sessione...")
                        
                        # HARD RESET: Rimuovi session state specifici
                        # 🔧 FIX: Preserva chiavi impersonazione e contesto ristorante
                        #          per evitare che l'admin perda i poteri dopo delete
                        keys_to_preserve = {
                            'user_data', 'logged_in',
                            # Impersonazione admin
                            'impersonating', 'admin_original_user', 'user_is_admin',
                            # Contesto ristorante attivo
                            'ristorante_id', 'ristoranti', 'partita_iva', 'nome_ristorante',
                        }
                        keys_to_remove = [k for k in st.session_state.keys() 
                                         if k not in keys_to_preserve]
                        for key in keys_to_remove:
                            st.session_state.pop(key, None)  # Sicuro: niente errore se non esiste
                        
                        progress.progress(100, text="Completato!")
                        time.sleep(0.1)
                        
                        # Mostra risultato DENTRO lo spinner (indentazione corretta)
                        if result["success"]:
                            st.success(f"✅ **{result['fatture_eliminate']} fatture** eliminate! ({result['righe_eliminate']} prodotti)")
                            st.info("🧹 **Ripristino completo**: Cache, JSON locali e stato sessione puliti")
                            
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
                            invalida_cache_memoria()
                            st.success("✅ Eliminato tutto!")
                            st.rerun()
                        else:
                            st.error(f"❌ Errore: {result['error']}")
            
            st.markdown("---")
        
        # ========== ELIMINA SINGOLA FATTURA ==========
        st.markdown("### 🗑️ Elimina Fattura Singola")
        
        # Usa fatture_summary già creato sopra
        if len(fatture_summary) > 0:
            # 🔍 FILTRO FORNITORE
            filtro_fornitore = st.text_input(
                "🔍 Filtra per Fornitore:",
                placeholder="Scrivi il nome del fornitore...",
                key="filtro_fornitore_gestione"
            )
            fatture_filtrate = fatture_summary
            if filtro_fornitore.strip():
                fatture_filtrate = fatture_summary[
                    fatture_summary['Fornitore'].str.contains(filtro_fornitore.strip(), case=False, na=False)
                ]
            
            # Crea opzioni dropdown con dict per passare tutti i dati
            fatture_options = []
            for idx, row in fatture_filtrate.iterrows():
                fatture_options.append({
                    'File': row['File'],
                    'Fornitore': row['Fornitore'],
                    'NumProdotti': int(row['NumProdotti']),
                    'Totale': row['Totale'],
                    'Data': row['Data']
                })
            
            if not fatture_options:
                st.info("🔭 Nessuna fattura trovata per il fornitore cercato.")
            else:
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
                            # (rimuovi sia il nome completo che il nome base normalizzato)
                            if 'files_processati_sessione' in st.session_state:
                                file_eliminato = fattura_selezionata['File']
                                st.session_state.files_processati_sessione.discard(file_eliminato)
                                st.session_state.files_processati_sessione.discard(os.path.splitext(file_eliminato)[0].lower())
                            
                            if result["success"]:
                                st.success(f"✅ Fattura **{fattura_selezionata['File']}** eliminata! ({result['righe_eliminate']} prodotti)")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error(f"❌ Errore: {result['error']}")
        else:
            st.info("🔭 Nessuna fattura da eliminare.")
        
        st.caption("⚠️ L'eliminazione è immediata e irreversibile")

    st.markdown("""
    <div style='padding: 8px 14px; font-size: 0.88rem; color: #9a3412; font-weight: 500;'>
        ⚠️ <strong>IMPORTANTE:</strong> Le fatture caricate devono corrispondere alla P.IVA del ristorante mostrato sopra! <strong>Altrimenti verranno scartate</strong>
    </div>
    """, unsafe_allow_html=True)


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
    
    # user_id già definito sopra (post-login check)
    try:
        stats_db = get_fatture_stats(user_id, st.session_state.get('ristorante_id'))
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
    
    # ============================================================
    # SELETTORE RISTORANTE PER ADMIN
    # ============================================================
    # Gli admin possono selezionare qualsiasi ristorante per le fatture di test
    if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
        st.markdown("### 👨‍💼 Modalità Admin - Seleziona Ristorante")
        
        if st.session_state.get('ristoranti') and len(st.session_state.ristoranti) > 0:
            # Crea lista ristoranti per selectbox
            ristoranti_admin = st.session_state.ristoranti
            
            # Trova indice ristorante attualmente selezionato
            current_rist_id = st.session_state.get('ristorante_id')
            try:
                current_idx = next(i for i, r in enumerate(ristoranti_admin) if r['id'] == current_rist_id)
            except StopIteration:
                current_idx = 0
            
            selected_idx = st.selectbox(
                "Seleziona ristorante per caricare fatture:",
                range(len(ristoranti_admin)),
                format_func=lambda i: f"🏪 {ristoranti_admin[i]['nome_ristorante']} - P.IVA: IT{ristoranti_admin[i]['partita_iva']}",
                index=current_idx,
                key="admin_ristorante_selector"
            )
            
            # Aggiorna ristorante selezionato
            selected_ristorante = ristoranti_admin[selected_idx]
            if selected_ristorante['id'] != st.session_state.get('ristorante_id'):
                st.session_state.ristorante_id = selected_ristorante['id']
                st.session_state.partita_iva = selected_ristorante['partita_iva']
                st.session_state.nome_ristorante = selected_ristorante['nome_ristorante']
                logger.info(f"👨‍💼 Admin: ristorante cambiato a rist_id={selected_ristorante['id']}")
                st.rerun()
            
            st.info(f"📌 Le fatture saranno caricate per: **{st.session_state.nome_ristorante}** (P.IVA: IT{st.session_state.partita_iva})")
            st.markdown("---")
        else:
            st.error("⚠️ Nessun ristorante disponibile nel sistema. Crea almeno un cliente prima di caricare fatture.")
            st.stop()
    
    # ============================================================
    # PRE-COMPUTE: Conta righe da categorizzare per UI (dal DataFrame cached)
    # ⚡ ALLINEATO con mostra_statistiche: escludi NOTE E DICITURE + needs_review
    # ============================================================
    _righe_da_class_ui = 0
    _prodotti_unici_ui = 0
    try:
        if not df_cache.empty and 'Categoria' in df_cache.columns:
            # Escludi le stesse righe escluse dalla dashboard (note + review) — solo lettura, no copy
            _mask_note = df_cache['Categoria'].fillna('') == '📝 NOTE E DICITURE'
            if 'needs_review' in df_cache.columns:
                _mask_review = df_cache['needs_review'].fillna(False) == True
                _df_for_count = df_cache[~(_mask_note | _mask_review)]
            else:
                _df_for_count = df_cache[~_mask_note]
            
            _mask_da_class = (
                _df_for_count['Categoria'].isna()
                | (_df_for_count['Categoria'] == 'Da Classificare')
                | (_df_for_count['Categoria'].astype(str).str.strip() == '')
            )
            _righe_da_class_ui = _mask_da_class.sum()
            _prodotti_unici_ui = _df_for_count[_mask_da_class]['Descrizione'].nunique()
    except Exception:
        pass

    # ============================================================
    # LAYOUT: FILE UPLOADER + AI INFO/BUTTON AFFIANCATI
    # ============================================================
    
    # CSS globale per compattare il file uploader e inserire testo italiano
    st.markdown("""
    <style>
    /* Compatta altezza drop zone */
    [data-testid="stFileUploaderDropzone"] {
        padding: 8px 15px !important;
        min-height: 0 !important;
        display: flex !important;
        align-items: center !important;
        gap: 12px !important;
    }
    /* Nascondi testo originale inglese "Drag and drop" + limit */
    [data-testid="stFileUploaderDropzoneInstructions"] {
        visibility: hidden !important;
        position: absolute !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    /* Traduci bottone Browse files → Sfoglia */
    [data-testid="stFileUploaderDropzone"] button {
        font-size: 0 !important;
        padding: 6px 16px !important;
        min-height: 0 !important;
        flex-shrink: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] button::after {
        content: "Sfoglia" !important;
        font-size: 0.85rem !important;
    }
    /* Testo italiano dentro la dropzone via ::after */
    [data-testid="stFileUploaderDropzone"]::after {
        content: "📂 Trascina file qui o clicca Sfoglia  ·  XML, P7M, PDF, JPG, JPEG, PNG · Max 200MB" !important;
        font-size: 0.78rem !important;
        color: #666 !important;
        white-space: nowrap !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col_upload, col_ai_right = st.columns([3, 2])

    with col_upload:
        uploaded_files = st.file_uploader(
            "Carica file",
            accept_multiple_files=True,
            type=['xml', 'p7m', 'pdf', 'jpg', 'jpeg', 'png'],
            label_visibility="collapsed",
            key=f"file_uploader_{st.session_state.get('uploader_key', 0)}"
        )

    with col_ai_right:
        # Spazio per allinearsi con la dropzone (file_uploader collapsed label riserva ~22px)
        st.markdown("<div style='margin-top: 34px;'></div>", unsafe_allow_html=True)
        if _righe_da_class_ui == 0:
            st.markdown("""
            <div style="
                background-color: #d4edda;
                border-left: 4px solid #28a745;
                padding: 10px 14px;
                border-radius: 4px;
                margin-bottom: 8px;
            ">
                <span style="color: #155724; font-weight: 600; font-size: 0.85rem;">✅ Nessun prodotto da categorizzare</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="
                padding: 10px 14px;
                margin-bottom: 8px;
            ">
                <span style="color: #1e40af; font-weight: 600; font-size: 1rem;">⚠️ {_righe_da_class_ui} righe da categorizzare ({_prodotti_unici_ui} prodotti unici)</span>
            </div>
            """, unsafe_allow_html=True)

        if st.button(
            "🧠 Avvia AI per Categorizzare",
            use_container_width=True,
            type="primary",
            key="btn_ai_categorizza_upload",
            disabled=(_righe_da_class_ui == 0)
        ):
            st.session_state.trigger_ai_categorize = True
            st.rerun()
    
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
        if st.button("🔄 Ripristina upload (pulisci cache sessione)", key="reset_upload_cache"):
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
            st.session_state.files_errori_report = {}
            # 🔥 Rimuovi flag force_empty per sbloccare caricamento
            if 'force_empty_until_upload' in st.session_state:
                del st.session_state.force_empty_until_upload
            st.success("✅ Cache pulita! Puoi ricaricare i file.")
            st.rerun()


# ============================================================
# SESSION STATE: Tracking file elaborati/errori
# ============================================================
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
    # Non serve rerun: la pagina è già pulita senza file caricati


# ============================================================
# MOSTRA MESSAGGI PERSISTENTI DALL'ULTIMO UPLOAD
# (rimangono visibili per 30 secondi, poi spariscono)
# ============================================================
if 'upload_messages' in st.session_state and st.session_state.upload_messages:
    _msg_age = time.time() - st.session_state.get('upload_messages_time', 0)
    if _msg_age < 30:
        for _msg in st.session_state.upload_messages:
            st.markdown(_msg, unsafe_allow_html=True)
    else:
        st.session_state.upload_messages = []


# 🔥 GESTIONE FILE CARICATI
if uploaded_files:
    # Pulisci messaggi precedenti all'inizio di un nuovo caricamento
    st.session_state.upload_messages = []
    # 🚫 BLOCCO POST-DELETE: Se c'è flag force_empty, ignora file caricati
    if st.session_state.get('force_empty_until_upload', False):
        st.warning("⚠️ **Hai appena eliminato tutte le fatture.** Clicca su 'Ripristina upload' prima di caricare nuovi file.")
        st.info("💡 Usa il pulsante '🔄 Ripristina upload' sopra per sbloccare il caricamento.")
        st.stop()  # Blocca esecuzione per evitare ricaricamento automatico
    
    # 🔒 RATE LIMIT UPLOAD: max file e dimensione totale
    if len(uploaded_files) > MAX_FILES_PER_UPLOAD:
        st.error(f"⚠️ Puoi caricare al massimo **{MAX_FILES_PER_UPLOAD} file** per volta. Hai selezionato {len(uploaded_files)} file.")
        st.stop()
    
    _total_upload_bytes = sum(f.size for f in uploaded_files)
    _max_upload_bytes = MAX_UPLOAD_TOTAL_MB * 1024 * 1024
    if _total_upload_bytes > _max_upload_bytes:
        _total_mb = _total_upload_bytes / (1024 * 1024)
        st.error(f"⚠️ Dimensione totale troppo grande: **{_total_mb:.0f} MB** (max {MAX_UPLOAD_TOTAL_MB} MB). Riduci il numero di file.")
        st.stop()
    
    # 🚀 PROGRESS BAR IMMEDIATA: Mostra subito che stiamo lavorando
    upload_placeholder = st.empty()
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text(f"🔍 Analisi di {len(uploaded_files)} file in corso...")
    
    # QUERY FILE GIÀ CARICATI SU SUPABASE (con filtro userid obbligatorio)
    
    try:
        # Verifica user_id disponibile
        user_data = st.session_state.get('user_data', {})
        user_id = user_data.get('id')
        if not user_id:
            logger.error("❌ user_id mancante in session_state durante query file")
            file_su_supabase = set()
        else:
            ristorante_id = st.session_state.get('ristorante_id')
            
            # ⚠️ Controllo: ristorante_id DEVE essere presente
            if not ristorante_id:
                logger.warning(f"⚠️ ristorante_id mancante per user {user_id} - rischio falsi positivi cross-ristorante")
            
            # Tentativo 1: Usa RPC function se disponibile (query aggregata SQL lato server)
            try:
                # 🔧 RPC con filtro multi-ristorante
                rpc_params = {'p_user_id': user_id}
                if ristorante_id:
                    rpc_params['p_ristorante_id'] = ristorante_id
                response_rpc = supabase.rpc('get_distinct_files', rpc_params).execute()
                # Tieni i nomi COMPLETI (con estensione) dal DB per confronto primario
                file_su_supabase_full = {row["file_origine"].strip().lower()
                                        for row in response_rpc.data 
                                        if row.get("file_origine") and row["file_origine"].strip()}
                # Nomi base (senza estensione) per confronto secondario XML/PDF
                file_su_supabase = {get_nome_base_file(row["file_origine"]) 
                                   for row in response_rpc.data 
                                   if row.get("file_origine") and row["file_origine"].strip()}
                logger.info(f"🔍 Query file DB: ristorante_id={ristorante_id}, trovati {len(file_su_supabase_full)} file distinti")
                    
            except Exception as rpc_error:
                # Fallback: Query normale ma ottimizzata CON PAGINAZIONE
                logger.warning(f"RPC function non disponibile, uso query normale con paginazione: {rpc_error}")
                
                file_su_supabase = set()
                file_su_supabase_full = set()
                page = 0
                page_size = 1000
                max_pages = 100  # Safety guard: max 100k righe
                
                while page < max_pages:
                    try:
                        offset = page * page_size
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
                            
                        for row in response.data:
                            if row.get("file_origine") and row["file_origine"].strip():
                                file_su_supabase_full.add(row["file_origine"].strip().lower())
                                file_su_supabase.add(get_nome_base_file(row["file_origine"]))
                        
                        if len(response.data) < page_size:
                            break
                            
                        page += 1
                        
                    except Exception as page_error:
                        logger.error(f"Errore paginazione pagina {page}: {page_error}")
                        break
                
                logger.info(f"🔍 Query file DB (fallback): ristorante_id={ristorante_id}, trovati {len(file_su_supabase_full)} file distinti")
        
        # 🔍 VERIFICA COERENZA: Se DB è vuoto ma session ha file, è un errore -> reset
        if len(file_su_supabase) == 0 and len(st.session_state.files_processati_sessione) > 0:
            logger.warning(f"⚠️ INCOERENZA RILEVATA: DB vuoto ma session ha {len(st.session_state.files_processati_sessione)} file -> RESET")
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
        
    except Exception as e:
        logger.exception(f"Errore caricamento file da DB per user_id={st.session_state.user_data.get('id')}")
        logger.error(f"Errore caricamento file da DB: {e}")
        st.error("❌ Errore nel caricamento dei dati. Riprova.")
        file_su_supabase = set()
        file_su_supabase_full = set()


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
    # Assicura che file_su_supabase_full esista (potrebbe mancare se errore prima)
    if 'file_su_supabase_full' not in locals():
        file_su_supabase_full = set()
    
    file_nuovi = []
    file_gia_processati = []
    
    just_uploaded = st.session_state.get('just_uploaded_files', set())
    
    for file in file_unici:
        filename = file.name
        filename_lower = filename.strip().lower()
        nome_base = get_nome_base_file(filename)
        
        # ── Confronto a 2 livelli ──────────────────────────────────
        # 1° LIVELLO: match ESATTO sul nome file completo (affidabile)
        # 2° LIVELLO: match sul nome base senza estensione (cattura XML/PDF stesso doc)
        is_exact_match = filename_lower in file_su_supabase_full
        is_base_match = nome_base in file_su_supabase
        is_just_uploaded = nome_base in just_uploaded
        
        if is_exact_match or is_base_match or is_just_uploaded:
            file_gia_processati.append(filename)
            # Log dettagliato per diagnosi
            reason = []
            if is_exact_match: reason.append('nome esatto in DB')
            if is_base_match and not is_exact_match: reason.append(f'nome base "{nome_base}" in DB')
            if is_just_uploaded: reason.append('appena caricato')
            logger.info(f"📋 SKIP '{filename}' → {', '.join(reason)}")
        # Protezione: Salta file che hanno già dato errore in questa sessione
        elif filename in st.session_state.get('files_con_errori', set()):
            continue
        else:
            file_nuovi.append(file)
    
    logger.info(f"📊 Dedup risultato: {len(file_nuovi)} nuovi, {len(file_gia_processati)} già presenti, {duplicate_count} duplicati upload")
    
    # Log file scartati come DUPLICATE_SKIPPED (solo quelli già nel DB, non appena caricati in sessione)
    if file_gia_processati:
        try:
            _uid = st.session_state.user_data.get('id', '')
            _email = st.session_state.user_data.get('email', 'unknown')
            for _fname in file_gia_processati:
                if get_nome_base_file(_fname) not in just_uploaded:
                    log_upload_event(
                        user_id=_uid,
                        user_email=_email,
                        file_name=_fname,
                        status='DUPLICATE_SKIPPED',
                        supabase_client=supabase
                    )
        except Exception as _log_ex:
            logger.warning(f"Errore logging duplicate skip: {_log_ex}")
    
    # Messaggio SOLO per ADMIN (interfaccia pulita per clienti)
    is_admin = st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False)
    
    # Salva riferimento a just_uploaded PRIMA di pulirlo
    erano_just_uploaded = just_uploaded.copy() if just_uploaded else set()
    
    # Sopprimi messaggi se arriviamo da AVVIA AI (flag one-shot)
    if st.session_state.get('suppress_upload_messages_once', False):
        st.session_state.suppress_upload_messages_once = False
    
    # ✅ Pulizia flag just_uploaded
    if erano_just_uploaded:
        st.session_state.just_uploaded_files = set()
    
    # ============================================================
    # ELABORAZIONE FILE NUOVI (solo se ci sono)
    # ============================================================
    
    # Riepilogo base per questa selezione (aggiornato dopo l'elaborazione)
    upload_summary = {
        'totale_selezionati': len(uploaded_names),
        'gia_presenti': len({n for n in uploaded_unique if (get_nome_base_file(n) in file_su_supabase or get_nome_base_file(n) in erano_just_uploaded)}),
        'duplicati_upload': duplicate_count,
        'nuovi_da_elaborare': len(file_nuovi),
        'caricate_successo': 0,
        'errori': 0
    }
    
    if file_nuovi:
        # Aggiorna progress bar: inizio elaborazione
        status_text.text(f"📄 Elaborazione {len(file_nuovi)} fatture...")
        
        # Contatori per statistiche DETTAGLIATE
        file_processati = 0
        righe_batch = 0
        salvati_supabase = 0
        salvati_json = 0
        errori = []
        file_ok = []
        file_note_credito = []
        file_errore = {}
        
        try:
            # Mostra animazione AI
            mostra_loading_ai(upload_placeholder, f"Analisi AI di {len(file_nuovi)} Fatture")
            
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
                    status_text.text(f"📄 Elaborazione {idx_globale}/{total_files}: {file.name[:TRUNCATE_DESC_LOG]}...")
                    
                    # Routing automatico per tipo file con TRY/EXCEPT ROBUSTO
                    try:
                        # ⚡ Validazione dimensione file (0-byte / file vuoti)
                        file_content = file.getvalue()
                        if not file_content or len(file_content) == 0:
                            raise ValueError(f"File vuoto (0 byte): {file.name}")
                        file.seek(0)  # Reset posizione dopo getvalue()
                        
                        # 🔒 Validazione magic bytes (verifica contenuto reale vs estensione)
                        _ext = nome_file.rsplit('.', 1)[-1].lower() if '.' in nome_file else ''
                        _magic_ok = False
                        if _ext == 'xml':
                            # XML: deve iniziare con <?xml o <  (BOM UTF-8 opzionale)
                            _head = file_content[:100].lstrip(b'\xef\xbb\xbf')  # strip BOM
                            _magic_ok = _head.lstrip().startswith((b'<?xml', b'<'))
                        elif _ext == 'p7m':
                            # P7M (PKCS#7/CMS): ASN.1 DER encoding starts with 0x30
                            _magic_ok = len(file_content) > 2 and file_content[0:1] == b'\x30'
                        elif _ext == 'pdf':
                            _magic_ok = file_content[:5] == b'%PDF-'
                        elif _ext in ('jpg', 'jpeg'):
                            _magic_ok = file_content[:2] == b'\xff\xd8'
                        elif _ext == 'png':
                            _magic_ok = file_content[:4] == b'\x89PNG'
                        
                        if not _magic_ok:
                            raise ValueError(f"Il contenuto del file non corrisponde all'estensione .{_ext}")
                        
                        if nome_file.endswith('.xml'):
                            items = estrai_dati_da_xml(file)
                        elif nome_file.endswith('.p7m'):
                            xml_stream = estrai_xml_da_p7m(file)
                            items = estrai_dati_da_xml(xml_stream)
                        elif nome_file.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                            items = estrai_dati_da_scontrino_vision(file)
                        else:
                            raise ValueError("Formato non supportato")
                        
                        # Validazione risultato parsing
                        if items is None:
                            raise ValueError("Parsing ritornato None")
                        if len(items) == 0:
                            raise ValueError("Nessuna riga estratta - DataFrame vuoto")
                        
                        # ============================================================
                        # VALIDAZIONE P.IVA CESSIONARIO (Anti-abuso)
                        # ═══════════════════════════════════════════════════════════════
                        # VALIDAZIONE P.IVA MULTI-RISTORANTE
                        # Applicata solo a XML e PDF (NON a immagini)
                        # ═══════════════════════════════════════════════════════════════
                        # ⚠️ SKIP anche per immagini JPG/PNG (solo XML e PDF)
                        is_image = nome_file.endswith(('.jpg', '.jpeg', '.png'))
                        
                        if not is_admin and not is_image:
                            # Estrai P.IVA dal cessionario (dalla prima riga - items è lista di dict)
                            piva_cessionario = None
                            if isinstance(items, list) and len(items) > 0:
                                piva_cessionario = items[0].get('piva_cessionario')
                            elif isinstance(items, dict):
                                piva_cessionario = items.get('piva_cessionario')
                            
                            # P.IVA ristorante ATTUALMENTE SELEZIONATO (multi-ristorante aware)
                            piva_attiva = st.session_state.get('partita_iva')
                            nome_ristorante_attivo = st.session_state.get('nome_ristorante', 'N/A')
                            
                            logger.info(f"🔍 Validazione P.IVA {file.name} - rist_id={st.session_state.get('ristorante_id')}")
                            
                            # ✅ CASO 2: P.IVA presente → VALIDAZIONE STRICT MULTI-RISTORANTE
                            if piva_attiva and piva_cessionario:
                                piva_cessionario_norm = normalizza_piva(piva_cessionario)
                                piva_attiva_norm = normalizza_piva(piva_attiva)
                                
                                if piva_cessionario_norm != piva_attiva_norm:
                                    # 🚫 BLOCCO: P.IVA non corrisponde al ristorante selezionato
                                    
                                    logger.warning(
                                        f"⚠️ UPLOAD BLOCCATO {file.name} - user_id={st.session_state.get('user_data', {}).get('id')} "
                                        f"P.IVA mismatch (rist_id={st.session_state.get('ristorante_id')})"
                                    )
                                    raise ValueError("🚫 FATTURA NON VALIDA - P.IVA FATTURA DIVERSA DA P.IVA AZIENDA")
                                else:
                                    # ✅ P.IVA match: log successo
                                    logger.info(f"✅ Validazione OK: P.IVA match per rist_id={st.session_state.get('ristorante_id')}")
                        
                        else:
                            # Admin/Impersonazione: log per debug (bypass validazione)
                            piva_cessionario = None
                            if isinstance(items, list) and len(items) > 0:
                                piva_cessionario = items[0].get('piva_cessionario')
                            logger.debug(f"👨‍💼 Admin upload {file.name} - P.IVA fattura: {piva_cessionario} (validazione bypassata)")
                        
                        # ============================================================
                        # BLOCCO FATTURE ANNO PRECEDENTE (per clienti non-admin)
                        # ============================================================
                        # Se il flag blocco_anno_precedente è attivo in pagine_abilitate,
                        # impedisci caricamento fatture con data_documento < 1 Gennaio anno corrente.
                        # Admin e impersonificati bypassano sempre.
                        if not is_admin:
                            _pagine_cfg = st.session_state.get('user_data', {}).get('pagine_abilitate') or {}
                            if _pagine_cfg.get('blocco_anno_precedente', True):
                                _data_doc = None
                                if isinstance(items, list) and len(items) > 0:
                                    _data_doc = items[0].get('Data_Documento') or items[0].get('data_documento')
                                if _data_doc and _data_doc != 'N/A':
                                    try:
                                        _dt_doc = pd.to_datetime(_data_doc)
                                        _anno_corrente = pd.Timestamp.now().year
                                        if _dt_doc.year < _anno_corrente:
                                            logger.warning(
                                                f"📅 UPLOAD BLOCCATO {file.name} - Data {_data_doc} precedente al {_anno_corrente} "
                                                f"(user: {st.session_state.get('user_data', {}).get('email')})"
                                            )
                                            raise ValueError(
                                                f"ANNO PRECEDENTE - La data documento ({_data_doc}) è precedente al "
                                                f"1 Gennaio {_anno_corrente}. È possibile caricare solo fatture dell'anno corrente."
                                            )
                                    except ValueError:
                                        raise
                                    except Exception:
                                        pass  # Se la data non è parsabile, lascia passare
                        
                        # Salva in memoria se trovati dati (SILENZIOSO)
                        result = salva_fattura_processata(file.name, items, silent=True)
                        
                        if result["success"]:
                            file_processati += 1
                            righe_batch += result["righe"]
                            if result["location"] == "supabase":
                                salvati_supabase += 1
                            elif result["location"] == "json":
                                salvati_json += 1
                            
                            # Rimuovi flag force empty: ci sono nuovi dati
                            if 'force_empty_until_upload' in st.session_state:
                                del st.session_state.force_empty_until_upload
                            
                            # Traccia successo (aggiungi sia nome completo che base normalizzato)
                            file_ok.append(file.name)
                            # Rileva nota di credito (TD04)
                            if isinstance(items, list) and len(items) > 0:
                                if str(items[0].get('tipo_documento', '')).upper().strip() == 'TD04':
                                    file_note_credito.append(file.name)
                            st.session_state.files_processati_sessione.add(file.name)
                            # Aggiungi anche nome base per prevenire duplicati con estensione diversa
                            st.session_state.files_processati_sessione.add(get_nome_base_file(file.name))
                            
                            # 🔥 FIX BUG #1: Rimuovi da files_con_errori se presente (file ora ha successo)
                            st.session_state.files_con_errori.discard(file.name)
                        else:
                            raise ValueError(f"Errore salvataggio: {result.get('error', 'Sconosciuto')}")
                    
                    except Exception as e:
                        # TRACCIA ERRORE DETTAGLIATO (silenzioso - solo log)
                        full_error = str(e)
                        error_msg = full_error[:TRUNCATE_ERROR_DISPLAY] + ("..." if len(full_error) > TRUNCATE_ERROR_DISPLAY else "")
                        logger.exception(f"❌ Errore elaborazione {file.name}: {full_error}")
                        file_errore[file.name] = error_msg
                        errori.append(f"{file.name}: {error_msg}")
                        
                        # NON mostrare errore qui (evita duplicati) - verrà mostrato nel report finale
                        
                        # ============================================================
                        # 🔥 FIX BUG #2: NON aggiungere a files_processati_sessione
                        # altrimenti il file viene skippato per sempre e non può riprovare
                        # ============================================================
                        # st.session_state.files_processati_sessione.add(file.name)  # ❌ RIMOSSO
                        
                        st.session_state.files_con_errori.add(file.name)
                        
                        # Salva anche in report persistente (per mostrarlo dopo download)
                        st.session_state.files_errori_report[file.name] = error_msg
                        
                        # Log upload event FAILED
                        try:
                            user_id = st.session_state.user_data.get("id")
                            user_email = st.session_state.user_data.get("email", "unknown")
                            error_stage = "PARSING" if file.name.endswith(('.xml', '.p7m')) else "VISION"
                            
                            log_upload_event(
                                user_id=user_id,
                                user_email=user_email,
                                file_name=file.name,
                                status="FAILED",
                                rows_parsed=0,
                                rows_saved=0,
                                error_stage=error_stage,
                                error_message=error_msg,
                                details={"exception_type": type(e).__name__},
                                supabase_client=supabase
                            )
                        except Exception as log_error:
                            logger.error(f"Errore logging failed event: {log_error}")
                        
                        # CONTINUA con il prossimo file invece di crashare
                        continue
                
                # ============================================================
                # PAUSA TRA BATCH (rate limit OpenAI + liberazione memoria)
                # ============================================================
                if batch_end < total_files:
                    time.sleep(BATCH_RATE_LIMIT_DELAY)  # Pausa tra batch per evitare rate limit
        
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
        # REPORT FINALE UNIFICATO
        # ============================================
        
        # Raccogli TUTTI i file problematici (errori elaborazione + duplicati)
        tutti_problematici = {}
        if file_errore:
            tutti_problematici.update(file_errore)
        for fname in file_gia_processati:
            tutti_problematici[fname] = "Già presente nel database"
        
        # === SALVA MESSAGGI IN SESSION_STATE (persistono fino al prossimo upload) ===
        _messages = []
        if file_processati > 0:
            msg_ok = f"1 fattura caricata" if file_processati == 1 else f"{file_processati} fatture caricate"
            _messages.append(f'<div style="padding:10px 16px;background:#d4edda;border-left:5px solid #28a745;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#155724;">✅ {msg_ok} con successo!</span></div>')
            # Messaggio aggiuntivo per note di credito
            if file_note_credito:
                nc_nomi = ", ".join(_html.escape(f) for f in file_note_credito)
                nc_n = len(file_note_credito)
                nc_lbl = "nota di credito caricata" if nc_n == 1 else "note di credito caricate"
                _messages.append(f'<div style="padding:10px 16px;background:#cce5ff;border-left:5px solid #004085;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#004085;">ℹ️ Attenzione: {nc_n} {nc_lbl}: </span><span style="font-size:0.82rem;color:#004085;">{nc_nomi}</span></div>')
        
        if tutti_problematici:
            n = len(tutti_problematici)
            # ── Raggruppa file per motivo di scarto ──
            motivi_raggruppati = defaultdict(list)
            for fname, motivo in tutti_problematici.items():
                # Normalizza motivi per raggruppamento leggibile
                if motivo == "Già presente nel database":
                    motivo_label = "Già caricata in precedenza (duplicata)"
                elif "P.IVA FATTURA DIVERSA" in motivo:
                    motivo_label = "P.IVA della fattura diversa da quella dell'azienda"
                elif "ANNO PRECEDENTE" in motivo:
                    motivo_label = "Data fattura dell'anno precedente"
                else:
                    motivo_label = motivo
                motivi_raggruppati[motivo_label].append(fname)
            
            # Costruisci HTML con dettaglio per motivo
            lbl = "fattura scartata" if n == 1 else "fatture scartate"
            dettaglio_html = ""
            for motivo, files_list in motivi_raggruppati.items():
                nomi_files = ", ".join(_html.escape(f) for f in files_list)
                dettaglio_html += f'<div style="margin-top:6px;"><span style="font-size:0.82rem;font-weight:600;color:#856404;">📌 {_html.escape(motivo)} ({len(files_list)}):</span><br/><span style="font-size:0.78rem;color:#856404;">{nomi_files}</span></div>'
            
            _messages.append(f'<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #ffc107;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#856404;">⚠️ {n} {lbl}:</span>{dettaglio_html}</div>')
            # Segna come processati per evitare ri-elaborazione
            for nome_file in tutti_problematici:
                st.session_state.files_processati_sessione.add(nome_file)
                st.session_state.files_processati_sessione.add(get_nome_base_file(nome_file))
        
        st.session_state.upload_messages = _messages
        st.session_state.upload_messages_time = time.time()
        st.session_state.files_errori_report = {}
        st.session_state.files_con_errori = set()
        
        if file_processati > 0 or tutti_problematici:
            st.cache_data.clear()
            invalida_cache_memoria()
            if 'righe_ai_appena_categorizzate' in st.session_state:
                st.session_state.righe_ai_appena_categorizzate = []
            if 'uploader_key' not in st.session_state:
                st.session_state.uploader_key = 0
            st.session_state.uploader_key += 1
            st.session_state.just_uploaded_files = set()
            st.session_state.files_processati_sessione = set()
            st.session_state.ultimo_upload_ids = []
            upload_summary['caricate_successo'] = file_processati
            upload_summary['errori'] = len(tutti_problematici)
            st.session_state.last_upload_summary = upload_summary
            st.rerun()
        else:
            upload_summary['caricate_successo'] = 0
            upload_summary['errori'] = len(tutti_problematici)
            st.session_state.last_upload_summary = upload_summary

    else:
        # Nessun file nuovo — TUTTI duplicati/già presenti
        # Mostra progress bar rapida anche per duplicati
        total_check = len(uploaded_files)
        for i in range(total_check):
            progress_bar.progress((i + 1) / total_check)
            status_text.text(f"🔍 Verifica {i + 1}/{total_check}: {uploaded_files[i].name[:TRUNCATE_DESC_LOG]}...")
            time.sleep(0.05)
        
        upload_placeholder.empty()
        progress_bar.empty()
        status_text.empty()
        
        st.session_state.last_upload_summary = upload_summary
        
        # Salva messaggio persistente per duplicati
        if file_gia_processati:
            nomi = ", ".join(_html.escape(f) for f in file_gia_processati)
            n = len(file_gia_processati)
            lbl = "fattura scartata perché già caricata in precedenza (duplicata)" if n == 1 else "fatture scartate perché già caricate in precedenza (duplicate)"
            st.session_state.upload_messages = [
                f'<div style="padding:10px 16px;background:#fff3cd;border-left:5px solid #ffc107;border-radius:6px;margin-bottom:8px;"><span style="font-size:0.88rem;font-weight:600;color:#856404;">⚠️ {n} {lbl}:</span><br/><span style="font-size:0.78rem;color:#856404;">{nomi}</span></div>'
            ]
            st.session_state.upload_messages_time = time.time()
            # Segna come processati
            for nome_file in file_gia_processati:
                st.session_state.files_processati_sessione.add(nome_file)
                st.session_state.files_processati_sessione.add(get_nome_base_file(nome_file))
        
        # Pulizia stato e reset uploader
        st.session_state.files_errori_report = {}
        st.session_state.files_con_errori = set()
        if 'uploader_key' not in st.session_state:
            st.session_state.uploader_key = 0
        st.session_state.uploader_key += 1
        logger.info(f"⚠️ {len(file_gia_processati)} fatture duplicate - stato pulito automaticamente")
        st.rerun()


# 🔥 CARICA E MOSTRA STATISTICHE SEMPRE (da Supabase)
# ⚡ RIUSA df_cache caricato sopra (evita doppia query DB)


# Crea placeholder per loading
loading_placeholder = st.empty()


try:
    # Mostra animazione AI durante caricamento
    mostra_loading_ai(loading_placeholder, "Caricamento Dashboard AI")
    
    # Riusa dati già caricati (df_cache) - evita seconda chiamata a carica_e_prepara_dataframe
    df_completo = df_cache
    
    loading_placeholder.empty()
    
    # Mostra dashboard direttamente senza messaggi
    if not df_completo.empty:
        mostra_statistiche(df_completo)
    else:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


except Exception as e:
    loading_placeholder.empty()
    logger.error(f"Errore durante il caricamento: {e}")
    st.error("❌ Errore durante il caricamento del file. Riprova.")
    logger.exception("Errore caricamento dashboard")
