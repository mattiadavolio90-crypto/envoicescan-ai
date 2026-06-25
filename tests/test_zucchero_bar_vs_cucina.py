"""Regola dominio (Mattia 25/06): lo ZUCCHERO si divide per USO/dimensione.

- MONODOSE per il caffe' (bustine 4g, scatole da centinaia/migliaia di pezzi,
  "monodose") = consumabile di servizio bar → VARIE BAR.
- DA CUCINA in confezione grande (busta/sacco kg, velo, semolato, canna in
  confezione) = ingrediente dispensa → SCATOLAME E CONSERVE.

La parola "bustina" da sola NON discrimina (esiste "busta 10kg"): conta il
marcatore monodose (grammatura piccola + tanti pezzi).
"""
import importlib

import pytest

ai = importlib.import_module("services.ai_service")
f = ai.applica_correzioni_dizionario
SENT = "__NO_MATCH__"


@pytest.mark.parametrize("desc", [
    "ZUCCHERO BUSTINE CANNA GR.4 X KG.4 (1000 PZ) NOVARESE",
    "ZUCCHERO BUSTINE BIANCO GR.4 X KG.8 (2000 PZ)",
    "ZUCCHERO CANNA BUSTINE 4G 10KG",
    "ZUCCHERO BIANCO BUSTINE 4G 10KG",
    "BUSTINE ZUCCHERO MONODOSE",
])
def test_zucchero_monodose_va_in_varie_bar(desc):
    assert f(desc, SENT) == "VARIE BAR"


@pytest.mark.parametrize("desc", [
    "ZUCCHERO IN BUSTA DA 1KGX10",
    "ZUCCHERO VELO IMPALPABILE KG1 ARPA",
    "ZUCCHERO SEMOLATO BUSTINE LOGO",
    "ZUCCHERO KG1 ERIDANIA",
    "KG3 ZUCCHERO CANNA RIOBA",
    "ZUCCHERO BIANCO IN BUSTINA SEMPIONE 10KG",  # 'bustina' ma sacco 10kg → cucina
])
def test_zucchero_da_cucina_va_in_scatolame(desc):
    assert f(desc, SENT) == "SCATOLAME E CONSERVE"


def test_zucchero_default_e_scatolame():
    """Senza marcatori, lo zucchero generico è dispensa, non bar."""
    assert f("ZUCCHERO", SENT) == "SCATOLAME E CONSERVE"
