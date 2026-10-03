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
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "uno@isolamento.test", sedi, {"analisi_fatture": True})
    # Sede attiva esplicita: le due sedi del seed hanno lo stesso created_at, e la
    # sede di default a pari data dipendeva da cosa era girato prima su quel DB.
    sc.conn.execute("UPDATE public.sotto_utenti SET ultimo_ristorante_id = %s WHERE id = %s",
                    (sc.a.ids["sede1"], su_id))
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


# ─── Fase 1c: sedi ───────────────────────────────────────────────────────────
#
# Lo scenario semina tutto sulla sede 1 di A. Un sotto-utente con TUTTE le pagine
# (tranne la Catena) ma solo sulla sede 2 percorre ogni GET dell'app: nessuna
# risposta deve contenere un dato della sede 1. E' il test che trova gli
# endpoint filtrati solo per account (user_id) e non per sede.

# Marcatori dell'account, non di una sede: il sotto-utente li vede di diritto.
_MARCATORI_DELL_ACCOUNT = {"RISTORANTE", "GRUPPO", "RAGIONE", "SEDE2"}


def _marcatori_sede1(sc):
    import re

    righe = sc.conn.execute(
        "SELECT to_jsonb(t)::text FROM public.fatture t WHERE user_id = %s", (sc.a.ids["user_id"],)
    ).fetchall()
    testo = " ".join(r[0] for r in righe)
    tutti = set(re.findall(r"(\w+?)_A_SEGRETO", testo))
    # Anche quelli seminati altrove (tag, personale, workspace, notifiche...).
    tutti |= {"SEDE1", "TAG", "SUGGERIMENTO", "DIPENDENTE", "DIPENDENTE2", "NOTA_TURNO", "NOTA_MENSILE",
              "SPESA", "RICETTA", "NOTA_RICETTA", "INGREDIENTE", "VOCE", "EVENTO", "DESCRIZIONE_EVENTO",
              "NOTIFICA", "CORPO_NOTIFICA", "NOTA_REGOLA", "NUMDOC", "PRODOTTO", "FORNITORE"}
    return {f"{m}_A_SEGRETO" for m in tutti - _MARCATORI_DELL_ACCOUNT}


def test_sotto_utente_di_una_sede_non_vede_i_dati_dell_altra(scenario, worker):
    from services import permessi_rotte as pr
    from tests.test_isolamento_per_risorsa import GET_SESSIONE, _risolvi

    sc = scenario
    pagine = {p: True for p in su.PAGINE_SOTTO_UTENTE if p != su.PAGINA_CATENA}
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "sede2@isolamento.test", [sc.a.ids["sede2"]], pagine)
    token = _login(sc, "sede2@isolamento.test").json()["token"]
    marcatori = _marcatori_sede1(sc)
    # Controllo: il titolare, sulla sede 1, li vede davvero (altrimenti il test non misura).
    visti_dal_titolare = set()
    trapelati = []
    for path, params in sorted(GET_SESSIONE.items()):
        if path.startswith(("/api/gruppo/", "/api/riparto/")) or path == "/api/fatture/da-assegnare":
            continue  # Catena: gia' negata dalla mappa (1b)
        if ("GET", path) in pr.ROTTE_VIETATE:
            continue
        p = _risolvi(params, sc.a, sc.a)
        mio = _chiama(sc, token, "GET", path, params=p)
        assert mio.status_code != 403, (path, mio.text[:200])
        trovati = sorted(m for m in marcatori if m in mio.text)
        if trovati or sc.a.ids["sede1"] in mio.text:
            trapelati.append((path, mio.status_code, trovati[:4]))
        visti_dal_titolare |= {m for m in marcatori if m in _chiama(sc, sc.a.token, "GET", path, params=p).text}
    assert not trapelati, "\n".join(map(str, trapelati))
    assert len(visti_dal_titolare) >= 10, sorted(visti_dal_titolare)


def _xml_per(piva):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
        "<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese>"
        f"<IdCodice>{piva}</IdCodice></IdFiscaleIVA></DatiAnagrafici></CessionarioCommittente></FatturaElettronicaHeader>"
        "<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento>"
        "<Data>2026-09-20</Data><Numero>77</Numero></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody>"
        "</p:FatturaElettronica>"
    ).encode()


def _carica(sc, token, nome, piva):
    return sc.client.post(
        "/api/upload/invoice", files={"file": (nome, _xml_per(piva), "application/xml")},
        headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER},
    )


def test_upload_smistato_su_una_sede_non_sua_e_rifiutato(scenario):
    sc = scenario
    piva_sede1 = sc.conn.execute("SELECT partita_iva FROM public.ristoranti WHERE id = %s",
                                 (sc.a.ids["sede1"],)).fetchone()[0]
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "sede2@isolamento.test",
                       [sc.a.ids["sede2"]], {"analisi_fatture": True})
    token = _login(sc, "sede2@isolamento.test").json()["token"]
    # FATT_A.xml esiste gia' sulla sede 1: col titolare lo smistamento ci arriva e
    # si ferma al controllo dei doppioni (nessuna AI, nessuna scrittura).
    titolare = _carica(sc, sc.a.token, sc.a.ids["file"], piva_sede1).json()
    assert (titolare.get("error") or "").startswith("ALREADY_LOADED"), titolare
    r = _carica(sc, token, sc.a.ids["file"], piva_sede1)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is False and r.json()["routing_status"] == "sede_non_consentita", r.json()


def test_sede_esplicita_non_assegnata_rifiutata_su_cestino_e_scadenziario(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "scad@isolamento.test",
                       [sc.a.ids["sede2"]], {"scadenziario": True})
    token = _login(sc, "scad@isolamento.test").json()["token"]
    for path, corpo in [
        ("/api/scadenziario/pagata", {"file_origini": [sc.a.ids["file"]]}),
        ("/api/scadenziario/scadenza", {"file_origine": sc.a.ids["file"], "scadenza_override": "2026-05-01"}),
        ("/api/cestino/ripristina", {"file_origine": sc.a.ids["file_cancellato"]}),
        ("/api/fatture/oscura", {"file_origine": sc.a.ids["file"], "oscurata": True}),
    ]:
        altrui = _chiama(sc, token, "POST", path, json={**corpo, "ristorante_id": sc.a.ids["sede1"]})
        assert altrui.status_code == 403, (path, altrui.text)
        # Controllo: la stessa chiamata sulla sua sede non e' rifiutata per la sede.
        mia = _chiama(sc, token, "POST", path, json={**corpo, "ristorante_id": sc.a.ids["sede2"]})
        assert mia.status_code != 403, (path, mia.text)


def test_sposta_sede_solo_fra_le_sue_sedi(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "scad@isolamento.test",
                       [sc.a.ids["sede2"]], {"scadenziario": True})
    token = _login(sc, "scad@isolamento.test").json()["token"]
    # Fattura divisa fra la sede 1 (non sua) e la sede 2 (sua): basta una riga
    # altrui per rifiutare, o lo spostamento si porterebbe dietro anche quella.
    sc.conn.execute(
        "UPDATE public.fatture SET ristorante_id = %s WHERE ctid = (SELECT ctid FROM public.fatture "
        "WHERE file_origine = %s AND deleted_at IS NULL LIMIT 1)", (sc.a.ids["sede2"], sc.a.ids["file"]))
    r = _chiama(sc, token, "POST", "/api/fatture/sposta-sede",
                json={"file_origine": sc.a.ids["file"], "ristorante_id": sc.a.ids["sede2"]})
    assert r.status_code == 404, r.text
    divisa = sc.conn.execute("SELECT DISTINCT ristorante_id::text FROM public.fatture "
                             "WHERE file_origine = %s AND deleted_at IS NULL ORDER BY 1", (sc.a.ids["file"],)).fetchall()
    assert sorted(divisa) == sorted([(sc.a.ids["sede1"],), (sc.a.ids["sede2"],)]), divisa
    sc.conn.execute("UPDATE public.fatture SET ristorante_id = %s WHERE file_origine = %s",
                    (sc.a.ids["sede1"], sc.a.ids["file"]))
    # La fattura sta sulla sede 1: non la puo' portare sulla sua.
    r = _chiama(sc, token, "POST", "/api/fatture/sposta-sede",
                json={"file_origine": sc.a.ids["file"], "ristorante_id": sc.a.ids["sede2"]})
    assert r.status_code == 404, r.text
    sede = sc.conn.execute("SELECT DISTINCT ristorante_id::text FROM public.fatture WHERE file_origine = %s",
                           (sc.a.ids["file"],)).fetchall()
    assert sede == [(sc.a.ids["sede1"],)]
    # Controllo: una fattura della sua sede si sposta, ma non verso una sede non sua.
    sc.conn.execute("UPDATE public.fatture SET ristorante_id = %s WHERE file_origine = %s",
                    (sc.a.ids["sede2"], sc.a.ids["file"]))
    r = _chiama(sc, token, "POST", "/api/fatture/sposta-sede",
                json={"file_origine": sc.a.ids["file"], "ristorante_id": sc.a.ids["sede1"]})
    assert r.status_code == 403, r.text
    # E il titolare la sposta come sempre.
    r = _chiama(sc, sc.a.token, "POST", "/api/fatture/sposta-sede",
                json={"file_origine": sc.a.ids["file"], "ristorante_id": sc.a.ids["sede1"]})
    assert r.status_code == 200, r.text


def _notifica(sc, sede, action_page, titolo):
    return str(sc.conn.execute(
        "INSERT INTO public.notification_inbox (user_id, ristorante_id, topic_key, source_type, severity, "
        "title, body, dedupe_key, action_page) VALUES (%s, %s, 'prova', 'operativa', 'info', %s, '', %s, %s) RETURNING id",
        (sc.a.ids["user_id"], sede, titolo, f"dk-{titolo}", action_page),
    ).fetchone()[0])


def test_notifiche_solo_delle_sue_pagine_senza_home(scenario):
    sc = scenario
    s1 = sc.a.ids["sede1"]
    _notifica(sc, s1, "/margini", "AVVISO_MARGINI")
    _notifica(sc, s1, "/analisi-fatture?tab=articoli", "AVVISO_FATTURE")
    _notifica(sc, s1, None, "AVVISO_SENZA_PAGINA")
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "f@isolamento.test", [s1], {"analisi_fatture": True})
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "h@isolamento.test", [s1], {"home": True})
    senza_home = _chiama(sc, _login(sc, "f@isolamento.test").json()["token"], "GET", "/api/notifiche").text
    con_home = _chiama(sc, _login(sc, "h@isolamento.test").json()["token"], "GET", "/api/notifiche").text
    assert "AVVISO_FATTURE" in senza_home
    assert "AVVISO_MARGINI" not in senza_home and "AVVISO_SENZA_PAGINA" not in senza_home
    assert all(t in con_home for t in ("AVVISO_MARGINI", "AVVISO_FATTURE", "AVVISO_SENZA_PAGINA"))


def test_notifiche_di_catena_solo_delle_sue_pagine_senza_home(scenario):
    # La Home di catena legge le stesse righe della campanella: stesso filtro.
    sc = scenario
    _notifica(sc, sc.a.ids["sede1"], "/margini", "AVVISO_MARGINI")
    _notifica(sc, sc.a.ids["sede2"], "/analisi-fatture", "AVVISO_FATTURE")
    tutte = [sc.a.ids["sede1"], sc.a.ids["sede2"]]
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "c@isolamento.test", tutte,
                       {"catena": True, "analisi_fatture": True})
    token = _login(sc, "c@isolamento.test").json()["token"]
    r = _chiama(sc, token, "GET", "/api/gruppo/notifiche")
    assert r.status_code == 200, r.text
    assert "AVVISO_FATTURE" in r.text and "AVVISO_MARGINI" not in r.text
    titolare = _chiama(sc, sc.a.token, "GET", "/api/gruppo/notifiche").text
    assert "AVVISO_FATTURE" in titolare and "AVVISO_MARGINI" in titolare


def test_archiviare_una_notifica_di_un_altra_sede_non_ha_effetto(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "h@isolamento.test", [sc.a.ids["sede2"]], {"home": True})
    token = _login(sc, "h@isolamento.test").json()["token"]
    altrui = sc.a.ids["notifica_id"]  # sulla sede 1
    mia = _notifica(sc, sc.a.ids["sede2"], None, "AVVISO_SEDE2")
    for nid in (altrui, mia):
        assert _chiama(sc, token, "POST", f"/api/notifiche/{nid}/dismiss").status_code == 200
    archiviate = {r[0] for r in sc.conn.execute(
        "SELECT id::text FROM public.notification_inbox WHERE dismissed_at IS NOT NULL AND user_id = %s",
        (sc.a.ids["user_id"],)).fetchall()}
    assert str(altrui) not in archiviate
    assert mia in archiviate


def test_agenda_scrive_sulla_sede_del_sotto_utente(scenario):
    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "ag@isolamento.test", [sc.a.ids["sede2"]], {"agenda": True})
    token = _login(sc, "ag@isolamento.test").json()["token"]
    r = _chiama(sc, token, "POST", "/api/workspace/diario",
                json={"data_evento": "2026-03-20", "titolo": "EVENTO_DEL_RESPONSABILE"})
    assert r.status_code == 200, r.text
    sede = sc.conn.execute("SELECT ristorante_id::text FROM public.diario_eventi WHERE titolo = %s",
                           ("EVENTO_DEL_RESPONSABILE",)).fetchone()[0]
    assert sede == sc.a.ids["sede2"]
    assert _sede_attiva_titolare(sc) == sc.a.ids["sede1"]


def _impronta_sede(sc, sede):
    import json

    tabelle = [r[0] for r in sc.conn.execute(
        "SELECT DISTINCT table_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND column_name = 'ristorante_id' AND table_name IN (SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE') ORDER BY 1"
    ).fetchall()]
    out = {}
    for t in tabelle:
        righe = sc.conn.execute(
            f'SELECT to_jsonb(x) FROM public."{t}" x WHERE x.ristorante_id::text = %s', (sede,)
        ).fetchall()
        out[t] = sorted(json.dumps(r[0], sort_keys=True, default=str) for r in righe)
    return out


def test_sotto_utente_non_raggiunge_le_risorse_di_un_altra_sede(scenario, worker):
    """Le ricette dell'isolamento, con gli id della sede 1, eseguite da un
    sotto-utente della sede 2: nessuna riga della sede 1 cambia, nessun suo dato
    torna indietro. E' l'isolamento fra clienti portato dentro lo stesso account."""
    from services import permessi_rotte as pr
    from tests.test_isolamento_per_risorsa import RICETTE, _contiene_id, _risolvi, _valori_inviati

    sc = scenario
    pagine = {p: True for p in su.PAGINE_SOTTO_UTENTE if p != su.PAGINA_CATENA}
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "sede2@isolamento.test", [sc.a.ids["sede2"]], pagine)
    token = _login(sc, "sede2@isolamento.test").json()["token"]
    marcatori = _marcatori_sede1(sc)
    rotte = _richieste(sc, worker)
    forma = {(m, __import__("re").sub(r"\{\w+\}", "{}", p)): (m, p) for m, p in rotte}
    problemi, non_raggiunte, eseguite = [], [], 0
    ids_sede1 = set(sc.a.id_noti()) - {sc.a.ids["user_id"], sc.a.ids["sede2"]}
    for r in RICETTE:
        generico = __import__("re").sub(r"\{(?:mio|altro)\.", "{", r.path)
        chiave = forma.get((r.metodo, __import__("re").sub(r"\{\w+\}", "{}", generico)))
        if chiave is None or not pr.rotta_consentita(
            {"_sotto_utente": {"id": "x"}, "pagine_abilitate": {**pagine, "catena": False}}, chiave
        ):
            continue  # rotte di Catena o vietate: le ferma gia' la mappa
        richiesta = {"path": _risolvi(r.path, sc.a, sc.a), "params": _risolvi(r.params, sc.a, sc.a),
                     "json": _risolvi(r.json_, sc.a, sc.a)}
        prima = _impronta_sede(sc, sc.a.ids["sede1"])
        prima2 = _impronta_sede(sc, sc.a.ids["sede2"])
        resp = _chiama(sc, token, r.metodo, richiesta["path"], params=richiesta["params"], json=richiesta["json"])
        dopo = _impronta_sede(sc, sc.a.ids["sede1"])
        nuove = {x for t in _impronta_sede(sc, sc.a.ids["sede2"]).values() for x in t} - {
            x for t in prima2.values() for x in t}
        puntano = [i for i in ids_sede1 if any(_contiene_id(x, i) for x in nuove)]
        if puntano:
            problemi.append(f"{r.etichetta} -> {resp.status_code} righe della sede 2 che puntano alla sede 1: {puntano}")
        corpo = resp.text or ""
        for inviato in sorted(_valori_inviati(richiesta), key=len, reverse=True):
            corpo = corpo.replace(inviato, "")
        cambiate = [t for t in dopo if dopo[t] != prima.get(t)]
        trovati = sorted(m for m in marcatori if m.lower() in corpo.lower())
        if cambiate or trovati or resp.status_code >= 500:
            problemi.append(f"{r.etichetta} -> {resp.status_code} cambiate={cambiate} dati={trovati[:3]}")
        # Controllo: la stessa ricetta dal titolare (sede 1) raggiunge la risorsa.
        # Nel savepoint: le ricette dopo trovano le risorse intatte.
        sc.conn.execute("SAVEPOINT controllo_titolare")
        try:
            suo = _chiama(sc, sc.a.token, r.metodo, richiesta["path"], params=richiesta["params"],
                          json=richiesta["json"])
            suo_corpo = suo.text or ""
            for inviato in sorted(_valori_inviati(richiesta), key=len, reverse=True):
                suo_corpo = suo_corpo.replace(inviato, "")
            raggiunta = (_impronta_sede(sc, sc.a.ids["sede1"]) != prima
                         or any(m.lower() in suo_corpo.lower() for m in marcatori))
            if not raggiunta:
                non_raggiunte.append(f"{r.etichetta} -> {suo.status_code}")
        finally:
            sc.conn.execute("ROLLBACK TO SAVEPOINT controllo_titolare")
            _clear_sessione_cache()
        eseguite += 1
    assert not problemi, "\n".join(problemi)
    # Le ricette che neanche il titolare fa arrivare alla risorsa non provano niente.
    assert eseguite >= 40 and len(non_raggiunte) <= eseguite // 4, (eseguite, non_raggiunte)


def test_cancellare_l_inventario_di_una_data_resta_sulla_sua_sede(scenario):
    sc = scenario
    for sede in (sc.a.ids["sede1"], sc.a.ids["sede2"]):
        sc.conn.execute(
            "INSERT INTO public.inventario_voci (user_id, ristorante_id, data_inventario, nome, quantita, "
            "prezzo_unitario) VALUES (%s, %s, '2026-04-30', 'VOCE_APRILE', 1, 1)",
            (sc.a.ids["user_id"], sede),
        )
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "w@isolamento.test", [sc.a.ids["sede2"]], {"workspace": True})
    token = _login(sc, "w@isolamento.test").json()["token"]
    r = _chiama(sc, token, "DELETE", "/api/workspace/inventario", params={"data": "2026-04-30"})
    assert r.status_code == 200 and r.json()["n_eliminate"] == 1, r.text
    restano = sc.conn.execute(
        "SELECT ristorante_id::text FROM public.inventario_voci WHERE data_inventario = '2026-04-30'"
    ).fetchall()
    assert restano == [(sc.a.ids["sede1"],)]


def test_il_titolare_cancella_l_inventario_di_una_data_solo_sulla_sede_attiva(scenario):
    # Lista e storico sono per sede: la cancellazione valeva su tutte le sedi.
    sc = scenario
    for sede in (sc.a.ids["sede1"], sc.a.ids["sede2"]):
        sc.conn.execute(
            "INSERT INTO public.inventario_voci (user_id, ristorante_id, data_inventario, nome, quantita, "
            "prezzo_unitario) VALUES (%s, %s, '2026-04-30', 'VOCE_APRILE', 1, 1)",
            (sc.a.ids["user_id"], sede),
        )
    sc.conn.execute("UPDATE public.users SET ultimo_ristorante_id = %s WHERE id = %s",
                    (sc.a.ids["sede2"], sc.a.ids["user_id"]))
    r = _chiama(sc, sc.a.token, "DELETE", "/api/workspace/inventario", params={"data": "2026-04-30"})
    assert r.status_code == 200 and r.json()["n_eliminate"] == 1, r.text
    restano = sc.conn.execute(
        "SELECT ristorante_id::text FROM public.inventario_voci WHERE data_inventario = '2026-04-30'"
    ).fetchall()
    assert restano == [(sc.a.ids["sede1"],)]


# ─── Fase 1d: l'area Account scrive sulla riga della PERSONA ────────────────

NUOVA_PASSWORD = "Altra-Password-Sede-2027!"


def _riga_titolare(sc, colonne):
    return sc.conn.execute(f"SELECT {colonne} FROM public.users WHERE id = %s", (sc.a.ids["user_id"],)).fetchone()


def test_cambia_password_del_sotto_utente_non_tocca_il_titolare(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "pw@isolamento.test", [sc.a.ids["sede1"]], {"margini": True})
    corrente = _login(sc, "pw@isolamento.test").json()["token"]
    altro_dispositivo = _login(sc, "pw@isolamento.test").json()["token"]
    prima = _riga_titolare(sc, "password_hash, password_changed_at")

    sbagliata = _chiama(sc, corrente, "POST", "/api/account/cambia-password",
                        json={"password_attuale": "non-e-questa", "nuova_password": NUOVA_PASSWORD})
    assert sbagliata.status_code == 400, sbagliata.text
    r = _chiama(sc, corrente, "POST", "/api/account/cambia-password",
                json={"password_attuale": PASSWORD, "nuova_password": NUOVA_PASSWORD})
    assert r.status_code == 200, r.text

    assert _riga_titolare(sc, "password_hash, password_changed_at") == prima
    assert sc.conn.execute("SELECT password_changed_at IS NOT NULL FROM public.sotto_utenti WHERE id = %s",
                           (su_id,)).fetchone()[0]
    assert _login(sc, "pw@isolamento.test").status_code == 401
    assert _login(sc, "pw@isolamento.test", NUOVA_PASSWORD).status_code == 200
    # Fuori gli altri dispositivi del sotto-utente, non lui ne' il titolare.
    assert _chiama(sc, corrente, "GET", "/api/auth/me").status_code == 200
    assert _chiama(sc, altro_dispositivo, "GET", "/api/auth/me").status_code == 401
    assert _chiama(sc, sc.a.token, "GET", "/api/auth/me").status_code == 200


def test_preferenze_del_sotto_utente_sulla_sua_riga(scenario):
    sc = scenario
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "pref@isolamento.test", [sc.a.ids["sede1"]], {"margini": True})
    token = _login(sc, "pref@isolamento.test").json()["token"]
    prima = _riga_titolare(sc, "tema, vista_fatture, email_settimanale")
    r = _chiama(sc, token, "POST", "/api/account/preferenze", json={"tema": "light", "vista_fatture": "calendario"})
    assert r.status_code == 200, r.text
    assert sc.conn.execute("SELECT tema, vista_fatture FROM public.sotto_utenti WHERE id = %s",
                           (su_id,)).fetchone() == ("light", "calendario")
    r = _chiama(sc, token, "POST", "/api/account/preferenze", json={"email_settimanale": False})
    assert r.status_code == 403, r.text
    assert _riga_titolare(sc, "tema, vista_fatture, email_settimanale") == prima


def test_consenso_privacy_del_sotto_utente_sulla_sua_riga(scenario):
    sc = scenario
    sc.conn.execute("UPDATE public.users SET privacy_accepted_at = NULL WHERE id = %s", (sc.a.ids["user_id"],))
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "priv@isolamento.test", [sc.a.ids["sede1"]], {"margini": True})
    token = _login(sc, "priv@isolamento.test").json()["token"]
    r = _chiama(sc, token, "POST", "/api/auth/accetta-privacy")
    assert r.status_code == 200, r.text
    assert sc.conn.execute("SELECT privacy_accepted_at IS NOT NULL FROM public.sotto_utenti WHERE id = %s",
                           (su_id,)).fetchone()[0]
    assert _riga_titolare(sc, "privacy_accepted_at") == (None,)


def test_account_me_del_sotto_utente_mostra_la_persona(scenario):
    sc = scenario
    sc.conn.execute("UPDATE public.users SET email_settimanale_abilitata = true WHERE id = %s", (sc.a.ids["user_id"],))
    sc.conn.execute("UPDATE public.users SET tema = 'dark', email_settimanale = true, "
                    "created_at = '2020-01-01' WHERE id = %s", (sc.a.ids["user_id"],))
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "me@isolamento.test", [sc.a.ids["sede1"]], {"margini": True})
    sc.conn.execute("UPDATE public.sotto_utenti SET tema = 'light', created_at = '2026-09-01' WHERE id = %s", (su_id,))
    token = _login(sc, "me@isolamento.test").json()["token"]
    me = _chiama(sc, token, "GET", "/api/account/me").json()
    assert me["email"] == "me@isolamento.test"
    assert me["sotto_utente"] is True and me["is_admin"] is False
    assert me["email_settimanale_abilitata"] is False and me["ultimo_accesso"]
    assert me["tema"] == "light" and me["email_settimanale"] is False
    assert me["membro_dal"].startswith("2026-09-01")
    titolare = _chiama(sc, sc.a.token, "GET", "/api/account/me").json()
    assert "sotto_utente" not in titolare and titolare["email_settimanale_abilitata"] is True


def test_elenco_sedi_dice_al_sotto_utente_se_ha_la_catena(scenario):
    sc = scenario
    tutte = [sc.a.ids["sede1"], sc.a.ids["sede2"]]
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "senza@isolamento.test", tutte, {"scadenziario": True})
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "con@isolamento.test", tutte, {"scadenziario": True, "catena": True})
    senza = _chiama(sc, _login(sc, "senza@isolamento.test").json()["token"], "GET", "/api/account/sedi").json()
    con = _chiama(sc, _login(sc, "con@isolamento.test").json()["token"], "GET", "/api/account/sedi").json()
    assert len(senza["sedi"]) == 2 and senza["catena"] is False
    assert con["catena"] is True
    assert "catena" not in _chiama(sc, sc.a.token, "GET", "/api/account/sedi").json()


# ─── Fase 1e: i casi del brief che mancavano ────────────────────────────────


def test_home_su_due_sedi_strumenti_delle_sue_pagine_e_quota_del_titolare(scenario):
    """Caso del brief: Home (= AI) su 2 sedi con la sola pagina Margini. La chat
    gli offre solo gli strumenti delle sue pagine, le sue domande consumano il
    contatore unico dell'account, e vede entrambe le sue sedi."""
    import services.fastapi_worker as fw
    from services import permessi_rotte as pr

    sc = scenario
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "home2@isolamento.test",
                       [sc.a.ids["sede1"], sc.a.ids["sede2"]], {"home": True, "margini": True})
    token = _login(sc, "home2@isolamento.test").json()["token"]

    rotta = pr._ROTTA_CORRENTE.set(("POST", "/api/chat"))
    try:
        utente = fw._resolve_user_from_token(f"Bearer {token}")
    finally:
        pr._ROTTA_CORRENTE.reset(rotta)
    assert str(utente["id"]) == sc.a.ids["user_id"]
    offerti = {t["function"]["name"] for t in fw._chat_tools_sede_offerti(utente, "ristorazione")}
    assert offerti and all(fw._CHAT_TOOL_FLAG[n] == "margini" for n in offerti), offerti
    assert "query_margini" in offerti and "query_costi" not in offerti

    # Un solo contatore: una domanda registrata dal titolare la vede anche lui.
    sc.conn.execute("SELECT public.chat_usage_check_and_log(%s, %s, 100, true, NULL)",
                    (sc.a.ids["user_id"], sc.a.ids["sede1"]))
    suo = _chiama(sc, token, "GET", "/api/account/me").json()["chat_usate_oggi"]
    del_titolare = _chiama(sc, sc.a.token, "GET", "/api/account/me").json()["chat_usate_oggi"]
    assert suo == del_titolare >= 1

    # Le sue due sedi: su entrambe la Home risponde.
    for sede in (sc.a.ids["sede1"], sc.a.ids["sede2"]):
        assert _chiama(sc, token, "POST", "/api/account/cambia-sede", json={"ristorante_id": sede}).status_code == 200
        assert _chiama(sc, token, "GET", "/api/home/kpi").status_code == 200


def test_soft_delete_visto_dal_sotto_utente_come_dal_titolare(scenario, worker):
    """Una fattura nel cestino compare solo dove compare al titolare (il cestino),
    mai nelle pagine: il sotto-utente usa le stesse query, non una copia."""
    from services import permessi_rotte as pr
    from tests.test_isolamento_per_risorsa import GET_SESSIONE, _risolvi

    sc = scenario
    pagine = {p: True for p in su.PAGINE_SOTTO_UTENTE if p != su.PAGINA_CATENA}
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "cestino@isolamento.test", [sc.a.ids["sede1"]], pagine)
    token = _login(sc, "cestino@isolamento.test").json()["token"]
    assert _sede_attiva_titolare(sc) == sc.a.ids["sede1"]
    cancellato = sc.a.ids["file_cancellato"]
    dove_suo, dove_titolare = set(), set()
    for path, params in sorted(GET_SESSIONE.items()):
        if path.startswith(("/api/gruppo/", "/api/riparto/")) or ("GET", path) in pr.ROTTE_VIETATE:
            continue
        p = _risolvi(params, sc.a, sc.a)
        if cancellato in _chiama(sc, token, "GET", path, params=p).text:
            dove_suo.add(path)
        if cancellato in _chiama(sc, sc.a.token, "GET", path, params=p).text:
            dove_titolare.add(path)
    assert dove_titolare, "il file cancellato non compare nemmeno nel cestino del titolare: il test non misura"
    assert all(p.startswith("/api/cestino") for p in dove_titolare), dove_titolare
    assert dove_suo == dove_titolare
