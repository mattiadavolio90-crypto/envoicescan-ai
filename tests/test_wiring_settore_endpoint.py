"""I gate del settore provati nei PUNTI CHE LI CHIAMANO, non nel loro corpo.

Questa fase ha pagato lo stesso difetto **quattro volte**, e ogni volta il codice
era corretto: era il presidio a misurare la funzione invece del suo uso.

1. il settore non arrivava da `chat_ai` a `_build_chat_system_prompt` — 20 test
   verdi sul prompt, mutante vivo;
2. `_chat_tools_gruppo` chiamata solo dai test: il mutante che rimetteva
   `_CHAT_TOOLS_GRUPPO` al call site sopravviveva a **tutta** la suite;
3. `_topics_per_settore`: idem, in due endpoint;
4. `_pagine_con_settore`: idem, ed e' il piu' grave — e' il gate della **Fase 3**,
   quello che spegne le tab a un negozio. Con `raw=None` (il default di quasi
   tutti gli account) un mutante al call site fa tornare `None`, e **nessuno**
   dei `tab_off_*` arriva al client: gli spegnimenti si spengono in silenzio, su
   login e a ogni refresh di sessione, senza che un test diventi rosso.

La regola che questo file incarna: **provare la funzione non prova che qualcuno
la usi**. Per ogni gate, si muta il CALL SITE, non solo il corpo.
"""
from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw
from config.constants import SETTORE_RETAIL, SETTORE_RISTORAZIONE

UTENTE = {
    "id": "u-1", "email": "negozio@x.it", "nome_ristorante": "NEGOZIO",
    "pagine_abilitate": None, "tema": "dark", "privacy_accepted_at": None,
}


def _sb_vuoto():
    sb = MagicMock()
    q = MagicMock()
    sb.table.return_value = q
    for m in ("select", "eq", "is_", "gte", "lte", "in_", "single", "limit", "order", "not_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[], count=1)
    return sb


# ── _pagine_con_settore: login e /me ─────────────────────────────────────

def _pagine_da_login(settore, monkeypatch):
    monkeypatch.setattr(fw, "_check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr("services.auth_service.verifica_credenziali",
                        lambda e, p: (dict(UTENTE), None))
    monkeypatch.setattr("services.session_service.crea_sessione",
                        lambda *a, **k: "tok-1")
    monkeypatch.setattr(fw, "_get_supabase_client", _sb_vuoto)
    monkeypatch.setattr("services.settore_service.settore_utente",
                        lambda uid, sb=None: settore)
    richiesta = MagicMock()
    richiesta.client = None
    richiesta.headers = {}
    resp = fw.auth_login(fw.LoginRequest(email="negozio@x.it", password="x"), richiesta)
    return resp.user.pagine_abilitate


def _pagine_da_me(settore, monkeypatch):
    monkeypatch.setattr("services.auth_service.verifica_sessione_da_cookie",
                        lambda t: dict(UTENTE))
    monkeypatch.setattr(fw, "_get_supabase_client", _sb_vuoto)
    monkeypatch.setattr(fw, "_resolve_sede_attiva", lambda u, sb: (None, "NEGOZIO"))
    monkeypatch.setattr("services.settore_service.settore_utente",
                        lambda uid, sb=None: settore)
    return fw.auth_me(authorization="Bearer tok-1").pagine_abilitate


@pytest.mark.parametrize("via", ["login", "me"])
def test_un_negozio_riceve_gli_spegnimenti_dall_endpoint(via, monkeypatch):
    """Il caso che la docstring di `_pagine_con_settore` chiama «quello che
    conta»: `pagine_abilitate` NULL, il default di quasi tutti gli account."""
    pagine = (_pagine_da_login if via == "login" else _pagine_da_me)(
        SETTORE_RETAIL, monkeypatch,
    )
    assert pagine is not None, (
        f"via {via}: un negozio ha ricevuto None, quindi NESSUN tab_off_* "
        "arriva al client e gli spegnimenti della Fase 3 sono inerti"
    )
    # Le tre chiavi SCRITTE A MANO, non lette da `_TAB_OFF_PER_SETTORE`: leggerle
    # di la' farebbe cambiare insieme codice e atteso, e un mutante sulla
    # costante sopravvivrebbe (e' l'errore «lista attesa scritta dentro il test»
    # gia' smascherato in Fase 3).
    for chiave in ("tab_off_workspace_foodcost", "tab_off_margini_coperti",
                   "tab_off_margini_analisi"):
        assert chiave in pagine, f"via {via}: manca {chiave}"


@pytest.mark.parametrize("via", ["login", "me"])
def test_un_ristorante_non_riceve_nessuno_spegnimento(via, monkeypatch):
    """`None` resta `None`: e' il vincolo — per un ristorante non cambia niente,
    nemmeno la forma del campo."""
    pagine = (_pagine_da_login if via == "login" else _pagine_da_me)(
        SETTORE_RISTORAZIONE, monkeypatch,
    )
    assert pagine is None


@pytest.mark.parametrize("via", ["login", "me"])
def test_gli_spegnimenti_si_sommano_ai_permessi_gia_impostati(via, monkeypatch):
    """Un negozio con permessi espliciti non deve perderli: il gate aggiunge, non
    sostituisce."""
    monkeypatch.setitem(UTENTE, "pagine_abilitate", {"margini": True, "agenda": True})
    try:
        pagine = (_pagine_da_login if via == "login" else _pagine_da_me)(
            SETTORE_RETAIL, monkeypatch,
        )
        assert "margini" in pagine and "agenda" in pagine
        assert "tab_off_margini_coperti" in pagine
    finally:
        UTENTE["pagine_abilitate"] = None


# ── _topics_per_settore: home_config GET e POST ──────────────────────────

def _topics_da_config(settore, monkeypatch, post=False):
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda a: dict(UTENTE))
    monkeypatch.setattr(fw, "_get_supabase_client", _sb_vuoto)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda u, s: "rid-1")
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda *a, **k: {})
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda u, s: (0, False))
    monkeypatch.setattr("services.db_service.get_price_alert_threshold", lambda *a, **k: 5.0)
    monkeypatch.setattr("services.settore_service.settore_utente",
                        lambda uid, sb=None: settore)
    if post:
        monkeypatch.setattr("services.db_service.set_price_alert_threshold", lambda *a, **k: None)
        resp = fw.home_config_post(fw.ConfigUpdateRequest(), authorization="Bearer t")
    else:
        resp = fw.home_config_get(authorization="Bearer t")
    return {t.key: t for t in resp.topics}


@pytest.mark.parametrize("post", [False, True], ids=["get", "post"])
def test_il_configuratore_di_un_negozio_non_offre_i_coperti(post, monkeypatch):
    topics = _topics_da_config(SETTORE_RETAIL, monkeypatch, post=post)
    assert "coperti_anomalia" not in topics, (
        "l'endpoint offre ancora il topic dei coperti: il gate e' nella funzione "
        "ma non nel punto che la chiama"
    )
    assert "food cost" not in topics["fatturato_mancante"].descrizione.lower()


@pytest.mark.parametrize("post", [False, True], ids=["get", "post"])
def test_il_configuratore_di_un_ristorante_e_quello_di_ieri(post, monkeypatch):
    topics = _topics_da_config(SETTORE_RISTORAZIONE, monkeypatch, post=post)
    atteso = {k: d for (k, _l, _b, d) in fw._CONFIG_TOPICS}
    assert {k: t.descrizione for k, t in topics.items()} == atteso
