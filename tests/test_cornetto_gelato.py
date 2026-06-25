"""Regola dominio (Mattia 25/06): CORNETTO gelato vs brioche.

"CORNETTO" di default è la brioche da forno → PASTICCERIA. Ma il CORNETTO GELATO
(Algida/Almagel/Sammontana, "cornetto max/classico") è un gelato → GELATI E DESSERT.
Discrimine: CORNETTO + marcatore-gelato (marchio gelataio, variante tipica del cono
gelato, o la parola GELATO). Senza marcatore la brioche-cornetto resta PASTICCERIA.

Caso reale: CASATI riceve cornetti Algida (via ALMAGEL) finiti in PASTICCERIA
confusi con i cornetti-brioche.
"""
import importlib

import pytest

ai = importlib.import_module("services.ai_service")
f = ai.applica_correzioni_dizionario


@pytest.mark.parametrize("desc", [
    "CORNETTO CLASSICO",
    "CORNETTO MAX NOCCIOLA CIOCCOL",
    "CORNETTO MAX PISTACCHIO",
    "CORNETTO ALGIDA",
    "CORNETTO GELATO VANIGLIA",
    "FA CORNETTO REB. GL VUOTO",
])
def test_cornetto_gelato_va_in_dessert(desc):
    """Il cornetto-gelato proposto come PASTICCERIA viene riportato a GELATI E DESSERT."""
    assert f(desc, "PASTICCERIA") == "GELATI E DESSERT"


@pytest.mark.parametrize("desc", [
    "CORNETTI BURRO 50PZ",
    "CORNETTO VUOTO SFOGLIATO",
    "CORNETTO INTEGRALE FARCITO",
    "CROISSANT CORNETTO ALBICOCCA",
])
def test_cornetto_brioche_resta_pasticceria(desc):
    """Il cornetto-brioche (senza marcatore gelato) resta PASTICCERIA."""
    assert f(desc, "PASTICCERIA") == "PASTICCERIA"
