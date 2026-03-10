"""
🔧 PANNELLO AMMINISTRAZIONE - OH YEAH!
===============================================
Pannello admin con 6 TAB:
- Gestione Clienti (con impersonazione)
- Review Righe €0 (con revisione permanente)
- Memoria Globale AI (prodotti_master)
- Memoria Clienti (prodotti_utente)
- Verifica Integrità Database
- Costi AI per Cliente
"""

import streamlit as st
import pandas as pd
import re
import html as _html
from datetime import datetime, timezone, timedelta
import time
import traceback
import extra_streamlit_components as stx
import requests

# Import corretto da utils (non da app.py per evitare esecuzione interfaccia)
from utils.formatters import carica_categorie_da_db
from utils.text_utils import estrai_nome_categoria, aggiungi_icona_categoria, pulisci_caratteri_corrotti
from utils.validation import is_dicitura_sicura, is_sconto_omaggio_sicuro
from utils.piva_validator import valida_formato_piva, normalizza_piva
from services.auth_service import crea_cliente_con_token
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
# RIPRISTINO SESSIONE DA COOKIE (session_token, come in app.py)
# ============================================================
try:
    # Inizializza logged_in se non esiste
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Ripristina sessione da token cookie se non loggato
    if not st.session_state.logged_in and _cookie_manager_admin is not None:
        _token_admin = _cookie_manager_admin.get("session_token")
        
        if _token_admin:
            try:
                response = supabase.table("users").select("*").eq("session_token", _token_admin).eq("attivo", True).execute()
                if response and getattr(response, 'data', None) and len(response.data) > 0:
                    st.session_state.logged_in = True
                    st.session_state.user_data = response.data[0]
                    logger.info(f"✅ Sessione admin ripristinata da session_token")
            except Exception as e:
                logger.error(f"Errore recupero utente da session_token: {e}")
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
admin_original_email = admin_original_user.get('email')
is_admin_impersonating = is_impersonating and admin_original_email in ADMIN_EMAILS

if user.get('email') not in ADMIN_EMAILS:
    # Se l'admin sta impersonando un cliente, consenti accesso al pannello
    # ripristinando automaticamente l'utente admin originale.
    if is_admin_impersonating:
        # Verifica integrità dati admin prima del ripristino
        if not admin_original_user.get('email') or admin_original_user['email'] not in ADMIN_EMAILS:
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
            except Exception:
                pass
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
            ristoranti_response = supabase.table('ristoranti').select('*').eq('user_id', user_id).execute()
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

    clienti_non_admin = [u for u in query_users.data if u.get('email') not in admin_emails_set]
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
                    'pagine_abilitate': user_data.get('pagine_abilitate') or {'marginalita': True, 'workspace': True},
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
                'pagine_abilitate': user_data.get('pagine_abilitate') or {'marginalita': True, 'workspace': True},
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
st.title("👨‍💼 Pannello Amministrazione")
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
tab_names = ["📊 Gestione Clienti", "💰 Review Righe €0", "🧠 Memoria Globale AI", "📝 Memoria Clienti", "🔍 Integrità Database", "💳 Costi AI"]
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
tab6 = (st.session_state.active_tab == 5)


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
                help="Email per login cliente"
            )
            new_name = st.text_input(
                "🏪 Nome ristorante *", 
                key="new_name", 
                placeholder="Es: Ristorante Da Mario",
                help="Nome locale"
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
                help="Nome ufficiale azienda (opzionale)"
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
            
            if not new_email or '@' not in new_email:
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
                        # Invia email con link attivazione
                        email_inviata = False
                        try:
                            brevo_api_key = st.secrets["brevo"]["api_key"]
                            sender_email = st.secrets["brevo"]["sender_email"]
                            app_url = st.secrets.get("app", {}).get("url", "https://envoicescan-ai.streamlit.app")
                            
                            # Link con token per impostare password
                            link_attivazione = f"{app_url}?reset_token={token}"
                            
                            url_brevo = "https://api.brevo.com/v3/smtp/email"
                            
                            email_html = f"""
                            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                <h2 style="color: #2c5aa0;">🎉 Benvenuto in OH YEAH!</h2>
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
                                    <strong>OH YEAH! Team</strong><br>
                                    <a href="https://envoicescan-ai.streamlit.app">envoicescan-ai.streamlit.app</a><br>
                                    📧 Support: mattiadavolio90@gmail.com
                                </p>
                            </div>
                            """
                            
                            payload = {
                                "sender": {"email": sender_email, "name": "OH YEAH!"},
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
                            .select('*')\
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
                                                    # Verifica P.IVA non duplicata
                                                    check_piva = supabase.table('ristoranti')\
                                                        .select('id')\
                                                        .eq('partita_iva', piva_norm_mr)\
                                                        .execute()
                                                    
                                                    if check_piva.data:
                                                        st.error(f"❌ P.IVA {piva_norm_mr} già registrata")
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
                                        
                                        if st.button(f"🗑️ Elimina {rist_da_eliminare['nome_ristorante']}", 
                                                    type="secondary", 
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
            <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#1976d2; font-weight:600;">👥 Clienti</div>
                    <div style="font-size:1.6rem; color:#1565c0; font-weight:bold;">{_n_clienti}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#2e7d32; font-weight:600;">✅ Attivi</div>
                    <div style="font-size:1.6rem; color:#1b5e20; font-weight:bold;">{_n_attivi}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#7b1fa2; font-weight:600;">🏢 Sedi</div>
                    <div style="font-size:1.6rem; color:#6a1b9a; font-weight:bold;">{_n_ristoranti}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#e65100; font-weight:600;">📄 Fatture</div>
                    <div style="font-size:1.6rem; color:#e65100; font-weight:bold;">{_n_fatture:,}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e0f7fa,#b2ebf2); border:2px solid #00bcd4; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#006064; font-weight:600;">📊 Righe</div>
                    <div style="font-size:1.6rem; color:#00838f; font-weight:bold;">{_n_righe:,}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#c2185b; font-weight:600;">💰 Costi</div>
                    <div style="font-size:1.6rem; color:#880e4f; font-weight:bold;">€{_tot_costi:,.0f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Ordina alfabeticamente per email
            df_clienti_sorted = df_clienti.sort_values('email', ascending=True)
            
            # ===== LISTA CLIENTI CON EXPANDER =====
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
                    _piva_str = row.get('partita_iva', '') or '—'
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
                            
                            cliente_data = {
                                'id': row['user_id'],
                                'email': row['email'],
                                'nome_ristorante': row['ristorante'],
                                'attivo': row['attivo']
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
                            
                            logger.info(f"🔀 IMPERSONAZIONE: admin={st.session_state.admin_original_user['email']} → cliente={row['email']}")
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
                                        
                                        logger.info(f"🔴 Account disattivato: {row['email']}")
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
                                        
                                        logger.info(f"🟢 Account attivato: {row['email']}")
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
                                    import uuid
                                    
                                    reset_token = str(uuid.uuid4())
                                    expires_at = datetime.now() + timedelta(hours=1)
                                    
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
                                        oggetto="🔑 Reset Password - OH YEAH!",
                                        corpo_html=f"""
                                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                            <h2 style="color: #2c5aa0;">🔑 Reset Password Richiesto</h2>
                                            <p>Ciao,</p>
                                            <p>L'amministratore ha richiesto un reset della tua password su <strong>OH YEAH!</strong>.</p>
                                            <p>Clicca sul pulsante per impostare una nuova password:</p>
                                            <div style="text-align: center; margin: 30px 0;">
                                                <a href="{reset_url}" style="background-color:#0ea5e9;color:white;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">🔐 Imposta Nuova Password</a>
                                            </div>
                                            <p style="color: #dc2626;">⚠️ <strong>Importante:</strong> Questo link è valido per <strong>1 ora</strong>.</p>
                                            <p style="color: #888; font-size: 13px;">Se non hai richiesto questo reset, ignora questa email.</p>
                                            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                                            <p style="color: #666; font-size: 13px;">---<br><strong>OH YEAH! Team</strong><br>📧 Support: mattiadavolio90@gmail.com</p>
                                        </div>
                                        """
                                    )
                                    
                                    if email_inviata:
                                        logger.info(f"📧 Email reset password inviata a: {row['email']}")
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
                            
                            # AZIONE 2b: Gestione Pagine Abilitate
                            st.markdown("**📄 Pagine Abilitate**")
                            st.caption("Analisi Fatture è sempre attiva")
                            
                            pagine = row.get('pagine_abilitate') or {'marginalita': True, 'workspace': True}
                            
                            new_marginalita = st.checkbox(
                                "💰 Marginalità",
                                value=pagine.get('marginalita', True),
                                key=f"page_marg_{row_key}"
                            )
                            new_workspace = st.checkbox(
                                "🍴 Workspace",
                                value=pagine.get('workspace', True),
                                key=f"page_ws_{row_key}"
                            )
                            
                            if new_marginalita != pagine.get('marginalita', True) or new_workspace != pagine.get('workspace', True):
                                try:
                                    new_pagine = {
                                        'marginalita': new_marginalita,
                                        'workspace': new_workspace,
                                        'blocco_anno_precedente': pagine.get('blocco_anno_precedente', True)
                                    }
                                    supabase.table('users')\
                                        .update({'pagine_abilitate': new_pagine})\
                                        .eq('id', row['user_id'])\
                                        .execute()
                                    
                                    logger.info(f"📄 Pagine aggiornate per {row['email']}: {new_pagine}")
                                    st.success(f"✅ Pagine aggiornate")
                                    _carica_stats_clienti_admin.clear()
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    if 'pagine_abilitate' in str(e) or 'PGRST204' in str(e):
                                        st.error("⚠️ Esegui migrazione 038_add_pagine_abilitate.sql su Supabase per abilitare questa funzionalità")
                                    else:
                                        st.error(f"Errore: {e}")
                                        logger.exception(f"Errore aggiornamento pagine_abilitate per {row.get('email')}")
                            
                            st.markdown("---")
                            
                            # AZIONE 2c: Blocco Fatture Anno Precedente
                            st.markdown("**📅 Restrizione Periodo Fatture**")
                            anno_corrente = datetime.now().year
                            st.caption(f"Se attivo, il cliente può caricare solo fatture dal 1 Gennaio {anno_corrente}")
                            
                            blocco_attivo = pagine.get('blocco_anno_precedente', True)
                            new_blocco = st.checkbox(
                                f"🔒 Blocca fatture precedenti al {anno_corrente}",
                                value=blocco_attivo,
                                key=f"blocco_anno_{row_key}"
                            )
                            
                            if new_blocco != blocco_attivo:
                                try:
                                    updated_pagine = {
                                        'marginalita': pagine.get('marginalita', True),
                                        'workspace': pagine.get('workspace', True),
                                        'blocco_anno_precedente': new_blocco
                                    }
                                    supabase.table('users')\
                                        .update({'pagine_abilitate': updated_pagine})\
                                        .eq('id', row['user_id'])\
                                        .execute()
                                    
                                    stato = "ATTIVATO" if new_blocco else "DISATTIVATO"
                                    logger.info(f"📅 Blocco anno precedente {stato} per {row['email']}")
                                    st.success(f"✅ Blocco fatture anno precedente {stato.lower()}")
                                    _carica_stats_clienti_admin.clear()
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: {e}")
                                    logger.exception(f"Errore aggiornamento blocco_anno per {row.get('email')}")
                            
                            st.markdown("---")
                            
                            # AZIONE 3: Elimina Account Completo (2 click)
                            st.markdown("**⚠️ Zona Pericolosa**")
                            
                            if st.button("🗑️ Elimina Account", key=f"elimina_btn_{row_key}", type="secondary", use_container_width=True):
                                st.session_state[f"show_delete_dialog_{row_key}"] = True
                            
                            if st.session_state.get(f"show_delete_dialog_{row_key}", False):
                                @st.dialog("⚠️ Conferma Eliminazione Account")
                                def show_delete_confirmation():
                                    admin_email = st.session_state.user_data.get('email')
                                    if row['email'] == admin_email or row['email'] in ADMIN_EMAILS:
                                        st.error("🚫 **ERRORE**: Non puoi eliminare il tuo account admin o altri account admin!")
                                        st.info("Se vuoi rimuovere un amministratore, contatta il supporto tecnico.")
                                        if st.button("❌ Chiudi", use_container_width=True):
                                            st.session_state[f"show_delete_dialog_{row_key}"] = False
                                            st.rerun()
                                        return
                                    
                                    st.warning(
                                        f"**Stai per eliminare definitivamente:**\n\n"
                                        f"👤 **{row['email']}** ({row['ristorante']})\n\n"
                                        f"📊 **Dati che verranno eliminati:**\n"
                                        f"- Account utente\n"
                                        f"- {row['num_fatture']} fatture\n"
                                        f"- {row['num_righe']} righe prodotto\n"
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
                                        key=f"elimina_mem_{row['user_id']}",
                                        help="Se attivo, rimuove le categorizzazioni di questo cliente dal database condiviso (prodotti_master)"
                                    )
                                    
                                    if elimina_memoria:
                                        st.warning("⚠️ Verranno eliminati anche i contributi alla memoria AI condivisa")
                                    
                                    st.markdown("---")
                                    
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        if st.button("❌ Annulla", use_container_width=True):
                                            st.session_state[f"show_delete_dialog_{row_key}"] = False
                                            st.rerun()
                                    
                                    with col2:
                                        if st.button("🗑️ Sì, elimina definitivamente", type="primary", use_container_width=True):
                                            try:
                                                with st.spinner(f"Eliminazione {row['email']}..."):
                                                    user_id_to_delete = row['user_id']
                                                    email_deleted = row['email']
                                                    
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
                                                    
                                                    if not user_id_to_delete:
                                                        raise ValueError("user_id_to_delete è vuoto!")
                                                    
                                                    if email_deleted in ADMIN_EMAILS:
                                                        raise ValueError(f"Tentativo di eliminare admin: {email_deleted}")
                                                    
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
                                                    
                                                    st.session_state[f"show_delete_dialog_{row_key}"] = False
                                                    _carica_stats_clienti_admin.clear()
                                                    time.sleep(2)
                                                    st.rerun()
                                                    
                                            except Exception as e:
                                                st.error(f"❌ Errore eliminazione: {e}")
                                                logger.exception(f"Errore critico eliminazione {row['email']}")
                                
                                show_delete_confirmation()
    
    except Exception as e:
        st.error(f"❌ Errore caricamento clienti: {e}")
        logger.exception("Errore gestione clienti")
        st.code(traceback.format_exc())

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
            return [u for u in data if u.get('email') not in ADMIN_EMAILS]
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
        
        if st.button("🤖 Esegui Auto-Review", type="primary", key="btn_auto_review"):
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
                            except Exception:
                                pass
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
                st.cache_data.clear()
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
    _cliente_label = cliente_selezionato['nome_ristorante'][:20] if filtro_cliente_id else "Tutti"
    
    st.markdown(f"""
    <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#e65100; font-weight:600;">📋 Righe Totali €0</div>
            <div style="font-size:1.6rem; color:#e65100; font-weight:bold;">{len(df_zero)}</div>
        </div>
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#2e7d32; font-weight:600;">✅ Prodotti Classificati</div>
            <div style="font-size:1.6rem; color:#1b5e20; font-weight:bold;">{len(cat_sospette)}</div>
        </div>
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#1976d2; font-weight:600;">👤 Cliente</div>
            <div style="font-size:1.6rem; color:#1565c0; font-weight:bold;">{_cliente_label}</div>
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
                        st.success(f"✅ {len(result.data) if result.data else occorrenze} righe → {nuova_categoria} (+ memoria globale)")
                        invalida_cache_memoria()
                        st.cache_data.clear()
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
                        st.success(f"📝 {len(result.data) if result.data else occorrenze} righe → NOTE E DICITURE (+ memoria globale)")
                        invalida_cache_memoria()
                        st.cache_data.clear()
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
                            
                            # Salva in memoria globale con categoria confermata
                            try:
                                supabase.table('prodotti_master').upsert({
                                    'descrizione': _d,
                                    'categoria': _cat_corrente,
                                    'confidence': 'altissima',
                                    'verified': True,
                                    'classificato_da': 'review-admin',
                                    'ultima_modifica': datetime.now(timezone.utc).isoformat()
                                }, on_conflict='descrizione').execute()
                                _mem_count += 1
                            except Exception:
                                pass
                        
                        st.success(f"✅ {_ok_count} righe confermate + {_mem_count} salvate in memoria globale")
                    except Exception as _e:
                        st.error(f"Errore batch: {_e}")
                st.session_state.review_zero_selezionate = set()
                st.session_state.review_zero_cb_counter += 1
                invalida_cache_memoria()
                st.cache_data.clear()
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
                        # 💾 Salva tutte in memoria globale come diciture
                        for _d in _descs:
                            try:
                                supabase.table('prodotti_master').upsert({
                                    'descrizione': _d,
                                    'categoria': '📝 NOTE E DICITURE',
                                    'confidence': 'altissima',
                                    'verified': True,
                                    'classificato_da': 'review-admin',
                                    'ultima_modifica': datetime.now(timezone.utc).isoformat()
                                }, on_conflict='descrizione').execute()
                            except Exception:
                                pass
                        st.success(f"📝 {_ok} righe → NOTE E DICITURE (+ memoria globale)")
                    except Exception as _e:
                        st.error(f"Errore batch: {_e}")
                st.session_state.review_zero_selezionate = set()
                st.session_state.review_zero_cb_counter += 1
                invalida_cache_memoria()
                st.cache_data.clear()
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
    user_email = user.get('email', '')
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
    totale_utilizzi = int(df_memoria['volte_visto'].sum())
    chiamate_risparmiate = totale_utilizzi - len(df_memoria)
    _non_verificati_html = ""
    if is_admin and campo_verified_exists:
        non_verificati = int((~df_memoria['verified']).sum())
        _non_verificati_html = f'<div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63; border-radius:12px; padding:14px 16px; text-align:center;"><div style="font-size:0.8rem; color:#c2185b; font-weight:600;">⚠️ Da Verificare</div><div style="font-size:1.6rem; color:#880e4f; font-weight:bold;">{non_verificati}</div></div>'
    
    st.markdown(f"""
    <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#1976d2; font-weight:600;">🧠 Prodotti Totali</div>
            <div style="font-size:1.6rem; color:#1565c0; font-weight:bold;">{len(df_memoria):,}</div>
        </div>
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#2e7d32; font-weight:600;">📊 Totale Utilizzi</div>
            <div style="font-size:1.6rem; color:#1b5e20; font-weight:bold;">{totale_utilizzi:,}</div>
        </div>
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#7b1fa2; font-weight:600;">💡 API Risparmiate</div>
            <div style="font-size:1.6rem; color:#6a1b9a; font-weight:bold;">{chiamate_risparmiate:,}</div>
        </div>
        {_non_verificati_html}
    </div>
    """, unsafe_allow_html=True)
    
    # ============================================================
    # AZIONI ADMIN CRITICHE
    # ============================================================
    if is_admin:
        st.markdown("---")
        st.markdown("### ⚠️ Azioni Amministratore")
        
        col_btn1, col_btn2, col_spacer = st.columns([2, 2, 6])
        
        with col_btn1:
            if st.button("🗑️ Svuota Memoria Globale", type="secondary", use_container_width=True):
                st.session_state.show_confirm_delete_memoria = True
        
        with col_btn2:
            if st.button("🔄 Invalida Cache", type="secondary", use_container_width=True):
                invalida_cache_memoria()
                st.success("✅ Cache invalidata (Streamlit + in-memory)!")
                st.rerun()
        
        # Mostra conferma solo se bottone premuto
        if st.session_state.get('show_confirm_delete_memoria', False):
            st.warning("""
            ### ⚠️ ATTENZIONE - OPERAZIONE IRREVERSIBILE
            
            Stai per **cancellare TUTTA la memoria globale AI**:
            - ❌ Tutti i prodotti appresi verranno eliminati
            - ❌ Tutti gli utenti dovranno ri-categorizzare da zero
            - ❌ Operazione NON può essere annullata
            """)
            
            col_confirm, col_cancel, col_spacer = st.columns([1, 1, 4])
            
            with col_confirm:
                if st.button("✅ CONFERMA", type="primary", use_container_width=True):
                    try:
                        # Svuota tabella prodotti_master (elimina tutti i record)
                        result = supabase.table('prodotti_master').delete().gte('id', 0).execute()
                        
                        # Verifica
                        check = supabase.table('prodotti_master').select('id', count='exact').execute()
                        count_after = check.count if check.count else 0
                        
                        if count_after == 0:
                            st.success("✅ Memoria globale svuotata con successo!")
                            logger.warning(f"🗑️ Memoria globale svuotata da admin: {user_email}")
                            invalida_cache_memoria()
                            st.session_state.show_confirm_delete_memoria = False
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"⚠️ Operazione parziale: rimasti {count_after} record")
                    except Exception as e:
                        st.error(f"❌ Errore: {str(e)}")
                        logger.error(f"Errore svuotamento memoria: {e}")
            
            with col_cancel:
                if st.button("❌ ANNULLA", use_container_width=True):
                    st.session_state.show_confirm_delete_memoria = False
                    st.rerun()
    
    st.markdown("---")
    
    # ============================================================
    # FILTRI
    # ============================================================
    st.markdown("### 🔍 Filtri")
    
    col_search, col_cat, col_verified, col_reset = st.columns([3, 2, 2, 1])
    
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
                ["Da Verificare", "Già Verificate", "Righe €0 Verificate", "Tutte"],
                key="filtro_verified"
            )
        else:
            filtro_verified = "Tutte"
    
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset", key="reset_filtri"):
            st.session_state.search_memoria = ""
            st.session_state.filtro_cat = "Tutte"
            if is_admin:
                st.session_state.filtro_verified = "Da Verificare"
            st.rerun()
    
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
    
    # ORDINA ALFABETICAMENTE per descrizione
    df_filtrato = df_filtrato.sort_values('descrizione').reset_index(drop=True)
    
    # ============================================================
    # INFO SEMPLICE + PAGINAZIONE
    # ============================================================
    
    # Paginazione per performance (50 righe per pagina)
    RIGHE_PER_PAGINA = 50
    totale_righe = len(df_filtrato)
    
    # Inizializza pagina corrente
    if 'pagina_memoria' not in st.session_state:
        st.session_state.pagina_memoria = 0
    
    num_pagine = (totale_righe + RIGHE_PER_PAGINA - 1) // RIGHE_PER_PAGINA
    
    col_info, col_pag = st.columns([2, 1])
    
    with col_info:
        st.caption(f"📊 Mostrando {totale_righe} prodotti")
    
    with col_pag:
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
    
    if df_filtrato.empty:
        st.warning("⚠️ Nessun prodotto trovato con questi filtri")
        return
    
    # Applica paginazione
    inizio = st.session_state.pagina_memoria * RIGHE_PER_PAGINA
    fine = min(inizio + RIGHE_PER_PAGINA, totale_righe)
    df_pagina = df_filtrato.iloc[inizio:fine]
    
    if num_pagine > 1:
        st.caption(f"Righe {inizio + 1}-{fine} di {totale_righe}")
    
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
    
    st.markdown("---")
    
    # ============================================================
    # TABELLA - TUTTE LE RIGHE FILTRATE
    # ============================================================
    num_modifiche = len(st.session_state.modifiche_memoria)
    
    if num_modifiche > 0:
        st.markdown(f"### 📋 Prodotti | 🔸 **{num_modifiche} modifiche pendenti**")
    else:
        st.markdown("### 📋 Prodotti")
    
    # HEADER TABELLA (con checkbox solo se admin, campo exists e filtro da verificare)
    mostra_checkbox = is_admin and campo_verified_exists and filtro_verified == "Da Verificare"
    
    if mostra_checkbox:
        # Bottoni per selezione massiva PRIMA della tabella
        st.markdown("#### Selezione Rapida")
        col_sel_all, col_desel_all = st.columns(2)
        
        with col_sel_all:
            righe_pagina_ids = set(df_pagina['id'].tolist())
            if st.button(f"☑️ Seleziona Tutte ({len(righe_pagina_ids)} righe)", use_container_width=True, key="btn_select_all"):
                st.session_state.righe_selezionate.update(righe_pagina_ids)
                st.session_state.checkbox_refresh_counter += 1  # Forza refresh checkbox
                st.rerun()
        
        with col_desel_all:
            if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_deselect_all"):
                st.session_state.righe_selezionate.difference_update(righe_pagina_ids)
                st.session_state.checkbox_refresh_counter += 1  # Forza refresh checkbox
                st.rerun()
        
        st.markdown("---")
        col_desc, col_cat, col_azioni = st.columns([4, 2.5, 1])
    else:
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
            if not verified:
                st.markdown(f"⚠️ `{desc_short}`", help=f"Testo completo: {descrizione}")
            else:
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

# Chiama la funzione unificata
if tab3:
    tab_memoria_globale_unificata()

# ============================================================
# TAB 4: MEMORIA CLIENTI (prodotti_utente)
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
    <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#1976d2; font-weight:600;">📝 Voci in Memoria</div>
            <div style="font-size:1.6rem; color:#1565c0; font-weight:bold;">{len(df_personalizzazioni):,}</div>
        </div>
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#2e7d32; font-weight:600;">📊 Totale Utilizzi</div>
            <div style="font-size:1.6rem; color:#1b5e20; font-weight:bold;">{_tot_utilizzi_clienti:,}</div>
        </div>
        <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800; border-radius:12px; padding:14px 16px; text-align:center;">
            <div style="font-size:0.8rem; color:#e65100; font-weight:600;">👥 Clienti Attivi</div>
            <div style="font-size:1.6rem; color:#e65100; font-weight:bold;">{_clienti_unici}</div>
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
    col_check, col_desc, col_cat = st.columns([0.5, 4, 2])
    
    with col_desc:
        st.markdown("**Descrizione**")
    
    with col_cat:
        st.markdown("**Categoria**")
    
    st.markdown("---")
    
    # CICLO RIGHE
    for idx, row in df_pagina.iterrows():
        row_id = row['id']
        descrizione = row['descrizione']
        categoria_corrente = row['categoria']
        volte_visto = row['volte_visto']
        
        col_check, col_desc, col_cat = st.columns([0.5, 4, 2])
        
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
        
        # CATEGORIA (solo display, no editing)
        with col_cat:
            st.markdown(f"**{categoria_corrente}**")
        
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

# Chiama la funzione unificata
if tab4:
    tab_personalizzazioni_clienti()

# ============================================================
# TAB 5: VERIFICA INTEGRITÀ DATABASE (era TAB 4)
# ============================================================

if tab5:
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
            return [u for u in data if u.get('email') not in ADMIN_EMAILS]
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
            .select('user_email, file_name, created_at')\
            .eq('status', 'DUPLICATE_SKIPPED')\
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
            df_dupl = df_dupl.rename(columns={
                'user_email': 'cliente',
                'file_name': 'file',
                'created_at': 'data tentativo'
            })
            df_dupl['data tentativo'] = pd.to_datetime(df_dupl['data tentativo']).dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(df_dupl, use_container_width=True, hide_index=True)
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
                        'prezzi_anomali': [],
                        'quantita_anomale': [],
                        'descrizioni_vuote': [],
                        'totali_errati': []
                    }
                    
                    # 1-5. Controlli principali in singolo pass (più veloce su dataset grandi)
                    oggi = datetime.now().date()
                    for _, row in df.iterrows():
                        fornitore = row.get('fornitore', 'N/A')
                        data_doc = row.get('data_documento', 'N/A')
                        descrizione = str(row.get('descrizione', 'N/A') or 'N/A')
                        desc_short = descrizione[:50]

                        # 1) Date invalide
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
                                'problema': "Data non valida"
                            })

                        # Normalizzazioni numeriche
                        try:
                            prezzo = float(row.get('prezzo_unitario', 0) or 0)
                        except Exception:
                            prezzo = 0.0

                        try:
                            quantita = float(row.get('quantita', 0) or 0)
                        except Exception:
                            quantita = 0.0

                        try:
                            totale = float(row.get('totale_riga', 0) or 0)
                        except Exception:
                            totale = 0.0

                        # 2) Prezzi anomali
                        if prezzo < 0:
                            problemi['prezzi_anomali'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'valore': f"€ {prezzo:.2f}",
                                'problema': "Prezzo negativo"
                            })
                        elif prezzo > 10000:
                            problemi['prezzi_anomali'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'valore': f"€ {prezzo:.2f}",
                                'problema': "Prezzo molto alto (> €10.000)"
                            })

                        # 3) Quantità anomale
                        if quantita < 0:
                            problemi['quantita_anomale'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'valore': quantita,
                                'problema': "Quantità negativa"
                            })
                        elif quantita > 10000:
                            problemi['quantita_anomale'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'valore': quantita,
                                'problema': "Quantità molto alta (> 10.000)"
                            })

                        # 4) Descrizioni vuote o troppo corte
                        desc_trim = descrizione.strip()
                        if len(desc_trim) < 3:
                            problemi['descrizioni_vuote'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_trim if desc_trim else '(vuota)',
                                'problema': "Descrizione mancante o troppo corta"
                            })

                        # 5) Totali non corrispondenti (prezzo × quantità ≠ totale)
                        calcolato = prezzo * quantita
                        if abs(calcolato - totale) > 0.02:
                            problemi['totali_errati'].append({
                                'fornitore': fornitore,
                                'data': data_doc,
                                'descrizione': desc_short,
                                'calcolato': f"€ {calcolato:.2f}",
                                'salvato': f"€ {totale:.2f}",
                                'problema': f"Differenza: € {abs(calcolato - totale):.2f}"
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
                            _n_prezzi = len(problemi['prezzi_anomali'])
                            _n_qta = len(problemi['quantita_anomale'])
                            _n_desc = len(problemi['descrizioni_vuote'])
                            _n_totali = len(problemi['totali_errati'])
                            
                            st.markdown(f"""
                            <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
                                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800; border-radius:12px; padding:14px 16px; text-align:center;">
                                    <div style="font-size:0.8rem; color:#e65100; font-weight:600;">📅 Date Invalide</div>
                                    <div style="font-size:1.6rem; color:#e65100; font-weight:bold;">{_n_date}</div>
                                </div>
                                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63; border-radius:12px; padding:14px 16px; text-align:center;">
                                    <div style="font-size:0.8rem; color:#c2185b; font-weight:600;">💰 Prezzi Anomali</div>
                                    <div style="font-size:1.6rem; color:#880e4f; font-weight:bold;">{_n_prezzi}</div>
                                </div>
                                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0; border-radius:12px; padding:14px 16px; text-align:center;">
                                    <div style="font-size:0.8rem; color:#7b1fa2; font-weight:600;">📦 Quantità Anomale</div>
                                    <div style="font-size:1.6rem; color:#6a1b9a; font-weight:bold;">{_n_qta}</div>
                                </div>
                                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3; border-radius:12px; padding:14px 16px; text-align:center;">
                                    <div style="font-size:0.8rem; color:#1976d2; font-weight:600;">📝 Descrizioni Vuote</div>
                                    <div style="font-size:1.6rem; color:#1565c0; font-weight:bold;">{_n_desc}</div>
                                </div>
                                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e0f7fa,#b2ebf2); border:2px solid #00bcd4; border-radius:12px; padding:14px 16px; text-align:center;">
                                    <div style="font-size:0.8rem; color:#006064; font-weight:600;">🧮 Totali Errati</div>
                                    <div style="font-size:1.6rem; color:#00838f; font-weight:bold;">{_n_totali}</div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            st.markdown("---")
                            
                            # Mostra dettagli per ogni categoria
                            if len(problemi['date_invalide']) > 0:
                                st.markdown("**📅 Date Invalide**")
                                st.dataframe(pd.DataFrame(problemi['date_invalide']), use_container_width=True, hide_index=True)
                            
                            if len(problemi['prezzi_anomali']) > 0:
                                st.markdown("**💰 Prezzi Anomali**")
                                st.dataframe(pd.DataFrame(problemi['prezzi_anomali']), use_container_width=True, hide_index=True)
                            
                            if len(problemi['quantita_anomale']) > 0:
                                st.markdown("**📦 Quantità Anomale**")
                                st.dataframe(pd.DataFrame(problemi['quantita_anomale']), use_container_width=True, hide_index=True)
                            
                            if len(problemi['descrizioni_vuote']) > 0:
                                st.markdown("**📝 Descrizioni Vuote**")
                                st.dataframe(pd.DataFrame(problemi['descrizioni_vuote']), use_container_width=True, hide_index=True)
                            
                            if len(problemi['totali_errati']) > 0:
                                st.markdown("**🧮 Totali Errati**")
                                st.dataframe(pd.DataFrame(problemi['totali_errati']), use_container_width=True, hide_index=True)
                        

            
            except Exception as e:
                st.error(f"❌ Errore durante la verifica: {str(e)}")
                with st.expander("🔍 Dettagli Tecnici"):
                    st.code(traceback.format_exc())


# ============================================================
# TAB 6: COSTI AI PER CLIENTE (era TAB 5)
# ============================================================

if tab6:
    st.markdown("## 💳 Costi AI per Cliente")
    st.caption("Monitoraggio utilizzo e costi OpenAI per estrazione PDF e categorizzazione prodotti")
    
    try:
        # Carica dati costi AI usando funzione RPC
        response = supabase.rpc('get_ai_costs_summary').execute()
        
        if not response.data or len(response.data) == 0:
            st.info("📊 Nessun utilizzo AI registrato. I costi verranno tracciati automaticamente quando i clienti caricano PDF o immagini.")
        else:
            df_costs = pd.DataFrame(response.data)
            
            # ⚠️ BACKWARDS COMPATIBILITY: Aggiungi colonna se non esiste (pre-migrazione)
            if 'ai_categorization_count' not in df_costs.columns:
                st.warning("⚠️ **Migrazione database necessaria!** Esegui `migrations/014_add_ai_cost_tracking.sql` per abilitare tracking categorizzazioni.")
                df_costs['ai_categorization_count'] = 0
                df_costs['ai_avg_cost_per_operation'] = df_costs.get('ai_avg_cost_per_pdf', 0)
            
            # ============================================================
            # STATISTICHE GENERALI (CARD STILIZZATE)
            # ============================================================
            st.markdown("### 📊 Riepilogo Globale")
            
            totale_costi = df_costs['ai_cost_total'].sum()
            totale_pdf = int(df_costs['ai_pdf_count'].sum())
            totale_categorization = int(df_costs['ai_categorization_count'].sum())
            totale_operazioni = totale_pdf + totale_categorization
            costo_medio = totale_costi / totale_operazioni if totale_operazioni > 0 else 0
            clienti_attivi = len(df_costs[(df_costs['ai_pdf_count'] > 0) | (df_costs['ai_categorization_count'] > 0)])
            
            st.markdown(f"""
            <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fce4ec,#f8bbd0); border:2px solid #e91e63; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#c2185b; font-weight:600;">💰 Totale Costi</div>
                    <div style="font-size:1.6rem; color:#880e4f; font-weight:bold;">${totale_costi:.2f}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e3f2fd,#bbdefb); border:2px solid #2196f3; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#1976d2; font-weight:600;">📄 PDF Processati</div>
                    <div style="font-size:1.6rem; color:#1565c0; font-weight:bold;">{totale_pdf:,}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#f3e5f5,#e1bee7); border:2px solid #9c27b0; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#7b1fa2; font-weight:600;">🧠 Categorizzazioni</div>
                    <div style="font-size:1.6rem; color:#6a1b9a; font-weight:bold;">{totale_categorization:,}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#fff3e0,#ffe0b2); border:2px solid #ff9800; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#e65100; font-weight:600;">📊 Costo Medio</div>
                    <div style="font-size:1.6rem; color:#e65100; font-weight:bold;">${costo_medio:.4f}</div>
                </div>
                <div style="flex:1; min-width:130px; background:linear-gradient(135deg,#e8f5e9,#c8e6c9); border:2px solid #4caf50; border-radius:12px; padding:14px 16px; text-align:center;">
                    <div style="font-size:0.8rem; color:#2e7d32; font-weight:600;">👥 Clienti Attivi</div>
                    <div style="font-size:1.6rem; color:#1b5e20; font-weight:bold;">{clienti_attivi}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # ============================================================
            # TABELLA DETTAGLIO PER CLIENTE
            # ============================================================
            st.markdown("### 📋 Dettaglio per Cliente")
            
            # Prepara DataFrame per visualizzazione
            df_display = df_costs[(df_costs['ai_pdf_count'] > 0) | (df_costs['ai_categorization_count'] > 0)].copy()
            
            if len(df_display) > 0:
                df_display['Cliente'] = df_display['nome_ristorante']
                df_display['Ragione Sociale'] = df_display['ragione_sociale'].fillna('-')
                df_display['PDF'] = df_display['ai_pdf_count'].astype(int)
                df_display['Categorizzazioni'] = df_display['ai_categorization_count'].astype(int)
                df_display['Tot Operazioni'] = (df_display['ai_pdf_count'] + df_display['ai_categorization_count']).astype(int)
                df_display['Costo Totale'] = df_display['ai_cost_total'].apply(lambda x: f"${x:.4f}")
                df_display['Costo/Op'] = df_display['ai_avg_cost_per_operation'].apply(lambda x: f"${x:.4f}")
                df_display['Ultimo Uso'] = pd.to_datetime(df_display['ai_last_usage']).dt.strftime('%Y-%m-%d %H:%M')
                
                # Mostra tabella
                st.dataframe(
                    df_display[['Cliente', 'Ragione Sociale', 'PDF', 'Categorizzazioni', 'Tot Operazioni', 'Costo Totale', 'Costo/Op', 'Ultimo Uso']],
                    width='stretch',
                    hide_index=True
                )
                
                # ============================================================
                # EXPORT CSV
                # ============================================================
                st.markdown("---")
                col_export, col_spacer = st.columns([2, 8])
                
                with col_export:
                    csv_data = df_display[['Cliente', 'Ragione Sociale', 'PDF', 'Categorizzazioni', 'Tot Operazioni', 'Costo Totale', 'Costo/Op', 'Ultimo Uso']].to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Esporta CSV",
                        data=csv_data,
                        file_name=f"costi_ai_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                # ============================================================
                # GRAFICO TOP CLIENTI
                # ============================================================
                st.markdown("---")
                st.markdown("### 📈 Top 10 Clienti per Costo")
                
                df_top = df_display.nlargest(10, 'ai_cost_total')
                
                fig = px.bar(
                    df_top,
                    x='Cliente',
                    y='ai_cost_total',
                    title='Costi AI per Cliente (Top 10)',
                    labels={'ai_cost_total': 'Costo ($)', 'Cliente': ''},
                    color='ai_cost_total',
                    color_continuous_scale='Blues'
                )
                
                fig.update_layout(
                    showlegend=False,
                    xaxis_tickangle=-45,
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # ============================================================
                # INFO E NOTE
                # ============================================================
                st.markdown("---")
                st.info("""
                **ℹ️ Note:**
                - I costi sono calcolati in base al modello **GPT-4o-mini** (sia Vision che Text)
                - **PDF Vision**: ~$0.02-0.04 per documento (dipende da complessità e numero prodotti)
                - **Categorizzazione**: ~$0.001-0.005 per batch (molto economico)
                - I file **XML sono gratuiti** (parsing locale, nessun costo AI)
                - Per ridurre i costi, incoraggia i clienti a usare XML quando possibile
                - La categorizzazione AI viene usata solo per prodotti "Da Classificare"
                """)
            else:
                st.warning("Nessun cliente ha ancora utilizzato funzioni AI")
    
    except Exception as e:
        st.error(f"❌ Errore caricamento dati: {str(e)}")
        logger.exception("Errore nel tab Costi AI")
        with st.expander("🔍 Dettagli Errore"):
            st.code(str(e))
