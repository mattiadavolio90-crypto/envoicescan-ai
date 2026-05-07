"""Test per utils/period_helper.py — logica date pura senza Streamlit."""
import pytest
from datetime import date
from unittest.mock import patch
from utils.period_helper import calcola_date_periodo, risolvi_periodo, PERIODO_OPTIONS


class TestCalcolaDatePeriodo:
    def test_returns_all_required_keys(self):
        result = calcola_date_periodo()
        assert set(result.keys()) == {
            'oggi', 'inizio_mese', 'inizio_trimestre',
            'inizio_semestre', 'inizio_anno',
        }

    def test_inizio_mese_is_first_day_of_current_month(self):
        result = calcola_date_periodo()
        assert result['inizio_mese'].day == 1
        assert result['inizio_mese'].month == result['oggi'].month
        assert result['inizio_mese'].year == result['oggi'].year

    def test_inizio_anno_is_january_first(self):
        result = calcola_date_periodo()
        assert result['inizio_anno'].month == 1
        assert result['inizio_anno'].day == 1
        assert result['inizio_anno'].year == result['oggi'].year

    @pytest.mark.parametrize("mese,expected_trim_start", [
        (1, 1), (2, 1), (3, 1),
        (4, 4), (5, 4), (6, 4),
        (7, 7), (8, 7), (9, 7),
        (10, 10), (11, 10), (12, 10),
    ])
    def test_inizio_trimestre_per_mese(self, mese, expected_trim_start):
        with patch('utils.period_helper.date') as mock_date:
            mock_date.today.return_value = date(2026, mese, 15)
            result = calcola_date_periodo()
        assert result['inizio_trimestre'].month == expected_trim_start
        assert result['inizio_trimestre'].day == 1

    @pytest.mark.parametrize("mese,expected_sem_start", [
        (1, 1), (3, 1), (6, 1),
        (7, 7), (9, 7), (12, 7),
    ])
    def test_inizio_semestre_per_mese(self, mese, expected_sem_start):
        with patch('utils.period_helper.date') as mock_date:
            mock_date.today.return_value = date(2026, mese, 15)
            result = calcola_date_periodo()
        assert result['inizio_semestre'].month == expected_sem_start
        assert result['inizio_semestre'].day == 1

    def test_tutte_le_date_sono_nel_passato_o_oggi(self):
        result = calcola_date_periodo()
        oggi = result['oggi']
        assert result['inizio_mese'] <= oggi
        assert result['inizio_trimestre'] <= oggi
        assert result['inizio_semestre'] <= oggi
        assert result['inizio_anno'] <= oggi


class TestRisolviPeriodo:
    def _date_periodo(self, mese: int = 5, giorno: int = 7, anno: int = 2026) -> dict:
        oggi = date(anno, mese, giorno)
        mese_trim = ((oggi.month - 1) // 3) * 3 + 1
        mese_sem = 1 if oggi.month <= 6 else 7
        return {
            'oggi': oggi,
            'inizio_mese': oggi.replace(day=1),
            'inizio_trimestre': oggi.replace(month=mese_trim, day=1),
            'inizio_semestre': oggi.replace(month=mese_sem, day=1),
            'inizio_anno': oggi.replace(month=1, day=1),
        }

    def test_mese_in_corso_returns_correct_range(self):
        dp = self._date_periodo()
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[0], dp)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 7)
        assert label is not None

    def test_anno_in_corso_starts_from_january(self):
        dp = self._date_periodo()
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[3], dp)
        assert start == date(2026, 1, 1)
        assert end == dp['oggi']

    def test_periodo_personalizzato_returns_none_start(self):
        dp = self._date_periodo()
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[4], dp)
        assert start is None
        assert label is None

    def test_trimestre_q1_starts_from_january(self):
        dp = self._date_periodo(mese=2)
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[1], dp)
        assert start == date(2026, 1, 1)

    def test_trimestre_q3_starts_from_july(self):
        dp = self._date_periodo(mese=9)
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[1], dp)
        assert start == date(2026, 7, 1)

    def test_semestre_h1_starts_from_january(self):
        dp = self._date_periodo(mese=3)
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[2], dp)
        assert start == date(2026, 1, 1)

    def test_semestre_h2_starts_from_july(self):
        dp = self._date_periodo(mese=8)
        start, end, label = risolvi_periodo(PERIODO_OPTIONS[2], dp)
        assert start == date(2026, 7, 1)

    def test_label_contains_date_strings(self):
        dp = self._date_periodo()
        _, _, label = risolvi_periodo(PERIODO_OPTIONS[0], dp)
        assert '2026' in label
