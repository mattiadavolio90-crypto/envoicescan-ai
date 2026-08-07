"""Test guardia: l'alert "ricavi mancanti" dell'Assistente AI considera la
modalità mensile.

Difetto osservato (OFFSIDE, 7/8): i clienti che inseriscono il TOTALE MENSILE
hanno i ricavi in ricavi_modalita_mensile e margini_mensili resta a 0 (misurati
6 mesi 2026 da 54.000-75.000 EUR). L'alert 2 leggeva SOLO margini_mensili e
quindi diceva in chat "Fatturato/ricavi non registrati per <mese>" a un cliente
che li aveva inseriti: l'assistente affermava il falso sui dati del cliente.

Fix: stesso fallback su _load_mensile_overrides già usato da
_briefing_dati_mensili_mancanti (:5054) e dalla card Salute.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw
from services.fastapi_worker import _build_chat_system_prompt

RID = "rist-offside"
FRASE_ALERT = "Fatturato/ricavi non registrati"


def _mese_prec():
    from datetime import date
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        oggi = datetime.now(tz=ZoneInfo("Europe/Rome")).date()
    except Exception:
        oggi = date.today()
    return (oggi.year - 1, 12) if oggi.month == 1 else (oggi.year, oggi.month - 1)


def _sb(modalita_rows):
    """margini_mensili sempre a 0 (modalità mensile), fatture presenti (l'alert 1
    non deve sporcare il prompt), ricavi_modalita_mensile = modalita_rows."""
    sb = MagicMock()
    state = {"table": None}

    def _table(name):
        state["table"] = name
        return q

    def _execute():
        t = state["table"]
        if t == "ricavi_modalita_mensile":
            return MagicMock(data=modalita_rows, count=None)
        if t == "margini_mensili":
            return MagicMock(data=[{
                "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
                "costo_dipendenti": 5000, "costo_personale_extra": 0,
            }], count=None)
        if t == "fatture":
            return MagicMock(data=[{"id": 1}], count=7)
        return MagicMock(data=[], count=0)

    q = MagicMock()
    sb.table.side_effect = _table
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.side_effect = _execute
    return sb


@pytest.fixture(autouse=True)
def _isola_contorno(monkeypatch):
    """Neutralizza le altre sezioni del prompt: qui interessa solo l'alert 2."""
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: MagicMock(has_data=False))
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))


def _prompt(modalita_rows):
    user = {"id": "u-offside", "nome_ristorante": "OFFSIDE", "email": "o@x.it"}
    return _build_chat_system_prompt(user, _sb(modalita_rows), None, ristorante_id=RID)


def test_override_mensile_non_genera_alert_ricavi_mancanti():
    """Il cliente HA inserito il totale mensile: l'assistente non deve dire il
    contrario. È il caso reale di OFFSIDE."""
    anno, mese = _mese_prec()
    modalita = [{
        "anno": anno, "mese": mese, "modalita": "mensile",
        "fatturato_iva10": 60270, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "coperti": None,
    }]
    assert FRASE_ALERT not in _prompt(modalita)


def test_senza_override_l_alert_resta():
    """Nessun ricavo da nessuna delle due fonti: l'alert è corretto e deve restare
    (se sparisse, il fix avrebbe disattivato l'alert invece di correggerlo)."""
    assert FRASE_ALERT in _prompt([])


def test_override_di_un_altro_mese_non_maschera_l_alert():
    """L'override esiste ma per un mese diverso da quello valutato: l'alert resta."""
    anno, mese = _mese_prec()
    altro_mese = 12 if mese != 12 else 1
    modalita = [{
        "anno": anno, "mese": altro_mese, "modalita": "mensile",
        "fatturato_iva10": 60270, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "coperti": None,
    }]
    assert FRASE_ALERT in _prompt(modalita)


def test_override_a_zero_non_maschera_l_alert():
    """Riga in modalità mensile ma con importi a 0: non è un ricavo registrato."""
    anno, mese = _mese_prec()
    modalita = [{
        "anno": anno, "mese": mese, "modalita": "mensile",
        "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "coperti": None,
    }]
    assert FRASE_ALERT in _prompt(modalita)
