"""
Helper per renderizzare sidebar condivisa in tutte le pagine
"""
import streamlit as st
from config.constants import ADMIN_EMAILS


def render_sidebar(user_data: dict):
    """
    Renderizza sidebar con navigazione condivisa
    
    Args:
        user_data: Dizionario con dati utente (deve contenere 'email')
    """
    # ⚠️ SAFETY CHECK: Non renderizzare sidebar se utente non loggato
    if not st.session_state.get('logged_in', False):
        # Nasconde immediatamente la sidebar
        st.markdown("""
            <style>
            [data-testid="stSidebar"],
            section[data-testid="stSidebar"] {
                display: none !important;
                visibility: hidden !important;
                width: 0 !important;
            }
            </style>
        """, unsafe_allow_html=True)
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
        # Info utente
        user_email = user_data.get('email', 'Utente')
        nome_ristorante = st.session_state.get('nome_ristorante', 'Ristorante')
        
        st.markdown(f"""
        <div style="background: #e0f2fe;
                    padding: 15px;
                    border-radius: 10px;
                    border: 2px solid #0ea5e9;
                    margin-bottom: 20px;">
            <div style="font-size: 12px; color: #0369a1; opacity: 0.9; margin-bottom: 5px; font-weight: 600;">👤 Account</div>
            <div style="font-size: 14px; font-weight: 700; color: #0c4a6e;">{user_email}</div>
            <div style="font-size: 11px; color: #0369a1; opacity: 0.8; margin-top: 5px;">{nome_ristorante}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # ============================================
        # SEZIONE OPERATIVO
        # ============================================
        st.markdown("### 📊 Operativo")
        if st.button("🏠 Dashboard Principale", use_container_width=True, key="sidebar_dashboard"):
            st.switch_page("app.py")
        
        if st.button("🍴 Workspace Ricette", use_container_width=True, key="sidebar_workspace"):
            st.switch_page("pages/workspace.py")
        
        st.markdown("---")
        
        # ============================================
        # SEZIONE ACCOUNT
        # ============================================
        st.markdown("### 👤 Account")
        if st.button("🔐 Cambio Password", use_container_width=True, key="sidebar_password"):
            st.switch_page("pages/cambio_password.py")
        
        if st.button("📜 Privacy Policy", use_container_width=True, key="sidebar_privacy"):
            st.switch_page("pages/privacy_policy.py")
        
        # ============================================
        # SEZIONE AMMINISTRAZIONE (solo per admin)
        # ============================================
        if user_email in ADMIN_EMAILS:
            st.markdown("---")
            st.markdown("### 👨‍💼 Amministrazione")
            if st.button("🔑 Pannello Admin", use_container_width=True, type="primary", key="sidebar_admin"):
                st.switch_page("pages/admin.py")
            
            if st.button("👥 Gestione Account", use_container_width=True, key="sidebar_gestione"):
                st.switch_page("pages/gestione_account.py")
        
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
            # Reset completo session_state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
            # Redirect automatico alla pagina di login
            st.switch_page("app.py")
