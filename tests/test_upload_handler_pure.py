"""Test per utils/upload_handler.py — funzioni pure senza Streamlit/Supabase."""
import pytest
from unittest.mock import patch
import pandas as pd

# Importa solo funzioni pure (senza side effects Streamlit/Supabase)
from services.upload_handler import (
    _is_trial_invoice_date_allowed,
    _make_problematic_upload_entry,
    _get_policy_block_kind,
)


class TestIsTrialInvoiceDateAllowed:
    def test_current_month_is_allowed(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-05-01', reference_date=ref) is True

    def test_last_day_current_month_is_allowed(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-05-31', reference_date=ref) is True

    def test_previous_month_is_allowed(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-04-15', reference_date=ref) is True

    def test_two_months_ago_is_blocked(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2026-03-01', reference_date=ref) is False

    def test_next_year_is_blocked(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2027-01-01', reference_date=ref) is False

    def test_previous_year_is_blocked(self):
        ref = pd.Timestamp('2026-05-07')
        assert _is_trial_invoice_date_allowed('2025-12-31', reference_date=ref) is False

    def test_none_data_is_allowed(self):
        """Data mancante → lascia passare per default (sicurezza verso l'alto)."""
        assert _is_trial_invoice_date_allowed(None) is True

    def test_na_string_is_allowed(self):
        assert _is_trial_invoice_date_allowed('N/A') is True

    def test_invalid_date_is_allowed(self):
        assert _is_trial_invoice_date_allowed('not-a-date') is True

    def test_january_ref_previous_month_is_december(self):
        """A gennaio, il mese precedente è dicembre dell'anno scorso."""
        ref = pd.Timestamp('2026-01-15')
        assert _is_trial_invoice_date_allowed('2025-12-01', reference_date=ref) is True
        assert _is_trial_invoice_date_allowed('2025-11-30', reference_date=ref) is False


class TestMakeProblematicUploadEntry:
    def test_returns_dict_with_expected_keys(self):
        result = _make_problematic_upload_entry('fattura.xml', 'file corrotto', 'parse_error')
        assert result == {
            'file_name': 'fattura.xml',
            'reason': 'file corrotto',
            'category': 'parse_error',
        }

    def test_preserves_values_as_is(self):
        result = _make_problematic_upload_entry('x', '', '')
        assert result['file_name'] == 'x'
        assert result['reason'] == ''
        assert result['category'] == ''


class TestGetPolicyBlockKind:
    def test_anno_precedente_prefix_returns_year(self):
        assert _get_policy_block_kind('ANNO PRECEDENTE: fattura.xml') == 'year'

    def test_mese_precedente_prefix_returns_month(self):
        assert _get_policy_block_kind('MESE PRECEDENTE: fattura.xml') == 'month'

    def test_blocco_trial_prefix_returns_trial(self):
        assert _get_policy_block_kind('BLOCCO TRIAL: periodo non consentito') == 'trial'

    def test_unknown_prefix_returns_none(self):
        assert _get_policy_block_kind('ERRORE GENERICO') is None

    def test_empty_string_returns_none(self):
        assert _get_policy_block_kind('') is None

    def test_none_returns_none(self):
        assert _get_policy_block_kind(None) is None

    def test_prefix_case_sensitive(self):
        """Il match deve essere case-sensitive come nel codice sorgente."""
        assert _get_policy_block_kind('anno precedente: fattura.xml') is None

    def test_partial_prefix_not_matched(self):
        assert _get_policy_block_kind('ANNO') is None
