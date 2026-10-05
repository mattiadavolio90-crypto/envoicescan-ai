"""Le spese scritte a mano si salvano con la cifra pagata, IVA compresa.

Mattia, 5/10/2026: una spesa senza fattura (scontrino, contanti) non scarica
l'IVA, che diventa costo; le fatture arrivano dallo SDI, quindi cio' che si
scrive a mano nelle Spese e' senza fattura. Lo scorporo del 3/10 (modulo Spese e
assistente) sottostimava il costo ed e' stato tolto: qui le rotte salvano
l'importo com'e', anche se un client di prima del deploy manda `iva_inclusa`.
L'assistente ha gli stessi presidi in `test_assistente_spesa_extra.py`.
"""
from pathlib import Path

import pytest

import services.routers.workspace as workspace
from tests.test_spese_extra import _crea_e_leggi_payload, _patch_e_leggi_updates

_TSX = Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)/workspace/spese-view.tsx"


def _body_nuova(**kw):
    base = dict(data_spesa="2026-10-02", tipo="fb", importo=120.0, descrizione="latte", categoria="LATTICINI")
    return workspace.NuovaSpesaBody(**{**base, **kw})


def test_la_spesa_si_salva_con_l_importo_pagato():
    assert _crea_e_leggi_payload(_body_nuova())["importo"] == 120.0


@pytest.mark.parametrize("aliquota", [4, 10, 22, 7])
def test_l_iva_di_un_client_vecchio_non_si_scorpora(aliquota):
    assert _crea_e_leggi_payload(_body_nuova(iva_inclusa=aliquota))["importo"] == 120.0


def test_la_modifica_salva_l_importo_pagato():
    body = workspace.AggiornaSpesaBody(importo=22.0, iva_inclusa=22)
    assert _patch_e_leggi_updates(body, "LATTICINI")["importo"] == 22.0


def test_la_modifica_senza_importo_non_lo_tocca_anche_con_l_iva():
    updates = _patch_e_leggi_updates(workspace.AggiornaSpesaBody(iva_inclusa=10, descrizione="x"), "LATTICINI")
    assert "importo" not in updates and updates["descrizione"] == "x"


def test_l_importo_si_arrotonda_al_centesimo():
    assert _crea_e_leggi_payload(_body_nuova(importo=10.005))["importo"] == round(10.005, 2)


def test_il_modulo_spese_non_chiede_ne_manda_l_iva():
    """Cablaggio del .tsx (non eseguibile qui): niente domanda sull'IVA, niente
    `iva_inclusa` nel corpo, e la riga che dice di scrivere la cifra pagata."""
    tsx = _TSX.read_text(encoding="utf-8")
    assert "iva_inclusa" not in tsx and "comprende l&apos;IVA" not in tsx
    assert "Scrivi quanto hai pagato, IVA compresa" in tsx
