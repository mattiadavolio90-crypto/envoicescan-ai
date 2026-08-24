"""Guardie sugli endpoint del router tag (audit §3b, 24/8/2026).

Prima di questa sessione NESSUN test esercitava services/routers/tag.py:
lo strato router era a copertura zero sugli endpoint. Le funzioni sono
chiamate direttamente (non via TestClient) perche' importare fastapi_worker
per intero non serve a provare la logica fixata.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import services.routers.tag as rt


class _Q:
    def __init__(self, rows, log):
        self._rows = list(rows)
        self._log = log

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._log.append((col, str(val)))
        self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _Sb:
    def __init__(self, tabelle):
        self.tabelle = tabelle
        self.filtri = []

    def table(self, nome):
        return _Q(self.tabelle.get(nome, []), self.filtri)


# assoc 221 -> sede B (SUSHILAND), assoc 79 -> sede A (LAND DEI SAPORI).
# Stesso user_id: e' la situazione reale misurata sul DB.
_ASSOC = [
    {"id": 79, "user_id": "u1", "ristorante_id": "sedeA"},
    {"id": 221, "user_id": "u1", "ristorante_id": "sedeB"},
]


@pytest.fixture
def patch_ctx(monkeypatch):
    def _apply(sb, ristorante_id="sedeA"):
        monkeypatch.setattr(rt, "_resolve_user_from_token", lambda *_a, **_k: {"id": "u1"})
        monkeypatch.setattr(rt, "_get_supabase_client", lambda *_a, **_k: sb)
        monkeypatch.setattr(rt, "_resolve_ristorante_id", lambda *_a, **_k: ristorante_id)
    return _apply


def test_remove_assoc_di_altra_sede_e_rifiutata(patch_ctx, monkeypatch):
    """Pre-fix l'endpoint non risolveva nemmeno ristorante_id: rimuovi_associazione
    filtra solo user_id, quindi un id dell'altra sede veniva cancellato."""
    cancellate = []
    monkeypatch.setattr(
        "services.db_service.rimuovi_associazione",
        lambda aid, uid: cancellate.append((aid, uid)),
    )
    sb = _Sb({"custom_tag_prodotti": _ASSOC})
    patch_ctx(sb, ristorante_id="sedeA")

    with pytest.raises(HTTPException) as exc:
        rt.remove_tag_prodotto(221, authorization="Bearer x")   # assoc della sede B

    assert exc.value.status_code == 404
    assert cancellate == [], "nessuna cancellazione deve partire"
    assert ("ristorante_id", "sedeA") in sb.filtri, "la sede deve essere filtrata"


def test_remove_assoc_della_propria_sede_funziona(patch_ctx, monkeypatch):
    cancellate = []
    monkeypatch.setattr(
        "services.db_service.rimuovi_associazione",
        lambda aid, uid: cancellate.append((aid, uid)),
    )
    sb = _Sb({"custom_tag_prodotti": _ASSOC})
    patch_ctx(sb, ristorante_id="sedeA")

    out = rt.remove_tag_prodotto(79, authorization="Bearer x")

    assert out == {"ok": True}
    assert cancellate == [(79, "u1")]


def test_refresh_fallito_lo_dice_al_client(patch_ctx, monkeypatch):
    """Pre-fix: pipeline fallita -> HTTP 200 con la lista VECCHIA, che il cliente
    legge come 'nessun suggerimento nuovo'."""
    sb = _Sb({})
    patch_ctx(sb)
    monkeypatch.setattr(
        "services.tag_suggestion_service.run_tag_suggestion_pipeline",
        lambda **_k: {"success": False, "error": "boom"},
    )
    monkeypatch.setattr(
        "services.tag_suggestion_service.list_pending_tag_suggestions",
        lambda **_k: [{"id": 1}],
    )

    out = rt.list_tag_suggestions(refresh=True, authorization="Bearer x")

    assert out["refresh_ok"] is False
    assert out["suggestions"] == [{"id": 1}]
    # l'errore interno non viene propagato al client
    assert "boom" not in str(out)


def test_refresh_riuscito_segnala_ok(patch_ctx, monkeypatch):
    sb = _Sb({})
    patch_ctx(sb)
    monkeypatch.setattr(
        "services.tag_suggestion_service.run_tag_suggestion_pipeline",
        lambda **_k: {"success": True, "total_suggestions": 3},
    )
    monkeypatch.setattr(
        "services.tag_suggestion_service.list_pending_tag_suggestions",
        lambda **_k: [{"id": 1}],
    )

    out = rt.list_tag_suggestions(refresh=True, authorization="Bearer x")
    assert out["refresh_ok"] is True


def test_senza_refresh_nessun_campo_aggiunto(patch_ctx, monkeypatch):
    """Il contratto della GET semplice non cambia: niente refresh_ok se non richiesto."""
    sb = _Sb({})
    patch_ctx(sb)
    monkeypatch.setattr(
        "services.tag_suggestion_service.run_tag_suggestion_pipeline",
        lambda **_k: pytest.fail("la pipeline non deve girare senza refresh"),
    )
    monkeypatch.setattr(
        "services.tag_suggestion_service.list_pending_tag_suggestions",
        lambda **_k: [],
    )

    out = rt.list_tag_suggestions(refresh=False, authorization="Bearer x")
    assert out == {"suggestions": []}
