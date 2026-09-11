"""Il gauge dei margini trova il commento del suo KPI, anche per un negozio.

I nomi KPI di `/api/margini/analisi` viaggiano come stringhe DISPLAY su entrambi
i lati: la response non ha una chiave stabile, quindi il match fra il gauge e il
suo commento e' un confronto di ETICHETTE. Ha gia' sbagliato una volta (il gauge
"Costi Gestione" cercava se stesso mentre il worker manda "Spese Generali", e
restava senza emoji ne' commento).

Col retail il rischio raddoppia: il worker rinomina il KPI merce in «Costo
Merce» (`_nome_kpi_per_settore`), e un frontend che cercasse il letterale
"Food Cost" perderebbe colore E diagnosi **senza dare errore** — `tsc` non
esegue niente, e nessun test di rendering esiste.

Qui il vincolo diventa eseguibile: si prende il nome che il BACKEND emette
davvero e si verifica che il client lo ritrovi.
"""
import pytest

from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from services.routers.margini import _nome_kpi_per_settore
from tests.helpers_ts import esegui_ts

MODULO = "lib/kpi-margini"
_RICHIEDE = ("normalizzaKpi", "commentoPerKpi", "nomeKpiMerce")


def _ts(espressione, argomento=None):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=_RICHIEDE)


# ── Il nome che il client cerca e' quello che il server manda ────────────

@pytest.mark.parametrize("settore", [SETTORE_RETAIL, SETTORE_RISTORAZIONE, None])
def test_il_client_cerca_il_nome_che_il_server_emette(settore):
    """Il presidio centrale: se i due lati divergono, il gauge resta muto."""
    lato_server = _nome_kpi_per_settore("food_cost", "Food Cost", settore)
    settore_js = "null" if settore is None else f"'{settore}'"
    lato_client = _ts(f"emit(m.nomeKpiMerce({settore_js}));")
    assert lato_client == lato_server, (
        f"settore {settore!r}: il worker manda {lato_server!r}, il gauge cerca "
        f"{lato_client!r} — il commento non verrebbe trovato e il gauge "
        f"perderebbe colore e diagnosi senza dare errore"
    )


def test_un_negozio_trova_il_commento_del_suo_kpi_merce():
    """Il flusso vero: la response del worker per un negozio, letta dal client."""
    nome = _nome_kpi_per_settore("food_cost", "Food Cost", SETTORE_RETAIL)
    trovato = _ts(
        "emit(m.commentoPerKpi(input.commenti, m.nomeKpiMerce('retail'))?.commento ?? null);",
        argomento={"commenti": [
            {"kpi_nome": nome, "percentuale": "62,0%", "commento": "confronta coi tuoi mesi",
             "emoji": "ℹ️", "colore": "#2563eb"},
            {"kpi_nome": "MOL", "percentuale": "8,0%", "commento": "MOL basso",
             "emoji": "🟠", "colore": "#ea580c"},
        ]},
    )
    assert trovato == "confronta coi tuoi mesi"


def test_un_ristorante_trova_ancora_il_commento_del_food_cost():
    nome = _nome_kpi_per_settore("food_cost", "Food Cost", SETTORE_RISTORAZIONE)
    trovato = _ts(
        "emit(m.commentoPerKpi(input.commenti, m.nomeKpiMerce(null))?.commento ?? null);",
        argomento={"commenti": [
            {"kpi_nome": nome, "percentuale": "26,5%", "commento": "Food cost eccellente",
             "emoji": "🟢", "colore": "#16a34a"},
        ]},
    )
    assert trovato == "Food cost eccellente"


def test_il_nome_di_un_settore_non_trova_quello_dell_altro():
    """Se `nomeKpiMerce` ignorasse il settore i due test sopra passerebbero
    entrambi con lo stesso valore, e non misurerebbero niente."""
    nome_retail = _nome_kpi_per_settore("food_cost", "Food Cost", SETTORE_RETAIL)
    trovato = _ts(
        "emit(m.commentoPerKpi(input.commenti, m.nomeKpiMerce(null))?.commento ?? null);",
        argomento={"commenti": [
            {"kpi_nome": nome_retail, "percentuale": "62,0%", "commento": "x",
             "emoji": "ℹ️", "colore": "#2563eb"},
        ]},
    )
    assert trovato is None, "un ristorante ha trovato il KPI di un negozio"


# ── La normalizzazione: le differenze che NON devono rompere il match ────

@pytest.mark.parametrize("a,b", [
    ("Food Cost", "food cost"),
    ("1° Margine", "1 margine"),
    ("Spese Generali", "spesegenerali"),
    ("Costo Merce", "  costo   merce  "),
])
def test_spazi_gradi_e_maiuscole_non_rompono_il_match(a, b):
    assert _ts("emit(m.normalizzaKpi(input.a) === m.normalizzaKpi(input.b));",
               argomento={"a": a, "b": b}) is True


@pytest.mark.parametrize("a,b", [
    ("Costo Merce", "Food Cost"),
    ("MOL", "1° Margine"),
    ("Spese Generali", "Costo del Lavoro"),
])
def test_kpi_diversi_restano_diversi(a, b):
    """Una normalizzazione troppo aggressiva farebbe combaciare tutto."""
    assert _ts("emit(m.normalizzaKpi(input.a) === m.normalizzaKpi(input.b));",
               argomento={"a": a, "b": b}) is False


def test_commento_assente_torna_undefined_non_il_primo():
    """Il gauge usa l'assenza per restare NEUTRO: se tornasse il primo elemento
    mostrerebbe il giudizio di un altro KPI."""
    trovato = _ts(
        "emit(m.commentoPerKpi(input.commenti, 'Non Esiste') ?? null);",
        argomento={"commenti": [
            {"kpi_nome": "MOL", "percentuale": "8%", "commento": "x",
             "emoji": "🟠", "colore": "#ea580c"},
        ]},
    )
    assert trovato is None
