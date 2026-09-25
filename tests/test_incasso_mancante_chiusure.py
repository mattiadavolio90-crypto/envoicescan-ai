"""«Manca l'incasso di ieri» tollera i giorni di chiusura dichiarati.

Residuo della fase 1 del piano consulente (§4 ii e iv), chiuso il 25/09/2026:
nello stesso briefing i due segnali sui ricavi avevano due politiche diverse.
`upload_ricavi_failed` tollerava le chiusure (finestra = giorni di chiusura + 1,
decisione del 19/06), `incasso_mancante` no: una sede chiusa il mercoledi'
riceveva «manca l'incasso di ieri» il giovedi', giorno del sollecito.

`giorni_chiusura_settimanali` e' un NUMERO di giorni, non quali: si guarda se
c'e' almeno un incasso negli ultimi N+1 giorni. Con 0 (tutte le sedi al 25/09)
la regola e' quella di prima: solo ieri. Il finto database filtra davvero le
date: e' li' che si vede la finestra.
"""
from __future__ import annotations

import datetime as _dtmod
from datetime import date, timedelta
from unittest.mock import patch

import pytest

import services.fastapi_worker as fw

GIOVEDI = date(2026, 9, 21 + fw._GIORNO_SOLLECITO_INCASSO)
IERI = GIOVEDI - timedelta(days=1)


class _Q:
    def __init__(self, righe):
        self.righe, self.filtri = righe, []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        self.filtri.append(lambda r: r.get(col) in vals)
        return self

    def gte(self, col, val):
        self.filtri.append(lambda r: str(r.get(col)) >= str(val))
        return self

    def lte(self, col, val):
        self.filtri.append(lambda r: str(r.get(col)) <= str(val))
        return self

    def lt(self, col, val):
        self.filtri.append(lambda r: str(r.get(col)) < str(val))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return type("R", (), {"data": [r for r in self.righe if all(f(r) for f in self.filtri)]})()


class _DB:
    def __init__(self, giorni_incasso):
        self.incassi = [{"ristorante_id": "r1", "data": g.isoformat()} for g in giorni_incasso]
        # storia lontana: la sede usa i giornalieri
        self.incassi.append({"ristorante_id": "r1", "data": "2026-05-01"})

    def table(self, nome):
        if nome == "ricavi_giornalieri":
            return _Q(self.incassi)
        return _Q([])


class _Giovedi(_dtmod.datetime):
    @classmethod
    def now(cls, tz=None):
        return _dtmod.datetime(GIOVEDI.year, GIOVEDI.month, GIOVEDI.day, 12, 0, tzinfo=tz)


def _avvisa(giorni_incasso, chiusura, monkeypatch):
    monkeypatch.setattr(fw, "_get_assistant_preferences",
                        lambda rid, sb: {"giorni_chiusura_settimanali": chiusura})
    monkeypatch.setattr(fw, "_load_mensile_overrides", lambda *a, **k: {})
    with patch.object(_dtmod, "datetime", _Giovedi):
        out = fw._briefing_dati_mensili_mancanti("r1", _DB(giorni_incasso), set())
    return "incasso_mancante" in {n["topic_key"] for n in out}


def test_senza_chiusure_conta_solo_ieri(monkeypatch):
    """Con 0 giorni di chiusura la regola e' quella di prima."""
    assert _avvisa([IERI], 0, monkeypatch) is False
    assert _avvisa([IERI - timedelta(days=1)], 0, monkeypatch) is True


def test_con_un_giorno_di_chiusura_ieri_puo_mancare(monkeypatch):
    """Chiuso ieri: l'incasso dell'altro ieri basta a non avvisare."""
    assert _avvisa([IERI - timedelta(days=1)], 1, monkeypatch) is False


def test_la_finestra_non_e_infinita(monkeypatch):
    """Con 1 giorno di chiusura la finestra e' di 2 giorni: tre giorni senza
    incasso restano un buco da segnalare."""
    assert _avvisa([IERI - timedelta(days=2)], 1, monkeypatch) is True
    assert _avvisa([IERI - timedelta(days=2)], 2, monkeypatch) is False


def test_preferenze_illeggibili_regola_severa(monkeypatch):
    def _rotte(rid, sb):
        raise RuntimeError("giu'")

    monkeypatch.setattr(fw, "_load_mensile_overrides", lambda *a, **k: {})
    monkeypatch.setattr(fw, "_get_assistant_preferences", _rotte)
    with patch.object(_dtmod, "datetime", _Giovedi):
        out = fw._briefing_dati_mensili_mancanti("r1", _DB([IERI - timedelta(days=1)]), set())
    assert "incasso_mancante" in {n["topic_key"] for n in out}


def test_un_incasso_futuro_non_copre_ieri(monkeypatch):
    """La finestra finisce a ieri: un incasso di oggi (inserito presto) non
    dice niente su ieri."""
    assert _avvisa([GIOVEDI], 0, monkeypatch) is True


@pytest.mark.parametrize("chiusura", [7, 30, -3])
def test_valori_assurdi_restano_limitati(monkeypatch, chiusura):
    """Una finestra di un mese spegnerebbe il sollecito: il tetto e' 6."""
    assert _avvisa([IERI - timedelta(days=10)], chiusura, monkeypatch) is True
