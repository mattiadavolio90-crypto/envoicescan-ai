"""Test dell'harness stesso — `tests/helpers_ts.py`.

Perché esiste: 12 file di test dipendono da `esegui_ts`, e fino all'1/9 nessuno
verificava l'harness. Il difetto trovato quel giorno era proprio di questa
natura: `json.dumps(argomento)` finiva in coda a `node -e <script>`, quindi un
argomento che inizia con `-` (un numero negativo) veniva letto da node **come
flag** — `node: bad option: -2.675`, rc=9, **stderr vuoto**. Un fallimento che
si legge come «il modulo sotto test è rotto», non come «l'harness rifiuta
l'input».

Era invisibile perché ogni test esistente passava dict o liste, che in JSON
iniziano con `{` o `[`. Un harness che non ha mai ricevuto un certo input non è
provato su quell'input, per quanti test verdi abbia.

Il modulo usato come cavia è `lib/catena-export` con `emit(input)`: rimanda
indietro l'argomento senza toccarlo, così il test misura il **trasporto**, non
la logica.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-export"


def _round_trip(argomento):
    """Manda `argomento` a node e se lo fa restituire identico."""
    return esegui_ts(MODULO, "emit(input);", argomento=argomento, richiede=["arrotonda2"])


@pytest.mark.parametrize(
    "argomento",
    [
        pytest.param(None, id="none"),
        pytest.param({"a": 1}, id="dict"),
        pytest.param([1, 2, 3], id="lista"),
        pytest.param("ciao", id="stringa"),
        pytest.param(42, id="int-positivo"),
        pytest.param(0, id="zero"),
        pytest.param(True, id="bool"),
        pytest.param("", id="stringa-vuota"),
        pytest.param({"n": -5, "l": [-1.5]}, id="negativi-annidati"),
    ],
)
def test_argomento_arriva_a_node_identico(argomento):
    """I tipi già in uso nei 12 file esistenti: nessuna regressione ammessa."""
    assert _round_trip(argomento) == argomento


@pytest.mark.parametrize(
    "argomento",
    [
        pytest.param(-42, id="int-negativo"),
        pytest.param(-2.675, id="float-negativo"),
        pytest.param(-0.001, id="float-negativo-piccolo"),
        pytest.param([-1, -2], id="lista-di-negativi"),
    ],
)
def test_argomento_negativo_non_viene_letto_come_flag(argomento):
    """La regressione da impedire: senza `--` nel comando node, questi
    argomenti fanno uscire il processo con rc=9 e stderr vuoto.

    Se questo test torna a fallire, **non cercare il bug nel modulo sotto
    test**: guarda `subprocess.run` in `helpers_ts.esegui_ts`.
    """
    assert _round_trip(argomento) == argomento


@pytest.mark.parametrize(
    "argomento",
    [
        pytest.param("--help", id="stringa-che-pare-flag"),
        pytest.param("-v", id="stringa-trattino"),
        pytest.param("--", id="stringa-doppio-trattino"),
    ],
)
def test_stringa_che_sembra_un_flag_resta_un_dato(argomento):
    """L'altro lato del fix: `--` non deve far sparire né alterare una stringa
    che *assomiglia* a un'opzione. Sono dati, non argomenti di node."""
    assert _round_trip(argomento) == argomento


def test_funzione_mancante_fallisce_invece_di_passare_per_caso():
    """`richiede` è una difesa contro il test che passa perché la funzione non
    c'è più: deve **fallire**, non skippare in silenzio."""
    with pytest.raises(AssertionError):
        esegui_ts(MODULO, "emit(1);", richiede=["funzioneCheNonEsisteDavvero"])


def test_modulo_inesistente_lo_dice_esplicitamente():
    with pytest.raises(AssertionError, match="non esiste"):
        esegui_ts("lib/modulo-che-non-esiste-affatto", "emit(1);")
