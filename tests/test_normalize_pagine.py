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


def test_trigger_servizi_off_viaggia_al_client():
    """Il flag dei suggerimenti serve AL CLIENT, che decide se mostrarli.

    Difetto trovato il 3/9: veniva filtrato qui perche' non e' una chiave-pagina,
    quindi `triggerAbilitati` (trigger-servizi.ts) non lo trovava mai nella lista
    e restituiva sempre true. L'admin lo spegneva, il DB lo registrava, il
    cliente continuava a vedere i suggerimenti. Nessun test lo copriva.
    """
    out = fw._normalize_pagine({"margini": True, "trigger_servizi_off": True})
    assert out is not None
    assert "trigger_servizi_off" in out


def test_trigger_servizi_off_spento_non_viaggia():
    # Convenzione inversa: il flag esiste solo quando i trigger vanno SPENTI.
    out = fw._normalize_pagine({"margini": True, "trigger_servizi_off": False})
    assert out == ["margini"]


class TestFlagPerTab:
    """Chiavi `tab_off_<sezione>_<tab>` (apps/web/src/lib/tab-flags.ts)."""

    def test_chiave_tab_viaggia_insieme_alle_pagine(self):
        out = fw._normalize_pagine({"margini": True, "tab_off_margini_coperti": True})
        assert out is not None
        assert set(out) == {"margini", "tab_off_margini_coperti"}

    def test_tab_accesa_non_viaggia(self):
        # Convenzione inversa: assente/False = tab ACCESA. E' cio' che protegge i
        # clienti esistenti, che non hanno nessuna chiave tab.
        out = fw._normalize_pagine({"margini": True, "tab_off_margini_coperti": False})
        assert out == ["margini"]

    def test_solo_chiavi_tab_resta_default_aperto(self):
        """La guardia OFFSIDE si valuta SOLO sulle chiavi-pagina.

        Se le chiavi tab la facessero scattare, un cliente con i soli 'tab_off_*'
        impostati perderebbe tutto il menu: lo stesso bug, un piano piu' in basso.
        """
        assert fw._normalize_pagine({"tab_off_margini_coperti": True}) is None

    def test_sezione_inventata_scartata(self):
        out = fw._normalize_pagine({"margini": True, "tab_off_pippo_x": True})
        assert out == ["margini"]

    def test_prefisso_senza_tab_scartato(self):
        for k in ("tab_off_", "tab_off_margini", "tab_off_margini_"):
            out = fw._normalize_pagine({"margini": True, k: True})
            assert out == ["margini"], k

    def test_chiave_sconosciuta_resta_fuori(self):
        out = fw._normalize_pagine({"margini": True, "chiave_inventata": True})
        assert out == ["margini"]


def test_i_tool_della_chat_non_cambiano_con_le_chiavi_tab():
    """Invariante: le chiavi trasportate NON devono alterare il gate dei tool.

    _normalize_pagine alimenta anche la chat AI (fastapi_worker: `_TOOL_FLAG`).
    Il gate e' sicuro solo finche' interroga la lista per appartenenza puntuale
    di una chiave-pagina. Qui si confronta l'esito REALE del filtro con e senza
    chiavi extra: se qualcuno lo riscrivesse iterando la lista, questo fallisce.
    """
    tool_flag = {
        "query_costi": "analisi_fatture",
        "ultimi_acquisti": "analisi_fatture",
        "query_scadenze": "scadenziario",
        "query_margini": "margini",
        "query_coperti": "margini",
        "confronto_prezzi": "prezzi",
        "trend_prezzo": "prezzi",
        "query_appuntamenti": "agenda",
    }

    def tool_ammessi(raw):
        pagine = fw._normalize_pagine(raw)
        if pagine is None:
            return set(tool_flag)
        attive = set(pagine)
        return {t for t, flag in tool_flag.items() if flag in attive}

    base = {"margini": True, "prezzi": True, "analisi_fatture": False}
    con_extra = {
        **base,
        "tab_off_margini_coperti": True,
        "tab_off_prezzi_score": True,
        "trigger_servizi_off": True,
    }
    assert tool_ammessi(con_extra) == tool_ammessi(base)
    assert tool_ammessi(base) == {
        "query_margini", "query_coperti", "confronto_prezzi", "trend_prezzo",
    }
