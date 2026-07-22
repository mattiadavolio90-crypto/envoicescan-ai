"""Test Fase 3 (Strada A) — apertura "fatture arrivate ieri" per sedi SDI.

Contesto: una sede con SDI attivo che NON inserisce l'incasso giornaliero (es.
OFFSIDE) non avrebbe mai un'apertura positiva nel briefing (niente MOL in
finestra, niente incasso di ieri) -> resterebbe una pura to-do list. Il suo dato
fresco e' l'arrivo delle fatture. Questi test blindano:

- `_fatture_arrivate_ieri_sdi`: conta le fatture (file_origine distinti) comparse
  ieri, l'importo e le righe da controllare, SOLO se sdi_attivo=true; None
  altrimenti (niente apertura forzata su chi non e' SDI o non ha ricevuto nulla).
- `_fatture_arrivate_frase`: accenno con un paio di numeri (quante + importo), e le
  righe da controllare rimandano alla card sotto — senza diventare un elenco.

Decisione Mattia 22/07 (piano briefing dinamico): Strada A, solo il briefing che
accenna; se un giorno nasce la card SDI dedicata, l'accenno toglie gli importi e
rimanda alla card (regola gia' scritta nel template, non nella logica).
"""
import os
from datetime import date

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

from services.fastapi_worker import _fatture_arrivate_ieri_sdi  # noqa: E402
from services.daily_briefing_service import (  # noqa: E402
    _fatture_arrivate_frase,
    _buona_notizia_bullet,
    _buona_notizia_frase,
)

RID = "rist-offside"
IERI = date(2026, 7, 20)


class _FakeQuery:
    """Query-builder finto: ignora i filtri, restituisce righe fisse. `.single()`
    torna la prima riga (come PostgREST) per la lettura di ristoranti.sdi_attivo."""

    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def lt(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def single(self):
        # PostgREST .single(): una riga sola. Espone data=dict, non lista.
        return _FakeSingle(self._rows[0] if self._rows else {})

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _FakeSingle:
    def __init__(self, row):
        self._row = row

    def execute(self):
        return type("R", (), {"data": self._row})()


class _FakeSB:
    """Instrada la query alla tabella giusta: `ristoranti` -> flag sdi_attivo,
    `fatture` -> le righe fattura."""

    def __init__(self, sdi_attivo=True, fatture_rows=None):
        self._sdi = sdi_attivo
        self._fatture = fatture_rows or []

    def table(self, name):
        if name == "ristoranti":
            return _FakeQuery([{"sdi_attivo": self._sdi}])
        if name == "fatture":
            return _FakeQuery(list(self._fatture))
        return _FakeQuery([])


def _riga(file_origine, totale_riga=0.0, needs_review=False):
    return {
        "file_origine": file_origine,
        "totale_riga": totale_riga,
        "needs_review": needs_review,
    }


# ── _fatture_arrivate_ieri_sdi ───────────────────────────────────────────────

def test_conta_fatture_distinte_e_importo():
    """3 righe su 2 file distinti = 2 fatture; importo = somma dei totali riga."""
    sb = _FakeSB(sdi_attivo=True, fatture_rows=[
        _riga("F1.xml", 100.0),
        _riga("F1.xml", 50.0),
        _riga("F2.xml", 200.0),
    ])
    out = _fatture_arrivate_ieri_sdi(RID, sb, IERI)
    assert out is not None
    assert out["n_fatture"] == 2
    assert out["importo"] == 350
    assert out["righe_da_controllare"] == 0


def test_conta_righe_da_controllare():
    sb = _FakeSB(sdi_attivo=True, fatture_rows=[
        _riga("F1.xml", 100.0, needs_review=True),
        _riga("F1.xml", 50.0, needs_review=False),
        _riga("F2.xml", 200.0, needs_review=True),
    ])
    out = _fatture_arrivate_ieri_sdi(RID, sb, IERI)
    assert out["n_fatture"] == 2
    assert out["righe_da_controllare"] == 2


def test_none_se_non_sdi():
    """Sede non SDI: niente apertura fatture (per loro l'apertura e' l'incasso)."""
    sb = _FakeSB(sdi_attivo=False, fatture_rows=[_riga("F1.xml", 100.0)])
    assert _fatture_arrivate_ieri_sdi(RID, sb, IERI) is None


def test_none_se_nessuna_fattura_ieri():
    """SDI attivo ma ieri non e' arrivato nulla: nessuna apertura forzata."""
    sb = _FakeSB(sdi_attivo=True, fatture_rows=[])
    assert _fatture_arrivate_ieri_sdi(RID, sb, IERI) is None


def test_ignora_righe_senza_file_origine():
    """Righe senza file_origine non contano come fattura (dati sporchi)."""
    sb = _FakeSB(sdi_attivo=True, fatture_rows=[
        _riga(None, 100.0),
        _riga("", 50.0),
    ])
    assert _fatture_arrivate_ieri_sdi(RID, sb, IERI) is None


# ── _fatture_arrivate_frase (accenno) ────────────────────────────────────────

def test_frase_plurale_con_importo_e_righe():
    p = {"tipo": "fatture_arrivate", "n_fatture": 3, "importo": 1240,
         "righe_da_controllare": 2}
    f = _fatture_arrivate_frase(p)
    assert "3 fatture" in f
    assert "1.240" in f  # importo formattato all'italiana
    assert "2 righe" in f
    assert "qui sotto" in f  # rimanda alla card, non elenca


def test_frase_singolare():
    p = {"tipo": "fatture_arrivate", "n_fatture": 1, "importo": 171,
         "righe_da_controllare": 0}
    f = _fatture_arrivate_frase(p)
    assert "una fattura" in f
    assert "171" in f
    # Nessuna riga da controllare -> niente accenno alle righe.
    assert "controllare" not in f


def test_frase_una_riga_da_controllare_singolare():
    p = {"tipo": "fatture_arrivate", "n_fatture": 2, "importo": 500,
         "righe_da_controllare": 1}
    f = _fatture_arrivate_frase(p)
    assert "una riga" in f


def test_frase_vuota_se_zero_fatture():
    assert _fatture_arrivate_frase(
        {"tipo": "fatture_arrivate", "n_fatture": 0, "importo": 0,
         "righe_da_controllare": 0}
    ) == ""


# ── Integrazione con il dispatcher dell'apertura ─────────────────────────────

def test_bullet_e_frase_instradano_su_fatture_arrivate():
    """Sia il bullet (input AI) sia la frase (template) devono riconoscere il
    nuovo tipo e produrre l'accenno, non stringa vuota."""
    p = {"tipo": "fatture_arrivate", "n_fatture": 3, "importo": 1240,
         "righe_da_controllare": 0}
    assert "3 fatture" in _buona_notizia_bullet(p)
    assert "3 fatture" in _buona_notizia_frase(p)
