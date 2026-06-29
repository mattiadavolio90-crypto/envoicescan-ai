"""Regressione: gli alert "dati mancanti" dell'Assistente AI costruivano il
bound superiore del mese precedente con giorno hardcoded 31 ("2026-06-31"), una
data INVALIDA per i mesi da 28/29/30 giorni. data_documento è una colonna DATE:
la query .lte("data_documento", "2026-06-31") sollevava un errore inghiottito da
un try/except, disattivando silenziosamente gli alert proprio il 1/7 (mese
precedente = giugno, 30 giorni). Il fix usa calendar.monthrange per l'ultimo
giorno reale del mese."""
from calendar import monthrange
from datetime import date

import pytest


def _bound_mese_precedente(oggi: date) -> tuple[str, str]:
    """Replica la logica del fix in _build_chat_system_prompt: inizio/fine del
    mese precedente con l'ultimo giorno REALE (mai -31 hardcoded)."""
    if oggi.month == 1:
        anno, mese = oggi.year - 1, 12
    else:
        anno, mese = oggi.year, oggi.month - 1
    inizio = f"{anno}-{mese:02d}-01"
    ultimo = monthrange(anno, mese)[1]
    fine = f"{anno}-{mese:02d}-{ultimo:02d}"
    return inizio, fine


@pytest.mark.parametrize("oggi", [date(2026, m, 1) for m in range(1, 13)])
def test_bound_fine_sempre_data_valida(oggi):
    """Per ogni mese dell'anno il bound 'fine' deve essere una data ISO valida."""
    _, fine = _bound_mese_precedente(oggi)
    # non deve lanciare: era il bug (es. "2026-06-31")
    date.fromisoformat(fine)


def test_go_live_1_luglio_mese_precedente_e_giugno_30():
    """Caso go-live: il 1/7/2026 il mese precedente è giugno → fine = 2026-06-30."""
    inizio, fine = _bound_mese_precedente(date(2026, 7, 1))
    assert inizio == "2026-06-01"
    assert fine == "2026-06-30", f"Atteso 2026-06-30 (giugno ha 30 giorni), trovato {fine}"


def test_gennaio_rollover_a_dicembre_anno_precedente():
    """A gennaio il mese precedente è dicembre dell'anno prima, con 31 giorni."""
    inizio, fine = _bound_mese_precedente(date(2026, 1, 15))
    assert inizio == "2025-12-01"
    assert fine == "2025-12-31"


def test_marzo_mese_precedente_febbraio_28_in_anno_non_bisestile():
    """A marzo 2026 (non bisestile) il mese precedente febbraio finisce il 28."""
    _, fine = _bound_mese_precedente(date(2026, 3, 10))
    assert fine == "2026-02-28"


def test_marzo_2028_febbraio_bisestile_29():
    """A marzo 2028 (bisestile) febbraio finisce il 29."""
    _, fine = _bound_mese_precedente(date(2028, 3, 10))
    assert fine == "2028-02-29"
