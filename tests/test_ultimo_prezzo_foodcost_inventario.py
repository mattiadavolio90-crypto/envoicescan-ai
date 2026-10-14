"""L'«ultimo prezzo» del foodcost e dell'inventario e' l'ultima fattura pagata,
a prezzo ponderato (`utils/voci_prezzo.ultimo_acquisto_per_descrizione`).

Prima era la prima RIGA dell'ultima data: con lo stesso articolo su piu' righe
dell'ultima fattura dipendeva dall'ordine del database, e un omaggio a 0 €
accanto alla riga pagata proponeva 0 € (76 articoli sul live, 14/10/2026). La
RPC del foodcost ha la gemella SQL (tests/test_sql_funzioni_pagina.py); qui si
prova che i due chiamanti Python passano dalla regola.
"""
from unittest.mock import MagicMock

import utils.supabase_paging as paging
from services import foodcost_service

RIGHE = [
    # l'ordine e' quello del caricamento (data decrescente): l'omaggio e' per primo
    {"descrizione": "LATTE", "prezzo_unitario": 0.0, "quantita": 1, "unita_misura": "PZ",
     "data_documento": "2026-05-01", "file_origine": "b.xml", "categoria": "LATTICINI"},
    {"descrizione": "LATTE", "prezzo_unitario": 2.0, "quantita": 1, "unita_misura": "PZ",
     "data_documento": "2026-05-01", "file_origine": "b.xml", "categoria": "LATTICINI"},
    {"descrizione": "LATTE", "prezzo_unitario": 4.0, "quantita": 3, "unita_misura": "PZ",
     "data_documento": "2026-05-01", "file_origine": "b.xml", "categoria": "LATTICINI"},
    {"descrizione": "LATTE", "prezzo_unitario": 1.0, "quantita": 1, "unita_misura": "PZ",
     "data_documento": "2026-04-01", "file_origine": "a.xml", "categoria": "LATTICINI"},
]


def test_il_ripiego_del_foodcost_propone_il_prezzo_ponderato_dell_ultima_fattura(monkeypatch):
    def rpc_rotta(*a, **k):
        raise RuntimeError("RPC assente")

    monkeypatch.setattr(foodcost_service, "_articoli_rows_da_rpc", rpc_rotta)
    monkeypatch.setattr(foodcost_service, "_articoli_rows_full_load", lambda *a, **k: RIGHE)

    articoli = foodcost_service.get_articoli_da_fatture(MagicMock(), "u1", "r1")
    assert [(a["nome"], a["prezzo_unitario"]) for a in articoli] == [("LATTE", 3.5)]


def test_l_inventario_propone_il_prezzo_ponderato_dell_ultima_fattura(monkeypatch):
    import services.db_service as db_service
    from services.routers import workspace

    monkeypatch.setattr(workspace, "_resolve_user_from_token", lambda a: {"id": "u1"})
    monkeypatch.setattr(workspace, "_get_supabase_client", lambda: MagicMock())
    monkeypatch.setattr(workspace, "_resolve_ristorante_id", lambda u, sb: "r1")
    monkeypatch.setattr(db_service, "escludi_oscurate", lambda q: q)
    monkeypatch.setattr(db_service, "filter_active", lambda q: q)
    monkeypatch.setattr(paging, "fetch_all", lambda builder: RIGHE)

    articoli = workspace.ws_inventario_articoli(authorization="Bearer x")["articoli"]
    assert [(a["nome"], a["prezzo_unitario"], a["categoria"]) for a in articoli] == [("LATTE", 3.5, "LATTICINI")]
