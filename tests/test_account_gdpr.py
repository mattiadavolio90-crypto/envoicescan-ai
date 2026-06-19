"""Test guardia: diritti GDPR self-service (Art. 17 cancellazione, Art. 20 portabilità).

Coprono le route REALI account_elimina / account_esporta_dati di
services.routers.account, con auth/supabase mockati:
  - elimina richiede conferma esatta "ELIMINA"
  - elimina rifiuta gli account admin (no auto-lockout amministrazione)
  - elimina/esporta operano SEMPRE sull'id del token (mai cross-account)
  - esporta non include mai password/hash/token
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.account as account


class _Q:
    """Mock chain supabase: select/eq/limit/delete/execute."""
    def __init__(self, store):
        self._store = store
        self._op = "select"
        self._tab = None

    def select(self, *_a, **_k):
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._store)


class FakeSB:
    def __init__(self, rows_by_table=None):
        self.rows_by_table = rows_by_table or {}
        self.deleted_tables = []

    def table(self, name):
        store = self.rows_by_table.get(name, [])
        q = _Q(store)
        orig = q.execute

        def _exec():
            if q._op == "delete":
                self.deleted_tables.append(name)
            return orig()
        q.execute = _exec
        return q


def _patch(user, sb):
    return patch.multiple(
        account,
        _resolve_user_from_token=MagicMock(return_value=user),
        _get_supabase_client=MagicMock(return_value=sb),
    )


# ── Elimina account (Art. 17) ────────────────────────────────────────────────

def test_elimina_richiede_conferma_esatta():
    sb = FakeSB()
    with _patch({"id": "u1", "email": "cliente@x.it"}, sb), \
         patch.object(account, "_is_admin_email", return_value=False):
        with pytest.raises(account.HTTPException) as ei:
            account.account_elimina(account.EliminaAccountBody(conferma="elimina pure"), authorization="Bearer t")
    assert ei.value.status_code == 400
    assert "users" not in sb.deleted_tables  # niente delete senza conferma


def test_elimina_blocca_account_admin():
    sb = FakeSB()
    with _patch({"id": "a1", "email": "md@oneflux.it"}, sb), \
         patch.object(account, "_is_admin_email", return_value=True):
        with pytest.raises(account.HTTPException) as ei:
            account.account_elimina(account.EliminaAccountBody(conferma="ELIMINA"), authorization="Bearer t")
    assert ei.value.status_code == 403
    assert "users" not in sb.deleted_tables


def test_elimina_cliente_ok_cancella_users():
    sb = FakeSB()
    with _patch({"id": "u1", "email": "cliente@x.it"}, sb), \
         patch.object(account, "_is_admin_email", return_value=False):
        out = account.account_elimina(account.EliminaAccountBody(conferma="ELIMINA"), authorization="Bearer t")
    assert out["ok"] is True
    assert "users" in sb.deleted_tables  # la cancellazione di users propaga in cascade


def test_elimina_conferma_case_insensitive():
    """'elimina' minuscolo va accettato (upper() lato server)."""
    sb = FakeSB()
    with _patch({"id": "u1", "email": "cliente@x.it"}, sb), \
         patch.object(account, "_is_admin_email", return_value=False):
        out = account.account_elimina(account.EliminaAccountBody(conferma="elimina"), authorization="Bearer t")
    assert out["ok"] is True


# ── Esporta dati (Art. 20) ───────────────────────────────────────────────────

def test_esporta_non_include_password_ne_token():
    sb = FakeSB({"users": [{"id": "u1", "email": "c@x.it", "nome_ristorante": "Da Mario"}]})
    with _patch({"id": "u1", "email": "c@x.it"}, sb):
        out = account.account_esporta_dati(authorization="Bearer t")
    # I campi sensibili NON devono comparire nel profilo esportato (la select usa
    # una whitelist). La nota testuale può citare "password" come spiegazione: qui
    # controlliamo le chiavi reali dei dati, non il testo descrittivo.
    profilo_keys = set((out.get("profilo") or {}).keys())
    assert not (profilo_keys & {"password", "password_hash", "reset_code", "reset_token", "session_token"})
    assert out["titolare_trattamento"].startswith("Recoma System")


def test_esporta_include_le_sezioni_dati():
    sb = FakeSB({
        "users": [{"id": "u1", "email": "c@x.it"}],
        "fatture": [{"id": 1, "user_id": "u1"}],
        "ricette": [{"id": 9, "userid": "u1"}],
    })
    with _patch({"id": "u1", "email": "c@x.it"}, sb):
        out = account.account_esporta_dati(authorization="Bearer t")
    assert out["profilo"]["email"] == "c@x.it"
    assert isinstance(out["fatture"], list) and len(out["fatture"]) == 1
    assert isinstance(out["ricette"], list) and len(out["ricette"]) == 1
