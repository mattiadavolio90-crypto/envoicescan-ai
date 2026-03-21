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
)

from .auth_service import (
    verify_and_migrate_password,
    verifica_credenziali,
    invia_codice_reset,
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
    # Auth functions
    'verify_and_migrate_password',
    'verifica_credenziali',
    'invia_codice_reset',
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
import os
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

def _get_supabase_credentials() -> tuple[str, str]:
    """
    Risolve URL e key Supabase con doppio fallback:
      1. st.secrets (Streamlit Cloud / app UI)
      2. variabili d'ambiente (worker CLI, GitHub Actions, test locali)
    Questo permette di usare get_supabase_client() sia dall'UI che dal worker.
    """
    # --- Tentativo 1: st.secrets (presente solo quando gira dentro Streamlit) ---
    try:
        import streamlit as st
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return url, key
    except Exception:
        pass

    # --- Tentativo 2: env vars (worker / GitHub Actions / test locali) ---
    url = os.environ.get("SUPABASE_URL", "")
    # Il worker usa la service_role key per bypassare RLS;
    # se non presente, cade sulla anon key per retrocompatibilità.
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY", "")
    )
    if url and key:
        return url, key

    raise RuntimeError(
        "Credenziali Supabase non trovate. "
        "Imposta SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY nelle env vars."
    )


def get_supabase_client():
    """
    Restituisce un client Supabase.
    - Dentro Streamlit: usa st.secrets + cache @st.cache_resource.
    - Fuori Streamlit (worker CLI): crea client diretto da env vars.

    Returns:
        Client Supabase configurato
    """
    options = SyncClientOptions(
        postgrest_client_timeout=30,
        storage_client_timeout=30,
    )
    # Usa cache Streamlit solo quando Streamlit è in esecuzione
    try:
        import streamlit as st
        # Verifica che lo script context sia attivo (non solo il modulo importato)
        _ = st.secrets["supabase"]["url"]

        # Definizione locale della versione cached — eseguita solo in contesto Streamlit
        @st.cache_resource(ttl=3600)
        def _cached_client():
            url, key = _get_supabase_credentials()
            return create_client(url, key, options=options)

        return _cached_client()
    except Exception:
        # Fuori Streamlit: client senza cache (worker gestisce il proprio ciclo di vita)
        url, key = _get_supabase_credentials()
        return create_client(url, key, options=options)

