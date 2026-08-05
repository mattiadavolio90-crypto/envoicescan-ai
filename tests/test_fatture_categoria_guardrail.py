"""Test dei guardrail categoria su PATCH /api/fatture/{riga_id}/categoria e
POST /api/fatture/categoria-batch (services/routers/fatture.py).

Guardia contro la regressione HIGH trovata nell'audit §1 2026-08-05: la
whitelist ammetteva sia "📝 NOTE E DICITURE" che la variante senza emoji
"NOTE E DICITURE", ma il constraint DB (fatture_note_diciture_solo_importo_zero_chk)
confronta solo la stringa CON emoji — quindi la variante senza emoji scavalcava
la regola di dominio #2 (NOTE E DICITURE solo su totale_riga==0) e un costo
reale poteva sparire dal MOL senza errore. Fix: normalizzazione + guardrail
applicativo replicato da admin.py:967-976.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.fatture as fatture


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table
        self._filters = {}
        self._select_cols = None
        self._in_ids = None
        self._update_payload = None

    def select(self, cols=None, *a, **k):
        self._select_cols = cols
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def is_(self, *a, **k): return self

    def in_(self, col, ids):
        self._in_ids = list(ids)
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def execute(self):
        if self._update_payload is not None:
            # stato FINALE della catena: eq()/in_() sono già stati applicati.
            self._c.updates.setdefault(self._t, []).append(dict(
                payload=self._update_payload, filters=dict(self._filters), in_ids=self._in_ids,
            ))
            target = self._in_ids if self._in_ids is not None else [r["id"] for r in self._c.rows]
            return SimpleNamespace(data=[{"id": i} for i in target])
        if self._t == "fatture" and self._select_cols:
            rows = self._c.rows
            if self._in_ids is not None:
                rows = [r for r in rows if r["id"] in self._in_ids]
            return SimpleNamespace(data=rows)
        if self._t == "prodotti_utente":
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, rows):
        self.rows = rows
        self.updates = {}

    def table(self, name):
        return _Query(self, name)


_RISTORANTE_ID = "sede-1"


def _patch_common(sb):
    mock_invalida = MagicMock(return_value=None)
    p = patch.multiple(
        fatture,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _resolve_ristorante_id=MagicMock(return_value=_RISTORANTE_ID),
        _invalidate_fatture_rows_cache=mock_invalida,
    )
    return p, mock_invalida


# ─── PATCH singola riga ────────────────────────────────────────────────────

def test_patch_categoria_normalizza_note_senza_emoji_e_richiede_importo_zero():
    sb = _FakeSB([{"id": 1, "totale_riga": 15.0, "prezzo_unitario": 15.0}])
    p, _ = _patch_common(sb)
    with p:
        with pytest.raises(HTTPException) as exc:
            fatture.aggiorna_categoria_riga(
                1, fatture.AggiornaCategoriaRequest(categoria="NOTE E DICITURE"),
                authorization="Bearer x",
            )
    assert exc.value.status_code == 422


def test_patch_categoria_note_senza_emoji_passa_su_importo_zero():
    sb = _FakeSB([{"id": 1, "totale_riga": 0.0, "prezzo_unitario": 0.0}])
    p, mock_invalida = _patch_common(sb)
    with p:
        out = fatture.aggiorna_categoria_riga(
            1, fatture.AggiornaCategoriaRequest(categoria="NOTE E DICITURE"),
            authorization="Bearer x",
        )
    assert out["categoria"] == "📝 NOTE E DICITURE"  # normalizzata
    upd = sb.updates["fatture"][0]
    assert upd["payload"]["categoria"] == "📝 NOTE E DICITURE"
    mock_invalida.assert_called_once_with(_RISTORANTE_ID)


def test_patch_categoria_normale_non_richiede_guardrail():
    sb = _FakeSB([{"id": 1, "totale_riga": 42.0, "prezzo_unitario": 42.0}])
    p, _ = _patch_common(sb)
    with p:
        out = fatture.aggiorna_categoria_riga(
            1, fatture.AggiornaCategoriaRequest(categoria="CARNE"),
            authorization="Bearer x",
        )
    assert out["categoria"] == "CARNE"


# ─── categoria-batch ────────────────────────────────────────────────────────

def test_batch_note_senza_emoji_restringe_alle_righe_importo_zero():
    sb = _FakeSB([
        {"id": 1, "totale_riga": 0.0, "prezzo_unitario": 0.0},
        {"id": 2, "totale_riga": 30.0, "prezzo_unitario": 30.0},
    ])
    p, _ = _patch_common(sb)
    with p:
        out = fatture.categoria_batch(
            fatture.CategoriaBatchRequest(nuova_categoria="NOTE E DICITURE", descrizione="COMMISSIONI BANCARIE"),
            authorization="Bearer x",
        )
    assert out["righe_aggiornate"] == 1
    upd = sb.updates["fatture"][-1]
    assert upd["payload"]["categoria"] == "📝 NOTE E DICITURE"
    assert upd["in_ids"] == [1]  # solo la riga a importo zero, MAI la riga da 30€
    # il filtro ristorante_id resta comunque presente sull'update finale (isolamento tenant)
    assert upd["filters"].get("ristorante_id") == _RISTORANTE_ID


def test_batch_note_rifiutata_se_nessuna_riga_a_importo_zero():
    sb = _FakeSB([{"id": 2, "totale_riga": 30.0, "prezzo_unitario": 30.0}])
    p, _ = _patch_common(sb)
    with p:
        with pytest.raises(HTTPException) as exc:
            fatture.categoria_batch(
                fatture.CategoriaBatchRequest(nuova_categoria="📝 NOTE E DICITURE", descrizione="COMMISSIONI BANCARIE"),
                authorization="Bearer x",
            )
    assert exc.value.status_code == 422


def test_batch_rispetta_riga_ids_nel_guardrail():
    sb = _FakeSB([
        {"id": 1, "totale_riga": 0.0, "prezzo_unitario": 0.0},
        {"id": 2, "totale_riga": 0.0, "prezzo_unitario": 0.0},
    ])
    p, _ = _patch_common(sb)
    with p:
        out = fatture.categoria_batch(
            fatture.CategoriaBatchRequest(
                nuova_categoria="📝 NOTE E DICITURE", descrizione="COMMISSIONI BANCARIE", riga_ids=[1],
            ),
            authorization="Bearer x",
        )
    upd = sb.updates["fatture"][-1]
    # anche se la riga 2 sarebbe idonea per importo, riga_ids la esclude a monte
    assert upd["in_ids"] == [1]
