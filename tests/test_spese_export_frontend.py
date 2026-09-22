"""Test dell'export CSV della vista Spese (`lib/spese-export.ts`).

Eseguono il TypeScript vero via node (`helpers_ts.esegui_ts`): `apps/web/` non
ha un runner proprio per scelta strutturale — `deploy-vercel.yml` si attiva su
`apps/web/**`, quindi un runner li' farebbe deployare la produzione a ogni
merge di test.

Il modulo nasce da un difetto trovato il 22/09/2026 controllando tutti e nove
gli export dell'app: la guardia dell'export guardava le voci del mese intero
mentre il file scriveva quelle filtrate, e con un filtro che non seleziona
nulla usciva un CSV senza righe con sotto i totali del mese. Questi test
esistono perche' quel difetto e' vissuto dentro un `.tsx`, dove nessun test
arriva.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/spese-export"

# `richiede` controlla `typeof m[nome] === "function"`: solo funzioni. Le
# esportazioni che sono VALORI le presidia test_esportazioni_valore_presenti.
FUNZIONI = ["importoCsv", "cellaCsv", "righeExportSpese", "righeTotaliSpese",
            "csvSpese", "nomeFileSpese", "puoEsportareSpese"]

VALORI = ["headerSpese", "ETICHETTA_TOTALE_FB", "ETICHETTA_TOTALE_GENERALI"]

# Le due funzioni di formato che il componente passa da fuori. `fmtData` della
# vista Spese e' `GG/MM` SENZA anno — diversa da quella di `lib/inventario` —
# e riprodurla qui e' voluto: se un giorno le si unificasse, il file cambierebbe
# e questi test lo direbbero.
PROLOGO_FMT = (
    "const fd = (iso) => { const [,m2,d] = iso.split('-'); return `${d}/${m2}`; };"
    "const lt = (t) => (t === 'fb' ? 'Food & Beverage' : 'Spese Generali');"
)


def _esegui(espressione, argomento=None):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=FUNZIONI)


def test_esportazioni_valore_presenti():
    """Le esportazioni che non sono funzioni sfuggono a `richiede`: una rinomina
    le farebbe arrivare `undefined` senza che il prologo se ne accorga."""
    presenti = _esegui("emit(input.map((n) => typeof m[n] !== \"undefined\"));", VALORI)
    assert presenti == [True] * len(VALORI), dict(zip(VALORI, presenti))


def _voce(**kw):
    base = {
        "data_spesa": "2026-09-03",
        "tipo": "fb",
        "categoria": "ORTOFRUTTA",
        "descrizione": "Cassette pomodori",
        "importo": 120.5,
        "note": None,
    }
    base.update(kw)
    return base


# ─── Il difetto del 22/09/2026: totali coerenti con le righe ────────────────

def test_totali_sono_la_somma_delle_righe_esportate():
    """Il cuore del fix. I totali descrivono le voci nel file, non il mese
    intero: sommando la colonna Importo il cliente deve ritrovare i totali in
    fondo, altrimenti il file si contraddice da solo."""
    voci = [_voce(importo=100.0, tipo="fb"), _voce(importo=50.0, tipo="generale")]
    righe = _esegui(
        PROLOGO_FMT + "emit(m.righeTotaliSpese(input, 'fb', 'generale'));", voci
    )
    assert righe[1][0] == "TOTALE F&B"
    assert righe[1][4] == "100"
    assert righe[2][0] == "TOTALE GENERALI"
    assert righe[2][4] == "50"


def test_filtro_che_esclude_tutto_non_puo_esportare():
    """Con un filtro attivo che non seleziona nulla l'export si ferma. Prima
    scaricava un file senza righe con i totali del mese intero sotto: numeri
    che non corrispondevano a niente di visibile a schermo."""
    assert _esegui("emit(m.puoEsportareSpese(input));", []) is False
    assert _esegui("emit(m.puoEsportareSpese(input));", [_voce()]) is True


def test_totali_su_elenco_vuoto_sono_zero_non_il_totale_del_mese():
    """Anche se qualcuno chiamasse la costruzione con zero voci, i totali
    restano zero. E' la seconda gamba della stessa guardia: se un domani il
    controllo saltasse, il file uscirebbe almeno coerente."""
    righe = _esegui(
        PROLOGO_FMT + "emit(m.righeTotaliSpese(input, 'fb', 'generale'));", []
    )
    assert righe[1][4] == "0"
    assert righe[2][4] == "0"


def test_totale_generali_non_assorbe_un_tipo_sconosciuto():
    """Due confronti positivi, non uno negativo: e' cio' che fa il server
    (`workspace.py`, ws_spese_list). Con `!== fb` una voce di tipo ignoto
    finirebbe nei generali e il file direbbe una cosa diversa dall'API."""
    voci = [_voce(importo=10.0, tipo="fb"), _voce(importo=999.0, tipo="ignoto")]
    righe = _esegui(
        PROLOGO_FMT + "emit(m.righeTotaliSpese(input, 'fb', 'generale'));", voci
    )
    assert righe[1][4] == "10"
    assert righe[2][4] == "0"


def test_riga_separatrice_ha_tutte_le_colonne():
    """Una riga davvero vuota Excel la legge come riga a una sola colonna."""
    righe = _esegui(
        PROLOGO_FMT + "emit(m.righeTotaliSpese(input, 'fb', 'generale'));", [_voce()]
    )
    intestazioni = _esegui("emit(m.headerSpese);")
    assert righe[0] == [""] * len(intestazioni)


# ─── Le celle che il cliente legge ──────────────────────────────────────────

def test_riga_export_oggetto_completo():
    r = _esegui(PROLOGO_FMT + "emit(m.righeExportSpese(input, fd, lt));", [_voce()])
    assert r == [["03/09", "Food & Beverage", "ORTOFRUTTA", "Cassette pomodori",
                  "120,5", ""]]


def test_header_copre_esattamente_le_colonne_della_riga():
    riga = _esegui(PROLOGO_FMT + "emit(m.righeExportSpese(input, fd, lt));", [_voce()])
    assert len(riga[0]) == len(_esegui("emit(m.headerSpese);"))


def test_header_ordine_esatto():
    assert _esegui("emit(m.headerSpese);") == [
        "Data", "Tipo", "Categoria", "Descrizione", "Importo", "Note",
    ]


def test_campi_nulli_diventano_celle_vuote():
    """Un `null` serializzato come "null" in una cella e' un dato falso."""
    r = _esegui(
        PROLOGO_FMT + "emit(m.righeExportSpese(input, fd, lt));",
        [_voce(categoria=None, note=None)],
    )
    assert r[0][2] == ""
    assert r[0][5] == ""


def test_importo_negativo_mantiene_il_segno():
    """Uno storno e' un importo negativo: in valore assoluto sommerebbe invece
    di sottrarre."""
    assert _esegui("emit(m.importoCsv(input));", -45.5) == "-45,5"


def test_importo_usa_la_virgola_decimale():
    """Con il punto, Excel in locale italiano legge la colonna come testo."""
    assert _esegui("emit(m.importoCsv(input));", 1234.56) == "1234,56"


def test_importo_arrotonda_a_due_decimali():
    assert _esegui("emit(m.importoCsv(input));", 10.005) == "10,01"
    assert _esegui("emit(m.importoCsv(input));", 0.1 + 0.2) == "0,3"


# ─── Il formato CSV: un campo non deve poter spezzare la riga ───────────────

def test_cella_sempre_fra_virgolette():
    assert _esegui("emit(m.cellaCsv(input));", "ACME") == '"ACME"'


def test_punto_e_virgola_nel_campo_non_spezza_la_riga():
    """Il separatore e' `;` e i nomi fornitore delle fatture lo contengono."""
    assert _esegui("emit(m.cellaCsv(input));", "ROSSI; C.") == '"ROSSI; C."'


def test_virgolette_nel_campo_sono_raddoppiate():
    """RFC 4180: senza il raddoppio la cella chiude in anticipo e tutte le
    colonne successive slittano di una posizione."""
    assert _esegui("emit(m.cellaCsv(input));", 'Pomodoro "San Marzano"') == (
        '"Pomodoro ""San Marzano"""'
    )


def test_cella_null_non_diventa_la_stringa_null():
    assert _esegui("emit(m.cellaCsv(input));", None) == '""'


def test_csv_completo_struttura_e_terminatori():
    """Il file intero: intestazioni, una riga, separatrice, due totali. `\\r\\n`
    e' il terminatore che Excel si aspetta."""
    testo = _esegui(
        PROLOGO_FMT + "emit(m.csvSpese(input, fd, lt, 'fb', 'generale'));", [_voce()]
    )
    righe = testo.split("\r\n")
    assert len(righe) == 5
    assert righe[0] == '"Data";"Tipo";"Categoria";"Descrizione";"Importo";"Note"'
    assert righe[1] == '"03/09";"Food & Beverage";"ORTOFRUTTA";"Cassette pomodori";"120,5";""'
    assert righe[2] == '"";"";"";"";"";""'
    assert righe[3] == '"TOTALE F&B";"";"";"";"120,5";""'
    assert righe[4] == '"TOTALE GENERALI";"";"";"";"0";""'


def test_nome_file_invariato():
    """Chi ha cartelle o automatismi che cercano il file per nome non deve
    accorgersi del cambio."""
    assert _esegui(
        "emit(m.nomeFileSpese(input[0], input[1]));", ["2026-09-01", "2026-09-30"]
    ) == "spese_2026-09-01_2026-09-30.csv"
