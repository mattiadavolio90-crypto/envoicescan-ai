"""Admin → Categorie, «Da sistemare» (14/10/2026).

La pagina sostituisce le 4 tab di Categorie: una lista sola di righe su cui
serve una decisione (`needs_review` o `Da Classificare`), un gruppo per
descrizione, il piu' pesante in euro per primo. Qui la composizione pura
(`services/admin_categorie_service.py`), la lettura delle righe dal DB e il
contatore della pagina Oggi, che deve dire lo stesso numero della pagina.
"""
from __future__ import annotations

from unittest.mock import patch

import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin
import services.settore_service as ss
from services.admin_categorie_service import (
    NOTE_E_DICITURE, chiave_descrizione, componi_da_sistemare, conta_da_sistemare,
)
from tests.test_admin_qualita_fix_audit import _ADMIN, _FakeSB as _ClassificaSB
from tests.test_categorie_admin import FakeClient


def _r(id_, desc, categoria="SERVIZI E CONSULENZE", totale=10.0, user="u1", fornitore="F1", prezzo=None):
    return {"id": id_, "descrizione": desc, "categoria": categoria, "totale_riga": totale,
            "prezzo_unitario": totale if prezzo is None else prezzo, "user_id": user, "fornitore": fornitore}


def _niente(_desc, _cat):
    return None, None


def _componi(righe, umane=frozenset(), nomi=None, retail=frozenset(), suggerisci=_niente):
    return componi_da_sistemare(righe, set(umane), nomi or {"u1": "Trattoria", "u2": "Pizzeria"}, set(retail), suggerisci)


# ─── composizione ────────────────────────────────────────────────────────────

def test_le_varianti_di_una_descrizione_fanno_un_gruppo_solo():
    gruppi = _componi([_r(2, "pane casereccio "), _r(1, "PANE CASERECCIO")])
    assert len(gruppi) == 1
    g = gruppi[0]
    assert g["chiave"] == "PANE CASERECCIO"
    assert g["ids"] == [1, 2] and g["righe"] == 2
    assert g["descrizione"] == "PANE CASERECCIO"


def test_gli_euro_sono_in_valore_assoluto_e_ordinano_la_lista():
    gruppi = _componi([
        _r(1, "PICCOLO", totale=5),
        _r(2, "NOTA DI CREDITO", totale=-300),
        _r(3, "MEDIO", totale=100), _r(4, "MEDIO", totale=50),
    ])
    assert [g["descrizione"] for g in gruppi] == ["NOTA DI CREDITO", "MEDIO", "PICCOLO"]
    assert [g["euro"] for g in gruppi] == [300.0, 150.0, 5.0]


def test_a_parita_di_euro_vince_chi_ha_piu_righe_poi_l_alfabeto():
    gruppi = _componi([_r(1, "B", totale=0), _r(2, "A", totale=0), _r(3, "C", totale=0), _r(4, "C", totale=0)])
    assert [g["descrizione"] for g in gruppi] == ["C", "A", "B"]


def test_le_scelte_dei_clienti_restano_fuori_anche_con_maiuscole_e_spazi():
    gruppi = _componi([_r(1, " coupon z "), _r(2, "TORTA")], umane={chiave_descrizione("COUPON Z")})
    assert [g["descrizione"] for g in gruppi] == ["TORTA"]


def test_categoria_prevalente_e_categorie_diverse():
    gruppi = _componi([
        _r(1, "X", categoria="VERDURE"), _r(2, "X", categoria="FRUTTA"), _r(3, "X", categoria="VERDURE"),
    ])
    assert gruppi[0]["categoria"] == "VERDURE"
    assert gruppi[0]["categorie"] == ["FRUTTA", "VERDURE"]


def test_a_parita_la_categoria_si_sceglie_per_alfabeto_non_per_ordine_di_arrivo():
    a = _componi([_r(1, "X", categoria="VERDURE"), _r(2, "X", categoria="FRUTTA")])
    b = _componi([_r(1, "X", categoria="FRUTTA"), _r(2, "X", categoria="VERDURE")])
    assert a[0]["categoria"] == b[0]["categoria"] == "FRUTTA"


def test_categoria_vuota_conta_come_da_classificare():
    g = _componi([_r(1, "X", categoria=None)])[0]
    assert g["categoria"] == "Da Classificare" and g["categorie"] == ["Da Classificare"]


def test_cliente_e_fornitore():
    uno = _componi([_r(1, "X", fornitore="METRO"), _r(2, "X", fornitore="METRO"), _r(3, "X", fornitore="SOGEGROSS")])[0]
    assert uno["cliente"] == "Trattoria" and uno["cliente_ids"] == ["u1"]
    assert uno["fornitore"] == "METRO"
    due = _componi([_r(1, "Y", user="u1"), _r(2, "Y", user="u2")])[0]
    assert due["cliente"] == "2 clienti" and due["cliente_ids"] == ["u1", "u2"]
    senza = _componi([_r(1, "Z", fornitore=" "), _r(2, "Z", user="u9", fornitore=None)])[0]
    assert senza["fornitore"] is None
    # Un cliente senza nome nella mappa si vede col suo id, non sparisce.
    assert senza["cliente"] == "2 clienti" and senza["cliente_ids"] == ["u1", "u9"]


def test_descrizione_vuota_si_vede_come_trattino():
    assert _componi([_r(1, "")])[0]["descrizione"] == "—"


# ─── suggerimento ────────────────────────────────────────────────────────────

def test_il_suggerimento_arriva_dal_suggeritore():
    g = _componi([_r(1, "SALMONE")], suggerisci=lambda d, c: ("PESCE", "regola"))[0]
    assert (g["suggerita"], g["fonte"]) == ("PESCE", "regola")


def test_niente_suggerimento_se_ripete_la_categoria():
    g = _componi([_r(1, "SALMONE", categoria="PESCE")], suggerisci=lambda d, c: ("PESCE", "regola"))[0]
    assert g["suggerita"] is None and g["fonte"] is None


def test_un_gruppo_con_righe_di_un_negozio_non_ha_suggerimento():
    chiamate = []

    def sugg(d, c):
        chiamate.append(d)
        return "CARNE", "regola"

    g = _componi([_r(1, "BISTECCA", user="u1"), _r(2, "BISTECCA", user="u2")], retail={"u2"}, suggerisci=sugg)[0]
    assert g["suggerita"] is None and chiamate == []


def test_note_non_si_suggerisce_a_un_gruppo_con_importi():
    sugg = lambda d, c: (NOTE_E_DICITURE, "regola")  # noqa: E731
    con_totale = _componi([_r(1, "RIGA FATTURA", totale=0), _r(2, "RIGA FATTURA", totale=12)], suggerisci=sugg)[0]
    assert con_totale["suggerita"] is None
    # Totale zero ma prezzo no: `admin_qualita_classifica` la considera con importo.
    con_prezzo = _componi([_r(1, "RIGA FATTURA", totale=0, prezzo=3)], suggerisci=sugg)[0]
    assert con_prezzo["suggerita"] is None
    a_zero = _componi([_r(1, "RIGA FATTURA", totale=0, prezzo=0)], suggerisci=sugg)[0]
    assert a_zero["suggerita"] == NOTE_E_DICITURE


# ─── Oggi e Categorie dicono lo stesso numero ────────────────────────────────

def test_il_contatore_conta_i_gruppi_della_pagina():
    righe = [_r(1, "A"), _r(2, "a "), _r(3, "B"), _r(4, "COUPON"), _r(5, "")]
    umane = {"COUPON"}
    assert conta_da_sistemare(righe, umane) == len(_componi(righe, umane=umane)) == 3


# ─── lettura dal DB ──────────────────────────────────────────────────────────

UTENTI = [
    {"id": "u1", "email": "cliente@x.it", "nome_ristorante": "Trattoria"},
    {"id": "u2", "email": "altro@x.it", "nome_ristorante": "Pizzeria"},
    {"id": "adm", "email": " MD@oneflux.it ", "nome_ristorante": "Admin"},
]


def _f(id_, desc, user="u1", needs_review=True, categoria="VERDURE", oscurata=False, deleted_at=None, totale=10.0):
    return {"id": id_, "descrizione": desc, "categoria": categoria, "fornitore": "F", "totale_riga": totale,
            "prezzo_unitario": totale, "user_id": user, "needs_review": needs_review,
            "oscurata": oscurata, "deleted_at": deleted_at}


def _sb(fatture, prodotti_utente=()):
    return FakeClient({"users": UTENTI, "fatture": fatture, "prodotti_utente": list(prodotti_utente), "prodotti_master": []})


def _endpoint(monkeypatch, sb):
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(admin, "_admin_emails_set", lambda: {"md@oneflux.it"})
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: "ristorazione")
    return admin.admin_categorie_da_sistemare(admin_user=_ADMIN)


def test_entrano_needs_review_e_da_classificare_una_volta_sola(monkeypatch):
    sb = _sb([
        _f(1, "DUBBIA"),
        _f(2, "SENZA CATEGORIA", needs_review=False, categoria="Da Classificare"),
        _f(3, "ENTRAMBE", categoria="Da Classificare"),
        _f(4, "A POSTO", needs_review=False),
    ])
    out = _endpoint(monkeypatch, sb)
    assert sorted(i for g in out["gruppi"] for i in g["ids"]) == [1, 2, 3]


def test_restano_fuori_cestino_oscurate_e_admin(monkeypatch):
    sb = _sb([
        _f(1, "VIVA"),
        _f(2, "NEL CESTINO", deleted_at="2026-10-01"),
        _f(3, "ESCLUSA DAI CONTI", oscurata=True),
        _f(4, "DELL'ADMIN", user="adm"),
    ])
    out = _endpoint(monkeypatch, sb)
    assert [g["descrizione"] for g in out["gruppi"]] == ["VIVA"]
    assert out["clienti"] == [{"id": "u1", "nome": "Trattoria"}]


def test_le_scelte_a_mano_del_cliente_restano_fuori(monkeypatch):
    sb = _sb([_f(1, "COUPON Z"), _f(2, "TORTA")],
             prodotti_utente=[{"user_id": "u1", "descrizione": "coupon z", "classificato_da": "Manuale (cliente)"}])
    out = _endpoint(monkeypatch, sb)
    assert [g["descrizione"] for g in out["gruppi"]] == ["TORTA"]


def test_i_clienti_del_filtro_sono_quelli_con_qualcosa_da_sistemare(monkeypatch):
    sb = _sb([_f(1, "A", user="u2"), _f(2, "B", user="u1")])
    out = _endpoint(monkeypatch, sb)
    assert out["clienti"] == [{"id": "u2", "nome": "Pizzeria"}, {"id": "u1", "nome": "Trattoria"}]


def test_oggi_conta_quello_che_mostra_la_pagina(monkeypatch):
    sb = _sb([
        _f(1, "A"), _f(2, "a"), _f(3, "B", needs_review=False, categoria="Da Classificare"),
        _f(4, "C", oscurata=True), _f(5, "COUPON Z"),
    ], prodotti_utente=[{"user_id": "u1", "descrizione": "COUPON Z", "classificato_da": "Manuale"}])
    out = _endpoint(monkeypatch, sb)
    assert admin._conta_categorie_da_controllare(sb) == len(out["gruppi"]) == 2


# ─── classifica: «Annulla» riporta indietro solo quello che e' cambiato ──────

def test_classifica_registra_le_righe_scritte_e_restituisce_il_log(monkeypatch):
    righe = [
        {"id": 1, "descrizione": "RIGA", "prezzo_unitario": 0, "totale_riga": 0, "categoria": "Da Classificare", "ristorante_id": "r1", "user_id": "u1"},
        {"id": 2, "descrizione": "RIGA", "prezzo_unitario": 5, "totale_riga": 5, "categoria": "Da Classificare", "ristorante_id": "r1", "user_id": "u1"},
    ]
    sb = _ClassificaSB({"fatture": righe, "prodotti_master": [], "ai_review_log": []})
    registrati = []
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: "ristorazione")
    with patch.multiple(
        admin,
        get_supabase_client=lambda *a, **k: sb,
        aggiorna_categoria_fatture=lambda *a, **k: len(k.get("ids") or []),
        _log_review_action=lambda *a, **k: registrati.append(k["ids_fatture"]) or 77,
        _invalidate_fatture_rows_cache=lambda *a, **k: None,
    ):
        out = admin.admin_qualita_classifica(admin.ClassificaBody(ids=[1, 2], categoria=NOTE_E_DICITURE), admin_user=_ADMIN)
    # NOTE va solo sulla riga a zero euro: e' l'unica che «Annulla» deve toccare.
    assert registrati == [[1]]
    assert out["log_id"] == 77 and out["righe_aggiornate"] == 1
