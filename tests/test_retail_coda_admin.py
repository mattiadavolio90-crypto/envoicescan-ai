"""La coda qualita' dell'admin non suggerisce food a un negozio, e non lo promuove in memoria globale.

Terzo punto d'uscita trovato dal reviewer (seconda lettura). `admin_qualita_coda`
lavora su tutti gli utenti non-admin e propone `_suggerimento_deterministico`
(dizionario e regole dei ristoranti); il pulsante «Accetta tutti» del frontend
scrive in blocco le fonti `regola`/`memoria`. `admin_qualita_classifica` poi
promuove la descrizione in `prodotti_master` verified=True.

Scelta (coerente con la guardia gia' in `admin_qualita_risolvi_conflitto`): le
righe di un negozio RESTANO in coda — l'admin deve poterle classificare a mano —
ma senza suggerimento (ne' deterministico ne' AI), e la memoria globale non si
tocca quando le righe sono tutte di account retail.
"""
from __future__ import annotations

from unittest.mock import patch

import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin
import services.settore_service as ss
from tests.test_admin_qualita_fix_audit import _ADMIN, _FakeSB as _ClassificaSB
from tests.test_categorie_admin import FakeClient

UTENTI = [
    {"id": "u-rist", "email": "rist@x.it", "nome_ristorante": "Trattoria"},
    {"id": "u-retail", "email": "shop@x.it", "nome_ristorante": "Ferramenta"},
]
SETTORI = {"u-rist": "ristorazione", "u-retail": "retail"}


def _riga(id_, desc, user):
    return {"id": id_, "descrizione": desc, "categoria": "Da Classificare", "fornitore": "X",
            "prezzo_unitario": 10.0, "totale_riga": 10.0, "quantita": 1, "tipo_documento": "TD01",
            "needs_review": True, "user_id": user}


def _coda(monkeypatch, righe):
    sb = FakeClient({"users": UTENTI, "fatture": righe, "prodotti_utente": [], "prodotti_master": []})
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(admin, "_admin_emails_set", lambda: set())
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    out = admin.admin_qualita_coda(admin_user=_ADMIN)
    return {g["descrizione"]: g for g in out["gruppi"]}


def test_un_gruppo_di_un_negozio_resta_in_coda_senza_suggerimento(monkeypatch):
    gruppi = _coda(monkeypatch, [_riga(1, "BISTECCA DI MANZO", "u-retail"), _riga(2, "BISTECCA DI MANZO", "u-rist")])
    # Stesso testo per i due clienti: un solo gruppo, e contiene righe retail.
    g = gruppi["BISTECCA DI MANZO"]
    assert sorted(g["ids"]) == [1, 2]
    assert g["categoria_suggerita"] is None and g["fonte"] is None


def test_per_un_ristorante_il_suggerimento_deterministico_resta(monkeypatch):
    gruppi = _coda(monkeypatch, [_riga(1, "BISTECCA DI MANZO", "u-rist")])
    g = gruppi["BISTECCA DI MANZO"]
    assert g["categoria_suggerita"] == "CARNE"
    assert g["fonte"] in ("regola", "memoria")


def test_una_riga_retail_da_sola_resta_in_coda_senza_suggerimento(monkeypatch):
    gruppi = _coda(monkeypatch, [_riga(1, "TROTA SALMONATA", "u-retail")])
    g = gruppi["TROTA SALMONATA"]
    assert g["ids"] == [1]
    assert g["categoria_suggerita"] is None and g["fonte"] is None


def _classifica(monkeypatch, righe, categoria="MANUTENZIONE E ATTREZZATURE"):
    sb = _ClassificaSB({"fatture": righe, "prodotti_master": [], "ai_review_log": []})
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    with patch.multiple(
        admin,
        get_supabase_client=lambda *a, **k: sb,
        aggiorna_categoria_fatture=lambda *a, **k: len(k.get("ids") or []),
        _log_review_action=lambda *a, **k: None,
        _invalidate_fatture_rows_cache=lambda *a, **k: None,
    ):
        admin.admin_qualita_classifica(admin.ClassificaBody(ids=[r["id"] for r in righe], categoria=categoria), admin_user=_ADMIN)
    return [op for op in sb.ops if op[1] == "prodotti_master"]


def _riga_cl(id_, user):
    return {"id": id_, "descrizione": "SCAFFALE METALLICO", "prezzo_unitario": 90.0, "categoria": "Da Classificare",
            "ristorante_id": f"r-{user}", "user_id": user}


def test_classificare_righe_di_un_negozio_non_scrive_in_memoria_globale(monkeypatch):
    assert _classifica(monkeypatch, [_riga_cl(1, "u-retail")]) == []


def test_classificare_righe_di_un_ristorante_promuove_come_prima(monkeypatch):
    assert _classifica(monkeypatch, [_riga_cl(1, "u-rist")]) == [("upsert", "prodotti_master")]


def test_gruppo_misto_promuove_per_i_ristoranti(monkeypatch):
    assert _classifica(monkeypatch, [_riga_cl(1, "u-retail"), _riga_cl(2, "u-rist")]) == [("upsert", "prodotti_master")]
