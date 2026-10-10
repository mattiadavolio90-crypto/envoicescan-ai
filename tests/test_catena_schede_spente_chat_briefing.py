"""Le schede della catena spente dall'admin (`tab_off_catena_*`, fase H3) valgono
anche dove il frontend non le disegna: il briefing di gruppo e la chat di catena
(fase I, 10/10/2026).

Residui della H: con «Da collocare» spenta la riga del «Da fare» spariva, ma
l'audio del riquadro, `/m` e «tutto in ordine» contavano ancora la coda; e la chat
di catena rispondeva con coperti e margini a chi li aveva spenti. Si prova il
comportamento, non il sorgente.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

import services.fastapi_worker as fw  # noqa: E402
from services.routers import gruppo  # noqa: E402

# Un account con tutte le pagine e, a scelta, schede di catena spente.
PAGINE_BASE = {"margini": True, "analisi_fatture": True, "agenda": True, "scadenziario": True}


def _pagine(*spente):
    return {**PAGINE_BASE, **{f"tab_off_catena_{s}": True for s in spente}}


# ── Il briefing di gruppo non conta la coda spenta ───────────────────────────

RIGA = {
    "ristorante_id": "a", "mese": 6, "fatturato_iva10": 11_000,
    "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
    "altri_costi_fb": 0, "altri_costi_spese": 0,
    "quote_riparto_fb": 0, "quote_riparto_spese": 0,
    "costo_dipendenti": 1_000, "costo_personale_extra": 0,
}


def _overview(pagine, n_coda=3, utente_ko=False, segnali=(0, "info")):
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "in_", "eq", "lte", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[RIGA], count=n_coda)
    sb.table.return_value = q
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res
    if utente_ko:
        utente = MagicMock(side_effect=RuntimeError("sessione illeggibile"))
    else:
        utente = MagicMock(return_value={"id": "u1", "pagine_abilitate": pagine})

    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, "u1", [{"id": "a"}], "Gruppo", {"a": "PV a"}, ["a"])), \
         patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)), \
         patch.object(gruppo, "_completezza_dati_pv", return_value={}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_resolve_user_from_token", utente), \
         patch.object(gruppo, "_fatture_arrivate_ieri_gruppo",
                      return_value={"n_assegnate": 0, "n_in_coda": n_coda}), \
         patch.object(gruppo, "_salute_indici_batch", return_value={"a": 90}), \
         patch.object(gruppo, "_conta_segnali_cache", return_value=segnali), \
         patch.object(gruppo, "_avvisi_delle_sedi", return_value=([], [])), \
         patch.object(gruppo, "_get_gruppo_config", return_value=(set(), set())), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               return_value={"a": ({6: 4_000.0}, {})}), \
         patch.object(gruppo, "_calcola_segnali", return_value=[]):
        return gruppo.gruppo_overview(authorization="Bearer t").briefing


def test_coda_accesa_il_briefing_la_conta():
    b = _overview(_pagine())
    assert b.n_fatture_da_collocare == 3
    assert b.fatture_ieri_da_assegnare is True
    assert "tutto in ordine" not in b.narrativa, "con 3 fatture in coda non e' tutto in ordine"


def test_coda_spenta_il_briefing_non_la_conta():
    b = _overview(_pagine("collocare"))
    assert b.n_fatture_da_collocare == 0
    assert b.fatture_ieri_da_assegnare is False


def test_coda_spenta_il_tutto_in_ordine_non_aspetta_la_coda():
    """Era il residuo della H: con la scheda spenta la coda restava un motivo per
    non dire «tutto in ordine», e nessuno poteva toglierla."""
    assert "tutto in ordine" in _overview(_pagine("collocare")).narrativa


def test_coda_spenta_non_toglie_gli_altri_motivi():
    """Spegnere la scheda toglie la coda dal conto, non il resto: una segnalazione
    aperta resta un motivo per non dire «tutto in ordine»."""
    b = _overview(_pagine("collocare"), segnali=(2, "warning"))
    assert "tutto in ordine" not in b.narrativa


def test_altra_scheda_spenta_la_coda_resta():
    """Solo `collocare` toglie la coda: spegnere margini o spesa non la tocca."""
    assert _overview(_pagine("margini", "spesa", "costi", "scadenze", "coperti")).n_fatture_da_collocare == 3


def test_pagine_illeggibili_la_coda_resta():
    """Dato assente != via libera: se non si sa cosa ha spento, si mostra la coda
    (una riga in piu') invece di taciuta."""
    assert _overview(None, utente_ko=True).n_fatture_da_collocare == 3


def test_account_senza_restrizioni_la_coda_resta():
    assert _overview(None).n_fatture_da_collocare == 3


# ── Gli strumenti di gruppo della chat ──────────────────────────────────────

def _nomi(tools):
    return [t["function"]["name"] for t in tools]


def test_tutto_acceso_la_lista_e_la_stessa():
    base = fw._chat_tools_gruppo("ristorazione")
    assert fw._chat_tools_gruppo_per_pagine(base, fw._normalize_pagine(_pagine())) is base
    assert fw._chat_tools_gruppo_per_pagine(base, None) is base


def test_margini_spenta_via_lo_strumento_dei_margini():
    base = fw._chat_tools_gruppo("ristorazione")
    out = fw._chat_tools_gruppo_per_pagine(base, fw._normalize_pagine(_pagine("margini")))
    assert "gruppo_margini_coperti" not in _nomi(out)
    assert {"gruppo_overview", "gruppo_spesa", "gruppo_segnali"} <= set(_nomi(out))


def test_spesa_spenta_via_lo_strumento_della_spesa():
    base = fw._chat_tools_gruppo("ristorazione")
    out = fw._chat_tools_gruppo_per_pagine(base, fw._normalize_pagine(_pagine("spesa")))
    assert "gruppo_spesa" not in _nomi(out)
    assert "gruppo_margini_coperti" in _nomi(out)


def test_coperti_spenti_lo_strumento_resta_ma_non_promette_coperti():
    base = fw._chat_tools_gruppo("ristorazione")
    out = fw._chat_tools_gruppo_per_pagine(base, fw._normalize_pagine(_pagine("coperti")))
    margini = next(t for t in out if t["function"]["name"] == "gruppo_margini_coperti")
    descr = margini["function"]["description"].lower()
    assert "coperto" not in descr and "coperti" not in descr and "scontrino" not in descr
    assert "margine" in descr and "food cost" in descr


def test_filtrare_non_cambia_la_lista_di_modulo():
    originale = next(t for t in fw._CHAT_TOOLS_GRUPPO
                     if t["function"]["name"] == "gruppo_margini_coperti")["function"]["description"]
    base = fw._chat_tools_gruppo("ristorazione")
    fw._chat_tools_gruppo_per_pagine(base, fw._normalize_pagine(_pagine("coperti", "spesa")))
    assert [t["function"]["name"] for t in fw._CHAT_TOOLS_GRUPPO] == [
        "gruppo_overview", "gruppo_margini_coperti", "gruppo_spesa", "gruppo_segnali"]
    assert next(t for t in fw._CHAT_TOOLS_GRUPPO
                if t["function"]["name"] == "gruppo_margini_coperti")["function"]["description"] == originale
    assert "coperti" in originale


# ── Il dispatcher rifiuta cio' che non e' offerto, anche se il modello lo nomina

RISPOSTA = {
    "nome_gruppo": "G", "periodo_label": "2026",
    "righe": [{"ristorante_id": "a", "nome": "A", "margine_perc": 10.0, "fatturato": 100.0,
               "coperti": 50, "scontrino_medio": 2.0, "mp_per_coperto": 0.5,
               "dati_incompleti": False, "food_cost_perc": 30.0}],
    "gruppo": {"ristorante_id": "", "nome": "Gruppo", "margine_perc": 10.0, "fatturato": 100.0,
               "coperti": 50, "scontrino_medio": 2.0, "mp_per_coperto": 0.5,
               "dati_incompleti": False, "food_cost_perc": 30.0},
    "n_incompleti": 0,
}


def _esegui(nome, pagine, monkeypatch):
    chiamate = []

    def finto(n, args, auth):
        chiamate.append(n)
        import copy
        return copy.deepcopy(RISPOSTA)

    monkeypatch.setattr(fw, "_chat_esegui_tool_gruppo", finto)
    out = fw._chat_esegui_tool_catena(
        nome, {}, user={}, supabase_client=None, authorization="Bearer t",
        settore="ristorazione", sedi=[], nomi_di_sede=frozenset(),
        pagine=fw._normalize_pagine(pagine),
    )
    return out, chiamate


@pytest.mark.parametrize("nome,scheda", [("gruppo_margini_coperti", "margini"), ("gruppo_spesa", "spesa")])
def test_strumento_di_scheda_spenta_non_si_esegue(nome, scheda, monkeypatch):
    out, chiamate = _esegui(nome, _pagine(scheda), monkeypatch)
    assert "errore" in out
    assert chiamate == [], "uno strumento spento non deve nemmeno leggere i dati"


def test_strumento_di_scheda_accesa_si_esegue(monkeypatch):
    out, chiamate = _esegui("gruppo_margini_coperti", _pagine("spesa"), monkeypatch)
    assert chiamate == ["gruppo_margini_coperti"] and "errore" not in out


def test_altri_strumenti_non_dipendono_dalle_schede(monkeypatch):
    out, chiamate = _esegui("gruppo_segnali", _pagine("margini", "spesa"), monkeypatch)
    assert chiamate == ["gruppo_segnali"] and "errore" not in out


def test_coperti_spenti_la_risposta_non_li_contiene(monkeypatch):
    out, _ = _esegui("gruppo_margini_coperti", _pagine("coperti"), monkeypatch)
    for riga in out["righe"] + [out["gruppo"]]:
        assert not {"coperti", "scontrino_medio", "mp_per_coperto"} & set(riga)
        assert riga["margine_perc"] == 10.0 and riga["food_cost_perc"] == 30.0


def test_coperti_accesi_la_risposta_e_intera(monkeypatch):
    out, _ = _esegui("gruppo_margini_coperti", _pagine("spesa"), monkeypatch)
    assert out["righe"][0]["coperti"] == 50 and out["gruppo"]["scontrino_medio"] == 2.0


def test_senza_pagine_nessuna_restrizione(monkeypatch):
    out, _ = _esegui("gruppo_margini_coperti", None, monkeypatch)
    assert out["righe"][0]["coperti"] == 50


# ── Il prompt di catena non rimanda a cio' che non c'e' ──────────────────────

def _prompt(pagine, settore="ristorazione"):
    user = {"id": "u1", "nome_referente": "", "pagine_abilitate": pagine}
    with patch.object(fw, "_gruppo_router_mod", side_effect=RuntimeError("niente overview")):
        return fw._build_chat_system_prompt_catena(user, MagicMock(), "Bearer t", settore)


def test_prompt_tutto_acceso_nomina_i_tre_strumenti():
    p = _prompt(_pagine())
    assert "gruppo_margini_coperti" in p and "gruppo_spesa" in p and "gruppo_segnali" in p
    assert "scontrino/coperti" in p and "incasso_fuori_norma" in p


def test_prompt_margini_spenta_non_nomina_lo_strumento():
    p = _prompt(_pagine("margini"))
    assert "gruppo_margini_coperti" not in p and "incasso_fuori_norma" not in p
    assert "gruppo_spesa" in p, "la spesa e' un'altra scheda"
    assert "coperti," not in p.split("segnalazioni")[0].split("margini,")[-1]


def test_prompt_spesa_spenta_non_nomina_lo_strumento():
    p = _prompt(_pagine("spesa"))
    assert "gruppo_spesa" not in p
    assert "gruppo_margini_coperti" in p


def test_prompt_coperti_spenti_non_li_promette():
    p = _prompt(_pagine("coperti"))
    assert "scontrino/coperti" not in p
    assert "gruppo_margini_coperti" in p
    assert "spesa fornitori, segnalazioni" in p


def test_prompt_retail_coperti_spenti_resta_quello_dei_negozi():
    """Un negozio non ha i coperti in nessun caso: la riga e' gia' la sua."""
    assert _prompt(_pagine("coperti"), "retail") == _prompt(_pagine(), "retail")


# ── Dentro chat_ai: cio' che il modello riceve ───────────────────────────────

USER = {"id": "u-1", "email": "u@x.it", "nome_ristorante": "A"}


def _chat_catena(monkeypatch, pagine):
    visto = {}
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "eq", "order", "limit", "is_", "single"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(
        data=[{"id": "rid-1", "nome_ristorante": "A"}, {"id": "rid-2", "nome_ristorante": "B"}], count=2,
    )
    sb.table.return_value = q
    sb.rpc.return_value.execute.return_value = MagicMock(data=1)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token",
                        lambda auth: {**USER, "pagine_abilitate": pagine})
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, True))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda u, s: 600)
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, s=None: "ristorazione")
    monkeypatch.setattr(fw, "_build_chat_system_prompt_catena", lambda *a, **k: "prompt")

    def _loop(client, messages, tools, esegui, log_ctx=""):
        visto["tools"] = {t["function"]["name"] for t in tools}
        visto["esegui"] = esegui
        return ("ok", 1, 1)

    monkeypatch.setattr(fw, "_chat_loop_openai", _loop)
    req = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="margini?")], contesto="catena")
    fw.chat_ai(req, authorization="Bearer t")
    return visto


def test_chat_ai_catena_margini_spenta(monkeypatch):
    chiamate = []
    monkeypatch.setattr(fw, "_chat_esegui_tool_gruppo", lambda n, a, auth: chiamate.append(n) or {"ok": 1})
    v = _chat_catena(monkeypatch, _pagine("margini"))
    assert "gruppo_margini_coperti" not in v["tools"] and "gruppo_spesa" in v["tools"]
    assert "errore" in v["esegui"]("gruppo_margini_coperti", {})
    assert chiamate == [], "il dispatcher di chat_ai deve conoscere le pagine, non solo la lista offerta"


def test_chat_ai_catena_coperti_spenti_la_risposta_non_li_contiene(monkeypatch):
    import copy
    monkeypatch.setattr(fw, "_chat_esegui_tool_gruppo", lambda n, a, auth: copy.deepcopy(RISPOSTA))
    v = _chat_catena(monkeypatch, _pagine("coperti"))
    out = v["esegui"]("gruppo_margini_coperti", {})
    assert "coperti" not in out["righe"][0] and "coperti" not in out["gruppo"]
    assert out["righe"][0]["margine_perc"] == 10.0


def test_chat_ai_catena_tutto_acceso(monkeypatch):
    v = _chat_catena(monkeypatch, _pagine())
    assert {"gruppo_margini_coperti", "gruppo_spesa", "gruppo_segnali", "gruppo_overview"} <= v["tools"]
