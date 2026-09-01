"""Test di `parseNumeroIt` in `apps/web/src/lib/format.ts`.

Perché esiste: fino all'1/9/2026 l'app convertiva gli importi digitati con
`Number(testo.replace(",", "."))`, in **60 punti diversi**. Quella forma
sbaglia su due input che un utente italiano scrive tutti i giorni:

  "1.234,56"  -> NaN          (il punto delle migliaia resta)
  "1.234"     -> 1.234        mille volte meno, **senza nessun errore**

Il secondo è il pericoloso: non viene respinto, viene salvato. Un costo di
1.234 € finiva nel database come 1,23 €.

`parseNumeroIt` è la fonte unica che sostituisce quel pattern. Questi test
sono il contratto: se cambiano, cambia il significato di ogni importo che un
cliente digita.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/format"
RICHIEDE = ["parseNumeroIt"]


def _parse(testo):
    return esegui_ts(
        MODULO, "emit(m.parseNumeroIt(input));", argomento=testo, richiede=RICHIEDE
    )


def _e_nan(testo):
    return esegui_ts(
        MODULO,
        "emit(Number.isNaN(m.parseNumeroIt(input)));",
        argomento=testo,
        richiede=RICHIEDE,
    )


# ─── Formato italiano: virgola decimale, punto migliaia ─────────────────────

@pytest.mark.parametrize(
    "testo,atteso",
    [
        ("1.234,56", 1234.56),
        ("1.234.567,89", 1234567.89),
        ("1234,56", 1234.56),
        ("0,5", 0.5),
        (",5", 0.5),
        ("-1.234,56", -1234.56),
        ("-0,01", -0.01),
        ("1.000.000,00", 1000000.0),
    ],
)
def test_virgola_decimale_con_migliaia(testo, atteso):
    """Se c'è una virgola è LEI il separatore decimale: i punti sono migliaia."""
    assert _parse(testo) == atteso


# ─── Il caso ambiguo: solo punti ────────────────────────────────────────────

@pytest.mark.parametrize(
    "testo,atteso",
    [
        ("1.234", 1234),      # 3 cifre finali -> migliaia
        ("12.345", 12345),
        ("1.234.567", 1234567),
        ("1.23", 1.23),       # 2 cifre -> decimale all'inglese
        ("1.2", 1.2),
        ("1.2345", 1.2345),   # 4 cifre -> decimale
        ("0.5", 0.5),
    ],
)
def test_solo_punti_la_regola_delle_tre_cifre(testo, atteso):
    """Senza virgola, l'ultimo gruppo decide: 3 cifre = migliaia, altrimenti
    decimale. È l'unica disambiguazione possibile senza chiedere all'utente, ed
    è la stessa che usa Excel in locale italiano.

    `"1.234"` è il caso che rendeva grave il vecchio bug: dava `1.234` e veniva
    salvato così, mille volte meno del dovuto.
    """
    assert _parse(testo) == atteso


# ─── Interi e forme semplici ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "testo,atteso",
    [("2000", 2000), ("0", 0), ("-500", -500), ("999999", 999999)],
)
def test_interi(testo, atteso):
    assert _parse(testo) == atteso


# ─── Rumore che arriva da copia-incolla ─────────────────────────────────────

@pytest.mark.parametrize(
    "testo,atteso",
    [
        ("€ 1.234,56", 1234.56),
        ("1.234,56 €", 1234.56),
        ("1 234,56", 1234.56),          # spazio normale
        (" 1.234,56 ", 1234.56),  # nbsp, tipico da Excel
        ("  2000  ", 2000),
        ("1 234,56", 1234.56),     # narrow nbsp
    ],
)
def test_simboli_e_spazi_vengono_ignorati(testo, atteso):
    """Un importo incollato da Excel o da un PDF porta con sé nbsp e simboli:
    respingerlo per quello sarebbe un rifiuto incomprensibile per l'utente."""
    assert _parse(testo) == atteso


# ─── Input che deve restare NaN ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "testo",
    [
        "", "   ", "abc", "1,2,3", "1.2.3", "--5", "€", "12a34",
        # Notazioni che `Number()` accetta ma che nessuno digita in un campo
        # importo. Senza la guardia `FORMA_NUMERICA` darebbero un valore
        # silenziosamente sbagliato — e `"Infinity"` passerebbe `importo > 0`.
        "0x10", "1e3", "Infinity", "-Infinity", "0b101", "0o17",
    ],
)
def test_input_malformato_resta_nan(testo):
    """Il parser non deve diventare "generoso": un input senza senso resta NaN
    e chi chiama lo respinge. `""` compreso — un campo vuoto non è zero euro,
    è l'assenza di un importo."""
    assert _e_nan(testo) is True


def test_null_e_undefined_sono_nan():
    assert esegui_ts(
        MODULO,
        "emit({ n: Number.isNaN(m.parseNumeroIt(null)), u: Number.isNaN(m.parseNumeroIt(undefined)) });",
        richiede=RICHIEDE,
    ) == {"n": True, "u": True}


# ─── Il contratto col chiamante ─────────────────────────────────────────────

def test_lo_zero_esplicito_non_e_nan():
    """`"0"` è un importo valido scritto dall'utente, e vale 0 — diverso da `""`
    che è l'assenza di importo. Chi chiama distingue i due con `Number.isNaN`."""
    assert _parse("0") == 0
    assert _e_nan("0") is False
    assert _e_nan("") is True


# ─── parseDecimaleIt: dove la regola delle migliaia NON va applicata ────────

DECIMALE = ["parseDecimaleIt", "parseDecimaleItOZero"]


def _decimale(testo):
    return esegui_ts(
        MODULO, "emit(m.parseDecimaleIt(input));", argomento=testo, richiede=DECIMALE
    )


@pytest.mark.parametrize(
    "testo,atteso",
    [
        ("33.333", 33.333),   # percentuale: NON trentatremila
        ("1.234", 1.234),     # ore: NON milleduecento
        ("7.5", 7.5),
        ("8,5", 8.5),
        ("0,25", 0.25),
        ("100", 100),
        ("12.50", 12.5),
    ],
)
def test_decimale_il_punto_resta_decimale(testo, atteso):
    """Su ore, percentuali e prezzi unitari il separatore delle migliaia non ha
    senso: i valori sono piccoli per natura.

    `"33.333"` è trentatré virgola trecentotrentatré, non trentatremila —
    applicare la regola delle 3 cifre lo renderebbe **mille volte più grande**,
    ed è esattamente il rischio che questa variante esiste per evitare.
    """
    assert _decimale(testo) == atteso


def test_decimale_e_importo_divergono_di_proposito():
    """Le due funzioni danno risultati diversi sullo stesso input, e deve essere
    così: `"1.234"` è 1234 € su un importo, 1,234 su un conteggio di ore.
    La scelta è del chiamante, non del parser."""
    r = esegui_ts(
        MODULO,
        'emit({ importo: m.parseNumeroIt("1.234"), decimale: m.parseDecimaleIt("1.234") });',
        richiede=["parseNumeroIt", "parseDecimaleIt"],
    )
    assert r == {"importo": 1234, "decimale": 1.234}


@pytest.mark.parametrize("testo,atteso", [("50%", 50), ("33,3%", 33.3), ("€ 12,50", 12.5)])
def test_decimale_toglie_simboli(testo, atteso):
    assert _decimale(testo) == atteso


def test_decimale_o_zero_sul_vuoto():
    r = esegui_ts(
        MODULO,
        'emit({ vuoto: m.parseDecimaleItOZero(""), valido: m.parseDecimaleItOZero("8,5") });',
        richiede=DECIMALE,
    )
    assert r == {"vuoto": 0, "valido": 8.5}
