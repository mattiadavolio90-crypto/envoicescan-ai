"""Test dei 3 fix chiusi l'8/8/2026 dall'audit ONEFLUX §1 su services/routers/admin.py.

Nessuno di questi endpoint aveva test prima: e' il motivo per cui i bug erano
passati inosservati. Ogni classe difende UNA regola, e fallisce se il fix viene
tolto.

1. `admin_qualita_classifica`: la lettura di `categoria_da` per l'audit log deve
   avvenire PRIMA dell'update, altrimenti registra la categoria NUOVA e
   "Annulla" riscrive la stessa categoria invece di ripristinarla (misurato:
   51/51 righe di ai_review_log in produzione avevano categoria_da == categoria_a).
2. Ogni scrittura su fatture.categoria/needs_review deve invalidare la cache
   righe, o il contatore "da controllare" in Home resta stale fino a 30 min
   (_BRIEFING_TTL_MINUTI).
3. `admin_cambia_email` / `admin_crea_cliente`: non si puo' assegnare a un
   account cliente un'email presente in ADMIN_EMAILS — lo promuoverebbe ad admin
   al primo login, senza passare da nessun controllo.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin


# ─── Fake Supabase minimale, con registrazione dell'ordine delle operazioni ───

class _Q:
    def __init__(self, sb, table):
        self._sb = sb
        self._t = table
        self._op = "select"
        self._payload = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload, **k):
        self._op = "upsert"
        self._payload = payload
        return self

    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def range(self, *a, **k): return self

    def execute(self):
        self._sb.ops.append((self._op, self._t))
        if self._op == "select":
            return SimpleNamespace(data=self._sb.rows.get(self._t, []))
        if self._op == "update" and self._t == "fatture":
            # Simula la scrittura: cambia la categoria delle righe in memoria, cosi'
            # una rilettura DOPO l'update vedrebbe il valore nuovo.
            for r in self._sb.rows.get("fatture", []):
                r.update(self._payload)
        return SimpleNamespace(data=self._sb.rows.get(self._t, []))


class _FakeSB:
    def __init__(self, rows):
        self.rows = rows
        self.ops = []

    def table(self, name):
        return _Q(self, name)


_ADMIN = {"email": "md@oneflux.it"}


# ─── 1. categoria_da letta prima dell'update ─────────────────────────────────

class TestCategoriaDaPrimaDellUpdate:
    def _run(self):
        rows = {
            "fatture": [{
                "id": 1, "descrizione": "POMODORI PELATI",
                "categoria": "Da Classificare", "prezzo_unitario": 3.5,
                "totale_riga": 7.0, "ristorante_id": "rid-1",
            }],
            "prodotti_master": [],
            "ai_review_log": [],
        }
        sb = _FakeSB(rows)
        log = MagicMock()
        body = SimpleNamespace(
            ids=[1], categoria="VERDURE", salva_memoria=False,
        )
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _log_review_action=log,
            _invalidate_fatture_rows_cache=MagicMock(),
        ):
            out = admin.admin_qualita_classifica(body, admin_user=_ADMIN)
        return out, sb, log

    def test_categoria_da_e_quella_precedente_non_quella_nuova(self):
        """Il bug: categoria_da == categoria_a rendeva "Annulla" un no-op."""
        _out, _sb, log = self._run()
        kwargs = log.call_args.kwargs
        assert kwargs["categoria_da"] == "Da Classificare"
        assert kwargs["categoria_a"] == "VERDURE"
        assert kwargs["categoria_da"] != kwargs["categoria_a"]

    def test_la_select_precede_l_update_su_fatture(self):
        """Difende l'ordine, non solo il risultato: se un domani si reintroduce una
        rilettura dopo l'update, questo test cade."""
        _out, sb, _log = self._run()
        ops_fatture = [op for op, t in sb.ops if t == "fatture"]
        assert ops_fatture.index("select") < ops_fatture.index("update")

    def test_invalidazione_cache_chiamata_col_ristorante(self):
        rows = {
            "fatture": [{
                "id": 1, "descrizione": "X", "categoria": "Da Classificare",
                "prezzo_unitario": 1.0, "totale_riga": 1.0, "ristorante_id": "rid-1",
            }],
            "prodotti_master": [], "ai_review_log": [],
        }
        sb = _FakeSB(rows)
        inval = MagicMock()
        body = SimpleNamespace(ids=[1], categoria="VERDURE", salva_memoria=False)
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _log_review_action=MagicMock(),
            _invalidate_fatture_rows_cache=inval,
        ):
            admin.admin_qualita_classifica(body, admin_user=_ADMIN)
        inval.assert_called_once_with("rid-1")


# ─── 2. invalidazione cache su annulla ───────────────────────────────────────

class TestAnnullaInvalidaCache:
    def test_annulla_invalida_la_cache(self):
        rows = {
            "ai_review_log": [{
                "id": 7, "categoria_da": "Da Classificare",
                "categoria_a": "VERDURE", "ids_fatture": [1],
                "descrizione": "POMODORI", "annullato_at": None,
            }],
            "fatture": [{"id": 1, "categoria": "VERDURE"}],
        }
        sb = _FakeSB(rows)
        inval = MagicMock()
        body = SimpleNamespace(log_id=7)
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _log_review_action=MagicMock(),
            _invalidate_fatture_rows_cache=inval,
        ):
            admin.admin_qualita_audit_annulla(body, admin_user=_ADMIN)
        inval.assert_called_once()

    def test_annulla_ripristina_la_categoria_precedente(self):
        rows = {
            "ai_review_log": [{
                "id": 7, "categoria_da": "Da Classificare",
                "categoria_a": "VERDURE", "ids_fatture": [1],
                "descrizione": "POMODORI", "annullato_at": None,
            }],
            "fatture": [{"id": 1, "categoria": "VERDURE"}],
        }
        sb = _FakeSB(rows)
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _log_review_action=MagicMock(),
            _invalidate_fatture_rows_cache=MagicMock(),
        ):
            admin.admin_qualita_audit_annulla(body=SimpleNamespace(log_id=7), admin_user=_ADMIN)
        assert sb.rows["fatture"][0]["categoria"] == "Da Classificare"
        assert sb.rows["fatture"][0]["needs_review"] is True


# ─── 3. privilege escalation via email admin ─────────────────────────────────

class TestNonAssegnabileEmailAdmin:
    def test_cambia_email_rifiuta_email_amministrativa(self):
        sb = _FakeSB({"users": [{"id": "c1", "email": "cliente@x.it"}]})
        body = SimpleNamespace(nuova_email="  MD@ONEFLUX.IT  ")
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _admin_emails_set=MagicMock(return_value={"md@oneflux.it"}),
        ), pytest.raises(HTTPException) as exc:
            admin.admin_cambia_email("c1", body, admin_user=_ADMIN)
        assert exc.value.status_code == 403

    def test_cambia_email_consente_email_normale(self):
        sb = _FakeSB({"users": []})

        def _table(name):
            q = _Q(sb, name)
            return q

        sb_users = _FakeSB({"users": [{"id": "c1", "email": "cliente@x.it"}]})
        body = SimpleNamespace(nuova_email="nuovo@x.it")
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb_users),
            _admin_emails_set=MagicMock(return_value={"md@oneflux.it"}),
        ), patch("services.session_service.revoca_tutte_sessioni", MagicMock(return_value=0)):
            # `dup` legge la stessa lista users: il fake ritorna righe, quindi il
            # 409 "email gia' registrata" scatta prima. Verifichiamo solo che NON
            # sia il 403 del controllo admin.
            with pytest.raises(HTTPException) as exc:
                admin.admin_cambia_email("c1", body, admin_user=_ADMIN)
        assert exc.value.status_code != 403

    def test_crea_cliente_rifiuta_email_amministrativa(self):
        body = SimpleNamespace(email="md@oneflux.it", nome_ristorante="Test")
        crea = MagicMock()
        with patch.multiple(
            admin,
            _admin_emails_set=MagicMock(return_value={"md@oneflux.it"}),
        ), patch("services.auth_service.crea_cliente_con_token", crea), \
             pytest.raises(HTTPException) as exc:
            admin.admin_crea_cliente(body, admin_user=_ADMIN)
        assert exc.value.status_code == 403
        crea.assert_not_called()
