"""Fase 3, step 2: l'assistente PROPONE le cifre dettate — su Postgres vero.

`/api/chat` gira per intero (quota, gate pagina, closure degli strumenti) con i
due clienti del test di isolamento; solo il modello e' finto: un loop che chiama
gli strumenti che il test gli dice e torna una risposta. Cio' che si prova:
- lo strumento non scrive niente, e la proposta esce in `ChatResponse.proposte`;
- la proposta, rimandata cosi' com'e' a POST /api/assistente/registra, passa:
  la card non promette mai cio' che la Conferma rifiuterebbe;
- senza divisione IVA, su un mese a totale, su un valore gia' uguale: nessuna card,
  e il modello riceve il motivo;
- solo con la pagina Margini, solo nella vista del locale.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401
from tests.test_sql_sotto_utenti import _cache_pulita, _crea_sotto_utente, _login  # noqa: F401

pytestmark = pytest.mark.sql

OGGI = datetime.now(tz=ZoneInfo("Europe/Rome")).date()
IERI = OGGI - timedelta(days=1)
MESE_SCORSO = OGGI.replace(day=1) - timedelta(days=1)
INCASSO = {"data": IERI.isoformat(), "iva10": 1800, "senza_iva": 540}


@pytest.fixture
def modello(worker, monkeypatch):
    """Il modello finto: esegue le chiamate in `chiamate` e registra cosa legge."""
    stato = {"chiamate": [], "letti": [], "tools": [], "reply": "Ecco la card: premi Conferma."}

    def _loop(client, messages, tools, esegui, log_ctx=""):
        stato["tools"] = [t["function"]["name"] for t in tools]
        stato["letti"] = [esegui(nome, dict(args)) for nome, args in stato["chiamate"]]
        return (stato["reply"], 1, 1)

    monkeypatch.setattr(worker, "_chat_loop_openai", _loop)
    monkeypatch.setattr(worker, "_build_chat_system_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr(worker, "_build_chat_system_prompt_catena", lambda *a, **k: "prompt")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return stato


def _chat(sc, chi=None, token=None, contesto="sede", card=True):
    corpo = {"messages": [{"role": "user", "content": "ieri 2.340"}], "contesto": contesto,
             "card_conferma": card}
    token = token or (chi or sc.a).token
    return sc.client.post("/api/chat", json=corpo,
                          headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER})


def _conferma(sc, proposta, chi=None):
    return sc.chiama(chi or sc.a, "POST", "/api/assistente/registra", json_=proposta)


def _giorno(sc, sede, giorno=IERI):
    return sc.conn.execute(
        "SELECT fatturato_iva10::float, altri_ricavi_noiva::float, coperti FROM public.ricavi_giornalieri "
        "WHERE ristorante_id = %s AND data = %s", (sede, giorno),
    ).fetchone()


# ─── La proposta e la sua Conferma ────────────────────────────────────────────
def test_la_proposta_non_scrive_e_la_conferma_la_accetta_com_e(scenario, modello):
    a = scenario.a
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    resp = _chat(scenario)
    assert resp.status_code == 200, resp.text
    [proposta] = resp.json()["proposte"]
    assert proposta["tipo"] == "incasso_giorno"
    assert proposta["ristorante_id"] == a.ids["sede1"]
    assert proposta["data"] == IERI.isoformat()
    assert (proposta["fatturato_iva10"], proposta["altri_ricavi_noiva"], proposta["fatturato_iva22"]) == (1800, 540, 0)
    assert proposta["precedente"] is None
    assert proposta["sede_nome"]
    assert modello["letti"][0]["proposta_pronta"] is True
    assert _giorno(scenario, a.ids["sede1"]) is None, "lo strumento ha scritto"

    conferma = _conferma(scenario, proposta)
    assert conferma.status_code == 200, conferma.text
    assert _giorno(scenario, a.ids["sede1"])[:2] == (1800.0, 540.0)


def test_valore_gia_presente_viaggia_nella_proposta_e_la_conferma_sostituisce(scenario, modello):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10, coperti) "
        "VALUES (%s, %s, %s, 700, 55)", (a.ids["user_id"], a.ids["sede1"], IERI),
    )
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    [proposta] = _chat(scenario).json()["proposte"]
    assert proposta["precedente"] == {"fatturato_iva10": 700.0, "altri_ricavi_noiva": 0.0, "fatturato_iva22": 0.0}
    assert modello["letti"][0]["valore_attuale"] == proposta["precedente"]
    assert _conferma(scenario, proposta).status_code == 200
    assert _giorno(scenario, a.ids["sede1"]) == (1800.0, 540.0, 55)


def test_personale_con_extra_e_la_sua_conferma(scenario, modello):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, costo_personale_extra) "
        "VALUES (%s, %s, %s, %s, 450)", (a.ids["user_id"], a.ids["sede1"], MESE_SCORSO.year, MESE_SCORSO.month),
    )
    modello["chiamate"] = [("proponi_personale", {"anno": MESE_SCORSO.year, "mese": MESE_SCORSO.month,
                                                  "importo": 12000})]
    [proposta] = _chat(scenario).json()["proposte"]
    assert (proposta["tipo"], proposta["costo_dipendenti"], proposta["costo_personale_extra"]) == \
        ("personale_mese", 12000, 450)
    assert modello["letti"][0]["extra_gia_registrati"] == 450
    assert _conferma(scenario, proposta).status_code == 200


def test_fatturato_del_mese_e_la_sua_conferma(scenario, modello):
    modello["chiamate"] = [("proponi_fatturato_mese", {"anno": MESE_SCORSO.year, "mese": MESE_SCORSO.month,
                                                       "iva10": 30000, "senza_iva": 2000, "iva22": 500})]
    [proposta] = _chat(scenario).json()["proposte"]
    assert proposta["tipo"] == "fatturato_mese" and proposta["precedente"] is None
    assert (proposta["fatturato_iva10"], proposta["altri_ricavi_noiva"], proposta["fatturato_iva22"]) == \
        (30000, 2000, 500), "il 22% detto dal cliente si perde"
    assert _conferma(scenario, proposta).status_code == 200


# ─── Quando non c'e' card ─────────────────────────────────────────────────────
@pytest.mark.parametrize("args", [
    {"data": IERI.isoformat(), "iva10": 2340},
    {"data": IERI.isoformat(), "senza_iva": 2340},
    {"data": IERI.isoformat(), "iva10": "duemila", "senza_iva": 0},
], ids=["manca-senza-iva", "manca-10", "non-numero"])
def test_senza_divisione_iva_il_modello_deve_chiedere(scenario, modello, args):
    modello["chiamate"] = [("proponi_incasso", args)]
    resp = _chat(scenario)
    assert resp.json()["proposte"] == []
    assert "Chiedi al cliente" in modello["letti"][0]["cosa_fare"]


def test_mese_a_totale_nessuna_card_e_il_motivo_al_modello(scenario, modello):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_modalita_mensile (ristorante_id, anno, mese, modalita, fatturato_iva10) "
        "VALUES (%s, %s, %s, 'mensile', 40000)", (a.ids["sede1"], IERI.year, IERI.month),
    )
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    assert _chat(scenario).json()["proposte"] == []
    assert "totale del mese" in modello["letti"][0]["errore"]


def test_fatturato_su_mese_con_giorni_nessuna_card(scenario, modello):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10) VALUES (%s, %s, %s, 500)",
        (a.ids["user_id"], a.ids["sede1"], MESE_SCORSO.replace(day=10)),
    )
    modello["chiamate"] = [("proponi_fatturato_mese", {"anno": MESE_SCORSO.year, "mese": MESE_SCORSO.month,
                                                       "iva10": 30000, "senza_iva": 0})]
    assert _chat(scenario).json()["proposte"] == []
    assert "giorno per giorno" in modello["letti"][0]["errore"]


def test_cifra_gia_registrata_uguale_nessuna_card(scenario, modello):
    a = scenario.a
    scenario.conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10, altri_ricavi_noiva) "
        "VALUES (%s, %s, %s, 1800, 540)", (a.ids["user_id"], a.ids["sede1"], IERI),
    )
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    assert _chat(scenario).json()["proposte"] == []
    assert modello["letti"][0]["gia_registrato"] is True


@pytest.mark.parametrize("args,nome", [
    ({**INCASSO, "data": (OGGI + timedelta(days=1)).isoformat()}, "proponi_incasso"),
    ({**INCASSO, "iva10": 150_000}, "proponi_incasso"),
    ({"anno": OGGI.year + 1, "mese": 1, "importo": 1000}, "proponi_personale"),
    ({"anno": OGGI.year, "mese": OGGI.month, "importo": 0}, "proponi_personale"),
], ids=["giorno-futuro", "fuori-scala", "mese-futuro", "personale-zero"])
def test_cifra_non_valida_nessuna_card_e_il_motivo(scenario, modello, args, nome):
    modello["chiamate"] = [(nome, args)]
    assert _chat(scenario).json()["proposte"] == []
    assert modello["letti"][0]["errore"]


def test_senza_risposta_del_modello_nessuna_card(scenario, modello):
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    modello["reply"] = None
    assert _chat(scenario).json()["proposte"] == []


# ─── Piu' proposte nella stessa risposta ──────────────────────────────────────
def test_la_stessa_cifra_proposta_due_volte_vale_l_ultima(scenario, modello):
    modello["chiamate"] = [("proponi_incasso", INCASSO), ("proponi_incasso", {**INCASSO, "iva10": 1900})]
    [proposta] = _chat(scenario).json()["proposte"]
    assert proposta["fatturato_iva10"] == 1900


def test_al_massimo_tre_card_per_risposta(scenario, modello):
    giorni = [(IERI - timedelta(days=i)).isoformat() for i in range(4)]
    modello["chiamate"] = [("proponi_incasso", {**INCASSO, "data": g}) for g in giorni]
    proposte = _chat(scenario).json()["proposte"]
    assert [p["data"] for p in proposte] == giorni[:3]
    assert "troppe" in modello["letti"][3]["errore"]


# ─── Chi puo' e dove ──────────────────────────────────────────────────────────
def test_senza_margini_gli_strumenti_non_ci_sono_e_non_si_eseguono(scenario, modello):
    _crea_sotto_utente(scenario.conn, scenario.a.ids["user_id"], "resp@proposte.test",
                       [scenario.a.ids["sede1"]], {"home": True, "margini": False, "analisi_fatture": True})
    token = _login(scenario, "resp@proposte.test").json()["token"]
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    resp = _chat(scenario, token=token)
    assert resp.status_code == 200, resp.text
    assert not {"proponi_incasso", "proponi_personale", "proponi_fatturato_mese"} & set(modello["tools"])
    assert resp.json()["proposte"] == []
    assert "non disponibile" in modello["letti"][0]["errore"]


def test_sotto_utente_con_margini_riceve_la_card_della_sua_sede(scenario, modello):
    _crea_sotto_utente(scenario.conn, scenario.a.ids["user_id"], "resp2@proposte.test",
                       [scenario.a.ids["sede2"]], {"home": True, "margini": True})
    token = _login(scenario, "resp2@proposte.test").json()["token"]
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    [proposta] = _chat(scenario, token=token).json()["proposte"]
    assert proposta["ristorante_id"] == scenario.a.ids["sede2"]


def test_in_catena_niente_strumenti_di_proposta(scenario, modello):
    modello["chiamate"] = []
    resp = _chat(scenario, contesto="catena")
    assert resp.status_code == 200, resp.text
    assert not [n for n in modello["tools"] if n.startswith("proponi")]
    assert resp.json()["proposte"] == []


def test_il_dispatcher_condiviso_con_la_catena_non_esegue_le_proposte(scenario, worker):
    esito = worker._chat_esegui_tool_sede(
        "proponi_incasso", INCASSO, user={"id": scenario.a.ids["user_id"]}, supabase_client=scenario.sb,
        authorization=None, ristorante_id=scenario.a.ids["sede1"], settore=None,
    )
    assert "solo nella Home" in esito["errore"]
    assert _giorno(scenario, scenario.a.ids["sede1"]) is None


def test_un_client_che_non_mostra_le_card_non_riceve_ne_strumenti_ne_proposte(scenario, modello):
    """/m legge solo `reply`: un «premi Conferma» senza card sarebbe falso."""
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    resp = _chat(scenario, card=False)
    assert resp.status_code == 200, resp.text
    assert not [n for n in modello["tools"] if n.startswith("proponi")]
    assert resp.json()["proposte"] == []
    assert "non disponibile" in modello["letti"][0]["errore"]
    assert _giorno(scenario, scenario.a.ids["sede1"]) is None


def test_la_richiesta_che_mostra_le_card_arriva_al_prompt(scenario, modello, worker, monkeypatch):
    visto = {}

    def _spia(*_a, **k):
        visto["cifre"] = k.get("cifre_dettate")
        return "prompt"

    monkeypatch.setattr(worker, "_build_chat_system_prompt", _spia)
    _chat(scenario, card=True)
    assert visto["cifre"] is True


def test_sede_attiva_spenta_nessuna_card(scenario, modello):
    """La sede della sessione e' letta da users.ultimo_ristorante_id senza
    ricontrollarla: se nel frattempo e' stata spenta, niente card."""
    a = scenario.a
    scenario.conn.execute("UPDATE public.users SET ultimo_ristorante_id = %s WHERE id = %s",
                          (a.ids["sede2"], a.ids["user_id"]))
    scenario.conn.execute("UPDATE public.ristoranti SET attivo = false WHERE id = %s", (a.ids["sede2"],))
    modello["chiamate"] = [("proponi_incasso", INCASSO)]
    resp = _chat(scenario)
    assert resp.status_code == 200, resp.text
    assert resp.json()["proposte"] == []
    assert modello["letti"][0]["errore"] == "Sede non trovata"
