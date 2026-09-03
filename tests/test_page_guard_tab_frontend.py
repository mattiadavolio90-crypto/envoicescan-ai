"""La guardia sulle tab, provata sul comportamento e non sul sorgente.

`page-guard.ts` importa `next/navigation` (notFound/redirect) e non e' eseguibile
da node fuori da Next. Quello che si puo' — e si deve — presidiare qui e' la
DECISIONE che il guard prende, che vive tutta in `risolviTab`/`tabAttive`: il
guard e' l'involucro che traduce quella decisione in redirect o 404.

Il presidio serve perche' la scelta "redirect, non 404" e' una decisione di
prodotto dell'owner: un link salvato a una tab poi spenta deve portare il cliente
su una tab che puo' vedere, non su un errore. Un mutante che risponda 404 al posto
del redirect e' invisibile ai tipi e a `tsc`.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/tab-flags"
_RICHIEDE = ["risolviTab", "tabAttive", "primaTabAttiva"]


def _decisione(pagine, sezione, richiesta):
    """Riproduce i tre esiti del guard con le funzioni vere che lo governano."""
    return esegui_ts(
        MODULO,
        """
        const [pagine, sezione, richiesta] = input;
        const risolta = m.risolviTab(pagine, sezione, richiesta);
        if (risolta == null) emit({ esito: "404" });
        else if (risolta === richiesta) emit({ esito: "rende", tab: risolta });
        else emit({ esito: "redirect", tab: risolta });
        """,
        [pagine, sezione, richiesta],
        richiede=_RICHIEDE,
    )


def test_tab_consentita_viene_resa_senza_redirect():
    assert _decisione([], "margini", "coperti") == {"esito": "rende", "tab": "coperti"}


def test_link_a_tab_spenta_redirige_non_404():
    """La decisione dell'owner: chi ha un vecchio link non deve prendere un errore."""
    esito = _decisione(["tab_off_margini_coperti"], "margini", "coperti")
    assert esito == {"esito": "redirect", "tab": "calcolo"}


def test_url_inventato_redirige_al_default():
    assert _decisione([], "prezzi", "pippo") == {"esito": "redirect", "tab": "variazioni"}


def test_sezione_senza_tab_attive_da_404():
    """Ultimo esito: header e filtri sopra un corpo vuoto sembrerebbero un guasto."""
    spente = ["tab_off_workspace_foodcost", "tab_off_workspace_inventario"]
    assert _decisione(spente, "workspace", "foodcost") == {"esito": "404"}


def test_la_pagina_di_arrivo_non_redirige_di_nuovo():
    """Il guard redirige solo se risolta !== richiesta: se la destinazione a sua
    volta redirigesse, il cliente resterebbe in un ciclo infinito."""
    pagine = ["tab_off_agenda_tutto", "tab_off_agenda_appuntamenti"]
    primo = _decisione(pagine, "agenda", "tutto")
    assert primo["esito"] == "redirect"
    secondo = _decisione(pagine, "agenda", primo["tab"])
    assert secondo == {"esito": "rende", "tab": primo["tab"]}


def test_la_voce_di_menu_sparisce_quando_sparisce_l_ultima_tab():
    """Complemento del 404: senza questo filtro resterebbe in sidebar un link
    verso una pagina che risponde 404."""
    esito = esegui_ts(
        MODULO,
        """
        const spente = ["tab_off_workspace_foodcost", "tab_off_workspace_inventario"];
        emit({
          workspace: m.sezioneHaTabAttive(spente, "workspace"),
          margini: m.sezioneHaTabAttive(spente, "margini"),
          senza_tab: m.sezioneHaTabAttive(spente, "analisi_e_tag"),
        });
        """,
        richiede=["sezioneHaTabAttive"],
    )
    assert esito == {"workspace": False, "margini": True, "senza_tab": True}
