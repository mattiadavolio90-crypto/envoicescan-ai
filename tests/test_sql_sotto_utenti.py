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
