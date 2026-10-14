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
    from utils.voci_prezzo import salto_da_controllare

    assert salto_da_controllare(a, b) is atteso


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


def test_la_stella_di_una_famiglia_di_consegne_si_accende():
    """Il fornitore scrive il numero d'ordine nella descrizione («... NORVEGIA
    ORDER 2025916»): ogni consegna e' un nome diverso. Il 12/10/2026 quelle 4
    stelle sono state riscritte col fornitore intero e la descrizione corta (60):
    valgono per la famiglia, e nessuna delle altre due forme le riconosceva."""
    forn = "LA GE' GE' PESCA DI GAVAZZI SANTO & C. S.R.L"
    desc = "SALMONI 5/6 FRESCHI SALMAR ACQUACULTUA SALMO SALAR ALLEVATO NORVEGIA ORDER 2025916 (1014546)"
    famiglia = f"{desc[:60].strip()}|{forn}"
    assert _v([10.0, 12.0], descrizione=desc, fornitore=forn, preferiti_keys={famiglia})["preferito"] is True
    altro = "SALMONI 5/6 FRESCHI NORVEGIAN ACQUACUL SALMO SALAR ALLEVATO NORVEGIA ORDER 1 (1)"
    assert _v([10.0, 12.0], descrizione=altro, fornitore=forn, preferiti_keys={famiglia})["preferito"] is False


# ─── Il numero d'ordine nel nome (utils/voci_prezzo.py, regola 3) ───────────

@pytest.mark.parametrize("descrizione, atteso", [
    ("SALMONI 5/6 FRESCHI SALMAR ACQUACULTUA SALMO SALAR ALLEVATO NORVEGIA ORDER 2025916 (1014546)",
     "SALMONI 5/6 FRESCHI SALMAR ACQUACULTUA SALMO SALAR ALLEVATO NORVEGIA"),
    ("SALMONI 5/6 H111 FRESCHI ACQUACU SALMO SALAR ALLEVATO NORVEGIA ORDER 41484 (122741) BRAVO",
     "SALMONI 5/6 H111 FRESCHI ACQUACU SALMO SALAR ALLEVATO NORVEGIA BRAVO"),
    ("Salmone order 2009323(1005322)", "Salmone"),            # senza spazio prima della parentesi, minuscolo
    ("SALMONE ORDER 123 BRAVO", "SALMONE BRAVO"),              # senza parentesi: lo spazio dopo il numero resta
    ("RPA - CANCELLED ORDER COMMISSION", "RPA - CANCELLED ORDER COMMISSION"),  # ORDER senza numero: resta
    ("DISORDER 12", "DISORDER 12"),                            # parola intera, non suffisso
    ("  Limone bio ", "Limone bio"),
])
def test_togli_numero_ordine(descrizione, atteso):
    from utils.voci_prezzo import chiave_prodotto, togli_numero_ordine

    assert togli_numero_ordine(descrizione) == atteso
    assert chiave_prodotto(descrizione) == atteso.upper()


def test_il_numero_d_ordine_non_e_nel_nome_a_video_ne_nella_chiave():
    desc = "DENTICE GIBBOSO 1/2 PESCATO DENTEX GIBBOSUS ORDER 2025916 (1014546)"
    v = _v([10.0, 12.0], descrizione=desc)
    assert v["prodotto"] == "DENTICE GIBBOSO 1/2 PESCATO DENTEX GIBBOSUS"
    assert v["desc_key"] == "DENTICE GIBBOSO 1/2 PESCATO DENTEX GIBBOSUS"


def test_due_consegne_con_numeri_d_ordine_diversi_sono_una_serie():
    """Prima del 13/10/2026 ogni consegna di LA GE' GE' era una serie da un
    acquisto: 1.140 righe su 2.520 senza mai una variazione. Qui il controllo e'
    nelle due direzioni: stesso prodotto si unisce, prodotto diverso no."""
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync

    def riga(desc, prezzo, data):
        return {"descrizione": desc, "categoria": "PESCE", "fornitore": "LA GE' GE' PESCA",
                "prezzo_unitario": prezzo, "quantita": 1, "totale_riga": prezzo,
                "data_documento": data, "file_origine": f"{data}.xml", "tipo_documento": "TD24"}

    righe = [riga("SALMONI 5/6 SALMAR ORDER 2012258 (1007082)", 10.0, "2026-09-25"),
             riga("SALMONI 5/6 SALMAR ORDER 2012995 (1007786)", 12.0, "2026-10-05"),
             riga("SALMONI 5/6 MOWI ORDER 20131407 (100638660)", 10.0, "2026-09-25"),
             riga("SALMONI 5/6 MOWI ORDER 20148324 (100703803)", 10.0, "2026-10-05")]
    variazioni = _calcola_variazioni_prezzi_sync(righe, 5.0)
    assert [(v["prodotto"], v["aumento_perc"]) for v in variazioni] == [("SALMONI 5/6 SALMAR", 20.0)]


def test_lo_score_conta_i_prodotti_senza_il_numero_d_ordine():
    from tests.test_prezzi_score_fornitori import OGGI, _serie
    from services.routers.prezzi import _calcola_score_fornitori

    rows = (_serie("AGLIO ORDER 1 (1)", "LA GE' GE' PESCA", [("2026-04-01", 1.0), ("2026-05-01", 1.0)]) +
            _serie("AGLIO ORDER 2 (2)", "LA GE' GE' PESCA", [("2026-06-01", 1.0)]) +
            _serie("AGLIO NERO", "LA GE' GE' PESCA", [("2026-06-01", 9.0)]))
    assert [f.n_prodotti for f in _calcola_score_fornitori(rows, [], {}, oggi=OGGI)] == [2]


def test_la_nota_dei_sei_mesi_resta_anche_sui_nomi_lunghi():
    """Tagliata insieme al nome a 60, oltre i 53 caratteri la nota spariva o ne
    restava un pezzo («… ⚠️ >6») che la scheda non riconosce."""
    lungo = "SALMONI 5/6 FRESCHI SALMAR ACQUACULTUA SALMO SALAR ALLEVATO NORVEGIA"
    v = _v([1.0, 2.0], descrizione=lungo, data_penultimo="2025-09-01")
    assert v["prodotto"] == lungo[:60] + " ⚠️ >6m"
    assert _v([1.0, 2.0], descrizione=lungo)["prodotto"] == lungo[:60]


def test_un_fornitore_mancante_non_fa_cadere_l_osservatorio():
    """Il nome a video si calcola su tutte le serie, anche da un acquisto solo:
    `mode()` di una colonna tutta vuota e' vuoto e `[0]` faceva KeyError su
    tutta la pagina. Sul live le colonne sono NOT NULL; il calcolo non deve
    dipenderne."""
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync

    righe = [
        {"descrizione": "PANE", "fornitore": None, "categoria": "PANE", "prezzo_unitario": 1.0,
         "quantita": 1, "data_documento": "2026-03-01", "file_origine": "a.xml", "tipo_documento": "TD01"},
        {"descrizione": "LATTE", "fornitore": "ADC", "categoria": "LATTICINI", "prezzo_unitario": 1.0,
         "quantita": 1, "data_documento": "2026-03-01", "file_origine": "a.xml", "tipo_documento": "TD01"},
        {"descrizione": "LATTE", "fornitore": "ADC", "categoria": "LATTICINI", "prezzo_unitario": 2.0,
         "quantita": 1, "data_documento": "2026-04-01", "file_origine": "b.xml", "tipo_documento": "TD01"},
    ]
    assert [v["prodotto"] for v in _calcola_variazioni_prezzi_sync(righe, 5.0)] == ["LATTE"]
