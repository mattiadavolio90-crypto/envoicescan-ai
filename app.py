import streamlit as st
import pandas as pd
import os
import html as _html
import hmac as _hmac
from collections import defaultdict

import io
import time

from utils.streamlit_compat import patch_streamlit_width_api

patch_streamlit_width_api()

# Import costanti da modulo separato
from config.constants import (
    CATEGORIE_SPESE_GENERALI,
    ADMIN_EMAILS,
    TRUNCATE_ERROR_DISPLAY,
    TRUNCATE_DESC_LOG,
    TRUNCATE_DESC_QUERY,
    UI_DELAY_SHORT,
    UI_DELAY_MEDIUM,
    UI_DELAY_LONG,
    UI_DELAY_QUICK,
    BATCH_RATE_LIMIT_DELAY,
    MAX_FILES_PER_UPLOAD,
    MAX_UPLOAD_TOTAL_MB,
    MAX_AI_CALLS_PER_DAY,
    MESI_ITA,
    MAX_RIGHE_GLOBALE,
    MAX_RIGHE_BATCH,
    BATCH_FILE_SIZE,
    SESSION_INACTIVITY_HOURS as _SESSION_INACTIVITY_HOURS,
    LAST_SEEN_WRITE_THROTTLE_SECONDS as _LAST_SEEN_WRITE_THROTTLE_SECONDS,
)

# Import utilities da moduli separati
from utils.text_utils import (
    normalizza_stringa,
    estrai_nome_categoria,
    escape_ilike as _escape_ilike,
    format_fattura_label,
)

from utils.piva_validator import normalizza_piva

from utils.formatters import (
    calcola_prezzo_standard_intelligente,
    carica_categorie_da_db,
    log_upload_event,
    get_nome_base_file
)

from utils.ristorante_helper import add_ristorante_filter, ensure_admin_test_workspace
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ui_helpers import load_css, load_js, render_pivot_mensile

# Import services
from services.ai_service import (
    carica_memoria_completa,
    invalida_cache_memoria,
    applica_correzioni_dizionario,
    salva_correzione_in_memoria_globale,
    salva_correzione_in_memoria_locale,
    classifica_con_ai,
    mostra_loading_ai,
    svuota_memoria_globale,
    set_global_memory_enabled,
    ottieni_categoria_prodotto
)

from services.auth_service import (
    verify_and_migrate_password,
    verifica_credenziali,
    invia_codice_reset,
    aggiorna_last_seen,
    imposta_password_da_token,
    verifica_sessione_da_cookie,
)

try:
    from services.auth_service import riepilogo_fatture_auto_da_ultimo_login
except ImportError:
    def riepilogo_fatture_auto_da_ultimo_login(*args, **kwargs):
        return {
            'has_new': False,
            'file_count': 0,
            'row_count': 0,
            'event_count': 0,
            'recent_files': [],
            'files_detail': [],
            'window_start': None,
            'window_end': None,
        }

from services.invoice_service import (
    estrai_dati_da_xml,
    estrai_xml_da_p7m,
    estrai_dati_da_scontrino_vision,
    salva_fattura_processata,
)

from services.db_service import (
    carica_e_prepara_dataframe,
    elimina_fattura_completa,
    elimina_tutte_fatture,
    get_fatture_stats,
    clear_fatture_cache,
    get_fatture_cestino,
    ripristina_fattura,
    svuota_cestino,
)

from components.dashboard_renderer import mostra_statistiche
from services.upload_handler import handle_uploaded_files
from services.notification_service import (
    build_credit_note_notifications,
    build_monthly_data_notifications,
    build_price_alert_notifications,
    build_scoped_notification_id,
    build_td24_date_notifications,
    build_upload_outcome_notifications,
    build_upload_quality_notifications,
    dismiss_notification_ids,
    get_dismissed_notification_ids,
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


def _show_toast_once(toast_id: str, message: str, icon: str = None) -> None:
    """Mostra un toast una sola volta per sessione."""
    if not message:
        return
    if 'shown_dashboard_toasts' not in st.session_state:
        st.session_state.shown_dashboard_toasts = set()
    if toast_id in st.session_state.shown_dashboard_toasts:
        return
    st.toast(message, icon=icon)
    st.session_state.shown_dashboard_toasts.add(toast_id)


def _apply_notification_navigation_target(notification: dict) -> None:
    """Imposta eventuale stato tab prima del cambio pagina dalle notifiche."""
    if not isinstance(notification, dict):
        return

    state_key = notification.get('action_state_key')
    state_value = notification.get('action_state_value')
    if state_key and state_value is not None:
        st.session_state[state_key] = state_value


def _render_operational_notifications(notifications, user_id, dismissed_ids, supabase_client):
    """Render compatto delle notifiche gestionali con dismiss persistente."""
    if not notifications:
        return

    styles = {
        'warning': {
            'border': '#f59e0b',
            'background': '#fff7ed',
            'title': '#9a3412',
            'body': '#7c2d12',
        },
        'info': {
            'border': '#3b82f6',
            'background': '#eff6ff',
            'title': '#1d4ed8',
            'body': '#1e3a8a',
        },
    }

    for notification in notifications:
        _show_toast_once(
            f"operational::{notification.get('id')}",
            notification.get('toast') or notification.get('title') or 'Nuova notifica',
            icon=notification.get('icon'),
        )

    count_label = 'promemoria operativo' if len(notifications) == 1 else 'promemoria operativi'

    st.markdown("""
    <style>
    div.st-key-expander_operational_notifications [data-testid="stExpander"] details summary {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 700;
        color: #92400e;
    }
    div.st-key-expander_operational_notifications [data-testid="stExpander"] details {
        border: 2px solid #f59e0b;
        border-radius: 12px;
        margin-bottom: 1rem;
    }
    div.st-key-expander_operational_notifications [data-testid="stExpander"] details[open] summary {
        border-bottom: 1px solid #fcd34d;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.container(key="expander_operational_notifications"):
        st.markdown(
            f"<span style='font-size:1.05rem; font-weight:700; color:#92400e;'>"
            f"🔔 Hai {len(notifications)} {count_label}"
            f"</span>",
            unsafe_allow_html=True,
        )

        with st.expander("📌 Dettaglio promemoria", expanded=False):
            for idx, notification in enumerate(notifications):
                palette = styles.get(notification.get('level'), styles['info'])
                _n_title = _html.escape(notification.get('title', 'Notifica'))
                _n_body = _html.escape(notification.get('body', ''))
                cols = st.columns([5, 1, 1])
                with cols[0]:
                    st.markdown(
                        f"""
                        <div style="border-left:4px solid {palette['border']}; background:{palette['background']};
                                    border-radius:10px; padding:12px 14px; margin-bottom:10px;">
                            <div style="font-weight:700; color:{palette['title']}; margin-bottom:4px;">
                                {notification.get('icon', '🔔')} {_n_title}
                            </div>
                            <div style="font-size:0.92rem; color:{palette['body']};">
                                {_n_body}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    action_page = notification.get('action_page')
                    if action_page and st.button(
                        notification.get('action_label', 'Apri'),
                        key=f"operational_notification_action_{idx}",
                        use_container_width=True,
                    ):
                        _apply_notification_navigation_target(notification)
                        st.switch_page(action_page)
                with cols[2]:
                    if st.button(
                        "Nascondi",
                        key=f"operational_notification_hide_{idx}",
                        use_container_width=True,
                    ):
                        dismiss_notification_ids(
                            user_id=user_id,
                            notification_ids=[notification.get('id')],
                            supabase_client=supabase_client,
                        )
                        st.rerun()


def _render_auto_invoice_notice(auto_notice, user_id, dismissed_ids, supabase_client, ristorante_id):
    """Render della notifica fatture automatiche sotto il contesto ristorante."""
    if not auto_notice or st.session_state.get('auto_invoice_notice_dismissed', False):
        return

    files_detail = auto_notice.get('files_detail', []) or []
    pending_files = []
    for finfo in files_detail:
        notification_id = build_scoped_notification_id(
            f"auto-file:{finfo.get('file_name', '')}",
            ristorante_id,
        )
        if finfo.get('file_name') in st.session_state.auto_invoice_handled:
            continue
        if notification_id in dismissed_ids:
            continue
        pending_files.append(finfo)

    if not pending_files:
        return

    # Mantieni ordinamento cronologico di ricezione (piu recente prima).
    pending_files = sorted(
        pending_files,
        key=lambda x: str(x.get('created_at') or ''),
        reverse=True,
    )

    # Split chiaro per il cliente:
    # - nuove: ricevute dopo l'ultimo login
    # - in sospeso: backlog non ancora confermato
    nuove_count = int(auto_notice.get('new_count') or 0)
    totale_da_conferma = int(auto_notice.get('total_pending_count') or len(pending_files))
    in_sospeso_count = int(auto_notice.get('pending_count') or max(0, totale_da_conferma - nuove_count))

    if not st.session_state.get('auto_invoice_notice_toast_shown', False):
        fatture_label = 'fattura' if len(pending_files) == 1 else 'fatture'
        toast_message = f"Hai ricevuto {len(pending_files)} {fatture_label} automatiche"
        st.toast(f"📬 {toast_message}", icon="📥")
        st.session_state.auto_invoice_notice_toast_shown = True

    st.markdown("""
    <style>
    div.st-key-expander_auto_invoices [data-testid="stExpander"] details summary {
        background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 700;
        color: #1e3a8a;
    }
    div.st-key-expander_auto_invoices [data-testid="stExpander"] details {
        border: 2px solid #3b82f6;
        border-radius: 12px;
        margin-bottom: 1rem;
    }
    div.st-key-expander_auto_invoices [data-testid="stExpander"] details[open] summary {
        border-bottom: 1px solid #93c5fd;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.container(key="expander_auto_invoices"):
        fatture_label = 'fattura' if len(pending_files) == 1 else 'fatture'
        _hdr_col, _save_all_col = st.columns([5, 1])
        with _hdr_col:
            st.markdown(
                f"<span style='font-size:1.05rem; font-weight:700; color:#1e3a8a;'>"
                f"🔔 Sono arrivate {len(pending_files)} nuove {fatture_label} dall'ultimo tuo accesso"
                f"</span>",
                unsafe_allow_html=True,
            )
        with _save_all_col:
            if st.button("✅ Salva tutte", key="auto_notice_save_all", use_container_width=True, type="primary"):
                _ack_uid = st.session_state.user_data.get('id')
                _ack_event_ids = []
                for _f in pending_files:
                    _ack_event_ids.extend(_f.get('event_ids') or [])
                _ack_event_ids = list({eid for eid in _ack_event_ids if eid is not None})
                if _ack_uid and _ack_event_ids:
                    try:
                        supabase_client.table('upload_events') \
                            .update({'needs_ack': False}) \
                            .eq('user_id', _ack_uid) \
                            .in_('id', _ack_event_ids) \
                            .execute()
                    except Exception as _ack_err:
                        logger.error(f"Errore ack needs_ack Salva tutte: {_ack_err}")
                for f in pending_files:
                    st.session_state.auto_invoice_handled.add(f['file_name'])
                clear_fatture_cache()
                st.session_state.auto_invoice_notice_dismissed = True
                st.rerun()
        expander_title = (
            f"📄 Fatture | Nuove: {nuove_count} | "
            f"In sospeso da confermare: {in_sospeso_count} | "
            f"Totale da confermare: {totale_da_conferma}"
        )
        with st.expander(expander_title, expanded=False):
            for idx, finfo in enumerate(pending_files):
                fname = finfo.get('file_name', 'file sconosciuto')
                fornitore = finfo.get('fornitore', 'Sconosciuto')
                data_doc = finfo.get('data_documento', '')
                num_righe = finfo.get('num_righe', 0)
                totale = finfo.get('totale', 0)

                col_detail, col_btns = st.columns([6, 2])
                with col_detail:
                    _row_label = format_fattura_label(
                        file_name=fname,
                        fornitore=fornitore,
                        totale=totale,
                        num_righe=num_righe,
                        data=data_doc,
                        max_file_chars=28,
                    )
                    st.markdown(
                        f"{_row_label}",
                    )
                with col_btns:
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("💾 Salva", key=f"auto_save_{idx}", use_container_width=True):
                            _ack_uid = st.session_state.user_data.get('id')
                            _ack_event_ids = [eid for eid in (finfo.get('event_ids') or []) if eid is not None]
                            if _ack_uid:
                                try:
                                    if _ack_event_ids:
                                        supabase_client.table('upload_events') \
                                            .update({'needs_ack': False}) \
                                            .eq('user_id', _ack_uid) \
                                            .in_('id', _ack_event_ids) \
                                            .execute()
                                except Exception as _ack_err:
                                    logger.error(f"Errore ack needs_ack Salva {fname}: {_ack_err}")
                            st.session_state.auto_invoice_handled.add(fname)
                            clear_fatture_cache()
                            st.rerun()
                    with bc2:
                        if st.button("❌ Rifiuta", key=f"auto_reject_{idx}", use_container_width=True):
                            _ack_uid = st.session_state.user_data.get('id')
                            _ack_event_ids = [eid for eid in (finfo.get('event_ids') or []) if eid is not None]
                            if _ack_uid:
                                try:
                                    if _ack_event_ids:
                                        supabase_client.table('upload_events') \
                                            .update({'needs_ack': False}) \
                                            .eq('user_id', _ack_uid) \
                                            .in_('id', _ack_event_ids) \
                                            .execute()
                                except Exception as _ack_err:
                                    logger.error(f"Errore ack needs_ack Rifiuta {fname}: {_ack_err}")
                            try:
                                _reject_uid = st.session_state.user_data.get('id')
                                _reject_rid = st.session_state.get('ristorante_id')
                                elimina_fattura_completa(fname, _reject_uid, ristoranteid=_reject_rid, soft_delete=False)
                                invalida_cache_memoria()
                                clear_fatture_cache()
                            except Exception as _rej_err:
                                logger.error(f"Errore rifiuto fattura auto {fname}: {_rej_err}")
                            st.session_state.auto_invoice_handled.add(fname)
                            st.rerun()


# ============================================
# FUNZIONE CALCOLO PREZZO STANDARDIZZATO
# ============================================

st.set_page_config(
    page_title="OH YEAH! Hub",
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
# ============================================================
_rerun_count = st.session_state.get('_rerun_guard', 0)
if _rerun_count > 8:
    import logging as _logging_guard
    _logging_guard.getLogger('fci_app').critical(f"🚨 RERUN LOOP DETECTED ({_rerun_count} consecutivi) - reset forzato")
    st.session_state._rerun_guard = 0
    st.session_state.force_reload = False
    st.error("⚠️ Rilevato loop di aggiornamento. La pagina è stata stabilizzata.")
    st.stop()
st.session_state._rerun_guard = _rerun_count + 1

# ============================================================
# SIDEBAR: NASCONDI SUBITO SE NON LOGGATO (anti-flash)
# ============================================================
if not st.session_state.get('logged_in', False):
    from utils.ui_helpers import hide_sidebar_css
    hide_sidebar_css()

# CSS + JS branding (caricati da file statici)
load_css('branding.css')
load_css('layout.css')
load_js('branding.js')

st.markdown("""
<style>
/* =========================================================
   RESPONSIVE GLOBAL - Desktop invariato, tablet e mobile
   ========================================================= */

html, body, .stApp {
    overflow-x: hidden !important;
}

.main .block-container,
.block-container {
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}

[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
[data-testid="column"],
[data-testid="stExpander"],
[data-testid="stExpander"] details {
    min-width: 0 !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}

/* Tabelle e data editor: mai fuori schermo */
[data-testid="stDataFrame"],
div[data-testid="stDataFrameGlideDataEditor"],
.stDataFrame,
.file-status-table,
[data-testid="stTable"] {
    max-width: 100% !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
}

[data-testid="stDataFrame"] > div,
div[data-testid="stDataFrameGlideDataEditor"] > div,
.file-status-table table {
    min-width: max-content !important;
}

/* Intestazioni tabelle: MAIUSCOLO + GRASSETTO */
div[data-testid="stDataFrame"] div[role="columnheader"],
div[data-testid="stDataFrame"] div[role="columnheader"] *,
div[data-testid="stDataFrameGlideDataEditor"] div[role="columnheader"],
div[data-testid="stDataFrameGlideDataEditor"] div[role="columnheader"] *,
div[data-testid="stDataEditor"] div[role="columnheader"],
div[data-testid="stDataEditor"] div[role="columnheader"] * {
    font-weight: 700 !important;
    text-transform: uppercase !important;
}

/* Plotly full width */
[data-testid="stPlotlyChart"],
[data-testid="stPlotlyChart"] > div,
.js-plotly-plot,
.plot-container,
.plotly {
    width: 100% !important;
    max-width: 100% !important;
}

/* Bottoni più robusti anche fuori mobile */
button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"],
[data-testid="stDownloadButton"] button {
    min-height: 2.75rem !important;
}
/* Il bottone uploader ha il suo scope dedicato in main_documents_upload_section */

/* Tablet */
@media (min-width: 768px) and (max-width: 1024px) {
    html {
        font-size: 15px !important;
    }

    .main .block-container,
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    [data-testid="column"] {
        margin-bottom: 1rem !important;
    }

    [data-testid="stMetric"] {
        padding: 1rem 0.9rem !important;
        border-width: 3px !important;
    }

    .kpi-card,
    .kpi-card-cp,
    .admin-metric-card {
        padding: 0.9rem !important;
    }

    /* KPI principali: 2 per riga */
    [data-testid="stHorizontalBlock"]:has(.kpi-card),
    [data-testid="stHorizontalBlock"]:has(.kpi-card-cp),
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        flex-wrap: wrap !important;
        gap: 0.75rem !important;
    }

    [data-testid="stHorizontalBlock"]:has(.kpi-card) > div[data-testid="column"],
    [data-testid="stHorizontalBlock"]:has(.kpi-card-cp) > div[data-testid="column"],
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"] {
        flex: 1 1 calc(50% - 0.75rem) !important;
        max-width: calc(50% - 0.75rem) !important;
    }

    section[data-testid="stSidebar"],
    [data-testid="stSidebar"] {
        width: 230px !important;
        min-width: 230px !important;
        max-width: 230px !important;
    }
}

/* Mobile */
@media (max-width: 767px) {
    html {
        font-size: 16px !important;
    }

    .main .block-container,
    .block-container {
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        padding-top: 1rem !important;
        padding-bottom: 4rem !important;
    }

    /* Tutto in colonna singola */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.75rem !important;
    }

    [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        width: 100% !important;
        min-width: 100% !important;
        max-width: 100% !important;
        flex: 1 1 100% !important;
        margin-bottom: 0.75rem !important;
    }

    /* KPI e card singole */
    [data-testid="stHorizontalBlock"]:has(.kpi-card) > div[data-testid="column"],
    [data-testid="stHorizontalBlock"]:has(.kpi-card-cp) > div[data-testid="column"],
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"] {
        flex: 1 1 100% !important;
        max-width: 100% !important;
    }

    [data-testid="stMetric"] {
        padding: 1rem !important;
        border-width: 2px !important;
    }

    [data-testid="stMetricValue"] > div {
        font-size: 1.8rem !important;
    }

    [data-testid="stMetricLabel"] > div,
    .kpi-card .kpi-label,
    .kpi-card-cp .kpi-label,
    .admin-metric-label {
        font-size: 1rem !important;
    }

    .kpi-card .kpi-value,
    .kpi-card-cp .kpi-value,
    .admin-metric-value {
        font-size: 1.4rem !important;
    }

    /* Font minimo leggibile */
    p, li, label, span, div,
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        font-size: max(16px, 1rem);
    }

    /* Bottoni touch-friendly */
    button,
    [data-testid="stDownloadButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        min-height: 44px !important;
        padding-top: 0.8rem !important;
        padding-bottom: 0.8rem !important;
    }

    button p {
        font-size: 1rem !important;
        white-space: normal !important;
        line-height: 1.25 !important;
    }

    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    textarea {
        min-height: 44px !important;
        font-size: 16px !important;
    }

    [data-testid="stDataFrame"],
    div[data-testid="stDataFrameGlideDataEditor"],
    .file-status-table,
    [data-testid="stPlotlyChart"] {
        overflow-x: auto !important;
    }

    [data-testid="stExpander"] {
        width: 100% !important;
        max-width: 100% !important;
    }

    section[data-testid="stSidebar"],
    [data-testid="stSidebar"] {
        width: min(85vw, 320px) !important;
        min-width: min(85vw, 320px) !important;
        max-width: min(85vw, 320px) !important;
    }
}
</style>
""", unsafe_allow_html=True)


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

# ============================================================
# COOKIE MANAGER - SESSIONE PERSISTENTE
# ============================================================
try:
    import extra_streamlit_components as stx
    _cookie_manager = stx.CookieManager(key="cookie_manager_app")
except Exception as _ce:
    _cookie_manager = None
    logger.warning(f"CookieManager non disponibile: {_ce}")

# ============================================
# IMPOSTA COOKIE IMPERSONAZIONE (richiesto da admin.py via session_state)
# ============================================
# admin.py imposta _set_impersonation_cookie prima di switch_page("app.py").
# Qui lo leggiamo e scriviamo il cookie browser, così sopravvive al F5.
if st.session_state.get('_set_impersonation_cookie') and _cookie_manager is not None:
    try:
        _cookie_manager.set(
            "impersonation_user_id",
            str(st.session_state.get('_set_impersonation_cookie', '')),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            secure=True, same_site="strict"
        )
    except Exception as _ice:
        logger.warning(f"Errore impostazione cookie impersonazione: {_ice}")
    if '_set_impersonation_cookie' in st.session_state:
        del st.session_state['_set_impersonation_cookie']

# ============================================
# TIMEOUT IMPERSONAZIONE (max 30 minuti)
# ============================================
if st.session_state.get('impersonating', False):
    _imp_started_raw = st.session_state.get('impersonation_started_at')
    if _imp_started_raw:
        try:
            _imp_started_dt = datetime.fromisoformat(str(_imp_started_raw).replace('Z', '+00:00'))
            if _imp_started_dt.tzinfo is None:
                _imp_started_dt = _imp_started_dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - _imp_started_dt) > timedelta(minutes=30):
                _imp_client_email = st.session_state.get('user_data', {}).get('email', '?')
                _imp_admin_email = st.session_state.get('admin_original_user', {}).get('email', '?')
                logger.warning(f"🔒 IMPERSONATION TIMEOUT: admin={_imp_admin_email} → client={_imp_client_email}")
                # Ripristina admin
                if 'admin_original_user' in st.session_state:
                    st.session_state.user_data = st.session_state.admin_original_user.copy()
                    del st.session_state.admin_original_user
                st.session_state.impersonating = False
                st.session_state.user_is_admin = True
                st.session_state.pop('impersonation_started_at', None)
                if _cookie_manager is not None:
                    try:
                        _cookie_manager.set("impersonation_user_id", "",
                                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    except Exception:
                        pass
                st.warning("⏰ Sessione impersonazione scaduta (30 min). Sei tornato admin.")
                st.rerun()
        except (ValueError, TypeError):
            pass

# ============================================
# GESTIONE LOGOUT FORZATO VIA QUERY PARAMS
# ============================================
if st.query_params.get("logout") == "1":
    logger.warning("🚨 LOGOUT FORZATO via query params - pulizia sessione")
    # Token già invalidato da sidebar_helper, ma tenta anche qui come fallback
    try:
        _email_for_logout = st.session_state.get('user_data', {}).get('email')
        if _email_for_logout:
            supabase.table('users').update({
                'session_token': None,
                'session_token_created_at': None,
                'last_seen_at': None,
            }).eq('email', _email_for_logout).execute()
    except Exception as _logout_err:
        logger.warning(f"⚠️ Impossibile invalidare session_token in DB durante logout: {_logout_err}")
    st.session_state.clear()
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.query_params.clear()
    st.rerun()

# Ripristina sessione da cookie solo se NON in stato di logout forzato
_force_logout_active = st.session_state.get('force_logout', False)

if not st.session_state.logged_in and not _force_logout_active and _cookie_manager is not None:
    try:
        _token_cookie = _cookie_manager.get("session_token")
        if _token_cookie:
            _u = verifica_sessione_da_cookie(_token_cookie, inactivity_hours=_SESSION_INACTIVITY_HOURS)
            if _u:
                st.session_state.logged_in = True
                st.session_state.user_data = _u
                st.session_state.partita_iva = _u.get('partita_iva')
                st.session_state.created_at = _u.get('created_at')
                if (_u.get('email') or '').strip().lower() in ADMIN_EMAILS:
                    st.session_state.user_is_admin = True
                # Force refresh dati da DB (la cache potrebbe essere stale)
                clear_fatture_cache()
                st.session_state.force_reload = True
                logger.info(f"✅ Sessione ripristinata da token per user_id={_u.get('id')} — fatture cache cleared")
            else:
                # Token non valido, scaduto o inattivo → pulisci cookie e vai al login
                try:
                    _cookie_manager.set("session_token", "",
                                        expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                except Exception:
                    pass
                logger.info("🔒 Session token non valido o scaduto - richiesto login")
                st.session_state._cookie_checked = True
        elif not st.session_state.get('_cookie_checked', False):
            # Primo render: CookieManager non ha ancora letto i cookie, aspetta un ciclo
            st.session_state._cookie_checked = True
            st.markdown("""
                <div style='display:flex;align-items:center;justify-content:center;
                            height:80vh;flex-direction:column;gap:12px;'>
                    <div style='font-size:2rem;'>⏳</div>
                    <div style='color:#94a3b8;font-size:0.95rem;'>Caricamento sessione...</div>
                </div>
            """, unsafe_allow_html=True)
            st.stop()
        # else: nessun token e già controllato → login normale
    except Exception as cookie_err:
        logger.warning(f"Errore ripristino sessione da cookie: {cookie_err}")


# ✅ Reset contatore anti-loop SOLO nella pagina login (non loggato)
# Il reset nel flow autenticato avviene DOPO il render completo (vedi fine file)
if not st.session_state.get('logged_in', False):
    st.session_state._rerun_guard = 0

# Aggiorna last_seen_at con throttling: massimo 1 scrittura ogni 5 minuti per sessione Streamlit
if st.session_state.get('logged_in', False):
    _active_user_id = st.session_state.get('user_data', {}).get('id')
    if _active_user_id:
        _now_utc = datetime.now(timezone.utc)
        _last_seen_write_raw = st.session_state.get('_last_seen_write_at')
        _should_write_last_seen = False

        if not _last_seen_write_raw:
            _should_write_last_seen = True
        else:
            try:
                _last_write_dt = datetime.fromisoformat(str(_last_seen_write_raw).replace('Z', '+00:00'))
                if _last_write_dt.tzinfo is None:
                    _last_write_dt = _last_write_dt.replace(tzinfo=timezone.utc)
                _should_write_last_seen = (_now_utc - _last_write_dt).total_seconds() >= _LAST_SEEN_WRITE_THROTTLE_SECONDS
            except (ValueError, TypeError):
                _should_write_last_seen = True

        if _should_write_last_seen:
            if aggiorna_last_seen(_active_user_id, supabase):
                st.session_state._last_seen_write_at = _now_utc.isoformat()


# ============================================================
# GESTIONE TOKEN RESET PASSWORD (NUOVO CLIENTE + RECUPERO PASSWORD)
# ============================================================
# Se c'è il parametro reset_token, mostra form impostazione password
if st.query_params.get("reset_token"):
    from services.auth_service import imposta_password_da_token, valida_password_compliance
    
    reset_token = st.query_params.get("reset_token")
    
    # Nascondi sidebar per pagina pulita
    hide_sidebar_css()
    
    st.markdown("""
    <h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
        🔐 <span style="background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;">Imposta la tua Password</span>
    </h2>
    """, unsafe_allow_html=True)
    
    # Verifica token valido
    try:
        check_result = supabase.table('users')\
            .select('id, email, nome_ristorante, reset_expires, password_hash')\
            .eq('reset_code', reset_token)\
            .execute()
        
        if not check_result.data:
            st.error("❌ Link non valido o già utilizzato")
            st.info("💡 Se hai già impostato la password, vai al login. Altrimenti contatta il supporto per un nuovo link.")
            if st.button("🔑 Vai al Login"):
                st.query_params.clear()
                st.rerun()
            st.stop()
        
        user_data = check_result.data[0]
        
        # Check scadenza token
        expires_str = user_data.get('reset_expires')
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                now_utc = datetime.now(timezone.utc)
                
                if now_utc > expires:
                    st.error("⏰ Link scaduto (validità: 24 ore)")
                    st.info("💡 Contatta il supporto per ricevere un nuovo link di attivazione.")
                    st.stop()
            except Exception as e:
                logger.warning(f"Errore parsing data scadenza token: {e}")
        
        # Mostra info utente
        is_nuovo_cliente = user_data.get('password_hash') is None
        
        if is_nuovo_cliente:
            st.success(f"✅ Benvenuto, **{user_data.get('nome_ristorante')}**!")
            st.info(f"📧 Il tuo account: **{user_data.get('email')}**")
            st.markdown("Imposta una password sicura per accedere all'app.")
        else:
            st.info(f"📧 Reset password per: **{user_data.get('email')}**")
        
        # Form impostazione password
        with st.form("form_imposta_password"):
            nuova_password = st.text_input(
                "🔑 Nuova Password",
                type="password",
                help="Minimo 10 caratteri, con maiuscola, minuscola e numero"
            )
            
            conferma_password = st.text_input(
                "🔑 Conferma Password",
                type="password"
            )
            
            st.markdown("""
            **Requisiti password:**
            - ✅ Almeno 10 caratteri
            - ✅ Almeno 3 tra: maiuscola, minuscola, numero, simbolo
            - ❌ Non usare email o nome ristorante
            - ❌ Non usare password comuni
            """)

            # GDPR Art.6 — consenso esplicito al trattamento dati (solo primo accesso)
            gdpr_accepted = True  # default per reset password (utente già registrato)
            if is_nuovo_cliente:
                gdpr_accepted = st.checkbox(
                    "✅ Ho letto e accetto l'[Informativa Privacy](/?page=privacy) "
                    "(D.lgs. 196/2003 e GDPR UE 2016/679). "
                    "Acconsento al trattamento dei miei dati per l'erogazione del servizio.",
                    key="gdpr_consent_activation"
                )
            
            submitted = st.form_submit_button("✅ Conferma Password", type="primary", use_container_width=True)
            
            if submitted:
                # Validazioni
                if is_nuovo_cliente and not gdpr_accepted:
                    st.error("⚠️ Devi accettare l'Informativa Privacy per continuare.")
                elif not nuova_password or not conferma_password:
                    st.error("⚠️ Compila entrambi i campi password")
                elif nuova_password != conferma_password:
                    st.error("❌ Le password non coincidono")
                else:
                    # Valida compliance GDPR
                    errori = valida_password_compliance(
                        nuova_password,
                        user_data.get('email', ''),
                        user_data.get('nome_ristorante', '')
                    )
                    
                    if errori:
                        for err in errori:
                            st.error(err)
                    else:
                        # Imposta password
                        successo, messaggio, _ = imposta_password_da_token(
                            reset_token,
                            nuova_password,
                            supabase
                        )
                        
                        if successo:
                            st.success("""
                            🎉 **Password impostata con successo!**
                            
                            Ora puoi effettuare il login con la tua email e password.
                            """)
                            st.balloons()
                            
                            # Pulisci token da URL
                            time.sleep(UI_DELAY_LONG)
                            st.query_params.clear()
                            st.rerun()
                        else:
                            st.error(messaggio)
    
    except Exception as e:
        st.error("❌ Errore durante la verifica del link. Riprova o contatta il supporto.")
        logger.exception("Errore verifica reset_token")
    
    st.stop()  # Non mostrare resto app


# ============================================================
# HELPER FUNCTIONS
# ============================================================

# is_admin_or_impersonating() → unica definizione in utils.app_controllers


def mostra_pagina_login():
    """Form login con recupero password - ESTETICA STREAMLIT PULITA"""
    # Elimina completamente sidebar e pulsante (CSS già applicato globalmente prima del login)
    # Solo CSS aggiuntivo per padding login
    st.markdown("""
        <style>
        /* ✂️ RIDUCI SPAZIO SUPERIORE LOGIN */
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 3rem !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Messaggio scadenza trial (mostrato dopo logout automatico da app.py)
    if st.session_state.pop('_trial_expired_msg', False):
        st.error(
            "⏰ **Prova gratuita scaduta.** Il tuo account è stato disattivato. "
            "Contatta il supporto per attivare un abbonamento."
        )

    render_oh_yeah_header()
    
    st.markdown("""
<h2 style="font-size: clamp(2.2rem, 5.5vw, 3.2rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🔐 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Accedi al Sistema</span>
</h2>
""", unsafe_allow_html=True)
    
    # Nota legale senza sfondo
    st.markdown("""
<p style="font-size: clamp(0.7rem, 1.6vw, 0.82rem); color: #1e3a8a; margin: 0.75rem 0 1.25rem 0; line-height: 1.6;">
    📄 <strong>Nota Legale:</strong> Questo servizio offre strumenti di analisi gestionale e non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati.
</p>
""", unsafe_allow_html=True)

    # ── Informativa cookie (Garante Privacy IT — cookie tecnici strettamente necessari) ──
    # I cookie tecnici di sessione non richiedono consenso preventivo ma l'utente va informato.
    st.markdown("""
<div style="background:#f0f7ff;border:1px solid #bdd7f5;border-radius:6px;padding:8px 12px;
            font-size:0.75rem;color:#1e3a8a;margin-bottom:0.8rem;line-height:1.5;">
    🍪 <strong>Cookie tecnici:</strong> Questo sito utilizza esclusivamente cookie tecnici di sessione,
    necessari al funzionamento del servizio. Non vengono usati cookie di profilazione o tracciamento.
    Per maggiori informazioni consulta la pagina dedicata dopo il login.
</div>
""", unsafe_allow_html=True)
    
    # Tab navigazione stile bottoni (stesso stile dell'app)
    if 'login_tab_attivo' not in st.session_state:
        st.session_state.login_tab_attivo = "login"

    st.markdown("""
        <style>
        /* Bottone Accedi: azzurro, larghezza 200px */
        div[data-testid="stFormSubmitButton"] button {
            background-color: #0ea5e9 !important;
            color: white !important;
            width: 200px !important;
        }
        div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #0284c7 !important;
        }
        /* Fix altezza pagina */
        .main .block-container {
            max-height: none !important;
        }
        div[data-testid="stForm"] {
            max-height: none !important;
            height: auto !important;
        }
        section[data-testid="stSidebar"] ~ div {
            max-height: none !important;
            overflow-y: auto !important;
        }
        </style>
    """, unsafe_allow_html=True)
    col_lt1, col_lt2, _ = st.columns([1.2, 1.8, 5])
    with col_lt1:
        if st.button("🔑 LOGIN", key="lt_btn_login", use_container_width=True,
                     type="primary" if st.session_state.login_tab_attivo == "login" else "secondary"):
            if st.session_state.login_tab_attivo != "login":
                st.session_state.login_tab_attivo = "login"
                st.rerun()
    with col_lt2:
        if st.button("🔄 RECUPERA PASSWORD", key="lt_btn_reset", use_container_width=True,
                     type="primary" if st.session_state.login_tab_attivo == "reset" else "secondary"):
            if st.session_state.login_tab_attivo != "reset":
                st.session_state.login_tab_attivo = "reset"
                st.rerun()

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    if st.session_state.login_tab_attivo == "login":
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="tua@email.com")
            password = st.text_input("🔑 Password", type="password", placeholder="La tua password")
            
            st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Accedi")
            
            if submit:
                if not email or not password:
                    st.error("⚠️ Compila tutti i campi!")
                else:
                    with st.spinner("Verifica credenziali..."):
                        user, errore = verifica_credenziali(email, password)
                        
                        if user:
                            user.pop('password_hash', None)  # Non esporre hash in session
                            st.session_state.force_logout = False  # Reset anti-loop prima di aprire la sessione
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False  # ← Reset flag logout
                            st.session_state.pop('_session_token_set_this_run', None)  # Reset guard cookie per questo login
                            
                            # Salva P.IVA in session_state per validazione fatture
                            st.session_state.partita_iva = user.get('partita_iva')
                            st.session_state.created_at = user.get('created_at')
                            
                            # Pulizia chiave login UI
                            st.session_state.pop('login_tab_attivo', None)

                            # Notifica fatture automatiche ricevute tra login precedente e corrente
                            try:
                                summary_auto = riepilogo_fatture_auto_da_ultimo_login(
                                    user_id=user.get('id'),
                                    last_login_precedente=user.get('last_login_precedente'),
                                    login_at=user.get('login_at'),
                                    supabase_client=supabase,
                                )
                                if summary_auto.get('has_new') and (user.get('email') or '').strip().lower() not in ADMIN_EMAILS:
                                    st.session_state.auto_invoice_notice = summary_auto
                                    st.session_state.auto_invoice_notice_toast_shown = False
                                    st.session_state.auto_invoice_notice_dismissed = False
                                    # Badge 🧠 nel category_editor per righe inserite via worker
                                    st.session_state.auto_received_file_origini = {
                                        f['file_name'] for f in summary_auto.get('files_detail', [])
                                    }
                                else:
                                    st.session_state.pop('auto_invoice_notice', None)
                                    st.session_state.pop('auto_invoice_notice_toast_shown', None)
                                    st.session_state.pop('auto_invoice_notice_dismissed', None)
                                    st.session_state.pop('auto_received_file_origini', None)
                            except Exception as _notice_err:
                                logger.warning(f"Errore preparazione notifica fatture automatiche: {_notice_err}")
                            
                            # 🍪 Genera e salva session_token nel DB + cookie persistente
                            if _cookie_manager is not None and not st.session_state.get('_session_token_set_this_run'):
                                st.session_state['_session_token_set_this_run'] = True
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _s_token = _secrets.token_urlsafe(32)
                                    supabase.table('users').update({
                                        'session_token': _s_token,
                                        'session_token_created_at': _now_utc.isoformat(),
                                        'last_seen_at': _now_utc.isoformat(),
                                    }).eq('id', user.get('id')).execute()
                                    _cookie_manager.set("session_token", _s_token,
                                                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                                                        secure=True, same_site="strict")
                                    st.session_state._last_seen_write_at = _now_utc.isoformat()
                                except Exception as _ce:
                                    logger.warning(f"Errore salvataggio session token: {_ce}")
                            else:
                                st.warning(
                                    "⚠️ Sessione non persistente: "
                                    "verifica che i cookie siano abilitati nel browser. "
                                    "Verrai disconnesso ad ogni aggiornamento pagina."
                                )
                            
                            # Verifica se è admin e imposta flag
                            if (user.get('email') or '').strip().lower() in ADMIN_EMAILS:
                                st.session_state.user_is_admin = True
                                logger.info(f"✅ Login ADMIN: user_id={user.get('id')}")
                                st.success("✅ Accesso effettuato come ADMIN!")
                                time.sleep(UI_DELAY_SHORT)
                                # Reindirizza direttamente al pannello admin
                                st.switch_page("pages/admin.py")
                                st.stop()
                            else:
                                st.session_state.user_is_admin = False
                                logger.info(f"✅ Login cliente: user_id={user.get('id')}")
                                # Force refresh dati post-login (invalida cache stale)
                                clear_fatture_cache()
                                st.session_state.force_reload = True
                                st.session_state.show_welcome = True
                                logger.info(f"[LOGIN] Fatture cache cleared + force_reload per user_id={user.get('id')}")
                                st.success("✅ Accesso effettuato!")
                                time.sleep(UI_DELAY_MEDIUM)
                                st.rerun()
                        else:
                            st.error(f"❌ {errore}")

    elif st.session_state.login_tab_attivo == "reset":
        st.markdown("#### Reset Password via Email")
        st.markdown("""
            <style>
            /* Bottoni reset: larghezza auto, Invia Codice azzurro */
            div.st-key-reset_btn_invia button {
                width: auto !important;
                min-width: unset !important;
                background-color: #0ea5e9 !important;
                color: white !important;
            }
            div.st-key-reset_btn_invia button:hover {
                background-color: #0284c7 !important;
            }
            div.st-key-reset_btn_conferma button {
                width: auto !important;
                min-width: unset !important;
            }
            </style>
        """, unsafe_allow_html=True)

        reset_email = st.text_input("📧 Email per reset", placeholder="tua@email.com", key="reset_email")

        with st.container(key="reset_btn_invia"):
            if st.button("📨 Invia Codice"):
                if not reset_email:
                    st.warning("⚠️ Inserisci un'email")
                else:
                    success, msg = invia_codice_reset(reset_email)
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                        st.info(f"ℹ️ {msg}")

        st.markdown("---")

        code_input = st.text_input("🔢 Codice ricevuto", placeholder="Inserisci il codice", key="code_input")
        new_pwd = st.text_input("🔑 Nuova password (min 10 caratteri)", type="password", key="new_pwd")
        confirm_pwd = st.text_input("🔑 Conferma password", type="password", key="confirm_pwd")

        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        with st.container(key="reset_btn_conferma"):
            if st.button("✅ Conferma Reset", type="primary"):
                if not reset_email or not code_input or not new_pwd or not confirm_pwd:
                    st.warning("⚠️ Compila tutti i campi")
                elif new_pwd != confirm_pwd:
                    st.error("❌ Le password non coincidono")
                else:
                    from services.auth_service import valida_password_compliance
                    errori = valida_password_compliance(new_pwd, reset_email)
                    if errori:
                        for e in errori:
                            st.error(f"❌ {e}")
                    else:
                        successo, messaggio, user = imposta_password_da_token(code_input, new_pwd)
                    
                        if successo and user:
                            st.session_state.logged_in = True
                            st.session_state.user_data = user
                            st.session_state.force_logout = False
                            st.session_state.pop('login_tab_attivo', None)
                            if _cookie_manager is not None:
                                try:
                                    _now_utc = datetime.now(timezone.utc)
                                    _s_token = _secrets.token_urlsafe(32)
                                    supabase.table('users').update({
                                        'session_token': _s_token,
                                        'session_token_created_at': _now_utc.isoformat(),
                                        'last_seen_at': _now_utc.isoformat(),
                                    }).eq('id', user.get('id')).execute()
                                    _cookie_manager.set("session_token", _s_token,
                                                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                                                        secure=True, same_site="strict")
                                    st.session_state._last_seen_write_at = _now_utc.isoformat()
                                except Exception:
                                    pass
                            else:
                                st.warning(
                                    "⚠️ Sessione non persistente: "
                                    "verifica che i cookie siano abilitati nel browser. "
                                    "Verrai disconnesso ad ogni aggiornamento pagina."
                                )
                            st.success("✅ Password aggiornata! Accesso automatico...")
                            time.sleep(UI_DELAY_LONG)
                            st.rerun()
                        else:
                            st.error(f"❌ {messaggio}")


# ============================================================
# CHECK LOGIN ALL'AVVIO
# ============================================================
# (logged_in già inizializzato sopra — riga ~262)

# VERIFICA FINALE: se force_logout è attivo, FORZA logged_in = False
if st.session_state.get('force_logout', False):
    logger.critical("⛔ force_logout attivo - forzando logged_in=False")
    st.session_state.logged_in = False
    st.session_state.user_data = None

# Se NON loggato, mostra login e STOP
if not st.session_state.get('logged_in', False):
    logger.info("👤 Utente non loggato - mostrando pagina login")
    st.session_state._rerun_guard = 0
    mostra_pagina_login()
    st.stop()

# Se arrivi qui, sei loggato! Vai DIRETTO ALL'APP
user = st.session_state.user_data

# ULTIMA VERIFICA: se user_data è None o invalido, FORZA logout immediato
if not user or not user.get('email'):
    logger.critical("❌ user_data è None o mancante email - FORZA LOGOUT")
    if _cookie_manager is not None:
        try:
            # Invalida token nel DB prima di pulire la sessione
            _email_emergency = st.session_state.get('user_data', {}).get('email') if st.session_state.get('user_data') else None
            if _email_emergency:
                supabase.table('users').update({
                    'session_token': None,
                    'session_token_created_at': None,
                    'last_seen_at': None,
                }).eq('email', _email_emergency).execute()
        except Exception:
            pass
    st.session_state.clear()
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.rerun()


# ============================================
# VERIFICA E RIPRISTINO FLAG ADMIN
# ============================================
# Ripristina flag admin se l'utente è in ADMIN_EMAILS
# (necessario perché session_state viene perso al refresh della pagina)
if (user.get('email') or '').strip().lower() in ADMIN_EMAILS:
    if not st.session_state.get('user_is_admin', False):
        st.session_state.user_is_admin = True
        logger.info(f"✅ Flag admin ripristinato per user_id={user.get('id')}")
else:
    # Assicura che non-admin non abbiano il flag
    if st.session_state.get('user_is_admin', False):
        st.session_state.user_is_admin = False
        logger.warning(f"⚠️ Flag admin rimosso per utente non-admin: user_id={user.get('id')}")


# ============================================
# RIPRISTINO IMPERSONAZIONE DA COOKIE (dopo F5/refresh)
# ============================================
# Se l'admin è loggato ma non sta impersonando, controlla se c'era
# un'impersonazione attiva prima del refresh e ripristinala.
if (st.session_state.get('user_is_admin', False)
        and not st.session_state.get('impersonating', False)
        and _cookie_manager is not None):
    try:
        _imp_uid_cookie = _cookie_manager.get("impersonation_user_id")
        if _imp_uid_cookie:
            _imp_resp = supabase.table("users") \
                .select("id, email, nome_ristorante, attivo, pagine_abilitate") \
                .eq("id", _imp_uid_cookie).eq("attivo", True).execute()
            if _imp_resp and _imp_resp.data:
                _imp_customer = _imp_resp.data[0]
                # Salva dati admin originali e passa a quelli del cliente
                st.session_state.admin_original_user = st.session_state.user_data.copy()
                st.session_state.user_data = {
                    'id': _imp_customer['id'],
                    'email': _imp_customer['email'],
                    'nome_ristorante': _imp_customer.get('nome_ristorante'),
                    'attivo': _imp_customer.get('attivo', True),
                    'pagine_abilitate': _imp_customer.get('pagine_abilitate'),
                }
                st.session_state.user_is_admin = False
                st.session_state.impersonating = True
                # Preserva il timestamp originale se già presente (evita reset timer ad ogni F5)
                if not st.session_state.get('impersonation_started_at'):
                    st.session_state.impersonation_started_at = datetime.now(timezone.utc).isoformat()
                # Aggiorna variabile locale user per il resto della pagina
                user = st.session_state.user_data
                logger.info(f"✅ Impersonazione ripristinata da cookie dopo refresh: user_id={_imp_customer.get('id')}")
            else:
                # Cliente non trovato (disattivato o cancellato) → pulisci il cookie
                _cookie_manager.set("impersonation_user_id", "",
                                    expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                logger.warning(f"⚠️ Cliente impersonato non trovato (id={_imp_uid_cookie}) - cookie rimosso")
    except Exception as _imp_e:
        logger.warning(f"Errore ripristino impersonazione da cookie: {_imp_e}")


# ============================================
# CARICAMENTO RISTORANTI (MULTI-RISTORANTE STEP 2)
# ============================================
# Carica ristoranti dell'utente (oppure TUTTI i ristoranti se admin)
# ⚠️ SAFETY CHECK: Verifica che user sia definito (dovrebbe essere già controllato sopra)
if not user or not user.get('id'):
    logger.error("❌ ERRORE CRITICO: user non definito in caricamento ristoranti")
    st.session_state.logged_in = False
    st.session_state.force_logout = True
    st.session_state._cookie_checked = True
    st.rerun()

_is_pure_admin_session = st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False)

if _is_pure_admin_session:
    try:
        admin_workspace = ensure_admin_test_workspace(supabase, user)
        st.session_state.ristoranti = [admin_workspace] if admin_workspace else []

        if admin_workspace:
            st.session_state.ristorante_id = admin_workspace['id']
            st.session_state.partita_iva = admin_workspace.get('partita_iva')
            st.session_state.nome_ristorante = admin_workspace.get('nome_ristorante') or 'Ambiente Test Admin'
            logger.info(f"🧪 Admin workspace test attivo: rist_id={admin_workspace['id']}")
        else:
            logger.warning("⚠️ Nessun workspace test admin disponibile")
            st.session_state.pop('ristorante_id', None)
            st.session_state.partita_iva = None
            st.session_state.nome_ristorante = 'Ambiente Test Admin'
    except Exception as e:
        logger.exception(f"Errore setup workspace test admin: {e}")
        st.session_state.ristoranti = []
        st.session_state.pop('ristorante_id', None)
        st.session_state.partita_iva = None
        st.session_state.nome_ristorante = 'Ambiente Test Admin'
elif 'ristoranti' not in st.session_state or not st.session_state.get('ristorante_id'):
    try:
        # Utente normale o admin in impersonificazione: carica solo i ristoranti del profilo attivo
        ristoranti = supabase.table('ristoranti')\
            .select('id, nome_ristorante, partita_iva, ragione_sociale')\
            .eq('user_id', user.get('id'))\
            .eq('attivo', True)\
            .execute()
        
        logger.info(f"🔍 DEBUG: Caricati {len(ristoranti.data) if ristoranti.data else 0} ristoranti per user_id={user.get('id')}")
        st.session_state.ristoranti = ristoranti.data if ristoranti.data else []
        
        # Se ha ristoranti, imposta il default
        if st.session_state.ristoranti:
            # Se non c'è un ristorante selezionato, usa l'ultimo usato (se ancora disponibile)
            if 'ristorante_id' not in st.session_state:
                ultimo_id = user.get('ultimo_ristorante_id')
                ristorante_default = None
                if ultimo_id:
                    ristorante_default = next(
                        (r for r in st.session_state.ristoranti if r['id'] == ultimo_id), None
                    )
                if ristorante_default is None:
                    ristorante_default = st.session_state.ristoranti[0]
                st.session_state.ristorante_id = ristorante_default['id']
                st.session_state.partita_iva = ristorante_default['partita_iva']
                st.session_state.nome_ristorante = ristorante_default['nome_ristorante']
                logger.info(f"🏢 Ristorante caricato: rist_id={ristorante_default['id']}{' [ultimo usato]' if ultimo_id and ristorante_default['id'] == ultimo_id else ' [primo in lista]'}")
        else:
            # ⚠️ UTENTE LEGACY: Nessun ristorante trovato
            if not st.session_state.get('user_is_admin', False):
                piva = user.get('partita_iva')
                nome = user.get('nome_ristorante')
                user_id = user.get('id')
                
                # Tenta creazione automatica ristorante se ha P.IVA
                if piva and user_id:
                    logger.warning(f"⚠️ Utente legacy {user_id} senza ristoranti - tentativo creazione automatica")
                    logger.warning(f"   Dati: nome='{nome}', piva=***{piva[-4:] if piva and len(piva) >= 4 else '????'}")
                    try:
                        # Cerca ristorante con questa P.IVA DELLO STESSO UTENTE
                        check_existing = supabase.table('ristoranti')\
                            .select('id, user_id, nome_ristorante')\
                            .eq('partita_iva', piva)\
                            .eq('user_id', user_id)\
                            .execute()
                        
                        if check_existing.data and len(check_existing.data) > 0:
                            # È il suo ristorante, usalo
                            existing = check_existing.data[0]
                            st.session_state.ristoranti = [existing]
                            st.session_state.ristorante_id = existing['id']
                            st.session_state.partita_iva = piva
                            st.session_state.nome_ristorante = existing['nome_ristorante']
                            logger.info(f"✅ Ristorante esistente trovato e collegato: {existing['id']}")
                        else:
                            # Non esiste, crea nuovo
                            nome_rist = nome or f"Ristorante {piva}"
                            new_rist = supabase.table('ristoranti').insert({
                                'user_id': user_id,
                                'nome_ristorante': nome_rist,
                                'partita_iva': piva,
                                'ragione_sociale': user.get('ragione_sociale', ''),
                                'attivo': True
                            }).execute()
                            
                            if new_rist.data:
                                st.session_state.ristoranti = new_rist.data
                                st.session_state.ristorante_id = new_rist.data[0]['id']
                                st.session_state.partita_iva = piva
                                st.session_state.nome_ristorante = nome
                                logger.info(f"✅ Ristorante creato automaticamente: {new_rist.data[0]['id']}")
                                st.success("✅ Account configurato correttamente!")
                                st.rerun()  # Ricarica per applicare i cambiamenti
                            else:
                                logger.error(f"❌ Creazione ristorante fallita per utente {user_id} - response vuota")
                                st.warning("⚠️ Configurazione account incompleta. Alcune funzionalità potrebbero non essere disponibili.")
                    except Exception as create_err:
                        logger.error(f"❌ ERRORE DETTAGLIATO creazione ristorante: {str(create_err)}")
                        logger.error(f"   Tipo errore: {type(create_err).__name__}")
                        # Non bloccare con st.stop(), permetti accesso all'app
                        st.warning(f"⚠️ Problemi di configurazione rilevati: {str(create_err)[:100]}")
                else:
                    # Nessuna P.IVA o dati mancanti - permetti comunque l'accesso
                    logger.warning(f"⚠️ Utente {user_id} senza ristoranti e dati incompleti - accesso limitato")
                    st.warning("⚠️ Configurazione account incompleta. Contatta l'assistenza per configurare il tuo ristorante.")
            
            # FALLBACK vecchio codice per compatibilità
            # ⚠️ Solo se ristoranti NON è stato popolato dalle operazioni sopra
            if not st.session_state.get('user_is_admin', False) and not st.session_state.get('ristoranti'):
                piva = user.get('partita_iva')
                nome = user.get('nome_ristorante')
                
                logger.warning(f"⚠️ Utente {user.get('email')} senza ristoranti in tabella - fallback su dati users")
                
                # Imposta dati di fallback dalla tabella users
                st.session_state.partita_iva = piva
                st.session_state.nome_ristorante = nome
            elif st.session_state.get('user_is_admin', False) and not st.session_state.get('ristoranti'):
                # Admin senza ristoranti nel sistema
                logger.warning(f"⚠️ Admin senza ristoranti nel sistema")
    except Exception as e:
        logger.exception(f"Errore caricamento ristoranti: {e}")
        # Fallback: usa dati utente (solo per non-admin)
        if not st.session_state.get('user_is_admin', False):
            st.session_state.ristoranti = []
            st.session_state.partita_iva = user.get('partita_iva')
            st.session_state.nome_ristorante = user.get('nome_ristorante')


# ============================================
# ADMIN PURO: ACCESSO APP SENZA RESTRIZIONI
# ============================================
if st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False):
    logger.info(f"👨‍💼 Admin user_id={user.get('id')} in modalità unrestricted su app.py")

# ============================================
# TRIAL: VERIFICA SCADENZA + CARICA INFO
# ============================================
# Solo per utenti normali (non admin, non impersonazione da admin)
if (
    not st.session_state.get('user_is_admin', False)
    and not st.session_state.get('impersonating', False)
    and user.get('id')
):
    _t_uid = user['id']
    _t_now = datetime.now(timezone.utc)
    _t_last_raw = st.session_state.get('_trial_check_at')

    # Forza refresh anche se il TTL non è scaduto ma il mese in cache
    # non corrisponde al mese corrente (es. cache rimasta da sessione precedente).
    _cached_ti = st.session_state.get('trial_info', {})
    _cached_month = _cached_ti.get('trial_month')
    _current_month = _t_now.month
    _month_mismatch = (
        _cached_ti.get('is_trial') and
        _cached_month is not None and
        _cached_month != _current_month
    )

    _t_needs_refresh = (
        'trial_info' not in st.session_state
        or not _t_last_raw
        or _month_mismatch
        or (_t_now - datetime.fromisoformat(
            str(_t_last_raw).replace('Z', '+00:00')
        )).total_seconds() > 300
    )
    if _t_needs_refresh:
        from services.auth_service import get_trial_info as _get_ti, disattiva_trial_scaduta as _dis_ti
        _fresh_ti = _get_ti(_t_uid, supabase)
        st.session_state.trial_info = _fresh_ti
        st.session_state._trial_check_at = _t_now.isoformat()
        if _fresh_ti.get('expired'):
            _ok_dis = _dis_ti(_t_uid, supabase)
            if not _ok_dis:
                logger.error(
                    f"⚠️ disattiva_trial_scaduta FALLITA per user_id={_t_uid} "
                    f"— logout forzato comunque, il DB verrà aggiornato al prossimo tentativo"
                )
            try:
                supabase.table('users').update({
                    'session_token': None,
                    'session_token_created_at': None,
                }).eq('id', _t_uid).execute()
            except Exception as _tok_err:
                logger.error(f"Errore invalidazione session_token per trial scaduta: {_tok_err}")
            st.session_state.clear()
            st.session_state.logged_in = False
            st.session_state._trial_expired_msg = True
            logger.warning(f"⏰ Trial scaduta → logout forzato: user_id={_t_uid} (disattivazione_ok={_ok_dis})")
            st.rerun()
else:
    # Admin o sessione impersonazione: nessuna restrizione trial.
    # Sovrascriviamo SEMPRE (non solo se assente) per evitare che un trial_info
    # residuo da una sessione precedente appaia su un nuovo giro di impersonazione.
    st.session_state.trial_info = {
        'is_trial': False, 'days_left': 0,
        'trial_month': None, 'trial_year': None, 'expired': False,
    }

# ============================================
# BANNER IMPERSONAZIONE (solo per admin che impersonano)
# ============================================

if st.session_state.get('impersonating', False):
    # Banner visibile quando l'admin sta impersonando un cliente
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f59e0b 0%, #dc2626 100%); 
                padding: clamp(0.75rem, 2vw, 1rem); 
                border-radius: 10px; 
                margin-bottom: 1.25rem; 
                text-align: center;
                border: 3px solid #dc2626;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
        <h3 style="color: white; margin: 0; font-size: clamp(1rem, 2.5vw, 1.25rem);">
            ⚠️ MODALITÀ IMPERSONAZIONE
        </h3>
        <p style="color: #fef3c7; margin: 0.625rem 0 0 0; font-size: clamp(0.875rem, 2vw, 1rem); word-wrap: break-word;">
            Stai visualizzando l'account di: <strong>{_html.escape(user.get('nome_ristorante', 'Cliente'))}</strong> ({_html.escape(user.get('email', ''))})
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Bottone "Torna Admin" in colonna separata
    col_back_admin, col_spacer = st.columns([2, 8])
    with col_back_admin:
        if st.button("🔙 Torna Admin", type="primary", use_container_width=True, key="back_to_admin_btn"):
            # Ripristina dati admin originali
            if 'admin_original_user' in st.session_state:
                _imp_client_email_end = st.session_state.get('user_data', {}).get('email', '?')
                st.session_state.user_data = st.session_state.admin_original_user.copy()
                del st.session_state.admin_original_user
                st.session_state.impersonating = False
                
                # Ripristina flag admin
                st.session_state.user_is_admin = True
                
                # 🏢 RIPRISTINA RISTORANTI ADMIN (tutti i ristoranti del sistema)
                try:
                    ristoranti_admin = supabase.table('ristoranti')\
                        .select('id, nome_ristorante, partita_iva, ragione_sociale, user_id')\
                        .eq('attivo', True)\
                        .order('nome_ristorante')\
                        .execute()
                    
                    st.session_state.ristoranti = ristoranti_admin.data if ristoranti_admin.data else []
                    
                    # Rimuovi ristorante_id specifico (admin vede tutti i ristoranti)
                    if st.session_state.get('ristorante_id'):
                        del st.session_state.ristorante_id
                    if 'partita_iva' in st.session_state:
                        del st.session_state.partita_iva
                    if 'nome_ristorante' in st.session_state:
                        del st.session_state.nome_ristorante
                    
                    logger.info(f"🔙 ADMIN: Ripristinati {len(st.session_state.ristoranti)} ristoranti del sistema")
                except Exception as e:
                    logger.error(f"Errore ripristino ristoranti admin: {e}")
                
                # Log uscita impersonazione con durata
                _imp_duration_min = '?'
                _imp_started_end = st.session_state.get('impersonation_started_at')
                if _imp_started_end:
                    try:
                        _imp_s_dt = datetime.fromisoformat(str(_imp_started_end).replace('Z', '+00:00'))
                        if _imp_s_dt.tzinfo is None:
                            _imp_s_dt = _imp_s_dt.replace(tzinfo=timezone.utc)
                        _imp_duration_min = int((datetime.now(timezone.utc) - _imp_s_dt).total_seconds() / 60)
                    except (ValueError, TypeError):
                        pass
                st.session_state.pop('impersonation_started_at', None)
                logger.info(f"🔒 IMPERSONATION END: admin={st.session_state.user_data.get('email')} → client={_imp_client_email_end} duration={_imp_duration_min}min")
                
                # Rimuovi cookie impersonazione (non deve più sopravvivere al refresh)
                if _cookie_manager is not None:
                    try:
                        _cookie_manager.set("impersonation_user_id", "",
                                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    except Exception:
                        pass
                
                # Redirect al pannello admin
                st.switch_page("pages/admin.py")
                st.stop()
            else:
                st.error("⚠️ Errore: dati admin originali non trovati")
                st.session_state.impersonating = False
                if _cookie_manager is not None:
                    try:
                        _cookie_manager.set("impersonation_user_id", "",
                                            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc))
                    except Exception:
                        pass
                st.rerun()
    
    st.markdown("---")


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

auto_notice = st.session_state.get('auto_invoice_notice')
_is_admin_session = (_sess_email or '').strip().lower() in ADMIN_EMAILS

if not _is_admin_session:
    try:
        auto_notice = riepilogo_fatture_auto_da_ultimo_login(
            user_id=st.session_state.get('user_data', {}).get('id'),
            last_login_precedente=st.session_state.get('user_data', {}).get('last_login_precedente'),
            login_at=st.session_state.get('user_data', {}).get('login_at'),
            supabase_client=supabase,
        )
        if auto_notice.get('has_new'):
            st.session_state.auto_invoice_notice = auto_notice
            st.session_state.auto_invoice_notice_dismissed = False
            st.session_state.auto_received_file_origini = {
                f['file_name'] for f in auto_notice.get('files_detail', [])
            }
        else:
            st.session_state.pop('auto_invoice_notice', None)
            st.session_state.pop('auto_invoice_notice_dismissed', None)
            st.session_state.pop('auto_received_file_origini', None)
        auto_notice = st.session_state.get('auto_invoice_notice')
    except Exception as _dashboard_notice_err:
        logger.warning(f"Errore refresh notifica fatture automatiche: {_dashboard_notice_err}")

operational_notifications = []
if not _is_admin_session:
    operational_notifications = build_monthly_data_notifications(
        user_id=st.session_state.get('user_data', {}).get('id'),
        ristorante_id=st.session_state.get('ristorante_id'),
        reference_dt=datetime.now(timezone.utc),
    )
    operational_notifications.extend(
        build_upload_outcome_notifications(
            st.session_state.get('last_upload_notification_context')
        )
    )
    operational_notifications.extend(
        build_upload_quality_notifications(
            st.session_state.get('last_upload_notification_context')
        )
    )
    operational_notifications.extend(
        build_price_alert_notifications(
            st.session_state.get('last_upload_notification_context'),
            threshold_pct=5.0,
        )
    )
    operational_notifications.extend(
        build_credit_note_notifications(
            st.session_state.get('last_upload_notification_context')
        )
    )
    operational_notifications.extend(
        build_td24_date_notifications(
            st.session_state.get('last_upload_notification_context')
        )
    )

# Stato file gestiti (salvati/rifiutati) — persistente durante la sessione
if 'auto_invoice_handled' not in st.session_state:
    st.session_state.auto_invoice_handled = set()

st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-top: 0.5rem;">
    🧠 <span style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;">Analisi Fatture AI</span>
</h2>
<div style='padding: 4px 14px 0; font-size: 0.88rem; color: #1e2a4a; font-weight: 500; margin-bottom: 1.5rem;'>
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
<div style="background:linear-gradient(135deg,#fef9c3,#fef08a);border:2px solid {_tb_color};
            border-radius:10px;padding:12px 18px;margin-bottom:1rem;
            display:flex;align-items:center;gap:12px;">
    <span style="font-size:1.6rem;">⏳</span>
    <div>
        <strong style="color:{_tb_color};font-size:1rem;">
            Prova gratuita attiva &mdash; Rimangono {_tb_days} giorni
        </strong><br>
        <span style="color:#92400e;font-size:0.85rem;">
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
        st.markdown('<h3 style="color:#1e3a5f;font-weight:700;">🏢 Seleziona Ristorante da Gestire</h3>', unsafe_allow_html=True)
        
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
        <div style='padding: 8px 14px; font-size: 0.88rem; color: #1e3a5f; font-weight: 500;'>
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
                               '_fonte_pm_cache']:
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

    _current_user_id = st.session_state.get('user_data', {}).get('id')
    _current_ristorante_id = st.session_state.get('ristorante_id')
    _dismissed_notification_ids = set()
    if _current_user_id and not _is_admin_session:
        _dismissed_notification_ids = get_dismissed_notification_ids(_current_user_id, supabase)

    _visible_operational_notifications = []
    for notification in operational_notifications:
        _scoped_id = build_scoped_notification_id(notification.get('id'), _current_ristorante_id)
        if _scoped_id in _dismissed_notification_ids:
            continue
        _visible_operational_notifications.append({**notification, 'id': _scoped_id})

    if _visible_operational_notifications:
        _render_operational_notifications(
            notifications=_visible_operational_notifications,
            user_id=_current_user_id,
            dismissed_ids=_dismissed_notification_ids,
            supabase_client=supabase,
        )

    if not _is_admin_session:
        _render_auto_invoice_notice(
            auto_notice=auto_notice,
            user_id=_current_user_id,
            dismissed_ids=_dismissed_notification_ids,
            supabase_client=supabase,
            ristorante_id=_current_ristorante_id,
        )

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
    if not df_cache.empty:
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
    except Exception:
        pass

    # ============================================================
    # LAYOUT: FILE UPLOADER + AI INFO/BUTTON AFFIANCATI
    # ============================================================
    with st.container(key="main_documents_upload_section"):
        _is_pure_admin_upload = st.session_state.get('user_is_admin', False) and not st.session_state.get('impersonating', False)
        _documents_warning_html = (
            "🧪 <strong>AMBIENTE TEST ADMIN:</strong> puoi caricare documenti liberamente per prove, training AI e categorizzazione."
            if _is_pure_admin_upload
            else "⚠️ <strong>IMPORTANTE:</strong> Le fatture caricate devono corrispondere alla P.IVA del ristorante mostrato sopra! <strong>Altrimenti verranno scartate</strong>"
        )

        st.markdown(f"""
        <div class="documents-header-row">
            <div class="documents-title">📄 Documenti</div>
            <div class="documents-warning">
                {_documents_warning_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <style>
        div.st-key-main_documents_upload_section .documents-header-row {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.5rem 1rem;
            padding: 0 0 12px 0;
        }
        div.st-key-main_documents_upload_section .documents-title {
            font-size: 2.25rem;
            font-weight: 700;
            color: #1f4e8c;
            line-height: 1.2;
        }
        div.st-key-main_documents_upload_section .documents-warning {
            font-size: 0.88rem;
            color: #166534;
            font-weight: 500;
            line-height: 1.4;
        }
        /* upload_hint_row: forza tutti i wrapper Streamlit a restringersi al contenuto */
        div.st-key-upload_hint_row {
            display: inline-flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 0.55rem !important;
            flex-wrap: nowrap !important;
            width: auto !important;
            max-width: 100% !important;
        }
        div.st-key-upload_hint_row > div,
        div.st-key-upload_hint_row > div > div {
            width: fit-content !important;
            max-width: fit-content !important;
            flex: 0 0 auto !important;
            min-width: 0 !important;
        }
        div.st-key-upload_hint_row > div:last-child,
        div.st-key-upload_hint_row > div:last-child > div {
            width: auto !important;
            max-width: none !important;
        }
        div.st-key-main_documents_upload_section .upload-format-hint {
            color: #2d6a4f;
            font-size: clamp(0.8rem, 0.3vw + 0.74rem, 0.9rem);
            font-weight: 600;
            line-height: 1.3;
            white-space: nowrap;
            margin: 0 !important;
        }
        div.st-key-main_documents_upload_section .upload-ai-spacer {
            height: 34px;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] {
            margin: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] > div,
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] > div > div,
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] section,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"],
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] > div {
            width: fit-content !important;
            max-width: fit-content !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] section {
            display: inline-flex !important;
            align-items: center !important;
            padding: 0 !important;
            min-height: 0 !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] {
            display: inline-flex !important;
            align-items: center !important;
            padding: 0 !important;
            min-height: 0 !important;
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzoneInstructions"] {
            visibility: hidden !important;
            position: absolute !important;
            width: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] > div {
            width: auto !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button {
            min-width: 12.5rem !important;
            height: 2.9rem !important;
            min-height: 2.9rem !important;
            padding: 0.72rem 1.05rem !important;
            border-radius: 10px !important;
            border: 1px solid #2d6a4f !important;
            background-color: #2d6a4f !important;
            color: transparent !important;
            box-shadow: none !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            position: relative !important;
            overflow: hidden !important;
            transform: none !important;
            line-height: 1 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button > * {
            opacity: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button p,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button span,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button div {
            font-size: 0 !important;
            line-height: 0 !important;
            margin: 0 !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button::after {
            content: "📄 Carica Documenti" !important;
            position: absolute !important;
            left: 50% !important;
            top: 50% !important;
            transform: translate(-50%, -50%) !important;
            width: max-content !important;
            text-align: center !important;
            font-size: clamp(0.85rem, 0.4vw + 0.75rem, 1rem) !important;
            line-height: 1.1 !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            pointer-events: none !important;
        }
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button:hover,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button:focus,
        div.st-key-main_documents_upload_section [data-testid="stFileUploaderDropzone"] button:active {
            border-color: #1f513b !important;
            background-color: #1f513b !important;
            color: transparent !important;
            transform: none !important;
        }
        @media (max-width: 767px) {
            div.st-key-main_documents_upload_section .upload-format-hint {
                min-height: auto;
                padding-top: 0.15rem;
            }
            div.st-key-main_documents_upload_section .upload-ai-spacer {
                height: 12px;
            }
        }
        </style>
        """, unsafe_allow_html=True)

        col_upload, col_ai_right = st.columns([3, 2])

        with col_upload:
            with st.container(key="upload_hint_row"):
                uploaded_files = st.file_uploader(
                    "Carica file",
                    accept_multiple_files=True,
                    type=['xml', 'p7m', 'pdf', 'jpg', 'jpeg', 'png'],
                    label_visibility="collapsed",
                    key=f"file_uploader_{st.session_state.get('uploader_key', 0)}"
                )
                if uploaded_files and len(uploaded_files) > 0:
                    st.markdown(
                        """
                        <style>
                        div.st-key-main_documents_upload_section [data-testid="stFileUploader"] {
                            visibility: hidden !important;
                            height: 0 !important;
                            min-height: 0 !important;
                            margin: 0 !important;
                            padding: 0 !important;
                            overflow: hidden !important;
                            pointer-events: none !important;
                        }
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )
                st.markdown(
                    "<div class='upload-format-hint'>Formati accettati: XML, P7M, PDF, PNG, JPG, JPEG · Max 200MB</div>",
                    unsafe_allow_html=True,
                )

        with col_ai_right:
            st.markdown("<div class='upload-ai-spacer'></div>", unsafe_allow_html=True)
    
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

    # ============================================================
    # INIZIALIZZAZIONE SET ERRORI (prevenzione loop)
    # ============================================================
    if 'files_con_errori' not in st.session_state:
        st.session_state.files_con_errori = set()

    # Bottone Reset Upload (solo admin)
    if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
        if st.button("🔄 Ripristina upload (pulisci cache sessione)", key="reset_upload_cache"):
            st.session_state.files_processati_sessione = set()
            st.session_state.files_con_errori = set()
            st.session_state.files_errori_report = {}
            # 🔥 Rimuovi flag force_empty per sbloccare caricamento
            if 'force_empty_until_upload' in st.session_state:
                del st.session_state.force_empty_until_upload
            st.success("✅ Cache pulita! Puoi ricaricare i file.")
            st.rerun()

    if not df_cache.empty:
        st.markdown("""
        <style>
        /* Expander Gestione Fatture - sfondo verde chiaro */
        div.st-key-expander_gestione_fatture [data-testid="stExpander"] details summary {
            background: linear-gradient(135deg, rgba(220, 252, 231, 0.96) 0%, rgba(187, 247, 208, 0.96) 100%) !important;
            border-radius: 8px !important;
            padding: 10px 14px !important;
            color: #166534 !important;
            font-weight: 600 !important;
            border: 1px solid #86efac !important;
        }
        div.st-key-expander_gestione_fatture [data-testid="stExpander"] details {
            background: rgba(240, 253, 244, 0.95) !important;
            border: 1px solid #86efac !important;
            border-radius: 8px !important;
        }
        div.st-key-expander_gestione_fatture [data-testid="stExpander"] details[open] summary {
            border-bottom: 1px solid #86efac !important;
            border-radius: 8px 8px 0 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        with st.container(key="expander_gestione_fatture"):
          with st.expander("🗂️ Apri per gestire le Fatture Caricate (Elimina)", expanded=False):
            
            # ========================================
            # BOX STATISTICHE
            # ========================================
            try:
                stats_db = get_fatture_stats(user_id, st.session_state.get('ristorante_id'))
            except Exception as e:
                logger.error(f"Errore get_fatture_stats: {e}")
                st.error("❌ Errore caricamento statistiche")
                stats_db = {'num_uniche': 0, 'num_righe': 0, 'success': False}

            num_fatture_xml_p7m = 0
            num_altri_documenti = 0
            if 'FileOrigine' in df_cache.columns:
                file_unici = {
                    str(file_name).strip()
                    for file_name in df_cache['FileOrigine'].dropna().unique().tolist()
                    if str(file_name).strip()
                }
                estensioni_fatture = {'.xml', '.p7m'}
                num_fatture_xml_p7m = sum(
                    1 for file_name in file_unici
                    if os.path.splitext(file_name)[1].lower() in estensioni_fatture
                )
                num_altri_documenti = len(file_unici) - num_fatture_xml_p7m

            # Conta note di credito (TD04) dai file unici in df_cache
            num_note_credito = 0
            if 'TipoDocumento' in df_cache.columns and 'FileOrigine' in df_cache.columns:
                num_note_credito = df_cache[df_cache['TipoDocumento'].str.upper().str.strip() == 'TD04']['FileOrigine'].nunique()
            note_credito_html = f' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #FF5500;">{num_note_credito:,}</strong>' if num_note_credito > 0 else ' | 📝 Note di Credito: <strong style="font-size: 1.2em; color: #FF5500;">0</strong>'
            altri_documenti_html = f' | 📎 Altri Documenti: <strong style="font-size: 1.2em; color: #FF5500;">{num_altri_documenti:,}</strong>'
            st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, rgba(22, 101, 52, 0.18) 0%, rgba(21, 128, 61, 0.24) 100%);
        padding: clamp(0.75rem, 1.8vw, 0.9rem) clamp(0.9rem, 2.5vw, 1.4rem);
        border-radius: 10px;
        border-left: 5px solid rgba(21, 128, 61, 0.55);
        box-shadow: 0 3px 6px rgba(22, 101, 52, 0.16);
        margin: 0 0 20px 0;
        display: block;
        width: min(100%, 44rem);
        min-width: 0;
        box-sizing: border-box;
        backdrop-filter: blur(10px);
    ">
        <span style="color: #14532d; font-size: clamp(0.95rem, 1.3vw, 1.05rem); font-weight: 700; line-height: 1.45; overflow-wrap: anywhere;">
            📊 Fatture: <strong style="font-size: 1.2em; color: #166534;">{num_fatture_xml_p7m:,}</strong>{note_credito_html}{altri_documenti_html} | 
            📋 Righe Totali: <strong style="font-size: 1.2em; color: #166534;">{stats_db["num_righe"]:,}</strong>
        </span>
    </div>
    """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Raggruppa per file origine per creare summary
            _agg_dict = {
                'Fornitore': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],
                'TotaleRiga': 'sum',
                'NumeroRiga': 'count',
                'DataDocumento': 'first'
            }
            if 'CreatedAt' in df_cache.columns:
                _agg_dict['CreatedAt'] = 'max'
            fatture_summary = df_cache.groupby('FileOrigine').agg(_agg_dict).reset_index()
            
            # 🔧 FIX: Reset index prima di rinominare (già fatto ma assicuriamo drop=True)
            fatture_summary = fatture_summary.reset_index(drop=True)
            
            if 'CreatedAt' in fatture_summary.columns:
                fatture_summary.columns = ['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data', 'CreatedAt']
                fatture_summary = fatture_summary.sort_values('CreatedAt', ascending=False)
            else:
                fatture_summary.columns = ['File', 'Fornitore', 'Totale', 'NumProdotti', 'Data']
                fatture_summary = fatture_summary.sort_values('Data', ascending=False)
            
            # 🔍 DEBUG TOOL: Rimosso - Usa Upload Events in Admin Panel per diagnostica
            
            # 🗑️ PULSANTE SVUOTA TUTTO (solo admin/impersonificati - nessuna conferma richiesta)
            if st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False):
                st.markdown("### 🗑️ Eliminazione Massiva")
                
                if st.button(
                    "🗑️ ELIMINA TUTTO",
                    type="primary",
                    use_container_width=True,
                    key="btn_svuota_definitivo"
                ):
                        with st.spinner("🗑️ Eliminazione in corso..."):
                            # Progress bar per UX
                            progress = st.progress(0)
                            progress.progress(20, text="Eliminazione da Supabase...")
                            
                            result = elimina_tutte_fatture(user_id, ristoranteid=st.session_state.get('ristorante_id'))
                            
                            # 🔥 INVALIDAZIONE CACHE: Forza reload dati dopo eliminazione
                            invalida_cache_memoria()  # Reset memoria AI
                            
                            # 🔥 RESET SESSION: Reinizializza set vuoti (non solo clear)
                            st.session_state.files_processati_sessione = set()
                            st.session_state.files_con_errori = set()
                            
                            progress.progress(40, text="Pulizia file JSON locali...")
                            
                            # HARD RESET: Elimina file JSON obsoleti
                            json_files = ['fattureprocessate.json', 'fatture.json', 'data.json']
                            for json_file in json_files:
                                if os.path.exists(json_file):
                                    try:
                                        os.remove(json_file)
                                        logger.info(f"🗑️ Rimosso file JSON obsoleto: {json_file}")
                                    except Exception as e:
                                        logger.warning(f"⚠️ Impossibile rimuovere {json_file}: {e}")
                            
                            progress.progress(60, text="Pulizia cache Streamlit...")
                            
                            # HARD RESET: Pulisci TUTTE le cache
                            st.cache_data.clear()
                            try:
                                st.cache_resource.clear()
                            except Exception as e:
                                logger.warning(f"⚠️ Errore clear cache_resource durante hard reset: {e}")
                            
                            progress.progress(80, text="Ripristino sessione...")
                            
                            # HARD RESET: Rimuovi session state specifici
                            # 🔧 FIX: Preserva chiavi impersonazione e contesto ristorante
                            #          per evitare che l'admin perda i poteri dopo delete
                            keys_to_preserve = {
                                'user_data', 'logged_in',
                                # Impersonazione admin
                                'impersonating', 'admin_original_user', 'user_is_admin',
                                # Contesto ristorante attivo
                                'ristorante_id', 'ristoranti', 'partita_iva', 'nome_ristorante',
                            }
                            keys_to_remove = [k for k in st.session_state.keys() 
                                             if k not in keys_to_preserve]
                            for key in keys_to_remove:
                                st.session_state.pop(key, None)  # Sicuro: niente errore se non esiste
                            
                            progress.progress(100, text="Completato!")
                            time.sleep(0.1)
                            
                            # Mostra risultato DENTRO lo spinner (indentazione corretta)
                            if result["success"]:
                                st.success(f"✅ **{result['fatture_eliminate']} fatture** spostate nel cestino! ({result['righe_eliminate']} prodotti)")
                                st.info("🗑️ Le fatture resteranno nel cestino per 30 giorni, poi verranno eliminate definitivamente.")
                                
                                # LOG AUDIT: Verifica immediata post-delete
                                try:
                                    verify_query = supabase.table("fatture").select("id", count="exact").eq("user_id", user_id)
                                    verify_query = add_ristorante_filter(verify_query)
                                    verify = verify_query.execute()
                                    num_residue = verify.count or 0
                                    if num_residue == 0:
                                        logger.info(f"✅ DELETE VERIFIED: 0 righe rimaste per user_id={user_id}")
                                        st.success(f"✅ Verifica: Database pulito (0 righe)")
                                    else:
                                        logger.error(f"⚠️ DELETE INCOMPLETE: {num_residue} righe ancora presenti per user_id={user_id}")
                                        st.error(f"⚠️ Attenzione: {num_residue} righe ancora presenti (possibile problema RLS)")
                                except Exception as e:
                                    logger.exception("Errore verifica post-delete")
                                
                                # Reset checkbox
                                if 'check_conferma_svuota' in st.session_state:
                                    del st.session_state.check_conferma_svuota
                                
                                # 🔥 FLAG HIDE UPLOADER: Nascondi uploader dopo eliminazione totale
                                st.session_state.hide_uploader = True
                                st.session_state.files_processati_sessione = set()
                                st.cache_data.clear()
                                invalida_cache_memoria()
                                st.success("✅ Eliminato tutto!")
                                st.rerun()
                            else:
                                st.error(f"❌ Errore: {result['error']}")
                
                st.markdown("---")
            
            # ========== ELIMINA SINGOLA FATTURA ==========
            st.markdown("### 🗑️ Elimina Fattura Singola")
            
            # Usa fatture_summary già creato sopra
            if len(fatture_summary) > 0:
                # 🔍 FILTRO FORNITORE — selectbox con lista fornitori disponibili
                fornitori_disponibili = sorted(fatture_summary['Fornitore'].dropna().unique().tolist())
                opzioni_fornitore = ["— Tutti i fornitori —"] + fornitori_disponibili
                filtro_fornitore_sel = st.selectbox(
                    "🔍 Filtra per Fornitore:",
                    options=opzioni_fornitore,
                    key="filtro_fornitore_gestione"
                )
                if filtro_fornitore_sel == "— Tutti i fornitori —":
                    fatture_filtrate = fatture_summary
                else:
                    fatture_filtrate = fatture_summary[fatture_summary['Fornitore'] == filtro_fornitore_sel]
                
                # Crea opzioni dropdown con dict per passare tutti i dati
                fatture_options = []
                for idx, row in fatture_filtrate.iterrows():
                    fatture_options.append({
                        'File': row['File'],
                        'Fornitore': row['Fornitore'],
                        'NumProdotti': int(row['NumProdotti']),
                        'Totale': row['Totale'],
                        'Data': row['Data']
                    })
                
                if not fatture_options:
                    st.info("🔭 Nessuna fattura trovata per il fornitore cercato.")
                else:
                    fattura_selezionata = st.selectbox(
                        "Seleziona fattura da eliminare:",
                        options=fatture_options,
                        format_func=lambda x: format_fattura_label(
                            file_name=x['File'],
                            fornitore=x['Fornitore'],
                            totale=x['Totale'],
                            num_righe=x['NumProdotti'],
                            data=x['Data'],
                        ),
                        help="Il nome file viene mostrato completo e si adatta allo spazio disponibile",
                        key="select_fattura_elimina"
                    )
                    
                    col_btn, col_spacer = st.columns([1, 3])
                    with col_btn:
                        if st.button("🗑️ Elimina Fattura", type="secondary", use_container_width=True):
                            with st.spinner(f"🗑️ Eliminazione in corso..."):
                                result = elimina_fattura_completa(fattura_selezionata['File'], user_id, ristoranteid=st.session_state.get('ristorante_id'))
                                
                                # 🔥 INVALIDAZIONE CACHE: Forza reload dati dopo eliminazione
                                invalida_cache_memoria()  # Reset memoria AI
                                clear_fatture_cache()  # Invalida solo cache fatture
                                
                                # 🔥 RESET SESSION: Rimuovi file eliminato dalla lista processati
                                # (rimuovi sia il nome completo che il nome base normalizzato)
                                if 'files_processati_sessione' in st.session_state:
                                    file_eliminato = fattura_selezionata['File']
                                    st.session_state.files_processati_sessione.discard(file_eliminato)
                                    st.session_state.files_processati_sessione.discard(os.path.splitext(file_eliminato)[0].lower())
                                
                                if result["success"]:
                                    st.success(f"✅ Fattura **{fattura_selezionata['File']}** spostata nel cestino ({result['righe_eliminate']} prodotti)")
                                    time.sleep(0.3)
                                    st.rerun()
                                else:
                                    st.error(f"❌ Errore: {result['error']}")
            else:
                st.info("🔭 Nessuna fattura da eliminare.")
            
            st.caption("🗑️ Le fatture eliminate vengono spostate nel cestino per 30 giorni")



# ============================================================
# SESSION STATE: Tracking file elaborati/errori
# ============================================================
if 'files_processati_sessione' not in st.session_state:
    st.session_state.files_processati_sessione = set()

if 'files_con_errori' not in st.session_state:
    st.session_state.files_con_errori = set()

if 'files_errori_report' not in st.session_state:
    st.session_state.files_errori_report = {}  # Dizionario persistente per mostrare report anche dopo rerun


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
# MOSTRA MESSAGGI PERSISTENTI DALL'ULTIMO UPLOAD
# (rimangono visibili per 30 secondi, poi spariscono)
# ============================================================
if 'upload_messages' in st.session_state and st.session_state.upload_messages:
    _msg_age = time.time() - st.session_state.get('upload_messages_time', 0)
    if _msg_age < 30:
        for _msg in st.session_state.upload_messages:
            st.markdown(_msg, unsafe_allow_html=True)
        # Inline st.error per TD24 MISSING (pct < 50%)
        _td24_ctx = (st.session_state.get('last_upload_notification_context') or {}).get('td24_date_alerts') or []
        _td24_missing = [a for a in _td24_ctx if a.get('status') == 'missing']
        if _td24_missing:
            _td24_lines = []
            for _a in _td24_missing:
                _td24_lines.append(
                    f"• **{_a.get('fornitore', '?')}** ({_a.get('file_name', '?')}) — "
                    f"{_a.get('lines_with_date', 0)}/{_a.get('lines_total', 0)} righe con data consegna"
                )
            st.error(
                "📅 **Fatture differite (TD24) senza data consegna:**\n\n"
                + "\n".join(_td24_lines)
                + "\n\nLa data consegna è importante per l'analisi dei margini mensili."
            )
    else:
        st.session_state.upload_messages = []


# 🔥 MOSTRA ERRORE LIMITE UPLOAD (dopo reset widget)
if '_upload_limit_error' in st.session_state:
    st.error(st.session_state.pop('_upload_limit_error'))

# 🔥 GESTIONE FILE CARICATI
if uploaded_files:
    handle_uploaded_files(uploaded_files, supabase, user_id)
    # [DEBUG]
    _debug_session_snap("POST_UPLOAD")

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
