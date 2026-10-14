"""Un acquisto = una fattura (`utils/voci_prezzo.una_riga_per_documento`).

Lo stesso prodotto su piu' righe della stessa fattura contava come piu'
acquisti: ORTOFRUTTA 2,88 -> 3,83 -> 2,88 tutto nella fattura 39/FA
(screenshot di Mattia del 14/10/2026), GINSENG 5 acquisti su 4 fatture. Questa
e' la regola unica che usano Osservatorio, storico e avvisi; la RPC di catena
ne ha la gemella in SQL.
"""
import pandas as pd
import pytest

from utils.voci_prezzo import una_riga_per_documento


def _righe(*righe):
    base = {"sede": "A", "prodotto": "ORTOFRUTTA", "fornitore": "GIANOLI", "data": "2026-04-04", "um": "PZ"}
    return pd.DataFrame([{**base, **r} for r in righe])


def _uno(df, **kw):
    opzioni = dict(
        chiavi=["sede", "prodotto", "fornitore"], file="file", data="data", prezzo="prezzo",
        quantita="q", unita="um", somme=("totale",), massimo=("categoria",),
    )
    opzioni.update(kw)
    return una_riga_per_documento(df, **opzioni)


def test_tre_righe_della_stessa_fattura_sono_un_acquisto_a_prezzo_ponderato():
    df = _righe(
        {"file": "39.xml", "prezzo": 2.88, "q": 2, "totale": 5.75},
        {"file": "39.xml", "prezzo": 3.83, "q": 4, "totale": 15.32},
        {"file": "39.xml", "prezzo": 2.88, "q": 2, "totale": 5.75},
    )
    out = _uno(df)
    assert len(out) == 1
    assert out.loc[0, "q"] == 8
    assert out.loc[0, "prezzo"] == pytest.approx((2.88 * 2 + 3.83 * 4 + 2.88 * 2) / 8)
    assert out.loc[0, "totale"] == pytest.approx(5.75 + 15.32 + 5.75)


def test_fatture_diverse_restano_acquisti_diversi():
    df = _righe({"file": "39.xml", "prezzo": 2.0, "q": 1}, {"file": "40.xml", "prezzo": 3.0, "q": 1})
    assert _uno(df)["prezzo"].tolist() == [2.0, 3.0]


def test_lo_stesso_nome_file_in_due_sedi_non_si_fonde():
    """41 nomi di file compaiono in piu' sedi sul live (14/10/2026)."""
    df = _righe({"file": "1.xml", "prezzo": 2.0, "q": 1}, {"file": "1.xml", "prezzo": 9.0, "q": 1, "sede": "B"})
    assert len(_uno(df)) == 2


def test_unita_diverse_nella_stessa_fattura_non_si_fondono():
    """Decisione di Mattia: un cartone mediato con un pezzo e' un prezzo senza senso."""
    df = _righe(
        {"file": "1.xml", "prezzo": 84.55, "q": 1, "um": "CT"},
        {"file": "1.xml", "prezzo": 4.90, "q": 16, "um": " pz "},
        {"file": "1.xml", "prezzo": 5.10, "q": 16, "um": "PZ"},
    )
    out = _uno(df)
    assert sorted(out["q"].tolist()) == [1, 32], "PZ e ' pz ' sono la stessa unita', CT no"


def test_righe_senza_file_restano_acquisti_a_se():
    df = _righe({"file": None, "prezzo": 1.0, "q": 1}, {"file": "", "prezzo": 2.0, "q": 1}, {"file": None, "prezzo": 3.0, "q": 1})
    out = _uno(df)
    assert out["prezzo"].tolist() == [1.0, 2.0, 3.0]
    assert out["file"].isna().all()


def test_quantita_mancante_vale_uno():
    df = _righe({"file": "1.xml", "prezzo": 10.0, "q": None}, {"file": "1.xml", "prezzo": 20.0, "q": 3})
    assert _uno(df).loc[0, "prezzo"] == pytest.approx((10 + 60) / 4)


def test_quantita_sommata_non_positiva_ripiega_sulla_media_semplice():
    df = _righe({"file": "1.xml", "prezzo": 3.0, "q": 0}, {"file": "1.xml", "prezzo": 5.0, "q": 0})
    assert _uno(df).loc[0, "prezzo"] == pytest.approx(4.0)


def test_lo_spareggio_a_parita_di_data_e_il_nome_del_file():
    """La RPC ordina `data, file_origine, unita'` con COLLATE "C": l'ultimo
    acquisto del giorno e' lo stesso nelle due pagine."""
    df = _righe({"file": "B.xml", "prezzo": 2.0, "q": 1}, {"file": "A.xml", "prezzo": 1.0, "q": 1}, {"file": "a.xml", "prezzo": 3.0, "q": 1})
    assert _uno(df)["file"].tolist() == ["A.xml", "B.xml", "a.xml"]


def test_le_date_ordinano_prima_del_file():
    df = _righe({"file": "A.xml", "prezzo": 2.0, "q": 1, "data": "2026-05-01"}, {"file": "Z.xml", "prezzo": 1.0, "q": 1, "data": "2026-04-01"})
    assert _uno(df)["prezzo"].tolist() == [1.0, 2.0]


def test_massimo_e_prima_riga():
    df = _righe(
        {"file": "1.xml", "prezzo": 1.0, "q": 1, "categoria": "B", "descrizione": "prima"},
        {"file": "1.xml", "prezzo": 1.0, "q": 1, "categoria": "a", "descrizione": "seconda"},
        {"file": "1.xml", "prezzo": 1.0, "q": 1, "categoria": None, "descrizione": "terza"},
    )
    out = _uno(df)
    assert out.loc[0, "categoria"] == "a", "ordine dei caratteri, come COLLATE \"C\""
    assert out.loc[0, "descrizione"] == "prima"


def test_totale_tutto_mancante_resta_mancante():
    df = _righe({"file": "1.xml", "prezzo": 1.0, "q": 1, "totale": None}, {"file": "1.xml", "prezzo": 1.0, "q": 1, "totale": None})
    assert pd.isna(_uno(df).loc[0, "totale"])


def test_tabella_vuota():
    assert _uno(pd.DataFrame(columns=["sede", "prodotto", "fornitore", "file", "data", "prezzo", "q", "um"])).empty
