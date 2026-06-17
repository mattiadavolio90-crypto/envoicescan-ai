"""Test per _briefing_dati_mensili_mancanti (services.fastapi_worker).

Difetto 2: il briefing leggeva solo notification_inbox, che pero' veniva
popolata soltanto dalla vecchia pagina Streamlit. Sull'app nuova le notifiche
"fatturato/costo personale mancante" non comparivano e il briefing diceva
"tutto ok" mentre la Salute (calcolata live) segnalava il mese mancante.

L'helper ricalcola quelle notifiche LIVE dalla stessa fonte della Salute
(margini_mensili, mese precedente, personale = dipendenti + extra), cosi' le
due sezioni Home restano sempre coerenti.
"""
from datetime import date

from unittest.mock import MagicMock

from services.fastapi_worker import _briefing_dati_mensili_mancanti

RID = "rist-xyz"


def _mese_precedente():
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        oggi = datetime.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = date.today()
    if oggi.month == 1:
        return oggi.year - 1, 12
    return oggi.year, oggi.month - 1


def _mese_corrente():
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        oggi = datetime.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = date.today()
    return oggi.year, oggi.month


def _sb(margini_rows, incasso_ieri=True, modalita_rows=None):
    """Mock supabase a tre tabelle.

    La funzione interroga 'margini_mensili', 'ricavi_modalita_mensile' (override
    della modalità mensile) e 'ricavi_giornalieri'.
    incasso_ieri=True -> riga di ieri presente (nessuna notifica incasso).
    modalita_rows -> righe di ricavi_modalita_mensile (modalità 'mensile').
    """
    incasso_rows = [{"data": "2026-06-03"}] if incasso_ieri else []
    modalita_rows = modalita_rows or []

    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        if state["table"] == "ricavi_giornalieri":
            return MagicMock(data=incasso_rows)
        if state["table"] == "ricavi_modalita_mensile":
            return MagicMock(data=modalita_rows)
        return MagicMock(data=margini_rows)

    q = MagicMock()
    q.table.side_effect = _table
    q.select.return_value = q
    q.eq.return_value = q
    q.in_.return_value = q
    q.limit.return_value = q
    q.execute.side_effect = _execute
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
        assert n["dedupe_key"]
        if n["topic_key"] in ("fatturato_mancante", "costo_personale_mancante"):
            assert isinstance(n["payload"].get("mese"), str)
            assert isinstance(n["payload"].get("anno"), int)


def test_errore_db_non_propaga():
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.side_effect = RuntimeError("boom")
    assert _briefing_dati_mensili_mancanti(RID, q) == []


# ── Incasso di ieri ─────────────────────────────────────────────────────────

def test_incasso_ieri_presente_nessuna_notifica():
    # Margini completi + incasso di ieri presente -> nessuna notifica.
    rows = [{
        "fatturato_iva10": 1000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 500, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(RID, _sb(rows, incasso_ieri=True))
    assert out == []


def test_incasso_ieri_mancante_genera_notifica():
    rows = [{
        "fatturato_iva10": 1000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 500, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(RID, _sb(rows, incasso_ieri=False))
    assert _topics(out) == {"incasso_mancante"}


def test_incasso_e_mensili_insieme():
    # Tutto mancante: i tre topic compaiono insieme.
    out = _briefing_dati_mensili_mancanti(RID, _sb([], incasso_ieri=False))
    assert _topics(out) == {
        "fatturato_mancante", "costo_personale_mancante", "incasso_mancante",
    }


# ── Modalità mensile: il fatturato sta in ricavi_modalita_mensile ────────────

def test_fatturato_mensile_soddisfa_alert():
    # Bug reale (CASATI 14, TIME CAFE): fatturato inserito in modalità mensile
    # -> margini_mensili resta a 0, ma l'alert non deve comparire.
    anno, mese = _mese_precedente()
    cur_anno, cur_mese = _mese_corrente()
    modalita = [{
        "anno": anno, "mese": mese, "modalita": "mensile",
        "fatturato_iva10": 9328, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "coperti": None,
    }]
    # Costo personale presente per isolare il solo fatturato.
    rows = [{
        "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 500, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(
        RID, _sb(rows, incasso_ieri=False, modalita_rows=modalita)
    )
    # L'override mensile del mese precedente soddisfa il fatturato.
    assert "fatturato_mancante" not in _topics(out)


def test_incasso_ieri_non_alert_se_mese_corrente_mensile():
    # Mese corrente in modalità mensile: il cliente non inserisce giornalieri,
    # quindi l'incasso di ieri non manca mai davvero -> nessun alert quotidiano.
    cur_anno, cur_mese = _mese_corrente()
    modalita = [{
        "anno": cur_anno, "mese": cur_mese, "modalita": "mensile",
        "fatturato_iva10": 100, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "coperti": None,
    }]
    rows = [{
        "fatturato_iva10": 1000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": 500, "costo_personale_extra": 0,
    }]
    out = _briefing_dati_mensili_mancanti(
        RID, _sb(rows, incasso_ieri=False, modalita_rows=modalita)
    )
    assert "incasso_mancante" not in _topics(out)
