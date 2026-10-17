"""Dove atterra e cosa vede un sotto-utente (`lib/sotto-utente.ts`): TS vero via node.

Il blocco vero sta sul worker (403); qui si decide solo di non mandare nessuno
su una pagina che gli risponderebbe 403. Il rischio opposto e' peggiore: che un
titolare di oggi atterri altrove o perda la Home. Per questo ogni caso del
titolare e' scritto per esteso accanto a quello del sotto-utente.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/sotto-utente"
FUNZIONI = ["haHome", "haCatena", "primaPaginaAbilitata"]


def _prima(utente, mobile=False):
    return esegui_ts(MODULO, "emit(m.primaPaginaAbilitata(input.u, input.mobile));",
                     {"u": utente, "mobile": mobile}, richiede=FUNZIONI)


def _vede(utente):
    return esegui_ts(MODULO, "emit([m.haHome(input), m.haCatena(input)]);", utente, richiede=FUNZIONI)


TITOLARE_MONO = {"pagine_abilitate": None, "num_sedi": 1}
TITOLARE_CATENA = {"pagine_abilitate": None, "num_sedi": 3}
# Titolare con le pagine ristrette dall'admin: nella lista non c'e' "home", e
# la Home non deve sparire (e' il motivo per cui home/catena non sono pagine
# dell'account).
TITOLARE_RISTRETTO = {"pagine_abilitate": ["margini"], "num_sedi": 1, "sotto_utente": False}


def test_titolari_come_prima():
    assert _prima(TITOLARE_MONO) is None
    assert _prima(TITOLARE_CATENA) == "/catena"
    assert _prima(TITOLARE_CATENA, mobile=True) is None
    assert _prima({**TITOLARE_MONO, "is_admin": True}) == "/admin"
    assert _prima(TITOLARE_RISTRETTO) is None
    assert _vede(TITOLARE_MONO) == [True, False]
    assert _vede(TITOLARE_CATENA) == [True, True]
    assert _vede(TITOLARE_RISTRETTO) == [True, False]


def _su(pagine, num_sedi=1):
    return {"pagine_abilitate": pagine, "num_sedi": num_sedi, "sotto_utente": True, "is_admin": False}


def test_sotto_utente_con_la_home_atterra_sulla_home():
    assert _prima(_su(["home", "margini"])) is None
    assert _vede(_su(["home", "margini"])) == [True, False]


def test_sotto_utente_senza_home_atterra_sulla_prima_pagina_del_menu():
    assert _prima(_su(["agenda", "margini"])) == "/margini"
    assert _prima(_su(["workspace"])) == "/workspace"
    assert _vede(_su(["margini"])) == [False, False]


def test_sotto_utente_senza_pagine_atterra_sulle_impostazioni():
    assert _prima(_su([])) == "/impostazioni"
    assert _prima(_su(None)) == "/impostazioni"


def test_catena_solo_col_flag_e_con_piu_sedi():
    assert _prima(_su(["home", "catena"], num_sedi=2)) == "/catena"
    assert _vede(_su(["home", "catena"], num_sedi=2)) == [True, True]
    # Piu' sedi ma senza Catena: il suo punto vendita, non la plancia di gruppo.
    assert _prima(_su(["home"], num_sedi=2)) is None
    assert _vede(_su(["home"], num_sedi=2)) == [True, False]
    assert _prima(_su(["margini"], num_sedi=2)) == "/margini"
    # Flag acceso ma una sola sede: la plancia di gruppo non ha senso.
    assert _vede(_su(["home", "catena"], num_sedi=1)) == [True, False]
    assert _prima(_su(["catena", "prezzi"], num_sedi=2), mobile=True) == "/prezzi"


# ─── /m: tab della bottom-nav ───────────────────────────────────────────────

FUNZIONI_M = ["vedeTabMobile", "tabMobileNascoste", "primaTabMobile"]


def _nascoste(utente):
    return esegui_ts(MODULO, "emit(m.tabMobileNascoste(input));", utente, richiede=FUNZIONI_M)


def _prima_m(utente):
    return esegui_ts(MODULO, "emit(m.primaTabMobile(input));", utente, richiede=FUNZIONI_M)


def test_titolare_vede_tutte_le_tab_mobile():
    assert _nascoste(TITOLARE_MONO) == []
    assert _nascoste(TITOLARE_RISTRETTO) == []


def test_tab_mobile_del_sotto_utente_seguono_le_sue_pagine():
    assert _nascoste(_su(["home", "agenda"])) == []
    assert _nascoste(_su(["home", "margini"])) == ["/m/diario", "/m/turni"]
    # Strumenti non apre diario, spese e personale (audit di ottobre #31).
    assert _nascoste(_su(["workspace"])) == ["/m/briefing", "/m/chat", "/m/diario", "/m/turni"]
    assert _nascoste(_su(["margini"])) == ["/m/briefing", "/m/chat", "/m/diario", "/m/turni"]


def test_prima_tab_mobile_del_sotto_utente():
    assert _prima_m(_su(["home"])) == "/m/briefing"
    assert _prima_m(_su(["agenda"])) == "/m/diario"
    assert _prima_m(_su(["prezzi"])) == "/m/impostazioni"


def test_pagina_con_tutte_le_tab_spente_non_e_un_atterraggio():
    # Margini senza nessuna tab accesa fa 404: si scende alla pagina dopo.
    spente = ["tab_off_margini_calcolo", "tab_off_margini_coperti", "tab_off_margini_analisi"]
    assert _prima(_su(["margini", "agenda", *spente])) == "/agenda"


def test_nessun_redirect_porta_alla_pagina_negata():
    """requireHome/requireCatena/requireTabMobile redirigono su queste funzioni:
    se la destinazione fosse la pagina negata, il sotto-utente resterebbe in un
    ciclo di redirect. Si provano tutte le combinazioni di Home/Catena/pagine."""
    risultati = esegui_ts(MODULO, """
        const out = [];
        const extra = [[], ["margini"], ["agenda"], ["workspace"], ["prezzi"]];
        for (const home of [false, true]) for (const catena of [false, true])
        for (const sedi of [1, 2]) for (const e of extra) {
          const u = { sotto_utente: true, num_sedi: sedi,
                      pagine_abilitate: [...(home ? ["home"] : []), ...(catena ? ["catena"] : []), ...e] };
          const dest = m.primaPaginaAbilitata(u) ?? "/dashboard";
          const destM = m.primaTabMobile(u);
          if (!m.haHome(u) && dest === "/dashboard") out.push(["home", u]);
          if (!m.haCatena(u) && dest === "/catena") out.push(["catena", u]);
          if (!m.vedeTabMobile(u, destM)) out.push(["mobile", u]);
        }
        emit(out);
    """, None, richiede=FUNZIONI + FUNZIONI_M)
    assert risultati == []


def test_la_conversazione_e_della_persona_non_dell_account():
    """Stesso dispositivo, stesso account: titolare e dipendenti non devono
    ritrovarsi la conversazione (e le card da confermare) l'uno dell'altro."""
    ids = esegui_ts(MODULO, "emit(input.map((u) => m.idPersona(u)));", [
        {"id": "u-1", "email": "titolare@x.it"},
        {"id": "u-1", "email": "titolare@x.it", "sotto_utente": False},
        {"id": "u-1", "email": "sala@x.it", "sotto_utente": True},
        {"id": "u-1", "email": "cucina@x.it", "sotto_utente": True},
    ], richiede=["idPersona"])
    # Il titolare tiene la chiave di sempre: la sua conversazione aperta resta.
    assert ids[:2] == ["u-1", "u-1"]
    assert ids[2] == "u-1:sala@x.it" and ids[3] == "u-1:cucina@x.it"


def test_configura_assistente_solo_al_titolare():
    # Il worker vieta al sotto-utente il salvataggio (ROTTE_VIETATE): il pulsante
    # gli prometteva un'impostazione che finiva in «Riprova».
    esiti = esegui_ts(MODULO, "emit(input.map((u) => m.mostraConfigAssistente(u)));", [
        {"pagine_abilitate": None},
        {"pagine_abilitate": ["margini"], "sotto_utente": False},
        {"pagine_abilitate": ["home", "catena"], "sotto_utente": True},
        None,
    ], richiede=["mostraConfigAssistente"])
    assert esiti == [True, True, False, False]


def test_configura_assistente_cablato_sulle_due_home():
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "app" / "(app)"
    home = (app / "dashboard" / "page.tsx").read_text(encoding="utf-8")
    sintesi = (app / "catena" / "sintesi-catena.tsx").read_text(encoding="utf-8")
    catena = (app / "catena" / "page.tsx").read_text(encoding="utf-8")
    assert home.count("<ConfigAssistente ") == 1
    assert "azioni={config && mostraConfigAssistente(utente) && <ConfigAssistente config={config} />}" in home
    assert sintesi.count("<ConfigAssistenteCatena />") == 1
    assert "azioni={configAssistente ? <ConfigAssistenteCatena /> : undefined}" in sintesi
    assert "configAssistente = false," in sintesi
    assert "configAssistente={mostraConfigAssistente(utente)}" in catena


# Le tab di /m e i file che le rendono: le rotte che chiamano sono quelle del worker
# (le route di Next le inoltrano con lo stesso percorso).
_FILE_TAB_MOBILE = {
    "/m/diario": ["mobile-diario.tsx", "mobile-spese.tsx", "mobile-incassi.tsx"],
    "/m/turni": ["mobile-turni.tsx"],
}


def _rotte_chiamate(nome_file):
    import re
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "app" / "(mobile)" / "m"
    testo = next(base.rglob(nome_file)).read_text(encoding="utf-8")
    percorsi = set()
    for grezzo in re.findall(r"""["'`](/api/[^"'`?]*)""", testo):
        percorsi.add(re.sub(r"\$\{[^}]*\}", "{}", grezzo).rstrip("/"))
    return percorsi


def _rotte_worker(percorso):
    import re

    from services import permessi_rotte as pr

    forma = re.compile("^" + re.escape(percorso).replace(r"\{\}", r"[^/]+") + "$")
    return {r: pagine for r, pagine in pr.PAGINE_PER_ROTTA.items()
            if forma.match(re.sub(r"\{\w+\}", "x", r[1]))}


def test_tab_mobile_visibile_solo_se_il_worker_ne_apre_le_rotte():
    combinazioni = [[], ["agenda"], ["workspace"], ["margini"], ["home"], ["workspace", "margini"],
                    ["home", "workspace"], ["agenda", "workspace"], ["home", "agenda"]]
    visibili = esegui_ts(MODULO, """
        emit(input.map((p) => Object.fromEntries(["/m/diario", "/m/turni"].map((h) =>
            [h, m.vedeTabMobile({ sotto_utente: true, num_sedi: 1, pagine_abilitate: p }, h)]))));
    """, combinazioni, richiede=FUNZIONI_M)
    contate = 0
    for pagine, vede in zip(combinazioni, visibili):
        for tab, nomi in _FILE_TAB_MOBILE.items():
            if not vede[tab]:
                continue
            for nome in nomi:
                percorsi = _rotte_chiamate(nome)
                assert percorsi, f"nessuna rotta letta in {nome}: il test non misura"
                for percorso in percorsi:
                    rotte = _rotte_worker(percorso)
                    assert rotte, f"{percorso} ({nome}) non e' in PAGINE_PER_ROTTA"
                    for rotta, ammesse in rotte.items():
                        contate += 1
                        assert set(ammesse) & set(pagine), (pagine, tab, rotta)
    assert contate > 0
