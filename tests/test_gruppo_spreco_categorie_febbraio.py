"""Test del fix febbraio in `gruppo_spreco_categorie` (services/routers/gruppo.py).

Il bug (audit ONEFLUX §1, 8/8/2026): l'ultimo giorno del mese era indovinato con
`31 if mese in (1,3,5,...) else (29 if mese == 2 else 30)`, che per febbraio
restituiva SEMPRE 29. In un anno non bisestile la data `AAAA-02-29` non esiste e
Postgres rispondeva APIError 22008 ("date/time field value out of range"),
inghiottito dall'except del chiamante: la finestra "Spreco per categoria"
tornava vuota invece di mostrare i dati di febbraio.

Il fix usa `calendar.monthrange`, come faceva gia' un'altra funzione dello stesso
file. Questo test verifica la data passata all'aggregatore, non il rendering:
e' quella la riga che sbagliava.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.gruppo as gruppo


class _Q:
    def __init__(self, sb, table):
        self._sb = sb
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def order(self, *a, **k): return self

    def execute(self):
        return SimpleNamespace(data=self._sb.rows.get(self._t, []))


class _FakeSB:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _Q(self, name)


_IDS = ["rid-1"]
_SEDI = [{"id": "rid-1", "nome_ristorante": "Locale A"}]


def _chiama(anno, mese):
    """Chiama l'endpoint catturando le date passate all'aggregatore fatture."""
    catturate = {}

    def _fake_load(sb, rid, data_da, data_a):
        catturate["data_da"] = data_da
        catturate["data_a"] = data_a
        return {}

    fw = SimpleNamespace(
        _load_fatture_fb_per_categoria_e_mese=_fake_load,
        _load_mensile_overrides=lambda *a, **k: {},
    )
    sb = _FakeSB({"margini_mensili": []})

    with patch.multiple(
        gruppo,
        _resolve_gruppo=MagicMock(return_value=(sb, "u1", _SEDI, "Gruppo", {"rid-1": "Locale A"}, _IDS)),
        _anno_mese_corrente=MagicMock(return_value=(anno, 12)),
        _completezza_dati_pv=MagicMock(return_value={}),
        _fw=MagicMock(return_value=fw),
    ):
        gruppo.gruppo_spreco_categorie(mese=mese, authorization="Bearer x")

    return catturate


@pytest.mark.parametrize("anno,atteso", [
    (2026, "2026-02-28"),   # non bisestile — il caso che si rompeva
    (2027, "2027-02-28"),   # non bisestile
    (2024, "2024-02-29"),   # bisestile: il 29 esiste davvero
    (2028, "2028-02-29"),   # bisestile
])
def test_febbraio_ultimo_giorno_reale(anno, atteso):
    """Prima del fix questi 4 casi davano tutti `-02-29`: 2 su 4 date inesistenti."""
    out = _chiama(anno, mese=2)
    assert out["data_a"] == atteso
    assert out["data_da"] == f"{anno}-02-01"


@pytest.mark.parametrize("mese,giorno", [
    (1, "31"), (3, "31"), (4, "30"), (6, "30"),
    (9, "30"), (11, "30"), (12, "31"),
])
def test_altri_mesi_invariati(mese, giorno):
    """Il fix non deve cambiare i mesi che erano gia' corretti."""
    out = _chiama(2026, mese=mese)
    assert out["data_a"] == f"2026-{mese:02d}-{giorno}"


def test_data_a_e_sempre_una_data_valida():
    """Guardia generale: nessun mese produce una data che Postgres rifiuterebbe."""
    from datetime import date
    for anno in (2024, 2026, 2027, 2028):
        for mese in range(1, 13):
            out = _chiama(anno, mese=mese)
            date.fromisoformat(out["data_a"])  # solleva se la data non esiste
