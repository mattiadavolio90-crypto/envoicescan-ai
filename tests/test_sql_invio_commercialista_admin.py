"""La scheda admin «Invio al commercialista» contro il worker vero e un Postgres
vero (fase D).

Si chiamano gli endpoint col TestClient, come li chiama il proxy Next.js; il DB
e' quello della migration. Finto solo Invoicetronic. Il gate `_verify_admin` si
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
SEDE_2 = "4f0f0000-0000-4000-8000-0000000000a2"
PIVA = "07863990961"
ALTRA = "12345678903"
AZIENDA = 1756
CHIAVE = "chiave-finta-commercialista"
EMAIL = "studio@commercialista.test"


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
    fw.app.dependency_overrides[admin._verify_admin] = lambda: {"email": "md@oneflux.it"}
    for uid, email in ((U1, "a1@ic.test"), (U2, "a2@ic.test")):
        _cur(db_sql, "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')", uid, email)
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, sdi_attivo) "
                 "VALUES (%s, %s, 'OFFSIDE', %s, TRUE, TRUE)", SEDE_1, U1, PIVA)
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                 "VALUES (%s, %s, 'ALTRO', %s, TRUE)", SEDE_2, U2, ALTRA)
    client = TestClient(fw.app, raise_server_exceptions=False, headers={"X-Worker-Key": CHIAVE})
    client.finto = finto
    client.db = db_sql
    yield client
    fw.app.dependency_overrides.pop(admin._verify_admin, None)


def _base(cliente=U1):
    return f"/api/admin/clienti/{cliente}/invio-commercialista"


def _collega(app):
    r = app.post(_base(), json={"piva": PIVA})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _completa(app, cid, email=EMAIL):
    """Come lo attiva il cliente dalle Impostazioni (l'admin non puo')."""
    _cur(app.db, "UPDATE public.invio_commercialista_config SET email_destinatario = %s, data_partenza = %s, "
                 "frequenza = 'mensile' WHERE id = %s", email, _oggi() - timedelta(days=40), cid)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET consenso_ricevuto = true, consenso_data = %s, "
                 "consenso_email = %s, consenso_at = now(), consenso_da = 'a1@ic.test', consenso_testo = 'Autorizzo' "
                 "WHERE id = %s", _oggi() - timedelta(days=1), email, cid)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET attivo = true WHERE id = %s", cid)


def _invio_inviato(app, cid, dal, al):
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s", dal, cid)
    iid = str(_cur(app.db, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                           "destinatario, tipo, periodo_dal, periodo_al, richiesto_da) VALUES (%s, %s, %s, %s, %s, 'primo', %s, %s, 'admin') "
                           "RETURNING id", cid, U1, PIVA, AZIENDA, EMAIL, dal, al)[0][0])
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now() WHERE id = %s", iid)
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'inviato' WHERE id = %s", iid)
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


# ─── Collegare la P.IVA ──────────────────────────────────────────────────────

def test_lo_stato_propone_le_piva_del_cliente(app):
    dati = app.get(_base()).json()
    assert dati["piva_disponibili"] == [PIVA] and dati["configurazioni"] == []
    assert dati["oggi"] == _oggi().isoformat()


def test_la_prova_collega_la_piva_a_invoicetronic(app):
    """Prima che il cliente attivi, l'admin puo' fare la prova a vuoto: la P.IVA
    si collega (spenta, senza email ne' consenso) col company_id trovato."""
    cid = _collega(app)
    config = app.get(_base()).json()["configurazioni"]
    assert [c["id"] for c in config] == [cid] and config[0]["invoicetronic_company_id"] == AZIENDA
    assert (config[0]["attivo"], config[0]["email_destinatario"], config[0]["consenso_ricevuto"]) == (False, None, False)
    assert app.get(_base()).json()["piva_disponibili"] == []


def test_la_piva_di_un_altro_cliente_non_si_collega(app):
    r = app.post(_base(), json={"piva": ALTRA})
    assert r.status_code == 400 and app.finto.chiamate == []


def test_una_piva_che_non_e_su_invoicetronic(app):
    app.finto.aziende.clear()
    r = app.post(_base(), json={"piva": PIVA})
    assert r.status_code == 404 and "prima fattura" in r.json()["detail"]


def test_un_azienda_diversa_da_quella_delle_fatture_arrivate_non_si_collega(app):
    _cur(app.db, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, ristorante_id, source, payload_meta) "
                 "VALUES (1, 'evt-a', %s, 'done', %s, %s, 'invoicetronic', %s::jsonb)",
         PIVA, U1, SEDE_1, json.dumps({"invoicetronic_company_id": 999}))
    assert app.post(_base(), json={"piva": PIVA}).status_code == 409
    assert _cur(app.db, "SELECT count(*) FROM public.invio_commercialista_config")[0][0] == 0


def test_lo_storico_che_coincide_si_collega(app):
    _cur(app.db, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, ristorante_id, source, payload_meta) "
                 "VALUES (1, 'evt-a', %s, 'done', %s, %s, 'invoicetronic', %s::jsonb)",
         PIVA, U1, SEDE_1, json.dumps({"invoicetronic_company_id": AZIENDA}))
    _collega(app)


def test_una_seconda_configurazione_per_la_stessa_piva(app):
    _collega(app)
    r = app.post(_base(), json={"piva": PIVA})
    assert r.status_code == 409 and "gia' una configurazione" in r.json()["detail"]


# ─── L'admin spegne, non accende ─────────────────────────────────────────────

def test_l_admin_non_accende(app):
    """Il consenso e' del cliente: anche una configurazione con tutto al suo posto
    la riaccende solo lui."""
    cid = _collega(app)
    _completa(app, cid)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET attivo = false WHERE id = %s", cid)
    r = app.patch(f"{_base()}/{cid}", json={"attivo": True})
    assert r.status_code == 400 and "cliente" in r.json()["detail"]
    assert _cur(app.db, "SELECT attivo FROM public.invio_commercialista_config")[0][0] is False


def test_l_admin_spegne(app):
    cid = _collega(app)
    _completa(app, cid)
    assert app.patch(f"{_base()}/{cid}", json={"attivo": False}).json()["attivo"] is False


@pytest.mark.parametrize("corpo", [
    {"email_destinatario": "altro@studio.test"}, {"frequenza": "settimanale"}, {"data_partenza": "2026-07-15"},
    {"consenso_data": "2026-09-30"}, {"revoca_consenso": True}, {},
])
def test_email_consenso_e_partenza_non_li_tocca_l_admin(app, corpo):
    cid = _collega(app)
    _completa(app, cid)
    r = app.patch(f"{_base()}/{cid}", json=corpo)
    assert r.status_code == 400
    assert _cur(app.db, "SELECT email_destinatario, frequenza, consenso_ricevuto, attivo "
                        "FROM public.invio_commercialista_config")[0] == (EMAIL, "mensile", True, True)


def test_la_configurazione_di_un_altro_cliente_non_si_tocca(app):
    cid = _collega(app)
    assert app.patch(f"{_base(U2)}/{cid}", json={"attivo": False}).status_code == 404
    assert app.post(f"{_base(U2)}/{cid}/invii", json={
        "tipo": "prova", "dal": (_oggi() - timedelta(days=30)).isoformat(),
        "al": (_oggi() - timedelta(days=1)).isoformat()}).status_code == 404


def test_riprendere_toglie_la_sospensione(app):
    cid = _collega(app)
    _completa(app, cid)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET sospesa_at = now(), sospesa_motivo = 'x' WHERE id = %s", cid)
    config = app.patch(f"{_base()}/{cid}", json={"riprendi": True}).json()
    assert (config["sospesa_at"], config["sospesa_motivo"]) == (None, None)


# ─── Chiedere un invio ───────────────────────────────────────────────────────

def _invii(app):
    return _cur(app.db, "SELECT tipo, periodo_dal, periodo_al, stato, richiesto_da, destinatario "
                        "FROM public.invio_commercialista_invii ORDER BY creata_at")


@pytest.mark.parametrize("tipo", ["invia_ora", "primo", "ordinario"])
def test_l_admin_non_lancia_primo_ne_ordinario(app, tipo):
    """Il primo invio e i successivi li crea il pianificatore notturno."""
    cid = _collega(app)
    _completa(app, cid)
    r = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": tipo, "dal": (_oggi() - timedelta(days=30)).isoformat(), "al": (_oggi() - timedelta(days=1)).isoformat()})
    assert r.status_code == 422 and _invii(app) == []


@pytest.mark.parametrize("dal,al,messaggio", [
    (-10, 0, "al piu' tardi ieri"),
    (-3 * 365, -5, "2 anni"),
    (-5, -10, "dopo quella di fine"),
])
def test_la_prova_con_un_periodo_sbagliato(app, dal, al, messaggio):
    cid = _collega(app)
    r = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "prova", "dal": (_oggi() + timedelta(days=dal)).isoformat(), "al": (_oggi() + timedelta(days=al)).isoformat()})
    assert r.status_code == 400 and messaggio in r.json()["detail"]


def test_la_prova_si_chiede_anche_a_configurazione_spenta(app):
    cid = _collega(app)
    r = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "prova", "dal": (_oggi() - timedelta(days=30)).isoformat(), "al": (_oggi() - timedelta(days=1)).isoformat()})
    assert r.status_code == 200, r.text
    assert _invii(app)[0][0] == "prova"


def test_un_secondo_invio_mentre_il_primo_e_in_coda(app):
    cid = _collega(app)
    corpo = {"tipo": "prova", "dal": (_oggi() - timedelta(days=30)).isoformat(), "al": (_oggi() - timedelta(days=1)).isoformat()}
    assert app.post(f"{_base()}/{cid}/invii", json=corpo).status_code == 200
    r = app.post(f"{_base()}/{cid}/invii", json=corpo)
    assert r.status_code == 409 and "in corso o da chiarire" in r.json()["detail"]


def test_a_configurazione_spenta_il_reinvio_e_rifiutato_dal_db(app):
    cid = _collega(app)
    _completa(app, cid)
    _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    app.patch(f"{_base()}/{cid}", json={"attivo": False})
    r = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "reinvio", "dal": (_oggi() - timedelta(days=20)).isoformat(), "al": (_oggi() - timedelta(days=10)).isoformat()})
    assert r.status_code == 400 and "configurazione spenta" in r.json()["detail"]


def test_senza_sede_sdi_niente_reinvio_ma_la_prova_si(app):
    cid = _collega(app)
    _completa(app, cid)
    _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    _cur(app.db, "UPDATE public.ristoranti SET sdi_attivo = false WHERE id = %s", SEDE_1)
    r = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "reinvio", "dal": (_oggi() - timedelta(days=20)).isoformat(), "al": (_oggi() - timedelta(days=10)).isoformat()})
    assert r.status_code == 400 and "SDI" in r.json()["detail"]
    assert app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "prova", "dal": (_oggi() - timedelta(days=30)).isoformat(),
        "al": (_oggi() - timedelta(days=1)).isoformat()}).status_code == 200


def test_il_reinvio_resta_nel_gia_inviato(app):
    cid = _collega(app)
    _completa(app, cid)
    _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    fuori = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "reinvio", "dal": (_oggi() - timedelta(days=20)).isoformat(), "al": (_oggi() - timedelta(days=5)).isoformat()})
    assert fuori.status_code == 400 and "gia' stato inviato" in fuori.json()["detail"]
    dentro = app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "reinvio", "dal": (_oggi() - timedelta(days=20)).isoformat(), "al": (_oggi() - timedelta(days=10)).isoformat()})
    assert dentro.status_code == 200, dentro.text


# ─── Chiarire e annullare ────────────────────────────────────────────────────

def _incerto(app, cid):
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s",
         _oggi() - timedelta(days=40), cid)
    iid = str(_cur(app.db, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                           "destinatario, tipo, periodo_dal, periodo_al, richiesto_da) VALUES (%s, %s, %s, %s, %s, 'primo', %s, %s, 'admin') "
                           "RETURNING id", cid, U1, PIVA, AZIENDA, EMAIL, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))[0][0])
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now() WHERE id = %s", iid)
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'esito_incerto' WHERE id = %s", iid)
    return iid


def test_esito_incerto_arrivato_consuma_il_periodo(app):
    cid = _collega(app)
    _completa(app, cid)
    iid = _incerto(app, cid)
    r = app.post(f"{_base()}/{cid}/invii/{iid}/chiarisci", json={"esito": "arrivata"})
    assert r.json()["stato"] == "inviato"
    assert app.get(_base()).json()["configurazioni"][0]["ultimo_giorno_inviato"] == (_oggi() - timedelta(days=10)).isoformat()


def test_esito_incerto_non_arrivato_libera_il_periodo(app):
    cid = _collega(app)
    _completa(app, cid)
    iid = _incerto(app, cid)
    r = app.post(f"{_base()}/{cid}/invii/{iid}/chiarisci", json={"esito": "non_arrivata"})
    assert r.json()["stato"] == "errore" and r.json()["chiarito_non_partito_at"] is not None
    assert app.get(_base()).json()["configurazioni"][0]["ultimo_giorno_inviato"] is None, \
        "il periodo si rispedisce: il pianificatore rifa' il primo"


def test_si_chiarisce_solo_un_esito_incerto(app):
    cid = _collega(app)
    _completa(app, cid)
    iid = _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    assert app.post(f"{_base()}/{cid}/invii/{iid}/chiarisci", json={"esito": "non_arrivata"}).status_code == 409


def test_si_annulla_solo_una_richiesta_non_presa(app):
    cid = _collega(app)
    assert app.post(f"{_base()}/{cid}/invii", json={
        "tipo": "prova", "dal": (_oggi() - timedelta(days=30)).isoformat(),
        "al": (_oggi() - timedelta(days=1)).isoformat()}).status_code == 200
    iid = str(_cur(app.db, "SELECT id FROM public.invio_commercialista_invii")[0][0])
    r = app.post(f"{_base()}/{cid}/invii/{iid}/annulla")
    assert r.json()["stato"] == "errore" and r.json()["motivo"] == "annullato dall'admin"
    assert app.post(f"{_base()}/{cid}/invii/{iid}/annulla").status_code == 409


def test_un_invio_di_un_altra_configurazione_non_si_tocca(app):
    """Due configurazioni dello stesso cliente: l'invio della prima non si
    raggiunge dal percorso della seconda."""
    terza = "98765432109"
    _cur(app.db, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                 "VALUES ('4f0f0000-0000-4000-8000-0000000000a3', %s, 'TERZA', %s, TRUE)", U1, terza)
    app.finto.aziende[terza] = {"id": 3000, "vat": f"IT{terza}", "name": "TERZA SRL"}
    cid = _collega(app)
    _completa(app, cid)
    iid = _incerto(app, cid)
    altra = app.post(_base(), json={"piva": terza}).json()["id"]
    assert app.post(f"{_base()}/{altra}/invii/{iid}/chiarisci", json={"esito": "arrivata"}).status_code == 404
    assert app.post(f"{_base()}/{altra}/invii/{iid}/annulla").status_code == 404


def test_invoicetronic_in_errore(app):
    from services.invoicetronic_client import ErroreInvoicetronic

    def rotto(piva):
        raise ErroreInvoicetronic("HTTP 401", status=401, configurazione=True)
    app.finto.azienda_per_piva = rotto
    r = app.post(_base(), json={"piva": PIVA})
    assert r.status_code == 503 and "HTTP 401" in r.json()["detail"]



# ─── Storia orfana e cancellazione dell'account ──────────────────────────────

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
    cid = _collega(app)
    _completa(app, cid)
    iid = _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
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



def test_un_id_che_non_e_un_uuid_e_un_404_non_un_500(app):
    """Il proxy li ferma prima; chiamando il worker direttamente arrivavano al DB
    come cast fallito."""
    assert app.get("/api/admin/clienti/non-un-uuid/invio-commercialista").status_code == 404
    cid = _collega(app)
    assert app.patch(f"{_base()}/non-un-uuid", json={"attivo": False}).status_code == 404
    assert app.post(f"{_base()}/{cid}/invii/non-un-uuid/annulla").status_code == 404


def test_l_export_dei_dati_del_cliente_contiene_l_invio_al_commercialista(app, monkeypatch):
    """Art. 15 e 20: l'email del commercialista e il registro sono dati del cliente."""
    from services.routers import account
    cid = _collega(app)
    _completa(app, cid)
    _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    monkeypatch.setattr(account, "_resolve_user_from_token", lambda authorization: {"id": U1, "email": "a1@ic.test"})
    dati = app.get("/api/account/esporta-dati").json()
    assert [c["email_destinatario"] for c in dati["invio_commercialista_configurazioni"]] == [EMAIL]
    assert len(dati["invio_commercialista_invii"]) == 1
