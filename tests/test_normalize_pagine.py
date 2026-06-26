"""Guardie su _normalize_pagine: decide il menu del PV da users.pagine_abilitate.

Bug OFFSIDE (26/06): pagine_abilitate = {"blocco_mesi_precedenti": false} — un dict
non-null SENZA chiavi-pagina — veniva normalizzato a [] (lista vuota), che la
sidebar interpreta come "tutte le pagine bloccate". Il cliente scendeva nel punto
vendita ma vedeva solo la Home: sembrava "non uscire dalla catena".
"""
import os

os.environ.setdefault("WORKER_DEV_MODE", "1")  # salta il guard worker-key all'import

import services.fastapi_worker as fw


def test_none_resta_none_default_aperto():
    # pagine_abilitate=NULL → default aperto (sidebar mostra tutto).
    assert fw._normalize_pagine(None) is None


def test_dict_senza_chiavi_pagina_e_default_aperto():
    # Solo impostazioni non-pagina → NON "tutto bloccato", ma default aperto.
    assert fw._normalize_pagine({"blocco_mesi_precedenti": False}) is None
    assert fw._normalize_pagine({"blocco_mesi_precedenti": True}) is None


def test_dict_con_pagine_filtra_solo_quelle_attive():
    raw = {
        "agenda": True, "prezzi": True, "margini": True, "workspace": True,
        "scadenziario": True, "analisi_e_tag": True, "analisi_fatture": True,
        "blocco_mesi_precedenti": False,
    }
    out = fw._normalize_pagine(raw)
    assert out is not None
    assert "blocco_mesi_precedenti" not in out  # impostazione, non pagina
    assert set(out) == {
        "agenda", "prezzi", "margini", "workspace",
        "scadenziario", "analisi_e_tag", "analisi_fatture",
    }


def test_dict_pagina_spenta_resta_esclusa():
    # Qui esiste almeno una chiave-pagina → il dict È un set pagine esplicito:
    # le pagine a False restano bloccate (comportamento voluto).
    out = fw._normalize_pagine({"margini": True, "prezzi": False})
    assert out == ["margini"]


def test_lista_passthrough():
    assert fw._normalize_pagine(["margini", "prezzi"]) == ["margini", "prezzi"]
