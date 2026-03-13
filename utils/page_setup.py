"""Utility condivise per il setup delle pagine Streamlit."""

import json
import streamlit as st
from config.logger_setup import get_logger
from services import get_supabase_client

logger = get_logger('page_setup')


@st.cache_data(ttl=60)
def _fetch_pagine_abilitate(user_id: str):
    """Query DB per pagine_abilitate con cache 60s."""
    supabase = get_supabase_client()
    try:
        result = supabase.table('users').select('pagine_abilitate').eq('id', user_id).execute()
        if result.data:
            return result.data[0].get('pagine_abilitate')
    except Exception as e:
        logger.warning(f"Errore query pagine_abilitate per {user_id}: {e}")
    return None


def check_page_enabled(page_key: str, user_id: str):
    """
    Controlla se la pagina è abilitata per l'utente leggendo dal DB (cached 60s).
    Sincronizza anche session_state.user_data['pagine_abilitate'].
    Se non abilitata, mostra warning e blocca la pagina con st.stop().
    """
    pagine_raw = _fetch_pagine_abilitate(user_id)
    if pagine_raw is not None:
        st.session_state.user_data['pagine_abilitate'] = pagine_raw
        logger.debug(f"pagine_abilitate dal DB per {user_id}: {pagine_raw}")
    else:
        logger.warning(f"Utente {user_id} non trovato o errore DB durante check pagina '{page_key}'")

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
