"""Sotto-utenti, fase 1a: modello dati, login, sessione, sede attiva — su Postgres vero.

Il worker gira in-process con TestClient e parla col DB dello snapshot (piu' la
migration 20260928215000_sotto_utenti.sql) attraverso `ClientSQL`: login,
sessione e cambio sede passano dalle stesse catene di produzione.

Semina: i due clienti del test di isolamento (A e B, 2 sedi ciascuno). I
sotto-utenti sono di A.
"""
from __future__ import annotations

import pytest
from psycopg import errors as pg_errors

from services import sotto_utenti_service as su
from services.auth_service import _clear_sessione_cache, ph
from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401

pytestmark = pytest.mark.sql

PASSWORD = "Responsabile-Sede-2027!"


@pytest.fixture(autouse=True)
def _cache_pulita():
    import services.fastapi_worker as fw

    # Il limite per IP del worker (30 richieste/min, in memoria) conta anche i
    # login di questi test, che arrivano tutti dallo stesso client finto.
    fw._rate_buckets.clear()
    _clear_sessione_cache()
    yield
    _clear_sessione_cache()
    fw._rate_buckets.clear()


def _crea_sotto_utente(conn, titolare_id, email, sedi, pagine, attivo=True):
    import json

    riga = conn.execute(
        "INSERT INTO public.sotto_utenti (titolare_id, email, password_hash, nome, attivo, pagine) "
        "VALUES (%s, %s, %s, 'Responsabile', %s, %s::jsonb) RETURNING id",
        (titolare_id, email, ph.hash(PASSWORD), attivo, json.dumps(pagine)),
    ).fetchone()
    for sede in sedi:
        conn.execute(
            "INSERT INTO public.sotto_utenti_sedi (sotto_utente_id, ristorante_id) VALUES (%s, %s)",
            (riga[0], sede),
        )
    return str(riga[0])


def _login(sc, email, password=PASSWORD):
    return sc.client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Worker-Key": CHIAVE_WORKER},
    )


def _chiama(sc, token, metodo, path, **kw):
    return sc.client.request(
        metodo, path, headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER}, **kw
    )


def _sede_attiva_titolare(sc):
    return str(sc.conn.execute(
        "SELECT ultimo_ristorante_id FROM public.users WHERE id = %s", (sc.a.ids["user_id"],)
    ).fetchone()[0])


# ─── Login e sessione ────────────────────────────────────────────────────────


def test_login_sotto_utente_resta_nel_tenant_del_titolare(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                               [sc.a.ids["sede2"]], {"analisi_fatture": True})
    r = _login(sc, "Resp1@Isolamento.test ")
    assert r.status_code == 200, r.text
    utente = r.json()["user"]
    assert utente["id"] == sc.a.ids["user_id"]
    assert utente["email"] == "resp1@isolamento.test"
    assert utente["sotto_utente"] is True
    assert utente["is_admin"] is False
    assert utente["num_sedi"] == 1
    assert utente["pagine_abilitate"] == ["analisi_fatture"]

    sessione = sc.conn.execute(
        "SELECT user_id::text, sotto_utente_id::text FROM public.sessioni WHERE token = %s",
        (r.json()["token"],),
    ).fetchone()
    assert sessione == (sc.a.ids["user_id"], su_id)

    me = _chiama(sc, r.json()["token"], "GET", "/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["sede_attiva_id"] == sc.a.ids["sede2"]
    assert me.json()["sotto_utente"] is True
    assert me.json()["pagine_abilitate"] == ["analisi_fatture"]


def test_titolare_invariato(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                       [sc.a.ids["sede2"]], {"analisi_fatture": True})
    me = _chiama(sc, sc.a.token, "GET", "/api/auth/me")
    assert me.status_code == 200, me.text
    corpo = me.json()
    assert corpo["sotto_utente"] is False
    assert corpo["pagine_abilitate"] is None
    assert corpo["num_sedi"] == 2
    assert corpo["sede_attiva_id"] == sc.a.ids["sede1"]


def test_password_sbagliata_rifiutata(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    r = _login(sc, "resp1@isolamento.test", "Sbagliata-Del-Tutto-9!")
    assert r.status_code == 401
    assert r.json()["detail"] == "Credenziali errate o account disattivato"


def test_sotto_utente_disattivato_login_rifiutato_e_sessione_morta(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                               [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "resp1@isolamento.test").json()["token"]
    assert _chiama(sc, token, "GET", "/api/auth/me").status_code == 200

    sc.conn.execute("UPDATE public.sotto_utenti SET attivo = false WHERE id = %s", (su_id,))
    # Nessuna revoca esplicita: basta che scada la cache breve dei sotto-utenti.
    _clear_sessione_cache()
    assert _chiama(sc, token, "GET", "/api/auth/me").status_code == 401
    assert _login(sc, "resp1@isolamento.test").status_code == 401


def test_la_sessione_di_un_sotto_utente_resta_in_cache_al_massimo_2_secondi(scenario):
    # La cache e' per processo: la revoca svuota solo quello che la esegue, gli
    # altri se ne accorgono alla scadenza. Si misura la scadenza scritta, non la
    # costante — e il titolare resta a 30 s (controllo positivo).
    import time

    from services import auth_service

    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "resp1@isolamento.test").json()["token"]
    assert _chiama(sc, token, "GET", "/api/auth/me").status_code == 200
    assert _chiama(sc, sc.a.token, "GET", "/api/auth/me").status_code == 200
    adesso = time.time()
    assert auth_service._SESSIONE_CACHE[token][0] - adesso <= 2.0
    assert auth_service._SESSIONE_CACHE[sc.a.token][0] - adesso > 20


def test_titolare_disattivato_chiude_anche_i_sotto_utenti(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "resp1@isolamento.test").json()["token"]
    sc.conn.execute("UPDATE public.users SET attivo = false WHERE id = %s", (sc.a.ids["user_id"],))
    _clear_sessione_cache()
    assert _chiama(sc, token, "GET", "/api/auth/me").status_code == 401
    assert _login(sc, "resp1@isolamento.test").status_code == 401


def test_sotto_utente_senza_sedi_non_entra(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test", [], {"analisi_fatture": True})
    assert _login(sc, "resp1@isolamento.test").status_code == 401


def test_sede_disattivata_esce_dalle_sedi_consentite(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                       [sc.a.ids["sede1"], sc.a.ids["sede2"]], {"analisi_fatture": True})
    token = _login(sc, "resp1@isolamento.test").json()["token"]
    sc.conn.execute("UPDATE public.ristoranti SET attivo = false WHERE id = %s", (sc.a.ids["sede1"],))
    _clear_sessione_cache()
    me = _chiama(sc, token, "GET", "/api/auth/me").json()
    assert me["num_sedi"] == 1
    assert me["sede_attiva_id"] == sc.a.ids["sede2"]


def test_admin_negato_anche_se_il_titolare_e_admin(scenario, monkeypatch):
    sc = scenario
    monkeypatch.setenv("ADMIN_EMAILS", "a@isolamento.test,resp1@isolamento.test")
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "resp1@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    r = _login(sc, "resp1@isolamento.test")
    assert r.json()["user"]["is_admin"] is False
    token = r.json()["token"]
    assert _chiama(sc, token, "GET", "/api/admin/overview").status_code == 403
    # Controllo: la stessa rotta col titolare admin passa il gate.
    assert _chiama(sc, sc.a.token, "GET", "/api/admin/overview").status_code != 403


# ─── Catena effettiva ────────────────────────────────────────────────────────


def test_catena_solo_con_tutte_le_sedi(scenario):
    sc = scenario
    pagine = {"analisi_fatture": True, "home": True, "catena": True}
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "tutte@isolamento.test",
                       [sc.a.ids["sede1"], sc.a.ids["sede2"]], pagine)
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "una@isolamento.test",
                       [sc.a.ids["sede1"]], pagine)
    tutte = _login(sc, "tutte@isolamento.test").json()["user"]
    una = _login(sc, "una@isolamento.test").json()["user"]
    assert "catena" in tutte["pagine_abilitate"] and tutte["num_sedi"] == 2
    assert "catena" not in una["pagine_abilitate"] and "home" in una["pagine_abilitate"]


def test_sede_nuova_spegne_la_catena_finche_non_e_assegnata(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "tutte@isolamento.test",
                       [sc.a.ids["sede1"], sc.a.ids["sede2"]], {"home": True, "catena": True})
    token = _login(sc, "tutte@isolamento.test").json()["token"]
    sc.conn.execute(
        "INSERT INTO public.ristoranti (user_id, nome_ristorante, partita_iva, attivo) "
        "VALUES (%s, 'Sede nuova', '11111111119', true)",
        (sc.a.ids["user_id"],),
    )
    _clear_sessione_cache()
    me = _chiama(sc, token, "GET", "/api/auth/me").json()
    assert "catena" not in me["pagine_abilitate"]


# ─── Sede attiva per persona ─────────────────────────────────────────────────


def test_due_sotto_utenti_cambiano_sede_senza_spostare_gli_altri(scenario):
    sc = scenario
    sedi = [sc.a.ids["sede1"], sc.a.ids["sede2"]]
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", sedi, {"analisi_fatture": True})
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "due@isolamento.test", sedi, {"analisi_fatture": True})
    t1 = _login(sc, "uno@isolamento.test").json()["token"]
    t2 = _login(sc, "due@isolamento.test").json()["token"]

    r = _chiama(sc, t1, "POST", "/api/account/cambia-sede", json={"ristorante_id": sc.a.ids["sede2"]})
    assert r.status_code == 200, r.text
    _clear_sessione_cache()

    assert _chiama(sc, t1, "GET", "/api/auth/me").json()["sede_attiva_id"] == sc.a.ids["sede2"]
    assert _chiama(sc, t2, "GET", "/api/auth/me").json()["sede_attiva_id"] == sc.a.ids["sede1"]
    assert _chiama(sc, sc.a.token, "GET", "/api/auth/me").json()["sede_attiva_id"] == sc.a.ids["sede1"]
    assert _sede_attiva_titolare(sc) == sc.a.ids["sede1"]


def test_titolare_che_cambia_sede_non_sposta_il_sotto_utente(scenario):
    sc = scenario
    sedi = [sc.a.ids["sede1"], sc.a.ids["sede2"]]
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", sedi, {"analisi_fatture": True})
    t1 = _login(sc, "uno@isolamento.test").json()["token"]
    r = _chiama(sc, sc.a.token, "POST", "/api/account/cambia-sede", json={"ristorante_id": sc.a.ids["sede2"]})
    assert r.status_code == 200, r.text
    _clear_sessione_cache()
    assert _chiama(sc, t1, "GET", "/api/auth/me").json()["sede_attiva_id"] == sc.a.ids["sede1"]


def test_cambia_sede_solo_verso_sedi_assegnate(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "uno@isolamento.test").json()["token"]
    stessa_azienda = _chiama(sc, token, "POST", "/api/account/cambia-sede",
                             json={"ristorante_id": sc.a.ids["sede2"]})
    altra_azienda = _chiama(sc, token, "POST", "/api/account/cambia-sede",
                            json={"ristorante_id": sc.b.ids["sede1"]})
    assert stessa_azienda.status_code == 403
    assert altra_azienda.status_code == 404
    _clear_sessione_cache()
    assert _chiama(sc, token, "GET", "/api/auth/me").json()["sede_attiva_id"] == sc.a.ids["sede1"]


def test_elenco_sedi_solo_quelle_assegnate(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test",
                       [sc.a.ids["sede2"]], {"analisi_fatture": True})
    token = _login(sc, "uno@isolamento.test").json()["token"]
    sedi = _chiama(sc, token, "GET", "/api/account/sedi").json()
    assert [s["id"] for s in sedi["sedi"]] == [sc.a.ids["sede2"]]
    assert sedi["ristorante_attivo_id"] == sc.a.ids["sede2"]
    del_titolare = _chiama(sc, sc.a.token, "GET", "/api/account/sedi").json()
    assert {s["id"] for s in del_titolare["sedi"]} == {sc.a.ids["sede1"], sc.a.ids["sede2"]}


# ─── Tetto sessioni per persona ──────────────────────────────────────────────


def test_i_login_dei_sotto_utenti_non_buttano_fuori_il_titolare(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    # La sessione del titolare e' la piu' vecchia: con un tetto contato male
    # sarebbe la prima a cadere (senza, pareggio su now() della transazione).
    sc.conn.execute(
        "UPDATE public.sessioni SET last_seen_at = now() - interval '1 hour' WHERE token = %s",
        (sc.a.token,),
    )
    for _ in range(7):
        assert _login(sc, "uno@isolamento.test").status_code == 200
    attive = sc.conn.execute(
        "SELECT count(*) FILTER (WHERE sotto_utente_id IS NULL), "
        "       count(*) FILTER (WHERE sotto_utente_id IS NOT NULL) "
        "FROM public.sessioni WHERE user_id = %s AND revoked_at IS NULL",
        (sc.a.ids["user_id"],),
    ).fetchone()
    assert attive[0] == 1  # la sessione seminata del titolare
    from config.constants import MAX_SESSIONI_ATTIVE
    assert attive[1] == MAX_SESSIONI_ATTIVE
    assert _chiama(sc, sc.a.token, "GET", "/api/auth/me").status_code == 200


def test_i_login_di_un_sotto_utente_non_buttano_fuori_un_altro(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "due@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token_due = _login(sc, "due@isolamento.test").json()["token"]
    # Nella transazione del test now() e' lo stesso per tutte le righe: senza
    # questo l'ordine per last_seen_at sarebbe un pareggio, e la sessione di
    # «due» potrebbe salvarsi per caso anche con un tetto contato male.
    sc.conn.execute(
        "UPDATE public.sessioni SET last_seen_at = now() - interval '1 hour' WHERE token = %s",
        (token_due,),
    )
    for _ in range(7):
        assert _login(sc, "uno@isolamento.test").status_code == 200
    assert _chiama(sc, token_due, "GET", "/api/auth/me").status_code == 200


def test_revoca_sessioni_sotto_utente(scenario):
    from services.session_service import revoca_sessioni_sotto_utente

    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test",
                               [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "uno@isolamento.test").json()["token"]
    assert revoca_sessioni_sotto_utente(su_id, supabase_client=sc.sb) == 1
    assert _chiama(sc, token, "GET", "/api/auth/me").status_code == 401
    assert _chiama(sc, sc.a.token, "GET", "/api/auth/me").status_code == 200


# ─── Vincoli del database ────────────────────────────────────────────────────


def _viola(conn, errore, sql, *params):
    conn.execute("SAVEPOINT prova")
    with pytest.raises(errore):
        conn.execute(sql, params)
    conn.execute("ROLLBACK TO SAVEPOINT prova")


def test_email_di_un_titolare_non_puo_essere_di_un_sotto_utente(scenario):
    sc = scenario
    _viola(sc.conn, pg_errors.UniqueViolation,
           "INSERT INTO public.sotto_utenti (titolare_id, email, password_hash) VALUES (%s, %s, 'x')",
           sc.a.ids["user_id"], "b@isolamento.test")


def test_email_di_un_sotto_utente_non_puo_diventare_di_un_titolare(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", [sc.a.ids["sede1"]], {})
    _viola(sc.conn, pg_errors.UniqueViolation,
           "UPDATE public.users SET email = 'Uno@Isolamento.test' WHERE id = %s", sc.b.ids["user_id"])
    _viola(sc.conn, pg_errors.UniqueViolation,
           "INSERT INTO public.users (email, password_hash, nome_ristorante) "
           "VALUES ('uno@isolamento.test', 'x', 'Nuovo')")


def test_email_duplicata_fra_sotto_utenti(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", [sc.a.ids["sede1"]], {})
    _viola(sc.conn, pg_errors.UniqueViolation,
           "INSERT INTO public.sotto_utenti (titolare_id, email, password_hash) VALUES (%s, %s, 'x')",
           sc.b.ids["user_id"], "uno@isolamento.test")


def test_email_non_normalizzata_rifiutata(scenario):
    sc = scenario
    _viola(sc.conn, pg_errors.CheckViolation,
           "INSERT INTO public.sotto_utenti (titolare_id, email, password_hash) VALUES (%s, %s, 'x')",
           sc.a.ids["user_id"], "Maiuscole@Isolamento.test")


def test_sede_di_un_altro_account_non_si_assegna(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", [sc.a.ids["sede1"]], {})
    _viola(sc.conn, pg_errors.CheckViolation,
           "INSERT INTO public.sotto_utenti_sedi (sotto_utente_id, ristorante_id) VALUES (%s, %s)",
           su_id, sc.b.ids["sede1"])


def test_titolare_di_un_sotto_utente_non_si_cambia(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", [sc.a.ids["sede1"]], {})
    _viola(sc.conn, pg_errors.CheckViolation,
           "UPDATE public.sotto_utenti SET titolare_id = %s WHERE id = %s", sc.b.ids["user_id"], su_id)


def test_sessione_di_sotto_utente_intestata_a_un_altro_account(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", [sc.a.ids["sede1"]], {})
    _viola(sc.conn, pg_errors.CheckViolation,
           "INSERT INTO public.sessioni (user_id, token, sotto_utente_id) VALUES (%s, 'tok-x', %s)",
           sc.b.ids["user_id"], su_id)


def test_eliminare_il_sotto_utente_cancella_le_sue_sessioni(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test",
                               [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "uno@isolamento.test").json()["token"]
    sc.conn.execute("DELETE FROM public.sotto_utenti WHERE id = %s", (su_id,))
    assert sc.conn.execute("SELECT count(*) FROM public.sessioni WHERE token = %s", (token,)).fetchone()[0] == 0


def test_tabelle_chiuse_ad_anon_e_authenticated(scenario):
    sc = scenario
    for ruolo in ("anon", "authenticated"):
        for tabella in ("sotto_utenti", "sotto_utenti_sedi"):
            assert sc.conn.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT')", (ruolo, f"public.{tabella}")
            ).fetchone()[0] is False, (ruolo, tabella)


def test_chiavi_pagina_allineate_al_worker(worker):
    assert su.PAGINE_ACCOUNT == worker._PAGINE_FLAG


# ─── Fase 1b: pagine bloccate dal server ─────────────────────────────────────
#
# Un sotto-utente percorre TUTTE le rotte dell'app con richieste valide (le
# ricette e le GET del test di isolamento, sugli id di A): senza pagine ogni
# rotta risponde 403, con tutte le pagine nessuna risponde col 403 del controllo.
# Le rotte senza ricetta partono con la richiesta minima valida letta dallo
# schema OpenAPI: un 422 vorrebbe dire che l'endpoint non e' stato eseguito, e
# non proverebbe il controllo, quindi e' un fallimento anche quello.

_RIFIUTO_PAGINA = "Pagina non consentita per questo utente"
_UUID_FINTO = "00000000-0000-4000-8000-000000000001"


# Rotte senza ricetta che rispondono 400/422 prima di guardare la sessione.
# Una tupla e' un file da caricare.
_CORPI_SENZA_RICETTA = {
    ("POST", "/api/account/elimina"): {"conferma": "ELIMINA"},
    ("POST", "/api/prezzi/soglia-alert"): {"soglia": 5},
    ("POST", "/api/ricavi/import-xls"): ("ricavi.xlsx", b"non importa", "application/octet-stream"),
    ("POST", "/api/chat"): {"messages": [{"role": "user", "content": "ciao"}]},
}


def _rotte_app(worker):
    from fastapi.routing import APIRoute

    out = set()
    for r in worker.app.routes:
        if isinstance(r, APIRoute):
            out |= {(m, r.path) for m in r.methods if m not in ("HEAD", "OPTIONS")}
    return out


def _richieste(sc, worker):
    """{(metodo, rotta): (metodo, path, params, json, valida)} per ogni rotta dell'app."""
    import re

    from tests.test_isolamento_per_risorsa import GET_SESSIONE, RICETTE, _risolvi

    rotte = _rotte_app(worker)
    forma = {(m, re.sub(r"\{\w+\}", "{}", p)): (m, p) for m, p in rotte}
    a = sc.a
    out = {}
    for r in RICETTE:
        generico = re.sub(r"\{(?:mio|altro)\.", "{", r.path)
        chiave = forma.get((r.metodo, re.sub(r"\{\w+\}", "{}", generico)))
        if chiave and chiave not in out:
            out[chiave] = (r.metodo, _risolvi(r.path, a, a), _risolvi(r.params, a, a),
                           _risolvi(r.json_, a, a), True)
    for path, params in GET_SESSIONE.items():
        if ("GET", path) in rotte:
            out.setdefault(("GET", path), ("GET", path, _risolvi(params, a, a), None, True))
    for chiave, corpo in _CORPI_SENZA_RICETTA.items():
        out[chiave] = (chiave[0], chiave[1], None, corpo, True)
    schema = worker.app.openapi()
    for metodo, path in rotte:
        if (metodo, path) in out:
            continue
        concreto = re.sub(r"\{\w+\}", _UUID_FINTO, path)
        params, corpo = _minimi_da_openapi(schema, metodo, path)
        out[(metodo, path)] = (metodo, concreto, params, corpo, False)
    return out


def _valore_minimo(sch, comp, profondita=0):
    """Il valore piu' semplice che passa lo schema: serve a superare la validazione."""
    if "$ref" in sch:
        return _valore_minimo(comp[sch["$ref"].split("/")[-1]], comp, profondita)
    for chiave in ("anyOf", "oneOf", "allOf"):
        if chiave in sch:
            varianti = [v for v in sch[chiave] if v.get("type") != "null"] or sch[chiave]
            return _valore_minimo(varianti[0], comp, profondita)
    if "enum" in sch:
        return sch["enum"][0]
    if "default" in sch and sch["default"] is not None:
        return sch["default"]
    tipo, formato = sch.get("type"), sch.get("format")
    if tipo == "object" or "properties" in sch:
        return {k: _valore_minimo(sch["properties"][k], comp, profondita + 1)
                for k in sch.get("required", []) if k in sch.get("properties", {})}
    if tipo == "array":
        n = sch.get("minItems", 0) or (1 if profondita == 0 else 0)
        return [_valore_minimo(sch.get("items", {}), comp, profondita + 1) for _ in range(n)]
    if tipo == "integer":
        return max(1, int(sch.get("minimum", 1)))
    if tipo == "number":
        return max(1, sch.get("minimum", 1))
    if tipo == "boolean":
        return False
    if formato == "date":
        return "2026-03-03"
    if formato == "date-time":
        return "2026-03-03T10:00:00"
    if formato == "uuid":
        return _UUID_FINTO
    if formato == "binary":
        return b"x"
    lunghezza = max(1, sch.get("minLength", 1))
    return "x" * lunghezza


def _minimi_da_openapi(schema, metodo, path):
    op = schema["paths"].get(path, {}).get(metodo.lower(), {})
    comp = schema.get("components", {}).get("schemas", {})
    params = {
        p["name"]: _valore_minimo(p.get("schema", {}), comp)
        for p in op.get("parameters", []) if p.get("in") == "query" and p.get("required")
    } or None
    contenuto = op.get("requestBody", {}).get("content", {})
    if "multipart/form-data" in contenuto:
        return params, ("file.xml", b"<x/>", "application/xml")
    if "application/json" in contenuto:
        return params, _valore_minimo(contenuto["application/json"]["schema"], comp)
    return params, ({} if metodo in ("POST", "PUT", "PATCH") else None)


def _esegui(sc, token, richiesta):
    metodo, path, params, corpo, _ = richiesta
    if isinstance(corpo, tuple):
        return sc.client.request(
            metodo, path, files={"file": corpo},
            headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER},
        )
    return sc.client.request(
        metodo, path, params=params, json=corpo,
        headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER},
    )


def _rifiuto_di_pagina(resp):
    try:
        return resp.status_code == 403 and resp.json().get("detail") == _RIFIUTO_PAGINA
    except ValueError:
        return False


def test_sotto_utente_senza_pagine_e_fermato_su_ogni_rotta(scenario, worker):
    from services import permessi_rotte as pr

    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "nessuna@isolamento.test", [sc.a.ids["sede1"]], {})
    token = _login(sc, "nessuna@isolamento.test").json()["token"]
    esenti = pr.ROTTE_COMUNI | pr.ROTTE_SENZA_SESSIONE
    passate = []
    for chiave, richiesta in sorted(_richieste(sc, worker).items()):
        if chiave in esenti:
            continue
        resp = _esegui(sc, token, richiesta)
        if not _rifiuto_di_pagina(resp):
            passate.append((chiave, resp.status_code, resp.text[:120]))
    assert not passate, "\n".join(f"{k} {st} {t}" for k, st, t in passate)


def test_sotto_utente_con_tutte_le_pagine_non_e_fermato_dal_controllo(scenario, worker, monkeypatch):
    from services import permessi_rotte as pr

    # /api/chat passa il controllo: senza chiave si ferma prima di OpenAI.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sc = scenario
    tutte = {p: True for p in su.PAGINE_SOTTO_UTENTE}
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "tutto@isolamento.test",
                       [sc.a.ids["sede1"], sc.a.ids["sede2"]], tutte)
    token = _login(sc, "tutto@isolamento.test").json()["token"]
    # logout e cambio password chiuderebbero la sessione a meta' giro.
    consentite = (set(pr.PAGINE_PER_ROTTA) | pr.ROTTE_COMUNI) - {
        ("POST", "/api/auth/logout"), ("POST", "/api/account/cambia-password"),
    }
    richieste = _richieste(sc, worker)
    fermate = [k for k in sorted(consentite) if _rifiuto_di_pagina(_esegui(sc, token, richieste[k]))]
    assert not fermate, fermate
    vietate = sorted(pr.ROTTE_VIETATE) + [("GET", "/api/admin/overview")]
    for chiave in vietate:
        assert _esegui(sc, token, richieste[chiave]).status_code == 403, chiave


def test_titolare_mai_fermato_dal_controllo(scenario, worker):
    from services import permessi_rotte as pr

    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "nessuna@isolamento.test", [sc.a.ids["sede1"]], {})
    richieste = _richieste(sc, worker)
    fermate = [
        k for k in sorted(set(pr.PAGINE_PER_ROTTA) | pr.ROTTE_COMUNI - {("POST", "/api/auth/logout")})
        if _rifiuto_di_pagina(_esegui(sc, sc.a.token, richieste[k]))
    ]
    assert not fermate, fermate


def test_solo_analisi_fatture_su_una_sede(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "fatture@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "fatture@isolamento.test").json()["token"]
    periodo = {"data_da": "2026-01-01", "data_a": "2026-12-31"}
    assert _chiama(sc, token, "GET", "/api/fatture/kpi", params=periodo).status_code == 200
    for metodo, path, kw in [
        ("GET", "/api/margini/kpi", {"params": periodo}),
        ("GET", "/api/prezzi/variazioni", {"params": periodo}),
        ("POST", "/api/chat", {"json": {"messages": [{"role": "user", "content": "ciao"}]}}),
        ("GET", "/api/gruppo/overview", {}),
        ("GET", "/api/home/kpi", {}),
        ("POST", "/api/account/elimina", {"json": {"conferma": "ELIMINA"}}),
        ("GET", "/api/account/esporta-dati", {}),
    ]:
        assert _chiama(sc, token, metodo, path, **kw).status_code == 403, path


def _domande_registrate(sc):
    return sc.conn.execute(
        "SELECT count(*) FROM public.chat_usage_log WHERE user_id = %s", (sc.a.ids["user_id"],)
    ).fetchone()[0]


@pytest.mark.parametrize("pagine,sedi,contesto", [
    ({"home": True, "catena": True}, ["sede1"], "catena"),          # flag senza tutte le sedi
    ({"home": True}, ["sede1", "sede2"], "catena"),                 # tutte le sedi senza flag
    ({"catena": True}, ["sede1", "sede2"], "sede"),                 # catena senza Home
])
def test_chat_rifiutata_per_contesto_prima_della_quota(scenario, monkeypatch, pagine, sedi, contesto):
    sc = scenario
    monkeypatch.setenv("OPENAI_API_KEY", "chiave-finta")
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "chat@isolamento.test",
                       [sc.a.ids[s] for s in sedi], pagine)
    token = _login(sc, "chat@isolamento.test").json()["token"]
    prima = _domande_registrate(sc)
    r = _chiama(sc, token, "POST", "/api/chat",
                json={"messages": [{"role": "user", "content": "ciao"}], "contesto": contesto})
    assert r.status_code == 403, r.text
    assert _domande_registrate(sc) == prima


def test_home_completa_uguale_al_titolare_sulla_stessa_sede(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "home@isolamento.test", [sc.a.ids["sede1"]], {"home": True})
    token = _login(sc, "home@isolamento.test").json()["token"]
    assert _sede_attiva_titolare(sc) == sc.a.ids["sede1"]
    for path in ("/api/home/kpi", "/api/home/salute", "/api/home/briefing"):
        mio = _chiama(sc, token, "GET", path)
        assert mio.status_code == 200, (path, mio.text[:200])
    assert _chiama(sc, token, "GET", "/api/home/kpi").json() == _chiama(sc, sc.a.token, "GET", "/api/home/kpi").json()


def test_riparto_solo_con_la_catena(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "scad@isolamento.test",
                       [sc.a.ids["sede1"], sc.a.ids["sede2"]], {"scadenziario": True, "analisi_fatture": True})
    token = _login(sc, "scad@isolamento.test").json()["token"]
    assert _chiama(sc, token, "POST", "/api/riparto/da-fattura",
                   json={"file_origine": sc.a.ids["file"], "descrizione": "x"}).status_code == 403
    assert _chiama(sc, token, "GET", "/api/riparto/regola-fornitore",
                   params={"fornitore": sc.a.ids["fornitore"]}).status_code == 403
    assert _chiama(sc, token, "GET", "/api/scadenziario").status_code == 200


def test_modificare_il_dict_di_sessione_non_allarga_le_richieste_dopo(scenario):
    from services import permessi_rotte as pr
    from services.auth_service import verifica_sessione_da_cookie

    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "cache@isolamento.test",
                       [sc.a.ids["sede1"]], {"analisi_fatture": True})
    token = _login(sc, "cache@isolamento.test").json()["token"]
    _clear_sessione_cache()
    segno = pr._ROTTA_CORRENTE.set(("GET", "/api/auth/me"))
    try:
        for _ in range(2):  # prima dalla lettura (e scrittura in cache), poi dalla cache
            u = verifica_sessione_da_cookie(token)
            assert u["pagine_abilitate"]["margini"] is False
            assert su.sedi_consentite(u) == {sc.a.ids["sede1"]}
            u["pagine_abilitate"]["margini"] = True
            u["_sotto_utente"]["sedi"].append(sc.a.ids["sede2"])
        u = verifica_sessione_da_cookie(token)
        assert u["pagine_abilitate"]["margini"] is False
        assert su.sedi_consentite(u) == {sc.a.ids["sede1"]}
    finally:
        pr._ROTTA_CORRENTE.reset(segno)
