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
    r = app.post(_base(), json={"piva": PIVA, "company_id": AZIENDA})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _completa(app, cid, email=EMAIL):
    for corpo in ({"email_destinatario": email, "data_partenza": (_oggi() - timedelta(days=40)).isoformat()},
                  {"consenso_data": (_oggi() - timedelta(days=1)).isoformat()},
                  {"attivo": True}):
        r = app.patch(f"{_base()}/{cid}", json=corpo)
        assert r.status_code == 200, r.text
    return r.json()


def _invio_inviato(app, cid, dal, al):
    iid = str(_cur(app.db, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                           "destinatario, tipo, periodo_dal, periodo_al, richiesto_da) VALUES (%s, %s, %s, %s, %s, 'primo', %s, %s, 'admin') "
                           "RETURNING id", cid, U1, PIVA, AZIENDA, EMAIL, dal, al)[0][0])
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso' WHERE id = %s", iid)
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


def test_si_cerca_l_azienda_e_si_collega(app):
    r = app.get(f"{_base()}/azienda", params={"piva": PIVA})
    assert r.json() == {"company_id": AZIENDA, "nome": "OFFSIDE SRL", "vat": f"IT{PIVA}", "gia_viste": []}
    cid = _collega(app)
    config = app.get(_base()).json()["configurazioni"]
    assert [c["id"] for c in config] == [cid] and config[0]["invoicetronic_company_id"] == AZIENDA
    assert config[0]["attivo"] is False and app.get(_base()).json()["piva_disponibili"] == []


def test_la_piva_di_un_altro_cliente_non_si_cerca(app):
    r = app.get(f"{_base()}/azienda", params={"piva": ALTRA})
    assert r.status_code == 400 and app.finto.chiamate == []


def test_una_piva_che_non_e_su_invoicetronic(app):
    app.finto.aziende.clear()
    r = app.get(f"{_base()}/azienda", params={"piva": PIVA})
    assert r.status_code == 404 and "prima fattura" in r.json()["detail"]


def test_un_azienda_diversa_da_quella_delle_fatture_arrivate_non_si_collega(app):
    _cur(app.db, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, ristorante_id, source, payload_meta) "
                 "VALUES (1, 'evt-a', %s, 'done', %s, %s, 'invoicetronic', %s::jsonb)",
         PIVA, U1, SEDE_1, json.dumps({"invoicetronic_company_id": 999}))
    assert app.get(f"{_base()}/azienda", params={"piva": PIVA}).status_code == 409
    assert app.post(_base(), json={"piva": PIVA, "company_id": AZIENDA}).status_code == 409


def test_lo_storico_che_coincide_si_mostra(app):
    _cur(app.db, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, ristorante_id, source, payload_meta) "
                 "VALUES (1, 'evt-a', %s, 'done', %s, %s, 'invoicetronic', %s::jsonb)",
         PIVA, U1, SEDE_1, json.dumps({"invoicetronic_company_id": AZIENDA}))
    assert app.get(f"{_base()}/azienda", params={"piva": PIVA}).json()["gia_viste"] == [AZIENDA]


def test_il_company_id_lo_decide_invoicetronic_non_il_body(app):
    r = app.post(_base(), json={"piva": PIVA, "company_id": 5})
    assert r.status_code == 409
    assert _cur(app.db, "SELECT count(*) FROM public.invio_commercialista_config")[0][0] == 0


def test_una_seconda_configurazione_per_la_stessa_piva(app):
    _collega(app)
    r = app.post(_base(), json={"piva": PIVA, "company_id": AZIENDA})
    assert r.status_code == 409 and "gia' una configurazione" in r.json()["detail"]


# ─── Configurare ─────────────────────────────────────────────────────────────

def test_una_configurazione_completa_si_accende_e_l_email_si_normalizza(app):
    cid = _collega(app)
    config = _completa(app, cid, email="  Studio@Commercialista.TEST ")
    assert config["attivo"] is True and config["email_destinatario"] == EMAIL and config["consenso_email"] == EMAIL


def test_accendere_senza_consenso_dice_cosa_manca(app):
    cid = _collega(app)
    app.patch(f"{_base()}/{cid}", json={"email_destinatario": EMAIL, "data_partenza": "2026-07-15"})
    r = app.patch(f"{_base()}/{cid}", json={"attivo": True})
    assert r.status_code == 400 and "consenso" in r.json()["detail"]


def test_email_e_consenso_insieme_valgono_per_l_email_nuova(app):
    cid = _collega(app)
    _completa(app, cid)
    r = app.patch(f"{_base()}/{cid}", json={"email_destinatario": "nuovo@studio.test",
                                            "consenso_data": _oggi().isoformat()})
    config = r.json()
    assert config["consenso_email"] == "nuovo@studio.test" and config["consenso_ricevuto"] is True
    assert config["attivo"] is False, "cambiare email spegne: va riacceso"


def test_consenso_senza_email_rifiutato(app):
    cid = _collega(app)
    r = app.patch(f"{_base()}/{cid}", json={"consenso_data": _oggi().isoformat()})
    assert r.status_code == 400 and "Prima scrivi l'email" in r.json()["detail"]


def test_consenso_con_una_data_futura_rifiutato(app):
    cid = _collega(app)
    app.patch(f"{_base()}/{cid}", json={"email_destinatario": EMAIL})
    r = app.patch(f"{_base()}/{cid}", json={"consenso_data": (_oggi() + timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and "futura" in r.json()["detail"]


def test_revocare_il_consenso_spegne(app):
    cid = _collega(app)
    _completa(app, cid)
    config = app.patch(f"{_base()}/{cid}", json={"revoca_consenso": True}).json()
    assert (config["attivo"], config["consenso_ricevuto"], config["consenso_email"]) == (False, False, None)


@pytest.mark.parametrize("giorni", [3 * 365, 0, -5])
def test_data_di_partenza_fuori_dai_limiti(app, giorni):
    cid = _collega(app)
    r = app.patch(f"{_base()}/{cid}", json={"data_partenza": (_oggi() - timedelta(days=giorni)).isoformat()})
    assert r.status_code == 400


def test_la_configurazione_di_un_altro_cliente_non_si_tocca(app):
    cid = _collega(app)
    assert app.patch(f"{_base(U2)}/{cid}", json={"frequenza": "settimanale"}).status_code == 404
    assert app.post(f"{_base(U2)}/{cid}/invii", json={"tipo": "invia_ora"}).status_code == 404


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


def test_il_primo_invio_parte_dalla_data_di_partenza(app):
    cid = _collega(app)
    _completa(app, cid)
    r = app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"})
    assert r.status_code == 200, r.text
    assert _invii(app) == [("primo", _oggi() - timedelta(days=40), _oggi() - timedelta(days=1), "richiesto", "admin", EMAIL)]


def test_dopo_il_primo_invia_ora_manda_il_periodo_maturato(app):
    cid = _collega(app)
    _completa(app, cid)
    _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    assert app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"}).status_code == 200
    assert _invii(app)[-1][:3] == ("ordinario", _oggi() - timedelta(days=9), _oggi() - timedelta(days=1))


def test_il_primo_invio_non_va_oltre_i_due_anni(app):
    """La data di partenza era valida quando e' stata scritta; il tempo passa."""
    cid = _collega(app)
    _completa(app, cid)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s",
         _oggi() - timedelta(days=3 * 365), cid)
    assert app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"}).status_code == 200
    from services.invio_commercialista_service import limite_due_anni
    assert _invii(app)[0][1] == limite_due_anni(_oggi())


def test_niente_da_inviare(app):
    cid = _collega(app)
    _completa(app, cid)
    _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=1))
    r = app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"})
    assert r.status_code == 400 and "Niente da inviare" in r.json()["detail"]


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


def test_a_configurazione_spenta_invia_ora_e_rifiutato_dal_db(app):
    cid = _collega(app)
    app.patch(f"{_base()}/{cid}", json={"email_destinatario": EMAIL, "data_partenza": "2026-07-15"})
    r = app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"})
    assert r.status_code == 400 and "configurazione spenta" in r.json()["detail"]


def test_senza_sede_sdi_niente_invio_ma_la_prova_si(app):
    cid = _collega(app)
    _completa(app, cid)
    _cur(app.db, "UPDATE public.ristoranti SET sdi_attivo = false WHERE id = %s", SEDE_1)
    r = app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"})
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
    assert app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"}).status_code == 200
    assert _invii(app)[-1][0] == "primo", "il periodo si rispedisce"


def test_si_chiarisce_solo_un_esito_incerto(app):
    cid = _collega(app)
    _completa(app, cid)
    iid = _invio_inviato(app, cid, _oggi() - timedelta(days=40), _oggi() - timedelta(days=10))
    assert app.post(f"{_base()}/{cid}/invii/{iid}/chiarisci", json={"esito": "non_arrivata"}).status_code == 409


def test_si_annulla_solo_una_richiesta_non_presa(app):
    cid = _collega(app)
    _completa(app, cid)
    assert app.post(f"{_base()}/{cid}/invii", json={"tipo": "invia_ora"}).status_code == 200
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
    altra = app.post(_base(), json={"piva": terza, "company_id": 3000}).json()["id"]
    assert app.post(f"{_base()}/{altra}/invii/{iid}/chiarisci", json={"esito": "arrivata"}).status_code == 404
    assert app.post(f"{_base()}/{altra}/invii/{iid}/annulla").status_code == 404


def test_invoicetronic_in_errore(app):
    from services.invoicetronic_client import ErroreInvoicetronic

    def rotto(piva):
        raise ErroreInvoicetronic("HTTP 401", status=401, configurazione=True)
    app.finto.azienda_per_piva = rotto
    r = app.get(f"{_base()}/azienda", params={"piva": PIVA})
    assert r.status_code == 503 and "HTTP 401" in r.json()["detail"]
