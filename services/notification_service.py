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
        'failed': 'con errore di elaborazione',
        'blocked': 'bloccate dalle regole di caricamento',
        'other': 'scartate',
    }
    actionable_total = sum(category_counts.get(key, 0) for key in ('failed', 'other'))
    # I duplicati e i blocchi da regole upload sono gia mostrati nel riepilogo
    # sotto il pulsante Carica Documenti. Evitiamo quindi doppio avviso nell'expander.
    if actionable_total <= 0:
        return []

    summary_parts = []
    for key in ('failed', 'other'):
        count = category_counts.get(key, 0)
        if count > 0:
            summary_parts.append(f"{count} {labels[key]}")

    total_problematic = actionable_total
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


def build_upload_quality_notifications(upload_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Crea una notifica solo per i casi realmente rimasti irrisolti dopo il passaggio automatico AI."""
    if not upload_context:
        return []

    upload_id = str(upload_context.get('upload_id') or '').strip()
    quality_checks = upload_context.get('quality_checks') or {}
    if not upload_id or not quality_checks:
        return []

    verification_ok = bool(quality_checks.get('verification_ok'))
    if not verification_ok:
        err = _html.escape(str(quality_checks.get('verification_error') or 'verifica non disponibile'))
        return [{
            'id': f'upload-quality-{upload_id}',
            'level': 'warning',
            'icon': '🧪',
            'title': 'Verifica qualità upload non completata',
            'body': f"Le fatture risultano caricate, ma il controllo automatico finale non è riuscito: {err}.",
            'toast': 'Verifica qualità da ricontrollare',
        }]

    rows_saved = int(quality_checks.get('rows_saved') or 0)
    uncategorized_rows = int(quality_checks.get('uncategorized_rows') or 0)
    uncategorized_unique = int(quality_checks.get('uncategorized_unique_products') or 0)

    # Le righe a €0 e quelle marcate needs_review sono gestite automaticamente
    # nel tab "Review Righe 0€" — non richiedono una notifica separata.
    if uncategorized_rows <= 0:
        return []

    prod_label = f"/{uncategorized_unique} {_pluralize(uncategorized_unique, 'prodotto univoco', 'prodotti univoci')}" if uncategorized_unique else ""
    examples = [
        _html.escape(str(item).strip())
        for item in (quality_checks.get('uncategorized_examples') or [])
        if str(item).strip()
    ]

    body = (
        f"{uncategorized_rows} {_pluralize(uncategorized_rows, 'riga', 'righe')}{prod_label} "
        f"non sono state categorizzate automaticamente perché la descrizione non contiene abbastanza informazioni."
    )
    if examples:
        body += "<br/>Verifica queste voci:<br/>• " + "<br/>• ".join(examples[:8])

    return [{
        'id': f'upload-quality-{upload_id}',
        'level': 'warning',
        'icon': '⚠️',
        'title': 'Alcune voci richiedono verifica',
        'body': body,
        'toast': f"{uncategorized_rows} righe Da Classificare",
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
        'action_state_key': 'cp_tab_attivo',
        'action_state_value': 'variazioni',
    }]


def build_credit_note_notifications(upload_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Crea una notifica dedicata quando l'ultimo upload contiene note di credito."""
    if not upload_context:
        return []

    upload_id = str(upload_context.get('upload_id') or '').strip()
    credit_note_files = upload_context.get('credit_note_files') or []
    if not upload_id or not credit_note_files:
        return []

    count = len(credit_note_files)
    body = (
        f"Nell'ultimo caricamento sono state rilevate {count} "
        f"{_pluralize(count, 'nota di credito', 'note di credito')} (TD04)."
    )

    return [{
        'id': f'credit-notes-{upload_id}',
        'level': 'info',
        'icon': '🧾',
        'title': 'Note di credito rilevate',
        'body': body,
        'toast': f"{count} {_pluralize(count, 'nota di credito rilevata', 'note di credito rilevate')}",
        'action_label': 'Vai alla pagina',
        'action_page': 'pages/3_controllo_prezzi.py',
        'action_state_key': 'cp_tab_attivo',
        'action_state_value': 'nc',
    }]


def build_td24_date_notifications(upload_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Crea notifiche per fatture differite TD24 con data consegna mancante o parziale.

    Soglie:
      - pct < 50%  → MISSING (warning)  — alert inline + expander
      - pct < 95%  → WARNING (info)     — solo expander
      - pct >= 95% → silenzioso
    """
    if not upload_context:
        return []

    upload_id = str(upload_context.get('upload_id') or '').strip()
    td24_alerts = upload_context.get('td24_date_alerts') or []
    if not upload_id or not td24_alerts:
        return []

    notifications: List[Dict[str, Any]] = []

    missing_files = [a for a in td24_alerts if a.get('status') == 'missing']
    warning_files = [a for a in td24_alerts if a.get('status') == 'warning']

    def _build_body(alerts: List[Dict[str, Any]], no_ddt_note: bool = False) -> str:
        parts = []
        for a in alerts:
            fname = _html.escape(str(a.get('file_name', '?')))
            fornitore = _html.escape(str(a.get('fornitore', '?')))
            pct = float(a.get('pct') or 0.0)
            line = (
                f"{fornitore} ({fname}) — "
                f"{a.get('lines_with_date', 0)}/{a.get('lines_total', 0)} righe con data "
                f"({pct:.1f}% coperta)"
            )
            if no_ddt_note and pct == 0.0:
                line += (
                    " · Il fornitore ha emesso questa fattura come TD24 senza blocchi DDT "
                    "(probabile errore nel tipo documento usato dal fornitore — nessuna azione richiesta da parte tua)"
                )
            parts.append(line)
        return '<br/>'.join(parts)

    # Separa i "missing" in due gruppi: copertura 0% (errore fornitore) vs parziale (dato realmente assente)
    no_ddt_files = [a for a in missing_files if float(a.get('pct') or 0.0) == 0.0]
    partial_missing_files = [a for a in missing_files if float(a.get('pct') or 0.0) > 0.0]

    if no_ddt_files:
        n = len(no_ddt_files)
        notifications.append({
            'id': f'td24-date-noddt-{upload_id}',
            'level': 'info',
            'icon': 'ℹ️',
            'title': f"Fattura differita senza DDT ({n} {_pluralize(n, 'file', 'file')})",
            'body': _build_body(no_ddt_files, no_ddt_note=True),
            'toast': f"ℹ️ {n} {_pluralize(n, 'fattura', 'fatture')} TD24 senza DDT — nessuna azione richiesta",
        })

    if partial_missing_files:
        n = len(partial_missing_files)
        notifications.append({
            'id': f'td24-date-missing-{upload_id}',
            'level': 'warning',
            'icon': '📅',
            'title': f"Fattura differita con dati consegna mancanti ({n} {_pluralize(n, 'file', 'file')})",
            'body': _build_body(partial_missing_files),
            'toast': f"📅 {n} {_pluralize(n, 'fattura differita', 'fatture differite')} con date mancanti",
        })

    if warning_files:
        n = len(warning_files)
        notifications.append({
            'id': f'td24-date-warning-{upload_id}',
            'level': 'info',
            'icon': '📅',
            'title': f"Fattura differita con data consegna parziale ({n} {_pluralize(n, 'file', 'file')})",
            'body': _build_body(warning_files),
            'toast': f"📅 {n} {_pluralize(n, 'fattura differita', 'fatture differite')} con data parziale",
        })

    return notifications


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
            'action_state_key': 'margine_tab',
            'action_state_value': 'calcolo',
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
            'action_state_key': 'margine_tab',
            'action_state_value': 'calcolo',
        })

    return notifications