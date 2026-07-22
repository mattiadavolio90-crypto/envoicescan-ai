"""Test `_fatture_arrivate_ieri_gruppo` (Home catena, 22/07).

Contesto: la Home catena deve accennare alle fatture comparse ieri per TUTTO il
gruppo, sommando due sorgenti che convivono senza sovrapporsi:

  A) `fatture` (già assegnate a un PV) — il caso normale quando ogni sede ha la
     propria P.IVA (SUSHILAND) o quando il routing per indirizzo ha già
     smistato la fattura da solo;
  B) `fatture_queue` status='da_assegnare' (in coda) — il caso di una P.IVA
     condivisa fra sedi (OFFSIDE), dove l'app non sa a quale locale
     appartenga la fattura finché non la assegni a mano.

Nessun doppio conteggio: una fattura è O in coda in attesa O già smistata
('done', nata in `fatture`) — mai entrambe. La STESSA formula deve valere per
OFFSIDE-oggi (tutto in coda), OFFSIDE-futuro (routing per indirizzo maturo,
tutto assegnato) e SUSHILAND (già tutto assegnato): cambia solo il peso fra le
due sorgenti, non il calcolo.
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

from services.routers.gruppo import _fatture_arrivate_ieri_gruppo  # noqa: E402

IDS = ["pv-a", "pv-b"]
USER_ID = "user-offside"

_IERI = (datetime.now(tz=ZoneInfo("Europe/Rome")) - timedelta(days=1)).date()


class _FakeQuery:
    def __init__(self, rows, count=None):
        self._rows = rows
        self._count = count if count is not None else len(rows)

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def lt(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows, "count": self._count})()


class _FakeSB:
    """Instrada `fatture` -> righe assegnate ai PV, `fatture_queue` -> conteggio coda."""

    def __init__(self, fatture_rows=None, coda_count=0):
        self._fatture = fatture_rows or []
        self._coda_count = coda_count

    def table(self, name):
        if name == "fatture":
            return _FakeQuery(list(self._fatture))
        if name == "fatture_queue":
            return _FakeQuery([], count=self._coda_count)
        return _FakeQuery([])


def _riga(file_origine):
    return {"file_origine": file_origine}


def test_conta_solo_assegnate_ai_pv():
    sb = _FakeSB(fatture_rows=[_riga("F1.xml"), _riga("F2.xml")], coda_count=0)
    out = _fatture_arrivate_ieri_gruppo(sb, USER_ID, IDS)
    assert out == {"n_assegnate": 2, "n_in_coda": 0}


def test_conta_solo_coda_caso_offside():
    sb = _FakeSB(fatture_rows=[], coda_count=11)
    out = _fatture_arrivate_ieri_gruppo(sb, USER_ID, IDS)
    assert out == {"n_assegnate": 0, "n_in_coda": 11}


def test_somma_entrambe_le_sorgenti_senza_sovrapporsi():
    # Caso misto: alcune fatture già assegnate (routing per indirizzo riuscito),
    # altre ancora in coda (P.IVA condivisa, indirizzo non riconosciuto).
    sb = _FakeSB(fatture_rows=[_riga("F1.xml")], coda_count=3)
    out = _fatture_arrivate_ieri_gruppo(sb, USER_ID, IDS)
    assert out["n_assegnate"] == 1
    assert out["n_in_coda"] == 3


def test_file_origine_distinti_non_righe():
    # 3 righe ma 2 documenti: conta 2 fatture, non 3 (stessa regola della Home PV).
    sb = _FakeSB(fatture_rows=[_riga("F1.xml"), _riga("F1.xml"), _riga("F2.xml")])
    out = _fatture_arrivate_ieri_gruppo(sb, USER_ID, IDS)
    assert out["n_assegnate"] == 2


def test_nessuna_novita_tutto_zero():
    sb = _FakeSB(fatture_rows=[], coda_count=0)
    out = _fatture_arrivate_ieri_gruppo(sb, USER_ID, IDS)
    assert out == {"n_assegnate": 0, "n_in_coda": 0}
