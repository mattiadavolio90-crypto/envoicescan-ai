"""Utility condivise per il setup delle pagine Streamlit."""

import json
import streamlit as st
from services import get_supabase_client


def check_page_enabled(page_key: str, user_id: str):
    """
    Controlla se la pagina è abilitata per l'utente leggendo dal DB.
    Sincronizza anche session_state.user_data['pagine_abilitate'].
    Se non abilitata, mostra warning e blocca la pagina con st.stop().
    """
    supabase = get_supabase_client()
    user = st.session_state.user_data

    try:
        result = supabase.table('users').select('pagine_abilitate').eq('id', user_id).execute()
        if result.data:
            pagine_raw = result.data[0].get('pagine_abilitate')
            st.session_state.user_data['pagine_abilitate'] = pagine_raw
        else:
            pagine_raw = user.get('pagine_abilitate')
    except Exception:
        pagine_raw = user.get('pagine_abilitate')

    if isinstance(pagine_raw, str):
        try:
            pagine_raw = json.loads(pagine_raw)
        except Exception:
            pagine_raw = None

    pagine_abilitate = pagine_raw or {'marginalita': True, 'workspace': True}

    if not pagine_abilitate.get(page_key, True):
        st.warning("⚠️ Questa pagina non è abilitata per il tuo account. Contatta l'amministratore.")
        st.stop()
