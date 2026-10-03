"""Scheda cliente → «Sotto-utenti» (`lib/sotto-utenti-admin.ts`): TS vero via node.

Le regole vere le applica il worker (400); qui conta che la scheda non lasci
spuntare la Catena senza tutte le sedi, che togliere una sede la tolga, e che
il proxy non inoltri al worker percorsi inventati.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/sotto-utenti-admin"
FUNZIONI = ["alterna", "catenaDisponibile", "erroreSelezione", "percorsoProxy", "pagineInOrdine", "selezioneIniziale"]

SEDI = [{"id": "s1", "nome": "NAVIGLI"}, {"id": "s2", "nome": "CASATI"}]
CLIENTE = "4f0f0000-0000-4000-8000-000000000001"
SU = "4f0f0000-0000-4000-8000-0000000000a1"


def _alterna(sel, tipo, voce, sedi=SEDI):
    return esegui_ts(MODULO, "emit(m.alterna(input.sel, input.tipo, input.voce, input.sedi));",
                     {"sel": sel, "tipo": tipo, "voce": voce, "sedi": sedi}, richiede=FUNZIONI)


def _catena(scelte, sedi=SEDI):
    return esegui_ts(MODULO, "emit(m.catenaDisponibile(input.scelte, input.sedi));",
                     {"scelte": scelte, "sedi": sedi}, richiede=FUNZIONI)


def _proxy(cliente, segmenti):
    return esegui_ts(MODULO, "emit(m.percorsoProxy(input.c, input.s));", {"c": cliente, "s": segmenti}, richiede=FUNZIONI)


def _errore(sel, email=None):
    codice = "emit(m.erroreSelezione(input.sel, input.email ?? undefined));"
    return esegui_ts(MODULO, codice, {"sel": sel, "email": email}, richiede=FUNZIONI)


def test_catena_solo_con_tutte_le_sedi():
    assert _catena(["s1"]) is False
    assert _catena(["s2", "s1"]) is True
    assert _catena([], []) is False


def test_spuntare_la_catena_senza_tutte_le_sedi_non_fa_niente():
    sel = {"pagine": ["home"], "sedi": ["s1"]}
    assert _alterna(sel, "pagine", "catena") == sel
    tutte = {"pagine": ["home"], "sedi": ["s1", "s2"]}
    assert _alterna(tutte, "pagine", "catena") == {"pagine": ["home", "catena"], "sedi": ["s1", "s2"]}


def test_togliere_una_sede_toglie_la_catena():
    sel = {"pagine": ["home", "catena"], "sedi": ["s1", "s2"]}
    assert _alterna(sel, "sedi", "s2") == {"pagine": ["home"], "sedi": ["s1"]}


def test_alterna_aggiunge_e_toglie():
    sel = {"pagine": [], "sedi": []}
    sel = _alterna(sel, "pagine", "margini")
    assert sel == {"pagine": ["margini"], "sedi": []}
    sel = _alterna(sel, "sedi", "s1")
    assert sel == {"pagine": ["margini"], "sedi": ["s1"]}
    assert _alterna(sel, "pagine", "margini") == {"pagine": [], "sedi": ["s1"]}


def test_errore_selezione():
    assert _errore({"pagine": [], "sedi": ["s1"]}) == "Scegli almeno una pagina"
    assert _errore({"pagine": ["home"], "sedi": []}) == "Scegli almeno una sede"
    assert _errore({"pagine": ["home"], "sedi": ["s1"]}) is None
    assert _errore({"pagine": ["home"], "sedi": ["s1"]}, "non-una-email") == "Email non valida"
    assert _errore({"pagine": ["home"], "sedi": ["s1"]}, " sala@locale.it ") is None


def test_proxy_solo_percorsi_noti():
    base = f"/api/admin/clienti/{CLIENTE}/sotto-utenti"
    assert _proxy(CLIENTE, []) == base
    assert _proxy(CLIENTE, [SU]) == f"{base}/{SU}"
    assert _proxy(CLIENTE, [SU, "invia-link"]) == f"{base}/{SU}/invia-link"
    assert _proxy("non-un-id", []) is None
    assert _proxy(CLIENTE, ["non-un-id"]) is None
    assert _proxy(CLIENTE, ["non-un-id", "invia-link"]) is None
    assert _proxy(CLIENTE, ["..", "flags"]) is None
    assert _proxy(CLIENTE, [SU, "elimina-tutto"]) is None
    assert _proxy(CLIENTE, [SU, "invia-link", "x"]) is None


def test_pagine_nell_ordine_del_menu_con_home_prima():
    out = esegui_ts(MODULO, "emit(m.pagineInOrdine(input));",
                    ["workspace", "catena", "home", "analisi_fatture", "margini"], richiede=FUNZIONI)
    assert out == ["home", "analisi_fatture", "margini", "workspace", "catena"]


def _iniziale(su, assegnabili, sedi=SEDI):
    return esegui_ts(MODULO, "emit(m.selezioneIniziale(input.su, input.a, input.sedi));",
                     {"su": su, "a": assegnabili, "sedi": sedi}, richiede=FUNZIONI)


def test_modifica_parte_solo_da_cio_che_si_puo_ancora_dare():
    # Al cliente e' stata spenta «margini»: senza casella non la si potrebbe
    # togliere, e il worker rifiuterebbe ogni salvataggio.
    su = {"pagine": ["analisi_fatture", "margini"], "sedi": ["s1"]}
    assert _iniziale(su, ["analisi_fatture", "home", "catena"]) == {"pagine": ["analisi_fatture"], "sedi": ["s1"]}
    # Sede non piu' attiva: esce dalla selezione.
    assert _iniziale({"pagine": ["home"], "sedi": ["s1", "vecchia"]}, ["home"]) == {"pagine": ["home"], "sedi": ["s1"]}
    # Catena con tutte le sedi resta; se una sede non c'e' piu' fra quelle scelte, cade.
    con = {"pagine": ["home", "catena"], "sedi": ["s1", "s2"]}
    assert _iniziale(con, ["home", "catena"]) == con
    nuova_sede = SEDI + [{"id": "s3", "nome": "BRERA"}]
    assert _iniziale(con, ["home", "catena"], nuova_sede) == {"pagine": ["home"], "sedi": ["s1", "s2"]}


def test_le_pagine_si_chiamano_come_nella_barra_laterale():
    """Il 3/10 il pannello diceva «Margini», «Prezzi», «Workspace»: Mattia non
    ritrovava le pagine della sidebar. Il confronto e' con le voci vere."""
    import re
    from pathlib import Path

    sidebar = (Path(__file__).resolve().parents[1] / "apps/web/src/components/nav/app-sidebar.tsx").read_text(encoding="utf-8")
    voci = re.findall(r'\{ title: "([^"]+)", url: "[^"]+", icon: \w+, flag: (?:"(\w+)"|null) \}', sidebar)
    assert len(voci) >= 8, voci
    etichette = esegui_ts(MODULO, "emit(m.ETICHETTA_PAGINA);")
    for titolo, flag in voci:
        chiave = flag or "home"
        assert etichette[chiave].startswith(titolo), (chiave, etichette[chiave], titolo)
