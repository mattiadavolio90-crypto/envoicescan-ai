"""Lo strumento della chat «confronto_prezzi»: l'ultimo prezzo di ogni fornitore
e' la sua ultima fattura pagata, a prezzo ponderato (un acquisto e' una
fattura, 14/10/2026). Prima era la prima riga dell'ultima data: a caso fra le
righe della stessa fattura, e anche un omaggio a 0 € accanto.
"""
from types import SimpleNamespace

import pytest

from services import fastapi_worker as fw


class _Catena:
    def __init__(self, righe):
        self._righe = righe

    def __getattr__(self, nome):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=self._righe)


def _riga(fornitore, descrizione, prezzo, quantita, file, data, um="PZ"):
    return {"fornitore": fornitore, "descrizione": descrizione, "prezzo_unitario": prezzo,
            "quantita": quantita, "file_origine": file, "data_documento": data, "unita_misura": um}


def test_ultimo_prezzo_per_fornitore_e_l_ultima_fattura_ponderata():
    righe = [
        _riga("ADC", "MOZZARELLA", 2.0, 1, "b.xml", "2026-05-01"),
        _riga("ADC", "MOZZARELLA", 4.0, 3, "b.xml", "2026-05-01"),
        _riga("ADC", "MOZZARELLA", 0.0, 1, "b.xml", "2026-05-01"),
        _riga("ADC", "MOZZARELLA", 1.0, 1, "a.xml", "2026-04-01"),
        # il file piu' «grande» e' il piu' vecchio: vince la data, non il nome
        _riga("MEFON", "MOZZARELLA 1KG", 9.0, 1, "z.xml", "2026-03-01"),
        _riga("MEFON", "MOZZARELLA 125G", 3.0, 2, "a.xml", "2026-04-15"),
    ]
    esito = fw._chat_confronto_prezzi({"id": "u1"}, _Catena(righe), "mozzarella")
    per_forn = {f["fornitore"]: f for f in esito["fornitori"]}
    assert per_forn["ADC"]["prezzo"] == pytest.approx(3.5), "(2x1 + 4x3) / 4, l'omaggio non pesa"
    assert per_forn["MEFON"]["prezzo"] == 3.0 and per_forn["MEFON"]["descrizione"] == "MOZZARELLA 125G", (
        "del fornitore conta il prodotto comprato piu' di recente, senza mescolare 125 g e 1 kg"
    )
    assert [f["fornitore"] for f in esito["fornitori"]] == ["MEFON", "ADC"], "dal prezzo piu' basso"


def test_un_fornitore_trovato_solo_per_categoria_senza_descrizione_non_rompe():
    """La ricerca trova anche per categoria: righe senza descrizione non danno
    un «ultimo acquisto», e `max()` su niente faceva cadere lo strumento."""
    righe = [_riga("ADC", "", 2.0, 1, "b.xml", "2026-05-01"), _riga("MEFON", "LATTE", 1.0, 1, "m.xml", "2026-05-01")]
    esito = fw._chat_confronto_prezzi({"id": "u1"}, _Catena(righe), "latticini")
    assert [f["fornitore"] for f in esito["fornitori"]] == ["MEFON"]


# ── Unita' di misura diverse (audit di ottobre 2026, K20) ─────────────────


def test_prezzi_in_unita_diverse_non_si_mettono_in_fila():
    """1,20 €/PZ (mozzarella da 125 g) non e' «piu' conveniente» di 8 €/KG: al
    kg costa 9,60. Ogni voce porta la sua unita', l'ordine e' dentro l'unita' e
    il migliore lo dice lo strumento per ciascuna."""
    righe = [
        _riga("ALFA", "MOZZARELLA FIOR DI LATTE KG", 8.0, 1, "a.xml", "2026-05-01", um="KG"),
        _riga("BETA", "MOZZARELLA 125G", 1.2, 1, "b.xml", "2026-05-01", um="PZ"),
        _riga("GAMMA", "MOZZARELLA BUFALA", 7.5, 1, "c.xml", "2026-05-01", um="KG."),
        _riga("DELTA", "MOZZARELLA 250G", 2.0, 1, "d.xml", "2026-05-01", um="NUM."),
        _riga("EPSILON", "MOZZARELLA CT 3KG", 36.0, 1, "e.xml", "2026-05-01", um="CT"),
    ]
    esito = fw._chat_confronto_prezzi({"id": "u1"}, _Catena(righe), "mozzarella")
    assert [(f["fornitore"], f["unita"]) for f in esito["fornitori"]] == [
        ("GAMMA", "KG"), ("ALFA", "KG"),
        ("BETA", "PZ"), ("DELTA", "PZ"),
        ("EPSILON", "CT"),
    ]
    assert esito["migliore_per_unita"] == {"KG": "GAMMA", "PZ": "BETA", "CT": "EPSILON"}
    assert "unita' di misura diverse" in esito["nota"]


def test_sinonimi_del_pezzo_sono_la_stessa_unita():
    righe = [
        _riga("ALFA", "UOVA", 0.30, 1, "a.xml", "2026-05-01", um="NR"),
        _riga("BETA", "UOVA", 0.25, 1, "b.xml", "2026-05-01", um="N."),
    ]
    esito = fw._chat_confronto_prezzi({"id": "u1"}, _Catena(righe), "uova")
    assert {f["unita"] for f in esito["fornitori"]} == {"PZ"}
    assert esito["migliore_per_unita"] == {"PZ": "BETA"}
    assert "nota" not in esito
