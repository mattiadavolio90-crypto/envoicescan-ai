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
import re
from pathlib import Path
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

_FIXTURE_IERI = (
    Path(__file__).resolve().parent / "fixtures" / "chat_prompt_ristorazione_pre_fase4.txt"
)

# Le date che il prompt calcola da `oggi`: nella fixture sono segnaposto, o il
# presidio diventerebbe rosso domani senza che il codice sia cambiato.
_NEUTRALIZZA = (
    (re.compile(r"Oggi e' \d{1,2} \w+ \d{4}\. L'anno corrente e' \d{4}\."),
     "Oggi e' <DATA>. L'anno corrente e' <ANNO>."),
    (re.compile(r"usa SEMPRE l'anno corrente \(\d{4}\)"),
     "usa SEMPRE l'anno corrente (<ANNO>)"),
    (re.compile(r"\(oggi è il \d{1,2}\)"), "(oggi è il <GIORNO>)"),
)


def _senza_date(testo: str) -> str:
    for pattern, segnaposto in _NEUTRALIZZA:
        testo = pattern.sub(segnaposto, testo)
    return testo


@pytest.mark.parametrize("settore", [SETTORE_RISTORAZIONE, None, "", "valore_ignoto"])
def test_ramo_ristorazione_e_identico_a_prima(settore, monkeypatch):
    """Il prompt INTERO contro uno snapshot preso da `23c0706~1`, non sei
    sottostringhe scelte.

    La prima stesura di questo presidio asseriva sottostringhe, ed era CIECA
    proprio sulle quattro righe che avevo cambiato senza accorgermene — una
    delle quali sgrammaticata («da il pesce»). Il reviewer l'ha smascherata
    generando il prompt sui due commit e confrontando gli md5: e' lo stesso modo
    in cui va provato adesso.

    Include i casi `None`/vuoto/ignoto: il fail-safe del settore va verso la
    ristorazione, ed e' li' che cade ogni chiamante che non lo passa.
    """
    atteso = _senza_date(_FIXTURE_IERI.read_text(encoding="utf-8"))
    ottenuto = _senza_date(_prompt(settore, monkeypatch))
    assert ottenuto == atteso, (
        "il prompt di un RISTORANTE e' cambiato: e' il vincolo di Mattia, "
        "nemmeno un'etichetta"
    )


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


# ── Findings della review, chiusi qui ────────────────────────────────────

def test_la_description_dei_tool_di_gruppo_non_promette_i_coperti_a_un_negozio():
    """La *description* e' testo che il modello legge e su cui decide. Il tool
    resta (serve i margini, e toglierlo li toglierebbe insieme ai coperti), ma
    dice solo cio' che per un negozio e' vero."""
    tools = {t["function"]["name"]: t["function"]["description"]
             for t in fw._chat_tools_gruppo(SETTORE_RETAIL)}
    assert "coperti" not in tools["gruppo_margini_coperti"].lower()
    assert "scontrino" not in tools["gruppo_margini_coperti"].lower()
    assert "margine" in tools["gruppo_margini_coperti"].lower()


def test_i_tool_di_gruppo_restano_tutti_disponibili_al_negozio():
    """Cambia la descrizione, non l'insieme: un negozio deve poter confrontare
    i suoi punti vendita come prima."""
    assert ([t["function"]["name"] for t in fw._chat_tools_gruppo(SETTORE_RETAIL)]
            == [t["function"]["name"] for t in fw._CHAT_TOOLS_GRUPPO])


@pytest.mark.parametrize("settore", [SETTORE_RISTORAZIONE, None, "", "valore_ignoto"])
def test_i_tool_di_gruppo_di_un_ristorante_sono_l_oggetto_di_oggi(settore):
    """Identita', non uguaglianza: una copia significherebbe che qualcuno ha
    ricostruito la lista, ed e' il punto in cui un testo si perde."""
    assert fw._chat_tools_gruppo(settore) is fw._CHAT_TOOLS_GRUPPO


def test_deviare_le_descrizioni_non_muta_la_costante_condivisa():
    """`_CHAT_TOOLS_GRUPPO` e' di modulo: mutarla la cambierebbe per TUTTI i
    processi, ristoranti compresi, e il bug sarebbe intermittente (il primo
    negozio che apre la chat rovina i ristoranti di quel processo).

    Il confronto NON puo' essere «prima == dopo» letto dalla costante stessa:
    un mutante che la riscrive in place la cambia gia' alla prima chiamata, e
    il confronto resta verde. Si misura invece che un RISTORANTE, chiamato
    DOPO un negozio, riceva ancora le descrizioni di ieri."""
    fw._chat_tools_gruppo(SETTORE_RETAIL)
    dopo = {t["function"]["name"]: t["function"]["description"]
            for t in fw._chat_tools_gruppo(SETTORE_RISTORAZIONE)}
    assert "coperti" in dopo["gruppo_margini_coperti"].lower(), (
        "un negozio ha rovinato le descrizioni dei ristoranti nello stesso processo"
    )
    assert "pesce" in dopo["gruppo_spesa"].lower()


def test_api_classify_ricade_sulla_sede_se_manca_l_utente(monkeypatch):
    """Simmetria col fallback locale di `worker_client`: senza, lo STESSO
    chiamante otterrebbe un settore diverso a seconda che il worker HTTP sia
    raggiungibile, e il sintomo sarebbe indistinguibile da «il prompt retail
    non funziona»."""
    ricevuti: list = []

    def _finta(**kw):
        ricevuti.append(kw)
        return ["ARTICOLO DI VENDITA"], ["alta"]

    import services.ai_service as ai
    monkeypatch.setattr(ai, "classifica_con_ai", _finta)
    monkeypatch.setattr(ai, "carica_memoria_completa", lambda *a, **k: None)
    monkeypatch.setattr(ai, "set_ai_context", lambda *a, **k: None)
    monkeypatch.setattr(ai, "ai_degradata", lambda: False)
    monkeypatch.setattr("services.settore_service.settore_utente",
                        lambda uid, sb=None: SETTORE_RISTORAZIONE)
    monkeypatch.setattr("services.settore_service.settore_sede",
                        lambda rid, sb=None: SETTORE_RETAIL)
    monkeypatch.setattr(fw, "_check_rate_limit", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    richiesta = MagicMock()
    richiesta.client = None
    richiesta.headers = {}

    fw.classify(richiesta, fw.ClassifyRequest(descrizioni=["MARTELLO"], ristorante_id="rid-1"))
    assert ricevuti[-1]["settore"] == SETTORE_RETAIL

    fw.classify(richiesta, fw.ClassifyRequest(descrizioni=["MARTELLO"], user_id="u-1",
                                              ristorante_id="rid-1"))
    assert ricevuti[-1]["settore"] == SETTORE_RISTORAZIONE, "la sede ha vinto sull'account"

    fw.classify(richiesta, fw.ClassifyRequest(descrizioni=["MARTELLO"]))
    assert ricevuti[-1]["settore"] is None


def _tools_gruppo_offerti(settore, monkeypatch):
    """La lista che arriva DAVVERO al loop nel ramo catena.

    Senza questo, i quattro presidi su `_chat_tools_gruppo` provano che la
    funzione e' corretta, non che qualcuno la usi: un mutante che rimette
    `_CHAT_TOOLS_GRUPPO` al call site sopravvive a tutta la suite. E' la stessa
    famiglia del presidio gia' smascherato in questa fase — «il settore non
    arrivava dall'endpoint al prompt» — chiuso li' e riaperto qui.
    """
    catturati = {}

    def _loop(client, messages, tools, esegui, log_ctx=""):
        catturati["descrizioni"] = {
            t["function"]["name"]: t["function"]["description"] for t in tools
        }
        return ("ok", 1, 1)

    sb = _sb()
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(count=3)
    sb.rpc.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=1)))

    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda auth: dict(USER))
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (30, True))
    monkeypatch.setattr(fw, "_chat_domande_oggi", lambda *a, **k: 1)
    monkeypatch.setattr(fw, "_gruppo_chat_disabilitata", lambda uid, s: False)
    monkeypatch.setattr(fw, "_build_chat_system_prompt_catena", lambda *a, **k: "prompt")
    monkeypatch.setattr(fw, "_chat_loop_openai", _loop)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda uid, sb=None: settore)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    fw.chat_ai(
        fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="chi va meglio?")],
                       contesto="catena"),
        authorization="Bearer t",
    )
    return catturati["descrizioni"]


def test_la_catena_di_un_negozio_riceve_davvero_le_descrizioni_deviate(monkeypatch):
    d = _tools_gruppo_offerti(SETTORE_RETAIL, monkeypatch)
    assert "coperti" not in d["gruppo_margini_coperti"].lower(), (
        "l'endpoint offre ancora la description con i coperti: il fix e' nella "
        "funzione ma non nel punto che la chiama"
    )
    assert "margine" in d["gruppo_margini_coperti"].lower()


def test_la_catena_di_un_ristorante_riceve_le_descrizioni_di_ieri(monkeypatch):
    d = _tools_gruppo_offerti(SETTORE_RISTORAZIONE, monkeypatch)
    atteso = {t["function"]["name"]: t["function"]["description"]
              for t in fw._CHAT_TOOLS_GRUPPO}
    assert d == atteso
