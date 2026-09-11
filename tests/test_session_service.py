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


# ─── Retry dell'insert sulle cadute di connessione ────────────────────────────
#
# Regressione 11/09/2026: una connessione HTTP/2 chiusa dal server ma ancora nel
# pool faceva fallire l'INSERT di sessione con RemoteProtocolError. httpx non
# ritenta un INSERT, quindi il login rispondeva 500 con le credenziali gia'
# verificate (utente fuori, "Errore creazione sessione").

class RemoteProtocolError(Exception):
    """Stesso nome di classe di httpx.RemoteProtocolError: il riconoscimento in
    session_service e' per nome della classe, non per import — quindi il nome
    qui deve combaciare esattamente con quello vero."""


class _ClientCheCade(FakeClient):
    """FakeClient che fa cadere i primi N insert con l'errore indicato."""

    def __init__(self, cadute, errore=None):
        super().__init__()
        self.cadute = cadute
        self.tentativi_insert = 0
        self._errore = errore or RemoteProtocolError("<ConnectionTerminated error_code:0>")

    def table(self, name):
        q = super().table(name)
        insert_originale = q.insert

        def insert(row):
            self.tentativi_insert += 1
            if self.tentativi_insert <= self.cadute:
                raise self._errore
            return insert_originale(row)

        q.insert = insert
        return q


@pytest.fixture(autouse=True)
def _niente_attesa_nei_test(monkeypatch):
    monkeypatch.setattr(ss, "_INSERT_BACKOFF_SECONDS", 0)


def test_crea_sessione_ritenta_dopo_caduta_connessione():
    sb = _ClientCheCade(cadute=2)
    token = ss.crea_sessione("u1", supabase_client=sb)
    assert token
    assert sb.tentativi_insert == 3
    # La sessione e' utilizzabile: il token restituito e' quello salvato.
    assert ss.risolvi_sessione(token, supabase_client=sb) == "u1"


def test_token_resta_lo_stesso_fra_i_tentativi():
    sb = _ClientCheCade(cadute=1)
    token = ss.crea_sessione("u1", supabase_client=sb)
    assert [r["token"] for r in sb.sessioni] == [token]


def test_crea_sessione_si_arrende_dopo_il_cap():
    sb = _ClientCheCade(cadute=99)
    with pytest.raises(RemoteProtocolError):
        ss.crea_sessione("u1", supabase_client=sb)
    assert sb.tentativi_insert == ss._INSERT_TENTATIVI


def test_errore_applicativo_non_viene_ritentato():
    """Un permission denied non e' una caduta di rete: deve emergere subito,
    o il retry maschererebbe un bug vero moltiplicando le scritture."""
    sb = _ClientCheCade(cadute=99, errore=Exception("permission denied for table sessioni"))
    with pytest.raises(Exception, match="permission denied"):
        ss.crea_sessione("u1", supabase_client=sb)
    assert sb.tentativi_insert == 1


def test_duplicato_token_vale_successo():
    """Se un tentativo era passato davvero, il ritentativo sbatte sull'indice
    unico: la sessione esiste, il login non deve fallire."""
    sb = _ClientCheCade(cadute=99, errore=Exception("duplicate key value violates unique constraint (23505)"))
    assert ss.crea_sessione("u1", supabase_client=sb)
    assert sb.tentativi_insert == 1


# ─── Il client anon non va ricreato a ogni login ──────────────────────────────
#
# Incidente 11/09/2026: _get_supabase_anon_client() creava un client Supabase
# nuovo (pool proprio, mai chiuso) a ogni login. Sotto traffico normale questo
# esauriva le connessioni verso Supabase e l'INSERT in `sessioni` cadeva con
# ConnectionTerminated -> login 500 con le credenziali gia' verificate.

def test_client_anon_creato_una_volta_sola(monkeypatch):
    from services import auth_service as a

    creati = []

    def _fake_create_client(url, key):
        creati.append((url, key))
        return object()

    monkeypatch.setattr(a, "_ANON_CLIENT", None)
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    # Sul worker st.secrets non esiste: la funzione cade sulle env var. Nei test
    # lo shim Streamlit risponde, quindi va neutralizzato o non si misura il
    # percorso reale.
    monkeypatch.setattr(a, "_ANON_CLIENT", None)
    import sys, types
    finto_st = types.ModuleType("streamlit")
    def _boom(*_a, **_k):
        raise RuntimeError("no secrets")
    class _S:
        def __getitem__(self, _k): _boom()
        def get(self, *_a, **_k): _boom()
    finto_st.secrets = _S()
    monkeypatch.setitem(sys.modules, "streamlit", finto_st)
    import supabase
    monkeypatch.setattr(supabase, "create_client", _fake_create_client)

    primo = a._get_supabase_anon_client()
    for _ in range(20):
        a._get_supabase_anon_client()

    assert primo is not None
    assert len(creati) == 1, f"client creati: {len(creati)} (atteso 1)"


def test_client_anon_non_memorizza_il_fallimento(monkeypatch):
    """Un None cachato lascerebbe il bridge morto per tutta la vita del processo
    anche dopo che la chiave viene configurata."""
    from services import auth_service as a

    monkeypatch.setattr(a, "_ANON_CLIENT", None)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    import sys, types
    finto_st = types.ModuleType("streamlit")
    def _boom(*_a, **_k):
        raise RuntimeError("no secrets")
    class _S:
        def __getitem__(self, _k): _boom()
        def get(self, *_a, **_k): _boom()
    finto_st.secrets = _S()
    monkeypatch.setitem(sys.modules, "streamlit", finto_st)
    import supabase
    monkeypatch.setattr(supabase, "create_client", lambda url, key: object())

    assert a._get_supabase_anon_client() is None

    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    assert a._get_supabase_anon_client() is not None
