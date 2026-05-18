"""Servizio Daily Briefing: genera e salva uno snapshot giornaliero delle notifiche.

Responsabilità:
- get_today_briefing   : legge snapshot di oggi da daily_briefing_state
- generate_and_save_briefing : costruisce snapshot deterministico + upsert su DB
- _build_snapshot      : logica pura di composizione bullets (no AI)

Quota bullet: 3 slot L1 (severity=error) + 2 slot L2 (warning/info).
Nessuna promozione di slot tra livelli.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import re as _re

from config.logger_setup import get_logger

try:
    from zoneinfo import ZoneInfo
    _TZ_ROME = ZoneInfo("Europe/Rome")
except ImportError:
    _TZ_ROME = None

logger = get_logger('daily_briefing')

# ============================================================
# COSTANTI
# ============================================================

_QUOTA_L1 = 3   # slot riservati a severity=error
_QUOTA_L2 = 2   # slot riservati a severity=warning/info

# Topic riconosciuti → livello slot
_TOPIC_SLOT: Dict[str, str] = {
    'scadenza_superata':        'L1',
    'upload_failed':            'L1',
    'scadenza_imminente':       'L2',
    'fatturato_mancante':       'L2',
    'costo_personale_mancante': 'L2',
    'price_alert':              'L2',
    'uncategorized_rows':       'L2',
}

# Ordine di priorità all'interno dello stesso slot (più basso = prima)
_TOPIC_PRIORITY: Dict[str, int] = {
    'scadenza_superata':        10,
    'upload_failed':            20,
    'scadenza_imminente':       30,
    'fatturato_mancante':       40,
    'costo_personale_mancante': 50,
    'price_alert':              60,
    'uncategorized_rows':       70,
}


# ============================================================
# HELPERS INTERNI
# ============================================================

def _today_rome() -> date:
    """Restituisce la data odierna nel fuso Europe/Rome."""
    if _TZ_ROME:
        return datetime.now(tz=_TZ_ROME).date()
    return date.today()


def _severity_max(notifications: List[Dict[str, Any]]) -> str:
    """Restituisce la severità più alta tra le notifiche passate."""
    best = 'info'
    for n in notifications:
        sev = str(n.get('severity') or '')
        if sev == 'error':
            return 'error'
        if sev == 'warning':
            best = 'warning'
    return best


def _bullet_for(notif: Dict[str, Any]) -> str:
    """Genera il testo del bullet per una notifica usando payload quando disponibile."""
    topic = str(notif.get('topic_key') or '')
    payload = notif.get('payload') or {}
    title = str(notif.get('title') or '')

    if topic == 'scadenza_superata':
        count = payload.get('count')
        totale = payload.get('totale')
        if count and totale is not None:
            parola = 'fattura scaduta' if count == 1 else 'fatture scadute'
            return f"\u26a0\ufe0f {count} {parola} per \u20ac {totale:,.2f} \u2014 controlla il pagamento."
        return f"\u26a0\ufe0f {title}"

    if topic == 'upload_failed':
        count = payload.get('count')
        if count:
            parola = 'fattura non \u00e8 stata caricata' if count == 1 else 'fatture non sono state caricate'
            return f"\u274c {count} {parola} \u2014 riprova o contatta il supporto."
        return f"\u274c {title}"

    if topic == 'scadenza_imminente':
        count = payload.get('count')
        totale = payload.get('totale')
        if count and totale is not None:
            parola = 'fattura in scadenza' if count == 1 else 'fatture in scadenza'
            return f"\U0001F4C5 {count} {parola} entro 7 giorni per \u20ac {totale:,.2f}."
        return f"\U0001F4C5 {title}"

    if topic == 'fatturato_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if mese and anno:
            return f"\U0001F4CA Il fatturato di {mese} {anno} non \u00e8 ancora stato inserito."
        return f"\U0001F4CA {title}"

    if topic == 'costo_personale_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if mese and anno:
            return f"\U0001F465 Il costo del personale di {mese} {anno} non \u00e8 ancora stato inserito."
        return f"\U0001F465 {title}"

    if topic == 'price_alert':
        count = payload.get('count')
        top_product = payload.get('top_product')
        top_pct = payload.get('top_increase_pct')
        if count:
            prodotti = 'prodotto' if count == 1 else 'prodotti'
            base = f"\U0001F4C8 Alert prezzi su {count} {prodotti}"
            if top_product and top_pct is not None:
                base += f" \u2014 es. {top_product} +{top_pct:.1f}%"
            return base + "."
        return f"\U0001F4C8 {title}"

    if topic == 'uncategorized_rows':
        count = payload.get('uncategorized_rows') or payload.get('count')
        if count:
            righe = 'riga richiede' if count == 1 else 'righe richiedono'
            return f"\U0001F3F7\ufe0f {count} {righe} classificazione manuale."
        return f"\U0001F3F7\ufe0f {title}"

    # Fallback generico: restituisce il titolo della notifica
    return title


def _parse_count_from_title(title: str) -> Optional[int]:
    """Estrae il numero tra parentesi da titoli come 'Scadenze superate (300)'."""
    m = _re.search(r'\((\d+)\)', title)
    return int(m.group(1)) if m else None


def _parse_mese_anno_from_title(title: str):
    """Estrae (mese, anno) da titoli come '... di Aprile 2026 ...'."""
    m = _re.search(r'di ([A-Za-zÀ-ú]+)\s+(\d{4})', title)
    if m:
        return m.group(1).capitalize(), int(m.group(2))
    return None, None


def _narrative_phrase_for(notif: Dict[str, Any]) -> str:
    """Frase narrativa con contesto e motivazione per un singolo topic."""
    topic = str(notif.get('topic_key') or '')
    payload = notif.get('payload') or {}
    title = str(notif.get('title') or '')

    if topic == 'scadenza_superata':
        count = payload.get('count') or _parse_count_from_title(title)
        if count:
            parola = 'scadenza superata' if count == 1 else 'scadenze superate'
            return (
                f"Abbiamo {count} {parola}: controlla di aver confermato il pagamento "
                f"o di aver impostato la giusta data di scadenza."
            )
        return f"{title}."

    if topic == 'upload_failed':
        count = payload.get('count') or _parse_count_from_title(title)
        if count:
            if count == 1:
                return (
                    "Una fattura non \u00e8 stata caricata correttamente: riprova l'upload "
                    "o contatta il supporto per non perdere nessun documento."
                )
            return (
                f"{count} fatture non sono state caricate correttamente: riprova l'upload "
                "o contatta il supporto per non perdere nessun documento."
            )
        return f"{title}."

    if topic == 'scadenza_imminente':
        count = payload.get('count') or _parse_count_from_title(title)
        totale = payload.get('totale')
        if count:
            parola = 'fattura scade' if count == 1 else 'fatture scadono'
            base = f"{count} {parola} entro i prossimi 7 giorni"
            if totale is not None:
                base += f" (\u20ac\u00a0{int(totale):,})".replace(',', '.')
            return base + ": \u00e8 il momento giusto per verificare che i pagamenti siano in ordine."
        return f"{title}."

    if topic == 'fatturato_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if not (mese and anno):
            mese, anno = _parse_mese_anno_from_title(title)
        if mese and anno:
            return (
                f"Il fatturato di {mese} {anno} non \u00e8 ancora stato inserito: "
                f"aggiornarlo ti permette di vedere in tempo reale come stai andando."
            )
        return f"{title}."

    if topic == 'costo_personale_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if not (mese and anno):
            mese, anno = _parse_mese_anno_from_title(title)
        if mese and anno:
            return (
                f"Il costo del personale di {mese} {anno} manca ancora: "
                f"senza di esso MOL e percentuali di margine non sono affidabili."
            )
        return f"{title}."

    if topic == 'price_alert':
        count = payload.get('count') or _parse_count_from_title(title)
        top_product = payload.get('top_product')
        top_pct = payload.get('top_increase_pct')
        if count:
            prodotti = 'prodotto ha avuto una variazione di prezzo' if count == 1 else 'prodotti hanno avuto variazioni di prezzo'
            base = f"{count} {prodotti} significativa"
            if top_product and top_pct is not None:
                base += f" (es. {top_product} +{top_pct:.1f}%)"
            return base + ": vale la pena controllare se impattano i tuoi margini."
        return f"{title}."

    if topic == 'uncategorized_rows':
        count = payload.get('uncategorized_rows') or payload.get('count') or _parse_count_from_title(title)
        if count:
            righe = 'riga attende' if count == 1 else 'righe attendono'
            return (
                f"{count} {righe} classificazione manuale: "
                f"categorizzarle rende i tuoi report pi\u00f9 precisi e affidabili."
            )
        return f"{title}."

    return f"{title}."


def _compose_narrative(selected: List[Dict[str, Any]], severity_max: str) -> str:
    """Compone il testo narrativo colloquiale con apertura, corpo e chiusura.

    Gestisce la fusione di fatturato_mancante + costo_personale_mancante
    quando si riferiscono allo stesso mese/anno.
    """
    if not selected:
        return "Ciao!\nTutto in ordine per oggi. Buon lavoro!"

    sentences: List[str] = []
    skip_topics: set = set()

    # Fusione fatturato + costo personale stesso mese/anno
    fat = next((n for n in selected if n.get('topic_key') == 'fatturato_mancante'), None)
    costo = next((n for n in selected if n.get('topic_key') == 'costo_personale_mancante'), None)
    if fat and costo:
        fp = fat.get('payload') or {}
        cp = costo.get('payload') or {}
        fat_mese = fp.get('mese') or _parse_mese_anno_from_title(str(fat.get('title') or ''))[0]
        fat_anno = fp.get('anno') or _parse_mese_anno_from_title(str(fat.get('title') or ''))[1]
        cp_mese  = cp.get('mese') or _parse_mese_anno_from_title(str(costo.get('title') or ''))[0]
        cp_anno  = cp.get('anno') or _parse_mese_anno_from_title(str(costo.get('title') or ''))[1]
        if fat_mese and fat_mese == cp_mese and fat_anno and fat_anno == cp_anno:
            mese, anno = fat_mese, fat_anno
            sentences.append(
                f"Il fatturato e il costo del personale di {mese} {anno} non li hai ancora inseriti: "
                f"se li inserisci puoi scoprire quanto stai marginando e se stai migliorando!"
            )
            skip_topics = {'fatturato_mancante', 'costo_personale_mancante'}

    for n in selected:
        if n.get('topic_key') in skip_topics:
            continue
        sentences.append(_narrative_phrase_for(n))

    body = "\n".join(sentences)
    return f"Ciao! Vediamo il lavoro da fare oggi:\n{body}\nBuon lavoro"



# ============================================================
# LOGICA SNAPSHOT (pura, testabile)
# ============================================================

def _build_snapshot(notifications: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Costruisce lo snapshot giornaliero in modo deterministico (no AI).

    - Deduplica per topic_key (tiene la prima occorrenza, le notifiche arrivano
      ordinate per source_event_at DESC da get_inbox_notifications)
    - Separa in L1 (error) e L2 (warning/info)
    - Ordina per priorita\u2019 interna
    - Applica quota: max _QUOTA_L1 L1 + max _QUOTA_L2 L2
    - Nessuna promozione di slot
    """
    seen_topics: Dict[str, Dict[str, Any]] = {}
    for n in notifications:
        t = str(n.get('topic_key') or '')
        if t and t not in seen_topics:
            seen_topics[t] = n

    known = [n for n in seen_topics.values() if n.get('topic_key') in _TOPIC_SLOT]

    l1 = sorted(
        [n for n in known if _TOPIC_SLOT[n['topic_key']] == 'L1'],
        key=lambda n: _TOPIC_PRIORITY.get(str(n.get('topic_key', '')), 99),
    )
    l2 = sorted(
        [n for n in known if _TOPIC_SLOT[n['topic_key']] == 'L2'],
        key=lambda n: _TOPIC_PRIORITY.get(str(n.get('topic_key', '')), 99),
    )

    selected = l1[:_QUOTA_L1] + l2[:_QUOTA_L2]
    bullets = [_bullet_for(n) for n in selected]
    sev_max = _severity_max(notifications)

    return {
        'bullets': bullets,
        'narrative': _compose_narrative(selected, sev_max),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'notif_count': len(notifications),
        'severity_max': sev_max,
    }


# ============================================================
# CRUD
# ============================================================

def get_today_briefing(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Optional[Dict[str, Any]]:
    """Legge lo snapshot di oggi da daily_briefing_state.

    Restituisce il dict snapshot se esiste, None altrimenti.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return None
    try:
        today = _today_rome().isoformat()
        resp = (
            supabase_client.table('daily_briefing_state')
            .select('snapshot,created_at')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .eq('generated_for_date', today)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows:
            snap = dict(rows[0].get('snapshot') or {})
            snap['_db_created_at'] = rows[0].get('created_at')
            return snap
        return None
    except Exception as exc:
        logger.error("Errore get_today_briefing: %s", exc)
        return None


def generate_and_save_briefing(
    user_id: str,
    ristorante_id: str,
    notifications: List[Dict[str, Any]],
    supabase_client=None,
) -> Optional[Dict[str, Any]]:
    """Genera snapshot deterministico dalle notifiche e lo salva su DB.

    Upsert su (user_id, ristorante_id, generated_for_date).
    Restituisce lo snapshot salvato, None in caso di errore.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return None
    try:
        today = _today_rome()
        snapshot = _build_snapshot(notifications)
        snapshot['generated_for_date'] = today.isoformat()

        record = {
            'user_id':            user_id,
            'ristorante_id':      ristorante_id,
            'generated_for_date': today.isoformat(),
            'snapshot':           snapshot,
            'updated_at':         datetime.now(timezone.utc).isoformat(),
        }
        (
            supabase_client.table('daily_briefing_state')
            .upsert(record, on_conflict='user_id,ristorante_id,generated_for_date')
            .execute()
        )
        logger.info(
            "Briefing generato per ristorante_id=%s data=%s bullets=%d",
            ristorante_id, today.isoformat(), len(snapshot['bullets']),
        )
        return snapshot
    except Exception as exc:
        logger.error("Errore generate_and_save_briefing: %s", exc)
        return None
