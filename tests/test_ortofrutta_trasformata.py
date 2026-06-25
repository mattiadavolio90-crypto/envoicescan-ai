"""Regola dominio (Mattia 25/06): VERDURE e FRUTTA contengono SOLO prodotti
freschi o surgelati. La frutta/verdura TRASFORMATA o CONSERVATA (in scatola,
sciroppata, sottolio, sottaceto, in salamoia, concentrata, essiccata, in polvere,
pelati...) va in SCATOLAME E CONSERVE.

I SURGELATI/CONGELATI NON sono marcatori di conservazione: restano ortofrutta.
La regola scatta SOLO quando la categoria risultante sarebbe VERDURE/FRUTTA, così
non tocca altri alimenti (es. salse, pesce sottolio gestiti altrove).
"""
import importlib

import pytest

ai = importlib.import_module("services.ai_service")
f = ai.applica_correzioni_dizionario

SENT = "__NO_MATCH__"


@pytest.mark.parametrize("desc", [
    "DOPPIO CONCENTRATO DI POMODORO 12X440G",
    "CONCENTRATO POMODORO 400G",
    "POMODORI PELATI 6X3KG",
    "PASSATA POMODORO 700G",
    "PESCHE SCIROPPATE 6X400G",
    "ANANAS SCIROPPATO",
    "OLIVE IN SALAMOIA 5KG",
    "CARCIOFINI SOTTOLIO 1KG",
    "CIPOLLE SOTTACETO",
    "FUNGHI SECCHI ESSICCATI",
    "FAGIOLI IN BARATTOLO",
])
def test_ortofrutta_trasformata_va_in_scatolame(desc):
    """Anche partendo da una proposta VERDURE/FRUTTA, il marcatore di conservazione
    riporta a SCATOLAME E CONSERVE."""
    assert f(desc, "VERDURE") == "SCATOLAME E CONSERVE"
    assert f(desc, "FRUTTA") == "SCATOLAME E CONSERVE"


@pytest.mark.parametrize("desc,attesa", [
    ("POMODORO RAMATO 5KG", "VERDURE"),
    ("POMODORI GRAPPOLO", "VERDURE"),
    ("CAROTE FRESCHE 10KG", "VERDURE"),
    ("SPINACI SURGELATI 1KG", "VERDURE"),
    ("ZUCCA DELICA", "VERDURE"),
    ("MELE GOLDEN", "FRUTTA"),
    ("BANANE 18KG", "FRUTTA"),
    ("ANANAS FRESCO", "FRUTTA"),
])
def test_ortofrutta_fresca_o_surgelata_resta(desc, attesa):
    """Freschi e SURGELATI restano in VERDURE/FRUTTA: surgelato non è conserva."""
    assert f(desc, attesa) == attesa


def test_surgelato_non_e_marcatore():
    """SURGELAT/CONGELAT esplicitamente NON spostano in SCATOLAME."""
    assert f("PISELLI SURGELATI 2,5KG", "VERDURE") == "VERDURE"
    assert f("FRUTTI DI BOSCO CONGELATI", "FRUTTA") == "FRUTTA"


def test_regola_non_tocca_altri_alimenti():
    """La regola scatta SOLO se la categoria base è VERDURE/FRUTTA: un alimento
    non-ortofrutta con un marcatore di conservazione NON viene spostato a SCATOLAME
    dalla regola (resta nella sua categoria)."""
    # PESCE + 'sottolio': non è ortofrutta → la regola non interviene
    assert f("TONNO SOTTOLIO 3X80G", "PESCE") == "PESCE"
    # LATTICINI + 'in salamoia' (es. mozzarella): non è ortofrutta → invariato
    assert f("MOZZARELLA IN SALAMOIA 1KG", "LATTICINI") == "LATTICINI"
