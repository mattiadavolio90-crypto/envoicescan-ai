"""
Services Package
Contiene la business logic dell'applicazione organizzata per dominio.

Services disponibili:
- ai_service: Classificazione AI e gestione memoria prodotti
- auth_service: Autenticazione, login e reset password
- invoice_service: Parsing fatture XML/PDF e salvataggio
- db_service: ✅ Query e analisi database (caricamento, alert, sconti)
"""

from .ai_service import (
    carica_memoria_completa,
    invalida_cache_memoria,
    ottieni_categoria_prodotto,
    categorizza_con_memoria,
    applica_correzioni_dizionario,
    salva_correzione_in_memoria_globale,
    salva_correzione_in_memoria_locale,
    classifica_con_ai,
    mostra_loading_ai,
    # Legacy functions (deprecate)
    carica_memoria_ai,
    salva_memoria_ai,
    aggiorna_memoria_ai
)

from .auth_service import (
    verify_and_migrate_password,
    verifica_credenziali,
    invia_codice_reset,
    hash_password,
)

from .invoice_service import (
    estrai_dati_da_xml,
    estrai_dati_da_scontrino_vision,
    salva_fattura_processata,
)

from .db_service import (
    carica_e_prepara_dataframe,
    ricalcola_prezzi_con_sconti,
    calcola_alert,
    carica_sconti_e_omaggi,
)

__all__ = [
    # Core AI functions
    'carica_memoria_completa',
    'invalida_cache_memoria',
    'ottieni_categoria_prodotto',
    'categorizza_con_memoria',
    'applica_correzioni_dizionario',
    'salva_correzione_in_memoria_globale',
    'salva_correzione_in_memoria_locale',
    'classifica_con_ai',
    'mostra_loading_ai',
    # Legacy functions
    'carica_memoria_ai',
    'salva_memoria_ai',
    'aggiorna_memoria_ai',
    # Auth functions
    'verify_and_migrate_password',
    'verifica_credenziali',
    'invia_codice_reset',
    'hash_password',
    # Invoice functions
    'estrai_dati_da_xml',
    'estrai_dati_da_scontrino_vision',
    'salva_fattura_processata',
    # DB functions
    'carica_e_prepara_dataframe',
    'ricalcola_prezzi_con_sconti',
    'calcola_alert',
    'carica_sconti_e_omaggi',
    # Supabase singleton
    'get_supabase_client',
]

# ============================================
# SUPABASE SINGLETON (Cached Resource)
# ============================================
import streamlit as st
from supabase import create_client

@st.cache_resource
def get_supabase_client():
    """
    Restituisce istanza singleton del client Supabase.
    Cached per tutta la sessione dell'app per evitare ricreare connessioni.
    
    Returns:
        Client Supabase configurato
    """
    return create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"]
    )

