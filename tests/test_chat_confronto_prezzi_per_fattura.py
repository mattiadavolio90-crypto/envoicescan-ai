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
