"""Fase 3 del piano consulente: la «Conferma» delle cifre dettate, su Postgres vero.

`POST /api/assistente/registra` scrive solo quando il cliente preme Conferma su
una card proposta dall'assistente. Qui si prova sul DB dello snapshot, con i due
clienti del test di isolamento (A e B, due sedi ciascuno):
- la sede viene dalla proposta ed e' riverificata (altrui, tecnica, spenta,
  malformata -> 404; sotto-utente senza la sede o senza Margini -> 403), e la
  stessa chiamata sui propri id scrive davvero;
- 409 quando il valore registrato non e' piu' quello mostrato sulla card;
- si scrive solo cio' che e' dettato: coperti, extra, totale mensile restano.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401
from tests.test_sql_sotto_utenti import PASSWORD, _cache_pulita, _crea_sotto_utente, _login  # noqa: F401

pytestmark = pytest.mark.sql

URL = "/api/assistente/registra"
OGGI = datetime.now(tz=ZoneInfo("Europe/Rome")).date()
IERI = OGGI - timedelta(days=1)
MESE_SCORSO = OGGI.replace(day=1) - timedelta(days=1)


def _registra(sc, chi, **corpo):
    return sc.chiama(chi, "POST", URL, json_=corpo)


def _con_token(sc, token, **corpo):
    return sc.client.post(
        URL, json=corpo, headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER}
    )


def _riga(sc, sql, *params):
    return sc.conn.execute(sql, params).fetchone()


def _giorno(sc, sede, giorno):
    return _riga(
        sc,
        "SELECT fatturato_iva10::float, altri_ricavi_noiva::float, fatturato_iva22::float, coperti, source "
        "FROM public.ricavi_giornalieri WHERE ristorante_id = %s AND data = %s",
        sede, giorno,
    )


def _incasso(sede, giorno=IERI, **extra):
    return {"tipo": "incasso_giorno", "ristorante_id": sede, "data": giorno.isoformat(),
            "fatturato_iva10": 1800, "altri_ricavi_noiva": 540, **extra}


def _nuova_sede(sc, chi, *, attivo=True, tecnica=False):
    sede = str(uuid.uuid4())
    sc.conn.execute(
        "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, sede_tecnica) "
        "VALUES (%s, %s, 'EXTRA', %s, %s, %s)",
        (sede, chi.ids["user_id"], str(uuid.uuid4().int)[:11], attivo, tecnica),
    )
    return sede


# ─── La sede ──────────────────────────────────────────────────────────────────
def test_sui_propri_id_scrive_davvero(scenario):
    a = scenario.a
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _giorno(scenario, a.ids["sede1"], IERI) == (1800.0, 540.0, 0.0, None, "manuale")
    assert resp.json()["valori"] == {"data": IERI.isoformat(), "fatturato_iva10": 1800.0,
                                     "altri_ricavi_noiva": 540.0, "fatturato_iva22": 0.0}


def test_scrive_sulla_sede_della_proposta_non_su_quella_attiva(scenario):
    a = scenario.a
    resp = _registra(scenario, a, **_incasso(a.ids["sede2"]))
    assert resp.status_code == 200, resp.text
    assert _giorno(scenario, a.ids["sede2"], IERI) is not None
    assert _giorno(scenario, a.ids["sede1"], IERI) is None


@pytest.mark.parametrize("tipo", ["incasso_giorno", "personale_mese", "fatturato_mese"])
def test_la_sede_di_un_altro_cliente_e_404_e_non_scrive(scenario, tipo):
    a, b = scenario.a, scenario.b
    prima = scenario.impronta(b)
    corpo = {
        "incasso_giorno": _incasso(b.ids["sede1"]),
        "personale_mese": {"tipo": tipo, "ristorante_id": b.ids["sede1"], "anno": OGGI.year,
                           "mese": OGGI.month, "costo_dipendenti": 9000},
        "fatturato_mese": {"tipo": tipo, "ristorante_id": b.ids["sede1"], "anno": MESE_SCORSO.year,
                           "mese": MESE_SCORSO.month, "fatturato_iva10": 30000},
    }[tipo]
    resp = _registra(scenario, a, **corpo)
    assert resp.status_code == 404, resp.text
    assert scenario.impronta(b) == prima


@pytest.mark.parametrize("quale", ["tecnica", "spenta", "malformata", "inesistente"])
def test_sede_non_scrivibile_e_404(scenario, quale):
    a = scenario.a
    sede = {
        "tecnica": lambda: _nuova_sede(scenario, a, tecnica=True),
        "spenta": lambda: _nuova_sede(scenario, a, attivo=False),
        "malformata": lambda: "non-un-uuid",
        "inesistente": lambda: str(uuid.uuid4()),
    }[quale]()
    resp = _registra(scenario, a, **_incasso(sede))
    assert resp.status_code == 404, resp.text
    assert scenario.conn.execute(
        "SELECT count(*) FROM public.ricavi_giornalieri WHERE data = %s", (IERI,)
    ).fetchone()[0] == 0


# ─── Sotto-utenti ─────────────────────────────────────────────────────────────
def _token_sotto_utente(sc, pagine, email="resp@registra.test"):
    _crea_sotto_utente(sc.conn, sc.a.ids["user_id"], email, [sc.a.ids["sede1"]], pagine)
    resp = _login(sc, email)
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_sotto_utente_con_margini_scrive_sulla_sua_sede(scenario):
    token = _token_sotto_utente(scenario, {"home": True, "margini": True})
    resp = _con_token(scenario, token, **_incasso(scenario.a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _giorno(scenario, scenario.a.ids["sede1"], IERI) is not None


def test_sotto_utente_su_una_sede_non_sua_e_403(scenario):
    token = _token_sotto_utente(scenario, {"home": True, "margini": True})
    resp = _con_token(scenario, token, **_incasso(scenario.a.ids["sede2"]))
    assert resp.status_code == 403, resp.text
    assert _giorno(scenario, scenario.a.ids["sede2"], IERI) is None


def test_sotto_utente_senza_margini_e_403(scenario):
    token = _token_sotto_utente(scenario, {"home": True, "margini": False})
    resp = _con_token(scenario, token, **_incasso(scenario.a.ids["sede1"]))
    assert resp.status_code == 403, resp.text
    assert _giorno(scenario, scenario.a.ids["sede1"], IERI) is None


# ─── Incasso di un giorno ─────────────────────────────────────────────────────
def _semina_giorno(sc, sede, giorno, iva10=500, noiva=0, coperti=40, source="email"):
    sc.conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10, "
        "altri_ricavi_noiva, coperti, source) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (sc.a.ids["user_id"], sede, giorno, iva10, noiva, coperti, source),
    )


def test_riga_esistente_si_aggiorna_e_i_coperti_restano(scenario):
    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], IERI, iva10=500, coperti=40)
    precedente = {"fatturato_iva10": 500, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"], precedente=precedente))
    assert resp.status_code == 200, resp.text
    assert _giorno(scenario, a.ids["sede1"], IERI) == (1800.0, 540.0, 0.0, 40, "manuale")


def test_riga_nata_dopo_la_card_e_409_col_valore_nuovo(scenario):
    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], IERI, iva10=700, noiva=50)
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {
        "motivo": "valore_cambiato",
        "attuale": {"fatturato_iva10": 700.0, "altri_ricavi_noiva": 50.0, "fatturato_iva22": 0.0},
    }
    assert _giorno(scenario, a.ids["sede1"], IERI)[:2] == (700.0, 50.0)


def test_valore_cambiato_dopo_la_card_e_409(scenario):
    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], IERI, iva10=700)
    precedente = {"fatturato_iva10": 500, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"], precedente=precedente))
    assert resp.status_code == 409, resp.text
    assert _giorno(scenario, a.ids["sede1"], IERI)[0] == 700.0


def test_riga_tutta_a_zero_vale_come_nessun_valore(scenario):
    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], IERI, iva10=0, coperti=35)
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _giorno(scenario, a.ids["sede1"], IERI) == (1800.0, 540.0, 0.0, 35, "manuale")


def test_mese_tenuto_a_totale_rifiuta_il_giorno_e_non_lo_spegne(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, fatturato_iva10) "
        "VALUES (%s, %s, %s, 'mensile', 40000)",
        (a.ids["sede1"], IERI.year, IERI.month),
    )
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["motivo"] == "mese_a_totale"
    assert _giorno(scenario, a.ids["sede1"], IERI) is None
    assert _riga(scenario, "SELECT modalita FROM public.ricavi_modalita_mensile WHERE ristorante_id = %s "
                           "AND anno = %s AND mese = %s", a.ids["sede1"], IERI.year, IERI.month)[0] == "mensile"


# Futuro = dopodomani, non domani: OGGI si calcola alla raccolta, e se la suite
# passa la mezzanotte di Roma «domani» diventa oggi (3/10/2026, 3 rossi).
@pytest.mark.parametrize("giorno,importi", [
    (OGGI + timedelta(days=2), {}),
    (OGGI - timedelta(days=61), {}),
    (IERI, {"fatturato_iva10": -10}),
    (IERI, {"fatturato_iva10": 0, "altri_ricavi_noiva": 0}),
    (IERI, {"fatturato_iva10": 99_000, "altri_ricavi_noiva": 1_001}),
], ids=["futuro", "troppo-indietro", "negativo", "zero", "fuori-scala"])
def test_incasso_non_valido_e_400_e_non_scrive(scenario, giorno, importi):
    a = scenario.a
    resp = _registra(scenario, a, **{**_incasso(a.ids["sede1"], giorno=giorno), **importi})
    assert resp.status_code == 400, resp.text
    assert _giorno(scenario, a.ids["sede1"], giorno) is None


def test_limiti_del_periodo_sono_ammessi(scenario):
    a = scenario.a
    # «Oggi» al momento della chiamata, non alla raccolta: i limiti sono esatti.
    oggi = datetime.now(tz=ZoneInfo("Europe/Rome")).date()
    for giorno in (oggi, oggi - timedelta(days=60)):
        resp = _registra(scenario, a, **_incasso(a.ids["sede1"], giorno=giorno))
        assert resp.status_code == 200, (giorno, resp.text)


# ─── Personale di un mese ─────────────────────────────────────────────────────
def _personale(sede, anno=OGGI.year, mese=OGGI.month, **extra):
    return {"tipo": "personale_mese", "ristorante_id": sede, "anno": anno, "mese": mese,
            "costo_dipendenti": 12000, **extra}


def _margini(sc, sede, anno, mese):
    return _riga(sc, "SELECT costo_dipendenti::float, costo_personale_extra::float FROM public.margini_mensili "
                     "WHERE ristorante_id = %s AND anno = %s AND mese = %s", sede, anno, mese)


def test_personale_senza_riga_la_crea(scenario):
    a = scenario.a
    resp = _registra(scenario, a, **_personale(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _margini(scenario, a.ids["sede1"], OGGI.year, OGGI.month)[0] == 12000.0


def test_personale_a_zero_vale_come_nessun_valore_e_l_extra_resta(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_personale_extra) "
        "VALUES (%s, %s, %s, %s, 800)",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    resp = _registra(scenario, a, **_personale(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _margini(scenario, a.ids["sede1"], OGGI.year, OGGI.month) == (12000.0, 800.0)


def test_personale_con_la_sola_chiamata_scrive_il_lordo_e_la_chiamata_resta(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_personale_chiamata) "
        "VALUES (%s, %s, %s, %s, 37)",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    resp = _registra(scenario, a, **_personale(a.ids["sede1"], costo_dipendenti=1000))
    assert resp.status_code == 200, resp.text
    assert _riga(scenario, "SELECT costo_dipendenti::float, costo_personale_extra::float, "
                           "costo_personale_chiamata::float FROM public.margini_mensili "
                           "WHERE ristorante_id = %s AND anno = %s AND mese = %s",
                 a.ids["sede1"], OGGI.year, OGGI.month) == (1000.0, 0.0, 37.0)


def test_personale_gia_registrato_serve_il_precedente(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_dipendenti) "
        "VALUES (%s, %s, %s, %s, 8000)",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    resp = _registra(scenario, a, **_personale(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {"motivo": "valore_cambiato", "attuale": {"costo_dipendenti": 8000.0}}
    resp = _registra(scenario, a, **_personale(a.ids["sede1"], precedente={"costo_dipendenti": 8000}))
    assert resp.status_code == 200, resp.text
    assert _margini(scenario, a.ids["sede1"], OGGI.year, OGGI.month)[0] == 12000.0


@pytest.mark.parametrize("delta_mesi,importo", [(1, 12000), (-13, 12000), (0, 300_001), (0, 0)],
                         ids=["futuro", "troppo-indietro", "fuori-scala", "zero"])
def test_personale_non_valido_e_400(scenario, delta_mesi, importo):
    a = scenario.a
    indice = OGGI.year * 12 + OGGI.month - 1 + delta_mesi
    anno, mese = divmod(indice, 12)
    resp = _registra(scenario, a, **_personale(a.ids["sede1"], anno=anno, mese=mese + 1, costo_dipendenti=importo))
    assert resp.status_code == 400, resp.text
    assert _margini(scenario, a.ids["sede1"], anno, mese + 1) is None


# ─── Fatturato di un mese ─────────────────────────────────────────────────────
def _fatturato(sede, **extra):
    return {"tipo": "fatturato_mese", "ristorante_id": sede, "anno": MESE_SCORSO.year,
            "mese": MESE_SCORSO.month, "fatturato_iva10": 30000, "altri_ricavi_noiva": 2000, **extra}


def _modalita(sc, sede):
    return _riga(sc, "SELECT modalita, fatturato_iva10::float, altri_ricavi_noiva::float, coperti "
                     "FROM public.ricavi_modalita_mensile WHERE ristorante_id = %s AND anno = %s AND mese = %s",
                 sede, MESE_SCORSO.year, MESE_SCORSO.month)


def test_fatturato_su_mese_senza_giorni_lo_mette_a_totale(scenario):
    a = scenario.a
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _modalita(scenario, a.ids["sede1"]) == ("mensile", 30000.0, 2000.0, None)


def test_fatturato_su_mese_con_giorni_e_409(scenario):
    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], MESE_SCORSO.replace(day=10))
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["motivo"] == "mese_con_giorni"
    assert _modalita(scenario, a.ids["sede1"]) is None


def test_fatturato_su_mese_gia_a_totale_sostituisce_e_i_coperti_restano(scenario):
    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], MESE_SCORSO.replace(day=10))
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, fatturato_iva10, coperti) "
        "VALUES (%s, %s, %s, 'mensile', 25000, 900)",
        (a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
    )
    precedente = {"fatturato_iva10": 25000, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"], precedente=precedente))
    assert resp.status_code == 200, resp.text
    assert _modalita(scenario, a.ids["sede1"]) == ("mensile", 30000.0, 2000.0, 900)


def test_fatturato_su_riga_giornaliera_senza_giorni_la_porta_a_totale(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita) "
        "VALUES (%s, %s, %s, 'giornaliero')",
        (a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
    )
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _modalita(scenario, a.ids["sede1"])[:3] == ("mensile", 30000.0, 2000.0)


# ─── Fatturato scritto a mano in Margini (terza fonte) ────────────────────────
def _fatturato_a_mano(sc, anno, mese, iva10=76225):
    sc.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, fatturato_iva10) "
        "VALUES (%s, %s, %s, %s, %s)",
        (sc.a.ids["user_id"], sc.a.ids["sede1"], anno, mese, iva10),
    )


def test_fatturato_a_mano_in_margini_e_il_valore_da_mostrare_sulla_card(scenario):
    a = scenario.a
    _fatturato_a_mano(scenario, MESE_SCORSO.year, MESE_SCORSO.month)
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == {
        "motivo": "valore_cambiato",
        "attuale": {"fatturato_iva10": 76225.0, "altri_ricavi_noiva": 0.0, "fatturato_iva22": 0.0},
    }
    assert _modalita(scenario, a.ids["sede1"]) is None
    precedente = {"fatturato_iva10": 76225, "altri_ricavi_noiva": 0, "fatturato_iva22": 0}
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"], precedente=precedente))
    assert resp.status_code == 200, resp.text
    assert _modalita(scenario, a.ids["sede1"]) == ("mensile", 30000.0, 2000.0, None)


def test_giorno_su_mese_col_fatturato_a_mano_e_409_e_il_totale_resta(scenario):
    a = scenario.a
    _fatturato_a_mano(scenario, IERI.year, IERI.month)
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["motivo"] == "mese_a_totale"
    assert _giorno(scenario, a.ids["sede1"], IERI) is None
    assert _riga(scenario, "SELECT fatturato_iva10::float FROM public.margini_mensili WHERE ristorante_id = %s "
                           "AND anno = %s AND mese = %s", a.ids["sede1"], IERI.year, IERI.month)[0] == 76225.0


def test_giorno_su_mese_a_totale_con_importi_a_zero_resta_rifiutato(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita) "
        "VALUES (%s, %s, %s, 'mensile')",
        (a.ids["sede1"], IERI.year, IERI.month),
    )
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"]))
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["motivo"] == "mese_a_totale"


@pytest.mark.parametrize("delta_mesi,importo", [(1, 30000), (-13, 30000), (-1, 500_001), (-1, 0)],
                         ids=["futuro", "troppo-indietro", "fuori-scala", "zero"])
def test_fatturato_mese_non_valido_e_400(scenario, delta_mesi, importo):
    a = scenario.a
    anno, mese0 = divmod(OGGI.year * 12 + OGGI.month - 1 + delta_mesi, 12)
    corpo = {**_fatturato(a.ids["sede1"]), "anno": anno, "mese": mese0 + 1,
             "fatturato_iva10": importo, "altri_ricavi_noiva": 0}
    resp = _registra(scenario, a, **corpo)
    assert resp.status_code == 400, resp.text
    assert _riga(scenario, "SELECT count(*) FROM public.ricavi_modalita_mensile WHERE ristorante_id = %s",
                 a.ids["sede1"])[0] == 0


def test_il_tetto_del_fatturato_mese_ammette_il_limite(scenario):
    a = scenario.a
    resp = _registra(scenario, a, **_fatturato(a.ids["sede1"], fatturato_iva10=500_000, altri_ricavi_noiva=0))
    assert resp.status_code == 200, resp.text


# ─── updated_at e scritture concorrenti ───────────────────────────────────────
def test_l_aggiornamento_del_personale_rinfresca_updated_at(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_dipendenti, updated_at) "
        "VALUES (%s, %s, %s, %s, 0, '2020-01-01')",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    assert _registra(scenario, a, **_personale(a.ids["sede1"])).status_code == 200
    assert _riga(scenario, "SELECT updated_at > '2021-01-01' FROM public.margini_mensili WHERE ristorante_id = %s "
                           "AND anno = %s AND mese = %s", a.ids["sede1"], OGGI.year, OGGI.month)[0] is True


def test_l_aggiornamento_del_totale_rinfresca_updated_at(scenario):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, updated_at) "
        "VALUES (%s, %s, %s, 'giornaliero', '2020-01-01')",
        (a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
    )
    assert _registra(scenario, a, **_fatturato(a.ids["sede1"])).status_code == 200
    assert _riga(scenario, "SELECT updated_at > '2021-01-01' FROM public.ricavi_modalita_mensile "
                           "WHERE ristorante_id = %s", a.ids["sede1"])[0] is True


def test_valore_cambiato_fra_lettura_e_scrittura_non_viene_sovrascritto(scenario):
    """La corsa vera: la lettura ha visto 500, poi un'email di cassa scrive 700
    prima dell'update. L'update condizionato non trova la riga e risponde 409."""
    from fastapi import HTTPException

    from services.routers import assistente as A

    a = scenario.a
    _semina_giorno(scenario, a.ids["sede1"], IERI, iva10=500)
    letto = A.leggi_incasso_giorno(scenario.sb, a.ids["sede1"], IERI)
    scenario.conn.execute(
        "UPDATE public.ricavi_giornalieri SET fatturato_iva10 = 700 WHERE ristorante_id = %s AND data = %s",
        (a.ids["sede1"], IERI),
    )
    dettato = {"fatturato_iva10": 1800.0, "altri_ricavi_noiva": 540.0, "fatturato_iva22": 0.0}
    with pytest.raises(HTTPException) as exc:
        A._aggiorna(scenario.sb, "ricavi_giornalieri", letto, a.ids["sede1"], dettato, dettato,
                    lambda: A.leggi_incasso_giorno(scenario.sb, a.ids["sede1"], IERI))
    assert exc.value.status_code == 409
    assert exc.value.detail["attuale"]["fatturato_iva10"] == 700.0
    assert _giorno(scenario, a.ids["sede1"], IERI)[0] == 700.0


def _corsa(scenario, tabella, leggi, sql_intanto, params_intanto, dettato):
    """Legge, lascia che un altro scriva, poi prova l'update condizionato."""
    from fastapi import HTTPException

    from services.routers import assistente as A

    letto = leggi()
    scenario.conn.execute(sql_intanto, params_intanto)
    with pytest.raises(HTTPException) as exc:
        A._aggiorna(scenario.sb, tabella, letto, scenario.a.ids["sede1"], dettato, dettato, leggi)
    return exc.value


def test_totale_mensile_cambiato_fra_lettura_e_scrittura_e_409(scenario):
    from services.routers import assistente as A

    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, fatturato_iva10) "
        "VALUES (%s, %s, %s, 'mensile', 25000)",
        (a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
    )
    errore = _corsa(
        scenario, "ricavi_modalita_mensile",
        lambda: A.leggi_fatturato_mese(scenario.sb, a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
        "UPDATE public.ricavi_modalita_mensile SET fatturato_iva10 = 26000 WHERE ristorante_id = %s",
        (a.ids["sede1"],),
        {"fatturato_iva10": 30000.0, "altri_ricavi_noiva": 0.0, "fatturato_iva22": 0.0, "modalita": "mensile"},
    )
    assert errore.status_code == 409 and errore.detail["attuale"]["fatturato_iva10"] == 26000.0
    assert _modalita(scenario, a.ids["sede1"])[1] == 26000.0


def test_mese_passato_a_totale_fra_lettura_e_scrittura_e_409(scenario):
    from services.routers import assistente as A

    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, fatturato_iva10) "
        "VALUES (%s, %s, %s, 'giornaliero', 40000)",
        (a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
    )
    errore = _corsa(
        scenario, "ricavi_modalita_mensile",
        lambda: A.leggi_fatturato_mese(scenario.sb, a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
        "UPDATE public.ricavi_modalita_mensile SET modalita = 'mensile' WHERE ristorante_id = %s",
        (a.ids["sede1"],),
        {"fatturato_iva10": 30000.0, "altri_ricavi_noiva": 0.0, "fatturato_iva22": 0.0, "modalita": "mensile"},
    )
    assert errore.status_code == 409
    assert _modalita(scenario, a.ids["sede1"])[:2] == ("mensile", 40000.0)


def test_personale_cambiato_fra_lettura_e_scrittura_e_409(scenario):
    from services.routers import assistente as A

    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_dipendenti) "
        "VALUES (%s, %s, %s, %s, 8000)",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    errore = _corsa(
        scenario, "margini_mensili",
        lambda: A.leggi_personale(scenario.sb, a.ids["sede1"], OGGI.year, OGGI.month),
        "UPDATE public.margini_mensili SET costo_dipendenti = 9000 WHERE ristorante_id = %s",
        (a.ids["sede1"],),
        {"costo_dipendenti": 12000.0},
    )
    assert errore.status_code == 409 and errore.detail["attuale"] == {"costo_dipendenti": 9000.0}
    assert _margini(scenario, a.ids["sede1"], OGGI.year, OGGI.month)[0] == 9000.0


def test_personale_null_nel_db_si_aggiorna(scenario):
    """La condizione dell'update su un valore NULL e' `is null`, non `= null`
    (che non combacia mai e darebbe un 409 a vuoto)."""
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_dipendenti) "
        "VALUES (%s, %s, %s, %s, NULL)",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    resp = _registra(scenario, a, **_personale(a.ids["sede1"]))
    assert resp.status_code == 200, resp.text
    assert _margini(scenario, a.ids["sede1"], OGGI.year, OGGI.month)[0] == 12000.0


def test_il_personale_mostra_anche_l_extra_e_la_chiamata_per_la_card(scenario):
    from services.routers import assistente as A

    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_dipendenti, "
        "costo_personale_extra, costo_personale_chiamata) VALUES (%s, %s, %s, %s, 8000, 450.5, 37)",
        (a.ids["user_id"], a.ids["sede1"], OGGI.year, OGGI.month),
    )
    letto = A.leggi_personale(scenario.sb, a.ids["sede1"], OGGI.year, OGGI.month)
    assert letto.attuale == {"costo_dipendenti": 8000.0}
    assert letto.info == {"costo_personale_extra": 450.5, "costo_personale_chiamata": 37.0}


# ─── Dopo la scrittura ────────────────────────────────────────────────────────
def test_dopo_la_conferma_si_invalidano_kpi_briefing_e_campanella(scenario, worker, monkeypatch):
    from services import daily_briefing_service

    a = scenario.a
    chiamate = []
    monkeypatch.setattr(worker, "_invalidate_home_kpi_cache", lambda rid=None: chiamate.append(("kpi", rid)))
    monkeypatch.setattr(daily_briefing_service, "invalidate_today_briefing",
                        lambda uid, rid, sb=None: chiamate.append(("briefing", uid, rid)))
    worker._LIVE_SEGNALI_CACHE[a.ids["sede2"]] = (0, ["manca l'incasso"])
    try:
        resp = _registra(scenario, a, **_incasso(a.ids["sede2"]))
        assert resp.status_code == 200, resp.text
        assert ("kpi", a.ids["sede2"]) in chiamate
        assert ("briefing", a.ids["user_id"], a.ids["sede2"]) in chiamate
        assert a.ids["sede2"] not in worker._LIVE_SEGNALI_CACHE
    finally:
        worker._LIVE_SEGNALI_CACHE.pop(a.ids["sede2"], None)


def test_un_rifiuto_non_invalida_niente(scenario, worker, monkeypatch):
    a = scenario.a
    chiamate = []
    monkeypatch.setattr(worker, "_invalidate_home_kpi_cache", lambda rid=None: chiamate.append(rid))
    resp = _registra(scenario, a, **_incasso(a.ids["sede1"], giorno=OGGI + timedelta(days=2)))
    assert resp.status_code == 400
    assert chiamate == []
