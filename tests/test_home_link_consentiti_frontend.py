"""Home: un link si mostra solo se la pagina d'arrivo si apre (audit di ottobre #24).

KPI, Completezza dati e «Da fare» portavano un sotto-utente con la Home ma senza
Margini, Analisi Fatture o Prezzi su un 404. Il dato resta (la Home intera e' una
scelta), il link no. `hrefSeConsentito` usa le stesse guardie della pagina.
"""
import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

MODULO = "lib/guardia-pagina"
WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

HREF = [
    "/margini", "/analisi-fatture?tab=articoli", "/prezzi", "/margini/qualcosa#x",
    "/dashboard", "/catena", "/impostazioni", "/notifiche", "", None,
]


def _link(utente):
    return esegui_ts(MODULO, "emit(input.h.map((h) => m.hrefSeConsentito(h, input.u)));",
                     {"h": HREF, "u": utente}, richiede=["hrefSeConsentito"])


def test_titolare_tiene_tutti_i_link():
    assert _link({"pagine_abilitate": None, "num_sedi": 1}) == HREF[:8] + [None, None]


def test_sotto_utente_con_la_sola_home_perde_i_link_alle_pagine_che_non_ha():
    assert _link({"sotto_utente": True, "num_sedi": 2, "pagine_abilitate": ["home"]}) == [
        None, None, None, None, "/dashboard", None, "/impostazioni", "/notifiche", None, None,
    ]


def test_sotto_utente_tiene_i_link_alle_sue_pagine():
    utente = {"sotto_utente": True, "num_sedi": 2, "pagine_abilitate": ["home", "catena", "margini", "prezzi"]}
    assert _link(utente) == [
        "/margini", None, "/prezzi", "/margini/qualcosa#x", "/dashboard", "/catena", "/impostazioni", "/notifiche",
        None, None,
    ]


def test_pagina_con_tutte_le_tab_spente_non_e_un_link():
    spente = ["tab_off_margini_calcolo", "tab_off_margini_coperti", "tab_off_margini_analisi"]
    utente = {"sotto_utente": True, "num_sedi": 1, "pagine_abilitate": ["home", "margini", *spente]}
    assert _link(utente)[0] is None
    assert _link({**utente, "pagine_abilitate": ["home", "margini", spente[0]]})[0] == "/margini"


def test_stessa_mappa_percorso_pagina_del_worker():
    from services import permessi_rotte as pr

    ts = esegui_ts(MODULO, "emit(m.PAGINA_DI_PERCORSO);", None, richiede=["hrefSeConsentito"])
    assert ts == dict(pr._PAGINA_DI_PERCORSO)


def test_da_fare_senza_pulsante_verso_una_pagina_che_non_ha():
    azioni = [
        {"id": "a", "severity": "warning", "testo": "Margini", "cta_label": "Apri", "cta_page": "/margini"},
        {"id": "b", "severity": "info", "testo": "Fatture", "cta_label": "Vedi", "cta_page": "/analisi-fatture"},
    ]
    voci = esegui_ts("lib/home-da-fare", """
        const nessuno = m.vociDaAzioniPV(input.a, () => false);
        const su = m.vociDaAzioniPV(input.a, () => false, input.u);
        emit([nessuno.map((v) => v.azione), su.map((v) => v.azione), su.map((v) => v.testo)]);
    """, {"a": azioni, "u": {"sotto_utente": True, "num_sedi": 1, "pagine_abilitate": ["home", "analisi_fatture"]}},
        richiede=["vociDaAzioniPV"])
    senza, con, testi = voci
    assert senza == [{"tipo": "pagina", "href": "/margini", "etichetta": "Apri"},
                     {"tipo": "pagina", "href": "/analisi-fatture", "etichetta": "Vedi"}]
    assert con == [None, {"tipo": "pagina", "href": "/analisi-fatture", "etichetta": "Vedi"}]
    assert testi == ["Margini", "Fatture"]


def _codice(percorso):
    testo = (WEB / percorso).read_text(encoding="utf-8")
    testo = re.sub(r"\{?/\*.*?\*/\}?", "", testo, flags=re.S)
    return re.sub(r"(?<![:\"'])//[^\n]*", "", testo)


def test_cablaggio_nelle_due_home():
    home = _codice("app/(app)/dashboard/page.tsx")
    assert "<KpiBlock kpi={kpi} settore={user?.tipo_attivita} utente={user} />" in home
    assert "<SaluteCard salute={salute} utente={user} />" in home
    assert "visibilita={utente && visibilitaDi(utente)}" in home
    mobile = _codice("app/(mobile)/m/briefing/page.tsx")
    assert "<KpiBlock kpi={kpi} settore={user?.tipo_attivita} utente={user} />" in mobile

    kpi = _codice("app/(app)/dashboard/kpi-block.tsx")
    # Un solo <Link>, quello di ForseLink: nessun link fisso rimasto.
    assert kpi.count("<Link") == 1
    assert not re.search(r'href="/', kpi)
    assert "const vai = (href: string) => (utente ? hrefSeConsentito(href, utente) : href);" in kpi
    assert len(re.findall(r'href=\{vai\("/(margini|analisi-fatture|prezzi)"\)', kpi)) == 7

    salute = _codice("app/(app)/dashboard/salute-card.tsx")
    assert "const href = hideLinks ? null : vai(v.cta_page);" in salute
    assert "href={href}" in salute and "v.cta_page &&" not in salute

    briefing = _codice("app/(app)/dashboard/home-briefing.tsx")
    assert "vociDaAzioniPV(visibili, puoIgnorare, visibilita)" in briefing
