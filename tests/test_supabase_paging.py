"""Presidio di utils/supabase_paging.fetch_all.

Il modulo esiste perche' PostgREST tronca a 1000 righe senza errore, senza
warning e senza log: una query troncata non sembra rotta, sembra un dato piu'
piccolo. Su ONEFLUX e' gia' successo due volte (filtro categorie che perdeva
"Da Classificare" su 4 sedi; briefing di catena che sottostimava le fatture).

I test chiamano fetch_all vero contro un builder che si comporta come PostgREST
(onora l'ultimo range applicato), invece di ricalcolare la paginazione: un test
che riscrive la formula sopravvive al mutante.
"""

import logging

import pytest

from utils.supabase_paging import fetch_all


class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeBuilder:
    """Builder PostgREST-like: `range()` accumula, l'ULTIMO valore vince.

    Riproduce il dettaglio documentato in supabase_paging: lo stesso builder e'
    riusato a ogni pagina e i parametri si accumulano; il server onora l'ultimo.
    """

    def __init__(self, rows):
        self._rows = rows
        self.ranges = []

    def range(self, start, end):
        self.ranges.append((start, end))
        return self

    def execute(self):
        start, end = self.ranges[-1]
        return _FakeResp(self._rows[start:end + 1])


def _rows(n):
    return [{"id": i} for i in range(n)]


def test_prende_tutte_le_righe_oltre_la_prima_pagina():
    """2.500 righe con pagine da 1000: senza paginazione ne tornerebbero 1000."""
    builder = _FakeBuilder(_rows(2500))

    out = fetch_all(builder)

    assert len(out) == 2500
    assert [r["id"] for r in out] == list(range(2500))


def test_pagine_richieste_senza_sovrapposizioni_ne_buchi():
    builder = _FakeBuilder(_rows(2500))

    fetch_all(builder)

    assert builder.ranges == [(0, 999), (1000, 1999), (2000, 2999)]


def test_ultima_pagina_piena_chiude_con_una_pagina_vuota():
    """Con un totale multiplo esatto serve un giro in piu' per sapere che e' finita."""
    builder = _FakeBuilder(_rows(2000))

    out = fetch_all(builder)

    assert len(out) == 2000
    assert builder.ranges[-1] == (2000, 2999)


def test_meno_di_una_pagina_non_chiede_la_seconda():
    builder = _FakeBuilder(_rows(10))

    out = fetch_all(builder)

    assert len(out) == 10
    assert builder.ranges == [(0, 999)]


def test_risultato_vuoto_non_va_in_loop():
    builder = _FakeBuilder([])

    assert fetch_all(builder) == []
    assert builder.ranges == [(0, 999)]


def test_il_troncamento_al_cap_non_e_silenzioso(caplog):
    """La garanzia del modulo: tronca, ma lo dice. Un cap muto sarebbe il difetto
    che questo file esiste per impedire."""
    builder = _FakeBuilder(_rows(500))

    with caplog.at_level(logging.WARNING, logger="supabase_paging"):
        out = fetch_all(builder, page_size=100, max_rows=300)

    assert len(out) == 300
    assert any("TRONCATO" in r.message or "troncato" in r.message.lower()
               for r in caplog.records), "il troncamento deve emettere un warning"


def test_page_size_personalizzato_rispettato():
    builder = _FakeBuilder(_rows(250))

    out = fetch_all(builder, page_size=100)

    assert len(out) == 250
    assert builder.ranges == [(0, 99), (100, 199), (200, 299)]


@pytest.mark.parametrize("totale", [1, 999, 1000, 1001, 1999, 2000, 2001])
def test_nessuna_riga_persa_ne_duplicata_al_variare_del_totale(totale):
    builder = _FakeBuilder(_rows(totale))

    out = fetch_all(builder)

    assert [r["id"] for r in out] == list(range(totale))
