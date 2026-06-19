"""Test del "Flusso dati" admin — controllo ricezione fatture Invoicetronic.

- `admin_sistema_invoicetronic_salute`: aggrega `fatture_queue` per cliente
  (via P.IVA delle sedi), classifica lo stato e raccoglie le P.IVA orfane.
- azioni correttive: `admin_queue_assegna_piva`, `admin_queue_riprova`,
  `admin_queue_assegna_sede` — agiscono SOLO se lo stato del record è quello
  atteso (guard) e riusano le RPC DB esistenti.

Fake client Supabase in-memory che riproduce il chaining usato dal router
(table/select/eq/in_/gte/order/update/limit/execute + rpc).
"""
import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin
import pytest
from fastapi import HTTPException


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _RpcCall:
    """`sb.rpc(...)` ritorna un oggetto con `.execute()` (come supabase-py)."""
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _Result(self._data)


class _Query:
    def __init__(self, store):
        self._store = store
        self._op = "select"
        self._filters = []
        self._in = None
        self._gte = []
        self._limit = None
        self._update_vals = None
        self._is_null = []
        self._count = None
        self._range = None

    def select(self, *_a, **_k):
        self._op = "select"
        self._count = _k.get("count")
        return self

    def is_(self, f, val):
        if val == "null":
            self._is_null.append(f)
        return self

    def update(self, vals):
        self._op = "update"
        self._update_vals = dict(vals)
        return self

    def eq(self, f, v):
        self._filters.append((f, v))
        return self

    def in_(self, f, vals):
        self._in = (f, list(vals))
        return self

    def gte(self, f, soglia):
        self._gte.append((f, soglia))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def _matches(self, row):
        for f, v in self._filters:
            if row.get(f) != v:
                return False
        if self._in is not None:
            f, vals = self._in
            if row.get(f) not in vals:
                return False
        for f, soglia in self._gte:
            if str(row.get(f) or "") < soglia:
                return False
        for f in self._is_null:
            if row.get(f) is not None:
                return False
        return True

    def execute(self):
        rows = [r for r in self._store if self._matches(r)]
        if self._op == "update":
            for r in rows:
                r.update(self._update_vals)
            return _Result([dict(r) for r in rows])
        total = len(rows)
        out = [dict(r) for r in rows]
        if self._range is not None:
            start, end = self._range
            out = out[start:end + 1]
        if self._limit is not None:
            out = out[: self._limit]
        return _Result(out, count=(total if self._count else None))


class FakeClient:
    def __init__(self, tables, rpc_handlers=None):
        self._tables = {k: list(v) for k, v in tables.items()}
        self._rpc = rpc_handlers or {}
        self.rpc_calls = []

    def table(self, name):
        return _Query(self._tables.setdefault(name, []))

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        handler = self._rpc.get(name, lambda p: 0)
        return _RpcCall(handler(params))

    def dump(self, name):
        return self._tables.get(name, [])


# ─── A1: invoicetronic-salute ─────────────────────────────────────────────────

def test_salute_classifica_e_separa_orfane(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({
        "ristoranti": [
            {"id": "r1", "user_id": "u1", "nome_ristorante": "LAND", "partita_iva": "11111111111", "attivo": True},
            {"id": "r2", "user_id": "u2", "nome_ristorante": "TIME", "partita_iva": "22222222222", "attivo": True},
            {"id": "r3", "user_id": "u3", "nome_ristorante": "OFF-A", "partita_iva": "33333333333", "attivo": True},
            {"id": "r4", "user_id": "u3", "nome_ristorante": "OFF-B", "partita_iva": "33333333333", "attivo": True},
        ],
        "fatture_queue": [
            # u1 sano (done non è problematico, finisce nei "sani")
            {"id": 1, "user_id": "u1", "piva_raw": "11111111111", "status": "done", "created_at": "2026-06-10", "payload_meta": {}},
            # u2: unknown_tenant sulla sua P.IVA → critico
            {"id": 2, "user_id": None, "piva_raw": "22222222222", "status": "unknown_tenant", "created_at": "2026-06-11", "payload_meta": {"numero_fattura": "F2"}},
            # u3: multi-sede da_assegnare → warning
            {"id": 3, "user_id": "u3", "piva_raw": "33333333333", "status": "da_assegnare", "created_at": "2026-06-12", "payload_meta": {}},
            # orfana: P.IVA di nessun cliente
            {"id": 4, "user_id": None, "piva_raw": "99999999999", "status": "unknown_tenant", "created_at": "2026-06-13", "payload_meta": {"numero_fattura": "ORF"}},
        ],
    })
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    res = admin.admin_sistema_invoicetronic_salute(giorni=365)
    per_user = {it["user_id"]: it for it in res["items"]}

    assert per_user["u1"]["stato"] == "ok"
    assert per_user["u1"]["n_sani"] == 1
    assert per_user["u2"]["stato"] == "critico"
    assert per_user["u2"]["n_unknown"] == 1
    assert per_user["u3"]["stato"] == "warning"
    assert per_user["u3"]["n_da_assegnare"] == 1
    # u3 ha due sedi
    assert len(per_user["u3"]["sedi"]) == 2
    # la P.IVA sconosciuta a tutti finisce in orfane (non attribuita a un cliente)
    assert len(res["orfane"]) == 1
    assert res["orfane"][0]["piva_raw"] == "99999999999"
    assert res["counts"]["critico"] == 1
    assert res["counts"]["warning"] == 1
    assert res["counts"]["ok"] == 1


def test_salute_multisede_usa_nome_gruppo(monkeypatch):
    """Una catena (multi-sede) mostra in testata il nome del gruppo, non la sede."""
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({
        "ristoranti": [
            {"id": "r1", "user_id": "u1", "nome_ristorante": "SUSHI SAN GIULIANO", "partita_iva": "11111111111", "attivo": True},
            {"id": "r2", "user_id": "u1", "nome_ristorante": "SUSHI MARIANO", "partita_iva": "22222222222", "attivo": True},
            {"id": "r3", "user_id": "u2", "nome_ristorante": "TIME CAFE", "partita_iva": "33333333333", "attivo": True},
        ],
        "users": [
            {"id": "u1", "nome_gruppo": "SUSHILAND"},
            {"id": "u2", "nome_gruppo": None},
        ],
        "fatture_queue": [],
    })
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    res = admin.admin_sistema_invoicetronic_salute(giorni=365)
    per_user = {it["user_id"]: it for it in res["items"]}

    # catena → nome del gruppo
    assert per_user["u1"]["nome"] == "SUSHILAND"
    # singola sede → nome del ristorante (nessun gruppo)
    assert per_user["u2"]["nome"] == "TIME CAFE"


# ─── A2: assegna-piva ─────────────────────────────────────────────────────────

def test_assegna_piva_con_ristorante_sblocca_solo_unknown(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({
        "ristoranti": [{"id": "r1", "user_id": "u1", "attivo": True}],
        "fatture_queue": [
            {"id": 1, "piva_raw": "12345678901", "status": "unknown_tenant", "user_id": None, "ristorante_id": None},
            {"id": 2, "piva_raw": "12345678901", "status": "done", "user_id": "x", "ristorante_id": "y"},
        ],
    })
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    body = admin.AssegnaPivaBody(piva="12345678901", ristorante_id="r1")
    res = admin.admin_queue_assegna_piva(body, admin_user={"email": "md@oneflux.it"})
    assert res["sbloccate"] == 1
    rec = {r["id"]: r for r in sb.dump("fatture_queue")}
    assert rec[1]["status"] == "pending" and rec[1]["user_id"] == "u1"
    # il record 'done' non viene toccato
    assert rec[2]["status"] == "done"


def test_assegna_piva_senza_ristorante_usa_rpc(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({"fatture_queue": []}, rpc_handlers={"resolve_unknown_tenant": lambda p: 3})
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    body = admin.AssegnaPivaBody(piva="12345678901")
    res = admin.admin_queue_assegna_piva(body, admin_user={"email": "md@oneflux.it"})
    assert res["sbloccate"] == 3
    assert sb.rpc_calls == [("resolve_unknown_tenant", {"p_piva": "12345678901"})]


# ─── A3: riprova (guard di stato) ─────────────────────────────────────────────

def test_riprova_solo_failed_o_dead(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({"fatture_queue": [
        {"id": 1, "status": "dead"},
        {"id": 2, "status": "done"},
    ]})
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    res = admin.admin_queue_riprova(admin.RiprovaQueueBody(queue_id=1), admin_user={"email": "x"})
    assert res["ok"] is True
    assert sb.dump("fatture_queue")[0]["status"] == "pending"

    # 'done' non è riprovabile → 409
    with pytest.raises(HTTPException) as ei:
        admin.admin_queue_riprova(admin.RiprovaQueueBody(queue_id=2), admin_user={"email": "x"})
    assert ei.value.status_code == 409


# ─── A4: assegna-sede (guard + RPC) ───────────────────────────────────────────

def test_assegna_sede_solo_da_assegnare(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient(
        {"fatture_queue": [{"id": 1, "status": "da_assegnare"}]},
        rpc_handlers={"assegna_fattura_a_sede": lambda p: True},
    )
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    res = admin.admin_queue_assegna_sede(
        admin.AssegnaSedeQueueBody(queue_id=1, ristorante_id="r1"), admin_user={"email": "x"})
    assert res["ok"] is True
    assert sb.rpc_calls == [("assegna_fattura_a_sede", {"p_queue_id": 1, "p_ristorante_id": "r1"})]


def test_assegna_sede_record_inesistente_404(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({"fatture_queue": [{"id": 1, "status": "done"}]})
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    with pytest.raises(HTTPException) as ei:
        admin.admin_queue_assegna_sede(
            admin.AssegnaSedeQueueBody(queue_id=1, ristorante_id="r1"), admin_user={"email": "x"})
    assert ei.value.status_code == 404


def test_modulo_admin_importa_helper_flusso_dati():
    assert hasattr(admin, "admin_sistema_invoicetronic_salute")
    assert hasattr(admin, "admin_queue_assegna_piva")
    assert hasattr(admin, "admin_queue_riprova")
    assert hasattr(admin, "admin_queue_assegna_sede")
    assert hasattr(admin, "_classifica_salute_invoicetronic")


# ─── A5: badges home admin (conteggi leggeri) ─────────────────────────────────

def test_badges_conta_solo_problematici(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({
        "fatture_queue": [
            {"id": 1, "status": "unknown_tenant"},
            {"id": 2, "status": "da_assegnare"},
            {"id": 3, "status": "done"},        # sano → non contato
        ],
        "users": [
            {"id": "u1", "email": "cliente@test.it"},
            {"id": "adm", "email": "md@oneflux.it"},  # admin → escluso da allowed_ids
        ],
        # categorie = DESCRIZIONI uniche needs_review, escluse le scelte umane
        "fatture": [
            {"id": "a", "user_id": "u1", "descrizione": "GELATO X", "needs_review": True, "deleted_at": None},
            {"id": "a2", "user_id": "u1", "descrizione": "GELATO X", "needs_review": True, "deleted_at": None},  # stessa descr → 1 sola
            {"id": "d", "user_id": "u1", "descrizione": "TORTA Y", "needs_review": True, "deleted_at": None},
            {"id": "e", "user_id": "u1", "descrizione": "COUPON Z", "needs_review": True, "deleted_at": None},   # impronta umana → escluso
            {"id": "b", "user_id": "u1", "descrizione": "X", "needs_review": True, "deleted_at": "2026-01-01"},  # cestino → escluso
            {"id": "c", "user_id": "u1", "descrizione": "OK", "needs_review": False, "deleted_at": None},        # non review → escluso
        ],
        "prodotti_utente": [
            {"descrizione": "COUPON Z", "classificato_da": "Manuale (cliente)", "user_id": "u1"},
        ],
        "prodotti_master": [],
        "marketplace_leads": [
            {"id": "l1", "stato": "nuovo"},
            {"id": "l2", "stato": "gestito"},   # non nuovo → escluso
        ],
    })
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)

    res = admin.admin_badges()
    # categorie = {GELATO X, TORTA Y} = 2 (COUPON Z escluso perché scelta umana)
    assert res == {"flusso_dati": 2, "categorie": 2, "richieste": 1}


def test_badges_tutto_pulito_a_zero(monkeypatch):
    monkeypatch.setattr(admin, "_verify_admin", lambda **k: {"email": "md@oneflux.it"})
    sb = FakeClient({
        "fatture_queue": [], "fatture": [], "marketplace_leads": [],
        "users": [{"id": "u1", "email": "cliente@test.it"}],
        "prodotti_utente": [], "prodotti_master": [],
    })
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    assert admin.admin_badges() == {"flusso_dati": 0, "categorie": 0, "richieste": 0}
