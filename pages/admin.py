"""
🔧 PANNELLO AMMINISTRAZIONE - OH YEAH! Hub
===============================================
Pannello admin con 5 TAB:
- Gestione Clienti (con impersonazione)
- Review Righe €0 (con revisione permanente)
- Memoria AI (globale, clienti, conflitti, audit)
- Verifica Integrità Database
- Costi AI per Cliente
"""

import streamlit as st
import pandas as pd
import json
import re
import html as _html
from datetime import datetime, timezone, timedelta
import time
import traceback
import plotly.express as px
import extra_streamlit_components as stx
import requests

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

# Import corretto da utils (non da app.py per evitare esecuzione interfaccia)
from utils.formatters import carica_categorie_da_db
from utils.text_utils import estrai_nome_categoria, aggiungi_icona_categoria, pulisci_caratteri_corrotti
from utils.validation import is_dicitura_sicura, is_sconto_omaggio_sicuro
from utils.piva_validator import valida_formato_piva, normalizza_piva
from services.auth_service import crea_cliente_con_token, verifica_sessione_da_cookie
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header

# Importa costanti per filtri e admin
from config.constants import CATEGORIE_SPESE_GENERALI, ADMIN_EMAILS, CATEGORIE_FOOD_BEVERAGE, CATEGORIE_MATERIALI, CATEGORIE_SPESE_OPERATIVE

# ============================================================
# SETUP
# ============================================================

# Import singleton Supabase e utilities
from services import get_supabase_client
from config.logger_setup import get_logger

# Setup logging (usa configurazione centralizzata)
logger = get_logger('admin')

# Setup pagina
st.set_page_config(
    page_title="Pannello Admin", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.admin-metrics-grid {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 20px;
}
.admin-metric-card {
    flex: 1 1 clamp(9.5rem, 18vw, 13rem);
    min-width: min(100%, clamp(9.5rem, 18vw, 13rem));
    max-width: 100%;
    border-radius: 12px;
    padding: clamp(0.7rem, 1.4vw, 0.9rem) clamp(0.8rem, 1.8vw, 1rem);
    text-align: center;
    box-sizing: border-box;
}
.admin-metric-card--compact {
    flex-basis: clamp(8.5rem, 16vw, 11rem);
    min-width: min(100%, clamp(8.5rem, 16vw, 11rem));
    padding: clamp(0.65rem, 1.2vw, 0.8rem);
}
.admin-metric-label {
    font-size: clamp(0.72rem, 0.55vw + 0.58rem, 0.82rem);
    font-weight: 600;
    line-height: 1.35;
    overflow-wrap: anywhere;
}
.admin-metric-value {
    font-size: clamp(1.1rem, 1vw + 0.85rem, 1.6rem);
    font-weight: 700;
    line-height: 1.2;
    overflow-wrap: anywhere;
}
.admin-note-inline {
    font-size: clamp(0.72rem, 0.45vw + 0.62rem, 0.8rem);
    color: #888;
    margin-top: 4px;
    line-height: 1.4;
    overflow-wrap: anywhere;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# CONNESSIONE SUPABASE (usa singleton condiviso)
# ============================================================

# Ottieni client Supabase singleton
supabase = get_supabase_client()

# CookieManager sempre attivo (usato sia per sessione che per cookie impersonazione)
try:
    _cookie_manager_admin = stx.CookieManager(key="cookie_manager_admin")
except Exception as _ce_adm:
    _cookie_manager_admin = None
    logger.warning(f"CookieManager non disponibile in admin: {_ce_adm}")

# ============================================================
# RIPRISTINO SESSIONE DA COOKIE (session_token + timeout inattività)
# ============================================================
try:
    # Inizializza logged_in se non esiste
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Ripristina sessione da token cookie se non loggato
    if not st.session_state.logged_in and _cookie_manager_admin is not None:
        _token_admin = _cookie_manager_admin.get("session_token")
        
        if _token_admin:
            _u_admin = verifica_sessione_da_cookie(_token_admin, inactivity_hours=8)
            if _u_admin:
                st.session_state.logged_in = True
                st.session_state.user_data = _u_admin
                logger.info(f"✅ Sessione admin ripristinata da session_token")
            else:
                logger.info("🔒 Session token admin non valido o scaduto")
except Exception as e:
    logger.error(f'Errore controllo cookie sessione: {e}')

# ============================================================
# CHECK AUTENTICAZIONE
# ============================================================

# Nascondi sidebar immediatamente se non loggato
if not st.session_state.get('logged_in', False):
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()

if not st.session_state.get('logged_in', False):
    st.switch_page("app.py")

user = st.session_state.get('user_data', {})

is_impersonating = st.session_state.get('impersonating', False)
admin_original_user = st.session_state.get('admin_original_user', {})
admin_original_email = (admin_original_user.get('email') or '').strip().lower()
is_admin_impersonating = is_impersonating and admin_original_email in ADMIN_EMAILS

if (user.get('email') or '').strip().lower() not in ADMIN_EMAILS:
    # Se l'admin sta impersonando un cliente, consenti accesso al pannello
    # ripristinando automaticamente l'utente admin originale.
    if is_admin_impersonating:
        # Verifica integrità dati admin prima del ripristino
        if not admin_original_user.get('email') or (admin_original_user['email'] or '').strip().lower() not in ADMIN_EMAILS:
            logger.critical(f"⛔ Tentativo ripristino admin con email non autorizzata: {admin_original_user.get('email')}")
            st.session_state.clear()
            st.session_state.logged_in = False
            st.error("⛔ Sessione compromessa. Effettua un nuovo login.")
            st.stop()
        st.session_state.user_data = admin_original_user.copy()
        st.session_state.user_is_admin = True
        st.session_state.impersonating = False
        if 'admin_original_user' in st.session_state:
            del st.session_state.admin_original_user
        user = st.session_state.get('user_data', {})
        # Pulisci cookie impersonazione
        if _cookie_manager_admin is not None:
            try:
                _cookie_manager_admin.set("impersonation_user_id", "",
                                          expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
            except Exception as ce:
                logger.warning(f"Errore reset cookie impersonazione: {ce}")
        logger.info(f"🔙 Ripristino automatico admin da impersonazione: {user.get('email')}")
        st.info("🔙 Sessione admin ripristinata")
    else:
        st.error("⛔ Accesso riservato agli amministratori")
        st.stop()

# ============================================================
# SIDEBAR CONDIVISA
# ============================================================
render_sidebar(user)

# ============================================================
# INIZIALIZZAZIONE RISTORANTI (come in app.py)
# ============================================================
# Gli admin vedono TUTTI i ristoranti, quindi non impostiamo ristorante_id specifico
# Se necessario caricare ristoranti per operazioni specifiche:
if 'ristoranti' not in st.session_state:
    try:
        user_id = st.session_state.user_data.get('id')
        if user_id:
            ristoranti_response = supabase.table('ristoranti').select('id, nome_ristorante, partita_iva').eq('user_id', user_id).execute()
            if ristoranti_response.data:
                st.session_state.ristoranti = ristoranti_response.data
                logger.info(f"✅ {len(ristoranti_response.data)} ristoranti caricati per admin")
    except Exception as e:
        logger.error(f"Errore caricamento ristoranti admin: {e}")

# ============================================================
# HELPER FUNCTIONS

def invalida_cache_memoria():
    """Invalida ENTRAMBE le cache: Streamlit cache_data + cache in-memory ai_service."""
    st.cache_data.clear()
    # 🔧 FIX: Invalida anche cache in-memory di ai_service (altrimenti resta stale!)
    try:
        from services.ai_service import invalida_cache_memoria as invalida_cache_ai
        invalida_cache_ai()
    except ImportError:
        pass
    logger.info("✅ Cache memoria invalidata (Streamlit + in-memory)")


def _merge_and_save_pagina_abilitata(user_id: str, page_key: str, enabled: bool) -> dict:
    """
    Aggiorna una singola chiave in users.pagine_abilitate facendo merge con il JSONB esistente.
    Non sovrascrive le altre chiavi già presenti.
    """
    current_resp = supabase.table('users').select('pagine_abilitate').eq('id', user_id).execute()
    current_raw = current_resp.data[0].get('pagine_abilitate') if current_resp.data else {}

    if isinstance(current_raw, str):
        try:
            current_raw = json.loads(current_raw)
        except Exception:
            current_raw = {}

    current_pagine = current_raw if isinstance(current_raw, dict) else {}
    merged_pagine = dict(current_pagine)
    merged_pagine[page_key] = enabled

    supabase.table('users')\
        .update({'pagine_abilitate': merged_pagine})\
        .eq('id', user_id)\
        .execute()

    # Invalida cache globale + cache specifica della lista clienti admin.
    st.cache_data.clear()
    try:
        _carica_stats_clienti_admin.clear()
    except Exception:
        pass

    return merged_pagine


def _is_valid_email_format(email: str) -> bool:
    """Validazione base formato email."""
    if not email:
        return False
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return re.fullmatch(pattern, email) is not None


def _email_exists_for_other_user(email: str, user_id: str) -> bool:
    """Ritorna True se l'email esiste gia' per un altro utente."""
    try:
        try:
            resp = supabase.table('users')\
                .select('id, email')\
                .ilike('email', email)\
                .limit(1)\
                .execute()
        except Exception:
            # Fallback se ilike non e' supportato dal client in uso.
            resp = supabase.table('users')\
                .select('id, email')\
                .eq('email', email)\
                .limit(1)\
                .execute()

        if not resp.data:
            return False

        return str(resp.data[0].get('id')) != str(user_id)
    except Exception as e:
        logger.warning(f"Errore verifica email duplicata: {e}")
        return True  # fail-safe: block the change if uncertain


# ──────────────────────────────────────────────────────────
# CACHED: Statistiche clienti per Tab1 (query pesanti)
# ──────────────────────────────────────────────────────────

def _empty_stats() -> dict:
    return {
        'num_fatture': 0,
        'num_righe': 0,
        'ultimo_caricamento': None,
        'totale_costi': 0.0,
        'debug': {
            'totale_raw': 0,
            'escluse_note': 0,
            'escluse_review': 0,
            'escluse_date_invalide': 0,
            'incluse_finale': 0,
            'somma_totale_riga': 0.0,
            'righe_con_date': []
        }
    }

def _update_stats_bucket(bucket: dict, row: dict):
    bucket['num_righe'] += 1

    file_origine = row.get('file_origine')
    if file_origine:
        bucket['_file_unici'].add(file_origine)

    created_at = row.get('created_at')
    if created_at:
        try:
            dt = pd.to_datetime(created_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if bucket['ultimo_caricamento'] is None or dt > bucket['ultimo_caricamento']:
                bucket['ultimo_caricamento'] = dt
        except Exception:
            pass

    debug = bucket['debug']
    debug['totale_raw'] += 1

    try:
        categoria = str(row.get('categoria', '')).strip()
        needs_review = row.get('needs_review', False)
        data_documento = row.get('data_documento')
        totale_riga = float(row.get('totale_riga', 0) or 0)

        if categoria == '📝 NOTE E DICITURE':
            debug['escluse_note'] += 1
            return

        if needs_review:
            debug['escluse_review'] += 1
            return

        try:
            data_dt = pd.to_datetime(data_documento, errors='coerce')
            if pd.isna(data_dt):
                debug['escluse_date_invalide'] += 1
                return
        except (ValueError, TypeError):
            debug['escluse_date_invalide'] += 1
            return

        debug['incluse_finale'] += 1
        debug['somma_totale_riga'] += totale_riga
        bucket['totale_costi'] += totale_riga

        if len(debug['righe_con_date']) < 5:
            debug['righe_con_date'].append({
                'data': str(data_documento),
                'importo': totale_riga,
                'categoria': categoria
            })
    except Exception as e:
        logger.warning(f"Errore calcolo costo riga {row.get('id')}: {e}")

def _finalize_bucket(bucket: dict) -> dict:
    return {
        'num_fatture': len(bucket.get('_file_unici', set())),
        'num_righe': bucket.get('num_righe', 0),
        'ultimo_caricamento': bucket.get('ultimo_caricamento'),
        'totale_costi': bucket.get('totale_costi', 0.0),
        'debug': bucket.get('debug', _empty_stats()['debug'])
    }


@st.cache_data(ttl=300, show_spinner="⏳ Caricamento statistiche clienti...")
def _carica_stats_clienti_admin(admin_emails_tuple: tuple):
    """
    Carica e aggrega statistiche per tutti i clienti (non-admin).
    Cached per 300 secondi per evitare query pesanti ad ogni rerun.
    
    Returns:
        tuple: (stats_clienti_list, has_piva_column, has_pagine_column)
    """
    from services import get_supabase_client
    sb = get_supabase_client()
    admin_emails_set = set(admin_emails_tuple)

    # 1) Query utenti - fallback progressivi per colonne mancanti
    has_piva_column = True
    has_pagine_column = True

    _MISSING_COL = ('42703', 'does not exist', 'PGRST204', 'Could not find')

    try:
        query_users = sb.table('users')\
            .select('id, email, nome_ristorante, attivo, created_at, partita_iva, ragione_sociale, pagine_abilitate')\
            .order('email')\
            .execute()
    except Exception as col_err:
        if not any(k in str(col_err) for k in _MISSING_COL):
            raise col_err
        # Potrebbe mancare pagine_abilitate: riprova senza
        has_pagine_column = False
        try:
            query_users = sb.table('users')\
                .select('id, email, nome_ristorante, attivo, created_at, partita_iva, ragione_sociale')\
                .order('email')\
                .execute()
        except Exception as col_err2:
            if not any(k in str(col_err2) for k in _MISSING_COL):
                raise col_err2
            # Manca anche partita_iva (migration 009 non eseguita)
            query_users = sb.table('users')\
                .select('id, email, nome_ristorante, attivo, created_at')\
                .order('email')\
                .execute()
            has_piva_column = False

    if not query_users.data:
        return [], has_piva_column, has_pagine_column

    clienti_non_admin = [u for u in query_users.data if (u.get('email') or '').strip().lower() not in admin_emails_set]
    if not clienti_non_admin:
        return [], has_piva_column, has_pagine_column

    user_ids = [u['id'] for u in clienti_non_admin if u.get('id')]

    # 2) Carica ristoranti attivi in batch
    ristoranti_by_user = {}
    try:
        for i in range(0, len(user_ids), 100):
            chunk_ids = user_ids[i:i + 100]
            rist_resp = sb.table('ristoranti')\
                .select('id, user_id, nome_ristorante, partita_iva, ragione_sociale')\
                .eq('attivo', True)\
                .in_('user_id', chunk_ids)\
                .execute()
            for rist in (rist_resp.data or []):
                ristoranti_by_user.setdefault(rist['user_id'], []).append(rist)
    except Exception as e:
        logger.warning(f"Errore caricamento batch ristoranti: {e}")

    # 3) Carica fatture in batch con paginazione
    stats_by_user = {}
    stats_by_rist = {}

    for i in range(0, len(user_ids), 100):
        chunk_ids = user_ids[i:i + 100]
        offset = 0
        page_size = 1000

        while True:
            fatture_resp = sb.table('fatture')\
                .select('user_id, ristorante_id, file_origine, created_at, data_documento, totale_riga, categoria, needs_review')\
                .in_('user_id', chunk_ids)\
                .order('created_at', desc=False)\
                .range(offset, offset + page_size - 1)\
                .execute()

            rows = fatture_resp.data or []
            if not rows:
                break

            for row in rows:
                uid = row.get('user_id')
                rid = row.get('ristorante_id')

                if uid not in stats_by_user:
                    base = _empty_stats()
                    base['_file_unici'] = set()
                    stats_by_user[uid] = base
                _update_stats_bucket(stats_by_user[uid], row)

                key = (uid, rid)
                if key not in stats_by_rist:
                    base = _empty_stats()
                    base['_file_unici'] = set()
                    stats_by_rist[key] = base
                _update_stats_bucket(stats_by_rist[key], row)

            if len(rows) < page_size:
                break
            offset += page_size

    # 4) Costruisci righe finali
    stats_clienti = []
    for user_data in clienti_non_admin:
        user_id = user_data['id']
        ristoranti_utente = ristoranti_by_user.get(user_id, [])

        if ristoranti_utente:
            for rist in ristoranti_utente:
                stats = _finalize_bucket(stats_by_rist.get((user_id, rist['id']), {'_file_unici': set(), **_empty_stats()}))
                stats_clienti.append({
                    'user_id': user_id,
                    'ristorante_id': rist['id'],
                    'email': user_data['email'],
                    'ristorante': rist['nome_ristorante'],
                    'attivo': user_data.get('attivo', True),
                    'pagine_abilitate': user_data.get('pagine_abilitate') or {},
                    'partita_iva': rist.get('partita_iva'),
                    'ragione_sociale': rist.get('ragione_sociale', ''),
                    'num_fatture': stats['num_fatture'],
                    'num_righe': stats['num_righe'],
                    'ultimo_caricamento': stats['ultimo_caricamento'],
                    'totale_costi': stats['totale_costi'],
                    'debug': stats['debug']
                })
        else:
            stats = _finalize_bucket(stats_by_user.get(user_id, {'_file_unici': set(), **_empty_stats()}))
            stats_clienti.append({
                'user_id': user_id,
                'ristorante_id': None,
                'email': user_data['email'],
                'ristorante': user_data.get('nome_ristorante') or "❌ Nessun Ristorante",
                'attivo': user_data.get('attivo', True),
                'pagine_abilitate': user_data.get('pagine_abilitate') or {},
                'partita_iva': user_data.get('partita_iva'),
                'ragione_sociale': user_data.get('ragione_sociale', ''),
                'num_fatture': stats['num_fatture'],
                'num_righe': stats['num_righe'],
                'ultimo_caricamento': stats['ultimo_caricamento'],
                'totale_costi': stats['totale_costi'],
                'debug': stats['debug']
            })

    return stats_clienti, has_piva_column, has_pagine_column


# ============================================================
# HEADER
# ============================================================

render_oh_yeah_header()
st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
    👨‍💼 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Pannello Amministrazione</span>
</h2>
""", unsafe_allow_html=True)
st.caption(f"Admin: {user.get('email')} | [🏠 Torna all'App](/) | [🔓 Cambia Password](/gestione_account)")
st.markdown("---")

# ============================================================
# TABS PRINCIPALI CON PERSISTENZA
# ============================================================

# Inizializza tab attivo in session_state (default = 0)
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

# Cache categorie in session_state (carica 1 sola volta)
if 'categorie_cached' not in st.session_state:
    st.session_state.categorie_cached = carica_categorie_da_db(supabase_client=supabase)
    logger.info(f"✅ Categorie caricate in cache: {len(st.session_state.categorie_cached)} categorie")

# Usa radio buttons nascosti per mantenere tab attivo
tab_names = ["📊 Gestione Clienti", "💰 Review Righe €0", "🧠 Memoria AI", "🔍 Integrità Database", "💳 Costi AI"]

if st.session_state.active_tab >= len(tab_names):
    st.session_state.active_tab = 0
if 'tab_selector' in st.session_state and st.session_state.tab_selector >= len(tab_names):
    st.session_state.tab_selector = 0

selected_tab = st.radio(
    "Seleziona Tab",
    range(len(tab_names)),
    format_func=lambda x: tab_names[x],
    key="tab_selector",
    horizontal=True,
    label_visibility="collapsed"
)

# Aggiorna tab attivo se cambiato dall'utente
if selected_tab != st.session_state.active_tab:
    st.session_state.active_tab = selected_tab

st.markdown("---")

# Mostra solo il contenuto del tab selezionato
tab1 = (st.session_state.active_tab == 0)
tab2 = (st.session_state.active_tab == 1)
tab3 = (st.session_state.active_tab == 2)
tab4 = (st.session_state.active_tab == 3)
tab5 = (st.session_state.active_tab == 4)


# ============================================================
# TAB 1: GESTIONE CLIENTI + IMPERSONAZIONE
# ============================================================

if tab1:
    st.markdown("### 📊 Gestione Clienti e Sedi")
    st.caption("Visualizza statistiche clienti e accedi come utente impersonando account")
    
    # ============================================================
    # CREA NUOVO CLIENTE (solo admin) - GDPR COMPLIANT
    # ============================================================
    # L'admin NON imposta password. Il cliente la imposta via link email.
    # ============================================================
    
    with st.expander("➕ Crea Nuovo Cliente", expanded=False):
        st.info("📧 **GDPR Compliant**: Il cliente riceverà un'email per impostare la propria password. L'admin non conosce mai le password dei clienti.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_email = st.text_input(
                "📧 Email cliente *", 
                key="new_email", 
                placeholder="cliente@esempio.com",
                help="Email per login cliente",
                max_chars=254,
            )
            new_name = st.text_input(
                "🏪 Nome ristorante *", 
                key="new_name", 
                placeholder="Es: Ristorante Da Mario",
                help="Nome locale",
                max_chars=100,
            )
        
        with col2:
            new_piva = st.text_input(
                "🏢 Partita IVA *", 
                key="new_piva", 
                placeholder="12345678901",
                max_chars=11,
                help="11 cifre numeriche"
            )
            new_ragione_sociale = st.text_input(
                "📄 Ragione Sociale", 
                key="new_ragione_sociale", 
                placeholder="Mario Rossi S.r.l. (opzionale)",
                help="Nome ufficiale azienda (opzionale)",
                max_chars=150,
            )
        
        # Validazione real-time P.IVA
        if new_piva:
            piva_norm = normalizza_piva(new_piva)
            if len(piva_norm) == 11:
                valida, msg = valida_formato_piva(piva_norm)
                if valida:
                    st.success(f"✅ P.IVA valida: {piva_norm}")
                else:
                    st.error(msg)
            elif len(piva_norm) > 0:
                st.warning(f"⚠️ P.IVA incompleta: {len(piva_norm)}/11 cifre")
        
        st.markdown("---")
        
        if st.button("🆕 Crea Account e Invia Email", type="primary", use_container_width=True):
            # Validazione input
            errori_form = []
            
            if not new_email or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$', new_email.strip()):
                errori_form.append("❌ Email non valida")
            
            if not new_name:
                errori_form.append("❌ Nome ristorante obbligatorio")
            
            if not new_piva:
                errori_form.append("❌ P.IVA obbligatoria")
            else:
                piva_valida, piva_msg = valida_formato_piva(new_piva)
                if not piva_valida:
                    errori_form.append(piva_msg)
            
            if errori_form:
                for err in errori_form:
                    st.error(err)
            else:
                try:
                    # Crea cliente con token (senza password)
                    successo, messaggio, token = crea_cliente_con_token(
                        email=new_email,
                        nome_ristorante=new_name,
                        partita_iva=new_piva,
                        ragione_sociale=new_ragione_sociale,
                        supabase_client=supabase
                    )
                    
                    if not successo:
                        st.error(messaggio)
                    else:
                        # Se il messaggio contiene warning ristorante, mostralo
                        if "⚠️" in messaggio:
                            st.warning(messaggio)
                        # Invia email con link attivazione
                        email_inviata = False
                        link_attivazione = ""
                        try:
                            brevo_api_key = st.secrets["brevo"]["api_key"]
                            sender_email = st.secrets["brevo"]["sender_email"]
                            app_url = st.secrets.get("app", {}).get("url", "https://envoicescan-ai.streamlit.app")
                            
                            # Link con token per impostare password
                            link_attivazione = f"{app_url}?reset_token={token}"
                            
                            url_brevo = "https://api.brevo.com/v3/smtp/email"
                            
                            email_html = f"""
                            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                <h2 style="color: #2c5aa0;">🎉 Benvenuto in OH YEAH! Hub</h2>
                                <p>Ciao <strong>{_html.escape(new_name)}</strong>,</p>
                                <p>Il tuo account è stato creato con successo dal nostro team.</p>
                                
                                <p><strong>Per iniziare, imposta la tua password personale:</strong></p>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{link_attivazione}" 
                                       style="background-color: #0ea5e9; 
                                              color: white; 
                                              padding: 15px 30px; 
                                              text-decoration: none; 
                                              border-radius: 6px; 
                                              display: inline-block;
                                              font-weight: bold;">
                                        🔐 Imposta Password
                                    </a>
                                </div>
                                
                                <p style="color: #dc2626;">
                                    ⚠️ <strong>Importante:</strong> Questo link scade tra <strong>24 ore</strong> per sicurezza.
                                </p>
                                
                                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                                
                                <p><strong>📧 La tua email di accesso:</strong> {_html.escape(new_email)}</p>
                                <p><strong>🏢 P.IVA registrata:</strong> {_html.escape(normalizza_piva(new_piva))}</p>
                                
                                <p>Dopo aver impostato la password, potrai:</p>
                                <ul>
                                    <li>✅ Caricare fatture XML automaticamente</li>
                                    <li>📊 Vedere dashboard analytics in tempo reale</li>
                                    <li>🔔 Ricevere alert su anomalie prezzi</li>
                                </ul>
                                
                                <p style="margin-top: 30px; color: #666; font-size: 14px;">
                                    <strong>Hai domande?</strong> Rispondi direttamente a questa email, ti risponderemo al più presto!
                                </p>
                                
                                <p style="color: #666; font-size: 14px;">
                                    ---<br>
                                    <strong>OH YEAH! Hub Team</strong><br>
                                    📧 Support: mattiadavolio90@gmail.com
                                </p>
                            </div>
                            """
                            
                            payload = {
                                "sender": {"email": sender_email, "name": "OH YEAH! Hub"},
                                "to": [{"email": new_email, "name": _html.escape(new_name)}],
                                "replyTo": {"email": "mattiadavolio90@gmail.com", "name": "Mattia Davolio - Support"},
                                "subject": f"🆕 Benvenuto {_html.escape(new_name)} - Imposta la tua Password",
                                "htmlContent": email_html
                            }
                            
                            response = requests.post(
                                url_brevo, 
                                json=payload, 
                                headers={
                                    "api-key": brevo_api_key,
                                    "Content-Type": "application/json"
                                },
                                timeout=10
                            )
                            
                            if response.status_code == 201:
                                email_inviata = True
                                logger.info(f"✅ Email attivazione inviata a {new_email}")
                            else:
                                logger.warning(f"⚠️ Email non inviata: {response.status_code} - {response.text}")
                                
                        except Exception as e:
                            logger.error(f"❌ Errore invio email: {e}")
                        
                        # Mostra messaggio di successo
                        if email_inviata:
                            st.success(f"""
                            ✅ **Cliente creato con successo!**
                            
                            📧 Email inviata a: **{new_email}**
                            🔗 Link attivazione valido per: **24 ore**
                            🏢 P.IVA: **{normalizza_piva(new_piva)}**
                            
                            Il cliente riceverà un'email per impostare la propria password.
                            """)
                        else:
                            st.success(f"✅ Cliente {new_email} creato con successo!")
                            st.warning("⚠️ Errore invio email automatico.")
                            st.info(f"""
                            📋 **Comunica manualmente al cliente:**
                            
                            Link attivazione: `{link_attivazione}`
                            
                            Il link scade tra 24 ore.
                            """)
                        
                        logger.info(f"✅ Nuovo cliente creato da admin: {new_email} | P.IVA: {normalizza_piva(new_piva)} | Email: {email_inviata}")
                        _carica_stats_clienti_admin.clear()
                        time.sleep(2)
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Errore creazione cliente: {e}")
                    logger.exception(f"Errore creazione cliente {new_email}")
    
    # ════════════════════════════════════════════════════════════════════════════
    # SEZIONE: GESTIONE MULTI-RISTORANTE
    # ════════════════════════════════════════════════════════════════════════════
    
    with st.expander("🏢 Gestione Multi-Sede", expanded=False):
        st.caption("Aggiungi o rimuovi sedi per cliente (ciascuna con P.IVA unica)")
        
        try:
            # Carica clienti
            query_users_mr = supabase.table('users')\
                .select('id, email, nome_ristorante')\
                .order('email')\
                .execute()
            
            if query_users_mr.data:
                # Dropdown selezione cliente
                cliente_emails = [u['email'] for u in query_users_mr.data]
                cliente_selezionato = st.selectbox(
                    "👤 Seleziona Cliente",
                    options=cliente_emails,
                    key="select_cliente_multi_rist"
                )
                
                if cliente_selezionato:
                    # Trova user selezionato
                    user_sel = next((u for u in query_users_mr.data if u['email'] == cliente_selezionato), None)
                    
                    if user_sel:
                        # Carica ristoranti di questo utente
                        ristoranti_query = supabase.table('ristoranti')\
                            .select('id, nome_ristorante, partita_iva, ragione_sociale, attivo')\
                            .eq('user_id', user_sel['id'])\
                            .execute()
                        
                        ristoranti_list = ristoranti_query.data if ristoranti_query.data else []
                        num_ristoranti = len(ristoranti_list)
                        
                        col_info, col_azioni = st.columns([2, 3])
                        
                        with col_info:
                            st.metric("🏪 Sedi configurate", num_ristoranti)
                            st.caption(f"📧 {cliente_selezionato}")
                            
                            # Lista ristoranti attuali
                            if num_ristoranti > 0:
                                st.markdown("**Sedi attive:**")
                                for idx, r in enumerate(ristoranti_list, 1):
                                    status_icon = "✅" if r.get('attivo') else "🔴"
                                    st.write(f"{idx}. {status_icon} **{r['nome_ristorante']}**")
                                    st.caption(f"   📋 P.IVA: `{r['partita_iva']}` | {r.get('ragione_sociale', 'N/A')}")
                        
                        with col_azioni:
                            # AZIONE: Aggiungi Ristorante
                            # 🔄 Chiave dinamica per forzare reset form dopo creazione
                            form_key = st.session_state.get('form_ristorante_key', 0)
                            
                            with st.expander("➕ Aggiungi Nuova Sede", expanded=False):
                                with st.form(f"form_nuovo_ristorante_{user_sel['id']}_{form_key}"):
                                    st.markdown("**Nuova Sede**")
                                    
                                    new_nome = st.text_input("Nome Sede *", placeholder="Es: Trattoria Mario 2")
                                    new_piva_mr = st.text_input("P.IVA * (11 cifre)", placeholder="12345678901", max_chars=11)
                                    new_ragione_mr = st.text_input("Ragione Sociale", placeholder="Opzionale")
                                    
                                    # Validazione real-time P.IVA
                                    if new_piva_mr:
                                        piva_norm_mr = normalizza_piva(new_piva_mr)
                                        if len(piva_norm_mr) == 11:
                                            valida_mr, msg_mr = valida_formato_piva(piva_norm_mr)
                                            if valida_mr:
                                                st.success(f"✅ P.IVA valida: {piva_norm_mr}")
                                            else:
                                                st.error(msg_mr)
                                    
                                    if st.form_submit_button("✅ Crea Ristorante", type="primary", use_container_width=True):
                                        if not new_nome or not new_piva_mr:
                                            st.error("❌ Nome e P.IVA obbligatori")
                                        else:
                                            piva_norm_mr = normalizza_piva(new_piva_mr)
                                            valida_mr, msg_mr = valida_formato_piva(piva_norm_mr)
                                            
                                            if not valida_mr:
                                                st.error(msg_mr)
                                            else:
                                                try:
                                                    # Verifica P.IVA non duplicata PER LO STESSO UTENTE
                                                    check_piva = supabase.table('ristoranti')\
                                                        .select('id')\
                                                        .eq('partita_iva', piva_norm_mr)\
                                                        .eq('user_id', user_sel['id'])\
                                                        .execute()
                                                    
                                                    if check_piva.data:
                                                        st.error(f"❌ P.IVA {piva_norm_mr} già registrata per questo cliente")
                                                    else:
                                                        # Inserisci nuovo ristorante
                                                        supabase.table('ristoranti').insert({
                                                            'user_id': user_sel['id'],
                                                            'nome_ristorante': new_nome,
                                                            'partita_iva': piva_norm_mr,
                                                            'ragione_sociale': new_ragione_mr if new_ragione_mr else None,
                                                            'attivo': True
                                                        }).execute()
                                                        
                                                        # 🔄 SYNC: Aggiorna users.nome_ristorante se è il primo ristorante
                                                        if num_ristoranti == 0:
                                                            supabase.table('users').update({
                                                                'nome_ristorante': new_nome,
                                                                'partita_iva': piva_norm_mr
                                                            }).eq('id', user_sel['id']).execute()
                                                            logger.info(f"🔄 Aggiornato users.nome_ristorante per {cliente_selezionato}")
                                                        
                                                        logger.info(f"✅ Sede creata: {new_nome} (P.IVA: {piva_norm_mr}) per {cliente_selezionato}")
                                                        st.success(f"✅ Sede **{new_nome}** creata!")
                                                        
                                                        # 🔄 Reset form: incrementa chiave per forzare pulizia campi
                                                        if 'form_ristorante_key' not in st.session_state:
                                                            st.session_state.form_ristorante_key = 0
                                                        st.session_state.form_ristorante_key += 1
                                                        
                                                        _carica_stats_clienti_admin.clear()
                                                        time.sleep(1)
                                                        st.rerun()
                                                except Exception as e:
                                                    st.error(f"❌ Errore creazione: {e}")
                                                    logger.exception(f"Errore creazione ristorante per {cliente_selezionato}")
                            
                            # AZIONE: Elimina Sede
                            if num_ristoranti > 0:
                                with st.expander("🗑️ Elimina Sede", expanded=False):
                                    st.warning("⚠️ Eliminazione permanente")
                                    
                                    rist_da_eliminare = st.selectbox(
                                        "Sede da eliminare",
                                        options=ristoranti_list,
                                        format_func=lambda r: f"{r['nome_ristorante']} (P.IVA: {r['partita_iva']})",
                                        key=f"select_elimina_rist_{user_sel['id']}"
                                    )
                                    
                                    if rist_da_eliminare:
                                        st.caption(f"⚠️ Verranno eliminate anche tutte le fatture associate")
                                        
                                        _confirm_elimina_sede = st.checkbox(
                                            f"⚠️ Confermo l'eliminazione permanente di "
                                            f"{rist_da_eliminare['nome_ristorante']} e tutte le sue fatture",
                                            key=f"confirm_elimina_sede_{rist_da_eliminare['id']}"
                                        )
                                        
                                        if st.button(f"🗑️ Elimina {rist_da_eliminare['nome_ristorante']}", 
                                                    type="secondary",
                                                    disabled=not _confirm_elimina_sede,
                                                    key=f"btn_elimina_{rist_da_eliminare['id']}"):
                                            try:
                                                # Elimina ristorante (cascade elimina anche fatture via FK)
                                                supabase.table('ristoranti')\
                                                    .delete()\
                                                    .eq('id', rist_da_eliminare['id'])\
                                                    .execute()
                                                
                                                # 🔄 SYNC: Aggiorna users.nome_ristorante con il prossimo ristorante attivo
                                                ristoranti_rimasti = supabase.table('ristoranti')\
                                                    .select('nome_ristorante, partita_iva')\
                                                    .eq('user_id', user_sel['id'])\
                                                    .eq('attivo', True)\
                                                    .limit(1)\
                                                    .execute()
                                                
                                                if ristoranti_rimasti.data:
                                                    # Aggiorna con il primo ristorante rimasto
                                                    nuovo_default = ristoranti_rimasti.data[0]
                                                    supabase.table('users').update({
                                                        'nome_ristorante': nuovo_default['nome_ristorante'],
                                                        'partita_iva': nuovo_default['partita_iva']
                                                    }).eq('id', user_sel['id']).execute()
                                                    logger.info(f"🔄 users.nome_ristorante aggiornato a: {nuovo_default['nome_ristorante']}")
                                                else:
                                                    # Nessun ristorante rimasto: imposta NULL
                                                    supabase.table('users').update({
                                                        'nome_ristorante': None,
                                                        'partita_iva': None
                                                    }).eq('id', user_sel['id']).execute()
                                                    logger.warning(f"⚠️ Nessun ristorante rimasto per {cliente_selezionato}, users.nome_ristorante = NULL")
                                                
                                                logger.warning(f"🗑️ Sede eliminata: {rist_da_eliminare['nome_ristorante']} di {cliente_selezionato}")
                                                st.success("✅ Sede eliminata!")
                                                _carica_stats_clienti_admin.clear()
                                                time.sleep(1)
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"❌ Errore eliminazione: {e}")
                                                logger.exception(f"Errore eliminazione ristorante {rist_da_eliminare['id']}")
            else:
                st.info("📭 Nessun cliente registrato")
        
        except Exception as e:
            st.error(f"❌ Errore gestione multi-ristorante: {e}")
            logger.exception("Errore sezione multi-ristorante")
    
    try:
        # 🚀 CACHED: Carica stats clienti (query pesanti cached 300s)
        stats_clienti, has_piva_column, has_pagine_column = _carica_stats_clienti_admin(tuple(ADMIN_EMAILS))

        if not has_piva_column:
            st.warning("⚠️ Esegui migrazione 009_add_piva_password.sql su Supabase per abilitare P.IVA")
        if not has_pagine_column:
            st.warning("⚠️ Esegui migrazione 038_add_pagine_abilitate.sql su Supabase per abilitare i flag pagine")

        if not stats_clienti:
            st.info("📭 Nessun cliente registrato (esclusi admin)")
        else:
            df_clienti = pd.DataFrame(stats_clienti)

            if df_clienti.empty:
                st.info("📭 Nessun dato cliente disponibile")
                st.stop()
            
            # ===== METRICHE GENERALI (CARD STILIZZATE) =====
            _n_clienti = int(df_clienti['user_id'].nunique())
            _n_attivi = int(df_clienti[df_clienti['attivo'] == True]['user_id'].nunique())
            _n_ristoranti = int(df_clienti[df_clienti['ristorante_id'].notna()]['ristorante_id'].nunique())
            _n_fatture = int(df_clienti['num_fatture'].sum())
            _n_righe = int(df_clienti['num_righe'].sum())
            _tot_costi = df_clienti['totale_costi'].sum()
            
            st.markdown(f"""
            <div class="admin-metrics-grid">
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
                    <div class="admin-metric-label" style="color:#1976d2;">👥 Clienti</div>
                    <div class="admin-metric-value" style="color:#1565c0;">{_n_clienti}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50;">
                    <div class="admin-metric-label" style="color:#2e7d32;">✅ Attivi</div>
                    <div class="admin-metric-value" style="color:#1b5e20;">{_n_attivi}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0;">
                    <div class="admin-metric-label" style="color:#7b1fa2;">🏢 Sedi</div>
                    <div class="admin-metric-value" style="color:#6a1b9a;">{_n_ristoranti}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
                    <div class="admin-metric-label" style="color:#e65100;">📄 Fatture</div>
                    <div class="admin-metric-value" style="color:#e65100;">{_n_fatture:,}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#e0f7fa,#b2ebf2); border:2px solid #00bcd4;">
                    <div class="admin-metric-label" style="color:#006064;">📊 Righe</div>
                    <div class="admin-metric-value" style="color:#00838f;">{_n_righe:,}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63;">
                    <div class="admin-metric-label" style="color:#c2185b;">💰 Costi</div>
                    <div class="admin-metric-value" style="color:#880e4f;">€{_tot_costi:,.0f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Ordina alfabeticamente per email
            df_clienti_sorted = df_clienti.sort_values('email', ascending=True)
            
            # ===== LISTA CLIENTI CON EXPANDER =====
            # --- BATCH pre-fetch pagine_abilitate (N+1 fix) ---
            _all_user_ids = df_clienti_sorted['user_id'].dropna().unique().tolist()
            try:
                _fresh_batch = supabase.table('users') \
                    .select('id, pagine_abilitate, trial_active, trial_activated_at') \
                    .in_('id', _all_user_ids) \
                    .execute()
                _fresh_pagine_map = {
                    r['id']: r.get('pagine_abilitate')
                    for r in (_fresh_batch.data or [])
                }
                _fresh_trial_map = {
                    r['id']: {
                        'trial_active': r.get('trial_active', False),
                        'trial_activated_at': r.get('trial_activated_at'),
                    }
                    for r in (_fresh_batch.data or [])
                }
            except Exception:
                _fresh_pagine_map = {}
                _fresh_trial_map = {}
            for idx, row in df_clienti_sorted.iterrows():
                row_key = f"{row['user_id']}_{row.get('ristorante_id', idx)}"
                status_icon = "🟢" if row['attivo'] else "🔴"
                
                # Calcola label attività
                _ultimo = row.get('ultimo_caricamento')
                if pd.notna(_ultimo):
                    _giorni = (pd.Timestamp.now(tz=timezone.utc) - _ultimo).days
                    if _giorni == 0:
                        _att_label = "🟢 Oggi"
                    elif _giorni < 7:
                        _att_label = f"🟢 {_giorni}g fa"
                    elif _giorni < 30:
                        _att_label = f"🟡 {_giorni}g fa"
                    else:
                        _att_label = f"🔴 {_giorni}g fa"
                else:
                    _att_label = "⚪ Mai"
                
                _exp_label = f"{status_icon} **{row['ristorante']}** — {row['email']}"
                
                with st.expander(_exp_label, expanded=False):
                    # Box blu con statistiche (stile app principale)
                    _costi_fmt = f"€{row.get('totale_costi', 0):,.2f}"
                    _piva_str = _html.escape(str(row.get('partita_iva', '') or '—'))
                    st.markdown(f"""
                    <div style="background-color:#E3F2FD; padding:12px 18px; border-radius:8px; border:2px solid #2196F3; margin-bottom:12px;">
                        <p style="color:#1565C0; font-size:0.95rem; font-weight:bold; margin:0; line-height:1.5;">
                            📄 Fatture: {row['num_fatture']}  &nbsp;|&nbsp;  📊 Righe: {row['num_righe']}  &nbsp;|&nbsp;  💰 {_costi_fmt}  &nbsp;|&nbsp;  🕐 {_att_label}  &nbsp;|&nbsp;  🏢 P.IVA: {_piva_str}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Riga bottoni
                    col_entra, col_menu, col_spacer = st.columns([1.5, 1.5, 5])
                    
                    with col_entra:
                        if st.button("👁️ Entra come cliente", key=f"impersona_{row_key}", type="primary", use_container_width=True):
                            st.session_state.admin_original_user = st.session_state.user_data.copy()
                            st.session_state.impersonating = True
                            st.session_state.impersonation_started_at = datetime.now(timezone.utc).isoformat()
                            
                            # Leggi pagine_abilitate dal batch pre-caricato (N+1 fix)
                            _fresh_pagine = _fresh_pagine_map.get(row['user_id'], row.get('pagine_abilitate'))
                            
                            cliente_data = {
                                'id': row['user_id'],
                                'email': row['email'],
                                'nome_ristorante': row['ristorante'],
                                'attivo': row['attivo'],
                                'partita_iva': row.get('partita_iva'),
                                'pagine_abilitate': _fresh_pagine,
                            }
                            st.session_state.user_data = cliente_data
                            
                            try:
                                ristoranti_cliente = supabase.table('ristoranti')\
                                    .select('id, nome_ristorante, partita_iva, ragione_sociale')\
                                    .eq('user_id', row['user_id'])\
                                    .eq('attivo', True)\
                                    .execute()
                                
                                if ristoranti_cliente.data and len(ristoranti_cliente.data) > 0:
                                    st.session_state.ristoranti = ristoranti_cliente.data
                                    rist_selezionato = None
                                    row_ristorante_id = row.get('ristorante_id')
                                    if row_ristorante_id:
                                        rist_selezionato = next((r for r in ristoranti_cliente.data if r.get('id') == row_ristorante_id), None)
                                    if rist_selezionato is None:
                                        rist_selezionato = ristoranti_cliente.data[0]

                                    st.session_state.ristorante_id = rist_selezionato['id']
                                    st.session_state.partita_iva = rist_selezionato['partita_iva']
                                    st.session_state.nome_ristorante = rist_selezionato['nome_ristorante']
                                    logger.info(f"🏢 Impersonazione: Caricato ristorante {rist_selezionato['nome_ristorante']} (ID: {rist_selezionato['id']})")
                                else:
                                    st.session_state.ristoranti = []
                                    st.session_state.ristorante_id = None
                                    st.session_state.partita_iva = row.get('partita_iva')
                                    st.session_state.nome_ristorante = row['ristorante']
                                    logger.warning(f"⚠️ Utente {row['email']} non ha ristoranti nella tabella ristoranti")
                            except Exception as e:
                                logger.error(f"Errore caricamento ristoranti durante impersonazione: {e}")
                                st.session_state.ristoranti = []
                                st.session_state.ristorante_id = None
                            
                            st.session_state.user_is_admin = False
                            st.session_state._set_impersonation_cookie = str(row['user_id'])
                            
                            logger.info(f"� IMPERSONATION START: admin={st.session_state.admin_original_user['email']} → client={row['email']}")
                            st.success(f"✅ Accesso come: {row['email']}")
                            time.sleep(0.8)
                            st.switch_page("app.py")
                    
                    with col_menu:
                        with st.popover("⚙️ Azioni", use_container_width=True):
                            st.markdown("**Azioni Cliente**")
                            
                            # AZIONE 1: Attiva/Disattiva
                            stato_attuale = row['attivo']
                            if stato_attuale:
                                if st.button("🔴 Disattiva Account", key=f"disattiva_{row_key}", type="secondary", use_container_width=True):
                                    try:
                                        supabase.table('users')\
                                            .update({'attivo': False})\
                                            .eq('id', row['user_id'])\
                                            .execute()
                                        
                                        logger.info(f"🔴 Account disattivato: {row['email']} | admin={user.get('email')}")
                                        st.success(f"Account {row['email']} disattivato")
                                        _carica_stats_clienti_admin.clear()
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore: {e}")
                            else:
                                if st.button("🟢 Attiva Account", key=f"attiva_{row_key}", type="primary", use_container_width=True):
                                    try:
                                        supabase.table('users')\
                                            .update({'attivo': True})\
                                            .eq('id', row['user_id'])\
                                            .execute()
                                        
                                        logger.info(f"🟢 Account attivato: {row['email']} | admin={user.get('email')}")
                                        st.success(f"Account {row['email']} attivato")
                                        _carica_stats_clienti_admin.clear()
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Errore: {e}")
                            
                            st.markdown("---")
                            
                            # AZIONE 2: Invia Email Reset Password (GDPR compliant)
                            st.markdown("**Reset Password**")
                            st.caption("Il cliente riceverà un'email per impostare la nuova password")
                            
                            if st.button("📧 Invia Email Reset", key=f"reset_{row_key}", type="primary", use_container_width=True):
                                try:
                                    import secrets as _admin_secrets
                                    
                                    reset_token = _admin_secrets.token_urlsafe(32)
                                    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                                    
                                    supabase.table('users')\
                                        .update({
                                            'reset_code': reset_token,
                                            'reset_expires': expires_at.isoformat()
                                        })\
                                        .eq('id', row['user_id'])\
                                        .execute()
                                    
                                    from services.email_service import invia_email
                                    
                                    base_url = st.secrets.get("app", {}).get("url", "https://envoicescan-ai.streamlit.app")
                                    reset_url = f"{base_url}/?reset_token={reset_token}"
                                    
                                    email_inviata = invia_email(
                                        destinatario=row['email'],
                                        oggetto="🔑 Reset Password - OH YEAH! Hub",
                                        corpo_html=f"""
                                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                            <h2 style="color: #2c5aa0;">🔑 Reset Password Richiesto</h2>
                                            <p>Ciao,</p>
                                            <p>L'amministratore ha richiesto un reset della tua password su <strong>OH YEAH! Hub</strong>.</p>
                                            <p>Clicca sul pulsante per impostare una nuova password:</p>
                                            <div style="text-align: center; margin: 30px 0;">
                                                <a href="{reset_url}" style="background-color:#0ea5e9;color:white;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">🔐 Imposta Nuova Password</a>
                                            </div>
                                            <p style="color: #dc2626;">⚠️ <strong>Importante:</strong> Questo link è valido per <strong>1 ora</strong>.</p>
                                            <p style="color: #888; font-size: 13px;">Se non hai richiesto questo reset, ignora questa email.</p>
                                            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                                            <p style="color: #666; font-size: 13px;">---<br><strong>OH YEAH! Hub Team</strong><br>📧 Support: mattiadavolio90@gmail.com</p>
                                        </div>
                                        """
                                    )
                                    
                                    if email_inviata:
                                        logger.info(f"📧 Email reset password inviata a: {row['email']} | admin={user.get('email')}")
                                        st.success(f"✅ Email inviata a {row['email']}")
                                    else:
                                        st.warning(f"⚠️ Token generato ma email non inviata. Link: {reset_url}")
                                    
                                    time.sleep(1.5)
                                    st.rerun()
                                except Exception as e:
                                    if '42703' in str(e) or 'does not exist' in str(e):
                                        st.error("⚠️ Esegui migrazione 001 per abilitare reset password via email")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore invio email reset: {e}")
                            
                            st.markdown("---")

                            # AZIONE 2a: Cambio Email Cliente (solo admin)
                            with st.expander("✉️ Cambia Email", expanded=False):
                                st.caption("Aggiorna l'email di login del cliente e invalida la sua sessione corrente")

                                with st.form(key=f"change_email_form_{row['user_id']}"):
                                    nuova_email_input = st.text_input(
                                        "Nuova email",
                                        value="",
                                        placeholder="cliente@dominio.it",
                                        key=f"new_email_input_{row['user_id']}"
                                    )
                                    submit_cambio_email = st.form_submit_button(
                                        "✅ Conferma Cambio Email",
                                        use_container_width=True,
                                        type="primary"
                                    )

                                if submit_cambio_email:
                                    old_email = (row.get('email') or '').strip()
                                    new_email = (nuova_email_input or '').strip().lower()

                                    if not _is_valid_email_format(new_email):
                                        st.error("⚠️ Inserisci un'email valida")
                                    elif new_email == old_email.strip().lower():
                                        st.error("⚠️ La nuova email deve essere diversa da quella attuale")
                                    else:
                                        try:
                                            if _email_exists_for_other_user(new_email, row['user_id']):
                                                st.error("⚠️ Questa email esiste gia' nel sistema")
                                            else:
                                                # Step 1: aggiorna SOLO email per lo user_id target.
                                                supabase.table('users')\
                                                    .update({'email': new_email})\
                                                    .eq('id', row['user_id'])\
                                                    .execute()

                                                # Step 2: invalida token sessione del cliente.
                                                supabase.table('users')\
                                                    .update({
                                                        'session_token': None,
                                                        'session_token_created_at': None
                                                    })\
                                                    .eq('id', row['user_id'])\
                                                    .execute()

                                                st.cache_data.clear()
                                                try:
                                                    _carica_stats_clienti_admin.clear()
                                                except Exception:
                                                    pass

                                                logger.info(
                                                    f"✉️ Cambio email cliente eseguito da admin: user_id={row['user_id']}, "
                                                    f"old_email={old_email}, new_email={new_email}, session_token_invalidato=True"
                                                )
                                                st.success(f"✅ Email aggiornata: {old_email} → {new_email}")
                                                time.sleep(1)
                                                st.rerun()
                                        except Exception as e:
                                            st.error(f"Errore cambio email: {e}")
                                            logger.exception(f"Errore cambio email cliente {row.get('user_id')}: {e}")

                            st.markdown("---")
                            
                            # AZIONE 2b: Gestione Pagine Abilitate
                            st.markdown("### Opzioni")
                            pagine = row.get('pagine_abilitate') or {'workspace': True}
                            
                            _ws_stato = "attivo" if pagine.get('workspace', True) else "disattivo"
                            new_workspace = st.checkbox(
                                f"Foodcost (attuale: {_ws_stato})",
                                value=pagine.get('workspace', True),
                                key=f"workspace_toggle_{row['user_id']}"
                            )
                            
                            if new_workspace != pagine.get('workspace', True):
                                try:
                                    new_pagine = _merge_and_save_pagina_abilitata(
                                        user_id=row['user_id'],
                                        page_key='workspace',
                                        enabled=new_workspace
                                    )
                                    
                                    # Verifica che il salvataggio sia andato a buon fine
                                    _verify = supabase.table('users').select('pagine_abilitate').eq('id', row['user_id']).execute()
                                    _verify_val = _verify.data[0].get('pagine_abilitate') if _verify.data else None
                                    
                                    logger.info(f"📄 Pagine aggiornate per {row['email']} (user_id={row['user_id']}): salvato={new_pagine}, verifica_db={_verify_val}")
                                    st.success(f"✅ Foodcost {'attivato' if new_workspace else 'disattivato'} per {row['email']}")
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    if 'pagine_abilitate' in str(e) or 'PGRST204' in str(e):
                                        st.error("⚠️ Esegui migrazione 038_add_pagine_abilitate.sql su Supabase per abilitare questa funzionalità")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore aggiornamento pagine_abilitate per {row.get('email')}")
                            
                            # Toggle Calcolo Margine
                            _cm_stato = "attivo" if pagine.get('calcolo_margine', True) else "disattivo"
                            new_calcolo_margine = st.checkbox(
                                f"Calcolo Margine (attuale: {_cm_stato})",
                                value=pagine.get('calcolo_margine', True),
                                key=f"calcolo_margine_toggle_{row['user_id']}"
                            )
                            
                            if new_calcolo_margine != pagine.get('calcolo_margine', True):
                                try:
                                    _merge_and_save_pagina_abilitata(
                                        user_id=row['user_id'],
                                        page_key='calcolo_margine',
                                        enabled=new_calcolo_margine
                                    )
                                    logger.info(f"📊 Calcolo Margine {'attivato' if new_calcolo_margine else 'disattivato'} per {row['email']}")
                                    st.success(f"✅ Calcolo Margine {'attivato' if new_calcolo_margine else 'disattivato'} per {row['email']}")
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    if 'pagine_abilitate' in str(e) or 'PGRST204' in str(e):
                                        st.error("⚠️ Esegui migrazione 038_add_pagine_abilitate.sql su Supabase per abilitare questa funzionalità")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore aggiornamento pagine_abilitate per {row.get('email')}")
                            
                            # Toggle Controllo Prezzi
                            _cp_stato = "attivo" if pagine.get('controllo_prezzi', True) else "disattivo"
                            new_controllo_prezzi = st.checkbox(
                                f"Controllo Prezzi (attuale: {_cp_stato})",
                                value=pagine.get('controllo_prezzi', True),
                                key=f"controllo_prezzi_toggle_{row['user_id']}"
                            )
                            
                            if new_controllo_prezzi != pagine.get('controllo_prezzi', True):
                                try:
                                    _merge_and_save_pagina_abilitata(
                                        user_id=row['user_id'],
                                        page_key='controllo_prezzi',
                                        enabled=new_controllo_prezzi
                                    )
                                    logger.info(f"💰 Controllo Prezzi {'attivato' if new_controllo_prezzi else 'disattivato'} per {row['email']}")
                                    st.success(f"✅ Controllo Prezzi {'attivato' if new_controllo_prezzi else 'disattivato'} per {row['email']}")
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    if 'pagine_abilitate' in str(e) or 'PGRST204' in str(e):
                                        st.error("⚠️ Esegui migrazione 038_add_pagine_abilitate.sql su Supabase per abilitare questa funzionalità")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore aggiornamento pagine_abilitate per {row.get('email')}")

                            # Toggle Analisi Personalizzata
                            _ap_stato = "attivo" if pagine.get('analisi_personalizzata', False) else "disattivo"
                            new_analisi_personalizzata = st.checkbox(
                                f"Analisi Personalizzata (attuale: {_ap_stato})",
                                value=pagine.get('analisi_personalizzata', False),
                                key=f"analisi_personalizzata_toggle_{row['user_id']}"
                            )

                            if new_analisi_personalizzata != pagine.get('analisi_personalizzata', False):
                                try:
                                    _merge_and_save_pagina_abilitata(
                                        user_id=row['user_id'],
                                        page_key='analisi_personalizzata',
                                        enabled=new_analisi_personalizzata
                                    )
                                    logger.info(
                                        f"🏷️ Analisi Personalizzata "
                                        f"{'attivata' if new_analisi_personalizzata else 'disattivata'} "
                                        f"per {row['email']}"
                                    )
                                    st.success(
                                        f"✅ Analisi Personalizzata "
                                        f"{'attivata' if new_analisi_personalizzata else 'disattivata'} "
                                        f"per {row['email']}"
                                    )
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    if 'pagine_abilitate' in str(e) or 'PGRST204' in str(e):
                                        st.error("⚠️ Esegui migrazione 038_add_pagine_abilitate.sql su Supabase per abilitare questa funzionalità")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore aggiornamento pagine_abilitate per {row.get('email')}")
                            
                            st.markdown("---")
                            
                            # AZIONE 2c: Blocco Fatture Anno Precedente
                            anno_corrente = datetime.now().year
                            
                            blocco_attivo = pagine.get('blocco_anno_precedente', True)
                            new_blocco = st.checkbox(
                                f"Blocca fatture precedenti all'anno in corso (attuale: {'attivo' if blocco_attivo else 'disattivo'} - riferimento: {anno_corrente})",
                                value=blocco_attivo,
                                key=f"blocco_anno_{row_key}"
                            )
                            
                            if new_blocco != blocco_attivo:
                                try:
                                    _merge_and_save_pagina_abilitata(
                                        user_id=row['user_id'],
                                        page_key='blocco_anno_precedente',
                                        enabled=new_blocco
                                    )
                                    
                                    stato = "ATTIVATO" if new_blocco else "DISATTIVATO"
                                    logger.info(f"📅 Blocco anno precedente {stato} per {row['email']}")
                                    st.success(f"✅ Blocco fatture anno precedente {stato.lower()}")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                                    logger.exception(f"Errore aggiornamento blocco_anno per {row.get('email')}")
                            
                            st.markdown("---")

                            # AZIONE 2c-bis: Blocco Fatture Mesi Precedenti (anno corrente)
                            mese_corrente_nome = datetime.now().strftime('%B').capitalize()
                            
                            blocco_mesi_attivo = pagine.get('blocco_mesi_precedenti', False)
                            new_blocco_mesi = st.checkbox(
                                f"Blocca fatture dei mesi precedenti (attuale: {'attivo' if blocco_mesi_attivo else 'disattivo'} - consente solo {mese_corrente_nome} {anno_corrente}; non si applica ai trial)",
                                value=blocco_mesi_attivo,
                                key=f"blocco_mesi_{row_key}"
                            )
                            
                            if new_blocco_mesi != blocco_mesi_attivo:
                                try:
                                    _merge_and_save_pagina_abilitata(
                                        user_id=row['user_id'],
                                        page_key='blocco_mesi_precedenti',
                                        enabled=new_blocco_mesi
                                    )
                                    
                                    stato_mesi = "ATTIVATO" if new_blocco_mesi else "DISATTIVATO"
                                    logger.info(f"📆 Blocco mesi precedenti {stato_mesi} per {row['email']}")
                                    st.success(f"✅ Blocco mesi precedenti {stato_mesi.lower()}")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                                    logger.exception(f"Errore aggiornamento blocco_mesi per {row.get('email')}")
                            
                            st.markdown("---")

                            # AZIONE 2d: Trial 7 Giorni Gratuiti
                            st.markdown("**🎟️ Prova Gratuita 7 Giorni**")
                            st.caption("Attiva accesso trial per mese corrente e precedente con export Excel abilitato")

                            _trial_data = _fresh_trial_map.get(row['user_id'], {})
                            _has_active_trial = _trial_data.get('trial_active', False)
                            _trial_act_raw = _trial_data.get('trial_activated_at')

                            if _has_active_trial and _trial_act_raw:
                                try:
                                    _trial_act_dt = datetime.fromisoformat(
                                        _trial_act_raw.replace('Z', '+00:00')
                                    )
                                    _trial_exp_dt = _trial_act_dt + timedelta(days=7)
                                    _trial_days_rem = max(
                                        0,
                                        (_trial_exp_dt - datetime.now(timezone.utc)).days
                                    )
                                    st.info(
                                        f"🎟️ Trial attiva — scade tra **{_trial_days_rem} giorni** "
                                        f"({_trial_exp_dt.strftime('%d/%m/%Y')})"
                                    )
                                except Exception:
                                    st.info("🎟️ Trial attiva")
                            else:
                                if st.button(
                                    "🎟️ Attiva Trial 7 Giorni",
                                    key=f"trial_{row_key}",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    from services.auth_service import attiva_trial as _at
                                    _ok, _msg = _at(
                                        row['user_id'],
                                        user.get('email', ''),
                                        supabase
                                    )
                                    if _ok:
                                        st.success(f"✅ {_msg}")
                                        logger.info(
                                            f"🎟️ Trial attivata da admin: "
                                            f"{user.get('email')} → {row['email']}"
                                        )
                                        _carica_stats_clienti_admin.clear()
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {_msg}")

                            st.markdown("---")

                            # AZIONE 3: Elimina Account Completo (2 click)
                            # FIX CRITICO: salviamo i dati del cliente in session_state
                            # perché @st.dialog esegue fragment-rerun e la closure su 'row'
                            # punterebbe all'ULTIMO client del loop, non a quello selezionato.
                            st.markdown("**⚠️ Zona Pericolosa**")
                            
                            if st.button("🗑️ Elimina Account", key=f"elimina_btn_{row_key}", type="secondary", use_container_width=True):
                                # Salva snapshot dei dati del cliente da eliminare
                                st.session_state['_delete_target'] = {
                                    'user_id': row['user_id'],
                                    'email': row['email'],
                                    'ristorante': row['ristorante'],
                                    'num_fatture': row['num_fatture'],
                                    'num_righe': row['num_righe'],
                                    'row_key': row_key,
                                }
                                st.session_state['_show_delete_dialog'] = True
                            
                            # Il dialog viene aperto FUORI dal loop (sotto)
    
    except Exception as e:
        st.error(f"❌ Errore caricamento clienti: {e}")
        logger.exception("Errore gestione clienti")
        st.code(traceback.format_exc())

    # ============================================================
    # DIALOG ELIMINAZIONE ACCOUNT (fuori dal loop per evitare bug closure)
    # I dati del cliente target sono salvati in session_state['_delete_target']
    # ============================================================
    if st.session_state.get('_show_delete_dialog', False) and st.session_state.get('_delete_target'):
        @st.dialog("⚠️ Conferma Eliminazione Account")
        def show_delete_confirmation():
            # Leggi i dati dal session_state (NON dalla closure del loop)
            target = st.session_state['_delete_target']
            target_user_id = target['user_id']
            target_email = target['email']
            target_ristorante = target['ristorante']
            target_num_fatture = target['num_fatture']
            target_num_righe = target['num_righe']
            target_row_key = target['row_key']

            admin_email = (st.session_state.user_data.get('email') or '').strip().lower()
            target_email_normalized = (target_email or '').strip().lower()
            if target_email_normalized == admin_email or target_email_normalized in ADMIN_EMAILS:
                st.error("🚫 **ERRORE**: Non puoi eliminare il tuo account admin o altri account admin!")
                st.info("Se vuoi rimuovere un amministratore, contatta il supporto tecnico.")
                if st.button("❌ Chiudi", use_container_width=True):
                    st.session_state['_show_delete_dialog'] = False
                    st.session_state.pop('_delete_target', None)
                    st.rerun()
                return

            st.warning(
                f"**Stai per eliminare definitivamente:**\n\n"
                f"👤 **{target_email}** ({target_ristorante})\n\n"
                f"📊 **Dati che verranno eliminati:**\n"
                f"- Account utente\n"
                f"- {target_num_fatture} fatture\n"
                f"- {target_num_righe} righe prodotto\n"
                f"- Log upload\n\n"
                f"✅ **Memoria globale preservata (default):**\n"
                f"- Categorizzazioni condivise\n"
                f"- Contributi alla memoria collettiva\n\n"
                f"⚠️ **Questa azione è IRREVERSIBILE**"
            )

            st.markdown("---")
            elimina_memoria = st.checkbox(
                "🗑️ Elimina anche contributi alla memoria globale",
                value=False,
                key=f"elimina_mem_{target_user_id}",
                help="Se attivo, rimuove le categorizzazioni di questo cliente dal database condiviso (prodotti_master)"
            )

            if elimina_memoria:
                st.warning("⚠️ Verranno eliminati anche i contributi alla memoria AI condivisa")

            st.markdown("---")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("❌ Annulla", use_container_width=True):
                    st.session_state['_show_delete_dialog'] = False
                    st.session_state.pop('_delete_target', None)
                    st.rerun()

            with col2:
                if st.button("🗑️ Sì, elimina definitivamente", type="primary", use_container_width=True):
                    try:
                        with st.spinner(f"Eliminazione {target_email}..."):
                            user_id_to_delete = target_user_id
                            email_deleted = target_email

                            if not user_id_to_delete:
                                raise ValueError("user_id_to_delete è vuoto!")

                            if (email_deleted or '').strip().lower() in ADMIN_EMAILS:
                                raise ValueError(f"Tentativo di eliminare admin: {email_deleted}")

                            deleted = {
                                'fatture': 0,
                                'prodotti': 0,
                                'upload_events': 0,
                                'memoria_globale': 0
                            }

                            try:
                                result_fatture = supabase.table('fatture')\
                                    .delete()\
                                    .eq('user_id', user_id_to_delete)\
                                    .execute()
                                deleted['fatture'] = len(result_fatture.data) if result_fatture.data else 0
                            except Exception as e:
                                logger.warning(f"Errore eliminazione fatture: {e}")

                            try:
                                result_prodotti = supabase.table('prodotti_utente')\
                                    .delete()\
                                    .eq('user_id', user_id_to_delete)\
                                    .execute()
                                deleted['prodotti'] = len(result_prodotti.data) if result_prodotti.data else 0
                            except Exception as e:
                                logger.warning(f"Errore eliminazione prodotti: {e}")

                            try:
                                result_events = supabase.table('upload_events')\
                                    .delete()\
                                    .eq('user_id', user_id_to_delete)\
                                    .execute()
                                deleted['upload_events'] = len(result_events.data) if result_events.data else 0
                            except Exception as e:
                                logger.warning(f"Errore eliminazione upload_events: {e}")

                            tables_extra = [
                                ('classificazioni_manuali', 'user_id'),
                                ('ricette', 'userid'),
                                ('ingredienti_workspace', 'userid'),
                                ('note_diario', 'userid'),
                                ('ristoranti', 'user_id'),
                            ]
                            for table_name, id_col in tables_extra:
                                try:
                                    supabase.table(table_name).delete().eq(id_col, user_id_to_delete).execute()
                                    logger.info(f"🗑️ Pulita tabella {table_name} per {email_deleted}")
                                except Exception as e:
                                    logger.warning(f"Errore pulizia {table_name}: {e}")

                            if elimina_memoria:
                                try:
                                    result_master = supabase.table('prodotti_master')\
                                        .delete()\
                                        .eq('user_id', user_id_to_delete)\
                                        .execute()
                                    deleted['memoria_globale'] = len(result_master.data) if result_master.data else 0
                                    logger.info(f"🗑️ Memoria globale eliminata: {deleted['memoria_globale']} record")
                                except Exception as e:
                                    logger.warning(f"Errore eliminazione memoria globale: {e}")

                            logger.warning(f"🗑️ Eliminazione utente: {email_deleted} (ID: {user_id_to_delete})")

                            result_user = supabase.table('users')\
                                .delete()\
                                .eq('id', user_id_to_delete)\
                                .execute()

                            if not result_user.data:
                                logger.error(f"⚠️ Eliminazione utente fallita per ID: {user_id_to_delete}")

                            try:
                                invalida_cache_memoria()
                            except Exception as e:
                                logger.warning(f"Errore invalidazione cache: {e}")

                            memoria_status = f"ELIMINATA ({deleted['memoria_globale']} record)" if elimina_memoria else "PRESERVATA"
                            logger.warning(
                                f"🗑️ ELIMINAZIONE ACCOUNT | "
                                f"Admin: {st.session_state.user_data['email']} | "
                                f"Cliente: {email_deleted} | "
                                f"Fatture: {deleted['fatture']} | "
                                f"Prodotti locali: {deleted['prodotti']} | "
                                f"Events: {deleted['upload_events']} | "
                                f"Memoria globale: {memoria_status}"
                            )

                            st.success(f"✅ Account {email_deleted} eliminato")

                            info_msg = (
                                f"📊 **Dati eliminati:**\n"
                                f"- Fatture: {deleted['fatture']}\n"
                                f"- Prodotti locali: {deleted['prodotti']}\n"
                                f"- Upload Events: {deleted['upload_events']}\n\n"
                            )

                            if elimina_memoria:
                                info_msg += f"🗑️ Memoria globale: {deleted['memoria_globale']} contributi eliminati"
                            else:
                                info_msg += "✅ Memoria globale condivisa preservata"

                            st.info(info_msg)

                            st.session_state['_show_delete_dialog'] = False
                            st.session_state.pop('_delete_target', None)
                            _carica_stats_clienti_admin.clear()
                            time.sleep(2)
                            st.rerun()

                    except Exception as e:
                        st.error(f"❌ Errore eliminazione: {e}")
                        logger.exception(f"Errore critico eliminazione {target_email}")

        show_delete_confirmation()

# ============================================================
# TAB 2: REVIEW RIGHE €0 CON SISTEMA CONFERMA
# ============================================================

if tab2:
    st.markdown("## 📊 Review Righe Prezzo €0")
    st.caption("Verifica righe con prezzo €0 - potrebbero essere omaggi o diciture")

    @st.cache_data(ttl=60, show_spinner=False)
    def _carica_clienti_attivi_non_admin():
        try:
            resp = supabase.table('users')\
                .select('id, email, nome_ristorante')\
                .eq('attivo', True)\
                .order('nome_ristorante', desc=False)\
                .execute()
            data = resp.data if resp.data else []
            return [u for u in data if (u.get('email') or '').strip().lower() not in ADMIN_EMAILS]
        except Exception:
            return []
    
    # ============================================================
    # FILTRO PER CLIENTE
    # ============================================================
    st.markdown("### 👥 Seleziona Cliente")
    
    try:
        clienti = _carica_clienti_attivi_non_admin()
        
        # Opzione "Tutti" all'inizio
        opzioni_clienti = [{'id': 'TUTTI', 'email': 'Tutti i clienti', 'nome_ristorante': 'Tutti'}] + clienti
        
        cliente_selezionato = st.selectbox(
            "Visualizza problemi di",
            opzioni_clienti,
            format_func=lambda x: f"🌐 {x['nome_ristorante']}" if x['id'] == 'TUTTI' else f"👤 {x['nome_ristorante']} ({x['email']})",
            key="filtro_cliente_review"
        )
        
        filtro_cliente_id = None if cliente_selezionato['id'] == 'TUTTI' else cliente_selezionato['id']
        
    except Exception as e:
        st.error(f"Errore caricamento clienti: {e}")
        filtro_cliente_id = None
    
    st.markdown("---")
    
    # ============================================================
    # CARICAMENTO RIGHE €0 CON FILTRO CLIENTE
    # ============================================================
    @st.cache_data(ttl=60, show_spinner=False)
    def carica_righe_zero_con_filtro(cliente_id=None):
        """
        Carica righe da validare: €0 OPPURE needs_review=true.
        Query singola ottimizzata con OR.
        
        Args:
            cliente_id: UUID cliente o None per tutti
            
        Returns:
            DataFrame con righe da validare
        """
        try:
            # Query singola con OR per entrambe le condizioni
            all_data = []
            page_size = 1000
            offset = 0
            
            while True:
                query = supabase.table('fatture')\
                    .select('id, descrizione, categoria, fornitore, file_origine, data_documento, user_id, prezzo_unitario, needs_review, reviewed_at, reviewed_by')\
                    .or_('prezzo_unitario.eq.0,needs_review.eq.true')\
                    .is_('reviewed_at', 'null')\
                    .order('id', desc=False)\
                    .range(offset, offset + page_size - 1)
                
                # Applica filtro cliente se specificato
                if cliente_id:
                    query = query.eq('user_id', cliente_id)
                
                response = query.execute()
                
                if not response.data:
                    break
                    
                all_data.extend(response.data)
                
                if len(response.data) < page_size:
                    break
                    
                offset += page_size
            
            df = pd.DataFrame(all_data) if all_data else pd.DataFrame()
            
            # Pulisci descrizioni corrotte (encoding errato da fornitori CJK)
            if not df.empty and 'descrizione' in df.columns:
                df['descrizione'] = df['descrizione'].apply(
                    lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x
                )
            
            # Log statistiche
            if not df.empty:
                n_zero = len(df[df['prezzo_unitario'] == 0]) if 'prezzo_unitario' in df.columns else 0
                n_review = len(df[df['needs_review'] == True]) if 'needs_review' in df.columns else 0
                logger.info(f"🔍 Righe da validare: {n_zero} €0 | {n_review} needs_review | {len(df)} totali (dedup)")
            
            return df
            
        except Exception as e:
            logger.error(f"Errore caricamento righe review: {e}")
            return pd.DataFrame()

    def _build_review_update_query(payload: dict, descrizione_target: str, cliente_id_target: str = None):
        query = supabase.table('fatture').update(payload)\
            .eq('descrizione', descrizione_target)\
            .or_('prezzo_unitario.eq.0,needs_review.eq.true')
        if cliente_id_target:
            query = query.eq('user_id', cliente_id_target)
        return query

    def _build_review_batch_update(payload: dict, descrizioni: list, cliente_id_target: str = None):
        """Aggiorna N descrizioni in una singola query con .in_()"""
        query = supabase.table('fatture').update(payload)\
            .in_('descrizione', descrizioni)\
            .or_('prezzo_unitario.eq.0,needs_review.eq.true')
        if cliente_id_target:
            query = query.eq('user_id', cliente_id_target)
        return query
    
    df_zero = carica_righe_zero_con_filtro(filtro_cliente_id)
    
    if df_zero.empty:
        st.success("✅ Nessuna riga da revisionare!")
        st.stop()
    
    # ============================================================
    # 🤖 AUTO-REVIEW INTELLIGENTE (riduce lavoro admin ~70%)
    # ============================================================
    st.markdown("### 🤖 Auto-Review Intelligente")
    st.caption("Classifica automaticamente diciture sicure e sconti/omaggi riconoscibili")
    
    # Pre-calcola quante righe sarebbero auto-classificate
    _desc_uniche_zero = df_zero['descrizione'].unique()
    _auto_diciture = []
    _auto_sconti = []
    _ambigue = []
    for _d in _desc_uniche_zero:
        if is_dicitura_sicura(_d, 0, 1):
            _auto_diciture.append(_d)
        elif is_sconto_omaggio_sicuro(_d):
            _auto_sconti.append(_d)
        else:
            _ambigue.append(_d)
    
    _col_prev1, _col_prev2, _col_prev3 = st.columns(3)
    with _col_prev1:
        st.metric("📝 Diciture auto-rilevate", len(_auto_diciture))
    with _col_prev2:
        st.metric("🎁 Sconti/Omaggi auto-rilevati", len(_auto_sconti))
    with _col_prev3:
        st.metric("❓ Ambigue (da revisionare)", len(_ambigue))
    
    if len(_auto_diciture) > 0 or len(_auto_sconti) > 0:
        with st.expander("🔍 Anteprima auto-classificazione", expanded=False):
            if _auto_diciture:
                st.markdown("**📝 Diciture (saranno marcate NOTE E DICITURE):**")
                for _d in _auto_diciture[:15]:
                    st.caption(f"  • {_d[:80]}")
                if len(_auto_diciture) > 15:
                    st.caption(f"  ... e altre {len(_auto_diciture) - 15}")
            if _auto_sconti:
                st.markdown("**🎁 Sconti/Omaggi (categoria confermata):**")
                for _d in _auto_sconti[:15]:
                    _cat = df_zero[df_zero['descrizione'] == _d]['categoria'].iloc[0] if not df_zero[df_zero['descrizione'] == _d].empty else 'N/A'
                    st.caption(f"  • {_d[:80]} → {_cat}")
                if len(_auto_sconti) > 15:
                    st.caption(f"  ... e altri {len(_auto_sconti) - 15}")
        
        _confirm_auto_review = st.checkbox(
            "⚠️ Confermo l'esecuzione su tutti i clienti selezionati",
            key="confirm_auto_review"
        )
        
        if st.button("🤖 Esegui Auto-Review", type="primary", key="btn_auto_review", disabled=not _confirm_auto_review):
            with st.spinner("Auto-classificazione in corso..."):
                _auto_ok = 0
                _auto_err = 0
                _auto_mem_ok = 0
                
                # 1) Diciture sicure → NOTE E DICITURE + salva in memoria globale
                if _auto_diciture:
                    try:
                        result = _build_review_batch_update({
                            'categoria': '📝 NOTE E DICITURE',
                            'needs_review': False,
                            'reviewed_at': datetime.now(timezone.utc).isoformat(),
                            'reviewed_by': 'auto-review'
                        }, _auto_diciture, filtro_cliente_id).execute()
                        _auto_ok += len(result.data) if result.data else len(_auto_diciture)
                        
                        # Salva in memoria globale come diciture verificate
                        for _d in _auto_diciture:
                            try:
                                supabase.table('prodotti_master').upsert({
                                    'descrizione': _d,
                                    'categoria': '📝 NOTE E DICITURE',
                                    'confidence': 'altissima',
                                    'verified': True,
                                    'classificato_da': 'auto-review',
                                    'ultima_modifica': datetime.now(timezone.utc).isoformat()
                                }, on_conflict='descrizione').execute()
                                _auto_mem_ok += 1
                            except Exception as e:
                                _auto_err += 1
                                logger.error(f"Errore salvataggio dicitura {_d[:40]}: {e}")
                    except Exception as _e:
                        _auto_err += 1
                        logger.error(f"Errore auto-review diciture: {_e}")
                
                # 2) Sconti/omaggi → conferma categoria attuale + salva in memoria globale
                if _auto_sconti:
                    for _d in _auto_sconti:
                        try:
                            _cat_corrente = df_zero[df_zero['descrizione'] == _d]['categoria'].iloc[0]
                            # Se categoria è ancora "Da Classificare", skip (non sappiamo quale assegnare)
                            if not _cat_corrente or _cat_corrente == 'Da Classificare':
                                continue
                            
                            result = _build_review_update_query({
                                'needs_review': False,
                                'reviewed_at': datetime.now(timezone.utc).isoformat(),
                                'reviewed_by': 'auto-review'
                            }, _d, filtro_cliente_id).execute()
                            _auto_ok += len(result.data) if result.data else 1
                            
                            # Salva in memoria globale con categoria confermata
                            supabase.table('prodotti_master').upsert({
                                'descrizione': _d,
                                'categoria': _cat_corrente,
                                'confidence': 'alta',
                                'verified': True,
                                'classificato_da': 'auto-review',
                                'ultima_modifica': datetime.now(timezone.utc).isoformat()
                            }, on_conflict='descrizione').execute()
                            _auto_mem_ok += 1
                        except Exception as _e:
                            _auto_err += 1
                            logger.error(f"Errore auto-review sconto '{_d[:40]}': {_e}")
                
                invalida_cache_memoria()
                st.success(f"🤖 Auto-Review completata: {_auto_ok} righe classificate, {_auto_mem_ok} salvate in memoria globale")
                if _auto_err > 0:
                    st.warning(f"⚠️ {_auto_err} errori durante auto-review")
                time.sleep(1)
                st.rerun()
    else:
        st.info("✅ Nessuna riga auto-classificabile. Tutte le righe richiedono revisione manuale.")
    
    st.markdown("---")
    
    # ============================================================
    # STATISTICHE (CARD STILIZZATE)
    # ============================================================
    cat_sospette = df_zero[~df_zero['categoria'].isin(['NOTE E DICITURE', 'Da Classificare'])]
    _cliente_label = _html.escape(cliente_selezionato['nome_ristorante'][:20]) if filtro_cliente_id else "Tutti"
    
    st.markdown(f"""
    <div class="admin-metrics-grid">
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
            <div class="admin-metric-label" style="color:#e65100;">📋 Righe Totali €0</div>
            <div class="admin-metric-value" style="color:#e65100;">{len(df_zero)}</div>
        </div>
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50;">
            <div class="admin-metric-label" style="color:#2e7d32;">✅ Prodotti Classificati</div>
            <div class="admin-metric-value" style="color:#1b5e20;">{len(cat_sospette)}</div>
        </div>
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
            <div class="admin-metric-label" style="color:#1976d2;">👤 Cliente</div>
            <div class="admin-metric-value" style="color:#1565c0;">{_cliente_label}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ============================================================
    # FILTRO PER CATEGORIA
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_cat, col_forn = st.columns(2)
    
    with col_cat:
        cat_uniche = ['Tutte'] + sorted(df_zero['categoria'].unique().tolist())
        filtro_categoria = st.selectbox(
            "Filtra per categoria",
            cat_uniche,
            key="filtro_cat_zero"
        )
    
    with col_forn:
        forn_unici = ['Tutti'] + sorted(df_zero['fornitore'].dropna().unique().tolist())
        filtro_fornitore = st.selectbox(
            "Filtra per fornitore",
            forn_unici,
            key="filtro_forn_zero"
        )
    
    # Applica filtri
    df_display = df_zero.copy()
    
    # Traccia filtri precedenti per reset pagina
    filtri_correnti = f"{filtro_categoria}_{filtro_fornitore}"
    if 'filtri_review_prev' not in st.session_state:
        st.session_state.filtri_review_prev = filtri_correnti
    elif st.session_state.filtri_review_prev != filtri_correnti:
        # Filtri cambiati: reset pagina
        st.session_state.pagina_review = 0
        st.session_state.filtri_review_prev = filtri_correnti
    
    if filtro_categoria != 'Tutte':
        df_display = df_display[df_display['categoria'] == filtro_categoria]
    
    if filtro_fornitore != 'Tutti':
        df_display = df_display[df_display['fornitore'] == filtro_fornitore]
    
    # ============================================================
    # RAGGRUPPA PER DESCRIZIONE (una riga = tutte le occorrenze)
    # ============================================================
    df_grouped = df_display.groupby('descrizione', as_index=False).agg({
        'id': 'first',  # Prendi primo ID (per chiave bottone)
        'categoria': 'first',  # Prima categoria trovata
        'fornitore': 'first',  # Primo fornitore
        'file_origine': lambda x: ', '.join(set(x.dropna().astype(str)))[:30]  # File unici (max 30 char)
    })
    
    # Aggiungi colonna occorrenze
    df_grouped['occorrenze'] = df_display.groupby('descrizione').size().values
    
    # ORDINA ALFABETICAMENTE per descrizione
    df_grouped = df_grouped.sort_values('descrizione').reset_index(drop=True)
    
    # ============================================================
    # PAGINAZIONE PER PERFORMANCE (25 righe = più veloce)
    # ============================================================
    RIGHE_PER_PAGINA = 25
    totale_righe = len(df_grouped)
    
    # Inizializza pagina corrente
    if 'pagina_review' not in st.session_state:
        st.session_state.pagina_review = 0
    
    num_pagine = (totale_righe + RIGHE_PER_PAGINA - 1) // RIGHE_PER_PAGINA
    
    col_info, col_pag = st.columns([2, 1])
    
    with col_info:
        st.info(f"📋 Mostrando {totale_righe} descrizioni uniche ({len(df_display)} righe totali)")
    
    with col_pag:
        if num_pagine > 1:
            pagina = st.number_input(
                f"Pag. (max {num_pagine})",
                min_value=1,
                max_value=num_pagine,
                value=st.session_state.pagina_review + 1,
                step=1,
                key="input_pagina_review",
                label_visibility="visible"
            )
            st.session_state.pagina_review = pagina - 1
    
    if df_grouped.empty:
        st.info("Nessuna riga con questi filtri")
        st.stop()
    
    # Applica paginazione
    inizio = st.session_state.pagina_review * RIGHE_PER_PAGINA
    fine = min(inizio + RIGHE_PER_PAGINA, totale_righe)
    df_pagina = df_grouped.iloc[inizio:fine]
    
    if num_pagine > 1:
        st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")
    
    st.markdown("---")
    
    # ============================================================
    # TABELLA CON AZIONI INLINE (selectbox + 2 bottoni per riga)
    # ============================================================
    st.markdown("### 📝 Righe da Revisionare (raggruppate)")
    
    # Prepara lista categorie (usata per ogni riga)
    _categorie_fb = sorted(CATEGORIE_FOOD_BEVERAGE + CATEGORIE_MATERIALI)
    _categorie_spese = sorted(CATEGORIE_SPESE_OPERATIVE)
    _categorie_review = ["NOTE E DICITURE"] + _categorie_spese + _categorie_fb

    # Init session state per selezione massiva
    if 'review_zero_selezionate' not in st.session_state:
        st.session_state.review_zero_selezionate = set()
    if 'review_zero_cb_counter' not in st.session_state:
        st.session_state.review_zero_cb_counter = 0

    # Descrizioni della pagina corrente (per select/deselect all)
    _desc_pagina = set(df_pagina['descrizione'].tolist())

    # Pulsanti selezione rapida
    _num_sel = len(st.session_state.review_zero_selezionate & _desc_pagina)
    col_sel_all, col_desel_all, col_sel_info = st.columns([1.5, 1.5, 3])
    with col_sel_all:
        if st.button(f"☑️ Seleziona Tutte ({len(_desc_pagina)})", use_container_width=True, key="rv_select_all"):
            st.session_state.review_zero_selezionate.update(_desc_pagina)
            st.session_state.review_zero_cb_counter += 1
            st.rerun()
    with col_desel_all:
        if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="rv_deselect_all"):
            st.session_state.review_zero_selezionate.difference_update(_desc_pagina)
            st.session_state.review_zero_cb_counter += 1
            st.rerun()
    with col_sel_info:
        if _num_sel > 0:
            st.info(f"✅ {_num_sel} righe selezionate — usa le Azioni Massive in fondo")

    st.markdown("---")

    # HEADER
    col_sel_h, col_desc, col_occur, col_cat_h, col_forn, col_azioni = st.columns([0.4, 2.5, 0.6, 2.5, 1.5, 1.2])
    with col_sel_h:
        st.markdown("**☑**")
    with col_desc:
        st.markdown("**Descrizione**")
    with col_occur:
        st.markdown("**N°**")
    with col_cat_h:
        st.markdown("**Categoria**")
    with col_forn:
        st.markdown("**Fornitore**")
    with col_azioni:
        st.markdown("**Azioni**")
    
    st.markdown("---")
    
    for idx, row in df_pagina.iterrows():
        descrizione = row['descrizione']
        categoria_corrente = row['categoria']
        fornitore = row.get('fornitore', 'N/A')
        occorrenze = row['occorrenze']
        
        col_sel, col_desc, col_occur, col_cat, col_forn, col_azioni = st.columns([0.4, 2.5, 0.6, 2.5, 1.5, 1.2])

        # CHECKBOX SELEZIONE
        with col_sel:
            _cb_key = f"rv_cb_{idx}_{st.session_state.review_zero_cb_counter}"
            _checked = descrizione in st.session_state.review_zero_selezionate
            if st.checkbox("", value=_checked, key=_cb_key, label_visibility="collapsed"):
                st.session_state.review_zero_selezionate.add(descrizione)
            else:
                st.session_state.review_zero_selezionate.discard(descrizione)

        # DESCRIZIONE + Badge review + Badge tipo sospetto
        with col_desc:
            needs_review_flag = row.get('needs_review', False) if 'needs_review' in df_pagina.columns else False
            review_badge = "🔍 " if needs_review_flag else ""
            # Badge tipo sospetto auto-rilevato
            if is_dicitura_sicura(descrizione, 0, 1):
                tipo_badge = "🏷️"
                tipo_help = "Dicitura probabile"
            elif is_sconto_omaggio_sicuro(descrizione):
                tipo_badge = "🎁"
                tipo_help = "Sconto/Omaggio probabile"
            else:
                tipo_badge = "❓"
                tipo_help = "Ambiguo - revisione manuale"
            desc_short = descrizione[:80] + "..." if len(descrizione) > 80 else descrizione
            st.markdown(f"{tipo_badge} `{review_badge}{desc_short}`", help=f"{tipo_help} | Testo completo: {descrizione}")
        
        # OCCORRENZE
        with col_occur:
            st.markdown(f"`{occorrenze}×`")
        
        # SELECTBOX CATEGORIA INLINE
        with col_cat:
            # Pre-seleziona categoria corrente se presente nella lista
            _cat_norm = categoria_corrente.replace("📝 ", "") if categoria_corrente else "NOTE E DICITURE"
            _default_idx = 0
            for _i, _c in enumerate(_categorie_review):
                if _c == categoria_corrente or _c == _cat_norm:
                    _default_idx = _i
                    break
            nuova_categoria = st.selectbox(
                "",
                _categorie_review,
                index=_default_idx,
                key=f"cat_{idx}",
                label_visibility="collapsed"
            )
        
        # FORNITORE
        with col_forn:
            forn_short = fornitore[:15] if fornitore else "N/A"
            st.caption(forn_short)
        
        # AZIONI: ✅ Salva categoria selezionata | 📝 Dicitura (NOTE E DICITURE in 1 click)
        with col_azioni:
            col_a1, col_a2 = st.columns(2)
            
            with col_a1:
                if st.button("✅", key=f"save_{idx}", help="Salva categoria selezionata + memoria globale"):
                    try:
                        result = _build_review_update_query({
                            'categoria': nuova_categoria,
                            'needs_review': False,
                            'reviewed_at': datetime.now(timezone.utc).isoformat(),
                            'reviewed_by': 'admin'
                        }, descrizione, filtro_cliente_id).execute()
                        # 💾 Salva in memoria globale (verificato da admin)
                        supabase.table('prodotti_master').upsert({
                            'descrizione': descrizione,
                            'categoria': nuova_categoria,
                            'confidence': 'altissima',
                            'verified': True,
                            'classificato_da': 'review-admin',
                            'ultima_modifica': datetime.now(timezone.utc).isoformat()
                        }, on_conflict='descrizione').execute()
                        _n = len(result.data) if result.data else occorrenze
                        logger.info(f"✅ REVIEW singola: '{descrizione[:60]}' → {nuova_categoria} ({_n} righe, cliente={filtro_cliente_id or 'TUTTI'})")  
                        st.success(f"✅ {_n} righe → {nuova_categoria} (+ memoria globale)")
                        invalida_cache_memoria()
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore: {e}")
            
            with col_a2:
                if st.button("📝", key=f"nota_{idx}", help="Segna come Nota/Dicitura + memoria globale"):
                    try:
                        result = _build_review_update_query({
                            'categoria': '📝 NOTE E DICITURE',
                            'needs_review': False,
                            'reviewed_at': datetime.now(timezone.utc).isoformat(),
                            'reviewed_by': 'admin'
                        }, descrizione, filtro_cliente_id).execute()
                        # 💾 Salva in memoria globale come dicitura verificata
                        supabase.table('prodotti_master').upsert({
                            'descrizione': descrizione,
                            'categoria': '📝 NOTE E DICITURE',
                            'confidence': 'altissima',
                            'verified': True,
                            'classificato_da': 'review-admin',
                            'ultima_modifica': datetime.now(timezone.utc).isoformat()
                        }, on_conflict='descrizione').execute()
                        _n = len(result.data) if result.data else occorrenze
                        logger.info(f"📝 REVIEW singola: '{descrizione[:60]}' → NOTE E DICITURE ({_n} righe, cliente={filtro_cliente_id or 'TUTTI'})")
                        st.success(f"📝 {_n} righe → NOTE E DICITURE (+ memoria globale)")
                        invalida_cache_memoria()
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore: {e}")
        
        st.markdown("---")

    # ============================================================
    # AZIONI MASSIVE (mostrate solo se ci sono righe selezionate)
    # ============================================================
    _num_sel_fin = len(st.session_state.review_zero_selezionate)
    if _num_sel_fin > 0:
        st.markdown("---")
        st.markdown(f"### ⚡ Azioni Massive — {_num_sel_fin} righe selezionate")

        col_mass_btn1, col_mass_btn2, col_mass_cancel = st.columns([2, 2, 1])

        with col_mass_btn1:
            if st.button(f"✅ Conferma Categorie Correnti ({_num_sel_fin})", use_container_width=True, key="rv_mass_confirm", type="primary"):
                with st.spinner("Conferma categorie in corso..."):
                    try:
                        _descs = list(st.session_state.review_zero_selezionate)
                        _ok_count = 0
                        _mem_count = 0
                        _batch_master = []
                        # Per ogni descrizione selezionata, conferma la SUA categoria corrente
                        for _d in _descs:
                            # Recupera categoria corrente dal df
                            _cat_row = df_grouped[df_grouped['descrizione'] == _d]
                            _cat_corrente = _cat_row['categoria'].iloc[0] if not _cat_row.empty else None
                            if not _cat_corrente or _cat_corrente == 'Da Classificare':
                                continue
                            
                            # Aggiorna fatture: segna come reviewato
                            result = _build_review_update_query({
                                'needs_review': False,
                                'reviewed_at': datetime.now(timezone.utc).isoformat(),
                                'reviewed_by': 'admin'
                            }, _d, filtro_cliente_id).execute()
                            _ok_count += len(result.data) if result.data else 1
                            
                            # Accumula per batch upsert
                            _batch_master.append({
                                'descrizione': _d,
                                'categoria': _cat_corrente,
                                'confidence': 'altissima',
                                'verified': True,
                                'classificato_da': 'review-admin',
                                'ultima_modifica': datetime.now(timezone.utc).isoformat()
                            })
                        
                        if _batch_master:
                            try:
                                supabase.table('prodotti_master').upsert(
                                    _batch_master, on_conflict='descrizione'
                                ).execute()
                                _mem_count = len(_batch_master)
                            except Exception:
                                pass
                        
                        logger.info(f"✅ REVIEW batch conferma: {_ok_count} righe aggiornate, {_mem_count} in memoria globale, cliente={filtro_cliente_id or 'TUTTI'}, categorie={list(set(x['categoria'] for x in _batch_master))}")
                        st.success(f"✅ {_ok_count} righe confermate + {_mem_count} salvate in memoria globale")
                    except Exception as _e:
                        logger.error(f"❌ REVIEW batch conferma fallita: {_e}")
                        st.error(f"Errore batch: {_e}")
                st.session_state.review_zero_selezionate = set()
                st.session_state.review_zero_cb_counter += 1
                invalida_cache_memoria()
                time.sleep(0.8)
                st.rerun()

        with col_mass_btn2:
            if st.button(f"📝 Tutte Diciture ({_num_sel_fin})", use_container_width=True, key="rv_mass_nota"):
                with st.spinner("Salvataggio in corso..."):
                    try:
                        _descs = list(st.session_state.review_zero_selezionate)
                        result = _build_review_batch_update({
                            'categoria': '📝 NOTE E DICITURE',
                            'needs_review': False,
                            'reviewed_at': datetime.now(timezone.utc).isoformat(),
                            'reviewed_by': 'admin'
                        }, _descs, filtro_cliente_id).execute()
                        _ok = len(result.data) if result.data else len(_descs)
                        # 💾 Salva tutte in memoria globale come diciture (batch)
                        _batch_diciture = [
                            {
                                'descrizione': _d,
                                'categoria': '📝 NOTE E DICITURE',
                                'confidence': 'altissima',
                                'verified': True,
                                'classificato_da': 'review-admin',
                                'ultima_modifica': datetime.now(timezone.utc).isoformat()
                            }
                            for _d in _descs
                        ]
                        if _batch_diciture:
                            try:
                                supabase.table('prodotti_master').upsert(
                                    _batch_diciture, on_conflict='descrizione'
                                ).execute()
                            except Exception:
                                pass
                        logger.info(f"📝 REVIEW batch diciture: {_ok} righe → NOTE E DICITURE, cliente={filtro_cliente_id or 'TUTTI'}")
                        st.success(f"📝 {_ok} righe → NOTE E DICITURE (+ memoria globale)")
                    except Exception as _e:
                        logger.error(f"❌ REVIEW batch diciture fallita: {_e}")
                        st.error(f"Errore batch: {_e}")
                st.session_state.review_zero_selezionate = set()
                st.session_state.review_zero_cb_counter += 1
                invalida_cache_memoria()
                time.sleep(0.8)
                st.rerun()

        with col_mass_cancel:
            if st.button("❌ Annulla", use_container_width=True, key="rv_mass_cancel"):
                st.session_state.review_zero_selezionate = set()
                st.session_state.review_zero_cb_counter += 1
                st.rerun()

# ============================================================
# FOOTER
# ============================================================
# TAB 3: MEMORIA GLOBALE AI - TABELLA UNIFICATA
# ============================================================

def tab_memoria_globale_unificata():
    """
    TAB Memoria Globale - VERSIONE DEFINITIVA
    - Mostra TUTTE le righe filtrate (no limite)
    - Scroll nativo Streamlit
    - Checkbox master funzionante
    - Info semplice
    """
    st.markdown("## 🧠 Memoria Globale Prodotti")
    st.caption("Gestisci classificazioni condivise tra tutti i clienti")

    def _priority_badge(label, bg_color, text_color, border_color):
        return (
            f"<span style=\"display:inline-block;padding:0.15rem 0.55rem;border-radius:999px;"
            f"background:{bg_color};color:{text_color};border:1px solid {border_color};"
            f"font-size:0.78rem;font-weight:700;letter-spacing:0.01em;\">{label}</span>"
        )
    
    # Funzione helper per toggle massivo
    def toggle_all_rows(righe_ids, seleziona):
        """Seleziona o deseleziona tutte le righe della pagina"""
        if seleziona:
            st.session_state.righe_selezionate.update(righe_ids)
        else:
            st.session_state.righe_selezionate.difference_update(righe_ids)
    
    # ============================================================
    # IDENTIFICA RUOLO
    # ============================================================
    user = st.session_state.get('user_data', {})
    user_email = (user.get('email', '') or '').strip().lower()
    is_admin = user_email in ADMIN_EMAILS
    
    if not is_admin:
        st.info("👤 **MODALITÀ CLIENTE**: Personalizzazioni solo tue")
    
    # ============================================================
    # CARICAMENTO DATI
    # ============================================================
    @st.cache_data(ttl=60, show_spinner=False)
    def carica_memoria_globale():
        """
        Carica MEMORIA GLOBALE (prodotti_master) - disponibile per TUTTI.
        Questo tab mostra SEMPRE prodotti_master, non prodotti_utente.
        Usa paginazione per superare il limite Supabase di 1000 righe.
        """
        try:
            campo_verified_exists = False
            all_data = []
            page_size = 1000
            offset = 0
            
            while True:
                try:
                    response = supabase.table('prodotti_master')\
                        .select('id, descrizione, categoria, volte_visto, created_at, verified, classificato_da')\
                        .order('id', desc=False)\
                        .range(offset, offset + page_size - 1)\
                        .execute()
                    campo_verified_exists = True
                except Exception:
                    # Campo verified non esiste ancora, usa query senza
                    response = supabase.table('prodotti_master')\
                        .select('id, descrizione, categoria, volte_visto, created_at')\
                        .order('id', desc=False)\
                        .range(offset, offset + page_size - 1)\
                        .execute()
                
                if not response.data:
                    break
                    
                all_data.extend(response.data)
                
                if len(response.data) < page_size:
                    break  # Ultima pagina
                    
                offset += page_size
            
            logger.info(f"📊 Memoria Globale caricata: {len(all_data)} prodotti (paginazione superata)")
            
            df = pd.DataFrame(all_data)
            # Pulisci descrizioni corrotte (encoding errato da fatture CJK)
            if not df.empty and 'descrizione' in df.columns:
                df['descrizione'] = df['descrizione'].apply(
                    lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x
                )
            # Aggiungi colonna verified se non esiste (solo per UI, non nel DB)
            if 'verified' not in df.columns:
                df['verified'] = False  # Default: da verificare
            if 'classificato_da' not in df.columns:
                df['classificato_da'] = ''
            return df, campo_verified_exists
        except Exception as e:
            logger.error(f"Errore caricamento memoria globale: {e}")
            return pd.DataFrame(), False
    
    df_memoria, campo_verified_exists = carica_memoria_globale()
    df_sospette = _carica_globale_sospette_dataset() if is_admin and campo_verified_exists else pd.DataFrame()
    
    if df_memoria.empty:
        st.warning("📭 Memoria vuota. Inizia a caricare fatture per popolarla!")
        return
    
    # ⚠️ AVVISO MIGRATION NECESSARIA (solo admin)
    if is_admin and not campo_verified_exists:
        st.warning("""
        ⚠️ **Sistema Verifica Non Disponibile**: Il campo `verified` non esiste nel database.
        
        **Per abilitare la funzionalità di verifica prodotti:**
        1. Apri [Supabase Dashboard SQL Editor](https://supabase.com/dashboard)
        2. Copia ed esegui: `migrations/008_add_verified_to_prodotti_master.sql`
        3. Oppure esegui: `python run_migration_008.py`
        """)
    
    # ============================================================
    # METRICHE (CARD STILIZZATE)
    # ============================================================
    totale_prodotti = len(df_memoria)
    verificati = totale_prodotti
    non_verificati = 0
    if is_admin and campo_verified_exists:
        non_verificati = int((~df_memoria['verified']).sum())
        verificati = int((df_memoria['verified']).sum())
    elif 'verified' in df_memoria.columns:
        non_verificati = int((~df_memoria['verified']).sum())
        verificati = totale_prodotti - non_verificati

    badge_verificati = _priority_badge("VERIFICATI", "#e8f5e9", "#1b5e20", "#43a047")
    badge_review = _priority_badge("DA VERIFICARE", "#fff3e0", "#e65100", "#ff9800")
    badge_totale = _priority_badge("TOTALE", "#e3f2fd", "#1565c0", "#2196f3")

    st.markdown(
        (
            "<div style=\"display:flex;gap:0.5rem;flex-wrap:wrap;margin:0.35rem 0 0.85rem 0;\">"
            f"{badge_review}<span style=\"font-size:0.9rem;color:#555;\">Storico da ricontrollare con le regole nuove</span>"
            f"{badge_verificati}<span style=\"font-size:0.9rem;color:#555;\">Voci già confermate manualmente</span>"
            f"{badge_totale}<span style=\"font-size:0.9rem;color:#555;\">Panoramica completa memoria condivisa</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    
    st.markdown(f"""
    <div class="admin-metrics-grid">
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
            <div class="admin-metric-label" style="color:#1976d2;">🧠 Totali</div>
            <div class="admin-metric-value" style="color:#1565c0;">{totale_prodotti:,}</div>
        </div>
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50;">
            <div class="admin-metric-label" style="color:#2e7d32;">✅ Verificati</div>
            <div class="admin-metric-value" style="color:#1b5e20;">{verificati:,}</div>
        </div>
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
            <div class="admin-metric-label" style="color:#ef6c00;">⚠️ Da Verificare</div>
            <div class="admin-metric-value" style="color:#e65100;">{non_verificati:,}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if is_admin and campo_verified_exists:
        if non_verificati > 0:
            st.warning(
                f"Ci sono {non_verificati} righe da verificare. Considerale backlog storico: molte sono state classificate prima delle regole nuove, quindi conviene ricontrollarle prima di considerare pulita la memoria globale."
            )
        else:
            st.success("Tutte le righe globali risultano già verificate.")
    
    # ============================================================
    # AZIONI ADMIN
    # ============================================================
    if is_admin:
        st.markdown("---")
        st.markdown("### ⚠️ Azioni Amministratore")

        col_btn, col_spacer = st.columns([2, 8])
        with col_btn:
            if st.button("🔄 Invalida Cache", type="secondary", use_container_width=True):
                invalida_cache_memoria()
                st.success("✅ Cache invalidata (Streamlit + in-memory)!")
                st.rerun()
    
    st.markdown("---")
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    # Inizializza pagina corrente
    if 'pagina_memoria' not in st.session_state:
        st.session_state.pagina_memoria = 0

    col_search, col_cat, col_verified, col_pag = st.columns([3, 2, 2, 1.5])
    
    with col_search:
        # Inizializza session_state se non esiste
        if 'search_memoria' not in st.session_state:
            st.session_state.search_memoria = ""
        
        search_text = st.text_input(
            "🔍 Cerca descrizione",
            value=st.session_state.search_memoria,
            placeholder="es: POMODORO, OLIO, PASTA",
            key="search_memoria"
        )
    
    with col_cat:
        categorie = st.session_state.categorie_cached
        # Inizializza session_state se non esiste
        if 'filtro_cat' not in st.session_state:
            st.session_state.filtro_cat = "Tutte"
        
        filtro_cat = st.selectbox(
            "Filtra categoria",
            ["Tutte"] + categorie,
            key="filtro_cat"
        )
    
    with col_verified:
        # Filtro verified (SOLO per admin E se campo esiste)
        if is_admin and campo_verified_exists:
            if 'filtro_verified' not in st.session_state:
                st.session_state.filtro_verified = "Da Verificare"  # Default: mostra solo non verificate
            
            filtro_verified = st.selectbox(
                "Stato verifica",
                ["Da Verificare", "Sospette (regole attuali)", "Già Verificate", "Righe €0 Verificate", "Tutte"],
                key="filtro_verified"
            )
        else:
            filtro_verified = "Tutte"
    
    with col_pag:
        pag_placeholder = st.empty()
    
    # ============================================================
    # APPLICA FILTRI
    # ============================================================
    df_filtrato = df_memoria.copy()
    
    # Traccia filtri precedenti per reset pagina
    filtri_correnti = f"{search_text}_{filtro_cat}_{filtro_verified}"
    if 'filtri_memoria_prev' not in st.session_state:
        st.session_state.filtri_memoria_prev = filtri_correnti
    elif st.session_state.filtri_memoria_prev != filtri_correnti:
        # Filtri cambiati: reset pagina
        st.session_state.pagina_memoria = 0
        st.session_state.filtri_memoria_prev = filtri_correnti
    
    if search_text:
        # Ricerca SMART: cerca ogni parola individualmente
        # Es: "BUCCIA NERA CAMPRIANO CHIANTI DOCG 75 CL" → cerca "BUCCIA" AND "NERA" AND "CAMPRIANO" etc.
        # Ignora numeri (che vengono rimossi dalla normalizzazione)
        parole = [p for p in search_text.strip().split() if len(p) >= 2 and not re.match(r'^\d+$', p)]
        
        if parole:
            filtro_ricerca = pd.Series([True] * len(df_filtrato), index=df_filtrato.index)
            for parola in parole:
                filtro_ricerca = filtro_ricerca & df_filtrato['descrizione'].str.contains(parola, case=False, na=False, regex=False)
            df_filtrato = df_filtrato[filtro_ricerca]
        
        # Logging per debug ricerca
        logger.info(f"🔍 Ricerca Memoria Globale: '{search_text}' (parole: {parole}) → {len(df_filtrato)} risultati trovati")
        
        # Info visuale per l'admin
        if is_admin and len(df_filtrato) == 0:
            st.warning(f"""
            ⚠️ **Nessun risultato per:** `{search_text}`
            
            **Possibili cause:**
            1. L'articolo non è mai stato categorizzato automaticamente (rimasto "Da Classificare")
            2. La descrizione nel DB è normalizzata diversamente (controlla nel Debug Info sopra)
            3. L'articolo è solo in Memoria Clienti (tab "Memoria Clienti")
            
            💡 **Suggerimento:** Controlla il tab "Memoria Clienti" per vedere se l'articolo è lì con una categorizzazione manuale del cliente.
            """)
    
    if filtro_cat != "Tutte":
        cat_clean = estrai_nome_categoria(filtro_cat)
        df_filtrato = df_filtrato[df_filtrato['categoria'] == cat_clean]
    
    # FILTRO VERIFIED (solo admin e se campo esiste)
    if is_admin and campo_verified_exists and filtro_verified != "Tutte":
        if filtro_verified == "Da Verificare":
            df_filtrato = df_filtrato[df_filtrato['verified'] == False]
        elif filtro_verified == "Sospette (regole attuali)":
            if df_sospette.empty:
                df_filtrato = df_filtrato.iloc[0:0]
            else:
                df_filtrato = df_filtrato.merge(
                    df_sospette[['id', 'categoria_suggerita', 'motivo_sospetto']],
                    on='id',
                    how='inner'
                )
        elif filtro_verified == "Già Verificate":
            df_filtrato = df_filtrato[df_filtrato['verified'] == True]
        elif filtro_verified == "Righe €0 Verificate":
            if 'classificato_da' in df_filtrato.columns:
                df_filtrato = df_filtrato[
                    (df_filtrato['verified'] == True) &
                    (df_filtrato['classificato_da'] == 'review-admin')
                ]
            else:
                df_filtrato = df_filtrato.iloc[0:0]  # Nessun risultato se colonna mancante
    
    # Per il backlog da verificare conviene ordinare per impatto, non solo alfabeticamente.
    if is_admin and campo_verified_exists and filtro_verified in ("Da Verificare", "Sospette (regole attuali)"):
        df_filtrato = df_filtrato.sort_values(['volte_visto', 'descrizione'], ascending=[False, True]).reset_index(drop=True)
    else:
        df_filtrato = df_filtrato.sort_values('descrizione').reset_index(drop=True)
    
    # ============================================================
    # INFO SEMPLICE + PAGINAZIONE
    # ============================================================
    
    # Paginazione per performance (50 righe per pagina)
    RIGHE_PER_PAGINA = 50
    totale_righe = len(df_filtrato)
    
    num_pagine = (totale_righe + RIGHE_PER_PAGINA - 1) // RIGHE_PER_PAGINA

    with pag_placeholder.container():
        if num_pagine > 1:
            pagina = st.number_input(
                f"Pag. (max {num_pagine})",
                min_value=1,
                max_value=num_pagine,
                value=st.session_state.pagina_memoria + 1,
                step=1,
                key="input_pagina_memoria",
                label_visibility="visible"
            )
            st.session_state.pagina_memoria = pagina - 1
        else:
            st.caption("Pag. 1")
    
    if df_filtrato.empty:
        st.warning("⚠️ Nessun prodotto trovato con questi filtri")
        return
    
    # Applica paginazione
    inizio = st.session_state.pagina_memoria * RIGHE_PER_PAGINA
    fine = min(inizio + RIGHE_PER_PAGINA, totale_righe)
    df_pagina = df_filtrato.iloc[inizio:fine]
    
    # ============================================================
    # INIZIALIZZA MODIFICHE PENDENTI E SELEZIONE
    # ============================================================
    if 'modifiche_memoria' not in st.session_state:
        st.session_state.modifiche_memoria = {}
    
    # Inizializza selezione righe per verifica (SOLO per admin)
    if 'righe_selezionate' not in st.session_state:
        st.session_state.righe_selezionate = set()
    
    # Contatore refresh per forzare ricreazione checkbox dopo selezione massiva
    if 'checkbox_refresh_counter' not in st.session_state:
        st.session_state.checkbox_refresh_counter = 0
    
    # ============================================================
    # TABELLA - TUTTE LE RIGHE FILTRATE
    # ============================================================

    # HEADER TABELLA (con checkbox solo se admin, campo exists e filtro da verificare)
    mostra_checkbox = is_admin and campo_verified_exists and filtro_verified == "Da Verificare"
    
    if mostra_checkbox:
        # Selezione rapida + info righe
        col_sel_title, col_sel_info = st.columns([2, 3])
        with col_sel_title:
            st.markdown("#### Selezione Rapida")
        with col_sel_info:
            st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")

        st.markdown(
            f"{badge_review} <span style='color:#666;'>Qui stai guardando il backlog storico non ancora confermato</span>",
            unsafe_allow_html=True,
        )

        # Bottoni compatti, ravvicinati e allineati a sinistra
        col_actions_left, _spacer = st.columns([2.2, 5.8])
        with col_actions_left:
            col_sel_all, col_desel_all = st.columns([1, 1])

            with col_sel_all:
                righe_pagina_ids = set(df_pagina['id'].tolist())
                if st.button("☑️ Seleziona", use_container_width=False, key="btn_select_all"):
                    st.session_state.righe_selezionate.update(righe_pagina_ids)
                    st.session_state.checkbox_refresh_counter += 1  # Forza refresh checkbox
                    st.rerun()

            with col_desel_all:
                if st.button("⬜ Deseleziona", use_container_width=False, key="btn_deselect_all"):
                    st.session_state.righe_selezionate.difference_update(righe_pagina_ids)
                    st.session_state.checkbox_refresh_counter += 1  # Forza refresh checkbox
                    st.rerun()

        st.markdown("---")
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
    elif is_admin and campo_verified_exists and filtro_verified == "Sospette (regole attuali)":
        st.markdown(
            f"{badge_review} <span style='color:#666;'>Subset automatico: righe non verificate che oggi il motore classificherebbe diversamente</span>",
            unsafe_allow_html=True,
        )
        if not df_sospette.empty:
            st.warning(
                f"Sono state individuate {len(df_sospette)} righe sospette secondo le regole attuali. Questa vista serve per concentrare la review manuale dove la logica nuova segnala una divergenza reale."
            )

        st.markdown("---")
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
    else:
        st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
    
    with col_desc:
        st.markdown("**Descrizione**")
    
    with col_cat:
        st.markdown("**Categoria**")
    
    with col_azioni:
        st.markdown("**Azioni**")
    
    st.markdown("---")
    
    # CICLO SOLO SULLE RIGHE DELLA PAGINA CORRENTE (per performance)
    # Usa categorie da cache
    categorie = st.session_state.categorie_cached
    
    for idx, row in df_pagina.iterrows():
        row_id = row['id']
        descrizione = row['descrizione']
        categoria_corrente = row['categoria']
        volte_visto = row['volte_visto']
        verified = row.get('verified', True)
        
        # Prepara colonne (con o senza checkbox)
        if mostra_checkbox:
            col_check, col_desc, col_cat, col_azioni = st.columns([0.5, 3.5, 2.5, 1])
        else:
            col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
        
        # CHECKBOX (solo se admin e mostra righe da verificare)
        if mostra_checkbox:
            with col_check:
                is_checked = row_id in st.session_state.righe_selezionate
                # Key dinamica con refresh counter per forzare ricreazione dopo selezione massiva
                checked = st.checkbox(
                    "sel",
                    value=is_checked,
                    key=f"chk_{row_id}_r{st.session_state.checkbox_refresh_counter}",
                    label_visibility="collapsed"
                )
                # Aggiorna stato in tempo reale
                if checked:
                    st.session_state.righe_selezionate.add(row_id)
                else:
                    st.session_state.righe_selezionate.discard(row_id)
        
        # DESCRIZIONE
        with col_desc:
            desc_short = descrizione[:80] + "..." if len(descrizione) > 80 else descrizione
            # Emoji stato verifica
            if filtro_verified == "Sospette (regole attuali)":
                categoria_suggerita = row.get('categoria_suggerita', '')
                motivo_sospetto = row.get('motivo_sospetto', 'dizionario_attuale')
                st.markdown(
                    f"<div style='margin:0.15rem 0 0.4rem 0;padding:0.35rem 0.65rem;background:#fff8f1;border-left:4px solid #fb923c;border-radius:8px;font-size:0.82rem;font-weight:700;color:#9a3412;'>Sospetta: oggi il motore propone {categoria_suggerita} ({motivo_sospetto})</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"⚠️ `{desc_short}`", help=f"Testo completo: {descrizione}")
            elif not verified:
                st.markdown(
                    "<div style='margin:0.15rem 0 0.4rem 0;padding:0.35rem 0.65rem;background:#fff8f1;border-left:4px solid #fb923c;border-radius:8px;font-size:0.82rem;font-weight:700;color:#9a3412;'>Da verificare: voce storica da ricontrollare</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"⚠️ `{desc_short}`", help=f"Testo completo: {descrizione}")
            else:
                st.markdown(
                    "<div style='margin:0.15rem 0 0.4rem 0;padding:0.35rem 0.65rem;background:#f3fbf4;border-left:4px solid #4ade80;border-radius:8px;font-size:0.82rem;font-weight:700;color:#166534;'>Verificata: voce già confermata</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"✅ `{desc_short}`", help=f"Testo completo: {descrizione}")
        
        # DROPDOWN CATEGORIA (modifica inline)
        with col_cat:
            # Controlla se c'è una modifica pendente
            if descrizione in st.session_state.modifiche_memoria:
                cat_default = st.session_state.modifiche_memoria[descrizione]['nuova_categoria']
            else:
                cat_default = categoria_corrente
            
            # Estrai nome categoria SENZA emoji
            cat_pulita = estrai_nome_categoria(cat_default)
            index_default = categorie.index(cat_pulita) if cat_pulita in categorie else 0
            
            nuova_cat = st.selectbox(
                "cat",
                categorie,
                index=index_default,
                key=f"cat_{row_id}",
                label_visibility="collapsed"
            )
            
            # Traccia modifica se diversa
            cat_clean = estrai_nome_categoria(nuova_cat)
            if cat_clean != categoria_corrente:
                st.session_state.modifiche_memoria[descrizione] = {
                    'nuova_categoria': cat_clean,
                    'occorrenze': volte_visto,
                    'categoria_originale': categoria_corrente,
                    'row_id': row_id  # Serve per auto-verificare quando salvi
                }
            elif descrizione in st.session_state.modifiche_memoria:
                # Ripristinata categoria originale, rimuovi da pendenti
                del st.session_state.modifiche_memoria[descrizione]
        
        # AZIONI - Badge modifica o info volte visto
        with col_azioni:
            # Mostra badge se c'è modifica pendente, altrimenti volte visto
            if descrizione in st.session_state.modifiche_memoria:
                st.markdown("🔸 **Mod**")
            else:
                st.caption(f"{volte_visto}×")
        
        st.markdown("---")
    
    # ============================================================
    # BARRA AZIONI UNIFICATA (Verifiche + Modifiche)
    # ============================================================
    # Ricalcola num_selezionate DOPO il ciclo (quando le checkbox hanno aggiornato lo stato)
    num_selezionate = len(st.session_state.righe_selezionate)
    num_modifiche = len(st.session_state.modifiche_memoria)
    
    # ✅ PULSANTE UNICO: Gestisce entrambe le operazioni (verifiche checkbox + modifiche categorie)
    if is_admin and campo_verified_exists and (num_selezionate > 0 or num_modifiche > 0):
        st.markdown("---")
        st.markdown("### 💾 Salvataggio e Conferma")
        
        # Info riassuntiva
        info_parts = []
        if num_modifiche > 0:
            totale_righe_affected = sum(m['occorrenze'] for m in st.session_state.modifiche_memoria.values())
            info_parts.append(f"**{num_modifiche}** modifiche categorie → **{totale_righe_affected}** righe")
        if num_selezionate > 0:
            info_parts.append(f"**{num_selezionate}** verifiche checkbox")
        
        st.info(f"📊 Azioni pendenti: {' | '.join(info_parts)}")
        
        # Preview modifiche (se esistono)
        if num_modifiche > 0:
            with st.expander("🔍 Preview Modifiche Categorie", expanded=False):
                for desc, info in list(st.session_state.modifiche_memoria.items())[:10]:
                    desc_short = desc[:80] + "..." if len(desc) > 80 else desc
                    st.markdown(f"- `{desc_short}` ({info['occorrenze']}×): {info['categoria_originale']} → **{info['nuova_categoria']}**")
                if num_modifiche > 10:
                    st.caption(f"... e altre {num_modifiche - 10} modifiche")
        
        # Bottoni azione unificati
        col_save, col_cancel, col_export = st.columns([2, 1, 1.5])
        
        with col_save:
            # Label dinamica
            label_parts = []
            if num_modifiche > 0:
                label_parts.append(f"{num_modifiche} modifiche")
            if num_selezionate > 0:
                label_parts.append(f"{num_selezionate} verifiche")
            
            button_label = f"💾 Salva e Conferma ({' + '.join(label_parts)})"
            
            if st.button(button_label, type="primary", use_container_width=True, key="save_unified"):
                with st.spinner("💾 Salvataggio in corso..."):
                    success_messages = []
                    
                    try:
                        # STEP 1: Salva modifiche categorie (se esistono)
                        if num_modifiche > 0:
                            success_count = 0
                            total_rows = 0
                            
                            for descrizione, info in st.session_state.modifiche_memoria.items():
                                try:
                                    # Admin: aggiorna memoria globale + auto-verifica
                                    supabase.table('prodotti_master')\
                                        .update({
                                            'categoria': info['nuova_categoria'],
                                            'verified': True  # ✅ Auto-verifica: correzione manuale = già controllata
                                        })\
                                        .eq('descrizione', descrizione)\
                                        .execute()
                                    
                                    # 🛡️ PROTEZIONE PRIORITÀ: Aggiorna fatture SOLO per utenti 
                                    # che NON hanno personalizzazione locale (prodotti_utente)
                                    # Se un cliente ha override locale, le sue fatture NON vengono toccate
                                    try:
                                        # Trova user_id con override locale per questa descrizione
                                        override_resp = supabase.table('prodotti_utente')\
                                            .select('user_id')\
                                            .eq('descrizione', descrizione)\
                                            .execute()
                                        
                                        user_ids_con_override = set()
                                        if override_resp.data:
                                            user_ids_con_override = {row['user_id'] for row in override_resp.data}
                                        
                                        if user_ids_con_override:
                                            # Aggiorna fatture ESCLUDENDO utenti con override locale
                                            # PostgREST non supporta NOT IN direttamente, quindi usiamo approccio iterativo
                                            # Prima: aggiorna TUTTE le fatture con questa descrizione
                                            result = supabase.table('fatture')\
                                                .update({'categoria': info['nuova_categoria']})\
                                                .eq('descrizione', descrizione)\
                                                .execute()
                                            
                                            # Poi: RIPRISTINA le fatture degli utenti con override locale
                                            for uid in user_ids_con_override:
                                                cat_locale = supabase.table('prodotti_utente')\
                                                    .select('categoria')\
                                                    .eq('user_id', uid)\
                                                    .eq('descrizione', descrizione)\
                                                    .limit(1)\
                                                    .execute()
                                                if cat_locale.data:
                                                    supabase.table('fatture')\
                                                        .update({'categoria': cat_locale.data[0]['categoria']})\
                                                        .eq('descrizione', descrizione)\
                                                        .eq('user_id', uid)\
                                                        .execute()
                                            
                                            logger.info(f"🛡️ Protetti {len(user_ids_con_override)} utenti con override locale per '{descrizione[:40]}'")
                                        else:
                                            # Nessun override locale: aggiorna tutte le fatture normalmente
                                            result = supabase.table('fatture')\
                                                .update({'categoria': info['nuova_categoria']})\
                                                .eq('descrizione', descrizione)\
                                                .execute()
                                    except Exception as prot_err:
                                        logger.warning(f"⚠️ Errore protezione override, fallback update globale: {prot_err}")
                                        result = supabase.table('fatture')\
                                            .update({'categoria': info['nuova_categoria']})\
                                            .eq('descrizione', descrizione)\
                                            .execute()
                                    
                                    num_updated = len(result.data) if result.data else info['occorrenze']
                                    success_count += 1
                                    total_rows += num_updated
                                    
                                except Exception as e:
                                    logger.error(f"Errore salvataggio '{descrizione}': {e}")
                            
                            logger.info(f"✅ MEMORIA GLOBALE: {success_count} categorie modificate, {total_rows} righe fatture aggiornate")
                            success_messages.append(f"✅ {success_count} modifiche salvate ({total_rows} righe aggiornate)")
                            
                            # Reset modifiche
                            st.session_state.modifiche_memoria = {}
                        
                        # STEP 2: Conferma verifiche checkbox (se esistono)
                        if num_selezionate > 0:
                            righe_ids = list(st.session_state.righe_selezionate)
                            
                            supabase.table('prodotti_master')\
                                .update({'verified': True})\
                                .in_('id', righe_ids)\
                                .execute()
                            
                            logger.info(f"✅ MEMORIA GLOBALE: {num_selezionate} prodotti verificati (checkbox)")
                            success_messages.append(f"✅ {num_selezionate} verifiche confermate")
                            
                            # Reset selezione
                            st.session_state.righe_selezionate = set()
                        
                        # Refresh cache (Streamlit + in-memory)
                        invalida_cache_memoria()
                        
                        # Mostra success unificato
                        st.success("\n\n".join(success_messages))
                        time.sleep(1.5)
                        st.rerun()
                        
                    except Exception as e:
                        logger.error(f"Errore salvataggio unificato: {e}")
                        st.error(f"❌ Errore durante il salvataggio: {e}")
        
        with col_cancel:
            if st.button("❌ Annulla Tutte", use_container_width=True, key="cancel_unified"):
                st.session_state.modifiche_memoria = {}
                st.session_state.righe_selezionate = set()
                st.rerun()
        
        with col_export:
            # Export solo se ci sono modifiche
            if num_modifiche > 0:
                export_data = []
                for desc, info in st.session_state.modifiche_memoria.items():
                    export_data.append({
                        'Descrizione': desc,
                        'Occorrenze': info['occorrenze'],
                        'Categoria Originale': info['categoria_originale'],
                        'Nuova Categoria': info['nuova_categoria']
                    })
                df_export = pd.DataFrame(export_data)
                csv = df_export.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="📄 Export CSV",
                    data=csv,
                    file_name=f"modifiche_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="export_unified_csv"
                )

# ============================================================
# VISTA MEMORIA CLIENTI (prodotti_utente)
# ============================================================

def tab_personalizzazioni_clienti():
    """
    TAB Memoria Clienti - VERSIONE UNIFICATA
    Replica del tab Memoria Globale ma con dati da prodotti_utente
    - Interfaccia semplice (Descrizione + Categoria)
    - Checkbox per selezione multipla
    - Bottoni "Applica Globalmente" e "Elimina Selezionati"
    """
    st.markdown("## 📝 Memoria Clienti")
    st.caption("Gestisci le modifiche manuali che ogni cliente ha fatto alle categorie")
    
    st.info("""
    🔧 **Gestione Memoria Clienti**: 
    
    ℹ️ **Comportamento:**
    - Queste personalizzazioni sono **locali** (solo per il cliente specifico)
    - Hanno **priorità** sulla memoria globale per quel cliente
    - Puoi **promuoverle** a memoria globale per condividerle con tutti 
    - Puoi **eliminarle** per far usare la memoria globale al cliente
    """)
    
    # ============================================================
    # CARICAMENTO DATI
    # ============================================================
    @st.cache_data(ttl=60, show_spinner=False)
    def carica_personalizzazioni_completa():
        """Carica TUTTE le personalizzazioni con paginazione (supera limite 1000 Supabase)."""
        try:
            all_data = []
            page_size = 1000
            offset = 0
            
            while True:
                response = supabase.table('prodotti_utente')\
                    .select('id, descrizione, categoria, volte_visto, created_at, user_id')\
                    .order('id', desc=False)\
                    .range(offset, offset + page_size - 1)\
                    .execute()
                
                if not response.data:
                    break
                    
                all_data.extend(response.data)
                
                if len(response.data) < page_size:
                    break
                    
                offset += page_size
            
            logger.info(f"📊 Memoria Clienti caricata: {len(all_data)} personalizzazioni")
            df = pd.DataFrame(all_data)
            # Pulisci descrizioni corrotte (encoding errato da fatture CJK)
            if not df.empty and 'descrizione' in df.columns:
                df['descrizione'] = df['descrizione'].apply(
                    lambda x: pulisci_caratteri_corrotti(x) if isinstance(x, str) else x
                )
            return df
        except Exception as e:
            logger.error(f"Errore caricamento personalizzazioni: {e}")
            return pd.DataFrame()
    
    df_personalizzazioni = carica_personalizzazioni_completa()
    
    if df_personalizzazioni.empty:
        st.warning("📭 Nessuna personalizzazione trovata. I clienti non hanno ancora modificato categorie manualmente.")
        return
    
    # ============================================================
    # METRICHE (CARD STILIZZATE)
    # ============================================================
    _tot_utilizzi_clienti = int(df_personalizzazioni['volte_visto'].sum())
    _clienti_unici = int(df_personalizzazioni['user_id'].nunique())
    
    st.markdown(f"""
    <div class="admin-metrics-grid">
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
            <div class="admin-metric-label" style="color:#1976d2;">📝 Voci in Memoria</div>
            <div class="admin-metric-value" style="color:#1565c0;">{len(df_personalizzazioni):,}</div>
        </div>
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50;">
            <div class="admin-metric-label" style="color:#2e7d32;">📊 Totale Utilizzi</div>
            <div class="admin-metric-value" style="color:#1b5e20;">{_tot_utilizzi_clienti:,}</div>
        </div>
        <div class="admin-metric-card" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
            <div class="admin-metric-label" style="color:#e65100;">👥 Clienti Attivi</div>
            <div class="admin-metric-value" style="color:#e65100;">{_clienti_unici}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_search, col_cat, col_reset = st.columns([3, 2, 1])
    
    with col_search:
        if 'search_personalizzazioni' not in st.session_state:
            st.session_state.search_personalizzazioni = ""
        
        search_text = st.text_input(
            "🔍 Cerca descrizione",
            value=st.session_state.search_personalizzazioni,
            placeholder="es: POMODORO, OLIO, PASTA",
            key="search_personalizzazioni"
        )
    
    with col_cat:
        categorie = st.session_state.categorie_cached
        if 'filtro_cat_pers' not in st.session_state:
            st.session_state.filtro_cat_pers = "Tutte"
        
        filtro_cat = st.selectbox(
            "Filtra categoria",
            ["Tutte"] + categorie,
            key="filtro_cat_pers"
        )
    
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset", key="reset_filtri_pers"):
            st.session_state.search_personalizzazioni = ""
            st.session_state.filtro_cat_pers = "Tutte"
            st.session_state.filtro_cliente_pers = "Tutti"
            st.rerun()
    
    # Filtro per cliente (mappa user_id → email)
    user_id_to_email = {}
    try:
        resp_utenti = supabase.table('users').select('id, email').execute()
        user_id_to_email = {u['id']: u['email'] for u in (resp_utenti.data or [])}
    except Exception:
        pass
    
    df_personalizzazioni['email_cliente'] = df_personalizzazioni['user_id'].map(user_id_to_email).fillna('Sconosciuto')
    
    emails_disponibili = sorted(df_personalizzazioni['email_cliente'].unique().tolist())
    if 'filtro_cliente_pers' not in st.session_state:
        st.session_state.filtro_cliente_pers = "Tutti"
    
    filtro_cliente = st.selectbox(
        "👤 Filtra per cliente",
        ["Tutti"] + emails_disponibili,
        key="filtro_cliente_pers"
    )
    
    # ============================================================
    # APPLICA FILTRI
    # ============================================================
    df_filtrato = df_personalizzazioni.copy()
    
    # Traccia filtri precedenti per reset pagina
    filtri_correnti = f"{search_text}_{filtro_cat}_{filtro_cliente}"
    if 'filtri_pers_prev' not in st.session_state:
        st.session_state.filtri_pers_prev = filtri_correnti
    elif st.session_state.filtri_pers_prev != filtri_correnti:
        st.session_state.pagina_pers = 0
        st.session_state.filtri_pers_prev = filtri_correnti
    
    if search_text:
        # Ricerca SMART: parola per parola, ignora numeri (normalizzazione li rimuove dal DB)
        parole = [p for p in search_text.strip().split() if len(p) >= 2 and not re.match(r'^\d+$', p)]
        
        if parole:
            filtro_ricerca = pd.Series([True] * len(df_filtrato), index=df_filtrato.index)
            for parola in parole:
                filtro_ricerca = filtro_ricerca & df_filtrato['descrizione'].str.contains(parola, case=False, na=False, regex=False)
            df_filtrato = df_filtrato[filtro_ricerca]
    
    if filtro_cat != "Tutte":
        cat_clean = estrai_nome_categoria(filtro_cat)
        df_filtrato = df_filtrato[df_filtrato['categoria'] == cat_clean]
    
    if filtro_cliente != "Tutti":
        df_filtrato = df_filtrato[df_filtrato['email_cliente'] == filtro_cliente]
    
    # ORDINA ALFABETICAMENTE per descrizione
    df_filtrato = df_filtrato.sort_values('descrizione').reset_index(drop=True)
    
    # ============================================================
    # INFO + PAGINAZIONE
    # ============================================================
    RIGHE_PER_PAGINA = 25
    totale_righe = len(df_filtrato)
    
    if 'pagina_pers' not in st.session_state:
        st.session_state.pagina_pers = 0
    
    num_pagine = (totale_righe + RIGHE_PER_PAGINA - 1) // RIGHE_PER_PAGINA
    
    col_info, col_pag = st.columns([2, 1])
    
    with col_info:
        st.info(f"📊 Mostrando {totale_righe} voci")
    
    with col_pag:
        if num_pagine > 1:
            pagina = st.number_input(
                f"Pag. (max {num_pagine})",
                min_value=1,
                max_value=num_pagine,
                value=st.session_state.pagina_pers + 1,
                step=1,
                key="input_pagina_pers",
                label_visibility="visible"
            )
            st.session_state.pagina_pers = pagina - 1
    
    if df_filtrato.empty:
        st.warning("⚠️ Nessuna memoria trovata con questi filtri")
        return
    
    # Applica paginazione
    inizio = st.session_state.pagina_pers * RIGHE_PER_PAGINA
    fine = min(inizio + RIGHE_PER_PAGINA, totale_righe)
    df_pagina = df_filtrato.iloc[inizio:fine]
    
    if num_pagine > 1:
        st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")
    
    # ============================================================
    # INIZIALIZZA SELEZIONE
    # ============================================================
    if 'righe_pers_selezionate' not in st.session_state:
        st.session_state.righe_pers_selezionate = set()
    
    if 'checkbox_pers_refresh_counter' not in st.session_state:
        st.session_state.checkbox_pers_refresh_counter = 0
    
    st.markdown("---")
    
    # ============================================================
    # TABELLA
    # ============================================================
    st.markdown("### 📋 Memoria Clienti")
    
    # Bottoni selezione massiva
    st.markdown("#### Selezione Rapida")
    col_sel_all, col_desel_all = st.columns(2)
    
    with col_sel_all:
        righe_pagina_ids = set(df_pagina['id'].tolist())
        if st.button(f"☑️ Seleziona Tutte ({len(righe_pagina_ids)} righe)", use_container_width=True, key="btn_select_all_pers"):
            st.session_state.righe_pers_selezionate.update(righe_pagina_ids)
            st.session_state.checkbox_pers_refresh_counter += 1
            st.rerun()
    
    with col_desel_all:
        if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_deselect_all_pers"):
            st.session_state.righe_pers_selezionate.difference_update(righe_pagina_ids)
            st.session_state.checkbox_pers_refresh_counter += 1
            st.rerun()
    
    st.markdown("---")
    
    # HEADER TABELLA
    col_check, col_desc, col_cat, col_save = st.columns([0.5, 3.5, 2.2, 1.1])
    
    with col_desc:
        st.markdown("**Descrizione**")
    
    with col_cat:
        st.markdown("**Categoria**")

    with col_save:
        st.markdown("**Salva**")
    
    st.markdown("---")
    
    # CICLO RIGHE
    for idx, row in df_pagina.iterrows():
        row_id = row['id']
        descrizione = row['descrizione']
        categoria_corrente = row['categoria']
        volte_visto = row['volte_visto']
        
        user_id = row['user_id']
        email_cliente = row.get('email_cliente', 'Sconosciuto')

        col_check, col_desc, col_cat, col_save = st.columns([0.5, 3.5, 2.2, 1.1])
        
        # CHECKBOX
        with col_check:
            is_checked = row_id in st.session_state.righe_pers_selezionate
            checked = st.checkbox(
                "sel",
                value=is_checked,
                key=f"chk_pers_{row_id}_r{st.session_state.checkbox_pers_refresh_counter}",
                label_visibility="collapsed"
            )
            if checked:
                st.session_state.righe_pers_selezionate.add(row_id)
            else:
                st.session_state.righe_pers_selezionate.discard(row_id)
        
        # DESCRIZIONE
        with col_desc:
            desc_short = descrizione[:60] + "..." if len(descrizione) > 60 else descrizione
            st.markdown(f"`{desc_short}` ({volte_visto}×)")
            st.caption(email_cliente)
        
        # CATEGORIA con editing inline
        with col_cat:
            cat_pulita = estrai_nome_categoria(categoria_corrente)
            index_default = categorie.index(cat_pulita) if cat_pulita in categorie else 0
            nuova_cat = st.selectbox(
                "Categoria cliente",
                categorie,
                index=index_default,
                key=f"cat_pers_{row_id}",
                label_visibility="collapsed"
            )

        with col_save:
            if st.button("💾", key=f"save_pers_{row_id}", use_container_width=True, help="Salva categoria locale"):
                try:
                    nuova_cat_clean = estrai_nome_categoria(nuova_cat)
                    _aggiorna_categoria_locale(
                        local_id=row_id,
                        descrizione=descrizione,
                        user_id=user_id,
                        nuova_categoria=nuova_cat_clean,
                    )
                    invalida_cache_memoria()
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore salvataggio categoria: {e}")
        
        st.markdown("---")
    
    # ============================================================
    # BARRA AZIONI
    # ============================================================
    num_selezionate = len(st.session_state.righe_pers_selezionate)
    
    if num_selezionate > 0:
        st.markdown("---")
        st.markdown("### 💾 Azioni su Selezionati")
        
        st.info(f"📊 {num_selezionate} voci selezionate")
        
        col_global, col_delete, col_cancel = st.columns([2, 2, 1])
        
        with col_global:
            if st.button(f"🌍 Applica Globalmente ({num_selezionate})", type="primary", use_container_width=True, key="apply_global_batch"):
                with st.spinner("🌍 Applicazione globale in corso..."):
                    try:
                        righe_ids = list(st.session_state.righe_pers_selezionate)
                        df_selezionate = df_filtrato[df_filtrato['id'].isin(righe_ids)]
                        
                        success_count = 0
                        for idx, row in df_selezionate.iterrows():
                            try:
                                # Upsert in prodotti_master
                                supabase.table('prodotti_master').upsert({
                                    'descrizione': row['descrizione'],
                                    'categoria': row['categoria'],
                                    'volte_visto': 1,
                                    'verified': True,
                                    'classificato_da': "Admin (promozione da personalizzazione)"
                                }, on_conflict='descrizione').execute()
                                
                                success_count += 1
                            except Exception as e:
                                logger.error(f"Errore promozione '{row['descrizione']}': {e}")
                        
                        # Elimina da memoria clienti (ora gestite da globale)
                        supabase.table('prodotti_utente')\
                            .delete()\
                            .in_('id', righe_ids)\
                            .execute()
                        
                        st.session_state.righe_pers_selezionate = set()
                        invalida_cache_memoria()
                        st.success(f"✅ {success_count} voci applicate globalmente!")
                        time.sleep(1.5)
                        st.rerun()
                        
                    except Exception as e:
                        logger.error(f"Errore applicazione globale: {e}")
                        st.error(f"❌ Errore: {e}")
        
        with col_delete:
            if st.button(f"🗑️ Elimina Selezionati ({num_selezionate})", type="secondary", use_container_width=True, key="delete_batch_pers"):
                with st.spinner("🗑️ Eliminazione in corso..."):
                    try:
                        righe_ids = list(st.session_state.righe_pers_selezionate)
                        
                        supabase.table('prodotti_utente')\
                            .delete()\
                            .in_('id', righe_ids)\
                            .execute()
                        
                        st.session_state.righe_pers_selezionate = set()
                        invalida_cache_memoria()
                        st.success(f"✅ {num_selezionate} voci eliminate!")
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        logger.error(f"Errore eliminazione: {e}")
                        st.error(f"❌ Errore: {e}")
        
        with col_cancel:
            if st.button("❌ Annulla", use_container_width=True, key="cancel_pers"):
                st.session_state.righe_pers_selezionate = set()
                st.rerun()


@st.cache_data(ttl=60, show_spinner=False)
def _load_all_rows_paginated(table_name: str, select_fields: str):
    rows = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            supabase.table(table_name)
            .select(select_fields)
            .order('id', desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = response.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def _carica_conflitti_memoria_dataset():
    global_rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto')
    local_rows = _load_all_rows_paginated('prodotti_utente', 'id, descrizione, categoria, volte_visto, user_id, classificato_da')

    if not global_rows or not local_rows:
        return pd.DataFrame()

    users_resp = supabase.table('users').select('id, email, nome_ristorante').execute()
    users_map = {
        row['id']: {
            'email': row.get('email') or 'Sconosciuto',
            'nome_ristorante': row.get('nome_ristorante') or 'N/A',
        }
        for row in (users_resp.data or [])
    }

    df_global = pd.DataFrame(global_rows).rename(
        columns={
            'id': 'global_id',
            'categoria': 'categoria_globale',
            'volte_visto': 'volte_visto_globale',
        }
    )
    df_local = pd.DataFrame(local_rows).rename(
        columns={
            'id': 'local_id',
            'categoria': 'categoria_locale',
            'volte_visto': 'volte_visto_locale',
        }
    )

    for frame in (df_global, df_local):
        if not frame.empty and 'descrizione' in frame.columns:
            frame['descrizione'] = frame['descrizione'].apply(
                lambda value: pulisci_caratteri_corrotti(value) if isinstance(value, str) else value
            )

    df_conf = df_local.merge(df_global, on='descrizione', how='inner')
    if df_conf.empty:
        return pd.DataFrame()

    df_conf = df_conf[df_conf['categoria_locale'] != df_conf['categoria_globale']].copy()
    if 'classificato_da' in df_conf.columns:
        df_conf = df_conf[
            ~df_conf['classificato_da'].fillna('').astype(str).str.contains('eccezione locale accettata', case=False, regex=False)
        ].copy()
    if df_conf.empty:
        return pd.DataFrame()

    df_conf['email_cliente'] = df_conf['user_id'].map(lambda uid: users_map.get(uid, {}).get('email', 'Sconosciuto'))
    df_conf['ristorante_cliente'] = df_conf['user_id'].map(lambda uid: users_map.get(uid, {}).get('nome_ristorante', 'N/A'))
    df_conf['impatto_locale'] = df_conf['volte_visto_locale'].fillna(0).astype(int)
    df_conf['impatto_globale'] = df_conf['volte_visto_globale'].fillna(0).astype(int)
    df_conf['impatto_totale'] = (df_conf['impatto_locale'] * 10) + df_conf['impatto_globale']
    return df_conf.sort_values(['impatto_totale', 'descrizione'], ascending=[False, True]).reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def _carica_globale_review_dataset():
    try:
        rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto, verified, classificato_da')
        campo_verified_exists = True
    except Exception:
        rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto')
        campo_verified_exists = False

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(), campo_verified_exists

    df['descrizione'] = df['descrizione'].apply(
        lambda value: pulisci_caratteri_corrotti(value) if isinstance(value, str) else value
    )
    if 'verified' not in df.columns:
        df['verified'] = False
    if 'classificato_da' not in df.columns:
        df['classificato_da'] = ''
    df['volte_visto'] = df['volte_visto'].fillna(0).astype(int)
    return df.sort_values(['verified', 'volte_visto', 'descrizione'], ascending=[True, False, True]).reset_index(drop=True), campo_verified_exists


@st.cache_data(ttl=60, show_spinner=False)
def _carica_audit_mismatch_prodotti_master():
    from services.ai_service import applica_regole_categoria_forti

    try:
        rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto, verified')
    except Exception:
        rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto')
    if not rows:
        return pd.DataFrame()

    mismatches = []
    for row in rows:
        # Salta voci verificate manualmente dall'admin — decisioni intenzionali
        if row.get('verified'):
            continue
        desc = row.get('descrizione') or ''
        cat_attuale = row.get('categoria') or 'Da Classificare'
        nuova_cat, motivo = applica_regole_categoria_forti(desc, cat_attuale)
        if motivo and nuova_cat != cat_attuale:
            mismatches.append({
                'id': row['id'],
                'descrizione': pulisci_caratteri_corrotti(desc) if isinstance(desc, str) else desc,
                'categoria_attuale': cat_attuale,
                'categoria_proposta': nuova_cat,
                'motivo': motivo,
                'volte_visto': int(row.get('volte_visto') or 0),
            })

    if not mismatches:
        return pd.DataFrame()

    return pd.DataFrame(mismatches).sort_values(['volte_visto', 'descrizione'], ascending=[False, True]).reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def _carica_globale_sospette_dataset():
    from services.ai_service import applica_correzioni_dizionario, applica_regole_categoria_forti

    try:
        rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto, verified, classificato_da')
    except Exception:
        rows = _load_all_rows_paginated('prodotti_master', 'id, descrizione, categoria, volte_visto')

    if not rows:
        return pd.DataFrame()

    sospette = []
    for row in rows:
        if row.get('verified'):
            continue

        desc = row.get('descrizione') or ''
        cat_attuale = (row.get('categoria') or 'Da Classificare').strip()
        cat_keyword = applica_correzioni_dizionario(desc, 'Da Classificare')
        cat_suggerita, motivo = applica_regole_categoria_forti(desc, cat_keyword)

        if not cat_suggerita or cat_suggerita == 'Da Classificare' or cat_suggerita == cat_attuale:
            continue

        sospette.append({
            'id': row['id'],
            'descrizione': pulisci_caratteri_corrotti(desc) if isinstance(desc, str) else desc,
            'categoria_attuale': cat_attuale,
            'categoria_suggerita': cat_suggerita,
            'motivo_sospetto': motivo or 'dizionario_attuale',
            'classificato_da': row.get('classificato_da') or '',
            'volte_visto': int(row.get('volte_visto') or 0),
        })

    if not sospette:
        return pd.DataFrame()

    return pd.DataFrame(sospette).sort_values(['volte_visto', 'descrizione'], ascending=[False, True]).reset_index(drop=True)


# ============================================================
# AZIONI CONDIVISE: Promozione e Allineamento con cascade fatture
# ============================================================

def _promuovi_locale_a_globale(global_id: int, local_id: int, descrizione: str,
                                categoria_locale: str, classificato_da: str):
    """
    Promuove una categoria cliente a memoria globale:
    1. Aggiorna prodotti_master.categoria
    2. Aggiorna fatture di TUTTI gli utenti SENZA override locale per questa descrizione
    3. Rimuove l'override locale (prodotti_utente) del cliente promotore
    """
    # 1. Aggiorna prodotti_master
    supabase.table('prodotti_master').update({
        'categoria': categoria_locale,
        'verified': True,
        'classificato_da': classificato_da,
    }).eq('id', global_id).execute()

    # 2. Cascade fatture con protezione override
    try:
        override_resp = supabase.table('prodotti_utente')\
            .select('user_id, categoria')\
            .eq('descrizione', descrizione)\
            .execute()

        user_ids_con_override = {}
        for row in (override_resp.data or []):
            uid = row['user_id']
            if uid:
                user_ids_con_override[uid] = row['categoria']

        # Aggiorna TUTTE le fatture con questa descrizione
        supabase.table('fatture')\
            .update({'categoria': categoria_locale})\
            .eq('descrizione', descrizione)\
            .execute()

        # Ripristina fatture degli utenti che hanno ALTRI override locali (non il promotore)
        for uid, cat_override in user_ids_con_override.items():
            if cat_override != categoria_locale:
                supabase.table('fatture')\
                    .update({'categoria': cat_override})\
                    .eq('descrizione', descrizione)\
                    .eq('user_id', uid)\
                    .execute()
    except Exception as e:
        logger.warning(f"⚠️ Errore cascade fatture per '{descrizione[:40]}': {e}")

    # 3. Rimuove l'override locale del promotore
    supabase.table('prodotti_utente').delete().eq('id', local_id).execute()


def _allinea_a_globale(local_id: int, descrizione: str, user_id: str, categoria_globale: str):
    """
    Rimuove override locale e riallinea il cliente alla memoria globale:
    1. Elimina la riga da prodotti_utente
    2. Aggiorna le fatture del cliente con la categoria globale
    """
    # 1. Rimuove override locale
    supabase.table('prodotti_utente').delete().eq('id', local_id).execute()

    # 2. Aggiorna fatture del cliente
    try:
        supabase.table('fatture')\
            .update({'categoria': categoria_globale})\
            .eq('descrizione', descrizione)\
            .eq('user_id', user_id)\
            .execute()
    except Exception as e:
        logger.warning(f"⚠️ Errore aggiornamento fatture cliente per '{descrizione[:40]}': {e}")


def _aggiorna_categoria_globale(row_id: int, descrizione: str, nuova_categoria: str,
                               verified: bool = False, classificato_da: str | None = None):
    """
    Aggiorna la categoria globale e propaga la modifica alle fatture,
    preservando eventuali override locali in prodotti_utente.
    """
    payload = {'categoria': nuova_categoria}
    if verified:
        payload['verified'] = True
    if classificato_da:
        payload['classificato_da'] = classificato_da

    supabase.table('prodotti_master').update(payload).eq('id', row_id).execute()

    try:
        override_resp = supabase.table('prodotti_utente')\
            .select('user_id, categoria')\
            .eq('descrizione', descrizione)\
            .execute()

        supabase.table('fatture')\
            .update({'categoria': nuova_categoria})\
            .eq('descrizione', descrizione)\
            .execute()

        for ov_row in (override_resp.data or []):
            supabase.table('fatture')\
                .update({'categoria': ov_row['categoria']})\
                .eq('descrizione', descrizione)\
                .eq('user_id', ov_row['user_id'])\
                .execute()
    except Exception as e:
        logger.warning(f"⚠️ Errore cascade globale per '{descrizione[:40]}': {e}")


def _aggiorna_categoria_locale(local_id: int, descrizione: str, user_id: str, nuova_categoria: str):
    """Aggiorna una categoria locale e propaga la modifica alle fatture del cliente."""
    supabase.table('prodotti_utente').update({
        'categoria': nuova_categoria,
        'classificato_da': 'Admin (edit memoria clienti)',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', local_id).execute()

    try:
        supabase.table('fatture')\
            .update({'categoria': nuova_categoria})\
            .eq('descrizione', descrizione)\
            .eq('user_id', user_id)\
            .execute()
    except Exception as e:
        logger.warning(f"⚠️ Errore cascade locale per '{descrizione[:40]}': {e}")


def _mantieni_locale_solo_cliente(local_id: int, descrizione: str, user_id: str, categoria_locale: str):
    """Conferma che il conflitto e' intenzionale e deve restare solo per quel cliente."""
    supabase.table('prodotti_utente').update({
        'categoria': categoria_locale,
        'classificato_da': 'Admin (eccezione locale accettata)',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', local_id).execute()

    try:
        supabase.table('fatture')\
            .update({'categoria': categoria_locale})\
            .eq('descrizione', descrizione)\
            .eq('user_id', user_id)\
            .execute()
    except Exception as e:
        logger.warning(f"⚠️ Errore conferma eccezione locale per '{descrizione[:40]}': {e}")


def tab_da_fare_memoria_ai():
    """Coda operativa prioritaria del nuovo hub Memoria AI."""
    st.markdown("## ✅ Da fare")
    st.caption("Qui trovi solo conflitti e anomalie prioritarie. Il resto del backlog resta nel tab Globale.")

    def _priority_badge(label, bg_color, text_color, border_color):
        return (
            f"<span style=\"display:inline-block;padding:0.15rem 0.55rem;border-radius:999px;"
            f"background:{bg_color};color:{text_color};border:1px solid {border_color};"
            f"font-size:0.78rem;font-weight:700;letter-spacing:0.01em;\">{label}</span>"
        )

    badge_alta = _priority_badge("ALTA PRIORITA", "#fff3e0", "#e65100", "#ff9800")
    badge_media = _priority_badge("SOSPETTA", "#fce4ec", "#ad1457", "#e91e63")
    badge_bassa = _priority_badge("ERRORE", "#e8f5e9", "#1b5e20", "#43a047")

    df_conflitti = _carica_conflitti_memoria_dataset()
    df_globale, campo_verified_exists = _carica_globale_review_dataset()
    df_sospette = _carica_globale_sospette_dataset() if campo_verified_exists else pd.DataFrame()
    df_audit = _carica_audit_mismatch_prodotti_master()
    categorie = st.session_state.categorie_cached

    non_verificati_totali = 0
    if not df_globale.empty and campo_verified_exists:
        non_verificati_totali = int((df_globale['verified'] == False).sum())

    priorita_frames = []
    ids_sospette = set()

    if not df_sospette.empty:
        df_sospette_queue = df_sospette.copy()
        df_sospette_queue['queue_tipo'] = 'Sospetta'
        df_sospette_queue['categoria_attesa'] = df_sospette_queue['categoria_suggerita']
        ids_sospette = set(df_sospette_queue['id'].tolist())
        priorita_frames.append(df_sospette_queue[[
            'id', 'descrizione', 'categoria_attuale', 'categoria_attesa',
            'motivo_sospetto', 'classificato_da', 'volte_visto', 'queue_tipo'
        ]])

    if not df_audit.empty:
        df_audit_queue = df_audit[~df_audit['id'].isin(ids_sospette)].copy()
        if not df_audit_queue.empty:
            df_audit_queue['queue_tipo'] = 'Errore'
            df_audit_queue['categoria_attesa'] = df_audit_queue['categoria_proposta']
            df_audit_queue['motivo_sospetto'] = df_audit_queue['motivo']
            df_audit_queue['classificato_da'] = 'audit'
            priorita_frames.append(df_audit_queue[[
                'id', 'descrizione', 'categoria_attuale', 'categoria_attesa',
                'motivo_sospetto', 'classificato_da', 'volte_visto', 'queue_tipo'
            ]])

    df_priorita = pd.concat(priorita_frames, ignore_index=True) if priorita_frames else pd.DataFrame(
        columns=['id', 'descrizione', 'categoria_attuale', 'categoria_attesa', 'motivo_sospetto', 'classificato_da', 'volte_visto', 'queue_tipo']
    )
    if not df_priorita.empty:
        df_priorita = df_priorita.sort_values(['queue_tipo', 'volte_visto', 'descrizione'], ascending=[True, False, True]).reset_index(drop=True)

    backlog_restante_globale = max(non_verificati_totali - df_priorita['id'].nunique(), 0) if campo_verified_exists else 0

    totale_priorita = len(df_conflitti) + len(df_priorita)
    st.markdown(
        f"""
        <div class="admin-metrics-grid">
            <div class="admin-metric-card" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
                <div class="admin-metric-label" style="color:#ef6c00;">🔥 Da fare ora</div>
                <div class="admin-metric-value" style="color:#e65100;">{totale_priorita:,}</div>
            </div>
            <div class="admin-metric-card" style="background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63;">
                <div class="admin-metric-label" style="color:#c2185b;">⚔️ Conflitti inclusi</div>
                <div class="admin-metric-value" style="color:#880e4f;">{len(df_conflitti):,}</div>
            </div>
            <div class="admin-metric-card" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
                <div class="admin-metric-label" style="color:#1976d2;">🌍 Nel tab Globale</div>
                <div class="admin-metric-value" style="color:#1565c0;">{backlog_restante_globale:,}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(df_conflitti) > 0:
        st.warning(
            f"Priorita alta: {len(df_conflitti)} conflitti attivi. Sotto trovi solo le anomalie globali realmente prioritarie; il resto resta nel tab Globale."
        )
    elif len(df_priorita) > 0:
        st.info(
            f"Nessun conflitto attivo. Restano {len(df_priorita)} verifiche prioritarie e {backlog_restante_globale} righe non verificate consultabili nel tab Globale."
        )
    else:
        st.success("Nessuna attivita prioritaria pendente nella memoria AI.")

    st.markdown("---")
    st.markdown("### 🔥 Coda prioritaria")
    st.markdown(
        f"{badge_alta} <span style='color:#666;'>I conflitti sono già inclusi qui e compaiono per primi</span>",
        unsafe_allow_html=True,
    )
    st.caption("Prima risolvi i conflitti tra memoria cliente e globale, poi confermi o correggi le anomalie globali prioritarie.")

    if not df_conflitti.empty:
        for _, row in df_conflitti.iterrows():
            desc_short = row['descrizione'][:80] + '...' if len(row['descrizione']) > 80 else row['descrizione']
            box1, box2, box3, box4 = st.columns([4.2, 1.25, 1.4, 1.4])
            with box1:
                st.markdown(f"{badge_alta} `{_html.escape(desc_short)}`", unsafe_allow_html=True)
                st.caption(f"{row['email_cliente']} · locale {row['categoria_locale']} vs globale {row['categoria_globale']}")
            with box2:
                if st.button("Globale", key=f"dafare_promote_{row['local_id']}", help="Promuovi categoria cliente a globale", use_container_width=True):
                    try:
                        _promuovi_locale_a_globale(
                            global_id=row['global_id'],
                            local_id=row['local_id'],
                            descrizione=row['descrizione'],
                            categoria_locale=row['categoria_locale'],
                            classificato_da='Admin (promozione da da-fare conflitti)',
                        )
                        invalida_cache_memoria()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore promozione: {e}")
            with box3:
                if st.button("Solo cliente", key=f"dafare_keep_local_{row['local_id']}", help="Mantieni questa categoria solo per questo cliente", use_container_width=True):
                    try:
                        _mantieni_locale_solo_cliente(
                            local_id=row['local_id'],
                            descrizione=row['descrizione'],
                            user_id=row['user_id'],
                            categoria_locale=row['categoria_locale'],
                        )
                        invalida_cache_memoria()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore conferma locale: {e}")
            with box4:
                if st.button("Usa globale", key=f"dafare_align_{row['local_id']}", help="Rimuovi override locale e riallinea al globale", use_container_width=True):
                    try:
                        _allinea_a_globale(
                            local_id=row['local_id'],
                            descrizione=row['descrizione'],
                            user_id=row['user_id'],
                            categoria_globale=row['categoria_globale'],
                        )
                        invalida_cache_memoria()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore riallineamento: {e}")
            st.markdown("---")

    st.markdown(
        f"{badge_media} <span style='color:#666;'>Sospette secondo le regole attuali</span> "
        f"{badge_bassa} <span style='color:#666;'>Mismatch audit da correggere</span>",
        unsafe_allow_html=True,
    )
    st.caption("Dopo i conflitti trovi solo errori e sospette prioritarie. Tutte le altre righe non verificate restano nel tab Globale.")

    if df_priorita.empty:
        if df_conflitti.empty:
            st.success("Nessuna attivita prioritaria da gestire")
            return
        st.info("Non restano altre anomalie prioritarie oltre ai conflitti.")

    if 'dafare_priorita_selezionate' not in st.session_state:
        st.session_state.dafare_priorita_selezionate = set()
    if 'dafare_priorita_refresh' not in st.session_state:
        st.session_state.dafare_priorita_refresh = 0

    righe_priorita_ids = set(df_priorita['id'].tolist())

    col_sel_title, col_sel_info = st.columns([2, 4])
    with col_sel_title:
        st.markdown("#### Selezione rapida")
    with col_sel_info:
        st.caption(f"Righe prioritarie mostrate: {len(df_priorita)}")

    col_sel_all, col_desel_all, col_hint = st.columns([1.2, 1.2, 4.6])
    with col_sel_all:
        if st.button("☑️ Seleziona tutte", key="dafare_select_all_priorita", use_container_width=True):
            st.session_state.dafare_priorita_selezionate.update(righe_priorita_ids)
            st.session_state.dafare_priorita_refresh += 1
            st.rerun()
    with col_desel_all:
        if st.button("⬜ Deseleziona tutte", key="dafare_deselect_all_priorita", use_container_width=True):
            st.session_state.dafare_priorita_selezionate.difference_update(righe_priorita_ids)
            st.session_state.dafare_priorita_refresh += 1
            st.rerun()
    with col_hint:
        st.caption("Seleziona le righe che vuoi confermare in blocco, poi salva tutto in fondo.")

    st.markdown("---")

    col_check_h, col_desc_h, col_cat_h, col_info_h = st.columns([0.55, 4.1, 2.3, 1.5])
    with col_desc_h:
        st.markdown("**Descrizione**")
    with col_cat_h:
        st.markdown("**Categoria**")
    with col_info_h:
        st.markdown("**Info**")
    st.markdown("---")

    selezionate_correnti = set()
    for _, row in df_priorita.iterrows():
        row_id = row['id']
        categoria_default = estrai_nome_categoria(row['categoria_attesa'])
        index_default = categorie.index(categoria_default) if categoria_default in categorie else 0
        badge = badge_media if row['queue_tipo'] == 'Sospetta' else badge_bassa

        col_check, col_desc, col_cat, col_info = st.columns([0.55, 4.1, 2.3, 1.5])
        with col_check:
            checked = st.checkbox(
                "sel",
                value=row_id in st.session_state.dafare_priorita_selezionate,
                key=f"dafare_chk_{row_id}_r{st.session_state.dafare_priorita_refresh}",
                label_visibility="collapsed",
            )
            if checked:
                selezionate_correnti.add(row_id)

        with col_desc:
            desc_short = row['descrizione'][:90] + '...' if len(row['descrizione']) > 90 else row['descrizione']
            st.markdown(f"{badge} `{_html.escape(desc_short)}`", unsafe_allow_html=True)
            st.caption(
                f"{row['queue_tipo']} · {row['categoria_attuale']} → {row['categoria_attesa']} · {row['motivo_sospetto']} · {int(row['volte_visto'])}×"
            )

        with col_cat:
            st.selectbox(
                "Categoria prioritaria",
                categorie,
                index=index_default,
                key=f"dafare_priorita_cat_{row_id}",
                label_visibility="collapsed",
            )

        with col_info:
            sorgente = (row.get('classificato_da') or 'N/D').replace('keyword-auto', 'keyword').replace('AI', 'AI')
            st.caption(sorgente)

        st.markdown("---")

    st.session_state.dafare_priorita_selezionate = selezionate_correnti
    num_selezionate = len(selezionate_correnti)

    if num_selezionate == 0:
        st.info("Seleziona una o più righe prioritarie per salvarle in blocco.")
        return

    righe_selezionate_df = df_priorita[df_priorita['id'].isin(selezionate_correnti)].copy()
    num_modifiche = 0
    for _, row in righe_selezionate_df.iterrows():
        nuova_cat = estrai_nome_categoria(st.session_state.get(f"dafare_priorita_cat_{row['id']}", row['categoria_attesa']))
        if nuova_cat != row['categoria_attuale']:
            num_modifiche += 1

    st.markdown("### 💾 Salvataggio massivo")
    st.info(
        f"Hai selezionato {num_selezionate} righe prioritarie. Tra queste, {num_modifiche} avranno una categoria diversa da quella attuale."
    )

    col_save, col_cancel = st.columns([2, 1])
    with col_save:
        if st.button(f"💾 Salva e conferma ({num_selezionate})", type="primary", use_container_width=True, key="dafare_save_massivo"):
            try:
                with st.spinner("Salvataggio massivo in corso..."):
                    success_count = 0
                    for _, row in righe_selezionate_df.iterrows():
                        nuova_cat = estrai_nome_categoria(st.session_state.get(f"dafare_priorita_cat_{row['id']}", row['categoria_attesa']))
                        _aggiorna_categoria_globale(
                            row_id=row['id'],
                            descrizione=row['descrizione'],
                            nuova_categoria=nuova_cat,
                            verified=True,
                            classificato_da=f"Admin (da fare {str(row['queue_tipo']).lower()})",
                        )
                        success_count += 1

                    invalida_cache_memoria()
                    st.session_state.dafare_priorita_selezionate = set()
                    st.session_state.dafare_priorita_refresh += 1
                    st.success(f"✅ {success_count} righe prioritarie salvate e confermate")
                    st.rerun()
            except Exception as e:
                st.error(f"Errore salvataggio massivo: {e}")
    with col_cancel:
        if st.button("❌ Annulla selezione", use_container_width=True, key="dafare_cancel_massivo"):
            st.session_state.dafare_priorita_selezionate = set()
            st.session_state.dafare_priorita_refresh += 1
            st.rerun()
def tab_memoria_ai_hub():
    """Hub unificato e semplificato per memoria AI."""
    st.markdown("## 🧠 Memoria AI")
    st.caption("Accesso semplice e immediato: da fare, memoria globale, memoria clienti")

    if 'vista_memoria_ai' not in st.session_state:
        st.session_state.vista_memoria_ai = "✅ Da fare"

    vista_memoria = st.radio(
        "Vista Memoria AI",
        ["✅ Da fare", "🌍 Globale", "👤 Clienti"],
        horizontal=True,
        key="vista_memoria_ai",
        label_visibility="collapsed",
    )

    st.markdown("---")

    if vista_memoria == "✅ Da fare":
        tab_da_fare_memoria_ai()
    elif vista_memoria == "🌍 Globale":
        tab_memoria_globale_unificata()
    else:
        tab_personalizzazioni_clienti()


# Chiama il nuovo hub unificato
if tab3:
    tab_memoria_ai_hub()

# ============================================================
# TAB 4: VERIFICA INTEGRITÀ DATABASE
# ============================================================

if tab4:
    st.markdown("## 🔍 Verifica Integrità Database")
    st.caption("Controlla anomalie nei dati delle fatture: date invalide, prezzi anomali, quantità strane, descrizioni vuote, duplicati, ecc.")

    @st.cache_data(ttl=60, show_spinner=False)
    def _carica_clienti_integrita_non_admin():
        try:
            resp = supabase.table('users')\
                .select('email, nome_ristorante')\
                .eq('attivo', True)\
                .order('nome_ristorante')\
                .execute()
            data = resp.data if resp.data else []
            return [u for u in data if (u.get('email') or '').strip().lower() not in ADMIN_EMAILS]
        except Exception:
            return []

    def _fetch_fatture_integrita_paginate(build_query_fn):
        """Pagina una query Supabase. build_query_fn() deve restituire un nuovo oggetto query ogni volta."""
        all_rows = []
        page_size = 1000
        offset = 0
        while True:
            resp = build_query_fn().range(offset, offset + page_size - 1).execute()
            rows = resp.data if resp.data else []
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < page_size:
                break
            offset += page_size
        return all_rows
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_email, col_periodo = st.columns(2)
    
    with col_email:
        # Carica lista clienti
        try:
            clienti_non_admin = _carica_clienti_integrita_non_admin()

            if clienti_non_admin:

                # Opzione "Tutti" all'inizio
                opzioni_clienti = ["Tutti i clienti"] + [
                    f"{c.get('nome_ristorante', 'N/A')} ({c['email']})" 
                    for c in clienti_non_admin
                ]
                
                # Mappa per recuperare email dalla selezione
                email_map = {
                    f"{c.get('nome_ristorante', 'N/A')} ({c['email']})": c['email']
                    for c in clienti_non_admin
                }
            else:
                opzioni_clienti = ["Tutti i clienti"]
                email_map = {}
        except Exception as e:
            logger.warning(f"Errore caricamento clienti per filtro: {e}")
            opzioni_clienti = ["Tutti i clienti"]
            email_map = {}
        
        # Selectbox clienti
        filtro_cliente_sel = st.selectbox(
            "👤 Seleziona Cliente",
            options=opzioni_clienti,
            key="filtro_cliente_upload_events"
        )
        
        # Estrai email dalla selezione
        if filtro_cliente_sel == "Tutti i clienti":
            filtro_email = None
        else:
            filtro_email = email_map.get(filtro_cliente_sel, None)
    
    with col_periodo:
        # Filtro periodo
        filtro_periodo = st.selectbox(
            "Periodo",
            ["Ultimi 30 giorni", "Ultimi 90 giorni", "Ultimi 180 giorni", "Tutto"],
            key="filtro_periodo_integrity"
        )
    
    st.markdown("---")

    # ============================================================
    # FILE SCARTATI (DUPLICATI) - da upload_events
    # ============================================================
    st.markdown("### 📋 File Scartati come Duplicati")
    st.caption("File che i clienti hanno tentato di ricaricare ma erano già presenti nel database")

    try:
        query_dupl = supabase.table('upload_events')\
            .select('user_email, file_name, created_at, status, details')\
            .in_('status', ['DUPLICATE_SKIPPED', 'DUPLICATE_IN_SELECTION'])\
            .order('created_at', desc=True)

        if filtro_email:
            query_dupl = query_dupl.eq('user_email', filtro_email)

        if filtro_periodo == "Ultimi 30 giorni":
            query_dupl = query_dupl.gte('created_at', (datetime.now() - timedelta(days=30)).isoformat())
        elif filtro_periodo == "Ultimi 90 giorni":
            query_dupl = query_dupl.gte('created_at', (datetime.now() - timedelta(days=90)).isoformat())
        elif filtro_periodo == "Ultimi 180 giorni":
            query_dupl = query_dupl.gte('created_at', (datetime.now() - timedelta(days=180)).isoformat())

        resp_dupl = query_dupl.limit(500).execute()
        dupl_data = resp_dupl.data if resp_dupl.data else []

        if not dupl_data:
            st.info("✅ Nessun file scartato nel periodo selezionato")
        else:
            st.warning(f"⚠️ **{len(dupl_data)} tentativi** di ricaricare file già presenti nel database")
            df_dupl = pd.DataFrame(dupl_data)
            if 'details' in df_dupl.columns:
                df_dupl['motivo'] = df_dupl['details'].apply(
                    lambda d: (d or {}).get('reason', '') if isinstance(d, dict) else ''
                )
            else:
                df_dupl['motivo'] = ''
            df_dupl = df_dupl.rename(columns={
                'user_email': 'cliente',
                'file_name': 'file',
                'created_at': 'data tentativo',
                'status': 'stato',
            })
            df_dupl['data tentativo'] = pd.to_datetime(df_dupl['data tentativo']).dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(df_dupl[['cliente', 'file', 'stato', 'motivo', 'data tentativo']], use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"⚠️ Impossibile caricare log duplicati: {e}")

    st.markdown("---")

    # ============================================================
    # VERIFICA INTEGRITÀ
    # ============================================================
    
    if st.button("🔍 Verifica Integrità Dati", key="btn_verifica_integrity", type="primary"):
        with st.spinner("Analisi dati in corso..."):
            try:
                # Prepara filtri per query paginata
                _filtro_rist_ids = None
                _filtro_user_id = None
                _filtro_data_limite = None
                
                # Filtro per ristorante (basato su email utente)
                if filtro_email:
                    user_resp = supabase.table('users').select('id').eq('email', filtro_email).execute()
                    if user_resp.data:
                        user_id = user_resp.data[0]['id']
                        rist_resp = supabase.table('ristoranti').select('id').eq('user_id', user_id).execute()
                        if rist_resp.data:
                            _filtro_rist_ids = [r['id'] for r in rist_resp.data if r.get('id')]
                        else:
                            _filtro_user_id = user_id
                
                # Filtro periodo
                if filtro_periodo == "Ultimi 30 giorni":
                    _filtro_data_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                elif filtro_periodo == "Ultimi 90 giorni":
                    _filtro_data_limite = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
                elif filtro_periodo == "Ultimi 180 giorni":
                    _filtro_data_limite = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
                
                def _build_integrity_query():
                    q = supabase.table('fatture').select('data_documento, prezzo_unitario, quantita, descrizione, totale_riga, fornitore')
                    if _filtro_rist_ids:
                        if len(_filtro_rist_ids) == 1:
                            q = q.eq('ristorante_id', _filtro_rist_ids[0])
                        else:
                            q = q.in_('ristorante_id', _filtro_rist_ids)
                    elif _filtro_user_id:
                        q = q.eq('user_id', _filtro_user_id)
                    if _filtro_data_limite:
                        q = q.gte('data_documento', _filtro_data_limite)
                    return q
                
                # Esegui query con paginazione (evita limite default 1000)
                rows = _fetch_fatture_integrita_paginate(_build_integrity_query)

                if not rows:
                    st.info("📭 Nessuna fattura trovata per il periodo selezionato")
                else:
                    df = pd.DataFrame(rows)
                    
                    # ============================================================
                    # ANALISI PROBLEMI
                    # ============================================================
                    
                    problemi = {
                        'date_invalide': [],
                        'righe_fantasma': [],
                        'dati_incompleti': [],
                        'importi_estremi': [],
                        'quantita_negative': [],
                        'descrizioni_vuote': [],
                        'totali_errati': []
                    }
                    
                    # Soglie per check reali (non falsi positivi da business normale)
                    SOGLIA_IMPORTO_ESTREMO = 50000.0   # €50.000 per singola riga → possibile errore parsing
                    SOGLIA_QTA_NEGATIVA = 0.0           # quantità negativa → sempre bug
                    SOGLIA_TOTALE_DIFF_ABS = 1.0        # differenza assoluta > €1.00 (non arrotondamento)
                    SOGLIA_TOTALE_DIFF_PCT = 0.05        # E differenza % > 5% del totale atteso

                    oggi = datetime.now().date()
                    for _, row in df.iterrows():
                        fornitore = row.get('fornitore', 'N/A')
                        data_doc = row.get('data_documento', 'N/A')
                        descrizione = str(row.get('descrizione', 'N/A') or 'N/A')
                        desc_short = descrizione[:50]

                        # Normalizzazioni numeriche
                        prezzo_raw = row.get('prezzo_unitario', None)
                        quantita_raw = row.get('quantita', None)
                        totale_raw = row.get('totale_riga', None)

                        try:
                            prezzo = float(prezzo_raw or 0)
                        except Exception:
                            prezzo = None

                        try:
                            quantita = float(quantita_raw or 0)
                        except Exception:
                            quantita = None

                        try:
                            totale = float(totale_raw or 0)
                        except Exception:
                            totale = None

                        # 1) Date invalide (future o non parsabili)
                        try:
                            data_fattura = pd.to_datetime(data_doc).date()
                            if data_fattura > oggi:
                                problemi['date_invalide'].append({
                                    'fornitore': fornitore,
                                    'data': data_doc,
                                    'descrizione': desc_short,
                                    'problema': f"Data futura: {data_fattura}"
                                })
                        except Exception:
                            problemi['date_invalide'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'problema': "Data non valida / non parsabile"
                            })

                        # 2) Righe fantasma: prezzo=0, quantità=0, totale=0
                        #    Indicano bug nell'import (riga vuota salvata per errore)
                        if prezzo == 0 and quantita == 0 and totale == 0:
                            desc_trim_f = descrizione.strip()
                            if len(desc_trim_f) >= 3:  # ha una descrizione ma tutti valori zero
                                problemi['righe_fantasma'].append({
                                    'fornitore': fornitore,
                                    'data': data_doc,
                                    'descrizione': desc_short,
                                    'problema': "Riga con prezzo=0, quantità=0, totale=0 (possibile bug import)"
                                })

                        # 3) Dati incompleti: prezzo e quantità valorizzati ma totale_riga null
                        #    Bug nel pipeline di salvataggio
                        if totale_raw is None and prezzo_raw is not None and quantita_raw is not None:
                            problemi['dati_incompleti'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'prezzo': f"€ {prezzo:.2f}" if prezzo is not None else 'N/A',
                                'quantita': quantita,
                                'problema': "totale_riga NULL con prezzo e quantità valorizzati (bug salvataggio)"
                            })

                        # 4) Importo riga estremo: |totale| > €50.000
                        #    Quasi certamente errore di parsing (es. cifre attaccate)
                        if totale is not None and abs(totale) > SOGLIA_IMPORTO_ESTREMO:
                            problemi['importi_estremi'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'totale_riga': f"€ {totale:,.2f}",
                                'problema': f"Importo singola riga > €{SOGLIA_IMPORTO_ESTREMO:,.0f} (possibile errore parsing)"
                            })

                        # 5) Quantità negativa (mai legittima — le note di credito hanno prezzo negativo, non quantità)
                        if quantita is not None and quantita < SOGLIA_QTA_NEGATIVA:
                            problemi['quantita_negative'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'valore': quantita,
                                'problema': "Quantità negativa (bug nel parser PDF)"
                            })

                        # 6) Descrizioni vuote o troppo corte
                        desc_trim = descrizione.strip()
                        if len(desc_trim) < 3:
                            problemi['descrizioni_vuote'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_trim if desc_trim else '(vuota)',
                                'problema': "Descrizione mancante o troppo corta"
                            })

                        # 7) Totali non corrispondenti: differenza > €1.00 E > 5%
                        #    Filtra il rumore da arrotondamento float (diff 1-20 cent)
                        #    Intercetta veri errori: IVA sbagliata, riga sommata male, ecc.
                        if prezzo is not None and quantita is not None and totale is not None:
                            calcolato = prezzo * quantita
                            diff_abs = abs(calcolato - totale)
                            base = abs(calcolato) if abs(calcolato) > 0.01 else abs(totale)
                            diff_pct = (diff_abs / base) if base > 0.01 else 0
                            if diff_abs > SOGLIA_TOTALE_DIFF_ABS and diff_pct > SOGLIA_TOTALE_DIFF_PCT:
                                problemi['totali_errati'].append({
                                    'fornitore': fornitore,
                                    'data': data_doc,
                                    'descrizione': desc_short,
                                    'calcolato': f"€ {calcolato:.2f}",
                                    'salvato': f"€ {totale:.2f}",
                                    'problema': f"Differenza: € {diff_abs:.2f} ({diff_pct*100:.1f}%)"
                                })
                    
                    # ============================================================
                    # RISULTATI
                    # ============================================================
                    
                    totale_problemi = sum(len(v) for v in problemi.values())
                    
                    if totale_problemi == 0:
                        st.success("✅ Nessun problema di integrità rilevato!")
                        st.info(f"Analizzate **{len(df):,} righe** di fatture. Tutti i dati sono corretti.")
                    else:
                        st.warning(f"⚠️ Trovati **{totale_problemi} problemi** su {len(df):,} righe analizzate")
                        
                        with st.expander(f"📊 Riepilogo Problemi ({totale_problemi})", expanded=True):
                            _n_date = len(problemi['date_invalide'])
                            _n_fantasma = len(problemi['righe_fantasma'])
                            _n_incompleti = len(problemi['dati_incompleti'])
                            _n_estremi = len(problemi['importi_estremi'])
                            _n_qta_neg = len(problemi['quantita_negative'])
                            _n_desc = len(problemi['descrizioni_vuote'])
                            _n_totali = len(problemi['totali_errati'])
                            
                            st.markdown(f"""
                            <div class="admin-metrics-grid" style="gap:10px;">
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
                                    <div class="admin-metric-label" style="color:#e65100;">📅 Date Invalide</div>
                                    <div class="admin-metric-value" style="color:#e65100;">{_n_date}</div>
                                </div>
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63;">
                                    <div class="admin-metric-label" style="color:#c2185b;">👻 Righe Fantasma</div>
                                    <div class="admin-metric-value" style="color:#880e4f;">{_n_fantasma}</div>
                                </div>
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0;">
                                    <div class="admin-metric-label" style="color:#7b1fa2;">⚠️ Dati Incompleti</div>
                                    <div class="admin-metric-value" style="color:#6a1b9a;">{_n_incompleti}</div>
                                </div>
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#ffebee,#ffcdd2); border:2px solid #f44336;">
                                    <div class="admin-metric-label" style="color:#b71c1c;">💸 Importi Estremi</div>
                                    <div class="admin-metric-value" style="color:#b71c1c;">{_n_estremi}</div>
                                </div>
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50;">
                                    <div class="admin-metric-label" style="color:#1b5e20;">📦 Qtà Negative</div>
                                    <div class="admin-metric-value" style="color:#1b5e20;">{_n_qta_neg}</div>
                                </div>
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
                                    <div class="admin-metric-label" style="color:#1976d2;">📝 Desc. Vuote</div>
                                    <div class="admin-metric-value" style="color:#1565c0;">{_n_desc}</div>
                                </div>
                                <div class="admin-metric-card admin-metric-card--compact" style="background:linear-gradient(135deg,#e0f7fa,#b2ebf2); border:2px solid #00bcd4;">
                                    <div class="admin-metric-label" style="color:#006064;">🧮 Totali Errati</div>
                                    <div class="admin-metric-value" style="color:#00838f;">{_n_totali}</div>
                                </div>
                            </div>
                            <div class="admin-note-inline">
                                ℹ️ Check attivi: date future/invalide · righe fantasma (tutto a zero) · totale_riga NULL · importo singola riga &gt;€50.000 · quantità negative · descrizioni vuote · totale diverge &gt;€1 e &gt;5%
                            </div>
                            """, unsafe_allow_html=True)
                            
                            st.markdown("---")
                            
                            if _n_date > 0:
                                st.markdown("**📅 Date Invalide** — data futura o non parsabile")
                                st.dataframe(pd.DataFrame(problemi['date_invalide']), use_container_width=True, hide_index=True)
                            
                            if _n_fantasma > 0:
                                st.markdown("**👻 Righe Fantasma** — prezzo=0, quantità=0, totale=0 (bug import)")
                                st.dataframe(pd.DataFrame(problemi['righe_fantasma']), use_container_width=True, hide_index=True)
                            
                            if _n_incompleti > 0:
                                st.markdown("**⚠️ Dati Incompleti** — totale_riga NULL con prezzo e quantità valorizzati (bug salvataggio)")
                                st.dataframe(pd.DataFrame(problemi['dati_incompleti']), use_container_width=True, hide_index=True)
                            
                            if _n_estremi > 0:
                                st.markdown("**💸 Importi Estremi** — singola riga >€50.000 (possibile errore parsing)")
                                st.dataframe(pd.DataFrame(problemi['importi_estremi']), use_container_width=True, hide_index=True)
                            
                            if _n_qta_neg > 0:
                                st.markdown("**📦 Quantità Negative** — bug nel parser PDF")
                                st.dataframe(pd.DataFrame(problemi['quantita_negative']), use_container_width=True, hide_index=True)
                            
                            if _n_desc > 0:
                                st.markdown("**📝 Descrizioni Vuote** — descrizione mancante o troppo corta")
                                st.dataframe(pd.DataFrame(problemi['descrizioni_vuote']), use_container_width=True, hide_index=True)
                            
                            if _n_totali > 0:
                                st.markdown("**🧮 Totali Errati** — differenza >€1 e >5% (esclude arrotondamento float)")
                                st.dataframe(pd.DataFrame(problemi['totali_errati']), use_container_width=True, hide_index=True)
                        

            
            except Exception as e:
                st.error("❌ Errore durante la verifica del database.")
                logger.exception("Errore verifica integrità DB")
                with st.expander("🔍 Dettagli Tecnici"):
                    st.code(traceback.format_exc())

    # ============================================================
    # FATTURE TD24 — COPERTURA DATA CONSEGNA
    # ============================================================
    st.markdown("---")
    with st.expander("📅 Fatture TD24 — Copertura Data Consegna", expanded=False):
        st.caption("Fatture differite (TD24): percentuale di righe con data consegna estratta dal DDT.")
        try:
            # Query: conta righe TD24 per utente, con e senza data_consegna
            _td24_query = supabase.table('fatture')\
                .select('user_id, file_origine, fornitore, data_consegna, data_documento, totale_riga')\
                .eq('tipo_documento', 'TD24')

            if filtro_email:
                # Cerca user_id dalla email
                _user_resp = supabase.table('users').select('id').eq('email', filtro_email).execute()
                if _user_resp.data:
                    _td24_query = _td24_query.eq('user_id', _user_resp.data[0]['id'])

            # Applica lo stesso filtro periodo del resto del pannello
            _td24_days = None
            if filtro_periodo == "Ultimi 30 giorni":
                _td24_days = 30
            elif filtro_periodo == "Ultimi 90 giorni":
                _td24_days = 90
            elif filtro_periodo == "Ultimi 180 giorni":
                _td24_days = 180
            if _td24_days is not None:
                _cutoff_date = (datetime.now(timezone.utc) - timedelta(days=_td24_days)).strftime('%Y-%m-%d')
                _td24_query = _td24_query.gte('data_documento', _cutoff_date)

            _td24_rows = []
            _offset = 0
            _page = 1000
            while True:
                _resp = _td24_query.range(_offset, _offset + _page - 1).execute()
                _batch = _resp.data if _resp.data else []
                if not _batch:
                    break
                _td24_rows.extend(_batch)
                if len(_batch) < _page:
                    break
                _offset += _page

            if _td24_rows:
                df_td24 = pd.DataFrame(_td24_rows)
                df_td24['has_date'] = df_td24['data_consegna'].notna() & (df_td24['data_consegna'] != '')
                df_td24['totale_riga'] = pd.to_numeric(df_td24.get('totale_riga'), errors='coerce').fillna(0)

                # Aggregazione per user_id + file
                agg = df_td24.groupby(['user_id', 'file_origine', 'fornitore']).agg(
                    righe_totali=('has_date', 'count'),
                    righe_con_data=('has_date', 'sum'),
                    totale_eur=('totale_riga', 'sum'),
                ).reset_index()
                agg['pct_coperta'] = (agg['righe_con_data'] / agg['righe_totali'] * 100).round(1)
                agg['status'] = agg['pct_coperta'].apply(
                    lambda p: '🔴 Missing' if p < 50 else ('🟡 Parziale' if p < 95 else '🟢 OK')
                )

                # Riepilogo per utente
                user_agg = agg.groupby('user_id').agg(
                    file_td24=('file_origine', 'nunique'),
                    righe_totali=('righe_totali', 'sum'),
                    righe_con_data=('righe_con_data', 'sum'),
                ).reset_index()
                user_agg['pct_coperta'] = (user_agg['righe_con_data'] / user_agg['righe_totali'] * 100).round(1)

                # Risolvi email da user_id
                _uid_list = user_agg['user_id'].unique().tolist()
                _email_map = {}
                for _uid in _uid_list:
                    try:
                        _e_resp = supabase.table('users').select('email').eq('id', _uid).limit(1).execute()
                        if _e_resp.data:
                            _email_map[_uid] = _e_resp.data[0]['email']
                    except Exception:
                        pass
                user_agg['email'] = user_agg['user_id'].map(_email_map).fillna('?')

                # KPI
                col1, col2, col3 = st.columns(3)
                col1.metric("File TD24 totali", int(agg['file_origine'].nunique()))
                col2.metric("Copertura media", f"{user_agg['pct_coperta'].mean():.1f}%")
                _n_problem = len(agg[agg['pct_coperta'] < 95])
                col3.metric("File con alert", _n_problem)

                st.markdown("**Riepilogo per cliente:**")
                st.dataframe(
                    user_agg[['email', 'file_td24', 'righe_totali', 'righe_con_data', 'pct_coperta']].rename(columns={
                        'email': 'Email',
                        'file_td24': 'File TD24',
                        'righe_totali': 'Righe Totali',
                        'righe_con_data': 'Con Data',
                        'pct_coperta': '% Coperta',
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

                # Dettaglio file con problemi
                _problem_files = agg[agg['pct_coperta'] < 95].sort_values('pct_coperta')
                if not _problem_files.empty:
                    st.markdown("**Dettaglio file con copertura < 95%:**")
                    _display = _problem_files[['fornitore', 'file_origine', 'righe_totali', 'righe_con_data', 'pct_coperta', 'totale_eur', 'status']].rename(columns={
                        'fornitore': 'Fornitore',
                        'file_origine': 'File',
                        'righe_totali': 'Righe',
                        'righe_con_data': 'Con Data',
                        'pct_coperta': '% Coperta',
                        'totale_eur': 'Totale €',
                        'status': 'Status',
                    })
                    st.dataframe(_display, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Tutti i file TD24 hanno copertura data consegna ≥ 95%.")
            else:
                st.info("Nessuna fattura TD24 trovata nel database.")
        except Exception as e:
            st.error("❌ Errore durante il caricamento dati TD24.")
            logger.exception("Errore sezione TD24 admin")


# ============================================================
# TAB 6: COSTI AI PER CLIENTE (era TAB 5)
# ============================================================

if tab5:
    st.markdown("## 💳 Costi AI per Cliente")
    st.caption("Monitoraggio reale dei costi AI per periodo, cliente e tipo operazione")
    
    try:
        periodo_options = {
            'Ultimi 7 giorni': 7,
            'Ultimi 30 giorni': 30,
            'Ultimi 90 giorni': 90,
            'Tutto': None,
        }
        col_periodo, col_refresh = st.columns([2, 1])
        with col_periodo:
            periodo_label = st.selectbox(
                'Periodo',
                list(periodo_options.keys()),
                index=1,
                key='ai_costs_period',
            )
        with col_refresh:
            st.markdown('<br>', unsafe_allow_html=True)
            if st.button('🔄 Aggiorna', key='refresh_ai_costs', use_container_width=True):
                st.rerun()

        days_value = periodo_options[periodo_label]
        summary_args = {'p_days': days_value} if days_value is not None else {}
        timeseries_args = {'p_days': days_value or 30}
        recent_args = {'p_days': days_value or 30, 'p_limit': 100}

        response = supabase.rpc('get_ai_costs_summary', summary_args).execute()
        timeseries_response = supabase.rpc('get_ai_costs_timeseries', timeseries_args).execute()
        recent_response = supabase.rpc('get_ai_recent_operations', recent_args).execute()

        if not response.data or len(response.data) == 0:
            st.info('📊 Nessun utilizzo AI registrato nel periodo selezionato.')
        else:
            df_costs = pd.DataFrame(response.data)
            df_timeseries = pd.DataFrame(timeseries_response.data or [])
            df_recent = pd.DataFrame(recent_response.data or [])

            st.markdown('### 📊 Riepilogo Globale')

            totale_costi = float(df_costs['ai_cost_total'].sum())
            totale_pdf = int(df_costs['ai_pdf_count'].sum())
            totale_categorization = int(df_costs['ai_categorization_count'].sum())
            totale_operazioni = totale_pdf + totale_categorization
            totale_pdf_cost = float(df_costs['pdf_cost_total'].sum())
            totale_categorization_cost = float(df_costs['categorization_cost_total'].sum())
            totale_tokens = int(df_costs['total_tokens'].sum())
            costo_medio = totale_costi / totale_operazioni if totale_operazioni > 0 else 0
            costo_medio_pdf = totale_pdf_cost / totale_pdf if totale_pdf > 0 else 0
            costo_medio_categ = totale_categorization_cost / totale_categorization if totale_categorization > 0 else 0
            clienti_attivi = len(df_costs)

            st.markdown(f"""
            <div class="admin-metrics-grid">
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63;">
                    <div class="admin-metric-label" style="color:#c2185b;">💰 Totale Costi</div>
                    <div class="admin-metric-value" style="color:#880e4f;">${totale_costi:.4f}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3;">
                    <div class="admin-metric-label" style="color:#1976d2;">📄 Costo PDF</div>
                    <div class="admin-metric-value" style="color:#1565c0;">${totale_pdf_cost:.4f}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0;">
                    <div class="admin-metric-label" style="color:#7b1fa2;">🧠 Costo Categ.</div>
                    <div class="admin-metric-value" style="color:#6a1b9a;">${totale_categorization_cost:.4f}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800;">
                    <div class="admin-metric-label" style="color:#e65100;">📊 Costo Medio</div>
                    <div class="admin-metric-value" style="color:#e65100;">${costo_medio:.4f}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50;">
                    <div class="admin-metric-label" style="color:#2e7d32;">🔢 Token Totali</div>
                    <div class="admin-metric-value" style="color:#1b5e20;">{totale_tokens:,}</div>
                </div>
                <div class="admin-metric-card" style="background:linear-gradient(135deg,#ede7f6,#d1c4e9); border:2px solid #673ab7;">
                    <div class="admin-metric-label" style="color:#512da8;">👥 Clienti Attivi</div>
                    <div class="admin-metric-value" style="color:#4527a0;">{clienti_attivi}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.caption(
                f'Operazioni nel periodo: {totale_operazioni:,} | '
                f'PDF: {totale_pdf:,} (${costo_medio_pdf:.4f}/pdf) | '
                f'Categorizzazioni: {totale_categorization:,} (${costo_medio_categ:.4f}/batch)'
            )

            st.markdown('### 📋 Dettaglio per Cliente')
            df_display = df_costs.copy()
            df_display['Cliente'] = df_display['nome_ristorante']
            df_display['Ragione Sociale'] = df_display['ragione_sociale'].fillna('-')
            df_display['PDF'] = df_display['ai_pdf_count'].astype(int)
            df_display['Categorizzazioni'] = df_display['ai_categorization_count'].astype(int)
            df_display['Costo PDF'] = df_display['pdf_cost_total'].apply(lambda x: f"${float(x):.4f}")
            df_display['Costo Categ.'] = df_display['categorization_cost_total'].apply(lambda x: f"${float(x):.4f}")
            df_display['Costo Totale'] = df_display['ai_cost_total'].apply(lambda x: f"${float(x):.4f}")
            df_display['Costo/Op'] = df_display['ai_avg_cost_per_operation'].apply(lambda x: f"${float(x):.4f}")
            df_display['Token'] = df_display['total_tokens'].astype(int)
            df_display['Ultimo Uso'] = pd.to_datetime(df_display['ai_last_usage']).dt.strftime('%Y-%m-%d %H:%M')

            st.dataframe(
                df_display[['Cliente', 'Ragione Sociale', 'PDF', 'Categorizzazioni', 'Costo PDF', 'Costo Categ.', 'Costo Totale', 'Costo/Op', 'Token', 'Ultimo Uso']],
                width='stretch',
                hide_index=True,
            )

            st.markdown('---')
            col_export, col_spacer = st.columns([2, 8])
            with col_export:
                csv_data = df_display[['Cliente', 'Ragione Sociale', 'PDF', 'Categorizzazioni', 'Costo PDF', 'Costo Categ.', 'Costo Totale', 'Costo/Op', 'Token', 'Ultimo Uso']].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label='📥 Esporta CSV',
                    data=csv_data,
                    file_name=f"costi_ai_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                    use_container_width=True,
                )

            if not df_timeseries.empty:
                st.markdown('---')
                st.markdown('### 📈 Andamento Costi')
                df_timeseries['usage_date'] = pd.to_datetime(df_timeseries['usage_date'])
                fig_trend = px.line(
                    df_timeseries,
                    x='usage_date',
                    y=['total_cost', 'pdf_cost', 'categorization_cost'],
                    markers=True,
                    title='Trend costi AI nel periodo',
                    labels={'usage_date': '', 'value': 'Costo ($)', 'variable': 'Serie'},
                )
                fig_trend.update_layout(height=380)
                st.plotly_chart(fig_trend, use_container_width=True)

            st.markdown('---')
            st.markdown('### 📈 Top 10 Clienti per Costo')
            df_top = df_costs.nlargest(10, 'ai_cost_total').copy()
            df_top['Cliente'] = df_top['nome_ristorante']
            fig = px.bar(
                df_top,
                x='Cliente',
                y='ai_cost_total',
                title='Costi AI per Cliente (Top 10)',
                labels={'ai_cost_total': 'Costo ($)', 'Cliente': ''},
                color='ai_cost_total',
                color_continuous_scale='Blues'
            )
            fig.update_layout(showlegend=False, xaxis_tickangle=-45, height=400)
            st.plotly_chart(fig, use_container_width=True)

            if not df_recent.empty:
                st.markdown('---')
                st.markdown('### 🧾 Ultime Operazioni AI')
                df_recent['Quando'] = pd.to_datetime(df_recent['created_at']).dt.strftime('%Y-%m-%d %H:%M')
                df_recent['Cliente'] = df_recent['nome_ristorante']
                df_recent['Tipo'] = df_recent['operation_type'].replace({'pdf': 'PDF', 'categorization': 'Categorizzazione', 'other': 'Altro'})
                df_recent['Costo'] = df_recent['total_cost'].apply(lambda x: f"${float(x):.6f}")
                df_recent['Token'] = df_recent['total_tokens'].astype(int)
                df_recent['Item'] = df_recent['item_count'].astype(int)
                df_recent['File'] = df_recent['source_file'].fillna('-')
                st.dataframe(
                    df_recent[['Quando', 'Cliente', 'Tipo', 'model', 'Item', 'Token', 'Costo', 'File']],
                    width='stretch',
                    hide_index=True,
                )

            st.markdown('---')
            st.info(
                'I costi ora sono letti da un ledger eventi AI: puoi analizzarli per periodo, split PDF/categorizzazione e ultime operazioni. '
                'I file XML restano gratuiti.'
            )
    
    except Exception as e:
        st.error("❌ Errore caricamento dati Costi AI.")
        logger.exception("Errore nel tab Costi AI")
        with st.expander("🔍 Dettagli Errore"):
            st.code(traceback.format_exc())

