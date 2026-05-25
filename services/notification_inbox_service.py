"""CRUD + helpers per notification_inbox.

Responsabilità:
- Costruire i record da inserire (factory build_notification_record)
- Calcolare dedupe_key e expires_at per tipologia
- Upsert batch via RPC Postgres (upsert_notification_inbox)
- Query lista notifiche (attive, non scadute, ordinate per recency)
- Badge count
- Dismiss singolo e dismiss-all
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config.logger_setup import get_logger

logger = get_logger('notification_inbox')

# ============================================================
# COSTANTI
# ============================================================

# Durata vita notifiche per source_type
_EXPIRES_DELTA: Dict[str, timedelta] = {
    'operativa':      timedelta(days=7),
    'upload':         timedelta(days=14),
    'invoicetronic':  timedelta(days=3),
}

# Topic ricorrenti (DO UPDATE su conflict) vs one-shot (DO NOTHING)
_REFRESH_ON_CONFLICT_TOPICS = {
    'scadenza_superata',
    'scadenza_imminente',
    'fatturato_mancante',
    'costo_personale_mancante',
    'invoicetronic_auto',
    'food_cost_soglia_superata',
    'mol_negativo',
    'food_cost_trend_peggioramento',
    'fornitore_critico_consecutivo',
    'nota_credito_non_usata',
    'sconto_fornitore_scaduto',
    'tag_suggestion_new_tag',
    'tag_suggestion_extend_tag',
}

# Soglia "Nuova": notifiche con source_event_at più recente di 24h
_NEW_THRESHOLD_HOURS = 24


# ============================================================
# BUCKET HELPERS
# ============================================================

def _bucket_iso_week(dt: Optional[datetime] = None) -> str:
    """Bucket settimana ISO: '2026-W20'."""
    ref = dt or datetime.now(timezone.utc)
    return ref.strftime('%G-W%V')


def _bucket_iso_month(dt: Optional[datetime] = None) -> str:
    """Bucket mese ISO: '2026-04'."""
    ref = dt or datetime.now(timezone.utc)
    return ref.strftime('%Y-%m')


def _bucket_file_ids(file_ids: List[str]) -> str:
    """Bucket basato su hash MD5 dei file_ids dell'upload (ordinati per stabilità)."""
    joined = '|'.join(sorted(str(f) for f in file_ids))
    return hashlib.md5(joined.encode(), usedforsecurity=False).hexdigest()[:12]


def _bucket_daily(dt: Optional[datetime] = None) -> str:
    """Bucket giornaliero: '2026-05-13'."""
    ref = dt or datetime.now(timezone.utc)
    return ref.strftime('%Y-%m-%d')


def build_dedupe_key(ristorante_id: str, topic_key: str, bucket: str) -> str:
    """Compone la dedupe_key: '{ristorante_id}::{topic_key}::{bucket}'."""
    return f"{ristorante_id}::{topic_key}::{bucket}"


def resolve_bucket(topic_key: str, file_ids: Optional[List[str]] = None,
                   pending_count: Optional[int] = None,
                   ref_dt: Optional[datetime] = None) -> str:
    """Calcola il bucket corretto per il topic_key dato.

    - scadenza_superata/imminente    → settimana ISO
    - fatturato_mancante/costo_pers  → mese ISO
    - food_cost/mol/trend            → mese ISO
    - piva_dup/fornitore_critico     → settimana ISO
    - invoicetronic_auto             → '{count}::{date}'
    - fattura_duplicata/anomalia     → hash file_ids (fallback: daily)
    - nota_credito/sconto/fornitore  → settimana ISO
    - record_prezzo/piva_mancante    → hash file_ids (fallback: daily)
    - trial_scadenza_imminente       → giornaliero
    - tutto il resto (upload)        → hash file_ids (fallback: daily)
    """
    if topic_key in ('scadenza_superata', 'scadenza_imminente'):
        return _bucket_iso_week(ref_dt)
    if topic_key in ('fatturato_mancante', 'costo_personale_mancante'):
        return _bucket_iso_month(ref_dt)
    if topic_key in ('food_cost_soglia_superata', 'mol_negativo', 'food_cost_trend_peggioramento'):
        return _bucket_iso_month(ref_dt)
    if topic_key in (
        'piva_duplicata_fornitore',
        'fornitore_critico_consecutivo',
        'nota_credito_non_usata',
        'sconto_fornitore_scaduto',
        'tag_suggestion_new_tag',
        'tag_suggestion_extend_tag',
    ):
        return _bucket_iso_week(ref_dt)
    if topic_key == 'invoicetronic_auto':
        count_str = str(pending_count or 0)
        date_str = _bucket_daily(ref_dt)
        return f"{count_str}::{date_str}"
    if topic_key in (
        'fattura_duplicata',
        'fattura_anomala_importo',
        'prezzo_prodotto_record_storico',
        'piva_fornitore_mancante',
    ) and file_ids:
        return _bucket_file_ids(file_ids)
    if topic_key == 'trial_scadenza_imminente':
        return _bucket_daily(ref_dt)
    # upload one-shot e tutto il resto
    if file_ids:
        return _bucket_file_ids(file_ids)
    return _bucket_daily(ref_dt)


# ============================================================
# FACTORY
# ============================================================

def build_notification_record(
    user_id: str,
    ristorante_id: str,
    topic_key: str,
    source_type: str,
    severity: str,
    title: str,
    body: str,
    payload: Optional[Dict[str, Any]] = None,
    action_page: Optional[str] = None,
    file_ids: Optional[List[str]] = None,
    pending_count: Optional[int] = None,
    ref_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Costruisce un record pronto per l'upsert in notification_inbox.

    Calcola automaticamente:
    - dedupe_key  (via resolve_bucket)
    - expires_at  (via _EXPIRES_DELTA per source_type)
    - refresh_on_conflict (True se topic ricorrente)
    """
    now = ref_dt or datetime.now(timezone.utc)
    bucket = resolve_bucket(topic_key, file_ids=file_ids, pending_count=pending_count, ref_dt=now)
    dedupe_key = build_dedupe_key(ristorante_id, topic_key, bucket)
    delta = _EXPIRES_DELTA.get(source_type, timedelta(days=7))
    expires_at = (now + delta).isoformat()

    return {
        'user_id': user_id,
        'ristorante_id': ristorante_id,
        'topic_key': topic_key,
        'source_type': source_type,
        'severity': severity,
        'title': title,
        'body': body,
        'payload': payload or {},
        'action_page': action_page,
        'dedupe_key': dedupe_key,
        'source_event_at': now.isoformat(),
        'expires_at': expires_at,
        'refresh_on_conflict': topic_key in _REFRESH_ON_CONFLICT_TOPICS,
    }


# ============================================================
# UPSERT
# ============================================================

def upsert_inbox_notifications(
    notifications: List[Dict[str, Any]],
    supabase_client=None,
) -> int:
    """Esegue upsert batch via RPC. Restituisce il numero di righe inserite (0 = ok DO NOTHING).

    Non solleva mai eccezioni per non bloccare il flusso principale.
    """
    if not notifications or supabase_client is None:
        return 0
    try:
        result = supabase_client.rpc(
            'upsert_notification_inbox',
            {'p_notifications': notifications}
        ).execute()
        count = result.data or 0
        logger.info(f"📬 Inbox upsert: {count} righe inserite/{len(notifications)} record inviati")
        return int(count)
    except Exception as exc:
        logger.error(f"❌ Errore upsert notification_inbox: {exc}")
        return 0


# ============================================================
# QUERY
# ============================================================

def get_inbox_notifications(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
    source_type: Optional[str] = None,
    include_expired: bool = False,
) -> List[Dict[str, Any]]:
    """Restituisce le notifiche attive (dismissed_at IS NULL) per user+ristorante.

    Ordinate per source_event_at DESC (più recenti prima).
    Le notifiche scadute (expires_at < now) sono escluse di default.
    Arricchisce ogni record con is_new (bool).
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return []
    try:
        now = datetime.now(timezone.utc)
        now_iso = now.strftime('%Y-%m-%dT%H:%M:%SZ')

        query = (
            supabase_client.table('notification_inbox')
            .select('id,topic_key,source_type,severity,title,body,payload,action_page,source_event_at,expires_at')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .neq('topic_key', 'fornitore_unico_categoria')
            .is_('dismissed_at', 'null')
            .order('source_event_at', desc=True)
        )
        if not include_expired:
            query = query.or_(f'expires_at.is.null,expires_at.gt.{now_iso}')
        if source_type:
            query = query.eq('source_type', source_type)

        rows = (query.execute().data or [])

        threshold = now - timedelta(hours=_NEW_THRESHOLD_HOURS)
        result = []
        for row in rows:
            # Arricchisce con is_new
            try:
                seat = datetime.fromisoformat(row['source_event_at'].replace('Z', '+00:00'))
                row['is_new'] = seat >= threshold
            except (ValueError, AttributeError, KeyError):
                row['is_new'] = False
            result.append(row)
        return result
    except Exception as exc:
        logger.error(f"❌ Errore get_inbox_notifications: {exc}")
        return []


# Cache layer per badge count: @st.cache_data(ttl=30) evita query DB ridondanti
# su ogni re-render della pagina. La cache è condivisa per processo (non per sessione)
# ma è comunque user+ristorante-specifica tramite i parametri.
try:
    import streamlit as _st_badge

    @_st_badge.cache_data(ttl=30, show_spinner=False)
    def _get_inbox_badge_cached(user_id: str, ristorante_id: str) -> int:
        """Badge count cached 30s — elimina la query DB ridondante sui re-render."""
        from services import get_supabase_client as _get_sb
        sb = _get_sb()
        rows = get_inbox_notifications(user_id, ristorante_id, sb)
        return len(rows)
except Exception:
    def _get_inbox_badge_cached(user_id: str, ristorante_id: str) -> int:  # type: ignore[misc]
        from services import get_supabase_client as _get_sb
        sb = _get_sb()
        rows = get_inbox_notifications(user_id, ristorante_id, sb)
        return len(rows)


def get_inbox_badge_count(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> int:
    """Conta le notifiche attive e non scadute. Usato per il badge nel tab header."""
    if not user_id or not ristorante_id:
        return 0
    try:
        result = _get_inbox_badge_cached(str(user_id), str(ristorante_id))
        if not isinstance(result, int):
            raise TypeError("cache returned non-int")
        return result
    except Exception:
        rows = get_inbox_notifications(user_id, ristorante_id, supabase_client)
        return len(rows)


# ============================================================
# DISMISS
# ============================================================

def dismiss_inbox_notification(
    notification_id: str,
    supabase_client=None,
) -> bool:
    """Soft-delete di una singola notifica (sets dismissed_at = now())."""
    if not notification_id or supabase_client is None:
        return False
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase_client.table('notification_inbox') \
            .update({'dismissed_at': now_iso}) \
            .eq('id', notification_id) \
            .execute()
        return True
    except Exception as exc:
        logger.error(f"❌ Errore dismiss_inbox_notification {notification_id}: {exc}")
        return False


def dismiss_all_inbox_notifications(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
    source_type: Optional[str] = None,
) -> bool:
    """Soft-delete di tutte le notifiche attive per user+ristorante (opz. filtrate per source_type)."""
    if not user_id or not ristorante_id or supabase_client is None:
        return False
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        query = (
            supabase_client.table('notification_inbox')
            .update({'dismissed_at': now_iso})
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .is_('dismissed_at', 'null')
        )
        if source_type:
            query = query.eq('source_type', source_type)
        query.execute()
        return True
    except Exception as exc:
        logger.error(f"❌ Errore dismiss_all_inbox_notifications: {exc}")
        return False


def dismiss_inbox_topics(
    user_id: str,
    ristorante_id: str,
    topic_keys: List[str],
    supabase_client=None,
) -> bool:
    """Soft-delete massivo per topic specifici (solo notifiche attive).

    Usato per cleanup server-side di topic dismessi dal prodotto.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return False
    topics = [str(t).strip() for t in (topic_keys or []) if str(t).strip()]
    if not topics:
        return False
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        (
            supabase_client.table('notification_inbox')
            .update({'dismissed_at': now_iso})
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .is_('dismissed_at', 'null')
            .in_('topic_key', topics)
            .execute()
        )
        return True
    except Exception as exc:
        logger.error(f"❌ Errore dismiss_inbox_topics: {exc}")
        return False
