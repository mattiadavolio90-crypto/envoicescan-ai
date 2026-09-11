"""La chat AI di un negozio: prompt e strumenti (RETAIL_FASI.md, Fase 4).

Due difetti dichiarati dal reviewer alla chiusura della Fase 3:

1. il prompt di sede diceva «Rispondi SOLO a domande sui dati del ristorante» e
   hardcodava «soglia normale e' 28-33%» — per un negozio sono affermazioni
   false, e il modello le ripete al cliente come proprie;
2. il gate dei tool guarda le chiavi-PAGINA, e i `tab_off_*` della Fase 3 non lo
   sono: un negozio NON vedeva la tab Coperti e poteva comunque chiedere i
   coperti in chat. Spegnerli via `pagine_abilitate` non era un'alternativa:
   `query_margini` e `query_coperti` sono mappati sullo STESSO flag `margini`.

Il presidio piu' importante e' `test_ramo_ristorazione_e_identico_a_prima`: il
vincolo di Mattia e' che un cliente ristorazione non veda cambiare nemmeno
un'etichetta, e qui si dimostra per uguaglianza col testo letterale di ieri.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE
from services.fastapi_worker import _build_chat_system_prompt, _build_chat_system_prompt_catena

USER = {
    "id": "u-test", "nome_ristorante": "TEST", "email": "t@x.it",
    "pagine_abilitate": {"margini": True, "analisi_fatture": True, "agenda": True},
}


def _kpi_mock():
    return MagicMock(
        has_data=True, food_cost_pct=30.0, fatturato=10000.0,
        costo_personale=2000.0, spese_generali=1000.0, mol=3000.0,
        periodo_label="agosto 2026", confronto_label=None,
    )


def _sb():
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[], count=0)
    return sb


def _prompt(settore, monkeypatch):
    monkeypatch.setattr(fw, "home_kpi", lambda *a, **k: _kpi_mock())
    monkeypatch.setattr(fw, "_chat_top_cat_forn", lambda *a, **k: ([], []))
    return _build_chat_system_prompt(USER, _sb(), None, "r-1", settore)


# ── 1. Il prompt del negozio non dice cose false ──────────────────────────

def test_negozio_non_legge_i_benchmark_della_ristorazione(monkeypatch):
    p = _prompt(SETTORE_RETAIL, monkeypatch)
    assert "28-33%" not in p, "la soglia food cost della ristorazione e' finita nel prompt di un negozio"
    assert "ristorazione italiana" not in p
    assert "Food cost %" not in p


def test_negozio_riceve_la_regola_del_confronto_coi_propri_mesi(monkeypatch):
    p = _prompt(SETTORE_RETAIL, monkeypatch)
    assert "NIENTE soglie di settore" in p
    assert "mesi precedenti" in p


def test_negozio_non_viene_chiamato_ristorante(monkeypatch):
    p = _prompt(SETTORE_RETAIL, monkeypatch)
    assert "dati del negozio" in p
    assert "dati del ristorante" not in p
    assert "Conti del negozio" in p


def test_negozio_non_legge_food_cost_nei_kpi(monkeypatch):
    p = _prompt(SETTORE_RETAIL, monkeypatch)
    assert "- Costo merce: 30.0%" in p
    assert "- Food cost:" not in p


def test_negozio_non_riceve_la_riga_dei_coperti(monkeypatch):
    """Il tool non gli viene offerto: prometterlo nel prompt e' peggio che tacere."""
    p = _prompt(SETTORE_RETAIL, monkeypatch)
    assert "query_coperti" not in p
    assert "scontrino medio" not in p


def test_ristorante_riceve_ancora_la_riga_dei_coperti(monkeypatch):
    p = _prompt(SETTORE_RISTORAZIONE, monkeypatch)
    assert "usa query_coperti" in p
    assert "scontrino medio" in p


# ── 2. Il vincolo: per un ristorante NON cambia niente ────────────────────

_BENCHMARK_RISTORAZIONE = """## Benchmark di settore (ristorazione italiana — usa questi per valutare)
Quando l'utente chiede "va bene?", "è troppo?", "sono nella norma?", usa queste soglie per dare una valutazione concreta:

**Food cost %** (costi food ÷ fatturato):
- <28% → eccellente | 28-33% → nella norma | 33-38% → sopra la media (attenzione) | >38% → critico

**MOL %** (margine operativo lordo ÷ fatturato):
- >20% → eccellente | 12-20% → nella norma | 5-12% → basso | <5% → critico

**Costo personale %** (costo personale ÷ fatturato):
- <24% → contenuto | 24-30% → nella norma | 30-35% → elevato | >35% → critico

**Spese generali %** (spese generali ÷ fatturato):
- <15% → contenute | 15-22% → nella norma | 22-28% → elevate | >28% → fuori controllo

Esempio corretto: "Il tuo food cost è al 26,5% → eccellente per il settore (soglia normale è 28-33%)."
NON inventare benchmark diversi da questi. Se non riesci a calcolare la % perché manca fatturato o costi, dillo."""


@pytest.mark.parametrize("settore", [SETTORE_RISTORAZIONE, None, "", "valore_ignoto"])
def test_ramo_ristorazione_e_identico_a_prima(settore, monkeypatch):
    """Il testo letterale di ieri, non una sua parafrasi.

    Include i casi `None`/ignoto: il fail-safe del settore va verso la
    ristorazione, ed e' li' che cade ogni chiamante che non lo passa.
    """
    p = _prompt(settore, monkeypatch)
    assert _BENCHMARK_RISTORAZIONE in p
    assert 'integrato nel gestionale del ristorante "TEST"' in p
    assert "Rispondi SOLO a domande sui dati del ristorante: costi, fornitori, food cost, margini, MOL, fatture, scadenze." in p
    assert "da collega esperto in F&B" in p
    assert "- Food cost: 30.0%" in p
    assert '## Food cost "0.0%" o "n/d": NON è cibo a costo zero' in p


def test_settore_none_e_ristorazione_danno_lo_stesso_prompt(monkeypatch):
    assert _prompt(None, monkeypatch) == _prompt(SETTORE_RISTORAZIONE, monkeypatch)


# ── 3. Gate dei tool: sul settore, non sulla pagina ───────────────────────

def test_query_coperti_e_vietato_al_retail():
    assert "query_coperti" in fw._TOOL_VIETATI_PER_SETTORE[SETTORE_RETAIL]


def test_query_margini_resta_al_retail():
    assert "query_margini" not in fw._TOOL_VIETATI_PER_SETTORE[SETTORE_RETAIL]


def test_nessun_tool_vietato_alla_ristorazione():
    assert fw._TOOL_VIETATI_PER_SETTORE.get(SETTORE_RISTORAZIONE) is None


# ── 4. Chat catena: un negozio multi-sede arriva qui davvero ──────────────

def _prompt_catena(settore, monkeypatch):
    monkeypatch.setattr(
        fw, "_gruppo_router_mod",
        lambda: MagicMock(gruppo_overview=MagicMock(side_effect=RuntimeError("no"))),
    )
    return _build_chat_system_prompt_catena(USER, _sb(), None, settore)


def test_catena_retail_non_parla_di_ristoranti(monkeypatch):
    p = _prompt_catena(SETTORE_RETAIL, monkeypatch)
    assert "GRUPPO di negozi" in p
    assert "GRUPPO di ristoranti" not in p
    assert "28-33%" not in p


def test_catena_ristorazione_identica_a_prima(monkeypatch):
    p = _prompt_catena(SETTORE_RISTORAZIONE, monkeypatch)
    assert "GRUPPO di ristoranti «il gruppo», non di un singolo locale." in p
    assert "Food cost: <28% eccellente | 28-33% norma | 33-38% attenzione | >38% critico" in p
    assert '- Per "quale PV ha il margine/scontrino/coperti migliore o peggiore" usa gruppo_margini_coperti.' in p


# ── 5. Il gate nell'endpoint vero, non nella costante ─────────────────────
#
# Asserire su `_TOOL_VIETATI_PER_SETTORE` prova solo che la costante contiene
# una stringa. Qui si esegue `chat_ai` e si cattura la lista `tools` che arriva
# davvero al loop OpenAI: e' l'unico modo perche' il presidio muoia se il gate
# viene tolto.

def _chat_request():
    return fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="quanti coperti ho fatto ieri?")])


def _tools_offerti(settore, monkeypatch):
    catturati = {}

    def _loop(client, messages, tools, esegui, log_ctx=""):
        catturati["tools"] = [t["function"]["name"] for t in tools]
        catturati["esegui"] = esegui
        return ("ok", 1, 1)

    sb = _sb()
    sb.rpc.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=1)))
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(USER))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, False))
    monkeypatch.setattr(fw, "_chat_domande_oggi", lambda *a, **k: 1)
    def _prompt_spy(user, sb_, auth, rid, settore_ric=None):
        catturati["settore_al_prompt"] = settore_ric
        return "prompt"

    monkeypatch.setattr(fw, "_build_chat_system_prompt", _prompt_spy)
    monkeypatch.setattr(fw, "_chat_loop_openai", _loop)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, sb=None: settore)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    fw.chat_ai(_chat_request(), authorization="Bearer t")
    return catturati


def test_endpoint_non_offre_query_coperti_a_un_negozio(monkeypatch):
    c = _tools_offerti(SETTORE_RETAIL, monkeypatch)
    assert "query_coperti" not in c["tools"]
    assert "query_margini" in c["tools"], "togliendo i coperti sono spariti anche i margini"


def test_endpoint_offre_query_coperti_a_un_ristorante(monkeypatch):
    c = _tools_offerti(SETTORE_RISTORAZIONE, monkeypatch)
    assert "query_coperti" in c["tools"]
    assert "query_margini" in c["tools"]


def test_esecuzione_rifiutata_anche_se_il_modello_inventa_il_nome(monkeypatch):
    """Il dispatcher esegue per nome e non consulta `tools`: un nome allucinato
    passerebbe il gate della lista. E' la famiglia dei sette buchi della Fase 1."""
    c = _tools_offerti(SETTORE_RETAIL, monkeypatch)
    esito = c["esegui"]("query_coperti", {})
    assert "errore" in esito
    assert "non disponibile" in esito["errore"]


def test_esecuzione_dei_coperti_resta_viva_per_un_ristorante(monkeypatch):
    c = _tools_offerti(SETTORE_RISTORAZIONE, monkeypatch)
    chiamato = {}
    monkeypatch.setattr(fw, "_chat_query_coperti", lambda *a, **k: chiamato.setdefault("si", True))
    c["esegui"]("query_coperti", {})
    assert chiamato.get("si") is True


def test_il_settore_arriva_davvero_al_prompt(monkeypatch):
    """M3: senza questo, `chat_ai` poteva passare None al prompt e tutti i test
    del prompt restavano verdi — misurano la funzione, non il suo chiamante."""
    c = _tools_offerti(SETTORE_RETAIL, monkeypatch)
    assert c["settore_al_prompt"] == SETTORE_RETAIL


def test_il_settore_ristorazione_arriva_al_prompt(monkeypatch):
    c = _tools_offerti(SETTORE_RISTORAZIONE, monkeypatch)
    assert c["settore_al_prompt"] == SETTORE_RISTORAZIONE
