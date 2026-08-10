"""Test estrazione data_consegna dalle fatture differite TD24.

Il builder di notifiche TD24 (`build_td24_date_notifications`) viveva in
`services/notification_service.py`, rimosso il 17/7/2026 insieme al frontend
Streamlit: era il wrapper di presentazione per la UI dismessa. La logica di
dominio TD24 (estrazione DatiDDT, copertura, normalizzazione) sta in
`utils/formatters.py` ed e' viva in `invoice_service` — ed e' quella coperta qui.
"""
import pytest
from utils.formatters import normalizza_data_consegna_td24


# ── Estrazione DatiDDT ───────────────────────────────────────────────
#
# La classe TestDatiDDTExtraction e' stata RIMOSSA il 10/8/2026 (audit §3).
# Replicava l'algoritmo di estrazione di invoice_service.estrai_dati_da_xml
# in una funzione locale e testava la copia: restava verde anche rompendo il
# codice di produzione. Con TD24 a 11.773 righe attive (35% del totale) e
# data_consegna valorizzata sul 99,98%, era copertura nominale su un percorso
# molto caldo.
#
# Gli stessi schemi (A, C, D, PARTESA, DDT multipli, riferimenti non numerici)
# sono ora coperti contro la funzione VERA in:
#     tests/test_invoice_td24_ddt.py
# con 4 mutazioni verificate rosse.
#
# Qui restano solo i test che esercitano funzioni realmente importate
# (utils.formatters.normalizza_data_consegna_td24) e la logica di soglia.


# ── Alert coverage calc (upload_handler logic) ───────────────────────

class TestTd24CoverageCalc:
    """Soglie dell'alert copertura TD24.

    ⚠️ Anche questa classe REPLICA la logica (quella di `upload_handler.py`)
    invece di importarla: difende le soglie come scelta di prodotto, NON il
    codice che le applica. Lasciata il 10/8/2026 perche' il suo originale vive
    dentro `handle_uploaded_files`, il blocco legacy che l'audit §2 ha escluso
    per misura (raggiungibile solo da `legacy_streamlit/`). Se quel codice
    tornera' vivo, va coperto contro la funzione vera come fatto per DatiDDT in
    `tests/test_invoice_td24_ddt.py`.
    """

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
