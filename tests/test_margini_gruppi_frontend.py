"""Tabella Margini a gruppi apribili (fase C4, 04/10/2026, SCREEN 15 di Mattia).

La tabella mostra le TESTATE — Incasso, Spese F&B, Spese generali, Costo
personale — con Margine F&B e MOL sempre visibili; il dettaglio compare solo
aprendo il gruppo. La riga «= Spese Generali + Personale» e' sparita.

La struttura (ordine, gruppo, testata) vive in `lib/margini-aggregati.ts`
(`RIGHE_MARGINI`) e si ESEGUE qui con node: prima i blocchi si riconoscevano da
indici scritti a mano (`SEP_BEFORE = {4, 8, 12}`), che con le righe che
compaiono e spariscono non vogliono piu' dire niente.

Cosa NON copre: il rendering React (chevron, aria-expanded, stato). Di quello si
provano qui solo le funzioni che il .tsx ritaglia o chiama, piu' i punti di
chiamata letti dal sorgente dove un'esecuzione non e' possibile.
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

_MODULO = "lib/margini-aggregati"
_TABELLA = Path("apps/web/src/app/(app)/margini/calcolo-tab.tsx")
_DEMO_DATI = Path("apps/web/src/lib/demo-data.ts")
_DEMO_SCHERMO = Path("apps/web/src/components/demo/screens/demo-margini.tsx")

_TESTATE_E_RISULTATI = [
    "fatturato_netto", "costi_fb_totali", "primo_margine",
    "costi_spese_totali", "costi_personale", "mol",
]
_DETTAGLIO = {
    "incasso": ["fatturato_iva10", "fatturato_iva22", "altri_ricavi_noiva"],
    "fb": ["costi_fb_auto", "altri_costi_fb"],
    "spese": ["costi_spese_auto", "altri_costi_spese"],
    "personale": ["costo_dipendenti", "costo_personale_extra", "costo_personale_chiamata"],
}
_TESTATA = {
    "incasso": "fatturato_netto", "fb": "costi_fb_totali",
    "spese": "costi_spese_totali", "personale": "costi_personale",
}


def _visibili(espansi):
    """Le chiavi delle righe visibili con questi gruppi aperti."""
    return esegui_ts(
        _MODULO,
        "emit(m.righeVisibili(m.RIGHE_MARGINI, input).map((r) => r.key));",
        argomento=espansi,
        richiede=["righeVisibili"],
    )


def _atteso_con_aperti(aperti):
    out = []
    for k in _TESTATE_E_RISULTATI:
        out.append(k)
        for g, testata in _TESTATA.items():
            if k == testata and g in aperti:
                out.extend(_DETTAGLIO[g])
    return out


def _struttura():
    return esegui_ts(
        _MODULO,
        "emit(m.RIGHE_MARGINI.map((r) => ({ key: r.key, gruppo: r.gruppo, testata: !!r.testata })));",
        richiede=["righeVisibili"],
    )


# ───────────────────────── chiusi di default ────────────────────────────────

def test_all_apertura_si_vedono_solo_testate_margine_e_mol():
    """La tabella corta della richiesta: sei righe, nell'ordine del conto economico."""
    iniziali = esegui_ts(
        _MODULO, "emit(m.gruppiEspansiIniziali());",
        richiede=["gruppiEspansiIniziali"],
    )
    assert _visibili(iniziali) == _TESTATE_E_RISULTATI


def test_il_componente_parte_dai_gruppi_chiusi_e_senza_memoria():
    """Lo stato iniziale del .tsx e' quello della funzione, non un letterale.

    E niente localStorage: Mattia vuole la tabella corta a ogni apertura.
    """
    src = _TABELLA.read_text(encoding="utf-8")
    assert "useState<GruppoMargini[]>(gruppiEspansiIniziali)" in src
    righe_codice = [
        r for r in src.splitlines() if not r.lstrip().startswith(("//", "*", "/*"))
    ]
    assert not [r for r in righe_codice if "localStorage" in r or "sessionStorage" in r]


# ───────────────────── apertura di un solo gruppo ───────────────────────────

@pytest.mark.parametrize("gruppo", sorted(_DETTAGLIO))
def test_aprire_un_gruppo_mostra_il_suo_dettaglio_e_solo_quello(gruppo):
    espansi = esegui_ts(
        _MODULO,
        "emit(m.alternaGruppo(m.gruppiEspansiIniziali(), input));",
        argomento=gruppo,
        richiede=["alternaGruppo", "gruppiEspansiIniziali"],
    )
    assert espansi == [gruppo]
    visibili = _visibili(espansi)
    assert visibili == _atteso_con_aperti({gruppo})
    for altro, righe in _DETTAGLIO.items():
        if altro != gruppo:
            assert not set(righe) & set(visibili), f"aperto {gruppo}, si vede anche {altro}"


def test_riaprire_lo_stesso_gruppo_lo_richiude_e_non_tocca_gli_altri():
    res = esegui_ts(
        _MODULO,
        """
        const a = m.alternaGruppo([], "fb");
        const b = m.alternaGruppo(a, "personale");
        const c = m.alternaGruppo(b, "fb");
        emit({ a, b, c });
        """,
        richiede=["alternaGruppo"],
    )
    assert res["a"] == ["fb"]
    assert sorted(res["b"]) == ["fb", "personale"]
    assert res["c"] == ["personale"]


def test_tutti_aperti_mostrano_tutte_le_righe_nell_ordine():
    tutte = [r["key"] for r in _struttura()]
    assert _visibili(sorted(_DETTAGLIO)) == tutte
    assert tutte == _atteso_con_aperti(set(_DETTAGLIO))


# ───────────────────────────── separatori ───────────────────────────────────

def _separatori(espansi):
    return esegui_ts(
        _MODULO,
        """
        const v = m.righeVisibili(m.RIGHE_MARGINI, input);
        emit(v.map((r, i) => [r.key, m.separatoreSopra(r, v[i - 1] ?? null), m.rigaPiede(r)]));
        """,
        argomento=espansi,
        richiede=["separatoreSopra", "rigaPiede", "righeVisibili"],
    )


@pytest.mark.parametrize("espansi", [[], ["incasso"], ["fb"], ["spese"], ["personale"],
                                     ["incasso", "fb", "spese", "personale"]])
def test_separatore_sopra_ogni_blocco_mai_dentro_un_gruppo(espansi):
    struttura = {r["key"]: r for r in _struttura()}
    righe = _separatori(espansi)
    assert righe[0][1] is False, "niente aria sopra la prima riga della tabella"
    for i, (key, sep, _piede) in enumerate(righe):
        if i == 0:
            continue
        r = struttura[key]
        if r["testata"] or r["gruppo"] is None:
            assert sep is True, f"manca il separatore sopra {key} (aperti: {espansi})"
        else:
            assert sep is False, f"separatore dentro il gruppo {r['gruppo']}, sopra {key}"


def test_due_sempre_visibili_di_fila_restano_separate():
    """Margine F&B e MOL sono blocchi a se': anche adiacenti, ognuno ha la sua aria."""
    assert esegui_ts(
        _MODULO,
        'emit(m.separatoreSopra({ key: "mol", gruppo: null }, { key: "primo_margine", gruppo: null }));',
        richiede=["separatoreSopra"],
    ) is True


def test_il_piede_e_solo_il_mol():
    righe = _separatori(sorted(_DETTAGLIO))
    assert [k for k, _s, piede in righe if piede] == ["mol"]


def _estrai_pad_y() -> str:
    src = _TABELLA.read_text(encoding="utf-8")
    inizio = src.index("function padYRiga(")
    fine = src.index("\n}\n", inizio) + len("\n}\n")
    corpo = src[inizio:fine]
    corpo = corpo.replace("row: RowDef, precedente: RowDef | null): string {", "row, precedente) {")
    assert "RowDef" not in corpo, "firma di padYRiga cambiata: aggiorna il ritaglio"
    return corpo


def test_la_tabella_usa_le_regole_della_riga_non_gli_indici():
    """`padYRiga` del .tsx, ESEGUITA: e' lei che decide l'aria di ogni <td>."""
    res = esegui_ts(
        _MODULO,
        "const { separatoreSopra, rigaPiede } = m;\n" + _estrai_pad_y() + """
        const v = m.righeVisibili(m.RIGHE_MARGINI, input);
        emit(v.map((r, i) => [r.key, padYRiga(r, v[i - 1] ?? null)]));
        """,
        argomento=["personale"],
        richiede=["separatoreSopra", "rigaPiede"],
    )
    assert res == [
        ["fatturato_netto", "py-2"],
        ["costi_fb_totali", "pt-4 pb-2"],
        ["primo_margine", "pt-4 pb-2"],
        ["costi_spese_totali", "pt-4 pb-2"],
        ["costi_personale", "pt-4 pb-2"],
        ["costo_dipendenti", "py-2"],
        ["costo_personale_extra", "py-2"],
        ["costo_personale_chiamata", "py-2"],
        ["mol", "py-3.5"],
    ]


def test_niente_piu_indici_fissi_e_si_disegnano_le_righe_visibili():
    src = _TABELLA.read_text(encoding="utf-8")
    for vecchio in ("SEP_BEFORE", "IDX_PIEDE", "ROWS.map(("):
        assert vecchio not in src, f"{vecchio} e' tornato: la tabella ignora i gruppi"
    assert "righeVisibili(ROWS, espansi)" in src
    # desktop e vista stretta disegnano entrambe la lista filtrata
    assert src.count("righe.map((row, ri)") == 2
    assert "key={row.key}" in src


# ─────────────────────── riga Chiamata e aspetto ────────────────────────────

def _aspetto():
    """L'oggetto ASPETTO del .tsx, ritagliato ed eseguito: e' letterale puro."""
    src = _TABELLA.read_text(encoding="utf-8")
    inizio = src.index("const ASPETTO: Record<ChiaveRigaMargini, Aspetto> = {")
    fine = src.index("\n};\n", inizio) + len("\n};\n")
    corpo = src[inizio:fine].replace(": Record<ChiaveRigaMargini, Aspetto>", "")
    return corpo


def _righe_complete():
    return esegui_ts(
        _MODULO,
        _aspetto() + """
        emit(m.RIGHE_MARGINI.map((r) => {
          const row = { ...r, ...ASPETTO[r.key] };
          return { ...row, apreCosto: m.apreCostoPersonale(row) };
        }));
        """,
        richiede=["apreCostoPersonale"],
    )


def test_la_chiamata_e_una_voce_del_personale_modificabile():
    righe = {r["key"]: r for r in _righe_complete()}
    ch = righe["costo_personale_chiamata"]
    assert ch["gruppo"] == "personale"
    assert not ch.get("testata")
    assert ch["label"] == "Chiamata"
    assert ch["type"] == "input-editable"
    assert ch["field"] == "costo_personale_chiamata"
    assert [righe[k]["label"] for k in _DETTAGLIO["personale"]] == ["Lordo", "Ore extra", "Chiamata"]


def test_celle_che_aprono_il_modulo_del_personale():
    """Le tre voci E la testata, anche a gruppo chiuso: il briefing manda su
    /margini per il personale mancante e l'inserimento resta a un clic.
    Nessun'altra riga apre il modulo del personale."""
    righe = _righe_complete()
    assert [r["key"] for r in righe if r["apreCosto"]] == [
        "costi_personale", "costo_dipendenti", "costo_personale_extra", "costo_personale_chiamata",
    ]


def test_le_celle_usano_il_predicato_del_modulo():
    src = _TABELLA.read_text(encoding="utf-8")
    assert "if (apreCostoPersonale(row)) {" in src
    assert "const isPersonale = apreCostoPersonale(row);" in src


def test_ogni_riga_della_struttura_ha_il_suo_aspetto():
    righe = _righe_complete()
    assert all(r.get("label") for r in righe)
    testate = {r["gruppo"]: r["label"] for r in righe if r.get("testata")}
    assert testate == {
        "incasso": "Incasso", "fb": "Spese F&B",
        "spese": "Spese generali", "personale": "Costo personale",
    }


def test_rows_del_componente_nasce_dalla_struttura():
    src = _TABELLA.read_text(encoding="utf-8")
    assert "const ROWS: RowDef[] = RIGHE_MARGINI.map((r) => ({ ...r, ...ASPETTO[r.key] }));" in src


# ─────────────────────────── totale_costi sparita ───────────────────────────

def test_la_riga_spese_piu_personale_non_c_e_piu():
    res = esegui_ts(
        _MODULO,
        "emit({ righe: m.RIGHE_MARGINI.map((r) => r.key), derive: Object.keys(m.DERIVE) });",
        richiede=["rowVal"],
    )
    assert "totale_costi" not in res["righe"]
    assert "totale_costi" not in res["derive"]
    for p in (_TABELLA, _DEMO_DATI, _DEMO_SCHERMO):
        testo = p.read_text(encoding="utf-8")
        assert "totale_costi" not in testo, f"{p} cita ancora totale_costi"
        assert "= Spese Generali + Personale" not in testo, f"{p} ha ancora la riga"


# ───────────────────────────── nessuna orfana ───────────────────────────────

def test_ogni_riga_sta_in_un_gruppo_o_e_sempre_visibile():
    righe = _struttura()
    sempre = [r["key"] for r in righe if r["gruppo"] is None]
    assert sempre == ["primo_margine", "mol"]
    gruppi = {}
    for i, r in enumerate(righe):
        if r["gruppo"] is not None:
            assert r["gruppo"] in _DETTAGLIO, f"{r['key']} in un gruppo sconosciuto"
            gruppi.setdefault(r["gruppo"], []).append((i, r))
    for g, membri in gruppi.items():
        indici = [i for i, _r in membri]
        assert indici == list(range(indici[0], indici[0] + len(indici))), f"gruppo {g} spezzato"
        assert membri[0][1]["testata"] and membri[0][1]["key"] == _TESTATA[g], (
            f"la testata di {g} non e' in cima"
        )
        assert sum(1 for _i, r in membri if r["testata"]) == 1
        assert [r["key"] for _i, r in membri[1:]] == _DETTAGLIO[g]


# ─────────────────────────────── demo ───────────────────────────────────────

def test_la_demo_ha_tre_voci_del_personale_che_quadrano():
    """La Chiamata e' TOLTA dal lordo: personale e MOL restano quelli del tour."""
    src = _DEMO_DATI.read_text(encoding="utf-8")
    for nome, personale, mol in (
        ("demoMarginiApr", 18000, 14400),
        ("demoMarginiMag", 18700, 13100),
        ("demoMarginiTot", 36700, 27500),
    ):
        blocco = src[src.index(f"export const {nome}"):]
        blocco = blocco[:blocco.index("\n};")]
        v = {k: float(n) for k, n in re.findall(r"^\s+(\w+): (-?\d+(?:\.\d+)?),$", blocco, re.M)}
        assert v["costo_personale_chiamata"] > 0, nome
        assert v["costo_dipendenti"] + v["costo_personale_extra"] + v["costo_personale_chiamata"] == personale, nome
        assert v["costi_personale"] == personale and v["mol"] == mol, nome
        assert v["fatturato_netto"] - v["costi_fb_totali"] - v["costi_spese_totali"] - v["costi_personale"] == v["mol"], nome
    kpi = src[src.index("export const demoKpi"):]
    assert re.search(r"costo_personale: 18700,", kpi[:kpi.index("\n};")])


def test_la_demo_tiene_l_ancora_del_mol():
    assert 'data-demo-anchor="mol"' in _DEMO_SCHERMO.read_text(encoding="utf-8")
