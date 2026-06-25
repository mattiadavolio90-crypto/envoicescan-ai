"""Regola dominio (Mattia 25/06): la PASTA RIPIENA si classifica per FORMA,
non per ripieno.

Raviolo / wonton / gyoza / dumpling / xiaolongbao / shumai / involtino-primavera
(asiatico) = pasta ripiena → PASTA E CEREALI, a prescindere dal contenuto
(gamberi, manzo, verza). Il ripieno NON deve vincere: "ravioli di gamberi" è pasta,
non pesce.

Eccezione: l'involtino "di carne" ALL'ITALIANA (fettina arrotolata) NON ha il
marcatore asiatico → resta CARNE/SALUMI.
"""
import importlib

import pytest

ai = importlib.import_module("services.ai_service")
f = ai.applica_correzioni_dizionario
SENT = "__NO_MATCH__"


@pytest.mark.parametrize("desc", [
    "RAVIOLI DI GAMBERI HAUKAU 5*2KG",
    "RAVIOLI DI POLPO",
    "RAVIOLI DI MANZO",
    "RAVIOLI PESCE KG1 (5) S GINESTRA",
    "RAVIOLI VERZA E CARNE LVYUAN 2X2,5KG",
    "INVOLTINO VIETNAM (POLLO) 7X1,9KGX50PZ",
    "INVOLTINO VIETNAM(MAIALE) 1,75X7PZ",
    "GYOZA CON CARNE E CAVOLA 2,5KG",
    "DUMPLING GAMBERI",
    "SHUMAI DI MAIALE",
    "XIAOLONGBAO MAIALE",
    "SPRING ROLL VEGETALI",
    "PASTO DI WONTON 30X300G",
])
def test_pasta_ripiena_va_in_pasta_e_cereali(desc):
    # Anche se il ripieno è pesce/carne, la forma-pasta vince.
    assert f(desc, "PESCE") == "PASTA E CEREALI"
    assert f(desc, "CARNE") == "PASTA E CEREALI"


@pytest.mark.parametrize("desc,categoria_base", [
    ("INVOLTINI DI CARNE BOVINA 1KG", "CARNE"),
    ("INVOLTINO POLLO ARROSTO", "CARNE"),
])
def test_involtino_italiano_non_diventa_pasta(desc, categoria_base):
    """Senza marcatore asiatico, l'involtino di carne all'italiana NON viene
    spostato in PASTA dalla regola forma-pasta (resta nella sua categoria)."""
    assert f(desc, categoria_base) == categoria_base
    # garanzia diretta: la regola pasta-ripiena non scatta senza marcatore asiatico
    assert ai._pasta_ripiena_per_forma(desc.upper(), categoria_base) == categoria_base
