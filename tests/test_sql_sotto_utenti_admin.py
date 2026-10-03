"""Sotto-utenti dal pannello Admin (Fase 2) — su Postgres vero.

Il gate `_verify_admin` si sostituisce (e' provato altrove): qui conta cosa
fanno gli endpoint una volta dentro. Finto solo Brevo. Il ciclo che conta e'
quello reale: l'admin crea, il sotto-utente riceve il link, sceglie la password
da /api/auth/reset-confirm ed entra con le sole pagine e sedi scelte.
"""
from __future__ import annotations

import re

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401
from tests.test_sql_sotto_utenti import PASSWORD, _cache_pulita, _chiama, _crea_sotto_utente, _login  # noqa: F401

pytestmark = pytest.mark.sql

EMAIL = "sala@isolamento.test"


@pytest.fixture
def admin(scenario, monkeypatch):
    import services.fastapi_worker as fw
    from services import email_service
    from services.routers import admin as admin_router

    inviate = []

    def finto_brevo(to_email, to_name, subject, html_body, **kw):
        inviate.append({"to": to_email, "subject": subject, "html": html_body, **kw})
        return True

    monkeypatch.setattr(email_service, "brevo_send", finto_brevo)
    fw.app.dependency_overrides[admin_router._verify_admin] = lambda: {"email": "md@oneflux.it"}
    scenario.inviate = inviate
    yield scenario
    fw.app.dependency_overrides.pop(admin_router._verify_admin, None)


def _base(sc, cliente=None):
    return f"/api/admin/clienti/{cliente or sc.a.ids['user_id']}/sotto-utenti"


def _adm(sc, metodo, path, **kw):
    return sc.client.request(metodo, path, headers={"X-Worker-Key": CHIAVE_WORKER}, **kw)


def _crea(sc, **kw):
    body = {"email": EMAIL, "nome": "Sala", "pagine": ["analisi_fatture"], "sedi": [sc.a.ids["sede1"]]}
    body.update(kw)
    return _adm(sc, "POST", _base(sc), json=body)


def _token_dall_email(sc):
    m = re.search(r"token=([A-Za-z0-9_\-]+)", sc.inviate[-1]["html"])
    assert m, sc.inviate[-1]["html"]
    return m.group(1)


def _attiva(sc, token, password=PASSWORD):
    return sc.client.post(
        "/api/auth/reset-confirm",
        json={"token": token, "password": password, "privacy_accepted": True},
        headers={"X-Worker-Key": CHIAVE_WORKER},
    )


def _riga(sc, email=EMAIL):
    return sc.conn.execute(
        "SELECT attivo, password_hash, reset_code, privacy_accepted_at FROM public.sotto_utenti WHERE email = %s",
        (email,),
    ).fetchone()


# ─── Il ciclo completo ────────────────────────────────────────────────────────


def test_crea_attiva_ed_entra_solo_sulla_sua_pagina_e_sede(admin):
    sc = admin
    r = _crea(sc)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["email_inviata"] is True and corpo["link_attivazione"] is None
    su = corpo["sotto_utente"]
    assert su["stato"] == "in_attesa"
    assert su["pagine"] == ["analisi_fatture"] and su["sedi"] == [sc.a.ids["sede1"]]
    assert "password_hash" not in su and "reset_code" not in su

    # In attesa: nessuna password indovinabile, nemmeno quella che sceglierà.
    assert _login(sc, EMAIL).status_code == 401
    assert len(sc.inviate) == 1 and sc.inviate[0]["to"] == EMAIL
    assert "onboarding=1" in sc.inviate[0]["html"]

    token = _token_dall_email(sc)
    assert _attiva(sc, token).status_code == 200
    attivo, hash_, reset_code, privacy = _riga(sc)
    assert attivo and hash_.startswith("$argon2") and reset_code is None and privacy is not None
    # Il token vale una volta sola.
    assert _attiva(sc, token, "Un-Altra-Password-2027!").status_code == 400

    login = _login(sc, EMAIL)
    assert login.status_code == 200, login.text
    utente = login.json()["user"]
    assert utente["sotto_utente"] is True and utente["id"] == sc.a.ids["user_id"]
    assert utente["pagine_abilitate"] == ["analisi_fatture"] and utente["num_sedi"] == 1
    tok = login.json()["token"]
    assert _chiama(sc, tok, "GET", "/api/fatture/mesi-disponibili").status_code == 200
    assert _chiama(sc, tok, "GET", "/api/margini").status_code == 403

    elenco = _adm(sc, "GET", _base(sc)).json()
    assert [s["stato"] for s in elenco["sotto_utenti"]] == ["attivo"]
    assert {s["id"] for s in elenco["sedi"]} == {sc.a.ids["sede1"], sc.a.ids["sede2"]}


def test_il_link_non_cambia_la_password_del_titolare(admin):
    sc = admin
    prima = sc.conn.execute("SELECT password_hash FROM public.users WHERE id = %s", (sc.a.ids["user_id"],)).fetchone()
    _crea(sc)
    assert _attiva(sc, _token_dall_email(sc)).status_code == 200
    dopo = sc.conn.execute("SELECT password_hash FROM public.users WHERE id = %s", (sc.a.ids["user_id"],)).fetchone()
    assert prima == dopo


def test_link_scaduto_rifiutato(admin):
    sc = admin
    _crea(sc)
    token = _token_dall_email(sc)
    sc.conn.execute("UPDATE public.sotto_utenti SET reset_expires = now() - interval '1 minute' WHERE email = %s", (EMAIL,))
    r = _attiva(sc, token)
    assert r.status_code == 400 and "scaduto" in r.json()["detail"].lower()
    assert not _riga(sc)[1].startswith("$argon2")


def test_password_debole_rifiutata_all_attivazione(admin):
    sc = admin
    _crea(sc)
    r = _attiva(sc, _token_dall_email(sc), "ristorante")
    assert r.status_code == 400
    assert not _riga(sc)[1].startswith("$argon2")


def test_disattivato_non_si_attiva_dal_link(admin):
    sc = admin
    su_id = _crea(sc).json()["sotto_utente"]["id"]
    token = _token_dall_email(sc)
    assert _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"attivo": False}).status_code == 200
    assert _attiva(sc, token).status_code == 400
    assert not _riga(sc)[1].startswith("$argon2")


# ─── Le regole all'ingresso ───────────────────────────────────────────────────


def test_catena_solo_con_tutte_le_sedi(admin):
    sc = admin
    r = _crea(sc, pagine=["home", "catena"])
    assert r.status_code == 400 and "Catena" in r.json()["detail"]
    assert _riga(sc) is None
    ok = _crea(sc, pagine=["home", "catena"], sedi=[sc.a.ids["sede1"], sc.a.ids["sede2"]])
    assert ok.status_code == 200, ok.text
    su_id = ok.json()["sotto_utente"]["id"]
    # Togliere una sede a chi ha la Catena: rifiutato, non spento in silenzio.
    r = _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"sedi": [sc.a.ids["sede1"]]})
    assert r.status_code == 400
    assert sorted(_adm(sc, "GET", _base(sc)).json()["sotto_utenti"][0]["sedi"]) == sorted([sc.a.ids["sede1"], sc.a.ids["sede2"]])


def test_sede_di_un_altro_cliente_rifiutata(admin):
    sc = admin
    r = _crea(sc, sedi=[sc.b.ids["sede1"]])
    assert r.status_code == 400 and "sede non trovata" in r.json()["detail"]
    assert _riga(sc) is None


def test_pagina_che_il_titolare_non_ha_rifiutata(admin):
    sc = admin
    sc.conn.execute("UPDATE public.users SET pagine_abilitate = %s WHERE id = %s",
                    ('{"analisi_fatture": true}', sc.a.ids["user_id"]))
    r = _crea(sc, pagine=["margini"])
    assert r.status_code == 400 and "titolare non ha: margini" in r.json()["detail"]
    pagine = _adm(sc, "GET", _base(sc)).json()["pagine_assegnabili"]
    assert "margini" not in pagine and {"analisi_fatture", "home", "catena"} <= set(pagine)


@pytest.mark.parametrize("email", ["a@isolamento.test", "md@oneflux.it"])
def test_email_gia_di_un_account_o_admin_rifiutata(admin, email):
    sc = admin
    # La prima e' l'email del titolare A (seed); la seconda e' admin.
    reale = sc.conn.execute("SELECT email FROM public.users WHERE id = %s", (sc.a.ids["user_id"],)).fetchone()[0]
    r = _crea(sc, email=reale if email.startswith("a@") else email)
    assert r.status_code in (403, 409), r.text
    assert sc.conn.execute("SELECT count(*) FROM public.sotto_utenti").fetchone()[0] == 0


def test_email_gia_di_un_sotto_utente_rifiutata(admin):
    sc = admin
    assert _crea(sc).status_code == 200
    r = _adm(sc, "POST", _base(sc, sc.b.ids["user_id"]),
             json={"email": EMAIL.upper(), "pagine": ["home"], "sedi": [sc.b.ids["sede1"]]})
    assert r.status_code == 409
    assert "sotto-utente" in r.json()["detail"]


def test_sotto_utente_di_un_altro_cliente_non_si_tocca(admin):
    sc = admin
    su_id = _crea(sc).json()["sotto_utente"]["id"]
    altro = _base(sc, sc.b.ids["user_id"])
    assert _adm(sc, "PATCH", f"{altro}/{su_id}", json={"attivo": False}).status_code == 404
    assert _adm(sc, "DELETE", f"{altro}/{su_id}").status_code == 404
    assert _adm(sc, "POST", f"{altro}/{su_id}/invia-link").status_code == 404
    assert _adm(sc, "GET", altro).json()["sotto_utenti"] == []
    assert _riga(sc)[0] is True


def test_id_malformati_sono_404(admin):
    sc = admin
    assert _adm(sc, "GET", "/api/admin/clienti/non-un-id/sotto-utenti").status_code == 404
    assert _adm(sc, "PATCH", f"{_base(sc)}/non-un-id", json={"attivo": False}).status_code == 404


# ─── Modifica, disattivazione, eliminazione, nuovo link ───────────────────────


def test_modifica_pagine_e_sedi_arriva_alla_sessione(admin):
    sc = admin
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    tok = _login(sc, EMAIL).json()["token"]
    assert _chiama(sc, tok, "GET", "/api/margini").status_code == 403
    r = _adm(sc, "PATCH", f"{_base(sc)}/{su_id}",
             json={"pagine": ["margini"], "sedi": [sc.a.ids["sede2"]], "nome": "Cucina"})
    assert r.status_code == 200, r.text
    assert r.json()["sotto_utente"]["pagine"] == ["margini"]
    assert r.json()["sotto_utente"]["sedi"] == [sc.a.ids["sede2"]]
    assert r.json()["sotto_utente"]["nome"] == "Cucina"
    from services.auth_service import _clear_sessione_cache
    _clear_sessione_cache()
    assert _chiama(sc, tok, "GET", "/api/margini").status_code == 200
    assert _chiama(sc, tok, "GET", "/api/fatture/mesi-disponibili").status_code == 403
    assert _chiama(sc, tok, "GET", "/api/auth/me").json()["sede_attiva_id"] == sc.a.ids["sede2"]


def test_modifica_solo_le_pagine_tiene_le_sedi(admin):
    sc = admin
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede2"]], {"analisi_fatture": True})
    r = _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"pagine": ["prezzi"]})
    assert r.status_code == 200 and r.json()["sotto_utente"]["sedi"] == [sc.a.ids["sede2"]]


def test_disattiva_butta_fuori_e_riattiva(admin):
    sc = admin
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    tok = _login(sc, EMAIL).json()["token"]
    r = _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"attivo": False})
    assert r.status_code == 200 and r.json()["sessioni_chiuse"] == 1
    assert r.json()["sotto_utente"]["stato"] == "disattivato"
    from services.auth_service import _clear_sessione_cache
    _clear_sessione_cache()
    assert _chiama(sc, tok, "GET", "/api/auth/me").status_code == 401
    assert _login(sc, EMAIL).status_code == 401
    assert _adm(sc, "POST", f"{_base(sc)}/{su_id}/invia-link").status_code == 400
    assert _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"attivo": True}).status_code == 200
    assert _login(sc, EMAIL).status_code == 200


def test_elimina_lo_toglie_con_sessioni_e_sedi(admin):
    sc = admin
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    tok = _login(sc, EMAIL).json()["token"]
    assert _adm(sc, "DELETE", f"{_base(sc)}/{su_id}").status_code == 200
    for tabella, colonna in (("sotto_utenti", "id"), ("sotto_utenti_sedi", "sotto_utente_id"), ("sessioni", "sotto_utente_id")):
        n = sc.conn.execute(f"SELECT count(*) FROM public.{tabella} WHERE {colonna} = %s", (su_id,)).fetchone()[0]
        assert n == 0, tabella
    from services.auth_service import _clear_sessione_cache
    _clear_sessione_cache()
    assert _chiama(sc, tok, "GET", "/api/auth/me").status_code == 401
    # Il titolare non se ne accorge.
    assert _chiama(sc, sc.a.token, "GET", "/api/auth/me").status_code == 200


def test_nuovo_link_a_chi_e_gia_attivo_cambia_password_e_chiude_le_sessioni(admin):
    sc = admin
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    tok = _login(sc, EMAIL).json()["token"]
    r = _adm(sc, "POST", f"{_base(sc)}/{su_id}/invia-link")
    assert r.status_code == 200 and r.json()["email_inviata"] is True
    assert "onboarding=1" not in sc.inviate[-1]["html"]
    # Finche' non usa il link, la password vecchia vale ancora.
    assert _login(sc, EMAIL).status_code == 200
    assert _attiva(sc, _token_dall_email(sc), "Turno-Pranzo-Nuovo-2027!").status_code == 200
    from services.auth_service import _clear_sessione_cache
    _clear_sessione_cache()
    assert _chiama(sc, tok, "GET", "/api/auth/me").status_code == 401
    assert _login(sc, EMAIL).status_code == 401
    assert _login(sc, EMAIL, "Turno-Pranzo-Nuovo-2027!").status_code == 200


def test_email_non_partita_restituisce_il_link(admin, monkeypatch):
    sc = admin
    from services import email_service
    monkeypatch.setattr(email_service, "brevo_send", lambda *a, **k: False)
    r = _crea(sc)
    assert r.status_code == 200
    assert r.json()["email_inviata"] is False
    assert "reset-password?token=" in r.json()["link_attivazione"]


def test_se_le_sedi_non_si_scrivono_non_resta_niente(admin, monkeypatch):
    sc = admin
    vera = sc.sb.table

    def tabella(nome):
        t = vera(nome)
        if nome == "sotto_utenti_sedi":
            def rotta(*a, **k):
                raise RuntimeError("scrittura sedi fallita")
            t.insert = rotta
        return t

    monkeypatch.setattr(sc.sb, "table", tabella)
    assert _crea(sc).status_code == 500
    assert _riga(sc) is None


def test_senza_admin_niente(scenario):
    sc = scenario
    # Gate vero: la sessione del titolare non e' admin.
    r = _chiama(sc, sc.a.token, "GET", _base(sc))
    assert r.status_code == 403
    r = sc.client.post(_base(sc), json={"email": EMAIL, "pagine": ["home"], "sedi": [sc.a.ids["sede1"]]},
                       headers={"Authorization": f"Bearer {sc.a.token}", "X-Worker-Key": CHIAVE_WORKER})
    assert r.status_code == 403
    assert sc.conn.execute("SELECT count(*) FROM public.sotto_utenti").fetchone()[0] == 0


def test_pagina_spenta_al_cliente_non_blocca_la_modifica(admin):
    sc = admin
    su_id = _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]],
                               {"analisi_fatture": True, "margini": True})
    sc.conn.execute("UPDATE public.users SET pagine_abilitate = %s WHERE id = %s",
                    ('{"analisi_fatture": true}', sc.a.ids["user_id"]))
    # Solo il nome: niente rivalidazione di pagine che non tocca.
    r = _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"nome": "Cucina"})
    assert r.status_code == 200, r.text
    # Con la selezione che la scheda manda (senza la pagina spenta): salva.
    r = _adm(sc, "PATCH", f"{_base(sc)}/{su_id}", json={"pagine": ["analisi_fatture"], "sedi": [sc.a.ids["sede1"]]})
    assert r.status_code == 200 and r.json()["sotto_utente"]["pagine"] == ["analisi_fatture"]


def test_link_sostituito_mentre_si_attiva_non_dichiara_successo(admin, monkeypatch):
    sc = admin
    _crea(sc)
    token = _token_dall_email(sc)
    vera = sc.sb.table

    def tabella(nome):
        t = vera(nome)
        if nome == "sotto_utenti":
            originale = t.update

            def update(dati):
                # L'admin rigenera il link fra la lettura e la scrittura.
                if "password_hash" in dati:
                    sc.conn.execute("UPDATE public.sotto_utenti SET reset_code = 'nuovo' WHERE email = %s", (EMAIL,))
                return originale(dati)
            t.update = update
        return t

    monkeypatch.setattr(sc.sb, "table", tabella)
    r = _attiva(sc, token)
    assert r.status_code == 400
    assert not _riga(sc)[1].startswith("$argon2")


# ─── «Password dimenticata» dal login ─────────────────────────────────────────


def _password_dimenticata(sc, email=EMAIL):
    return sc.client.post("/api/auth/reset-request", json={"email": email},
                          headers={"X-Worker-Key": CHIAVE_WORKER})


def test_password_dimenticata_vale_anche_per_il_sotto_utente(admin):
    sc = admin
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    r = _password_dimenticata(sc)
    assert r.status_code == 200, r.text
    generico = r.json()["message"]
    assert len(sc.inviate) == 1 and sc.inviate[0]["to"] == EMAIL
    assert "onboarding=1" not in sc.inviate[0]["html"]
    assert _attiva(sc, _token_dall_email(sc), "Turno-Pranzo-Nuovo-2027!").status_code == 200
    assert _login(sc, EMAIL, "Turno-Pranzo-Nuovo-2027!").status_code == 200
    # La risposta e' la stessa di un'email sconosciuta: non rivela chi esiste.
    assert _password_dimenticata(sc, "nessuno@isolamento.test").json()["message"] == generico


def test_password_dimenticata_non_rimanda_entro_cinque_minuti(admin):
    sc = admin
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    assert _password_dimenticata(sc).status_code == 200
    import services.fastapi_worker as fw
    fw._rate_buckets.clear()
    assert _password_dimenticata(sc).status_code == 200
    assert len(sc.inviate) == 1


def test_password_dimenticata_non_attiva_chi_e_in_attesa_o_disattivato(admin):
    sc = admin
    _crea(sc)  # in attesa: ha gia' il link di attivazione dell'admin
    assert len(sc.inviate) == 1
    # Link dell'admin scaduto: a fermarlo dev'essere lo stato, non i 5 minuti.
    sc.conn.execute("UPDATE public.sotto_utenti SET reset_expires = now() - interval '1 day' WHERE email = %s", (EMAIL,))
    assert _password_dimenticata(sc).status_code == 200
    assert len(sc.inviate) == 1
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], "spento@isolamento.test", [sc.a.ids["sede1"]],
                       {"analisi_fatture": True}, attivo=False)
    assert _password_dimenticata(sc, "spento@isolamento.test").status_code == 200
    assert len(sc.inviate) == 1


def test_password_dimenticata_se_l_email_non_parte_si_puo_riprovare_subito(admin, monkeypatch):
    sc = admin
    from services import email_service
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], EMAIL, [sc.a.ids["sede1"]], {"analisi_fatture": True})
    monkeypatch.setattr(email_service, "brevo_send", lambda *a, **k: False)
    assert _password_dimenticata(sc).status_code == 200
    assert _riga(sc)[2] is None
    inviate = []
    monkeypatch.setattr(email_service, "brevo_send", lambda to, *a, **k: inviate.append(to) or True)
    import services.fastapi_worker as fw
    fw._rate_buckets.clear()
    assert _password_dimenticata(sc).status_code == 200
    assert inviate == [EMAIL]
