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


# ─── Avvisi sui TAG (prezzo medio ponderato del tag, due meta' di 90 giorni) ──

def _avvisi_tag(monkeypatch, righe, descrizioni):
    """`_alert_tag` col vero `analizza_tag`: finte solo le due letture dal DB
    (tag e associazioni), il prezzo medio lo calcola il codice di produzione."""
    from datetime import date, timedelta
    from services import db_service, price_impact_service as pis

    monkeypatch.setattr(pis, "get_custom_tags", lambda u, r: [{"id": 1, "nome": "BIRRA"}])
    assoc = [{"descrizione_key": db_service._normalize_custom_tag_key(d), "descrizione": d, "fattore_kg": None}
             for d in descrizioni]
    monkeypatch.setattr(db_service, "get_custom_tag_prodotti_bulk", lambda ids, u: {1: assoc})
    oggi = date.today()
    df = pd.DataFrame([
        {"Descrizione": d, "Fornitore": "PARTESA", "DataDocumento": (oggi - timedelta(days=giorni)).isoformat(),
         "PrezzoUnitario": p, "Quantita": 1.0, "TotaleRiga": p, "UnitaMisura": "PZ",
         "Categoria": "BIRRE", "FileOrigine": f"{d}-{giorni}.xml"}
        for d, giorni, p in righe
    ])
    return pis._alert_tag("u", "r", df, 5.0)


def test_un_rincaro_vero_del_tag_e_un_avviso(monkeypatch):
    """Controllo positivo: senza questo i due test sotto sarebbero verdi a vuoto."""
    righe = [("FUSTO BIRRA", 70, 100.0), ("FUSTO BIRRA", 10, 120.0)]
    assert [a["nome"] for a in _avvisi_tag(monkeypatch, righe, ["FUSTO BIRRA"])] == ["BIRRA"]


def test_una_cauzione_nel_tag_non_fa_un_rincaro(monkeypatch):
    righe = [("FUSTO BIRRA", 70, 100.0), ("FUSTO BIRRA", 10, 100.0), ("ADDEBITO CAUZIONI", 10, 900.0)]
    assert _avvisi_tag(monkeypatch, righe, ["FUSTO BIRRA", "ADDEBITO CAUZIONI"]) == []


def test_un_cambio_di_confezione_nel_tag_non_e_un_avviso(monkeypatch):
    righe = [("FUSTO BIRRA", 70, 10.0), ("FUSTO BIRRA", 10, 100.0)]
    assert _avvisi_tag(monkeypatch, righe, ["FUSTO BIRRA"]) == []


def test_due_consegne_con_numero_d_ordine_sono_lo_stesso_prodotto():
    """Il nome con «ORDER n (m)» spezzava la serie anche in Home: due consegne,
    due gruppi da un acquisto, nessun avviso. Il prodotto diverso resta diverso."""
    righe = (_righe("SALMONI 5/6 SALMAR ORDER 2012258 (1007082)", [10.0]) +
             _righe("SALMONI 5/6 SALMAR ORDER 2012995 (1007786)", [12.0]) +
             _righe("SALMONI 5/6 MOWI ORDER 1 (1)", [10.0]) + _righe("SALMONI 5/6 MOWI ORDER 2 (2)", [10.0]))
    for i, r in enumerate(righe):
        r["DataDocumento"] = f"2026-0{3 + i % 2}-10"
    assert _prodotti(righe) == ["SALMONI 5/6 SALMAR"]


def test_la_stella_sulla_famiglia_combacia_con_l_avviso_senza_numero_d_ordine():
    from services.price_impact_service import _pref_match_key

    forn = "LA GE' GE' PESCA DI GAVAZZI SANTO & C. S.R.L"
    assert _pref_match_key("SALMONI 5/6 SALMAR ORDER 2012258 (1007082)", forn) == _pref_match_key("SALMONI 5/6 SALMAR", forn)
