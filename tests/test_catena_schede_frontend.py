"""Le schede di Gestione Fatture e di Analisi catena (`lib/catena-schede.ts`).

Il 28/9/2026 (decisione di Mattia) le funzioni della Home di catena sono
diventate schede di pagina: la coda delle fatture di gruppo e i costi di gruppo
in Gestione Fatture, i tre confronti fra sedi in Analisi catena. Qui si prova la
parte che decide COSA si vede, eseguita davvero con node:

- quale scheda si apre per un `?tab=` qualunque (anche sbagliato);
- che spegnere lo scadenziario tolga la sola scheda «Scadenze", non la coda e i
  costi di gruppo che prima stavano in una Home senza interruttore;
- il conteggio della coda sull'etichetta, e niente numero quando non e' letto.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-schede"


def _risolvi(schede, richiesta, predefinita=None):
    arg = {"schede": schede, "richiesta": richiesta, "predefinita": predefinita}
    return esegui_ts(
        MODULO,
        "emit(input.predefinita == null"
        " ? m.risolviScheda(m[input.schede], input.richiesta)"
        " : m.risolviScheda(m[input.schede], input.richiesta, input.predefinita));",
        argomento=arg,
        richiede=["risolviScheda"],
    )


def _schede_fatture(da_collocare, pagine):
    return esegui_ts(
        MODULO,
        "emit(m.schedeFattureCatena(input.n, input.pagine));",
        argomento={"n": da_collocare, "pagine": pagine},
        richiede=["schedeFattureCatena"],
    )


def _chiavi(schede):
    return [s["key"] for s in schede]


# ─── Quale scheda si apre ───────────────────────────────────────────────────


@pytest.mark.parametrize("richiesta", ["spesa", "margini", "tag"])
def test_analisi_una_scheda_valida_si_apre_lei(richiesta):
    assert _risolvi("SCHEDE_ANALISI_CATENA", richiesta) == richiesta


@pytest.mark.parametrize("richiesta", [None, "", "pippo", "SPESA", "calcolo"])
def test_analisi_una_richiesta_ignota_ricade_sulla_prima(richiesta):
    """Un link vecchio o un refuso non deve rendere la pagina senza corpo."""
    assert _risolvi("SCHEDE_ANALISI_CATENA", richiesta) == "spesa"


def test_fatture_dal_menu_si_apre_sulle_scadenze():
    """Chi apre Gestione Fatture dal menu ci va per pagare: prima delle schede
    la voce apriva lo scadenziario, e deve restare cosi'."""
    assert _risolvi("SCHEDE_FATTURE_CATENA", None, "scadenze") == "scadenze"
    assert _risolvi("SCHEDE_FATTURE_CATENA", "pippo", "scadenze") == "scadenze"


def test_fatture_il_link_della_coda_apre_la_coda():
    assert _risolvi("SCHEDE_FATTURE_CATENA", "collocare", "scadenze") == "collocare"


def test_predefinita_non_disponibile_ricade_sulla_prima_disponibile():
    """Scadenziario spento: la predefinita «scadenze» non c'e', e la pagina
    deve aprire comunque una scheda che esiste."""
    out = esegui_ts(
        MODULO,
        "emit(m.risolviScheda(m.schedeFattureCatena(0, []), null, m.SCHEDA_FATTURE_PREDEFINITA));",
        richiede=["risolviScheda", "schedeFattureCatena"],
    )
    assert out == "collocare"


def test_la_predefinita_dichiarata_e_scadenze():
    assert esegui_ts(MODULO, "emit(m.SCHEDA_FATTURE_PREDEFINITA);") == "scadenze"


def test_il_link_della_coda_porta_alla_scheda_collocare():
    """Home, caricamento e briefing rimandano qui: il link e la chiave della
    scheda devono coincidere, o il rimando apre le scadenze."""
    out = esegui_ts(
        MODULO,
        "emit([m.LINK_CODA_GRUPPO, m.LINK_ANALISI_SPESA, m.LINK_ANALISI_MARGINI]);",
    )
    assert out == [
        "/catena/fatture?tab=collocare",
        "/catena/analisi?tab=spesa",
        "/catena/analisi?tab=margini",
    ]


# ─── Quali schede si vedono ─────────────────────────────────────────────────


@pytest.mark.parametrize("pagine", [None, ["scadenziario"], ["margini", "scadenziario"]])
def test_con_lo_scadenziario_le_schede_sono_tre(pagine):
    assert _chiavi(_schede_fatture(0, pagine)) == ["collocare", "costi", "scadenze"]


@pytest.mark.parametrize("pagine", [[], ["margini", "analisi_fatture"]])
def test_senza_scadenziario_restano_coda_e_costi(pagine):
    """Prima la pagina intera era chiusa dal flag `scadenziario`: la coda e i
    costi di gruppo, arrivati dalla Home, non devono sparire con lui."""
    assert _chiavi(_schede_fatture(0, pagine)) == ["collocare", "costi"]


# ─── Il conteggio della coda ────────────────────────────────────────────────


@pytest.mark.parametrize("n, attesa", [(1, "Da collocare (1)"), (12, "Da collocare (12)")])
def test_il_conteggio_sta_sull_etichetta(n, attesa):
    assert _schede_fatture(n, None)[0]["label"] == attesa


@pytest.mark.parametrize("n", [0, None, -1])
def test_niente_numero_se_zero_o_non_letto(n):
    """`null` = worker giu': niente numero, non uno zero inventato."""
    assert _schede_fatture(n, None)[0]["label"] == "Da collocare"


def test_il_conteggio_non_si_attacca_alle_altre_schede():
    etichette = [s["label"] for s in _schede_fatture(5, None)]
    assert etichette == ["Da collocare (5)", "Costi di gruppo", "Scadenze"]


def test_le_etichette_non_si_accumulano_fra_chiamate():
    """La funzione copia le schede: se mutasse la costante condivisa, la seconda
    chiamata leggerebbe «Da collocare (3) (3)»."""
    out = esegui_ts(
        MODULO,
        "m.schedeFattureCatena(3, null); emit(m.schedeFattureCatena(3, null)[0].label);",
        richiede=["schedeFattureCatena"],
    )
    assert out == "Da collocare (3)"
