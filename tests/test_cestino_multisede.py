"""Test guardia: soft-delete cestino e spostamento fattura per account multi-sede.

Contesto (audit 19/06): per i clienti con UNA P.IVA e PIÙ sedi (es. OFFSIDE/
OVERTIME) lo stesso `file_origine` può esistere su più ristoranti. Due bug
latenti:

  Bug A — elimina_fattura_soft (cestino.py) cercava la fattura per
    (user_id, file_origine) SENZA vincolare la sede attiva: con file_origine
    omonimo su due sedi poteva cestinare la fattura della sede SBAGLIATA. In più
    ritornava sempre `righe_eliminate: 1` hardcoded, anche con 0 righe toccate.

  Bug B — la RPC sposta_fattura_a_sede, spostando le righe verso un'altra sede
    che contiene già lo stesso file_origine, violava uq_fatture_dedup
    (user_id, ristorante_id, file_origine, numero_riga) → 500 opaco e potenziale
    spostamento parziale. Ora il router traduce l'errore dedicato in un 409 chiaro.

Questi test esercitano la logica REALE degli endpoint (fake client in-memory che
riproduce il chaining supabase-py), non una replica.
"""
import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.cestino as cestino
import services.routers.fatture as fatture
import pytest
from fastapi import HTTPException

from tests.test_flusso_dati_admin import FakeClient


def _bind_cestino(monkeypatch, sb, user_id, ristorante_id):
    """Mocka i wrapper lazy del router cestino verso un fake client + sede attiva."""
    monkeypatch.setattr(cestino, "_resolve_user_from_token", lambda *a, **k: {"id": user_id})
    monkeypatch.setattr(cestino, "_get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(cestino, "_resolve_ristorante_id", lambda *a, **k: ristorante_id)


# ─── Bug A: soft-delete vincolato alla sede attiva ────────────────────────────

def test_soft_delete_cestina_solo_la_sede_attiva(monkeypatch):
    """Stesso file_origine su due sedi: cestinare dalla sede r1 NON deve toccare r2."""
    sb = FakeClient({
        "fatture": [
            {"id": "a1", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": None},
            {"id": "a2", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 2, "deleted_at": None},
            {"id": "b1", "user_id": "u1", "ristorante_id": "r2", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": None},
        ],
    })
    _bind_cestino(monkeypatch, sb, "u1", "r1")

    res = cestino.elimina_fattura_soft(
        cestino.FatturaEliminaRequest(file_origine="F.xml"), authorization="Bearer x"
    )

    assert res["success"] is True
    assert res["righe_eliminate"] == 2  # solo le 2 righe di r1, non 3
    by_id = {r["id"]: r for r in sb.dump("fatture")}
    assert by_id["a1"]["deleted_at"] is not None
    assert by_id["a2"]["deleted_at"] is not None
    # La fattura della sede r2 NON è stata toccata
    assert by_id["b1"]["deleted_at"] is None


def test_soft_delete_404_se_file_non_in_sede_attiva(monkeypatch):
    """Il file esiste, ma su un'altra sede: dalla sede attiva è un 404, non un
    cestinamento della sede sbagliata."""
    sb = FakeClient({
        "fatture": [
            {"id": "b1", "user_id": "u1", "ristorante_id": "r2", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": None},
        ],
    })
    _bind_cestino(monkeypatch, sb, "u1", "r1")  # sede attiva r1, file solo su r2

    with pytest.raises(HTTPException) as ei:
        cestino.elimina_fattura_soft(
            cestino.FatturaEliminaRequest(file_origine="F.xml"), authorization="Bearer x"
        )
    assert ei.value.status_code == 404
    # La fattura su r2 resta intatta
    assert sb.dump("fatture")[0]["deleted_at"] is None


def test_soft_delete_409_se_gia_nel_cestino(monkeypatch):
    sb = FakeClient({
        "fatture": [
            {"id": "a1", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": "2026-06-01"},
        ],
    })
    _bind_cestino(monkeypatch, sb, "u1", "r1")

    with pytest.raises(HTTPException) as ei:
        cestino.elimina_fattura_soft(
            cestino.FatturaEliminaRequest(file_origine="F.xml"), authorization="Bearer x"
        )
    assert ei.value.status_code == 409


def test_soft_delete_conta_le_righe_reali(monkeypatch):
    """Una fattura con 3 righe deve riportare righe_eliminate=3, non 1 hardcoded."""
    sb = FakeClient({
        "fatture": [
            {"id": "a1", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": None},
            {"id": "a2", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 2, "deleted_at": None},
            {"id": "a3", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 3, "deleted_at": None},
        ],
    })
    _bind_cestino(monkeypatch, sb, "u1", "r1")

    res = cestino.elimina_fattura_soft(
        cestino.FatturaEliminaRequest(file_origine="F.xml"), authorization="Bearer x"
    )
    assert res["righe_eliminate"] == 3


# ─── Bug B: spostamento — collisione tradotta in 409 leggibile ────────────────

def test_sposta_collisione_diventa_409(monkeypatch):
    """Se la RPC segnala collisione_file_in_sede_destinazione, l'endpoint risponde
    409 con messaggio chiaro, non 400/500 opaco."""
    def _rpc_collisione(_params):
        raise Exception('... collisione_file_in_sede_destinazione ...')

    sb = FakeClient(
        {
            "fatture": [
                {"id": "a1", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": None},
            ],
        },
        rpc_handlers={"sposta_fattura_a_sede": _rpc_collisione},
    )
    monkeypatch.setattr(fatture, "_resolve_user_from_token", lambda *a, **k: {"id": "u1"})
    monkeypatch.setattr(fatture, "_get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(fatture, "_invalidate_fatture_rows_cache", lambda *a, **k: None)

    with pytest.raises(HTTPException) as ei:
        fatture.fatture_sposta_sede(
            fatture.SpostaSedeBody(file_origine="F.xml", ristorante_id="r2"),
            authorization="Bearer x",
        )
    assert ei.value.status_code == 409
    assert "destinazione" in ei.value.detail.lower()


def test_sposta_ok_ritorna_righe_spostate(monkeypatch):
    sb = FakeClient(
        {
            "fatture": [
                {"id": "a1", "user_id": "u1", "ristorante_id": "r1", "file_origine": "F.xml", "numero_riga": 1, "deleted_at": None},
            ],
        },
        rpc_handlers={"sposta_fattura_a_sede": lambda p: 1},
    )
    monkeypatch.setattr(fatture, "_resolve_user_from_token", lambda *a, **k: {"id": "u1"})
    monkeypatch.setattr(fatture, "_get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(fatture, "_invalidate_fatture_rows_cache", lambda *a, **k: None)

    res = fatture.fatture_sposta_sede(
        fatture.SpostaSedeBody(file_origine="F.xml", ristorante_id="r2"),
        authorization="Bearer x",
    )
    assert res["ok"] is True
    assert res["righe_spostate"] == 1
