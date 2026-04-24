"""Test estrazione data_consegna da TD24 e notification builder."""
import pytest
from services.notification_service import build_td24_date_notifications
from utils.formatters import normalizza_data_consegna_td24


# ── Notification builder ─────────────────────────────────────────────


class TestBuildTd24DateNotifications:

    def test_none_context(self):
        assert build_td24_date_notifications(None) == []

    def test_empty_context(self):
        assert build_td24_date_notifications({}) == []

    def test_no_alerts(self):
        ctx = {
            'upload_id': '20260417120000',
            'td24_date_alerts': [],
        }
        assert build_td24_date_notifications(ctx) == []

    def test_missing_alert(self):
        ctx = {
            'upload_id': '20260417120000',
            'td24_date_alerts': [{
                'file_name': 'FATTURA_TD24.xml',
                'fornitore': 'METRO',
                'status': 'missing',
                'lines_total': 15,
                'lines_with_date': 0,
                'pct': 0.0,
            }],
        }
        notifs = build_td24_date_notifications(ctx)
        assert len(notifs) == 1
        n = notifs[0]
        assert n['level'] == 'info'
        assert n['icon'] == 'ℹ️'
        assert 'td24-date-noddt-' in n['id']
        assert 'METRO' in n['body']
        assert '0/15' in n['body']
        assert 'nessuna azione richiesta' in n['body']

    def test_warning_alert(self):
        ctx = {
            'upload_id': '20260417120000',
            'td24_date_alerts': [{
                'file_name': 'FATTURA_TD24.xml',
                'fornitore': 'Nordfish',
                'status': 'warning',
                'lines_total': 10,
                'lines_with_date': 6,
                'pct': 60.0,
            }],
        }
        notifs = build_td24_date_notifications(ctx)
        assert len(notifs) == 1
        n = notifs[0]
        assert n['level'] == 'info'
        assert 'td24-date-warning-' in n['id']
        assert 'Nordfish' in n['body']
        assert '6/10' in n['body']

    def test_mixed_missing_and_warning(self):
        ctx = {
            'upload_id': '20260417120000',
            'td24_date_alerts': [
                {
                    'file_name': 'A.xml', 'fornitore': 'METRO',
                    'status': 'missing', 'lines_total': 10,
                    'lines_with_date': 2, 'pct': 20.0,
                },
                {
                    'file_name': 'B.xml', 'fornitore': 'Nordfish',
                    'status': 'warning', 'lines_total': 8,
                    'lines_with_date': 5, 'pct': 62.5,
                },
            ],
        }
        notifs = build_td24_date_notifications(ctx)
        assert len(notifs) == 2
        levels = {n['level'] for n in notifs}
        assert levels == {'warning', 'info'}

    def test_xss_protection(self):
        ctx = {
            'upload_id': '20260417120000',
            'td24_date_alerts': [{
                'file_name': '<script>alert(1)</script>.xml',
                'fornitore': '<b>XSS</b>',
                'status': 'missing',
                'lines_total': 5,
                'lines_with_date': 0,
                'pct': 0.0,
            }],
        }
        notifs = build_td24_date_notifications(ctx)
        body = notifs[0]['body']
        assert '<script>' not in body
        assert '&lt;script&gt;' in body
        assert '<b>' not in body


# ── Parser: DatiDDT extraction ───────────────────────────────────────

class TestDatiDDTExtraction:
    """Test the DatiDDT → data_consegna mapping logic in isolation.

    We replicate the extraction algorithm from invoice_service.estrai_dati_da_xml
    as a pure function to test without mocking the entire XML pipeline.
    """

    @staticmethod
    def _extract_ddt_map(dati_generali: dict):
        """Replicate the DatiDDT extraction logic from estrai_dati_da_xml."""
        import re
        from datetime import datetime as dt

        ddt_date_map = {}
        ddt_global_date = None

        dati_ddt_raw = dati_generali.get('DatiDDT')
        if dati_ddt_raw is not None:
            if isinstance(dati_ddt_raw, dict):
                dati_ddt_raw = [dati_ddt_raw]
            if isinstance(dati_ddt_raw, list):
                for ddt_block in dati_ddt_raw:
                    if not isinstance(ddt_block, dict):
                        continue
                    data_ddt = str(ddt_block.get('DataDDT') or '').strip()
                    if not data_ddt:
                        continue
                    rif_linee = ddt_block.get('RiferimentoNumeroLinea')
                    if rif_linee is None:
                        ddt_global_date = data_ddt
                    else:
                        if not isinstance(rif_linee, list):
                            rif_linee = [rif_linee]
                        for num in rif_linee:
                            try:
                                ddt_date_map[int(num)] = data_ddt
                            except (ValueError, TypeError):
                                pass

        return ddt_date_map, ddt_global_date

    @staticmethod
    def _regex_fallback(descrizione: str):
        """Replicate the regex fallback from estrai_dati_da_xml."""
        import re
        from datetime import datetime as dt

        match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', descrizione)
        if match:
            dd, mm, yyyy = match.groups()
            try:
                parsed = dt.strptime(f"{yyyy}-{mm}-{dd}", "%Y-%m-%d")
                if 2020 <= parsed.year <= 2030:
                    return parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    # Schema A: DatiDDT con RiferimentoNumeroLinea
    def test_schema_a_mapped_lines(self):
        dati = {
            'DatiDDT': [
                {
                    'NumeroDDT': 'DDT001',
                    'DataDDT': '2026-03-15',
                    'RiferimentoNumeroLinea': ['1', '2', '3'],
                },
            ]
        }
        m, g = self._extract_ddt_map(dati)
        assert m == {1: '2026-03-15', 2: '2026-03-15', 3: '2026-03-15'}
        assert g is None

    # Schema A: single dict (not list)
    def test_schema_a_single_dict(self):
        dati = {
            'DatiDDT': {
                'NumeroDDT': 'DDT001',
                'DataDDT': '2026-04-01',
                'RiferimentoNumeroLinea': '5',
            }
        }
        m, g = self._extract_ddt_map(dati)
        assert m == {5: '2026-04-01'}
        assert g is None

    # Schema C: DatiDDT senza RiferimentoNumeroLinea → global
    def test_schema_c_global_date(self):
        dati = {
            'DatiDDT': {
                'NumeroDDT': 'DDT999',
                'DataDDT': '2026-02-28',
            }
        }
        m, g = self._extract_ddt_map(dati)
        assert m == {}
        assert g == '2026-02-28'

    # Schema D: no DatiDDT → regex fallback
    def test_schema_d_regex_fallback(self):
        assert self._regex_fallback("MERCE DDT 15/03/2026") == "2026-03-15"

    def test_regex_no_match(self):
        assert self._regex_fallback("Pollo fresco kg 2") is None

    def test_regex_invalid_date(self):
        assert self._regex_fallback("DDT 32/13/2026") is None

    def test_regex_year_out_of_range(self):
        assert self._regex_fallback("DDT 01/01/2019") is None

    # Multiple DatiDDT blocks (multi-DDT per fattura)
    def test_multiple_ddt_blocks(self):
        dati = {
            'DatiDDT': [
                {
                    'DataDDT': '2026-03-10',
                    'RiferimentoNumeroLinea': ['1', '2'],
                },
                {
                    'DataDDT': '2026-03-12',
                    'RiferimentoNumeroLinea': ['3', '4'],
                },
            ]
        }
        m, g = self._extract_ddt_map(dati)
        assert m == {1: '2026-03-10', 2: '2026-03-10', 3: '2026-03-12', 4: '2026-03-12'}
        assert g is None

    def test_empty_ddt(self):
        m, g = self._extract_ddt_map({})
        assert m == {}
        assert g is None


# ── Alert coverage calc (upload_handler logic) ───────────────────────

class TestTd24CoverageCalc:
    """Replicate the coverage logic from upload_handler.py to test soglie."""

    @staticmethod
    def _compute_alert(items):
        """Replicate: filtra righe totale > 0, calcola pct, classifica."""
        _filtered = [r for r in items if float(r.get('Totale_Riga', 0) or 0) > 0]
        total = len(_filtered)
        if total == 0:
            return None  # nessun alert se nessuna riga valida
        with_date = sum(1 for r in _filtered if r.get('data_consegna'))
        pct = (with_date / total * 100)
        if pct >= 95:
            return None  # silenzioso
        return 'missing' if pct < 50 else 'warning'

    def test_pct_100_silenzioso(self):
        items = [{'Totale_Riga': 10, 'data_consegna': '2026-03-15'}] * 5
        assert self._compute_alert(items) is None

    def test_pct_95_silenzioso(self):
        items = [{'Totale_Riga': 10, 'data_consegna': '2026-03-15'}] * 19 + \
                [{'Totale_Riga': 10, 'data_consegna': None}]
        # 19/20 = 95% → silenzioso
        assert self._compute_alert(items) is None

    def test_pct_94_warning(self):
        items = [{'Totale_Riga': 10, 'data_consegna': '2026-03-15'}] * 94 + \
                [{'Totale_Riga': 10, 'data_consegna': None}] * 6
        # 94/100 = 94% → warning
        assert self._compute_alert(items) == 'warning'

    def test_pct_49_missing(self):
        items = [{'Totale_Riga': 10, 'data_consegna': '2026-03-15'}] * 49 + \
                [{'Totale_Riga': 10, 'data_consegna': None}] * 51
        # 49/100 = 49% → missing
        assert self._compute_alert(items) == 'missing'

    def test_pct_0_missing(self):
        items = [{'Totale_Riga': 10, 'data_consegna': None}] * 10
        assert self._compute_alert(items) == 'missing'

    def test_zero_righe_no_alert(self):
        # Fattura TD24 con zero righe prodotto → no division by zero, no alert
        assert self._compute_alert([]) is None

    def test_solo_righe_totale_zero_no_alert(self):
        # Tutte righe con totale 0 (omaggi) → filtrate → no alert
        items = [{'Totale_Riga': 0, 'data_consegna': None}] * 5
        assert self._compute_alert(items) is None

    def test_filtra_spese_trasporto(self):
        # 5 righe merce con data + 2 righe trasporto (totale 0) senza data
        # Solo le 5 merce contano → 100% coperto → silenzioso
        items = [{'Totale_Riga': 10, 'data_consegna': '2026-03-15'}] * 5 + \
                [{'Totale_Riga': 0, 'data_consegna': None}] * 2
        assert self._compute_alert(items) is None

    def test_data_consegna_none_integrato(self):
        # Nessun DDT, nessuna data in descrizione → data_consegna=None ovunque
        items = [{'Totale_Riga': 10, 'data_consegna': None}] * 15
        assert self._compute_alert(items) == 'missing'


class TestTd24FallbackNormalization:

    def test_fallback_to_document_date_when_missing(self):
        items = [{
            'tipo_documento': 'TD24',
            'Data_Documento': '2026-04-24',
            'Totale_Riga': 10,
            'data_consegna': None,
        }]

        normalizza_data_consegna_td24(items)

        assert items[0]['data_consegna'] == '2026-04-24'

    def test_preserves_existing_delivery_date(self):
        items = [{
            'tipo_documento': 'TD24',
            'Data_Documento': '2026-04-24',
            'Totale_Riga': 10,
            'data_consegna': '2026-04-20',
        }]

        normalizza_data_consegna_td24(items)

        assert items[0]['data_consegna'] == '2026-04-20'

    def test_non_td24_is_unchanged(self):
        items = [{
            'tipo_documento': 'TD01',
            'Data_Documento': '2026-04-24',
            'Totale_Riga': 10,
            'data_consegna': None,
        }]

        normalizza_data_consegna_td24(items)

        assert items[0]['data_consegna'] is None
