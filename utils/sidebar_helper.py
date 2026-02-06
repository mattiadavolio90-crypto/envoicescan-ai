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
    # CSS: nasconde navigazione automatica e pulsante chiusura sidebar
    st.markdown("""
        <style>
        [data-testid="stSidebarNav"] {display: none;}
        [data-testid="collapsedControl"] {display: none !important;}
        button[kind="header"] {display: none !important;}
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
        
        # Link pagine comuni
        st.markdown("#### 📋 Pagine")
        if st.button("🏠 Dashboard Principale", use_container_width=True, key="sidebar_dashboard"):
            st.switch_page("app.py")
        
        if st.button("🍴 Workspace Ricette", use_container_width=True, key="sidebar_workspace"):
            st.switch_page("pages/workspace.py")
        
        if st.button("🔐 Cambio Password", use_container_width=True, key="sidebar_password"):
            st.switch_page("pages/cambio_password.py")
        
        if st.button("📜 Privacy Policy", use_container_width=True, key="sidebar_privacy"):
            st.switch_page("pages/privacy_policy.py")
        
        # Sezione Admin (solo per admin)
        if user_email in ADMIN_EMAILS:
            st.markdown("---")
            st.markdown("#### ⚙️ Amministrazione")
            if st.button("🔑 Pannello Admin", use_container_width=True, type="primary", key="sidebar_admin"):
                st.switch_page("pages/admin.py")
            
            if st.button("👥 Gestione Account", use_container_width=True, key="sidebar_gestione"):
                st.switch_page("pages/gestione_account.py")
