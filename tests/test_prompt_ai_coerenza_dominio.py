"""Il prompt AI deve rispettare la regola di dominio #1 di CLAUDE.md.

`config/prompt_ai_potenziato.py` non aveva alcun test. Fino al 29/8/2026
conteneva la riga:

    "DEVI classificare OGNI articolo. 'Da Classificare' NON è MAI una risposta
     valida. Se non sei sicuro, scegli la categoria PIÙ PROBABILE"

che e' la negazione esatta della regola #1 ("una riga si classifica SOLO se
dizionario/regole o l'AI la riconoscono con sicurezza"). La rete a valle
reggeva, ma la regola viveva in due posti che si contraddicevano e quello
senza test era il prompt. Il prompt si contraddiceva perfino da solo: altre
righe istruivano l'AI su cosa NON mettere in "Da Classificare", presupponendo
che potesse usarla.
"""

import re

import pytest

from config.constants import CATEGORIA_NON_CLASSIFICATA
from config.prompt_ai_potenziato import (
    PROMPT_CLASSIFICAZIONE_AI,
    get_prompt_classificazione,
)


def test_il_prompt_non_vieta_la_categoria_di_dominio():
    """Nessuna riga deve dichiarare "Da Classificare" una risposta non valida."""
    testo = PROMPT_CLASSIFICAZIONE_AI
    divieti = re.findall(
        r'^.*"?Da Classificare"?.*(?:NON è MAI|non è mai|MAI una risposta).*$',
        testo, re.MULTILINE | re.IGNORECASE,
    )
    assert not divieti, (
        "Il prompt vieta all'AI la categoria che la regola di dominio #1 "
        f"impone di usare quando non riconosce la riga: {divieti}"
    )


def test_il_prompt_ammette_esplicitamente_la_categoria_di_dominio():
    assert CATEGORIA_NON_CLASSIFICATA in PROMPT_CLASSIFICAZIONE_AI


def test_il_prompt_non_spinge_a_indovinare_quando_incerto():
    """"Se non sei sicuro scegli la piu' probabile" e' esattamente il fallback
    travestito che la regola #1 ha eliminato."""
    testo = PROMPT_CLASSIFICAZIONE_AI.lower()
    assert "se non sei sicuro, scegli la categoria più probabile" not in testo


def test_il_divieto_su_note_e_diciture_resta():
    """La regola di dominio #2 vale ancora: NOTE e' riservata, l'AI non la usa."""
    assert "NOTE E DICITURE" in PROMPT_CLASSIFICAZIONE_AI
    assert re.search(
        r'NON usare MAI "NOTE E DICITURE"', PROMPT_CLASSIFICAZIONE_AI
    ), "Il divieto sulle NOTE all'AI e' corretto e non va rimosso"


def test_la_grafia_errata_non_compare():
    """'Da Clasificare' (una sola s) e' una variante sbagliata nota."""
    assert "Da Clasificare" not in PROMPT_CLASSIFICAZIONE_AI


def test_get_prompt_classificazione_sostituisce_gli_articoli():
    reso = get_prompt_classificazione("1. MOZZARELLA 500G")
    assert "{ARTICOLI}" not in reso
    assert "MOZZARELLA" in reso
