"""Notifiche in-app per promemoria operativi e dati mancanti."""

import html as _html
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from config.constants import MESI_ITA
from config.logger_setup import get_logger
from services.margine_service import carica_margini_anno

logger = get_logger('notification')


def _pluralize(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _format_price_alert_summary(price_alerts: List[Dict[str, Any]], max_items: int = 3) -> str:
    if not price_alerts:
        return ''

    snippets = []
    for alert in price_alerts[:max_items]:
        product = _html.escape(str(alert.get('product') or 'Prodotto').strip())
        increase_pct = float(alert.get('increase_pct') or 0.0)
        snippets.append(f"{product} (+{increase_pct:.1f}%)")
    return ', '.join(snippets)


def build_upload_outcome_notifications(upload_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Crea una notifica compatta per upload falliti o fatture scartate."""
    if not upload_context:
        return []

    problematic_files = upload_context.get('problematic_files') or []
    upload_id = str(upload_context.get('upload_id') or '').strip()
    if not problematic_files or not upload_id:
        return []

    category_counts = Counter(
        str(item.get('category') or 'other').strip().lower()
        for item in problematic_files
    )
    labels = {
        'duplicate': 'gia presenti',
        'failed': 'con errore di elaborazione',
        'blocked': 'bloccate dalle regole di caricamento',
        'other': 'scartate',
    }
    summary_parts = []
    for key in ('duplicate', 'failed', 'blocked', 'other'):
        count = category_counts.get(key, 0)
        if count > 0:
            summary_parts.append(f"{count} {labels[key]}")

    total_problematic = len(problematic_files)
    fatture_label = _pluralize(total_problematic, 'fattura non e entrata', 'fatture non sono entrate')
    body = f"Nell'ultimo caricamento {total_problematic} {fatture_label}"
    if summary_parts:
        body += ': ' + ', '.join(summary_parts)
    body += '.'

    return [{
        'id': f'upload-outcome-{upload_id}',
        'level': 'warning',
        'icon': '⚠️',
        'title': 'Upload con file scartati o falliti',
        'body': body,
        'toast': f"Upload da controllare: {total_problematic} {_pluralize(total_problematic, 'file scartato', 'file scartati')}",
    }]


def build_price_alert_notifications(
    upload_context: Optional[Dict[str, Any]],
    threshold_pct: float = 5.0,
) -> List[Dict[str, Any]]:
    """Crea una notifica per aumenti prezzo rilevati sull'ultimo upload."""
    if not upload_context:
        return []

    upload_id = str(upload_context.get('upload_id') or '').strip()
    price_alerts = upload_context.get('price_alerts') or []
    if not upload_id or not price_alerts:
        return []

    count = len(price_alerts)
    summary = _format_price_alert_summary(price_alerts)
    prodotti_label = _pluralize(count, 'prodotto ha superato', 'prodotti hanno superato')
    body = (
        f"Nell'ultimo caricamento {count} {prodotti_label} il +{threshold_pct:.0f}% rispetto "
        "all'acquisto precedente."
    )
    if summary:
        body += f" Alert principali: {summary}."

    return [{
        'id': f'price-alerts-{upload_id}',
        'level': 'warning',
        'icon': '📈',
        'title': f'Alert prezzi oltre +{threshold_pct:.0f}% su nuove fatture',
        'body': body,
        'toast': f"Attenzione prezzi: {count} {_pluralize(count, 'aumento rilevato', 'aumenti rilevati')}",
        'action_label': 'Vai alla pagina',
        'action_page': 'pages/3_controllo_prezzi.py',
    }]


def build_scoped_notification_id(base_id: str, ristorante_id: Optional[str]) -> str:
    """Crea un identificativo stabile della notifica nel contesto del ristorante."""
    return f"rist:{ristorante_id or 'global'}:{base_id}"


def get_dismissed_notification_ids(user_id: str, supabase_client=None) -> Set[str]:
    """Carica l'insieme delle notifiche gia nascoste dall'utente."""
    if not user_id:
        return set()

    try:
        from services import get_supabase_client

        if supabase_client is None:
            supabase_client = get_supabase_client()

        response = supabase_client.table('users') \
            .select('dismissed_notification_ids') \
            .eq('id', user_id) \
            .limit(1) \
            .execute()

        row = (response.data or [{}])[0] or {}
        raw_map = row.get('dismissed_notification_ids') or {}
        if isinstance(raw_map, dict):
            return {str(key) for key in raw_map.keys()}
        return set()
    except Exception as exc:
        logger.warning(f"Errore caricamento notifiche viste per {user_id}: {exc}")
        return set()


def dismiss_notification_ids(
    user_id: str,
    notification_ids: Iterable[str],
    supabase_client=None,
) -> bool:
    """Segna una o piu notifiche come gia viste sul profilo utente."""
    ids = [str(notification_id).strip() for notification_id in notification_ids if str(notification_id).strip()]
    if not user_id or not ids:
        return False

    try:
        from services import get_supabase_client

        if supabase_client is None:
            supabase_client = get_supabase_client()

        response = supabase_client.table('users') \
            .select('dismissed_notification_ids') \
            .eq('id', user_id) \
            .limit(1) \
            .execute()
        row = (response.data or [{}])[0] or {}
        current_map = row.get('dismissed_notification_ids') or {}
        if not isinstance(current_map, dict):
            current_map = {}

        dismissed_at = datetime.now(timezone.utc).isoformat()
        for notification_id in ids:
            current_map[notification_id] = dismissed_at

        supabase_client.table('users') \
            .update({'dismissed_notification_ids': current_map}) \
            .eq('id', user_id) \
            .execute()
        return True
    except Exception as exc:
        logger.warning(f"Errore salvataggio notifiche viste per {user_id}: {exc}")
        return False


def get_previous_month_period(reference_dt: Optional[datetime] = None) -> Tuple[int, int]:
    """Restituisce anno e mese del mese precedente alla data di riferimento."""
    current_dt = reference_dt or datetime.now(timezone.utc)
    if current_dt.month == 1:
        return current_dt.year - 1, 12
    return current_dt.year, current_dt.month - 1


def build_monthly_data_notifications(
    user_id: str,
    ristorante_id: str,
    reference_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Costruisce notifiche in-app per dati mensili mancanti del mese precedente."""
    if not user_id or not ristorante_id:
        return []

    year, month = get_previous_month_period(reference_dt)
    month_label = MESI_ITA.get(month, str(month)).title()

    try:
        dati_anno = carica_margini_anno(user_id, ristorante_id, year) or {}
        dati_mese = dati_anno.get(month) or {}
    except Exception as exc:
        logger.warning(f"Errore preparazione notifiche mensili {year}/{month}: {exc}")
        return []

    fatturato_totale = sum(
        float(dati_mese.get(field_name, 0.0) or 0.0)
        for field_name in ('fatturato_iva10', 'fatturato_iva22', 'altri_ricavi_noiva')
    )
    costo_dipendenti = float(dati_mese.get('costo_dipendenti', 0.0) or 0.0)

    notifications: List[Dict[str, Any]] = []

    if fatturato_totale <= 0:
        notifications.append({
            'id': f'missing-revenue-{year}-{month:02d}',
            'level': 'warning',
            'icon': '📊',
            'title': f'Fatturato di {month_label} {year} non ancora inserito',
            'body': (
                f'Nel tab Calcolo Ricavi-Costi-Margini non risultano ancora compilati i ricavi '
                f'del mese precedente ({month_label} {year}).'
            ),
            'toast': f'Promemoria: manca il fatturato di {month_label} {year}',
            'action_label': 'Vai alla pagina',
            'action_page': 'pages/1_calcolo_margine.py',
        })

    if costo_dipendenti <= 0:
        notifications.append({
            'id': f'missing-labor-cost-{year}-{month:02d}',
            'level': 'warning',
            'icon': '👥',
            'title': f'Costo del personale di {month_label} {year} non ancora inserito',
            'body': (
                f'Per {month_label} {year} il valore del costo del lavoro e\' ancora vuoto o a zero. '
                'Compilarlo mantiene affidabili MOL e percentuali.'
            ),
            'toast': f'Promemoria: manca il costo del personale di {month_label} {year}',
            'action_label': 'Vai alla pagina',
            'action_page': 'pages/1_calcolo_margine.py',
        })

    return notifications