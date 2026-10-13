"""Admin → Oggi: lettura della risposta, gruppi, sedi per i pulsanti e la riga
dei numeri (lib/admin-oggi.ts)."""
from __future__ import annotations

from tests.helpers_ts import esegui_ts

MODULO = "lib/admin-oggi"
FUNZIONI = ["leggiOggi", "raggruppa", "sediPerAzione", "rigaNumeri"]

SEDI = [
    {"id": "r1", "nome": "Navigli", "partita_iva": "111", "user_id": "u1", "cliente": "OFFSIDE"},
    {"id": "r2", "nome": "Casati", "partita_iva": None, "user_id": "u1", "cliente": "OFFSIDE"},
    {"id": "r3", "nome": "Time Cafe", "partita_iva": "333", "user_id": "u2", "cliente": "TIME"},
]


def _f(espressione, arg):
    return esegui_ts(MODULO, f"emit({espressione});", argomento=arg, richiede=FUNZIONI)


def test_una_risposta_senza_voci_non_e_tutto_a_posto():
    for d in (None, {"detail": "errore"}, {"voci": None, "numeri": {}}, {"voci": []}):
        assert _f("m.leggiOggi(input)", d) is None, d
    letto = _f("m.leggiOggi(input)", {"voci": [], "numeri": {"clienti": 7}})
    assert letto["numeri"]["clienti"] == 7 and letto["numeri"]["fatture_ieri"] is None
    assert letto["sedi"] == [] and letto["_errors"] == []


def test_urgenti_e_da_fare():
    voci = [{"chiave": "a", "gravita": "oggi"}, {"chiave": "b", "gravita": "critico"}, {"chiave": "c", "gravita": "oggi"}]
    g = _f("m.raggruppa(input)", voci)
    assert [v["chiave"] for v in g["urgenti"]] == ["b"]
    assert [v["chiave"] for v in g["daFare"]] == ["a", "c"]


def test_smistare_offre_solo_le_sedi_del_cliente_assegnare_tutte():
    sede = _f("m.sediPerAzione(input[0], input[1])", [{"tipo": "assegna_sede", "queue_id": 1, "user_id": "u1"}, SEDI])
    assert sede == [{"id": "r1", "label": "Navigli — 111"}, {"id": "r2", "label": "Casati"}]
    piva = _f("m.sediPerAzione(input[0], input[1])", [{"tipo": "assegna_piva", "queue_id": 1, "piva": "9"}, SEDI])
    assert [s["label"] for s in piva] == ["Navigli (OFFSIDE)", "Casati (OFFSIDE)", "Time Cafe (TIME)"]


def test_riga_dei_numeri():
    n = {"fatture_ieri": 1, "fatture_mese": 56, "costo_ai_mese": 0.1, "clienti_attivi": 7, "clienti": 7}
    assert _f("m.rigaNumeri(input)", n) == "Ieri 1 fattura · 56 nel mese · costo AI del mese $ 0,10 · 7 clienti attivi su 7"
    vuoti = {"fatture_ieri": None, "fatture_mese": None, "costo_ai_mese": None, "clienti_attivi": 0, "clienti": 0}
    assert _f("m.rigaNumeri(input)", vuoti) == "0 clienti attivi su 0"
