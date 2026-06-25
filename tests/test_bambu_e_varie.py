"""Regole dominio (Mattia 25/06) sulle categorie "VARIE".

1) BAMBÙ: stessa parola, due nature.
   - Bacchette/bastoncini/spiedini di bambù (monouso, posata) → MATERIALE DI CONSUMO
   - Germogli / bambù conservato / foglie (commestibile) → SUSHI VARIE
2) Snack da rivendita (taralli, tartine) → SHOP, non VARIE BAR.
3) Miele: confezione grande = dispensa → SCATOLAME; bustine monodose bar → VARIE BAR.
"""
import importlib

import pytest

ai = importlib.import_module("services.ai_service")
f = ai.applica_correzioni_dizionario
SENT = "__NO_MATCH__"


@pytest.mark.parametrize("desc", [
    "BASTONCINO BAMBU 2000PZ",
    "BASTONCINI DI BAMBU 200XPZ100 15CM",
    "BACCHETTE DI BAMBU NERI A 1000PZ",
    "BACCHETTE BAMBU SENZA GUSCIO 2000PZ",
    "250SPIEDINI BAMBU NODO 10CM MP",
])
def test_bambu_posata_va_in_materiale(desc):
    assert f(desc, SENT) == "MATERIALE DI CONSUMO"


@pytest.mark.parametrize("desc", [
    "BAMBU CONSERVATO 6X2900G",
    "GERMOGLI DI BAMBU CONSERVATI",
    "FOGLIE DI BAMBU SOTTOVUOTO",
])
def test_bambu_cibo_resta_sushi_varie(desc):
    assert f(desc, SENT) == "SUSHI VARIE"


@pytest.mark.parametrize("desc", [
    "SMART TARALLI CLASSIC-GR 500",
    "ESSEL. TARTINE GR.500-GR 500",
])
def test_snack_va_in_shop(desc):
    assert f(desc, SENT) == "SHOP"


def test_miele_grande_in_scatolame_bustine_in_bar():
    assert f("KG1 MIELE MILLEFIORI MC", SENT) == "SCATOLAME E CONSERVE"
    assert f("MIELE ACACIA 500G", SENT) == "SCATOLAME E CONSERVE"
    assert f("CONFEZIONE MIELE IN BUSTINE", SENT) == "VARIE BAR"
