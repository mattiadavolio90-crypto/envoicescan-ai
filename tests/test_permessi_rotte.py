"""Controllo pagine dei sotto-utenti lato server: la mappa e le sue regole.

Il comportamento su Postgres vero (un sotto-utente che percorre tutte le rotte)
sta in tests/test_sql_sotto_utenti.py; qui ci sono i presidi che non hanno
bisogno del DB: ogni rotta dichiarata, ogni rotta con la dipendenza che registra
la rotta, e le regole di `rotta_consentita`.
"""
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from services import permessi_rotte as pr
from services import sotto_utenti_service as su


@pytest.fixture(scope="module")
def fw():
    import services.fastapi_worker as fw

    return fw


def _rotte_app(fw):
    out = set()
    for r in fw.app.routes:
        if isinstance(r, APIRoute):
            out |= {(m, r.path) for m in r.methods if m not in ("HEAD", "OPTIONS")}
    return out


def _dichiarate():
    return set(pr.PAGINE_PER_ROTTA) | pr.ROTTE_COMUNI | pr.ROTTE_VIETATE | pr.ROTTE_SENZA_SESSIONE


def test_ogni_rotta_dell_app_e_dichiarata(fw):
    mancanti = {
        r for r in _rotte_app(fw) - _dichiarate() if not r[1].startswith(pr.PREFISSO_ADMIN)
    }
    assert not mancanti, (
        "Rotte nuove senza pagina: un sotto-utente riceve 403. Dichiarale in "
        f"services/permessi_rotte.py (PAGINE_PER_ROTTA, o gli insiemi sotto): {sorted(mancanti)}"
    )


def test_nessuna_rotta_dichiarata_e_stantia(fw):
    stantie = _dichiarate() - _rotte_app(fw)
    assert not stantie, f"Rotte dichiarate che l'app non ha piu': {sorted(stantie)}"


def test_una_rotta_sta_in_un_solo_insieme():
    insiemi = [set(pr.PAGINE_PER_ROTTA), pr.ROTTE_COMUNI, pr.ROTTE_VIETATE, pr.ROTTE_SENZA_SESSIONE]
    for i, a in enumerate(insiemi):
        for b in insiemi[i + 1:]:
            assert not (a & b), sorted(a & b)
    # Le admin si dichiarano solo se non usano la sessione (gate macchina).
    admin = {r for r in _dichiarate() if r[1].startswith(pr.PREFISSO_ADMIN)}
    assert admin <= pr.ROTTE_SENZA_SESSIONE, admin - pr.ROTTE_SENZA_SESSIONE


def test_le_pagine_della_mappa_esistono():
    usate = set().union(*pr.PAGINE_PER_ROTTA.values())
    assert usate <= su.PAGINE_SOTTO_UTENTE, usate - su.PAGINE_SOTTO_UTENTE
    assert all(pr.PAGINE_PER_ROTTA.values())


def test_ogni_rotta_registra_la_rotta(fw):
    # Senza la dipendenza globale il ContextVar resta vuoto e il sotto-utente
    # riceve 403 ovunque: il presidio vede anche un router montato a parte.
    def chiamate(dep):
        out = []
        for d in dep.dependencies:
            out.append(d.call)
            out += chiamate(d)
        return out

    senza = [
        (sorted(r.methods), r.path) for r in fw.app.routes
        if isinstance(r, APIRoute) and pr.registra_rotta not in chiamate(r.dependant)
    ]
    assert not senza, senza


# ─── rotta_consentita ────────────────────────────────────────────────────────

SEDI = [{"id": "s1", "sede_tecnica": False}, {"id": "s2", "sede_tecnica": False}]


def _sotto_utente(pagine, sedi=("s1",)):
    titolare = {"id": "u1", "email": "t@x.it", "pagine_abilitate": None, "ultimo_ristorante_id": "s1"}
    return su.sovrapponi(titolare, {"id": "su1", "email": "r@x.it", "pagine": pagine}, list(sedi), SEDI)


TITOLARE = {"id": "u1", "email": "t@x.it", "pagine_abilitate": {"margini": False}}


@pytest.mark.parametrize("rotta", [
    None, ("POST", "/api/account/elimina"), ("GET", "/api/admin/overview"), ("GET", "/rotta/che/non/esiste"),
])
def test_titolare_passa_sempre(rotta):
    assert pr.rotta_consentita(TITOLARE, rotta) is True


def test_sotto_utente_fuori_da_una_richiesta_e_rifiutato():
    assert pr.rotta_consentita(_sotto_utente({"margini": True}), None) is False


def test_rotte_comuni_anche_senza_pagine():
    u = _sotto_utente({})
    assert all(pr.rotta_consentita(u, r) for r in pr.ROTTE_COMUNI)


def test_rotta_di_pagina_solo_con_la_pagina():
    rotta = ("GET", "/api/margini")
    assert pr.rotta_consentita(_sotto_utente({"margini": True}), rotta) is True
    assert pr.rotta_consentita(_sotto_utente({"prezzi": True}), rotta) is False


def test_pagine_alternative():
    rotta = ("GET", "/api/ricavi/giornalieri")
    assert pr.rotta_consentita(_sotto_utente({"agenda": True}), rotta) is True
    assert pr.rotta_consentita(_sotto_utente({"margini": True}), rotta) is True
    assert pr.rotta_consentita(_sotto_utente({"prezzi": True}), rotta) is False


def test_catena_serve_effettiva_non_basta_il_flag():
    rotta = ("GET", "/api/gruppo/overview")
    assert pr.rotta_consentita(_sotto_utente({"catena": True}, sedi=("s1",)), rotta) is False
    assert pr.rotta_consentita(_sotto_utente({"catena": True}, sedi=("s1", "s2")), rotta) is True


TUTTE = {p: True for p in su.PAGINE_SOTTO_UTENTE}


@pytest.mark.parametrize("rotta", sorted(pr.ROTTE_VIETATE | pr.ROTTE_SENZA_SESSIONE)
                         + [("GET", "/api/admin/overview"), ("GET", "/rotta/che/non/esiste")])
def test_vietate_anche_con_tutte_le_pagine(rotta):
    assert pr.rotta_consentita(_sotto_utente(TUTTE, sedi=("s1", "s2")), rotta) is False


# ─── L'aggancio in verifica_sessione_da_cookie ───────────────────────────────


@pytest.fixture
def sessione(monkeypatch):
    from services import auth_service

    box = {}
    monkeypatch.setattr(auth_service, "_verifica_sessione_da_cookie", lambda *a, **k: box.get("user"))
    token = pr._ROTTA_CORRENTE.set(None)
    yield box
    pr._ROTTA_CORRENTE.reset(token)


def test_sotto_utente_su_rotta_non_sua_riceve_403(sessione):
    from services.auth_service import verifica_sessione_da_cookie

    sessione["user"] = _sotto_utente({"prezzi": True})
    pr._ROTTA_CORRENTE.set(("GET", "/api/margini"))
    with pytest.raises(HTTPException) as exc:
        verifica_sessione_da_cookie("tok")
    assert exc.value.status_code == 403


def test_sotto_utente_su_rotta_sua_passa(sessione):
    from services.auth_service import verifica_sessione_da_cookie

    sessione["user"] = _sotto_utente({"margini": True})
    pr._ROTTA_CORRENTE.set(("GET", "/api/margini"))
    assert verifica_sessione_da_cookie("tok")["id"] == "u1"


def test_sotto_utente_senza_rotta_registrata_riceve_403(sessione):
    from services.auth_service import verifica_sessione_da_cookie

    sessione["user"] = _sotto_utente(TUTTE, sedi=("s1", "s2"))
    with pytest.raises(HTTPException):
        verifica_sessione_da_cookie("tok")


def test_titolare_non_passa_dal_controllo(sessione):
    from services.auth_service import verifica_sessione_da_cookie

    sessione["user"] = dict(TITOLARE)
    assert verifica_sessione_da_cookie("tok") == TITOLARE
    sessione["user"] = None
    assert verifica_sessione_da_cookie("tok") is None


# ─── Catena: la ripetono i router, per le chiamate interne ───────────────────
# La rotta d'ingresso puo' non essere di catena (la chat e il briefing chiamano
# funzioni dei router): il riparto e le viste di gruppo lo ricontrollano.


def test_riparto_rifiuta_il_sotto_utente_senza_catena():
    from services.routers import riparto

    with pytest.raises(HTTPException) as exc:
        riparto._require_catena(_sotto_utente({"scadenziario": True}, sedi=("s1", "s2")), sb=None)
    assert exc.value.status_code == 403


def test_viste_di_gruppo_rifiutano_il_sotto_utente_senza_catena(monkeypatch):
    from services.routers import gruppo

    monkeypatch.setattr(gruppo, "_resolve_user_from_token",
                        lambda _a: _sotto_utente({"catena": True}, sedi=("s1",)))
    monkeypatch.setattr(gruppo, "_get_supabase_client", lambda: pytest.fail("non deve leggere il DB"))
    with pytest.raises(HTTPException) as exc:
        gruppo._resolve_gruppo("Bearer x")
    assert exc.value.status_code == 403


def test_rotte_di_gruppo_e_riparto_solo_con_la_catena():
    # Leggono o scrivono tutte le sedi: aprirne una a un'altra pagina darebbe la
    # catena a chi non ha tutte le sedi. `_resolve_gruppo` lo ripete, ma non
    # tutte le rotte di gruppo ci passano (notifiche, costi-comuni, chat-config).
    aperte = {
        r: p for r, p in pr.PAGINE_PER_ROTTA.items()
        if r[1].startswith(("/api/gruppo/", "/api/riparto/")) and p != frozenset({pr.C})
    }
    assert not aperte, aperte


# ─── Sede attiva: una sola fonte ─────────────────────────────────────────────


def test_la_sede_attiva_si_legge_dalla_sessione_non_da_users():
    # `_get_ristorante_id_for_user(user_id, sb)` rilegge users.ultimo_ristorante_id:
    # per un sotto-utente e' la sede del TITOLARE. Resta solo all'admin, che
    # lavora su un cliente scelto da lui; gli endpoint usano la sessione.
    import ast
    from pathlib import Path

    radice = Path(__file__).resolve().parents[1]
    chiamanti = []
    for f in sorted((radice / "services").rglob("*.py")):
        albero = ast.parse(f.read_text(encoding="utf-8-sig"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Call):
                nome = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
                if nome == "_get_ristorante_id_for_user":
                    chiamanti.append(f"{f.relative_to(radice)}:{nodo.lineno}")
    fuori = [c for c in chiamanti if not c.startswith("services/routers/admin.py")]
    assert chiamanti, "il rilevatore non trova nemmeno i chiamanti dell'admin"
    assert not fuori, fuori
