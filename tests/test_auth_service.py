"""Test per services/auth_service.py — Validazione password GDPR."""
import pytest
from unittest.mock import MagicMock

from services.auth_service import valida_password_compliance
from services.auth_service import riepilogo_fatture_auto_da_ultimo_login


class TestValidaPasswordCompliance:
    """Verifica regole GDPR Art.32 + Garante Privacy Italia."""

    def test_password_valida(self):
        errori = valida_password_compliance("Ab1!defghi", "test@email.com")
        assert errori == []

    def test_password_troppo_corta(self):
        errori = valida_password_compliance("Ab1!defg", "test@email.com")
        assert any("10 caratteri" in e for e in errori)

    def test_password_vuota(self):
        errori = valida_password_compliance("", "test@email.com")
        assert any("obbligatoria" in e for e in errori)

    def test_password_comune(self):
        errori = valida_password_compliance("password", "test@email.com")
        assert any("comune" in e.lower() for e in errori)

    def test_password_con_email(self):
        """Email nella password → errore dati personali."""
        errori = valida_password_compliance("testuser1234!", "testuser@email.com")
        assert any("email" in e.lower() for e in errori)

    def test_password_con_nome_ristorante(self):
        errori = valida_password_compliance("ilpizzaiolo12!", "a@b.com", "Il Pizzaiolo")
        assert any("ristorante" in e.lower() for e in errori)

    def test_no_complessita(self):
        """Solo minuscole → manca complessità 3/4."""
        errori = valida_password_compliance("abcdefghijklmnop", "test@email.com")
        assert any("Aggiungi" in e for e in errori)

    def test_carattere_ripetuto(self):
        errori = valida_password_compliance("aaaaaaaaaa", "test@email.com")
        assert any("ripetuto" in e for e in errori)

    def test_sequenza_numerica(self):
        errori = valida_password_compliance("012345678901234", "test@email.com")
        assert any("sequenza" in e.lower() for e in errori)

    def test_password_forte(self):
        """Password complessa con tutti i requisiti → nessun errore."""
        errori = valida_password_compliance("Str0ng!P@ss2026", "user@domain.com")
        assert errori == []

    def test_nome_ristorante_corto_ignorato(self):
        """Nome ristorante < 4 char non dovrebbe generare falso positivo."""
        errori = valida_password_compliance("Abc123!@#xyz", "a@b.com", "Bar")
        assert not any("ristorante" in e.lower() for e in errori)


def _make_query_mock(data):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.in_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = MagicMock(data=data)
    return query


class TestRiepilogoFattureAuto:

    def test_include_needs_review_counts(self):
        upload_events_query = _make_query_mock([
            {
                'file_name': 'fattura-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-08T08:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_OK',
            }
        ])
        fatture_query = _make_query_mock([
            {
                'file_origine': 'fattura-a.xml',
                'fornitore': 'Test Fornitore',
                'data_documento': '2026-04-07',
                'totale_riga': 10.0,
                'created_at': '2026-04-08T08:00:00Z',
                'needs_review': True,
            },
            {
                'file_origine': 'fattura-a.xml',
                'fornitore': 'Test Fornitore',
                'data_documento': '2026-04-07',
                'totale_riga': 12.0,
                'created_at': '2026-04-08T08:00:01Z',
                'needs_review': False,
            },
        ])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [upload_events_query, fatture_query]

        summary = riepilogo_fatture_auto_da_ultimo_login(
            user_id='user-1',
            last_login_precedente='2026-04-07T08:00:00Z',
            login_at='2026-04-08T08:00:00Z',
            supabase_client=supabase_client,
        )

        assert summary['has_new'] is True
        assert summary['needs_review_count'] == 1
        assert summary['files_detail'][0]['needs_review_count'] == 1

    def test_ignore_manual_upload_events(self):
        upload_events_query = _make_query_mock([
            {
                'file_name': 'manuale-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-08T08:00:00Z',
                'details': {'source': 'manual_upload'},
                'status': 'SAVED_OK',
            }
        ])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [upload_events_query]

        summary = riepilogo_fatture_auto_da_ultimo_login(
            user_id='user-1',
            last_login_precedente='2026-04-07T08:00:00Z',
            login_at='2026-04-08T08:00:00Z',
            supabase_client=supabase_client,
        )

        assert summary['has_new'] is False
        assert summary['file_count'] == 0

    def test_counts_and_event_ids_grouped_by_file(self):
        upload_events_query = _make_query_mock([
            {
                'id': 101,
                'file_name': 'fattura-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-08T09:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_OK',
            },
            {
                'id': 99,
                'file_name': 'fattura-a.xml',
                'rows_saved': 2,
                'created_at': '2026-04-07T08:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_OK',
            },
            {
                'id': 102,
                'file_name': 'fattura-b.xml',
                'rows_saved': 1,
                'created_at': '2026-04-07T07:00:00Z',
                'details': {'source': 'invoicetronic'},
                'status': 'SAVED_PARTIAL',
            },
        ])
        fatture_query = _make_query_mock([
            {
                'file_origine': 'fattura-a.xml',
                'fornitore': 'Fornitore A',
                'data_documento': '2026-04-08',
                'totale_riga': 10.0,
                'created_at': '2026-04-08T09:00:00Z',
                'needs_review': False,
            },
            {
                'file_origine': 'fattura-b.xml',
                'fornitore': 'Fornitore B',
                'data_documento': '2026-04-07',
                'totale_riga': 5.0,
                'created_at': '2026-04-07T07:00:00Z',
                'needs_review': False,
            },
        ])

        supabase_client = MagicMock()
        supabase_client.table.side_effect = [upload_events_query, fatture_query]

        summary = riepilogo_fatture_auto_da_ultimo_login(
            user_id='user-1',
            last_login_precedente='2026-04-07T08:00:00Z',
            login_at='2026-04-08T08:30:00Z',
            supabase_client=supabase_client,
        )

        assert summary['has_new'] is True
        assert summary['file_count'] == 2
        assert summary['total_pending_count'] == 2
        assert summary['new_count'] == 1
        assert summary['pending_count'] == 1

        file_a = next(f for f in summary['files_detail'] if f['file_name'] == 'fattura-a.xml')
        assert sorted(file_a['event_ids']) == [99, 101]
