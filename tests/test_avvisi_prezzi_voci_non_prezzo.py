"""Gli avvisi prezzi (`calcola_alert`) seguono le stesse regole dell'Osservatorio.

`calcola_alert` alimenta la Home (avvisi e ribassi), la chat, le notifiche dopo
il caricamento e il briefing. Fino al 12/10/2026 l'Osservatorio escludeva le
cauzioni e metteva «da controllare» i salti di 10 volte o piu', mentre gli
avvisi no: la Home avrebbe detto «ADDEBITO CAUZIONI -99,9%» fra i ribassi su
una riga che l'Osservatorio non mostra piu'. La definizione e' unica
(`utils/voci_prezzo.py`); qui si prova che `calcola_alert` la usa davvero.
"""
import pandas as pd

from services.db_service import calcola_alert


def _righe(desc, prezzi, *, categoria="BEVANDE", fornitore="PARTESA"):
    return [
        {"Descrizione": desc, "Fornitore": fornitore, "DataDocumento": f"2026-0{i + 3}-10",
         "PrezzoUnitario": p, "Categoria": categoria, "FileOrigine": f"{desc}-{i}.xml", "Quantita": 2.0}
        for i, p in enumerate(prezzi)
    ]


def _prodotti(df):
    return sorted(calcola_alert(pd.DataFrame(df), soglia_minima=5.0)["Prodotto"].str.replace(" ⚠️ >6m", ""))


def test_le_cauzioni_non_sono_un_avviso_qualunque_sia_la_categoria():
    righe = _righe("ADDEBITO CAUZIONI", [150.54, 165.0], categoria="VARIE BAR") + _righe("BIB COCA COLA", [15.80, 17.58])
    # 150 -> 165 e' un +9,6%: senza l'esclusione passerebbe la soglia.
    assert _prodotti(righe) == ["BIB COCA COLA"]


def test_un_cambio_di_confezione_non_e_un_avviso():
    righe = _righe("BEVANDA ALLE ERBE", [0.52, 14.0]) + _righe("LIMONE", [17.0, 20.0], categoria="FRUTTA")
    assert _prodotti(righe) == ["LIMONE"]


def test_appena_sotto_le_dieci_volte_e_ancora_un_avviso():
    assert _prodotti(_righe("AGLIO", [4.5, 44.9], categoria="VERDURE")) == ["AGLIO"]


def test_la_cauzione_si_riconosce_anche_scritta_minuscola():
    righe = _righe("Addebito cauzioni vuoti", [150.54, 165.0]) + _righe("BIB COCA COLA", [15.80, 17.58])
    assert _prodotti(righe) == ["BIB COCA COLA"]


def test_la_stella_su_un_fornitore_dal_nome_lungo_arriva_agli_avvisi():
    """`calcola_alert` tronca il fornitore a 20 caratteri e la stella lo salva
    intero: fino al 12/10/2026 il confronto falliva sempre, e in modalita'
    «solo preferiti» i prodotti di 10 stelle su 19 non arrivavano mai in Home."""
    from services.price_impact_service import _filtra_rilevanti, _pref_match_key

    forn = "LA GE' GE' PESCA DI GAVAZZI SANTO & C. S.R.L"
    df_alert = calcola_alert(pd.DataFrame(_righe("SALMONE NORVEGIA", [10.0, 12.0], categoria="PESCE", fornitore=forn)), 5.0)
    stelle = {_pref_match_key("SALMONE NORVEGIA", forn)}
    tenute = _filtra_rilevanti(df_alert, pd.Series(True, index=df_alert.index), set(), stelle)
    assert list(tenute["Prodotto"]) == ["SALMONE NORVEGIA"]
