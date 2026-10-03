"""L'invio al commercialista attivato dal cliente dalle Impostazioni, contro il
worker vero e un Postgres vero (02/10/2026).

Si chiamano gli endpoint col TestClient, come li chiama il proxy Next.js; il DB
e' quello delle migration. Finti solo Invoicetronic, Telegram e la sessione.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.sql

ROMA = ZoneInfo("Europe/Rome")
U1 = "5a0a0000-0000-4000-8000-000000000001"
U2 = "5a0a0000-0000-4000-8000-000000000002"
PIVA = "07863990961"
SENZA_SDI = "11111111115"
ALTRUI = "12345678903"
AZIENDA = 1756
CHIAVE = "chiave-finta-cliente"
EMAIL = "studio@commercialista.test"
BASE = "/api/account/invio-commercialista"


def _oggi():
    return datetime.now(ROMA).date()


def _cur(db_sql, sql, *params):
    with db_sql.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.fetchall() if cur.description else []


class _Invoicetronic:
    def __init__(self):
        self.aziende = {PIVA: {"id": AZIENDA, "vat": f"IT{PIVA}", "name": "OFFSIDE SRL"}}

    def azienda_per_piva(self, piva):
        return self.aziende.get(piva)


@pytest.fixture
def app(db_sql, monkeypatch):
    import os
    os.environ.setdefault("WORKER_DEV_MODE", "1")
    import services.fastapi_worker as fw
    from fastapi.testclient import TestClient
    from services.routers import invio_commercialista_cliente as rotte
    from tests.helpers_supabase_sql import ClientSQL

    sb = ClientSQL(db_sql)
    monkeypatch.setattr(fw, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "WORKER_SECRET_KEY", CHIAVE)
    monkeypatch.setattr(fw, "WORKER_DEV_MODE", False)
    monkeypatch.setenv("INVIO_COMMERCIALISTA_ATTIVO", "1")
    finto = _Invoicetronic()
    avvisi = []
    monkeypatch.setattr(rotte, "_client_invoicetronic", lambda: finto)
    monkeypatch.setattr(rotte, "_avvisa_admin", avvisi.append)
    utente = {"id": U1, "email": "Titolare@IC.test"}
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda authorization: dict(utente))
    for uid, email in ((U1, "titolare@ic.test"), (U2, "altro@ic.test")):
        _cur(db_sql, "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')", uid, email)
    sedi = [
        ("5a0a0000-0000-4000-8000-0000000000a1", U1, "OFFSIDE", PIVA, True),
        ("5a0a0000-0000-4000-8000-0000000000a2", U1, "OVERTIME", PIVA, True),
        ("5a0a0000-0000-4000-8000-0000000000a3", U1, "MAGAZZINO", SENZA_SDI, False),
        ("5a0a0000-0000-4000-8000-0000000000a4", U2, "ALTRO", ALTRUI, True),
    ]
    for sid, uid, nome, piva, sdi in sedi:
        _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, sdi_attivo) "
                     "VALUES (%s, %s, %s, %s, TRUE, %s)", sid, uid, nome, piva, sdi)
    for piva in (PIVA, ALTRUI):
        _cur(db_sql, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, source, payload_meta, created_at) "
                     "VALUES (nextval('public.fatture_queue_id_seq'), %s, %s, 'invoicetronic', %s, now() - interval '1 hour')",
             f"ev-seme-{piva}", piva, f'{{"invoicetronic_company_id": {AZIENDA if piva == PIVA else 3000}}}')
    _cur(db_sql, "INSERT INTO public.sessioni (user_id, token, source) VALUES (%s, 't', 'login')", U1)
    client = TestClient(fw.app, raise_server_exceptions=False,
                        headers={"X-Worker-Key": CHIAVE, "Authorization": "Bearer t"})
    client.db, client.finto, client.avvisi, client.utente = db_sql, finto, avvisi, utente
    return client


def _attiva(app, **campi):
    corpo = {"piva": PIVA, "email": EMAIL, "frequenza": "settimanale", "autorizzo": True, **campi}
    return app.post(BASE, json=corpo)


def _config(app):
    righe = _cur(app.db, "SELECT attivo, email_destinatario, frequenza, data_partenza, consenso_ricevuto, consenso_email, "
                         "consenso_da, consenso_testo, consenso_at IS NOT NULL, invoicetronic_company_id, user_id::text "
                         "FROM public.invio_commercialista_config WHERE piva = %s", PIVA)
    return righe[0] if righe else None


def _arrivata(app, giorni_fa, company=AZIENDA):
    _cur(app.db, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, source, payload_meta, created_at) "
                 "VALUES (nextval('public.fatture_queue_id_seq'), %s, %s, 'invoicetronic', %s, now() - make_interval(days => %s))",
         f"ev-{giorni_fa}-{company}", PIVA, f'{{"invoicetronic_company_id": {company}}}', giorni_fa)


# ─── Cosa vede il cliente ────────────────────────────────────────────────────

def test_vede_solo_le_piva_che_ricevono_via_sdi_coi_nomi_delle_sedi(app):
    dati = app.get(BASE).json()
    assert [(v["piva"], v["sedi"], v["attivo"]) for v in dati["pive"]] == [(PIVA, ["OFFSIDE", "OVERTIME"], False)]
    assert dati["disponibile"] is True
    assert "{email}" in dati["testo_autorizzazione"] and dati["frequenze"]["settimanale"] == "ogni lunedì"


def test_finche_l_interruttore_e_spento_non_si_attiva(app, monkeypatch):
    monkeypatch.delenv("INVIO_COMMERCIALISTA_ATTIVO")
    assert app.get(BASE).json()["disponibile"] is False
    r = _attiva(app)
    assert r.status_code == 409 and _config(app) is None


# ─── Attivare ────────────────────────────────────────────────────────────────

def test_attivare_collega_registra_il_consenso_e_accende(app):
    from services import invio_commercialista_service as svc
    r = _attiva(app)
    assert r.status_code == 200, r.text
    (attivo, email, frequenza, partenza, consenso, consenso_email, da, testo, con_ora, company, uid) = _config(app)
    assert (attivo, email, frequenza, consenso, consenso_email, company, uid) == (
        True, EMAIL, "settimanale", True, EMAIL, AZIENDA, U1)
    assert partenza == _oggi(), "di default solo le fatture nuove"
    assert da == "titolare@ic.test" and con_ora
    assert testo == svc.testo_autorizzazione(EMAIL, "settimanale", PIVA) and EMAIL in testo and PIVA in testo
    voce = r.json()["pive"][0]
    assert voce["attivo"] is True and voce["prossimo_invio"] is not None and voce["attivato_il"] is not None
    assert len(app.avvisi) == 1 and EMAIL not in app.avvisi[0] and "titolare" not in app.avvisi[0].lower()


def test_senza_autorizzazione_non_si_attiva(app):
    r = _attiva(app, autorizzo=False)
    assert r.status_code == 400 and _config(app) is None


@pytest.mark.parametrize("email", ["senza-chiocciola", "a@b", "due@@x.it", ""])
def test_email_non_valida(app, email):
    r = _attiva(app, email=email)
    assert r.status_code == 400 and _config(app) is None


def test_l_email_si_salva_normalizzata(app):
    assert _attiva(app, email="  Studio@Commercialista.TEST ").status_code == 200
    assert _config(app)[1] == EMAIL


@pytest.mark.parametrize("piva", [SENZA_SDI, ALTRUI, "0786399096"])
def test_solo_le_proprie_piva_che_ricevono_via_sdi(app, piva):
    r = _attiva(app, piva=piva)
    assert r.status_code == 400
    assert _cur(app.db, "SELECT count(*) FROM public.invio_commercialista_config")[0][0] == 0


def test_includere_le_gia_ricevute_parte_dalla_prima_fattura(app):
    _arrivata(app, 20)
    _arrivata(app, 5)
    voce = app.get(BASE).json()["pive"][0]
    assert voce["recupero_dal"] == (_oggi() - timedelta(days=20)).isoformat()
    assert _attiva(app, includi_precedenti=True).status_code == 200
    assert _config(app)[3] == _oggi() - timedelta(days=20)


def test_azienda_non_ancora_su_invoicetronic(app):
    app.finto.aziende.clear()
    r = _attiva(app)
    assert r.status_code == 400 and "prima" in r.json()["detail"] and _config(app) is None


def test_azienda_incoerente_avvisa_l_admin_e_non_collega(app):
    _arrivata(app, 3, company=999)
    r = _attiva(app)
    assert r.status_code == 409 and _config(app) is None
    assert len(app.avvisi) == 1 and "999" in app.avvisi[0]


def test_una_configurazione_sospesa_non_la_riaccende_il_cliente(app):
    assert _attiva(app).status_code == 200
    _cur(app.db, "UPDATE public.invio_commercialista_config SET sospesa_at = now() WHERE piva = %s", PIVA)
    r = _attiva(app, email="nuovo@studio.test")
    assert r.status_code == 409 and _config(app)[1] == EMAIL


# ─── Modificare, disattivare, riattivare ─────────────────────────────────────

def test_cambiare_email_rinnova_il_consenso_e_resta_attivo(app):
    _arrivata(app, 20)
    assert _attiva(app, includi_precedenti=True).status_code == 200
    assert _attiva(app, email="nuovo@studio.test", frequenza="mensile").status_code == 200
    attivo, email, frequenza, partenza, consenso, consenso_email, _, testo, _, _, _ = _config(app)
    assert (attivo, email, frequenza, consenso, consenso_email) == (True, "nuovo@studio.test", "mensile", True, "nuovo@studio.test")
    assert "nuovo@studio.test" in testo and "il 1° di ogni mese" in testo
    assert partenza == _oggi() - timedelta(days=20), "gia' attivo: da quando si parte non cambia"


def test_disattivare_e_riattivare_solo_le_nuove(app):
    _arrivata(app, 20)
    assert _attiva(app, includi_precedenti=True).status_code == 200
    r = app.post(f"{BASE}/disattiva", json={"piva": PIVA})
    assert r.status_code == 200 and r.json()["pive"][0]["attivo"] is False and _config(app)[0] is False
    assert _attiva(app).status_code == 200
    assert _config(app)[3] == _oggi(), "riattivato senza le gia' ricevute: si riparte da oggi"


def test_disattivare_una_piva_mai_attivata(app):
    assert app.post(f"{BASE}/disattiva", json={"piva": PIVA}).status_code == 404


def test_la_configurazione_di_un_altro_account_non_si_tocca(app):
    assert _attiva(app).status_code == 200
    app.utente.update({"id": U2, "email": "altro@ic.test"})
    assert app.post(f"{BASE}/disattiva", json={"piva": PIVA}).status_code == 409
    assert _config(app)[0] is True


# ─── Chi puo' ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("metodo,percorso", [("get", BASE), ("post", BASE), ("post", f"{BASE}/disattiva")])
def test_un_sotto_utente_non_puo(app, metodo, percorso):
    from services.sotto_utenti_service import CHIAVE_CONTESTO
    app.utente[CHIAVE_CONTESTO] = {"id": "5a0a0000-0000-4000-8000-0000000000ff"}
    corpo = {"piva": PIVA, "email": EMAIL, "frequenza": "settimanale", "autorizzo": True}
    r = getattr(app, metodo)(percorso, **({} if metodo == "get" else {"json": corpo}))
    assert r.status_code == 403
    assert _config(app) is None


def test_le_rotte_sono_vietate_ai_sotto_utenti_nella_mappa():
    from services.permessi_rotte import ROTTE_VIETATE
    assert {("GET", BASE), ("POST", BASE), ("POST", f"{BASE}/disattiva")} <= ROTTE_VIETATE


def test_flag_sdi_acceso_ma_nessuna_fattura_arrivata_niente_scheda(app):
    """Il caso di Sushiland e Land: SDI «attivo» dal 23/06, mai arrivato niente."""
    _cur(app.db, "DELETE FROM public.fatture_queue WHERE piva_raw = %s", PIVA)
    assert app.get(BASE).json()["pive"] == []
    assert _attiva(app).status_code == 400 and _config(app) is None


# ─── Review del 02/10 ────────────────────────────────────────────────────────

def test_l_admin_che_impersona_non_attiva_al_posto_del_cliente(app):
    """La sessione d'impersonazione e' una sessione vera del cliente: senza questo
    controllo il consenso risulterebbe dato dal cliente, ed e' falso."""
    _cur(app.db, "UPDATE public.sessioni SET source = 'impersonation' WHERE token = 't'")
    assert app.get(BASE).json()["impersonazione"] is True
    r = _attiva(app)
    assert r.status_code == 403 and "solo lui" in r.json()["detail"] and _config(app) is None


def test_l_admin_che_impersona_puo_spegnere(app):
    assert _attiva(app).status_code == 200
    _cur(app.db, "UPDATE public.sessioni SET source = 'impersonation' WHERE token = 't'")
    assert app.post(f"{BASE}/disattiva", json={"piva": PIVA}).status_code == 200
    assert _config(app)[0] is False


def test_il_titolare_non_risulta_in_impersonazione(app):
    assert app.get(BASE).json()["impersonazione"] is False


def test_una_sede_disattivata_non_porta_la_sua_piva(app):
    _cur(app.db, "UPDATE public.ristoranti SET attivo = false WHERE partita_iva = %s", PIVA)
    assert app.get(BASE).json()["pive"] == []


def test_le_gia_ricevute_partono_dopo_lo_storico_di_una_configurazione_cancellata(app):
    _arrivata(app, 40)
    assert _attiva(app, includi_precedenti=True).status_code == 200
    cid = _cur(app.db, "SELECT id FROM public.invio_commercialista_config")[0][0]
    fino = _oggi() - timedelta(days=20)
    _cur(app.db, "UPDATE public.invio_commercialista_config SET data_partenza = %s WHERE id = %s",
         _oggi() - timedelta(days=40), cid)
    iid = _cur(app.db, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                       "destinatario, tipo, periodo_dal, periodo_al, richiesto_da) VALUES (%s, %s, %s, %s, %s, 'primo', %s, %s, "
                       "'notturno') RETURNING id", cid, U1, PIVA, AZIENDA, EMAIL, _oggi() - timedelta(days=40), fino)[0][0]
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now() WHERE id = %s", iid)
    _cur(app.db, "UPDATE public.invio_commercialista_invii SET stato = 'inviato' WHERE id = %s", iid)
    _cur(app.db, "DELETE FROM public.invio_commercialista_config WHERE id = %s", cid)
    assert app.get(BASE).json()["pive"][0]["recupero_dal"] == (fino + timedelta(days=1)).isoformat()
    assert _attiva(app, includi_precedenti=True).status_code == 200
    assert _config(app)[3] == fino + timedelta(days=1)
