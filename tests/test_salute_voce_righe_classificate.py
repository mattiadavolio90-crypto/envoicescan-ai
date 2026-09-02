"""La voce "Righe classificate" della card Salute non deve mentire.

Difetto misurato il 2/9/2026 su dati di produzione: il testo scegliva il ramo
"Nessun prodotto da classificare" guardando le righe caricate negli ULTIMI 30
GIORNI invece di quelle da controllare. Quattro sedi su undici leggevano
"Nessun prodotto da classificare" pur avendone — la peggiore 187 righe, ultimo
caricamento 21 luglio.

Il pallino della voce era corretto (`ok` guarda `da_controllare`) e anche il
deep-link a `?verifica=1`: mentiva solo la frase, che e' l'unica cosa che il
cliente legge.

AGGIORNAMENTO 02/09/2026 (fase B3): `da_controllare` ora sono i PRODOTTI DISTINTI,
non le righe — prima Salute e briefing mostravano due numeri per la stessa cosa
(San Giuliano 187 righe vs 112 prodotti, Villa Guardia 156 vs 100). Cambiato di
conseguenza anche il sostantivo della frase: dire "112 righe" a chi ne ha 187
sarebbe la stessa bugia di prima, con un'unita' di misura al posto di un ramo.
Le cifre qui sotto sono ora i PRODOTTI misurati a DB.
"""
import inspect

from services.fastapi_worker import _dettaglio_righe_classificate as dettaglio


# ── I quattro casi reali che mentivano (righe da controllare, 0 caricate in 30gg)
def test_sede_ferma_da_luglio_con_112_prodotti_non_dice_nessuna():
    """Il caso peggiore misurato: 112 prodotti (187 righe), fermo dal 21 luglio."""
    assert dettaglio(112, 5620) == "112 prodotti da controllare"


def test_sede_ferma_con_18_prodotti():
    assert dettaglio(18, 4592) == "18 prodotti da controllare"


def test_sede_ferma_con_5_prodotti():
    assert dettaglio(5, 3888) == "5 prodotti da controllare"


def test_sede_ferma_con_una_sola_riga():
    """Anche una riga sola va detta: era "Nessun prodotto da classificare"."""
    assert dettaglio(1, 63) == "1 prodotto da controllare"


# ── I casi che erano già corretti, e devono restare tali ────────────────────
def test_sede_attiva_col_conteggio():
    assert dettaglio(156, 6743) == "156 prodotti da controllare"


def test_casati14_tutte_classificate():
    """CASATI 14 (Francesco): 1.264 righe, zero da controllare."""
    assert dettaglio(0, 1264) == "Tutti i prodotti sono classificati"


def test_sede_senza_alcuna_riga():
    """L'unico caso in cui "Nessun prodotto da classificare" e' vero."""
    assert dettaglio(0, 0) == "Nessun prodotto da classificare"


# ── Le due proprieta' che il difetto violava ────────────────────────────────
def test_il_conteggio_non_dipende_dalle_righe_totali():
    """Chi ha righe da controllare le vede dette, quale che sia la storia della
    sede. Era esattamente cio' che il ramo su `tot_righe` rompeva."""
    for totali in (0, 1, 23, 1264, 39249):
        assert dettaglio(7, totali) == "7 prodotti da controllare", totali


def test_mai_nessuna_riga_quando_ce_ne_sono_da_controllare():
    """La frase falsa non deve poter uscire con da_controllare > 0."""
    for n in (1, 10, 30, 187, 518):
        for totali in (0, 100, 10000):
            assert dettaglio(n, totali) != "Nessun prodotto da classificare"


def test_la_voce_non_guarda_piu_la_finestra_recente():
    """Guardia strutturale: il sorgente non deve tornare a decidere il testo
    su `tot_righe` (le righe dei 30 giorni). Uccide il mutante che ripristina
    il ternario vecchio dentro home_salute."""
    import services.fastapi_worker as fw

    corpo = inspect.getsource(fw.home_salute)
    assert "_dettaglio_righe_classificate(" in corpo
    assert "Nessun prodotto da classificare" not in corpo, (
        "il testo e' tornato inline in home_salute: decide di nuovo su tot_righe"
    )
