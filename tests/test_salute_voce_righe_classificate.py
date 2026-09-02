"""La voce "Righe classificate" della card Salute non deve mentire.

Difetto misurato il 2/9/2026 su dati di produzione: il testo scegliva il ramo
"Nessuna riga da classificare" guardando le righe caricate negli ULTIMI 30
GIORNI invece di quelle da controllare. Quattro sedi su undici leggevano
"Nessuna riga da classificare" pur avendone — la peggiore 187 righe, ultimo
caricamento 21 luglio.

Il pallino della voce era corretto (`ok` guarda `da_controllare`) e anche il
deep-link a `?verifica=1`: mentiva solo la frase, che e' l'unica cosa che il
cliente legge.
"""
import inspect

from services.fastapi_worker import _dettaglio_righe_classificate as dettaglio


# ── I quattro casi reali che mentivano (righe da controllare, 0 caricate in 30gg)
def test_sede_ferma_da_luglio_con_187_righe_non_dice_nessuna():
    """Il caso peggiore misurato: 187 righe, nessun caricamento da 21 luglio."""
    assert dettaglio(187, 5620) == "187 righe da controllare"


def test_sede_ferma_con_30_righe():
    assert dettaglio(30, 4592) == "30 righe da controllare"


def test_sede_ferma_con_10_righe():
    assert dettaglio(10, 3888) == "10 righe da controllare"


def test_sede_ferma_con_una_sola_riga():
    """Anche una riga sola va detta: era "Nessuna riga da classificare"."""
    assert dettaglio(1, 63) == "1 righe da controllare"


# ── I casi che erano già corretti, e devono restare tali ────────────────────
def test_sede_attiva_col_conteggio():
    assert dettaglio(156, 6743) == "156 righe da controllare"


def test_casati14_tutte_classificate():
    """CASATI 14 (Francesco): 1.264 righe, zero da controllare."""
    assert dettaglio(0, 1264) == "Tutte le righe sono classificate"


def test_sede_senza_alcuna_riga():
    """L'unico caso in cui "Nessuna riga da classificare" e' vero."""
    assert dettaglio(0, 0) == "Nessuna riga da classificare"


# ── Le due proprieta' che il difetto violava ────────────────────────────────
def test_il_conteggio_non_dipende_dalle_righe_totali():
    """Chi ha righe da controllare le vede dette, quale che sia la storia della
    sede. Era esattamente cio' che il ramo su `tot_righe` rompeva."""
    for totali in (0, 1, 23, 1264, 39249):
        assert dettaglio(7, totali) == "7 righe da controllare", totali


def test_mai_nessuna_riga_quando_ce_ne_sono_da_controllare():
    """La frase falsa non deve poter uscire con da_controllare > 0."""
    for n in (1, 10, 30, 187, 518):
        for totali in (0, 100, 10000):
            assert dettaglio(n, totali) != "Nessuna riga da classificare"


def test_la_voce_non_guarda_piu_la_finestra_recente():
    """Guardia strutturale: il sorgente non deve tornare a decidere il testo
    su `tot_righe` (le righe dei 30 giorni). Uccide il mutante che ripristina
    il ternario vecchio dentro home_salute."""
    import services.fastapi_worker as fw

    corpo = inspect.getsource(fw.home_salute)
    assert "_dettaglio_righe_classificate(" in corpo
    assert "Nessuna riga da classificare" not in corpo, (
        "il testo e' tornato inline in home_salute: decide di nuovo su tot_righe"
    )
