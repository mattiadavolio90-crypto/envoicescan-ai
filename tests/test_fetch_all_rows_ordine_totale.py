"""`_fetch_all_rows` legge le pagine su un ordine totale, o perde righe in silenzio.

Il difetto che presidia, misurato il 10/09/2026 sul DB vivo: la memoria locale di
un cliente con 3.067 voci (4 pagine) tornava, in 2 letture su 10, con 66 e 653
righe mancanti rimpiazzate da duplicati — e il TOTALE era sempre 3.067. Senza
ORDER BY, OFFSET/LIMIT non promette che la pagina 2 continui la pagina 1: il
planner puo' restituire un ordine fisico diverso a ogni richiesta. Il worker
teneva quella memoria a meta' in cache per un'ora, e in quell'ora le correzioni
del cliente sulle voci mancanti non valevano.

Il fake qui sotto fa cio' che fa il planner quando nessuno gli chiede un ordine:
ruota l'elenco di 7 posizioni a ogni richiesta. Con `.order("id")` le pagine sono
fette dello stesso elenco e il risultato copre ogni riga una volta sola; senza,
il totale torna (2.500) ma 14 righe sono duplicate e 14 mancano — esattamente il
sintomo visto in produzione. L'asserzione e' sugli id DISTINTI: il conteggio da
solo e' un aggregato in cui i buchi e i duplicati si compensano.
"""
from __future__ import annotations

import services.ai_service as ai_service

RIGHE = 2500  # tre pagine da 1000: 1000 + 1000 + 500


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, righe, contatore):
        self._righe = righe
        self._contatore = contatore
        self._filtri: list = []
        self._ordine = None
        self._range = None

    def select(self, *_a, **_k):
        return self

    def eq(self, colonna, valore):
        self._filtri.append((colonna, valore))
        return self

    def order(self, colonna, desc=False, **_k):
        self._ordine = (colonna, desc)
        return self

    def range(self, lo, hi):
        self._range = (lo, hi)
        return self

    def execute(self):
        righe = [r for r in self._righe if all(r.get(c) == v for c, v in self._filtri)]
        if self._ordine:
            colonna, desc = self._ordine
            righe = sorted(righe, key=lambda r: r[colonna], reverse=desc)
        elif righe:
            # Nessun ordine chiesto: ordine "fisico" diverso a ogni richiesta.
            k = (self._contatore[0] * 7) % len(righe)
            righe = righe[k:] + righe[:k]
        self._contatore[0] += 1
        lo, hi = self._range
        return _Res(righe[lo:hi + 1])


class _FakeSB:
    def __init__(self, righe):
        self._righe = righe
        self.richieste = [0]

    def table(self, _nome):
        return _Query(self._righe, self.richieste)


def _righe(n, utente="u1"):
    # Id e descrizione ordinano in modo DIVERSO: la descrizione conta all'indietro.
    # Cosi' "un ordine totale qualsiasi" non basta a passare: il test chiede che
    # l'ordine sia quello della chiave primaria, che e' l'unica unica su
    # `prodotti_utente` letto intero (la descrizione e' unica solo per utente).
    return [{"id": f"{i:05d}", "user_id": utente, "descrizione": f"PRODOTTO {n - i:05d}"} for i in range(n)]


def test_le_pagine_coprono_ogni_riga_una_volta_sola():
    sb = _FakeSB(_righe(RIGHE))
    out = ai_service._fetch_all_rows(sb, "prodotti_utente", "id, descrizione", filters={"user_id": "u1"})
    ids = [r["id"] for r in out]
    assert len(ids) == RIGHE
    assert len(set(ids)) == RIGHE, f"{RIGHE - len(set(ids))} righe perse e rimpiazzate da duplicati"
    assert ids == sorted(ids), "le pagine non seguono la chiave primaria crescente"
    assert sb.richieste[0] == 3


def test_il_filtro_resta_applicato_sulle_pagine():
    sb = _FakeSB(_righe(RIGHE, "u1") + _righe(300, "u2"))
    out = ai_service._fetch_all_rows(sb, "prodotti_utente", "id", filters={"user_id": "u2"})
    assert {r["user_id"] for r in out} == {"u2"}
    assert len({r["id"] for r in out}) == 300


def test_sotto_una_pagina_una_sola_richiesta():
    sb = _FakeSB(_righe(4))
    out = ai_service._fetch_all_rows(sb, "classificazioni_manuali", "id")
    assert [r["id"] for r in out] == ["00000", "00001", "00002", "00003"]
    assert sb.richieste[0] == 1
