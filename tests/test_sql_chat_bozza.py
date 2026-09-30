"""Fase 3, step 4: la bozza al fornitore nella chat — su Postgres vero.

`/api/chat` gira per intero con i due clienti del test di isolamento; solo il
modello e' finto (un loop che chiama gli strumenti indicati dal test). Cio' che si
prova:
- la bozza e' la stessa che il cliente trova in Prezzi → Score, sulla sua sede;
- i dati dell'altro cliente non entrano, anche con lo stesso fornitore;
- niente da trattare = nessuna card, e il modello riceve il motivo;
- solo con la pagina Prezzi, solo nella vista del locale, solo se il client
  mostra le card.
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401
from tests.test_sql_sotto_utenti import _cache_pulita, _crea_sotto_utente, _login  # noqa: F401

pytestmark = pytest.mark.sql

OGGI = date(2026, 9, 30)
MESI = ("2026-02-10", "2026-04-10", "2026-06-10", "2026-08-10")


@pytest.fixture
def modello(worker, monkeypatch):
    """Il modello finto: esegue le chiamate in `chiamate` e registra cosa legge."""
    stato = {"chiamate": [], "letti": [], "tools": [], "reply": "Ecco la bozza da copiare."}

    def _loop(client, messages, tools, esegui, log_ctx=""):
        stato["tools"] = [t["function"]["name"] for t in tools]
        stato["letti"] = [esegui(nome, dict(args)) for nome, args in stato["chiamate"]]
        return (stato["reply"], 1, 1)

    from services.routers import prezzi

    prezzi._invalidate_prezzi_rows_cache()
    monkeypatch.setattr(worker, "_chat_loop_openai", _loop)
    monkeypatch.setattr(worker, "_build_chat_system_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr(worker, "_build_chat_system_prompt_catena", lambda *a, **k: "prompt")
    monkeypatch.setattr(worker._assistente, "_oggi", lambda: OGGI)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    yield stato
    prezzi._invalidate_prezzi_rows_cache()


def _acquisti(sc, cliente, sede, fornitore, prodotto, prezzi_unitari):
    for i, (giorno, prezzo) in enumerate(zip(MESI, prezzi_unitari)):
        sc.conn.execute(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, data_documento, "
            "fornitore, descrizione, categoria, quantita, prezzo_unitario, totale_riga) "
            "VALUES (%s, %s, %s, 1, %s, %s, %s, 'PESCE', 10, %s, %s)",
            (cliente.ids["user_id"], sede, f"{fornitore}-{sede}-{i}.xml", giorno, fornitore, prodotto,
             prezzo, prezzo * 10),
        )


@pytest.fixture
def acquisti(scenario):
    a, b = scenario.a, scenario.b
    _acquisti(scenario, a, a.ids["sede1"], "ITTICA MARINA SRL", "SALMONE NORVEGESE", (18.9, 18.9, 18.9, 21.9))
    _acquisti(scenario, a, a.ids["sede1"], "PANIFICIO STABILE", "PANE CASERECCIO", (3.0, 3.0, 3.0, 3.0))
    _acquisti(scenario, a, a.ids["sede2"], "CASEIFICIO DUE SRL", "MOZZARELLA BUFALA", (9.0, 9.0, 9.0, 11.0))
    # L'altro cliente ha lo stesso fornitore con un altro prodotto in rincaro.
    _acquisti(scenario, b, b.ids["sede1"], "ITTICA MARINA SRL", "ORATA", (12.0, 12.0, 12.0, 15.0))
    return scenario


def _chat(sc, chi=None, token=None, contesto="sede", card=True):
    corpo = {"messages": [{"role": "user", "content": "preparami un messaggio per Ittica Marina"}],
             "contesto": contesto, "card_conferma": card}
    token = token or (chi or sc.a).token
    return sc.client.post("/api/chat", json=corpo,
                          headers={"Authorization": f"Bearer {token}", "X-Worker-Key": CHIAVE_WORKER})


# ─── La bozza ─────────────────────────────────────────────────────────────────
def test_la_bozza_e_quella_della_pagina_score(acquisti, modello):
    sc = acquisti
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "ittica marina"})]
    resp = _chat(sc)
    assert resp.status_code == 200, resp.text
    [bozza] = resp.json()["bozze"]
    assert bozza["fornitore"] == "ITTICA MARINA SRL"
    assert "Salmone Norvegese" in bozza["testo"]
    assert "Orata" not in bozza["testo"], "e' entrato un acquisto dell'altro cliente"
    assert bozza["sede_nome"]
    assert modello["letti"][0]["bozza_pronta"] is True
    assert any("Salmone Norvegese" in s for s in modello["letti"][0]["segnali"])

    pagina = sc.chiama(sc.a, "GET", "/api/prezzi/score-fornitori",
                       params={"data_da": "2026-01-01", "data_a": OGGI.isoformat()})
    assert pagina.status_code == 200, pagina.text
    [dalla_pagina] = [f for f in pagina.json()["fornitori"] if f["fornitore"] == "ITTICA MARINA SRL"]
    assert bozza["testo"] == dalla_pagina["bozza"]["testo"]
    assert bozza["periodo"] == dalla_pagina["periodo"]


def test_l_altro_cliente_ha_la_sua(acquisti, modello):
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    [bozza] = _chat(acquisti, chi=acquisti.b).json()["bozze"]
    assert "Orata" in bozza["testo"]
    assert "Salmone" not in bozza["testo"]


def test_il_periodo_parte_dal_primo_gennaio(acquisti, modello, worker, monkeypatch):
    """Il 2027 non ha acquisti: la bozza non pesca nell'anno prima."""
    monkeypatch.setattr(worker._assistente, "_oggi", lambda: date(2027, 3, 1))
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    assert _chat(acquisti).json()["bozze"] == []
    assert "nessuna fattura quest'anno" in modello["letti"][0]["errore"]


def test_niente_da_trattare_nessuna_card_e_il_motivo(acquisti, modello):
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Panificio"})]
    assert _chat(acquisti).json()["bozze"] == []
    letto = modello["letti"][0]
    assert letto["bozza"] == "nessuna" and letto["motivo"]
    assert "Non scrivere tu una bozza" in letto["cosa_fare"]


def test_fornitore_sconosciuto_il_modello_riceve_l_elenco(acquisti, modello):
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Macelleria Rossi"})]
    assert _chat(acquisti).json()["bozze"] == []
    letto = modello["letti"][0]
    assert "non trovato" in letto["errore"]
    assert "ITTICA MARINA SRL" in letto["fornitori"]
    assert "ORATA" not in str(letto)


def test_negozio_stessa_bozza(acquisti, modello, monkeypatch):
    """Regola 7: il testo non nomina ristorante ne' cucina, la pagina Prezzi e'
    aperta ai negozi con la stessa bozza — nessuna deviazione."""
    monkeypatch.setattr("services.settore_service.settore_utente", lambda *a, **k: "retail")
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    [bozza] = _chat(acquisti).json()["bozze"]
    assert "bozza_fornitore" in modello["tools"]
    assert "Salmone Norvegese" in bozza["testo"]


def test_senza_risposta_del_modello_nessuna_card(acquisti, modello):
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    modello["reply"] = None
    assert _chat(acquisti).json()["bozze"] == []


# ─── Piu' bozze nella stessa risposta (il modello le chiede, la closure le tiene) ─
def _finta(worker, monkeypatch):
    def _prepara(args, **_k):
        b = worker._assistente.BozzaFornitore(fornitore=args["fornitore"], testo=f"testo {args['n']}")
        return b, {"bozza_pronta": True}

    monkeypatch.setattr(worker._assistente, "prepara_bozza", _prepara)


def test_lo_stesso_fornitore_due_volte_vale_l_ultima(scenario, modello, worker, monkeypatch):
    _finta(worker, monkeypatch)
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica", "n": 1}),
                           ("bozza_fornitore", {"fornitore": "ittica ", "n": 2})]
    assert [b["testo"] for b in _chat(scenario).json()["bozze"]] == ["testo 2"]


def test_al_massimo_tre_bozze(scenario, modello, worker, monkeypatch):
    _finta(worker, monkeypatch)
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": f"F{i}", "n": i}) for i in range(4)]
    assert [b["fornitore"] for b in _chat(scenario).json()["bozze"]] == ["F0", "F1", "F2"]
    assert "troppe" in modello["letti"][3]["errore"]


# ─── Chi puo' e dove ──────────────────────────────────────────────────────────
def test_senza_prezzi_lo_strumento_non_c_e_e_non_si_esegue(acquisti, modello):
    _crea_sotto_utente(acquisti.conn, acquisti.a.ids["user_id"], "resp@bozza.test",
                       [acquisti.a.ids["sede1"]], {"home": True, "margini": True, "prezzi": False})
    token = _login(acquisti, "resp@bozza.test").json()["token"]
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    resp = _chat(acquisti, token=token)
    assert resp.status_code == 200, resp.text
    assert "bozza_fornitore" not in modello["tools"]
    assert resp.json()["bozze"] == []
    assert "non disponibile" in modello["letti"][0]["errore"]


def test_sotto_utente_con_prezzi_legge_la_sua_sede(acquisti, modello):
    _crea_sotto_utente(acquisti.conn, acquisti.a.ids["user_id"], "resp2@bozza.test",
                       [acquisti.a.ids["sede2"]], {"home": True, "prezzi": True})
    token = _login(acquisti, "resp2@bozza.test").json()["token"]
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Caseificio"}),
                           ("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    resp = _chat(acquisti, token=token)
    [bozza] = resp.json()["bozze"]
    assert "Mozzarella Bufala" in bozza["testo"]
    assert "non trovato" in modello["letti"][1]["errore"], "ha letto gli acquisti di un'altra sede"


def test_in_catena_niente_bozza(acquisti, modello):
    modello["chiamate"] = []
    resp = _chat(acquisti, contesto="catena")
    assert resp.status_code == 200, resp.text
    assert "bozza_fornitore" not in modello["tools"]
    assert resp.json()["bozze"] == []


def test_il_dispatcher_condiviso_con_la_catena_non_prepara_bozze(acquisti, worker):
    esito = worker._chat_esegui_tool_sede(
        "bozza_fornitore", {"fornitore": "Ittica Marina"}, user={"id": acquisti.a.ids["user_id"]},
        supabase_client=acquisti.sb, authorization=None, ristorante_id=acquisti.a.ids["sede1"], settore=None,
    )
    assert "solo nella Home" in esito["errore"]


def test_un_client_che_non_mostra_le_card_non_ha_lo_strumento(acquisti, modello):
    """/m legge solo `reply`: una bozza «nella card qui sotto» non la vedrebbe."""
    modello["chiamate"] = [("bozza_fornitore", {"fornitore": "Ittica Marina"})]
    resp = _chat(acquisti, card=False)
    assert resp.status_code == 200, resp.text
    assert "bozza_fornitore" not in modello["tools"]
    assert resp.json()["bozze"] == []
    assert "non disponibile" in modello["letti"][0]["errore"]
