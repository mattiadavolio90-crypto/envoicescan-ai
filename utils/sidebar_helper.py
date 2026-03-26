"""
Helper per renderizzare sidebar e header condivisi in tutte le pagine
"""
import streamlit as st
import html as _html
import os
from config.constants import ADMIN_EMAILS
from config.logger_setup import get_logger

logger = get_logger('sidebar_helper')


def render_oh_yeah_header():
    """
    Renderizza il titolo 'OH YEAH!' centrato in alto, 
    un po' più grande dei titoli di pagina ma non troppo.
    Da richiamare in ogni pagina PRIMA del contenuto.
    """
    st.markdown("""
<div style="text-align: center; margin-bottom: 2rem; margin-top: -2rem;">
    <h1 style="font-size: clamp(3.5rem, 7vw, 5rem); font-weight: 900; margin: 0; letter-spacing: 3px; line-height: 1.1; display: inline-flex; align-items: flex-end; gap: 0.3rem;">
        <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;">OH YEAH!</span>
        <span style="font-size: clamp(1rem, 2vw, 1.5rem); font-weight: 700; color: #1e3a8a; letter-spacing: 2px; margin-bottom: 0.8rem;">app</span>
    </h1>
</div>
""", unsafe_allow_html=True)


def render_sidebar(user_data: dict):
    """
    Renderizza sidebar con navigazione condivisa
    
    Args:
        user_data: Dizionario con dati utente (deve contenere 'email')
    """
    # ⚠️ SAFETY CHECK: Non renderizzare sidebar se utente non loggato
    if not st.session_state.get('logged_in', False):
        # Nasconde immediatamente la sidebar
        from utils.ui_helpers import hide_sidebar_css
        hide_sidebar_css()
        return
    
    # CSS: nasconde navigazione automatica, pulsante chiusura, e FORZA sidebar sempre aperta
    st.markdown("""
        <style>
        /* Nasconde navigazione automatica e pulsante chiusura */
        [data-testid="stSidebarNav"] {display: none !important;}
        [data-testid="collapsedControl"] {display: none !important; pointer-events: none !important;}
        button[kind="header"] {display: none !important;}
        
        /* Forza sidebar SEMPRE visibile e aperta */
        [data-testid="stSidebar"],
        section[data-testid="stSidebar"] {
            display: flex !important;
            visibility: visible !important;
            width: 260px !important;
            min-width: 260px !important;
            max-width: 260px !important;
            opacity: 1 !important;
            transform: none !important;
            position: relative !important;
        }
        
        /* Nasconde freccia/pulsante chiudi sidebar */
        [data-testid="stSidebar"] button[aria-label="Close"],
        [data-testid="stSidebar"] button[aria-label="Chiudi"],
        [data-testid="stSidebar"] [data-testid="baseButton-header"],
        [data-testid="stSidebar"] button[kind="headerNoPadding"],
        .stSidebar [data-testid="collapsedControl"],
        div[data-testid="collapsedControl"] {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
            width: 0 !important;
            height: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    with st.sidebar:
        # Nome app in alto
        st.markdown("""
        <div style="text-align: center; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 2px solid #e2e8f0;">
            <div style="display: inline-flex; align-items: flex-end; gap: 0.2rem;">
                <span style="font-size: 1.4rem; font-weight: 900; letter-spacing: 1px;
                    background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;">OH YEAH!</span>
                <span style="font-size: 0.7rem; font-weight: 700; color: #1e3a8a; letter-spacing: 1px; margin-bottom: 0.3rem;">app</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Info utente
        user_email = user_data.get('email', 'Utente')
        _is_pure_admin_sidebar = (
            user_email.lower() in [e.lower() for e in ADMIN_EMAILS]
            and not st.session_state.get('impersonating', False)
        )
        if _is_pure_admin_sidebar:
            nome_ristorante = "Amministratore"
        else:
            nome_ristorante = st.session_state.get('nome_ristorante') or user_data.get('nome_ristorante') or 'Ristorante'
        
        # Escape HTML per prevenire XSS
        user_email_safe = _html.escape(user_email)
        nome_ristorante_safe = _html.escape(nome_ristorante)
        
        st.markdown(f"""
        <div style="background: #e0f2fe;
                    padding: clamp(0.75rem, 2vw, 1rem);
                    border-radius: 10px;
                    border: 2px solid #0ea5e9;
                    margin-bottom: 1.25rem;">
            <div style="font-size: clamp(0.65rem, 1.5vw, 0.75rem); color: #0369a1; opacity: 0.9; margin-bottom: 0.3rem; font-weight: 600;">👤 Account</div>
            <div title="{user_email_safe}" style="font-size: clamp(0.75rem, 1.8vw, 0.875rem); font-weight: 700; color: #0c4a6e; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{user_email_safe}</div>
            <div title="{nome_ristorante_safe}" style="font-size: clamp(0.6rem, 1.4vw, 0.7rem); color: #0369a1; opacity: 0.8; margin-top: 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{nome_ristorante_safe}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Rileva pagina corrente tramite sys._getframe (O(1), evita inspect.stack())
        current_script = ''
        try:
            import sys
            frame = sys._getframe(1)
            # Risali max 10 frame per trovare il file pagina (molto più veloce di inspect.stack())
            _page_names = {'app.py', '1_calcolo_margine.py', '2_workspace.py', '3_controllo_prezzi.py',
                           'gestione_account.py', 'privacy_policy.py', 'admin.py'}
            for _ in range(10):
                if frame is None:
                    break
                fname = os.path.basename(frame.f_code.co_filename)
                if fname in _page_names:
                    current_script = fname
                    break
                frame = frame.f_back
        except Exception as e:
            logger.debug(f"Frame inspection fallita: {e}")
        
        # CSS per forzare colore blu uniforme sui bottoni attivi della sidebar
        # Usa selettore specifico per la sidebar così non tocca il resto dell'app
        st.markdown("""
        <style>
        [data-testid="stSidebar"] button[kind="primary"] {
            background-color: #2563eb !important;
            border-color: #2563eb !important;
            color: white !important;
            font-weight: 600 !important;
        }
        [data-testid="stSidebar"] button[kind="primary"]:hover {
            background-color: #1d4ed8 !important;
            border-color: #1d4ed8 !important;
        }
        [data-testid="stSidebar"] button[kind="primary"]:active,
        [data-testid="stSidebar"] button[kind="primary"]:focus {
            background-color: #2563eb !important;
            border-color: #2563eb !important;
            color: white !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # ============================================
        # SEZIONE OPERATIVO
        # ============================================
        # Admin puro (non impersonificato) vede SOLO pannello admin
        _is_pure_admin = user_email in ADMIN_EMAILS and not is_admin_impersonating
        
        if not _is_pure_admin:
            st.markdown("### 📋 Sezioni e Funzioni")
            
            if st.button("🧠 Analisi Fatture AI", use_container_width=True, key="sidebar_dashboard",
                         type="primary" if current_script == 'app.py' else "secondary"):
                st.switch_page("app.py")
            
            # Pagine abilitabili dall'admin
            _pagine_raw = st.session_state.get('user_data', {}).get('pagine_abilitate')
            if isinstance(_pagine_raw, str):
                import json
                try:
                    _pagine_raw = json.loads(_pagine_raw)
                except Exception as e:
                    logger.warning(f"Errore parsing pagine_abilitate sidebar: {e}")
                    _pagine_raw = {}
            pagine_abilitate = _pagine_raw if isinstance(_pagine_raw, dict) else {}
            
            if st.button("🔍 Controllo Prezzi", use_container_width=True, key="sidebar_controllo_prezzi",
                         type="primary" if current_script == '3_controllo_prezzi.py' else "secondary"):
                st.switch_page("pages/3_controllo_prezzi.py")
            
            if st.button("💰 Calcolo Marginalità", use_container_width=True, key="sidebar_margine",
                         type="primary" if current_script == '1_calcolo_margine.py' else "secondary"):
                st.switch_page("pages/1_calcolo_margine.py")
            
            if pagine_abilitate.get('workspace', True):
                if st.button("🍴 Workspace", use_container_width=True, key="sidebar_workspace",
                             type="primary" if current_script == '2_workspace.py' else "secondary"):
                    st.switch_page("pages/2_workspace.py")
        
        st.markdown("---")
        
        # ============================================
        # SEZIONE ACCOUNT
        # ============================================
        st.markdown("### 👤 Account")
        
        if st.button("⚙️ Gestione Account", use_container_width=True, key="sidebar_gestione",
                     type="primary" if current_script == 'gestione_account.py' else "secondary"):
            st.switch_page("pages/gestione_account.py")
        
        if st.button("🔒 Privacy Policy", use_container_width=True, key="sidebar_privacy",
                     type="primary" if current_script == 'privacy_policy.py' else "secondary"):
            st.switch_page("pages/privacy_policy.py")
        
        # ============================================
        # SEZIONE AMMINISTRAZIONE (solo per admin)
        # ============================================
        if user_email in ADMIN_EMAILS or st.session_state.get('impersonating', False):
            st.markdown("---")
            st.markdown("### 👨‍💼 Amministrazione")
            if st.button("🔑 Pannello Admin", use_container_width=True, key="sidebar_admin",
                         type="primary" if current_script == 'admin.py' else "secondary"):
                st.switch_page("pages/admin.py")
        
        # ============================================
        # LOGOUT (in fondo)
        # ============================================
        st.markdown("---")
        
        # CSS per bottone logout rosso
        st.markdown("""
            <style>
            button[key="sidebar_logout"] {
                background-color: #dc2626 !important;
                color: white !important;
                border: 1px solid #dc2626 !important;
            }
            button[key="sidebar_logout"]:hover {
                background-color: #b91c1c !important;
                border: 1px solid #b91c1c !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        if st.button("Logout", use_container_width=True, type="primary", key="sidebar_logout"):
            # 1. Registra logout nel database
            try:
                from services.auth_service import registra_logout_utente
                user_email_logout = st.session_state.get('user_data', {}).get('email')
                if user_email_logout:
                    registra_logout_utente(user_email_logout)
            except Exception as e:
                logger.warning(f"Errore registrazione logout: {e}")
            
            # 2. INVALIDA session_token nel DB (CRITICO: deve avvenire QUI,
            #    perché in un'app multipage ?logout=1 potrebbe non raggiungere app.py)
            try:
                from services import get_supabase_client
                _sb = get_supabase_client()
                _email_logout = st.session_state.get('user_data', {}).get('email')
                if _email_logout:
                    _sb.table('users').update({'session_token': None}).eq('email', _email_logout).execute()
                    logger.info(f"🔒 Session token invalidato per: {_email_logout}")
            except Exception as _te:
                logger.warning(f"Errore invalidazione session_token: {_te}")
            
            # 3. Pulisci session_state e forza redirect
            st.session_state.clear()
            st.session_state.logged_in = False
            st.session_state._cookie_checked = True
            st.query_params["logout"] = "1"
            st.rerun()
