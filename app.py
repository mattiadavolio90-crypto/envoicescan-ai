import streamlit as st
import pandas as pd
import os
import html as _html
from collections import defaultdict

import io
import time

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

# Import costanti da modulo separato
from config.constants import (
    ADMIN_EMAILS,
    MAX_RIGHE_GLOBALE,
    SESSION_INACTIVITY_HOURS as _SESSION_INACTIVITY_HOURS,
    LAST_SEEN_WRITE_THROTTLE_SECONDS as _LAST_SEEN_WRITE_THROTTLE_SECONDS,
)

from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ui_helpers import load_css, load_js

# Import services
from services.ai_service import mostra_loading_ai

from services.db_service import (
    carica_e_prepara_dataframe,
    get_fatture_stats,
    clear_fatture_cache,
    get_fatture_cestino,
)

from components.dashboard_renderer import mostra_statistiche
from components.upload_panel import render_upload_panel
from controllers.upload_controller import (
    show_upload_messages,
    process_uploaded_files,
    render_competenza_review,
)

# ============================================================
# INTERFACCIA PRINCIPALE CON CACHING OTTIMIZZATO
# ============================================================
from components.notifications_panel import (
    refresh_auto_invoice_notice,
    build_operational_notifications,
    ingest_notifications_to_inbox,
    show_operational_toasts,
)


# [DEBUG] Helper snapshot session_state — attivo solo con DEBUG_MODE=1
def _debug_session_snap(label: str) -> None:
    if os.getenv("DEBUG_MODE") != "1":
        return
    keys_of_interest = [
        "force_reload", "rerun_guard", "ristorante_id",
        "files_processati_sessione", "hide_uploader",
        "ultimo_upload_ids", "last_upload_summary"
    ]
    snap = {k: st.session_state.get(k) for k in keys_of_interest}
    logger.debug(f"[SESSION SNAP — {label}] {snap}")
# ============================================================

# AutoInvoiceNotice spostata in pages/5_notifiche_e_gestione.py (Step 3)


# ============================================
# FUNZIONE CALCOLO PREZZO STANDARDIZZATO
# ============================================

st.set_page_config(
    page_title="ONEFLUX",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# ============================================================
# GUARDIA ANTI-LOOP: Limita rerun consecutivi (safety net)
# Usa finestra sliding di 60s per distinguere loop infiniti da flussi legittimi
# ============================================================
_rerun_count = st.session_state.get('_rerun_guard', 0)
_rerun_last_reset = st.session_state.get('_rerun_last_reset', time.time())
# Auto-reset counter ogni 60 secondi (finestra sliding)
if (time.time() - _rerun_last_reset) > 60:
    _rerun_count = 0
    st.session_state._rerun_last_reset = time.time()
if _rerun_count > 15:
    import logging as _logging_guard
    _logging_guard.getLogger('fci_app').critical(f"🚨 RERUN LOOP DETECTED ({_rerun_count} consecutivi in <60s) - reset forzato")
    st.session_state._rerun_guard = 0
    st.session_state._rerun_last_reset = time.time()
    st.session_state.force_reload = False
    st.error("⚠️ Rilevato loop di aggiornamento. La pagina è stata stabilizzata.")
    st.stop()
st.session_state._rerun_guard = _rerun_count + 1

# CSS + JS branding (caricati da file statici)
load_css('design_tokens.css')
load_css('branding.css')
load_css('layout.css')
load_css('responsive.css')
load_css('common.css')
load_js('branding.js')

# ============================================================
# SIDEBAR: NASCONDI SUBITO SE NON LOGGATO (anti-flash)
# Deve essere DOPO i load_css per sovrascrivere branding.css
# ============================================================
if not st.session_state.get('logged_in', False):
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()


# ============================================================
# 🔒 SISTEMA AUTENTICAZIONE CON RECUPERO PASSWORD
# ============================================================
from supabase import Client
from datetime import datetime, timedelta, timezone
import uuid as _uuid
import secrets as _secrets
import logging
import sys

# Logger con fallback cloud-compatible
logger = logging.getLogger('fci_app')
if not logger.handlers:
    try:
        # Prova filesystem locale (sviluppo)
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler('debug.log', maxBytes=50_000_000, backupCount=10, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.info("✅ Logging su file locale attivo")
    except (OSError, PermissionError) as e:
        # Fallback: stdout per cloud read-only
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info("✅ Logging su stdout attivo (cloud mode)")


# ============================================================
# INIZIALIZZAZIONE SUPABASE CON CONNECTION POOLING
# ============================================================
# Usa singleton centralizzato da services/__init__.py
from services import get_supabase_client

# Inizializza client globale (singleton)
try:
    supabase: Client = get_supabase_client()
except Exception as e:
    logger.exception("Connessione Supabase fallita")
    st.error("⛔ Servizio temporaneamente non disponibile. Riprova tra qualche minuto.")
    st.stop()


# Inizializza logged_in se non esiste
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

from controllers.auth_controller import (
    init_cookie_manager,
    handle_impersonation_cookie_set,
    check_impersonation_timeout,
    handle_force_logout,
    restore_session_from_cookie,
    update_last_seen_throttled,
    handle_reset_token_page,
    check_login_gate,
    restore_admin_flags,
    restore_impersonation_from_cookie,
    check_trial_or_expire,
    render_impersonation_banner,
)
from controllers.session_controller import init_ristoranti_session

# ============================================================
# FLUSSO AUTENTICAZIONE (controllers/auth_controller.py)
# ============================================================
_cookie_manager = init_cookie_manager()

handle_impersonation_cookie_set(_cookie_manager, supabase)
check_impersonation_timeout(_cookie_manager)

handle_force_logout(supabase)
restore_session_from_cookie(_cookie_manager, supabase, _SESSION_INACTIVITY_HOURS, clear_fatture_cache)

if not st.session_state.get('logged_in', False):
    st.session_state._rerun_guard = 0

update_last_seen_throttled(supabase, _LAST_SEEN_WRITE_THROTTLE_SECONDS)


handle_reset_token_page(supabase)  # st.stop() se reset_token presente
# ============================================================
# HELPER FUNCTIONS
# ============================================================

# is_admin_or_impersonating() → unica definizione in utils.app_controllers

# ============================================================
# GATE LOGIN + UTENTE (controllers/auth_controller.py)
# ============================================================
check_login_gate(supabase, _cookie_manager)  # st.stop() se non loggato

user = st.session_state.user_data


restore_admin_flags()
restore_impersonation_from_cookie(_cookie_manager, supabase)
user = st.session_state.user_data  # refresh dopo eventuale ripristino impersonazione


# ============================================
# RISTORANTI (controllers/session_controller.py)
# ============================================
init_ristoranti_session(supabase, user)


# ============================================
# ADMIN PURO: ACCESSO APP SENZA RESTRIZIONI
# ============================================
if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
    logger.info(f"👨‍💼 Admin user_id={user.get('id')} in modalità unrestricted su app.py")
elif st.session_state.get('logged_in', False) and st.session_state.get('ristorante_id'):
    if not st.session_state.get('_gfn_auto_redirect_done', False):
        st.session_state._gfn_auto_redirect_done = True
        st.switch_page("pages/5_notifiche_e_gestione.py")

# ============================================================
# TRIAL + BANNER IMPERSONAZIONE (controllers/auth_controller.py)
# ============================================================
check_trial_or_expire(supabase)

render_impersonation_banner(supabase, _cookie_manager)


# ============================================
# SIDEBAR CON NAVIGAZIONE E INFO
# ============================================
render_sidebar(user)


# ============================================
# HEADER
# ============================================

render_oh_yeah_header()

# ============================================
# DEBUG LOGGING: session user_id vs DB
# ============================================
_sess_uid = st.session_state.get('user_data', {}).get('id', 'N/A')
_sess_rid = st.session_state.get('ristorante_id', 'N/A')
_sess_email = st.session_state.get('user_data', {}).get('email', 'N/A')
logger.debug(
    f"[SESSION DEBUG] email={_sess_email} user_id={_sess_uid} "
    f"ristorante_id={_sess_rid} force_reload={st.session_state.get('force_reload')}"
)

st.session_state.pop('show_welcome', None)

_is_admin_session = (_sess_email or '').strip().lower() in ADMIN_EMAILS

# ============================================================
# NOTIFICHE: auto_invoice_notice + operational
# (components/notifications_panel.py)
# ============================================================
if not _is_admin_session:
    refresh_auto_invoice_notice(supabase, st.session_state.get('user_data', {}))
auto_notice = st.session_state.get('auto_invoice_notice')

operational_notifications = []
if not _is_admin_session:
    _user_id_notifications = st.session_state.get('user_data', {}).get('id')
    _ristorante_id_notifications = st.session_state.get('ristorante_id')
    _upload_ctx = st.session_state.get('last_upload_notification_context') or {}
    _is_impersonating = st.session_state.get('impersonating', False)
    operational_notifications = build_operational_notifications(
        supabase=supabase,
        user_id=_user_id_notifications,
        ristorante_id=_ristorante_id_notifications,
        is_impersonating=_is_impersonating,
        upload_ctx=_upload_ctx,
    )
    ingest_notifications_to_inbox(
        operational_notifications, supabase, _user_id_notifications, _ristorante_id_notifications
    )

# Stato file gestiti (salvati/rifiutati) — persistente durante la sessione
if 'auto_invoice_handled' not in st.session_state:
    st.session_state.auto_invoice_handled = set()

st.markdown("""
<h2 class="page-title">
    🧠 <span class="page-title-gradient">Analisi Fatture</span>
</h2>
<div class="legal-note">
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</div>
""", unsafe_allow_html=True)

# ============================================
# TRIAL BANNER
# ============================================
_tb = st.session_state.get('trial_info', {})
if _tb.get('is_trial') and not st.session_state.get('impersonating', False):
    _tb_days = _tb.get('days_left', 0)
    _tb_color = '#dc2626' if _tb_days <= 2 else '#d97706'
    st.markdown(f"""
<div class="trial-banner" style="border-color:{_tb_color};">
    <span class="trial-banner__icon">⏳</span>
    <div>
        <strong class="trial-banner__title" style="color:{_tb_color};">
            Prova gratuita attiva &mdash; Rimangono {_tb_days} giorni
        </strong><br>
        <span class="trial-banner__body">
            Accesso alle fatture del mese in corso e del mese precedente.
            Upload: max 50 file, solo XML/P7M. Export Excel disponibile anche durante la prova.
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# Recupera email e nome ristorante intelligente
user_email = (user.get('email') or user.get('Email') or user.get('user_email') or 
              (st.session_state.user_data.get('email') if st.session_state.user_data else None) or 
              'Email non disponibile')

# 🎯 LOGICA INTELLIGENTE: Single vs Multi-Ristorante (usa dati già in sessione, zero query DB)
ristoranti_session = st.session_state.get('ristoranti', [])
num_ristoranti = len(ristoranti_session)

if num_ristoranti == 0:
    nome_ristorante = "Nessun Ristorante"
elif num_ristoranti == 1:
    nome_ristorante = ristoranti_session[0].get('nome_ristorante', 'Ristorante')
else:
    nome_ristorante = "Multi-Ristorante"

# Nota legale spostata nel header accanto al titolo

# ============================================
# DROPDOWN MULTI-RISTORANTE
# ============================================
# Mostra dropdown per clienti NON admin con più ristoranti
if (user.get('email') or '').strip().lower() not in ADMIN_EMAILS:
    ristoranti = st.session_state.get('ristoranti', [])
    
    if len(ristoranti) > 1:
        st.markdown('<h3 class="section-heading">🏢 Seleziona Ristorante da Gestire</h3>', unsafe_allow_html=True)
        
        # Trova indice ristorante corrente
        current_id = st.session_state.get('ristorante_id')
        current_idx = 0
        for idx, r in enumerate(ristoranti):
            if r['id'] == current_id:
                current_idx = idx
                break
        
        # Dropdown ristorante
        ristorante_idx = st.selectbox(
            "🏪 Scegli ristorante:",
            range(len(ristoranti)),
            index=current_idx,
            format_func=lambda i: f"{ristoranti[i]['nome_ristorante']}",
            key="dropdown_ristorante_main",
            help="Seleziona il ristorante per cui vuoi caricare e analizzare fatture"
        )
        
        # Info ristorante sotto il dropdown, su tutta la larghezza
        rag_soc = _html.escape(ristoranti[ristorante_idx].get('ragione_sociale') or 'N/A')
        nome_r = _html.escape(ristoranti[ristorante_idx]['nome_ristorante'])
        piva_r = _html.escape(ristoranti[ristorante_idx]['partita_iva'])
        st.markdown(f"""
        <div class="ristorante-info-bar">
            ✅ <strong>Attivo</strong> &nbsp;·&nbsp; 📋 {nome_r} &nbsp;·&nbsp; 🏢 IT{piva_r} &nbsp;·&nbsp; 📄 {rag_soc}
        </div>
        """, unsafe_allow_html=True)
        
        # Aggiorna sessione se cambiato
        selected_ristorante = ristoranti[ristorante_idx]
        if st.session_state.get('ristorante_id') != selected_ristorante['id']:
            st.session_state.ristorante_id = selected_ristorante['id']
            st.session_state.partita_iva = selected_ristorante['partita_iva']
            st.session_state.nome_ristorante = selected_ristorante['nome_ristorante']
            
            # 🧹 Pulizia cache contesto ristorante precedente
            if 'files_processati_sessione' in st.session_state:
                st.session_state.files_processati_sessione = set()
            if 'files_con_errori' in st.session_state:
                st.session_state.files_con_errori = set()
            # 🧹 Pulizia chiavi stale da ristorante precedente
            for _stale_key in ['righe_ai_appena_categorizzate', 'righe_keyword_appena_categorizzate',
                               'righe_memoria_appena_categorizzate', 'righe_modificate_manualmente',
                               'force_reload', 'force_empty_until_upload',
                               'files_errori_report', 'last_upload_summary', 'last_upload_notification_context', 'ultimo_upload_ids',
                               'ingredienti_temp', 'ricetta_edit_mode', 'ricetta_edit_data',
                               '_fonte_pm_cache',
                               # 🧹 RESET: Cache pagina gestione_documenti (gfn_* namespace)
                               'gfn_documenti_cache_version', 'gfn_fornitori_cache_version',
                               'gfn_filtro_scadenziario', 'gfn_giorni_imminenti', 'gfn_ordine_scadenza',
                               # 🧹 RESET: AutoInvoiceNotice (Step 3)
                               'auto_invoice_handled', 'auto_invoice_notice_dismissed', 'auto_invoice_notice_toast_shown',
                               '_auto_invoice_notice_refresh_ts',
                               # 🧹 RESET: Cache notifiche operative DB-heavy
                               '_operational_notifications_refresh_ts', '_operational_notifications_db',
                               '_operational_notifications_price_threshold', '_operational_notifications_cache_key']:
                st.session_state.pop(_stale_key, None)
            clear_fatture_cache()
            
            # 💾 Salva l'ultimo ristorante usato nel DB per ripristinarlo alla prossima sessione
            try:
                supabase.table('users').update(
                    {'ultimo_ristorante_id': selected_ristorante['id']}
                ).eq('id', user.get('id')).execute()
            except Exception as _e:
                logger.warning(f"Errore salvataggio ultimo_ristorante_id: {_e}")
            
            logger.info(f"🔄 Ristorante cambiato: rist_id={selected_ristorante['id']}")
            # [DEBUG]
            _debug_session_snap("CAMBIO_RISTORANTE")
            st.rerun()
        
        st.markdown("---")
    
    elif len(ristoranti) == 1:
        # Singolo ristorante: mostra solo info compatta
        st.info(f"🏪 **Ristorante:** {ristoranti[0]['nome_ristorante']} | 📋 **P.IVA:** `IT{ristoranti[0]['partita_iva']}`")

    # Toast operativi (non-UI expander — solo toast silenzioso una volta per sessione)
    if not _is_admin_session:
        show_operational_toasts(operational_notifications)

    # AutoInvoiceNotice spostata in pages/5_notifiche_e_gestione.py (Step 3)

    st.markdown("---")

# ============================================================
# API KEY OPENAI
# ============================================================
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    logger.exception("API Key OpenAI non trovata o accesso a st.secrets fallito")
    st.error("⛔ Configurazione AI non disponibile. Contatta l'amministratore.")
    st.stop()

# ============================================================
# INTERFACCIA PRINCIPALE CON CACHING OTTIMIZZATO
# ============================================================


if 'timestamp_ultimo_caricamento' not in st.session_state:
    st.session_state.timestamp_ultimo_caricamento = time.time()


# 🔒 IMPORTANTE: user_id per cache isolata (multi-tenancy)
try:
    user_id = st.session_state.user_data["id"]
except (KeyError, TypeError, AttributeError):
    logger.critical("❌ user_data corrotto o mancante campo 'id' - FORZA LOGOUT")
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.error("⚠️ Sessione invalida. Effettua nuovamente il login.")
    st.rerun()

# ⚡ SINGLE DATA LOAD: Carica una sola volta, riusa per Gestione Fatture + Dashboard
force_refresh = st.session_state.get('force_reload', False)
if force_refresh:
    st.session_state.force_reload = False
    logger.info("🔄 FORCE RELOAD attivato dopo categorizzazione AI")

# [DEBUG]
_debug_session_snap("PRE_LOAD")

with st.spinner("⏳ Caricamento dati..."):
    df_cache = carica_e_prepara_dataframe(user_id, force_refresh=force_refresh, ristorante_id=st.session_state.get('ristorante_id'))

# Inizializzazione safe: get_fatture_stats viene ridefinito dentro l'expander
# ma potrebbe non essere raggiunto se df_cache è vuoto.
stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}

# === GESTIONE VISIBILITÀ UPLOADER ===
if st.session_state.get("hide_uploader", False):
    st.warning("⚠️ Hai eliminato tutte le fatture.")
    if st.button("🔄 Ricarica Pagina", key="refresh_page_btn"):
        st.session_state.hide_uploader = False
        st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
        st.components.v1.html(
            """
            <script>
            window.parent.location.reload();
            </script>
            """,
            height=0
        )
    uploaded_files = []  # Nessun file da elaborare in questo stato
else:
    fatture_cestino_cache = []
    try:
        fatture_cestino_cache = get_fatture_cestino(
            user_id,
            ristorante_id=st.session_state.get('ristorante_id')
        )
    except Exception as e:
        logger.error(f"Errore caricamento cestino fatture: {e}")
        fatture_cestino_cache = []

    mostra_expander_gestione = (not df_cache.empty) or bool(fatture_cestino_cache)

    if mostra_expander_gestione:
        try:
            stats_db = get_fatture_stats(user_id, st.session_state.get('ristorante_id'))
        except Exception as e:
            logger.error(f"Errore get_fatture_stats: {e}")
            stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}

    # ============================================================
    # CHECK LIMITE RIGHE GLOBALE (STEP 1 - Performance)
    # ============================================================
    # Configurazione limiti (importati da constants.py)
    
    # user_id già definito sopra (post-login check)
    # stats_db già calcolato nel box statistiche sopra (evita doppia query)
    righe_totali = stats_db.get('num_righe', 0)
    
    # Controllo prima elaborazione
    if righe_totali >= MAX_RIGHE_GLOBALE:
        st.error(f"⚠️ Limite database raggiunto ({righe_totali:,} righe). Elimina vecchie fatture.")
        st.warning("Usa 'Gestione Fatture Caricate' sopra per eliminare")
        st.stop()  # Blocca file_uploader
    
    # Warning se vicino al limite (80%)
    elif righe_totali >= MAX_RIGHE_GLOBALE * 0.8:
        percentuale = (righe_totali / MAX_RIGHE_GLOBALE * 100)
        st.warning(f"⚠️ Database quasi pieno: {righe_totali:,}/{MAX_RIGHE_GLOBALE:,} righe ({percentuale:.0f}%)")
    
    # ============================================================
    # WORKSPACE TEST FISSO PER ADMIN
    # ============================================================
    if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
        st.info("🧪 Ambiente test admin attivo: qui puoi usare le stesse pagine operative del cliente senza selezionare un ristorante.")
        st.markdown("---")
    
    # ============================================================
    # PRE-COMPUTE: Conta righe da categorizzare per UI (dal DataFrame cached)
    # ⚡ ALLINEATO con mostra_statistiche: escludi NOTE E DICITURE + needs_review
    # ============================================================
    _righe_da_class_ui = 0
    _prodotti_unici_ui = 0
    try:
        if not df_cache.empty and 'Categoria' in df_cache.columns:
            # Escludi le stesse righe escluse dalla dashboard (note + review) — solo lettura, no copy
            _cat_col_ui = df_cache['Categoria'].fillna('')
            _mask_note = (_cat_col_ui == '📝 NOTE E DICITURE') | (_cat_col_ui == 'NOTE E DICITURE')
            if 'needs_review' in df_cache.columns:
                _mask_review = df_cache['needs_review'].fillna(False) == True
                _df_for_count = df_cache[~(_mask_note | _mask_review)]
            else:
                _df_for_count = df_cache[~_mask_note]
            
            _mask_da_class = (
                _df_for_count['Categoria'].isna()
                | (_df_for_count['Categoria'] == 'Da Classificare')
                | (_df_for_count['Categoria'].astype(str).str.strip() == '')
            )
            _righe_da_class_ui = _mask_da_class.sum()
            _prodotti_unici_ui = _df_for_count[_mask_da_class]['Descrizione'].nunique()
    except Exception as _e:
        logger.debug(f"Calcolo contatori UI da classificare non riuscito (non bloccante): {_e}")

    # ============================================================
    # UPLOAD PANEL (components/upload_panel.py)
    # ============================================================
    uploaded_files = render_upload_panel()

    # 🧠 RESET ICONE AI al nuovo caricamento (solo session_state, niente DB)
    if uploaded_files and len(uploaded_files) > 0:
        current_upload_ids = [f.name for f in uploaded_files]
        ultimo_upload = st.session_state.get('ultimo_upload_ids', [])
        
        # Rilevamento nuovo caricamento (file diversi)
        if current_upload_ids != ultimo_upload:
            # Reset solo session_state (no query DB costosa)
            if 'righe_ai_appena_categorizzate' in st.session_state:
                st.session_state.righe_ai_appena_categorizzate = []
            logger.info("🧹 Reset icone AI - nuovo caricamento rilevato")
            st.session_state.ultimo_upload_ids = current_upload_ids
            # Pulisce riepilogo ultimo upload all'inizio di un nuovo caricamento
            if 'last_upload_summary' in st.session_state:
                del st.session_state.last_upload_summary
            # Evita che banner/messaggi del batch precedente restino visibili sul nuovo upload.
            st.session_state.upload_messages = []
            st.session_state.upload_messages_time = 0
            st.session_state.pop('last_upload_notification_context', None)

    # Bottone Reset Upload (solo admin impersonificato)
    if st.session_state.get('impersonating', False):
        if st.button("🔄 Ripristina upload (pulisci cache sessione)", key="reset_upload_cache"):
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
            st.session_state.files_errori_report = {}
            # 🔥 Rimuovi flag force_empty per sbloccare caricamento
            if 'force_empty_until_upload' in st.session_state:
                del st.session_state.force_empty_until_upload
            st.success("✅ Cache pulita! Puoi ricaricare i file.")
            st.rerun()

# ============================================================
# SESSION STATE: Tracking file elaborati/errori
# ============================================================
if 'files_processati_sessione' not in st.session_state:
    st.session_state.files_processati_sessione = set()

if 'files_con_errori' not in st.session_state:
    st.session_state.files_con_errori = set()

if 'files_errori_report' not in st.session_state:
    st.session_state.files_errori_report = {}  # Dizionario persistente per mostrare report anche dopo rerun

# Se l'uploader e vuoto, permetti nuovamente l'elaborazione dello stesso batch in futuro.
if not uploaded_files:
    st.session_state.pop('_last_processed_upload_token', None)


# ============================================================
# AUTO-PULIZIA: Se non ci sono file caricati ma ci sono errori nel report,
# significa che l'utente ha rimosso i file → pulisci automaticamente
# ============================================================
if not uploaded_files and len(st.session_state.files_errori_report) > 0:
    logger.info("🧹 Auto-pulizia errori dopo rimozione file")
    st.session_state.files_con_errori = set()
    st.session_state.files_errori_report = {}
    # Non serve rerun: la pagina è già pulita senza file caricati


# ============================================================
# UPLOAD: messaggi, processing, review competenza
# (controllers/upload_controller.py)
# ============================================================
show_upload_messages()
process_uploaded_files(uploaded_files, supabase, user_id)
# [DEBUG]
_debug_session_snap("POST_UPLOAD")
render_competenza_review(user_id)

# 🔥 CARICA E MOSTRA STATISTICHE SEMPRE (da Supabase)
# ⚡ RIUSA df_cache caricato sopra (evita doppia query DB)


# Crea placeholder per loading
loading_placeholder = st.empty()


try:
    # Mostra animazione AI durante caricamento
    mostra_loading_ai(loading_placeholder, "Caricamento Dashboard AI")
    
    # Riusa dati già caricati (df_cache) - evita seconda chiamata a carica_e_prepara_dataframe
    df_completo = df_cache
    
    loading_placeholder.empty()
    
    # Mostra dashboard direttamente senza messaggi
    if not df_completo.empty:
        mostra_statistiche(df_completo, supabase, uploaded_files)
    else:
        st.info("📊 Nessun dato disponibile. Carica le tue prime fatture!")


except Exception as e:
    loading_placeholder.empty()
    logger.error(f"Errore durante il caricamento: {e}")
    st.error("❌ Errore durante il caricamento del file. Riprova.")
    logger.exception("Errore caricamento dashboard")

# ✅ Reset contatore anti-loop DOPO che il render è completato senza rerun
# (se siamo arrivati qui, il ciclo corrente è terminato normalmente)
if st.session_state.get('logged_in', False):
    st.session_state._rerun_guard = 0

