"""Ricavi «senza IVA»: il cliente li elimina e la sede non li accetta piu' (12/10/2026).

Su Postgres vero, con i due clienti del test di isolamento (A e B, due sedi
ciascuno). Si prova:
- la RPC `elimina_ricavi_noiva` toglie solo il no IVA: 10%, 22% e coperti
  restano al centesimo, il netto mensile scende esattamente del no IVA tolto,
  anche nei mesi senza giornalieri e nell'override mensile;
- l'altro cliente e l'altra sede restano intatti, e un id altrui ferma tutto;
- dopo l'esclusione nessun canale rimette il no IVA (upsert stile Passbi,
  modalita' mensile, POST diretto su margini_mensili), finche' non si riattiva.
"""
from __future__ import annotations

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401

pytestmark = pytest.mark.sql


def _uno(sc, query, *params):
    return sc.conn.execute(query, params).fetchone()


def _giorno(sc, sede, data):
    return _uno(
        sc,
        "SELECT fatturato_iva10::float, fatturato_iva22::float, altri_ricavi_noiva::float, coperti "
        "FROM public.ricavi_giornalieri WHERE ristorante_id = %s AND data = %s",
        sede, data,
    )


def _mese(sc, sede, anno, mese):
    return _uno(
        sc,
        "SELECT fatturato_iva10::float, fatturato_iva22::float, altri_ricavi_noiva::float, "
        "fatturato_netto::float, primo_margine::float, mol::float "
        "FROM public.margini_mensili WHERE ristorante_id = %s AND anno = %s AND mese = %s",
        sede, anno, mese,
    )


def _upsert_giorno(sc, user, sede, data, iva10, iva22, noiva, coperti=None):
    """Lo stesso upsert di Passbi: tutte e tre le colonne, on conflict (sede, data)."""
    sc.conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10, "
        "fatturato_iva22, altri_ricavi_noiva, coperti, source) VALUES (%s, %s, %s, %s, %s, %s, %s, 'email') "
        "ON CONFLICT (ristorante_id, data) DO UPDATE SET fatturato_iva10 = EXCLUDED.fatturato_iva10, "
        "fatturato_iva22 = EXCLUDED.fatturato_iva22, altri_ricavi_noiva = EXCLUDED.altri_ricavi_noiva, "
        "coperti = EXCLUDED.coperti, source = EXCLUDED.source",
        (user, sede, data, iva10, iva22, noiva, coperti),
    )


def _elimina(sc, user, sedi):
    return sc.conn.execute(
        "SELECT ristorante_id::text, giorni, mesi, euro::float FROM public.elimina_ricavi_noiva(%s, %s::uuid[])",
        (user, list(sedi)),
    ).fetchall()


def _escluso(sc, sede):
    return _uno(sc, "SELECT escludi_ricavi_noiva FROM public.ristoranti WHERE id = %s", sede)[0]


@pytest.fixture
def dati(scenario):
    """Agosto 2026 per la sede1 di A e di B: un giorno misto, un giorno di solo
    no IVA, un giorno senza no IVA. Luglio 2026 in margini_mensili senza
    giornalieri (no IVA scritto a mano), settembre in modalita' mensile."""
    sc = scenario
    for chi in (sc.a, sc.b):
        u, s1, s2 = chi.ids["user_id"], chi.ids["sede1"], chi.ids["sede2"]
        _upsert_giorno(sc, u, s1, "2026-08-01", 1100, 1220, 300, 50)
        _upsert_giorno(sc, u, s1, "2026-08-02", 0, 0, 200)
        _upsert_giorno(sc, u, s1, "2026-08-03", 550, 0, 0, 20)
        _upsert_giorno(sc, u, s2, "2026-08-01", 220, 0, 70)
        sc.conn.execute(
            "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, fatturato_iva10, "
            "fatturato_iva22, altri_ricavi_noiva, fatturato_netto, costi_fb_auto, costo_dipendenti, "
            "primo_margine, mol) VALUES (%s, %s, 2026, 7, 2200, 0, 400, 2400, 600, 500, 1800, 1300)",
            (u, s1),
        )
        sc.conn.execute(
            "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, "
            "fatturato_iva10, fatturato_iva22, altri_ricavi_noiva) VALUES (%s, 2026, 9, 'mensile', 11000, 0, 900)",
            (s1,),
        )
    return sc


def test_elimina_toglie_solo_il_no_iva_e_il_netto_scende_esattamente(dati):
    sc, a = dati, dati.a
    s1 = a.ids["sede1"]
    netto_prima = _mese(sc, s1, 2026, 8)[3]

    esito = _elimina(sc, a.ids["user_id"], [s1])

    assert esito == [(s1, 2, 3, 500.0)]
    assert _giorno(sc, s1, "2026-08-01") == (1100.0, 1220.0, 0.0, 50)
    assert _giorno(sc, s1, "2026-08-02") is None
    assert _giorno(sc, s1, "2026-08-03") == (550.0, 0.0, 0.0, 20)
    agosto = _mese(sc, s1, 2026, 8)
    assert agosto[:3] == (1650.0, 1220.0, 0.0)
    assert agosto[3] == pytest.approx(netto_prima - 500, abs=0.01)
    assert _escluso(sc, s1) is True


def test_mese_senza_giornalieri_ricalcola_netto_primo_margine_e_mol(dati):
    sc, a = dati, dati.a
    _elimina(sc, a.ids["user_id"], [a.ids["sede1"]])
    # 2200/1,10 = 2000 di netto; 600 di food -> 1400; 500 di personale -> 900.
    assert _mese(sc, a.ids["sede1"], 2026, 7) == (2200.0, 0.0, 0.0, 2000.0, 1400.0, 900.0)


def test_override_mensile_perde_il_no_iva_e_tiene_il_resto(dati):
    sc, a = dati, dati.a
    _elimina(sc, a.ids["user_id"], [a.ids["sede1"]])
    riga = _uno(
        sc,
        "SELECT modalita, fatturato_iva10::float, altri_ricavi_noiva::float FROM public.ricavi_modalita_mensile "
        "WHERE ristorante_id = %s AND anno = 2026 AND mese = 9",
        a.ids["sede1"],
    )
    assert riga == ("mensile", 11000.0, 0.0)


def test_l_altra_sede_e_l_altro_cliente_restano_intatti(dati):
    sc, a, b = dati, dati.a, dati.b
    prima_b = sc.impronta(b)
    _elimina(sc, a.ids["user_id"], [a.ids["sede1"]])
    assert sc.impronta(b) == prima_b
    assert _giorno(sc, a.ids["sede2"], "2026-08-01") == (220.0, 0.0, 70.0, None)
    assert _escluso(sc, a.ids["sede2"]) is False


def test_una_sede_altrui_ferma_tutto_anche_le_proprie(dati):
    sc, a, b = dati, dati.a, dati.b
    import psycopg

    sc.conn.execute("SAVEPOINT prima")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _elimina(sc, a.ids["user_id"], [a.ids["sede1"], b.ids["sede1"]])
    sc.conn.execute("ROLLBACK TO SAVEPOINT prima")
    assert _giorno(sc, a.ids["sede1"], "2026-08-01")[2] == 300.0
    assert _giorno(sc, b.ids["sede1"], "2026-08-01")[2] == 300.0
    assert _escluso(sc, a.ids["sede1"]) is False


def test_dopo_l_esclusione_passbi_non_rimette_il_no_iva(dati):
    sc, a = dati, dati.a
    u, s1 = a.ids["user_id"], a.ids["sede1"]
    _elimina(sc, u, [s1])

    _upsert_giorno(sc, u, s1, "2026-08-01", 1100, 1220, 300, 50)
    _upsert_giorno(sc, u, s1, "2026-08-04", 330, 0, 90, 10)
    _upsert_giorno(sc, u, s1, "2026-08-05", 0, 0, 120)

    assert _giorno(sc, s1, "2026-08-01") == (1100.0, 1220.0, 0.0, 50)
    assert _giorno(sc, s1, "2026-08-04") == (330.0, 0.0, 0.0, 10)
    assert _giorno(sc, s1, "2026-08-05") is None
    assert _mese(sc, s1, 2026, 8)[2] == 0.0


def test_giorno_esistente_non_viene_svuotato_da_un_file_di_solo_no_iva(dati):
    """Il BEFORE INSERT salta la riga proposta: l'upsert non tocca il giorno che c'e'."""
    sc, a = dati, dati.a
    u, s1 = a.ids["user_id"], a.ids["sede1"]
    _elimina(sc, u, [s1])
    _upsert_giorno(sc, u, s1, "2026-08-03", 0, 0, 80)
    assert _giorno(sc, s1, "2026-08-03") == (550.0, 0.0, 0.0, 20)


def test_dopo_l_esclusione_modalita_mensile_e_margini_diretti_scrivono_zero(dati):
    sc, a = dati, dati.a
    u, s1 = a.ids["user_id"], a.ids["sede1"]
    _elimina(sc, u, [s1])
    sc.conn.execute(
        "UPDATE public.ricavi_modalita_mensile SET altri_ricavi_noiva = 700 "
        "WHERE ristorante_id = %s AND anno = 2026 AND mese = 9",
        (s1,),
    )
    assert _uno(
        sc,
        "SELECT altri_ricavi_noiva::float FROM public.ricavi_modalita_mensile "
        "WHERE ristorante_id = %s AND anno = 2026 AND mese = 9",
        s1,
    )[0] == 0.0
    # Come POST /api/margini: netto, primo margine e MOL calcolati col no IVA dentro.
    sc.conn.execute(
        "UPDATE public.margini_mensili SET altri_ricavi_noiva = 400, fatturato_netto = 2400, "
        "primo_margine = 1800, mol = 1300 WHERE ristorante_id = %s AND anno = 2026 AND mese = 7",
        (s1,),
    )
    assert _mese(sc, s1, 2026, 7) == (2200.0, 0.0, 0.0, 2000.0, 1400.0, 900.0)


def test_la_sede_non_esclusa_continua_a_ricevere_il_no_iva(dati):
    sc, a = dati, dati.a
    u = a.ids["user_id"]
    _elimina(sc, u, [a.ids["sede1"]])
    _upsert_giorno(sc, u, a.ids["sede2"], "2026-08-04", 100, 0, 45)
    assert _giorno(sc, a.ids["sede2"], "2026-08-04")[2] == 45.0


def test_riattivata_la_sede_il_no_iva_rientra(dati):
    sc, a = dati, dati.a
    u, s1 = a.ids["user_id"], a.ids["sede1"]
    _elimina(sc, u, [s1])
    sc.conn.execute("UPDATE public.ristoranti SET escludi_ricavi_noiva = false WHERE id = %s", (s1,))
    _upsert_giorno(sc, u, s1, "2026-08-01", 1100, 1220, 300, 50)
    assert _giorno(sc, s1, "2026-08-01")[2] == 300.0
    assert _mese(sc, s1, 2026, 8)[2] == 300.0


def test_due_chiamate_nella_stessa_transazione(dati):
    """Le tabelle temporanee si ricreano: la seconda chiamata non si rompe e non tocca piu' niente."""
    sc, a = dati, dati.a
    _elimina(sc, a.ids["user_id"], [a.ids["sede1"]])
    assert _elimina(sc, a.ids["user_id"], [a.ids["sede1"]]) == [(a.ids["sede1"], 0, 0, 0.0)]


def test_la_rpc_non_e_eseguibile_da_anon_e_authenticated(sql):
    righe = sql(
        "SELECT r.rolname, has_function_privilege(r.rolname, 'public.elimina_ricavi_noiva(uuid, uuid[])', 'EXECUTE') "
        "FROM pg_roles r WHERE r.rolname IN ('anon', 'authenticated', 'service_role') ORDER BY 1"
    )
    assert righe == [("anon", False), ("authenticated", False), ("service_role", True)]


# ─── Gli endpoint del worker ──────────────────────────────────────────────────
URL_STATO = "/api/account/ricavi-noiva"
URL_ELIMINA = "/api/account/ricavi-noiva/elimina"
URL_RIATTIVA = "/api/account/ricavi-noiva/riattiva"


def test_lo_stato_elenca_solo_le_proprie_sedi_con_il_no_iva_presente(dati):
    sc, a = dati, dati.a
    resp = sc.chiama(a, "GET", URL_STATO)
    assert resp.status_code == 200
    sedi = {s["id"]: s for s in resp.json()["sedi"]}
    assert set(sedi) == {a.ids["sede1"], a.ids["sede2"]}
    # Agosto 500 (300 + 200 dai giornalieri) + luglio 400 scritto a mano +
    # settembre 900 dal totale mensile, che nei Margini vince sull'aggregato.
    assert sedi[a.ids["sede1"]]["euro_noiva"] == 1800.0
    assert sedi[a.ids["sede2"]]["euro_noiva"] == 70.0
    assert not any(s["escluso"] for s in sedi.values())


def test_elimina_dall_endpoint_scrive_e_svuota_le_cache(dati, monkeypatch):
    sc, a = dati, dati.a
    import services.daily_briefing_service as dbs
    import services.fastapi_worker as fw

    briefing, kpi = [], []
    monkeypatch.setattr(dbs, "invalidate_today_briefing", lambda u, r, sb: briefing.append(r))
    monkeypatch.setattr(fw, "_invalidate_home_kpi_cache", lambda r=None: kpi.append(r))
    fw._LIVE_SEGNALI_CACHE[a.ids["sede1"]] = (0, ["vecchio"])
    sc.conn.execute(
        "INSERT INTO public.gruppo_segnali_state (user_id, generated_for_date) VALUES (%s, current_date)",
        (a.ids["user_id"],),
    )

    resp = sc.chiama(a, "POST", URL_ELIMINA, json_={"ristorante_ids": [a.ids["sede1"]], "conferma": "elimina"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["sedi"] == [{"id": a.ids["sede1"], "giorni": 2, "mesi": 3, "euro": 500.0}]
    assert _giorno(sc, a.ids["sede1"], "2026-08-01")[2] == 0.0
    assert briefing == [a.ids["sede1"]] and kpi == [a.ids["sede1"]]
    assert a.ids["sede1"] not in fw._LIVE_SEGNALI_CACHE
    assert _uno(sc, "SELECT count(*) FROM public.gruppo_segnali_state WHERE user_id = %s", a.ids["user_id"])[0] == 0
    stato = {s["id"]: s for s in sc.chiama(a, "GET", URL_STATO).json()["sedi"]}
    assert stato[a.ids["sede1"]]["escluso"] is True
    assert stato[a.ids["sede1"]]["euro_noiva"] == 0.0


def test_senza_la_parola_elimina_non_tocca_niente(dati):
    sc, a = dati, dati.a
    for conferma in (None, "", "SVUOTA", "elimina tutto"):
        resp = sc.chiama(a, "POST", URL_ELIMINA, json_={"ristorante_ids": [a.ids["sede1"]], "conferma": conferma})
        assert resp.status_code == 400, conferma
    assert _giorno(sc, a.ids["sede1"], "2026-08-01")[2] == 300.0
    assert _escluso(sc, a.ids["sede1"]) is False


def test_sede_altrui_o_nessuna_sede_non_tocca_niente(dati):
    sc, a, b = dati, dati.a, dati.b
    prima_b = sc.impronta(b)
    resp = sc.chiama(a, "POST", URL_ELIMINA,
                     json_={"ristorante_ids": [a.ids["sede1"], b.ids["sede1"]], "conferma": "ELIMINA"})
    assert resp.status_code == 404
    assert sc.chiama(a, "POST", URL_ELIMINA, json_={"ristorante_ids": [], "conferma": "ELIMINA"}).status_code == 400
    assert sc.chiama(a, "POST", URL_RIATTIVA, json_={"ristorante_ids": [b.ids["sede1"]]}).status_code == 404
    assert sc.impronta(b) == prima_b
    assert _giorno(sc, a.ids["sede1"], "2026-08-01")[2] == 300.0


def test_riattiva_rimette_il_campo_e_i_caricamenti_futuri(dati):
    sc, a = dati, dati.a
    s1 = a.ids["sede1"]
    sc.chiama(a, "POST", URL_ELIMINA, json_={"ristorante_ids": [s1], "conferma": "ELIMINA"})
    periodo = {"data_da": "2026-08-01", "data_a": "2026-08-31"}
    assert sc.chiama(a, "GET", "/api/ricavi/giornalieri", params=periodo).json()["noiva_escluso"] is True

    assert sc.chiama(a, "POST", URL_RIATTIVA, json_={"ristorante_ids": [s1]}).status_code == 200

    assert _escluso(sc, s1) is False
    assert sc.chiama(a, "GET", "/api/ricavi/giornalieri", params=periodo).json()["noiva_escluso"] is False
    _upsert_giorno(sc, a.ids["user_id"], s1, "2026-08-01", 1100, 1220, 300, 50)
    assert _giorno(sc, s1, "2026-08-01")[2] == 300.0


def test_inserimento_a_mano_su_sede_esclusa_salva_10_e_22_e_azzera_il_no_iva(dati):
    sc, a = dati, dati.a
    s1 = a.ids["sede1"]
    sc.chiama(a, "POST", URL_ELIMINA, json_={"ristorante_ids": [s1], "conferma": "ELIMINA"})
    resp = sc.chiama(a, "POST", "/api/ricavi/giornalieri", json_={
        "data": "2026-08-10", "fatturato_iva10": 440, "fatturato_iva22": 0, "altri_ricavi_noiva": 60,
    })
    assert resp.status_code == 200, resp.text
    assert _giorno(sc, s1, "2026-08-10")[:3] == (440.0, 0.0, 0.0)


def test_un_sotto_utente_non_vede_ne_elimina(dati):
    from tests.test_sql_sotto_utenti import _crea_sotto_utente, _login

    sc, a = dati, dati.a
    _crea_sotto_utente(sc.conn, a.ids["user_id"], "tutto@isolamento.test",
                       [a.ids["sede1"], a.ids["sede2"]],
                       {p: True for p in ("home", "margini", "analisi_fatture", "catena")})
    token = _login(sc, "tutto@isolamento.test").json()["token"]
    intestazioni = {"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER}
    assert sc.client.get(URL_STATO, headers=intestazioni).status_code == 403
    resp = sc.client.post(URL_ELIMINA, headers=intestazioni,
                          json={"ristorante_ids": [a.ids["sede1"]], "conferma": "ELIMINA"})
    assert resp.status_code == 403
    assert _giorno(sc, a.ids["sede1"], "2026-08-01")[2] == 300.0


# ─── L'assistente su una sede esclusa ────────────────────────────────────────
def _escludi(sc, chi):
    resp = sc.chiama(chi, "POST", URL_ELIMINA, json_={"ristorante_ids": [chi.ids["sede1"]], "conferma": "ELIMINA"})
    assert resp.status_code == 200, resp.text


def _ieri():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    return (datetime.now(tz=ZoneInfo("Europe/Rome")).date() - timedelta(days=1))


def test_l_assistente_non_registra_senza_iva_su_sede_esclusa(dati):
    """La card con no IVA > 0 (anche preparata prima dell'esclusione) e' rifiutata
    con un motivo chiaro: prima rispondeva «registrato» e il DB aveva 0."""
    sc, a = dati, dati.a
    _escludi(sc, a)
    giorno = _ieri().isoformat()
    corpo = {"tipo": "incasso_giorno", "ristorante_id": a.ids["sede1"], "data": giorno,
             "fatturato_iva10": 1800, "altri_ricavi_noiva": 540}
    resp = sc.chiama(a, "POST", "/api/assistente/registra", json_=corpo)
    assert resp.status_code == 400
    assert "esclusi" in resp.json()["detail"]
    assert _giorno(sc, a.ids["sede1"], giorno) is None

    resp = sc.chiama(a, "POST", "/api/assistente/registra", json_={**corpo, "altri_ricavi_noiva": 0})
    assert resp.status_code == 200, resp.text
    assert _giorno(sc, a.ids["sede1"], giorno)[:3] == (1800.0, 0.0, 0.0)


def test_l_assistente_su_sede_esclusa_non_chiede_ne_propone_il_senza_iva(dati):
    from services.routers import assistente as A

    sc, a = dati, dati.a
    _escludi(sc, a)
    user = {"id": a.ids["user_id"], "email": "a@isolamento.test"}
    oggi_meno_uno = _ieri().isoformat()

    proposta, al_modello = A.proponi("proponi_incasso", {"data": oggi_meno_uno, "iva10": 1800},
                                     user=user, sb=sc.sb, ristorante_id=a.ids["sede1"], sede_nome="S1")
    assert proposta is not None, al_modello
    assert proposta.altri_ricavi_noiva == 0.0 and proposta.fatturato_iva10 == 1800.0

    proposta, al_modello = A.proponi("proponi_incasso", {"data": oggi_meno_uno, "iva10": 1800, "senza_iva": 540},
                                     user=user, sb=sc.sb, ristorante_id=a.ids["sede1"], sede_nome="S1")
    assert proposta is None
    assert "esclusi" in al_modello["cosa_fare"]

    # Senza il 10%: la domanda al cliente e' su 10% e 22%, non sul senza IVA.
    _proposta, al_modello = A.proponi("proponi_incasso", {"data": oggi_meno_uno, "iva22": 500},
                                      user=user, sb=sc.sb, ristorante_id=a.ids["sede1"], sede_nome="S1")
    assert al_modello["errore"] == "divisione IVA mancante"
    assert "al 22%" in al_modello["cosa_fare"]
    assert "quanto senza IVA" not in al_modello["cosa_fare"]


def test_l_assistente_non_registra_il_totale_del_mese_con_senza_iva_su_sede_esclusa(dati):
    sc, a = dati, dati.a
    _escludi(sc, a)
    mese_scorso = _ieri().replace(day=1)
    from datetime import timedelta

    mese_scorso = mese_scorso - timedelta(days=1)
    corpo = {"tipo": "fatturato_mese", "ristorante_id": a.ids["sede1"], "anno": mese_scorso.year,
             "mese": mese_scorso.month, "fatturato_iva10": 30000, "altri_ricavi_noiva": 2000}
    resp = sc.chiama(a, "POST", "/api/assistente/registra", json_=corpo)
    assert resp.status_code == 400
    assert "esclusi" in resp.json()["detail"]


def test_sulla_sede_non_esclusa_l_assistente_chiede_ancora_il_senza_iva(dati):
    from services.routers import assistente as A

    sc, a = dati, dati.a
    user = {"id": a.ids["user_id"], "email": "a@isolamento.test"}
    proposta, al_modello = A.proponi("proponi_incasso", {"data": _ieri().isoformat(), "iva10": 1800},
                                     user=user, sb=sc.sb, ristorante_id=a.ids["sede1"], sede_nome="S1")
    assert proposta is None
    assert al_modello["errore"] == "divisione IVA mancante"


def test_giorno_di_solo_senza_iva_a_mano_su_sede_esclusa_spiega_perche(dati):
    """Prima era un 500 «Salvataggio fallito»: il trigger salta la riga di proposito."""
    sc, a = dati, dati.a
    _escludi(sc, a)
    resp = sc.chiama(a, "POST", "/api/ricavi/giornalieri", json_={
        "data": "2026-08-20", "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 90,
    })
    assert resp.status_code == 400
    assert "esclusi" in resp.json()["detail"]
    assert _giorno(sc, a.ids["sede1"], "2026-08-20") is None
