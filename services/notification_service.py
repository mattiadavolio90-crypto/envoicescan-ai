"""Notifiche in-app per promemoria operativi e dati mancanti."""

import html as _html
import hashlib
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import pandas as pd

from config.constants import MESI_ITA
from config.logger_setup import get_logger
from services.db_service import filter_active
from services.margine_service import carica_margini_anno
from utils.text_utils import normalizza_stringa

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
        snippets.append(f"• {product} (+{increase_pct:.1f}%)")
    return '\n'.join(snippets)


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

    # Severity error solo se c'è almeno un file con category='failed'
    has_failed = any(item.get('category') == 'failed' for item in problematic_files)

    return [{
        'id': f'upload-outcome-{upload_id}',
        'level': 'error' if has_failed else 'warning',
        'icon': '🔴' if has_failed else '⚠️',
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
        body += f"\n{summary}"

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
            'payload_data': {'mese': month_label, 'anno': year},
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
            'payload_data': {'mese': month_label, 'anno': year},
        })

    return notifications


def build_scadenza_documents_notifications(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Crea notifiche per documenti scaduti o in scadenza entro 7 giorni (Step 7)."""
    if not user_id or not ristorante_id:
        return []

    try:
        from services import get_supabase_client
        from datetime import date, timedelta
        
        sb = supabase_client or get_supabase_client()
        today = date.today()
        tomorrow_plus_7 = today + timedelta(days=7)
        # Orizzonte scaduto: solo gli ultimi 90 giorni. Senza questo limite lo
        # storico antico mai marcato "pagato" si accumula (es. 699k€), generando
        # un falso allarme. Le scadenze davvero rilevanti sono quelle recenti.
        scaduto_da = today - timedelta(days=90)

        # Carica documenti non pagati da fatture_documenti con scadenza nella
        # finestra [oggi-90gg, oggi+7gg] (filtro SQL)
        query = (
            filter_active(
                sb.table("fatture_documenti")
                .select("id,file_origine,fornitore,piva_fornitore,totale_documento,scadenza_effettiva,pagata")
                .eq("user_id", user_id)
                .eq("ristorante_id", ristorante_id)
                .eq("pagata", False)
            )
            .gte("scadenza_effettiva", scaduto_da.isoformat())
            .lte("scadenza_effettiva", tomorrow_plus_7.isoformat())
            .execute()
        )
        
        docs = query.data or []
        if not docs:
            return []
        
        # Esclude fornitori con regola RID (auto-pagato virtuale — pagata=False nel DB ma
        # lo scadenziario li mostra già come pagati; notificarli sarebbe un falso allarme)
        try:
            _regole_rid = (
                filter_active(
                    sb.table("fornitori_pagamenti_config")
                    .select("piva_fornitore")
                    .eq("user_id", user_id)
                    .eq("ristorante_id", ristorante_id)
                    .eq("modalita", "rid")
                    .eq("attiva", True)
                )
                .execute()
            )
            _pive_rid = {str(r.get("piva_fornitore") or "").strip() for r in (_regole_rid.data or [])} - {""}
            if _pive_rid:
                docs = [d for d in docs if str(d.get("piva_fornitore") or "").strip() not in _pive_rid]
        except Exception as _rid_err:
            logger.warning(f"Filtro RID notifiche fallito (non bloccante): {_rid_err}")
        
        if not docs:
            return []
        
        scadute = []
        imminenti = []
        
        for doc in docs:
            scad_str = doc.get("scadenza_effettiva")
            if not scad_str:
                continue
            
            try:
                from datetime import datetime as dt_cls
                scad_dt = dt_cls.strptime(scad_str, "%Y-%m-%d").date()
                delta = (scad_dt - today).days
                
                if delta < 0:
                    scadute.append(doc)
                elif delta <= 7:
                    imminenti.append(doc)
            except:
                continue
        
        notifications: List[Dict[str, Any]] = []
        
        # Notifica scadute (severity: error)
        if scadute:
            count = len(scadute)
            totale = sum(float(d.get("totale_documento", 0)) for d in scadute)
            
            examples = []
            for doc in scadute[:3]:
                fornitore = _html.escape(str(doc.get("fornitore") or "?"))
                file_orig = _html.escape(str(doc.get("file_origine") or "?"))
                examples.append(f"• {fornitore} ({file_orig})")
            
            body = f"**{count}** {_pluralize(count, 'documento scaduto', 'documenti scaduti')} per € {totale:,.2f}<br/>"
            if examples:
                body += "<br/>".join(examples)
            
            notifications.append({
                'id': f'scaduti-{ristorante_id}',
                'level': 'error',
                'icon': '🔴',
                'title': f'Scadenze superate ({count})',
                'body': body,
                'toast': f"⚠️ {count} {_pluralize(count, 'fattura scaduta', 'fatture scadute')} in attesa di pagamento",
                'action_label': 'Vai ai Documenti',
                'action_page': 'pages/5_notifiche_e_gestione.py',
                'payload_data': {'count': count, 'totale': round(totale, 2)},
            })
        
        # Notifica imminenti (7 giorni)
        if imminenti:
            count = len(imminenti)
            totale = sum(float(d.get("totale_documento", 0)) for d in imminenti)
            
            examples = []
            for doc in imminenti[:3]:
                fornitore = _html.escape(str(doc.get("fornitore") or "?"))
                file_orig = _html.escape(str(doc.get("file_origine") or "?"))
                scad = _html.escape(str(doc.get("scadenza_effettiva") or "?"))
                examples.append(f"• {fornitore} ({file_orig}) - {scad}")
            
            body = f"**{count}** {_pluralize(count, 'documento in scadenza', 'documenti in scadenza')} entro 7 giorni per € {totale:,.2f}<br/>"
            if examples:
                body += "<br/>".join(examples)
            
            notifications.append({
                'id': f'imminenti-{ristorante_id}',
                'level': 'info',
                'icon': '🟡',
                'title': f'Scadenze imminenti ({count})',
                'body': body,
                'toast': f"📅 {count} {_pluralize(count, 'fattura', 'fatture')} in scadenza nei prossimi 7 giorni",
                'action_label': 'Vai ai Documenti',
                'action_page': 'pages/5_notifiche_e_gestione.py',
                'payload_data': {'count': count, 'totale': round(totale, 2)},
            })
        
        return notifications
        
    except Exception as exc:
        logger.warning(f"Errore preparazione notifiche scadenze: {exc}")
        return []


def build_trial_notifications(
    user_id: str,
    trial_info: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Crea notifiche di trial in scadenza (attivate a 3 giorni prima della fine).
    
    Args:
        user_id: ID utente
        trial_info: Dict con chiavi: is_trial (bool), days_left (int), expires_at (ISO date str)
    
    Returns:
        Lista con max 1 notifica di warning se trial scade entro 3 giorni
    """
    if not user_id or not trial_info:
        return []
    
    is_trial = trial_info.get('is_trial', False)
    days_left = trial_info.get('days_left', 0)
    expires_at = trial_info.get('expires_at', '')
    
    # Gate: attiva SOLO se trial attivo AND giorni rimanenti <= 3
    if not is_trial or days_left > 3 or days_left < 0:
        return []
    
    if days_left == 0:
        title = '⏰ Trial scade OGGI'
        body = f"La versione di prova di ONEFLUX scade oggi. Contatta il team commerciale per attivare la versione completa."
    elif days_left == 1:
        title = '⏰ Trial scade domani'
        body = f"La versione di prova di ONEFLUX scade domani ({expires_at}). Contatta il team commerciale per attivare la versione completa."
    else:  # 2 o 3 giorni
        title = f'⏰ Trial scade tra {days_left} giorni'
        body = f"La versione di prova di ONEFLUX scade il {expires_at} ({days_left} giorni rimasti). Contatta il team commerciale per attivare la versione completa."
    
    return [{
        'id': f'trial-expiry-{user_id}',
        'level': 'warning',
        'icon': '⏰',
        'title': title,
        'body': body,
        'toast': f"Trial in scadenza: {days_left} giorni rimasti",
        'action_label': 'Contatta Support',
        'action_page': 'Dashboard',
    }]


def build_food_cost_notifications(
    user_id: str,
    ristorante_id: str,
    reference_dt: Optional[datetime] = None,
    soglia_food_cost: float = 32.0,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Crea notifiche su Food Cost, MOL e trend peggioramento per il mese precedente."""
    if not user_id or not ristorante_id:
        return []

    year, month = get_previous_month_period(reference_dt)
    month_label = MESI_ITA.get(month, str(month)).title()

    try:
        dati_anno = carica_margini_anno(user_id, ristorante_id, year) or {}
    except Exception as exc:
        logger.warning(f"Errore caricamento margini per food cost {year}: {exc}")
        return []

    # Guard obbligatorio: mese assente nel dizionario -> nessuna notifica
    if month not in dati_anno:
        return []

    dati_mese = dati_anno.get(month) or {}
    fatturato_netto = float(dati_mese.get('fatturato_netto', 0.0) or 0.0)
    if fatturato_netto <= 0:
        return []

    costo_fb = float(
        dati_mese.get('costo_fb', dati_mese.get('costi_fb_totali', 0.0)) or 0.0
    )
    food_cost_pct = (costo_fb / fatturato_netto * 100.0) if fatturato_netto > 0 else 0.0

    mol_raw = dati_mese.get('mol', None)
    if mol_raw is None:
        costo_totale = float(dati_mese.get('costo_totale', 0.0) or 0.0)
        costo_personale = float(dati_mese.get('costo_dipendenti', 0.0) or 0.0)
        mol = float(fatturato_netto - costo_totale - costo_personale)
    else:
        mol = float(mol_raw or 0.0)

    notifications: List[Dict[str, Any]] = []

    if food_cost_pct > soglia_food_cost:
        notifications.append({
            'id': f'food-cost-soglia-{year}-{month:02d}',
            'level': 'warning',
            'icon': '📊',
            'title': (
                f'Food Cost {month_label} {year}: {food_cost_pct:.1f}% '
                f'— sopra soglia ({soglia_food_cost:.0f}%)'
            ),
            'body': (
                'Il Food Cost del mese supera la soglia configurata. '
                'Verifica le categorie con maggior incidenza nella '
                'pagina Calcolo Margini.'
            ),
            'toast': f'Food Cost {food_cost_pct:.1f}% — sopra soglia',
            'action_label': 'Vai alla pagina',
            'action_page': 'pages/1_calcolo_margine.py',
            'action_state_key': 'margine_tab',
            'action_state_value': 'calcolo',
        })

    if mol < 0:
        notifications.append({
            'id': f'mol-negativo-{year}-{month:02d}',
            'level': 'warning',
            'icon': '📉',
            'title': f'MOL negativo a {month_label} {year}: €{mol:.2f}',
            'body': (
                f'Il Margine Operativo Lordo di {month_label} risulta negativo. '
                'Controlla i costi operativi e il fatturato dichiarato '
                'nella pagina Calcolo Margini.'
            ),
            'toast': f'MOL negativo {month_label}: €{mol:.2f}',
            'action_label': 'Vai alla pagina',
            'action_page': 'pages/1_calcolo_margine.py',
            'action_state_key': 'margine_tab',
            'action_state_value': 'calcolo',
        })

    def _decrement_year_month(y: int, m: int) -> Tuple[int, int]:
        if m == 1:
            return y - 1, 12
        return y, m - 1

    prev_ym: List[Tuple[int, int]] = []
    _y, _m = year, month
    for _ in range(3):
        _y, _m = _decrement_year_month(_y, _m)
        prev_ym.append((_y, _m))
    # Ordine richiesto: mese-3, mese-2, mese-1
    prev_ym = list(reversed(prev_ym))

    year_cache: Dict[int, Dict[int, Dict[str, Any]]] = {year: dati_anno}
    trend_values: List[float] = []
    trend_valid = True

    for py, pm in prev_ym:
        if py not in year_cache:
            try:
                year_cache[py] = carica_margini_anno(user_id, ristorante_id, py) or {}
            except Exception:
                year_cache[py] = {}

        mese_row = (year_cache.get(py) or {}).get(pm) or {}
        fatt_prev = float(mese_row.get('fatturato_netto', 0.0) or 0.0)
        if fatt_prev <= 0:
            trend_valid = False
            break

        costo_prev = float(
            mese_row.get('costo_fb', mese_row.get('costi_fb_totali', 0.0)) or 0.0
        )
        trend_values.append((costo_prev / fatt_prev) * 100.0)

    if trend_valid and len(trend_values) == 3:
        pct_m3, pct_m2, pct_m1 = trend_values
        if pct_m3 < pct_m2 < pct_m1:
            notifications.append({
                'id': f'food-cost-trend-{year}-{month:02d}',
                'level': 'warning',
                'icon': '📈',
                'title': 'Food Cost in aumento da 3 mesi consecutivi',
                'body': (
                    'Il Food Cost cresce ogni mese: '
                    f'{pct_m3:.1f}% → {pct_m2:.1f}% → {pct_m1:.1f}%. '
                    'Valuta se e stagionalita o una tendenza da correggere.'
                ),
                'toast': 'Food Cost in aumento da 3 mesi',
                'action_label': 'Vai alla pagina',
                'action_page': 'pages/1_calcolo_margine.py',
                'action_state_key': 'margine_tab',
                'action_state_value': 'calcolo',
            })

    return notifications


def _short_hash(value: str, length: int = 12) -> str:
    raw = str(value or '').strip().encode('utf-8', errors='ignore')
    return hashlib.md5(raw, usedforsecurity=False).hexdigest()[:length]


def _piva_is_valid(value: Any) -> bool:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return len(digits) >= 11


def build_controllo_prezzi_notifications(
    user_id: str,
    ristorante_id: str,
    upload_context: Optional[Dict[str, Any]] = None,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Costruisce notifiche per controllo prezzi e note credito."""
    if not user_id or not ristorante_id:
        return []

    try:
        from services import get_supabase_client

        sb = supabase_client or get_supabase_client()
        today = date.today()
        now_utc = datetime.now(timezone.utc)
        notifications: List[Dict[str, Any]] = []

        current_files = list((upload_context or {}).get('successful_files') or [])
        upload_id = str((upload_context or {}).get('upload_id') or '').strip()

        # 1) nota_credito_non_usata (TD04 > 30 giorni, nessun acquisto TD01/TD06 entro +45 giorni)
        # Limita a ultimi 180 giorni (NC più vecchie raramente rilevanti) e cap totale
        since_180_nc = (today - timedelta(days=180)).isoformat()
        nc_rows = (
            sb.table('fatture')
            .select('file_origine,fornitore,totale_documento,data_documento,created_at,piva_cedente,tipo_documento')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .eq('tipo_documento', 'TD04')
            .gte('data_documento', since_180_nc)
            .is_('deleted_at', 'null')
            .limit(500)
            .execute().data or []
        )
        if current_files:
            allowed = {str(f).strip() for f in current_files if str(f).strip()}
            nc_rows = [r for r in nc_rows if str(r.get('file_origine') or '').strip() in allowed]

        for row in nc_rows:
            piva = str(row.get('piva_cedente') or '').strip()
            if not _piva_is_valid(piva):
                continue

            file_origine = str(row.get('file_origine') or '').strip()
            fornitore = str(row.get('fornitore') or '?').strip()
            importo = abs(float(row.get('totale_documento') or 0.0))
            data_doc_s = str(row.get('data_documento') or '').strip()
            created_at_s = str(row.get('created_at') or '').strip()

            try:
                created_dt = datetime.fromisoformat(created_at_s.replace('Z', '+00:00')).date()
            except Exception:
                continue
            giorni = (today - created_dt).days
            if giorni <= 30:
                continue

            try:
                data_td04 = date.fromisoformat(data_doc_s)
            except Exception:
                continue

            upper = (data_td04 + timedelta(days=45)).isoformat()
            acquisti = (
                sb.table('fatture')
                .select('id', count='exact')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .in_('tipo_documento', ['TD01', 'TD06'])
                .eq('piva_cedente', piva)
                .gte('data_documento', data_td04.isoformat())
                .lte('data_documento', upper)
                .is_('deleted_at', 'null')
                .limit(1)
                .execute()
            )
            if int(getattr(acquisti, 'count', 0) or 0) > 0:
                continue

            notifications.append({
                'id': f'nc-non-usata-{_short_hash(file_origine)}',
                'level': 'info',
                'icon': '🧾',
                'title': f'Nota di credito non compensata — {fornitore}',
                'body': (
                    f'La nota di credito di €{importo:.2f} da {fornitore} ricevuta {giorni} giorni fa '
                    'non risulta ancora compensata da un acquisto successivo. Verifica se e stata applicata.'
                ),
                'toast': f'Nota credito non compensata: {fornitore}',
                'action_label': 'Vai alla pagina',
                'action_page': 'pages/3_controllo_prezzi.py',
                'action_state_key': 'cp_tab_attivo',
                'action_state_value': 'nc',
            })

        # 2) sconto_fornitore_scaduto
        current_rows: List[Dict[str, Any]] = []
        if current_files:
            current_rows = (
                sb.table('fatture')
                .select('fornitore,piva_cedente,sconto_percentuale,file_origine,data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .in_('file_origine', current_files)
                .is_('deleted_at', 'null')
                .execute().data or []
            )
        else:
            since_7 = (today - timedelta(days=7)).isoformat()
            current_rows = (
                sb.table('fatture')
                .select('fornitore,piva_cedente,sconto_percentuale,file_origine,data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .gte('data_documento', since_7)
                .is_('deleted_at', 'null')
                .execute().data or []
            )

        supplier_current: Dict[str, Dict[str, Any]] = {}
        for row in current_rows:
            piva = str(row.get('piva_cedente') or '').strip()
            if not _piva_is_valid(piva):
                continue
            fornitore = str(row.get('fornitore') or piva).strip() or piva
            sconto_val = float(row.get('sconto_percentuale') or 0.0)
            item = supplier_current.setdefault(piva, {'fornitore': fornitore, 'has_discount': False})
            if sconto_val > 0:
                item['has_discount'] = True

        if supplier_current:
            since_90 = (today - timedelta(days=90)).isoformat()
            storico_rows = (
                sb.table('fatture')
                .select('fornitore,piva_cedente,sconto_percentuale,data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .gte('data_documento', since_90)
                .is_('deleted_at', 'null')
                .execute().data or []
            )

            storico_sconti_count: Dict[str, int] = {}
            for row in storico_rows:
                piva = str(row.get('piva_cedente') or '').strip()
                if not piva:
                    continue
                sconto_val = float(row.get('sconto_percentuale') or 0.0)
                if sconto_val > 0:
                    storico_sconti_count[piva] = storico_sconti_count.get(piva, 0) + 1

            for piva, meta in supplier_current.items():
                if meta.get('has_discount'):
                    continue
                if int(storico_sconti_count.get(piva, 0)) < 2:
                    continue
                fornitore = str(meta.get('fornitore') or piva)
                notifications.append({
                    'id': f'sconto-scaduto-{piva}',
                    'level': 'info',
                    'icon': '🎁',
                    'title': f'Sconti non piu presenti — {fornitore}',
                    'body': (
                        f"{fornitore} non ha applicato sconti nell'ultimo ordine ricevuto. "
                        'Nelle fatture precedenti erano presenti sconti. Verifica se l accordo e ancora attivo.'
                    ),
                    'toast': f'Sconti assenti: {fornitore}',
                    'action_label': 'Vai alla pagina',
                    'action_page': 'pages/3_controllo_prezzi.py',
                    'action_state_key': 'cp_tab_attivo',
                    'action_state_value': 'sconti',
                })

        # 3) prezzo_prodotto_record_storico
        target_rows: List[Dict[str, Any]] = []
        if current_files:
            target_rows = (
                sb.table('fatture')
                .select('fornitore,piva_cedente,descrizione,prezzo_unitario,unita_misura,file_origine')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .in_('file_origine', current_files)
                .is_('deleted_at', 'null')
                .execute().data or []
            )
        else:
            since_7 = (today - timedelta(days=7)).isoformat()
            target_rows = (
                sb.table('fatture')
                .select('fornitore,piva_cedente,descrizione,prezzo_unitario,unita_misura,file_origine,data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .gte('data_documento', since_7)
                .is_('deleted_at', 'null')
                .execute().data or []
            )

        # ⚡ Pre-carica storici prezzi UNA volta per tutte le P.IVA target (evita N+1)
        _pivas_target: Set[str] = {
            str(r.get('piva_cedente') or '').strip()
            for r in target_rows
            if _piva_is_valid(str(r.get('piva_cedente') or '').strip())
        }
        storici_per_piva: Dict[str, List[Dict[str, Any]]] = {}
        if _pivas_target:
            try:
                _pivas_list = list(_pivas_target)
                # Batch IN query: limita a 200 P.IVA per evitare URL troppo lungo
                for _i in range(0, len(_pivas_list), 200):
                    _chunk = _pivas_list[_i:_i + 200]
                    _storici_resp = (
                        sb.table('fatture')
                        .select('prezzo_unitario,file_origine,descrizione,piva_cedente')
                        .eq('user_id', user_id)
                        .eq('ristorante_id', ristorante_id)
                        .in_('piva_cedente', _chunk)
                        .is_('deleted_at', 'null')
                        .limit(50000)
                        .execute().data or []
                    )
                    for _s in _storici_resp:
                        _p = str(_s.get('piva_cedente') or '').strip()
                        if _p:
                            storici_per_piva.setdefault(_p, []).append(_s)
            except Exception as _e:
                logger.warning(f"Errore pre-fetch storici prezzi (fallback per riga): {_e}")
                storici_per_piva = {}

        record_seen: Set[str] = set()
        for row in target_rows:
            piva = str(row.get('piva_cedente') or '').strip()
            descrizione = str(row.get('descrizione') or '').strip()
            prezzo = float(row.get('prezzo_unitario') or 0.0)
            um = str(row.get('unita_misura') or 'UM').strip() or 'UM'
            fornitore = str(row.get('fornitore') or piva or '?').strip()
            if not _piva_is_valid(piva) or not descrizione or prezzo <= 0:
                continue

            key_norm = normalizza_stringa(descrizione)
            if not key_norm:
                continue
            unique_key = f'{piva}::{key_norm}'

            storici = storici_per_piva.get(piva)
            if storici is None:
                # Fallback se pre-fetch fallito
                storici = (
                    sb.table('fatture')
                    .select('prezzo_unitario,file_origine,descrizione')
                    .eq('user_id', user_id)
                    .eq('ristorante_id', ristorante_id)
                    .eq('piva_cedente', piva)
                    .is_('deleted_at', 'null')
                    .execute().data or []
                )

            history_prices: List[float] = []
            for s_row in storici:
                s_desc = normalizza_stringa(str(s_row.get('descrizione') or ''))
                if s_desc != key_norm:
                    continue
                s_price = float(s_row.get('prezzo_unitario') or 0.0)
                if s_price > 0:
                    history_prices.append(s_price)

            if len(history_prices) < 5:
                continue

            prev_max = max(history_prices)
            if prev_max <= 0:
                continue
            if prezzo <= prev_max * 1.10:
                continue
            if unique_key in record_seen:
                continue

            aumento_pct = ((prezzo - prev_max) / prev_max) * 100.0
            record_seen.add(unique_key)
            notifications.append({
                'id': f'record-prezzo-{key_norm[:30]}',
                'level': 'warning',
                'icon': '🔝',
                'title': f'Nuovo record prezzo: {descrizione[:40]}',
                'body': (
                    f'{descrizione} ha raggiunto il prezzo record di €{prezzo:.4f}/{um} da {fornitore} '
                    f'— il piu alto registrato (+{aumento_pct:.1f}% rispetto al precedente).'
                ),
                'toast': f'Record prezzo: {descrizione[:30]}',
                'action_label': 'Vai alla pagina',
                'action_page': 'pages/3_controllo_prezzi.py',
                'action_state_key': 'cp_tab_attivo',
                'action_state_value': 'variazioni',
            })

        # Notifica "fornitore_unico_categoria" dismessa per scelta prodotto.

        return notifications
    except Exception as exc:
        logger.warning(f'Errore preparazione notifiche controllo prezzi: {exc}')
        return []


def build_qualita_anagrafica_notifications(
    user_id: str,
    ristorante_id: str,
    upload_context: Optional[Dict[str, Any]] = None,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Notifiche di qualità anagrafica fornitori (P.IVA mancante/non valida)."""
    if not user_id or not ristorante_id:
        return []

    try:
        from services import get_supabase_client

        sb = supabase_client or get_supabase_client()
        today = date.today()
        files = list((upload_context or {}).get('successful_files') or [])

        rows: List[Dict[str, Any]] = []
        if files:
            rows = (
                sb.table('fatture_documenti')
                .select('fornitore,piva_fornitore,file_origine,data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .in_('file_origine', files)
                .is_('deleted_at', 'null')
                .execute().data or []
            )
        else:
            since_7 = (today - timedelta(days=7)).isoformat()
            rows = (
                sb.table('fatture_documenti')
                .select('fornitore,piva_fornitore,file_origine,data_documento')
                .eq('user_id', user_id)
                .eq('ristorante_id', ristorante_id)
                .gte('data_documento', since_7)
                .is_('deleted_at', 'null')
                .execute().data or []
            )

        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            piva = str(row.get('piva_fornitore') or '').strip()
            if _piva_is_valid(piva):
                continue
            fornitore = str(row.get('fornitore') or 'FORNITORE SCONOSCIUTO').strip() or 'FORNITORE SCONOSCIUTO'
            key = normalizza_stringa(fornitore)[:20] or 'SCONOSCIUTO'
            if key not in grouped:
                grouped[key] = {'fornitore': fornitore, 'count': 0}
            grouped[key]['count'] += 1

        notifications: List[Dict[str, Any]] = []
        for key, data in grouped.items():
            fornitore = str(data['fornitore'])
            count = int(data['count'])
            notifications.append({
                'id': f'piva-mancante-{key}',
                'level': 'info',
                'icon': '📋',
                'title': f'P.IVA mancante: {fornitore}',
                'body': (
                    f'{fornitore} ha {count} {"fattura" if count == 1 else "fatture"} senza P.IVA cedente. '
                    'Senza P.IVA il sistema non puo rilevare duplicati o tracciare variazioni prezzo per questo fornitore.'
                ),
                'toast': f'P.IVA mancante: {fornitore}',
                'action_label': 'Vai alla pagina',
                'action_page': 'pages/5_notifiche_e_gestione.py',
            })

        return notifications
    except Exception as exc:
        logger.warning(f'Errore preparazione notifiche qualità anagrafica: {exc}')
        return []


def build_efficiency_spesa_notifications(
    fatturato_data: pd.DataFrame,
    spesa_data: pd.DataFrame,
    threshold_pct: float = 5.0,
    ristorante_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Crea notifiche per aumenti significativi nell'incidenza spesa/fatturato."""
    if fatturato_data.empty or spesa_data.empty:
        return []

    # Unisci i dati su mese e dimensione (categoria o fornitore)
    merged_data = pd.merge(
        spesa_data, fatturato_data,
        on=['mese', 'dimensione'],
        how='inner'
    )

    # Calcola l'incidenza e il trend mese su mese (guardia divisione per zero)
    merged_data['incidenza'] = merged_data.apply(
        lambda r: (float(r['spesa_totale']) / float(r['fatturato_totale']) * 100.0)
        if float(r.get('fatturato_totale') or 0) > 0 else 0.0,
        axis=1,
    )
    merged_data['trend'] = merged_data.groupby('dimensione')['incidenza'].pct_change() * 100

    # Filtra aumenti significativi
    alerts = merged_data[merged_data['trend'] > threshold_pct]

    notifications = []
    for _, row in alerts.iterrows():
        dimensione = row['dimensione']
        trend = row['trend']
        incidenza = row['incidenza']
        mese = row['mese']

        notifications.append({
            'id': build_scoped_notification_id(f'efficiency-alert:{dimensione}:{mese}', ristorante_id),
            'level': 'warning',
            'icon': '📊',
            'title': f'Aumento incidenza spesa per {dimensione}',
            'body': (
                f"L'incidenza della spesa per {dimensione} è aumentata del {trend:.1f}% "
                f"nel mese di {mese}. Incidenza attuale: {incidenza:.1f}%"
            ),
            'toast': f'Incidenza spesa aumentata: {dimensione}',
            'action_label': 'Vai alla sezione',
            'action_page': 'pages/4_analisi_personalizzata.py',
            'action_state_key': 'af_tab_attivo',
            'action_state_value': 'categorie' if 'Categoria' in dimensione else 'fornitori',
        })

    return notifications


def build_da_classificare_notifications(
    user_id: str,
    ristorante_id: Optional[str],
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Notifica persistente per righe fattura che richiedono classificazione manuale.

    Conta le righe con needs_review=True (oppure categoria NULL/vuota/'Da Classificare')
    che non sono state ancora risolte dall'utente. Se presenti, restituisce una notifica
    di tipo 'warning' con il conteggio e un link alla pagina di gestione.
    """
    if not user_id:
        return []
    try:
        if supabase_client is None:
            from services import get_supabase_client
            supabase_client = get_supabase_client()

        # Conta righe che richiedono review: needs_review=True o categoria assente
        query = (
            supabase_client.table('fatture')
            .select('id', count='exact')
            .eq('user_id', user_id)
            .is_('deleted_at', 'null')
            .or_('needs_review.eq.true,categoria.is.null,categoria.eq.')
        )
        if ristorante_id:
            query = query.eq('ristorante_id', ristorante_id)
        result = query.limit(0).execute()
        count = getattr(result, 'count', None)
        if count is None or count <= 0:
            return []

        # Recupera esempi (max 5 descrizioni)
        sample_query = (
            supabase_client.table('fatture')
            .select('descrizione')
            .eq('user_id', user_id)
            .is_('deleted_at', 'null')
            .or_('needs_review.eq.true,categoria.is.null,categoria.eq.')
        )
        if ristorante_id:
            sample_query = sample_query.eq('ristorante_id', ristorante_id)
        sample_result = sample_query.limit(5).execute()
        examples = []
        seen_desc: set = set()
        for row in (sample_result.data or []):
            desc = str(row.get('descrizione') or '').strip()
            if desc and desc not in seen_desc:
                examples.append(_html.escape(desc))
                seen_desc.add(desc)

        righe_label = _pluralize(count, 'riga richiede', 'righe richiedono')
        body = (
            f"{count} {righe_label} classificazione manuale perché la descrizione è "
            "ambigua o troppo generica per una categorizzazione automatica affidabile."
        )
        if examples:
            body += "<br/>Esempi:<br/>• " + "<br/>• ".join(examples)

        return [{
            'id': f'da-classificare-{user_id[:8]}-{ristorante_id or "all"}',
            'level': 'warning',
            'icon': '🏷️',
            'title': f'{count} {_pluralize(count, "prodotto da classificare", "prodotti da classificare")}',
            'body': body,
            'toast': (
                f'{count} {_pluralize(count, "riga da classificare", "righe da classificare")} '
                f'richied{_pluralize(count, "e", "ono")} attenzione'
            ),
            'action_label': 'Vai alla gestione',
            'action_page': 'pages/5_notifiche_e_gestione.py',
        }]
    except Exception as exc:
        logger.warning(f'Errore build_da_classificare_notifications: {exc}')
        return []
