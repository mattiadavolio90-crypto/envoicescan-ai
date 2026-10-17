"""Le guardie di pagina (`lib/guardia-pagina.ts`) con una sessione che non e' `ok`.

Audit di ottobre #21: sulla navigazione client il layout (app) non si rigira, e
le guardie con la sessione revocata o il worker giu' lasciavano passare con
pagine = null, cioe' senza restrizioni: le tab spente dall'admin tornavano
visibili. Ora `invalid` porta al login e `unavailable` non rende la pagina.
Accanto, i casi con la sessione valida: devono restare quelli di prima.
"""
import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

MODULO = "lib/guardia-pagina"
_RICHIEDE = ["guardiaPagina", "guardiaHome", "guardiaCatena", "guardiaTabMobile"]
WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

_ESITI = """
    const [s, arg] = input;
    emit([m.guardiaPagina(s, arg ?? "prezzi"), m.guardiaHome(s), m.guardiaCatena(s),
          m.guardiaTabMobile(s, arg ?? "/m/diario")]);
"""


def _tutte(sessione, arg=None):
    return esegui_ts(MODULO, _ESITI, [sessione, arg], richiede=_RICHIEDE)


def _ok(**user):
    return {"status": "ok", "user": {"pagine_abilitate": None, **user}}


def test_sessione_non_valida_porta_al_login_da_ogni_guardia():
    assert _tutte({"status": "invalid"}) == [{"esito": "redirect", "a": "/login"}] * 4


def test_worker_irraggiungibile_non_rende_la_pagina():
    assert _tutte({"status": "unavailable"}) == [{"esito": "non_disponibile"}] * 4


def test_titolare_passa_come_prima():
    passa = {"esito": "passa"}
    assert _tutte(_ok(num_sedi=1)) == [passa] * 4
    # Pagine ristrette dall'admin: requirePagina chiude, Home e Catena no.
    ristretto = _ok(pagine_abilitate=["margini"], num_sedi=1, sotto_utente=False)
    assert _tutte(ristretto) == [{"esito": "404"}, passa, passa, passa]
    assert _tutte(ristretto, "margini")[0] == passa


def test_sotto_utente_come_prima():
    su = _ok(sotto_utente=True, num_sedi=2, pagine_abilitate=["analisi_fatture"])
    pagina, home, catena, tab = _tutte(su, "analisi_fatture")
    assert pagina == {"esito": "passa"}
    assert home == {"esito": "redirect", "a": "/analisi-fatture"}
    assert catena == {"esito": "redirect", "a": "/analisi-fatture"}
    assert _tutte(su, "/m/diario")[3] == {"esito": "redirect", "a": "/m/impostazioni"}
    assert _tutte(su, "prezzi")[0] == {"esito": "404"}
    con_home = _ok(sotto_utente=True, num_sedi=2, pagine_abilitate=["home"])
    assert _tutte(con_home)[1:3] == [{"esito": "passa"}, {"esito": "redirect", "a": "/dashboard"}]
    con_catena = _ok(sotto_utente=True, num_sedi=2, pagine_abilitate=["home", "catena"])
    assert _tutte(con_catena)[2] == {"esito": "passa"}


def _senza_commenti(testo):
    testo = re.sub(r"/\*.*?\*/", "", testo, flags=re.S)
    return re.sub(r"//[^\n]*", "", testo)


def test_page_guard_applica_le_decisioni():
    guard = _senza_commenti((WEB / "lib" / "page-guard.ts").read_text(encoding="utf-8"))
    for chiamata in (
        "applica(guardiaPagina(await getCurrentSession(), flag));",
        "applica(guardiaHome(await getCurrentSession()));",
        "applica(guardiaCatena(await getCurrentSession()));",
        "applica(guardiaTabMobile(await getCurrentSession(), href));",
    ):
        assert guard.count(chiamata) == 1, chiamata
    assert 'if (e.esito === "404") notFound();' in guard
    assert 'if (e.esito === "redirect") redirect(e.a);' in guard
    assert re.search(r'if \(e\.esito === "non_disponibile"\) throw new Error\(', guard)
    # Nessuna uscita anticipata sulla sessione: era il fail-open.
    assert not re.search(r"status\s*!==\s*\"ok\"\)\s*return", guard)


def test_le_due_reti_rileggono_la_pagina_dal_server():
    # Senza error.tsx in (app) il throw della guardia darebbe la pagina d'errore
    # di Next; con `reset` il «Riprova» resterebbe sullo stesso errore.
    for percorso in ("app/(app)/error.tsx", "app/(mobile)/m/error.tsx"):
        testo = _senza_commenti((WEB / percorso).read_text(encoding="utf-8"))
        assert "onClick={() => unstable_retry()}" in testo, percorso
        assert "reset" not in testo, percorso
