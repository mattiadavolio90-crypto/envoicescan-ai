"""Utility condivise per il setup delle pagine Streamlit."""

import json
import streamlit as st
from config.logger_setup import get_logger
from services import get_supabase_client

logger = get_logger('page_setup')


def check_page_enabled(page_key: str, user_id: str):
    """
    Controlla se la pagina è abilitata per l'utente leggendo dal DB.
    Sincronizza anche session_state.user_data['pagine_abilitate'].
    Se non abilitata, mostra warning e blocca la pagina con st.stop().
    """
    supabase = get_supabase_client()

    try:
        result = supabase.table('users').select('pagine_abilitate').eq('id', user_id).execute()
        if result.data:
            pagine_raw = result.data[0].get('pagine_abilitate')
            st.session_state.user_data['pagine_abilitate'] = pagine_raw
            logger.debug(f"pagine_abilitate dal DB per {user_id}: {pagine_raw}")
        else:
            pagine_raw = st.session_state.get('user_data', {}).get('pagine_abilitate')
            logger.warning(f"Utente {user_id} non trovato in DB, uso session_state: {pagine_raw}")
    except Exception as e:
        pagine_raw = st.session_state.get('user_data', {}).get('pagine_abilitate')
        logger.warning(f"Errore query pagine_abilitate per {user_id}: {e}, uso session_state: {pagine_raw}")

    if isinstance(pagine_raw, str):
        try:
            pagine_raw = json.loads(pagine_raw)
        except Exception:
            pagine_raw = None

    # Default: workspace abilitato solo se non specificato
    pagine_abilitate = pagine_raw if isinstance(pagine_raw, dict) else {}

    is_enabled = pagine_abilitate.get(page_key, True)
    if not is_enabled:
        logger.info(f"Pagina '{page_key}' BLOCCATA per utente {user_id} (pagine={pagine_abilitate})")
        st.warning("⚠️ Questa pagina non è abilitata per il tuo account. Contatta l'amministratore.")
        st.stop()
