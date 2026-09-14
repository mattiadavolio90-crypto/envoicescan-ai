"""Lo stato "Scaduta / In scadenza" si decide col giorno di Roma, non con quello UTC.

Fra le 22:00 e le 24:00 UTC (ora legale) a Roma e' gia' domani: `date.today()`
sul worker Railway avrebbe dato una scadenza di oggi ancora "in scadenza" mentre
il cliente la vede gia' scaduta. `_oggi_rome()` esiste dal 2026 nello stesso
modulo e non era usato in questi due punti (14/09/2026).

Il test fissa `_oggi_rome` a una data lontana: se il codice tornasse a
`date.today()` (mutante) la scadenza risulterebbe pianificata, non scaduta.
"""
from datetime import date

from services.documenti_service import get_documenti_scadenziario
from tests.test_documenti_service_scadenziario import _FakeSupabase, _base_tables


def _tabelle():
    fatture = [{
        "user_id": "u1", "ristorante_id": "rist-1", "file_origine": "doc1.xml",
        "fornitore": "Fornitore SRL", "tipo_documento": "TD01", "totale_riga": 50.0,
        "data_documento": "2026-01-10", "created_at": "2026-01-10T10:00:00Z",
    }]
    documenti = [{
        "user_id": "u1", "ristorante_id": "rist-1", "file_origine": "doc1.xml",
        "piva_fornitore": "12345678901", "numero_documento": "1", "totale_documento": 50.0,
        "scadenza_xml": "2029-06-30", "giorni_termini_xml": None,
        "scadenza_effettiva": "2029-06-30", "scadenza_source": "xml",
        "scadenza_override": None, "pagata": False, "pagata_at": None,
    }]
    return _base_tables(fatture, documenti)


def test_lo_stato_usa_il_giorno_di_roma(monkeypatch):
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached", lambda *a, **k: []
    )
    monkeypatch.setattr("services.documenti_service._oggi_rome", lambda: date(2030, 1, 1))
    sb = _FakeSupabase(_tabelle())

    docs = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert len(docs) == 1
    assert docs[0]["stato_scadenza"] == "🔴 Scaduta"
