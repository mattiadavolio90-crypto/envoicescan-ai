"""
Test del multi-token (services/session_service.py) con un fake client Supabase
in-memory che riproduce il chaining usato dal modulo.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

import services.session_service as ss


# ─── Fake client Supabase minimale per la tabella "sessioni" ──────────────────

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, op):
        self._store = store
        self._op = op            # 'select' | 'insert' | 'update'
        self._filters = []       # lista di (campo, valore) per eq
        self._is_null = []       # campi con is_(.., 'null')
        self._order = None
        self._order_desc = False
        self._limit = None
        self._insert_row = None
        self._update_patch = None
        self._in = None          # (campo, [valori])

    def insert(self, row):
        self._op = "insert"
        self._insert_row = dict(row)
        return self

    def update(self, patch):
        self._op = "update"
        self._update_patch = dict(patch)
        return self

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, field, value):
        self._filters.append((field, value))
        return self

    def is_(self, field, _null):
        self._is_null.append(field)
        return self

    def in_(self, field, values):
        self._in = (field, list(values))
        return self

    def order(self, field, desc=False):
        self._order = field
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, row):
        for f, v in self._filters:
            if row.get(f) != v:
                return False
        for f in self._is_null:
            if row.get(f) is not None:
                return False
        if self._in is not None:
            f, vals = self._in
            if row.get(f) not in vals:
                return False
        return True

    def execute(self):
        if self._op == "insert":
            row = self._insert_row
            row.setdefault("id", f"id-{len(self._store)+1}-{time.time_ns()}")
            row.setdefault("created_at", ss._now_iso())
            row.setdefault("last_seen_at", ss._now_iso())
            row.setdefault("revoked_at", None)
            self._store.append(row)
            return _Result([dict(row)])

        rows = [r for r in self._store if self._matches(r)]

        if self._op == "update":
            for r in rows:
                r.update(self._update_patch)
            return _Result([dict(r) for r in rows])

        # select
        if self._order:
            rows = sorted(rows, key=lambda r: r.get(self._order) or "", reverse=self._order_desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result([dict(r) for r in rows])


class FakeClient:
    def __init__(self):
        self.sessioni = []

    def table(self, name):
        assert name == "sessioni", f"tabella inattesa: {name}"
        return _Query(self.sessioni, op=None)


@pytest.fixture
def fake():
    c = FakeClient()
    ss._LAST_SEEN_THROTTLE.clear()
    return c


# ─── Test ─────────────────────────────────────────────────────────────────────

def test_crea_e_risolvi_sessione(fake):
    token = ss.crea_sessione("u1", supabase_client=fake)
    assert token
    assert ss.risolvi_sessione(token, supabase_client=fake) == "u1"


def test_risolvi_sessione_token_inesistente(fake):
    assert ss.risolvi_sessione("non-esiste", supabase_client=fake) is None


def test_revoca_sessione(fake):
    token = ss.crea_sessione("u1", supabase_client=fake)
    assert ss.revoca_sessione(token, supabase_client=fake) is True
    assert ss.risolvi_sessione(token, supabase_client=fake) is None
    # revocare due volte: la seconda non trova nulla di attivo
    assert ss.revoca_sessione(token, supabase_client=fake) is False


def test_sessioni_multiple_coesistono(fake):
    t1 = ss.crea_sessione("u1", supabase_client=fake)
    t2 = ss.crea_sessione("u1", supabase_client=fake)
    # Entrambe valide: un secondo login NON slogga il primo
    assert ss.risolvi_sessione(t1, supabase_client=fake) == "u1"
    assert ss.risolvi_sessione(t2, supabase_client=fake) == "u1"


def test_evict_oltre_cap(fake, monkeypatch):
    monkeypatch.setattr(ss, "MAX_SESSIONI_ATTIVE", 5)
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    # 5 sessioni già esistenti con last_seen crescente (la prima è la più vecchia)
    vecchi = []
    for i in range(5):
        tok = ss.crea_sessione("u1", supabase_client=fake)
        for r in fake.sessioni:
            if r["token"] == tok:
                r["last_seen_at"] = (base + timedelta(seconds=i)).isoformat()
        vecchi.append(tok)

    # 6° login: deve triggerare l'evict della più vecchia (vecchi[0])
    nuovo = ss.crea_sessione("u1", supabase_client=fake)

    attive = [r for r in fake.sessioni if r["revoked_at"] is None]
    assert len(attive) == 5
    assert ss.risolvi_sessione(vecchi[0], supabase_client=fake) is None
    assert ss.risolvi_sessione(nuovo, supabase_client=fake) == "u1"


def test_inattivita_revoca(fake):
    token = ss.crea_sessione("u1", supabase_client=fake)
    # invecchia la sessione oltre la soglia
    vecchio = (datetime.now(timezone.utc) - timedelta(hours=ss.SESSION_INACTIVITY_HOURS + 1)).isoformat()
    for r in fake.sessioni:
        r["last_seen_at"] = vecchio
    assert ss.risolvi_sessione(token, supabase_client=fake) is None
    # ed è stata revocata nel DB
    assert all(r["revoked_at"] is not None for r in fake.sessioni)


def test_revoca_tutte_sessioni(fake):
    ss.crea_sessione("u1", supabase_client=fake)
    ss.crea_sessione("u1", supabase_client=fake)
    ss.crea_sessione("u2", supabase_client=fake)
    n = ss.revoca_tutte_sessioni("u1", supabase_client=fake)
    assert n == 2
    attive_u2 = [r for r in fake.sessioni if r["user_id"] == "u2" and r["revoked_at"] is None]
    assert len(attive_u2) == 1


def test_tocca_sessione_throttle(fake):
    token = ss.crea_sessione("u1", supabase_client=fake)
    # primo tocco scrive
    ss.tocca_sessione(token, supabase_client=fake)
    primo = next(r for r in fake.sessioni if r["token"] == token)["last_seen_at"]
    # secondo tocco entro la finestra di throttle: non riscrive
    ss.tocca_sessione(token, supabase_client=fake)
    secondo = next(r for r in fake.sessioni if r["token"] == token)["last_seen_at"]
    assert primo == secondo
