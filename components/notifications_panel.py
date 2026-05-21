"""
components/notifications_panel.py
Logica notifiche operative estratta da app.py (Step 1.4).

Espone:
    refresh_auto_invoice_notice(supabase, user_data)         Aggiorna session_state con fatture auto (TTL 60s).
    build_operational_notifications(supabase, user_id, ...)  Costruisce la lista notifiche operative (cached 300s).
    ingest_notifications_to_inbox(notifications, ...)        Ingesta le notifiche operative nell'inbox DB.
    show_operational_toasts(notifications)                   Mostra un toast silenzioso per notifica (1 volta/sessione).

Note:
    dismiss_notification_ids / get_dismissed_notification_ids / build_scoped_notification_id
    erano importate in app.py ma mai usate lì → non ri-esportate qui (cleanup Fase 1).
"""

import logging
import time
import importlib
import sys
from datetime import datetime, timezone

import streamlit as st

logger = logging.getLogger("fci_app")

# ============================================================
# IMPORT notification_service — retry difensivo su ImportError
# ============================================================
try:
    from services.notification_service import (
        build_controllo_prezzi_notifications,
        build_food_cost_notifications,
        build_credit_note_notifications,
        build_monthly_data_notifications,
        build_price_alert_notifications,
        build_qualita_anagrafica_notifications,
        build_scadenza_documents_notifications,
        build_td24_date_notifications,
        build_trial_notifications,
        build_upload_outcome_notifications,
        build_upload_quality_notifications,
    )
except ImportError:
    # Retry difensivo: evita crash su import intermittente con modulo parzialmente inizializzato.
    sys.modules.pop('services.notification_service', None)
    _notification_module = importlib.import_module('services.notification_service')

    build_controllo_prezzi_notifications   = _notification_module.build_controllo_prezzi_notifications
    build_food_cost_notifications          = _notification_module.build_food_cost_notifications
    build_credit_note_notifications        = _notification_module.build_credit_note_notifications
    build_monthly_data_notifications       = _notification_module.build_monthly_data_notifications
    build_price_alert_notifications        = _notification_module.build_price_alert_notifications
    build_qualita_anagrafica_notifications = _notification_module.build_qualita_anagrafica_notifications
    build_scadenza_documents_notifications = _notification_module.build_scadenza_documents_notifications
    build_td24_date_notifications          = _notification_module.build_td24_date_notifications
    build_trial_notifications              = _notification_module.build_trial_notifications
    build_upload_outcome_notifications     = _notification_module.build_upload_outcome_notifications
    build_upload_quality_notifications     = _notification_module.build_upload_quality_notifications

from services.notification_inbox_service import (
    build_notification_record,
    upsert_inbox_notifications,
)


# ============================================================
# HELPERS PRIVATI
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


# ============================================================
# FUNZIONI PUBBLICHE
# ============================================================

def refresh_auto_invoice_notice(supabase, user_data: dict) -> None:
    """
    Aggiorna ``session_state.auto_invoice_notice`` con le fatture arrivate
    automaticamente dall'ultimo login (TTL 60 secondi).

    Modifica session_state:
        auto_invoice_notice, auto_invoice_notice_dismissed, auto_received_file_origini,
        _auto_invoice_notice_refresh_ts
    """
    try:
        from services.auth_service import riepilogo_fatture_auto_da_ultimo_login
    except ImportError:
        def riepilogo_fatture_auto_da_ultimo_login(*args, **kwargs):
            return {
                'has_new': False, 'file_count': 0, 'row_count': 0,
                'event_count': 0, 'recent_files': [], 'files_detail': [],
                'window_start': None, 'window_end': None,
            }

    try:
        _now_ts = time.time()
        _last_refresh = st.session_state.get('_auto_invoice_notice_refresh_ts', 0)
        if _now_ts - _last_refresh > 60:
            auto_notice = riepilogo_fatture_auto_da_ultimo_login(
                user_id=user_data.get('id'),
                last_login_precedente=user_data.get('last_login_precedente'),
                login_at=user_data.get('login_at'),
                supabase_client=supabase,
            )
            st.session_state['_auto_invoice_notice_refresh_ts'] = _now_ts
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
    except Exception as _err:
        logger.warning(f"Errore refresh notifica fatture automatiche: {_err}")


def build_operational_notifications(
    supabase,
    user_id: str,
    ristorante_id: str,
    is_impersonating: bool,
    upload_ctx: dict,
) -> list:
    """
    Costruisce e restituisce la lista delle notifiche operative.

    - Notifiche DB-heavy: cached 300s in session_state (chiave include upload_id).
    - Notifiche upload-ctx: sempre fresche (solo dict, nessuna query DB).
    - Trial notifications: solo se non in impersonazione.

    Returns:
        list: notifiche operative attive per l'utente/ristorante corrente.
    """
    from services.db_service import get_price_alert_threshold

    _notif_cache_key = f"{user_id}::{ristorante_id}::{upload_ctx.get('upload_id', '')}"
    _notif_last_refresh = st.session_state.get('_operational_notifications_refresh_ts', 0)
    _notif_cached_key = st.session_state.get('_operational_notifications_cache_key', '')

    if time.time() - _notif_last_refresh > 300 or _notif_cache_key != _notif_cached_key:
        _price_threshold_db = float(
            upload_ctx.get('price_alert_threshold_pct')
            or get_price_alert_threshold(user_id)
        )
        _db_notifs = build_monthly_data_notifications(
            user_id=user_id,
            ristorante_id=ristorante_id,
            reference_dt=datetime.now(timezone.utc),
        )
        _db_notifs.extend(
            build_scadenza_documents_notifications(
                user_id=user_id,
                ristorante_id=ristorante_id,
            )
        )
        if not is_impersonating:
            _db_notifs.extend(
                build_food_cost_notifications(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    reference_dt=datetime.now(timezone.utc),
                )
            )
            _db_notifs.extend(
                build_controllo_prezzi_notifications(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    upload_context=st.session_state.get('last_upload_notification_context'),
                    supabase_client=supabase,
                )
            )
            _db_notifs.extend(
                build_qualita_anagrafica_notifications(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    upload_context=st.session_state.get('last_upload_notification_context'),
                    supabase_client=supabase,
                )
            )
        st.session_state['_operational_notifications_db'] = _db_notifs
        st.session_state['_operational_notifications_price_threshold'] = _price_threshold_db
        st.session_state['_operational_notifications_refresh_ts'] = time.time()
        st.session_state['_operational_notifications_cache_key'] = _notif_cache_key

    _price_alert_threshold = float(
        upload_ctx.get('price_alert_threshold_pct')
        or st.session_state.get('_operational_notifications_price_threshold')
        or get_price_alert_threshold(user_id)
    )
    operational_notifications = list(st.session_state.get('_operational_notifications_db', []))
    # Notifiche upload-ctx based: sempre fresche (elaborazione dict, nessuna query DB)
    operational_notifications.extend(build_upload_outcome_notifications(upload_ctx))
    operational_notifications.extend(build_upload_quality_notifications(upload_ctx))
    operational_notifications.extend(build_price_alert_notifications(upload_ctx, threshold_pct=_price_alert_threshold))
    operational_notifications.extend(build_credit_note_notifications(upload_ctx))
    operational_notifications.extend(build_td24_date_notifications(upload_ctx))
    # Trial notifications: attiva SOLO se trial attivo e NOT impersonating
    if not is_impersonating:
        operational_notifications.extend(
            build_trial_notifications(
                user_id=user_id,
                trial_info=st.session_state.get('trial_info'),
            )
        )
    return operational_notifications


def ingest_notifications_to_inbox(
    operational_notifications: list,
    supabase,
    user_id: str,
    ristorante_id: str,
) -> None:
    """
    Ingesta le notifiche operative nell'inbox DB (non-critical, silent on error).

    Bucket: mese per fatturato/costi, settimana ISO per scadenze,
    ``{count}::{today}`` per invoicetronic_auto.
    Notifiche ricorrenti: refresh_on_conflict=True (gestito da build_notification_record).
    """
    # ============================================================
    # INBOX INGESTION OPERATIVA
    # ============================================================
    try:
        _inbox_op_uid = str(user_id or '')
        _inbox_op_rid = str(ristorante_id or '')
        if not (_inbox_op_uid and _inbox_op_rid):
            return

        # Mappa id-prefix → (topic_key, severity default)
        _INBOX_OP_TOPIC_MAP = {
            'missing-revenue-':    ('fatturato_mancante',            'warning'),
            'missing-labor-cost-': ('costo_personale_mancante',      'warning'),
            'scaduti-':            ('scadenza_superata',              'warning'),
            'imminenti-':          ('scadenza_imminente',             'info'),
            'trial-expiry-':       ('trial_scadenza_imminente',       'warning'),
            'food-cost-soglia-':   ('food_cost_soglia_superata',      'warning'),
            'mol-negativo-':       ('mol_negativo',                   'warning'),
            'food-cost-trend-':    ('food_cost_trend_peggioramento',  'warning'),
            'nc-non-usata-':       ('nota_credito_non_usata',         'info'),
            'sconto-scaduto-':     ('sconto_fornitore_scaduto',       'info'),
            'record-prezzo-':      ('prezzo_prodotto_record_storico', 'warning'),
            'fornitore-unico-':    ('fornitore_unico_categoria',      'info'),
            'piva-mancante-':      ('piva_fornitore_mancante',        'info'),
        }
        _level_to_severity = {'warning': 'warning', 'error': 'error', 'info': 'info'}
        _inbox_op_records = []

        for _n in operational_notifications:
            _nid = str(_n.get('id') or '')
            _matched_topic = None
            _matched_sev = None
            for _prefix, (_topic, _sev) in _INBOX_OP_TOPIC_MAP.items():
                if _nid.startswith(_prefix):
                    _matched_topic = _topic
                    _matched_sev = _sev
                    break
            if not _matched_topic:
                continue
            _severity_resolved = _level_to_severity.get(
                str(_n.get('level') or ''), _matched_sev
            )
            _inbox_op_records.append(build_notification_record(
                user_id=_inbox_op_uid,
                ristorante_id=_inbox_op_rid,
                topic_key=_matched_topic,
                source_type='operativa',
                severity=_severity_resolved,
                title=str(_n.get('title') or ''),
                body=str(_n.get('body') or ''),
                payload=_n.get('payload_data') or {},
                action_page=str(_n.get('action_page') or ''),
            ))

        # invoicetronic_auto: conta upload_events.needs_ack pendenti per ristorante
        try:
            _iac_resp = (
                supabase.table('upload_events')
                .select('id', count='exact')
                .eq('needs_ack', True)
                .eq('ristorante_id', _inbox_op_rid)
                .in_('status', ['SAVED_OK', 'SAVED_PARTIAL'])
                .execute()
            )
            _iac_count = int(getattr(_iac_resp, 'count', 0) or 0)
            if _iac_count > 0:
                from datetime import date as _date_cls  # noqa: F401
                _inbox_op_records.append(build_notification_record(
                    user_id=_inbox_op_uid,
                    ristorante_id=_inbox_op_rid,
                    topic_key='invoicetronic_auto',
                    source_type='invoicetronic',
                    severity='info',
                    title=f'{_iac_count} {"fattura ricevuta" if _iac_count == 1 else "fatture ricevute"} da Invoicetronic',
                    body=(
                        f'{"Una fattura" if _iac_count == 1 else str(_iac_count) + " fatture"} '
                        f'ricevute automaticamente da Invoicetronic attendono conferma.'
                    ),
                    payload={'pending_count': _iac_count},
                    action_page='Gestione e Pagamenti',
                    pending_count=_iac_count,
                ))
        except Exception as _iac_exc:
            logger.warning(f"[INBOX] Errore conteggio invoicetronic_auto: {_iac_exc}")

        if _inbox_op_records:
            upsert_inbox_notifications(_inbox_op_records, supabase_client=supabase)

    except Exception as _inbox_op_exc:
        logger.warning(f"[INBOX] Errore ingestion operativa (non critico): {_inbox_op_exc}")

    # ============================================================
    # RADAR ANOMALIE SETTIMANALE — TTL 24h per sessione
    # ============================================================
    try:
        _radar_last_run = st.session_state.get('_radar_weekly_last_run_ts', 0)
        if time.time() - _radar_last_run > 86400:
            from services.anomaly_radar_service import check_weekly as _radar_check_weekly
            _radar_records = _radar_check_weekly(
                user_id=str(user_id or ''),
                ristorante_id=str(ristorante_id or ''),
                supabase_client=supabase,
            )
            if _radar_records:
                upsert_inbox_notifications(_radar_records, supabase_client=supabase)
            st.session_state['_radar_weekly_last_run_ts'] = time.time()
    except Exception as _radar_exc:
        logger.warning(f"[INBOX] Radar settimanale fallito (non critico): {_radar_exc}")


def show_operational_toasts(operational_notifications: list) -> None:
    """
    Mostra un toast silenzioso per ogni notifica operativa, una sola volta per sessione.
    Da chiamare con guard ``if not _is_admin_session:`` nel chiamante.
    """
    for _notif in operational_notifications:
        _show_toast_once(
            f"operational::{_notif.get('id')}",
            _notif.get('toast') or _notif.get('title') or 'Nuova notifica',
            icon=_notif.get('icon'),
        )
