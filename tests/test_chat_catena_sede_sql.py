"""Isolamento degli strumenti di sede nella chat di catena, su un Postgres vero
(step 6 dell'interfaccia, 29/9/2026).

Stessi due clienti di test_isolamento_per_risorsa.py (A e B, due sedi
ciascuno, ogni stringa di B marcata `_B_SEGRETO`), stesso ClientSQL che traduce
le catene del builder in SQL. Qui si chiama il dispatcher della chat di catena
come lo chiamerebbe il modello: con la sede di B per nome, per id, e con le
proprie — il controllo positivo, senza il quale un «vuoto» non prova niente.
"""
import json

import pytest

from tests.test_isolamento_per_risorsa import scenario, worker  # noqa: F401 - fixture

pytestmark = pytest.mark.sql


def _utente(cliente):
    return {"id": cliente.ids["user_id"], "email": f"{cliente.lettera.lower()}@isolamento.test"}


def _nome_sede(sc, rid):
    return sc.conn.execute("SELECT nome_ristorante FROM public.ristoranti WHERE id = %s", (rid,)).fetchone()[0]


def _esegui(worker, sc, cliente, nome, args):
    user = _utente(cliente)
    sedi = worker._chat_sedi_catena(user, sc.sb)
    return worker._chat_esegui_tool_catena(
        nome, args, user=user, supabase_client=sc.sb, authorization=None,
        settore="ristorazione", sedi=sedi,
        nomi_di_sede=frozenset(worker._CHAT_TOOLS_SEDE_IN_CATENA),
    )


def test_le_sedi_nominabili_sono_solo_quelle_dell_account(scenario, worker):  # noqa: F811
    a, b = scenario.a, scenario.b
    sedi = worker._chat_sedi_catena(_utente(a), scenario.sb)
    assert {s["id"] for s in sedi} == {a.ids["sede1"], a.ids["sede2"]}
    assert b.marker not in json.dumps(sedi)


@pytest.mark.parametrize("come", ["nome", "id"])
@pytest.mark.parametrize("strumento,args", [
    ("query_costi", {}),
    ("ultimi_acquisti", {"limite": 15}),
    ("query_appuntamenti", {"da": "2020-01-01", "a": "2030-12-31"}),
    ("trend_prezzo", {"prodotto": "PRODOTTO"}),
    ("confronto_prezzi", {"prodotto": "PRODOTTO"}),
])
def test_la_sede_dell_altro_cliente_non_si_raggiunge(scenario, worker, come, strumento, args):  # noqa: F811
    a, b = scenario.a, scenario.b
    sede_b = _nome_sede(scenario, b.ids["sede1"]) if come == "nome" else b.ids["sede1"]
    out = _esegui(worker, scenario, a, strumento, {**args, "sede": sede_b})
    testo = json.dumps(out, default=str)
    assert "errore" in out, f"{strumento} con la sede di B ({come}) non e' stato rifiutato: {testo[:400]}"
    assert b.marker not in testo and b.ids["sede1"] not in testo


@pytest.mark.parametrize("strumento,args,cosa", [
    ("query_costi", {}, "totale"),
    ("ultimi_acquisti", {"limite": 15}, "PRODOTTO"),
    ("query_appuntamenti", {"da": "2020-01-01", "a": "2030-12-31"}, "EVENTO"),
])
def test_controllo_la_propria_sede_trova_i_propri_dati(scenario, worker, strumento, args, cosa):  # noqa: F811
    a, b = scenario.a, scenario.b
    out = _esegui(worker, scenario, a, strumento, {**args, "sede": _nome_sede(scenario, a.ids["sede1"])})
    testo = json.dumps(out, default=str)
    assert "errore" not in out, testo[:400]
    assert out["sede"] == _nome_sede(scenario, a.ids["sede1"])
    assert cosa in testo, f"{strumento} sulla sede di A non ha trovato i dati di A: {testo[:400]}"
    assert b.marker not in testo


def test_gli_appuntamenti_con_una_sede_altrui_non_escono_neanche_chiamati_diretti(scenario, worker):  # noqa: F811
    """Il filtro user_id aggiunto il 29/9: anche se un id di sede altrui
    arrivasse fin qui, la query non restituisce gli appuntamenti di B."""
    a, b = scenario.a, scenario.b
    out = worker._chat_query_appuntamenti(_utente(a), scenario.sb, b.ids["sede1"], da="2020-01-01", a="2030-12-31")
    assert out["appuntamenti"] == [], out
    proprio = worker._chat_query_appuntamenti(_utente(a), scenario.sb, a.ids["sede1"], da="2020-01-01", a="2030-12-31")
    assert proprio["appuntamenti"], "controllo: gli appuntamenti di A sulla sede di A devono uscire"
