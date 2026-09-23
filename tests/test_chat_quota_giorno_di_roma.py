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


def test_il_messaggio_di_limite_dice_quando_si_azzera():
    """Il 429 prometteva 'Riprova domani', che col fuso vecchio era falso.

    Ora la finestra e' il giorno di Roma, quindi il contatore si azzera davvero
    a mezzanotte — e il messaggio lo dice, invece di lasciarlo indovinare.
    """
    import inspect

    sorgente = inspect.getsource(fw.chat_ai)
    assert "Il contatore si azzera a mezzanotte" in sorgente
    assert "Riprova domani" not in sorgente, (
        "'Riprova domani' non dice quando: col contatore sul giorno di Roma "
        "l'azzeramento e' a mezzanotte, e il messaggio deve dirlo"
    )


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
    messaggi = " | ".join(r.getMessage() for r in caplog.records)
    assert "limite giornaliero raggiunto" in messaggi, (
        "il blocco non ha lasciato traccia nei log: un rifiuto resta invisibile "
        f"e non e' misurabile. Log visti: {messaggi!r}"
    )
