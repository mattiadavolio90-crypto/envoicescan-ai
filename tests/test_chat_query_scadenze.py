"""Test guardia: _chat_query_scadenze (audit §3b chat, F1 — HIGH).

Difetto originale (25/8/2026, mattina): il tool dichiarava al modello il
totale su TUTTI i documenti non pagati ma troncava l'elenco a 30 voci senza
dirlo. Confermato sul DB live: 7 sedi su 9, fino a 37.9x di divergenza tra
totale dichiarato e somma delle 30 voci mostrate (LAND DEI SAPORI). Le
scadenze SENZA data finivano sempre in fondo per costruzione dell'ordinamento
(`scadenza or "9999"`), quindi sparivano dietro il troncamento anche quando
valevano la maggioranza del debito (fino al 91% su OVERTIME).

Primo fix (rivisto dal code-reviewer, 25/8 pomeriggio): mettere le voci SENZA
scadenza in cima dell'ordinamento risolveva la sparizione ma la SPOSTAVA
sull'altro insieme — su tutte e 7 le sedi con >=30 voci senza scadenza, le 30
mostrate diventavano ESCLUSIVAMENTE quelle senza scadenza, nascondendo le
scadenze imminenti/scadute che sono l'informazione piu' utile per "cosa devo
pagare questa settimana" (il caso d'uso dichiarato del tool). Un secondo
difetto (B3): con solo_da_pagare=False le voci gia' pagate, se senza
scadenza, salivano in cima insieme alle non pagate e potevano monopolizzare
l'elenco.

Fix finale: quota mista. Le voci CON scadenza (piu' urgenti/informative)
riempiono l'elenco fino al tetto meno una quota fissa (10) riservata alle
SENZA scadenza, cosi' non spariscono mai del tutto ma nemmeno monopolizzano.
Le pagate vanno in coda, mai in competizione con le non pagate per gli slot.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw


def _doc(fornitore, importo, scadenza=None, pagata=False):
    return {
        "fornitore": fornitore,
        "totale_documento": importo,
        "scadenza_effettiva": scadenza,
        "pagata": pagata,
    }


@pytest.fixture
def user():
    return {"id": "u-test", "email": "test@x.it"}


def _query(monkeypatch, docs, solo_da_pagare=True, ristorante_id="rid-1"):
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, sb: ristorante_id)
    monkeypatch.setattr(
        "services.documenti_service.get_documenti_scadenziario",
        lambda user_id, rid: docs,
    )
    return fw._chat_query_scadenze({"id": "u-test"}, MagicMock(), solo_da_pagare=solo_da_pagare)


def test_totale_parziale_dichiarato_quando_tronca(monkeypatch):
    docs = [_doc(f"forn{i}", 100.0, scadenza=f"2026-09-{(i % 28) + 1:02d}") for i in range(45)]
    r = _query(monkeypatch, docs)
    assert r["totale_parziale"] is True
    assert r["voci_totali"] == 45
    assert "nota" in r


def test_nessun_troncamento_non_dichiara_parziale(monkeypatch):
    docs = [_doc(f"forn{i}", 100.0, scadenza="2026-09-01") for i in range(10)]
    r = _query(monkeypatch, docs)
    assert "totale_parziale" not in r
    assert "voci_totali" not in r


def test_totale_dichiarato_copre_tutte_le_voci_non_solo_quelle_mostrate(monkeypatch):
    docs = [_doc(f"forn{i}", 1000.0, scadenza=f"2026-09-{(i % 28) + 1:02d}") for i in range(40)]
    r = _query(monkeypatch, docs)
    assert r["totale_da_pagare"] == 40000.0
    somma_mostrate = sum(v["importo"] for v in r["scadenze"])
    assert somma_mostrate < r["totale_da_pagare"]
    assert len(r["scadenze"]) == 30


def test_documenti_senza_scadenza_non_spariscono_del_tutto(monkeypatch):
    """Riproduce OVERTIME: la maggioranza del debito non ha scadenza_effettiva.
    Almeno la quota minima deve restare visibile anche quando superano il tetto;
    qui le con-data sono poche (5), quindi lo spazio che avanza va alle altre
    senza-data e non a slot vuoti — 30 mostrate in tutto, 5 con data e 25 senza."""
    docs_senza_scadenza = [_doc(f"vecchio{i}", 500.0, scadenza=None) for i in range(35)]
    docs_con_scadenza = [_doc(f"nuovo{i}", 10.0, scadenza="2026-09-01") for i in range(5)]
    r = _query(monkeypatch, docs_senza_scadenza + docs_con_scadenza)
    mostrati_senza_scadenza = sum(1 for v in r["scadenze"] if v["scadenza"] is None)
    assert mostrati_senza_scadenza >= fw._CHAT_SCADENZE_QUOTA_SENZA_DATA
    assert mostrati_senza_scadenza == 25
    assert len(r["scadenze"]) == fw._CHAT_SCADENZE_LIMIT
    assert r["senza_scadenza_non_mostrate"] == 10


def test_quota_minima_garantita_anche_con_molte_scadenze_note(monkeypatch):
    """Il caso in cui la quota conta davvero come MINIMO: le con-data da sole
    riempirebbero tutto il tetto (40 > 30) e senza la quota le senza-data
    sparirebbero, com'era nel bug originale."""
    docs_con_scadenza = [_doc(f"nuovo{i}", 10.0, scadenza=f"2026-09-{(i % 28) + 1:02d}") for i in range(40)]
    docs_senza_scadenza = [_doc(f"vecchio{i}", 500.0, scadenza=None) for i in range(15)]
    r = _query(monkeypatch, docs_con_scadenza + docs_senza_scadenza)
    mostrati_senza_scadenza = sum(1 for v in r["scadenze"] if v["scadenza"] is None)
    assert mostrati_senza_scadenza == fw._CHAT_SCADENZE_QUOTA_SENZA_DATA
    assert r["senza_scadenza_non_mostrate"] == 15 - fw._CHAT_SCADENZE_QUOTA_SENZA_DATA


def test_scadenze_imminenti_non_spariscono_dietro_le_senza_data(monkeypatch):
    """La regressione trovata dal code-reviewer: se le voci senza scadenza
    superano 30, il primo fix le mostrava TUTTE e nascondeva ogni scadenza
    imminente/scaduta — l'informazione che il tool esiste per dare."""
    docs_senza_scadenza = [_doc(f"vecchio{i}", 500.0, scadenza=None) for i in range(40)]
    docs_imminenti = [_doc(f"urgente{i}", 200.0, scadenza=f"2026-09-{i+1:02d}") for i in range(15)]
    r = _query(monkeypatch, docs_senza_scadenza + docs_imminenti)
    fornitori_mostrati = {v["fornitore"] for v in r["scadenze"]}
    assert {f"urgente{i}" for i in range(15)} <= fornitori_mostrati


def test_ordine_delle_con_data_e_per_scadenza_piu_vicina(monkeypatch):
    docs = [
        _doc("lontana", 100.0, scadenza="2026-12-01"),
        _doc("vicina", 100.0, scadenza="2026-09-01"),
        _doc("media", 100.0, scadenza="2026-10-01"),
    ]
    r = _query(monkeypatch, docs)
    assert [v["fornitore"] for v in r["scadenze"]] == ["vicina", "media", "lontana"]


def test_senza_scadenza_non_mostrate_assente_se_tutte_le_voci_hanno_scadenza(monkeypatch):
    docs = [_doc(f"forn{i}", 100.0, scadenza="2026-09-01") for i in range(5)]
    r = _query(monkeypatch, docs)
    assert "senza_scadenza_non_mostrate" not in r


def test_solo_da_pagare_true_esclude_pagate_dal_totale_e_dalle_voci(monkeypatch):
    docs = [
        _doc("forn-pagato", 5000.0, scadenza="2026-09-01", pagata=True),
        _doc("forn-aperto", 100.0, scadenza="2026-09-02", pagata=False),
    ]
    r = _query(monkeypatch, docs, solo_da_pagare=True)
    assert r["totale_da_pagare"] == 100.0
    assert len(r["scadenze"]) == 1
    assert r["scadenze"][0]["fornitore"] == "forn-aperto"


def test_solo_da_pagare_false_include_pagate_ma_non_nel_totale(monkeypatch):
    docs = [
        _doc("forn-pagato", 5000.0, scadenza="2026-09-01", pagata=True),
        _doc("forn-aperto", 100.0, scadenza="2026-09-02", pagata=False),
    ]
    r = _query(monkeypatch, docs, solo_da_pagare=False)
    assert r["totale_da_pagare"] == 100.0
    assert len(r["scadenze"]) == 2


def test_pagate_senza_scadenza_non_monopolizzano_elenco_su_solo_da_pagare_false(monkeypatch):
    """B3 (code-reviewer): con solo_da_pagare=False, molte voci pagate senza
    scadenza non devono rubare slot alle voci APERTE senza scadenza — sono
    queste che contano per 'cosa devo ancora pagare'.

    Le aperte qui superano da sole il tetto (35 > 30): ogni pagata mostrata
    sarebbe quindi un furto dimostrato, non spazio che avanzava. Il caso in
    cui le aperte NON riempiono il tetto e' un'altra cosa e resta legittimo
    (vedi test_solo_da_pagare_false_include_pagate_ma_non_nel_totale)."""
    docs_pagate_senza_data = [_doc(f"pagato{i}", 1000.0, scadenza=None, pagata=True) for i in range(40)]
    docs_aperte_senza_data = [_doc(f"apertosd{i}", 50.0, scadenza=None, pagata=False) for i in range(35)]
    r = _query(monkeypatch, docs_pagate_senza_data + docs_aperte_senza_data, solo_da_pagare=False)
    mostrati_pagati = [v for v in r["scadenze"] if v["pagata"]]
    assert len(mostrati_pagati) == 0
    assert len(r["scadenze"]) == fw._CHAT_SCADENZE_LIMIT


def test_nessuna_sede_risolta_ritorna_vuoto(monkeypatch):
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, sb: None)
    r = fw._chat_query_scadenze({"id": "u-test"}, MagicMock())
    assert r == {"scadenze": [], "totale_da_pagare": 0.0}
