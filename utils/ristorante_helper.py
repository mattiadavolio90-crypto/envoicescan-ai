"""
Helper per query multi-ristorante: Aggiunge automaticamente filtro ristorante_id
"""
import streamlit as st
from config.logger_setup import get_logger

logger = get_logger(__name__)

def add_ristorante_filter(query, ristorante_id=None):
    """
    Aggiunge automaticamente filtro ristorante_id a una query Supabase.
    
    Args:
        query: Query Supabase (già con .eq('user_id', ...))
        ristorante_id: Optional - se None usa session_state
    
    Returns:
        query: Query con filtro ristorante_id aggiunto
    
    Example:
        query = supabase.table("fatture").select("*").eq("user_id", user_id)
        query = add_ristorante_filter(query)
        result = query.execute()
    """
    try:
        # Se ristorante_id non fornito, prendi da session_state
        if ristorante_id is None:
            ristorante_id = st.session_state.get('ristorante_id')
        
        # Aggiungi filtro solo se ristorante_id presente (multi-ristorante attivo)
        if ristorante_id:
            query = query.eq("ristorante_id", ristorante_id)
            logger.debug(f"🔍 Filtro ristorante_id aggiunto: {ristorante_id}")
        
        return query
    except Exception as e:
        logger.error(f"❌ Errore in add_ristorante_filter: {e}")
        # In caso di errore, ritorna query inalterata per non bloccare l'app
        return query


def get_current_ristorante_id():
    """
    Recupera ristorante_id corrente dalla sessione.
    
    Returns:
        str: UUID del ristorante o None
    """
    try:
        return st.session_state.get('ristorante_id')
    except Exception as e:
        logger.error(f"❌ Errore recupero ristorante_id: {e}")
        return None


def is_multi_ristorante_active():
    """
    Verifica se l'utente ha multi-ristorante attivo.
    
    Returns:
        bool: True se utente ha più di 1 ristorante
    """
    ristoranti = st.session_state.get('ristoranti', [])
    return len(ristoranti) > 1
