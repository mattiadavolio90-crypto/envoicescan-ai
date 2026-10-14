"""Admin → Categorie, «Da sistemare» (lib/admin-categorie.ts): lettura della
risposta, filtro per cliente e testo, quando «Giusta» ha senso, testi."""
from __future__ import annotations

from tests.helpers_ts import esegui_ts

MODULO = "lib/admin-categorie"
FUNZIONI = ["leggiDaSistemare", "filtra", "puoConfermare", "rigaSotto", "esitoClassifica", "toglieGruppo", "riepilogo"]


def _g(chiave, categoria="VERDURE", categorie=None, cliente_ids=("u1",), fornitore="METRO", righe=1, euro=10.0, **extra):
    return {"chiave": chiave, "descrizione": chiave, "ids": [1], "righe": righe, "euro": euro,
            "categoria": categoria, "categorie": categorie or [categoria], "fornitore": fornitore,
            "cliente_ids": list(cliente_ids), "cliente": "Trattoria", "suggerita": None, "fonte": None, **extra}


def _ts(codice, argomento=None):
    return esegui_ts(MODULO, codice, argomento=argomento, richiede=FUNZIONI)


def test_leggi_accetta_la_risposta_buona():
    out = _ts("emit(m.leggiDaSistemare(input));", {"gruppi": [_g("A")], "clienti": [{"id": "u1", "nome": "T"}, {"id": 3}]})
    assert [g["chiave"] for g in out["gruppi"]] == ["A"]
    assert out["clienti"] == [{"id": "u1", "nome": "T"}]


def test_leggi_rifiuta_una_risposta_storta_invece_di_dire_tutto_a_posto():
    for cattiva in [None, {}, {"gruppi": None}, {"detail": "Errore"}, {"gruppi": [{"chiave": "A"}]},
                    {"gruppi": [_g("A", ids=[])]}, {"gruppi": [_g("A", ids=["1"])]}, {"gruppi": [_g("A", euro="10")]}]:
        assert _ts("emit(m.leggiDaSistemare(input));", cattiva) is None, cattiva


def test_leggi_senza_clienti_da_una_lista_vuota():
    assert _ts("emit(m.leggiDaSistemare(input).clienti);", {"gruppi": []}) == []


def test_filtra_per_cliente_e_testo():
    gruppi = [_g("PANE", cliente_ids=["u1"]), _g("LATTE", cliente_ids=["u2"], fornitore="GRANAROLO"),
              _g("BURRO", cliente_ids=["u1", "u2"], fornitore=None)]
    casi = {
        ("tutti", ""): ["PANE", "LATTE", "BURRO"],
        ("u2", ""): ["LATTE", "BURRO"],
        ("tutti", "  pan "): ["PANE"],
        ("tutti", "granar"): ["LATTE"],
        ("u1", "latte"): [],
    }
    for (cliente, testo), atteso in casi.items():
        out = _ts("emit(m.filtra(input.g, input.c, input.t).map(g => g.chiave));", {"g": gruppi, "c": cliente, "t": testo})
        assert out == atteso, (cliente, testo)


def test_giusta_solo_con_una_categoria_vera():
    casi = [
        (_g("A", categoria="VERDURE"), True),
        (_g("B", categoria="Da Classificare"), False),
        (_g("C", categoria="VERDURE", categorie=["FRUTTA", "VERDURE"]), False),
    ]
    out = _ts("emit(input.map(g => m.puoConfermare(g)));", [g for g, _ in casi])
    assert out == [atteso for _, atteso in casi]


def test_riga_sotto():
    out = _ts("emit([m.rigaSotto(input[0]), m.rigaSotto(input[1])]);",
              [_g("A", righe=1), _g("B", fornitore=None, righe=3)])
    assert out == ["METRO · Trattoria · 1 riga", "Trattoria · 3 righe"]


def test_esito_e_quando_togliere_il_gruppo():
    out = _ts("emit([[1,1],[4,4],[1,3],[0,2]].map(([s,c]) => [m.esitoClassifica(s,c), m.toglieGruppo(s,c)]));")
    assert out == [
        ["1 riga sistemata", True],
        ["4 righe sistemate", True],
        ["1 di 3 righe sistemate, le altre restano qui", False],
        ["0 di 2 righe sistemate, le altre restano qui", False],
    ]


def test_riepilogo():
    out = _ts("emit(m.riepilogo(input));", [_g("A", righe=2, euro=10.5), _g("B", righe=3, euro=4.5)])
    assert out == {"gruppi": 2, "righe": 5, "euro": 15}
