"""Test guardia: la card Salute considera il fatturato in modalità 'mensile'.

Difetto osservato (CASATI 14, 18/06): il fatturato di maggio era inserito in
modalità mensile (tabella ricavi_modalita_mensile), quindi margini_mensili.mese=5
restava a 0. La pagina Margini e il segnale del briefing leggono anche la modalità
mensile e mostrano maggio; la card Salute (e _salute_indice_rosso) leggevano SOLO
margini_mensili -> voce "Fatturato inserito" rossa anche col fatturato presente.

Fix: stesso fallback su _load_mensile_overrides usato da
_briefing_dati_mensili_mancanti, così Salute, Margini e briefing coincidono.
"""
from unittest.mock import MagicMock

import services.fastapi_worker as fw
from services.fastapi_worker import _salute_indice_rosso

RID = "rist-casati"


def _sb(modalita_rows):
    """Mock multi-tabella: fatture vuote, margini con solo personale (fatturato 0),
    ricavi_modalita_mensile = modalita_rows."""
    sb = MagicMock()
    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        t = state["table"]
        if t == "ricavi_modalita_mensile":
            return MagicMock(data=modalita_rows)
        if t == "margini_mensili":
            # fatturato 0, personale presente -> personale_ok True
            return MagicMock(data=[{
                "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
                "costo_dipendenti": 1000, "costo_personale_extra": 0,
            }])
        # fatture: nessuna riga recente
        return MagicMock(data=[])

    q = MagicMock()
    sb.table.side_effect = _table
    for m in ("select", "eq", "is_", "gte", "in_", "single", "limit"):
        getattr(q, m).return_value = q
    q.execute.side_effect = _execute
    return sb


def _mese_prec():
    from datetime import date
    try:
        from zoneinfo import ZoneInfo
        oggi = __import__("datetime").datetime.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = date.today()
    return (oggi.year - 1, 12) if oggi.month == 1 else (oggi.year, oggi.month - 1)


def test_override_mensile_evita_rosso(monkeypatch):
    # Niente costi/fatture (fatture_ok False), personale presente, fatturato SOLO
    # in modalità mensile: senza override sarebbe rosso, con override no.
    monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: 0.0)
    anno, mese = _mese_prec()
    modalita = [{
        "anno": anno, "mese": mese, "modalita": "mensile",
        "fatturato_iva10": 9328, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "coperti": None,
    }]
    assert _salute_indice_rosso(RID, _sb(modalita)) is False


def test_senza_override_resta_rosso(monkeypatch):
    # Stessa situazione ma senza modalità mensile: fatturato manca davvero -> rosso.
    monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: 0.0)
    assert _salute_indice_rosso(RID, _sb([])) is True
