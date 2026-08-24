"""Guardie sui fix di isolamento multi-sede e robustezza pipeline (audit §3b, 24/8/2026).

Contesto misurato sul DB live: l'utente 51015cc8-... possiede 4 sedi e ha tag
su 2 di esse (85 associazioni su LAND DEI SAPORI, 7 su SUSHILAND MARIANO).
I difetti difesi qui sono quindi raggiungibili, non teorici.

Il fake Supabase applica DAVVERO i filtri .eq(): con un fake che li registra
soltanto, un test sull'isolamento passerebbe anche senza il fix (errore gia'
occorso in questo ciclo, lezione 46).
"""
from types import SimpleNamespace

import pytest

import services.tag_suggestion_service as tss


class _Q:
    def __init__(self, rows, sink):
        self._rows = list(rows)
        self._sink = sink
        self._filtri = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filtri[col] = val
        self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self._sink.append(("update", dict(self._filtri), payload))
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _Sb:
    def __init__(self, tabelle):
        self.tabelle = tabelle
        self.scritture = []

    def table(self, nome):
        return _Q(self.tabelle.get(nome, []), self.scritture)


# Tag 9 appartiene alla sede A, tag 99 alla sede B: stesso utente.
_TAGS = [
    {"id": 9, "nome": "MAZZANCOLLE", "user_id": "u1", "ristorante_id": "sedeA"},
    {"id": 99, "nome": "SALMONE FRESCO", "user_id": "u1", "ristorante_id": "sedeB"},
]


def _sugg(sid=50, rid="sedeA"):
    return {
        "id": sid, "user_id": "u1", "ristorante_id": rid,
        "suggestion_type": "extend_tag", "status": "pending",
        "target_tag_id": 9, "suggested_tag_name": None,
        "items": [{"descrizione": "MAZZANCOLLE 41/50", "descrizione_key": "MAZZANCOLLE",
                   "selected_by_default": True}],
    }


def test_extend_tag_rifiuta_un_tag_di_un_altra_sede(monkeypatch):
    """Il target_tag_id arriva dal body: senza guardia le associazioni della
    sede A finivano dentro un tag della sede B, e il trigger DB riallineava
    user_id/ristorante_id al tag padre rendendo l'anomalia invisibile."""
    chiamate = []
    monkeypatch.setattr(tss, "aggiungi_associazioni",
                        lambda *a, **k: chiamate.append((a, k)))
    monkeypatch.setattr(tss, "clear_tags_cache", lambda: None)
    monkeypatch.setattr(tss, "_get_suggestion_with_items",
                        lambda *a, **k: _sugg())

    sb = _Sb({"custom_tags": _TAGS})
    res = tss.accept_suggestion_extend_tag(
        suggestion_id=50, tag_id=99,          # tag della sede B
        user_id="u1", ristorante_id="sedeA",  # utente operante sulla sede A
        supabase_client=sb,
    )

    assert res["success"] is False
    assert res["error"] == "target_tag_not_found"
    assert chiamate == [], "nessuna associazione deve essere scritta"


def test_extend_tag_accetta_un_tag_della_propria_sede(monkeypatch):
    chiamate = []
    monkeypatch.setattr(tss, "aggiungi_associazioni",
                        lambda *a, **k: chiamate.append((a, k)))
    monkeypatch.setattr(tss, "clear_tags_cache", lambda: None)
    monkeypatch.setattr(tss, "_get_suggestion_with_items",
                        lambda *a, **k: _sugg())

    sb = _Sb({"custom_tags": _TAGS})
    res = tss.accept_suggestion_extend_tag(
        suggestion_id=50, tag_id=9,
        user_id="u1", ristorante_id="sedeA",
        supabase_client=sb,
    )

    assert res["success"] is True
    assert res["tag_id"] == 9
    assert len(chiamate) == 1


# ─── Fix #8: una collisione non deve abortire l'intero ciclo ──────────────────

class _QEsplosiva:
    """Solleva sull'insert del primo suggerimento, funziona per gli altri."""

    def __init__(self, stato):
        self.stato = stato
        self._ultima = None

    def select(self, *_a, **_k):
        self._ultima = "select"
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        chiave = payload.get("cluster_key") if isinstance(payload, dict) else None
        if chiave == "boom":
            raise RuntimeError("duplicate key value violates unique constraint")
        self.stato["inseriti"].append(chiave)
        self._ultima = "insert"
        return self

    def update(self, *_a, **_k):
        return self

    def upsert(self, *_a, **_k):
        return self

    def delete(self):
        return self

    @property
    def not_(self):
        return self

    def in_(self, *_a, **_k):
        return self

    def execute(self):
        # select -> nessun pending esistente (si va sul ramo insert);
        # insert -> la riga creata, con l'id che serve agli item.
        return SimpleNamespace(data=[] if self._ultima == "select" else [{"id": 1}])


class _SbEsplosivo:
    def __init__(self):
        self.stato = {"inseriti": []}

    def table(self, _nome):
        return _QEsplosiva(self.stato)


def test_una_collisione_non_ferma_i_suggerimenti_successivi():
    """Pre-fix: l'eccezione risaliva a run_tag_suggestion_pipeline e abortiva
    il ciclo — i suggerimenti dopo quello in collisione non venivano scritti,
    ne' giravano dismiss e notifiche."""
    sb = _SbEsplosivo()
    suggestions = [
        {"suggestion_type": "new_tag", "cluster_key": "boom", "items": []},
        {"suggestion_type": "new_tag", "cluster_key": "ok_1", "items": []},
        {"suggestion_type": "new_tag", "cluster_key": "ok_2", "items": []},
    ]

    inserted = tss.upsert_tag_suggestions("u1", "sedeA", suggestions, supabase_client=sb)

    assert sb.stato["inseriti"] == ["ok_1", "ok_2"]
    assert inserted == 2
