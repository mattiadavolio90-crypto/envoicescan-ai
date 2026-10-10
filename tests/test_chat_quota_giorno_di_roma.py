"""La quota chat: messaggi di blocco, budget per piano, payload della RPC.

Le FINESTRE (giorno e mese di Roma) dal 10/10/2026 vivono solo in SQL, nella
RPC `chat_crediti_stato`: sono provate su un Postgres vero in
`tests/test_sql_chat_crediti.py` (e per la vecchia RPC in
`tests/test_sql_funzioni_pagina.py`). La storia del fuso, sotto, resta perche'
spiega i messaggi.

Contando in UTC il contatore si azzerava all'01:00 (CET) o alle 02:00 (CEST) di
Roma: chi chattava dopo mezzanotte spendeva la quota del giorno prima, e il
messaggio "Riprova domani" era falso nelle due direzioni. Misurato sul DB live
il 23/09/2026: 1 riga su 95 gia' addebitata al giorno sbagliato
(2026-06-17T23:25Z = 18/06 01:25 a Roma).

I casi si scelgono DOVE I DUE MONDI DIVERGONO: un'ora qualunque non distingue
UTC da Roma e lascia vivo il mutante. Qui la finestra utile e' fra mezzanotte e
le 02:00 di Roma, nei due regimi CET/CEST.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import services.fastapi_worker as fw



def test_un_blocco_lascia_traccia_nei_log(monkeypatch, caplog):
    """Un rifiuto deve essere osservabile, o la prossima decisione e' cieca.

    Il ramo 429 non scriveva nulla: ne' su DB (la RPC ritorna -1 senza inserire)
    ne' sul logger. Percio' "nessun cliente e' mai stato bloccato" non era una
    misura ma l'assenza dello strumento di misura — l'errore che ha aperto
    questa fase. Il presidio esegue il blocco e pretende la riga di log.
    """
    import logging

    from fastapi import HTTPException

    registro: dict = {}

    class _RpcBloccata:
        def execute(self):
            return MagicMock(data={"esito": "giorno", "oggi": 30, "mese": 30, "ricarica": 0})

    client = MagicMock()
    client.rpc.return_value = _RpcBloccata()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda *a, **k: {"id": "u1", "piano": "base"})
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda *a, **k: "r1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda *a, **k: (10, False))
    monkeypatch.setattr("services.get_supabase_client", lambda *a, **k: client)
    monkeypatch.setattr(
        "services.settore_service.settore_utente", lambda *a, **k: "ristorazione"
    )

    body = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="ciao")])

    with caplog.at_level(logging.WARNING):
        with pytest.raises(HTTPException) as ei:
            fw.chat_ai(body, "Bearer x")

    assert ei.value.status_code == 429, f"atteso 429, ricevuto {ei.value.status_code}"

    # Il testo che il cliente legge davvero, non quello scritto nel file: una
    # guardia su `inspect.getsource` sopravvive a un mutante che sposta la frase
    # in un commento e tronca il messaggio (provato dal reviewer: 7/7 verdi).
    detail = str(ei.value.detail)
    assert "si azzera a mezzanotte" in detail, (
        "il 429 non dice quando riparte: «per oggi» da solo non basta, il "
        f"cliente non sa se aspettare un'ora o un giorno. Detail: {detail!r}"
    )
    assert "domani" not in detail, (
        "«domani» e' l'indicazione che era falsa col fuso UTC e resta imprecisa "
        f"con quello di Roma: l'azzeramento e' a mezzanotte. Detail: {detail!r}"
    )
    messaggi = " | ".join(r.getMessage() for r in caplog.records)
    assert "limite giornaliero raggiunto" in messaggi, (
        "il blocco non ha lasciato traccia nei log: un rifiuto resta invisibile "
        f"e non e' misurabile. Log visti: {messaggi!r}"
    )


# ─── budget mensile: il vincolo vero, col giorno come freno ───────────────

def test_i_tetti_giornalieri_derivano_dal_budget_mensile():
    """I due numeri non si scrivono a mano: il giorno e' il 10% del mese.

    Due tabelle di costanti divergono al primo ritocco di una sola — e qui la
    divergenza non sarebbe visibile, perche' l'enforcement usa il giornaliero e
    il messaggio al cliente il mensile.

    ATTENZIONE al modo in cui questo si verifica. Confrontare
    `CHAT_LIMITI_PIANO[p]` con `_chat_limite_giornaliero_da_mensile(mese)` NON
    basta: se qualcuno scrive il dict a mano CON I VALORI GIUSTI, i due lati
    coincidono e il test passa — atteso e ottenuto si muovono insieme, la
    trappola «costante letta dai due lati». Il code-reviewer l'ha dimostrato
    con un mutante che scriveva 30/60/90 a mano: sopravvissuto a 15.836 test.
    Percio' qui si verifica il MECCANISMO: cambiata la percentuale, i tetti
    devono seguire. Una tabella hardcodata non segue.
    """
    import importlib

    for piano, mese in fw.CHAT_BUDGET_MENSILE_PIANO.items():
        atteso = fw._chat_limite_giornaliero_da_mensile(mese)
        assert fw.CHAT_LIMITI_PIANO[piano] == atteso, (
            f"piano {piano}: tetto giornaliero {fw.CHAT_LIMITI_PIANO[piano]} "
            f"non deriva dal budget mensile {mese} (atteso {atteso})"
        )

    # La prova vera: con una percentuale diversa i tetti DEVONO cambiare.
    # Si rilegge il sorgente del modulo e si riesegue il solo blocco delle
    # costanti con la percentuale mutata: se `CHAT_LIMITI_PIANO` e' costruito
    # dalla comprehension segue, se e' scritto a mano resta fermo e il test cade.
    import inspect
    import re

    sorgente = inspect.getsource(fw)
    blocco = re.search(
        r"^CHAT_LIMITI_PIANO: Dict\[str, int\] = \{.*?^\}",
        sorgente, re.S | re.M,
    )
    assert blocco, "CHAT_LIMITI_PIANO non trovato nel sorgente"

    ns = {
        "Dict": dict,
        "CHAT_BUDGET_MENSILE_PIANO": dict(fw.CHAT_BUDGET_MENSILE_PIANO),
        # la percentuale mutata: 20% invece di 10%
        "_chat_limite_giornaliero_da_mensile": lambda b: 0 if b <= 0 else max(1, int(b * 0.20)),
    }
    exec(blocco.group(0), ns)
    ricostruito = ns["CHAT_LIMITI_PIANO"]

    assert ricostruito["base"] == 200, (
        "raddoppiando la percentuale il tetto 'base' resta "
        f"{ricostruito['base']} invece di 200: CHAT_LIMITI_PIANO non e' "
        "derivato dal budget mensile, e' scritto a mano"
    )
    assert ricostruito["pro"] == 400, (
        f"stesso problema sul piano 'pro': {ricostruito['pro']} invece di 400"
    )

    assert fw.CHAT_QUOTA_GIORNALIERA_PCT == 0.10, (
        "la percentuale e' una decisione di prodotto: il mese deve coprire "
        "almeno 10 giorni di uso pieno"
    )


def test_il_piano_free_resta_a_zero_su_entrambe_le_finestre():
    """`chat_limite_giorno = 0` e' il gate «chat non disponibile» in 5 punti del
    frontend: se la derivazione producesse 1 invece di 0, la chat comparirebbe a
    chi non l'ha nel piano."""
    assert fw.CHAT_BUDGET_MENSILE_PIANO["free"] == 0
    assert fw.CHAT_LIMITI_PIANO["free"] == 0
    assert fw._chat_limite_giornaliero_da_mensile(0) == 0


def test_un_budget_piccolo_non_diventa_un_tetto_zero():
    """Il minimo a 1 evita che un budget non nullo produca un tetto 0, che il
    frontend legge come «chat non disponibile»: il cliente perderebbe la chat
    invece di averne poca."""
    assert fw._chat_limite_giornaliero_da_mensile(5) == 1
    assert fw._chat_limite_giornaliero_da_mensile(1) == 1


def test_i_crediti_per_piano_sono_quelli_decisi():
    """Decisione di Mattia del 10/10/2026: crediti al mese per sede, una
    domanda = 3 crediti, e i numeri della landing sono questi."""
    assert fw.CHAT_BUDGET_MENSILE_PIANO == {"free": 0, "base": 1000, "plus": 1500, "pro": 2000}
    assert fw.CHAT_CREDITI_PER_DOMANDA == 3
    assert fw.CHAT_PESO_SEDE_AGGIUNTIVA == 0.5


@pytest.mark.parametrize("piani, atteso", [
    (["base"], 1000),
    (["pro"], 2000),
    (["base", "base"], 1500),                       # OFFSIDE
    (["pro"] * 5, 6000),                             # SUSHILAND: era 4.500 domande
    (["base", "base", "pro"], 3000),                 # la piu' alta piena, non la prima letta
    (["base", "free"], 1000),                        # una sede free non aggiunge
    (["free"], 0),
    ([], 0),
])
def test_il_budget_della_catena_piena_la_sede_piu_alta_meta_le_altre(piani, atteso):
    assert fw._chat_budget_da_piani(piani) == atteso


def test_il_budget_mensile_del_pool_legge_le_sedi(monkeypatch):
    """Una catena: la sede col piano piu' alto piena, le altre a meta'."""
    client = MagicMock()
    sedi = MagicMock()
    sedi.data = [{"piano": "base"}, {"piano": "base"}, {"piano": "pro"}]
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = sedi

    tot = fw._chat_budget_mensile_pool({"id": "u1", "piano": "base"}, client)
    giorno, pool = fw._chat_quota_pool({"id": "u1", "piano": "base"}, client)

    assert tot == 3000, f"pool mensile {tot}, atteso 3000 (2000 + 1000/2 + 1000/2)"
    assert (giorno, pool) == (300, True), "il tetto del giorno e' il 10% del pool"


def test_una_sede_sola_non_e_un_pool(monkeypatch):
    client = MagicMock()
    sedi = MagicMock()
    sedi.data = [{"piano": None}]
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = sedi
    # piano della sede assente: vale quello dell'account
    assert fw._chat_quota_pool({"id": "u1", "piano": "plus"}, client) == (150, False)
    assert fw._chat_budget_mensile_pool({"id": "u1", "piano": "plus"}, client) == 1500


def test_lettura_sedi_fallita_ripiega_sul_piano_della_sede(monkeypatch):
    client = MagicMock()
    client.table.side_effect = RuntimeError("rete")
    monkeypatch.setattr(fw, "_resolve_piano_effettivo", lambda u, s: "pro")
    assert fw._chat_quota_pool({"id": "u1"}, client) == (200, False)
    assert fw._chat_budget_mensile_pool({"id": "u1"}, client) == 2000


def _blocca_con(monkeypatch, esito: str, con_client: bool = False, utente=None):
    """Esegue `chat_ai` con la RPC che ritorna il codice dato, e torna il 429.

    Con `con_client=True` ritorna anche il client mockato, per poter asserire
    COSA e' stato mandato alla RPC: il mock risponde uguale a qualunque payload,
    quindi senza questa verifica si potrebbe cancellare il parametro del budget
    mensile — cioe' spegnere la feature — e la suite resterebbe verde.
    """
    from fastapi import HTTPException

    class _Rpc:
        def execute(self):
            return MagicMock(data={"esito": esito, "oggi": 100, "mese": 1000, "ricarica": 0})

    client = MagicMock()
    client.rpc.return_value = _Rpc()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        fw, "_resolve_user_from_token", lambda *a, **k: utente or {"id": "u1", "piano": "base"}
    )
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda *a, **k: "r1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda *a, **k: (100, False))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda *a, **k: 1000)
    monkeypatch.setattr("services.get_supabase_client", lambda *a, **k: client)
    monkeypatch.setattr(
        "services.settore_service.settore_utente", lambda *a, **k: "ristorazione"
    )

    body = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="ciao")])
    with pytest.raises(HTTPException) as ei:
        fw.chat_ai(body, "Bearer x")
    assert ei.value.status_code == 429
    if con_client:
        return str(ei.value.detail), client
    return str(ei.value.detail)


def test_budget_mensile_esaurito_non_dice_torna_domani(monkeypatch):
    """«mese» = crediti del mese e ricarica finiti. Dirgli «torna domani» sarebbe
    una promessa falsa: domani sara' fermo di nuovo."""
    detail = _blocca_con(monkeypatch, "mese")

    assert "questo mese" in detail, f"non nomina il mese: {detail!r}"
    assert "mezzanotte" not in detail, (
        "sta dando il messaggio del tetto GIORNALIERO a chi ha finito il mese: "
        f"{detail!r}"
    )
    # Il messaggio intero, non un pezzo: con `in` un «999» o il numero del
    # giorno al posto di quello del mese passavano (residuo 2c della fase 2).
    assert detail == (
        "Hai usato tutti i 1.000 crediti AI di questo mese. "
        "Ripartono il 1° del mese prossimo: per continuare prima "
        "puoi chiedere una ricarica fra i Servizi."
    ), detail


def test_al_collaboratore_la_ricarica_la_chiede_il_titolare(monkeypatch):
    """Un sotto-utente non ha i Servizi: il messaggio non lo manda li'."""
    from services import sotto_utenti_service as su
    monkeypatch.setattr(su, "e_sotto_utente", lambda u: True)
    detail = _blocca_con(monkeypatch, "mese")
    assert detail.endswith("il titolare puo' chiedere una ricarica."), detail
    assert "Servizi" not in detail


def test_tetto_giornaliero_esaurito_non_parla_del_mese(monkeypatch):
    """«giorno» = giorno finito, il mese ha ancora margine: torna domani."""
    detail = _blocca_con(monkeypatch, "giorno")

    assert "questo mese" not in detail, (
        f"sta dando il messaggio del budget MENSILE a chi ha finito il giorno: {detail!r}"
    )
    # «100» e' contenuto in «1.000»: solo il confronto intero distingue il
    # tetto del giorno dal budget del mese (residuo 2c della fase 2).
    assert detail == (
        "Hai raggiunto il limite di 100 crediti AI per oggi. "
        "Il contatore si azzera a mezzanotte."
    ), detail


def test_la_rpc_riceve_davvero_tetti_e_costo(monkeypatch):
    """I parametri devono ARRIVARE alla RPC, non solo essere calcolati.

    Senza questo assert si puo' cancellare il budget mensile dal payload — cioe'
    spegnere il mese e con lui la ricarica — e la suite resta verde: il
    MagicMock risponde uguale a qualunque argomento.
    """
    _, client = _blocca_con(monkeypatch, "mese", con_client=True)

    assert client.rpc.call_count == 1, f"chiamate alla RPC: {client.rpc.call_count}"
    nome, payload = client.rpc.call_args[0]
    assert nome == "chat_crediti_check_and_log"
    assert payload == {
        "p_user_id": "u1",
        "p_ristorante_id": "r1",
        "p_pool": False,
        "p_crediti_giorno": 100,
        "p_crediti_mese": 1000,
        "p_costo": 3,
    }, payload


@pytest.mark.parametrize("data", [None, -1, 1, {"esito": "boh"}, {}])
def test_una_risposta_illeggibile_della_rpc_rifiuta_la_domanda(monkeypatch, data):
    """Fail-closed: un ritorno che non si capisce non e' un via libera (il
    vecchio contratto -1/-2/N non vale piu')."""
    from fastapi import HTTPException

    client = MagicMock()
    client.rpc.return_value.execute.return_value = MagicMock(data=data)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda *a, **k: {"id": "u1", "piano": "base"})
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda *a, **k: "r1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda *a, **k: (100, False))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda *a, **k: 1000)
    monkeypatch.setattr("services.get_supabase_client", lambda *a, **k: client)
    monkeypatch.setattr("services.settore_service.settore_utente", lambda *a, **k: "ristorazione")
    body = fw.ChatRequest(messages=[fw.ChatMessage(role="user", content="ciao")])
    with pytest.raises(HTTPException) as ei:
        fw.chat_ai(body, "Bearer x")
    assert ei.value.status_code == 503


def test_i_due_fallback_sul_piano_sconosciuto_restano_simmetrici():
    """Mese e giorno devono ripiegare sullo STESSO piano.

    `_chat_limite_per_piano` e `_chat_budget_mensile_per_piano` hanno ciascuna un
    fallback per i piani non riconosciuti. Se divergessero, un cliente con un
    piano scritto male avrebbe budget mensile 'base' e tetto giornaliero 'pro'
    (o viceversa): il docstring lo dichiara, ma nessun test lo verificava — un
    mutante del reviewer che spostava un solo fallback su 'pro' sopravviveva a
    15.836 test.
    """
    for sconosciuto in ("enterprise", "", None, "  BASE  ", "premium"):
        giorno = fw._chat_limite_per_piano(sconosciuto)
        mese = fw._chat_budget_mensile_per_piano(sconosciuto)
        atteso_giorno = fw._chat_limite_giornaliero_da_mensile(mese)
        assert giorno == atteso_giorno, (
            f"piano {sconosciuto!r}: il tetto giornaliero ({giorno}) non e' il "
            f"10% del budget mensile ({mese}, atteso {atteso_giorno}) — i due "
            "fallback sono divergenti"
        )

    # E il fallback e' 'base', non un piano piu' generoso: un piano scritto male
    # non deve regalare la quota del pro.
    assert fw._chat_budget_mensile_per_piano("enterprise") == fw.CHAT_BUDGET_MENSILE_PIANO["base"]
    assert fw._chat_limite_per_piano("enterprise") == fw.CHAT_LIMITI_PIANO["base"]


def test_il_default_del_limite_giorno_non_e_quello_vecchio():
    """`ChatConfig.chat_limite_giorno` ha un default, usato quando il valore vero
    non arriva. Lasciarlo a 10 (il tetto pre-23/09) mostrerebbe al cliente un
    numero che non esiste piu' in nessun piano."""
    import inspect

    campi = fw.ConfigResponse.model_fields
    default = campi["chat_limite_giorno"].default
    assert default == fw.CHAT_LIMITI_PIANO["base"], (
        f"il default e' {default} ma il tetto 'base' ora e' "
        f"{fw.CHAT_LIMITI_PIANO['base']}: il contatore mostrerebbe il valore "
        "vecchio quando quello vero non arriva"
    )
