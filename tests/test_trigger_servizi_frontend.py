"""`triggerAbilitati` decide se il cliente vede i suggerimenti commerciali.

Questa funzione era **corretta e senza alcun test**, mentre il difetto stava a
monte: `_normalize_pagine` scartava `trigger_servizi_off` perche' non e' una
chiave-pagina, quindi la lista non lo conteneva mai e qui si tornava sempre
`true`. L'admin spegneva l'interruttore, il DB lo registrava, il cliente
continuava a vedere i suggerimenti — e nessuno dei due lati era "sbagliato" da
solo. Il presidio della giunzione sta in `test_tab_flags_frontend.py`; qui si
fissa l'estremo TS, che restava scoperto.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/trigger-servizi"
_RICHIEDE = ["triggerAbilitati"]


def _abilitati(pagine):
    return esegui_ts(
        MODULO, "emit(m.triggerAbilitati(input))", pagine, richiede=_RICHIEDE
    )


def test_admin_vede_i_trigger():
    # pagine == null = nessuna restrizione.
    assert _abilitati(None) is True


def test_cliente_senza_flag_vede_i_trigger():
    # Convenzione inversa: assente = ACCESI, anche per i clienti esistenti.
    assert _abilitati(["margini", "prezzi"]) is True


def test_flag_presente_spegne_i_trigger():
    assert _abilitati(["margini", "trigger_servizi_off"]) is False
