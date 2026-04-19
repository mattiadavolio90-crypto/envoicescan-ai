"""
Helper per query multi-ristorante: Aggiunge automaticamente filtro ristorante_id
"""
import streamlit as st
from config.logger_setup import get_logger

logger = get_logger(__name__)

ADMIN_TEST_WORKSPACE_NAME = "Ambiente Test Admin"
ADMIN_TEST_WORKSPACE_RAGIONE_SOCIALE = "Workspace Test Admin"
ADMIN_TEST_WORKSPACE_PIVA = "00000000000"


def is_pure_admin_session() -> bool:
    """True se la sessione corrente è admin puro e non in impersonificazione."""
    try:
        return bool(
            st.session_state.get('user_is_admin', False)
            and not st.session_state.get('impersonating', False)
        )
    except Exception as e:
        logger.debug(f"Errore verifica pure admin session: {e}")
        return False


def ensure_admin_test_workspace(supabase_client, user: dict):
    """Recupera o crea il workspace test dedicato all'admin corrente."""
    user_id = (user or {}).get('id')
    if not supabase_client or not user_id:
        return None

    try:
        response = (
            supabase_client.table('ristoranti')
            .select('id, nome_ristorante, partita_iva, ragione_sociale, user_id')
            .eq('user_id', user_id)
            .eq('attivo', True)
            .order('nome_ristorante')
            .execute()
        )
        existing = response.data or []
    except Exception as e:
        logger.error(f"❌ Errore caricamento workspace admin: {e}")
        existing = []

    preferred = next(
        (
            r for r in existing
            if str(r.get('nome_ristorante') or '').strip().lower() == ADMIN_TEST_WORKSPACE_NAME.lower()
        ),
        None,
    )
    if preferred:
        return preferred

    payload = {
        'user_id': user_id,
        'nome_ristorante': ADMIN_TEST_WORKSPACE_NAME,
        'partita_iva': (
            str((user or {}).get('partita_iva') or '').strip()
            if str((user or {}).get('partita_iva') or '').strip().isdigit()
            and len(str((user or {}).get('partita_iva') or '').strip()) == 11
            else ADMIN_TEST_WORKSPACE_PIVA
        ),
        'ragione_sociale': ADMIN_TEST_WORKSPACE_RAGIONE_SOCIALE,
        'attivo': True,
    }

    try:
        created = supabase_client.table('ristoranti').insert(payload).execute()
        if created.data:
            logger.info(f"🧪 Workspace test admin creato: user_id={user_id}")
            return created.data[0]
    except Exception as e:
        logger.warning(f"⚠️ Creazione workspace test admin fallita: {e}")

    if existing:
        logger.info(f"ℹ️ Fallback su workspace admin esistente: user_id={user_id}")
        return existing[0]

    return None

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
        # Rilancia: meglio fallire visibilmente che mostrare dati non filtrati
        raise


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
