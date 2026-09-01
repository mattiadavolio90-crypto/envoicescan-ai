"""Test dell'export Excel delle finestre di catena (`lib/catena-export.ts`).

Eseguono il TypeScript vero via node (`helpers_ts.esegui_ts`): `apps/web/` non
ha un runner proprio per scelta strutturale — `deploy-vercel.yml` si attiva su
`apps/web/**`, quindi un runner li' farebbe deployare la produzione a ogni
merge di test.

Cosa misurano: le celle che il cliente apre in Excel. Gli assert sono su
stringhe e oggetti INTERI, non su "contiene": un'intestazione sbagliata in modo
coerente passerebbe un assert di coerenza interna.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-export"

COLS = [
    {"key": "margine_perc", "label": "Margine %"},
    {"key": "fatturato", "label": "Fatturato"},
    {"key": "coperti", "label": "Coperti"},
    {"key": "scontrino_medio", "label": "Scontrino medio"},
    {"key": "mp_per_coperto", "label": "€ materia prima / coperto"},
]

FUNZIONI = [
    "rigaExportMargini", "rigaExportGruppo", "notaIncompleti", "nomeFileMargini",
    "headerMargini", "etichettaDimensione", "headerPivot", "arrotonda2",
    "rigaExportPivot", "rigaTotalePivot", "nomeFoglioPivot", "nomeFilePivot",
]


def _pv(**kw):
    base = {
        "ristorante_id": "r1", "nome": "Centro", "margine_perc": 12.5,
        "fatturato": 100000.0, "coperti": 3000, "scontrino_medio": 33.33,
        "mp_per_coperto": 9.9, "dati_incompleti": False,
    }
    base.update(kw)
    return base


def _esegui(espressione, argomento=None):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=FUNZIONI)


# ─── Riga PV dell'export margini ────────────────────────────────────────────

def test_riga_export_margini_oggetto_completo_con_chiavi_esatte():
    """Le chiavi sono intestazioni di colonna: l'accento e lo spazio contano."""
    r = _esegui("emit(m.rigaExportMargini(input.r, input.c));", {"r": _pv(), "c": COLS})
    assert r == {
        "Punto vendita": "Centro",
        "Margine %": 12.5,
        "Fatturato": 100000.0,
        "Coperti": 3000,
        "Scontrino medio": 33.33,
        "€ materia prima / coperto": 9.9,
    }


def test_riga_export_margini_dati_incompleti_nasconde_ogni_numero():
    """Un PV incompleto non pubblica il fatturato: e' la regola di onesta' del file."""
    r = _esegui(
        "emit(m.rigaExportMargini(input.r, input.c));",
        {"r": _pv(dati_incompleti=True), "c": COLS},
    )
    assert r == {
        "Punto vendita": "Centro",
        "Margine %": "dati incompleti",
        "Fatturato": "dati incompleti",
        "Coperti": "dati incompleti",
        "Scontrino medio": "dati incompleti",
        "€ materia prima / coperto": "dati incompleti",
    }


def test_riga_export_margini_null_diventa_trattino_non_zero():
    """`—` e non `0`: un margine ignoto non e' un margine nullo."""
    r = _esegui(
        "emit(m.rigaExportMargini(input.r, input.c));",
        {"r": _pv(margine_perc=None, scontrino_medio=None), "c": COLS},
    )
    assert r["Margine %"] == "—"
    assert r["Scontrino medio"] == "—"
    assert r["Fatturato"] == 100000.0


def test_riga_export_margini_zero_resta_zero():
    """Lo zero e' un dato: distinguerlo da `null` e' il motivo del `== null`."""
    r = _esegui(
        "emit(m.rigaExportMargini(input.r, input.c));",
        {"r": _pv(margine_perc=0, fatturato=0, coperti=0), "c": COLS},
    )
    assert r["Margine %"] == 0
    assert r["Fatturato"] == 0
    assert r["Coperti"] == 0


def test_riga_export_margini_margine_negativo_esce_negativo():
    """Una sede in perdita esce in perdita, non azzerata."""
    r = _esegui(
        "emit(m.rigaExportMargini(input.r, input.c));",
        {"r": _pv(margine_perc=-18.4, fatturato=-2500.0), "c": COLS},
    )
    assert r["Margine %"] == -18.4
    assert r["Fatturato"] == -2500.0


def test_riga_export_margini_colonne_vuote_lascia_solo_il_nome():
    r = _esegui("emit(m.rigaExportMargini(input.r, []));", {"r": _pv()})
    assert r == {"Punto vendita": "Centro"}


def test_riga_export_margini_incompleti_prevale_su_null():
    """Ordine dei rami: `dati_incompleti` si valuta prima di `v == null`."""
    r = _esegui(
        "emit(m.rigaExportMargini(input.r, input.c));",
        {"r": _pv(dati_incompleti=True, margine_perc=None), "c": COLS},
    )
    assert r["Margine %"] == "dati incompleti"


# ─── Riga gruppo e qualificazione "(parziale)" ──────────────────────────────

def test_riga_gruppo_senza_incompleti_non_qualifica():
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 0));", {"r": _pv(), "c": COLS}
    )
    assert r["Margine %"] == 12.5


def test_riga_gruppo_con_incompleti_qualifica_solo_il_margine():
    """Il suffisso va sul margine, non sulle altre colonne."""
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 2));", {"r": _pv(), "c": COLS}
    )
    assert r["Margine %"] == "12.5 (parziale)"
    assert r["Fatturato"] == 100000.0
    assert r["Coperti"] == 3000


def test_riga_gruppo_non_qualifica_una_cella_gia_trattino():
    """`— (parziale)` si leggerebbe come un errore di formattazione."""
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 3));",
        {"r": _pv(margine_perc=None), "c": COLS},
    )
    assert r["Margine %"] == "—"


def test_riga_gruppo_non_qualifica_una_cella_dati_incompleti():
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 3));",
        {"r": _pv(dati_incompleti=True), "c": COLS},
    )
    assert r["Margine %"] == "dati incompleti"


def test_riga_gruppo_qualifica_anche_un_margine_zero():
    """Zero e' un numero: `typeof 0 === "number"` e va qualificato."""
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 1));",
        {"r": _pv(margine_perc=0), "c": COLS},
    )
    assert r["Margine %"] == "0 (parziale)"


def test_riga_gruppo_qualifica_un_margine_negativo():
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 1));",
        {"r": _pv(margine_perc=-7.25), "c": COLS},
    )
    assert r["Margine %"] == "-7.25 (parziale)"


def test_riga_gruppo_incompleti_negativo_non_qualifica():
    """Il conteggio non puo' essere negativo, ma la guardia e' `> 0` non `!== 0`."""
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, -1));", {"r": _pv(), "c": COLS}
    )
    assert r["Margine %"] == 12.5


def test_riga_gruppo_senza_colonna_margine_non_esplode():
    """`cols.find` puo' non trovare nulla: il codice deve reggere."""
    cols = [c for c in COLS if c["key"] != "margine_perc"]
    r = _esegui(
        "emit(m.rigaExportGruppo(input.r, input.c, 5));", {"r": _pv(), "c": cols}
    )
    assert r == {
        "Punto vendita": "Centro",
        "Fatturato": 100000.0,
        "Coperti": 3000,
        "Scontrino medio": 33.33,
        "€ materia prima / coperto": 9.9,
    }


def test_riga_gruppo_chiave_margine_configurabile():
    r = _esegui(
        'emit(m.rigaExportGruppo(input.r, input.c, 1, "fatturato"));',
        {"r": _pv(), "c": COLS},
    )
    assert r["Fatturato"] == "100000 (parziale)"
    assert r["Margine %"] == 12.5


# ─── Nota in coda ───────────────────────────────────────────────────────────

def test_nota_incompleti_assente_quando_zero():
    assert _esegui("emit(m.notaIncompleti(0));") is None


def test_nota_incompleti_assente_quando_negativo():
    assert _esegui("emit(m.notaIncompleti(-3));") is None


def test_nota_incompleti_singolare():
    assert _esegui("emit(m.notaIncompleti(1));") == (
        "Margine di gruppo parziale: 1 sede non ha ancora i costi caricati."
    )


def test_nota_incompleti_plurale():
    assert _esegui("emit(m.notaIncompleti(4));") == (
        "Margine di gruppo parziale: 4 sedi non hanno ancora i costi caricati."
    )


# ─── Header e nome file margini ─────────────────────────────────────────────

def test_header_margini_ordine_esatto():
    assert _esegui("emit(m.headerMargini(input));", COLS) == [
        "Punto vendita", "Margine %", "Fatturato", "Coperti",
        "Scontrino medio", "€ materia prima / coperto",
    ]


def test_header_margini_senza_colonne():
    assert _esegui("emit(m.headerMargini([]));") == ["Punto vendita"]


def test_nome_file_margini_stringa_intera():
    assert _esegui(
        'emit(m.nomeFileMargini("Giugno 2026", "2026-09-01"));'
    ) == "margini_coperti_giugno-2026.xlsx"


def test_nome_file_margini_fallback_su_periodo_vuoto():
    assert _esegui(
        'emit(m.nomeFileMargini("", "2026-09-01"));'
    ) == "margini_coperti_2026-09-01.xlsx"


def test_nome_file_margini_fallback_su_periodo_null():
    assert _esegui(
        'emit(m.nomeFileMargini(null, "2026-09-01"));'
    ) == "margini_coperti_2026-09-01.xlsx"


def test_nome_file_margini_fallback_se_lo_slug_si_azzera():
    """`"!!!"` produce slug vuoto: il fallback deve scattare lo stesso."""
    assert _esegui(
        'emit(m.nomeFileMargini("!!!", "2026-09-01"));'
    ) == "margini_coperti_2026-09-01.xlsx"


def test_nome_file_margini_accenti_diventano_trattini():
    assert _esegui(
        'emit(m.nomeFileMargini("Città Sedi", "2026-09-01"));'
    ) == "margini_coperti_citt-sedi.xlsx"


# ─── Pivot: dimensione, header, foglio ──────────────────────────────────────

def test_etichetta_dimensione_fornitore():
    assert _esegui('emit(m.etichettaDimensione("fornitore"));') == "Fornitore"


def test_etichetta_dimensione_categoria():
    assert _esegui('emit(m.etichettaDimensione("categoria"));') == "Categoria"


def test_header_pivot_ordine_esatto():
    pv = [{"id": "a", "nome": "Centro"}, {"id": "b", "nome": "Nord"}]
    assert _esegui(
        'emit(m.headerPivot("Categoria", input));', pv
    ) == ["Categoria", "Centro", "Nord", "Totale", "%"]


def test_header_pivot_senza_pv():
    assert _esegui('emit(m.headerPivot("Fornitore", []));') == [
        "Fornitore", "Totale", "%"
    ]


def test_nome_foglio_pivot_taglia_a_31():
    """Il limite e' duro nel formato xlsx: oltre, la libreria solleva."""
    lungo = "C" * 50
    r = _esegui("emit(m.nomeFoglioPivot(input));", lungo)
    assert len(r) == 31
    assert r == "C" * 31


def test_nome_foglio_pivot_non_tocca_le_etichette_reali():
    assert _esegui('emit(m.nomeFoglioPivot("Categoria"));') == "Categoria"
    assert _esegui('emit(m.nomeFoglioPivot("Fornitore"));') == "Fornitore"


def test_nome_file_pivot_stringa_intera():
    assert _esegui(
        'emit(m.nomeFilePivot("categoria", "Giugno 2026", "2026-09-01"));'
    ) == "spesa_per_pv_categoria_giugno-2026.xlsx"


def test_nome_file_pivot_fornitore():
    assert _esegui(
        'emit(m.nomeFilePivot("fornitore", "Anno 2026", "2026-09-01"));'
    ) == "spesa_per_pv_fornitore_anno-2026.xlsx"


def test_nome_file_pivot_fallback():
    assert _esegui(
        'emit(m.nomeFilePivot("categoria", "", "2026-09-01"));'
    ) == "spesa_per_pv_categoria_2026-09-01.xlsx"


# ─── Arrotondamento ─────────────────────────────────────────────────────────

def test_arrotonda2_casi_normali():
    assert _esegui("emit(m.arrotonda2(1234.5678));") == 1234.57
    assert _esegui("emit(m.arrotonda2(0));") == 0
    assert _esegui("emit(m.arrotonda2(-3.333));") == -3.33


def test_arrotonda2_negativo_conserva_il_segno():
    assert _esegui("emit(m.arrotonda2(-1234.567));") == -1234.57


@pytest.mark.parametrize(
    "valore,atteso",
    [
        (1.005, 1),        # 1.005*100 == 100.49999... in binario
        (0.005, 0.01),     # 0.005*100 == 0.5 esatto -> verso +inf
        (2.675, 2.68),
        (-2.675, -2.67),   # stesso valore, segno opposto, regola opposta
        (40.005, 40.01),
        (-40.005, -40.01),
        (0.125, 0.13),
        (-0.125, -0.12),
    ],
)
def test_fotografa_arrotondamento_mezzo_centesimo(valore, atteso):
    """ANOMALIA FOTOGRAFATA: l'arrotondamento sui mezzi centesimi non segue la
    regola commerciale italiana e non e' nemmeno simmetrico rispetto al segno.
    Non e' `Math.round` a decidere ma la rappresentazione binaria del prodotto.

    Questi valori sono il contratto attuale: se un fix centralizzato arrivera',
    questo test fallira' e va aggiornato DELIBERATAMENTE, non per caso.
    """
    assert _esegui("emit(m.arrotonda2(input));", valore) == atteso


# ─── Righe pivot ────────────────────────────────────────────────────────────

PV2 = [{"id": "a", "nome": "Centro"}, {"id": "b", "nome": "Nord"}]


def test_riga_pivot_oggetto_completo():
    riga = {
        "dim_val": "CARNE", "per_pv": {"a": 1234.567, "b": 890.123},
        "totale": 2124.69, "incidenza_pct": 33.333,
    }
    assert _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Categoria"));',
        {"r": riga, "pv": PV2},
    ) == {
        "Categoria": "CARNE", "Centro": 1234.57, "Nord": 890.12,
        "Totale": 2124.69, "%": "33.3%",
    }


def test_riga_pivot_pv_assente_vale_zero_non_trattino():
    """In una pivot di spesa una sede senza quella categoria ha speso zero."""
    riga = {"dim_val": "PESCE", "per_pv": {"a": 500.0}, "totale": 500.0, "incidenza_pct": 10.0}
    r = _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Categoria"));',
        {"r": riga, "pv": PV2},
    )
    assert r["Nord"] == 0
    assert r["Centro"] == 500.0


def test_riga_pivot_importo_negativo():
    """Nota di credito ripartita: la cella resta negativa."""
    riga = {"dim_val": "RESI", "per_pv": {"a": -320.55, "b": 0}, "totale": -320.55, "incidenza_pct": -2.5}
    r = _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Categoria"));',
        {"r": riga, "pv": PV2},
    )
    assert r["Centro"] == -320.55
    assert r["Totale"] == -320.55
    assert r["%"] == "-2.5%"


def test_riga_pivot_incidenza_un_solo_decimale():
    riga = {"dim_val": "X", "per_pv": {}, "totale": 0, "incidenza_pct": 99.99}
    r = _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Categoria"));',
        {"r": riga, "pv": PV2},
    )
    assert r["%"] == "100.0%"


def test_riga_pivot_dimensione_fornitore_usa_la_sua_etichetta():
    riga = {"dim_val": "METRO", "per_pv": {"a": 10}, "totale": 10, "incidenza_pct": 1}
    r = _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Fornitore"));',
        {"r": riga, "pv": PV2},
    )
    assert r["Fornitore"] == "METRO"
    assert "Categoria" not in r


def test_riga_pivot_senza_pv():
    riga = {"dim_val": "X", "per_pv": {}, "totale": 7.777, "incidenza_pct": 0}
    assert _esegui(
        'emit(m.rigaExportPivot(input.r, [], "Categoria"));', {"r": riga}
    ) == {"Categoria": "X", "Totale": 7.78, "%": "0.0%"}


def test_riga_pivot_nome_pv_uguale_alla_dimensione_si_sovrascrive():
    """ANOMALIA FOTOGRAFATA: un PV chiamato "Categoria" sovrascrive la prima
    colonna — le chiavi dell'oggetto sono i nomi visualizzati, non gli id.
    Il caso e' improbabile ma non impossibile, e il file uscirebbe muto."""
    riga = {"dim_val": "CARNE", "per_pv": {"a": 42.0}, "totale": 42.0, "incidenza_pct": 5}
    r = _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Categoria"));',
        {"r": riga, "pv": [{"id": "a", "nome": "Categoria"}]},
    )
    assert r["Categoria"] == 42.0


# ─── Riga TOTALE ────────────────────────────────────────────────────────────

def test_riga_totale_oggetto_completo():
    assert _esegui(
        'emit(m.rigaTotalePivot(input.t, 9999.999, input.pv, "Categoria"));',
        {"t": {"a": 1000.005, "b": 2000.004}, "pv": PV2},
    ) == {"Categoria": "TOTALE", "Centro": 1000.01, "Nord": 2000.0, "Totale": 10000.0, "%": "100%"}


def test_riga_totale_pv_assente_vale_zero():
    r = _esegui(
        'emit(m.rigaTotalePivot(input.t, 100, input.pv, "Categoria"));',
        {"t": {"a": 100}, "pv": PV2},
    )
    assert r["Nord"] == 0


def test_fotografa_totale_percentuale_costante():
    """ANOMALIA FOTOGRAFATA: la `%` della riga TOTALE e' la costante `"100%"`,
    non la somma delle incidenze. Se il backend tronca o esclude righe, le
    colonne possono sommare a 99,8% mentre il totale dichiara 100%.
    E' una scelta di leggibilita', ma il numero NON e' misurato."""
    r = _esegui(
        'emit(m.rigaTotalePivot({}, 0, [], "Categoria"));'
    )
    assert r["%"] == "100%"
    assert r["Totale"] == 0


def test_riga_totale_grand_total_negativo():
    """ANOMALIA FOTOGRAFATA (arrotondamento): `-5000.555` esce `-5000.55`, non
    `-5000.56`. Il mezzo centesimo negativo va verso lo zero, non lontano da
    esso — stesso difetto misurato in `test_fotografa_arrotondamento_*`, qui
    su un totale di gruppo, dove si vede in un file che il cliente scarica."""
    r = _esegui(
        'emit(m.rigaTotalePivot(input.t, -5000.555, input.pv, "Categoria"));',
        {"t": {"a": -5000.555}, "pv": [{"id": "a", "nome": "Centro"}]},
    )
    assert r["Centro"] == -5000.55
    assert r["Totale"] == -5000.55


# ─── Costanti ───────────────────────────────────────────────────────────────

def test_costanti_esposte_coerenti_con_le_celle():
    """Le costanti non sono decorative: le celle le usano davvero."""
    v = _esegui(
        "emit({ inc: m.CELLA_DATI_INCOMPLETI, vuota: m.CELLA_VUOTA, max: m.MAX_NOME_FOGLIO });"
    )
    assert v == {"inc": "dati incompleti", "vuota": "—", "max": 31}


# ─── Lacune chiuse dopo la mutazione (1/9) ──────────────────────────────────

def test_colonna_assente_dal_dato_esce_come_trattino():
    """Uccide il mutante `v == null` → `v === null`.

    Se il backend smette di mandare una colonna, `r[c.key]` è `undefined`:
    `== null` lo cattura e scrive `—`, `=== null` no. Col mutante la **chiave
    sparisce dall'oggetto** e la cella non esiste proprio nel file Excel —
    le colonne successive slittano rispetto all'header.
    """
    r = _esegui(
        "emit(m.rigaExportMargini(input.r, input.c));",
        {"r": _pv(), "c": [{"key": "margine_perc", "label": "Margine %"},
                           {"key": "inesistente", "label": "Fantasma"}]},
    )
    assert r == {"Punto vendita": "Centro", "Margine %": 12.5, "Fantasma": "—"}
    assert "Fantasma" in r


def test_spesa_zero_esplicita_e_assente_danno_entrambe_zero():
    """Una sede con spesa **esplicita** a zero e una **assente** escono uguali.

    NON uccide il mutante `?? 0` → `|| 0`, e verificato che non può: dopo
    `arrotonda2` i due divergono solo su `-0` (indistinguibile in JSON) e su
    `NaN` (che vorrebbe dire backend rotto). **Equivalenza vera** — la prima
    diagnosi la dava per fixture povera, la misura dice altro.

    Il test resta perché fissa il comportamento atteso di entrambi i casi, che
    è la cosa che il file Excel deve mostrare.
    """
    r = _esegui(
        'emit(m.rigaExportPivot(input.r, input.pv, "Categoria"));',
        {"r": {"dim_val": "D", "per_pv": {"a": 0}, "totale": 0, "incidenza_pct": 0},
         "pv": [{"id": "a", "nome": "Esplicita"}, {"id": "b", "nome": "Assente"}]},
    )
    assert r["Esplicita"] == 0
    assert r["Assente"] == 0


def test_nota_incompleti_su_due_sedi_usa_il_plurale():
    """Il confine singolare/plurale, fissato su entrambi i lati.

    NON uccide il mutante `=== 1` → `<= 1`, e non può: verificato che i due
    divergono **solo** su `0.5`, perché la guardia `<= 0` a monte esclude tutto
    il resto sotto 1. Un conteggio di sedi frazionario non esiste, quindi è
    un'**equivalenza vera** — dichiarata nel verbale, non zittita con una
    fixture impossibile."""
    assert _esegui("emit(m.notaIncompleti(2));") == (
        "Margine di gruppo parziale: 2 sedi non hanno ancora i costi caricati."
    )
    assert _esegui("emit(m.notaIncompleti(1));") == (
        "Margine di gruppo parziale: 1 sede non ha ancora i costi caricati."
    )


# ─── Coerenza header/righe: il difetto che sposta le colonne in Excel ───────

COLS_COME_NEL_TSX = [
    {"key": "margine_perc", "label": "Margine %", "altoMeglio": True, "tooltip": "MOL sul fatturato netto"},
    {"key": "fatturato", "label": "Fatturato", "altoMeglio": True, "tooltip": "al netto IVA"},
    {"key": "coperti", "label": "Coperti", "altoMeglio": True, "tooltip": "n coperti"},
    {"key": "scontrino_medio", "label": "Scontrino medio", "altoMeglio": True, "tooltip": "x"},
    {"key": "mp_per_coperto", "label": "€ materia prima / coperto", "altoMeglio": False, "tooltip": "y"},
]


def test_ogni_riga_ha_tutte_le_colonne_dell_header():
    """`json_to_sheet(rows, { header })` mappa per chiave: se una riga non ha
    una chiave dell'header, quella cella esce **vuota** e chi legge il file vede
    un buco — o peggio, legge il valore sotto l'intestazione sbagliata.

    Il test usa `COLS` nella forma **reale del `.tsx`**, con `altoMeglio` e
    `tooltip` che `ColonnaExport` non dichiara: il modulo deve ignorarli, non
    inciamparci. Copre insieme riga PV normale, PV incompleto e riga gruppo.
    """
    dati = {
        "cols": COLS_COME_NEL_TSX,
        "righe": [
            _pv(nome="Centro", margine_perc=14.2),
            _pv(nome="Nord", dati_incompleti=True, margine_perc=None, mp_per_coperto=None),
        ],
        "gruppo": _pv(nome="TOTALE GRUPPO", margine_perc=11.7),
    }
    r = _esegui(
        """
        const header = m.headerMargini(input.cols);
        const rows = input.righe.map((x) => m.rigaExportMargini(x, input.cols));
        const gruppo = m.rigaExportGruppo(input.gruppo, input.cols, 1);
        emit({ header, rows, gruppo });
        """,
        dati,
    )
    for riga in [*r["rows"], r["gruppo"]]:
        assert set(riga.keys()) == set(r["header"]), (
            f"riga {riga.get('Punto vendita')}: chiavi diverse dall'header — "
            "in Excel le celle slitterebbero"
        )
    assert r["gruppo"]["Margine %"] == "11.7 (parziale)"
    assert r["rows"][1]["Fatturato"] == "dati incompleti"


def test_ogni_riga_pivot_ha_tutte_le_colonne_dell_header():
    """Stesso invariante sulla pivot, dove le colonne sono i **nomi dei PV**:
    una sede senza quella categoria deve comunque avere la sua cella."""
    pv = [{"id": "a", "nome": "Centro"}, {"id": "b", "nome": "Nord"}]
    r = _esegui(
        """
        const dimLabel = m.etichettaDimensione("categoria");
        const header = m.headerPivot(dimLabel, input.pv);
        const rows = input.righe.map((x) => m.rigaExportPivot(x, input.pv, dimLabel));
        const totale = m.rigaTotalePivot(input.totali, 999, input.pv, dimLabel);
        emit({ header, rows, totale });
        """,
        {"pv": pv,
         "righe": [{"dim_val": "CARNE", "per_pv": {"a": 100.0}, "totale": 100.0, "incidenza_pct": 10.0}],
         "totali": {"a": 100.0}},
    )
    for riga in [*r["rows"], r["totale"]]:
        assert set(riga.keys()) == set(r["header"])
    assert r["rows"][0]["Nord"] == 0
