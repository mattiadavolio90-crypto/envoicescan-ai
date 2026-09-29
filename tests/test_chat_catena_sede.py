"""In vista catena l'assistente usa anche gli strumenti di UNA sede
(step 6 dell'interfaccia, 29/9/2026).

Prima la chat di catena aveva solo i quattro strumenti di gruppo e, per una
domanda su un locale, diceva «apri quel punto vendita». Ora offre anche quelli
di sede con un argomento `sede` obbligatorio.

Il punto delicato e' l'isolamento: `sede` la sceglie il MODELLO, cioe' testo
che il cliente puo' influenzare. Si accetta solo una sede dell'account (attiva,
non tecnica; per un sotto-utente una delle sue), e alle query va l'id della
riga letta col filtro user_id, mai un valore preso dagli argomenti. La prova
su un Postgres vero, con due clienti, sta in test_chat_catena_sede_sql.py.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw

SEDI = [
    {"id": "rid-1", "nome": "SUSHILAND CASATI 14"},
    {"id": "rid-2", "nome": "SUSHILAND NAVIGLI"},
    {"id": "rid-3", "nome": "SUSHILAND PORTA ROMANA"},
]
USER = {"id": "u-1", "email": "u@x.it", "nome_ristorante": "SUSHILAND CASATI 14"}


# ─── Quale sede ha nominato il modello ──────────────────────────────────────


@pytest.mark.parametrize("richiesta,atteso", [
    ("SUSHILAND NAVIGLI", "rid-2"),
    ("sushiland   navigli ", "rid-2"),
    ("rid-3", "rid-3"),
    ("Navigli", "rid-2"),
    ("porta romana", "rid-3"),
])
def test_sede_riconosciuta(richiesta, atteso):
    assert fw._chat_risolvi_sede(richiesta, SEDI)["id"] == atteso


@pytest.mark.parametrize("richiesta", [
    None, "", "   ",
    "SUSHILAND",          # pezzo comune a tutte: ambiguo
    "na",                 # troppo corto per un pezzo di nome
    "rid-99",             # un id che non e' fra le sedi dell'account
    "MILANO CENTRO",      # un nome che non c'e'
])
def test_sede_non_riconosciuta(richiesta):
    assert fw._chat_risolvi_sede(richiesta, SEDI) is None


def test_due_sedi_con_lo_stesso_nome_sono_ambigue():
    doppie = [{"id": "a", "nome": "CENTRO"}, {"id": "b", "nome": "centro"}]
    assert fw._chat_risolvi_sede("Centro", doppie) is None


# ─── Quali sedi si possono nominare ─────────────────────────────────────────


def _sb_sedi(righe):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "order"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=righe)
    sb.table.return_value = q
    return sb, q


def test_le_sedi_si_leggono_solo_dell_account_attive_e_non_tecniche():
    sb, q = _sb_sedi([{"id": "rid-1", "nome_ristorante": "A"}, {"id": "rid-2", "nome_ristorante": " "}])
    out = fw._chat_sedi_catena(USER, sb)
    sb.table.assert_called_with("ristoranti")
    filtri = {c.args for c in q.eq.call_args_list}
    assert ("user_id", "u-1") in filtri
    assert ("attivo", True) in filtri
    assert ("sede_tecnica", False) in filtri
    assert out == [{"id": "rid-1", "nome": "A"}], "una sede senza nome non si puo' nominare"


def test_un_sotto_utente_nomina_solo_le_sue_sedi(monkeypatch):
    sb, _ = _sb_sedi([{"id": "rid-1", "nome_ristorante": "A"}, {"id": "rid-2", "nome_ristorante": "B"}])
    monkeypatch.setattr(fw._su, "e_sotto_utente", lambda u: True)
    monkeypatch.setattr(fw._su, "contesto", lambda u: {"sedi_operative": ["rid-2"]})
    assert fw._chat_sedi_catena(USER, sb) == [{"id": "rid-2", "nome": "B"}]


# ─── Quali strumenti di sede si offrono in catena ───────────────────────────


def _nomi(tools):
    return {t["function"]["name"] for t in tools}


def test_in_catena_gli_strumenti_di_sede_hanno_la_sede_obbligatoria():
    tools = fw._chat_tools_sede_per_catena(USER, "ristorazione", SEDI)
    assert _nomi(tools) == set(fw._CHAT_TOOLS_SEDE_IN_CATENA)
    for t in tools:
        p = t["function"]["parameters"]
        assert "sede" in p["required"], t["function"]["name"]
        assert p["properties"]["sede"]["enum"] == [s["nome"] for s in SEDI]
        assert t["function"]["description"].startswith("Dati di UN SOLO punto vendita")


def test_i_coperti_non_si_offrono_in_catena():
    """query_coperti legge la sede dal token: in catena direbbe i coperti della
    sede attiva spacciandoli per quelli nominati."""
    assert "query_coperti" not in _nomi(fw._chat_tools_sede_per_catena(USER, "ristorazione", SEDI))


def test_la_lista_della_sede_non_viene_toccata():
    fw._chat_tools_sede_per_catena(USER, "ristorazione", SEDI)
    for t in fw._CHAT_TOOLS_SEDE:
        assert "sede" not in t["function"]["parameters"].get("properties", {})


def test_in_catena_valgono_i_permessi_di_pagina():
    senza_scadenze = dict(USER, pagine_abilitate={"analisi_fatture": True, "margini": True,
                                                  "prezzi": True, "agenda": True, "scadenziario": False})
    nomi = _nomi(fw._chat_tools_sede_per_catena(senza_scadenze, "ristorazione", SEDI))
    assert "query_scadenze" not in nomi and "query_costi" in nomi


def test_senza_sedi_nessuno_strumento_di_sede():
    assert fw._chat_tools_sede_per_catena(USER, "ristorazione", []) == []


# ─── L'esecuzione ───────────────────────────────────────────────────────────


def _catena(monkeypatch, nome, args, nomi_di_sede=None):
    visti = {"sede": [], "gruppo": []}

    def _sede(n, a, **kw):
        visti["sede"].append((n, a, kw))
        return {"totale": 1}

    monkeypatch.setattr(fw, "_chat_esegui_tool_sede", _sede)
    monkeypatch.setattr(fw, "_chat_esegui_tool_gruppo", lambda n, a, auth: visti["gruppo"].append(n) or {"g": 1})
    out = fw._chat_esegui_tool_catena(
        nome, args, user=USER, supabase_client=MagicMock(), authorization="Bearer t",
        settore="ristorazione", sedi=SEDI,
        nomi_di_sede=frozenset(fw._CHAT_TOOLS_SEDE_IN_CATENA) if nomi_di_sede is None else nomi_di_sede,
    )
    return out, visti


def test_la_sede_verificata_va_allo_strumento_come_id_della_riga(monkeypatch):
    out, visti = _catena(monkeypatch, "query_costi", {"sede": "navigli", "categoria": "pesce"})
    ((nome, args, kw),) = visti["sede"]
    assert nome == "query_costi"
    assert kw["ristorante_id"] == "rid-2"
    assert args == {"categoria": "pesce"}, "la sede non passa allo strumento come argomento"
    assert out == {"sede": "SUSHILAND NAVIGLI", "totale": 1}


@pytest.mark.parametrize("sede", [None, "rid-99", "SUSHILAND", "MILANO"])
def test_una_sede_non_riconosciuta_non_esegue_niente(monkeypatch, sede):
    out, visti = _catena(monkeypatch, "query_scadenze", {"sede": sede} if sede else {})
    assert visti["sede"] == [] and visti["gruppo"] == []
    assert "errore" in out
    assert out["punti_vendita"] == [s["nome"] for s in SEDI]


def test_uno_strumento_di_sede_non_offerto_non_si_esegue(monkeypatch):
    """Gate pagina all'esecuzione: se query_scadenze non e' stato offerto, un
    nome allucinato va al dispatcher di gruppo, che non lo conosce."""
    _, visti = _catena(monkeypatch, "query_scadenze", {"sede": "navigli"}, nomi_di_sede=frozenset({"query_costi"}))
    assert visti["sede"] == []
    assert visti["gruppo"] == ["query_scadenze"]


def test_gli_strumenti_di_gruppo_restano_di_gruppo(monkeypatch):
    out, visti = _catena(monkeypatch, "gruppo_overview", {})
    assert visti["gruppo"] == ["gruppo_overview"] and out == {"g": 1}


# ─── Le funzioni di sede usano la sede ricevuta, non quella del token ───────


def test_scadenze_e_margini_usano_la_sede_esplicita(monkeypatch):
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-ATTIVA")
    viste = []
    import services.documenti_service as ds
    monkeypatch.setattr(ds, "get_documenti_scadenziario", lambda uid, rid: viste.append(rid) or [])
    fw._chat_query_scadenze(USER, MagicMock(), ristorante_id="rid-2")
    assert viste == ["rid-2"]
    import services.margine_service as ms
    monkeypatch.setattr(ms, "carica_margini_anno", lambda uid, rid, a: viste.append(rid) or {})
    monkeypatch.setattr(ms, "calcola_costi_automatici_per_anno_sql", lambda uid, rid, a: ({}, {}))
    monkeypatch.setattr(fw, "_merge_override_mensile", lambda m, *a: m)
    fw._chat_query_margini(USER, MagicMock(), None, ristorante_id="rid-3")
    assert set(viste[1:]) == {"rid-3"}


def test_senza_sede_esplicita_resta_la_sede_attiva(monkeypatch):
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-ATTIVA")
    viste = []
    import services.documenti_service as ds
    monkeypatch.setattr(ds, "get_documenti_scadenziario", lambda uid, rid: viste.append(rid) or [])
    fw._chat_query_scadenze(USER, MagicMock())
    assert viste == ["rid-ATTIVA"]


def test_gli_appuntamenti_filtrano_anche_per_utente():
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "gte", "lte", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[])
    sb.table.return_value = q
    fw._chat_query_appuntamenti(USER, sb, "rid-2", da="2026-01-01", a="2026-12-31")
    filtri = {c.args for c in q.eq.call_args_list}
    assert ("user_id", "u-1") in filtri and ("ristorante_id", "rid-2") in filtri


# ─── Il prompt di catena ────────────────────────────────────────────────────


def _prompt_catena(monkeypatch, sedi):
    g = MagicMock()
    g.gruppo_overview.side_effect = RuntimeError("niente overview in questo test")
    monkeypatch.setattr(fw, "_gruppo_router_mod", lambda: g)
    return fw._build_chat_system_prompt_catena(USER, MagicMock(), None, "ristorazione", sedi=sedi)


def test_il_prompt_di_catena_elenca_le_sedi_e_spiega_sede(monkeypatch):
    p = _prompt_catena(monkeypatch, [s["nome"] for s in SEDI])
    assert "## Punti vendita del gruppo\n- SUSHILAND CASATI 14\n- SUSHILAND NAVIGLI\n- SUSHILAND PORTA ROMANA" in p
    assert "`sede`: scrivi il nome esatto dall'elenco" in p
    assert "invita ad aprire quel punto vendita" not in p


def test_senza_sedi_il_prompt_di_catena_resta_quello_di_prima(monkeypatch):
    p = _prompt_catena(monkeypatch, [])
    assert "Per domande sul singolo locale invita ad aprire quel punto vendita." in p
    assert "Punti vendita del gruppo" not in p


# ─── chat_ai in catena: offre gli strumenti di sede e passa le sedi al prompt ─


def test_chat_ai_catena_offre_gruppo_e_sede(monkeypatch):
    visto = {}
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "order", "limit", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(
        data=[{"id": s["id"], "nome_ristorante": s["nome"]} for s in SEDI], count=3,
    )
    sb.table.return_value = q
    sb.rpc.return_value.execute.return_value = MagicMock(data=1)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(USER))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, True))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 600)
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s=None: "ristorazione")

    def _prompt(*a, **k):
        visto["sedi_al_prompt"] = k.get("sedi")
        return "prompt"

    def _loop(client, messages, tools, esegui, log_ctx=""):
        visto["tools"] = {t["function"]["name"] for t in tools}
        visto["esegui"] = esegui
        return ("ok", 1, 1)

    monkeypatch.setattr(fw, "_build_chat_system_prompt_catena", _prompt)
    monkeypatch.setattr(fw, "_chat_loop_openai", _loop)
    req = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="scadenze di navigli?")], contesto="catena")
    fw.chat_ai(req, authorization="Bearer t")
    assert visto["sedi_al_prompt"] == [s["nome"] for s in SEDI]
    assert {"gruppo_overview", "query_scadenze", "query_costi"} <= visto["tools"]
    assert "query_coperti" not in visto["tools"]
    fuori = visto["esegui"]("query_costi", {"sede": "rid-99"})
    assert "errore" in fuori, "il dispatcher vero di chat_ai deve rifiutare una sede non dell'account"


# ─── Vista punto vendita: il gate pagina vale anche all'esecuzione ──────────
#
# Segnalato dal revisore il 29/9 (esisteva da prima): la catena lo aveva con
# `nomi_di_sede`, la vista PV solo sulla lista offerta.


def _esegui_pv(monkeypatch, user):
    visto = {}
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "order", "limit", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"nome_ristorante": "X"}], count=1)
    sb.table.return_value = q
    sb.rpc.return_value.execute.return_value = MagicMock(data=1)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(user))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, False))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 600)
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, s: {"chat_ai_enabled": True})
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s=None: "ristorazione")
    monkeypatch.setattr(fw, "_build_chat_system_prompt", lambda *a, **k: "prompt")

    def _loop(client, messages, tools, esegui, log_ctx=""):
        visto["esegui"] = esegui
        return ("ok", 1, 1)

    monkeypatch.setattr(fw, "_chat_loop_openai", _loop)
    fw.chat_ai(fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="x")]), authorization="Bearer t")
    return visto["esegui"]


def test_pv_uno_strumento_spento_per_pagina_non_si_esegue_anche_se_nominato(monkeypatch):
    senza_scadenze = dict(USER, pagine_abilitate={"analisi_fatture": True, "scadenziario": False})
    chiamato = []
    monkeypatch.setattr(fw, "_chat_query_scadenze", lambda *a, **k: chiamato.append(1) or {})
    esegui = _esegui_pv(monkeypatch, senza_scadenze)
    out = esegui("query_scadenze", {})
    assert chiamato == [] and "non disponibile" in out["errore"]


def test_pv_uno_strumento_offerto_si_esegue(monkeypatch):
    chiamato = []
    monkeypatch.setattr(fw, "_chat_query_scadenze", lambda *a, **k: chiamato.append(k) or {})
    esegui = _esegui_pv(monkeypatch, USER)
    esegui("query_scadenze", {})
    assert chiamato == [{"ristorante_id": "rid-1"}]


def test_il_controllo_di_settore_resta_anche_nel_dispatcher_di_sede():
    """Seconda difesa: da chat_ai ora il gate della lista arriva prima, ma chi
    chiama il dispatcher di sede direttamente trova ancora il rifiuto."""
    out = fw._chat_esegui_tool_sede(
        "query_coperti", {}, user=USER, supabase_client=MagicMock(), authorization=None,
        ristorante_id="rid-1", settore="retail",
    )
    assert "non disponibile per questa attivita'" in out["errore"]
