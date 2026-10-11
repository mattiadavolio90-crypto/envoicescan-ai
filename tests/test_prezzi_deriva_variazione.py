"""`_deriva_variazione`: la variazione di una coppia prodotto+fornitore.

E' condivisa fra l'Osservatorio del PV e la scheda «Prezzi» della catena, e il
test che confronta le due strade (`test_sql_gruppo_prezzi.py`) non la puo'
proteggere: una modifica qui cambia entrambe allo stesso modo e il confronto
resta verde. Misurato per mutazione l'11/10/2026 — «storico su 4 valori» e
«trend su 5» sopravvivevano. Questi casi sono scelti dove le due letture
divergono.
"""
import pytest

from services.routers.prezzi import _deriva_variazione, _frequenza_mensile


def _v(prezzi, soglia=0.0, **extra):
    base = dict(
        ultimi_prezzi=prezzi, media=sum(prezzi) / len(prezzi), data_penultimo="2026-03-01",
        data_ultimo="2026-04-01", descrizione="LIMONE", fornitore="MEFON", categoria="FRUTTA",
        n_fattura="f.xml", qta_ref=2.0, freq=3.0, soglia=soglia, preferiti_keys=set(),
    )
    base.update(extra)
    return _deriva_variazione(**base)


def test_lo_storico_mostra_gli_ultimi_cinque_prezzi():
    assert _v([1.0, 2.0, 3.0, 4.0, 5.0])["storico_valori"] == [1.0, 2.0, 3.0, 4.0, 5.0]


@pytest.mark.parametrize("prezzi, atteso", [
    # Sugli ultimi 4 solo due rialzi: «⬆». Sui 5 entrerebbe il -4 iniziale: «↕».
    ([5.0, 1.0, 2.0, 2.0, 3.0], "⬆"),
    ([1.0, 2.0, 3.0, 4.0], "⬆⬆"),
    ([4.0, 3.0, 2.0, 1.0], "⬇⬇"),
    ([1.0, 3.0, 2.0, 2.5], "↕"),
])
def test_il_trend_guarda_gli_ultimi_quattro_prezzi(prezzi, atteso):
    assert _v(prezzi)["trend"] == atteso


def test_sotto_soglia_nessuna_variazione():
    assert _v([10.0, 10.4], soglia=5.0) is None
    assert _v([10.0, 10.5], soglia=5.0)["aumento_perc"] == 5.0


def test_impatto_e_delta_per_quantita_per_frequenza():
    v = _v([10.0, 12.0])
    assert (v["delta_euro"], v["impatto_stimato"]) == (2.0, 12.0)


def test_oltre_sei_mesi_fra_gli_ultimi_due_acquisti_lo_dice_il_nome():
    assert _v([1.0, 2.0], data_penultimo="2025-09-01")["prodotto"] == "LIMONE ⚠️ >6m"


@pytest.mark.parametrize("n, prima, ultima, atteso", [
    (1, "2026-01-01", "2026-01-01", 1.0),
    (4, "2026-01-01", "2026-01-11", 4.0),
    (6, "2026-01-01", "2026-03-02", 3.0),
])
def test_frequenza_mensile(n, prima, ultima, atteso):
    assert _frequenza_mensile(n, prima, ultima) == pytest.approx(atteso)


def test_la_catena_non_trasforma_una_quantita_media_zero_in_uno():
    """L'Osservatorio usa la media delle quantita' com'e', anche 0: in catena un
    `or 1.0` la faceva diventare 1 e l'impatto della stessa riga divergeva."""
    from services.routers.gruppo import _variazioni_catena

    coppia = {
        "ristorante_id": "s1", "desc_key": "LIMONE", "forn_key": "MEFON", "descrizione": "LIMONE",
        "fornitore": "MEFON", "n_acquisti": 2, "ultimi_prezzi": [10.0, 12.0], "media": 11.0,
        "qta_media": 0, "prima_data": "2026-03-01", "ultima_data": "2026-04-01",
        "penultima_data": "2026-03-01", "categoria": "FRUTTA", "file_origine": "f.xml",
    }
    assert _variazioni_catena([coppia], {"s1": "Centro"}, 5.0)[0]["impatto_stimato"] == 0
    senza = {**coppia, "qta_media": None}
    assert _variazioni_catena([senza], {"s1": "Centro"}, 5.0)[0]["impatto_stimato"] != 0
