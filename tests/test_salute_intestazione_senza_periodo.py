"""L'intestazione della card Completezza dati non promette una finestra sola.

Il difetto, visto negli screenshot del 22/09/2026: la card diceva «Ultimi 30
Giorni» mentre TRE voci su quattro dicevano «Agosto». Non era un errore di
calcolo — ogni riga era vera — era il titolo rimasto indietro.

La cronologia lo spiega: la card nasce davvero a 30 giorni (ca2d3c8,
01/06/2026); poi fatturato e personale migrano all'ultimo mese completo e il
18/06 (8959e88) ci passano anche le fatture, senza che il titolo segua. Il
commento che dichiarava la scelta «deliberata» e' scaduto con loro: diceva «le
altre DUE voci restano sui 30 giorni», ed era rimasta solo «righe classificate».

**Perche' non si sceglie un titolo diverso invece di toglierlo** (decisione di
Mattia, 22/09): scrivere «Agosto» renderebbe falsa la quarta voce, che i 30
giorni li guarda per davvero, e farebbe sparire dall'interfaccia l'unico posto
in cui quella finestra e' nominata. Qualunque titolo unico mente su almeno una
voce, perche' le finestre sono tre.

**Perche' questo file esiste.** Prima non c'era NULLA che guardasse
l'etichetta: sostituendola con una stringa qualsiasi restavano verdi 619 test
(misurato il 22/09). Un'etichetta senza presidio torna a divergere in silenzio,
che e' esattamente come ci e' arrivata.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw


def _sb_vuoto():
    """Nessun dato: l'endpoint prende la via piu' corta e risponde comunque."""
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    return sb


@pytest.fixture
def _endpoint(monkeypatch):
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda *a, **k: {"id": "u1"})
    monkeypatch.setattr(fw, "_get_supabase_client", lambda *a, **k: _sb_vuoto())
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda *a, **k: "rist-1")
    return lambda: fw.home_salute(authorization="Bearer x")


def test_l_intestazione_non_dichiara_un_periodo(_endpoint):
    """Il campo resta nel contratto (tre consumatori lo leggono) ma vuoto:
    il frontend non rende lo <span> quando e' vuoto."""
    assert _endpoint().mese_label == ""


def test_non_dice_trenta_giorni(_endpoint):
    """La stringa che contraddiceva tre voci su quattro."""
    label = _endpoint().mese_label.lower()
    assert "30" not in label and "giorni" not in label


def test_non_dice_un_mese(_endpoint):
    """Nemmeno «agosto»: sposterebbe la bugia sulla quarta voce invece di
    toglierla."""
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    label = _endpoint().mese_label.lower()
    assert not any(m in label for m in mesi), label


def test_il_campo_esiste_ancora_nel_contratto(_endpoint):
    """Rimuoverlo romperebbe dashboard, /m e la demo: si svuota, non si toglie."""
    assert hasattr(_endpoint(), "mese_label")
