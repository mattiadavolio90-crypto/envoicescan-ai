"""Boost AI (fase J, 10/10/2026): Mattia attiva a mano la ricarica dall'Admin.

Le rotte `/api/admin/clienti/{id}/ricariche-ai`: leggono le ricariche e il
residuo (dalla stessa RPC della chat) e ne aggiungono una da 300 crediti. Che
la ricarica si spenda davvero dopo il mese e' provato su Postgres in
`tests/test_sql_chat_crediti.py`.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.routers import admin

CLIENTE = "11111111-1111-4111-8111-111111111111"
ADMIN = {"id": "a-1", "email": "mattia@oneflux.it"}


class _Tab:
    def __init__(self, db, nome):
        self.db, self.nome, self.filtri = db, nome, []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append((col, val))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def insert(self, riga):
        self.db.inseriti.append((self.nome, riga))
        return self

    def execute(self):
        # Come Postgres: un id che non e' un uuid e' un errore (22P02), non zero righe.
        import uuid as _uuid
        for col, val in self.filtri:
            if col in ("id", "user_id"):
                _uuid.UUID(str(val))
        righe = [r for r in self.db.righe.get(self.nome, []) if all(r.get(c) == v for c, v in self.filtri)]
        return MagicMock(data=righe)


class _DB:
    def __init__(self, righe):
        self.righe, self.inseriti = righe, []

    def table(self, nome):
        return _Tab(self, nome)


def _db(con_cliente=True):
    return _DB({
        "users": [{"id": CLIENTE}] if con_cliente else [],
        "chat_ricariche": [
            {"id": "r1", "user_id": CLIENTE, "crediti": 300, "nota": None, "creata_da": "m", "created_at": "2026-10-01T09:00:00Z"},
            {"id": "r2", "user_id": "22222222-2222-4222-8222-222222222222", "crediti": 900, "nota": None, "creata_da": "m", "created_at": "2026-10-02T09:00:00Z"},
        ],
    })


@pytest.fixture
def stato(monkeypatch):
    chiamate = []

    def finto(user_id, sede, pool, sb, solleva=False):
        chiamate.append((user_id, sede, pool, solleva))
        return {"oggi": 0, "mese": 0, "ricarica": 150}

    monkeypatch.setattr(admin, "_chat_crediti_stato", finto)
    return chiamate


def test_la_lettura_porta_le_ricariche_del_cliente_e_il_residuo(monkeypatch, stato):
    db = _db()
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    out = admin.admin_ricariche_ai(CLIENTE)
    assert [r["id"] for r in out["ricariche"]] == ["r1"], "le ricariche di un altro cliente non si vedono"
    assert out["residuo"] == 150 and out["crediti_boost"] == 300
    # il residuo e' quello dell'account intero, come lo spende la chat
    # e una lettura fallita deve essere un errore, non uno zero
    assert stato == [(CLIENTE, None, True, True)]


def test_cliente_inesistente_404(monkeypatch, stato):
    from fastapi import HTTPException
    monkeypatch.setattr(admin, "get_supabase_client", lambda: _db(con_cliente=False))
    with pytest.raises(HTTPException) as ei:
        admin.admin_ricariche_ai(CLIENTE)
    assert ei.value.status_code == 404
    db = _db(con_cliente=False)
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    with pytest.raises(HTTPException):
        admin.admin_aggiungi_ricarica_ai(CLIENTE, admin.RicaricaAiBody(), admin_user=ADMIN)
    assert db.inseriti == [], "una ricarica per un cliente che non c'e' non si scrive"


def test_l_aggiunta_scrive_300_crediti_con_chi_l_ha_fatta(monkeypatch, stato):
    db = _db()
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    out = admin.admin_aggiungi_ricarica_ai(CLIENTE, admin.RicaricaAiBody(nota="  bonifico 10/10 "), admin_user=ADMIN)
    assert db.inseriti == [("chat_ricariche", {
        "user_id": CLIENTE, "crediti": 300, "nota": "bonifico 10/10", "creata_da": "mattia@oneflux.it",
    })]
    assert out["residuo"] == 150


def test_nota_vuota_resta_null(monkeypatch, stato):
    db = _db()
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    admin.admin_aggiungi_ricarica_ai(CLIENTE, admin.RicaricaAiBody(nota="   "), admin_user=ADMIN)
    assert db.inseriti[0][1]["nota"] is None


@pytest.mark.parametrize("crediti", [0, -300, 3001, 30000])
def test_crediti_fuori_misura_rifiutati(crediti):
    with pytest.raises(ValidationError):
        admin.RicaricaAiBody(crediti=crediti)


def test_il_default_e_il_boost():
    assert admin.RicaricaAiBody().crediti == admin.RICARICA_AI_CREDITI == 300


def _dipendenze(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dipendenze(d)


@pytest.mark.parametrize("metodo", ["GET", "POST"])
def test_ogni_rotta_delle_ricariche_passa_dalla_verifica_admin(metodo):
    """La chiave del worker sola non basta: senza `_verify_admin` un cliente
    qualunque, passando dal proxy, leggerebbe o regalerebbe ricariche."""
    from services.fastapi_worker import app
    rotte = [
        r for r in app.routes
        if getattr(r, "path", "") == "/api/admin/clienti/{cliente_id}/ricariche-ai" and metodo in r.methods
    ]
    assert len(rotte) == 1
    assert admin._verify_admin in set(_dipendenze(rotte[0].dependant))


def test_le_rotte_chiedono_l_admin():
    """Senza sessione admin: 401, mai una scrittura."""
    from services.fastapi_worker import app
    client = TestClient(app)
    url = f"/api/admin/clienti/{CLIENTE}/ricariche-ai"
    for r in (client.get(url), client.post(url, json={})):
        assert r.status_code in (401, 403), r.status_code


def test_i_300_crediti_sono_gli_stessi_del_servizio_e_del_banner():
    """Il numero vive in tre posti: la rotta, la card del servizio e il banner."""
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "lib"
    n = f"{admin.RICARICA_AI_CREDITI} crediti"
    assert n in (web / "assistenza.ts").read_text(encoding="utf-8")
    assert n in (web / "trigger-servizi.ts").read_text(encoding="utf-8")


def test_crediti_illeggibili_sono_un_errore_non_uno_zero(monkeypatch):
    """Con uno zero a schermo Mattia aggiungerebbe una seconda ricarica a chi ne
    ha gia' una da spendere."""
    from fastapi import HTTPException
    sb = _db()
    sb.rpc = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rete"))
    monkeypatch.setattr(admin, "get_supabase_client", lambda: sb)
    with pytest.raises(HTTPException) as ei:
        admin.admin_ricariche_ai(CLIENTE)
    assert ei.value.status_code == 503


def test_id_non_uuid_e_un_404(monkeypatch, stato):
    from fastapi import HTTPException
    monkeypatch.setattr(admin, "get_supabase_client", lambda: _db())
    with pytest.raises(HTTPException) as ei:
        admin.admin_ricariche_ai("non-un-uuid")
    assert ei.value.status_code == 404


def test_lo_stato_solleva_solo_se_chiesto():
    import services.fastapi_worker as fw
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value = MagicMock(data=None)
    assert fw._chat_crediti_stato("u", None, True, sb) == {"oggi": 0, "mese": 0, "ricarica": 0}
    with pytest.raises(RuntimeError):
        fw._chat_crediti_stato("u", None, True, sb, solleva=True)


def test_ricarica_scritta_e_rilettura_fallita_non_dice_riprova(monkeypatch):
    """La ricarica e' gia' nel DB: un 503 «riprova» farebbe registrare la
    seconda al clic successivo. Si conferma, col residuo non leggibile."""
    db = _db()
    db.rpc = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rete"))
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    out = admin.admin_aggiungi_ricarica_ai(CLIENTE, admin.RicaricaAiBody(), admin_user=ADMIN)
    assert len(db.inseriti) == 1
    assert out == {"ricariche": [], "residuo": None, "crediti_boost": 300}
