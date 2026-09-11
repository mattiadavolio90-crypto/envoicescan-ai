"""Ricette, coperti e centri di produzione sono spenti per un negozio.

Fase 3, seconda casella. Sono tab che per un negozio non hanno significato: le
ricette e i coperti descrivono un servizio al tavolo che non esiste (la cassa di
un retail manda solo il fatturato), e i centri di produzione sono 5 secchi food
che un negozio con UNA categoria merce vedrebbe a zero, con le emoji di un
ristorante sopra.

Nessun meccanismo nuovo: si riusa quello dei flag per-tab dell'admin
(`tab_off_*`, `apps/web/src/lib/tab-flags.ts`), con la sua CONVENZIONE INVERSA —
la chiave e' presente quando la tab e' SPENTA. E' la ragione per cui i clienti
ristorazione non cambiano di una virgola: non hanno nessuna di quelle chiavi, e
il percorso che li riguarda resta identico.

`_normalize_pagine` NON e' stata toccata: ha cinque chiamanti e presidi che ne
asseriscono la firma. Gli spegnimenti stanno in una funzione separata.
"""
from __future__ import annotations

import pytest

import services.fastapi_worker as fw
import services.settore_service as ss
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE

_SPENTI_RETAIL = {
    "tab_off_workspace_foodcost",
    "tab_off_margini_coperti",
    "tab_off_margini_analisi",
}


class TestIlRistoranteNonCambiaDiUnaVirgola:
    """Il vincolo di Mattia, misurato invece che dichiarato."""

    @pytest.mark.parametrize("raw", [
        None,
        {"margini": True},
        {"margini": True, "prezzi": False},
        {"blocco_mesi_precedenti": True},
        ["margini", "prezzi"],
        {"margini": True, "tab_off_margini_coperti": True},
    ])
    def test_per_un_ristorante_e_identico_a_normalize_pagine(self, raw):
        assert fw._pagine_con_settore(raw, SETTORE_RISTORAZIONE) == fw._normalize_pagine(raw)

    @pytest.mark.parametrize("settore", [None, "", "settore-mai-visto"])
    def test_un_settore_assente_o_ignoto_non_spegne_niente(self, settore):
        # Fail-safe nella stessa direzione di settore_service: nel dubbio, il
        # comportamento dei ristoranti. Un negozio visto da ristorante e'
        # un'etichetta sbagliata; il contrario e' una pagina spenta a un pagante.
        assert fw._pagine_con_settore(None, settore) is None
        assert fw._pagine_con_settore({"margini": True}, settore) == ["margini"]


class TestIlNegozioHaLeTabSpente:

    def test_senza_restrizioni_il_negozio_riceve_comunque_gli_spegnimenti(self):
        # Il caso che conta: pagine_abilitate=None e' il default di quasi tutti
        # gli account. Se restasse None, gli spegnimenti non arriverebbero mai.
        out = fw._pagine_con_settore(None, SETTORE_RETAIL)
        assert out is not None
        assert _SPENTI_RETAIL <= set(out)

    def test_senza_restrizioni_il_negozio_vede_tutte_le_pagine(self):
        # "Nessuna restrizione" per un negozio significa tutte le pagine aperte,
        # non nessuna: la lista deve portarle tutte, o spegnerei il menu.
        out = fw._pagine_con_settore(None, SETTORE_RETAIL)
        assert fw._PAGINE_FLAG <= set(out)

    def test_con_restrizioni_gli_spegnimenti_si_aggiungono(self):
        out = fw._pagine_con_settore({"margini": True}, SETTORE_RETAIL)
        assert "margini" in out
        assert _SPENTI_RETAIL <= set(out)

    def test_nessuna_chiave_duplicata(self):
        # Un negozio a cui l'admin ha gia' spento i coperti a mano non deve
        # ritrovarsi la chiave due volte.
        out = fw._pagine_con_settore(
            {"margini": True, "tab_off_margini_coperti": True}, SETTORE_RETAIL
        )
        assert len(out) == len(set(out))

    def test_le_chiavi_sono_riconosciute_dal_worker(self):
        # Una chiave inventata viaggerebbe senza spegnere niente: `_is_tab_off_key`
        # e' lo stesso filtro che le fa sopravvivere a `_normalize_pagine`.
        for k in _SPENTI_RETAIL:
            assert fw._is_tab_off_key(k), f"{k} non passa il filtro del worker"

    def test_le_chiavi_esistono_davvero_nel_frontend(self):
        """Il presidio che vale: una chiave giusta di forma ma inesistente di
        fatto non spegne niente, e nessun test lo direbbe.

        Legge la costante VIVA, non `_SPENTI_RETAIL`: la prima stesura
        confrontava il TS con la lista attesa scritta qui sopra, e un mutante che
        storpiava la chiave nel codice (`copertini`) cambiava le due in blocco —
        il test restava verde su una chiave inesistente. Misurato l'11/9/2026 col
        mutante 10, che questo presidio non vedeva.
        """
        import re
        from pathlib import Path
        ts = Path("apps/web/src/lib/tab-flags.ts").read_text(encoding="utf-8")
        blocco = ts.split("TAB_SEZIONI", 1)[1]
        reali = {
            f"tab_off_{sez}_{tab}"
            for sez, corpo in re.findall(r"(\w+):\s*\[(.*?)\]", blocco, re.S)
            for tab in re.findall(r'key:\s*"([^"]+)"', corpo)
        }
        usate = set(fw._TAB_OFF_PER_SETTORE[SETTORE_RETAIL])
        assert usate <= reali, f"chiavi inesistenti nel frontend: {usate - reali}"
