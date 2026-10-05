"""Il rimando a Score Fornitori lo garantisce il codice, non il prompt (fase D3).

Il 5/10/2026 Mattia ha scritto alla chat «ho bisogno che scrivi una bozza per un
fornitore»: la regola del prompt c'era (`_riga_trattativa`), il modello ha
risposto «non scrivo bozze per i fornitori» e si e' offerto di aiutarlo a
scriverla, senza dire che le bozze sono gia' pronte in Osservatorio. Il prompt
non e' una garanzia: se la domanda chiede di scrivere a un fornitore e la
risposta non nomina Score Fornitori, `_rimando_score` aggiunge la frase.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw

FRASE_DI_MATTIA = "ho bisogno che scrivi una bozza per un fornitore"
RISPOSTA_DEL_5_10 = (
    "Posso aiutarti solo con dati e analisi del ristorante, non scrivo bozze per i fornitori. "
    "Se vuoi, posso fornirti i dati degli acquisti o dei prezzi per aiutarti a preparare la "
    "tua comunicazione. Vuoi?"
)
RIMANDO = ("Le bozze per trattare con un fornitore le trovi gia' pronte, con i tuoi acquisti, "
           "in Osservatorio → Score Fornitori")
CON_SCORE = {"prezzi": True, "margini": True}


def test_la_frase_di_mattia_riceve_il_rimando():
    out = fw._rimando_score(FRASE_DI_MATTIA, RISPOSTA_DEL_5_10, None)
    assert out == RISPOSTA_DEL_5_10 + "\n\n" + RIMANDO + "."


@pytest.mark.parametrize("domanda", [
    "mi scrivi una mail al fornitore del pesce?",
    "preparami un messaggio per il fornitore della carne",
    "cosa scrivo al fornitore per avere uno sconto?",
    "aiutami a trattare con il fornitore delle bevande",
    "Bozza per il mio FORNITORE di latticini",
    "fammi una lettera ai fornitori",
])
def test_altri_modi_di_chiederla(domanda):
    assert fw._rimando_score(domanda, "Non posso.", CON_SCORE).endswith(RIMANDO + ".")


@pytest.mark.parametrize("domanda", [
    "quale fornitore mi costa di piu'?",
    "quanto ho speso dal fornitore del pesce a settembre?",
    "scrivimi una bozza di menu",
    "inserisci latte 20 euro",
    "",
    # Dal revisore (5/10): domande di sola informazione
    "il fornitore mi ha mandato una mail col listino nuovo, i prezzi sono saliti?",
    "qual e' la mail del fornitore del pesce?",
    "ho in corso una trattativa col fornitore della carne: quanto ho speso quest'anno?",
    "quanti messaggi di errore ci sono sulle fatture del fornitore X?",
    "mandami un messaggio quando arriva la fattura del fornitore",
])
def test_le_altre_domande_restano_come_sono(domanda):
    assert fw._rimando_score(domanda, "Risposta.", CON_SCORE) == "Risposta."


def test_se_il_modello_lo_ha_gia_detto_non_si_ripete():
    gia = "Le trovi pronte in Osservatorio → Score fornitori."
    assert fw._rimando_score(FRASE_DI_MATTIA, gia, None) == gia


@pytest.mark.parametrize("pagine", [
    {"margini": True},
    {"prezzi": True, "tab_off_prezzi_score": True},
])
def test_chi_non_vede_lo_score_non_ci_viene_mandato(pagine):
    assert fw._rimando_score(FRASE_DI_MATTIA, "Non posso.", pagine) == "Non posso."


def test_risposta_vuota_resta_vuota():
    """Il «Non sono riuscito a elaborare la risposta» lo mette chat_ai su `reply` vuota."""
    assert fw._rimando_score(FRASE_DI_MATTIA, "", None) == ""


# ─── chat_ai: la rete e' collegata, in sede e in catena ─────────────────────


def _chat(monkeypatch, *, contesto, pagine, risposta, settore="ristorazione"):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "order", "limit", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(
        data=[{"id": "rid-1", "nome_ristorante": "A"}, {"id": "rid-2", "nome_ristorante": "B"}],
        count=2,
    )
    sb.table.return_value = q
    sb.rpc.return_value.execute.return_value = MagicMock(data=1)
    user = {"id": "u-1", "email": "u@x.it", "nome_ristorante": "A", "pagine_abilitate": pagine}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(user))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, contesto == "catena"))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 600)
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, s: {"chat_ai_enabled": True})
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)
    monkeypatch.setattr(fw._su, "verifica_catena", lambda u: None)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s=None: settore)
    monkeypatch.setattr(fw, "_build_chat_system_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr(fw, "_build_chat_system_prompt_catena", lambda *a, **k: "prompt")
    monkeypatch.setattr(fw, "_chat_loop_openai", lambda *a, **k: (risposta, 1, 1))
    req = fw.ChatRequest(
        messages=[
            fw.ChatMessage(role="user", content="quanto ho speso in pesce?"),
            fw.ChatMessage(role="assistant", content="1.200 euro a settembre."),
            fw.ChatMessage(role="user", content=FRASE_DI_MATTIA),
        ],
        contesto=contesto,
    )
    return fw.chat_ai(req, authorization="Bearer t").reply


def test_chat_ai_in_sede_aggiunge_il_rimando(monkeypatch):
    out = _chat(monkeypatch, contesto="sede", pagine=None, risposta="Non scrivo bozze.")
    assert out == "Non scrivo bozze.\n\n" + RIMANDO + "."


def test_chat_ai_in_catena_rimanda_al_locale(monkeypatch):
    out = _chat(monkeypatch, contesto="catena", pagine=None, risposta="Non scrivo bozze.")
    assert out.endswith(RIMANDO + ", aprendo quel locale.")
    out = _chat(monkeypatch, contesto="catena", pagine=None, risposta="Non scrivo bozze.",
                settore="retail")
    assert out.endswith(RIMANDO + ", aprendo quel punto vendita.")


def test_chat_ai_guarda_l_ultima_domanda(monkeypatch):
    """La bozza chiesta due messaggi fa non rimanda a ogni risposta successiva."""
    assert fw._ultima_domanda(fw.ChatRequest(messages=[
        fw.ChatMessage(role="user", content=FRASE_DI_MATTIA),
        fw.ChatMessage(role="assistant", content="..."),
        fw.ChatMessage(role="user", content="e quanto ho speso a settembre?"),
    ])) == "e quanto ho speso a settembre?"


def test_chat_ai_senza_score_non_aggiunge_niente(monkeypatch):
    out = _chat(monkeypatch, contesto="sede", pagine={"margini": True}, risposta="Non scrivo bozze.")
    assert out == "Non scrivo bozze."
