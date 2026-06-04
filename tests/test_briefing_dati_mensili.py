"""Test per _briefing_dati_mensili_mancanti (services.fastapi_worker).

Difetto 2: il briefing leggeva solo notification_inbox, che pero' veniva
popolata soltanto dalla vecchia pagina Streamlit. Sull'app nuova le notifiche
"fatturato/costo personale mancante" non comparivano e il briefing diceva
"tutto ok" mentre la Salute (calcolata live) segnalava il mese mancante.

L'helper ricalcola quelle notifiche LIVE dalla stessa fonte della Salute
(margini_mensili, mese precedente, personale = dipendenti + extra), cosi' le
due sezioni Home restano sempre coerenti.
"""
from unittest.mock import MagicMock

from services.fastapi_worker import _briefing_dati_mensili_mancanti

RID = "rist-xyz"


def _sb(rows):
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.execute.return_value = MagicMock(data=rows)
    return q


def _topics(notifs):
    return {n["topic_key"] for n in notifs}


def test_entrambi_presenti_nessuna_notifica():
    rows = [{
        "fatturato_iva10": 1000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 500, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(RID, _sb(rows))
    assert out == []


def test_manca_solo_fatturato():
    rows = [{
        "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 500, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(RID, _sb(rows))
    assert _topics(out) == {"fatturato_mancante"}


def test_manca_solo_personale():
    # Caso reale del bug: fatturato presente, personale a zero -> la Salute
    # segnalava il mese, il briefing diceva "tutto ok".
    rows = [{
        "fatturato_iva10": 100000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 0, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(RID, _sb(rows))
    assert _topics(out) == {"costo_personale_mancante"}


def test_personale_extra_conta():
    # Coerenza con la Salute: personale = dipendenti + extra. Solo extra basta.
    rows = [{
        "fatturato_iva10": 100000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 0, "costo_personale_extra": 200,
    }]
    out = _briefing_dati_mensili_mancanti(RID, _sb(rows))
    assert out == []


def test_nessuna_riga_entrambi_mancanti():
    out = _briefing_dati_mensili_mancanti(RID, _sb([]))
    assert _topics(out) == {"fatturato_mancante", "costo_personale_mancante"}


def test_formato_notifica_compatibile_inbox():
    out = _briefing_dati_mensili_mancanti(RID, _sb([]))
    for n in out:
        assert n["source_type"] == "live"
        assert n["severity"] == "warning"
        assert n["action_page"] == "/margini"
        assert isinstance(n["payload"].get("mese"), str)
        assert isinstance(n["payload"].get("anno"), int)
        assert n["dedupe_key"]


def test_errore_db_non_propaga():
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.execute.side_effect = RuntimeError("boom")
    assert _briefing_dati_mensili_mancanti(RID, q) == []
