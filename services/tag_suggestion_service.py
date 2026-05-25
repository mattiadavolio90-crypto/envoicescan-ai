"""Motore suggerimenti tag (new_tag + extend_tag) con workflow assistito.

Pipeline v1:
- analizza fatture ultimi N giorni (default 30)
- genera suggerimenti pending con soglie min prodotti/min occorrenze
- persiste suggerimenti + items
- genera notifiche inbox aggregate per i due topic richiesti
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from config.logger_setup import get_logger
from services import get_supabase_client
from services.db_service import _normalize_custom_tag_key, aggiungi_associazioni, clear_tags_cache, crea_tag
from services.notification_inbox_service import build_notification_record, upsert_inbox_notifications

logger = get_logger('tag_suggestion_service')

WINDOW_DAYS_DEFAULT = 30
MIN_PRODUCTS_DEFAULT = 6
MIN_ROWS_DEFAULT = 12
MIN_SCORE_EXTEND_DEFAULT = 0.82
MAX_POOL_ROWS = 12000
MAX_SUGGESTIONS_PER_TYPE = 20

_STOPWORDS = {
    'DI', 'DA', 'DE', 'DEL', 'DELLA', 'DELLO', 'DEI', 'E', 'IN', 'CON',
    'AL', 'ALLA', 'AI', 'PER', 'THE', 'AND', 'A', 'KG', 'GR', 'LT', 'ML', 'CL',
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize_key(descrizione_key: str) -> List[str]:
    tokens = [t.strip() for t in str(descrizione_key or '').split(' ') if t.strip()]
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _similarity_score(a_key: str, b_key: str) -> float:
    if not a_key or not b_key:
        return 0.0
    a_tokens = set(_tokenize_key(a_key))
    b_tokens = set(_tokenize_key(b_key))

    token_overlap = 0.0
    if a_tokens or b_tokens:
        inter = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        token_overlap = (inter / union) if union > 0 else 0.0

    fuzzy = SequenceMatcher(None, a_key, b_key).ratio()
    return max(token_overlap, fuzzy)


def _fetch_recent_rows(
    user_id: str,
    ristorante_id: str,
    window_days: int,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    sb = supabase_client or get_supabase_client()
    since_iso = (_utcnow() - timedelta(days=max(1, int(window_days)))).date().isoformat()

    rows = (
        sb.table('fatture')
        .select('descrizione,fornitore,data_documento')
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .gte('data_documento', since_iso)
        .is_('deleted_at', 'null')
        .limit(MAX_POOL_ROWS)
        .execute().data or []
    )
    return rows


def _aggregate_pool(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    pool: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        descrizione = str(row.get('descrizione') or '').strip()
        if not descrizione:
            continue
        key = _normalize_custom_tag_key(descrizione)
        if not key:
            continue

        item = pool.setdefault(
            key,
            {
                'descrizione': descrizione,
                'descrizione_key': key,
                'occorrenze': 0,
                'fornitori': set(),
                'ultima_data': row.get('data_documento'),
            },
        )
        item['occorrenze'] += 1

        fornitore = str(row.get('fornitore') or '').strip()
        if fornitore:
            item['fornitori'].add(fornitore)

        data_doc = row.get('data_documento')
        if data_doc and (not item['ultima_data'] or data_doc > item['ultima_data']):
            item['ultima_data'] = data_doc

    for val in pool.values():
        val['fornitori_count'] = len(val['fornitori'])
        val.pop('fornitori', None)

    return pool


def _fetch_tags_and_assoc(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> tuple[List[Dict[str, Any]], Dict[int, List[str]], set[str]]:
    sb = supabase_client or get_supabase_client()

    tags = (
        sb.table('custom_tags')
        .select('id,nome,emoji,colore')
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .execute().data or []
    )

    tag_ids = [int(t['id']) for t in tags if t.get('id') is not None]
    if not tag_ids:
        return tags, {}, set()

    assocs = (
        sb.table('custom_tag_prodotti')
        .select('tag_id,descrizione_key')
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .in_('tag_id', tag_ids)
        .execute().data or []
    )

    tag_assoc_keys: Dict[int, List[str]] = defaultdict(list)
    all_tag_keys: set[str] = set()
    for assoc in assocs:
        tag_id = assoc.get('tag_id')
        key = str(assoc.get('descrizione_key') or '').strip()
        if tag_id is None or not key:
            continue
        tag_assoc_keys[int(tag_id)].append(key)
        all_tag_keys.add(key)

    return tags, dict(tag_assoc_keys), all_tag_keys


def _build_new_tag_suggestions(
    untagged_pool: Dict[str, Dict[str, Any]],
    min_products: int,
    min_rows: int,
    window_days: int,
) -> List[Dict[str, Any]]:
    token_to_keys: Dict[str, List[str]] = defaultdict(list)

    for key in untagged_pool.keys():
        seen = set(_tokenize_key(key))
        for tok in seen:
            token_to_keys[tok].append(key)

    suggestions: List[Dict[str, Any]] = []
    for token, keys in token_to_keys.items():
        uniq_keys = sorted(set(keys))
        if len(uniq_keys) < min_products:
            continue

        matched_rows = sum(int(untagged_pool[k]['occorrenze']) for k in uniq_keys)
        if matched_rows < min_rows:
            continue

        items = []
        for k in uniq_keys:
            p = untagged_pool[k]
            items.append(
                {
                    'descrizione': p['descrizione'],
                    'descrizione_key': p['descrizione_key'],
                    'occorrenze': int(p['occorrenze']),
                    'fornitori_count': int(p['fornitori_count']),
                    'last_seen_date': p['ultima_data'],
                    'selected_by_default': True,
                }
            )

        confidence = min(100.0, 60.0 + len(uniq_keys) * 2.0)
        suggestions.append(
            {
                'suggestion_type': 'new_tag',
                'status': 'pending',
                'suggested_tag_name': token.title(),
                'target_tag_id': None,
                'cluster_key': f'new_tag::{token}',
                'confidence_score': round(confidence, 2),
                'detection_window_days': int(window_days),
                'matched_products_count': len(uniq_keys),
                'matched_rows_count': matched_rows,
                'items': items,
            }
        )

    suggestions.sort(key=lambda x: (-x['matched_products_count'], -x['matched_rows_count']))
    return suggestions[:MAX_SUGGESTIONS_PER_TYPE]


def _build_extend_tag_suggestions(
    tags: List[Dict[str, Any]],
    tag_assoc_keys: Dict[int, List[str]],
    untagged_pool: Dict[str, Dict[str, Any]],
    min_products: int,
    min_score: float,
    window_days: int,
) -> List[Dict[str, Any]]:
    tag_by_id = {int(t['id']): t for t in tags if t.get('id') is not None}
    matched_by_tag: Dict[int, List[tuple[str, float]]] = defaultdict(list)

    for key in untagged_pool.keys():
        best_tag_id = None
        best_score = 0.0

        for tag_id, assoc_keys in tag_assoc_keys.items():
            if not assoc_keys:
                continue
            score = max(_similarity_score(key, candidate) for candidate in assoc_keys)
            if score > best_score:
                best_score = score
                best_tag_id = tag_id

        if best_tag_id is not None and best_score >= float(min_score):
            matched_by_tag[int(best_tag_id)].append((key, best_score))

    suggestions: List[Dict[str, Any]] = []
    for tag_id, rows in matched_by_tag.items():
        uniq_keys = sorted({k for k, _ in rows})
        if len(uniq_keys) < min_products:
            continue

        items = []
        matched_rows = 0
        avg_score = 0.0
        for key, score in rows:
            p = untagged_pool[key]
            matched_rows += int(p['occorrenze'])
            avg_score += score
            items.append(
                {
                    'descrizione': p['descrizione'],
                    'descrizione_key': p['descrizione_key'],
                    'occorrenze': int(p['occorrenze']),
                    'fornitori_count': int(p['fornitori_count']),
                    'last_seen_date': p['ultima_data'],
                    'selected_by_default': True,
                }
            )

        if not items:
            continue

        avg_score = avg_score / len(rows)
        tag_name = str((tag_by_id.get(tag_id) or {}).get('nome') or f'Tag {tag_id}')

        suggestions.append(
            {
                'suggestion_type': 'extend_tag',
                'status': 'pending',
                'suggested_tag_name': None,
                'target_tag_id': int(tag_id),
                'cluster_key': f'extend_tag::{tag_id}',
                'confidence_score': round(min(100.0, avg_score * 100.0), 2),
                'detection_window_days': int(window_days),
                'matched_products_count': len(sorted({i['descrizione_key'] for i in items})),
                'matched_rows_count': matched_rows,
                'tag_name': tag_name,
                'items': items,
            }
        )

    suggestions.sort(key=lambda x: (-x['matched_products_count'], -x['matched_rows_count']))
    return suggestions[:MAX_SUGGESTIONS_PER_TYPE]


def build_recent_product_pool(
    user_id: str,
    ristorante_id: str,
    window_days: int = WINDOW_DAYS_DEFAULT,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    rows = _fetch_recent_rows(user_id, ristorante_id, window_days=window_days, supabase_client=supabase_client)
    pool = _aggregate_pool(rows)
    return list(pool.values())


def suggest_new_tags(
    user_id: str,
    ristorante_id: str,
    min_products: int,
    min_rows: int,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    rows = _fetch_recent_rows(user_id, ristorante_id, window_days=WINDOW_DAYS_DEFAULT, supabase_client=supabase_client)
    pool = _aggregate_pool(rows)
    _, _, all_tag_keys = _fetch_tags_and_assoc(user_id, ristorante_id, supabase_client=supabase_client)
    untagged = {k: v for k, v in pool.items() if k not in all_tag_keys}
    return _build_new_tag_suggestions(untagged, min_products=min_products, min_rows=min_rows, window_days=WINDOW_DAYS_DEFAULT)


def suggest_extend_existing_tags(
    user_id: str,
    ristorante_id: str,
    min_products: int,
    min_score: float,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    rows = _fetch_recent_rows(user_id, ristorante_id, window_days=WINDOW_DAYS_DEFAULT, supabase_client=supabase_client)
    pool = _aggregate_pool(rows)
    tags, tag_assoc, all_tag_keys = _fetch_tags_and_assoc(user_id, ristorante_id, supabase_client=supabase_client)
    untagged = {k: v for k, v in pool.items() if k not in all_tag_keys}
    return _build_extend_tag_suggestions(
        tags,
        tag_assoc,
        untagged,
        min_products=min_products,
        min_score=min_score,
        window_days=WINDOW_DAYS_DEFAULT,
    )


def upsert_tag_suggestions(
    user_id: str,
    ristorante_id: str,
    suggestions: List[Dict[str, Any]],
    supabase_client=None,
) -> int:
    if not user_id or not ristorante_id or not suggestions:
        return 0

    sb = supabase_client or get_supabase_client()
    now_iso = _utcnow().isoformat()
    inserted = 0

    for suggestion in suggestions:
        s_type = str(suggestion.get('suggestion_type') or '').strip()
        cluster_key = str(suggestion.get('cluster_key') or '').strip()
        if not s_type or not cluster_key:
            continue

        existing = (
            sb.table('custom_tag_suggestions')
            .select('id,status')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .eq('suggestion_type', s_type)
            .eq('cluster_key', cluster_key)
            .eq('status', 'pending')
            .limit(1)
            .execute().data or []
        )

        payload = {
            'user_id': user_id,
            'ristorante_id': ristorante_id,
            'suggestion_type': s_type,
            'status': 'pending',
            'suggested_tag_name': suggestion.get('suggested_tag_name'),
            'target_tag_id': suggestion.get('target_tag_id'),
            'cluster_key': cluster_key,
            'confidence_score': suggestion.get('confidence_score'),
            'detection_window_days': int(suggestion.get('detection_window_days') or WINDOW_DAYS_DEFAULT),
            'matched_products_count': int(suggestion.get('matched_products_count') or 0),
            'matched_rows_count': int(suggestion.get('matched_rows_count') or 0),
            'last_seen_at': now_iso,
        }

        if existing:
            suggestion_id = int(existing[0]['id'])
            (
                sb.table('custom_tag_suggestions')
                .update(payload)
                .eq('id', suggestion_id)
                .execute()
            )
        else:
            payload['first_seen_at'] = now_iso
            resp = sb.table('custom_tag_suggestions').insert(payload).execute().data or []
            if not resp:
                continue
            suggestion_id = int(resp[0]['id'])
            inserted += 1

        items = suggestion.get('items') or []
        (
            sb.table('custom_tag_suggestion_items')
            .delete()
            .eq('suggestion_id', suggestion_id)
            .execute()
        )

        if items:
            item_payload = []
            for item in items:
                item_payload.append(
                    {
                        'suggestion_id': suggestion_id,
                        'descrizione': str(item.get('descrizione') or '').strip(),
                        'descrizione_key': str(item.get('descrizione_key') or '').strip(),
                        'occorrenze': int(item.get('occorrenze') or 1),
                        'fornitori_count': int(item.get('fornitori_count') or 0),
                        'last_seen_date': item.get('last_seen_date'),
                        'selected_by_default': bool(item.get('selected_by_default', True)),
                    }
                )
            if item_payload:
                sb.table('custom_tag_suggestion_items').insert(item_payload).execute()

    return inserted


def list_pending_tag_suggestions(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    if not user_id or not ristorante_id:
        return []

    sb = supabase_client or get_supabase_client()
    now_iso = _utcnow().isoformat()

    suggestions = (
        sb.table('custom_tag_suggestions')
        .select(
            'id,suggestion_type,status,suggested_tag_name,target_tag_id,cluster_key,confidence_score,'
            'detection_window_days,matched_products_count,matched_rows_count,first_seen_at,last_seen_at,snooze_until'
        )
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .eq('status', 'pending')
        .order('last_seen_at', desc=True)
        .limit(50)
        .execute().data or []
    )

    suggestion_ids = [int(s['id']) for s in suggestions if s.get('id') is not None]
    if not suggestion_ids:
        return []

    items = (
        sb.table('custom_tag_suggestion_items')
        .select('id,suggestion_id,descrizione,descrizione_key,occorrenze,fornitori_count,last_seen_date,selected_by_default')
        .in_('suggestion_id', suggestion_ids)
        .order('occorrenze', desc=True)
        .execute().data or []
    )

    by_suggestion: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        sid = item.get('suggestion_id')
        if sid is None:
            continue
        by_suggestion[int(sid)].append(item)

    result = []
    for s in suggestions:
        snooze_until = s.get('snooze_until')
        if snooze_until and str(snooze_until) > now_iso:
            continue
        sid = int(s['id'])
        s['items'] = by_suggestion.get(sid, [])
        result.append(s)
    return result


def _get_suggestion_with_items(
    suggestion_id: int,
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Optional[Dict[str, Any]]:
    sb = supabase_client or get_supabase_client()
    rows = (
        sb.table('custom_tag_suggestions')
        .select('id,suggestion_type,status,suggested_tag_name,target_tag_id')
        .eq('id', int(suggestion_id))
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .limit(1)
        .execute().data or []
    )
    if not rows:
        return None

    suggestion = rows[0]
    items = (
        sb.table('custom_tag_suggestion_items')
        .select('descrizione,descrizione_key,selected_by_default')
        .eq('suggestion_id', int(suggestion_id))
        .execute().data or []
    )
    suggestion['items'] = items
    return suggestion


def accept_suggestion_create_tag(
    suggestion_id: int,
    tag_name: str | None,
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Dict[str, Any]:
    sb = supabase_client or get_supabase_client()
    suggestion = _get_suggestion_with_items(suggestion_id, user_id, ristorante_id, supabase_client=sb)
    if not suggestion:
        return {'success': False, 'error': 'suggestion_not_found'}

    if suggestion.get('suggestion_type') != 'new_tag':
        return {'success': False, 'error': 'invalid_suggestion_type'}

    items = [i for i in (suggestion.get('items') or []) if i.get('selected_by_default', True)]
    if not items:
        return {'success': False, 'error': 'no_items_selected'}

    new_tag_name = (tag_name or suggestion.get('suggested_tag_name') or '').strip()
    if not new_tag_name:
        return {'success': False, 'error': 'empty_tag_name'}

    try:
        tag = crea_tag(user_id=user_id, ristorante_id=ristorante_id, nome=new_tag_name, emoji=None, colore=None)
        tag_id = int(tag['id'])
    except Exception:
        existing = (
            sb.table('custom_tags')
            .select('id')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .ilike('nome', new_tag_name)
            .limit(1)
            .execute().data or []
        )
        if not existing:
            return {'success': False, 'error': 'create_tag_failed'}
        tag_id = int(existing[0]['id'])

    assoc_payload = [
        {
            'descrizione': str(i.get('descrizione') or '').strip(),
            'descrizione_key': str(i.get('descrizione_key') or '').strip(),
            'fattore_kg': None,
        }
        for i in items
        if str(i.get('descrizione_key') or '').strip()
    ]
    if assoc_payload:
        aggiungi_associazioni(tag_id, assoc_payload, user_id=user_id)

    (
        sb.table('custom_tag_suggestions')
        .update({'status': 'accepted', 'target_tag_id': tag_id})
        .eq('id', int(suggestion_id))
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .execute()
    )
    clear_tags_cache()
    return {'success': True, 'tag_id': tag_id, 'associazioni_aggiunte': len(assoc_payload)}


def accept_suggestion_extend_tag(
    suggestion_id: int,
    tag_id: int | None,
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Dict[str, Any]:
    sb = supabase_client or get_supabase_client()
    suggestion = _get_suggestion_with_items(suggestion_id, user_id, ristorante_id, supabase_client=sb)
    if not suggestion:
        return {'success': False, 'error': 'suggestion_not_found'}

    if suggestion.get('suggestion_type') != 'extend_tag':
        return {'success': False, 'error': 'invalid_suggestion_type'}

    target_tag_id = int(tag_id or suggestion.get('target_tag_id') or 0)
    if target_tag_id <= 0:
        return {'success': False, 'error': 'missing_target_tag_id'}

    items = [i for i in (suggestion.get('items') or []) if i.get('selected_by_default', True)]
    assoc_payload = [
        {
            'descrizione': str(i.get('descrizione') or '').strip(),
            'descrizione_key': str(i.get('descrizione_key') or '').strip(),
            'fattore_kg': None,
        }
        for i in items
        if str(i.get('descrizione_key') or '').strip()
    ]
    if assoc_payload:
        aggiungi_associazioni(target_tag_id, assoc_payload, user_id=user_id)

    (
        sb.table('custom_tag_suggestions')
        .update({'status': 'accepted', 'target_tag_id': target_tag_id})
        .eq('id', int(suggestion_id))
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .execute()
    )
    clear_tags_cache()
    return {'success': True, 'tag_id': target_tag_id, 'associazioni_aggiunte': len(assoc_payload)}


def dismiss_tag_suggestion(
    suggestion_id: int,
    user_id: str,
    ristorante_id: str,
    reason: str | None = None,
    supabase_client=None,
) -> bool:
    sb = supabase_client or get_supabase_client()
    payload: Dict[str, Any] = {'status': 'dismissed'}
    if reason:
        payload['feedback_note'] = str(reason).strip()[:1000]
    (
        sb.table('custom_tag_suggestions')
        .update(payload)
        .eq('id', int(suggestion_id))
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .execute()
    )
    return True


def snooze_tag_suggestion(
    suggestion_id: int,
    user_id: str,
    ristorante_id: str,
    days: int = 30,
    supabase_client=None,
) -> bool:
    sb = supabase_client or get_supabase_client()
    snooze_until = (_utcnow() + timedelta(days=max(1, int(days)))).isoformat()
    (
        sb.table('custom_tag_suggestions')
        .update({'status': 'snoozed', 'snooze_until': snooze_until})
        .eq('id', int(suggestion_id))
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .execute()
    )
    return True


def generate_tag_suggestion_notifications(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    pending = list_pending_tag_suggestions(user_id, ristorante_id, supabase_client=supabase_client)
    if not pending:
        return []

    new_tag_suggestions = [s for s in pending if s.get('suggestion_type') == 'new_tag']
    extend_suggestions = [s for s in pending if s.get('suggestion_type') == 'extend_tag']
    records: List[Dict[str, Any]] = []

    if new_tag_suggestions:
        prodotti = sum(int(s.get('matched_products_count') or 0) for s in new_tag_suggestions)
        records.append(
            build_notification_record(
                user_id=user_id,
                ristorante_id=ristorante_id,
                topic_key='tag_suggestion_new_tag',
                source_type='operativa',
                severity='info',
                title=f'Suggeriti {len(new_tag_suggestions)} nuovi tag',
                body=(
                    f'Rilevati {prodotti} prodotti coerenti negli ultimi 30 giorni. '
                    'Apri Analisi e Tag per confermare la creazione.'
                ),
                payload={'suggestions': len(new_tag_suggestions), 'products': prodotti},
                action_page='pages/4_analisi_personalizzata.py',
            )
        )

    if extend_suggestions:
        prodotti = sum(int(s.get('matched_products_count') or 0) for s in extend_suggestions)
        records.append(
            build_notification_record(
                user_id=user_id,
                ristorante_id=ristorante_id,
                topic_key='tag_suggestion_extend_tag',
                source_type='operativa',
                severity='info',
                title=f'{len(extend_suggestions)} suggerimenti per tag esistenti',
                body=(
                    f'Trovati {prodotti} nuovi prodotti reclutabili su tag esistenti negli ultimi 30 giorni. '
                    'Apri Analisi e Tag per confermare le aggiunte.'
                ),
                payload={'suggestions': len(extend_suggestions), 'products': prodotti},
                action_page='pages/4_analisi_personalizzata.py',
            )
        )

    return records


def run_tag_suggestion_pipeline(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
    min_products: int = MIN_PRODUCTS_DEFAULT,
    min_rows: int = MIN_ROWS_DEFAULT,
    min_score_extend: float = MIN_SCORE_EXTEND_DEFAULT,
) -> Dict[str, Any]:
    """Esegue detection + upsert suggerimenti + upsert notifiche (best effort)."""
    if not user_id or not ristorante_id:
        return {'success': False, 'error': 'missing_scope'}

    sb = supabase_client or get_supabase_client()
    try:
        rows = _fetch_recent_rows(user_id, ristorante_id, window_days=WINDOW_DAYS_DEFAULT, supabase_client=sb)
        pool = _aggregate_pool(rows)
        tags, tag_assoc_keys, all_tag_keys = _fetch_tags_and_assoc(user_id, ristorante_id, supabase_client=sb)
        untagged = {k: v for k, v in pool.items() if k not in all_tag_keys}

        new_tag = _build_new_tag_suggestions(
            untagged,
            min_products=int(min_products),
            min_rows=int(min_rows),
            window_days=WINDOW_DAYS_DEFAULT,
        )
        extend_tag = _build_extend_tag_suggestions(
            tags,
            tag_assoc_keys,
            untagged,
            min_products=int(min_products),
            min_score=float(min_score_extend),
            window_days=WINDOW_DAYS_DEFAULT,
        )

        suggestions = new_tag + extend_tag
        inserted = upsert_tag_suggestions(user_id, ristorante_id, suggestions, supabase_client=sb)

        records = generate_tag_suggestion_notifications(user_id, ristorante_id, supabase_client=sb)
        notif_inserted = upsert_inbox_notifications(records, supabase_client=sb) if records else 0

        return {
            'success': True,
            'total_suggestions': len(suggestions),
            'new_tag_suggestions': len(new_tag),
            'extend_tag_suggestions': len(extend_tag),
            'inserted_suggestions': inserted,
            'notification_records': len(records),
            'notifications_inserted': notif_inserted,
        }
    except Exception as exc:
        logger.warning(f'Tag suggestion pipeline fallita (non critico): {exc}')
        return {'success': False, 'error': str(exc)}
