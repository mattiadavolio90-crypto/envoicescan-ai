"""La logica della scheda «Prezzi» di Analisi catena (`lib/catena-prezzi.ts`).

Eseguita con node, non letta: decide quali righe si vedono col filtro del punto
vendita, l'etichetta «in N PV su M» e i KPI in cima. Il punto delicato e' il
filtro per PV sui divari: il divario e' di piu' sedi, e il suo «pagato in piu'»
attribuito a una sola le metterebbe in conto i costi delle altre.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-prezzi"


FUNZIONI = ("etichettaDiffusione", "filtraVariazioni", "filtraDivari", "totaliPrezzi", "pvDeiPrezzi",
            "chiaveStellaCatena", "stelleIniziali")


def _ts(codice, argomento=None):
    return esegui_ts(MODULO, codice, argomento=argomento, richiede=FUNZIONI)


def _var(rid, prodotto, impatto, perc=10.0, stesso=1, confr=1, fornitore="PARTESA"):
    return {
        "ristorante_id": rid, "nome_pv": f"PV {rid}", "prodotto": prodotto, "categoria": "BEVANDE",
        "fornitore": fornitore, "storico_valori": [1, 2], "media": 1.5, "penultimo": 1, "ultimo": 2,
        "aumento_perc": perc, "data": "2026-09-01", "trend": "⬆", "impatto_stimato": impatto,
        "delta_euro": 1, "n_pv_stesso_verso": stesso, "n_pv_confrontabili": confr,
    }


def _div(prodotto, per_pv, fornitore="PARTESA"):
    return {
        "prodotto": prodotto, "categoria": "BEVANDE", "fornitore": fornitore,
        "prezzo_min": min(p[1] for p in per_pv), "prezzo_max": max(p[1] for p in per_pv),
        "divario_perc": 10, "extra_stimato": sum(p[2] for p in per_pv),
        "per_pv": [
            {"ristorante_id": rid, "nome_pv": nome, "ultimo": prezzo, "data": "2026-09-01",
             "scarto_perc": 0, "extra_stimato": extra}
            for rid, prezzo, extra, nome in (p if len(p) == 4 else (*p, f"PV {p[0]}") for p in per_pv)
        ],
    }


@pytest.mark.parametrize("stesso, confr, atteso", [
    (3, 4, "In 3 PV su 4"),
    (2, 2, "In 2 PV su 2"),
    (1, 4, "Solo questo PV su 4"),
    (1, 1, None),
])
def test_etichetta_della_diffusione(stesso, confr, atteso):
    assert _ts("emit(m.etichettaDiffusione(input))",
               {"n_pv_stesso_verso": stesso, "n_pv_confrontabili": confr}) == atteso


def test_filtro_pv_e_ordine_per_impatto_assoluto():
    righe = [_var("a", "LIMONE", 5), _var("b", "SALMONE", -40), _var("a", "COCA", 12), _var("b", "PANE", 1)]
    tutte = _ts('emit(m.filtraVariazioni(input, {pv: "", ricerca: ""}).map(v => v.prodotto))', righe)
    assert tutte == ["SALMONE", "COCA", "LIMONE", "PANE"]
    solo_a = _ts('emit(m.filtraVariazioni(input, {pv: "a", ricerca: ""}).map(v => v.prodotto))', righe)
    assert solo_a == ["COCA", "LIMONE"]


def test_ricerca_su_prodotto_e_fornitore_senza_maiuscole():
    righe = [_var("a", "LIMONE", 5, fornitore="MEFON"), _var("a", "COCA", 3, fornitore="PARTESA")]
    assert _ts('emit(m.filtraVariazioni(input, {pv: "", ricerca: " mef "}).map(v => v.prodotto))', righe) == ["LIMONE"]
    assert _ts('emit(m.filtraVariazioni(input, {pv: "", ricerca: "coca"}).map(v => v.prodotto))', righe) == ["COCA"]


def test_divari_col_pv_scelto_restano_quelli_in_cui_c_e():
    divari = [_div("COCA", [("a", 15.8, 0), ("b", 17.58, 32)]), _div("LIMONE", [("b", 17, 0), ("c", 32, 60)])]
    assert _ts('emit(m.filtraDivari(input, {pv: "a", ricerca: ""}).map(d => d.prodotto))', divari) == ["COCA"]
    assert _ts('emit(m.filtraDivari(input, {pv: "b", ricerca: ""}).map(d => d.prodotto))', divari) == ["COCA", "LIMONE"]


def test_il_pagato_in_piu_di_un_pv_e_solo_il_suo():
    """Con «b» scelto: 32 (COCA) + 0 (LIMONE, dove b e' il piu' basso). Il totale
    dei due divari e' 92: attribuirlo a b gli metterebbe in conto i 60 di «c»."""
    divari = [_div("COCA", [("a", 15.8, 0), ("b", 17.58, 32)]), _div("LIMONE", [("b", 17, 0), ("c", 32, 60)])]
    per_b = _ts('emit(m.totaliPrezzi([], input, "b"))', divari)
    tutti = _ts('emit(m.totaliPrezzi([], input, ""))', divari)
    assert (per_b["divari"], per_b["extraDivari"]) == (2, 32)
    assert (tutti["divari"], tutti["extraDivari"]) == (2, 92)


def test_kpi_delle_variazioni():
    righe = [_var("a", "LIMONE", 5.555, perc=12), _var("b", "SALMONE", -40, perc=-8), _var("a", "COCA", 12.004, perc=6)]
    t = _ts('emit(m.totaliPrezzi(input, [], ""))', righe)
    assert (t["aumenti"], t["cali"]) == (2, 1)
    assert t["impattoNetto"] == pytest.approx(-22.44, abs=0.001)


def test_elenco_pv_dai_due_elenchi_in_ordine_di_nome():
    data = {
        "variazioni": [_var("z", "COCA", 1)],
        "divari": [_div("LIMONE", [("b", 17, 0, "Arese"), ("c", 32, 60, "Bollate")])],
        "soglia": 5, "periodo_label": "Anno 2026", "acquisti_nel_periodo": 10, "divario_finestra_giorni": 60,
    }
    assert _ts("emit(m.pvDeiPrezzi(input))", data) == [
        {"id": "b", "nome": "Arese"}, {"id": "c", "nome": "Bollate"}, {"id": "z", "nome": "PV z"},
    ]
    assert _ts("emit(m.pvDeiPrezzi(null))") == []


def test_da_controllare_fuori_da_tutti_e_dentro_la_sua_vista():
    righe = [_var("a", "BEVANDA", -1319, perc=-97), _var("a", "COCA", 12), _var("b", "LIMONE", 5)]
    righe[0]["da_controllare"] = True
    tutti = _ts('emit(m.filtraVariazioni(input, {pv: "", ricerca: ""}).map(v => v.prodotto))', righe)
    da_ctrl = _ts('emit(m.filtraVariazioni(input, {pv: "", ricerca: "", vista: "da_controllare"}).map(v => v.prodotto))', righe)
    assert (tutti, da_ctrl) == (["COCA", "LIMONE"], ["BEVANDA"])
    # I totali si fanno su «Tutti»: la riga da -1.319 non c'e'.
    assert _ts('emit(m.totaliPrezzi(m.filtraVariazioni(input, {pv: "", ricerca: ""}), [], ""))', righe)["impattoNetto"] == 17


def test_preferiti_dalle_stelle_della_scheda_non_dal_dato_iniziale():
    """La stella e' ottimistica: il filtro segue lo stato della scheda, e la
    stessa riga in due PV ha due stelle distinte."""
    righe = [_var("a", "SALMONE", 5, fornitore="ADC"), _var("b", "SALMONE", 4, fornitore="ADC")]
    righe[0]["preferito"] = True
    iniziali = _ts("emit([...m.stelleIniziali(input)])", righe)
    assert iniziali == ["a|SALMONE|ADC"]
    solo_b = _ts('emit(m.filtraVariazioni(input, {pv: "", ricerca: "", vista: "preferiti"}, new Set(["b|SALMONE|ADC"])).map(v => v.ristorante_id))', righe)
    assert solo_b == ["b"]


def test_divari_da_controllare_e_preferiti_che_vale_tutti():
    divari = [_div("AGLIO", [("a", 4.5, 0), ("b", 45, 400)]), _div("COCA", [("a", 15.8, 0), ("b", 17.58, 32)])]
    divari[0]["da_controllare"] = True
    assert _ts('emit(m.filtraDivari(input, {pv: "", ricerca: ""}).map(d => d.prodotto))', divari) == ["COCA"]
    assert _ts('emit(m.filtraDivari(input, {pv: "", ricerca: "", vista: "da_controllare"}).map(d => d.prodotto))', divari) == ["AGLIO"]
    assert _ts('emit(m.filtraDivari(input, {pv: "", ricerca: "", vista: "preferiti"}).map(d => d.prodotto))', divari) == ["COCA"]
