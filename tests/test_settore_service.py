"""`services.settore_service`: il settore di un account, una volta sola, fail-safe.

Presidia:
  - la prima sede reale ATTIVA decide; sede tecnica e sedi inattive non contano
    (nel fake sono messe PRIMA, cosi' un filtro in meno cambia la risposta);
  - senza sedi, con valore sconosciuto, con user_id assente o su errore DB:
    'ristorazione', e l'errore NON entra in cache (la chiamata dopo ritenta);
  - la cache risponde senza query entro il TTL, scade dopo, e l'admin la invalida;
  - `settore_sede` legge la sede per id, anche tecnica o inattiva.
"""
from __future__ import annotations

import pytest

import services.settore_service as ss

U = "utente-1"


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, righe, conta, esplodi):
        self._righe, self._conta, self._esplodi = righe, conta, esplodi
        self._eq: list = []
        self._ordine = None
        self._limit = None

    def select(self, *_a, **_k):
        return self

    def eq(self, c, v):
        self._eq.append((c, v))
        return self

    def order(self, c, **_k):
        self._ordine = c
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        self._conta[0] += 1
        if self._esplodi:
            raise RuntimeError("db giu'")
        righe = [r for r in self._righe if all(r.get(c) == v for c, v in self._eq)]
        if self._ordine:
            righe = sorted(righe, key=lambda r: r.get(self._ordine) or "")
        if self._limit is not None:
            righe = righe[: self._limit]
        return _Res(righe)


class _FakeSB:
    def __init__(self, righe, esplodi=False):
        self._righe = righe
        self.query = [0]
        self.esplodi = esplodi

    def table(self, _n):
        return _Query(self._righe, self.query, self.esplodi)


def _sede(id_, tipo, *, user=U, attivo=True, tecnica=False, created="2026-01-01"):
    return {"id": id_, "user_id": user, "tipo_attivita": tipo, "attivo": attivo,
            "sede_tecnica": tecnica, "created_at": created}


@pytest.fixture(autouse=True)
def _cache_pulita():
    ss.invalida_cache()
    yield
    ss.invalida_cache()


def test_account_retail():
    assert ss.settore_utente(U, _FakeSB([_sede("a", "retail")])) == "retail"
    assert ss.is_retail(U, _FakeSB([_sede("a", "retail")])) is True


def test_account_senza_sedi_e_ristorazione():
    sb = _FakeSB([])
    assert ss.settore_utente(U, sb) == "ristorazione"
    assert ss.is_retail(U, sb) is False


def test_user_id_assente_non_interroga():
    sb = _FakeSB([_sede("a", "retail")])
    assert ss.settore_utente(None, sb) == "ristorazione"
    assert sb.query[0] == 0


def test_la_sede_tecnica_non_decide():
    sb = _FakeSB([_sede("tec", "retail", tecnica=True, created="2025-01-01"), _sede("a", "ristorazione")])
    assert ss.settore_utente(U, sb) == "ristorazione"


def test_una_sede_inattiva_non_decide():
    sb = _FakeSB([_sede("chiusa", "retail", attivo=False, created="2025-01-01"), _sede("a", "ristorazione")])
    assert ss.settore_utente(U, sb) == "ristorazione"


def test_le_sedi_di_un_altro_utente_non_decidono():
    sb = _FakeSB([_sede("x", "retail", user="altro", created="2025-01-01"), _sede("a", "ristorazione")])
    assert ss.settore_utente(U, sb) == "ristorazione"


def test_un_valore_sconosciuto_vale_ristorazione():
    assert ss.settore_utente(U, _FakeSB([_sede("a", "bar")])) == "ristorazione"
    assert ss.settore_utente("u2", _FakeSB([_sede("b", None, user="u2")])) == "ristorazione"


def test_la_cache_risponde_senza_query_entro_il_ttl():
    sb = _FakeSB([_sede("a", "retail")])
    assert ss.settore_utente(U, sb) == "retail"
    assert ss.settore_utente(U, sb) == "retail"
    assert sb.query[0] == 1


def test_la_cache_scade_dopo_il_ttl(monkeypatch):
    sb = _FakeSB([_sede("a", "retail")])
    ss.settore_utente(U, sb)
    import time
    adesso = time.time()
    monkeypatch.setattr(ss.time, "time", lambda: adesso + ss.TTL_SECONDS + 1)
    sb._righe[0]["tipo_attivita"] = "ristorazione"
    assert ss.settore_utente(U, sb) == "ristorazione"
    assert sb.query[0] == 2


def test_l_admin_invalida_e_la_lettura_dopo_vede_il_nuovo_valore():
    sb = _FakeSB([_sede("a", "ristorazione")])
    assert ss.settore_utente(U, sb) == "ristorazione"
    sb._righe[0]["tipo_attivita"] = "retail"
    assert ss.settore_utente(U, sb) == "ristorazione"
    ss.invalida_cache(U)
    assert ss.settore_utente(U, sb) == "retail"


def test_invalidare_un_utente_non_svuota_gli_altri():
    sb = _FakeSB([_sede("a", "retail"), _sede("b", "ristorazione", user="u2")])
    ss.settore_utente(U, sb)
    ss.settore_utente("u2", sb)
    ss.invalida_cache("u2")
    ss.settore_utente(U, sb)
    assert sb.query[0] == 2


def test_un_errore_db_vale_ristorazione_e_non_resta_in_cache():
    sb = _FakeSB([_sede("a", "retail")], esplodi=True)
    assert ss.settore_utente(U, sb) == "ristorazione"
    sb.esplodi = False
    assert ss.settore_utente(U, sb) == "retail"
    assert sb.query[0] == 2


def test_settore_sede_legge_la_sede_per_id_anche_tecnica_o_inattiva():
    sb = _FakeSB([_sede("tec", "retail", tecnica=True), _sede("chiusa", "retail", attivo=False), _sede("a", "ristorazione")])
    assert ss.settore_sede("tec", sb) == "retail"
    assert ss.settore_sede("chiusa", sb) == "retail"
    assert ss.settore_sede("a", sb) == "ristorazione"
    assert ss.settore_sede("inesistente", sb) == "ristorazione"
    assert ss.settore_sede(None, sb) == "ristorazione"


def test_settore_sede_usa_la_cache_e_l_invalidazione_la_svuota():
    sb = _FakeSB([_sede("a", "retail")])
    assert ss.settore_sede("a", sb) == "retail"
    assert ss.settore_sede("a", sb) == "retail"
    assert sb.query[0] == 1
    ss.invalida_cache(U)
    ss.settore_sede("a", sb)
    assert sb.query[0] == 2
