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


# ─── Righe da controllare, cauzioni, stelle (12/10/2026) ─────────────────────

@pytest.mark.parametrize("a, b, atteso", [
    (1.0, 10.0, True),     # esattamente 10 volte: e' un cambio di confezione
    (1.0, 9.99, False),    # appena sotto: puo' ancora essere un rincaro vero
    (150.54, 0.10, True),  # la cauzione di OFFSIDE
    (14.0, 0.40, True),    # la bevanda di Sushiland, cassa contro bottiglia
    (0.0, 5.0, True),      # da zero a qualcosa non e' un prezzo confrontabile
])
def test_salto_da_controllare(a, b, atteso):
    from services.routers.prezzi import _salto_da_controllare

    assert _salto_da_controllare(a, b) is atteso


def test_la_variazione_da_dieci_volte_e_marcata_non_tolta():
    assert _v([150.54, 0.10])["da_controllare"] is True
    assert _v([10.0, 12.0])["da_controllare"] is False


def test_i_totali_dell_osservatorio_non_contano_le_righe_da_controllare():
    from services.routers.prezzi import _kpi_variazioni

    vera = {"aumento_perc": 20.0, "impatto_stimato": 55.09, "fornitore": "PARTESA"}
    salto = {"aumento_perc": -99.93, "impatto_stimato": -654.09, "fornitore": "PARTESA", "da_controllare": True}
    assert _kpi_variazioni([vera, salto]) == (20.0, 55.09, {"PARTESA"})
    assert _kpi_variazioni([salto]) == (0.0, 0.0, set())


def test_le_cauzioni_non_sono_prezzi_qualunque_sia_la_categoria():
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync

    def riga(desc, prezzo, data):
        return {"descrizione": desc, "categoria": "VARIE BAR", "fornitore": "PARTESA",
                "prezzo_unitario": prezzo, "quantita": 1, "totale_riga": prezzo,
                "data_documento": data, "file_origine": f"{data}.xml", "tipo_documento": "TD24"}

    righe = [riga("ADDEBITO CAUZIONI", 150.54, "2026-09-25"), riga("ADDEBITO CAUZIONI", 0.10, "2026-10-05"),
             riga("BIB COCA COLA", 15.80, "2026-09-25"), riga("BIB COCA COLA", 17.58, "2026-10-05")]
    assert [v["prodotto"] for v in _calcola_variazioni_prezzi_sync(righe, 5.0)] == ["BIB COCA COLA"]


def test_la_stella_salvata_col_nome_troncato_si_riaccende():
    """Fino all'11/10/2026 la stella salvava il nome a video (prodotto a 60,
    fornitore a 30): 10 preferiti su 19 non si riaccendevano. La chiave vecchia
    si riconosce ancora; la riga porta le chiavi intere per le stelle nuove."""
    desc = "PRODOTTO CON UNA DESCRIZIONE MOLTO LUNGA CHE SUPERA I SESSANTA CARATTERI DI SICURO"
    forn = "DINGFENG IMPORTEXPORT S.R.L. UNIPERSONALE"
    vecchia = f"{desc[:60]}|{forn[:30]}"
    v = _v([1.0, 2.0], descrizione=desc, fornitore=forn, preferiti_keys={vecchia})
    assert v["preferito"] is True
    assert (v["desc_key"], v["forn_key"]) == (desc, forn)
    assert _v([1.0, 2.0], descrizione=desc, fornitore=forn, preferiti_keys={f"{desc}|{forn}"})["preferito"] is True
    assert _v([1.0, 2.0], descrizione=desc, fornitore=forn, preferiti_keys=set())["preferito"] is False


def test_lo_score_non_penalizza_il_fornitore_per_un_cambio_di_confezione():
    from tests.test_prezzi_score_fornitori import OGGI, _serie
    from services.routers.prezzi import _calcola_score_fornitori

    rows = _serie("BEVANDA", "PARTESA", [("2026-06-01", 1.0), ("2026-07-01", 1.0), ("2026-08-01", 14.0)])
    salto = _v([1.0, 14.0], descrizione="BEVANDA", fornitore="PARTESA")
    assert salto["da_controllare"] is True
    con = _calcola_score_fornitori(rows, [salto], {}, oggi=OGGI)
    senza = _calcola_score_fornitori(rows, [], {}, oggi=OGGI)
    vera = _calcola_score_fornitori(rows, [{**salto, "da_controllare": False}], {}, oggi=OGGI)
    assert [f.score for f in con] == [f.score for f in senza]
    assert [f.score for f in vera] != [f.score for f in senza], "il caso non separa: lo score ignora le variazioni"
