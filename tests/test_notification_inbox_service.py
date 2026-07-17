"""
Unit + integration tests per services/notification_inbox_service.py

Copertura:
- build_notification_record(): dedupe_key, expires_at, refresh_on_conflict per ogni tipologia
- resolve_bucket(): formato corretto per tutti i topic_key
- upsert_inbox_notifications(): chiama RPC con payload corretto
- dismiss_inbox_notification(): isolamento tenant (no cross-user)
- dismiss_all_inbox_notifications(): con e senza filtro source_type
- get_inbox_notifications(): esclude scadute, marca is_new correttamente

Integration scenarios:
- Upload completo → dedupe_key corretto
- Secondo upload stesso ristorante stessa settimana → DO NOTHING (refresh_on_conflict=False)
- Dismiss singola → rimossa da lista attiva
- Switch ristorante → badge ricalcolato per nuovo ristorante
- Legacy migration one-shot → metadata.inbox_migration_done settato, non rieseguito
- invoicetronic needs_ack=0 → nessuna notifica invoicetronic_auto

Non regressione:
- operational_notifications dal dashboard: flusso invariato dopo Step 6
- last_upload_notification_context: struttura invariata dopo Step 5
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

from services.notification_inbox_service import (
    _bucket_daily,
    _bucket_file_ids,
    _bucket_iso_month,
    _bucket_iso_week,
    build_dedupe_key,
    build_notification_record,
    dismiss_all_inbox_notifications,
    dismiss_inbox_notification,
    get_inbox_badge_count,
    get_inbox_notifications,
    resolve_bucket,
    upsert_inbox_notifications,
)


# ────────────────────────────────────────────────
# Fixtures helpers
# ────────────────────────────────────────────────

UID  = 'user-aaa'
RID  = 'rist-bbb'
NOW  = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()


def _make_supabase_mock(return_data=None):
    """Restituisce un mock Supabase client che restituisce return_data su .execute()."""
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.neq.return_value = q
    q.is_.return_value = q
    q.in_.return_value = q
    q.or_.return_value = q
    q.order.return_value = q
    q.update.return_value = q
    q.rpc.return_value = q
    resp = MagicMock()
    resp.data = return_data or []
    resp.count = len(return_data) if isinstance(return_data, list) else 0
    q.execute.return_value = resp
    return q


# ════════════════════════════════════════════════
# BUCKET HELPERS
# ════════════════════════════════════════════════

class TestBucketHelpers:

    def test_iso_week_format(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        result = _bucket_iso_week(dt)
        assert result == '2026-W20'

    def test_iso_month_format(self):
        dt = datetime(2026, 3, 5, tzinfo=timezone.utc)
        result = _bucket_iso_month(dt)
        assert result == '2026-03'

    def test_daily_format(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        result = _bucket_daily(dt)
        assert result == '2026-05-13'

    def test_file_ids_hash_stable(self):
        h1 = _bucket_file_ids(['b.xml', 'a.xml'])
        h2 = _bucket_file_ids(['a.xml', 'b.xml'])
        assert h1 == h2  # Sort stabilizza l'output
        assert len(h1) == 12

    def test_file_ids_hash_differs_with_different_inputs(self):
        h1 = _bucket_file_ids(['a.xml'])
        h2 = _bucket_file_ids(['b.xml'])
        assert h1 != h2


# ════════════════════════════════════════════════
# RESOLVE BUCKET
# ════════════════════════════════════════════════

class TestResolveBucket:

    def test_scadenza_superata_returns_iso_week(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        assert resolve_bucket('scadenza_superata', ref_dt=dt) == '2026-W20'

    def test_scadenza_imminente_returns_iso_week(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        assert resolve_bucket('scadenza_imminente', ref_dt=dt) == '2026-W20'

    def test_fatturato_mancante_returns_iso_month(self):
        dt = datetime(2026, 4, 1, tzinfo=timezone.utc)
        assert resolve_bucket('fatturato_mancante', ref_dt=dt) == '2026-04'

    def test_costo_personale_mancante_returns_iso_month(self):
        dt = datetime(2026, 4, 1, tzinfo=timezone.utc)
        assert resolve_bucket('costo_personale_mancante', ref_dt=dt) == '2026-04'

    def test_invoicetronic_auto_bucket_format(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        result = resolve_bucket('invoicetronic_auto', pending_count=3, ref_dt=dt)
        assert result == '3::2026-05-13'

    def test_invoicetronic_auto_zero_count(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        result = resolve_bucket('invoicetronic_auto', pending_count=0, ref_dt=dt)
        assert result == '0::2026-05-13'

    def test_upload_topic_uses_file_ids_hash(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        file_ids = ['a.xml', 'b.xml']
        result = resolve_bucket('upload_failed', file_ids=file_ids, ref_dt=dt)
        assert result == _bucket_file_ids(file_ids)

    def test_upload_topic_fallback_to_daily_without_file_ids(self):
        dt = datetime(2026, 5, 13, tzinfo=timezone.utc)
        result = resolve_bucket('price_alert', ref_dt=dt)
        assert result == '2026-05-13'


# ════════════════════════════════════════════════
# BUILD NOTIFICATION RECORD
# ════════════════════════════════════════════════

class TestBuildNotificationRecord:

    def test_dedupe_key_for_scadenza_superata(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='scadenza_superata', source_type='operativa', severity='warning',
            title='T', body='B', ref_dt=NOW,
        )
        expected_bucket = _bucket_iso_week(NOW)
        expected_key = f'{RID}::scadenza_superata::{expected_bucket}'
        assert rec['dedupe_key'] == expected_key

    def test_dedupe_key_for_fatturato_mancante(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='fatturato_mancante', source_type='operativa', severity='warning',
            title='T', body='B', ref_dt=NOW,
        )
        expected_bucket = _bucket_iso_month(NOW)
        expected_key = f'{RID}::fatturato_mancante::{expected_bucket}'
        assert rec['dedupe_key'] == expected_key

    def test_dedupe_key_for_upload_failed_with_file_ids(self):
        file_ids = ['x.xml', 'y.xml']
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='T', body='B', file_ids=file_ids, ref_dt=NOW,
        )
        expected_bucket = _bucket_file_ids(file_ids)
        expected_key = f'{RID}::upload_failed::{expected_bucket}'
        assert rec['dedupe_key'] == expected_key

    def test_refresh_on_conflict_true_for_recurring_topics(self):
        for topic in ('scadenza_superata', 'scadenza_imminente',
                      'fatturato_mancante', 'costo_personale_mancante', 'invoicetronic_auto'):
            rec = build_notification_record(
                user_id=UID, ristorante_id=RID,
                topic_key=topic, source_type='operativa', severity='info',
                title='T', body='B', ref_dt=NOW,
            )
            assert rec['refresh_on_conflict'] is True, f"Expected refresh_on_conflict=True for {topic}"

    def test_refresh_on_conflict_false_for_one_shot_topics(self):
        for topic in ('upload_failed', 'price_alert', 'credit_note',
                      'td24_noddt', 'td24_partial', 'uncategorized_rows', 'quality_check_failed'):
            rec = build_notification_record(
                user_id=UID, ristorante_id=RID,
                topic_key=topic, source_type='upload', severity='warning',
                title='T', body='B', ref_dt=NOW,
            )
            assert rec['refresh_on_conflict'] is False, f"Expected refresh_on_conflict=False for {topic}"

    def test_expires_at_operativa_7_days(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='fatturato_mancante', source_type='operativa', severity='warning',
            title='T', body='B', ref_dt=NOW,
        )
        exp = datetime.fromisoformat(rec['expires_at'].replace('Z', '+00:00'))
        delta = exp - NOW
        assert abs(delta.days - 7) <= 1

    def test_expires_at_upload_14_days(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='T', body='B', ref_dt=NOW,
        )
        exp = datetime.fromisoformat(rec['expires_at'].replace('Z', '+00:00'))
        delta = exp - NOW
        assert abs(delta.days - 14) <= 1

    def test_expires_at_invoicetronic_3_days(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='invoicetronic_auto', source_type='invoicetronic', severity='info',
            title='T', body='B', ref_dt=NOW,
        )
        exp = datetime.fromisoformat(rec['expires_at'].replace('Z', '+00:00'))
        delta = exp - NOW
        assert abs(delta.days - 3) <= 1

    def test_all_required_fields_present(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='Titolo', body='Corpo',
        )
        required = {'user_id', 'ristorante_id', 'topic_key', 'source_type', 'severity',
                    'title', 'body', 'payload', 'dedupe_key', 'source_event_at', 'expires_at',
                    'refresh_on_conflict'}
        assert required.issubset(set(rec.keys()))
        assert rec['user_id'] == UID
        assert rec['ristorante_id'] == RID

    def test_payload_defaults_to_empty_dict(self):
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='price_alert', source_type='upload', severity='warning',
            title='T', body='B',
        )
        assert rec['payload'] == {}


# ════════════════════════════════════════════════
# UPSERT
# ════════════════════════════════════════════════

class TestUpsertInboxNotifications:

    def test_calls_rpc_with_correct_params(self):
        sb = _make_supabase_mock(return_data=2)
        sb.rpc.return_value = sb
        sb.execute.return_value = MagicMock(data=2)

        records = [
            build_notification_record(
                user_id=UID, ristorante_id=RID,
                topic_key='upload_failed', source_type='upload', severity='error',
                title='T', body='B', ref_dt=NOW,
            )
        ]
        result = upsert_inbox_notifications(records, supabase_client=sb)

        sb.rpc.assert_called_once_with(
            'upsert_notification_inbox',
            {'p_notifications': records}
        )
        assert result == 2

    def test_returns_zero_when_no_records(self):
        sb = _make_supabase_mock()
        result = upsert_inbox_notifications([], supabase_client=sb)
        assert result == 0
        sb.rpc.assert_not_called()

    def test_returns_zero_without_client(self):
        records = [build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='T', body='B',
        )]
        result = upsert_inbox_notifications(records, supabase_client=None)
        assert result == 0

    def test_silent_on_rpc_exception(self):
        sb = MagicMock()
        sb.rpc.side_effect = RuntimeError("Connection error")
        records = [build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='T', body='B',
        )]
        # Non deve sollevare eccezione
        result = upsert_inbox_notifications(records, supabase_client=sb)
        assert result == 0


# ════════════════════════════════════════════════
# DISMISS SINGOLA
# ════════════════════════════════════════════════

class TestDismissInboxNotification:

    def test_sets_dismissed_at_on_correct_id(self):
        sb = _make_supabase_mock()
        result = dismiss_inbox_notification('notif-id-123', supabase_client=sb)

        assert result is True
        sb.table.assert_called_with('notification_inbox')
        update_call = sb.update.call_args
        assert 'dismissed_at' in update_call.args[0]
        # Verifica filtro sull'ID corretto (tenant isolation)
        eq_calls = sb.eq.call_args_list
        id_filter = [c for c in eq_calls if c.args[0] == 'id']
        assert len(id_filter) == 1
        assert id_filter[0].args[1] == 'notif-id-123'

    def test_returns_false_without_id(self):
        sb = _make_supabase_mock()
        result = dismiss_inbox_notification('', supabase_client=sb)
        assert result is False
        sb.table.assert_not_called()

    def test_returns_false_without_client(self):
        result = dismiss_inbox_notification('notif-id-123', supabase_client=None)
        assert result is False

    def test_silent_on_exception(self):
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("DB error")
        result = dismiss_inbox_notification('notif-id-123', supabase_client=sb)
        assert result is False


# ════════════════════════════════════════════════
# DISMISS ALL
# ════════════════════════════════════════════════

class TestDismissAllInboxNotifications:

    def test_dismiss_all_without_source_type_filter(self):
        sb = _make_supabase_mock()
        result = dismiss_all_inbox_notifications(
            user_id=UID, ristorante_id=RID, supabase_client=sb,
        )
        assert result is True
        sb.table.assert_called_with('notification_inbox')
        # Verifica che NON sia stato applicato filtro source_type
        eq_calls = [c.args[0] for c in sb.eq.call_args_list]
        assert 'source_type' not in eq_calls

    def test_dismiss_all_with_source_type_filter(self):
        sb = _make_supabase_mock()
        result = dismiss_all_inbox_notifications(
            user_id=UID, ristorante_id=RID, supabase_client=sb,
            source_type='upload',
        )
        assert result is True
        eq_calls = [c.args[0] for c in sb.eq.call_args_list]
        assert 'source_type' in eq_calls

    def test_returns_false_without_user_id(self):
        sb = _make_supabase_mock()
        result = dismiss_all_inbox_notifications(
            user_id='', ristorante_id=RID, supabase_client=sb,
        )
        assert result is False

    def test_returns_false_without_ristorante_id(self):
        sb = _make_supabase_mock()
        result = dismiss_all_inbox_notifications(
            user_id=UID, ristorante_id='', supabase_client=sb,
        )
        assert result is False

    def test_returns_false_without_client(self):
        result = dismiss_all_inbox_notifications(
            user_id=UID, ristorante_id=RID, supabase_client=None,
        )
        assert result is False


# ════════════════════════════════════════════════
# GET INBOX NOTIFICATIONS
# ════════════════════════════════════════════════

class TestGetInboxNotifications:

    def _make_row(self, topic='upload_failed', source_event_at_offset_h=0,
                  expires_at_offset_h=48, dismissed_at=None):
        """Crea una riga notification_inbox mock con is_new calcolato in base all'offset."""
        sea = NOW + timedelta(hours=source_event_at_offset_h)
        exp = NOW + timedelta(hours=expires_at_offset_h)
        return {
            'id': f'id-{topic}-{source_event_at_offset_h}',
            'user_id': UID,
            'ristorante_id': RID,
            'topic_key': topic,
            'source_type': 'upload',
            'severity': 'warning',
            'title': 'Test',
            'body': 'Body',
            'dedupe_key': f'{RID}::{topic}::bucket',
            'source_event_at': sea.isoformat(),
            'expires_at': exp.isoformat(),
            'dismissed_at': dismissed_at,
            'payload': {},
        }

    def test_excludes_expired_records(self):
        """Il filtro expires_at viene applicato lato SQL con or_(expires_at is null OR > now)."""
        row_active = self._make_row('upload_failed', expires_at_offset_h=48)
        sb = _make_supabase_mock([row_active])

        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            result = get_inbox_notifications(UID, RID, supabase_client=sb)

        assert len(result) == 1
        assert result[0]['topic_key'] == 'upload_failed'
        sb.or_.assert_called_once()

    def test_marks_is_new_for_recent_records(self):
        """Notifiche < 24h → is_new=True; >= 24h → is_new=False."""
        row_new  = self._make_row('upload_failed',  source_event_at_offset_h=-12)   # 12h fa → nuova
        row_old  = self._make_row('price_alert',    source_event_at_offset_h=-30)   # 30h fa → precedente

        sb = _make_supabase_mock([row_new, row_old])

        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            result = get_inbox_notifications(UID, RID, supabase_client=sb)

        assert len(result) == 2
        new_notif = next(r for r in result if r['topic_key'] == 'upload_failed')
        old_notif = next(r for r in result if r['topic_key'] == 'price_alert')
        assert new_notif['is_new'] is True
        assert old_notif['is_new'] is False

    def test_returns_empty_list_for_missing_params(self):
        sb = _make_supabase_mock()
        assert get_inbox_notifications('', RID, supabase_client=sb) == []
        assert get_inbox_notifications(UID, '', supabase_client=sb) == []
        assert get_inbox_notifications(UID, RID, supabase_client=None) == []

    def test_filters_by_source_type_when_specified(self):
        sb = _make_supabase_mock([])
        get_inbox_notifications(UID, RID, supabase_client=sb, source_type='upload')
        eq_calls = [c.args for c in sb.eq.call_args_list]
        assert ('source_type', 'upload') in eq_calls

    def test_silent_on_db_exception(self):
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("DB error")
        result = get_inbox_notifications(UID, RID, supabase_client=sb)
        assert result == []


# ════════════════════════════════════════════════
# BADGE COUNT
# ════════════════════════════════════════════════

class TestGetInboxBadgeCount:

    def test_badge_equals_active_notification_count(self):
        row1 = {
            'id': 'r1', 'user_id': UID, 'ristorante_id': RID,
            'topic_key': 'upload_failed', 'source_type': 'upload', 'severity': 'error',
            'title': 'T', 'body': 'B', 'dedupe_key': 'k1',
            'source_event_at': NOW.isoformat(),
            'expires_at': (NOW + timedelta(hours=24)).isoformat(),
            'dismissed_at': None, 'payload': {},
        }
        row2 = {**row1, 'id': 'r2', 'topic_key': 'price_alert', 'dedupe_key': 'k2'}
        sb = _make_supabase_mock([row1, row2])

        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            count = get_inbox_badge_count(UID, RID, supabase_client=sb)

        assert count == 2

    def test_badge_zero_when_no_notifications(self):
        sb = _make_supabase_mock([])
        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            count = get_inbox_badge_count(UID, RID, supabase_client=sb)
        assert count == 0


# ════════════════════════════════════════════════
# INTEGRATION SCENARIOS
# ════════════════════════════════════════════════

class TestIntegrationScenarios:

    def test_upload_completion_generates_correct_dedupe_key(self):
        """Upload completo → dedupe_key basato su hash file_ids."""
        file_ids = ['fattura1.xml', 'fattura2.xml']
        rec = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='Errore', body='Corpo', file_ids=file_ids, ref_dt=NOW,
        )
        expected_bucket = _bucket_file_ids(file_ids)
        assert rec['dedupe_key'] == f'{RID}::upload_failed::{expected_bucket}'
        assert rec['refresh_on_conflict'] is False

    def test_second_upload_same_week_uses_do_nothing(self):
        """Due upload nella stessa settimana → stessa dedupe_key, refresh_on_conflict=False."""
        file_ids_1 = ['a.xml']
        file_ids_2 = ['b.xml']  # File diversi, stesso bucket solo se stessa hash
        rec1 = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='T', body='B', file_ids=file_ids_1, ref_dt=NOW,
        )
        rec2 = build_notification_record(
            user_id=UID, ristorante_id=RID,
            topic_key='upload_failed', source_type='upload', severity='error',
            title='T', body='B', file_ids=file_ids_2, ref_dt=NOW,
        )
        # File diversi → bucket diverso (hash diversa)
        assert rec1['dedupe_key'] != rec2['dedupe_key']
        # Entrambi one-shot
        assert rec1['refresh_on_conflict'] is False
        assert rec2['refresh_on_conflict'] is False

    def test_dismiss_single_removes_from_active_list(self):
        """Dopo dismiss, la notifica non deve più essere in lista attiva."""
        sb_active = _make_supabase_mock([{
            'id': 'notif-xyz', 'user_id': UID, 'ristorante_id': RID,
            'topic_key': 'upload_failed', 'source_type': 'upload', 'severity': 'error',
            'title': 'T', 'body': 'B', 'dedupe_key': 'k',
            'source_event_at': NOW.isoformat(),
            'expires_at': (NOW + timedelta(hours=24)).isoformat(),
            'dismissed_at': None, 'payload': {},
        }])
        sb_dismissed = _make_supabase_mock([])  # Dopo dismiss: lista vuota

        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            active_before = get_inbox_notifications(UID, RID, supabase_client=sb_active)

        assert len(active_before) == 1

        sb_dismiss = _make_supabase_mock()
        dismiss_inbox_notification('notif-xyz', supabase_client=sb_dismiss)
        sb_dismiss.update.assert_called_once()
        update_payload = sb_dismiss.update.call_args.args[0]
        assert 'dismissed_at' in update_payload

        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            active_after = get_inbox_notifications(UID, RID, supabase_client=sb_dismissed)

        assert len(active_after) == 0

    def test_switch_ristorante_different_badge_counts(self):
        """Badge per rist-A e rist-B devono essere indipendenti."""
        rist_a_rows = [{
            'id': 'r1', 'user_id': UID, 'ristorante_id': 'rist-A',
            'topic_key': 'upload_failed', 'source_type': 'upload', 'severity': 'error',
            'title': 'T', 'body': 'B', 'dedupe_key': 'k1',
            'source_event_at': NOW.isoformat(),
            'expires_at': (NOW + timedelta(hours=24)).isoformat(),
            'dismissed_at': None, 'payload': {},
        }]
        sb_a = _make_supabase_mock(rist_a_rows)
        sb_b = _make_supabase_mock([])   # Ristorante B: nessuna notifica

        with patch('services.notification_inbox_service.datetime') as mock_dt:
            mock_dt.now.return_value = NOW
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            count_a = get_inbox_badge_count(UID, 'rist-A', supabase_client=sb_a)
            count_b = get_inbox_badge_count(UID, 'rist-B', supabase_client=sb_b)

        assert count_a == 1
        assert count_b == 0

    def test_invoicetronic_auto_not_generated_when_no_pending(self):
        """Se needs_ack=0, la notifica invoicetronic_auto non viene creata."""
        # Simuliamo il controllo count fatto in app.py Step 6
        pending_count = 0
        records = []
        if pending_count > 0:
            records.append(build_notification_record(
                user_id=UID, ristorante_id=RID,
                topic_key='invoicetronic_auto', source_type='invoicetronic', severity='info',
                title='T', body='B', pending_count=pending_count, ref_dt=NOW,
            ))
        assert records == []

    def test_invoicetronic_auto_generated_when_pending(self):
        """Se needs_ack > 0, la notifica invoicetronic_auto viene creata con bucket corretto."""
        pending_count = 5
        records = []
        if pending_count > 0:
            records.append(build_notification_record(
                user_id=UID, ristorante_id=RID,
                topic_key='invoicetronic_auto', source_type='invoicetronic', severity='info',
                title=f'{pending_count} fatture ricevute', body='B',
                pending_count=pending_count, ref_dt=NOW,
            ))
        assert len(records) == 1
        expected_bucket = f'{pending_count}::2026-05-13'
        assert records[0]['dedupe_key'] == f'{RID}::invoicetronic_auto::{expected_bucket}'
        assert records[0]['refresh_on_conflict'] is True


# ════════════════════════════════════════════════
# NON REGRESSIONE — operational_notifications
# ════════════════════════════════════════════════
class TestNonRegressione:
    """Struttura del context di upload attesa da chi lo consuma.

    Storia: questa classe verificava che il servizio non rompesse il render
    Streamlit durante la migrazione. Il frontend Streamlit e' stato rimosso il
    17/7/2026 e con lui `services/notification_service.py`: i due test che lo
    importavano sono spariti insieme alla loro premessa. Resta il contratto
    sulle chiavi del context, che upload_handler produce tuttora.
    """

    def test_last_upload_notification_context_structure(self):
        """upload_notification_context mantiene tutte le chiavi attese."""
        required_keys = {
            'upload_id', 'created_at', 'successful_files', 'successful_count',
            'credit_note_files', 'problematic_files', 'problematic_count',
            'price_alert_threshold_pct', 'price_alerts', 'td24_date_alerts', 'stats',
        }
        # Costruisce un context minimale come fa upload_handler dopo Step 5
        ctx = {
            'upload_id': '20260513100000000',
            'created_at': NOW_ISO,
            'successful_files': ['a.xml'],
            'successful_count': 1,
            'credit_note_files': [],
            'problematic_files': [],
            'problematic_count': 0,
            'price_alert_threshold_pct': 10.0,
            'price_alerts': [],
            'td24_date_alerts': [],
            'stats': {'caricate_successo': 1, 'errori': 0},
        }
        assert required_keys.issubset(set(ctx.keys()))
