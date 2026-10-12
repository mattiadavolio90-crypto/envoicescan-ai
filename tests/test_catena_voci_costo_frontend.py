"""«Voci di costo» della scheda Margini di catena (Mattia, 12/10/2026).

La tabella gira i dati dei margini: righe = voci (Spese F&B, Spese generali,
Personale, Margine), colonne = punti vendita + gruppo, in % sul fatturato
netto. Qui si esegue con node la logica pura che decide cosa si legge e cosa
si colora (`lib/catena-confronti.ts`) e cosa finisce nel file Excel
(`lib/catena-export.ts`). Il rendering non ha runner: e' la parte che manca.
"""
import pytest

from tests.helpers_ts import esegui_ts


def _pv(nome, fb=None, spese=None, pers=None, margine=None, incompleti=False):
    return {
        "ristorante_id": f"id-{nome}", "nome": nome,
        "margine_perc": margine, "fatturato": 10_000, "coperti": 0,
        "scontrino_medio": None, "mp_per_coperto": None,
        "dati_incompleti": incompleti,
        "food_cost_perc": fb, "spese_generali_perc": spese, "personale_perc": pers,
    }


GRUPPO = _pv("Gruppo X", fb=30.0, spese=20.0, pers=25.0, margine=25.0)


def _voci(righe, gruppo=GRUPPO, n_incompleti=0):
    return esegui_ts(
        "lib/catena-confronti",
        "emit(m.vociCostoCatena(input.r, input.g, input.n));",
        argomento={"r": righe, "g": gruppo, "n": n_incompleti},
        richiede=["vociCostoCatena"],
    )


def _per_chiave(voci):
    return {v["key"]: v for v in voci}


def test_le_quattro_voci_nell_ordine_del_conto_economico():
    voci = _voci([_pv("A", 30, 20, 25, 25)])
    assert [(v["key"], v["label"]) for v in voci] == [
        ("food_cost_perc", "Spese F&B"),
        ("spese_generali_perc", "Spese generali"),
        ("personale_perc", "Personale"),
        ("margine_perc", "Margine"),
    ]


def test_le_colonne_seguono_le_righe_e_portano_i_valori():
    voci = _per_chiave(_voci([_pv("A", 30, 20, 25, 25), _pv("B", 35, 15, 30, 20)]))
    assert voci["spese_generali_perc"]["per_pv"] == [
        {"ristorante_id": "id-A", "valore": 20},
        {"ristorante_id": "id-B", "valore": 15},
    ]
    assert voci["personale_perc"]["gruppo"] == 25.0


def test_per_le_spese_vince_il_basso_per_il_margine_l_alto():
    """La direzione e' per voce: un margine colorato come un costo farebbe
    verde il locale che guadagna meno."""
    voci = _per_chiave(_voci([
        _pv("A", fb=30, spese=20, pers=25, margine=25),
        _pv("B", fb=35, spese=15, pers=30, margine=20),
        _pv("C", fb=32, spese=18, pers=28, margine=22),
    ]))
    assert (voci["food_cost_perc"]["best"], voci["food_cost_perc"]["worst"]) == (30, 35)
    assert (voci["spese_generali_perc"]["best"], voci["spese_generali_perc"]["worst"]) == (15, 20)
    assert (voci["personale_perc"]["best"], voci["personale_perc"]["worst"]) == (25, 30)
    assert (voci["margine_perc"]["best"], voci["margine_perc"]["worst"]) == (25, 20)


def test_la_sede_incompleta_si_legge_ma_non_entra_nel_confronto():
    """B e' incompleta: il suo F&B (10%) e' il piu' basso, ma con l'incasso o le
    fatture dell'ultimo mese mancanti e' spostato. Si mostra, non vince."""
    voci = _per_chiave(_voci([
        _pv("A", fb=30, spese=20, pers=25, margine=25),
        _pv("B", fb=10, spese=40, incompleti=True),
        _pv("C", fb=35, spese=18, pers=28, margine=19),
    ], n_incompleti=1))
    fb = voci["food_cost_perc"]
    assert {"ristorante_id": "id-B", "valore": 10} in fb["per_pv"]
    assert (fb["best"], fb["worst"]) == (30, 35)
    assert (voci["spese_generali_perc"]["best"], voci["spese_generali_perc"]["worst"]) == (18, 20)


def test_con_un_solo_pv_confrontabile_niente_colori():
    voci = _per_chiave(_voci([_pv("A", 30, 20, 25, 25), _pv("B", 10, 40, incompleti=True)], n_incompleti=1))
    assert (voci["food_cost_perc"]["best"], voci["food_cost_perc"]["worst"]) == (None, None)


def test_valore_mancante_resta_null_non_zero():
    """Un worker vecchio non manda i campi: «—», non «0%» colorato migliore."""
    vecchio = {k: v for k, v in _pv("A").items() if k not in ("spese_generali_perc", "personale_perc")}
    voci = _per_chiave(_voci([vecchio, _pv("B", 30, 20, 25, 25)]))
    assert voci["spese_generali_perc"]["per_pv"][0]["valore"] is None
    assert voci["spese_generali_perc"]["best"] is None


@pytest.mark.parametrize("n, atteso", [(0, False), (1, True), (3, True)])
def test_con_una_sede_incompleta_ogni_voce_del_gruppo_e_parziale(n, atteso):
    """Non solo il margine: una sede coi costi e senza l'incasso gonfia anche
    il F&B del gruppo."""
    voci = _voci([_pv("A", 30, 20, 25, 25)], n_incompleti=n)
    assert [v["gruppoParziale"] for v in voci] == [atteso] * 4


@pytest.mark.parametrize("valore, atteso", [
    (15, "text-positivo font-semibold"),
    (20, "text-negativo font-semibold"),
    (18, ""),
    (None, ""),
])
def test_tono_della_cella(valore, atteso):
    out = esegui_ts(
        "lib/catena-confronti",
        "emit(m.toneVoce(input.v, input.r));",
        argomento={"v": valore, "r": {"best": 15, "worst": 20}},
        richiede=["toneVoce"],
    )
    assert out == atteso


def test_tutti_uguali_nessun_colore():
    out = esegui_ts(
        "lib/catena-confronti",
        "emit([m.toneVoce(20, input), m.toneVoce(20, {best: null, worst: null})]);",
        argomento={"best": 20, "worst": 20},
        richiede=["toneVoce"],
    )
    assert out == ["", ""]


def test_rigaextremes_senza_direzione_resta_quella_dello_spreco():
    """L'estensione con `altoMeglio` non cambia lo spreco (default basso = meglio)."""
    out = esegui_ts(
        "lib/catena-confronti",
        "emit([m.rigaExtremes(input), m.rigaExtremes(input, true)]);",
        argomento={"per_pv": [{"valore": 3.0}, {"valore": 9.0}, {"valore": None}]},
        richiede=["rigaExtremes"],
    )
    assert out == [{"best": 3.0, "worst": 9.0}, {"best": 9.0, "worst": 3.0}]


# ─── Il foglio Excel ────────────────────────────────────────────────────────

def _export(righe, n_incompleti=0):
    voci = _voci(righe, n_incompleti=n_incompleti)
    return esegui_ts(
        "lib/catena-export",
        "emit({h: m.headerVoci(input.r, input.g), righe: m.righeExportVoci(input.v, input.r, input.g)});",
        argomento={"r": righe, "g": GRUPPO, "v": voci},
        richiede=["headerVoci", "righeExportVoci"],
    )


def test_il_foglio_ha_una_colonna_per_pv_e_il_gruppo():
    out = _export([_pv("A", 30, 20, 25, 25), _pv("B", 10, 40, incompleti=True)], n_incompleti=1)
    assert out["h"] == ["Voce (% sul fatturato netto)", "A", "B (incompleto)", "Gruppo X"]


def test_le_righe_del_foglio_come_a_schermo():
    """La sede incompleta esce coi suoi F&B e spese (a schermo ci sono), «—» su
    personale e margine. Il gruppo esce «(parziale)» su ogni voce."""
    out = _export([_pv("A", 30, 20, 25, 25), _pv("B", 10, 40, incompleti=True)], n_incompleti=1)
    assert out["righe"] == [
        {"Voce (% sul fatturato netto)": "Spese F&B", "A": 30, "B (incompleto)": 10, "Gruppo X": "30 (parziale)"},
        {"Voce (% sul fatturato netto)": "Spese generali", "A": 20, "B (incompleto)": 40, "Gruppo X": "20 (parziale)"},
        {"Voce (% sul fatturato netto)": "Personale", "A": 25, "B (incompleto)": "—", "Gruppo X": "25 (parziale)"},
        {"Voce (% sul fatturato netto)": "Margine", "A": 25, "B (incompleto)": "—", "Gruppo X": "25 (parziale)"},
    ]


def test_senza_incompleti_il_gruppo_esce_col_numero():
    out = _export([_pv("A", 30, 20, 25, 25)])
    assert out["righe"][0]["Gruppo X"] == 30
