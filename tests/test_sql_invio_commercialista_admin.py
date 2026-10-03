"""La card admin «Invio al commercialista» contro il worker vero e un Postgres
vero (25/09/2026; rifatta il 03/10/2026: attiva e disattiva solo l'admin).

Si chiamano gli endpoint col TestClient, come li chiama il proxy Next.js; il DB
e' quello delle migration. Finto solo Invoicetronic. Il gate `_verify_admin` si
sostituisce (e' provato altrove): qui conta cosa fanno gli endpoint una volta
dentro, e che il DB rifiuti cio' che non va, con parole che l'admin capisce.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.sql

ROMA = ZoneInfo("Europe/Rome")
U1 = "4f0f0000-0000-4000-8000-000000000001"
U2 = "4f0f0000-0000-4000-8000-000000000002"
SEDE_1 = "4f0f0000-0000-4000-8000-0000000000a1"
SEDE_1B = "4f0f0000-0000-4000-8000-0000000000a3"
SEDE_2 = "4f0f0000-0000-4000-8000-0000000000a2"
SEDE_NO_SDI = "4f0f0000-0000-4000-8000-0000000000a4"
PIVA = "07863990961"
SENZA_SDI = "11111111115"
ALTRA = "12345678903"
AZIENDA = 1756
CHIAVE = "chiave-finta-commercialista"
EMAIL = "studio@commercialista.test"
ADMIN = "md@oneflux.it"


def _oggi():
    return datetime.now(ROMA).date()


def _cur(db_sql, sql, *params):
    with db_sql.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.fetchall() if cur.description else []


class _Invoicetronic:
    def __init__(self):
        self.aziende = {PIVA: {"id": AZIENDA, "vat": f"IT{PIVA}", "name": "OFFSIDE SRL"}}
        self.chiamate = []

    def azienda_per_piva(self, piva):
        self.chiamate.append(piva)
        return self.aziende.get(piva)


def _arrivata(db_sql, piva, giorni_fa=3, company=AZIENDA):
    _cur(db_sql, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, source, payload_meta, created_at) "
                 "VALUES (nextval('public.fatture_queue_id_seq'), %s, %s, 'invoicetronic', %s::jsonb, "
                 "now() - make_interval(days => %s))",
         f"ev-{piva}-{giorni_fa}-{company}", piva, json.dumps({"invoicetronic_company_id": company}), giorni_fa)


@pytest.fixture
def app(db_sql, monkeypatch):
    import os
    os.environ.setdefault("WORKER_DEV_MODE", "1")
    import services.fastapi_worker as fw
    from fastapi.testclient import TestClient
    from services.routers import admin
    from services.routers import invio_commercialista as rotte
    from tests.helpers_supabase_sql import ClientSQL

    sb = ClientSQL(db_sql)
    monkeypatch.setattr(fw, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "WORKER_SECRET_KEY", CHIAVE)
    monkeypatch.setattr(fw, "WORKER_DEV_MODE", False)
    finto = _Invoicetronic()
    monkeypatch.setattr(rotte, "_client_invoicetronic", lambda: finto)
    fw.app.dependency_overrides[admin._verify_admin] = lambda: {"email": "MD@oneflux.it "}
    for uid, email in ((U1, "a1@ic.test"), (U2, "a2@ic.test")):
        _cur(db_sql, "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')", uid, email)
    for sid, uid, nome, piva, sdi in ((SEDE_1, U1, "OFFSIDE", PIVA, True), (SEDE_1B, U1, "OVERTIME", PIVA, True),
                                      (SEDE_NO_SDI, U1, "MAGAZZINO", SENZA_SDI, False),
                                      (SEDE_2, U2, "ALTRO", ALTRA, True)):
        _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, sdi_attivo) "
                     "VALUES (%s, %s, %s, %s, TRUE, %s)", sid, uid, nome, piva, sdi)
    _arrivata(db_sql, PIVA)
    client = TestClient(fw.app, raise_server_exceptions=False, headers={"X-Worker-Key": CHIAVE})
    client.finto = finto
    client.db = db_sql
    yield client
    fw.app.dependency_overrides.pop(admin._verify_admin, None)


def _base(cliente=U1):
    return f"/api/admin/clienti/{cliente}/invio-commercialista"


def _attiva(app, cliente=U1, **campi):
    return app.post(f"{_base(cliente)}/attiva", json={"piva": PIVA, "email": EMAIL, "frequenza": "settimanale", **campi})


def _config(app):
    righe = _cur(app.db, "SELECT id, attivo, email_destinatario, frequenza, data_partenza, consenso_ricevuto, "
                         "consenso_email, consenso_da, consenso_testo, consenso_at IS NOT NULL, "
                         "invoicetronic_company_id, sospesa_at FROM public.invio_commercialista_config WHERE piva = %s", PIVA)
    if not righe:
        return None
    nomi = ("id", "attivo", "email", "frequenza", "partenza", "consenso", "consenso_email", "da", "testo",
            "con_ora", "company", "sospesa_at")
    return dict(zip(nomi, righe[0]))


def _voce(risposta, piva=PIVA):
    return next(v for v in risposta["pive"] if v["piva"] == piva)


def _inviato(app, cid, dal, al, stato="inviato"):
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s", dal, cid)
    iid = str(_cur(app.db, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                           "destinatario, tipo, periodo_dal, periodo_al, richiesto_da) VALUES (%s, %s, %s, %s, %s, 'primo', %s, %s, "
                           "'notturno') RETURNING id", cid, U1, PIVA, AZIENDA, EMAIL, dal, al)[0][0])
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now() WHERE id = %s", iid)
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = %s WHERE id = %s", stato, iid)
    return iid


# ─── Chi entra ───────────────────────────────────────────────────────────────

def test_senza_admin_non_si_entra(app):
    from services.routers import admin
    import services.fastapi_worker as fw
    fw.app.dependency_overrides.pop(admin._verify_admin)
    assert app.get(_base()).status_code == 401


def test_ogni_endpoint_chiede_l_admin():
    from services.routers import admin
    from services.routers import invio_commercialista as rotte
    for rotta in rotte.router.routes:
        dipendenze = {d.call for d in rotta.dependant.dependencies}
        assert admin._verify_admin in dipendenze, rotta.path


def test_un_id_che_non_e_un_uuid_e_un_404_non_un_500(app):
    assert app.get("/api/admin/clienti/non-un-uuid/invio-commercialista").status_code == 404
    assert app.post(f"{_base()}/invii/non-un-uuid/chiarisci", json={"esito": "arrivata"}).status_code == 404


# ─── Cosa si vede ────────────────────────────────────────────────────────────

def test_una_riga_per_piva_che_riceve_via_sdi_coi_nomi_dei_locali(app):
    """OFFSIDE: due locali, una P.IVA, una riga. Il magazzino senza SDI non c'e'."""
    dati = app.get(_base()).json()
    assert [(v["piva"], v["sedi"], v["attivo"], v["arrivate"]) for v in dati["pive"]] == [
        (PIVA, ["OFFSIDE", "OVERTIME"], False, True)]
    assert dati["frequenze"]["settimanale"] == "ogni lunedì"


def test_i_locali_chiusi_non_portano_la_loro_piva(app):
    _cur(app.db, "UPDATE public.ristoranti SET attivo = false WHERE partita_iva = %s", PIVA)
    assert app.get(_base()).json()["pive"] == []
    assert _attiva(app).status_code == 400 and _config(app) is None


def test_senza_fatture_arrivate_la_riga_lo_dice(app):
    _cur(app.db, "DELETE FROM public.fatture_queue WHERE piva_raw = %s", PIVA)
    assert _voce(app.get(_base()).json())["arrivate"] is False


def test_l_interruttore_si_vede(app, monkeypatch):
    monkeypatch.delenv("INVIO_COMMERCIALISTA_ATTIVO", raising=False)
    assert app.get(_base()).json()["interruttore"] is False
    monkeypatch.setenv("INVIO_COMMERCIALISTA_ATTIVO", "1")
    assert app.get(_base()).json()["interruttore"] is True


# ─── Attivare ────────────────────────────────────────────────────────────────

def test_attivare_collega_registra_chi_e_accende(app):
    from services import invio_commercialista_service as svc
    r = _attiva(app, email="  Studio@Commercialista.TEST ")
    assert r.status_code == 200, r.text
    c = _config(app)
    assert (c["attivo"], c["email"], c["frequenza"], c["consenso"], c["consenso_email"], c["company"]) == (
        True, EMAIL, "settimanale", True, EMAIL, AZIENDA)
    assert c["partenza"] == _oggi(), "si parte dalle fatture arrivate da oggi"
    assert c["da"] == ADMIN and c["con_ora"]
    assert c["testo"] == svc.testo_attivazione(ADMIN, EMAIL, "settimanale", PIVA)
    voce = _voce(r.json())
    assert voce["attivo"] is True and voce["attivato_da"] == ADMIN and voce["prossimo_invio"] is not None
    assert app.finto.chiamate == [PIVA]


@pytest.mark.parametrize("email", ["senza-chiocciola", "a@b", "due@@x.it", ""])
def test_email_non_valida(app, email):
    r = _attiva(app, email=email)
    assert r.status_code == 400 and _config(app) is None


@pytest.mark.parametrize("piva", [SENZA_SDI, ALTRA, "0786399096"])
def test_solo_le_piva_del_cliente_che_ricevono_via_sdi(app, piva):
    r = _attiva(app, piva=piva)
    assert r.status_code == 400 and "SDI" in r.json()["detail"]
    assert _cur(app.db, "SELECT count(*) FROM public.invio_commercialista_config")[0][0] == 0
    assert app.finto.chiamate == []


def test_una_piva_che_non_e_su_invoicetronic(app):
    app.finto.aziende.clear()
    r = _attiva(app)
    assert r.status_code == 400 and "prima fattura" in r.json()["detail"] and _config(app) is None


def test_un_azienda_diversa_da_quella_delle_fatture_arrivate_non_si_collega(app):
    _arrivata(app.db, PIVA, giorni_fa=5, company=999)
    r = _attiva(app)
    assert r.status_code == 409 and "999" in r.json()["detail"] and _config(app) is None


def test_invoicetronic_in_errore(app):
    from services.invoicetronic_client import ErroreInvoicetronic

    def rotto(piva):
        raise ErroreInvoicetronic("HTTP 401", status=401, configurazione=True)
    app.finto.azienda_per_piva = rotto
    r = _attiva(app)
    assert r.status_code == 503 and "HTTP 401" in r.json()["detail"]


def test_cambiare_email_da_attivo_resta_attivo_e_la_partenza_non_cambia(app):
    assert _attiva(app).status_code == 200
    c = _config(app)
    prima = _oggi() - timedelta(days=10)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s", prima, c["id"])
    assert _attiva(app, email="nuovo@studio.test", frequenza="mensile").status_code == 200
    c = _config(app)
    assert (c["attivo"], c["email"], c["frequenza"], c["consenso_email"]) == (True, "nuovo@studio.test", "mensile",
                                                                              "nuovo@studio.test")
    assert c["partenza"] == prima and "nuovo@studio.test" in c["testo"]


def test_disattivare_e_riattivare_riparte_da_oggi(app):
    assert _attiva(app).status_code == 200
    cid = _config(app)["id"]
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s",
         _oggi() - timedelta(days=60), cid)
    r = app.post(f"{_base()}/disattiva", json={"piva": PIVA})
    assert r.status_code == 200 and _voce(r.json())["attivo"] is False and _config(app)["attivo"] is False
    assert _attiva(app).status_code == 200
    assert _config(app)["partenza"] == _oggi(), "il buco di quando era spento non si manda"


def test_riattivare_toglie_la_sospensione_della_guardia(app):
    assert _attiva(app).status_code == 200
    _cur(app.db, "UPDATE public.invio_commercialista_config SET sospesa_at = now(), sospesa_motivo = 'x'")
    assert app.post(f"{_base()}/disattiva", json={"piva": PIVA}).status_code == 200
    assert _attiva(app).status_code == 200
    c = _config(app)
    assert c["attivo"] is True and c["sospesa_at"] is None


def test_riattivare_con_la_piva_ora_anche_altrui_e_rifiutato_dal_db(app):
    assert _attiva(app).status_code == 200
    _cur(app.db, "UPDATE public.invio_commercialista_config SET sospesa_at = now(), sospesa_motivo = 'x'")
    _cur(app.db, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                 "VALUES ('4f0f0000-0000-4000-8000-0000000000a5', %s, 'COPIA', %s, TRUE)", U2, PIVA)
    assert app.post(f"{_base()}/disattiva", json={"piva": PIVA}).status_code == 200
    r = _attiva(app)
    assert r.status_code == 400 and "altro account" in r.json()["detail"]
    assert _config(app)["attivo"] is False


def test_una_piva_che_non_riceve_piu_via_sdi_si_vede_e_si_spegne(app):
    assert _attiva(app).status_code == 200
    _cur(app.db, "UPDATE public.ristoranti SET sdi_attivo = false WHERE partita_iva = %s", PIVA)
    voce = _voce(app.get(_base()).json())
    assert (voce["attivo"], voce["sdi_attivo"], voce["prossimo_invio"]) == (True, False, None)
    assert app.post(f"{_base()}/disattiva", json={"piva": PIVA}).status_code == 200


def test_disattivare_una_piva_mai_attivata(app):
    assert app.post(f"{_base()}/disattiva", json={"piva": PIVA}).status_code == 404


def test_la_configurazione_di_un_altro_cliente_non_si_tocca(app):
    assert _attiva(app).status_code == 200
    assert app.post(f"{_base(U2)}/disattiva", json={"piva": PIVA}).status_code == 404
    assert _config(app)["attivo"] is True


# ─── Chiarire un esito incerto ───────────────────────────────────────────────

def test_l_esito_incerto_si_vede_e_arrivato_consuma_il_periodo(app):
    assert _attiva(app).status_code == 200
    cid = _config(app)["id"]
    iid = _inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10), stato="esito_incerto")
    assert _voce(app.get(_base()).json())["da_chiarire"]["id"] == iid
    r = app.post(f"{_base()}/invii/{iid}/chiarisci", json={"esito": "arrivata"})
    assert r.status_code == 200 and _voce(r.json())["da_chiarire"] is None
    assert _voce(r.json())["ultimo_invio"]["periodo_al"] == (_oggi() - timedelta(days=10)).isoformat()


def test_esito_incerto_non_arrivato_libera_il_periodo(app):
    assert _attiva(app).status_code == 200
    cid = _config(app)["id"]
    iid = _inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10), stato="esito_incerto")
    r = app.post(f"{_base()}/invii/{iid}/chiarisci", json={"esito": "non_arrivata"})
    assert r.status_code == 200 and _voce(r.json())["ultimo_invio"] is None
    assert _cur(app.db, "SELECT stato FROM public.invio_commercialista_invii WHERE id = %s", iid)[0][0] == "errore"


def test_si_chiarisce_solo_un_esito_incerto(app):
    assert _attiva(app).status_code == 200
    inviato = _inviato(app, _config(app)["id"], _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    assert app.post(f"{_base()}/invii/{inviato}/chiarisci", json={"esito": "non_arrivata"}).status_code == 409


def test_l_esito_incerto_di_un_altro_cliente_non_si_chiarisce(app):
    assert _attiva(app).status_code == 200
    incerto = _inviato(app, _config(app)["id"], _oggi() - timedelta(days=40), _oggi() - timedelta(days=10),
                       stato="esito_incerto")
    assert app.post(f"{_base(U2)}/invii/{incerto}/chiarisci", json={"esito": "arrivata"}).status_code == 409
    assert _cur(app.db, "SELECT stato FROM public.invio_commercialista_invii WHERE id = %s", incerto)[0][0] == "esito_incerto"


# ─── Cancellazione dell'account ed export ────────────────────────────────────

class _ArchivioFinto:
    rimossi = []

    def __init__(self, sb):
        pass

    def rimuovi(self, percorsi):
        _ArchivioFinto.rimossi += list(percorsi)


def _con_zip(app, monkeypatch):
    from services import invio_commercialista_service as svc
    _ArchivioFinto.rimossi = []
    monkeypatch.setattr(svc, "ArchivioSupabase", _ArchivioFinto)
    assert _attiva(app).status_code == 200
    iid = _inviato(app, _config(app)["id"], _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET storage_paths = ARRAY['c/fatture.zip'], "
                 "link_scade_il = now() + interval '20 days' WHERE id = %s", iid)


def test_l_admin_che_cancella_il_cliente_toglie_subito_gli_zip(app, monkeypatch):
    _con_zip(app, monkeypatch)
    r = app.delete(f"/api/admin/clienti/{U1}")
    assert r.status_code == 200, r.text
    assert _ArchivioFinto.rimossi == ["c/fatture.zip"]
    assert _cur(app.db, "SELECT count(*) FROM public.users WHERE id = %s", U1)[0][0] == 0
    assert _cur(app.db, "SELECT count(*) FROM public.invio_commercialista_invii")[0][0] == 0


def test_il_cliente_che_si_cancella_toglie_subito_gli_zip(app, monkeypatch):
    from services.routers import account
    _con_zip(app, monkeypatch)
    monkeypatch.setattr(account, "_resolve_user_from_token", lambda authorization: {"id": U1, "email": "a1@ic.test"})
    r = app.post("/api/account/elimina", json={"conferma": "ELIMINA"})
    assert r.status_code == 200, r.text
    assert _ArchivioFinto.rimossi == ["c/fatture.zip"]
    assert _cur(app.db, "SELECT count(*) FROM public.users WHERE id = %s", U1)[0][0] == 0


def test_l_export_dei_dati_del_cliente_contiene_l_invio_al_commercialista(app, monkeypatch):
    """Art. 15 e 20: l'email del commercialista e il registro sono dati del cliente."""
    from services.routers import account
    assert _attiva(app).status_code == 200
    _inviato(app, _config(app)["id"], _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    monkeypatch.setattr(account, "_resolve_user_from_token", lambda authorization: {"id": U1, "email": "a1@ic.test"})
    dati = app.get("/api/account/esporta-dati").json()
    assert [c["email_destinatario"] for c in dati["invio_commercialista_configurazioni"]] == [EMAIL]
    assert len(dati["invio_commercialista_invii"]) == 1
