from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from services.notification_service import (
    build_monthly_data_notifications,
    build_price_alert_notifications,
    build_scoped_notification_id,
    build_upload_outcome_notifications,
    build_upload_quality_notifications,
    dismiss_notification_ids,
    get_dismissed_notification_ids,
    get_previous_month_period,
)


class TestNotificationService:

    def test_build_scoped_notification_id(self):
        scoped_id = build_scoped_notification_id('missing-revenue-2026-03', 'rist-1')
        assert scoped_id == 'rist:rist-1:missing-revenue-2026-03'

    def test_previous_month_wraps_to_previous_year(self):
        year, month = get_previous_month_period(datetime(2026, 1, 8, tzinfo=timezone.utc))
        assert (year, month) == (2025, 12)

    @patch('services.notification_service.carica_margini_anno')
    def test_build_monthly_notifications_when_previous_month_missing(self, mock_carica_margini):
        mock_carica_margini.return_value = {}

        notifications = build_monthly_data_notifications(
            user_id='user-1',
            ristorante_id='rist-1',
            reference_dt=datetime(2026, 4, 8, tzinfo=timezone.utc),
        )

        ids = {item['id'] for item in notifications}
        assert ids == {'missing-revenue-2026-03', 'missing-labor-cost-2026-03'}

    @patch('services.notification_service.carica_margini_anno')
    def test_build_monthly_notifications_empty_when_data_present(self, mock_carica_margini):
        mock_carica_margini.return_value = {
            3: {
                'fatturato_iva10': 1000.0,
                'fatturato_iva22': 500.0,
                'altri_ricavi_noiva': 100.0,
                'costo_dipendenti': 3200.0,
            }
        }

        notifications = build_monthly_data_notifications(
            user_id='user-1',
            ristorante_id='rist-1',
            reference_dt=datetime(2026, 4, 8, tzinfo=timezone.utc),
        )

        assert notifications == []

    def test_get_dismissed_notification_ids_reads_map_keys(self):
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.limit.return_value = query
        query.execute.return_value = MagicMock(data=[{'dismissed_notification_ids': {'rist:1:a': '2026-04-08T10:00:00Z'}}])
        supabase_client = MagicMock()
        supabase_client.table.return_value = query

        dismissed_ids = get_dismissed_notification_ids('user-1', supabase_client=supabase_client)

        assert dismissed_ids == {'rist:1:a'}

    def test_dismiss_notification_ids_updates_user_map(self):
        select_query = MagicMock()
        select_query.select.return_value = select_query
        select_query.eq.return_value = select_query
        select_query.limit.return_value = select_query
        select_query.execute.return_value = MagicMock(data=[{'dismissed_notification_ids': {'old-id': '2026-04-08T09:00:00Z'}}])

        update_query = MagicMock()
        update_query.update.return_value = update_query
        update_query.eq.return_value = update_query
        update_query.execute.return_value = MagicMock(data=[])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [select_query, update_query]

        result = dismiss_notification_ids('user-1', ['new-id'], supabase_client=supabase_client)

        assert result is True
        update_query.update.assert_called_once()
        payload = update_query.update.call_args.args[0]
        assert 'old-id' in payload['dismissed_notification_ids']
        assert 'new-id' in payload['dismissed_notification_ids']

    def test_build_upload_outcome_notifications_from_context(self):
        notifications = build_upload_outcome_notifications({
            'upload_id': 'upload-1',
            'problematic_files': [
                {'file_name': 'a.xml', 'reason': 'Già presente nel database', 'category': 'duplicate'},
                {'file_name': 'b.xml', 'reason': 'Errore parsing', 'category': 'failed'},
            ],
        })

        assert len(notifications) == 1
        assert notifications[0]['id'] == 'upload-outcome-upload-1'
        assert 'gia presenti' not in notifications[0]['body']
        assert 'con errore di elaborazione' in notifications[0]['body']

    def test_build_upload_outcome_notifications_ignores_only_duplicates(self):
        notifications = build_upload_outcome_notifications({
            'upload_id': 'upload-dup-only',
            'problematic_files': [
                {'file_name': 'a.xml', 'reason': 'Già presente nel database', 'category': 'duplicate'},
            ],
        })

        assert notifications == []

    def test_build_upload_outcome_notifications_ignores_only_blocked_files(self):
        notifications = build_upload_outcome_notifications({
            'upload_id': 'upload-blocked-only',
            'problematic_files': [
                {'file_name': 'a.xml', 'reason': 'Bloccata dalle regole della prova gratuita', 'category': 'blocked'},
                {'file_name': 'b.xml', 'reason': 'Formato non consentito durante la prova gratuita', 'category': 'blocked'},
            ],
        })

        assert notifications == []

    def test_build_price_alert_notifications_from_context(self):
        notifications = build_price_alert_notifications({
            'upload_id': 'upload-2',
            'price_alerts': [
                {'product': 'Mozzarella', 'increase_pct': 12.4, 'file_name': 'fattura.xml'},
                {'product': 'Olio', 'increase_pct': 8.1, 'file_name': 'fattura2.xml'},
            ],
        })

        assert len(notifications) == 1
        assert notifications[0]['id'] == 'price-alerts-upload-2'
        assert 'Mozzarella (+12.4%)' in notifications[0]['body']
        assert notifications[0]['action_page'] == 'pages/3_controllo_prezzi.py'

    def test_build_upload_quality_notifications_shows_only_real_unresolved_cases(self):
        notifications = build_upload_quality_notifications({
            'upload_id': 'upload-quality-1',
            'quality_checks': {
                'checked_files': 2,
                'rows_saved': 18,
                'zero_price_rows': 3,
                'needs_review_rows': 5,
                'uncategorized_rows': 2,
                'uncategorized_unique_products': 2,
                'uncategorized_examples': [
                    'VARIE',
                    'RIFERIMENTO DDT NR. 123',
                ],
                'note_rows': 1,
                'verification_ok': True,
            },
        })

        assert len(notifications) == 1
        assert notifications[0]['id'] == 'upload-quality-upload-quality-1'
        assert 'righe da rivedere' not in notifications[0]['body']
        assert 'righe a €0' not in notifications[0]['body']
        assert 'VARIE' in notifications[0]['body']
        assert 'RIFERIMENTO DDT NR. 123' in notifications[0]['body']

    def test_build_upload_quality_notifications_empty_when_clean(self):
        assert build_upload_quality_notifications({
            'upload_id': 'upload-clean',
            'quality_checks': {
                'checked_files': 1,
                'rows_saved': 12,
                'zero_price_rows': 0,
                'needs_review_rows': 0,
                'uncategorized_rows': 0,
                'note_rows': 0,
                'verification_ok': True,
            },
        }) == []

    # --- Edge cases ---

    def test_build_upload_outcome_notifications_returns_empty_for_none(self):
        assert build_upload_outcome_notifications(None) == []

    def test_build_upload_outcome_notifications_returns_empty_when_no_problematic(self):
        assert build_upload_outcome_notifications({
            'upload_id': 'x',
            'problematic_files': [],
        }) == []

    def test_build_upload_outcome_notifications_returns_empty_when_no_upload_id(self):
        assert build_upload_outcome_notifications({
            'upload_id': '',
            'problematic_files': [{'file_name': 'a.xml', 'category': 'failed'}],
        }) == []

    def test_build_price_alert_notifications_returns_empty_for_none(self):
        assert build_price_alert_notifications(None) == []

    def test_build_price_alert_notifications_returns_empty_when_no_alerts(self):
        assert build_price_alert_notifications({
            'upload_id': 'x',
            'price_alerts': [],
        }) == []

    def test_build_monthly_notifications_returns_empty_for_empty_user(self):
        assert build_monthly_data_notifications(
            user_id='',
            ristorante_id='rist-1',
        ) == []

    def test_build_monthly_notifications_returns_empty_for_empty_ristorante(self):
        assert build_monthly_data_notifications(
            user_id='user-1',
            ristorante_id='',
        ) == []

    def test_get_dismissed_returns_empty_for_empty_user(self):
        assert get_dismissed_notification_ids('') == set()

    def test_dismiss_returns_false_for_empty_ids(self):
        assert dismiss_notification_ids('user-1', []) is False

    def test_price_alert_escapes_html_in_product_name(self):
        notifications = build_price_alert_notifications({
            'upload_id': 'xss-test',
            'price_alerts': [
                {'product': '<img src=x onerror=alert(1)>', 'increase_pct': 10.0},
            ],
        })
        assert '<img' not in notifications[0]['body']
        assert '&lt;img' in notifications[0]['body']