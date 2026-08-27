"""Test §27 residuo (27/8/2026) — `pagata_at` va scritta in ora ITALIANA.

Il difetto, di segno inverso a quello chiuso in §27 (HIGH #6): il frontend scrive
l'aggiornamento ottimistico con `todayLocalIso()` (apps/web/src/lib/scadenziario.ts,
ora locale del browser) mentre il backend persisteva
`datetime.now(timezone.utc).date()`.

Fra mezzanotte e le 02:00 italiane del 1° del mese, UTC e' ancora nel mese
precedente: l'utente in Italia segna pagata alle 00:30 del 1° settembre, il
frontend mostra "01/09" e il DB salva "31/08". Dopo il reload il KPI
"Pagate (mese)" (che raggruppa per mese con `parseLocalDate`) conta la fattura
nel mese sbagliato. Finestra stretta, ma e' la stessa classe di difetto gia'
costata una tranche di remediation.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import services.documenti_service as DS


def test_oggi_rome_usa_il_fuso_italiano():
    assert DS._oggi_rome() == datetime.now(ZoneInfo("Europe/Rome")).date()


@pytest.mark.parametrize("istante_utc,atteso_it", [
    # Notte italiana di inizio mese: UTC e' ancora nel mese precedente.
    ("2026-08-31T22:30:00", date(2026, 9, 1)),   # 00:30 del 1/9 a Roma (CEST)
    ("2026-08-31T23:59:00", date(2026, 9, 1)),   # 01:59 del 1/9 a Roma
    # Inverno (CET, +1): stessa logica con un'ora di scarto.
    ("2026-01-31T23:30:00", date(2026, 2, 1)),   # 00:30 del 1/2 a Roma
    # Fuori dalla finestra critica i due fusi coincidono.
    ("2026-09-15T12:00:00", date(2026, 9, 15)),
])
def test_boundary_mese_la_data_italiana_differisce_da_utc(istante_utc, atteso_it, monkeypatch):
    """Il caso che il fix difende: stesso istante, mese diverso fra i due fusi."""
    fisso = datetime.fromisoformat(istante_utc).replace(tzinfo=timezone.utc)

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fisso.astimezone(tz) if tz else fisso.replace(tzinfo=None)

    monkeypatch.setattr("datetime.datetime", _DT)
    import importlib
    importlib.reload(DS)
    try:
        assert DS._oggi_rome() == atteso_it
    finally:
        monkeypatch.undo()
        importlib.reload(DS)


def test_segna_pagata_non_usa_piu_utc_diretto():
    """La sorgente non deve tornare a `datetime.now(timezone.utc).date()`.

    Ancorato al sorgente perche' il difetto e' nella SCELTA del fuso: un test
    sul valore passerebbe comunque per 22 ore su 24.
    """
    import inspect

    src = inspect.getsource(DS.segna_fattura_pagata)
    assert "_oggi_rome()" in src, "pagata_at deve usare la data italiana"
    assert 'payload["pagata_at"] = datetime.now(timezone.utc).date()' not in src


def test_pagata_manuale_at_resta_in_utc():
    """Controprova: il TIMESTAMP di audit resta UTC, ed e' corretto cosi'.

    `pagata_at` e' una DATA di calendario (semantica utente, va in ora italiana);
    `pagata_manuale_at` e' un istante (semantica di audit, va in UTC). Se un
    domani qualcuno "uniformasse" i due, questo test lo intercetta.
    """
    import inspect

    src = inspect.getsource(DS.segna_fattura_pagata)
    assert 'payload["pagata_manuale_at"] = datetime.now(timezone.utc).isoformat()' in src
