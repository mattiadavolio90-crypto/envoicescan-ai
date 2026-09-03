"""«Zero» e «non lo so» non sono lo stesso numero, nemmeno sul mobile.

`fetchNettoMese` (desktop) tipizza il netto come `number | null` e la
distinzione e' deliberata: `0` = mese senza ricavi, `null` = lettura fallita.
`tests/test_margini_netto_mese_frontend.py` la difende sul desktop, dove il
valore diventa la base delle percentuali salvate a DB.

**Sul mobile la distinzione era persa.** `mobile-incassi.tsx:274` faceva:

    nettoAutorevole?.netto ?? risposta?.totale_netto ?? 0

La catena di `??` schiaccia il `null` su `0`: il KPI «Incasso netto del mese»
mostrava **0,00 €** quando il dato non era stato letto. Non e' un dettaglio
estetico — e' il numero che il ristoratore legge per sapere quanto ha incassato.

**L'esposizione e' misurata, non stimata** (DB di produzione, 03/09/2026):
1.049 righe in `ricavi_giornalieri` su 6 sedi, ultimo dato il 02/09, piu' 17
override mensili su 4 sedi. Gli incassi ci sono gia': il difetto non aspetta.

Questi test coprono la funzione pura estratta in `lib/ricavi-netto-mese.ts`;
la scelta override-vs-giornalieri resta quella di `fetchNettoMese`, che il
mobile ora **chiama** invece di riscrivere.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/ricavi-netto-mese"
RICHIEDE = ["nettoDaMostrare", "dettaglioNettoMese"]

# Un formatter finto e riconoscibile: i test devono provare COSA viene
# formattato, non come. Il formatter vero (Intl) ha gia' i suoi test altrove, e
# dipenderebbe dalla locale di node.
_FMT = "(v) => `<<${v}>>`"


def _mostra(netto):
    return esegui_ts(
        MODULO,
        f"emit(m.nettoDaMostrare(input, {_FMT}))",
        argomento=netto,
        richiede=RICHIEDE,
    )


def test_lettura_fallita_non_diventa_zero_euro():
    """IL difetto che questo file esiste per impedire."""
    assert _mostra(None) == {"testo": "—", "disponibile": False}, (
        "un netto sconosciuto viene mostrato come un importo: il cliente legge "
        "'0,00 €' e crede di non aver incassato niente, mentre il dato non e' "
        "stato letto"
    )


def test_zero_vero_resta_zero_e_si_vede():
    """L'altra meta' della distinzione: uno zero misurato va mostrato."""
    assert _mostra(0) == {"testo": "<<0>>", "disponibile": True}, (
        "un mese davvero a zero viene nascosto dietro '—': il cliente non "
        "distingue piu' 'non ho incassato' da 'il dato manca'"
    )


@pytest.mark.parametrize("valore", [3227.27, 73322.73, 0.01, -150.5])
def test_un_importo_letto_viene_formattato(valore):
    """73.322,73 e 3.227,27 sono i due valori veri di giugno 2026 (override e
    giornalieri orfani): la differenza fra i due rami vale 70.095 EUR."""
    assert _mostra(valore) == {"testo": f"<<{valore}>>", "disponibile": True}


def test_nan_e_infinity_ricostruiti_in_js():
    """Il caso sopra, ma coi valori veri: JSON non sa trasportarli."""
    r = esegui_ts(
        MODULO,
        f"""emit([NaN, Infinity, -Infinity].map((v) => m.nettoDaMostrare(v, {_FMT})));""",
        richiede=RICHIEDE,
    )
    for esito in r:
        assert esito == {"testo": "—", "disponibile": False}, (
            f"un valore non finito arriva a schermo: {esito}"
        )


def test_undefined_e_trattato_come_assente():
    """Il campo puo' mancare del tutto se la risposta cambia forma."""
    r = esegui_ts(
        MODULO,
        f"emit(m.nettoDaMostrare(undefined, {_FMT}))",
        richiede=RICHIEDE,
    )
    assert r == {"testo": "—", "disponibile": False}


# ─── la riga di dettaglio sotto il KPI ──────────────────────────────────────

def _dettaglio(disponibile, mensile, giorni):
    return esegui_ts(
        MODULO,
        "emit(m.dettaglioNettoMese(input.d, input.m, input.g))",
        argomento={"d": disponibile, "m": mensile, "g": giorni},
        richiede=RICHIEDE,
    )


def test_senza_dato_non_si_dichiarano_zero_giorni():
    """«0 giorni inseriti» su una lettura fallita e' una seconda bugia: i giorni
    potrebbero esserci tutti."""
    assert _dettaglio(False, False, 0) == "Dato non disponibile"
    assert _dettaglio(False, True, 12) == "Dato non disponibile", (
        "con dato assente si dichiara comunque 'totale mensile': non lo sappiamo"
    )


def test_il_mese_in_override_lo_dice():
    assert _dettaglio(True, True, 0) == "Totale mensile inserito da desktop"


@pytest.mark.parametrize("giorni,atteso", [
    (0, "0 giorni inseriti"),
    (1, "1 giorno inserito"),
    (2, "2 giorni inseriti"),
    (31, "31 giorni inseriti"),
])
def test_singolare_e_plurale(giorni, atteso):
    assert _dettaglio(True, False, giorni) == atteso
