"""Radar Anomalie - rilevamento deterministico.

Base dati: fatture_documenti (1 riga = 1 documento).
Chiamato da upload_handler.py (check_on_upload) e da app.py (check_weekly).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import html

from config.logger_setup import get_logger
from services import get_supabase_client
from services.notification_inbox_service import (
    build_notification_record,
    upsert_inbox_notifications,
)

logger = get_logger('anomaly_radar')

CATEGORIE_CRITICHE = ['CARNE', 'PESCE', 'LATTICINI', 'SALUMI', 'PRODOTTI DA FORNO']


def check_on_upload(
    user_id: str,
    ristorante_id: str,
    upload_id: str,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Controlla anomalie post-upload su fatture_documenti."""
    if not user_id or not ristorante_id or not upload_id:
        return []

    records: List[Dict[str, Any]] = []
    sb = supabase_client or get_supabase_client()

    nuovi_docs = (
        sb.table('fatture_documenti')
        .select('id,piva_fornitore,fornitore,totale_documento,data_documento,file_origine')
        .eq('user_id', user_id)
        .eq('ristorante_id', ristorante_id)
        .eq('upload_id', upload_id)
        .is_('deleted_at', 'null')
        .execute().data or []
    )

    if not nuovi_docs:
        return []

    # --- PREFETCH bulk: una sola query per tutte le P.IVA dell'upload (elimina N+1) ---
    piva_set = {str(d.get('piva_fornitore') or '').strip() for d in nuovi_docs}
    piva_set.discard('')
    file_origini_upload = {str(d.get('file_origine') or '').strip() for d in nuovi_docs}

    storico_bulk: List[Dict[str, Any]] = []
    if piva_set:
        storico_bulk = (
            sb.table('fatture_documenti')
            .select('id,piva_fornitore,totale_documento,file_origine,data_documento')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .in_('piva_fornitore', list(piva_set))
            .is_('deleted_at', 'null')
            .order('data_documento', desc=True)
            .limit(10000)
            .execute().data or []
        )
    # Esclude i file dell'upload corrente per non confrontare ogni doc con se stesso
    storico_bulk = [r for r in storico_bulk if r.get('file_origine') not in file_origini_upload]

    by_piva: Dict[str, List] = defaultdict(list)
    for r in storico_bulk:
        by_piva[str(r.get('piva_fornitore') or '').strip()].append(r)
    # --- fine PREFETCH ---

    # Step 2: fattura_duplicata (zero query aggiuntive, usa by_piva locale)
    for doc in nuovi_docs:
        piva = str(doc.get('piva_fornitore') or '').strip()
        importo = float(doc.get('totale_documento') or 0)
        data_str = str(doc.get('data_documento') or '').strip()
        file_orig = str(doc.get('file_origine') or '').strip()
        fornitore = str(doc.get('fornitore') or '?').strip()

        if not piva or importo <= 0 or not data_str:
            continue

        try:
            data_doc = date.fromisoformat(data_str)
        except ValueError:
            continue

        data_min = data_doc - timedelta(days=30)
        data_max = data_doc + timedelta(days=30)

        for cand in by_piva.get(piva, []):
            try:
                cand_data = date.fromisoformat(str(cand.get('data_documento') or ''))
            except ValueError:
                continue
            if not (data_min <= cand_data <= data_max):
                continue
            importo_cand = float(cand.get('totale_documento') or 0)
            if importo_cand <= 0:
                continue
            diff_pct = abs(importo - importo_cand) / importo * 100
            if diff_pct <= 2.0:
                records.append(build_notification_record(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    topic_key='fattura_duplicata',
                    source_type='radar',
                    severity='error',
                    title=f'Possibile duplicato: {html.escape(fornitore)} - €{importo:.2f}',
                    body=(
                        f"Trovata un'altra fattura da {html.escape(fornitore)} (P.IVA {piva}) "
                        f"per €{importo:.2f} entro 30 giorni. Verifica prima di procedere al pagamento."
                    ),
                    payload={'piva': piva, 'importo': importo, 'file_origine': file_orig},
                    action_page='/analisi-e-tag',
                    file_ids=[upload_id],
                ))
                break

    # Step 3: piva_duplicata_fornitore
    try:
        tutti = (
            sb.table('fatture_documenti')
            .select('piva_fornitore,fornitore')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .is_('deleted_at', 'null')
            .limit(10000)
            .execute().data or []
        )

        piva_map: Dict[str, set] = defaultdict(set)
        for row in tutti:
            piva = str(row.get('piva_fornitore') or '').strip()
            fornitore = str(row.get('fornitore') or '').strip()
            if piva and fornitore:
                piva_map[piva].add(fornitore)

        for piva, nomi in piva_map.items():
            if len(nomi) > 1:
                nomi_sorted = sorted(nomi)
                nomi_str = ', '.join(nomi_sorted[:3])
                records.append(build_notification_record(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    topic_key='piva_duplicata_fornitore',
                    source_type='radar',
                    severity='warning',
                    title=f'P.IVA {piva} associata a nomi diversi',
                    body=(
                        f'La P.IVA {piva} risulta collegata a {len(nomi)} nomi diversi: {nomi_str}. '
                        'Possibile duplicato o cambio ragione sociale.'
                    ),
                    payload={'piva': piva, 'nomi': nomi_sorted},
                    action_page='/prezzi',
                ))
    except Exception as exc:
        logger.warning(f'Radar piva_dup fallito: {exc}')

    # Step 4: fattura_anomala_importo
    for doc in nuovi_docs:
        piva = str(doc.get('piva_fornitore') or '').strip()
        importo = float(doc.get('totale_documento') or 0)
        fornitore = str(doc.get('fornitore') or '?').strip()
        file_orig = str(doc.get('file_origine') or '').strip()

        if not piva or importo <= 0:
            continue

        try:
            storici = by_piva.get(piva, [])[:10]  # già ordinati per data_documento desc (prefetch)
            if len(storici) < 3:
                continue

            importi_storici = [
                float(row.get('totale_documento') or 0)
                for row in storici
                if float(row.get('totale_documento') or 0) > 0
            ]
            if not importi_storici:
                continue

            media = sum(importi_storici) / len(importi_storici)
            if media <= 0:
                continue

            if importo > media * 5:
                moltiplicatore = importo / media
                records.append(build_notification_record(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    topic_key='fattura_anomala_importo',
                    source_type='radar',
                    severity='warning',
                    title=f'Importo anomalo: {html.escape(fornitore)} - €{importo:.2f}',
                    body=(
                        f'Questo importo è {moltiplicatore:.1f}x superiore alla media storica di '
                        f'€{media:.2f} per {html.escape(fornitore)}.'
                    ),
                    payload={
                        'piva': piva,
                        'importo': importo,
                        'media': media,
                        'upload_id': upload_id,
                    },
                    action_page='/prezzi',
                    file_ids=[upload_id],
                ))
        except Exception as exc:
            logger.warning(f'Radar anomalia_importo fallito {piva}: {exc}')

    return records


def check_weekly(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """Controllo settimanale: fornitore_critico_consecutivo."""
    if not user_id or not ristorante_id:
        return []

    records: List[Dict[str, Any]] = []
    sb = supabase_client or get_supabase_client()

    try:
        three_months_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

        alerts = (
            sb.table('notification_inbox')
            .select('payload,created_at')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .eq('topic_key', 'price_alert')
            .gte('created_at', three_months_ago)
            .execute().data or []
        )

        piva_mesi: Dict[str, set] = defaultdict(set)
        piva_info: Dict[str, str] = {}

        for alert in alerts:
            payload = alert.get('payload') or {}
            created = str(alert.get('created_at') or '')
            try:
                dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                mese_key = f'{dt.year}-{dt.month:02d}'
            except Exception:
                continue

            prodotti = payload.get('price_alerts') or []
            if isinstance(prodotti, list):
                for prod in prodotti:
                    piva = str(prod.get('piva_fornitore') or '').strip()
                    fornitore = str(prod.get('fornitore') or prod.get('supplier') or '').strip()
                    if piva:
                        piva_mesi[piva].add(mese_key)
                        if fornitore:
                            piva_info[piva] = fornitore

        for piva, mesi in piva_mesi.items():
            mesi_sorted = sorted(mesi)
            if len(mesi_sorted) >= 3:
                consecutivi = _check_consecutive_months(mesi_sorted)
                if consecutivi >= 3:
                    fornitore = piva_info.get(piva, piva)
                    records.append(build_notification_record(
                        user_id=user_id,
                        ristorante_id=ristorante_id,
                        topic_key='fornitore_critico_consecutivo',
                        source_type='radar',
                        severity='warning',
                        title=f'{html.escape(fornitore)} - {consecutivi}o mese con aumenti prezzi',
                        body=(
                            f'{html.escape(fornitore)} ha superato la soglia prezzi per '
                            f'{consecutivi} mesi consecutivi. Valuta la rinegoziazione del contratto '
                            'o un fornitore alternativo.'
                        ),
                        payload={'piva': piva, 'mesi': mesi_sorted, 'consecutivi': consecutivi},
                        action_page='/prezzi',
                    ))
    except Exception as exc:
        logger.warning(f'Radar fornitore_critico fallito: {exc}')

    return records


def _check_consecutive_months(mesi_sorted: List[str]) -> int:
    """Ritorna il massimo numero di mesi consecutivi trovati in una lista YYYY-MM ordinata."""
    if not mesi_sorted:
        return 0

    parsed: List[tuple] = []
    for item in mesi_sorted:
        try:
            y_str, m_str = item.split('-', 1)
            parsed.append((int(y_str), int(m_str)))
        except Exception:
            continue

    if not parsed:
        return 0

    best = 1
    current = 1

    for idx in range(1, len(parsed)):
        prev_y, prev_m = parsed[idx - 1]
        cur_y, cur_m = parsed[idx]

        expected_y, expected_m = prev_y, prev_m + 1
        if expected_m == 13:
            expected_y, expected_m = prev_y + 1, 1

        if (cur_y, cur_m) == (expected_y, expected_m):
            current += 1
            best = max(best, current)
        else:
            current = 1

    return best
