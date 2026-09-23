"""La quota chat si conta sul giorno del ristoratore, non su quello del server.

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

from datetime import datetime, time, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

import services.fastapi_worker as fw

ROMA = ZoneInfo("Europe/Rome")


class _FakeQuery:
    """Registra il `gte` su created_at, che e' la decisione da provare."""

    def __init__(self, registro):
        self._r = registro

    def select(self, *a, **k):
        return self

    def gte(self, campo, valore):
        self._r["campo"] = campo
        self._r["inizio"] = valore
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return MagicMock(count=0)


def _inizio_finestra(monkeypatch, istante_utc: datetime) -> datetime:
    """Esegue il contatore con l'orologio fermo e ritorna l'inizio della finestra."""
    registro: dict = {}
    client = MagicMock()
    client.table.return_value = _FakeQuery(registro)

    class _Orologio(datetime):
        @classmethod
        def now(cls, tz=None):
            return istante_utc.astimezone(tz) if tz else istante_utc

    monkeypatch.setattr("datetime.datetime", _Orologio)
    fw._chat_domande_oggi("rid", "uid", client)
    assert registro["campo"] == "created_at"
    return datetime.fromisoformat(registro["inizio"])


@pytest.mark.parametrize(
    "istante_roma, giorno_atteso, regime",
    [
        # 00:30 di Roma: a UTC e' ancora il giorno PRIMA. E' il caso che
        # distingue i due fusi, ed e' quello capitato in produzione.
        (datetime(2026, 7, 18, 0, 30, tzinfo=ROMA), "2026-07-18", "CEST"),
        (datetime(2026, 1, 18, 0, 30, tzinfo=ROMA), "2026-01-18", "CET"),
        # 01:25 di Roma: l'ora esatta della riga trovata a DB il 18/06.
        (datetime(2026, 6, 18, 1, 25, tzinfo=ROMA), "2026-06-18", "CEST"),
        # Tarda sera: qui i due fusi coincidono, la finestra non deve spostarsi.
        (datetime(2026, 7, 17, 22, 30, tzinfo=ROMA), "2026-07-17", "CEST"),
    ],
)
def test_la_finestra_e_il_giorno_di_roma(monkeypatch, istante_roma, giorno_atteso, regime):
    inizio = _inizio_finestra(monkeypatch, istante_roma.astimezone(timezone.utc))
    atteso = datetime.combine(
        datetime.fromisoformat(giorno_atteso).date(), time.min, tzinfo=ROMA
    )
    assert inizio == atteso, (
        f"{regime}: alle {istante_roma:%d/%m %H:%M} di Roma la finestra deve partire "
        f"dalla mezzanotte del {giorno_atteso}, non da {inizio.isoformat()}"
    )


def test_dopo_mezzanotte_la_finestra_non_e_quella_del_giorno_prima(monkeypatch):
    """Il caso di produzione, scritto come lo vive il cliente.

    Alle 00:30 del 18/07 il ristoratore ha appena iniziato la giornata: le
    domande fatte il 17 non devono pesare sulla sua quota.
    """
    istante = datetime(2026, 7, 18, 0, 30, tzinfo=ROMA)
    inizio = _inizio_finestra(monkeypatch, istante.astimezone(timezone.utc))

    mezzanotte_utc = datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc)
    assert inizio > mezzanotte_utc, (
        "la finestra parte dalla mezzanotte UTC del giorno prima: il cliente "
        "spende la quota del 17 mentre a Roma e' gia' il 18"
    )
    assert inizio == datetime(2026, 7, 18, 0, 0, tzinfo=ROMA)




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
            return MagicMock(data=-1)  # -1 = limite raggiunto

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

    assert ricostruito["base"] == 60, (
        "raddoppiando la percentuale il tetto 'base' resta "
        f"{ricostruito['base']} invece di 60: CHAT_LIMITI_PIANO non e' "
        "derivato dal budget mensile, e' scritto a mano"
    )
    assert ricostruito["pro"] == 180, (
        f"stesso problema sul piano 'pro': {ricostruito['pro']} invece di 180"
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


def test_il_budget_mensile_del_pool_somma_le_sedi(monkeypatch):
    """Come il gemello giornaliero: una catena somma il budget di ogni sede."""
    client = MagicMock()
    sedi = MagicMock()
    sedi.data = [{"piano": "base"}, {"piano": "base"}, {"piano": "pro"}]
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = sedi

    tot = fw._chat_budget_mensile_pool({"id": "u1", "piano": "base"}, client)

    atteso = (
        fw.CHAT_BUDGET_MENSILE_PIANO["base"] * 2
        + fw.CHAT_BUDGET_MENSILE_PIANO["pro"]
    )
    assert tot == atteso, f"pool mensile {tot}, atteso {atteso} (300+300+900)"


def _blocca_con(monkeypatch, ritorno_rpc: int, con_client: bool = False):
    """Esegue `chat_ai` con la RPC che ritorna il codice dato, e torna il 429.

    Con `con_client=True` ritorna anche il client mockato, per poter asserire
    COSA e' stato mandato alla RPC: il mock risponde uguale a qualunque payload,
    quindi senza questa verifica si potrebbe cancellare il parametro del budget
    mensile — cioe' spegnere la feature — e la suite resterebbe verde.
    """
    from fastapi import HTTPException

    class _Rpc:
        def execute(self):
            return MagicMock(data=ritorno_rpc)

    client = MagicMock()
    client.rpc.return_value = _Rpc()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda *a, **k: {"id": "u1", "piano": "base"})
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda *a, **k: "r1")
    monkeypatch.setattr(fw, "_chat_quota_pool", lambda *a, **k: (30, False))
    monkeypatch.setattr(fw, "_chat_budget_mensile_pool", lambda *a, **k: 300)
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
    """-2 = mese finito. Dirgli «torna domani» sarebbe una promessa falsa: domani
    sara' fermo di nuovo. E' lo stesso difetto del «Riprova domani» corretto
    poche ore prima, un piano piu' su."""
    detail = _blocca_con(monkeypatch, -2)

    assert "questo mese" in detail, f"non nomina il mese: {detail!r}"
    assert "1°" in detail or "1\u00b0" in detail, (
        f"non dice quando riparte il budget: {detail!r}"
    )
    assert "mezzanotte" not in detail, (
        "sta dando il messaggio del tetto GIORNALIERO a chi ha finito il mese: "
        f"{detail!r}"
    )
    assert "300" in detail, f"non dice quante domande aveva: {detail!r}"


def test_tetto_giornaliero_esaurito_non_parla_del_mese(monkeypatch):
    """-1 = giorno finito, il mese ha ancora margine: il cliente torna domani."""
    detail = _blocca_con(monkeypatch, -1)

    assert "mezzanotte" in detail, f"non dice quando riparte: {detail!r}"
    assert "questo mese" not in detail, (
        f"sta dando il messaggio del budget MENSILE a chi ha finito il giorno: {detail!r}"
    )
    assert "30" in detail, f"non dice qual era il tetto di oggi: {detail!r}"


def test_la_rpc_riceve_davvero_il_budget_mensile(monkeypatch):
    """Il parametro del mese deve ARRIVARE alla RPC, non solo essere calcolato.

    Senza questo assert si puo' cancellare `p_limite_mensile` dal payload — cioe'
    disattivare l'intero budget mensile — e la suite resta verde: il MagicMock
    risponde uguale a qualunque argomento. E' il difetto «fix server senza
    presidio sul client», qui fra codice e RPC.
    """
    _, client = _blocca_con(monkeypatch, -2, con_client=True)

    assert client.rpc.call_count == 1, f"chiamate alla RPC: {client.rpc.call_count}"
    nome, payload = client.rpc.call_args[0]
    assert nome == "chat_usage_check_and_log"

    assert "p_limite_mensile" in payload, (
        "il budget mensile non arriva alla RPC: la feature e' spenta e nessun "
        f"altro test se ne accorge. Payload: {sorted(payload)}"
    )
    assert payload["p_limite_mensile"] == 300, (
        f"budget mensile sbagliato nel payload: {payload['p_limite_mensile']}"
    )
    # Gli altri quattro non devono sparire nel passaggio alla firma nuova.
    for atteso in ("p_user_id", "p_ristorante_id", "p_limite", "p_pool"):
        assert atteso in payload, f"manca {atteso} nel payload: {sorted(payload)}"
    assert payload["p_limite"] == 30, (
        f"tetto giornaliero sbagliato nel payload: {payload['p_limite']}"
    )


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


def test_la_finestra_del_mese_parte_dal_primo_a_mezzanotte_di_roma(monkeypatch):
    """`_chat_domande_mese` e' l'unico punto dove la finestra del mese vive in
    Python: e' la gemella della RPC, e se divergono nessuno se ne accorge.

    Il caso si sceglie DOVE I DUE MONDI DIVERGONO: a meta' mese, dove «dal primo»
    e «da oggi» danno risultati diversi. Un mutante che sostituisce
    `_oggi.replace(day=1)` con `_oggi` conta solo la giornata e sopravvive a
    qualunque test che usi il primo del mese.
    """
    registro: dict = {}

    class _Q:
        def select(self, *a, **k):
            return self

        def gte(self, campo, valore):
            registro["inizio"] = valore
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return MagicMock(count=7)

    client = MagicMock()
    client.table.return_value = _Q()

    # 18 luglio: se la finestra fosse «oggi» partirebbe dal 18, non dal 1°.
    istante = datetime(2026, 7, 18, 14, 0, tzinfo=ROMA)

    class _Orologio(datetime):
        @classmethod
        def now(cls, tz=None):
            return istante.astimezone(tz) if tz else istante

    monkeypatch.setattr("datetime.datetime", _Orologio)
    assert fw._chat_domande_mese("rid", "uid", client) == 7

    inizio = datetime.fromisoformat(registro["inizio"])
    atteso = datetime(2026, 7, 1, 0, 0, tzinfo=ROMA)
    assert inizio == atteso, (
        f"la finestra del mese parte da {inizio.isoformat()} invece che dal "
        f"primo a mezzanotte di Roma ({atteso.isoformat()}): il budget mensile "
        "conterebbe una finestra sbagliata"
    )


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
