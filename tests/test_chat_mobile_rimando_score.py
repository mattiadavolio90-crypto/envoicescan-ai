"""Il telefono non ha Osservatorio → Score Fornitori (fase I, 10/10/2026).

Il rimando a Score Fornitori (le bozze al fornitore stanno li', non nella chat)
dice dove andare. Su `/m` quella scheda non c'e': il rimando deve dire «dall'app
da computer». Il flag e' `ChatRequest.mobile`, separato da `card_conferma`: le
card con Conferma ora le mostrano la Home e `/m`, ma solo `/m` e' il telefono.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

import services.fastapi_worker as fw  # noqa: E402

DESKTOP = "in Osservatorio → Score Fornitori."
TELEFONO = "in Osservatorio → Score Fornitori, dall'app da computer."
DOMANDA = "scrivimi una bozza per il fornitore di pesce"


def test_il_flag_parte_spento():
    assert fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="x")]).mobile is False


def test_non_dipende_dalle_card():
    """Con le card accese e il flag spento (la Home) il rimando e' quello di sempre."""
    req = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="x")], card_conferma=True)
    assert req.card_conferma is True and req.mobile is False


def test_dove_score_solo_sul_telefono():
    assert fw._dove_score("", False) == ""
    assert fw._dove_score("", True) == ", dall'app da computer"
    assert fw._dove_score(", aprendo quel locale", True) == ", aprendo quel locale, dall'app da computer"
    assert fw._dove_score(", aprendo quel locale", False) == ", aprendo quel locale"


def test_riga_del_prompt_sul_telefono():
    assert fw._riga_trattativa(None, "").endswith(DESKTOP)
    assert fw._riga_trattativa(None, fw._dove_score("", True)).endswith(TELEFONO)


def test_riga_del_prompt_senza_score_non_rimanda_da_nessuna_parte():
    """Chi non vede la scheda (pagina o scheda spenta) non viene mandato altrove,
    telefono o no."""
    riga = fw._riga_trattativa(["margini"], fw._dove_score("", True))
    assert "Score" not in riga and riga.endswith(".")


def test_rimando_aggiunto_dal_codice_sul_telefono():
    out = fw._rimando_score(DOMANDA, "Non scrivo bozze.", None, fw._dove_score("", True))
    assert out.endswith(TELEFONO)


def test_rimando_aggiunto_dal_codice_sul_desktop_resta_quello_di_prima():
    out = fw._rimando_score(DOMANDA, "Non scrivo bozze.", None, fw._dove_score("", False))
    assert out.endswith(DESKTOP) and "computer" not in out


def _prompt_sede(mobile):
    with patch.object(fw, "home_kpi", side_effect=RuntimeError("niente kpi")):
        return fw._build_chat_system_prompt(
            {"id": "u1", "email": "u@x.it", "nome_ristorante": "A"}, MagicMock(), "Bearer t",
            "rid-1", "ristorazione", mobile=mobile,
        )


def test_prompt_di_sede_dice_dove_sul_telefono():
    assert TELEFONO in _prompt_sede(True)
    assert "dall'app da computer" not in _prompt_sede(False)
    assert DESKTOP in _prompt_sede(False)


def _prompt_catena(mobile):
    with patch.object(fw, "_gruppo_router_mod", side_effect=RuntimeError("niente overview")):
        return fw._build_chat_system_prompt_catena(
            {"id": "u1", "nome_referente": ""}, MagicMock(), "Bearer t", "ristorazione",
            cifre_dettate=True, mobile=mobile,
        )


def test_prompt_di_catena_dice_dove_sul_telefono():
    p = _prompt_catena(True)
    assert "aprendo quel locale, dall'app da computer." in p
    assert "dall'app da computer" not in _prompt_catena(False)


def test_prompt_di_catena_le_cifre_sul_telefono_non_parlano_di_una_home_con_la_chat():
    """Sul telefono la chat e' una scheda a parte: si scende nel locale e si detta li'."""
    assert "dalla Home e dirla li', nella chat" in _prompt_catena(True)
    assert "la Home di quel locale e dirla li'" in _prompt_catena(False)


# ─── chat_ai passa il flag fino al prompt e al rimando ───────────────────────


class _Fermo(Exception):
    pass


def _chat(monkeypatch, *, mobile, contesto="sede", risposta="Non scrivo bozze."):
    visto = {}
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "limit", "order", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"id": "rid-1", "nome_ristorante": "A"},
                                              {"id": "rid-2", "nome_ristorante": "B"}], count=2)
    sb.table.return_value = q
    sb.rpc.return_value.execute.return_value = MagicMock(data=1)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token",
                        lambda auth: {"id": "u-1", "email": "u@x.it", "nome_ristorante": "A"})
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, True))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 600)
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, s: {"chat_ai_enabled": True})
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s=None: "ristorazione")

    def _prompt(*a, **k):
        visto["mobile_al_prompt"] = k.get("mobile")
        return "prompt"

    monkeypatch.setattr(fw, "_build_chat_system_prompt", _prompt)
    monkeypatch.setattr(fw, "_build_chat_system_prompt_catena", _prompt)
    monkeypatch.setattr(fw, "_chat_loop_openai", lambda *a, **k: (risposta, 1, 1))
    req = fw.ChatRequest(
        messages=[fw.ChatMessage(role="user", content=DOMANDA)], contesto=contesto,
        card_conferma=True, mobile=mobile,
    )
    visto["reply"] = fw.chat_ai(req, authorization="Bearer t").reply
    return visto


@pytest.mark.parametrize("contesto", ["sede", "catena"])
def test_chat_ai_passa_il_flag_al_prompt(monkeypatch, contesto):
    assert _chat(monkeypatch, mobile=True, contesto=contesto)["mobile_al_prompt"] is True
    assert _chat(monkeypatch, mobile=False, contesto=contesto)["mobile_al_prompt"] is False


def test_chat_ai_sede_il_rimando_dice_dove_sul_telefono(monkeypatch):
    assert _chat(monkeypatch, mobile=True)["reply"].endswith(TELEFONO)
    assert _chat(monkeypatch, mobile=False)["reply"].endswith(DESKTOP)


def test_chat_ai_catena_il_rimando_dice_dove_sul_telefono(monkeypatch):
    assert _chat(monkeypatch, mobile=True, contesto="catena")["reply"].endswith(
        "aprendo quel locale, dall'app da computer.")
    assert _chat(monkeypatch, mobile=False, contesto="catena")["reply"].endswith(
        "aprendo quel locale.")
