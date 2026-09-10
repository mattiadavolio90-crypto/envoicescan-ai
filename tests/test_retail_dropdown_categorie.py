"""Il menu delle categorie di un negozio non mostra la tassonomia dei ristoranti (RETAIL_FASI.md 1.7).

`/api/fatture/categorie` unisce le categorie USATE dalla sede (gia' filtrate per
ristorante) alle CANONICHE della tabella globale `categorie`, che e' la
tassonomia dei ristoranti. Per un account retail le canoniche diventano
`categorie_ammesse('retail')`: ARTICOLO DI VENDITA piu' le spese generali.
ARTICOLO DI VENDITA non entra nella tabella `categorie`: comparirebbe nel menu di
ogni ristorante. Per i ristoranti l'unione e' quella di oggi.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import services.routers.fatture as fatture
import services.settore_service as ss

CANONICHE = ["CARNE", "VINI", "UTENZE E LOCALI", "📝 NOTE E DICITURE"]


class _SB:
    def table(self, _n):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a):
        return self

    def is_(self, *_a):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"nome": n} for n in CANONICHE])


def _categorie(monkeypatch, settore, usate):
    monkeypatch.setattr(fatture, "_resolve_user_from_token", lambda _a: {"id": "u1"})
    monkeypatch.setattr(fatture, "_resolve_ristorante_id", lambda _u, _sb: "r1")
    monkeypatch.setattr(fatture, "_get_supabase_client", lambda: _SB())
    monkeypatch.setattr(fatture, "fetch_all", lambda _q: [{"categoria": c} for c in usate])
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: settore)
    return fatture.get_categorie_disponibili(authorization="Bearer x")


def test_un_negozio_vede_articolo_e_spese_generali_non_le_food(monkeypatch):
    out = _categorie(monkeypatch, "retail", usate=["Da Classificare"])
    assert "ARTICOLO DI VENDITA" in out["categorie"]
    assert "UTENZE E LOCALI" in out["categorie"]
    assert "Da Classificare" in out["categorie"]
    assert "CARNE" not in out["categorie"] and "VINI" not in out["categorie"]


def test_le_categorie_usate_da_un_negozio_restano_visibili(monkeypatch):
    out = _categorie(monkeypatch, "retail", usate=["ARTICOLO DI VENDITA", "MANUTENZIONE E ATTREZZATURE"])
    assert out["usate"] == ["ARTICOLO DI VENDITA", "MANUTENZIONE E ATTREZZATURE"]


@pytest.mark.parametrize("settore", ["ristorazione", None])
def test_un_ristorante_vede_l_unione_di_oggi(monkeypatch, settore):
    out = _categorie(monkeypatch, settore, usate=["CARNE", "Da Classificare"])
    assert out["categorie"] == sorted({"CARNE", "Da Classificare", "VINI", "UTENZE E LOCALI"})
    assert "ARTICOLO DI VENDITA" not in out["categorie"]
