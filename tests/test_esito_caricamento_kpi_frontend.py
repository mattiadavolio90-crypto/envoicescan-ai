"""Un timeout e un periodo vuoto non devono dare la stessa schermata.

Perche' esiste
==============
`fetchKpiData` ripiega su sei zeri quando il worker non risponde entro 8s,
risponde male, o manca la sessione. Fino al 16/09/2026 quel ripiego era
indistinguibile da un periodo davvero vuoto: stessi sei "0 €", nessun retry,
nessun avviso. L'audit ha visto i riquadri fermi a zero per oltre 30 secondi
mentre la tabella sotto era gia' piena — non stavano caricando, si erano arresi.

L'app altrove distingue gia' "non ci sono dati" da "non sono riuscito a
caricare": `esito-caricamento.ts` fa esattamente questo per le LISTE, in 6
pagine, e il suo commento cita la stessa causa (Railway spegne il worker, il
risveglio sfora gli 8s). I KPI non sono righe ma sei totali, quindi la stessa
distinzione prende la forma di un flag e vive nello stesso modulo, non in uno
nuovo. Questi test impediscono che la pagina Margini torni a confondere i due
casi.

Il secondo invariante e' commerciale
====================================
`trigger-servizi` dichiara: «un campo assente = "non lo so", quindi il trigger
relativo non scatta». Su un ripiego, `molNegativo: false` affermerebbe che il
MOL e' sano — un giudizio su numeri mai arrivati. Un trigger che scatta (o tace)
per colpa di un timeout e' un messaggio commerciale mandato a caso.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/esito-caricamento"


def _chiama(funzione, kpi):
    return esegui_ts(
        MODULO,
        f"emit(m.{funzione}(input));",
        argomento=kpi,
        richiede=["kpiNonDisponibile", "kpiValutabiliPerTrigger"],
    )


# Un periodo davvero vuoto: zeri VERI, arrivati dal worker.
PERIODO_VUOTO = {"fatturato_netto": 0, "mol": 0, "food_cost_perc": 0}

# Il ripiego: stessi zeri, ma nessuno li ha calcolati.
RIPIEGO = {"fatturato_netto": 0, "mol": 0, "food_cost_perc": 0, "non_disponibile": True}

# Dati normali.
PIENO = {"fatturato_netto": 400000.0, "mol": 120000.0, "food_cost_perc": 31.4}


def test_il_periodo_vuoto_mostra_le_cifre():
    """Zero e' un dato: "non hai speso nulla" e' un'informazione vera."""
    assert _chiama("kpiNonDisponibile", PERIODO_VUOTO) is False


def test_il_ripiego_non_mostra_le_cifre():
    """Gli stessi zeri, ma nessuno li ha calcolati: va detto."""
    assert _chiama("kpiNonDisponibile", RIPIEGO) is True


def test_le_due_schermate_sono_diverse():
    """L'invariante che da' il nome al difetto: due situazioni diverse non
    possono produrre la stessa schermata. Se un giorno qualcuno togliesse il
    flag dal ripiego, questo test cade prima dell'utente."""
    assert _chiama("kpiNonDisponibile", PERIODO_VUOTO) != _chiama("kpiNonDisponibile", RIPIEGO)


def test_dati_pieni_mostrano_le_cifre():
    assert _chiama("kpiNonDisponibile", PIENO) is False


def test_il_trigger_non_si_valuta_sul_ripiego():
    """Il punto commerciale: niente giudizi su numeri mai arrivati."""
    assert _chiama("kpiValutabiliPerTrigger", RIPIEGO) is False


def test_il_trigger_si_valuta_su_un_periodo_vuoto_vero():
    """La direzione opposta, che impedisce di spegnere i trigger per sempre:
    un periodo vuoto e' un dato reale e resta valutabile."""
    assert _chiama("kpiValutabiliPerTrigger", PERIODO_VUOTO) is True


def test_il_trigger_si_valuta_sui_dati_pieni():
    assert _chiama("kpiValutabiliPerTrigger", PIENO) is True


def test_kpi_assenti_non_sono_valutabili():
    """`null` non e' "tutto bene": e' l'assenza del dato."""
    assert esegui_ts(
        MODULO,
        "emit(m.kpiValutabiliPerTrigger(null));",
        richiede=["kpiValutabiliPerTrigger"],
    ) is False


def test_le_due_funzioni_non_si_contraddicono():
    """Su ogni caso, "mostrabile" e "valutabile" devono concordare: se i numeri
    non si possono mostrare non si possono nemmeno giudicare, e viceversa. Sono
    due funzioni separate perche' hanno due chiamanti diversi, non perche'
    possano divergere."""
    for caso in (PERIODO_VUOTO, RIPIEGO, PIENO):
        mostrabile = not _chiama("kpiNonDisponibile", caso)
        valutabile = _chiama("kpiValutabiliPerTrigger", caso)
        assert mostrabile is valutabile, f"divergono su {caso}"
