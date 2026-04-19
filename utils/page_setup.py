"""Utility condivise per il setup delle pagine Streamlit."""

import json
import streamlit as st
from config.logger_setup import get_logger
from services import get_supabase_client

logger = get_logger('page_setup')

# Pagine opzionali: se la chiave manca in users.pagine_abilitate,
# il default deve essere FALSE per rollout sicuro.
OPTIONAL_PAGES = {
    'workspace',
    'analisi_personalizzata',
}


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

    Admin e sessioni in impersonazione bypassano sempre il gating.
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

    pagine_abilitate = pagine_raw if isinstance(pagine_raw, dict) else {}

    if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
        logger.debug(f"Bypass pagina '{page_key}' per admin/impersonazione (user={user_id})")
        return

    default_enabled = False if page_key in OPTIONAL_PAGES else True
    is_enabled = pagine_abilitate.get(page_key, default_enabled)
    if not is_enabled:
        logger.info(f"Pagina '{page_key}' BLOCCATA per utente {user_id} (pagine={pagine_abilitate})")
        st.warning("⚠️ Questa pagina non è abilitata per il tuo account. Contatta l'amministratore.")
        st.stop()
